#!/bin/bash

# Disaster Recovery Script
# Complete system restoration from encrypted backups

set -euo pipefail

# Load configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$(dirname "$SCRIPT_DIR")/config"
source "$CONFIG_DIR/dr-config.env"

# Global variables
RECOVERY_ID="recovery_$(date +%Y%m%d_%H%M%S)_$$"
LOG_FILE="$DR_BACKUP_DIR/logs/recovery-$RECOVERY_ID.log"
RECOVERY_ERRORS=0
RECOVERY_WARNINGS=0
PRE_RECOVERY_BACKUP=""
RECOVERY_MODE="full"  # full, database-only, files-only, config-only

# Logging functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $1" | tee -a "$LOG_FILE" >&2
    ((RECOVERY_ERRORS++))
}

log_warning() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WARNING] $1" | tee -a "$LOG_FILE"
    ((RECOVERY_WARNINGS++))
}

log_success() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [SUCCESS] $1" | tee -a "$LOG_FILE"
}

log_critical() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [CRITICAL] $1" | tee -a "$LOG_FILE" >&2
}

# Error handling and cleanup
cleanup_on_error() {
    log_critical "Recovery failed. System may be in an inconsistent state!"
    log_critical "Pre-recovery backup available at: $PRE_RECOVERY_BACKUP"
    log_critical "Recovery ID: $RECOVERY_ID"
    
    send_notification "CRITICAL" "Disaster recovery FAILED! System may be down. Recovery ID: $RECOVERY_ID"
    exit 1
}

trap cleanup_on_error ERR

# Display usage information
usage() {
    cat << EOF
Usage: $0 [OPTIONS] [BACKUP_SESSION]

Disaster Recovery Script for Odoo Multi-Tenant System

OPTIONS:
    -m, --mode MODE         Recovery mode: full, database-only, files-only, config-only
    -s, --session SESSION   Specific backup session to restore from
    -c, --cloud             Download from cloud storage instead of local
    -f, --force             Skip confirmation prompts (DANGEROUS)
    -t, --test             Test mode: validate recovery without making changes
    -h, --help             Show this help message

BACKUP_SESSION:
    Specific backup session directory name or 'latest' for most recent backup

Examples:
    $0                                    # Full recovery from latest backup
    $0 -m database-only latest           # Restore only databases from latest backup
    $0 -s backup_20231201_120000_1234    # Restore from specific session
    $0 -c -s backup_20231201_120000_1234 # Download and restore from cloud

IMPORTANT: This script will stop services and may cause downtime!
EOF
}

# Parse command line arguments
parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -m|--mode)
                RECOVERY_MODE="$2"
                shift 2
                ;;
            -s|--session)
                BACKUP_SESSION="$2"
                shift 2
                ;;
            -c|--cloud)
                USE_CLOUD="true"
                shift
                ;;
            -f|--force)
                FORCE="true"
                shift
                ;;
            -t|--test)
                TEST_MODE="true"
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                if [ -z "${BACKUP_SESSION:-}" ]; then
                    BACKUP_SESSION="$1"
                fi
                shift
                ;;
        esac
    done
    
    # Set defaults
    BACKUP_SESSION="${BACKUP_SESSION:-latest}"
    USE_CLOUD="${USE_CLOUD:-false}"
    FORCE="${FORCE:-false}"
    TEST_MODE="${TEST_MODE:-false}"
}

# Confirmation prompt
confirm_recovery() {
    if [ "$FORCE" = "true" ] || [ "$TEST_MODE" = "true" ]; then
        return 0
    fi
    
    log_critical "WARNING: This will restore the system from backup!"
    log_critical "Current data will be replaced with backup data!"
    log_critical "Services will be stopped during recovery!"
    
    echo
    echo "Recovery details:"
    echo "  Mode: $RECOVERY_MODE"
    echo "  Session: $BACKUP_SESSION"
    echo "  Cloud: $USE_CLOUD"
    echo "  Recovery ID: $RECOVERY_ID"
    echo
    
    read -p "Are you sure you want to proceed? Type 'YES' to continue: " confirm
    if [ "$confirm" != "YES" ]; then
        log "Recovery cancelled by user"
        exit 0
    fi
}

