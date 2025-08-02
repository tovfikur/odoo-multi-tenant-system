#!/bin/bash

# Backup Validation Script
# Validates backup integrity, cloud sync, and recoverability

set -euo pipefail

# Load configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$(dirname "$SCRIPT_DIR")/config"
source "$CONFIG_DIR/dr-config.env"

# Global variables
VALIDATION_ID="validate_$(date +%Y%m%d_%H%M%S)_$$"
LOG_FILE="$DR_BACKUP_DIR/logs/validation-$VALIDATION_ID.log"
VALIDATION_ERRORS=0
VALIDATION_WARNINGS=0

# Logging functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $1" | tee -a "$LOG_FILE" >&2
    ((VALIDATION_ERRORS++))
}

log_warning() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WARNING] $1" | tee -a "$LOG_FILE"
    ((VALIDATION_WARNINGS++))
}

log_success() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [SUCCESS] $1" | tee -a "$LOG_FILE"
}

# Find latest backup session
find_latest_backup() {
    local latest_session
    latest_session=$(find "$DR_SESSION_DIR" -type d -name "backup_*" -exec basename {} \; | sort -r | head -1)
    
    if [ -z "$latest_session" ]; then
        log_error "No backup sessions found in $DR_SESSION_DIR"
        return 1
    fi
    
    echo "$DR_SESSION_DIR/$latest_session"
}

# Validate backup manifest
validate_manifest() {
    local session_dir="$1"
    local manifest_file="$session_dir/backup-manifest.json"
    
    log "Validating backup manifest..."
    
    if [ ! -f "$manifest_file" ]; then
        log_error "Backup manifest not found: $manifest_file"
        return 1
    fi
    
    # Check if manifest is valid JSON
    if command -v jq &> /dev/null; then
        if ! jq . "$manifest_file" > /dev/null 2>&1; then
            log_error "Invalid JSON in manifest file"
            return 1
        fi
        
        # Extract information from manifest
        local session_id errors warnings
        session_id=$(jq -r '.session_id' "$manifest_file")
        errors=$(jq -r '.metadata.errors // 0' "$manifest_file")
        warnings=$(jq -r '.metadata.warnings // 0' "$manifest_file")
        
        log "Manifest validation passed"
        log "Session ID: $session_id"
        log "Backup errors: $errors"
        log "Backup warnings: $warnings"
        
        if [ "$errors" -gt 0 ]; then
            log_warning "Backup session had $errors errors"
        fi
        
        return 0
    else
        log_warning "jq not available, skipping detailed manifest validation"
        return 0
    fi
}

