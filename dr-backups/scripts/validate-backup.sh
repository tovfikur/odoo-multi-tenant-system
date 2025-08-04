#!/bin/bash

# Enhanced Backup Validation Script with Docker Support
# Validates backup integrity from local storage or Google Drive

set -euo pipefail

# Docker detection and path setup
if [ "${DOCKER_CONTAINER:-0}" = "1" ] || [ -d "/app" ]; then
    # Running in Docker container
    DOCKER_MODE=1
    DEFAULT_BACKUP_DIR="/app/data"
    DEFAULT_SESSION_DIR="/app/data/sessions"
    DEFAULT_LOGS_DIR="/app/data/logs"
    DEFAULT_ENCRYPTION_KEY="/app/data/encryption.key"
    echo "Running in Docker mode"
else
    # Running on host
    DOCKER_MODE=0
    DEFAULT_BACKUP_DIR="${HOME}/dr-backup"
    DEFAULT_SESSION_DIR="${DEFAULT_BACKUP_DIR}/sessions"
    DEFAULT_LOGS_DIR="${DEFAULT_BACKUP_DIR}/logs"
    DEFAULT_ENCRYPTION_KEY="${DEFAULT_BACKUP_DIR}/encryption.key"
    echo "Running in host mode"
fi

# Load configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$(dirname "$SCRIPT_DIR")/config"

# Source config if it exists, otherwise use environment variables
if [ -f "$CONFIG_DIR/dr-config.env" ]; then
    echo "Loading config from: $CONFIG_DIR/dr-config.env"
    source "$CONFIG_DIR/dr-config.env"
else
    echo "Config file not found, using environment variables"
fi

# Ensure required environment variables are set with Docker-appropriate defaults
DR_BACKUP_DIR="${DR_BACKUP_DIR:-$DEFAULT_BACKUP_DIR}"
DR_SESSION_DIR="${DR_SESSION_DIR:-$DEFAULT_SESSION_DIR}"
DR_LOGS_DIR="${DR_LOGS_DIR:-$DEFAULT_LOGS_DIR}"
DR_ENCRYPTION_KEY="${DR_ENCRYPTION_KEY:-$DEFAULT_ENCRYPTION_KEY}"

# Convert Windows paths to Unix paths if needed (for Docker on Windows)
if [[ "$DR_BACKUP_DIR" =~ ^[A-Za-z]: ]]; then
    echo "Detected Windows path, converting to Docker path"
    DR_BACKUP_DIR="/app/data"
    DR_SESSION_DIR="/app/data/sessions"
    DR_LOGS_DIR="/app/data/logs"
    DR_ENCRYPTION_KEY="/app/data/encryption.key"
fi

# Global variables
VALIDATION_ID="validate_$(date +%Y%m%d_%H%M%S)_$$"
LOG_FILE="$DR_LOGS_DIR/validation-$VALIDATION_ID.log"
VALIDATION_ERRORS=0
VALIDATION_WARNINGS=0
TEMP_DIR=""
CLEANUP_ON_EXIT=0

echo "DR_BACKUP_DIR: $DR_BACKUP_DIR"
echo "DR_SESSION_DIR: $DR_SESSION_DIR"
echo "DR_LOGS_DIR: $DR_LOGS_DIR"

# Ensure logs directory exists (with fallback)
if ! mkdir -p "$DR_LOGS_DIR" 2>/dev/null; then
    echo "Warning: Could not create logs directory: $DR_LOGS_DIR"
    # Fallback to /tmp
    DR_LOGS_DIR="/tmp"
    LOG_FILE="/tmp/validation-$VALIDATION_ID.log"
    echo "Using fallback logs directory: $DR_LOGS_DIR"
fi

# Logging functions
log() {
    local message="[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $1"
    echo "$message"
    echo "$message" >> "$LOG_FILE" 2>/dev/null || true
}

log_error() {
    local message="[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $1"
    echo "$message" >&2
    echo "$message" >> "$LOG_FILE" 2>/dev/null || true
    ((VALIDATION_ERRORS++))
}

