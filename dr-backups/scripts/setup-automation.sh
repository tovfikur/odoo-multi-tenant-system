#!/bin/bash

# Automation Setup Script
# Configures cron jobs and automated scheduling for DR system

set -euo pipefail

# Load configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$(dirname "$SCRIPT_DIR")/config"
source "$CONFIG_DIR/dr-config.env"

# Global variables
SETUP_ID="setup_$(date +%Y%m%d_%H%M%S)_$$"
LOG_FILE="$DR_BACKUP_DIR/logs/automation-setup-$SETUP_ID.log"
CRONTAB_BACKUP="/tmp/crontab-backup-$SETUP_ID"

# Logging functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $1" | tee -a "$LOG_FILE" >&2
}

log_success() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [SUCCESS] $1" | tee -a "$LOG_FILE"
}

# Display usage information
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Automation Setup for Disaster Recovery System

OPTIONS:
    --backup-time TIME      Daily backup time (default: 02:00)
    --validate-time TIME    Daily validation time (default: 03:00)
    --monitor-interval MIN  Monitoring interval in minutes (default: 60)
    --test-schedule SCHED   Test schedule (daily, weekly, monthly) (default: weekly)
    --remove               Remove all DR automation
    --dry-run              Show what would be configured without making changes
    --force                Force setup even if existing cron jobs found
    -h, --help             Show this help message

Examples:
    $0                                    # Setup with default schedule
    $0 --backup-time 01:30               # Custom backup time
    $0 --test-schedule daily             # Daily testing
    $0 --remove                          # Remove all automation
    $0 --dry-run                         # Preview configuration
EOF
}

# Parse command line arguments
parse_arguments() {
    BACKUP_TIME="02:00"
    VALIDATE_TIME="03:00"
    MONITOR_INTERVAL="60"
    TEST_SCHEDULE="weekly"
    DRY_RUN="false"
    REMOVE_AUTOMATION="false"
    FORCE_SETUP="false"
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --backup-time)
                BACKUP_TIME="$2"
                shift 2
                ;;
            --validate-time)
                VALIDATE_TIME="$2"
                shift 2
                ;;
            --monitor-interval)
                MONITOR_INTERVAL="$2"
                shift 2
                ;;
            --test-schedule)
                TEST_SCHEDULE="$2"
                shift 2
                ;;
            --remove)
                REMOVE_AUTOMATION="true"
                shift
                ;;
            --dry-run)
                DRY_RUN="true"
                shift
                ;;
            --force)
                FORCE_SETUP="true"
                shift
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
}

# Validate time format
validate_time() {
    local time="$1"
    if [[ ! "$time" =~ ^[0-2][0-9]:[0-5][0-9]$ ]]; then
        log_error "Invalid time format: $time (expected HH:MM)"
        return 1
    fi
    return 0
}

