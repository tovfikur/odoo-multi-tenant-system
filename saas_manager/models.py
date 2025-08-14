# Standard library imports
from datetime import datetime, timedelta

# Third-party imports
from flask_login import UserMixin

# Local application imports
from db import db

class SaasUser(db.Model, UserMixin):
    __tablename__ = 'saas_users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    phone = db.Column(db.String(20))
    timezone = db.Column(db.String(50), default='UTC')
    language = db.Column(db.String(10), default='en')
    notification_preferences = db.Column(db.JSON, default=lambda: {'email': True, 'sms': False})
    last_password_change = db.Column(db.DateTime, default=datetime.utcnow)
    failed_login_attempts = db.Column(db.Integer, default=0)
    account_locked_until = db.Column(db.DateTime)
    two_factor_enabled = db.Column(db.Boolean, default=False)
    two_factor_secret = db.Column(db.String(100))
    
    # Password reset functionality
    reset_token = db.Column(db.String(100))
    reset_token_expires = db.Column(db.DateTime)
    
    tenants = db.relationship('TenantUser', back_populates='user')
    public_keys = db.relationship('UserPublicKey', backref='user')
    notifications = db.relationship('UserNotification', back_populates='user', cascade='all, delete-orphan')
    support_tickets = db.relationship('SupportTicket', back_populates='user', cascade='all, delete-orphan')
    
    full_name = db.Column(db.String(100))
    bio = db.Column(db.Text)
    company = db.Column(db.String(100))
    location = db.Column(db.String(100))
    website = db.Column(db.String(200))
    profile_picture = db.Column(db.String(100))

    def get_profile_picture_url(self):
        """Get the URL for the profile picture or return None"""
        if self.profile_picture:
            return f'/static/uploads/profiles/{self.profile_picture}'
        return None
    
    def get_avatar_initials(self):
        """Get initials for avatar placeholder"""
        if self.full_name:
            names = self.full_name.split()
            if len(names) >= 2:
                return f"{names[0][0]}{names[1][0]}".upper()
            return names[0][0].upper()
        return self.username[0].upper()
    
    def generate_reset_token(self):
        """Generate a secure password reset token"""
        import secrets
        token = secrets.token_urlsafe(32)
        self.reset_token = token
        self.reset_token_expires = datetime.utcnow() + timedelta(hours=1)  # Token expires in 1 hour
        return token
    
    def verify_reset_token(self, token):
        """Verify if the reset token is valid and not expired"""
        return (self.reset_token == token and 
                self.reset_token_expires and 
                datetime.utcnow() < self.reset_token_expires)
    
    def clear_reset_token(self):
        """Clear the reset token after use"""
        self.reset_token = None
        self.reset_token_expires = None

class Tenant(db.Model):
    __tablename__ = 'tenants'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    subdomain = db.Column(db.String(50), nullable=False, unique=True)
    database_name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    plan = db.Column(db.String(50), default='basic')
    max_users = db.Column(db.Integer, default=10)
    storage_limit = db.Column(db.Integer, default=1024)
    is_active = db.Column(db.Boolean, default=True)
    admin_username = db.Column(db.String(50), nullable=False)
    admin_password = db.Column(db.String(255), nullable=False)
    password_salt = db.Column(db.String(32))
    last_password_change = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='pending')
    
    last_backup_at = db.Column(db.DateTime)
    backup_count = db.Column(db.Integer, default=0)
    total_storage_used = db.Column(db.BigInteger, default=0)  # in bytes
    last_activity_at = db.Column(db.DateTime)
    health_score = db.Column(db.Integer, default=100)  # 0-100
    custom_domain = db.Column(db.String(255))
    ssl_enabled = db.Column(db.Boolean, default=False)
    
    users = db.relationship('TenantUser', back_populates='tenant')

    def set_admin_password(self, password):
        try:
            import secrets
            self.password_salt = secrets.token_hex(16)
            self.admin_password = password
            self.last_password_change = datetime.utcnow()
        except Exception as e:
            from .utils import error_tracker
            error_tracker.log_error(e, {
                'tenant_id': self.id,
                'function': 'set_admin_password'
            })
            raise

    def get_admin_password(self):
        try:
            return self.admin_password
        except Exception as e:
            from .utils import error_tracker
            error_tracker.log_error(e, {
                'tenant_id': self.id,
                'function': 'get_admin_password'
            })
            return None

