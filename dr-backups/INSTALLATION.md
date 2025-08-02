# Disaster Recovery System Installation Guide

## Prerequisites

### System Requirements

- **Operating System**: Linux (Ubuntu 20.04+ recommended), Windows with WSL2
- **Available Disk Space**: 50GB minimum for local backups
- **Memory**: 4GB RAM minimum
- **Network**: Stable internet connection for cloud sync
- **Docker**: Docker and Docker Compose installed

### Required Software

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y \
    postgresql-client \
    openssl \
    curl \
    jq \
    awscli \
    mailutils \
    cron

# CentOS/RHEL
sudo yum install -y \
    postgresql \
    openssl \
    curl \
    jq \
    aws-cli \
    mailx \
    crontabs

# Windows (via Chocolatey)
choco install -y \
    postgresql \
    openssl \
    curl \
    jq \
    awscli \
    git
```

### Access Requirements

- **PostgreSQL**: Read access to all tenant databases
- **File System**: Read/write access to Odoo filestore
- **Cloud Storage**: AWS S3 bucket with appropriate permissions
- **Email**: SMTP server access for notifications
- **Network**: Outbound HTTPS access for cloud sync

## Step-by-Step Installation

### Step 1: Download and Setup

```bash
# Navigate to your Odoo installation
cd "K:\Odoo Multi-Tenant System"

# Verify the dr-backups directory exists
ls -la dr-backups/

