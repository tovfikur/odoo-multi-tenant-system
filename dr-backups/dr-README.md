# Disaster Recovery System for Odoo Multi-Tenant SaaS Platform

## Overview

This disaster recovery (DR) system provides comprehensive backup, validation, monitoring, and recovery capabilities for the Odoo Multi-Tenant SaaS platform. The system is designed to achieve:

- **Recovery Time Objective (RTO)**: 2 hours
- **Recovery Point Objective (RPO)**: 4 hours  
- **70% risk reduction** from current state
- **Zero production downtime** during implementation

## System Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Production    │    │  Local Backups  │    │ Cloud Storage   │
│     System      │───▶│   (Encrypted)   │───▶│   (AWS S3)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │              ┌─────────────────┐              │
         │              │   Monitoring    │              │
         └──────────────│   & Alerting    │──────────────┘
                        └─────────────────┘
                                 │
                        ┌─────────────────┐
                        │   Testing &     │
                        │  Validation     │
                        └─────────────────┘
```

## Quick Start

### 1. Initial Setup

```bash
# Navigate to the DR directory
cd "K:\Odoo Multi-Tenant System\dr-backups"

# Run initial setup
./scripts/setup-encryption.sh

# Configure AWS credentials (edit the config file)
nano config/dr-config.env
```

### 2. First Backup

```bash
# Run manual backup
./scripts/enhanced-backup.sh

# Validate the backup
./scripts/validate-backup.sh
```

### 3. Setup Automation

```bash
# Install automated schedules
./scripts/setup-automation.sh

# Run a test
./scripts/dr-test.sh -m backup-only -c
```

## Directory Structure

```
dr-backups/
├── config/
│   ├── dr-config.env           # Main configuration file
│   └── encryption.key          # Encryption key (auto-generated)
├── scripts/
│   ├── setup-encryption.sh     # Initial setup and cloud configuration
│   ├── enhanced-backup.sh      # Main backup script
│   ├── validate-backup.sh      # Backup validation
│   ├── disaster-recovery.sh    # Recovery procedures
│   ├── dr-monitor.sh           # Monitoring and alerting
│   ├── dr-test.sh              # Testing framework
│   └── setup-automation.sh     # Cron job automation
├── sessions/                   # Local backup sessions
│   └── backup_YYYYMMDD_HHMMSS_PID/
├── logs/                       # System logs
├── tests/                      # Test environments
└── README.md                   # This file
```

## Core Components

### 1. Enhanced Backup System (`enhanced-backup.sh`)

**Features:**
- Encrypted PostgreSQL database dumps
- Individual tenant database backups  
- Compressed and encrypted file storage backup
- Configuration backup
- Cloud storage synchronization
- Backup integrity validation
- Comprehensive logging and notifications

**Usage:**
```bash
./scripts/enhanced-backup.sh
```

**Configuration:**
- Backup directory: `DR_BACKUP_DIR`
- Cloud bucket: `DR_CLOUD_BUCKET`
- Encryption: AES-256-CBC
- Retention: 90 days cloud, 7 days local

### 2. Backup Validation (`validate-backup.sh`)

**Features:**
- Manifest validation
- Decryption testing
- Archive integrity checks
- Cloud sync verification
- Restoration testing (dry run)
- Age verification

**Usage:**
```bash
# Validate latest backup
./scripts/validate-backup.sh

# Validate specific session
./scripts/validate-backup.sh /path/to/session
```

### 3. Disaster Recovery (`disaster-recovery.sh`)

**Features:**
- Multiple recovery modes
- Cloud backup download
- Pre-recovery system backup
- Service management
- Health checks
- Rollback capabilities

**Recovery Modes:**
- `full`: Complete system restoration
- `database-only`: Database restoration only
- `files-only`: File storage restoration only
- `config-only`: Configuration restoration only

**Usage:**
```bash
# Full recovery from latest backup
./scripts/disaster-recovery.sh