class TenantUser(db.Model):
    __tablename__ = 'tenant_users'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('saas_users.id'), nullable=False)
    role = db.Column(db.String(20), default='user')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    tenant = db.relationship('Tenant', back_populates='users')
    user = db.relationship('SaasUser', back_populates='tenants')

class SubscriptionPlan(db.Model):
    __tablename__ = 'subscription_plans'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    price = db.Column(db.Float, nullable=False)
    features = db.Column(db.JSON)
    max_users = db.Column(db.Integer, nullable=False)
    storage_limit = db.Column(db.Integer, nullable=True)  # Allow null for unlimited storage
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    modules = db.Column(db.JSON, nullable=True)  # Added modules column for plan-specific features
    billing_interval = db.Column(db.String(20), default='monthly')  # monthly, yearly
    trial_period_days = db.Column(db.Integer, default=0)
    setup_fee = db.Column(db.Float, default=0.0)
    api_calls_limit = db.Column(db.Integer, default=10000)
    bandwidth_limit = db.Column(db.Integer, default=100)  # GB
    support_level = db.Column(db.String(50), default='basic')  # basic, premium, enterprise
    custom_branding = db.Column(db.Boolean, default=False)
    priority_support = db.Column(db.Boolean, default=False)
    sla_uptime = db.Column(db.Float, default=99.9)  # Percentage