# Make scripts executable
chmod +x dr-backups/scripts/*.sh

# Verify script permissions
ls -la dr-backups/scripts/
```

### Step 2: Configure the System

#### Edit Configuration File

```bash
# Open the configuration file
nano dr-backups/config/dr-config.env
```

**Required Configuration Changes:**

```bash
# === AWS Credentials (REQUIRED) ===
AWS_ACCESS_KEY_ID="your_aws_access_key_here"
AWS_SECRET_ACCESS_KEY="your_aws_secret_key_here"
DR_CLOUD_BUCKET="s3://your-company-dr-backups"
DR_CLOUD_REGION="us-east-1"

# === Email Notifications (REQUIRED) ===
DR_NOTIFICATION_EMAIL="admin@yourcompany.com"
DR_SMTP_HOST="smtp.gmail.com"
DR_SMTP_PORT="587"
DR_SMTP_USER="your-email@gmail.com"
DR_SMTP_PASSWORD="your-app-password"

# === Database Settings (Verify these match your setup) ===
POSTGRES_HOST="localhost"
POSTGRES_PORT="5432"
POSTGRES_USER="odoo_master"
POSTGRES_PASSWORD="secure_password_123"

# === Optional: Slack Integration ===
DR_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
```

#### AWS S3 Bucket Setup

1. **Create S3 Bucket:**
   ```bash
   # Using AWS CLI
   aws s3 mb s3://your-company-dr-backups --region us-east-1
   ```

2. **Enable Versioning:**
   ```bash
   aws s3api put-bucket-versioning \
       --bucket your-company-dr-backups \
       --versioning-configuration Status=Enabled
   ```

3. **Enable Encryption:**
   ```bash
   aws s3api put-bucket-encryption \
       --bucket your-company-dr-backups \
       --server-side-encryption-configuration '{
           "Rules": [{
               "ApplyServerSideEncryptionByDefault": {
                   "SSEAlgorithm": "AES256"
               }
           }]
       }'
   ```

### Step 3: Initialize Security

```bash
# Run the encryption setup script
cd dr-backups
./scripts/setup-encryption.sh
```

**This script will:**
- Generate a secure encryption key
- Configure AWS CLI
- Create and configure S3 bucket
- Test encryption and cloud connectivity
- Set up proper file permissions

**Expected Output:**
```
[INFO] Generating encryption key...
[INFO] Encryption key generated and saved
[INFO] Setting up AWS CLI...
[INFO] AWS CLI configured successfully
[INFO] Setting up S3 bucket for disaster recovery...
[INFO] S3 bucket setup completed successfully
[SUCCESS] All tests completed successfully
```

### Step 4: Test the Installation

#### Run Initial Backup Test

```bash
# Create first backup
./scripts/enhanced-backup.sh
```

**Expected Output:**
```
[INFO] Starting Enhanced Disaster Recovery Backup
[INFO] Session ID: backup_20231201_120000_1234
[INFO] Successfully backed up database: kdoo_tenant1
[INFO] Successfully backed up filestore
[INFO] Successfully uploaded backup to cloud
[SUCCESS] Backup completed successfully
```

#### Validate the Backup

```bash
# Validate the backup
./scripts/validate-backup.sh
```

**Expected Output:**
```
[INFO] Starting Backup Validation
[SUCCESS] Database backup valid: kdoo_tenant1
[SUCCESS] Filestore backup valid: 1250 files
[SUCCESS] Cloud sync verified: 5 files match
[SUCCESS] All backup validations passed
```

#### Run System Monitoring

```bash
# Check system status
./scripts/dr-monitor.sh
```

**Expected Output:**
```
[INFO] Starting DR Monitoring Check
[SUCCESS] Backup age is acceptable: 0 hours
[SUCCESS] All services are running normally
[SUCCESS] All health checks passed
```

### Step 5: Setup Automation

```bash
# Install automated schedules
./scripts/setup-automation.sh
```

**This will configure:**
- Daily backups at 2:00 AM
- Daily validation at 3:00 AM
- Hourly monitoring
- Weekly testing on Sundays
- Log rotation and cleanup

**Verify Cron Installation:**
```bash
# Check installed cron jobs
crontab -l | grep "# DR:"
```

### Step 6: Run Complete Test

```bash
# Run full system test
./scripts/dr-test.sh -m backup-only -c
```

**Expected Output:**
```
[INFO] Starting DR Testing Framework
[INFO] Test ID: test_20231201_130000_5678
[SUCCESS] Test database created with sample data
[PASSED] backup_creation: Backup created successfully (45s)
[PASSED] backup_validation: Backup validation successful (12s)
[PASSED] cloud_storage: Downloaded 5 files from cloud (8s)
[SUCCESS] Testing completed successfully
```

## Verification Checklist

### ✅ Installation Verification

- [ ] All required software installed
- [ ] Scripts are executable (`chmod +x`)
- [ ] Configuration file customized
- [ ] Encryption key generated
- [ ] AWS S3 bucket created and configured
- [ ] First backup completed successfully
- [ ] Backup validation passed
- [ ] Cloud sync working
- [ ] Monitoring system operational
- [ ] Automation/cron jobs installed
- [ ] Test framework working

### ✅ Security Verification

- [ ] Encryption key has 600 permissions
- [ ] AWS credentials configured securely
- [ ] S3 bucket has encryption enabled
- [ ] Backup files are encrypted
- [ ] Network connections use HTTPS/SSL
- [ ] Email credentials secured

### ✅ Functionality Verification

- [ ] Database backups working
- [ ] File storage backups working
- [ ] Configuration backups working
- [ ] Cloud upload/download working
- [ ] Email notifications working
- [ ] Webhook notifications working (if configured)
- [ ] Monitoring alerts working
- [ ] Log rotation working

## Common Installation Issues

### Issue 1: Permission Denied Errors

**Symptoms:**
```
./scripts/enhanced-backup.sh: Permission denied
```

**Solution:**
```bash
# Fix script permissions
chmod +x dr-backups/scripts/*.sh

# Fix directory permissions
chmod 755 dr-backups/
```

### Issue 2: AWS CLI Not Configured

**Symptoms:**
```
[ERROR] AWS CLI is not installed or not configured
```

**Solution:**
```bash
# Install AWS CLI (Ubuntu)
sudo apt install awscli

# Configure AWS CLI
aws configure
# Enter your Access Key ID
# Enter your Secret Access Key
# Enter default region (e.g., us-east-1)
# Enter default output format (json)

# Test configuration
aws s3 ls
```

### Issue 3: Database Connection Fails

**Symptoms:**
```
[ERROR] Failed to connect to PostgreSQL
```

**Solution:**
```bash
# Check PostgreSQL is running
docker-compose -f docker-compose.yml ps postgres

# Test connection manually
pg_isready -h localhost -p 5432 -U odoo_master

# Check credentials in configuration
cat dr-backups/config/dr-config.env | grep POSTGRES
```

### Issue 4: S3 Bucket Access Denied

**Symptoms:**
```
[ERROR] Failed to upload backup to cloud storage
```

**Solution:**
```bash
# Test S3 access
aws s3 ls s3://your-bucket-name/

# Check bucket permissions
aws s3api get-bucket-policy --bucket your-bucket-name

# Verify IAM permissions for your user
aws iam get-user
```

### Issue 5: Encryption Key Issues

**Symptoms:**
```
[ERROR] Encryption key not found
```

**Solution:**
```bash
# Check if key exists
ls -la dr-backups/config/encryption.key

# Regenerate key if missing
./scripts/setup-encryption.sh

# Verify key permissions
chmod 600 dr-backups/config/encryption.key
```

### Issue 6: Cron Jobs Not Working

**Symptoms:**
- Automated backups not running
- No cron log entries

**Solution:**
```bash
# Check if cron service is running
sudo systemctl status cron

# Start cron service if needed
sudo systemctl start cron
sudo systemctl enable cron

# Check cron logs
sudo tail -f /var/log/cron.log

# Verify cron jobs installed
crontab -l | grep "# DR:"

# Test cron job manually
/bin/bash dr-backups/scripts/enhanced-backup.sh
```

## Post-Installation Configuration

### Email Configuration

For **Gmail** with App Passwords:
```bash
DR_SMTP_HOST="smtp.gmail.com"
DR_SMTP_PORT="587"
DR_SMTP_USER="your-email@gmail.com"
DR_SMTP_PASSWORD="your-16-char-app-password"
```

For **Office 365**:
```bash
DR_SMTP_HOST="smtp.office365.com"
DR_SMTP_PORT="587"
DR_SMTP_USER="your-email@company.com"
DR_SMTP_PASSWORD="your-password"
```

### Slack Integration

1. Create a Slack app and webhook
2. Add webhook URL to configuration:
   ```bash
   DR_WEBHOOK_URL="https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX"
   ```

### Custom Schedules

```bash
# Backup every 6 hours
./scripts/setup-automation.sh --backup-time "00:00,06:00,12:00,18:00"

# Monitor every 15 minutes
./scripts/setup-automation.sh --monitor-interval 15

# Daily testing
./scripts/setup-automation.sh --test-schedule daily
```

## Maintenance

### Weekly Tasks
```bash
# Check system status
./scripts/dr-monitor.sh

# Review logs
tail -100 dr-backups/logs/monitor-*.log

# Check disk space
df -h dr-backups/
```

### Monthly Tasks
```bash
# Run full test
./scripts/dr-test.sh

# Review configuration
cat dr-backups/config/dr-config.env

# Update documentation
nano dr-backups/README.md
```

## Support

### Log Locations
```bash
# Main logs directory
ls -la dr-backups/logs/

# Recent backup logs
ls -la dr-backups/logs/backup-*.log

# Monitoring logs
ls -la dr-backups/logs/monitor-*.log

# Cron logs
ls -la dr-backups/logs/cron-*.log
```

### Getting Help

1. **Check logs** for error messages
2. **Review configuration** for missing or incorrect values
3. **Test connectivity** to databases and cloud storage
4. **Verify permissions** on files and directories
5. **Contact support** with specific error messages and log excerpts

### Emergency Support

For production issues requiring immediate assistance:

- **Emergency Hotline**: [Your emergency number]
- **Email**: emergency@yourcompany.com
- **Escalation**: management@yourcompany.com

---

**Installation Complete!** 🎉

Your disaster recovery system is now installed and configured. The system will automatically:
- Create daily encrypted backups
- Sync backups to cloud storage  
- Monitor system health
- Send alerts for any issues
- Run automated tests weekly

**Next Steps:**
1. Review the [README.md](README.md) for operational procedures
2. Familiarize yourself with the [EMERGENCY-RUNBOOK.md](EMERGENCY-RUNBOOK.md)
3. Schedule a disaster recovery drill
4. Train your team on the procedures
