#!/usr/bin/env python3
"""
Khudroo Management Application with Enhanced Error Tracking and Redis Integration
Main Flask application for managing Odoo tenants
"""

# Standard library imports
import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import secrets
import string
import sys
import traceback
import xmlrpc.client
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import secrets
import base64
from functools import wraps

# Third-party imports
import docker.errors
import psycopg2
import requests
from urllib.parse import urlparse
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, make_response, send_file
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_session import Session
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from PIL import Image
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from wtforms import StringField, PasswordField, SelectField, IntegerField, BooleanField, HiddenField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, ValidationError, Email, EqualTo, Optional

# Local application imports
from cache_manager import get_cached_user_tenants, get_cached_admin_stats, invalidate_tenant_cache, invalidate_user_cache, create_cache_manager
from db import db
from factory import create_app, init_db
from models import SaasUser, Tenant, TenantUser, SubscriptionPlan, WorkerInstance, UserPublicKey, CredentialAccess, Report, AuditLog, PaymentTransaction
from utils import error_tracker, logger, track_errors
from websocket_handler import WebSocketManager, setup_websocket_handlers, UpdateTrigger
from shared_utils import get_redis_client, get_docker_client, safe_execute, database_transaction, log_error_with_context

# Local application imports - use relative imports in package context
try:
    from .infra_admin import infra_admin_bp
    from .master_admin import master_admin_bp
    from .system_admin import system_admin_bp
    from .OdooDatabaseManager import OdooDatabaseManager
    from .TenantLogManager import TenantLogManager
    from .support import support_bp
    from .support_admin import support_admin_bp
    from .billing import BillingService, register_unified_billing_routes
    from .billing_routes import billing_bp
except ImportError:
    # Fallback to absolute imports when running as script
    from infra_admin import infra_admin_bp
    from master_admin import master_admin_bp
    from system_admin import system_admin_bp
    from OdooDatabaseManager import OdooDatabaseManager
    from TenantLogManager import TenantLogManager
    from support import support_bp
    from support_admin import support_admin_bp
    from billing import BillingService, register_unified_billing_routes
    from billing_routes import billing_bp
    


def run_async_in_background(coro):
    """Helper function to run an async coroutine in the background."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(coro)
    finally:
        loop.close()

def get_tenant_domain_url(tenant):
    """Generate dynamic domain URL for tenant based on current request"""
    try:
        # Get the current domain from the request
        if request:
            host = request.host
            # Remove port if present
            if ':' in host:
                host = host.split(':')[0]
            
            # Create the full domain URL
            scheme = 'https' if request.is_secure else 'http'
            return f"{scheme}://kdoo_{tenant.subdomain}.{host}"
        else:
            # Fallback to configured domain
            return f"https://kdoo_{tenant.subdomain}.domain.com"
    except Exception:
        # Fallback to default domain
        return f"https://kdoo_{tenant.subdomain}.domain.com"

# Create Flask app
app, csrf = create_app()
init_db(app)
app.register_blueprint(infra_admin_bp)
app.register_blueprint(master_admin_bp)
app.register_blueprint(system_admin_bp)
app.register_blueprint(support_bp)
app.register_blueprint(support_admin_bp)
app.register_blueprint(billing_bp)
logger.info("✅ Billing blueprint registered successfully")
logger.info(f"Billing blueprint routes: {[str(rule) for rule in app.url_map.iter_rules() if 'billing' in str(rule)]}")
register_unified_billing_routes(app, csrf)
logger.info("✅ Unified billing routes registered successfully")

# Register API routes (after all imports are available)
try:
    from api_routes import api_bp
    app.register_blueprint(api_bp)
    print("✅ API routes registered successfully")
except ImportError as e:
    print(f"⚠️  API routes not available: {e}")

# Register User API routes
try:
    from user_api import user_api_bp
    app.register_blueprint(user_api_bp)
    print("✅ User API routes registered successfully")
except ImportError as e:
    print(f"⚠️  User API routes not available: {e}")

# Register Public API routes
try:
    from public_api import public_api_bp
    app.register_blueprint(public_api_bp)
    print("✅ Public API routes registered successfully")
except ImportError as e:
    print(f"⚠️  Public API routes not available: {e}")

# Register Tenant API routes
try:
    from tenant_api import tenant_api_bp
    app.register_blueprint(tenant_api_bp)
    print("✅ Tenant API routes registered successfully")
except ImportError as e:
    print(f"⚠️  Tenant API routes not available: {e}")

# Register Billing API routes
try:
    from billing_api import billing_api_bp
    app.register_blueprint(billing_api_bp)
    print("✅ Billing API routes registered successfully")
except ImportError as e:
    print(f"⚠️  Billing API routes not available: {e}")

# Register Support API routes
try:
    from support_api import support_api_bp
    app.register_blueprint(support_api_bp)
    print("✅ Support API routes registered successfully")
except ImportError as e:
    print(f"⚠️  Support API routes not available: {e}")

# Add CSRF token to template context
@app.context_processor
def inject_csrf_token():
    """Make CSRF token available to all templates"""
    from flask_wtf.csrf import generate_csrf
    return dict(csrf_token=generate_csrf)

# Alternative method - add as template global
@app.template_global()
def csrf_token():
    """Generate CSRF token for templates"""
    from flask_wtf.csrf import generate_csrf
    return generate_csrf()

# Debug middleware to track all requests
@app.before_request
def log_request_debug():
    """Debug logging for all requests"""
    # Log ALL billing/payment related requests, not just payment ones
    if (request.endpoint and ('payment' in str(request.endpoint) or 'billing' in str(request.endpoint))) or \
       (request.path and ('/billing/' in request.path or '/payment' in request.path)):
        logger.info(f"=== COMPLETE REQUEST DEBUG ===")
        logger.info(f"Endpoint: {request.endpoint}")
        logger.info(f"Method: {request.method}")
        logger.info(f"URL: {request.url}")
        logger.info(f"Path: {request.path}")
        logger.info(f"User-Agent: {request.headers.get('User-Agent', 'None')[:100]}")
        logger.info(f"Referrer: {request.headers.get('Referer', 'None')}")
        logger.info(f"Current user: {current_user.id if current_user and hasattr(current_user, 'id') else 'Anonymous'}")
        
        # Log all headers for payment requests
        if request.method == 'POST':
            logger.info(f"All Headers: {dict(request.headers)}")
            logger.info(f"Form data: {dict(request.form)}")
            logger.info(f"Raw data: {request.get_data(as_text=True)[:500]}")
            logger.info(f"Content-Type: {request.content_type}")
            logger.info(f"CSRF token present: {'csrf_token' in request.form}")
            if 'csrf_token' in request.form:
                logger.info(f"CSRF token value: '{request.form['csrf_token']}'")
        
        # Also log session info
        from flask import session
        logger.info(f"Session keys: {list(session.keys())}")
        logger.info(f"Session CSRF: {session.get('csrf_token', 'NOT_FOUND')}")
        
        # Try to generate a fresh CSRF token for comparison
        try:
            from flask_wtf.csrf import generate_csrf
            fresh_token = generate_csrf()
            logger.info(f"Fresh CSRF token: {fresh_token}")
        except Exception as e:
            logger.error(f"Failed to generate fresh CSRF token: {e}")
        
        logger.info(f"=== END COMPLETE REQUEST DEBUG ===")

# CSRF error handler
@app.errorhandler(400) 
def csrf_error(reason):
    """Handle CSRF validation errors with detailed logging"""
    logger.error(f"=== CSRF ERROR DEBUG ===")
    logger.error(f"Error reason: {reason}")
    logger.error(f"Request method: {request.method}")
    logger.error(f"Request URL: {request.url}")
    logger.error(f"Request endpoint: {request.endpoint}")
    if request.method == 'POST':
        logger.error(f"Form data received: {dict(request.form)}")
        logger.error(f"CSRF token in form: {'csrf_token' in request.form}")
        if 'csrf_token' in request.form:
            logger.error(f"CSRF token value: {request.form['csrf_token']}")
    
    from flask import session
    logger.error(f"Session data: {dict(session)}")
    logger.error(f"=== END CSRF ERROR DEBUG ===")
    
    # Redirect back with error message
    flash('Security token validation failed. Please try again.', 'error')
    return redirect(request.referrer or url_for('dashboard'))

# Initialize Odoo manager and other services
odoo = OdooDatabaseManager(odoo_url="http://odoo_master:8069", master_pwd=os.environ.get('ODOO_MASTER_PASSWORD', 'admin123'))
logger.info(f"Using Odoo URL: {odoo.odoo_url}")
logger.info(f"Using Odoo Master Password: {odoo.master_pwd}")

# Initialize Redis client using shared utilities
redis_client = get_redis_client()
if redis_client:
    logger.info("Redis client initialized successfully")
else:
    logger.warning("Redis client not available")

# Configure Flask-Session to use Redis
if redis_client:
    app.config['SESSION_TYPE'] = 'redis'
    app.config['SESSION_REDIS'] = redis_client
    Session(app)
else:
    logger.warning("Redis not available, falling back to default session management")

# Initialize Flask-Limiter with Redis
if redis_client:
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["2000000 per day", "6000 per hour"],
        storage_uri=os.environ.get('REDIS_URL', 'redis://redis:6379/0')
    )
    limiter.init_app(app)
else:
    logger.warning("Redis not available, rate limiting disabled")
    limiter = None

# Initialize Docker client using shared utilities
docker_client = get_docker_client()
if docker_client:
    logger.info("Docker client initialized successfully")
else:
    logger.warning("Docker client not available")

# Initialize SocketIO
# Initialize SocketIO with proper configuration
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode='threading',
    logger=False,
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25
)

# Socket.io error handlers
@socketio.on_error_default
def default_error_handler(e):
    logger.error(f"Socket.io error: {e}")
    error_tracker.log_error(e, {'component': 'socketio'})

@socketio.on('connect_error')
def connect_error():
    logger.warning("Socket.io connection error")
    
# Configure Socket.io fallback for development
if os.environ.get('FLASK_ENV') == 'development':
    app.config['SOCKETIO_FALLBACK'] = True
    logger.info("Socket.io fallback enabled for development")
    
# Initialize cache manager
cache_manager = create_cache_manager(redis_client)
app.cache_manager = cache_manager

# Initialize WebSocket manager
ws_manager = WebSocketManager(socketio, redis_client)
update_trigger = UpdateTrigger(cache_manager, ws_manager)

# Setup WebSocket handlers
setup_websocket_handlers(socketio, ws_manager)


from flask_migrate import Migrate
migrate = Migrate(app, db)

@app.errorhandler(Exception)
def handle_exception(e):
    """Global error handler with detailed logging"""
    context = {
        'route': request.endpoint,
        'method': request.method,
        'url': request.url
    }
    
    request_info = error_tracker.get_request_info()
    error_info = error_tracker.log_error(e, context, request_info)
    
    if redis_client:
        try:
            error_data = {
                'timestamp': error_info['timestamp'],
                'error_type': error_info['error_type'],
                'error_message': error_info['error_message'],
                'context': error_info['context']
            }
            redis_client.lpush('recent_errors', json.dumps(error_data))
            redis_client.ltrim('recent_errors', 0, 99)  # Keep last 100 errors
        except Exception as redis_error:
            logger.warning(f"Failed to store error in Redis: {redis_error}")
    
    if isinstance(e, Exception):
        return jsonify({
            'error': 'Internal server error',
            'message': str(e),
            'timestamp': datetime.utcnow().isoformat(),
            'error_id': hash(str(error_info))
        }), 500

class TenantCredentialService:
    """Service for handling encrypted tenant credentials"""
    
    @staticmethod
    @track_errors('encrypt_credentials')
    def encrypt_credentials(public_key_pem, username, password):
        try:
            public_key = serialization.load_pem_public_key(public_key_pem.encode())
            credentials = f"{username}:{password}"
            encrypted = public_key.encrypt(
                credentials.encode('utf-8'),
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            return base64.b64encode(encrypted).decode('utf-8')
        except Exception as e:
            error_tracker.log_error(e, {'function': 'encrypt_credentials', 'username': username})
            return None
    
    @staticmethod
    @track_errors('generate_key_fingerprint')
    def generate_key_fingerprint(public_key_pem):
        try:
            return hashlib.sha256(public_key_pem.encode()).hexdigest()[:16]
        except Exception as e:
            error_tracker.log_error(e, {'function': 'generate_key_fingerprint'})
            return None
    
    @staticmethod
    @track_errors('validate_public_key')
    def validate_public_key(public_key_pem):
        try:
            serialization.load_pem_public_key(public_key_pem.encode())
            return True
        except Exception as e:
            error_tracker.log_error(e, {'function': 'validate_public_key'})
            return False

@track_errors('email_validator')
def email_validator(form, field):
    try:
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        if not re.match(email_pattern, field.data):
            raise ValidationError('Invalid email address.')
    except Exception as e:
        error_tracker.log_error(e, {'validator': 'email_validator', 'field_data': field.data, 'form': str(form)})
        raise ValidationError('Email validation failed.')

@track_errors('login_form_validation')
class LoginForm(FlaskForm):
    username = StringField('Username or Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])

class ForgotPasswordForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])

class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(), 
        EqualTo('password', message='Passwords must match.')
    ])

@track_errors('register_form_validation')
class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=50)])
    # email = StringField('Email', validators=[DataRequired(), email_validator])
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])

@track_errors('tenant_form_validation')
class TenantForm(FlaskForm):
    name = StringField('Organization Name', validators=[DataRequired(), Length(min=3, max=100)])
    subdomain = StringField('Subdomain', validators=[DataRequired(), Length(min=3, max=50)])
    plan = SelectField('Subscription Plan', choices=[], validators=[DataRequired()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.plan.choices = [(plan.name, plan.name.capitalize()) for plan in SubscriptionPlan.query.filter_by(is_active=True).all()]

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            if not current_user.is_authenticated or not current_user.is_admin:
                flash('Admin access required.', 'error')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        except Exception as e:
            error_tracker.log_error(e, {
                'decorator': 'admin_required',
                'function': f.__name__,
                'user_authenticated': current_user.is_authenticated if current_user else False
            })
            flash('Authorization error occurred.', 'error')
            return redirect(url_for('login'))
    return decorated_function








@track_errors('database_creation')
async def create_database(db_name, username='admin', password='admin',  modules=None, app=None):
    """Create Odoo database ONLY after successful payment"""
    
    # Import BillingService for status updates
    try:
        from billing_service import BillingService
    except ImportError:
        pass  # Use global BillingService if available
    
    default_modules = ['base', 'web', 'auth_signup', 'global_head_injector', 'saas_user_limit', 'muk_web_theme', 'sso_auth']
    if modules is None:
        modules = default_modules
    else:
        modules = list(set(modules) | set(default_modules))
    
    try:
        logger.info(f"Creating database {db_name} after successful payment")
        
        # Create database via Odoo HTTP API
        response = requests.post(
            f"{os.environ.get('ODOO_URL', 'http://odoo_master:8069')}/web/database/create",
            data={
                'master_pwd': os.environ.get('ODOO_MASTER_PASSWORD'),
                'name': db_name,
                'login': username,
                'password': password,
                'lang': 'en_US',
                'country_code': 'US',
                'phone': '',
                'demo': True
            },
            timeout=300
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to create database {db_name}: {response.status_code} - {response.text}")
            # Update tenant status to failed
            # Import the function from billing module
            from billing import _update_tenant_status_to_failed
            _update_tenant_status_to_failed(db_name, f"Database creation failed: {response.status_code}", app)
            return False
        
        logger.info(f"Database {db_name} created successfully")
            
        # Authenticate with the new database
        common = xmlrpc.client.ServerProxy(f"{os.environ.get('ODOO_URL', 'http://odoo_master:8069')}/xmlrpc/2/common")
        uid = common.authenticate(db_name, username, password, {})
        
        if not uid:
            logger.error(f"Authentication failed for database {db_name}")
            # Import the function from billing module
            from billing import _update_tenant_status_to_failed
            _update_tenant_status_to_failed(db_name, "Authentication failed after database creation", app)
            return False
        
        models = xmlrpc.client.ServerProxy(f"{os.environ.get('ODOO_URL', 'http://odoo_master:8069')}/xmlrpc/2/object")
        
        # Install additional modules
        logger.info(f"Installing modules: {', '.join(modules)}")
        for module in modules:
            try:
                module_ids = models.execute_kw(
                    db_name, uid, password,
                    'ir.module.module', 'search',
                    [[['name', '=', module], ['state', '!=', 'installed']]]
                )
                if module_ids:
                    models.execute_kw(
                        db_name, uid, password,
                        'ir.module.module', 'button_immediate_install',
                        [module_ids]
                    )
                    logger.info(f"Module {module} installed successfully")
                else:
                    logger.info(f"Module {module} already installed or not found")
            except Exception as e:
                logger.warning(f"Failed to install module {module}: {str(e)}")
                error_tracker.log_error(e, {'database_name': db_name, 'module': module})
        
        # Set company logo
        company_id = 1
        logo_path = os.path.join('static', 'img', 'kdoo-logo.png')
        try:
            with open(logo_path, 'rb') as logo_file:
                logo_data = logo_file.read()
                logo_base64 = base64.b64encode(logo_data).decode('utf-8')
                models.execute_kw(
                    db_name, uid, password,
                    'res.company', 'write',
                    [[company_id], {'logo': logo_base64}]
                )
                logger.info(f"Company logo set for database {db_name} from {logo_path}")
        except FileNotFoundError:
            logger.error(f"Logo file not found at {logo_path}")
            error_tracker.log_error(FileNotFoundError(f"Logo file not found at {logo_path}"), {'database_name': db_name})
        except Exception as e:
            logger.error(f"Failed to set company logo for {db_name}: {str(e)}")
            error_tracker.log_error(e, {'database_name': db_name, 'function': 'set_company_logo'})
        
        # Helper function to check if field exists
        def check_field_exists(model, field):
            try:
                fields = models.execute_kw(
                    db_name, uid, password,
                    'ir.model.fields', 'search',
                    [[['model', '=', model], ['name', '=', field]]]
                )
                return bool(fields)
            except Exception as e:
                logger.warning(f"Failed to check field {field} in {model}: {str(e)}")
                return False
        
        # Initialize SaaS user limit configuration
        try:
            # Get tenant from database name
            if db_name.startswith('kdoo_'):
                subdomain = db_name[5:]  # Remove 'kdoo_' prefix
                tenant = None
                with app.app_context():
                    tenant = Tenant.query.filter_by(subdomain=subdomain).first()
                
                if tenant:
                    # Get max_users from tenant plan
                    plan = SubscriptionPlan.query.filter_by(name=tenant.plan).first()
                    max_users = plan.max_users if plan else tenant.max_users or 10
                    
                    # Create or update SaaS config in Odoo
                    try:
                        # Check if saas.controller model exists (should be installed with saas_controller module)
                        model_exists = models.execute_kw(
                            db_name, uid, password,
                            'ir.model', 'search',
                            [[['model', '=', 'saas.controller']]]
                        )
                        
                        if model_exists:
                            # Create SaaS controller configuration
                            config_id = models.execute_kw(
                                db_name, uid, password,
                                'saas.controller', 'create',
                                [{
                                    'database_name': db_name,
                                    'max_users': max_users,
                                    'saas_manager_url': 'http://saas_manager:8000'
                                }]
                            )
                            logger.info(f"Created SaaS controller config for {db_name} with max_users: {max_users}")
                        else:
                            logger.warning(f"saas.controller model not found in {db_name}, user limits may not be enforced")
                    except Exception as config_error:
                        logger.warning(f"Failed to create SaaS controller config for {db_name}: {config_error}")
                else:
                    logger.warning(f"Tenant not found for database {db_name}")
        except Exception as saas_config_error:
            logger.warning(f"Failed to initialize SaaS user limit config for {db_name}: {saas_config_error}")
        
        logger.info("Odoo Database created successfully.")

        # Disable signup
        try:
            signup_field = 'auth_signup_uninvited'
            version_info = common.version()
            odoo_version = version_info.get('server_version', '')
            if odoo_version.startswith('15') or odoo_version.startswith('16'):
                signup_field = 'auth_signup.allow_uninvited'
            
            if check_field_exists('res.config.settings', signup_field):
                settings_id = models.execute_kw(
                    db_name, uid, password,
                    'res.config.settings', 'create',
                    [{signup_field: 'b2b' if signup_field == 'auth_signup_uninvited' else False}]
                )
                models.execute_kw(
                    db_name, uid, password,
                    'res.config.settings', 'execute',
                    [[settings_id]]
                )
                logger.info(f"Disabled 'Create Account' for database {db_name} using field {signup_field}")
            else:
                logger.warning(f"Field {signup_field} not found in res.config.settings for {db_name}, skipping signup disable")
        except xmlrpc.client.Fault as e:
            logger.warning(f"Failed to disable signup for {db_name}: {str(e)}")
            error_tracker.log_error(e, {'database_name': db_name, 'function': 'disable_signup'})
            
        logger.info("Signup disabled for Odoo database.")
        # Set primary color if web_debranding module is available
        try:
            module_ids = models.execute_kw(
                db_name, uid, password,
                'ir.module.module', 'search',
                [[['name', '=', 'web_debranding'], ['state', '=', 'installed']]]
            )
            if module_ids and check_field_exists('res.config.settings', 'web_debranding.primary_color'):
                settings_id = models.execute_kw(
                    db_name, uid, password,
                    'res.config.settings', 'create',
                    [{'web_debranding.primary_color': '#005B8C'}]
                )
                models.execute_kw(
                    db_name, uid, password,
                    'res.config.settings', 'execute',
                    [[settings_id]]
                )
                logger.info(f"Primary color set to #005B8C for database {db_name}")
            else:
                logger.info(f"web_debranding module or primary_color field not found, skipping primary color setting for {db_name}")
        except Exception as e:
            logger.warning(f"Failed to set primary color for {db_name}: {str(e)}")
            error_tracker.log_error(e, {'database_name': db_name, 'function': 'set_primary_color'})
        
        logger.info("Odoo Database created.")

        # UPDATE TENANT STATUS TO ACTIVE after successful database creation
        try:
            from models import Tenant
            from flask import current_app
            app_to_use = app if app else current_app
            
            # Create application context for background thread
            with app_to_use.app_context():
                tenant = Tenant.query.filter_by(database_name=db_name).first()
                if tenant:
                    tenant.status = 'active'  # Change from 'creating' to 'active'
                    tenant.is_active = True  # Ensure is_active is also set
                    db.session.commit()
                    logger.info(f"Updated tenant {tenant.id} status to active after successful database creation")
                    
                    # Invalidate cache to ensure frontend shows updated status immediately
                    try:
                        invalidate_tenant_cache(tenant.id)
                        logger.info(f"Invalidated cache for tenant {tenant.id} after status change")
                    except Exception as cache_error:
                        logger.warning(f"Failed to invalidate cache for tenant {tenant.id}: {cache_error}")
                    
                    # Create billing cycle immediately for newly activated tenant
                    try:
                        billing_service = BillingService()
                        billing_cycle = billing_service.create_billing_cycle(tenant.id)
                        logger.info(f"Created initial billing cycle for tenant {tenant.id}: {billing_cycle.id}")
                    except Exception as billing_error:
                        logger.error(f"Failed to create billing cycle for tenant {tenant.id}: {billing_error}")
                        # Don't fail tenant activation for billing cycle creation error
                        error_tracker.log_error(billing_error, {'tenant_id': tenant.id, 'function': 'create_initial_billing_cycle'})
                    
                    # Trigger real-time update (also needs app context)
                    try:
                        tenant_users = TenantUser.query.filter_by(tenant_id=tenant.id).all()
                        user_ids = [tu.user_id for tu in tenant_users]
                        
                        tenant_data = {
                            'id': tenant.id,
                            'name': tenant.name,
                            'subdomain': tenant.subdomain,
                            'status': 'active'
                        }
                        
                        update_trigger.tenant_status_changed(tenant_data, user_ids)
                        
                    except Exception as cache_error:
                        logger.warning(f"Failed to update cache after tenant activation: {cache_error}")
                else:
                    logger.error(f"Could not find tenant with database_name {db_name} to update status")
                
                # Trigger real-time update
                try:
                    tenant_users = TenantUser.query.filter_by(tenant_id=tenant.id).all()
                    user_ids = [tu.user_id for tu in tenant_users]
                    
                    tenant_data = {
                        'id': tenant.id,
                        'name': tenant.name,
                        'subdomain': tenant.subdomain,
                        'status': 'active'
                    }
                    
                    update_trigger.tenant_status_changed(tenant_data, user_ids)
                    
                except Exception as cache_error:
                    logger.warning(f"Failed to update cache after tenant activation: {cache_error}")
                    
                
        except Exception as e:
            logger.error(f"Failed to update tenant status to active: {e}")
            error_tracker.log_error(e, {'database_name': db_name, 'function': 'update_tenant_status'})
            # Don't fail the entire process for this error
        
        logger.info(f"Database {db_name} created and configured successfully - Tenant is now ACTIVE")
        return True
    
    except requests.exceptions.Timeout:
        logger.error(f"Database creation timed out for {db_name}")
        error_tracker.log_error(Exception("Database creation timeout"), {'database_name': db_name})
        # Import the function from billing module
        from billing import _update_tenant_status_to_failed
        _update_tenant_status_to_failed(db_name, "Database creation timed out", app)
        return False
        
    except Exception as e:
        logger.error(f"Error creating database {db_name}: {str(e)}")
        error_tracker.log_error(e, {'database_name': db_name})
        # Import the function from billing module
        from billing import _update_tenant_status_to_failed
        _update_tenant_status_to_failed(db_name, f"Database creation error: {str(e)}", app)
        return False






@track_errors('odoo_user_credentials_update')
def update_odoo_user_credentials(database_name, current_username, current_password, new_username, new_password):
    try:
        if not database_name.startswith('kdoo_'):
            raise ValueError(f"Invalid database name: {database_name}. Must start with 'kdoo_'")
        subdomain = database_name[len('kdoo_'):]
        
        odoo_url = os.environ.get('ODOO_MASTER_URL', 'http://odoo_master:8069')
        common = xmlrpc.client.ServerProxy(f'{odoo_url}/xmlrpc/2/common')
        uid = common.authenticate(database_name, current_username, current_password, {})
        
        if not uid:
            logger.error(f"Authentication failed for database {database_name} with username {current_username}")
            return False
        
        models = xmlrpc.client.ServerProxy(f'{odoo_url}/xmlrpc/2/object')
        user_ids = models.execute_kw(
            database_name, uid, current_password,
            'res.users', 'search',
            [[('login', '=', current_username)]]
        )
        if not user_ids:
            logger.error(f"User '{current_username}' not found in database {database_name}")
            return False
        
        user_id = user_ids[0]
        models.execute_kw(
            database_name, uid, current_password,
            'res.users', 'write',
            [[user_id], {'login': new_username, 'password': new_password}]
        )
        
        logger.info(f"Credentials updated for '{current_username}' to '{new_username}' in database {database_name}")
        return True
    
    except xmlrpc.client.Fault as e:
        logger.error(f"XML-RPC error: {e.faultCode} - {e.faultString}")
        return False
    except Exception as e:
        logger.error(f"Failed to update credentials for {database_name}: {str(e)}")
        return False

@track_errors('worker_selection')
def get_available_worker():
    try:
        if not docker_client:
            logger.warning("Docker client not available - using mock worker")
            return WorkerInstance.query.first()
        
        docker_client.ping()
        workers = WorkerInstance.query.filter_by(status='running').all()
        if not workers:
            logger.warning("No running workers found")
            return None
        
        available_worker = min(workers, key=lambda w: w.current_tenants)
        if available_worker.current_tenants < available_worker.max_tenants:
            return available_worker
        
        logger.warning("All workers at capacity")
        return None
        
    except docker.errors.APIError as e:
        error_tracker.log_error(e, {'docker_operation': 'ping'})
        return WorkerInstance.query.first()
    except Exception as e:
        error_tracker.log_error(e, {'function': 'get_available_worker'})
        return None

@app.route('/favicon.ico')
@track_errors('serve_favicon')
def favicon():
    return send_file(os.path.join('static', 'img', 'favicon.ico'))

@app.route('/pwa-worker.js')
@track_errors('serve_service_worker')
def serve_service_worker():
    return send_file(os.path.join('static', 'js', 'pwa-worker.js'), mimetype='application/javascript')


@app.route('/sw.js')
@track_errors('serve_sw_js')
def serve_sw_js():
    """Serve the main service worker file"""
    response = make_response(send_file(os.path.join('static', 'js', 'sw.js'), mimetype='application/javascript'))
    # Add headers for proper service worker caching
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/robots.txt')
@track_errors('serve_robots')
def serve_robots():
    """Serve robots.txt for SEO"""
    robots_content = """User-agent: *