# Validate database backups
validate_database_backups() {
    local session_dir="$1"
    local db_dir="$session_dir/databases"
    
    log "Validating database backups..."
    
    if [ ! -d "$db_dir" ]; then
        log_error "Database backup directory not found: $db_dir"
        return 1
    fi
    
    local db_count=0
    local valid_count=0
    
    for db_backup in "$db_dir"/*.sql.enc; do
        if [ -f "$db_backup" ]; then
            ((db_count++))
            local db_name
            db_name=$(basename "$db_backup" .sql.enc)
            
            log "Validating database backup: $db_name"
            
            # Test decryption
            local key temp_file
            key=$(cat "$DR_ENCRYPTION_KEY")
            temp_file="/tmp/validate_${db_name}_$$.sql"
            
            if openssl enc -d -aes-256-cbc -in "$db_backup" -out "$temp_file" -k "$key" 2>/dev/null; then
                # Verify it's a valid PostgreSQL dump
                if file "$temp_file" | grep -q "PostgreSQL custom database dump\|ASCII text"; then
                    # Try to get basic info from the dump
                    if head -n 20 "$temp_file" | grep -q "PostgreSQL database dump\|COMMENT.*ON.*DATABASE"; then
                        log_success "Database backup valid: $db_name"
                        ((valid_count++))
                    else
                        log_error "Database backup appears corrupted: $db_name"
                    fi
                else
                    log_error "Database backup is not a valid PostgreSQL dump: $db_name"
                fi
                rm -f "$temp_file"
            else
                log_error "Failed to decrypt database backup: $db_name"
            fi
        fi
    done
    
    if [ $db_count -eq 0 ]; then
        log_warning "No database backups found"
        return 1
    fi
    
    log "Database validation completed: $valid_count/$db_count valid"
    return 0
}

# Validate filestore backup
validate_filestore_backup() {
    local session_dir="$1"
    local filestore_backup="$session_dir/filestore/filestore.tar.gz.enc"
    
    log "Validating filestore backup..."
    
    if [ ! -f "$filestore_backup" ]; then
        log_warning "Filestore backup not found: $filestore_backup"
        return 1
    fi
    
    # Test decryption and archive integrity
    local key temp_file
    key=$(cat "$DR_ENCRYPTION_KEY")
    temp_file="/tmp/validate_filestore_$$.tar.gz"
    
    if openssl enc -d -aes-256-cbc -in "$filestore_backup" -out "$temp_file" -k "$key" 2>/dev/null; then
        if tar -tzf "$temp_file" > /dev/null 2>&1; then
            local file_count
            file_count=$(tar -tzf "$temp_file" | wc -l)
            log_success "Filestore backup valid: $file_count files"
            rm -f "$temp_file"
            return 0
        else
            log_error "Filestore backup is not a valid tar archive"
            rm -f "$temp_file"
            return 1
        fi
    else
        log_error "Failed to decrypt filestore backup"
        return 1
    fi
}

# Validate configuration backups
validate_config_backups() {
    local session_dir="$1"
    local config_dir="$session_dir/configs"
    
    log "Validating configuration backups..."
    
    if [ ! -d "$config_dir" ]; then
        log_warning "Configuration backup directory not found: $config_dir"
        return 1
    fi
    
    local config_count=0
    local valid_count=0
    
    for config_backup in "$config_dir"/*.tar.gz.enc; do
        if [ -f "$config_backup" ]; then
            ((config_count++))
            local config_name
            config_name=$(basename "$config_backup" .tar.gz.enc)
            
            log "Validating configuration backup: $config_name"
            
            # Test decryption and archive integrity
            local key temp_file
            key=$(cat "$DR_ENCRYPTION_KEY")
            temp_file="/tmp/validate_${config_name}_$$.tar.gz"
            
            if openssl enc -d -aes-256-cbc -in "$config_backup" -out "$temp_file" -k "$key" 2>/dev/null; then
                if tar -tzf "$temp_file" > /dev/null 2>&1; then
                    log_success "Configuration backup valid: $config_name"
                    ((valid_count++))
                else
                    log_error "Configuration backup is not a valid tar archive: $config_name"
                fi
                rm -f "$temp_file"
            else
                log_error "Failed to decrypt configuration backup: $config_name"
            fi
        fi
    done
    
    if [ $config_count -eq 0 ]; then
        log_warning "No configuration backups found"
    else
        log "Configuration validation completed: $valid_count/$config_count valid"
    fi
    
    return 0
}

# Validate cloud storage sync
validate_cloud_sync() {
    local session_dir="$1"
    local session_name
    session_name=$(basename "$session_dir")
    
    log "Validating cloud storage sync..."
    
    local bucket_name
    bucket_name=$(echo "$DR_CLOUD_BUCKET" | sed 's|s3://||')
    local cloud_path="backups/$session_name"
    
    # Check if session exists in cloud
    if aws s3 ls "s3://$bucket_name/$cloud_path/" > /dev/null 2>&1; then
        log_success "Backup session found in cloud: s3://$bucket_name/$cloud_path"
        
        # Compare local and cloud files
        local local_files cloud_files
        local_files=$(find "$session_dir" -name "*.enc" -o -name "*.json" | wc -l)
        cloud_files=$(aws s3 ls "s3://$bucket_name/$cloud_path/" --recursive | grep -E '\.(enc|json)$' | wc -l)
        
        if [ "$local_files" -eq "$cloud_files" ]; then
            log_success "File count matches: $local_files files in both local and cloud"
        else
            log_error "File count mismatch: $local_files local, $cloud_files cloud"
            return 1
        fi
        
        # Validate a few random files
        log "Validating random cloud files..."
        local sample_files
        sample_files=$(find "$session_dir" -name "*.enc" | head -3)
        
        for local_file in $sample_files; do
            local relative_path
            relative_path=$(echo "$local_file" | sed "s|$session_dir/||")
            local cloud_file="s3://$bucket_name/$cloud_path/$relative_path"
            
            if aws s3 ls "$cloud_file" > /dev/null 2>&1; then
                # Compare file sizes
                local local_size cloud_size
                local_size=$(stat -f%z "$local_file" 2>/dev/null || stat -c%s "$local_file" 2>/dev/null || echo "0")
                cloud_size=$(aws s3 ls "$cloud_file" | awk '{print $3}')
                
                if [ "$local_size" -eq "$cloud_size" ]; then
                    log_success "Cloud file validation passed: $relative_path"
                else
                    log_error "Cloud file size mismatch: $relative_path ($local_size vs $cloud_size)"
                fi
            else
                log_error "Cloud file not found: $cloud_file"
            fi
        done
        
        return 0
    else
        log_error "Backup session not found in cloud storage"
        return 1
    fi
}

# Test backup restoration (dry run)
test_restoration() {
    local session_dir="$1"
    
    log "Testing backup restoration (dry run)..."
    
    # Create temporary test directory
    local test_dir="/tmp/dr_restore_test_$$"
    mkdir -p "$test_dir"
    
    # Test database restoration
    log "Testing database restoration..."
    local db_backup
    db_backup=$(find "$session_dir/databases" -name "*.sql.enc" | head -1)
    
    if [ -f "$db_backup" ]; then
        local key temp_sql
        key=$(cat "$DR_ENCRYPTION_KEY")
        temp_sql="$test_dir/test_restore.sql"
        
        if openssl enc -d -aes-256-cbc -in "$db_backup" -out "$temp_sql" -k "$key" 2>/dev/null; then
            # Validate SQL structure
            if grep -q "CREATE TABLE\|INSERT INTO\|COPY.*FROM" "$temp_sql"; then
                log_success "Database restoration test passed"
            else
                log_error "Database restoration test failed: invalid SQL structure"
            fi
        else
            log_error "Database restoration test failed: decryption error"
        fi
    else
        log_warning "No database backup found for restoration test"
    fi
    
    # Test filestore restoration
    log "Testing filestore restoration..."
    local filestore_backup="$session_dir/filestore/filestore.tar.gz.enc"
    
    if [ -f "$filestore_backup" ]; then
        local key temp_archive
        key=$(cat "$DR_ENCRYPTION_KEY")
        temp_archive="$test_dir/test_filestore.tar.gz"
        
        if openssl enc -d -aes-256-cbc -in "$filestore_backup" -out "$temp_archive" -k "$key" 2>/dev/null; then
            if tar -tzf "$temp_archive" | head -5 > /dev/null 2>&1; then
                log_success "Filestore restoration test passed"
            else
                log_error "Filestore restoration test failed: invalid archive"
            fi
        else
            log_error "Filestore restoration test failed: decryption error"
        fi
    else
        log_warning "No filestore backup found for restoration test"
    fi
    
    # Cleanup test directory
    rm -rf "$test_dir"
    
    log "Restoration test completed"
}

# Check backup age
check_backup_age() {
    local session_dir="$1"
    local manifest_file="$session_dir/backup-manifest.json"
    
    log "Checking backup age..."
    
    if [ ! -f "$manifest_file" ]; then
        log_error "Cannot check backup age: manifest file not found"
        return 1
    fi
    
    local backup_time current_time age_hours
    
    if command -v jq &> /dev/null; then
        backup_time=$(jq -r '.start_time' "$manifest_file")
        current_time=$(date -u +%Y-%m-%dT%H:%M:%SZ)
        
        # Calculate age in hours (simplified)
        local backup_epoch current_epoch
        backup_epoch=$(date -d "$backup_time" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%SZ" "$backup_time" +%s 2>/dev/null || echo "0")
        current_epoch=$(date +%s)
        age_hours=$(( (current_epoch - backup_epoch) / 3600 ))
        
        log "Backup age: $age_hours hours"
        
        if [ "$age_hours" -gt 24 ]; then
            log_warning "Backup is older than 24 hours ($age_hours hours)"
        else
            log_success "Backup age is acceptable ($age_hours hours)"
        fi
    else
        # Fallback: check file modification time
        local backup_age_days
        backup_age_days=$(find "$session_dir" -name "backup-manifest.json" -mtime +1 | wc -l)
        
        if [ "$backup_age_days" -gt 0 ]; then
            log_warning "Backup is older than 1 day"
        else
            log_success "Backup is recent (less than 1 day old)"
        fi
    fi
}

# Generate validation report
generate_validation_report() {
    local session_dir="$1"
    local report_file="$DR_BACKUP_DIR/logs/validation-report-$VALIDATION_ID.json"
    
    cat > "$report_file" << EOF
{
    "validation_id": "$VALIDATION_ID",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "session_validated": "$(basename "$session_dir")",
    "results": {
        "errors": $VALIDATION_ERRORS,
        "warnings": $VALIDATION_WARNINGS,
        "status": "$( [ $VALIDATION_ERRORS -eq 0 ] && echo "passed" || echo "failed" )"
    },
    "system": {
        "hostname": "$(hostname)",
        "validator_version": "1.0"
    }
}
EOF
    
    log "Validation report generated: $report_file"
}

# Send validation notification
send_notification() {
    local status="$1"
    local message="$2"
    
    # Email notification
    if [ -n "$DR_NOTIFICATION_EMAIL" ] && command -v mail &> /dev/null; then
        echo "$message" | mail -s "DR Backup Validation [$status] - $VALIDATION_ID" "$DR_NOTIFICATION_EMAIL"
    fi
    
    # Log notification
    log "NOTIFICATION [$status]: $message"
}

# Main validation function
main() {
    local session_dir="${1:-}"
    
    log "=== Starting Backup Validation ==="
    log "Validation ID: $VALIDATION_ID"
    
    # Find session to validate
    if [ -z "$session_dir" ]; then
        session_dir=$(find_latest_backup)
        if [ $? -ne 0 ]; then
            exit 1
        fi
    fi
    
    log "Validating session: $(basename "$session_dir")"
    
    # Check if encryption key exists
    if [ ! -f "$DR_ENCRYPTION_KEY" ]; then
        log_error "Encryption key not found: $DR_ENCRYPTION_KEY"
        exit 1
    fi
    
    # Run validations
    validate_manifest "$session_dir"
    validate_database_backups "$session_dir"
    validate_filestore_backup "$session_dir"
    validate_config_backups "$session_dir"
    validate_cloud_sync "$session_dir"
    test_restoration "$session_dir"
    check_backup_age "$session_dir"
    
    # Generate report
    generate_validation_report "$session_dir"
    
    # Send notification
    if [ $VALIDATION_ERRORS -eq 0 ]; then
        log "=== Validation completed successfully ==="
        send_notification "SUCCESS" "Backup validation passed. Session: $(basename "$session_dir"), Warnings: $VALIDATION_WARNINGS"
        exit 0
    else
        log "=== Validation completed with errors ==="
        send_notification "ERROR" "Backup validation failed with $VALIDATION_ERRORS errors and $VALIDATION_WARNINGS warnings. Session: $(basename "$session_dir")"
        exit 1
    fi
}

# Run main function
main "$@"