# Database-only recovery
./scripts/disaster-recovery.sh -m database-only latest

# Recovery from cloud
./scripts/disaster-recovery.sh -c -s backup_20231201_120000_1234

# Test mode (no changes)
./scripts/disaster-recovery.sh -t
```

### 4. Monitoring System (`dr-monitor.sh`)

**Monitoring Areas:**
- Backup age and completeness
- Cloud storage synchronization
- Disk space usage
- Service health
- Backup integrity
- System resources

**Alerting:**
- Email notifications
- Webhook integration (Slack)
- JSON status reports
- Log rotation

**Usage:**
```bash
# Manual monitoring check
./scripts/dr-monitor.sh

# Check status report
cat logs/dr-status.json
```

### 5. Testing Framework (`dr-test.sh`)

**Test Types:**
- Backup creation testing
- Validation testing
- Recovery simulation
- Database restoration
- Cloud storage integration
- Monitoring system testing

**Test Modes:**
- `full`: Complete test cycle
- `backup-only`: Backup procedures only
- `restore-only`: Recovery procedures only  
- `validation-only`: Validation procedures only

**Usage:**
```bash
# Full test cycle
./scripts/dr-test.sh

# Backup testing only
./scripts/dr-test.sh -m backup-only -c

# Weekly automated test
./scripts/dr-test.sh -m backup-only -c
```

## Configuration

### Main Configuration File (`config/dr-config.env`)

Key settings:

```bash
# Core DR Settings
DR_BACKUP_DIR="K:\Odoo Multi-Tenant System\dr-backups"
DR_RETENTION_DAYS="90"
DR_LOCAL_RETENTION_DAYS="7"

# Database Settings  
POSTGRES_HOST="localhost"
POSTGRES_USER="odoo_master"
POSTGRES_PASSWORD="secure_password_123"

# Cloud Storage (AWS S3)
DR_CLOUD_BUCKET="s3://company-dr-backups"
AWS_ACCESS_KEY_ID="your_access_key"
AWS_SECRET_ACCESS_KEY="your_secret_key"

# Monitoring & Alerting
DR_NOTIFICATION_EMAIL="admin@company.com"
DR_WEBHOOK_URL=""  # Slack webhook URL
DR_ALERT_ON_BACKUP_AGE="86400"  # 24 hours
DR_ALERT_ON_DISK_USAGE="90"     # 90%

# Recovery Settings
DR_RTO_MINUTES="120"   # 2 hours
DR_RPO_HOURS="4"       # 4 hours
```

### AWS S3 Setup

1. Create S3 bucket with versioning enabled
2. Enable server-side encryption (AES-256)
3. Configure lifecycle policies:
   - Standard IA: 30 days
   - Glacier: 90 days
   - Deep Archive: 365 days
4. Set up IAM user with S3 permissions

### Email/Webhook Configuration

**Email Setup:**
```bash
DR_NOTIFICATION_EMAIL="admin@company.com"
DR_SMTP_HOST="smtp.gmail.com"
DR_SMTP_PORT="587"
```

**Slack Integration:**
```bash
DR_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
```

## Automation Schedule

Default automated schedule:

```bash
# Daily backup at 2:00 AM
0 2 * * * enhanced-backup.sh

# Daily validation at 3:00 AM  
0 3 * * * validate-backup.sh

# Hourly monitoring
0 * * * * dr-monitor.sh

# Weekly testing (Sundays at 4:00 AM)
0 4 * * 0 dr-test.sh -m backup-only -c

# Daily cleanup at 5:00 AM
0 5 * * * find logs/ -name "*.log" -mtime +30 -delete

# Session cleanup at 6:00 AM
0 6 * * * find sessions/ -name "backup_*" -mtime +7 -exec rm -rf {} \;
```

### Customizing Automation

```bash
# Custom backup time
./scripts/setup-automation.sh --backup-time 01:30

# Daily testing
./scripts/setup-automation.sh --test-schedule daily