# Find backup session
find_backup_session() {
    local session_name="$1"
    local session_dir
    
    if [ "$session_name" = "latest" ]; then
        session_dir=$(find "$DR_SESSION_DIR" -type d -name "backup_*" -exec basename {} \; | sort -r | head -1)
        if [ -z "$session_dir" ]; then
            log_error "No backup sessions found"
            return 1
        fi
        session_dir="$DR_SESSION_DIR/$session_dir"
    else
        session_dir="$DR_SESSION_DIR/$session_name"
        if [ ! -d "$session_dir" ]; then
            log_error "Backup session not found: $session_dir"
            return 1
        fi
    fi
    
    log "Using backup session: $(basename "$session_dir")"
    echo "$session_dir"
}

# Download backup from cloud
download_from_cloud() {
    local session_name="$1"
    local local_session_dir="$DR_SESSION_DIR/$session_name"
    
    log "Downloading backup from cloud storage..."
    
    local bucket_name
    bucket_name=$(echo "$DR_CLOUD_BUCKET" | sed 's|s3://||')
    local cloud_path="backups/$session_name"
    
    # Create local session directory
    mkdir -p "$local_session_dir"
    
    # Download backup files
    if aws s3 sync "s3://$bucket_name/$cloud_path" "$local_session_dir" \
        --exclude "*" --include "*.enc" --include "*.json"; then
        log_success "Downloaded backup from cloud: s3://$bucket_name/$cloud_path"
        echo "$local_session_dir"
    else
        log_error "Failed to download backup from cloud"
        return 1
    fi
}

# Create pre-recovery backup
create_pre_recovery_backup() {
    log "Creating pre-recovery backup of current state..."
    
    local pre_backup_dir="$DR_SESSION_DIR/pre_recovery_$RECOVERY_ID"
    PRE_RECOVERY_BACKUP="$pre_backup_dir"
    
    mkdir -p "$pre_backup_dir"/{databases,filestore,configs}
    
    # Quick database backup (only if databases exist)
    if docker-compose -f "$DOCKER_COMPOSE_FILE" ps postgres | grep -q "Up"; then
        log "Backing up current databases..."
        export PGPASSWORD="$POSTGRES_PASSWORD"
        
        local databases
        databases=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_MASTER_DB" -t -c \
            "SELECT datname FROM pg_database WHERE datistemplate = false AND datname != 'postgres';" | \
            grep -v "^$" | sed 's/^ *//' | sed 's/ *$//' || true)
        
        if [ -n "$databases" ]; then
            while IFS= read -r db_name; do
                if [ -n "$db_name" ]; then
                    pg_dump -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$db_name" \
                        --format=custom > "$pre_backup_dir/databases/${db_name}.dump" || true
                fi
            done <<< "$databases"
        fi
    fi
    
    # Backup current filestore
    if [ -d "$ODOO_FILESTORE_PATH" ]; then
        tar -czf "$pre_backup_dir/filestore/current_filestore.tar.gz" \
            -C "$ODOO_FILESTORE_PATH" . 2>/dev/null || true
    fi
    
    # Backup current configurations
    if [ -f "$DOCKER_COMPOSE_FILE" ]; then
        cp "$DOCKER_COMPOSE_FILE" "$pre_backup_dir/configs/" || true
    fi
    
    log_success "Pre-recovery backup created: $PRE_RECOVERY_BACKUP"
}

# Stop services safely
stop_services() {
    log "Stopping services for recovery..."
    
    if [ "$TEST_MODE" = "true" ]; then
        log "TEST MODE: Would stop services"
        return 0
    fi
    
    cd "$PROJECT_ROOT"
    
    # Graceful shutdown
    if docker-compose -f "$DOCKER_COMPOSE_FILE" ps | grep -q "Up"; then
        log "Stopping Docker Compose services..."
        docker-compose -f "$DOCKER_COMPOSE_FILE" down --timeout 30
        
        # Wait for services to stop
        local timeout=60
        while [ $timeout -gt 0 ] && docker-compose -f "$DOCKER_COMPOSE_FILE" ps | grep -q "Up"; do
            sleep 2
            ((timeout-=2))
        done
        
        if docker-compose -f "$DOCKER_COMPOSE_FILE" ps | grep -q "Up"; then
            log_warning "Some services did not stop gracefully, forcing shutdown..."
            docker-compose -f "$DOCKER_COMPOSE_FILE" down --timeout 5 --remove-orphans
        fi
    fi
    
    log_success "Services stopped successfully"
}

