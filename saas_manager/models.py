# Standard library imports
from datetime import datetime

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
    
    tenants = db.relationship('TenantUser', back_populates='user')
    public_keys = db.relationship('UserPublicKey', backref='user')
    
    full_name = db.Column(db.String(100))
    bio = db.Column(db.Text)
    company = db.Column(db.String(100))
    location = db.Column(db.String(100))
    website = db.Column(db.String(200))
    language = db.Column(db.String(10), default='en')
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
    storage_limit = db.Column(db.Integer, nullable=False)  # Added missing column
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

# SUPPORT MODELS - Added here to avoid table redefinition errors
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
    
    user = db.relationship('SaasUser', backref='support_tickets')

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

class BlockedIP(db.Model):
    """IP addresses blocked from accessing the system"""
    __tablename__ = 'blocked_ips'
    
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), unique=True, nullable=False)  # Supports IPv6
    reason = db.Column(db.String(255))
    blocked_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'), nullable=False)
    blocked_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)  # NULL means permanent
    is_active = db.Column(db.Boolean, default=True)
    
    blocker = db.relationship('SaasUser')

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