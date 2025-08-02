#!/bin/bash

# Disaster Recovery Monitoring and Alerting Script
# Monitors backup health, system status, and sends alerts

set -euo pipefail

# Load configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$(dirname "$SCRIPT_DIR")/config"
source "$CONFIG_DIR/dr-config.env"

# Global variables
MONITOR_ID="monitor_$(date +%Y%m%d_%H%M%S)_$$"
LOG_FILE="$DR_BACKUP_DIR/logs/monitor-$MONITOR_ID.log"
STATUS_FILE="$DR_BACKUP_DIR/logs/dr-status.json"
ALERT_LEVEL="INFO"  # INFO, WARNING, CRITICAL
ALERTS=()

# Logging functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $1" | tee -a "$LOG_FILE"
}

log_warning() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WARNING] $1" | tee -a "$LOG_FILE"
    ALERT_LEVEL="WARNING"
}

log_critical() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [CRITICAL] $1" | tee -a "$LOG_FILE"
    ALERT_LEVEL="CRITICAL"
}

log_debug() {
    if [ "$DR_DEBUG_MODE" = "true" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [DEBUG] $1" | tee -a "$LOG_FILE"
    fi
}

# Add alert to array
add_alert() {
    local severity="$1"
    local message="$2"
    local alert="{\"severity\": \"$severity\", \"message\": \"$message\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
    ALERTS+=("$alert")
}

# Check backup age
check_backup_age() {
    log "Checking backup age..."
    
    local latest_backup
    latest_backup=$(find "$DR_SESSION_DIR" -type d -name "backup_*" -exec basename {} \; | sort -r | head -1)
    
    if [ -z "$latest_backup" ]; then
        log_critical "No backups found!"
        add_alert "critical" "No backup sessions found in $DR_SESSION_DIR"
        return 1
    fi
    
    local backup_dir="$DR_SESSION_DIR/$latest_backup"
    local manifest_file="$backup_dir/backup-manifest.json"
    
    if [ ! -f "$manifest_file" ]; then
        log_critical "Latest backup manifest not found: $manifest_file"
        add_alert "critical" "Latest backup manifest missing"
        return 1
    fi
    
    # Extract backup time
    local backup_time current_time age_hours
    
    if command -v jq &> /dev/null; then
        backup_time=$(jq -r '.start_time' "$manifest_file" 2>/dev/null || echo "")
        
        if [ -n "$backup_time" ] && [ "$backup_time" != "null" ]; then
            current_time=$(date -u +%Y-%m-%dT%H:%M:%SZ)
            
            # Calculate age in hours
            local backup_epoch current_epoch
            backup_epoch=$(date -d "$backup_time" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%SZ" "$backup_time" +%s 2>/dev/null || echo "0")
            current_epoch=$(date +%s)
            age_hours=$(( (current_epoch - backup_epoch) / 3600 ))
            
            log "Latest backup age: $age_hours hours (session: $latest_backup)"
            
            # Check against alert threshold
            local alert_threshold_hours=$((DR_ALERT_ON_BACKUP_AGE / 3600))
            
            if [ "$age_hours" -gt "$alert_threshold_hours" ]; then
                log_critical "Backup is too old: $age_hours hours (threshold: $alert_threshold_hours hours)"
                add_alert "critical" "Backup age exceeds threshold: $age_hours hours"
                return 1
            else
                log "Backup age is acceptable: $age_hours hours"
                return 0
            fi
        else
            log_warning "Could not extract backup timestamp from manifest"
            add_alert "warning" "Unable to determine backup age"
            return 1
        fi
    else
        # Fallback: check file modification time
        local backup_age_hours
        backup_age_hours=$(find "$backup_dir" -name "backup-manifest.json" -printf '%h\n' | xargs stat -c %Y | head -1)
        backup_age_hours=$(( ($(date +%s) - backup_age_hours) / 3600 ))
        
        log "Latest backup age (estimated): $backup_age_hours hours"
        
        local alert_threshold_hours=$((DR_ALERT_ON_BACKUP_AGE / 3600))
        if [ "$backup_age_hours" -gt "$alert_threshold_hours" ]; then
            log_critical "Backup is too old: $backup_age_hours hours"
            add_alert "critical" "Backup age exceeds threshold: $backup_age_hours hours"
            return 1
        fi
    fi
    
    return 0
}

# Check cloud storage sync
check_cloud_sync() {
    log "Checking cloud storage sync..."
    
    if [ -z "$DR_CLOUD_BUCKET" ]; then
        log_warning "Cloud storage not configured"
        return 0
    fi
    
    # Get latest local backup
    local latest_backup
    latest_backup=$(find "$DR_SESSION_DIR" -type d -name "backup_*" -exec basename {} \; | sort -r | head -1)
    
    if [ -z "$latest_backup" ]; then
        log_warning "No local backup to check cloud sync"
        return 1
    fi
    
    # Check if backup exists in cloud
    local bucket_name
    bucket_name=$(echo "$DR_CLOUD_BUCKET" | sed 's|s3://||')
    local cloud_path="backups/$latest_backup"
    
    if aws s3 ls "s3://$bucket_name/$cloud_path/" > /dev/null 2>&1; then
        log "Latest backup found in cloud: s3://$bucket_name/$cloud_path"
        
        # Compare file counts
        local local_files cloud_files
        local_files=$(find "$DR_SESSION_DIR/$latest_backup" -name "*.enc" -o -name "*.json" | wc -l)
        cloud_files=$(aws s3 ls "s3://$bucket_name/$cloud_path/" --recursive | grep -E '\.(enc|json)$' | wc -l)
        
        if [ "$local_files" -eq "$cloud_files" ]; then
            log "Cloud sync verified: $local_files files match"
            return 0
        else
            log_warning "Cloud sync file count mismatch: $local_files local, $cloud_files cloud"
            add_alert "warning" "Cloud sync file count mismatch: $local_files local vs $cloud_files cloud"
            return 1
        fi
    else
        log_critical "Latest backup not found in cloud storage"
        add_alert "critical" "Latest backup missing from cloud storage"
        return 1
    fi
}

# Check disk space
check_disk_space() {
    log "Checking disk space..."
    
    local usage percentage
    
    if [ -d "$DR_BACKUP_DIR" ]; then
        usage=$(df "$DR_BACKUP_DIR" | tail -1 | awk '{print $5}' | sed 's/%//')
        
        log "Disk usage for backup directory: $usage%"
        
        if [ "$usage" -gt "$DR_ALERT_ON_DISK_USAGE" ]; then
            log_critical "Disk usage too high: $usage% (threshold: $DR_ALERT_ON_DISK_USAGE%)"
            add_alert "critical" "Disk usage critical: $usage% on backup directory"
            return 1
        elif [ "$usage" -gt $((DR_ALERT_ON_DISK_USAGE - 10)) ]; then
            log_warning "Disk usage getting high: $usage%"
            add_alert "warning" "Disk usage high: $usage% on backup directory"
        else
            log "Disk usage is acceptable: $usage%"
        fi
    else
        log_warning "Backup directory not found: $DR_BACKUP_DIR"
        add_alert "warning" "Backup directory not accessible"
        return 1
    fi
    
    return 0
}

# Check service health
check_service_health() {
    log "Checking service health..."
    
    cd "$PROJECT_ROOT"
    
    # Check if docker-compose file exists
    if [ ! -f "$DOCKER_COMPOSE_FILE" ]; then
        log_critical "Docker Compose file not found: $DOCKER_COMPOSE_FILE"
        add_alert "critical" "Docker Compose configuration missing"
        return 1
    fi
    
    # Check running services
    local running_services expected_services unhealthy_services
    
    if command -v docker-compose &> /dev/null; then
        running_services=$(docker-compose -f "$DOCKER_COMPOSE_FILE" ps --services --filter "status=running" | wc -l)
        expected_services=$(docker-compose -f "$DOCKER_COMPOSE_FILE" config --services | wc -l)
        unhealthy_services=$(docker-compose -f "$DOCKER_COMPOSE_FILE" ps --filter "status=exited" --format table | tail -n +2 | wc -l)
        
        log "Service status: $running_services/$expected_services running, $unhealthy_services unhealthy"
        
        if [ "$unhealthy_services" -gt 0 ]; then
            log_critical "Unhealthy services detected: $unhealthy_services"
            add_alert "critical" "$unhealthy_services services are not running properly"
            
            # List unhealthy services
            local unhealthy_list
            unhealthy_list=$(docker-compose -f "$DOCKER_COMPOSE_FILE" ps --filter "status=exited" --format "{{.Service}}" | tr '\n' ', ' | sed 's/,$//')
            if [ -n "$unhealthy_list" ]; then
                log_critical "Unhealthy services: $unhealthy_list"
                add_alert "critical" "Unhealthy services: $unhealthy_list"
            fi
            return 1
        elif [ "$running_services" -lt "$expected_services" ]; then
            log_warning "Some services are not running: $running_services/$expected_services"
            add_alert "warning" "Not all services are running: $running_services/$expected_services"
        else
            log "All services are running normally"
        fi
    else
        log_warning "Docker Compose not available, cannot check service health"
        add_alert "warning" "Cannot check service health: Docker Compose unavailable"
        return 1
    fi
    
    # Check PostgreSQL specifically
    export PGPASSWORD="$POSTGRES_PASSWORD"
    if pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" 2>/dev/null; then
        log "PostgreSQL is responsive"
    else
        log_critical "PostgreSQL is not responsive"
        add_alert "critical" "PostgreSQL database is not responding"
        return 1
    fi
    
    return 0
}

# Check backup integrity
check_backup_integrity() {
    log "Checking backup integrity..."
    
    local latest_backup
    latest_backup=$(find "$DR_SESSION_DIR" -type d -name "backup_*" -exec basename {} \; | sort -r | head -1)
    
    if [ -z "$latest_backup" ]; then
        log_warning "No backup found for integrity check"
        return 1
    fi
    
    local backup_dir="$DR_SESSION_DIR/$latest_backup"
    local manifest_file="$backup_dir/backup-manifest.json"
    
    if [ ! -f "$manifest_file" ]; then
        log_critical "Backup manifest missing: $manifest_file"
        add_alert "critical" "Backup manifest file missing"
        return 1
    fi
    
    # Check if backup completed successfully
    if command -v jq &> /dev/null; then
        local backup_status backup_errors
        backup_status=$(jq -r '.metadata.status // "unknown"' "$manifest_file")
        backup_errors=$(jq -r '.metadata.errors // 0' "$manifest_file")
        
        if [ "$backup_status" = "success" ] && [ "$backup_errors" -eq 0 ]; then
            log "Latest backup integrity: OK (status: $backup_status, errors: $backup_errors)"
        else
            log_critical "Latest backup has issues: status=$backup_status, errors=$backup_errors"
            add_alert "critical" "Latest backup completed with errors: $backup_errors"
            return 1
        fi
    fi
    
    # Quick validation of a sample file
    if [ -f "$DR_ENCRYPTION_KEY" ]; then
        local sample_backup
        sample_backup=$(find "$backup_dir" -name "*.enc" | head -1)
        
        if [ -f "$sample_backup" ]; then
            local key temp_file
            key=$(cat "$DR_ENCRYPTION_KEY")
            temp_file="/tmp/integrity_check_$$.tmp"
            
            if openssl enc -d -aes-256-cbc -in "$sample_backup" -out "$temp_file" -k "$key" 2>/dev/null; then
                log "Sample backup file decryption: OK"
                rm -f "$temp_file"
            else
                log_critical "Sample backup file decryption failed"
                add_alert "critical" "Backup file decryption test failed"
                rm -f "$temp_file"
                return 1
            fi
        fi
    else
        log_warning "Encryption key not found, cannot test decryption"
        add_alert "warning" "Cannot verify backup encryption: key missing"
    fi
    
    return 0
}

# Check system resources
check_system_resources() {
    log "Checking system resources..."
    
    # Check memory usage
    if command -v free &> /dev/null; then
        local mem_usage
        mem_usage=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100.0}')
        log "Memory usage: $mem_usage%"
        
        if [ "$mem_usage" -gt 90 ]; then
            log_critical "High memory usage: $mem_usage%"
            add_alert "critical" "System memory usage critical: $mem_usage%"
        elif [ "$mem_usage" -gt 80 ]; then
            log_warning "High memory usage: $mem_usage%"
            add_alert "warning" "System memory usage high: $mem_usage%"
        fi
    fi
    
    # Check load average
    if [ -f /proc/loadavg ]; then
        local load_avg
        load_avg=$(cat /proc/loadavg | cut -d' ' -f1)
        local cpu_count
        cpu_count=$(nproc)
        local load_percentage
        load_percentage=$(echo "$load_avg $cpu_count" | awk '{printf "%.0f", $1/$2 * 100}')
        
        log "Load average: $load_avg ($load_percentage% of CPU capacity)"
        
        if [ "$load_percentage" -gt 100 ]; then
            log_warning "High system load: $load_percentage%"
            add_alert "warning" "System load high: $load_percentage%"
        fi
    fi
    
    return 0
}

# Generate status report
generate_status_report() {
    local overall_status
    overall_status=$( [ "$ALERT_LEVEL" = "INFO" ] && echo "healthy" || echo "issues" )
    
    # Convert alerts array to JSON
    local alerts_json="["
    local first=true
    for alert in "${ALERTS[@]}"; do
        if [ "$first" = true ]; then
            first=false
        else
            alerts_json="$alerts_json,"
        fi
        alerts_json="$alerts_json$alert"
    done
    alerts_json="$alerts_json]"
    
    cat > "$STATUS_FILE" << EOF
{
    "monitor_id": "$MONITOR_ID",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "overall_status": "$overall_status",
    "alert_level": "$ALERT_LEVEL",
    "alerts": $alerts_json,
    "system": {
        "hostname": "$(hostname)",
        "uptime": "$(uptime -p 2>/dev/null || uptime)",
        "disk_usage": "$(df "$DR_BACKUP_DIR" 2>/dev/null | tail -1 | awk '{print $5}' || echo "unknown")",
        "backup_directory": "$DR_BACKUP_DIR"
    },
    "backup_status": {
        "latest_session": "$(find "$DR_SESSION_DIR" -type d -name "backup_*" -exec basename {} \; | sort -r | head -1 || echo "none")",
        "cloud_configured": $( [ -n "$DR_CLOUD_BUCKET" ] && echo "true" || echo "false" ),
        "encryption_key_exists": $( [ -f "$DR_ENCRYPTION_KEY" ] && echo "true" || echo "false" )
    },
    "monitoring": {
        "version": "1.0",
        "config_file": "$CONFIG_DIR/dr-config.env",
        "log_file": "$LOG_FILE"
    }
}
EOF
    
    log "Status report generated: $STATUS_FILE"
}

# Send alerts
send_alerts() {
    if [ ${#ALERTS[@]} -eq 0 ]; then
        log "No alerts to send"
        return 0
    fi
    
    log "Sending $ALERT_LEVEL level alert with ${#ALERTS[@]} issues"
    
    # Prepare alert message
    local alert_message="DR Monitoring Alert - $ALERT_LEVEL\n\n"
    alert_message="$alert_message""Monitor ID: $MONITOR_ID\n"
    alert_message="$alert_message""Timestamp: $(date)\n"
    alert_message="$alert_message""System: $(hostname)\n\n"
    alert_message="$alert_message""Issues detected:\n"
    
    for alert in "${ALERTS[@]}"; do
        if command -v jq &> /dev/null; then
            local severity message
            severity=$(echo "$alert" | jq -r '.severity')
            message=$(echo "$alert" | jq -r '.message')
            alert_message="$alert_message""- [$severity] $message\n"
        else
            alert_message="$alert_message""- $alert\n"
        fi
    done
    
    alert_message="$alert_message""\nFor details, check: $LOG_FILE\n"
    alert_message="$alert_message""Status report: $STATUS_FILE"
    
    # Email notification
    if [ -n "$DR_NOTIFICATION_EMAIL" ] && command -v mail &> /dev/null; then
        echo -e "$alert_message" | mail -s "DR Monitoring Alert [$ALERT_LEVEL] - $(hostname)" "$DR_NOTIFICATION_EMAIL"
        log "Email alert sent to $DR_NOTIFICATION_EMAIL"
    fi
    
    # Webhook notification (Slack, etc.)
    if [ -n "$DR_WEBHOOK_URL" ]; then
        local color
        case "$ALERT_LEVEL" in
            "CRITICAL") color="danger" ;;
            "WARNING") color="warning" ;;
            *) color="good" ;;
        esac
        
        local webhook_payload
        webhook_payload=$(cat << EOF
{
    "text": "DR Monitoring Alert [$ALERT_LEVEL]",
    "attachments": [
        {
            "color": "$color",
            "fields": [
                {"title": "System", "value": "$(hostname)", "short": true},
                {"title": "Alert Level", "value": "$ALERT_LEVEL", "short": true},
                {"title": "Issues", "value": "${#ALERTS[@]}", "short": true},
                {"title": "Monitor ID", "value": "$MONITOR_ID", "short": true}
            ],
            "text": "$(echo -e "$alert_message" | head -20 | tr '\n' ' ')"
        }
    ]
}
EOF
)
        
        if curl -X POST -H 'Content-type: application/json' --data "$webhook_payload" "$DR_WEBHOOK_URL" 2>/dev/null; then
            log "Webhook alert sent"
        else
            log_warning "Failed to send webhook alert"
        fi
    fi
}