# Start services
start_services() {
    log "Starting services after recovery..."
    
    if [ "$TEST_MODE" = "true" ]; then
        log "TEST MODE: Would start services"
        return 0
    fi
    
    cd "$PROJECT_ROOT"
    
    # Start services
    if docker-compose -f "$DOCKER_COMPOSE_FILE" up -d; then
        log "Services started, waiting for health checks..."
        
        # Wait for services to be healthy
        local timeout=300  # 5 minutes
        local healthy=false
        
        while [ $timeout -gt 0 ]; do
            if docker-compose -f "$DOCKER_COMPOSE_FILE" ps | grep -v "Exit\|Restarting"; then
                healthy=true
                break
            fi
            sleep 10
            ((timeout-=10))
        done
        
        if [ "$healthy" = "true" ]; then
            log_success "Services started successfully"
        else
            log_error "Services failed to start properly within timeout"
            return 1
        fi
    else
        log_error "Failed to start services"
        return 1
    fi
}

# Restore databases
restore_databases() {
    local session_dir="$1"
    local db_dir="$session_dir/databases"
    
    log "Restoring databases..."
    
    if [ ! -d "$db_dir" ]; then
        log_error "Database backup directory not found: $db_dir"
        return 1
    fi
    
    export PGPASSWORD="$POSTGRES_PASSWORD"
    
    # Wait for PostgreSQL to be ready
    log "Waiting for PostgreSQL to be ready..."
    local timeout=60
    while [ $timeout -gt 0 ]; do
        if pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" 2>/dev/null; then
            break
        fi
        sleep 2
        ((timeout-=2))
    done
    
    if [ $timeout -eq 0 ]; then
        log_error "PostgreSQL is not ready"
        return 1
    fi
    
    # Restore each database
    for db_backup in "$db_dir"/*.sql.enc; do
        if [ -f "$db_backup" ]; then
            local db_name
            db_name=$(basename "$db_backup" .sql.enc)
            
            log "Restoring database: $db_name"
            
            if [ "$TEST_MODE" = "true" ]; then
                log "TEST MODE: Would restore database $db_name"
                continue
            fi
            
            # Decrypt backup
            local key temp_sql
            key=$(cat "$DR_ENCRYPTION_KEY")
            temp_sql="/tmp/restore_${db_name}_$$.sql"
            
            if ! openssl enc -d -aes-256-cbc -in "$db_backup" -out "$temp_sql" -k "$key"; then
                log_error "Failed to decrypt database backup: $db_name"
                continue
            fi
            
            # Drop existing database if it exists
            psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_MASTER_DB" \
                -c "DROP DATABASE IF EXISTS \"$db_name\";" || true
            
            # Create new database
            psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_MASTER_DB" \
                -c "CREATE DATABASE \"$db_name\";"
            
            # Restore database from custom format
            if pg_restore -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
                -d "$db_name" --clean --no-owner --no-privileges "$temp_sql"; then
                log_success "Successfully restored database: $db_name"
            else
                log_error "Failed to restore database: $db_name"
            fi
            
            # Cleanup temporary file
            rm -f "$temp_sql"
        fi
    done
    
    log_success "Database restoration completed"
}

# Restore filestore
restore_filestore() {
    local session_dir="$1"
    local filestore_backup="$session_dir/filestore/filestore.tar.gz.enc"
    
    log "Restoring filestore..."
    
    if [ ! -f "$filestore_backup" ]; then
        log_warning "Filestore backup not found: $filestore_backup"
        return 1
    fi
    
    if [ "$TEST_MODE" = "true" ]; then
        log "TEST MODE: Would restore filestore"
        return 0
    fi
    
    # Decrypt and extract filestore
    local key temp_archive
    key=$(cat "$DR_ENCRYPTION_KEY")
    temp_archive="/tmp/restore_filestore_$$.tar.gz"
    
    if ! openssl enc -d -aes-256-cbc -in "$filestore_backup" -out "$temp_archive" -k "$key"; then
        log_error "Failed to decrypt filestore backup"
        return 1
    fi
    
    # Create backup of current filestore
    if [ -d "$ODOO_FILESTORE_PATH" ]; then
        mv "$ODOO_FILESTORE_PATH" "${ODOO_FILESTORE_PATH}.bak.$$"
    fi
    
    # Create new filestore directory
    mkdir -p "$ODOO_FILESTORE_PATH"
    
    # Extract filestore
    if tar -xzf "$temp_archive" -C "$ODOO_FILESTORE_PATH"; then
        log_success "Successfully restored filestore"
        # Remove backup
        rm -rf "${ODOO_FILESTORE_PATH}.bak.$$" 2>/dev/null || true
    else
        log_error "Failed to restore filestore"
        # Restore original if extraction failed
        if [ -d "${ODOO_FILESTORE_PATH}.bak.$$" ]; then
            rm -rf "$ODOO_FILESTORE_PATH"
            mv "${ODOO_FILESTORE_PATH}.bak.$$" "$ODOO_FILESTORE_PATH"
        fi
        rm -f "$temp_archive"
        return 1
    fi
    
    # Cleanup
    rm -f "$temp_archive"
    
    log_success "Filestore restoration completed"
}

# Restore configurations
restore_configurations() {
    local session_dir="$1"
    local config_dir="$session_dir/configs"
    
    log "Restoring configurations..."
    
    if [ ! -d "$config_dir" ]; then
        log_warning "Configuration backup directory not found: $config_dir"
        return 1
    fi
    
    for config_backup in "$config_dir"/*.tar.gz.enc; do
        if [ -f "$config_backup" ]; then
            local config_name
            config_name=$(basename "$config_backup" .tar.gz.enc)
            
            log "Restoring configuration: $config_name"
            
            if [ "$TEST_MODE" = "true" ]; then
                log "TEST MODE: Would restore configuration $config_name"
                continue
            fi
            
            # Decrypt configuration
            local key temp_archive
            key=$(cat "$DR_ENCRYPTION_KEY")
            temp_archive="/tmp/restore_${config_name}_$$.tar.gz"
            
            if ! openssl enc -d -aes-256-cbc -in "$config_backup" -out "$temp_archive" -k "$key"; then
                log_error "Failed to decrypt configuration backup: $config_name"
                continue
            fi
            
            # Extract to appropriate location based on config name
            case "$config_name" in
                "docker-compose.yml")
                    tar -xzf "$temp_archive" -C "$PROJECT_ROOT"
                    ;;
                "nginx")
                    tar -xzf "$temp_archive" -C "$(dirname "$NGINX_CONFIG_PATH")"
                    ;;
                "ssl")
                    tar -xzf "$temp_archive" -C "$(dirname "$SSL_CERTS_PATH")"
                    ;;
                *)
                    log_warning "Unknown configuration type: $config_name"
                    ;;
            esac
            
            rm -f "$temp_archive"
            log_success "Successfully restored configuration: $config_name"
        fi
    done
    
    log_success "Configuration restoration completed"
}

# Perform health checks
perform_health_checks() {
    log "Performing post-recovery health checks..."
    
    if [ "$TEST_MODE" = "true" ]; then
        log "TEST MODE: Would perform health checks"
        return 0
    fi
    
    local health_errors=0
    
    # Check PostgreSQL
    log "Checking PostgreSQL health..."
    if pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" 2>/dev/null; then
        log_success "PostgreSQL is healthy"
    else
        log_error "PostgreSQL health check failed"
        ((health_errors++))
    fi
    
    # Check databases
    log "Checking database accessibility..."
    export PGPASSWORD="$POSTGRES_PASSWORD"
    local databases
    databases=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_MASTER_DB" -t -c \
        "SELECT datname FROM pg_database WHERE datistemplate = false AND datname != 'postgres';" | \
        grep -v "^$" | sed 's/^ *//' | sed 's/ *$//' || true)
    
    if [ -n "$databases" ]; then
        while IFS= read -r db_name; do
            if [ -n "$db_name" ]; then
                if psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$db_name" \
                    -c "SELECT 1;" > /dev/null 2>&1; then
                    log_success "Database accessible: $db_name"
                else
                    log_error "Database not accessible: $db_name"
                    ((health_errors++))
                fi
            fi
        done <<< "$databases"
    fi
    
    # Check Docker services
    log "Checking Docker services..."
    cd "$PROJECT_ROOT"
    local unhealthy_services
    unhealthy_services=$(docker-compose -f "$DOCKER_COMPOSE_FILE" ps --filter "status=exited" --format table | tail -n +2 || true)
    
    if [ -n "$unhealthy_services" ]; then
        log_error "Some services are not running:"
        echo "$unhealthy_services" | while read -r line; do
            log_error "  $line"
        done
        ((health_errors++))
    else
        log_success "All Docker services are running"
    fi
    
    # Check filestore
    if [ -d "$ODOO_FILESTORE_PATH" ]; then
        local filestore_files
        filestore_files=$(find "$ODOO_FILESTORE_PATH" -type f | wc -l)
        log_success "Filestore accessible with $filestore_files files"
    else
        log_error "Filestore directory not found"
        ((health_errors++))
    fi
    
    if [ $health_errors -eq 0 ]; then
        log_success "All health checks passed"
        return 0
    else
        log_error "Health checks failed with $health_errors errors"
        return 1
    fi
}