# Custom monitoring interval  
./scripts/setup-automation.sh --monitor-interval 30

# Remove all automation
./scripts/setup-automation.sh --remove
```

## Security Features

### Encryption
- **Algorithm**: AES-256-CBC
- **Key Management**: Secure key generation and storage
- **Cloud Encryption**: Server-side encryption in S3
- **Transport Security**: HTTPS for cloud transfers

### Access Control
- **File Permissions**: Restricted access to backup files
- **Key Security**: Encryption key protected with 600 permissions
- **Audit Logging**: All DR operations logged
- **Secure Deletion**: Optional secure file deletion

### Network Security
- **SSL/TLS**: Encrypted data transmission
- **Authentication**: AWS IAM for cloud access
- **Firewall**: Configurable network restrictions

## Troubleshooting

### Common Issues

**1. Backup Fails with Permission Error**
```bash
# Check directory permissions
ls -la dr-backups/
chmod 755 dr-backups/
chmod +x scripts/*.sh
```

**2. Cloud Upload Fails**
```bash
# Test AWS credentials
aws s3 ls s3://your-bucket-name/
aws configure list

# Check network connectivity
ping s3.amazonaws.com
```

**3. Database Connection Issues**
```bash
# Test PostgreSQL connection
pg_isready -h localhost -p 5432 -U odoo_master

# Check Docker services
docker-compose -f docker-compose.yml ps
```

**4. Encryption/Decryption Fails**
```bash
# Verify encryption key exists
ls -la config/encryption.key

# Test encryption
echo "test" | openssl enc -aes-256-cbc -k "$(cat config/encryption.key)"
```

### Log Analysis

**Backup Logs:**
```bash
# Latest backup log
tail -f logs/backup-*.log

# Search for errors
grep ERROR logs/backup-*.log
```

**Monitoring Logs:**
```bash
# Monitor status
cat logs/dr-status.json | jq .

# Alert history
grep CRITICAL logs/monitor-*.log
```

**Recovery Logs:**
```bash
# Recovery operations
tail -f logs/recovery-*.log
```

### Performance Optimization

**Backup Performance:**
```bash
# Enable parallel backups
DR_MAX_PARALLEL_BACKUPS="3"

# Adjust compression level  
DR_COMPRESSION_LEVEL="6"

# Set I/O priority
DR_IO_NICE_LEVEL="7"
```

**Network Optimization:**
```bash
# Bandwidth limiting
DR_BANDWIDTH_LIMIT="10M"

# Use multipart uploads for large files
aws configure set default.s3.multipart_threshold 64MB
```

## Maintenance Procedures

### Weekly Tasks
1. Review backup status reports
2. Check monitoring alerts
3. Verify cloud storage sync
4. Review disk space usage

### Monthly Tasks  
1. Run full DR test
2. Review and update documentation
3. Test notification systems
4. Audit security configurations
5. Review retention policies

### Quarterly Tasks
1. Full disaster recovery drill
2. Review and update procedures
3. Security audit
4. Performance review
5. Budget and cost analysis

## Compliance and Auditing

### Audit Trail
- All operations logged with timestamps
- Session IDs for tracking
- Change management logs
- Access logging

### Compliance Features
- Data encryption at rest and in transit
- Configurable retention policies
- Secure key management
- Regular validation testing

### Reporting
- JSON status reports
- Automated alerting
- Test result documentation
- Compliance dashboards

## Support and Escalation

### Emergency Contacts
- **Primary**: admin@company.com
- **Secondary**: backup-admin@company.com  
- **Escalation**: management@company.com

### Emergency Procedures
1. **Data Loss Event**: Immediate recovery initiation
2. **System Compromise**: Secure recovery from clean backups
3. **Extended Outage**: Cloud-based recovery activation

### Documentation Updates
- Monthly review cycle
- Change approval process
- Version control
- Distribution list maintenance

---

**For additional support or questions, please refer to the troubleshooting section or contact the system administrator.**