# Convert time to cron format
time_to_cron() {
    local time="$1"
    local hour minute
    hour=$(echo "$time" | cut -d: -f1)
    minute=$(echo "$time" | cut -d: -f2)
    
    # Remove leading zeros
    hour=$((10#$hour))
    minute=$((10#$minute))
    
    echo "$minute $hour"
}

# Check for existing DR cron jobs
check_existing_jobs() {
    log "Checking for existing DR cron jobs..."
    
    local existing_jobs
    existing_jobs=$(crontab -l 2>/dev/null | grep -c "# DR:" || true)
    
    if [ "$existing_jobs" -gt 0 ]; then
        log "Found $existing_jobs existing DR cron jobs"
        
        if [ "$FORCE_SETUP" != "true" ] && [ "$REMOVE_AUTOMATION" != "true" ]; then
            log_error "Existing DR cron jobs found. Use --force to overwrite or --remove to clean up first."
            return 1
        fi
    else
        log "No existing DR cron jobs found"
    fi
    
    return 0
}

# Backup current crontab
backup_crontab() {
    log "Backing up current crontab..."
    
    if crontab -l > "$CRONTAB_BACKUP" 2>/dev/null; then
        log_success "Crontab backed up to: $CRONTAB_BACKUP"
    else
        log "No existing crontab found"
        touch "$CRONTAB_BACKUP"
    fi
}

# Remove existing DR cron jobs
remove_dr_jobs() {
    log "Removing existing DR cron jobs..."
    
    local temp_crontab="/tmp/crontab-temp-$SETUP_ID"
    
    # Get current crontab without DR jobs
    if crontab -l 2>/dev/null | grep -v "# DR:" > "$temp_crontab"; then
        if [ "$DRY_RUN" = "true" ]; then
            log "DRY RUN: Would remove DR cron jobs"
        else
            crontab "$temp_crontab"
            log_success "Existing DR cron jobs removed"
        fi
    else
        log "No cron jobs to remove"
    fi
    
    rm -f "$temp_crontab"
}

# Generate cron configuration
generate_cron_config() {
    log "Generating cron configuration..."
    
    local backup_cron validate_cron monitor_cron test_cron
    
    # Daily backup
    backup_cron=$(time_to_cron "$BACKUP_TIME")
    
    # Daily validation (1 hour after backup)
    validate_cron=$(time_to_cron "$VALIDATE_TIME")
    
    # Monitoring (every hour or custom interval)
    if [ "$MONITOR_INTERVAL" -eq 60 ]; then
        monitor_cron="0 *"
    else
        monitor_cron="*/$MONITOR_INTERVAL *"
    fi
    
    # Testing schedule
    case "$TEST_SCHEDULE" in
        "daily")
            test_cron="0 4 *"  # 4 AM daily
            ;;
        "weekly")
            test_cron="0 4 * * 0"  # 4 AM every Sunday
            ;;
        "monthly")
            test_cron="0 4 1 *"  # 4 AM first day of month
            ;;
        *)
            log_error "Invalid test schedule: $TEST_SCHEDULE"
            return 1
            ;;
    esac
    
    # Generate cron entries
    cat << EOF
# DR: Disaster Recovery Automation (Generated $(date))
# DR: Daily backup at $BACKUP_TIME
$backup_cron * * * $SCRIPT_DIR/enhanced-backup.sh >> $DR_BACKUP_DIR/logs/cron-backup.log 2>&1

# DR: Daily backup validation at $VALIDATE_TIME
$validate_cron * * * $SCRIPT_DIR/validate-backup.sh >> $DR_BACKUP_DIR/logs/cron-validation.log 2>&1

# DR: System monitoring every $MONITOR_INTERVAL minutes
$monitor_cron * * * $SCRIPT_DIR/dr-monitor.sh >> $DR_BACKUP_DIR/logs/cron-monitor.log 2>&1

# DR: Automated testing ($TEST_SCHEDULE)
$test_cron * $SCRIPT_DIR/dr-test.sh -m backup-only -c >> $DR_BACKUP_DIR/logs/cron-test.log 2>&1

# DR: Log cleanup (daily at 5 AM)
0 5 * * * find $DR_BACKUP_DIR/logs -name "*.log" -type f -mtime +30 -delete 2>/dev/null

# DR: Session cleanup (daily at 6 AM)
0 6 * * * find $DR_BACKUP_DIR/sessions -name "backup_*" -type d -mtime +$DR_LOCAL_RETENTION_DAYS -exec rm -rf {} \; 2>/dev/null

EOF
}

# Install cron jobs
install_cron_jobs() {
    log "Installing DR cron jobs..."
    
    local current_crontab="/tmp/current-crontab-$SETUP_ID"
    local new_crontab="/tmp/new-crontab-$SETUP_ID"
    
    # Get current crontab (excluding DR jobs)
    if crontab -l 2>/dev/null | grep -v "# DR:" > "$current_crontab"; then
        true  # File created successfully
    else
        touch "$current_crontab"  # No existing crontab
    fi
    
    # Combine current crontab with new DR jobs
    {
        cat "$current_crontab"
        echo ""
        generate_cron_config
    } > "$new_crontab"
    
    if [ "$DRY_RUN" = "true" ]; then
        log "DRY RUN: Would install the following cron jobs:"
        echo "----------------------------------------"
        generate_cron_config
        echo "----------------------------------------"
    else
        if crontab "$new_crontab"; then
            log_success "DR cron jobs installed successfully"
        else
            log_error "Failed to install cron jobs"
            return 1
        fi
    fi
    
    # Cleanup temporary files
    rm -f "$current_crontab" "$new_crontab"
}