# Send notification
send_notification() {
    local status="$1"
    local message="$2"
    
    # Email notification
    if [ -n "$DR_NOTIFICATION_EMAIL" ] && command -v mail &> /dev/null; then
        echo "$message" | mail -s "DR Recovery [$status] - $RECOVERY_ID" "$DR_NOTIFICATION_EMAIL"
    fi
    
    # Log notification
    log "NOTIFICATION [$status]: $message"
}

# Generate recovery report
generate_recovery_report() {
    local status="$1"
    local session_dir="$2"
    local report_file="$DR_BACKUP_DIR/logs/recovery-report-$RECOVERY_ID.json"
    
    cat > "$report_file" << EOF
{
    "recovery_id": "$RECOVERY_ID",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "mode": "$RECOVERY_MODE",
    "session_restored": "$(basename "$session_dir")",
    "cloud_source": $USE_CLOUD,
    "test_mode": $TEST_MODE,
    "results": {
        "status": "$status",
        "errors": $RECOVERY_ERRORS,
        "warnings": $RECOVERY_WARNINGS
    },
    "pre_recovery_backup": "$PRE_RECOVERY_BACKUP",
    "system": {
        "hostname": "$(hostname)",
        "recovery_version": "1.0"
    }
}
EOF
    
    log "Recovery report generated: $report_file"
}