Allow: /login
Allow: /register
Disallow: /admin/
Disallow: /api/
Disallow: /tenant/*/manage
Disallow: /billing/

Sitemap: {}/sitemap.xml
""".format(request.url_root.rstrip('/'))
    
    response = make_response(robots_content)
    response.headers['Content-Type'] = 'text/plain'
    return response

@app.route('/sitemap.xml')
@track_errors('serve_sitemap')
def serve_sitemap():
    """Serve sitemap for SEO"""
    sitemap_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>{request.url_root.rstrip('/')}/</loc>
        <changefreq>weekly</changefreq>
        <priority>1.0</priority>
    </url>
    <url>
        <loc>{request.url_root.rstrip('/')}/login</loc>
        <changefreq>monthly</changefreq>
        <priority>0.8</priority>
    </url>
    <url>
        <loc>{request.url_root.rstrip('/')}/register</loc>
        <changefreq>monthly</changefreq>
        <priority>0.8</priority>
    </url>
</urlset>"""
    
    response = make_response(sitemap_content)
    response.headers['Content-Type'] = 'application/xml'
    return response

@app.route('/static/browserconfig.xml')
@track_errors('serve_browserconfig')
def serve_browserconfig():
    """Serve browserconfig.xml for Windows tiles"""
    return send_file(os.path.join('static', 'browserconfig.xml'), mimetype='application/xml')

# Add PWA-specific headers to key routes
@app.after_request
def add_pwa_headers(response):
    """Add PWA-friendly headers"""
    # Add security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    # Add HTTPS redirect header for production
    if not app.debug and request.headers.get('X-Forwarded-Proto') != 'https':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    
    # Add cache headers for static assets
    if request.endpoint == 'static':
        response.headers['Cache-Control'] = 'public, max-age=31536000'  # 1 year
    elif request.endpoint in ['serve_manifest', 'serve_sw_js']:
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    
    return response


@app.route('/offline.html')
@track_errors('serve_offline_page')
def serve_offline_page():
    return send_file('./templates/offline.html')

@app.route('/manifest.json')
@track_errors('serve_manifest')
def serve_manifest():
    return send_file(os.path.join('static', 'manifest.json'), mimetype='application/manifest+json')

@app.route('/')
@track_errors('index_route')
def index():
    """Homepage"""
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
@track_errors('login_route')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    form = LoginForm()
    if form.validate_on_submit():
        try:
            # Try to find user by username or email
            username_or_email = form.username.data
            user = SaasUser.query.filter(
                (SaasUser.username == username_or_email) | 
                (SaasUser.email == username_or_email)
            ).first()
            if user and check_password_hash(user.password_hash, form.password.data) and user.is_active:
                login_user(user)
                user.last_login = datetime.utcnow()
                db.session.commit()
                flash('Logged in successfully!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid username or password.', 'error')
        except Exception as e:
            error_tracker.log_error(e, {'username': form.username.data, 'form_errors': form.errors})
            flash('Login error occurred. Please try again.', 'error')
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
@track_errors('register_route')
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        try:
            if SaasUser.query.filter_by(username=form.username.data).first():
                flash('Username already exists.', 'error')
                return render_template('register.html', form=form)
            if SaasUser.query.filter_by(email=form.email.data).first():
                flash('Email already exists.', 'error')
                return render_template('register.html', form=form)
            
            user = SaasUser(
                username=form.username.data,
                email=form.email.data,
                password_hash=generate_password_hash(form.password.data)
            )
            db.session.add(user)
            db.session.commit()
            
            try:
                update_trigger.user_stats_changed()
            except Exception as e:
                logger.warning(f"Failed to update user stats cache: {e}")
            
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            error_tracker.log_error(e, {'username': form.username.data, 'email': form.email.data, 'form_errors': form.errors})
            flash('Registration error occurred. Please try again.', 'error')
    return render_template('register.html', form=form)

@app.route('/logout')
@login_required
@track_errors('logout_route')
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/forgot-password', methods=['GET', 'POST'])
@track_errors('forgot_password_route')
def forgot_password():
    """Handle forgot password requests"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        try:
            user = SaasUser.query.filter_by(email=form.email.data).first()
            if user:
                # Generate reset token
                token = user.generate_reset_token()
                db.session.commit()
                
                # Send reset email using EmailManager
                try:
                    from email_config import EmailManager
                    success, message = EmailManager.send_password_reset_email(user, token)
                    
                    if success:
                        flash('Password reset instructions have been sent to your email.', 'success')
                    else:
                        flash(f'Failed to send reset email: {message}. Please contact administrator.', 'error')
                        # Fallback: show reset link for demo purposes
                        reset_url = url_for('reset_password', token=token, _external=True)
                        flash(f'For demo purposes, use this link: {reset_url}', 'info')
                        
                except Exception as email_error:
                    error_tracker.log_error(email_error, {'email': user.email, 'context': 'password_reset_email'})
                    # Fallback: show reset link for demo purposes
                    reset_url = url_for('reset_password', token=token, _external=True)
                    flash(f'Email service unavailable. For demo purposes, use this link: {reset_url}', 'info')
                
                # Log the password reset request
                from models import AuditLog
                audit_log = AuditLog(
                    user_id=user.id,
                    action='password_reset_requested',
                    details={'email': user.email}
                )
                db.session.add(audit_log)
                db.session.commit()
                
            else:
                # Don't reveal whether email exists or not
                flash('If your email is registered, you will receive reset instructions.', 'info')
                
            return redirect(url_for('login'))
            
        except Exception as e:
            error_tracker.log_error(e, {'email': form.email.data})
            flash('An error occurred. Please try again.', 'error')
    
    return render_template('forgot_password.html', form=form)

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
@track_errors('reset_password_route')
def reset_password(token):
    """Handle password reset with token"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    # Find user with valid token
    user = SaasUser.query.filter_by(reset_token=token).first()
    if not user or not user.verify_reset_token(token):
        flash('Invalid or expired reset token. Please request a new one.', 'error')
        return redirect(url_for('forgot_password'))
    
    form = ResetPasswordForm()
    if form.validate_on_submit():
        try:
            # Update password
            user.password_hash = generate_password_hash(form.password.data)
            user.last_password_change = datetime.utcnow()
            user.clear_reset_token()
            db.session.commit()
            
            # Log the password reset
            audit_log = AuditLog(
                user_id=user.id,
                action='password_reset_completed',
                details={'email': user.email}
            )
            db.session.add(audit_log)
            db.session.commit()
            
            flash('Your password has been reset successfully. Please log in.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            error_tracker.log_error(e, {'user_id': user.id})
            flash('An error occurred while resetting your password. Please try again.', 'error')
    
    return render_template('reset_password.html', form=form, token=token)

@app.route('/dashboard')
@login_required
@track_errors('enhanced_dashboard_route')
def dashboard():
    try:
        user_tenants = cache_manager.get_user_tenants(current_user.id)
        
        # Enhance tenants with billing information
        enhanced_tenants = []
        from billing_service import BillingService
        billing_service = BillingService()
        
        for tenant_data in user_tenants:
            # Get billing information for each tenant
            billing_info = billing_service.get_tenant_billing_info(tenant_data['id'])
            
            # Add billing information to tenant data
            if billing_info and billing_info.get('status') != 'no_active_cycle':
                tenant_data.update({
                    'billing_info': billing_info,
                    'is_expired': billing_info.get('is_expired', False),
                    'days_remaining': billing_info.get('days_remaining', 0),
                    'hours_remaining': billing_info.get('hours_remaining', 0),
                    'requires_payment': billing_info.get('requires_payment', False),
                    'can_renew_early': billing_info.get('can_renew_early', False)
                })
            else:
                # No active billing cycle
                tenant_data.update({
                    'billing_info': None,
                    'is_expired': True,
                    'days_remaining': 0,
                    'hours_remaining': 0,
                    'requires_payment': True,
                    'can_renew_early': False
                })
            
            enhanced_tenants.append(tenant_data)
        
        stats = {}
        
        # Check for pending registration
        pending_registration = None
        if session.get('registration_completed'):
            tenant_id = session.get('pending_tenant_id')
            if tenant_id:
                tenant = Tenant.query.get(tenant_id)
                if tenant and tenant.status in ['pending', 'creating']:
                    transaction = PaymentTransaction.query.filter_by(
                        tenant_id=tenant_id,
                        user_id=current_user.id
                    ).order_by(PaymentTransaction.created_at.desc()).first()
                    
                    pending_registration = {
                        'tenant': tenant,
                        'transaction': transaction,
                        'show_status': True
                    }
        
        if current_user.is_admin:
            stats = cache_manager.get_admin_stats()
        
        # Get subscription plans for plan-based display
        plans = SubscriptionPlan.query.filter_by(is_active=True).all()
        plans_data = [
            {
                'name': plan.name,
                'max_users': plan.max_users,
                'storage_limit': plan.storage_limit,
                'price': plan.price
            }
            for plan in plans
        ]
            
        return render_template('dashboard.html', 
                             tenants=enhanced_tenants, 
                             stats=stats,
                             plans=plans_data,
                             pending_registration=pending_registration)
    except Exception as e:
        error_tracker.log_error(e, {'user_id': current_user.id})
        flash('Error loading dashboard. Please try again.', 'error')
        return render_template('dashboard.html', tenants=[], stats={}, plans=[])


@app.route('/tenant/create', methods=['GET', 'POST'])
@login_required
@track_errors('create_tenant_route')
def create_tenant():
    form = TenantForm()
    plans = SubscriptionPlan.query.filter_by(is_active=True).all()
    plans_data = [
        {
            'id': plan.id,
            'name': plan.name,
            'price': float(plan.price),
            'max_users': plan.max_users,
            'storage_limit': plan.storage_limit,
            'features': plan.features,
            'modules': plan.modules or [],
            'is_active': plan.is_active,
            'created_at': plan.created_at.isoformat()
        }
        for plan in plans
    ]
    if form.validate_on_submit():
        try:
            if Tenant.query.filter_by(subdomain=form.subdomain.data).first():
                flash('Subdomain already exists.', 'error')
                return render_template('create_tenant.html', form=form, plans=plans_data)
            
            worker = get_available_worker()
            if not worker:
                flash('No available worker instances. Please try again later.', 'error')
                return render_template('create_tenant.html', form=form, plans=plans_data)
            
            db_name = f"kdoo_{form.subdomain.data}"
            admin_username = f"admin_{form.subdomain.data}"
            admin_password = generate_secure_password()
            
            # Create tenant record with pending status - NO DATABASE CREATION YET
            tenant = Tenant(
                name=form.name.data,
                subdomain=form.subdomain.data,
                database_name=db_name,
                plan=form.plan.data,
                admin_username=admin_username,
                status='pending'  # Will change to 'creating' after payment, then 'active' after DB creation
            )
            tenant.set_admin_password(admin_password)
            
            db.session.add(tenant)
            db.session.flush()  # Get the tenant ID
            
            tenant_user = TenantUser(tenant_id=tenant.id, user_id=current_user.id, role='admin')
            db.session.add(tenant_user)
            worker.current_tenants += 1  # Will be decremented if payment fails
            db.session.commit()

            try:
                # Prepare tenant data for broadcast
                tenant_data = {
                    'id': tenant.id,
                    'name': tenant.name,
                    'subdomain': tenant.subdomain,
                    'status': tenant.status,
                    'plan': tenant.plan
                }
                
                # Trigger cache updates and real-time notifications
                update_trigger.tenant_created(tenant_data, [current_user.id])
                
            except Exception as e:
                logger.warning(f"Failed to update cache after tenant creation: {e}")
            
            # Redirect to payment - database will be created ONLY after successful payment
            payment_url = BillingService.initiate_payment(tenant_id=tenant.id, user_id=current_user.id, plan=tenant.plan)
            return redirect(payment_url)
            
        except Exception as e:
            db.session.rollback()
            error_tracker.log_error(e, {
                'tenant_name': form.name.data,
                'subdomain': form.subdomain.data,
                'plan': form.plan.data,
                'user_id': current_user.id
            })
            flash('Error creating tenant. Please try again.', 'error')
    return render_template('create_tenant.html', form=form, plans=plans_data)


@app.route('/tenant/<int:tenant_id>/manage')
@login_required
@track_errors('manage_tenant_route')
def manage_tenant(tenant_id):
    try:
        tenant_user = TenantUser.query.filter_by(tenant_id=tenant_id, user_id=current_user.id).first()
        if not tenant_user and not current_user.is_admin:
            flash('Access denied.', 'error')
            return redirect(url_for('dashboard'))
        
        tenant = Tenant.query.get_or_404(tenant_id)
        
        # Update database active status
        try:
            actual_db_status = odoo.is_active(tenant.database_name)
            if tenant.is_active != actual_db_status:
                tenant.is_active = actual_db_status
                db.session.add(tenant)
                db.session.commit()
                
                # Invalidate cache for this tenant
                tenant_users = TenantUser.query.filter_by(tenant_id=tenant.id).all()
                user_ids = [tu.user_id for tu in tenant_users]
                cache_manager.invalidate_user_tenants_cache(user_ids)
                cache_manager.invalidate_admin_stats_cache()
        except Exception as e:
            logger.warning(f"Could not check database status for {tenant.database_name}: {e}")
        
        # Handle pending tenants without databases
        if tenant.status == 'pending':
            modules = 0
            storage_usage = '0 B'
            uptime = 'N/A'
            odoo_user = 0
        else:
            modules = odoo.get_installed_applications_count(tenant.database_name, tenant.admin_username, tenant.get_admin_password())
            storage_usage = odoo.get_database_storage_usage(tenant.database_name)['total_size_human']
            uptime = odoo.get_tenant_uptime(tenant.database_name)['uptime_human']
            odoo_user = odoo.get_users_count(tenant.database_name, tenant.admin_username, tenant.get_admin_password())['total_users']
        
        # Get available subscription plans for the edit modal
        plans = SubscriptionPlan.query.filter_by(is_active=True).all()
        plans_data = [
            {
                'name': plan.name,
                'display_name': plan.name.capitalize(),
                'price': plan.price,
                'max_users': plan.max_users,
                'storage_limit': plan.storage_limit,
                'features': plan.features or []
            }
            for plan in plans
        ]
        
        # Get billing information
        from billing_service import BillingService
        billing_service = BillingService()
        billing_info = billing_service.get_tenant_billing_info(tenant_id)
        
        return render_template('manage_tenant.html', 
                      tenant=tenant, 
                      modules=modules, 
                      storage_usage=storage_usage, 
                      uptime=uptime, 
                      odoo_user=odoo_user-1,
                      plans=plans_data,
                      tenant_id=tenant_id,
                      billing_info=billing_info)
    except Exception as e:
        error_tracker.log_error(e, {'tenant_id': tenant_id, 'user_id': current_user.id})
        flash('Error accessing tenant. Please try again.', 'error')
        return redirect(url_for('dashboard'))

@app.route('/admin/tenants')
@admin_required
@track_errors('admin_tenants_route')
def admin_tenants():
    show_deleted = request.args.get('show_deleted', 'false').lower() == 'true'
    try:
        if show_deleted:
            tenants = Tenant.query.all()  # Show all including deleted
        else:
            tenants = Tenant.query.filter(Tenant.status != 'deleted').all()  # Show only active
        
        # Update database active status for all tenants
        updated_tenants = []
        for tenant in tenants:
            try:
                actual_db_status = odoo.is_active(tenant.database_name)
                if tenant.is_active != actual_db_status:
                    tenant.is_active = actual_db_status
                    db.session.add(tenant)
                    updated_tenants.append(tenant.id)
            except Exception as e:
                logger.warning(f"Could not check database status for {tenant.database_name}: {e}")
        
        db.session.commit()
        
        # Invalidate cache for updated tenants
        if updated_tenants:
            cache_manager.invalidate_admin_stats_cache()
            # Invalidate user caches for affected tenants
            for tenant_id in updated_tenants:
                tenant_users = TenantUser.query.filter_by(tenant_id=tenant_id).all()
                user_ids = [tu.user_id for tu in tenant_users]
                cache_manager.invalidate_user_tenants_cache(user_ids)
        
        return render_template('admin_tenants.html', tenants=tenants)
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        flash('Error loading tenants. Please try again.', 'error')
        return render_template('admin_tenants.html', tenants=[])

@app.route('/admin/users')
@admin_required
@track_errors('admin_users_route')
def admin_users():
    try:
        users = SaasUser.query.all()
        return render_template('admin_users.html', users=users)
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        flash('Error loading users. Please try again.', 'error')
        return render_template('admin_users.html', users=[])

@app.route('/admin/workers')
@admin_required
@track_errors('admin_workers_route')
def admin_workers():
    try:
        workers = WorkerInstance.query.all()
        return render_template('admin_workers.html', workers=workers)
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        flash('Error loading workers. Please try again.', 'error')
        return render_template('admin_workers.html', workers=[])

@app.route('/admin/errors')
@admin_required
@track_errors('admin_errors_route')
def admin_errors():
    try:
        if not redis_client:
            return render_template('admin_errors.html', errors=[])
        errors = redis_client.lrange('recent_errors', 0, -1)
        error_list = [json.loads(e.decode('utf-8')) for e in errors]
        return render_template('admin_errors.html', errors=error_list)
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        flash('Error loading recent errors. Please try again.', 'error')
        return render_template('admin_errors.html', errors=[])

@app.route('/health')
@track_errors('health_check')
def health():
    try:
        db.session.execute(text('SELECT 1'))
        db_status = 'healthy'
    except Exception as e:
        db_status = 'unhealthy'
    
    redis_status = 'not_available'
    if redis_client:
        try:
            redis_client.ping()
            redis_status = 'healthy'
        except Exception as e:
            redis_status = 'unhealthy'
    
    return jsonify({
        'status': 'healthy' if db_status == 'healthy' and redis_status == 'healthy' else 'unhealthy',
        'services': {
            'database': db_status,
            'redis': redis_status,
            'docker': 'available' if docker_client else 'not_available'
        }
    })

@track_errors('password_generation')
def generate_secure_password(length=12):
    try:
        lowercase = string.ascii_lowercase
        uppercase = string.ascii_uppercase
        digits = string.digits
        special_chars = "!@#$%^&*"
        
        password = [
            secrets.choice(lowercase),
            secrets.choice(uppercase),
            secrets.choice(digits),
            secrets.choice(special_chars)
        ]
        
        all_chars = lowercase + uppercase + digits + special_chars
        for _ in range(length - 4):
            password.append(secrets.choice(all_chars))
        
        secrets.SystemRandom().shuffle(password)
        return ''.join(password)
    except Exception as e:
        error_tracker.log_error(e, {'function': 'generate_secure_password', 'length': length})
        return secrets.token_urlsafe(length)[:length]

@track_errors('tenant_access_verification')
def verify_tenant_access(user_id, tenant_id):
    try:
        user = SaasUser.query.get(user_id)
        if user and user.is_admin:
            return True
        tenant_user = TenantUser.query.filter_by(tenant_id=tenant_id, user_id=user_id).first()
        return tenant_user is not None
    except Exception as e:
        error_tracker.log_error(e, {'user_id': user_id, 'tenant_id': tenant_id, 'function': 'verify_tenant_access'})
        return False

@track_errors('odoo_session_creation')
def create_odoo_session(tenant_subdomain, username, password):
    try:
        domain = os.environ.get('DOMAIN', 'odoo-bangladesh.com')
        tenant_url = f"https://{tenant_subdomain}.{domain}"
        session = requests.Session()
        response = session.get(f"{tenant_url}/web/login")
        if response.status_code != 200:
            logger.error(f"Failed to access tenant login page: {response.status_code}")
            return None
        
        csrf_token = None
        if 'csrf_token' in response.text:
            csrf_match = re.search(r'csrf_token["\']:\s*["\']([^"\']+)["\']', response.text)
            if csrf_match:
                csrf_token = csrf_match.group(1)
        
        login_data = {'login': username, 'password': password, 'redirect': '/web'}
        if csrf_token:
            login_data['csrf_token'] = csrf_token
        
        login_response = session.post(f"{tenant_url}/web/login", data=login_data, allow_redirects=False)
        if login_response.status_code in [302, 303] and '/web' in login_response.headers.get('Location', ''):
            logger.info(f"Successfully created session for tenant: {tenant_subdomain}")
            return {'session_cookies': session.cookies.get_dict(), 'tenant_url': tenant_url, 'session_id': session.cookies.get('session_id'), 'success': True}
        elif login_response.status_code == 200 and ('/web' in login_response.url or 'database' not in login_response.text):
            return {'session_cookies': session.cookies.get_dict(), 'tenant_url': tenant_url, 'session_id': session.cookies.get('session_id'), 'success': True}
        
        logger.error(f"Login failed for tenant {tenant_subdomain}: Status {login_response.status_code}")
        return None
    except requests.exceptions.RequestException as e:
        error_tracker.log_error(e, {'tenant_subdomain': tenant_subdomain, 'username': username, 'function': 'create_odoo_session', 'error_type': 'request_exception'})
        return None
    except Exception as e:
        error_tracker.log_error(e, {'tenant_subdomain': tenant_subdomain, 'username': username, 'function': 'create_odoo_session'})
        return None

@track_errors('odoo_xmlrpc_auth')
def authenticate_odoo_xmlrpc(tenant_subdomain, username, password, database_name):
    try:
        domain = os.environ.get('DOMAIN', 'odoo-bangladesh.com')
        tenant_url = f"https://{tenant_subdomain}.{domain}"
        common = xmlrpc.client.ServerProxy(f'{tenant_url}/xmlrpc/2/common')
        version_info = common.version()
        logger.info(f"Odoo version for {tenant_subdomain}: {version_info}")
        uid = common.authenticate(database_name, username, password, {})
        if uid:
            logger.info(f"XML-RPC authentication successful for {tenant_subdomain}, UID: {uid}")
            return {'uid': uid, 'tenant_url': tenant_url, 'database': database_name, 'success': True}
        else:
            logger.error(f"XML-RPC authentication failed for {tenant_subdomain}")
            return None
    except xmlrpc.client.Fault as e:
        error_tracker.log_error(e, {'tenant_subdomain': tenant_subdomain, 'username': username, 'database_name': database_name, 'xmlrpc_fault_code': e.faultCode, 'xmlrpc_fault_string': e.faultString})
        return None
    except Exception as e:
        error_tracker.log_error(e, {'tenant_subdomain': tenant_subdomain, 'username': username, 'database_name': database_name, 'function': 'authenticate_odoo_xmlrpc'})
        return None

@track_errors('session_cookie_creation')
def create_session_response(session_data, target_url):
    try:
        if not session_data or not session_data.get('success'):
            return None
        response = make_response(redirect(target_url))
        cookies = session_data.get('session_cookies', {})
        for cookie_name, cookie_value in cookies.items():
            domain = os.environ.get('DOMAIN', 'odoo-bangladesh.com')
            response.set_cookie(
                cookie_name,
                cookie_value,
                domain=f".{domain}",
                httponly=True,
                secure=False,
                samesite='Lax',
                max_age=3600 * 24
            )
        logger.info(f"Created session response with {len(cookies)} cookies")
        return response
    except Exception as e:
        error_tracker.log_error(e, {'session_data': str(session_data)[:200], 'target_url': target_url, 'function': 'create_session_response'})
        return None

@track_errors('tenant_health_check')
def check_tenant_health(tenant_subdomain):
    try:
        domain = os.environ.get('DOMAIN', 'odoo-bangladesh.com')
        tenant_url = f"https://{tenant_subdomain}.{domain}"
        response = requests.get(f"{tenant_url}/web/health", timeout=10)
        if response.status_code == 200:
            return {'healthy': True, 'status_code': response.status_code, 'response_time': response.elapsed.total_seconds()}
        else:
            return {'healthy': False, 'status_code': response.status_code, 'error': f"HTTP {response.status_code}"}
    except requests.exceptions.Timeout:
        return {'healthy': False, 'error': 'Connection timeout'}
    except requests.exceptions.ConnectionError:
        return {'healthy': False, 'error': 'Connection failed'}
    except Exception as e:
        error_tracker.log_error(e, {'tenant_subdomain': tenant_subdomain, 'function': 'check_tenant_health'})
        return {'healthy': False, 'error': str(e)}

@track_errors('tenant_database_validation')
def validate_tenant_database(database_name):
    try:
        conn = psycopg2.connect(
            host=os.environ.get('POSTGRES_HOST', 'postgres'),
            port=os.environ.get('POSTGRES_PORT', '5432'),
            user=os.environ.get('POSTGRES_USER', 'odoo_master'),
            password=os.environ.get('POSTGRES_PASSWORD', 'secure_password_123'),
            database=database_name
        )
        cursor = conn.cursor()
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'res_users'
            );
        """)
        has_users_table = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return {'valid': has_users_table, 'database_name': database_name}
    except psycopg2.Error as e:
        error_tracker.log_error(e, {'database_name': database_name, 'postgres_error_code': e.pgcode if hasattr(e, 'pgcode') else None})
        return {'valid': False, 'error': str(e)}
    except Exception as e:
        error_tracker.log_error(e, {'database_name': database_name, 'function': 'validate_tenant_database'})
        return {'valid': False, 'error': str(e)}

@track_errors('get_tenant_by_subdomain')
def get_tenant_by_subdomain(subdomain):
    try:
        tenant = Tenant.query.filter_by(subdomain=subdomain).first()
        return tenant
    except Exception as e:
        error_tracker.log_error(e, {'subdomain': subdomain, 'function': 'get_tenant_by_subdomain'})
        return None

@track_errors('update_tenant_last_access')
def update_tenant_last_access(tenant_id):
    try:
        tenant = Tenant.query.get(tenant_id)
        if tenant:
            tenant.updated_at = datetime.utcnow()
            db.session.commit()
            return True
        return False
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'tenant_id': tenant_id, 'function': 'update_tenant_last_access'})
        return False

@app.route('/tenant/<subdomain>/auto-login')
@login_required
@limiter.limit("10 per minute") if redis_client else login_required
@track_errors('tenant_auto_login_route')
def tenant_auto_login(subdomain):
    try:
        tenant = get_tenant_by_subdomain(subdomain)
        if not tenant:
            flash('Tenant not found.', 'error')
            return redirect(url_for('dashboard'))
        
        if not verify_tenant_access(current_user.id, tenant.id):
            flash('Access denied to this tenant.', 'error')
            return redirect(url_for('dashboard'))
        
        if tenant.status != 'active':
            flash('Tenant is not active.', 'warning')
            return redirect(url_for('dashboard'))
        
        db_validation = validate_tenant_database(tenant.database_name)
        if not db_validation.get('valid'):
            flash('Tenant database is not accessible.', 'error')
            return redirect(url_for('dashboard'))
        
        health_check = check_tenant_health(subdomain)
        if not health_check.get('healthy'):
            flash('Tenant service is currently unavailable.', 'warning')
            return redirect(url_for('dashboard'))
        
        admin_username = tenant.admin_username
        admin_password_plain = tenant.get_admin_password()
        session_data = create_odoo_session(subdomain, admin_username, admin_password_plain)
        
        if session_data and session_data.get('success'):
            update_tenant_last_access(tenant.id)
            target_url = f"https://{subdomain}.{os.environ.get('DOMAIN', 'khudroo.com')}/web"
            response = create_session_response(session_data, target_url)
            if response:
                return response
            else:
                flash('Failed to create session. Please try again.', 'error')
        else:
            flash('Failed to authenticate with tenant. Please check tenant configuration.', 'error')
        return redirect(url_for('dashboard'))
    except Exception as e:
        error_tracker.log_error(e, {'subdomain': subdomain, 'user_id': current_user.id, 'function': 'tenant_auto_login'})
        flash('Error accessing tenant. Please try again.', 'error')
        return redirect(url_for('dashboard'))

@app.route('/api/user/public-key', methods=['POST'])
@login_required
@track_errors('store_public_key_route')
def store_public_key():
    try:
        data = request.get_json()
        public_key_pem = data.get('public_key')
        if not public_key_pem:
            return jsonify({'error': 'Public key is required'}), 400
        
        if not TenantCredentialService.validate_public_key(public_key_pem):
            return jsonify({'error': 'Invalid public key format'}), 400
        
        fingerprint = TenantCredentialService.generate_key_fingerprint(public_key_pem)
        UserPublicKey.query.filter_by(user_id=current_user.id).update({'is_active': False})
        user_key = UserPublicKey(user_id=current_user.id, public_key=public_key_pem, key_fingerprint=fingerprint, is_active=True)
        db.session.add(user_key)
        db.session.commit()
        return jsonify({'success': True, 'fingerprint': fingerprint, 'message': 'Public key stored successfully'})
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'user_id': current_user.id, 'function': 'store_public_key'})
        return jsonify({'error': 'Failed to store public key'}), 500

@app.route('/api/user/public-key/status')
@login_required
@track_errors('public_key_status_route')
def public_key_status():
    try:
        active_key = UserPublicKey.query.filter_by(user_id=current_user.id, is_active=True).first()
        return jsonify({
            'has_key': active_key is not None,
            'fingerprint': active_key.key_fingerprint if active_key else None,
            'created_at': active_key.created_at.isoformat() if active_key else None
        })
    except Exception as e:
        error_tracker.log_error(e, {'user_id': current_user.id, 'function': 'public_key_status'})
        return jsonify({'error': 'Failed to check key status'}), 500

@app.route('/api/tenant/<int:tenant_id>/encrypted-credentials')
@login_required
@track_errors('get_encrypted_credentials_route')
def get_encrypted_credentials(tenant_id):
    try:
        if not verify_tenant_access(current_user.id, tenant_id):
            return jsonify({'error': 'Access denied'}), 403
        
        user_key = UserPublicKey.query.filter_by(user_id=current_user.id, is_active=True).first()
        if not user_key:
            return jsonify({'error': 'No encryption key found. Please generate keys first.'}), 400
        
        tenant = Tenant.query.get_or_404(tenant_id)
        if tenant.status != 'active':
            return jsonify({'error': 'Tenant is not active'}), 400
        
        encrypted_credentials = TenantCredentialService.encrypt_credentials(user_key.public_key, tenant.admin_username, tenant.get_admin_password())
        if not encrypted_credentials:
            return jsonify({'error': 'Failed to encrypt credentials'}), 500
        
        access_log = CredentialAccess(user_id=current_user.id, tenant_id=tenant_id, ip_address=request.remote_addr, user_agent=str(request.user_agent), success=True)
        db.session.add(access_log)
        db.session.commit()
        return jsonify({
            'encrypted_credentials': encrypted_credentials,
            'tenant_id': tenant_id,
            'tenant_name': tenant.name,
            'subdomain': tenant.subdomain,
            'key_fingerprint': user_key.key_fingerprint
        })
    except Exception as e:
        try:
            access_log = CredentialAccess(user_id=current_user.id, tenant_id=tenant_id, ip_address=request.remote_addr, user_agent=str(request.user_agent), success=False)
            db.session.add(access_log)
            db.session.commit()
        except:
            pass
        error_tracker.log_error(e, {'user_id': current_user.id, 'tenant_id': tenant_id, 'function': 'get_encrypted_credentials'})
        return jsonify({'error': 'Failed to retrieve credentials'}), 500

@app.route('/api/tenant/<int:tenant_id>/access-logs')
@login_required
@track_errors('get_access_logs_route')
def get_access_logs(tenant_id):
    try:
        if not current_user.is_admin:
            tenant_user = TenantUser.query.filter_by(tenant_id=tenant_id, user_id=current_user.id, role='admin').first()
            if not tenant_user:
                return jsonify({'error': 'Access denied'}), 403
        
        logs = CredentialAccess.query.filter_by(tenant_id=tenant_id).order_by(CredentialAccess.accessed_at.desc()).limit(50).all()
        log_data = [{'user_id': log.user_id, 'username': log.user.username, 'accessed_at': log.accessed_at.isoformat(), 'ip_address': log.ip_address, 'success': log.success} for log in logs]
        return jsonify({'logs': log_data, 'total_count': len(log_data)})
    except Exception as e:
        error_tracker.log_error(e, {'user_id': current_user.id, 'tenant_id': tenant_id, 'function': 'get_access_logs'})
        return jsonify({'error': 'Failed to retrieve access logs'}), 500

@app.route('/api/user/rotate-keys', methods=['POST'])
@login_required
@track_errors('rotate_keys_route')
def rotate_keys():
    try:
        data = request.get_json()
        new_public_key = data.get('new_public_key')
        if not new_public_key:
            return jsonify({'error': 'New public key is required'}), 400
        
        if not TenantCredentialService.validate_public_key(new_public_key):
            return jsonify({'error': 'Invalid public key format'}), 400
        
        UserPublicKey.query.filter_by(user_id=current_user.id).update({'is_active': False})
        fingerprint = TenantCredentialService.generate_key_fingerprint(new_public_key)
        user_key = UserPublicKey(user_id=current_user.id, public_key=new_public_key, key_fingerprint=fingerprint, is_active=True)
        db.session.add(user_key)
        db.session.commit()
        return jsonify({'success': True, 'fingerprint': fingerprint, 'message': 'Keys rotated successfully'})
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'user_id': current_user.id, 'function': 'rotate_keys'})
        return jsonify({'error': 'Failed to rotate keys'}), 500

@app.route('/api/tenant/<int:tenant_id>/status')
@login_required
@track_errors('tenant_status_api')
def tenant_status(tenant_id):
    try:
        tenant = Tenant.query.get_or_404(tenant_id)
        tenant_user = TenantUser.query.filter_by(tenant_id=tenant_id, user_id=current_user.id).first()
        if not tenant_user and not current_user.is_admin:
            return jsonify({'error': 'Access denied'}), 403
        
        # Get billing information
        from billing_service import BillingService
        billing_service = BillingService()
        billing_info = billing_service.get_tenant_billing_info(tenant_id)
        
        # Prepare response data with billing information
        response_data = {
            'success': True,
            'id': tenant.id,
            'name': tenant.name,
            'subdomain': tenant.subdomain,
            'status': tenant.status,
            'is_active': tenant.is_active,
            'plan': tenant.plan,
            'created_at': tenant.created_at.isoformat() if tenant.created_at else None,
            'timestamp': datetime.utcnow().isoformat()  # Force cache invalidation
        }
        
        # Add billing information if available
        if billing_info and billing_info.get('status') != 'no_active_cycle':
            response_data.update({
                'hours_used': billing_info.get('hours_used', 0),
                'hours_remaining': billing_info.get('hours_remaining', 0),
                'days_remaining': billing_info.get('days_remaining', 0),
                'total_hours_allowed': billing_info.get('total_hours_allowed', 360),
                'billing_status': billing_info.get('status', 'unknown'),
                'is_expired': billing_info.get('is_expired', False),
                'requires_payment': billing_info.get('requires_payment', False)
            })
        else:
            # No active billing cycle - set defaults
            response_data.update({
                'hours_used': 0,
                'hours_remaining': 360,
                'days_remaining': 30,
                'total_hours_allowed': 360,
                'billing_status': 'no_active_cycle',
                'is_expired': True,  # No billing cycle means expired
                'requires_payment': True
            })
        
        # Create response with cache-busting headers
        response = jsonify(response_data)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        error_tracker.log_error(e, {'tenant_id': tenant_id, 'user_id': current_user.id})
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/tenant/<int:tenant_id>/creation_status')
@login_required
@track_errors('get_creation_status_route')
def get_creation_status(tenant_id):
    try:
        tenant = Tenant.query.get_or_404(tenant_id)
        if not verify_tenant_access(current_user.id, tenant.id):
            return jsonify({'error': 'Access denied'}), 403
        if not redis_client:
            return jsonify({'status': 'unknown'})
        cache_key = f"db_creation_status:{tenant.database_name}"
        status = redis_client.get(cache_key)
        if status:
            return jsonify({'status': status.decode('utf-8')})
        else:
            return jsonify({'status': 'unknown'})
    except Exception as e:
        error_tracker.log_error(e, {'tenant_id': tenant_id, 'user_id': current_user.id})
        return jsonify({'error': 'Failed to retrieve creation status'}), 500

@app.route('/api/tenant/<int:tenant_id>/logs', methods=['GET'])
@login_required
@track_errors('tenant_logs_route')
def get_tenant_logs(tenant_id):
    try:
        tenant_user = TenantUser.query.filter_by(tenant_id=tenant_id, user_id=current_user.id).first()
        if not tenant_user and not current_user.is_admin:
            logger.warning(f"Access denied for user {current_user.id} to tenant {tenant_id}")
            return jsonify({'error': 'Access denied'}), 403
        
        tenant = Tenant.query.get_or_404(tenant_id)
        logger.info(f"Retrieving logs for tenant {tenant_id}: {tenant.database_name}")
        log_manager = TenantLogManager(odoo, tenant.database_name)
        include_db_logs = request.args.get('include_db_logs', 'false').lower() == 'true'
        logs = log_manager.get_logs(db_name=tenant.database_name, hours=24, limit=1000)
        
        if include_db_logs:
            db_logs = log_manager.get_database_query_logs(db_name=tenant.database_name)
            logs.extend(db_logs)
            logs.sort(key=lambda x: x['timestamp'], reverse=True)
            logs = logs[:1000]
        
        formatted_logs = [{'id': idx + 1, 'timestamp': log['timestamp'].isoformat() if isinstance(log['timestamp'], datetime) else log['timestamp'], 'level': log['level'].lower(), 'service': log.get('service', 'odoo'), 'title': log.get('title', 'Log Entry'), 'message': log['message'], 'details': log.get('details', '')} for idx, log in enumerate(logs)]
        stats = {
            'total': len(formatted_logs),
            'error': len([log for log in formatted_logs if log['level'] == 'error']),
            'warning': len([log for log in formatted_logs if log['level'] == 'warning']),
            'info': len([log for log in formatted_logs if log['level'] == 'info']),
            'success': len([log for log in formatted_logs if log['level'] == 'success']),
            'last_update': datetime.utcnow().isoformat()
        }
        
        container_status = {}
        for key, name in log_manager.containers.items():
            try:
                container = log_manager.docker_client.containers.get(name)
                container_status[key] = {'name': name, 'status': container.status}
            except docker.errors.NotFound:
                container_status[key] = {'name': name, 'status': 'not_found'}
            except Exception as e:
                container_status[key] = {'name': name, 'status': f'error: {str(e)}'}
        
        debug_info = {
            'tenant_id': tenant_id,
            'database_name': tenant.database_name,
            'log_count': len(logs),
            'container_status': container_status
        }
        if current_user.is_admin:
            debug_info['available_tenants'] = log_manager.get_available_tenants(user_id=current_user.id, is_admin=True)
        else:
            debug_info['available_tenants'] = log_manager.get_available_tenants(user_id=current_user.id, is_admin=False)
        
        logger.info(f"Returning {len(formatted_logs)} logs for tenant {tenant_id}")
        return jsonify({'logs': formatted_logs, 'stats': stats, 'debug': debug_info})
    except Exception as e:
        error_tracker.log_error(e, {'tenant_id': tenant_id, 'user_id': current_user.id, 'function': 'get_tenant_logs'})
        logger.error(f"Failed to retrieve tenant logs for {tenant_id}: {e}")
        return jsonify({'error': 'Failed to retrieve tenant logs', 'details': str(e)}), 500

@app.route('/api/tenant/<int:tenant_id>/apps/available', methods=['GET'])
@login_required
@track_errors('get_available_apps_route')
def get_available_apps(tenant_id):
    try:
        tenant_user = TenantUser.query.filter_by(tenant_id=tenant_id, user_id=current_user.id).first()
        if not tenant_user and not current_user.is_admin:
            return jsonify({'error': 'Access denied'}), 403
        
        tenant = Tenant.query.get_or_404(tenant_id)
        available_apps = odoo.get_available_applications(tenant.database_name, tenant.admin_username, tenant.get_admin_password())
        return jsonify({'apps': available_apps, 'total_count': len(available_apps), 'tenant_id': tenant_id, 'timestamp': datetime.utcnow().isoformat()})
    except Exception as e:
        error_tracker.log_error(e, {'tenant_id': tenant_id, 'user_id': current_user.id, 'function': 'get_available_apps'})
        return jsonify({'error': 'Failed to retrieve available apps'}), 500

@app.route('/api/tenant/<int:tenant_id>/apps/installed', methods=['GET'])
@login_required
@track_errors('get_installed_apps_route')
def get_installed_apps(tenant_id):
    try:
        tenant_user = TenantUser.query.filter_by(tenant_id=tenant_id, user_id=current_user.id).first()
        if not tenant_user and not current_user.is_admin:
            return jsonify({'error': 'Access denied'}), 403
        
        tenant = Tenant.query.get_or_404(tenant_id)
        installed_apps = odoo.get_installed_applications(tenant.database_name, tenant.admin_username, tenant.get_admin_password())
        return jsonify({'apps': installed_apps, 'total_count': len(installed_apps), 'tenant_id': tenant_id, 'timestamp': datetime.utcnow().isoformat()})
    except Exception as e:
        error_tracker.log_error(e, {'tenant_id': tenant_id, 'user_id': current_user.id, 'function': 'get_installed_apps'})
        return jsonify({'error': 'Failed to retrieve installed apps'}), 500

@app.route('/tenant/<int:tenant_id>/toggle', methods=['POST'])
@login_required
@track_errors('toggle_tenant_route')
def toggle_tenant(tenant_id):
    tenant = Tenant.query.get_or_404(tenant_id)
    try:
        is_active = odoo.is_active(tenant.database_name)
        if is_active:
            odoo.deactivate(tenant.database_name)
            tenant.is_active = False
            db.session.commit()
            flash(f'Tenant {tenant.name} deactivated successfully.', 'success')
        else:
            odoo.activate(tenant.database_name)
            tenant.is_active = True
            db.session.commit()
            flash(f'Tenant {tenant.name} activated successfully.', 'success')
        
        try:
            tenant_users = TenantUser.query.filter_by(tenant_id=tenant.id).all()
            user_ids = [tu.user_id for tu in tenant_users]
            
            tenant_data = {
                'id': tenant.id,
                'name': tenant.name,
                'subdomain': tenant.subdomain,
                'status': 'active' if tenant.is_active else 'inactive'
            }
            
            update_trigger.tenant_status_changed(tenant_data, user_ids)
            
        except Exception as e:
            logger.warning(f"Failed to update cache after tenant toggle: {e}")
        
    except Exception as e:
        flash(f'Toggle failed: {e}', 'danger')
    return redirect(request.referrer)

@app.route('/tenant/<int:tenant_id>/restart', methods=['POST'])
def restart_tenant(tenant_id):
    tenant = Tenant.query.get_or_404(tenant_id)
    try:
        odoo.deactivate(tenant.database_name)
        odoo.activate(tenant.database_name)
        flash('Tenant restarted successfully.', 'success')
    except Exception as e:
        flash(f'Restart failed: {e}', 'danger')
    return redirect(request.referrer)

@app.route('/tenant/<int:tenant_id>/backup', methods=['POST'])
@login_required
@track_errors('backup_tenant_route')
def backup_tenant(tenant_id):
    tenant = Tenant.query.get_or_404(tenant_id)
    try:
        backup_path = odoo.backup(tenant.database_name)
        response = send_file(backup_path, as_attachment=True)
        flash(f'Backup created at {backup_path}', 'success')
        odoo.delete_backup(tenant.database_name)
        return response
    except Exception as e:
        flash(f'Backup failed: {e}', 'danger')
    return redirect(request.referrer)

@app.route('/tenant/<int:tenant_id>/restore', methods=['POST'])
@login_required
@track_errors('restore_tenant_route')
def restore_tenant(tenant_id):
    logger.info(f"🔄 RESTORE REQUEST STARTED - Tenant ID: {tenant_id}")
    logger.info(f"   - User: {current_user.username if current_user else 'Unknown'}")
    logger.info(f"   - IP: {request.remote_addr}")
    logger.info(f"   - User Agent: {request.headers.get('User-Agent', 'Unknown')}")
    logger.info(f"   - Referrer: {request.referrer}")
    
    tenant = Tenant.query.get_or_404(tenant_id)
    logger.info(f"   - Tenant Name: {tenant.name}")
    logger.info(f"   - Database Name: {tenant.database_name}")
    logger.info(f"   - Tenant Status: {tenant.status}")
    
    try:
        # Log form data
        logger.info(f"📝 FORM DATA ANALYSIS:")
        logger.info(f"   - Form keys: {list(request.form.keys())}")
        logger.info(f"   - Files keys: {list(request.files.keys())}")
        logger.info(f"   - CSRF token present: {'csrf_token' in request.form}")
        
        # Check if file was uploaded
        if 'backup_file' not in request.files:
            logger.error("❌ No backup_file in request.files")
            flash('No backup file selected', 'danger')
            return redirect(request.referrer)
        
        backup_file = request.files['backup_file']
        logger.info(f"📁 FILE UPLOAD ANALYSIS:")
        logger.info(f"   - Filename: {backup_file.filename}")
        logger.info(f"   - Content Type: {backup_file.content_type}")
        logger.info(f"   - Content Length: {backup_file.content_length}")
        
        if backup_file.filename == '' or not backup_file.filename.lower().endswith('.zip'):
            logger.error(f"❌ Invalid file: '{backup_file.filename}'")
            flash('Please select a valid ZIP backup file', 'danger')
            return redirect(request.referrer)
        
        # Create temporary file
        import tempfile
        import os
        
        logger.info("📦 Creating temporary file for backup...")
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_file:
            backup_file.save(temp_file.name)
            temp_file_path = temp_file.name
            
        file_size = os.path.getsize(temp_file_path)
        logger.info(f"   - Temp file path: {temp_file_path}")
        logger.info(f"   - File size: {file_size} bytes ({file_size/1024/1024:.2f} MB)")
        
        try:
            logger.info("🔄 Starting database restore process...")
            
            # Deactivate database first if active
            logger.info(f"🔍 Checking if database '{tenant.database_name}' is active...")
            if odoo.is_active(tenant.database_name):
                logger.info("   - Database is active, deactivating...")
                odoo.deactivate(tenant.database_name)
                logger.info("   ✅ Database deactivated")
            else:
                logger.info("   - Database is not active")
            
            # Delete existing database
            logger.info(f"🗑️ Deleting existing database '{tenant.database_name}'...")
            odoo.delete(tenant.database_name)
            logger.info("   ✅ Database deleted")
            
            # Restore from backup
            logger.info(f"🔄 Restoring database '{tenant.database_name}' from backup...")
            odoo.restore(temp_file_path, tenant.database_name)
            logger.info("   ✅ Database restored successfully")
            
            logger.info(f"🎉 RESTORE COMPLETED SUCCESSFULLY for tenant {tenant.name}")
            flash(f'Database {tenant.database_name} restored successfully', 'success')
            
        except Exception as restore_error:
            logger.error(f"❌ RESTORE PROCESS FAILED: {str(restore_error)}")
            logger.error(f"   - Error type: {type(restore_error).__name__}")
            logger.error(f"   - Error details: {restore_error}", exc_info=True)
            raise
            
        finally:
            # Clean up temporary file
            logger.info("🧹 Cleaning up temporary file...")
            try:
                os.unlink(temp_file_path)
                logger.info("   ✅ Temporary file deleted")
            except Exception as cleanup_error:
                logger.warning(f"   ⚠️ Failed to delete temp file: {cleanup_error}")
    
    except Exception as e:
        logger.error(f"❌ RESTORE ROUTE FAILED: {str(e)}")
        logger.error(f"   - Error type: {type(e).__name__}")
        logger.error(f"   - Full traceback:", exc_info=True)
        flash(f'Restore failed: {str(e)}', 'danger')
    
    logger.info(f"🔚 RESTORE REQUEST COMPLETED - Redirecting to: {request.referrer}")
    return redirect(request.referrer)

@app.route('/tenant/<int:tenant_id>/delete', methods=['POST'])
@login_required
@track_errors('delete_tenant_route')
def delete_tenant(tenant_id):
    tenant = Tenant.query.get_or_404(tenant_id)
    try:
        logger.info(f"Soft deleting tenant: {tenant.name} (ID: {tenant.id})")
        
        try:
            # Get affected users before deletion
            tenant_users = TenantUser.query.filter_by(tenant_id=tenant.id).all()
            user_ids = [tu.user_id for tu in tenant_users]
            
            tenant_data = {
                'id': tenant.id,
                'name': tenant.name,
                'subdomain': tenant.subdomain
            }
            
            # Trigger cache updates and real-time notifications
            update_trigger.tenant_deleted(tenant_data, user_ids)
            
        except Exception as e:
            logger.warning(f"Failed to update cache before tenant deletion: {e}")
        
        # Soft delete: Mark tenant as deleted instead of hard delete
        tenant.status = 'deleted'
        tenant.is_active = False
        tenant.updated_at = datetime.utcnow()
        
        # Keep TenantUser and CredentialAccess records for audit purposes
        # Just mark them as inactive if needed in the future
        
        db.session.commit()
        
        # Delete the Odoo database (this is still safe as data is backed up)
        try:
            odoo.delete(tenant.database_name)
            logger.info(f"Odoo database {tenant.database_name} deleted successfully")
        except Exception as e:
            logger.warning(f"Failed to delete Odoo database {tenant.database_name}: {e}")
        
        flash('Tenant archived successfully. All billing records preserved.', 'success')
        logger.info(f"Tenant {tenant.name} soft deleted successfully")
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Tenant deletion failed: {e}")
        flash(f'Deletion failed: {e}', 'danger')
    return redirect(url_for('dashboard'))



# Add this form class after your existing form classes
@track_errors('profile_form_validation')
class ProfileForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=50)])
    # email = StringField('Email', validators=[DataRequired(), email_validator])
    email = StringField('Email', validators=[DataRequired()])
    full_name = StringField('Full Name', validators=[Optional(), Length(max=100)])
    bio = TextAreaField('Bio', validators=[Optional(), Length(max=500)])
    company = StringField('Company', validators=[Optional(), Length(max=100)])
    location = StringField('Location', validators=[Optional(), Length(max=100)])
    website = StringField('Website', validators=[Optional(), Length(max=200)])
    timezone = SelectField('Timezone', choices=[], validators=[Optional()])
    language = SelectField('Language', choices=[
        ('en', 'English'),
        ('es', 'Spanish'),
        ('fr', 'French'),
        ('de', 'German'),
        ('zh', 'Chinese'),
        ('ja', 'Japanese'),
        ('ar', 'Arabic'),
    ], validators=[Optional()])
    current_password = PasswordField('Current Password', validators=[Optional()])
    new_password = PasswordField('New Password', validators=[
        Optional(), 
        Length(min=6, message='Password must be at least 6 characters long')
    ])
    confirm_password = PasswordField('Confirm New Password', validators=[
        Optional(),
        EqualTo('new_password', message='Passwords must match')
    ])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate timezone choices (simplified list)
        self.timezone.choices = [
            ('UTC', 'UTC'),
            ('US/Eastern', 'Eastern Time (US)'),
            ('US/Central', 'Central Time (US)'),
            ('US/Mountain', 'Mountain Time (US)'),
            ('US/Pacific', 'Pacific Time (US)'),
            ('Europe/London', 'London'),
            ('Europe/Paris', 'Paris'),
            ('Europe/Berlin', 'Berlin'),
            ('Asia/Tokyo', 'Tokyo'),
            ('Asia/Shanghai', 'Shanghai'),
            ('Asia/Kolkata', 'Mumbai'),
            ('Asia/Dhaka', 'Dhaka'),
            ('Australia/Sydney', 'Sydney'),
        ]




@track_errors('unified_registration_form_validation')
class UnifiedRegistrationForm(FlaskForm):
    """Unified form for user registration, tenant creation, and payment in one flow"""
    
    # User Information (Step 1)
    username = StringField('Username', validators=[
        DataRequired(message='Username is required'),
        Length(min=3, max=50, message='Username must be between 3 and 50 characters')
    ])
    email = StringField('Email', validators=[
        DataRequired(message='Email is required'),
        Email(message='Please enter a valid email address')
    ])
    password = PasswordField('Password', validators=[
        DataRequired(message='Password is required'),
        Length(min=6, message='Password must be at least 6 characters long')
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(message='Please confirm your password'),
        EqualTo('password', message='Passwords must match')
    ])
    full_name = StringField('Full Name', validators=[
        Optional(),
        Length(max=100, message='Full name cannot exceed 100 characters')
    ])
    company = StringField('Company', validators=[
        Optional(),
        Length(max=100, message='Company name cannot exceed 100 characters')
    ])
    
    # Organization Information (Step 2)
    organization_name = StringField('Organization Name', validators=[
        DataRequired(message='Organization name is required'),
        Length(min=3, max=100, message='Organization name must be between 3 and 100 characters')
    ])
    subdomain = StringField('Subdomain', validators=[
        DataRequired(message='Subdomain is required'),
        Length(min=3, max=50, message='Subdomain must be between 3 and 50 characters')
    ])
    industry = StringField('Industry', validators=[
        Optional(),
        Length(max=100, message='Industry cannot exceed 100 characters')
    ])
    country = SelectField('Country', choices=[
        ('', 'Select Country'),
        ('BD', 'Bangladesh'),
        ('IN', 'India'),
        ('PK', 'Pakistan'),
        ('US', 'United States'),
        ('UK', 'United Kingdom'),
        ('CA', 'Canada'),
        ('AU', 'Australia'),
        ('SG', 'Singapore'),
        ('MY', 'Malaysia'),
        ('TH', 'Thailand'),
        ('ID', 'Indonesia'),
        ('PH', 'Philippines'),
        ('VN', 'Vietnam'),
        ('AE', 'United Arab Emirates'),
        ('SA', 'Saudi Arabia'),
        ('OTHER', 'Other')
    ], validators=[Optional()])
    
    # Plan Selection (Step 3)
    selected_plan = HiddenField('Selected Plan', validators=[
        DataRequired(message='Please select a subscription plan')
    ])

    def validate_username(self, username):
        """Custom validation for username uniqueness"""
        user = SaasUser.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Username already exists. Please choose a different one.')
    
    def validate_email(self, email):
        """Custom validation for email uniqueness"""
        user = SaasUser.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Email already registered. Please use a different email or sign in.')
    
    def validate_subdomain(self, subdomain):
        """Custom validation for subdomain format and uniqueness"""
        # Check format
        if not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?$', subdomain.data):
            raise ValidationError('Subdomain must contain only letters, numbers, and hyphens, and cannot start or end with a hyphen.')
        
        # Check for reserved subdomains
        reserved_subdomains = ['www', 'api', 'admin', 'app', 'mail', 'ftp', 'blog', 'support', 'help']
        if subdomain.data.lower() in reserved_subdomains:
            raise ValidationError('This subdomain is reserved. Please choose a different one.')
        
        # Check uniqueness
        tenant = Tenant.query.filter_by(subdomain=subdomain.data).first()
        if tenant:
            raise ValidationError('Subdomain already taken. Please choose a different one.')
    
    def validate_selected_plan(self, selected_plan):
        """Custom validation for plan selection"""
        plan = SubscriptionPlan.query.filter_by(name=selected_plan.data, is_active=True).first()
        if not plan:
            raise ValidationError('Invalid plan selected. Please choose a valid subscription plan.')





@app.route('/register/unified', methods=['GET', 'POST'])
@track_errors('unified_register_route')
def unified_register():
    """Unified registration route that handles user registration, tenant creation, and payment"""
    form = UnifiedRegistrationForm()
    
    # Get active subscription plans for display
    plans = SubscriptionPlan.query.filter_by(is_active=True).order_by(SubscriptionPlan.price).all()
    plans_data = [
        {
            'id': plan.id,
            'name': plan.name,
            'price': float(plan.price),
            'max_users': plan.max_users,
            'storage_limit': plan.storage_limit,
            'features': plan.features or [],
            'modules': plan.modules or [],
            'is_active': plan.is_active,
            'created_at': plan.created_at.isoformat()
        }
        for plan in plans
    ]
    
    # Initialize status for template - FIXED VERSION
    status = {
        'tenant': {
            'status': 'new',
            'name': None,
            'subdomain': None,
            'plan': None  # Add missing plan field
        },
        'payment': {
            'status': 'pending',
            'transaction_id': None,
            'amount': 0
        },
        'user': {
            'active': False, 
            'verified': False
        }
    }
    
    # Check if user is authenticated and has pending registration
    if current_user.is_authenticated and session.get('registration_completed'):
        tenant_id = session.get('pending_tenant_id')
        if tenant_id:
            tenant = Tenant.query.get(tenant_id)
            if tenant:
                transaction = PaymentTransaction.query.filter_by(
                    tenant_id=tenant_id,
                    user_id=current_user.id
                ).order_by(PaymentTransaction.created_at.desc()).first()
                
                status = {
                    'tenant': {
                        'status': tenant.status,
                        'name': tenant.name,
                        'subdomain': tenant.subdomain,
                        'plan': tenant.plan  # Now properly included
                    },
                    'payment': {
                        'status': transaction.status if transaction else 'UNKNOWN',
                        'transaction_id': transaction.transaction_id if transaction else None,
                        'amount': transaction.amount if transaction else 0
                    },
                    'user': {
                        'active': current_user.is_active,
                        'verified': current_user.email_verified if hasattr(current_user, 'email_verified') else False
                    }
                }
    
    if request.method == 'GET':
        return render_template('unified_register.html', form=form, plans=plans_data, status=status)
    
    if form.validate_on_submit():
        try:
            # Step 1: Create user (inactive until payment succeeds)
            user = SaasUser(
                username=form.username.data,
                email=form.email.data,
                password_hash=generate_password_hash(form.password.data),
                full_name=form.full_name.data or None,
                company=form.company.data or None,
                is_active=False,  # Will be activated after successful payment
                email_verified=False  # Will be verified after payment
            )
            
            # Step 2: Get available worker
            worker = get_available_worker()
            if not worker:
                flash('Service temporarily unavailable. Please try again in a few minutes.', 'error')
                return render_template('unified_register.html', form=form, plans=plans_data, status=status)
            
            # Step 3: Create tenant
            db_name = f"kdoo_{form.subdomain.data}"
            admin_username = f"admin_{form.subdomain.data}"
            admin_password = generate_secure_password()
            
            tenant = Tenant(
                name=form.organization_name.data,
                subdomain=form.subdomain.data,
                database_name=db_name,
                plan=form.selected_plan.data,
                admin_username=admin_username,
                status='pending'  # Will change to 'creating' after payment, then 'active' after DB creation
            )
            tenant.set_admin_password(admin_password)
            
            # Step 4: Save everything in a transaction
            db.session.add(user)
            db.session.flush()  # Get user ID
            
            db.session.add(tenant)
            db.session.flush()  # Get tenant ID
            
            # Step 5: Create tenant-user relationship
            tenant_user = TenantUser(tenant_id=tenant.id, user_id=user.id, role='admin')
            db.session.add(tenant_user)
            
            # Step 6: Update worker capacity
            worker.current_tenants += 1
            
            # Step 7: Commit all changes
            db.session.commit()
            
            # Step 8: Log in the user immediately (but keep inactive)
            login_user(user)
            
            try:
                # Cache updates
                tenant_data = {
                    'id': tenant.id,
                    'name': tenant.name,
                    'subdomain': tenant.subdomain,
                    'status': tenant.status,
                    'plan': tenant.plan
                }
                
                update_trigger.tenant_created(tenant_data, [user.id])
                update_trigger.user_stats_changed()
                
            except Exception as e:
                logger.warning(f"Failed to update cache after unified registration: {e}")
            
            # Step 9: Initiate payment using enhanced billing
            try:
                # Import the enhanced billing service
                from .billing import BillingService
                
                payment_url = BillingService.initiate_unified_payment(
                    tenant_id=tenant.id, 
                    user_id=user.id, 
                    plan=tenant.plan
                )
                
                # Store registration completion status
                session['registration_completed'] = True
                session['pending_tenant_id'] = tenant.id
                
                flash('Registration completed! Redirecting to secure payment...', 'success')
                return redirect(payment_url)
                
            except Exception as payment_error:
                # If payment initiation fails, clean up properly
                try:
                    # Remove the created tenant and user
                    TenantUser.query.filter_by(tenant_id=tenant.id, user_id=user.id).delete()
                    worker.current_tenants -= 1
                    db.session.delete(tenant)
                    db.session.delete(user)
                    db.session.commit()
                except Exception as cleanup_error:
                    logger.error(f"Failed to cleanup after payment error: {cleanup_error}")
                    db.session.rollback()
                
                error_tracker.log_error(payment_error, {
                    'user_email': form.email.data,
                    'subdomain': form.subdomain.data,
                    'plan': form.selected_plan.data,
                    'function': 'initiate_unified_payment'
                })
                flash('Registration failed during payment setup. Please try again.', 'error')
                return render_template('unified_register.html', form=form, plans=plans_data, status=status)
            
        except Exception as e:
            db.session.rollback()
            error_tracker.log_error(e, {
                'form_data': {
                    'username': form.username.data,
                    'email': form.email.data,
                    'organization_name': form.organization_name.data,
                    'subdomain': form.subdomain.data,
                    'plan': form.selected_plan.data
                },
                'function': 'unified_register'
            })
            flash('Registration failed due to a system error. Please try again or contact support.', 'error')
    
    # If form validation failed, show errors
    return render_template('unified_register.html', form=form, plans=plans_data, status=status)

@app.route('/registration/status')
@login_required
@track_errors('registration_status_route')
def registration_status():
    """Check the status of current user's registration and payment"""
    try:
        if not session.get('registration_completed'):
            return redirect(url_for('dashboard'))
        
        tenant_id = session.get('pending_tenant_id')
        if not tenant_id:
            return redirect(url_for('dashboard'))
        
        tenant = Tenant.query.get(tenant_id)
        if not tenant:
            session.pop('registration_completed', None)
            session.pop('pending_tenant_id', None)
            return redirect(url_for('dashboard'))
        
        # Check latest payment transaction
        transaction = PaymentTransaction.query.filter_by(
            tenant_id=tenant_id,
            user_id=current_user.id
        ).order_by(PaymentTransaction.created_at.desc()).first()
        
        status_data = {
            'tenant': {
                'id': tenant.id,
                'name': tenant.name,
                'subdomain': tenant.subdomain,
                'status': tenant.status,
                'plan': tenant.plan
            },
            'payment': {
                'status': transaction.status if transaction else 'UNKNOWN',
                'transaction_id': transaction.transaction_id if transaction else None,
                'amount': transaction.amount if transaction else 0
            },
            'user': {
                'active': current_user.is_active,
                'verified': current_user.email_verified if hasattr(current_user, 'email_verified') else False
            }
        }
        
        return render_template('registration_status.html', status=status_data)
        
    except Exception as e:
        error_tracker.log_error(e, {
            'user_id': current_user.id,
            'function': 'registration_status'
        })
        return redirect(url_for('dashboard'))



# Add cleanup route for failed registrations
@app.route('/cleanup/failed-registration', methods=['POST'])
@login_required
@track_errors('cleanup_failed_registration')
def cleanup_failed_registration():
    """Clean up failed registration attempts"""
    try:
        if not session.get('registration_completed'):
            return jsonify({'error': 'No pending registration'}), 400
        
        tenant_id = session.get('pending_tenant_id')
        if not tenant_id:
            return jsonify({'error': 'No pending tenant'}), 400
        
        tenant = Tenant.query.get(tenant_id)
        if not tenant:
            session.pop('registration_completed', None)
            session.pop('pending_tenant_id', None)
            return jsonify({'success': True, 'message': 'Registration cleaned up'})
        
        # Only allow cleanup if payment failed or tenant creation failed
        if tenant.status not in ['failed', 'pending']:
            return jsonify({'error': 'Cannot cleanup active registration'}), 400
        
        # Check if user owns this tenant
        tenant_user = TenantUser.query.filter_by(
            tenant_id=tenant_id,
            user_id=current_user.id
        ).first()
        
        if not tenant_user:
            return jsonify({'error': 'Access denied'}), 403
        
        # Clean up
        try:
            # Delete tenant relationships
            TenantUser.query.filter_by(tenant_id=tenant_id).delete()
            CredentialAccess.query.filter_by(tenant_id=tenant_id).delete()
            PaymentTransaction.query.filter_by(tenant_id=tenant_id).delete()
            
            # Delete tenant
            db.session.delete(tenant)
            
            # Update worker capacity
            workers = WorkerInstance.query.filter(WorkerInstance.current_tenants > 0).all()
            for worker in workers:
                if worker.current_tenants > 0:
                    worker.current_tenants -= 1
            
            db.session.commit()
            
            # Clear session
            session.pop('registration_completed', None)
            session.pop('pending_tenant_id', None)
            
            return jsonify({'success': True, 'message': 'Failed registration cleaned up successfully'})
            
        except Exception as cleanup_error:
            db.session.rollback()
            error_tracker.log_error(cleanup_error, {
                'tenant_id': tenant_id,
                'user_id': current_user.id,
                'function': 'cleanup_failed_registration'
            })
            return jsonify({'error': 'Cleanup failed'}), 500
        
    except Exception as e:
        error_tracker.log_error(e, {
            'user_id': current_user.id,
            'function': 'cleanup_failed_registration'
        })
        return jsonify({'error': 'Cleanup error'}), 500


# WebSocket events for real-time updates
@socketio.on('join_registration_updates')
def on_join_registration_updates(data):
    """Join room for registration status updates"""
    if current_user.is_authenticated:
        room = f"user_{current_user.id}_registration"
        join_room(room)
        emit('joined', {'room': room})

@socketio.on('leave_registration_updates')
def on_leave_registration_updates(data):
    """Leave registration updates room"""
    if current_user.is_authenticated:
        room = f"user_{current_user.id}_registration"
        leave_room(room)
        emit('left', {'room': room})

# Add this to your UpdateTrigger class in websocket_handler.py
def payment_status_changed(self, transaction_id, status, tenant_data, user_ids):
    """Trigger payment status change updates"""
    try:
        update_data = {
            'type': 'payment_status_changed',
            'transaction_id': transaction_id,
            'status': status,
            'tenant': tenant_data,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        for user_id in user_ids:
            room = f"user_{user_id}_registration"
            self.ws_manager.emit_to_room(room, 'payment_update', update_data)
            
    except Exception as e:
        logger.warning(f"Failed to trigger payment status update: {e}")


# Add webhook endpoint for payment status updates
@app.route('/webhook/payment-status', methods=['POST'])
@track_errors('payment_webhook_route')
def payment_webhook():
    """Webhook endpoint for real-time payment status updates"""
    try:
        data = request.get_json()
        
        if not data or 'transaction_id' not in data:
            return jsonify({'error': 'Invalid webhook data'}), 400
        
        transaction_id = data['transaction_id']
        status = data.get('status', 'UNKNOWN')
        
        # Find and update transaction
        transaction = PaymentTransaction.query.filter_by(
            transaction_id=transaction_id
        ).first()
        
        if not transaction:
            logger.warning(f"Webhook: Transaction {transaction_id} not found")
            return jsonify({'error': 'Transaction not found'}), 404
        
        # Update status
        transaction.status = status
        transaction.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Trigger real-time updates via WebSocket
        try:
            tenant = Tenant.query.get(transaction.tenant_id)
            if tenant:
                tenant_data = {
                    'id': tenant.id,
                    'name': tenant.name,
                    'subdomain': tenant.subdomain,
                    'status': tenant.status
                }
                
                update_trigger.payment_status_changed(
                    transaction_id, 
                    status, 
                    tenant_data, 
                    [transaction.user_id]
                )
        except Exception as ws_error:
            logger.warning(f"Failed to send WebSocket update: {ws_error}")
        
        return jsonify({'success': True})
        
    except Exception as e:
        error_tracker.log_error(e, {'function': 'payment_webhook'})
        return jsonify({'error': 'Webhook processing failed'}), 500


# Renewal payment callback routes
@app.route('/renewal/payment/success/<int:tenant_id>', methods=['GET', 'POST'])
@csrf.exempt
@track_errors('renewal_payment_success_route')
def renewal_payment_success(tenant_id):
    """Handle successful renewal payment callback from SSLCommerz"""
    try:
        # Handle both GET and POST data from SSLCommerz
        transaction_id = request.args.get('tran_id') or request.form.get('tran_id')
        validation_id = request.args.get('val_id') or request.form.get('val_id')
        amount = request.args.get('amount') or request.form.get('amount', '50.00')
        
        logger.info(f"Renewal payment success callback - tenant_id: {tenant_id}, tran_id: {transaction_id}, val_id: {validation_id}")
        logger.info(f"GET params: {dict(request.args)}")
        logger.info(f"POST form: {dict(request.form)}")
        
        if not transaction_id:
            flash('Invalid payment transaction. Please contact support.', 'error')
            return redirect(url_for('dashboard'))
        
        # Import and handle renewal payment
        from billing_service import BillingService
        billing_service = BillingService()
        
        # Create payment data for renewal processing
        payment_data = {
            'payment_id': transaction_id,
            'amount': float(amount),
            'currency': 'BDT',
            'transaction_id': transaction_id,
            'response': {
                'validation_id': validation_id,
                'status': 'success',
                'gateway': 'sslcommerz'
            }
        }
        
        # Process renewal payment (extends billing cycle by 30 days)
        logger.info(f"Processing renewal payment via SUCCESS callback: {payment_data}")
        payment = billing_service.process_renewal_payment(tenant_id, payment_data)
        
        if payment:
            logger.info(f"Renewal payment processed successfully via SUCCESS callback for tenant {tenant_id}")
        
        flash('Payment successful! Your panel has been renewed for 30 days.', 'success')
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        logger.error(f"Error processing renewal payment success: {str(e)}", exc_info=True)
        flash('Payment completed but there was an issue processing the renewal. Please contact support.', 'warning')
        return redirect(url_for('dashboard'))

@app.route('/renewal/payment/fail/<int:tenant_id>', methods=['GET', 'POST'])
@csrf.exempt
def renewal_payment_fail(tenant_id):
    """Handle failed renewal payment callback"""
    flash('Payment failed. Please try again or contact support.', 'error')
    return redirect(url_for('billing.initiate_payment', tenant_id=tenant_id))

@app.route('/renewal/payment/cancel/<int:tenant_id>', methods=['GET', 'POST'])
@csrf.exempt
def renewal_payment_cancel(tenant_id):
    """Handle cancelled renewal payment callback"""
    flash('Payment was cancelled.', 'info')
    return redirect(url_for('billing.initiate_payment', tenant_id=tenant_id))

@app.route('/billing/renewal/ipn', methods=['POST'])
@csrf.exempt
@track_errors('renewal_payment_ipn')
def renewal_payment_ipn():
    """Handle SSLCommerz IPN (Instant Payment Notification) for renewal payments"""
    try:
        ipn_data = request.form.to_dict()
        transaction_id = ipn_data.get('tran_id')
        validation_id = ipn_data.get('val_id')
        status = ipn_data.get('status')
        
        if not transaction_id:
            logger.error("IPN received without transaction ID")
            return "INVALID", 400
        
        logger.info(f"Renewal payment IPN received for transaction {transaction_id}, status: {status}")
        
        if status == 'VALID':
            # Find the payment transaction
            from models import PaymentTransaction
            transaction = PaymentTransaction.query.filter_by(
                transaction_id=transaction_id
            ).first()
            
            if transaction and transaction.status == 'PENDING':
                # Process the renewal payment
                from billing_service import BillingService
                billing_service = BillingService()
                
                payment_data = {
                    'payment_id': transaction_id,
                    'amount': transaction.amount,
                    'currency': 'BDT',
                    'transaction_id': transaction_id,
                    'response': {
                        'validation_id': validation_id,
                        'status': 'success',
                        'gateway': 'sslcommerz'
                    }
                }
                
                logger.info(f"Processing renewal payment via IPN callback: {payment_data}")
                payment = billing_service.process_renewal_payment(transaction.tenant_id, payment_data)
                
                # Update transaction status
                transaction.status = 'COMPLETED'
                db.session.commit()
                
                if payment:
                    logger.info(f"Renewal payment processed successfully via IPN callback for transaction {transaction_id}")
                else:
                    logger.warning(f"Payment processing returned None via IPN callback for transaction {transaction_id}")
        
        return "VERIFIED", 200
        
    except Exception as e:
        logger.error(f"Error processing renewal payment IPN: {str(e)}", exc_info=True)
        return "ERROR", 500


# Add this API endpoint for real-time subdomain validation

@app.route('/api/validate-subdomain/<subdomain>')
@track_errors('validate_subdomain_api')
def validate_subdomain_api(subdomain):
    """API endpoint to validate subdomain availability in real-time"""
    try:
        # Check format
        if not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?$', subdomain):
            return jsonify({
                'available': False,
                'message': 'Subdomain must contain only letters, numbers, and hyphens'
            })
        
        # Check length
        if len(subdomain) < 3 or len(subdomain) > 50:
            return jsonify({
                'available': False,
                'message': 'Subdomain must be between 3 and 50 characters'
            })
        
        # Check reserved subdomains
        reserved_subdomains = ['www', 'api', 'admin', 'app', 'mail', 'ftp', 'blog', 'support', 'help']
        if subdomain.lower() in reserved_subdomains:
            return jsonify({
                'available': False,
                'message': 'This subdomain is reserved'
            })
        
        # Check uniqueness
        tenant = Tenant.query.filter_by(subdomain=subdomain).first()
        if tenant:
            return jsonify({
                'available': False,
                'message': 'Subdomain already taken'
            })
        
        return jsonify({
            'available': True,
            'message': 'Subdomain is available',
            'preview_url': f"https://{subdomain}.{request.host}"
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'subdomain': subdomain, 'function': 'validate_subdomain_api'})
        return jsonify({
            'available': False,
            'message': 'Error checking subdomain availability'
        }), 500

@app.route('/api/tenant/<subdomain>/user-limit')
@track_errors('get_tenant_user_limit_api')
def get_tenant_user_limit_api(subdomain):
    """API endpoint to get tenant user limit information for sync with Odoo"""
    try:
        # Find tenant by subdomain
        tenant = Tenant.query.filter_by(subdomain=subdomain).first()
        if not tenant:
            return jsonify({
                'success': False,
                'error': 'Tenant not found'
            }), 404
        
        # Get subscription plan details
        plan = SubscriptionPlan.query.filter_by(name=tenant.plan).first()
        max_users = plan.max_users if plan else tenant.max_users
        
        # Get current user count from TenantUser table
        current_user_count = TenantUser.query.filter_by(tenant_id=tenant.id).count()
        
        return jsonify({
            'success': True,
            'max_users': max_users,
            'current_users': current_user_count,
            'remaining_users': max(0, max_users - current_user_count),
            'tenant_status': tenant.status,
            'plan': tenant.plan
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'subdomain': subdomain, 'function': 'get_tenant_user_limit_api'})
        return jsonify({
            'success': False,
            'error': 'Error retrieving user limit information'
        }), 500


@app.route('/api/tenant/<subdomain>/config')
@track_errors('get_tenant_config_api')
def get_tenant_config_api(subdomain):
    """API endpoint to get complete tenant configuration for SaaS Controller"""
    try:
        # Find tenant by subdomain
        tenant = Tenant.query.filter_by(subdomain=subdomain).first()
        if not tenant:
            return jsonify({
                'success': False,
                'error': 'Tenant not found'
            }), 404
        
        # Get subscription plan details
        plan = SubscriptionPlan.query.filter_by(name=tenant.plan).first()
        
        # Build configuration response
        config = {
            'success': True,
            'tenant_id': tenant.id,
            'subdomain': tenant.subdomain,
            'status': tenant.status,
            'plan': tenant.plan,
            
            # User limits
            'max_users': plan.max_users if plan else tenant.max_users,
            'user_limit_enabled': True,
            
            # Branding settings (can be customized per plan)
            'remove_branding': plan.features.get('remove_branding', False) if plan and plan.features else False,
            'custom_app_name': tenant.custom_app_name or 'Business Manager',
            'custom_company_name': tenant.company_name,
            
            # Color schema (default or plan-specific)
            'primary_color': plan.theme.get('primary_color', '#017e84') if plan and hasattr(plan, 'theme') and plan.theme else '#017e84',
            'secondary_color': plan.theme.get('secondary_color', '#875a7b') if plan and hasattr(plan, 'theme') and plan.theme else '#875a7b',
            'accent_color': plan.theme.get('accent_color', '#017e84') if plan and hasattr(plan, 'theme') and plan.theme else '#017e84',
            
            # Feature controls
            'disable_apps_menu': plan.features.get('disable_apps_menu', False) if plan and plan.features else False,
            'disable_settings_menu': plan.features.get('disable_settings_menu', False) if plan and plan.features else False,
            'disable_debug_mode': plan.features.get('disable_debug_mode', True) if plan and plan.features else True,
            
            # Resource limits
            'max_storage_mb': plan.storage_limit_mb if plan else 1024,
            'max_email_per_day': plan.email_limit_per_day if plan else 100,
        }
        
        return jsonify(config)
        
    except Exception as e:
        error_tracker.log_error(e, {'subdomain': subdomain, 'function': 'get_tenant_config_api'})
        return jsonify({
            'success': False,
            'error': 'Error retrieving tenant configuration'
        }), 500

@app.route('/api/tenant/<subdomain>/users')
@track_errors('get_tenant_users_api')
def get_tenant_users_api(subdomain):
    """API endpoint to get tenant users information"""
    try:
        # Find tenant by subdomain
        tenant = Tenant.query.filter_by(subdomain=subdomain).first()
        if not tenant:
            return jsonify({
                'success': False,
                'error': 'Tenant not found'
            }), 404
        
        # Get users from TenantUser table
        tenant_users = TenantUser.query.filter_by(tenant_id=tenant.id).all()
        users_data = []
        
        for tu in tenant_users:
            user = tu.user
            users_data.append({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': tu.role,
                'created_at': tu.created_at.isoformat() if tu.created_at else None
            })
        
        return jsonify({
            'success': True,
            'users': users_data,
            'total_users': len(users_data),
            'max_users': tenant.max_users
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'subdomain': subdomain, 'function': 'get_tenant_users_api'})
        return jsonify({
            'success': False,
            'error': 'Error retrieving tenant users'
        }), 500

@app.route('/api/tenant/<subdomain>/user-limit', methods=['PUT'])
@track_errors('update_tenant_user_limit_api')
def update_tenant_user_limit_api(subdomain):
    """API endpoint to update tenant user limit"""
    try:
        # Find tenant by subdomain
        tenant = Tenant.query.filter_by(subdomain=subdomain).first()
        if not tenant:
            return jsonify({
                'success': False,
                'error': 'Tenant not found'
            }), 404
        
        data = request.get_json()
        if not data or 'max_users' not in data:
            return jsonify({
                'success': False,
                'error': 'max_users parameter is required'
            }), 400
        
        max_users = int(data['max_users'])
        if max_users < 1:
            return jsonify({
                'success': False,
                'error': 'max_users must be at least 1'
            }), 400
        
        # Update tenant max_users
        old_max_users = tenant.max_users
        tenant.max_users = max_users
        tenant.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Create audit log
        try:
            audit_log = AuditLog(
                tenant_id=tenant.id,
                action='user_limit_updated',
                details={
                    'old_max_users': old_max_users,
                    'new_max_users': max_users,
                    'updated_via': 'api'
                },
                ip_address=request.remote_addr,
                user_agent=str(request.user_agent)
            )
            db.session.add(audit_log)
            db.session.commit()
        except Exception as audit_error:
            logger.warning(f"Failed to create audit log for user limit update: {audit_error}")
        
        # Invalidate cache
        invalidate_tenant_cache(tenant.id)
        
        logger.info(f"Updated user limit for tenant {subdomain} from {old_max_users} to {max_users}")
        
        return jsonify({
            'success': True,
            'message': 'User limit updated successfully',
            'old_max_users': old_max_users,
            'new_max_users': max_users
        })
        
    except ValueError:
        return jsonify({
            'success': False,
            'error': 'max_users must be a valid integer'
        }), 400
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'subdomain': subdomain, 'function': 'update_tenant_user_limit_api'})
        return jsonify({
            'success': False,
            'error': 'Error updating user limit'
        }), 500

@app.route('/api/tenant/<int:tenant_id>/update', methods=['POST'])
@login_required
@track_errors('update_tenant_settings')
def update_tenant_settings(tenant_id):
    """Update tenant settings from the management interface"""
    try:
        # Check if user has access to this tenant
        if not current_user.is_admin:
            tenant_user = TenantUser.query.filter_by(tenant_id=tenant_id, user_id=current_user.id).first()
            if not tenant_user:
                return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        tenant = Tenant.query.get_or_404(tenant_id)
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        # Track changes
        changes = {}
        plan_changed = False
        
        # Update tenant name if provided
        if 'name' in data and data['name'] != tenant.name:
            changes['name'] = {'old': tenant.name, 'new': data['name']}
            tenant.name = data['name']
        
        # Update plan if provided
        if 'plan' in data and data['plan'] != tenant.plan:
            # Validate plan exists
            plan = SubscriptionPlan.query.filter_by(name=data['plan'], is_active=True).first()
            if not plan:
                return jsonify({'success': False, 'message': 'Invalid plan selected'}), 400
            
            changes['plan'] = {'old': tenant.plan, 'new': data['plan']}
            tenant.plan = data['plan']
            tenant.max_users = plan.max_users
            tenant.storage_limit = plan.storage_limit
            plan_changed = True
        
        # Update max_users if provided and plan didn't change
        if 'max_users' in data and not plan_changed:
            new_max_users = int(data['max_users'])
            if new_max_users != tenant.max_users:
                changes['max_users'] = {'old': tenant.max_users, 'new': new_max_users}
                tenant.max_users = new_max_users
        
        # Update storage_limit if provided and plan didn't change
        if 'storage_limit' in data and not plan_changed:
            new_storage_limit = int(data['storage_limit'])
            if new_storage_limit != tenant.storage_limit:
                changes['storage_limit'] = {'old': tenant.storage_limit, 'new': new_storage_limit}
                tenant.storage_limit = new_storage_limit
        
        # Save changes
        tenant.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Sync user limits if plan changed
        if plan_changed:
            try:
                sync_result = sync_tenant_user_limits(tenant_id)
                if not sync_result:
                    logger.warning(f"Failed to sync user limits for tenant {tenant_id} after settings update")
            except Exception as sync_error:
                logger.warning(f"Error syncing user limits for tenant {tenant_id}: {sync_error}")
        
        # Create audit log
        try:
            audit_log = AuditLog(
                user_id=current_user.id,
                tenant_id=tenant_id,
                action='tenant_settings_updated',
                details={
                    'changes': changes,
                    'plan_changed': plan_changed
                },
                ip_address=request.remote_addr,
                user_agent=str(request.user_agent)
            )
            db.session.add(audit_log)
            db.session.commit()
        except Exception as audit_error:
            logger.warning(f"Failed to create audit log for tenant settings update: {audit_error}")
        
        # Invalidate cache
        invalidate_tenant_cache(tenant_id)
        if current_user.id:
            invalidate_user_cache(current_user.id)
        
        logger.info(f"Updated tenant {tenant_id} settings: {changes}")
        
        return jsonify({
            'success': True,
            'message': 'Tenant settings updated successfully',
            'changes': changes,
            'plan_changed': plan_changed
        })
        
    except ValueError as ve:
        return jsonify({'success': False, 'message': f'Invalid data: {str(ve)}'}), 400
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'tenant_id': tenant_id, 'user_id': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to update tenant settings'}), 500



# Template filter for better status display
@app.template_filter('format_payment_status')
def format_payment_status(status):
    """Format payment status for display"""
    status_mapping = {
        'PENDING': ('warning', 'Processing'),
        'SUCCESS': ('success', 'Completed'),
        'FAILED': ('danger', 'Failed'),
        'CANCELLED': ('secondary', 'Cancelled'),
        'UNKNOWN': ('info', 'Unknown')
    }
    return status_mapping.get(status, ('info', status))

@app.template_filter('format_tenant_status')
def format_tenant_status(status):
    """Format tenant status for display"""
    status_mapping = {
        'pending': ('warning', 'Awaiting Payment'),
        'creating': ('info', 'Setting Up'),
        'active': ('success', 'Active'),
        'failed': ('danger', 'Setup Failed'),
        'inactive': ('secondary', 'Inactive')
    }
    return status_mapping.get(status, ('info', status.title()))

@app.template_filter('timeago')
def timeago(dt):
    """Convert datetime to time ago format"""
    if not dt:
        return 'Never'
    
    now = datetime.now()
    if dt.tzinfo is not None:
        now = now.replace(tzinfo=dt.tzinfo)
    
    diff = now - dt
    
    if diff.days > 365:
        years = diff.days // 365
        return f"{years} year{'s' if years > 1 else ''} ago"
    elif diff.days > 30:
        months = diff.days // 30
        return f"{months} month{'s' if months > 1 else ''} ago"
    elif diff.days > 0:
        return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    else:
        return "Just now"

# SSO (Single Sign-On) endpoint for tenant login
@app.route('/sso/tenant/<int:tenant_id>')
@login_required
@track_errors('sso_tenant_login')
def sso_tenant_login(tenant_id):
    """Generate secure login link and redirect to tenant Odoo instance"""
    try:
        # Verify user has access to this tenant
        tenant_user = TenantUser.query.filter_by(tenant_id=tenant_id, user_id=current_user.id).first()
        if not tenant_user and not current_user.is_admin:
            flash('Access denied to this tenant.', 'error')
            return redirect(url_for('dashboard'))
        
        # Get tenant information
        tenant = Tenant.query.get_or_404(tenant_id)
        
        if not tenant.is_active or tenant.status != 'active':
            flash('Tenant is not active. Cannot access inactive tenant.', 'warning')
            return redirect(url_for('dashboard'))
        
        # Generate secure token for SSO
        sso_token = secrets.token_urlsafe(32)
        
        # Store SSO token in Redis with expiration (5 minutes)
        sso_data = {
            'user_id': current_user.id,
            'tenant_id': tenant_id,
            'username': tenant.admin_username,
            'password': tenant.get_admin_password(),
            'database': tenant.database_name,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Cache the SSO token
        redis_client.setex(f"sso_token:{sso_token}", 300, json.dumps(sso_data))  # 5 minutes
        
        # Create SSO page URL that will handle the auto-login
        sso_url = url_for('sso_login_page', token=sso_token)
        
        logger.info(f"SSO login initiated for user {current_user.id} to tenant {tenant_id}")
        
        # Redirect to SSO login page
        return redirect(sso_url)
        
    except Exception as e:
        error_tracker.log_error(e, {'tenant_id': tenant_id, 'user_id': current_user.id})
        flash('Error initiating SSO login. Please try again.', 'error')
        return redirect(url_for('dashboard'))

# SSO validation endpoint (called by Odoo workers via nginx)
@app.route('/api/sso/validate/<token>')
@track_errors('sso_validate')
def sso_validate(token):
    """Validate SSO token and return login credentials"""
    try:
        # Get SSO data from Redis
        sso_data_json = redis_client.get(f"sso_token:{token}")
        if not sso_data_json:
            return jsonify({'error': 'Invalid or expired SSO token'}), 401
        
        sso_data = json.loads(sso_data_json)
        
        # Validate token age (additional security)
        token_time = datetime.fromisoformat(sso_data['timestamp'])
        if (datetime.utcnow() - token_time).total_seconds() > 300:  # 5 minutes
            redis_client.delete(f"sso_token:{token}")
            return jsonify({'error': 'SSO token expired'}), 401
        
        # Return credentials for auto-login
        response_data = {
            'database': sso_data['database'],
            'username': sso_data['username'],
            'password': sso_data['password'],
            'user_id': sso_data['user_id'],
            'tenant_id': sso_data['tenant_id']
        }
        
        # Delete token after use (single use)
        redis_client.delete(f"sso_token:{token}")
        
        logger.info(f"SSO token validated for user {sso_data['user_id']} to tenant {sso_data['tenant_id']}")
        
        return jsonify(response_data)
        
    except Exception as e:
        error_tracker.log_error(e, {'token': token})
        return jsonify({'error': 'SSO validation failed'}), 500

# SSO login page that performs auto-login to Odoo
@app.route('/sso/login/<token>')
@track_errors('sso_login_page')
def sso_login_page(token):
    """Display SSO login page that auto-logs into Odoo tenant"""
    try:
        # Get SSO data from Redis
        sso_data_json = redis_client.get(f"sso_token:{token}")
        if not sso_data_json:
            flash('SSO session expired. Please try again.', 'warning')
            return redirect(url_for('dashboard'))
        
        sso_data = json.loads(sso_data_json)
        
        # Validate token age
        token_time = datetime.fromisoformat(sso_data['timestamp'])
        if (datetime.utcnow() - token_time).total_seconds() > 300:  # 5 minutes
            redis_client.delete(f"sso_token:{token}")
            flash('SSO session expired. Please try again.', 'warning')
            return redirect(url_for('dashboard'))
        
        # Get tenant info for display
        tenant = Tenant.query.get(sso_data['tenant_id'])
        if not tenant:
            flash('Tenant not found.', 'error')
            return redirect(url_for('dashboard'))
        
        # Construct tenant URL
        tenant_url = f"https://{sso_data['database']}.{request.headers.get('Host', 'khudroo.com')}"
        
        # Create complete SSO data object for JavaScript
        complete_sso_data = {
            'tenant_url': tenant_url,
            'database': sso_data['database'],
            'username': sso_data['username'],
            'password': sso_data['password'],
            'token': token
        }
        
        # Render SSO page with auto-login form
        return render_template('sso_login.html', 
                             tenant=tenant,
                             tenant_url=tenant_url,
                             sso_data=sso_data,
                             complete_sso_data_json=json.dumps(complete_sso_data),
                             token=token)
        
    except Exception as e:
        error_tracker.log_error(e, {'token': token})
        flash('SSO login failed. Please try again.', 'error')
        return redirect(url_for('dashboard'))

# SSO proxy login - handles the actual login to Odoo and redirects with session
@app.route('/sso/proxy/<token>')
@track_errors('sso_proxy_login')
def sso_proxy_login(token):
    """Proxy login to Odoo and redirect with session cookie"""
    try:
        # Get SSO data from Redis
        sso_data_json = redis_client.get(f"sso_token:{token}")
        if not sso_data_json:
            flash('SSO session expired. Please try again.', 'warning')
            return redirect(url_for('dashboard'))
        
        sso_data = json.loads(sso_data_json)
        
        # Validate token age
        token_time = datetime.fromisoformat(sso_data['timestamp'])
        if (datetime.utcnow() - token_time).total_seconds() > 300:  # 5 minutes
            redis_client.delete(f"sso_token:{token}")
            flash('SSO session expired. Please try again.', 'warning')
            return redirect(url_for('dashboard'))
        
        # Delete token (single use)
        redis_client.delete(f"sso_token:{token}")
        
        tenant_url = f"https://{sso_data['database']}.{request.headers.get('Host', 'khudroo.com')}"
        login_url = f"{tenant_url}/web/login"
        
        logger.info(f"SSO proxy login attempt for user {sso_data['user_id']} to tenant {sso_data['tenant_id']}")
        
        # Create a beautiful redirect page with credentials display
        # Since nginx routing causes form submission issues, we'll provide a smooth
        # redirect experience with credentials shown to the user
        try:
            logger.info(f"Creating SSO redirect page for {sso_data['username']} to {sso_data['database']}")
            
            # Use our custom SSO endpoint for passwordless login
            redirect_url = f"{tenant_url}/sso/login?username={sso_data['username']}&password={sso_data['password']}&database={sso_data['database']}"
            
            logger.info(f"SSO redirect to: {redirect_url}")
            
            redirect_html = f'''
<!DOCTYPE html>
<html>
<head>
    <title>Opening {sso_data['database']} - Khudroo SSO</title>
    <meta http-equiv="refresh" content="3;url={redirect_url}">
    <style>
        body {{
            font-family: Inter, -apple-system, BlinkMacSystemFont, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-align: center;
        }}
        .sso-container {{
            max-width: 500px;
            padding: 50px 40px;
            background: rgba(255,255,255,0.1);
            border-radius: 20px;
            backdrop-filter: blur(15px);
            border: 1px solid rgba(255,255,255,0.2);
            box-shadow: 0 15px 35px rgba(0,0,0,0.3);
        }}
        .logo {{
            width: 80px;
            height: 80px;
            background: rgba(255,255,255,0.2);
            border-radius: 50%;
            margin: 0 auto 30px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 2rem;
            animation: pulse 2s ease-in-out infinite;
        }}
        @keyframes pulse {{
            0%, 100% {{ transform: scale(1); opacity: 1; }}
            50% {{ transform: scale(1.05); opacity: 0.8; }}
        }}
        .progress-bar {{
            width: 100%;
            height: 6px;
            background: rgba(255,255,255,0.2);
            border-radius: 3px;
            overflow: hidden;
            margin: 30px 0;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #00d4ff, #090979);
            width: 0%;
            border-radius: 3px;
            animation: progress 3s ease-out forwards;
        }}
        @keyframes progress {{
            to {{ width: 100%; }}
        }}
        .credentials {{
            background: rgba(255,255,255,0.1);
            padding: 25px;
            border-radius: 15px;
            margin: 25px 0;
            border: 1px solid rgba(255,255,255,0.2);
        }}
        .credential-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin: 15px 0;
            padding: 12px;
            background: rgba(255,255,255,0.1);
            border-radius: 8px;
            font-size: 0.95em;
        }}
        .credential-label {{
            font-weight: 600;
            opacity: 0.9;
        }}
        .credential-value {{
            font-family: 'Monaco', 'Menlo', monospace;
            background: rgba(0,0,0,0.2);
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.9em;
        }}
        .manual-link {{
            display: inline-block;
            margin-top: 20px;
            padding: 12px 24px;
            background: rgba(255,255,255,0.2);
            color: white;
            text-decoration: none;
            border-radius: 25px;
            transition: all 0.3s ease;
            border: 1px solid rgba(255,255,255,0.3);
        }}
        .manual-link:hover {{
            background: rgba(255,255,255,0.3);
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }}
        .status-text {{
            font-size: 0.9em;
            opacity: 0.8;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="sso-container">
        <div class="logo">🔐</div>
        <h2 style="margin: 0 0 10px 0; font-weight: 300;">Single Sign-On</h2>
        <p style="opacity: 0.9; margin-bottom: 25px;">Opening your Odoo instance...</p>
        
        <div class="progress-bar">
            <div class="progress-fill"></div>
        </div>
        
        <div class="credentials">
            <h4 style="margin: 0 0 20px 0; font-weight: 500;">Your Access Details</h4>
            <div class="credential-item">
                <span class="credential-label">Instance:</span>
                <span class="credential-value">{sso_data['database']}</span>
            </div>
            <div class="credential-item">
                <span class="credential-label">Username:</span>
                <span class="credential-value">{sso_data['username']}</span>
            </div>
            <div class="credential-item">
                <span class="credential-label">Status:</span>
                <span class="credential-value" style="color: #00ff88;">✓ Authenticated</span>
            </div>
        </div>
        
        <div class="status-text">
            You will be automatically redirected in 3 seconds...
        </div>
        
        <a href="{redirect_url}" class="manual-link">
            Continue to {sso_data['database']} →
        </a>
    </div>
    
    <script>
        // Enhanced redirect with countdown
        let countdown = 3;
        const statusText = document.querySelector('.status-text');
        
        const updateCountdown = () => {{
            if (countdown > 0) {{
                statusText.textContent = `You will be automatically redirected in ${{countdown}} second${{countdown !== 1 ? 's' : ''}}...`;
                countdown--;
                setTimeout(updateCountdown, 1000);
            }} else {{
                statusText.textContent = 'Redirecting now...';
                window.location.href = '{redirect_url}';
            }}
        }};
        
        setTimeout(updateCountdown, 1000);
    </script>
</body>
</html>'''
            return redirect_html
            
        except Exception as e:
            logger.error(f"SSO redirect error: {e}")
            # Fall through to fallback
            
            # Fallback: redirect to login page with prefilled credentials
            fallback_html = f'''
<!DOCTYPE html>
<html>
<head>
    <title>Redirecting to {sso_data['database']}</title>
    <meta http-equiv="refresh" content="3;url={tenant_url}/web/login">
    <style>
        body {{
            font-family: Inter, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #0066cc 0%, #004499 100%);
            color: white;
            text-align: center;
        }}
        .container {{
            max-width: 500px;
            padding: 40px;
        }}
        .credentials {{
            background: rgba(255,255,255,0.1);
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
            backdrop-filter: blur(10px);
        }}
        .credential-item {{
            margin: 10px 0;
            padding: 8px;
            background: rgba(255,255,255,0.2);
            border-radius: 5px;
            font-family: monospace;
        }}
        .spinner {{
            border: 4px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top: 4px solid white;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 20px auto;
        }}
        @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
        .error {{
            background: rgba(255,0,0,0.1);
            border: 1px solid rgba(255,0,0,0.3);
            padding: 15px;
            border-radius: 5px;
            margin: 10px 0;
        }}
        .btn {{
            display: inline-block;
            padding: 12px 24px;
            background: rgba(255,255,255,0.2);
            color: white;
            text-decoration: none;
            border-radius: 5px;
            margin: 10px;
            transition: background 0.3s;
        }}
        .btn:hover {{
            background: rgba(255,255,255,0.3);
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="spinner"></div>
        <h2>Opening {sso_data['database']}</h2>
        
        <div class="error">
            <i>Auto-login failed, redirecting to login page...</i>
        </div>
        
        <div class="credentials">
            <h4>Your Login Credentials:</h4>
            <div class="credential-item">
                <strong>Username:</strong> {sso_data['username']}
            </div>
            <div class="credential-item">
                <strong>Database:</strong> {sso_data['database']}
            </div>
            <p style="font-size: 0.9em; opacity: 0.8;">Enter your password to continue</p>
        </div>
        
        <p>You will be redirected to the login page in 3 seconds...</p>
        <a href="{tenant_url}/web/login" class="btn">Click Here to Login Now</a>
    </div>
    
    <script>
        // Auto-redirect after 3 seconds
        setTimeout(function() {{
            window.location.href = '{tenant_url}/web/login?login={sso_data['username']}&db={sso_data['database']}';
        }}, 3000);
    </script>
</body>
</html>'''
            return fallback_html
        
    except Exception as e:
        error_tracker.log_error(e, {'token': token})
        flash('SSO proxy login failed. Please try again.', 'error')
        return redirect(url_for('dashboard'))

def _generate_cookie_js(cookies, database):
    """Generate JavaScript to set cookies in the browser"""
    js_lines = []
    
    # Don't set domain for same-origin cookies - let them work on the current domain
    for cookie in cookies:
        # Create document.cookie statement for each cookie  
        cookie_value = f"{cookie.name}={cookie.value}"
        cookie_attrs = ["path=/"]
        
        # Don't add httponly flag in JavaScript (can't be set via JS)
        # Only add secure if we're on HTTPS
        cookie_attrs.append("secure")
        
        cookie_str = cookie_value + "; " + "; ".join(cookie_attrs)
        js_lines.append(f'document.cookie = "{cookie_str}";')
        js_lines.append(f'console.log("Set cookie: {cookie.name}");')
    
    return "\n        ".join(js_lines)

# Add error handler for payment-related errors
@app.errorhandler(404)
def payment_required(error):
    """Handle payment required errors"""
    return render_template('errors/payment_required.html'), 404

# Add these helper functions


@track_errors('profile_image_processing')
def save_profile_picture(form_picture, username):
    """Save and process profile picture"""
    try:
        random_hex = secrets.token_hex(8)
        _, f_ext = os.path.splitext(form_picture.filename)
        
        # Validate file extension
        allowed_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
        if f_ext.lower() not in allowed_extensions:
            raise ValueError("Invalid file extension")
        
        picture_fn = f"profile_{username}_{random_hex}{f_ext.lower()}"
        
        # Use app.root_path instead of current_app.root_path
        # Or use a direct path if you know your app structure
        upload_path = os.path.join(app.root_path, 'static', 'uploads', 'profiles')
        # Alternative: use absolute path
        # upload_path = os.path.join(os.getcwd(), 'static', 'uploads', 'profiles')
        
        os.makedirs(upload_path, exist_ok=True)
        
        picture_path = os.path.join(upload_path, picture_fn)
        
        # Process and save image
        with Image.open(form_picture) as img:
            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            
            # Resize to 300x300
            img.thumbnail((300, 300), Image.Resampling.LANCZOS)
            
            # Create square image
            square_img = Image.new('RGB', (300, 300), (255, 255, 255))
            x = (300 - img.width) // 2
            y = (300 - img.height) // 2
            square_img.paste(img, (x, y))
            
            square_img.save(picture_path, 'JPEG', quality=85, optimize=True)
        
        return picture_fn
        
    except Exception as e:
        error_tracker.log_error(e, {
            'username': username, 
            'function': 'save_profile_picture',
            'filename': getattr(form_picture, 'filename', 'unknown')
        })
        return None

@track_errors('allowed_file_check')
def allowed_file(filename):
    """Check if uploaded file is allowed"""
    if not filename or '.' not in filename:
        return False
    
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    extension = filename.rsplit('.', 1)[1].lower()
    return extension in ALLOWED_EXTENSIONS

def delete_profile_picture(filename):
    """Delete a profile picture file"""
    if not filename:
        return True
    
    try:
        picture_path = os.path.join(
            app.root_path, 'static', 'uploads', 'profiles', filename
        )
        if os.path.exists(picture_path):
            os.remove(picture_path)
        return True
    except Exception as e:
        error_tracker.log_error(e, {'filename': filename, 'function': 'delete_profile_picture'})
        return False

@track_errors('sync_tenant_user_limits')
def sync_tenant_user_limits(tenant_id):
    """Sync user limits with Odoo instance when plan changes"""
    try:
        tenant = Tenant.query.get(tenant_id)
        if not tenant:
            logger.warning(f"Tenant {tenant_id} not found for user limit sync")
            return False
        
        # Get plan details
        plan = SubscriptionPlan.query.filter_by(name=tenant.plan).first()
        max_users = plan.max_users if plan else tenant.max_users
        
        # Update tenant max_users if it differs from plan
        if tenant.max_users != max_users:
            tenant.max_users = max_users
            tenant.updated_at = datetime.utcnow()
            db.session.commit()
            logger.info(f"Updated tenant {tenant.subdomain} max_users to {max_users}")
        
        # Try to notify Odoo instance about the limit change
        try:
            import xmlrpc.client
            
            # Connect to Odoo and update SaaS config
            odoo_url = os.environ.get('ODOO_URL', 'http://odoo_master:8069')
            db_name = f"kdoo_{tenant.subdomain}"
            
            # Use admin credentials to update the config
            common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common")
            uid = common.authenticate(db_name, tenant.admin_username, tenant.get_admin_password(), {})
            
            if uid:
                models = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/object")
                
                # Search for existing SaaS controller config
                config_ids = models.execute_kw(
                    db_name, uid, tenant.get_admin_password(),
                    'saas.controller', 'search',
                    [[('database_name', '=', db_name)]]
                )
                
                if config_ids:
                    # Update existing config
                    models.execute_kw(
                        db_name, uid, tenant.get_admin_password(),
                        'saas.controller', 'write',
                        [config_ids, {'max_users': max_users}]
                    )
                else:
                    # Create new config
                    models.execute_kw(
                        db_name, uid, tenant.get_admin_password(),
                        'saas.controller', 'create',
                        [{'database_name': db_name, 'max_users': max_users}]
                    )
                
                logger.info(f"Successfully synced user limit {max_users} to Odoo for tenant {tenant.subdomain}")
                return True
            else:
                logger.warning(f"Failed to authenticate with Odoo for tenant {tenant.subdomain}")
                
        except Exception as odoo_error:
            logger.warning(f"Failed to sync user limit to Odoo for tenant {tenant.subdomain}: {odoo_error}")
        
        return True  # Return True even if Odoo sync failed, as SaaS Manager was updated
        
    except Exception as e:
        error_tracker.log_error(e, {'tenant_id': tenant_id, 'function': 'sync_tenant_user_limits'})
        return False

# Add these routes to your app.py


@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
@track_errors('edit_profile_route')
def edit_profile():
    form = ProfileForm()
    
    if request.method == 'GET':
        # Pre-populate form with current user data
        form.username.data = current_user.username
        form.email.data = current_user.email
        form.full_name.data = current_user.full_name or ''
        form.bio.data = current_user.bio or ''
        form.company.data = current_user.company or ''
        form.location.data = current_user.location or ''
        form.website.data = current_user.website or ''
        form.timezone.data = current_user.timezone or 'UTC'
        form.language.data = current_user.language or 'en'
    
    if form.validate_on_submit():
        try:
            # Check username uniqueness
            existing_user = SaasUser.query.filter(
                SaasUser.username == form.username.data,
                SaasUser.id != current_user.id
            ).first()
            if existing_user:
                flash('Username already exists. Please choose a different one.', 'error')
                return render_template('edit_profile.html', form=form)
            
            # Check email uniqueness
            existing_email = SaasUser.query.filter(
                SaasUser.email == form.email.data,
                SaasUser.id != current_user.id
            ).first()
            if existing_email:
                flash('Email already exists. Please choose a different one.', 'error')
                return render_template('edit_profile.html', form=form)
            
            # Verify current password if changing password
            if form.new_password.data:
                if not form.current_password.data:
                    flash('Current password is required to set a new password.', 'error')
                    return render_template('edit_profile.html', form=form)
                
                if not check_password_hash(current_user.password_hash, form.current_password.data):
                    flash('Current password is incorrect.', 'error')
                    return render_template('edit_profile.html', form=form)
            
            # Handle profile picture upload
            profile_picture_updated = False
            if 'profile_picture' in request.files:
                file = request.files['profile_picture']
                if file and file.filename and allowed_file(file.filename):
                    # Delete old picture first
                    if current_user.profile_picture:
                        delete_profile_picture(current_user.profile_picture)
                    
                    # Save new picture
                    picture_file = save_profile_picture(file, form.username.data)
                    if picture_file:
                        current_user.profile_picture = picture_file
                        profile_picture_updated = True
                    else:
                        flash('Failed to upload profile picture. Please try again.', 'warning')
            
            # Update user information
            current_user.username = form.username.data
            current_user.email = form.email.data
            current_user.full_name = form.full_name.data or None
            current_user.bio = form.bio.data or None
            current_user.company = form.company.data or None
            current_user.location = form.location.data or None
            current_user.website = form.website.data or None
            current_user.timezone = form.timezone.data or 'UTC'
            current_user.language = form.language.data or 'en'
            
            # Update password if provided
            if form.new_password.data:
                current_user.password_hash = generate_password_hash(form.new_password.data)
                current_user.last_password_change = datetime.utcnow()
            
            # Commit changes first
            db.session.commit()
            
            # Create audit log - FIXED VERSION
            try:
                audit_log = AuditLog(
                    user_id=current_user.id,
                    action='profile_updated',
                    details={
                        'username': form.username.data,
                        'email': form.email.data,
                        'password_changed': bool(form.new_password.data),
                        'profile_picture_updated': profile_picture_updated
                    },
                    ip_address=request.remote_addr,
                    user_agent=str(request.user_agent)  # This field now exists
                )
                db.session.add(audit_log)
                db.session.commit()
            except Exception as audit_error:
                # Don't fail the entire update if audit logging fails
                logger.warning(f"Failed to create audit log: {audit_error}")
                error_tracker.log_error(audit_error, {
                    'user_id': current_user.id,
                    'action': 'audit_log_creation_failed'
                })
            
            flash('Your profile has been updated successfully!', 'success')
            return redirect(url_for('view_profile'))
            
        except Exception as e:
            db.session.rollback()
            error_tracker.log_error(e, {
                'user_id': current_user.id,
                'form_data': {
                    'username': form.username.data,
                    'email': form.email.data
                }
            })
            flash('An error occurred while updating your profile. Please try again.', 'error')
    
    return render_template('edit_profile.html', form=form)

@app.route('/profile')
@login_required
@track_errors('view_profile_route')
def view_profile():
    """View user profile"""
    try:
        # Get user's tenants
        user_tenants = cache_manager.get_user_tenants(current_user.id)
        
        # Get recent activity (last 10 audit logs), excluding system-level activities
        system_actions = ['redis_flush', 'system_maintenance', 'cache_clear', 'backup_created']
        recent_activity = AuditLog.query.filter_by(user_id=current_user.id)\
            .filter(~AuditLog.action.in_(system_actions))\
            .order_by(AuditLog.created_at.desc())\
            .limit(10).all()
        
        # Add the current datetime for template calculations
        now = datetime.utcnow()
        
        return render_template('view_profile.html', 
                             user=current_user, 
                             tenants=user_tenants,
                             recent_activity=recent_activity,
                             now=now)  # Add this line
    except Exception as e:
        error_tracker.log_error(e, {'user_id': current_user.id})
        flash('Error loading profile. Please try again.', 'error')
        return redirect(url_for('dashboard'))


@app.route('/api/profile/upload-avatar', methods=['POST'])
@login_required
@track_errors('upload_avatar_api')
def upload_avatar():
    """API endpoint for avatar upload via AJAX"""
    try:
        if 'avatar' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['avatar']
        if not file or not file.filename:
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'File type not allowed. Use PNG, JPG, JPEG, GIF, or WebP'}), 400
        
        # Check file size (5MB max)
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > 5 * 1024 * 1024:
            return jsonify({'error': 'File too large (max 5MB)'}), 400
        
        # Delete old profile picture
        old_picture = current_user.profile_picture
        if old_picture:
            delete_profile_picture(old_picture)
        
        # Save new picture
        picture_file = save_profile_picture(file, current_user.username)
        if not picture_file:
            return jsonify({'error': 'Failed to process image'}), 500
        
        # Update database
        current_user.profile_picture = picture_file
        current_user.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Create audit log - FIXED VERSION
        try:
            audit_log = AuditLog(
                user_id=current_user.id,
                action='avatar_updated',
                details={'filename': picture_file},
                ip_address=request.remote_addr,
                user_agent=str(request.user_agent)  # Now properly included
            )
            db.session.add(audit_log)
            db.session.commit()
        except Exception as audit_error:
            # Don't fail the upload if audit logging fails
            logger.warning(f"Failed to create audit log for avatar upload: {audit_error}")
        
        avatar_url = url_for('static', filename=f'uploads/profiles/{picture_file}')
        return jsonify({
            'success': True,
            'avatar_url': avatar_url,
            'message': 'Avatar updated successfully!'
        })
        
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'user_id': current_user.id})
        return jsonify({'error': 'Failed to upload avatar'}), 500

# FIXED delete_avatar route - replace in app.py:

@app.route('/api/profile/delete-avatar', methods=['POST'])
@login_required
@track_errors('delete_avatar_api')
def delete_avatar():
    """API endpoint to delete user avatar"""
    try:
        old_picture = current_user.profile_picture
        
        if old_picture:
            # Delete file from filesystem
            delete_profile_picture(old_picture)
            
            # Update database
            current_user.profile_picture = None
            current_user.updated_at = datetime.utcnow()
            db.session.commit()
            
            # Create audit log - FIXED VERSION
            try:
                audit_log = AuditLog(
                    user_id=current_user.id,
                    action='avatar_deleted',
                    details={'old_filename': old_picture},
                    ip_address=request.remote_addr,
                    user_agent=str(request.user_agent)  # Now properly included
                )
                db.session.add(audit_log)
                db.session.commit()
            except Exception as audit_error:
                # Don't fail the deletion if audit logging fails
                logger.warning(f"Failed to create audit log for avatar deletion: {audit_error}")
        
        return jsonify({
            'success': True,
            'message': 'Avatar deleted successfully!'
        })
        
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'user_id': current_user.id})
        return jsonify({'error': 'Failed to delete avatar'}), 500

@app.route('/billing/overview')
@login_required
@track_errors('billing_overview_route')
def billing_overview():
    """Billing overview page showing all tenant billing status and transaction logs"""
    try:
        from billing_service import BillingService
        billing_service = BillingService()
        
        # Get all tenants for the current user
        if current_user.is_admin:
            # Admin can see all tenants
            tenants = Tenant.query.order_by(Tenant.created_at.desc()).all()
        else:
            # Regular user sees only their tenants
            tenant_users = TenantUser.query.filter_by(user_id=current_user.id).all()
            tenant_ids = [tu.tenant_id for tu in tenant_users]
            tenants = Tenant.query.filter(Tenant.id.in_(tenant_ids)).order_by(Tenant.created_at.desc()).all()
        
        # Enhance tenants with detailed billing information
        enhanced_tenants = []
        for tenant in tenants:
            billing_info = billing_service.get_tenant_billing_info(tenant.id)
            
            # Add billing info as tenant attributes
            tenant.billing_info = billing_info
            tenant.domain_url = get_tenant_domain_url(tenant)
            
            # Calculate accurate billing status
            if billing_info and billing_info.get('status') != 'no_active_cycle':
                # Tenant has an active billing cycle
                is_expired = billing_info.get('is_expired', False)
                days_remaining = billing_info.get('days_remaining', 0)
                hours_remaining = billing_info.get('hours_remaining', 0)
                
                if is_expired:
                    tenant.billing_status = 'expired'
                    tenant.billing_status_label = '❌ Expired'
                    tenant.billing_status_class = 'danger'
                elif days_remaining <= 2 and hours_remaining <= 48:
                    # Critical - less than 2 days or 48 hours
                    if days_remaining > 0:
                        tenant.billing_status = 'expiring_soon'
                        tenant.billing_status_label = f'⚠️ Expires in {days_remaining}d'
                        tenant.billing_status_class = 'warning'
                    elif hours_remaining > 0:
                        tenant.billing_status = 'expiring_soon'
                        tenant.billing_status_label = f'⚠️ Expires in {hours_remaining:.0f}h'
                        tenant.billing_status_class = 'warning'
                    else:
                        tenant.billing_status = 'expired'
                        tenant.billing_status_label = '❌ Expired'
                        tenant.billing_status_class = 'danger'
                elif days_remaining <= 7:
                    # Warning - less than 7 days
                    tenant.billing_status = 'expiring_soon'
                    tenant.billing_status_label = f'⚠️ Expires in {days_remaining}d'
                    tenant.billing_status_class = 'warning'
                else:
                    # Active with sufficient time
                    tenant.billing_status = 'active'
                    tenant.billing_status_label = f'✅ Active ({days_remaining}d left)'
                    tenant.billing_status_class = 'success'
            else:
                # No billing cycle or inactive tenant
                if tenant.is_active and tenant.status == 'active':
                    # Just activated, billing cycle should be created
                    tenant.billing_status = 'pending'
                    tenant.billing_status_label = '🔄 Initializing'
                    tenant.billing_status_class = 'info'
                else:
                    # Truly expired or inactive
                    tenant.billing_status = 'expired'
                    tenant.billing_status_label = '❌ Payment Required'
                    tenant.billing_status_class = 'danger'
            
            enhanced_tenants.append(tenant)
        
        # Get payment transactions for the user's tenants
        tenant_ids = [t.id for t in tenants]
        
        if current_user.is_admin:
            # Admin sees all transactions
            transactions = PaymentTransaction.query.order_by(PaymentTransaction.created_at.desc()).limit(50).all()
        else:
            # User sees only their transactions
            transactions = PaymentTransaction.query.filter(
                PaymentTransaction.user_id == current_user.id
            ).order_by(PaymentTransaction.created_at.desc()).limit(50).all()
        
        # Calculate billing summary
        total_tenants = len(tenants)
        active_tenants = len([t for t in tenants if t.is_active and (not hasattr(t, 'billing_info') or not t.billing_info or not t.billing_info.get('is_expired', False))])
        expired_tenants = len([t for t in tenants if hasattr(t, 'billing_info') and t.billing_info and t.billing_info.get('is_expired', False)])
        total_spent = sum([t.amount for t in transactions if t.status == 'VALIDATED'])
        pending_payments = len([t for t in transactions if t.status == 'PENDING'])
        
        billing_summary = {
            'total_tenants': total_tenants,
            'active_tenants': active_tenants,
            'inactive_tenants': total_tenants - active_tenants,
            'expired_tenants': expired_tenants,
            'total_spent': total_spent,
            'pending_payments': pending_payments,
            'recent_transactions': len(transactions)
        }
        
        return render_template('billing/billing_overview.html', 
                             tenants=enhanced_tenants,
                             transactions=transactions,
                             billing_summary=billing_summary,
                             now=datetime.utcnow())
        
    except Exception as e:
        error_tracker.log_error(e, {'user_id': current_user.id, 'function': 'billing_overview'})
        flash('Error loading billing overview. Please try again.', 'error')
        return redirect(url_for('dashboard'))

# Add this after your app initialization in app.py

@app.template_global()
def now():
    """Make current datetime available to all templates"""
    return datetime.utcnow()

# Static content pages
@app.route('/pricing')
def pricing():
    """Pricing page"""
    return render_template('pages/pricing.html')

@app.route('/security')
def security():
    """Security page"""
    return render_template('pages/security.html')

@app.route('/enterprise')
def enterprise():
    """Enterprise page"""
    return render_template('pages/enterprise.html')

@app.route('/careers')
def careers():
    """Careers page"""
    return render_template('pages/careers.html')

@app.route('/blog')
def blog():
    """Blog page"""
    return render_template('pages/blog.html')

@app.route('/press')
def press():
    """Press page"""
    return render_template('pages/press.html')

@app.route('/documentation')
def documentation():
    """Documentation page"""
    return render_template('pages/documentation.html')

@app.route('/api-reference')
def api_reference():
    """API Reference page"""
    return render_template('pages/api_reference.html')

@app.route('/tutorials')
def tutorials():
    """Tutorials page"""
    return render_template('pages/tutorials.html')

@app.route('/community')
def community():
    """Community page"""
    return render_template('pages/community.html')

@app.route('/help-center')
def help_center():
    """Help Center page"""
    return render_template('pages/help_center.html')

@app.route('/status')
def status_page():
    """Status page"""
    return render_template('pages/status.html')

@app.route('/terms')
def service_terms():
    """Service Terms page"""
    return render_template('pages/terms.html')

@app.route('/about')
def about():
    """About page"""
    return render_template('pages/about.html')

@app.route('/contact')
def contact():
    """Contact page"""
    return render_template('pages/contact.html')


# Modal fix testing routes
@app.route('/test-modal-fix')
def test_modal_fix():
    """Serve modal fix test page"""
    try:
        with open('/home/kendroo/odoo-multi-tenant-system/FRONTEND_TEST.html', 'r') as f:
            content = f.read()
        return content
    except Exception as e:
        return f"Error loading test page: {str(e)}", 500

@app.route('/test-nuclear-modal')
def test_nuclear_modal():
    """Serve nuclear modal test page"""
    try:
        with open('/home/kendroo/odoo-multi-tenant-system/NUCLEAR_MODAL_TEST.html', 'r') as f:
            content = f.read()
        return content
    except Exception as e:
        return f"Error loading nuclear test page: {str(e)}", 500

# Template context processors
@app.context_processor
def inject_now():
    """Inject current datetime into all template contexts"""
    return {'now': datetime.utcnow()}

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    logger.info(f"Starting Flask application with SocketIO on port {port}")
    socketio.run(
        app, 
        host='0.0.0.0', 
        port=port, 
        debug=debug, 
        allow_unsafe_werkzeug=True,
        use_reloader=False  # Prevent double initialization in debug mode
    )