# Create log rotation configuration
setup_log_rotation() {
    log "Setting up log rotation..."
    
    local logrotate_config="/etc/logrotate.d/dr-backup"
    
    if [ "$DRY_RUN" = "true" ]; then
        log "DRY RUN: Would create logrotate configuration at $logrotate_config"
        return 0
    fi
    
    # Check if we can write to logrotate directory
    if [ ! -w "/etc/logrotate.d" ]; then
        log "Cannot write to /etc/logrotate.d (permission denied)"
        log "Creating local log rotation script instead..."
        
        # Create local log rotation script
        local log_rotate_script="$SCRIPT_DIR/rotate-logs.sh"
        cat > "$log_rotate_script" << 'EOF'
#!/bin/bash
# DR Log Rotation Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$(dirname "$SCRIPT_DIR")/config"
source "$CONFIG_DIR/dr-config.env"

# Rotate and compress logs older than 7 days
find "$DR_BACKUP_DIR/logs" -name "*.log" -type f -mtime +7 -exec gzip {} \;

# Delete compressed logs older than 30 days
find "$DR_BACKUP_DIR/logs" -name "*.log.gz" -type f -mtime +30 -delete

# Rotate cron logs
for log_file in cron-backup.log cron-validation.log cron-monitor.log cron-test.log; do
    log_path="$DR_BACKUP_DIR/logs/$log_file"
    if [ -f "$log_path" ] && [ $(stat -c%s "$log_path" 2>/dev/null || echo 0) -gt 10485760 ]; then
        mv "$log_path" "${log_path}.$(date +%Y%m%d)"
        gzip "${log_path}.$(date +%Y%m%d)"
        touch "$log_path"
    fi
done
EOF
        
        chmod +x "$log_rotate_script"
        log_success "Local log rotation script created: $log_rotate_script"
        
    else
        # Create system logrotate configuration
        cat > "$logrotate_config" << EOF
$DR_BACKUP_DIR/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 $(whoami) $(whoami)
    copytruncate
}

$DR_BACKUP_DIR/logs/cron-*.log {
    size 10M
    rotate 5
    compress
    delaycompress
    missingok
    notifempty
    create 644 $(whoami) $(whoami)
    copytruncate
}
EOF
        
        log_success "Logrotate configuration created: $logrotate_config"
    fi
}

# Create systemd service (optional)
create_systemd_service() {
    log "Creating systemd service for DR monitoring..."
    
    local service_file="/etc/systemd/system/dr-monitor.service"
    local timer_file="/etc/systemd/system/dr-monitor.timer"
    
    if [ "$DRY_RUN" = "true" ]; then
        log "DRY RUN: Would create systemd service and timer"
        return 0
    fi
    
    # Check if we can write systemd files
    if [ ! -w "/etc/systemd/system" ]; then
        log "Cannot write to /etc/systemd/system (permission denied)"
        log "Skipping systemd service creation"
        return 0
    fi
    
    # Create service file
    cat > "$service_file" << EOF
[Unit]
Description=Disaster Recovery Monitoring
After=network.target

[Service]
Type=oneshot
User=$(whoami)
ExecStart=$SCRIPT_DIR/dr-monitor.sh
WorkingDirectory=$DR_BACKUP_DIR
StandardOutput=append:$DR_BACKUP_DIR/logs/systemd-monitor.log
StandardError=append:$DR_BACKUP_DIR/logs/systemd-monitor.log

[Install]
WantedBy=multi-user.target
EOF
    
    # Create timer file
    cat > "$timer_file" << EOF
[Unit]
Description=Run DR monitoring every hour
Requires=dr-monitor.service

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
EOF
    
    # Reload systemd and enable service
    systemctl daemon-reload
    systemctl enable dr-monitor.timer
    systemctl start dr-monitor.timer
    
    log_success "Systemd service and timer created and enabled"
}