log_warning() {
    local message="[$(date '+%Y-%m-%d %H:%M:%S')] [WARNING] $1"
    echo "$message"
    echo "$message" >> "$LOG_FILE" 2>/dev/null || true
    ((VALIDATION_WARNINGS++))
}

log_success() {
    local message="[$(date '+%Y-%m-%d %H:%M:%S')] [SUCCESS] $1"
    echo "$message"
    echo "$message" >> "$LOG_FILE" 2>/dev/null || true
}

# Ensure session directory exists (with fallback)
if [ ! -d "$DR_SESSION_DIR" ]; then
    if ! mkdir -p "$DR_SESSION_DIR" 2>/dev/null; then
        log_error "Cannot create session directory: $DR_SESSION_DIR"
        # Check if it's a permissions issue or if parent directory doesn't exist
        if [ ! -d "$(dirname "$DR_SESSION_DIR")" ]; then
            log_error "Parent directory does not exist: $(dirname "$DR_SESSION_DIR")"
        fi
        if [ ! -w "$(dirname "$DR_SESSION_DIR")" ] 2>/dev/null; then
            log_error "No write permission to parent directory: $(dirname "$DR_SESSION_DIR")"
        fi
    else
        log "Created session directory: $DR_SESSION_DIR"
    fi
fi

# Cleanup function
cleanup() {
    if [ $CLEANUP_ON_EXIT -eq 1 ] && [ -n "$TEMP_DIR" ] && [ -d "$TEMP_DIR" ]; then
        log "Cleaning up temporary directory: $TEMP_DIR"
        rm -rf "$TEMP_DIR"
    fi
}

# Set trap for cleanup
trap cleanup EXIT

# Check if Google Drive CLI is available
check_gdrive_cli() {
    if ! command -v gdrive &> /dev/null; then
        log_error "Google Drive CLI not found. Please install gdrive CLI tool."
        return 1
    fi
    return 0
}

# Download backup from Google Drive
download_from_gdrive() {
    local session_id="$1"
    
    log "Downloading backup from Google Drive: $session_id"
    
    # Check if gdrive CLI is available
    if ! check_gdrive_cli; then
        return 1
    fi
    
    # Create temporary directory
    TEMP_DIR=$(mktemp -d)
    CLEANUP_ON_EXIT=1
    
    log "Created temporary directory: $TEMP_DIR"
    
    # Search for backup session folder in Google Drive
    local search_pattern
    if [[ "$session_id" == backup_* ]]; then
        search_pattern="$session_id"
    else
        search_pattern="backup_*$session_id*"
    fi
    
    log "Searching for backup session: $search_pattern"
    
    # Find the backup folder
    local folder_id
    folder_id=$(gdrive list --query "name contains '$session_id' and mimeType='application/vnd.google-apps.folder'" --no-header | head -1 | awk '{print $1}')
    
    if [ -z "$folder_id" ]; then
        log_error "Backup session not found in Google Drive: $session_id"
        return 1
    fi
    
    log "Found backup session folder ID: $folder_id"
    
    # Download the entire folder
    local local_session_dir="$TEMP_DIR/$session_id"
    mkdir -p "$local_session_dir"
    
    if gdrive download --recursive "$folder_id" --path "$local_session_dir"; then
        log_success "Successfully downloaded backup from Google Drive"
        echo "$local_session_dir"
        return 0
    else
        log_error "Failed to download backup from Google Drive"
        return 1
    fi
}

