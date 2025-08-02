#!/bin/bash

# Installation Validation Script
# Comprehensive validation of DR system installation

set -euo pipefail

# Load configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$(dirname "$SCRIPT_DIR")/config"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Global variables
VALIDATION_ID="validate_install_$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$CONFIG_DIR/../logs/installation-validation-$VALIDATION_ID.log"
ERRORS=0
WARNINGS=0
TESTS_PASSED=0
TESTS_TOTAL=0

# Logging functions
log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
    ((ERRORS++))
}

log_warning() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
    ((WARNINGS++))
}

log_success() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
    ((TESTS_PASSED++))
}

log_info() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ${BLUE}[INFO]${NC} $1" | tee -a "$LOG_FILE"
}

# Test function wrapper
run_test() {
    local test_name="$1"
    local test_function="$2"
    
    ((TESTS_TOTAL++))
    log_info "Running test: $test_name"
    
    if $test_function; then
        log_success "✓ $test_name"
        return 0
    else
        log_error "✗ $test_name"
        return 1
    fi
}

# Test 1: Check directory structure
test_directory_structure() {
    local required_dirs=(
        "$CONFIG_DIR/../"
        "$CONFIG_DIR"
        "$SCRIPT_DIR"
        "$CONFIG_DIR/../logs"
        "$CONFIG_DIR/../sessions"
        "$CONFIG_DIR/../tests"
    )
    
    for dir in "${required_dirs[@]}"; do
        if [ ! -d "$dir" ]; then
            log_error "Required directory missing: $dir"
            return 1
        fi
    done
    
    return 0
}

# Test 2: Check required scripts
test_required_scripts() {
    local required_scripts=(
        "setup-encryption.sh"
        "enhanced-backup.sh"
        "validate-backup.sh"
        "disaster-recovery.sh"
        "dr-monitor.sh"
        "dr-test.sh"
        "setup-automation.sh"
    )
    
    for script in "${required_scripts[@]}"; do
        local script_path="$SCRIPT_DIR/$script"
        if [ ! -f "$script_path" ]; then
            log_error "Required script missing: $script"
            return 1
        fi
        
        if [ ! -x "$script_path" ]; then
            log_warning "Script not executable: $script"
            chmod +x "$script_path" 2>/dev/null || {
                log_error "Cannot make script executable: $script"
                return 1
            }
        fi
    done
    
    return 0
}

# Test 3: Check configuration file
test_configuration() {
    local config_file="$CONFIG_DIR/dr-config.env"
    
    if [ ! -f "$config_file" ]; then
        log_error "Configuration file missing: $config_file"
        return 1
    fi
    
    # Source the configuration
    if ! source "$config_file" 2>/dev/null; then
        log_error "Configuration file has syntax errors"
        return 1
    fi
    
    # Check required variables
    local required_vars=(
        "DR_BACKUP_DIR"
        "PROJECT_ROOT"
        "POSTGRES_HOST"
        "POSTGRES_USER"
        "POSTGRES_PASSWORD"
    )
    
    for var in "${required_vars[@]}"; do
        if [ -z "${!var:-}" ]; then
            log_error "Required configuration variable not set: $var"
            return 1
        fi
    done
    
    return 0
}

# Test 4: Check system dependencies
test_system_dependencies() {
    local required_commands=(
        "openssl"
        "pg_dump"
        "psql"
        "pg_isready"
        "docker"
        "docker-compose"
        "curl"
        "tar"
        "gzip"
    )
    
    local optional_commands=(
        "aws"
        "jq"
        "mail"
    )
    
    # Check required commands
    for cmd in "${required_commands[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            log_error "Required command not found: $cmd"
            return 1
        fi
    done
    
    # Check optional commands (warnings only)
    for cmd in "${optional_commands[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            log_warning "Optional command not found: $cmd"
        fi
    done
    
    return 0
}

