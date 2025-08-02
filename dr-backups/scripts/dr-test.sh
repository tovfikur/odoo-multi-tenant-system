#!/bin/bash

# Disaster Recovery Testing Framework
# Automated testing of backup and recovery procedures

set -euo pipefail

# Load configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$(dirname "$SCRIPT_DIR")/config"
source "$CONFIG_DIR/dr-config.env"

# Global variables
TEST_ID="test_$(date +%Y%m%d_%H%M%S)_$$"
LOG_FILE="$DR_BACKUP_DIR/logs/test-$TEST_ID.log"
TEST_DIR="$DR_BACKUP_DIR/tests/test-$TEST_ID"
TEST_ERRORS=0
TEST_WARNINGS=0
TEST_RESULTS=()

# Test modes
TEST_MODE="full"  # full, backup-only, restore-only, validation-only

# Logging functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $1" | tee -a "$LOG_FILE" >&2
    ((TEST_ERRORS++))
}

log_warning() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WARNING] $1" | tee -a "$LOG_FILE"
    ((TEST_WARNINGS++))
}

log_success() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [SUCCESS] $1" | tee -a "$LOG_FILE"
}

log_test_result() {
    local test_name="$1"
    local status="$2"
    local message="$3"
    local duration="${4:-0}"
    
    log "[$status] $test_name: $message (${duration}s)"
    
    local result="{\"name\": \"$test_name\", \"status\": \"$status\", \"message\": \"$message\", \"duration\": $duration, \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
    TEST_RESULTS+=("$result")
}

# Display usage information
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Disaster Recovery Testing Framework

OPTIONS:
    -m, --mode MODE      Test mode: full, backup-only, restore-only, validation-only
    -s, --session ID     Use specific backup session for restore tests
    -c, --cleanup        Clean up test environment after completion
    -k, --keep-data      Keep test data for manual inspection
    -t, --timeout SECS   Timeout for individual tests (default: 3600)
    -h, --help          Show this help message

Test Modes:
    full            Run complete backup and restore test cycle
    backup-only     Test only backup creation and validation
    restore-only    Test only restore procedures (requires existing backup)
    validation-only Test only backup validation procedures

Examples:
    $0                          # Run full test cycle
    $0 -m backup-only          # Test only backup procedures
    $0 -m restore-only -s latest  # Test restore from latest backup
    $0 -c                      # Run tests and cleanup afterwards
EOF
}

# Parse command line arguments
parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -m|--mode)
                TEST_MODE="$2"
                shift 2
                ;;
            -s|--session)
                TEST_SESSION="$2"
                shift 2
                ;;
            -c|--cleanup)
                CLEANUP_AFTER="true"
                shift
                ;;
            -k|--keep-data)
                KEEP_DATA="true"
                shift
                ;;
            -t|--timeout)
                TEST_TIMEOUT="$2"
                shift 2
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done
    
    # Set defaults
    TEST_SESSION="${TEST_SESSION:-}"
    CLEANUP_AFTER="${CLEANUP_AFTER:-false}"
    KEEP_DATA="${KEEP_DATA:-false}"
    TEST_TIMEOUT="${TEST_TIMEOUT:-3600}"
}

