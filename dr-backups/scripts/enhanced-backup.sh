#!/bin/bash

# Enhanced Disaster Recovery Backup Script
# Comprehensive backup system with encryption, cloud sync, and validation

set -euo pipefail

# Load configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$(dirname "$SCRIPT_DIR")/config"
source "$CONFIG_DIR/dr-config.env"

# Global variables
SESSION_ID="backup_$(date +%Y%m%d_%H%M%S)_$$"
SESSION_DIR="$DR_SESSION_DIR/$SESSION_ID"
LOG_FILE="$DR_BACKUP_DIR/logs/backup-$SESSION_ID.log"
BACKUP_MANIFEST="$SESSION_DIR/backup-manifest.json"
BACKUP_ERRORS=0
BACKUP_WARNINGS=0

# Logging functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $1" | tee -a "$LOG_FILE" >&2
    ((BACKUP_ERRORS++))
}

log_warning() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WARNING] $1" | tee -a "$LOG_FILE"
    ((BACKUP_WARNINGS++))
}

log_debug() {
    if [ "$DR_DEBUG_MODE" = "true" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [DEBUG] $1" | tee -a "$LOG_FILE"
    fi
}

# Error handling
cleanup_on_error() {
    log_error "Backup failed. Cleaning up session: $SESSION_ID"
    if [ "$DR_KEEP_TEMP_FILES" != "true" ]; then
        rm -rf "$SESSION_DIR"
    fi
    send_notification "ERROR" "Backup failed for session $SESSION_ID. Check logs: $LOG_FILE"
    exit 1
}

trap cleanup_on_error ERR

# Initialize backup session
initialize_session() {
    log "Initializing backup session: $SESSION_ID"
    
    # Create session directory structure
    mkdir -p "$SESSION_DIR"/{databases,filestore,configs,metadata}
    mkdir -p "$DR_BACKUP_DIR/logs"
    
    # Set process priority
    if [ -n "$DR_CPU_NICE_LEVEL" ]; then
        renice "$DR_CPU_NICE_LEVEL" $$
    fi
    
    if [ -n "$DR_IO_NICE_LEVEL" ] && command -v ionice &> /dev/null; then
        ionice -c 2 -n "$DR_IO_NICE_LEVEL" $$
    fi
    
    log "Session initialized successfully"
}

# Create backup manifest
create_manifest() {
    local start_time="$1"
    local end_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    
    cat > "$BACKUP_MANIFEST" << EOF
{
    "session_id": "$SESSION_ID",
    "backup_type": "full",
    "start_time": "$start_time",
    "end_time": "$end_time",
    "hostname": "$(hostname)",
    "project_root": "$PROJECT_ROOT",
    "postgres_host": "$POSTGRES_HOST",
    "encryption": {
        "enabled": true,
        "cipher": "$DR_ENCRYPTION_CIPHER",
        "key_file": "$DR_ENCRYPTION_KEY"
    },
    "databases": [],
    "filestore": {},
    "configurations": [],
    "metadata": {
        "errors": $BACKUP_ERRORS,
        "warnings": $BACKUP_WARNINGS,
        "retention_days": $DR_RETENTION_DAYS
    }
}
EOF
    
    log "Backup manifest created"
}

# Update manifest with database info
update_manifest_database() {
    local db_name="$1"
    local backup_file="$2"
    local size="$3"
    local checksum="$4"
    
    # Use jq to update the manifest
    if command -v jq &> /dev/null; then
        local temp_manifest=$(mktemp)
        jq --arg db "$db_name" --arg file "$backup_file" --arg size "$size" --arg checksum "$checksum" \
           '.databases += [{"name": $db, "file": $file, "size": $size, "checksum": $checksum}]' \
           "$BACKUP_MANIFEST" > "$temp_manifest"
        mv "$temp_manifest" "$BACKUP_MANIFEST"
    fi
}

# Get list of tenant databases
get_tenant_databases() {
    log "Discovering tenant databases..."
    
    export PGPASSWORD="$POSTGRES_PASSWORD"
    
    local databases
    databases=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_MASTER_DB" -t -c \
        "SELECT datname FROM pg_database WHERE datistemplate = false AND datname != 'postgres' AND datname LIKE 'kdoo_%';" | \
        grep -v "^$" | sed 's/^ *//' | sed 's/ *$//')
    
    if [ -z "$databases" ]; then
        log_warning "No tenant databases found"
        return 1
    fi
    
    log "Found tenant databases: $(echo "$databases" | tr '\n' ' ')"
    echo "$databases"
}

# Backup individual database with encryption
backup_database() {
    local db_name="$1"
    local backup_file="$SESSION_DIR/databases/${db_name}.sql.enc"
    local temp_file="$SESSION_DIR/databases/${db_name}.sql"
    
    log "Starting backup of database: $db_name"
    
    export PGPASSWORD="$POSTGRES_PASSWORD"
    
    # Create database dump
    if ! pg_dump -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$db_name" \
        --verbose --clean --no-owner --no-privileges --format=custom > "$temp_file"; then
        log_error "Failed to create dump for database: $db_name"
        return 1
    fi
    
    # Compress and encrypt the backup
    local key
    key=$(cat "$DR_ENCRYPTION_KEY")
    
    if ! openssl enc -aes-256-cbc -salt -in "$temp_file" -out "$backup_file" -k "$key"; then
        log_error "Failed to encrypt backup for database: $db_name"
        rm -f "$temp_file"
        return 1
    fi
    
    # Calculate checksum and size
    local size checksum
    size=$(stat -f%z "$backup_file" 2>/dev/null || stat -c%s "$backup_file" 2>/dev/null || echo "0")
    checksum=$(sha256sum "$backup_file" | cut -d' ' -f1)
    
    # Update manifest
    update_manifest_database "$db_name" "$(basename "$backup_file")" "$size" "$checksum"
    
    # Clean up temporary file
    rm -f "$temp_file"
    
    log "Successfully backed up database: $db_name (size: $size bytes)"
    return 0
}

# Backup file storage with compression and encryption
backup_filestore() {
    log "Starting filestore backup..."
    
    local filestore_archive="$SESSION_DIR/filestore/filestore.tar.gz.enc"
    local temp_archive="$SESSION_DIR/filestore/filestore.tar.gz"
    
    if [ ! -d "$ODOO_FILESTORE_PATH" ]; then
        log_warning "Filestore directory not found: $ODOO_FILESTORE_PATH"
        return 1
    fi
    
    # Create compressed archive
    if ! tar -czf "$temp_archive" -C "$ODOO_FILESTORE_PATH" .; then
        log_error "Failed to create filestore archive"
        return 1
    fi
    
    # Encrypt the archive
    local key
    key=$(cat "$DR_ENCRYPTION_KEY")
    
    if ! openssl enc -aes-256-cbc -salt -in "$temp_archive" -out "$filestore_archive" -k "$key"; then
        log_error "Failed to encrypt filestore archive"
        rm -f "$temp_archive"
        return 1
    fi
    
    # Calculate checksum and size
    local size checksum
    size=$(stat -f%z "$filestore_archive" 2>/dev/null || stat -c%s "$filestore_archive" 2>/dev/null || echo "0")
    checksum=$(sha256sum "$filestore_archive" | cut -d' ' -f1)
    
    # Update manifest with jq if available
    if command -v jq &> /dev/null; then
        local temp_manifest=$(mktemp)
        jq --arg file "$(basename "$filestore_archive")" --arg size "$size" --arg checksum "$checksum" \
           '.filestore = {"file": $file, "size": $size, "checksum": $checksum}' \
           "$BACKUP_MANIFEST" > "$temp_manifest"
        mv "$temp_manifest" "$BACKUP_MANIFEST"
    fi
    
    # Clean up temporary file
    rm -f "$temp_archive"
    
    log "Successfully backed up filestore (size: $size bytes)"
    return 0
}

# Backup configurations
backup_configurations() {
    log "Starting configuration backup..."
    
    local config_files=(
        "$DOCKER_COMPOSE_FILE"
        "$CONFIG_DIR/dr-config.env"
        "$NGINX_CONFIG_PATH"
        "$SSL_CERTS_PATH"
    )
    
    for config_path in "${config_files[@]}"; do
        if [ -e "$config_path" ]; then
            local config_name
            config_name=$(basename "$config_path")
            local backup_file="$SESSION_DIR/configs/${config_name}.tar.gz.enc"
            local temp_file="$SESSION_DIR/configs/${config_name}.tar.gz"
            
            # Create archive
            if [ -d "$config_path" ]; then
                tar -czf "$temp_file" -C "$(dirname "$config_path")" "$(basename "$config_path")"
            else
                tar -czf "$temp_file" -C "$(dirname "$config_path")" "$(basename "$config_path")"
            fi
            
            # Encrypt
            local key
            key=$(cat "$DR_ENCRYPTION_KEY")
            openssl enc -aes-256-cbc -salt -in "$temp_file" -out "$backup_file" -k "$key"
            
            rm -f "$temp_file"
            log "Backed up configuration: $config_name"
        else
            log_warning "Configuration not found: $config_path"
        fi
    done
    
    log "Configuration backup completed"
}

# Validate backup integrity
validate_backup() {
    log "Validating backup integrity..."
    
    local validation_errors=0
    
    # Validate databases
    for db_backup in "$SESSION_DIR"/databases/*.sql.enc; do
        if [ -f "$db_backup" ]; then
            local db_name
            db_name=$(basename "$db_backup" .sql.enc)
            
            # Test decryption
            local key
            key=$(cat "$DR_ENCRYPTION_KEY")
            local temp_file="$SESSION_DIR/test_decrypt_$db_name.sql"
            
            if openssl enc -d -aes-256-cbc -in "$db_backup" -out "$temp_file" -k "$key" 2>/dev/null; then
                # Test if it's a valid PostgreSQL dump
                if head -n 10 "$temp_file" | grep -q "PostgreSQL database dump"; then
                    log "Database backup validation passed: $db_name"
                else
                    log_error "Database backup validation failed: $db_name (not a valid PostgreSQL dump)"
                    ((validation_errors++))
                fi
                rm -f "$temp_file"
            else
                log_error "Database backup validation failed: $db_name (decryption failed)"
                ((validation_errors++))
            fi
        fi
    done
    
    # Validate filestore
    if [ -f "$SESSION_DIR/filestore/filestore.tar.gz.enc" ]; then
        local key
        key=$(cat "$DR_ENCRYPTION_KEY")
        local temp_file="$SESSION_DIR/test_filestore.tar.gz"
        
        if openssl enc -d -aes-256-cbc -in "$SESSION_DIR/filestore/filestore.tar.gz.enc" -out "$temp_file" -k "$key" 2>/dev/null; then
            if tar -tzf "$temp_file" > /dev/null 2>&1; then
                log "Filestore backup validation passed"
            else
                log_error "Filestore backup validation failed (not a valid tar archive)"
                ((validation_errors++))
            fi
            rm -f "$temp_file"
        else
            log_error "Filestore backup validation failed (decryption failed)"
            ((validation_errors++))
        fi
    fi
    
    if [ $validation_errors -eq 0 ]; then
        log "All backup validations passed"
        return 0
    else
        log_error "Backup validation failed with $validation_errors errors"
        return 1
    fi
}

# Upload to cloud storage
upload_to_cloud() {
    log "Uploading backup to cloud storage..."
    
    local upload_errors=0
    local destinations
    IFS=',' read -ra destinations <<< "$DR_BACKUP_DESTINATIONS"
    
    for dest in "${destinations[@]}"; do
        dest=$(echo "$dest" | tr -d ' ')
        case "$dest" in
            "aws")
                upload_to_aws || ((upload_errors++))
                ;;
            "gdrive")
                upload_to_gdrive || ((upload_errors++))
                ;;
            *)
                log_warning "Unknown backup destination: $dest"
                ;;
        esac
    done
    
    if [ $upload_errors -eq 0 ]; then
        log "Successfully uploaded backup to all destinations"
        return 0
    else
        log_error "Failed to upload to $upload_errors destination(s)"
        return 1
    fi
}

# Upload to AWS S3
upload_to_aws() {
    log "Uploading backup to AWS S3..."
    
    if [ -z "$DR_CLOUD_BUCKET" ]; then
        log_warning "AWS S3 bucket not configured"
        return 0
    fi
    
    local bucket_name
    bucket_name=$(echo "$DR_CLOUD_BUCKET" | sed 's|s3://||')
    local cloud_path="backups/$SESSION_ID"
    
    # Upload session directory
    if aws s3 sync "$SESSION_DIR" "s3://$bucket_name/$cloud_path" \
        --exclude "*" --include "*.enc" --include "*.json" \
        --storage-class STANDARD --server-side-encryption AES256; then
        
        log "Successfully uploaded backup to AWS S3: s3://$bucket_name/$cloud_path"
        
        # Update manifest with cloud info
        if command -v jq &> /dev/null; then
            local temp_manifest=$(mktemp)
            jq --arg cloud_path "$cloud_path" --arg bucket "$bucket_name" \
               '.cloud.aws = {"bucket": $bucket, "path": $cloud_path, "uploaded": true}' \
               "$BACKUP_MANIFEST" > "$temp_manifest"
            mv "$temp_manifest" "$BACKUP_MANIFEST"
            
            # Re-upload updated manifest
            aws s3 cp "$BACKUP_MANIFEST" "s3://$bucket_name/$cloud_path/"
        fi
        
        return 0
    else
        log_error "Failed to upload backup to AWS S3"
        return 1
    fi
}

# Upload to Google Drive
upload_to_gdrive() {
    log "Uploading backup to Google Drive..."
    
    if [ -z "$GDRIVE_FOLDER_NAME" ]; then
        log_warning "Google Drive not configured"
        return 0
    fi
    
    # Check if Python and required modules are available
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 not found, cannot upload to Google Drive"
        return 1
    fi
    
    local gdrive_script="$SCRIPT_DIR/gdrive-integration.py"
    if [ ! -f "$gdrive_script" ]; then
        log_error "Google Drive integration script not found: $gdrive_script"
        return 1
    fi
    
    # Upload each encrypted file
    local upload_count=0
    local upload_errors=0
    
    for file_path in "$SESSION_DIR"/**/*.enc "$SESSION_DIR"/*.json; do
        if [ -f "$file_path" ]; then
            local file_name
            file_name=$(basename "$file_path")
            local remote_name="$SESSION_ID/$file_name"
            
            if python3 "$gdrive_script" --config "$CONFIG_DIR/dr-config.env" --upload "$file_path" --remote-name "$remote_name"; then
                log "Uploaded to Google Drive: $file_name"
                ((upload_count++))
            else
                log_error "Failed to upload to Google Drive: $file_name"
                ((upload_errors++))
            fi
        fi
    done
    
    if [ $upload_errors -eq 0 ] && [ $upload_count -gt 0 ]; then
        log "Successfully uploaded $upload_count files to Google Drive"
        
        # Update manifest with Google Drive info
        if command -v jq &> /dev/null; then
            local temp_manifest=$(mktemp)
            jq --arg folder "$GDRIVE_FOLDER_NAME" --arg session "$SESSION_ID" \
               '.cloud.gdrive = {"folder": $folder, "session_path": $session, "uploaded": true, "file_count": $upload_count}' \
               "$BACKUP_MANIFEST" > "$temp_manifest"
            mv "$temp_manifest" "$BACKUP_MANIFEST"
        fi
        
        return 0
    else
        log_error "Google Drive upload failed: $upload_errors errors, $upload_count successful"
        return 1
    fi
}

# Cleanup old local backups
cleanup_old_backups() {
    log "Cleaning up old local backups..."
    
    local cutoff_date
    cutoff_date=$(date -d "$DR_LOCAL_RETENTION_DAYS days ago" +%Y%m%d || date -v-"$DR_LOCAL_RETENTION_DAYS"d +%Y%m%d)
    
    find "$DR_SESSION_DIR" -type d -name "backup_*" | while read -r session_dir; do
        local session_date
        session_date=$(basename "$session_dir" | cut -d'_' -f2)
        
        if [ "$session_date" \< "$cutoff_date" ]; then
            log "Removing old backup session: $(basename "$session_dir")"
            rm -rf "$session_dir"
        fi
    done
    
    log "Local cleanup completed"
}

# Send notification
send_notification() {
    local status="$1"
    local message="$2"
    
    log "Sending notification: [$status] $message"
    
    # Email notification
    if [ -n "$DR_NOTIFICATION_EMAIL" ] && command -v mail &> /dev/null; then
        echo "$message" | mail -s "DR Backup [$status] - $SESSION_ID" "$DR_NOTIFICATION_EMAIL"
    fi
    
    # Webhook notification (Slack, etc.)
    if [ -n "$DR_WEBHOOK_URL" ]; then
        local payload
        payload=$(cat << EOF
{
    "text": "DR Backup [$status]",
    "attachments": [
        {
            "color": "$( [ "$status" = "SUCCESS" ] && echo "good" || echo "danger" )",
            "fields": [
                {"title": "Session ID", "value": "$SESSION_ID", "short": true},
                {"title": "Status", "value": "$status", "short": true},
                {"title": "Message", "value": "$message", "short": false},
                {"title": "Errors", "value": "$BACKUP_ERRORS", "short": true},
                {"title": "Warnings", "value": "$BACKUP_WARNINGS", "short": true}
            ]
        }
    ]
}
EOF
)
        curl -X POST -H 'Content-type: application/json' --data "$payload" "$DR_WEBHOOK_URL" || true
    fi
}

# Generate status report
generate_status_report() {
    local status_file="$DR_BACKUP_DIR/logs/backup-status.json"
    
    cat > "$status_file" << EOF
{
    "last_backup": {
        "session_id": "$SESSION_ID",
        "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
        "status": "$( [ $BACKUP_ERRORS -eq 0 ] && echo "success" || echo "failed" )",
        "errors": $BACKUP_ERRORS,
        "warnings": $BACKUP_WARNINGS,
        "log_file": "$LOG_FILE"
    },
    "system": {
        "hostname": "$(hostname)",
        "disk_usage": "$(df "$DR_BACKUP_DIR" | tail -1 | awk '{print $5}' | sed 's/%//')",
        "backup_size": "$(du -sh "$SESSION_DIR" 2>/dev/null | cut -f1 || echo "unknown")"
    }
}
EOF
    
    log "Status report generated: $status_file"
}

# Main backup function
main() {
    local start_time
    start_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    
    log "=== Starting Enhanced Disaster Recovery Backup ==="
    log "Session ID: $SESSION_ID"
    log "Configuration: $CONFIG_DIR/dr-config.env"
    
    # Initialize
    initialize_session
    create_manifest "$start_time"
    
    # Check prerequisites
    if [ ! -f "$DR_ENCRYPTION_KEY" ]; then
        log_error "Encryption key not found: $DR_ENCRYPTION_KEY"
        log_error "Run setup-encryption.sh first"
        exit 1
    fi
    
    # Backup databases
    log "Starting database backups..."
    local databases
    if databases=$(get_tenant_databases); then
        while IFS= read -r db_name; do
            if [ -n "$db_name" ]; then
                backup_database "$db_name"
            fi
        done <<< "$databases"
    fi
    
    # Backup filestore
    backup_filestore
    
    # Backup configurations
    backup_configurations
    
    # Validate backups
    if [ "$DR_VERIFY_BACKUPS" = "true" ]; then
        validate_backup
    fi
    
    # Upload to cloud
    upload_to_cloud
    
    # Cleanup old backups
    cleanup_old_backups
    
    # Update manifest with final status
    local end_time
    end_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    
    if command -v jq &> /dev/null; then
        local temp_manifest=$(mktemp)
        jq --arg end_time "$end_time" --arg status "$( [ $BACKUP_ERRORS -eq 0 ] && echo "success" || echo "failed" )" \
           '.end_time = $end_time | .metadata.status = $status' \
           "$BACKUP_MANIFEST" > "$temp_manifest"
        mv "$temp_manifest" "$BACKUP_MANIFEST"
    fi
    
    # Generate status report
    generate_status_report
    
    # Send notification
    if [ $BACKUP_ERRORS -eq 0 ]; then
        log "=== Backup completed successfully ==="
        send_notification "SUCCESS" "Backup completed successfully. Session: $SESSION_ID, Warnings: $BACKUP_WARNINGS"
        exit 0
    else
        log "=== Backup completed with errors ==="
        send_notification "ERROR" "Backup completed with $BACKUP_ERRORS errors and $BACKUP_WARNINGS warnings. Session: $SESSION_ID"
        exit 1
    fi
}

# Check prerequisites
if ! command -v pg_dump &> /dev/null; then
    echo "ERROR: pg_dump not found. Please install PostgreSQL client tools."
    exit 1
fi

if ! command -v openssl &> /dev/null; then
    echo "ERROR: openssl not found. Please install OpenSSL."
    exit 1
fi

if ! command -v aws &> /dev/null; then
    echo "ERROR: aws CLI not found. Please install AWS CLI."
    exit 1
fi

# Run main function
main "$@"
