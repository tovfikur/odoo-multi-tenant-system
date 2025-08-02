# Emergency Disaster Recovery Runbook

## 🚨 EMERGENCY CONTACTS

| Role | Contact | Phone | Email |
|------|---------|-------|-------|
| **Primary DR Admin** | [Name] | [Phone] | admin@company.com |
| **Secondary DR Admin** | [Name] | [Phone] | backup-admin@company.com |
| **System Admin** | [Name] | [Phone] | sysadmin@company.com |
| **Management** | [Name] | [Phone] | management@company.com |
| **Cloud Provider** | AWS Support | 1-206-266-4064 | [Support Case] |

## ⚡ IMMEDIATE RESPONSE PROCEDURES

### STEP 1: ASSESS THE SITUATION (5 minutes)

**Determine the type of emergency:**

- [ ] **Data Loss/Corruption**: Files or databases are missing or corrupted
- [ ] **Complete System Failure**: All services are down
- [ ] **Partial Service Outage**: Some services are unavailable
- [ ] **Security Incident**: System compromise suspected
- [ ] **Hardware Failure**: Server or storage hardware issues
- [ ] **Network/Connectivity Issues**: Cannot access systems

**Quick Assessment Checklist:**
```bash
# Check system status
docker-compose -f docker-compose.yml ps

# Check database connectivity
pg_isready -h localhost -p 5432 -U odoo_master

# Check disk space
df -h

# Check recent logs
tail -100 /var/log/syslog
```

### STEP 2: IMMEDIATE CONTAINMENT (10 minutes)

**For Security Incidents:**
1. Disconnect affected systems from network
2. Preserve current state for forensics
3. Contact security team immediately

**For Other Incidents:**
1. Stop affected services gracefully
2. Create emergency backup of current state
3. Document the incident

**Emergency Documentation:**
```bash
# Create incident log
echo "$(date): INCIDENT STARTED - [DESCRIPTION]" >> dr-backups/logs/emergency-$(date +%Y%m%d).log

# Capture system state
docker-compose -f docker-compose.yml ps > incident-system-state.log
df -h > incident-disk-usage.log
```

## 🔥 RECOVERY PROCEDURES

### SCENARIO A: COMPLETE SYSTEM FAILURE

**Estimated Recovery Time: 1-2 hours**

#### Phase 1: Preparation (15 minutes)

1. **Verify Infrastructure**
   ```bash
   # Check hardware/VM status
   # Verify network connectivity
   # Confirm disk availability
   ```

2. **Prepare Recovery Environment**
   ```bash
   cd "K:\Odoo Multi-Tenant System\dr-backups"
   
   # Check encryption key
   ls -la config/encryption.key
   
   # Verify latest backup
   ./scripts/validate-backup.sh
   ```

3. **Notify Stakeholders**
   - Send initial incident notification
   - Provide estimated recovery time
   - Establish communication channel

#### Phase 2: System Recovery (45-60 minutes)

1. **Download Latest Backup from Cloud**
   ```bash
   # List available backups
   aws s3 ls s3://company-dr-backups/backups/ | tail -10
   
   # Full recovery from cloud
   ./scripts/disaster-recovery.sh -c --force
   ```

2. **Alternative: Local Backup Recovery**
   ```bash
   # If cloud is unavailable, use latest local backup
   ./scripts/disaster-recovery.sh --force
   ```

3. **Monitor Recovery Progress**
   ```bash
   # Follow recovery logs
   tail -f logs/recovery-*.log
   ```

#### Phase 3: Verification (15-30 minutes)

1. **System Health Checks**
   ```bash
   # Run health verification
   ./scripts/dr-monitor.sh
   
   # Check all services
   docker-compose -f docker-compose.yml ps
   
   # Test database connectivity
   pg_isready -h localhost -p 5432 -U odoo_master
   ```

2. **Application Testing**
   - [ ] Web interface accessible
   - [ ] User authentication working
   - [ ] Database queries responding
   - [ ] File uploads/downloads working
   - [ ] Email notifications working

3. **Performance Verification**
   ```bash
   # Check system load
   top
   
   # Check disk I/O
   iostat -x 1 5
   
   # Check memory usage
   free -h
   ```

### SCENARIO B: DATA CORRUPTION/LOSS

**Estimated Recovery Time: 30-90 minutes**

#### Phase 1: Damage Assessment (10 minutes)