# Create isolated test environment
create_test_environment() {
    log "Creating isolated test environment..."
    
    # Create test directory structure
    mkdir -p "$TEST_DIR"/{backup,restore,temp}
    
    # Create test database
    local test_db="kdoo_test_$TEST_ID"
    export PGPASSWORD="$POSTGRES_PASSWORD"
    
    log "Creating test database: $test_db"
    
    if psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_MASTER_DB" \
        -c "CREATE DATABASE \"$test_db\";" 2>/dev/null; then
        
        # Add some test data
        psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$test_db" << EOF
CREATE TABLE test_data (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO test_data (name) VALUES 
    ('Test Record 1'),
    ('Test Record 2'),
    ('Test Record 3');

CREATE TABLE test_verification (
    test_id VARCHAR(50),
    test_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO test_verification (test_id) VALUES ('$TEST_ID');
EOF
        
        log_success "Test database created with sample data"
        echo "$test_db"
    else
        log_error "Failed to create test database"
        return 1
    fi
}

# Test backup creation
test_backup_creation() {
    local start_time
    start_time=$(date +%s)
    
    log "Testing backup creation..."
    
    # Run enhanced backup script
    local backup_script="$SCRIPT_DIR/enhanced-backup.sh"
    
    if [ ! -f "$backup_script" ]; then
        log_test_result "backup_creation" "FAILED" "Backup script not found" "$(($(date +%s) - start_time))"
        return 1
    fi
    
    # Set test environment variables
    export DR_BACKUP_DIR="$TEST_DIR/backup"
    export DR_SESSION_DIR="$TEST_DIR/backup/sessions"
    mkdir -p "$DR_SESSION_DIR"
    
    if timeout "$TEST_TIMEOUT" "$backup_script" > "$TEST_DIR/backup.log" 2>&1; then
        local duration=$(($(date +%s) - start_time))
        log_test_result "backup_creation" "PASSED" "Backup created successfully" "$duration"
        
        # Find created backup session
        local backup_session
        backup_session=$(find "$DR_SESSION_DIR" -type d -name "backup_*" -exec basename {} \; | sort -r | head -1)
        
        if [ -n "$backup_session" ]; then
            echo "$DR_SESSION_DIR/$backup_session"
            return 0
        else
            log_test_result "backup_creation" "FAILED" "No backup session created" "$duration"
            return 1
        fi
    else
        local duration=$(($(date +%s) - start_time))
        log_test_result "backup_creation" "FAILED" "Backup script failed or timed out" "$duration"
        return 1
    fi
}

# Test backup validation
test_backup_validation() {
    local backup_session="$1"
    local start_time
    start_time=$(date +%s)
    
    log "Testing backup validation..."
    
    local validation_script="$SCRIPT_DIR/validate-backup.sh"
    
    if [ ! -f "$validation_script" ]; then
        log_test_result "backup_validation" "FAILED" "Validation script not found" "$(($(date +%s) - start_time))"
        return 1
    fi
    
    if timeout "$TEST_TIMEOUT" "$validation_script" "$backup_session" > "$TEST_DIR/validation.log" 2>&1; then
        local duration=$(($(date +%s) - start_time))
        log_test_result "backup_validation" "PASSED" "Backup validation successful" "$duration"
        return 0
    else
        local duration=$(($(date +%s) - start_time))
        log_test_result "backup_validation" "FAILED" "Backup validation failed" "$duration"
        return 1
    fi
}

# Test disaster recovery
test_disaster_recovery() {
    local backup_session="$1"
    local start_time
    start_time=$(date +%s)
    
    log "Testing disaster recovery (test mode)..."
    
    local recovery_script="$SCRIPT_DIR/disaster-recovery.sh"
    
    if [ ! -f "$recovery_script" ]; then
        log_test_result "disaster_recovery" "FAILED" "Recovery script not found" "$(($(date +%s) - start_time))"
        return 1
    fi
    
    # Test recovery in test mode (no actual changes)
    if timeout "$TEST_TIMEOUT" "$recovery_script" --test --force --session "$(basename "$backup_session")" > "$TEST_DIR/recovery.log" 2>&1; then
        local duration=$(($(date +%s) - start_time))
        log_test_result "disaster_recovery" "PASSED" "Recovery test completed successfully" "$duration"
        return 0
    else
        local duration=$(($(date +%s) - start_time))
        log_test_result "disaster_recovery" "FAILED" "Recovery test failed" "$duration"
        return 1
    fi
}

# Test database restoration to isolated environment
test_database_restoration() {
    local backup_session="$1"
    local start_time
    start_time=$(date +%s)
    
    log "Testing database restoration to isolated environment..."
    
    # Create test restore database
    local restore_db="kdoo_restore_test_$TEST_ID"
    export PGPASSWORD="$POSTGRES_PASSWORD"
    
    # Find a database backup to restore
    local db_backup
    db_backup=$(find "$backup_session/databases" -name "*.sql.enc" | head -1)
    
    if [ ! -f "$db_backup" ]; then
        log_test_result "database_restoration" "FAILED" "No database backup found" "$(($(date +%s) - start_time))"
        return 1
    fi
    
    local db_name
    db_name=$(basename "$db_backup" .sql.enc)
    
    log "Restoring database $db_name to $restore_db"
    
    # Decrypt backup
    local key temp_sql
    key=$(cat "$DR_ENCRYPTION_KEY")
    temp_sql="$TEST_DIR/temp/restore_test.sql"
    
    if ! openssl enc -d -aes-256-cbc -in "$db_backup" -out "$temp_sql" -k "$key"; then
        log_test_result "database_restoration" "FAILED" "Failed to decrypt database backup" "$(($(date +%s) - start_time))"
        return 1
    fi
    
    # Create restore database
    psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_MASTER_DB" \
        -c "CREATE DATABASE \"$restore_db\";" 2>/dev/null || true
    
    # Restore database
    if pg_restore -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
        -d "$restore_db" --clean --no-owner --no-privileges "$temp_sql" 2>/dev/null; then
        
        # Verify restoration by checking if we can connect and query
        local table_count
        table_count=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$restore_db" \
            -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" | tr -d ' \n' || echo "0")
        
        if [ "$table_count" -gt 0 ]; then
            local duration=$(($(date +%s) - start_time))
            log_test_result "database_restoration" "PASSED" "Database restored with $table_count tables" "$duration"
            
            # Cleanup test database
            psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_MASTER_DB" \
                -c "DROP DATABASE IF EXISTS \"$restore_db\";" 2>/dev/null || true
            
            rm -f "$temp_sql"
            return 0
        else
            log_test_result "database_restoration" "FAILED" "Database restored but no tables found" "$(($(date +%s) - start_time))"
        fi
    else
        log_test_result "database_restoration" "FAILED" "pg_restore failed" "$(($(date +%s) - start_time))"
    fi
    
    # Cleanup on failure
    psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_MASTER_DB" \
        -c "DROP DATABASE IF EXISTS \"$restore_db\";" 2>/dev/null || true
    rm -f "$temp_sql"
    return 1
}

# Test filestore restoration
test_filestore_restoration() {
    local backup_session="$1"
    local start_time
    start_time=$(date +%s)
    
    log "Testing filestore restoration..."
    
    local filestore_backup="$backup_session/filestore/filestore.tar.gz.enc"
    
    if [ ! -f "$filestore_backup" ]; then
        log_test_result "filestore_restoration" "SKIPPED" "No filestore backup found" "$(($(date +%s) - start_time))"
        return 0
    fi
    
    # Create test restore directory
    local restore_dir="$TEST_DIR/restore/filestore"
    mkdir -p "$restore_dir"
    
    # Decrypt and extract filestore
    local key temp_archive
    key=$(cat "$DR_ENCRYPTION_KEY")
    temp_archive="$TEST_DIR/temp/filestore.tar.gz"
    
    if openssl enc -d -aes-256-cbc -in "$filestore_backup" -out "$temp_archive" -k "$key" 2>/dev/null; then
        if tar -xzf "$temp_archive" -C "$restore_dir" 2>/dev/null; then
            local file_count
            file_count=$(find "$restore_dir" -type f | wc -l)
            local duration=$(($(date +%s) - start_time))
            log_test_result "filestore_restoration" "PASSED" "Filestore restored with $file_count files" "$duration"
            rm -f "$temp_archive"
            return 0
        else
            log_test_result "filestore_restoration" "FAILED" "Failed to extract filestore archive" "$(($(date +%s) - start_time))"
        fi
    else
        log_test_result "filestore_restoration" "FAILED" "Failed to decrypt filestore backup" "$(($(date +%s) - start_time))"
    fi
    
    rm -f "$temp_archive"
    return 1
}

# Test cloud storage integration
test_cloud_storage() {
    local backup_session="$1"
    local start_time
    start_time=$(date +%s)
    
    log "Testing cloud storage integration..."
    
    if [ -z "$DR_CLOUD_BUCKET" ]; then
        log_test_result "cloud_storage" "SKIPPED" "Cloud storage not configured" "$(($(date +%s) - start_time))"
        return 0
    fi
    
    local bucket_name
    bucket_name=$(echo "$DR_CLOUD_BUCKET" | sed 's|s3://||')
    local session_name
    session_name=$(basename "$backup_session")
    local cloud_path="backups/$session_name"
    
    # Check if backup exists in cloud
    if aws s3 ls "s3://$bucket_name/$cloud_path/" > /dev/null 2>&1; then
        # Test download
        local download_dir="$TEST_DIR/cloud_download"
        mkdir -p "$download_dir"
        
        if aws s3 sync "s3://$bucket_name/$cloud_path" "$download_dir" \
            --exclude "*" --include "*.enc" --include "*.json" 2>/dev/null; then
            
            local downloaded_files
            downloaded_files=$(find "$download_dir" -name "*.enc" -o -name "*.json" | wc -l)
            local duration=$(($(date +%s) - start_time))
            log_test_result "cloud_storage" "PASSED" "Downloaded $downloaded_files files from cloud" "$duration"
            return 0
        else
            log_test_result "cloud_storage" "FAILED" "Failed to download from cloud" "$(($(date +%s) - start_time))"
        fi
    else
        log_test_result "cloud_storage" "FAILED" "Backup not found in cloud storage" "$(($(date +%s) - start_time))"
    fi
    
    return 1
}

# Test monitoring system
test_monitoring() {
    local start_time
    start_time=$(date +%s)
    
    log "Testing monitoring system..."
    
    local monitor_script="$SCRIPT_DIR/dr-monitor.sh"
    
    if [ ! -f "$monitor_script" ]; then
        log_test_result "monitoring" "FAILED" "Monitor script not found" "$(($(date +%s) - start_time))"
        return 1
    fi
    
    if timeout 300 "$monitor_script" > "$TEST_DIR/monitor.log" 2>&1; then
        local duration=$(($(date +%s) - start_time))
        log_test_result "monitoring" "PASSED" "Monitoring check completed" "$duration"
        return 0
    else
        local duration=$(($(date +%s) - start_time))
        log_test_result "monitoring" "FAILED" "Monitoring check failed" "$duration"
        return 1
    fi
}

# Cleanup test environment
cleanup_test_environment() {
    log "Cleaning up test environment..."
    
    # Remove test databases
    export PGPASSWORD="$POSTGRES_PASSWORD"
    
    local test_databases
    test_databases=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_MASTER_DB" -t -c \
        "SELECT datname FROM pg_database WHERE datname LIKE '%test_$TEST_ID%';" | grep -v "^$" | sed 's/^ *//' | sed 's/ *$//' || true)
    
    if [ -n "$test_databases" ]; then
        while IFS= read -r db_name; do
            if [ -n "$db_name" ]; then
                log "Dropping test database: $db_name"
                psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_MASTER_DB" \
                    -c "DROP DATABASE IF EXISTS \"$db_name\";" 2>/dev/null || true
            fi
        done <<< "$test_databases"
    fi
    
    # Remove test directories
    if [ "$KEEP_DATA" != "true" ]; then
        rm -rf "$TEST_DIR"
        log "Test directory removed: $TEST_DIR"
    else
        log "Test data preserved: $TEST_DIR"
    fi
}

# Generate test report
generate_test_report() {
    local report_file="$DR_BACKUP_DIR/logs/test-report-$TEST_ID.json"
    
    # Convert results array to JSON
    local results_json="["
    local first=true
    for result in "${TEST_RESULTS[@]}"; do
        if [ "$first" = true ]; then
            first=false
        else
            results_json="$results_json,"
        fi
        results_json="$results_json$result"
    done
    results_json="$results_json]"
    
    # Calculate summary statistics
    local total_tests passed_tests failed_tests
    total_tests=${#TEST_RESULTS[@]}
    passed_tests=$(echo "$results_json" | grep -o '"status": "PASSED"' | wc -l || echo "0")
    failed_tests=$(echo "$results_json" | grep -o '"status": "FAILED"' | wc -l || echo "0")
    
    cat > "$report_file" << EOF
{
    "test_id": "$TEST_ID",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "mode": "$TEST_MODE",
    "summary": {
        "total_tests": $total_tests,
        "passed": $passed_tests,
        "failed": $failed_tests,
        "skipped": $((total_tests - passed_tests - failed_tests)),
        "errors": $TEST_ERRORS,
        "warnings": $TEST_WARNINGS,
        "overall_status": "$( [ $TEST_ERRORS -eq 0 ] && echo "success" || echo "failed" )"
    },
    "results": $results_json,
    "environment": {
        "hostname": "$(hostname)",
        "test_directory": "$TEST_DIR",
        "keep_data": $KEEP_DATA,
        "cleanup_after": $CLEANUP_AFTER
    },
    "logs": {
        "main_log": "$LOG_FILE",
        "test_directory": "$TEST_DIR"
    }
}
EOF
    
    log "Test report generated: $report_file"
}

# Send test notification
send_notification() {
    local status="$1"
    local message="$2"
    
    # Email notification
    if [ -n "$DR_NOTIFICATION_EMAIL" ] && command -v mail &> /dev/null; then
        echo "$message" | mail -s "DR Test [$status] - $TEST_ID" "$DR_NOTIFICATION_EMAIL"
    fi
    
    log "NOTIFICATION [$status]: $message"
}

# Main test function
main() {
    local start_time
    start_time=$(date +%s)
    
    log "=== Starting DR Testing Framework ==="
    log "Test ID: $TEST_ID"
    log "Test Mode: $TEST_MODE"
    log "Configuration: $CONFIG_DIR/dr-config.env"
    
    # Parse arguments
    parse_arguments "$@"
    
    # Create test environment
    mkdir -p "$DR_BACKUP_DIR/logs"
    mkdir -p "$DR_BACKUP_DIR/tests"
    
    local test_db backup_session
    
    # Run tests based on mode
    case "$TEST_MODE" in
        "full")
            test_db=$(create_test_environment)
            backup_session=$(test_backup_creation)
            if [ -n "$backup_session" ]; then
                test_backup_validation "$backup_session"
                test_disaster_recovery "$backup_session"
                test_database_restoration "$backup_session"
                test_filestore_restoration "$backup_session"
                test_cloud_storage "$backup_session"
            fi
            test_monitoring
            ;;
        "backup-only")
            test_db=$(create_test_environment)
            backup_session=$(test_backup_creation)
            if [ -n "$backup_session" ]; then
                test_backup_validation "$backup_session"
                test_cloud_storage "$backup_session"
            fi
            ;;
        "restore-only")
            if [ -n "$TEST_SESSION" ]; then
                backup_session=$(find "$DR_SESSION_DIR" -type d -name "*$TEST_SESSION*" | head -1)
                if [ -n "$backup_session" ]; then
                    test_disaster_recovery "$backup_session"
                    test_database_restoration "$backup_session"
                    test_filestore_restoration "$backup_session"
                else
                    log_error "Test session not found: $TEST_SESSION"
                fi
            else
                log_error "Test session required for restore-only mode"
            fi
            ;;
        "validation-only")
            if [ -n "$TEST_SESSION" ]; then
                backup_session=$(find "$DR_SESSION_DIR" -type d -name "*$TEST_SESSION*" | head -1)
                if [ -n "$backup_session" ]; then
                    test_backup_validation "$backup_session"
                else
                    log_error "Test session not found: $TEST_SESSION"
                fi
            else
                # Use latest backup
                backup_session=$(find "$DR_SESSION_DIR" -type d -name "backup_*" -exec basename {} \; | sort -r | head -1)
                if [ -n "$backup_session" ]; then
                    backup_session="$DR_SESSION_DIR/$backup_session"
                    test_backup_validation "$backup_session"
                else
                    log_error "No backup sessions found for validation"
                fi
            fi
            test_monitoring
            ;;
        *)
            log_error "Invalid test mode: $TEST_MODE"
            exit 1
            ;;
    esac
    
    # Cleanup if requested
    if [ "$CLEANUP_AFTER" = "true" ]; then
        cleanup_test_environment
    fi
    
    # Generate test report
    generate_test_report
    
    local total_duration=$(($(date +%s) - start_time))
    
    # Send notification
    if [ $TEST_ERRORS -eq 0 ]; then
        log "=== Testing completed successfully ==="
        log "Total duration: ${total_duration}s"
        log "Tests passed: $(echo "${TEST_RESULTS[@]}" | grep -o '"status": "PASSED"' | wc -l || echo "0")"
        send_notification "SUCCESS" "DR testing completed successfully. Test ID: $TEST_ID, Duration: ${total_duration}s"
        exit 0
    else
        log "=== Testing completed with errors ==="
        log "Total duration: ${total_duration}s"
        log "Errors: $TEST_ERRORS, Warnings: $TEST_WARNINGS"
        send_notification "ERROR" "DR testing completed with $TEST_ERRORS errors and $TEST_WARNINGS warnings. Test ID: $TEST_ID"
        exit 1
    fi
}

# Check prerequisites
if [ ! -f "$DR_ENCRYPTION_KEY" ]; then
    echo "ERROR: Encryption key not found: $DR_ENCRYPTION_KEY"
    echo "Run setup-encryption.sh first"
    exit 1
fi

# Run main function
main "$@"