# Test 5: Check encryption setup
test_encryption_setup() {
    source "$CONFIG_DIR/dr-config.env" 2>/dev/null || return 1
    
    if [ ! -f "$DR_ENCRYPTION_KEY" ]; then
        log_error "Encryption key file not found: $DR_ENCRYPTION_KEY"
        return 1
    fi
    
    # Check key permissions
    local key_perms
    key_perms=$(stat -c %a "$DR_ENCRYPTION_KEY" 2>/dev/null || stat -f %A "$DR_ENCRYPTION_KEY" 2>/dev/null || echo "unknown")
    
    if [ "$key_perms" != "600" ]; then
        log_warning "Encryption key permissions should be 600, found: $key_perms"
        chmod 600 "$DR_ENCRYPTION_KEY" 2>/dev/null || {
            log_error "Cannot fix encryption key permissions"
            return 1
        }
    fi
    
    # Test encryption/decryption
    local test_data="test encryption data"
    local temp_file="/tmp/encrypt_test_$$"
    local encrypted_file="/tmp/encrypt_test_$$.enc"
    local decrypted_file="/tmp/encrypt_test_$$.dec"
    
    echo "$test_data" > "$temp_file"
    
    local key
    key=$(cat "$DR_ENCRYPTION_KEY")
    
    if openssl enc -aes-256-cbc -salt -in "$temp_file" -out "$encrypted_file" -k "$key" 2>/dev/null; then
        if openssl enc -d -aes-256-cbc -in "$encrypted_file" -out "$decrypted_file" -k "$key" 2>/dev/null; then
            if diff "$temp_file" "$decrypted_file" > /dev/null 2>&1; then
                rm -f "$temp_file" "$encrypted_file" "$decrypted_file"
                return 0
            fi
        fi
    fi
    
    rm -f "$temp_file" "$encrypted_file" "$decrypted_file"
    log_error "Encryption/decryption test failed"
    return 1
}

# Test 6: Check database connectivity
test_database_connectivity() {
    source "$CONFIG_DIR/dr-config.env" 2>/dev/null || return 1
    
    export PGPASSWORD="$POSTGRES_PASSWORD"
    
    # Test connection
    if ! pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" &> /dev/null; then
        log_error "Cannot connect to PostgreSQL server"
        return 1
    fi
    
    # Test database query
    if ! psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_MASTER_DB" \
        -c "SELECT 1;" > /dev/null 2>&1; then
        log_error "Cannot execute queries on PostgreSQL"
        return 1
    fi
    
    return 0
}

# Test 7: Check Docker services
test_docker_services() {
    source "$CONFIG_DIR/dr-config.env" 2>/dev/null || return 1
    
    if [ ! -f "$DOCKER_COMPOSE_FILE" ]; then
        log_error "Docker Compose file not found: $DOCKER_COMPOSE_FILE"
        return 1
    fi
    
    # Change to project directory for docker-compose commands
    local old_pwd="$PWD"
    cd "$PROJECT_ROOT"
    
    # Check if services are running
    if ! docker-compose -f "$DOCKER_COMPOSE_FILE" ps | grep -q "Up"; then
        log_warning "Docker services may not be running"
        cd "$old_pwd"
        return 0  # Not a failure, just a warning
    fi
    
    cd "$old_pwd"
    return 0
}

# Test 8: Check cloud storage (if configured)
test_cloud_storage() {
    source "$CONFIG_DIR/dr-config.env" 2>/dev/null || return 1
    
    if [ -z "$DR_CLOUD_BUCKET" ]; then
        log_info "Cloud storage not configured (optional)"
        return 0
    fi
    
    if ! command -v aws &> /dev/null; then
        log_warning "AWS CLI not found, cannot test cloud storage"
        return 0
    fi
    
    # Test AWS credentials
    if ! aws sts get-caller-identity > /dev/null 2>&1; then
        log_warning "AWS credentials not configured or invalid"
        return 0
    fi
    
    # Test bucket access
    local bucket_name
    bucket_name=$(echo "$DR_CLOUD_BUCKET" | sed 's|s3://||')
    
    if ! aws s3 ls "s3://$bucket_name/" > /dev/null 2>&1; then
        log_warning "Cannot access S3 bucket: $bucket_name"
        return 0
    fi
    
    return 0
}

# Test 9: Check file permissions
test_file_permissions() {
    source "$CONFIG_DIR/dr-config.env" 2>/dev/null || return 1
    
    # Check if backup directory is writable
    if [ ! -w "$DR_BACKUP_DIR" ]; then
        log_error "Backup directory not writable: $DR_BACKUP_DIR"
        return 1
    fi
    
    # Check if we can create test files
    local test_file="$DR_BACKUP_DIR/.write_test_$$"
    if ! echo "test" > "$test_file" 2>/dev/null; then
        log_error "Cannot write to backup directory: $DR_BACKUP_DIR"
        return 1
    fi
    rm -f "$test_file"
    
    return 0
}

