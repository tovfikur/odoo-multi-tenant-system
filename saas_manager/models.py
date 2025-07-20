from datetime import datetime
from flask_login import UserMixin
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
    
    tenants = db.relationship('TenantUser', back_populates='user')
    public_keys = db.relationship('UserPublicKey', backref='user')

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('SaasUser')
    tenant = db.relationship('Tenant')