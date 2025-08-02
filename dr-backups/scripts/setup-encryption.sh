#!/bin/bash

# Disaster Recovery Encryption Setup Script
# Generates encryption keys and sets up secure storage

set -euo pipefail

# Load configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$(dirname "$SCRIPT_DIR")/config"
source "$CONFIG_DIR/dr-config.env"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$DR_BACKUP_DIR/logs/setup.log"
}

# Generate encryption key
generate_encryption_key() {
    log "Generating encryption key..."
    
    if [ -f "$DR_ENCRYPTION_KEY" ]; then
        log "WARNING: Encryption key already exists at $DR_ENCRYPTION_KEY"
        read -p "Do you want to regenerate it? This will make existing backups unreadable! (y/N): " confirm
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            log "Keeping existing encryption key"
            return 0
        fi
    fi
    
    # Generate 32-byte (256-bit) key
    openssl rand -base64 32 > "$DR_ENCRYPTION_KEY"
    chmod 600 "$DR_ENCRYPTION_KEY"
    log "Encryption key generated and saved to $DR_ENCRYPTION_KEY"
}

# Setup AWS CLI
setup_aws_cli() {
    log "Setting up AWS CLI..."
    
    if ! command -v aws &> /dev/null; then
        log "ERROR: AWS CLI is not installed. Please install it first."
        return 1
    fi
    
    if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
        log "WARNING: AWS credentials not set in configuration"
        log "Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in dr-config.env"
        return 1
    fi
    
    # Configure AWS CLI
    aws configure set aws_access_key_id "$AWS_ACCESS_KEY_ID"
    aws configure set aws_secret_access_key "$AWS_SECRET_ACCESS_KEY"
    aws configure set default.region "$DR_CLOUD_REGION"
    
    log "AWS CLI configured successfully"
}

# Create S3 bucket with encryption
setup_s3_bucket() {
    log "Setting up S3 bucket for disaster recovery..."
    
    # Extract bucket name from S3 URL
    BUCKET_NAME=$(echo "$DR_CLOUD_BUCKET" | sed 's|s3://||')
    
    # Check if bucket exists
    if aws s3 ls "s3://$BUCKET_NAME" 2>/dev/null; then
        log "S3 bucket $BUCKET_NAME already exists"
    else
        log "Creating S3 bucket $BUCKET_NAME..."
        aws s3 mb "s3://$BUCKET_NAME" --region "$DR_CLOUD_REGION"
    fi
    
    # Enable versioning
    log "Enabling versioning on S3 bucket..."
    aws s3api put-bucket-versioning \
        --bucket "$BUCKET_NAME" \
        --versioning-configuration Status=Enabled
    
    # Enable server-side encryption
    log "Enabling server-side encryption on S3 bucket..."
    aws s3api put-bucket-encryption \
        --bucket "$BUCKET_NAME" \
        --server-side-encryption-configuration '{
            "Rules": [
                {
                    "ApplyServerSideEncryptionByDefault": {
                        "SSEAlgorithm": "AES256"
                    },
                    "BucketKeyEnabled": true
                }
            ]
        }'
    
    # Set lifecycle policy for cost optimization
    log "Setting lifecycle policy for backup retention..."
    cat > /tmp/lifecycle-policy.json << EOF
{
    "Rules": [
        {
            "ID": "DRBackupLifecycle",
            "Status": "Enabled",
            "Filter": {"Prefix": "backups/"},
            "Transitions": [
                {
                    "Days": 30,
                    "StorageClass": "STANDARD_IA"
                },
                {
                    "Days": 90,
                    "StorageClass": "GLACIER"
                },
                {
                    "Days": 365,
                    "StorageClass": "DEEP_ARCHIVE"
                }
            ],
            "Expiration": {
                "Days": $DR_RETENTION_DAYS
            }
        }
    ]
}
EOF
    
    aws s3api put-bucket-lifecycle-configuration \
        --bucket "$BUCKET_NAME" \
        --lifecycle-configuration file:///tmp/lifecycle-policy.json
    
    rm /tmp/lifecycle-policy.json
    log "S3 bucket setup completed successfully"
}

# Test encryption and cloud connectivity
test_setup() {
    log "Testing encryption and cloud connectivity..."
    
    # Test encryption
    echo "test data" > /tmp/test-encrypt.txt
    KEY=$(cat "$DR_ENCRYPTION_KEY")
    
    # Encrypt test file
    openssl enc -aes-256-cbc -salt -in /tmp/test-encrypt.txt -out /tmp/test-encrypt.enc -k "$KEY"
    
    # Decrypt test file
    openssl enc -d -aes-256-cbc -in /tmp/test-encrypt.enc -out /tmp/test-decrypt.txt -k "$KEY"
    
    if diff /tmp/test-encrypt.txt /tmp/test-decrypt.txt > /dev/null; then
        log "Encryption test: PASSED"
    else
        log "ERROR: Encryption test failed"
        return 1
    fi
    
    # Test cloud upload/download
    BUCKET_NAME=$(echo "$DR_CLOUD_BUCKET" | sed 's|s3://||')
    
    aws s3 cp /tmp/test-encrypt.enc "s3://$BUCKET_NAME/test/test-file.enc"
    aws s3 cp "s3://$BUCKET_NAME/test/test-file.enc" /tmp/test-download.enc
    
    if diff /tmp/test-encrypt.enc /tmp/test-download.enc > /dev/null; then
        log "Cloud storage test: PASSED"
    else
        log "ERROR: Cloud storage test failed"
        return 1
    fi
    
    # Cleanup test files
    rm -f /tmp/test-*.txt /tmp/test-*.enc
    aws s3 rm "s3://$BUCKET_NAME/test/test-file.enc"
    
    log "All tests completed successfully"
}

# Install required tools
install_dependencies() {
    log "Checking and installing required dependencies..."
    
    # Check for required commands
    REQUIRED_COMMANDS=("openssl" "aws" "pg_dump" "psql" "docker" "docker-compose")
    MISSING_COMMANDS=()
    
    for cmd in "${REQUIRED_COMMANDS[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            MISSING_COMMANDS+=("$cmd")
        fi
    done
    
    if [ ${#MISSING_COMMANDS[@]} -gt 0 ]; then
        log "ERROR: Missing required commands: ${MISSING_COMMANDS[*]}"
        log "Please install the missing dependencies before continuing"
        return 1
    fi
    
    log "All required dependencies are installed"
}

# Main setup function
main() {
    log "=== Starting Disaster Recovery Setup ==="
    
    # Create necessary directories
    mkdir -p "$DR_BACKUP_DIR/logs"
    mkdir -p "$DR_BACKUP_DIR/sessions"
    mkdir -p "$(dirname "$DR_ENCRYPTION_KEY")"
    
    # Install dependencies
    install_dependencies
    
    # Generate encryption key
    generate_encryption_key
    
    # Setup cloud storage
    setup_aws_cli
    setup_s3_bucket
    
    # Test the setup
    test_setup
    
    log "=== Disaster Recovery Setup Completed Successfully ==="
    log "Next steps:"
    log "1. Update AWS credentials in dr-config.env if needed"
    log "2. Test the backup system with: ./enhanced-backup.sh"
    log "3. Schedule automated backups with cron"
}

# Check if running with appropriate permissions
if [ "$EUID" -eq 0 ]; then
    log "WARNING: Running as root. Consider using a dedicated backup user."
fi

# Run main function
main "$@"