# Test 10: Check cron installation
test_cron_installation() {
    # Check if cron service exists
    if ! command -v crontab &> /dev/null; then
        log_warning "Crontab command not found"
        return 0
    fi
    
    # Check for DR cron jobs
    local dr_jobs
    dr_jobs=$(crontab -l 2>/dev/null | grep -c "# DR:" || echo "0")
    
    if [ "$dr_jobs" -eq 0 ]; then
        log_info "No DR cron jobs found (run setup-automation.sh to install)"
        return 0
    fi
    
    log_info "Found $dr_jobs DR cron jobs installed"
    return 0
}

# Test 11: Validate script syntax
test_script_syntax() {
    local scripts=(
        "setup-encryption.sh"
        "enhanced-backup.sh"
        "validate-backup.sh"
        "disaster-recovery.sh"
        "dr-monitor.sh"
        "dr-test.sh"
        "setup-automation.sh"
    )
    
    for script in "${scripts[@]}"; do
        local script_path="$SCRIPT_DIR/$script"
        if ! bash -n "$script_path" 2>/dev/null; then
            log_error "Script has syntax errors: $script"
            return 1
        fi
    done
    
    return 0
}

# Generate validation report
generate_report() {
    local report_file="$CONFIG_DIR/../logs/installation-validation-report.json"
    
    cat > "$report_file" << EOF
{
    "validation_id": "$VALIDATION_ID",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "hostname": "$(hostname)",
    "summary": {
        "total_tests": $TESTS_TOTAL,
        "passed": $TESTS_PASSED,
        "failed": $((TESTS_TOTAL - TESTS_PASSED)),
        "errors": $ERRORS,
        "warnings": $WARNINGS,
        "overall_status": "$( [ $ERRORS -eq 0 ] && echo "PASSED" || echo "FAILED" )"
    },
    "system_info": {
        "os": "$(uname -s)",
        "architecture": "$(uname -m)",
        "shell": "$SHELL",
        "user": "$(whoami)"
    },
    "validation_log": "$LOG_FILE"
}
EOF
    
    log_info "Validation report generated: $report_file"
}

# Main validation function
main() {
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║         Disaster Recovery System Installation Validation    ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo
    
    log_info "Starting installation validation"
    log_info "Validation ID: $VALIDATION_ID"
    
    # Create logs directory if it doesn't exist
    mkdir -p "$(dirname "$LOG_FILE")"
    
    # Run all tests
    run_test "Directory Structure" test_directory_structure
    run_test "Required Scripts" test_required_scripts
    run_test "Configuration File" test_configuration
    run_test "System Dependencies" test_system_dependencies
    run_test "Encryption Setup" test_encryption_setup
    run_test "Database Connectivity" test_database_connectivity
    run_test "Docker Services" test_docker_services
    run_test "Cloud Storage" test_cloud_storage
    run_test "File Permissions" test_file_permissions
    run_test "Cron Installation" test_cron_installation
    run_test "Script Syntax" test_script_syntax
    
    # Generate report
    generate_report
    
    echo
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║                      VALIDATION SUMMARY                     ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo
    echo -e "Total Tests: ${BLUE}$TESTS_TOTAL${NC}"
    echo -e "Passed: ${GREEN}$TESTS_PASSED${NC}"
    echo -e "Failed: ${RED}$((TESTS_TOTAL - TESTS_PASSED))${NC}"
    echo -e "Errors: ${RED}$ERRORS${NC}"
    echo -e "Warnings: ${YELLOW}$WARNINGS${NC}"
    echo
    
    if [ $ERRORS -eq 0 ]; then
        echo -e "${GREEN}✓ VALIDATION PASSED${NC} - DR system is properly installed"
        echo
        echo -e "${BLUE}Next Steps:${NC}"
        echo "1. Review any warnings above"
        echo "2. Run your first backup: ./scripts/enhanced-backup.sh"
        echo "3. Setup automation: ./scripts/setup-automation.sh"
        echo "4. Read the documentation: README.md"
        echo
        exit 0
    else
        echo -e "${RED}✗ VALIDATION FAILED${NC} - Please fix the errors above"
        echo
        echo -e "${BLUE}Common Solutions:${NC}"
        echo "1. Install missing dependencies"
        echo "2. Fix configuration in config/dr-config.env"
        echo "3. Run setup-encryption.sh for encryption setup"
        echo "4. Check database connectivity"
        echo
        echo -e "Log file: $LOG_FILE"
        echo
        exit 1
    fi
}

# Run main function
main "$@"