class WorkerInstance(db.Model):
    __tablename__ = 'worker_instances'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    container_name = db.Column(db.String(100), nullable=False)
    port = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='running')
    current_tenants = db.Column(db.Integer, default=0)
    max_tenants = db.Column(db.Integer, default=10)
    server_id = db.Column(db.Integer, db.ForeignKey('infrastructure_servers.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_health_check = db.Column(db.DateTime)

class UserPublicKey(db.Model):
    __tablename__ = 'user_public_keys'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('saas_users.id'), nullable=False)
    public_key = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    key_fingerprint = db.Column(db.String(64))

class CredentialAccess(db.Model):
    __tablename__ = 'credential_access_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('saas_users.id'), nullable=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    accessed_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    success = db.Column(db.Boolean, default=True)
    
    user = db.relationship('SaasUser')
    tenant = db.relationship('Tenant')

class Report(db.Model):
    __tablename__ = 'reports'
    
    id = db.Column(db.Integer, primary_key=True)
    report_type = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('saas_users.id'))
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'))
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.JSON)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('SaasUser')
    tenant = db.relationship('Tenant')

    def to_dict(self):
        """Convert audit log to dictionary for API responses"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'tenant_id': self.tenant_id,
            'action': self.action,
            'details': self.details,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'user_email': self.user.email if self.user else None
        }

# SUPPORT MODELS - These are for the existing support system (different from API)
class SupportTicket(db.Model):
    __tablename__ = 'support_tickets'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('saas_users.id'), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='open')  # open, in_progress, closed
    priority = db.Column(db.String(20), default='medium')  # low, medium, high, urgent
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    admin_notes = db.Column(db.Text)
    
    user = db.relationship('SaasUser', back_populates='support_tickets')

    def to_dict(self):
        return {
            'id': self.id,
            'subject': self.subject,
            'message': self.message,
            'status': self.status,
            'priority': self.priority,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'admin_notes': self.admin_notes,
            'user_email': self.user.email if self.user else None
        }

class SupportReply(db.Model):
    __tablename__ = 'support_replies'
    
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('support_tickets.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('saas_users.id'), nullable=True)  # None for admin replies
    message = db.Column(db.Text, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    ticket = db.relationship('SupportTicket', backref='replies')
    user = db.relationship('SaasUser', backref='support_replies')

    def to_dict(self):
        return {
            'id': self.id,
            'ticket_id': self.ticket_id,
            'message': self.message,
            'is_admin': self.is_admin,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'user_email': self.user.email if self.user else 'Admin'
        }

class Payment(db.Model):
    """Payment tracking for manual verification"""
    __tablename__ = 'payments'
    
    id = db.Column(db.String(50), primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('saas_users.id'), nullable=False)
    plan = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='USD')
    status = db.Column(db.String(20), default='pending')  # pending, verified, rejected, processing, failed
    payment_method = db.Column(db.String(50), default='stripe')
    transaction_id = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    verified_at = db.Column(db.DateTime)
    verified_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'))
    notes = db.Column(db.Text)
    payment_metadata = db.Column(db.JSON)
    
    # Relationships
    tenant = db.relationship('Tenant', backref='payments')
    user = db.relationship('SaasUser', foreign_keys=[user_id], backref='payments')
    verifier = db.relationship('SaasUser', foreign_keys=[verified_by])

class PaymentTransaction(db.Model):
    """Model to store payment transaction details"""
    __tablename__ = 'payment_transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.String(100), unique=True, nullable=False)
    validation_id = db.Column(db.String(100), nullable=True)  # Store val_id from SSLCommerz
    tenant_id = db.Column(db.Integer, nullable=False)  # Just an integer, no foreign key
    user_id = db.Column(db.Integer, db.ForeignKey('saas_users.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default='BDT')
    status = db.Column(db.String(50), default='PENDING')
    payment_method = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    response_data = db.Column(db.String(2000))  # Store raw response from SSLCommerz
    
    # Relationship with user (keeping this one)
    user = db.relationship('SaasUser', backref='payment_transactions')
    
    # NO tenant relationship - removed completely
    
    def get_tenant(self):
        """Get the associated tenant by manual lookup"""
        # Import here to avoid circular imports
        from models import Tenant
        return Tenant.query.get(self.tenant_id)
    
    def get_tenant_name(self):
        """Helper method to get tenant name safely"""
        tenant = self.get_tenant()
        return tenant.name if tenant else f"Unknown Tenant (ID: {self.tenant_id})"
    
    def __repr__(self):
        return f"<PaymentTransaction {self.transaction_id} - {self.status}>"


class SystemSetting(db.Model):
    """System-wide settings and configuration"""
    __tablename__ = 'system_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)
    value_type = db.Column(db.String(20), default='string')  # string, int, float, bool, json
    description = db.Column(db.Text)
    category = db.Column(db.String(50), default='general')
    is_public = db.Column(db.Boolean, default=False)  # Can be accessed by non-admin users
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'))
    
    updater = db.relationship('SaasUser')
    
    def get_typed_value(self):
        """Return value converted to appropriate type"""
        if self.value_type == 'int':
            return int(self.value) if self.value else 0
        elif self.value_type == 'float':
            return float(self.value) if self.value else 0.0
        elif self.value_type == 'bool':
            return self.value.lower() in ('true', '1', 'yes') if self.value else False
        elif self.value_type == 'json':
            import json
            return json.loads(self.value) if self.value else {}
        return self.value



class TenantModule(db.Model):
    """Track installed modules per tenant"""
    __tablename__ = 'tenant_modules'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    module_name = db.Column(db.String(100), nullable=False)
    version = db.Column(db.String(20))
    installed_at = db.Column(db.DateTime, default=datetime.utcnow)
    installed_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'))
    is_active = db.Column(db.Boolean, default=True)
    
    tenant = db.relationship('Tenant', backref='installed_modules')
    installer = db.relationship('SaasUser')
    
    __table_args__ = (db.UniqueConstraint('tenant_id', 'module_name'),)

class SystemMaintenanceLog(db.Model):
    """Log system maintenance activities"""
    __tablename__ = 'maintenance_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    operation = db.Column(db.String(100), nullable=False)  # backup, cleanup, optimize, etc.
    status = db.Column(db.String(20), default='running')  # running, completed, failed
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    initiated_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'))
    details = db.Column(db.JSON)
    error_message = db.Column(db.Text)
    
    initiator = db.relationship('SaasUser')

class SystemNotification(db.Model):
    """System-wide notifications for administrators"""
    __tablename__ = 'system_notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    level = db.Column(db.String(20), default='info')  # info, warning, error, success
    category = db.Column(db.String(50), default='system')
    target_users = db.Column(db.JSON)  # List of user IDs, empty = all admins
    is_read = db.Column(db.Boolean, default=False)
    is_dismissible = db.Column(db.Boolean, default=True)
    expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'))
    
    creator = db.relationship('SaasUser')

class TenantBackup(db.Model):
    """Track tenant backup operations"""
    __tablename__ = 'tenant_backups'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    backup_type = db.Column(db.String(20), default='full')  # full, incremental
    file_path = db.Column(db.String(500))
    file_size = db.Column(db.BigInteger)  # Size in bytes
    status = db.Column(db.String(20), default='pending')  # pending, completed, failed
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    initiated_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'))
    error_message = db.Column(db.Text)
    backup_metadata = db.Column(db.JSON)
    
    tenant = db.relationship('Tenant', backref='backups')
    initiator = db.relationship('SaasUser')

class BillingCycle(db.Model):
    """Track billing cycles for each tenant"""
    __tablename__ = 'billing_cycles'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    cycle_start = db.Column(db.DateTime, default=datetime.utcnow)
    cycle_end = db.Column(db.DateTime)
    total_hours_allowed = db.Column(db.Integer, default=360)  # 30 days * 12 hours
    hours_used = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='active')  # active, expired, renewed
    reminder_sent = db.Column(db.Boolean, default=False)
    auto_deactivated = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    tenant = db.relationship('Tenant', backref='billing_cycles')
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.cycle_end:
            self.cycle_end = self.cycle_start + timedelta(days=30)
    
    @property
    def hours_remaining(self):
        return max(0, self.total_hours_allowed - self.hours_used)
    
    @property
    def days_remaining(self):
        if not self.cycle_end:
            return 0
            
        # Ensure consistent datetime comparison (same fix as is_expired)
        current_time = datetime.utcnow()
        cycle_end_time = self.cycle_end
        
        # If cycle_end has timezone info, convert to naive UTC
        if hasattr(cycle_end_time, 'tzinfo') and cycle_end_time.tzinfo is not None:
            cycle_end_time = cycle_end_time.replace(tzinfo=None)
            
        delta = cycle_end_time - current_time
        return max(0, delta.days)
    
    @property
    def is_expired(self):
        # Check hours usage first
        if self.hours_used >= self.total_hours_allowed:
            return True
        
        # Check time expiry - handle None cycle_end and ensure proper comparison
        if not self.cycle_end:
            return True
            
        # Ensure both datetimes are timezone-naive for comparison
        current_time = datetime.utcnow()
        cycle_end_time = self.cycle_end
        
        # If cycle_end has timezone info, convert to naive UTC
        if hasattr(cycle_end_time, 'tzinfo') and cycle_end_time.tzinfo is not None:
            cycle_end_time = cycle_end_time.replace(tzinfo=None)
            
        return current_time > cycle_end_time
    
    @property
    def should_send_reminder(self):
        return (not self.reminder_sent and 
                self.hours_remaining <= 84 and  # 7 days * 12 hours
                not self.is_expired)

class UsageTracking(db.Model):
    """Track hourly usage for each tenant"""
    __tablename__ = 'usage_tracking'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    billing_cycle_id = db.Column(db.Integer, db.ForeignKey('billing_cycles.id'), nullable=False)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)
    database_active = db.Column(db.Boolean, default=False)
    uptime_hours = db.Column(db.Float, default=0.0)  # Fraction of hour the DB was active
    downtime_reason = db.Column(db.String(100))  # maintenance, user_deactivated, expired, etc.
    
    tenant = db.relationship('Tenant', backref='usage_logs')
    billing_cycle = db.relationship('BillingCycle', backref='usage_logs')

class PaymentHistory(db.Model):
    """Enhanced payment history for billing cycles"""
    __tablename__ = 'payment_history'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    billing_cycle_id = db.Column(db.Integer, db.ForeignKey('billing_cycles.id'), nullable=True)
    payment_id = db.Column(db.String(100), unique=True)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='USD')
    payment_method = db.Column(db.String(50))
    status = db.Column(db.String(20), default='pending')  # pending, completed, failed, refunded
    gateway_transaction_id = db.Column(db.String(200))
    gateway_response = db.Column(db.JSON)
    paid_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    tenant = db.relationship('Tenant', backref='payment_history')
    billing_cycle = db.relationship('BillingCycle', backref='payments')

class BillingNotification(db.Model):
    """Track billing-related notifications and support tickets"""
    __tablename__ = 'billing_notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    billing_cycle_id = db.Column(db.Integer, db.ForeignKey('billing_cycles.id'), nullable=False)
    support_ticket_id = db.Column(db.Integer, db.ForeignKey('support_tickets.id'), nullable=True)
    notification_type = db.Column(db.String(50), nullable=False)  # reminder, expiry, renewal
    message = db.Column(db.Text, nullable=False)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    viewed_at = db.Column(db.DateTime)
    is_read = db.Column(db.Boolean, default=False)
    
    tenant = db.relationship('Tenant', backref='billing_notifications')
    billing_cycle = db.relationship('BillingCycle', backref='notifications')
    support_ticket = db.relationship('SupportTicket', backref='billing_notifications')



def add_helper_methods_to_models():
    """Add helper methods to existing models"""
    
    # Add to WorkerInstance model
    @property
    def load_percentage(self):
        if self.max_tenants == 0:
            return 0
        return (self.current_tenants / self.max_tenants) * 100
    
    @property
    def is_overloaded(self):
        return self.current_tenants > self.max_tenants
    
    # Add to Tenant model
    @property
    def resource_usage_score(self):
        """Calculate resource usage score for load balancing"""
        # This is a simplified calculation
        base_score = 1
        if hasattr(self, 'storage_usage') and self.storage_usage:
            base_score += self.storage_usage / 1000  # Adjust based on storage
        
        user_count = TenantUser.query.filter_by(tenant_id=self.id).count()
        base_score += user_count * 0.1  # Adjust based on user count
        
        return base_score

# ================= INFRASTRUCTURE ADMIN MODELS =================

class InfrastructureServer(db.Model):
    """Infrastructure server management model"""
    __tablename__ = 'infrastructure_servers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    ip_address = db.Column(db.String(45), nullable=False)
    username = db.Column(db.String(50), nullable=False)
    password = db.Column(db.String(255))  # Encrypted
    ssh_key_path = db.Column(db.String(500))
    port = db.Column(db.Integer, default=22)
    
    # Service roles this server can handle
    service_roles = db.Column(db.JSON, default=list)
    current_services = db.Column(db.JSON, default=list)
    
    # Server specifications
    cpu_cores = db.Column(db.Integer)
    memory_gb = db.Column(db.Integer)
    disk_gb = db.Column(db.Integer)
    os_type = db.Column(db.String(50))
    
    # Status and health
    status = db.Column(db.String(20), default='pending')
    last_health_check = db.Column(db.DateTime)
    health_score = db.Column(db.Integer, default=100)
    
    # Deployment tracking
    deployment_status = db.Column(db.String(50), default='ready')
    deployment_log = db.Column(db.Text)
    
    # Monitoring and alerts
    monitoring_enabled = db.Column(db.Boolean, default=True)
    alert_email = db.Column(db.String(100))
    alert_webhook = db.Column(db.String(500))
    
    # Resource limits
    max_cpu_usage = db.Column(db.Integer, default=80)
    max_memory_usage = db.Column(db.Integer, default=80)
    max_disk_usage = db.Column(db.Integer, default=85)
    
    # Network configuration
    internal_ip = db.Column(db.String(45))
    external_ip = db.Column(db.String(45))
    network_zone = db.Column(db.String(50), default='production')
    
    # Backup configuration
    backup_enabled = db.Column(db.Boolean, default=True)
    backup_frequency = db.Column(db.String(50), default='daily')
    backup_retention_days = db.Column(db.Integer, default=30)
    last_backup_at = db.Column(db.DateTime)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'))
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'ip_address': self.ip_address,
            'service_roles': self.service_roles,
            'current_services': self.current_services,
            'status': self.status,
            'health_score': self.health_score,
            'deployment_status': self.deployment_status,
            'cpu_cores': self.cpu_cores,
            'memory_gb': self.memory_gb,
            'disk_gb': self.disk_gb,
            'os_type': self.os_type,
            'last_health_check': self.last_health_check.isoformat() if self.last_health_check else None,
            'created_at': self.created_at.isoformat()
        }

class DomainMapping(db.Model):
    """Domain mapping for custom domains to tenants"""
    __tablename__ = 'domain_mappings'
    
    id = db.Column(db.Integer, primary_key=True)
    custom_domain = db.Column(db.String(255), nullable=False, unique=True)
    target_subdomain = db.Column(db.String(100), nullable=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'))
    
    # Load balancing configuration
    load_balancer_enabled = db.Column(db.Boolean, default=True)
    load_balancer_method = db.Column(db.String(50), default='round_robin')
    upstream_servers = db.Column(db.JSON, default=list)
    
    # SSL Configuration
    ssl_enabled = db.Column(db.Boolean, default=False)
    ssl_cert_path = db.Column(db.String(500))
    ssl_key_path = db.Column(db.String(500))
    ssl_auto_renew = db.Column(db.Boolean, default=True)
    ssl_provider = db.Column(db.String(50), default='letsencrypt')
    
    # Security settings
    force_https = db.Column(db.Boolean, default=True)
    hsts_enabled = db.Column(db.Boolean, default=True)
    security_headers = db.Column(db.JSON, default=dict)
    
    # Caching and performance
    cache_enabled = db.Column(db.Boolean, default=True)
    cache_ttl = db.Column(db.Integer, default=3600)
    compression_enabled = db.Column(db.Boolean, default=True)
    
    # Rate limiting
    rate_limit_enabled = db.Column(db.Boolean, default=False)
    rate_limit_requests = db.Column(db.Integer, default=100)
    rate_limit_window = db.Column(db.Integer, default=60)
    
    # Access control
    ip_whitelist = db.Column(db.JSON, default=list)
    ip_blacklist = db.Column(db.JSON, default=list)
    geo_restrictions = db.Column(db.JSON, default=dict)
    
    # Status and monitoring
    status = db.Column(db.String(20), default='pending')
    last_verified = db.Column(db.DateTime)
    verification_status = db.Column(db.String(50))
    uptime_check_enabled = db.Column(db.Boolean, default=True)
    uptime_check_interval = db.Column(db.Integer, default=300)
    
    # Analytics and logging
    access_log_enabled = db.Column(db.Boolean, default=True)
    analytics_enabled = db.Column(db.Boolean, default=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'))
    
    # Relationships
    tenant = db.relationship('Tenant', backref='domain_mappings')
    
    def to_dict(self):
        return {
            'id': self.id,
            'custom_domain': self.custom_domain,
            'target_subdomain': self.target_subdomain,
            'tenant_id': self.tenant_id,
            'tenant_name': self.tenant.name if self.tenant else None,
            'ssl_enabled': self.ssl_enabled,
            'status': self.status,
            'verification_status': self.verification_status,
            'last_verified': self.last_verified.isoformat() if self.last_verified else None,
            'created_at': self.created_at.isoformat()
        }

class DeploymentTask(db.Model):
    """Deployment and migration task tracking"""
    __tablename__ = 'deployment_tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    task_type = db.Column(db.String(50), nullable=False)
    service_type = db.Column(db.String(50), nullable=False)
    source_server_id = db.Column(db.Integer, db.ForeignKey('infrastructure_servers.id'))
    target_server_id = db.Column(db.Integer, db.ForeignKey('infrastructure_servers.id'))
    
    # Task configuration
    config = db.Column(db.JSON)
    priority = db.Column(db.String(20), default='normal')
    
    # Dependencies
    depends_on = db.Column(db.JSON, default=list)
    blocks = db.Column(db.JSON, default=list)
    
    # Status tracking
    status = db.Column(db.String(20), default='pending')
    progress = db.Column(db.Integer, default=0)
    current_step = db.Column(db.String(100))
    total_steps = db.Column(db.Integer, default=1)
    
    # Logging and debugging
    logs = db.Column(db.Text)
    error_message = db.Column(db.Text)
    debug_info = db.Column(db.JSON)
    
    # Performance tracking
    estimated_duration = db.Column(db.Integer)
    actual_duration = db.Column(db.Integer)
    
    # Resource usage
    cpu_usage_avg = db.Column(db.Float)
    memory_usage_avg = db.Column(db.Float)
    disk_io_total = db.Column(db.BigInteger)
    network_io_total = db.Column(db.BigInteger)
    
    # Rollback information
    rollback_supported = db.Column(db.Boolean, default=False)
    rollback_data = db.Column(db.JSON)
    rolled_back_at = db.Column(db.DateTime)
    rolled_back_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'))
    
    # Timestamps
    scheduled_at = db.Column(db.DateTime)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'))
    
    # Relationships
    source_server = db.relationship('InfrastructureServer', foreign_keys=[source_server_id])
    target_server = db.relationship('InfrastructureServer', foreign_keys=[target_server_id])
    
    def to_dict(self):
        return {
            'id': self.id,
            'task_type': self.task_type,
            'service_type': self.service_type,
            'source_server': self.source_server.name if self.source_server else None,
            'target_server': self.target_server.name if self.target_server else None,
            'status': self.status,
            'progress': self.progress,
            'current_step': self.current_step,
            'priority': self.priority,
            'error_message': self.error_message,
            'estimated_duration': self.estimated_duration,
            'actual_duration': self.actual_duration,
            'rollback_supported': self.rollback_supported,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'created_at': self.created_at.isoformat()
        }

class CronJob(db.Model):
    """Cron job management across infrastructure"""
    __tablename__ = 'cron_jobs'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    command = db.Column(db.Text, nullable=False)
    schedule = db.Column(db.String(100), nullable=False)
    server_id = db.Column(db.Integer, db.ForeignKey('infrastructure_servers.id'))
    
    # Job configuration
    working_directory = db.Column(db.String(500))
    environment_vars = db.Column(db.JSON, default=dict)
    timeout_seconds = db.Column(db.Integer, default=3600)
    retry_attempts = db.Column(db.Integer, default=0)
    retry_delay = db.Column(db.Integer, default=60)
    
    # Notification settings
    notify_on_success = db.Column(db.Boolean, default=False)
    notify_on_failure = db.Column(db.Boolean, default=True)
    notification_email = db.Column(db.String(100))
    notification_webhook = db.Column(db.String(500))
    
    # Status tracking
    status = db.Column(db.String(20), default='active')
    last_run = db.Column(db.DateTime)
    next_run = db.Column(db.DateTime)
    last_result = db.Column(db.Text)
    last_exit_code = db.Column(db.Integer)
    run_count = db.Column(db.Integer, default=0)
    success_count = db.Column(db.Integer, default=0)
    failure_count = db.Column(db.Integer, default=0)
    
    # Performance tracking
    avg_runtime_seconds = db.Column(db.Float, default=0.0)
    max_runtime_seconds = db.Column(db.Float, default=0.0)
    last_runtime_seconds = db.Column(db.Float, default=0.0)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'))
    
    # Relationships
    server = db.relationship('InfrastructureServer', backref='cron_jobs')

class NetworkScanResult(db.Model):
    """Network scan results for server discovery"""
    __tablename__ = 'network_scan_results'
    
    id = db.Column(db.Integer, primary_key=True)
    scan_task_id = db.Column(db.Integer, db.ForeignKey('deployment_tasks.id'))
    ip_address = db.Column(db.String(45), nullable=False)
    hostname = db.Column(db.String(255))
    
    # Connectivity
    is_reachable = db.Column(db.Boolean, default=False)
    response_time_ms = db.Column(db.Float)
    
    # SSH accessibility
    ssh_accessible = db.Column(db.Boolean, default=False)
    ssh_port = db.Column(db.Integer, default=22)
    ssh_version = db.Column(db.String(100))
    
    # System information
    os_type = db.Column(db.String(50))
    os_version = db.Column(db.String(100))
    kernel_version = db.Column(db.String(100))
    cpu_cores = db.Column(db.Integer)
    memory_gb = db.Column(db.Integer)
    disk_gb = db.Column(db.Integer)
    architecture = db.Column(db.String(20))
    
    # Installed services
    installed_services = db.Column(db.JSON, default=list)
    running_services = db.Column(db.JSON, default=list)
    open_ports = db.Column(db.JSON, default=list)
    
    # Security information
    has_firewall = db.Column(db.Boolean, default=False)
    firewall_type = db.Column(db.String(50))
    requires_sudo = db.Column(db.Boolean, default=True)
    
    # Suitability assessment
    suitability_score = db.Column(db.Integer, default=0)
    recommended_roles = db.Column(db.JSON, default=list)
    compatibility_issues = db.Column(db.JSON, default=list)
    
    # Auto-setup readiness
    auto_setup_ready = db.Column(db.Boolean, default=False)
    setup_requirements = db.Column(db.JSON, default=list)
    estimated_setup_time = db.Column(db.Integer)
    
    # Timestamps
    scanned_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ConfigurationTemplate(db.Model):
    """Templates for server and service configurations"""
    __tablename__ = 'configuration_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    template_type = db.Column(db.String(50), nullable=False)
    
    # Template content
    template_content = db.Column(db.Text, nullable=False)
    template_variables = db.Column(db.JSON, default=dict)
    default_values = db.Column(db.JSON, default=dict)
    
    # Template metadata
    version = db.Column(db.String(20), default='1.0')
    category = db.Column(db.String(50))
    tags = db.Column(db.JSON, default=list)
    
    # Requirements and compatibility
    min_memory_gb = db.Column(db.Integer)
    min_cpu_cores = db.Column(db.Integer)
    min_disk_gb = db.Column(db.Integer)
    supported_os = db.Column(db.JSON, default=list)
    required_services = db.Column(db.JSON, default=list)
    
    # Usage tracking
    usage_count = db.Column(db.Integer, default=0)
    last_used_at = db.Column(db.DateTime)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    is_validated = db.Column(db.Boolean, default=False)
    validation_results = db.Column(db.JSON)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'))

class InfrastructureAlert(db.Model):
    """Infrastructure monitoring alerts"""
    __tablename__ = 'infrastructure_alerts'
    
    id = db.Column(db.Integer, primary_key=True)
    alert_type = db.Column(db.String(50), nullable=False)
    severity = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    
    # Source information
    server_id = db.Column(db.Integer, db.ForeignKey('infrastructure_servers.id'))
    domain_id = db.Column(db.Integer, db.ForeignKey('domain_mappings.id'))
    service_name = db.Column(db.String(100))
    
    # Alert data
    metric_name = db.Column(db.String(100))
    metric_value = db.Column(db.Float)
    threshold_value = db.Column(db.Float)
    alert_data = db.Column(db.JSON)
    
    # Status and resolution
    status = db.Column(db.String(20), default='active')
    acknowledged_at = db.Column(db.DateTime)
    acknowledged_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'))
    resolved_at = db.Column(db.DateTime)
    resolved_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'))
    resolution_notes = db.Column(db.Text)
    
    # Notification tracking
    notification_sent = db.Column(db.Boolean, default=False)
    notification_methods = db.Column(db.JSON, default=list)
    notification_failures = db.Column(db.JSON, default=list)
    
    # Frequency and deduplication
    occurrence_count = db.Column(db.Integer, default=1)
    first_occurrence = db.Column(db.DateTime, default=datetime.utcnow)
    last_occurrence = db.Column(db.DateTime, default=datetime.utcnow)
    fingerprint = db.Column(db.String(100))
    
    # Escalation
    escalation_level = db.Column(db.Integer, default=0)
    escalated_at = db.Column(db.DateTime)
    auto_resolve_after = db.Column(db.Integer)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    server = db.relationship('InfrastructureServer', backref='alerts')
    domain = db.relationship('DomainMapping', backref='alerts')

# Import UserNotification at the end to avoid circular import issues
try:
    from user_notifications import UserNotification
except ImportError:
    # UserNotification may not be available during initial setup
    pass