# Verify automation setup
verify_setup() {
    log "Verifying automation setup..."
    
    # Check cron jobs
    local dr_jobs
    dr_jobs=$(crontab -l 2>/dev/null | grep -c "# DR:" || true)
    
    if [ "$dr_jobs" -gt 0 ]; then
        log_success "Found $dr_jobs DR cron jobs installed"
    else
        log_error "No DR cron jobs found"
        return 1
    fi
    
    # Check script permissions
    local scripts=("enhanced-backup.sh" "validate-backup.sh" "dr-monitor.sh" "dr-test.sh")
    for script in "${scripts[@]}"; do
        local script_path="$SCRIPT_DIR/$script"
        if [ -x "$script_path" ]; then
            log "Script executable: $script"
        else
            log_error "Script not executable: $script"
            if [ "$DRY_RUN" != "true" ]; then
                chmod +x "$script_path"
                log "Made script executable: $script"
            fi
        fi
    done
    
    # Check directories
    local dirs=("$DR_BACKUP_DIR/logs" "$DR_BACKUP_DIR/sessions")
    for dir in "${dirs[@]}"; do
        if [ -d "$dir" ]; then
            log "Directory exists: $dir"
        else
            log_error "Directory missing: $dir"
            if [ "$DRY_RUN" != "true" ]; then
                mkdir -p "$dir"
                log "Created directory: $dir"
            fi
        fi
    done
    
    log_success "Automation setup verification completed"
}

# Show current configuration
show_configuration() {
    log "Current DR automation configuration:"
    echo "=================================="
    echo "Backup time: $BACKUP_TIME"
    echo "Validation time: $VALIDATE_TIME" 
    echo "Monitor interval: $MONITOR_INTERVAL minutes"
    echo "Test schedule: $TEST_SCHEDULE"
    echo "Dry run: $DRY_RUN"
    echo "Force setup: $FORCE_SETUP"
    echo "Remove automation: $REMOVE_AUTOMATION"
    echo ""
    
    if [ "$DRY_RUN" != "true" ]; then
        echo "Existing DR cron jobs:"
        crontab -l 2>/dev/null | grep "# DR:" || echo "None found"
    fi
    echo "=================================="
}

# Main setup function
main() {
    log "=== Starting DR Automation Setup ==="
    log "Setup ID: $SETUP_ID"
    
    # Parse arguments
    parse_arguments "$@"
    
    # Show configuration
    show_configuration
    
    # Validate arguments
    if ! validate_time "$BACKUP_TIME" || ! validate_time "$VALIDATE_TIME"; then
        exit 1
    fi
    
    # Create logs directory
    mkdir -p "$DR_BACKUP_DIR/logs"
    
    # Check for existing jobs
    if [ "$REMOVE_AUTOMATION" != "true" ]; then
        check_existing_jobs
    fi
    
    # Backup current crontab
    backup_crontab
    
    # Remove automation if requested
    if [ "$REMOVE_AUTOMATION" = "true" ]; then
        remove_dr_jobs
        log_success "DR automation removed successfully"
        return 0
    fi
    
    # Remove existing DR jobs if force is enabled
    if [ "$FORCE_SETUP" = "true" ]; then
        remove_dr_jobs
    fi
    
    # Install new cron jobs
    install_cron_jobs
    
    # Setup log rotation
    setup_log_rotation
    
    # Create systemd service (optional)
    if command -v systemctl &> /dev/null && [ "$DRY_RUN" != "true" ]; then
        create_systemd_service
    fi
    
    # Verify setup
    verify_setup
    
    if [ "$DRY_RUN" = "true" ]; then
        log "=== DRY RUN COMPLETED ==="
        log "No changes were made to the system"
    else
        log "=== Automation setup completed successfully ==="
        log "Crontab backup saved to: $CRONTAB_BACKUP"
        log ""
        log "Next steps:"
        log "1. Test the setup: crontab -l | grep '# DR:'"
        log "2. Monitor logs: tail -f $DR_BACKUP_DIR/logs/cron-*.log"
        log "3. Run manual test: $SCRIPT_DIR/dr-test.sh -m backup-only -c"
    fi
}

# Check if running with appropriate permissions
if [ "$EUID" -eq 0 ]; then
    echo "WARNING: Running as root. Consider using a dedicated backup user."
fi

# Run main function
main "$@"