# Main recovery function
main() {
    local start_time
    start_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    
    log "=== Starting Disaster Recovery ==="
    log "Recovery ID: $RECOVERY_ID"
    log "Mode: $RECOVERY_MODE"
    log "Test Mode: $TEST_MODE"
    
    # Parse arguments
    parse_arguments "$@"
    
    # Confirm recovery
    confirm_recovery
    
    # Check prerequisites
    if [ ! -f "$DR_ENCRYPTION_KEY" ]; then
        log_error "Encryption key not found: $DR_ENCRYPTION_KEY"
        exit 1
    fi
    
    # Find or download backup session
    local session_dir
    if [ "$USE_CLOUD" = "true" ]; then
        session_dir=$(download_from_cloud "$BACKUP_SESSION")
    else
        session_dir=$(find_backup_session "$BACKUP_SESSION")
    fi
    
    # Create pre-recovery backup
    create_pre_recovery_backup
    
    # Stop services
    stop_services
    
    # Perform recovery based on mode
    case "$RECOVERY_MODE" in
        "full")
            restore_databases "$session_dir"
            restore_filestore "$session_dir"
            restore_configurations "$session_dir"
            ;;
        "database-only")
            restore_databases "$session_dir"
            ;;
        "files-only")
            restore_filestore "$session_dir"
            ;;
        "config-only")
            restore_configurations "$session_dir"
            ;;
        *)
            log_error "Invalid recovery mode: $RECOVERY_MODE"
            exit 1
            ;;
    esac
    
    # Start services (except for config-only mode)
    if [ "$RECOVERY_MODE" != "config-only" ] && [ "$DR_AUTO_START_SERVICES" = "true" ]; then
        start_services
    fi
    
    # Perform health checks
    if [ "$DR_POST_RECOVERY_HEALTH_CHECK" = "true" ]; then
        perform_health_checks
    fi
    
    # Generate report
    local final_status
    final_status=$( [ $RECOVERY_ERRORS -eq 0 ] && echo "success" || echo "failed" )
    generate_recovery_report "$final_status" "$session_dir"
    
    # Send notification
    if [ $RECOVERY_ERRORS -eq 0 ]; then
        log "=== Recovery completed successfully ==="
        send_notification "SUCCESS" "Disaster recovery completed successfully. Mode: $RECOVERY_MODE, Session: $(basename "$session_dir"), Warnings: $RECOVERY_WARNINGS"
        exit 0
    else
        log "=== Recovery completed with errors ==="
        send_notification "ERROR" "Disaster recovery completed with $RECOVERY_ERRORS errors and $RECOVERY_WARNINGS warnings. Mode: $RECOVERY_MODE, Session: $(basename "$session_dir")"
        exit 1
    fi
}

# Check if running with appropriate permissions
if [ "$EUID" -eq 0 ]; then
    log_warning "Running as root. Consider using a dedicated user."
fi

# Run main function
main "$@"