1. **Identify Affected Components**
   ```bash
   # Check database integrity
   export PGPASSWORD="secure_password_123"
   
   # List all databases
   psql -h localhost -U odoo_master -d postgres -c "\l"
   
   # Check specific tenant database
   psql -h localhost -U odoo_master -d kdoo_tenant1 -c "SELECT COUNT(*) FROM res_users;"
   ```

2. **Assess Backup Requirements**
   ```bash
   # Find last known good backup
   ./scripts/validate-backup.sh
   
   # Check backup age
   ls -la dr-backups/sessions/
   ```

#### Phase 2: Targeted Recovery (20-60 minutes)

1. **Database-Only Recovery**
   ```bash
   # Stop services first
   docker-compose -f docker-compose.yml down
   
   # Recover databases only
   ./scripts/disaster-recovery.sh -m database-only --force
   
   # Start services
   docker-compose -f docker-compose.yml up -d
   ```

2. **File Storage Recovery (if needed)**
   ```bash
   # Files-only recovery
   ./scripts/disaster-recovery.sh -m files-only --force
   ```

#### Phase 3: Data Verification (10-20 minutes)

1. **Verify Data Integrity**
   ```bash
   # Check recent transactions
   psql -h localhost -U odoo_master -d kdoo_tenant1 -c "SELECT * FROM res_users ORDER BY create_date DESC LIMIT 10;"
   
   # Verify file attachments
   ls -la odoo_filestore/
   ```

2. **User Acceptance Testing**
   - [ ] Login as test user
   - [ ] Create test record
   - [ ] Upload test file
   - [ ] Generate test report

### SCENARIO C: PARTIAL SERVICE OUTAGE

**Estimated Recovery Time: 15-45 minutes**

#### Phase 1: Service Diagnosis (5 minutes)

1. **Identify Failed Services**
   ```bash
   # Check service status
   docker-compose -f docker-compose.yml ps
   
   # Check individual containers
   docker logs odoo_master
   docker logs postgres
   docker logs nginx
   ```

2. **Check Dependencies**
   ```bash
   # Database connectivity
   pg_isready -h localhost -p 5432 -U odoo_master
   
   # Redis connectivity  
   redis-cli ping
   
   # Network connectivity
   curl -I http://localhost:8069
   ```

#### Phase 2: Service Recovery (10-30 minutes)

1. **Restart Failed Services**
   ```bash
   # Restart specific service
   docker-compose -f docker-compose.yml restart [service_name]
   
   # Or restart all services
   docker-compose -f docker-compose.yml down
   docker-compose -f docker-compose.yml up -d
   ```

2. **Configuration Recovery (if needed)**
   ```bash
   # Restore configurations only
   ./scripts/disaster-recovery.sh -m config-only --force
   ```

#### Phase 3: Service Verification (5-10 minutes)

1. **Health Checks**
   ```bash
   # Monitor system status
   ./scripts/dr-monitor.sh
   
   # Check application health
   curl -f http://localhost:8069/web/health
   ```

### SCENARIO D: SECURITY INCIDENT

**Estimated Recovery Time: 2-4 hours**

#### Phase 1: Immediate Response (15 minutes)

1. **Isolate Systems**
   ```bash
   # Stop all services immediately
   docker-compose -f docker-compose.yml down
   
   # Disconnect from network (if possible)
   # Document current state before changes
   ```

2. **Preserve Evidence**
   ```bash
   # Create forensic backup
   mkdir -p incident-$(date +%Y%m%d)/
   cp -r logs/ incident-$(date +%Y%m%d)/logs/
   docker-compose -f docker-compose.yml logs > incident-$(date +%Y%m%d)/docker-logs.txt
   ```

3. **Notification**
   - Contact security team immediately
   - Notify management
   - Document timeline

#### Phase 2: Clean Recovery (60-120 minutes)

1. **Prepare Clean Environment**
   ```bash
   # Remove potentially compromised data
   # Rebuild from clean backups
   # Update all credentials
   ```

2. **Secure Recovery**
   ```bash
   # Use backup from before suspected compromise
   ./scripts/disaster-recovery.sh -s [clean_backup_session] --force
   
   # Change all passwords
   # Regenerate encryption keys
   # Update access credentials
   ```

#### Phase 3: Security Hardening (30-60 minutes)

1. **Security Updates**
   - Update all system packages
   - Apply security patches
   - Review access controls