# Cleanup old logs
cleanup_old_logs() {
    log "Cleaning up old monitoring logs..."
    
    # Clean logs older than retention period
    find "$DR_BACKUP_DIR/logs" -name "monitor-*.log" -type f -mtime +7 -delete 2>/dev/null || true
    find "$DR_BACKUP_DIR/logs" -name "validation-*.log" -type f -mtime +7 -delete 2>/dev/null || true
    find "$DR_BACKUP_DIR/logs" -name "recovery-*.log" -type f -mtime +30 -delete 2>/dev/null || true
    
    log "Log cleanup completed"
}

# Main monitoring function
main() {
    log "=== Starting DR Monitoring Check ==="
    log "Monitor ID: $MONITOR_ID"
    log "Configuration: $CONFIG_DIR/dr-config.env"
    
    # Create logs directory if it doesn't exist
    mkdir -p "$DR_BACKUP_DIR/logs"
    
    # Run all checks
    check_backup_age
    check_cloud_sync
    check_disk_space
    check_service_health
    check_backup_integrity
    check_system_resources
    
    # Generate status report
    generate_status_report
    
    # Send alerts if any issues found
    if [ ${#ALERTS[@]} -gt 0 ]; then
        send_alerts
    fi
    
    # Cleanup old logs
    cleanup_old_logs
    
    log "=== Monitoring check completed ==="
    log "Alert level: $ALERT_LEVEL"
    log "Issues found: ${#ALERTS[@]}"
    log "Status report: $STATUS_FILE"
    
    # Exit with appropriate code
    case "$ALERT_LEVEL" in
        "CRITICAL") exit 2 ;;
        "WARNING") exit 1 ;;
        *) exit 0 ;;
    esac
}

# Run main function
main "$@"