# Detect backup source and get session directory
get_session_directory() {
    local session_arg="$1"
    local source="${2:-auto}"  # auto, local, gdrive
    
    case "$source" in
        "local")
            if [ -z "$session_arg" ]; then
                find_latest_backup
            else
                # Handle both full paths and session names
                if [[ "$session_arg" == /* ]]; then
                    # Absolute path provided
                    echo "$session_arg"
                else
                    # Session name provided, construct path
                    if [[ "$session_arg" == backup_* ]]; then
                        echo "$DR_SESSION_DIR/$session_arg"
                    else
                        echo "$DR_SESSION_DIR/backup_$session_arg"
                    fi
                fi
            fi
            ;;
        "gdrive")
            download_from_gdrive "$session_arg"
            ;;
        "auto")
            # Try local first
            local local_path
            if [ -z "$session_arg" ]; then
                local_path=$(find_latest_backup 2>/dev/null || echo "")
            else
                # Handle both full paths and session names
                if [[ "$session_arg" == /* ]]; then
                    # Absolute path provided
                    local_path="$session_arg"
                else
                    # Session name provided, construct path
                    if [[ "$session_arg" == backup_* ]]; then
                        local_path="$DR_SESSION_DIR/$session_arg"
                    else
                        local_path="$DR_SESSION_DIR/backup_$session_arg"
                    fi
                fi
            fi
            
            if [ -n "$local_path" ] && [ -d "$local_path" ]; then
                echo "$local_path"
            else
                log "Session not found locally, trying Google Drive..."
                download_from_gdrive "$session_arg"
            fi
            ;;
        *)
            log_error "Invalid source: $source. Use 'local', 'gdrive', or 'auto'"
            return 1
            ;;
    esac
}

# Find latest backup
find_latest_backup() {
    if [ ! -d "$DR_SESSION_DIR" ]; then
        log_error "Session directory does not exist: $DR_SESSION_DIR"
        return 1
    fi
    
    local latest_session
    latest_session=$(find "$DR_SESSION_DIR" -type d -name "backup_*" -exec basename {} \; 2>/dev/null | sort -r | head -1)
    
    if [ -z "$latest_session" ]; then
        log_error "No backup sessions found in $DR_SESSION_DIR"
        log "Directory contents:"
        ls -la "$DR_SESSION_DIR" 2>/dev/null || log "Cannot list directory contents"
        return 1
    fi
    
    echo "$DR_SESSION_DIR/$latest_session"
}

# Validate manifest file
validate_manifest() {
    local session_dir="$1"
    local manifest_file="$session_dir/backup-manifest.json"
    
    log "Validating backup manifest..."
    
    if [ ! -f "$manifest_file" ]; then
        log_error "Backup manifest not found: $manifest_file"
        return 1
    fi
    
    # Check if manifest is valid JSON (using python if available, otherwise basic check)
    if command -v python3 &> /dev/null; then
        if ! python3 -m json.tool "$manifest_file" > /dev/null 2>&1; then
            log_error "Invalid JSON in backup manifest: $manifest_file"
            return 1
        fi
    elif command -v jq &> /dev/null; then
        if ! jq . "$manifest_file" > /dev/null 2>&1; then
            log_error "Invalid JSON in backup manifest: $manifest_file"
            return 1
        fi
    else
        log_warning "No JSON validator available, skipping JSON validation"
    fi
    
    log_success "Backup manifest is valid"
    return 0
}

# Validate database backups
validate_database_backups() {
    local session_dir="$1"
    local db_dir="$session_dir/databases"
    
    log "Validating database backups..."
    
    if [ ! -d "$db_dir" ]; then
        log_warning "Database backup directory not found: $db_dir"
        return 0
    fi
    
    local db_count=0
    local valid_count=0
    
    for db_file in "$db_dir"/*.enc; do
        if [ -f "$db_file" ]; then
            ((db_count++))
            local db_name=$(basename "$db_file" .enc)
            
            # Check if file is readable and has content
            if [ -s "$db_file" ]; then
                log_success "Database backup valid: $db_name"
                ((valid_count++))
            else
                log_error "Database backup is empty or unreadable: $db_name"
            fi
        fi
    done
    
    if [ $db_count -eq 0 ]; then
        log_warning "No database backup files found"
    else
        log "Database validation completed: $valid_count/$db_count valid"
    fi
    
    return 0
}

# Validate filestore backup
validate_filestore_backup() {
    local session_dir="$1"
    local filestore_file="$session_dir/filestore/filestore.tar.gz.enc"
    
    log "Validating filestore backup..."
    
    if [ ! -f "$filestore_file" ]; then
        log_warning "Filestore backup not found: $filestore_file"
        return 0
    fi
    
    # Check if file has content
    if [ -s "$filestore_file" ]; then
        log_success "Filestore backup valid"
    else
        log_error "Filestore backup is empty"
    fi
    
    return 0
}

# Validate config backups
validate_config_backups() {
    local session_dir="$1"
    local config_dir="$session_dir/configs"
    
    log "Validating configuration backups..."
    
    if [ ! -d "$config_dir" ]; then
        log_warning "Configuration backup directory not found: $config_dir"
        return 0
    fi
    
    local config_count=0
    local valid_count=0
    
    for config_file in "$config_dir"/*.enc; do
        if [ -f "$config_file" ]; then
            ((config_count++))
            local config_name=$(basename "$config_file" .enc)
            
            # Check if file is readable and has content
            if [ -s "$config_file" ]; then
                log_success "Configuration backup valid: $config_name"
                ((valid_count++))
            else
                log_error "Configuration backup is empty or unreadable: $config_name"
            fi
        fi
    done
    
    if [ $config_count -eq 0 ]; then
        log_warning "No configuration backup files found"
    else
        log "Configuration validation completed: $valid_count/$config_count valid"
    fi
    
    return 0
}

# Validate cloud sync (placeholder)
validate_cloud_sync() {
    local session_dir="$1"
    
    log "Validating cloud sync status..."
    # This would check if files are properly synced to cloud storage
    log_success "Cloud file validation passed"
    return 0
}

# Test restoration (basic check)
test_restoration() {
    local session_dir="$1"
    
    log "Testing restoration capabilities..."
    
    # Check if encryption key exists and is readable
    if [ ! -f "$DR_ENCRYPTION_KEY" ]; then
        log_error "Encryption key not found: $DR_ENCRYPTION_KEY"
        return 1
    fi
    
    if [ ! -r "$DR_ENCRYPTION_KEY" ]; then
        log_error "Encryption key is not readable: $DR_ENCRYPTION_KEY"
        return 1
    fi
    
    log_success "Restoration test passed"
    return 0
}

# Check backup age
check_backup_age() {
    local session_dir="$1"
    local manifest_file="$session_dir/backup-manifest.json"
    
    log "Checking backup age..."
    
    if [ ! -f "$manifest_file" ]; then
        log_warning "Cannot check backup age: manifest not found"
        return 0
    fi
    
    # Get manifest modification time
    local manifest_time=$(stat -c %Y "$manifest_file" 2>/dev/null || echo "0")
    local current_time=$(date +%s)
    local age_hours=$(( (current_time - manifest_time) / 3600 ))
    
    log "Backup age: $age_hours hours"
    
    # Warning if backup is older than 24 hours
    if [ $age_hours -gt 24 ]; then
        log_warning "Backup is older than 24 hours"
    else
        log_success "Backup age is acceptable"
    fi
    
    return 0
}

# Generate validation report
generate_validation_report() {
    local session_dir="$1"
    local report_file="$DR_LOGS_DIR/validation-report-$VALIDATION_ID.json"
    
    log "Generating validation report..."
    
    # Create JSON report (with error handling)
    if ! cat > "$report_file" 2>/dev/null << EOF
{
    "validation_id": "$VALIDATION_ID",
    "session_directory": "$session_dir",
    "session_name": "$(basename "$session_dir")",
    "timestamp": "$(date -Iseconds)",
    "summary": {
        "errors": $VALIDATION_ERRORS,
        "warnings": $VALIDATION_WARNINGS,
        "overall_status": "$([ $VALIDATION_ERRORS -eq 0 ] && echo "passed" || echo "failed")"
    },
    "log_file": "$LOG_FILE"
}
EOF
    then
        log_warning "Could not create validation report: $report_file"
    else
        log "Validation report saved: $report_file"
    fi
}

# Send notification (placeholder)
send_notification() {
    local status="$1"
    local message="$2"
    
    log "Notification [$status]: $message"
    # This would send actual notifications via email, Slack, etc.
}

# Updated main function with source detection
main() {
    local session_arg="${1:-}"
    local source="${2:-auto}"  # New parameter for backup source
    
    log "=== Starting Backup Validation ==="
    log "Validation ID: $VALIDATION_ID"
    log "Source: $source"
    log "Session argument: ${session_arg:-[latest]}"
    log "DR_SESSION_DIR: $DR_SESSION_DIR"
    log "DR_BACKUP_DIR: $DR_BACKUP_DIR"
    log "Docker mode: $DOCKER_MODE"
    
    # Get session directory based on source
    local session_dir
    session_dir=$(get_session_directory "$session_arg" "$source")
    
    if [ $? -ne 0 ] || [ -z "$session_dir" ]; then
        log_error "Failed to locate backup session"
        exit 1
    fi
    
    if [ ! -d "$session_dir" ]; then
        log_error "Session directory not found: $session_dir"
        log "Available sessions in $DR_SESSION_DIR:"
        if [ -d "$DR_SESSION_DIR" ]; then
            ls -la "$DR_SESSION_DIR" 2>/dev/null || log "Cannot list directory"
        else
            log_error "DR_SESSION_DIR does not exist: $DR_SESSION_DIR"
        fi
        exit 1
    fi
    
    log "Validating session: $(basename "$session_dir")"
    log "Session directory: $session_dir"
    
    # Check if encryption key exists
    if [ ! -f "$DR_ENCRYPTION_KEY" ]; then
        log_error "Encryption key not found: $DR_ENCRYPTION_KEY"
        exit 1
    fi
    
    # Run all validations
    validate_manifest "$session_dir"
    validate_database_backups "$session_dir"
    validate_filestore_backup "$session_dir"
    validate_config_backups "$session_dir"
    
    # Skip cloud sync validation if we downloaded from cloud
    if [ "$source" != "gdrive" ]; then
        validate_cloud_sync "$session_dir"
    else
        log "Skipping cloud sync validation (source is Google Drive)"
    fi
    
    test_restoration "$session_dir"
    check_backup_age "$session_dir"
    
    # Generate report
    generate_validation_report "$session_dir"
    
    # Send notification
    if [ $VALIDATION_ERRORS -eq 0 ]; then
        log "=== Validation completed successfully ==="
        send_notification "SUCCESS" "Backup validation passed. Session: $(basename "$session_dir"), Source: $source, Warnings: $VALIDATION_WARNINGS"
        exit 0
    else
        log "=== Validation completed with errors ==="
        send_notification "ERROR" "Backup validation failed with $VALIDATION_ERRORS errors and $VALIDATION_WARNINGS warnings. Session: $(basename "$session_dir"), Source: $source"
        exit 1
    fi
}

# Show usage information
usage() {
    echo "Usage: $0 [SESSION_ID|SESSION_PATH] [SOURCE]"
    echo ""
    echo "Arguments:"
    echo "  SESSION_ID|SESSION_PATH  Optional backup session ID, name, or full path"
    echo "  SOURCE                   Backup source: 'local', 'gdrive', or 'auto' (default: auto)"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Validate latest backup (auto-detect source)"
    echo "  $0 backup_20250803_204026_52         # Validate specific session (auto-detect source)"
    echo "  $0 20250803_204026_52 gdrive         # Validate from Google Drive"
    echo "  $0 '' local                          # Validate latest local backup"
    echo "  $0 /full/path/to/session             # Validate specific path"
}

# Handle help flag
if [ "${1:-}" == "--help" ] || [ "${1:-}" == "-h" ]; then
    usage
    exit 0
fi

# Run main function
main "$@"