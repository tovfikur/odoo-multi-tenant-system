#!/bin/bash

# Odoo SaaS System Backup Script
# This script backs up PostgreSQL databases and filestore data

set -e

# Configuration
BACKUP_DIR="/opt/backups"
POSTGRES_HOST="postgres"
POSTGRES_USER="odoo_master"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
DATE=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${BACKUP_DIR}/backup.log"

# Ensure backup directory exists
mkdir -p "${BACKUP_DIR}/databases"
mkdir -p "${BACKUP_DIR}/filestore"
mkdir -p "${BACKUP_DIR}/logs"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
}

# Function to backup a single database
backup_database() {
    local db_name=$1
    local backup_file="${BACKUP_DIR}/databases/${db_name}_${DATE}.sql"
    
    log "Starting backup of database: ${db_name}"
    
    export PGPASSWORD="${POSTGRES_PASSWORD}"
    
    if pg_dump -h "${POSTGRES_HOST}" -U "${POSTGRES_USER}" -d "${db_name}" \
        --verbose --clean --no-owner --no-privileges > "${backup_file}"; then
        
        # Compress the backup
        gzip "${backup_file}"
        log "Successfully backed up database: ${db_name}"
        return 0
    else
        log "ERROR: Failed to backup database: ${db_name}"
        return 1
    fi
}

# Function to backup filestore
backup_filestore() {
    local filestore_source="/opt/odoo/filestore"
    local filestore_backup="${BACKUP_DIR}/filestore/filestore_${DATE}.tar.gz"
    
    log "Starting filestore backup"
    
    if [ -d "${filestore_source}" ]; then
        if tar -czf "${filestore_backup}" -C "${filestore_source}" .; then
            log "Successfully backed up filestore"
            return 0
        else
            log "ERROR: Failed to backup filestore"
            return 1
        fi
    else
        log "WARNING: Filestore directory not found: ${filestore_source}"
        return 1
    fi
}

# Function to get list of databases
get_databases() {
    export PGPASSWORD="${POSTGRES_PASSWORD}"
    
    psql -h "${POSTGRES_HOST}" -U "${POSTGRES_USER}" -d postgres -t -c \
        "SELECT datname FROM pg_database WHERE datistemplate = false AND datname != 'postgres';" | \
        grep -v "^$" | sed 's/^ *//' | sed 's/ *$//'
}

# Function to cleanup old backups
cleanup_old_backups() {
    log "Cleaning up backups older than ${RETENTION_DAYS} days"
    
    # Clean database backups
    find "${BACKUP_DIR}/databases" -name "*.sql.gz" -type f -mtime +${RETENTION_DAYS} -delete
    
    # Clean filestore backups
    find "${BACKUP_DIR}/filestore" -name "*.tar.gz" -type f -mtime +${RETENTION_DAYS} -delete
    
    # Clean log files
    find "${BACKUP_DIR}/logs" -name "*.log" -type f -mtime +${RETENTION_DAYS} -delete
    
    log "Cleanup completed"
}

# Function to send notification
send_notification() {
    local status=$1
    local message=$2
    
    # You can implement email notification here
    # For now, just log the message
    log "NOTIFICATION [${status}]: ${message}"
}

# Main backup function
main() {
    log "=== Starting Odoo SaaS System Backup ==="
    
    local backup_errors=0
    
    # Get list of databases to backup
    databases=$(get_databases)
    
    if [ -z "${databases}" ]; then
        log "WARNING: No databases found to backup"
        send_notification "WARNING" "No databases found to backup"
        exit 1
    fi
    
    # Backup each database
    while IFS= read -r db_name; do
        if [ -n "${db_name}" ]; then
            if ! backup_database "${db_name}"; then
                ((backup_errors++))
            fi
        fi
    done <<< "${databases}"
    
    # Backup filestore
    if ! backup_filestore; then
        ((backup_errors++))
    fi
    
    # Cleanup old backups
    cleanup_old_backups
    
    # Report results
    if [ ${backup_errors} -eq 0 ]; then
        log "=== Backup completed successfully ==="
        send_notification "SUCCESS" "All backups completed successfully"
        exit 0
    else
        log "=== Backup completed with ${backup_errors} errors ==="
        send_notification "ERROR" "Backup completed with ${backup_errors} errors"
        exit 1
    fi
}

# Check if running as root or with appropriate permissions
if [ "$EUID" -ne 0 ] && [ "$(id -u)" != "999" ]; then
    echo "This script should be run as root or docker user"
    exit 1
fi

# Run main function
main "$@"