2. **Enhanced Monitoring**
   - Enable additional logging
   - Implement intrusion detection
   - Schedule security scans

## 📊 COMMUNICATION PROCEDURES

### Initial Notification Template

```
SUBJECT: URGENT - System Outage/Data Recovery in Progress

INCIDENT: [Brief description]
START TIME: [Timestamp]
ESTIMATED RECOVERY: [Time estimate]
IMPACT: [Services affected]
RECOVERY TEAM: [Names]

ACTIONS TAKEN:
- [Action 1]
- [Action 2]

NEXT UPDATE: [Time]

Contact: [Emergency contact info]
```

### Status Update Template

```
SUBJECT: UPDATE - System Recovery Progress

INCIDENT: [Reference to original]
STATUS: [In Progress/Completed/Complications]
COMPLETION: [Percentage or updated estimate]

PROGRESS UPDATE:
- [Completed actions]
- [Current activities]
- [Remaining tasks]

NEXT UPDATE: [Time]
```

### Recovery Completion Template

```
SUBJECT: RESOLVED - System Recovery Complete

INCIDENT: [Reference]
RESOLUTION TIME: [Actual time taken]
ROOT CAUSE: [Brief explanation]

SYSTEMS RESTORED:
- [Service 1] - Operational
- [Service 2] - Operational

POST-INCIDENT ACTIONS:
- [Monitoring enhanced]
- [Process improvements]
- [Follow-up items]

INCIDENT CLOSED: [Timestamp]
```

## 🔧 TROUBLESHOOTING QUICK REFERENCE

### Common Error Messages

**"Permission denied" during recovery:**
```bash
# Fix script permissions
chmod +x dr-backups/scripts/*.sh

# Check directory ownership
chown -R $(whoami):$(whoami) dr-backups/
```

**"Database connection refused":**
```bash
# Check PostgreSQL status
docker-compose -f docker-compose.yml ps postgres

# Restart database
docker-compose -f docker-compose.yml restart postgres

# Wait for database ready
while ! pg_isready -h localhost -p 5432 -U odoo_master; do sleep 2; done
```

**"Cloud storage access denied":**
```bash
# Check AWS credentials
aws configure list

# Test S3 access
aws s3 ls s3://company-dr-backups/

# Update credentials if needed
aws configure
```

**"Encryption key not found":**
```bash
# Check key location
ls -la dr-backups/config/encryption.key

# Regenerate if necessary (WARNING: Will make existing backups unreadable)
./scripts/setup-encryption.sh
```

### Recovery Verification Checklist

- [ ] All Docker containers running
- [ ] Database accepting connections
- [ ] Web interface accessible
- [ ] User authentication working
- [ ] File uploads/downloads working
- [ ] Email notifications working
- [ ] Monitoring system active
- [ ] Backups resuming normally
- [ ] Performance within normal range
- [ ] No error messages in logs

### Rollback Procedures

If recovery fails or causes issues:

```bash
# Stop current services
docker-compose -f docker-compose.yml down

# Restore from pre-recovery backup
./scripts/disaster-recovery.sh -s [pre_recovery_backup] --force

# If that fails, restore from cloud
./scripts/disaster-recovery.sh -c -s [known_good_backup] --force
```

## 📋 POST-INCIDENT PROCEDURES

### Immediate Actions (Within 24 hours)

1. **Document Everything**
   - Timeline of events
   - Actions taken
   - Lessons learned
   - Process improvements

2. **Verify Full Recovery**
   - Run complete system tests
   - Verify data integrity
   - Check monitoring systems
   - Resume normal backups

3. **Stakeholder Communication**
   - Send final resolution notice
   - Schedule debrief meeting
   - Update status pages

### Follow-up Actions (Within 1 week)

1. **Root Cause Analysis**
   - Technical investigation
   - Process review
   - Documentation updates
   - Training needs assessment

2. **Process Improvements**
   - Update procedures
   - Enhance monitoring
   - Improve automation
   - Strengthen preventive measures

3. **Testing and Validation**
   - Test improved procedures
   - Validate new monitoring
   - Update disaster recovery plan
   - Schedule next DR drill

---

## 📞 EMERGENCY HOTLINE

**24/7 Emergency Response**: [Emergency Number]

**For immediate assistance during an incident, call the emergency hotline and reference this runbook.**

**Last Updated**: [Date]
**Next Review**: [Date]
**Version**: 1.0
