#!/usr/bin/env python3
"""
Odoo SaaS Management Application with Enhanced Error Tracking and Redis Integration
Main Flask application for managing Odoo tenants
"""

import os
import logging
import sys
import traceback
import inspect
from datetime import datetime, timedelta
from functools import wraps
import secrets
import string
import xmlrpc.client
import requests
import docker
import redis
import bcrypt
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, make_response, send_file
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_session import Session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from wtforms import StringField, PasswordField, SelectField, IntegerField, BooleanField
from wtforms.validators import DataRequired, Length, NumberRange, ValidationError
import re
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import base64
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.exceptions import InvalidSignature
import hashlib
from factory import create_app, init_db
from utils import error_tracker, logger, track_errors
from db import db
from models import SaasUser, Tenant, TenantUser, SubscriptionPlan, WorkerInstance, UserPublicKey, CredentialAccess, Report, AuditLog
from billing import BillingService

try:
    from .master_admin import master_admin_bp
except ImportError:
    from master_admin import master_admin_bp
    
try:
    from .OdooDatabaseManager import OdooDatabaseManager
except ImportError:
    from OdooDatabaseManager import OdooDatabaseManager
    
try:
    from .TenantLogManager import TenantLogManager
except ImportError:
    from TenantLogManager import TenantLogManager

def run_async_in_background(coro):
    """Helper function to run an async coroutine in the background."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(coro)
    finally:
        loop.close()

# Create Flask app
app = create_app()
init_db(app)
app.register_blueprint(master_admin_bp)

# Initialize Odoo manager and other services
odoo = OdooDatabaseManager(odoo_url="http://odoo_master:8069", master_pwd=os.environ.get('ODOO_MASTER_PASSWORD', 'admin123'))
print(f"Using Odoo URL: {odoo.odoo_url}")
print(f"Using Odoo Master Password: {odoo.master_pwd}")

# Initialize Redis client
redis_client = None
try:
    redis_client = redis.Redis.from_url(os.environ.get('REDIS_URL', 'redis://redis:6379/0'))
    redis_client.ping()
    logger.info("Redis client initialized successfully")
except redis.ConnectionError as e:
    error_tracker.log_error(e, {'component': 'redis_initialization'})
    redis_client = None
except Exception as e:
    error_tracker.log_error(e, {'component': 'redis_initialization'})
    redis_client = None

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
        default_limits=["200 per day", "50 per hour"],
        storage_uri=os.environ.get('REDIS_URL', 'redis://redis:6379/0')
    )
    limiter.init_app(app)
else:
    logger.warning("Redis not available, rate limiting disabled")
    limiter = None

docker_client = None
try:
    docker_client = docker.from_env()
    docker_client.ping()
    logger.info("Docker client initialized successfully")
except docker.errors.DockerException as e:
    error_tracker.log_error(e, {'component': 'docker_initialization'})
    docker_client = None
except Exception as e:
    error_tracker.log_error(e, {'component': 'docker_initialization'})
    docker_client = None

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
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])

@track_errors('register_form_validation')
class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=50)])
    email = StringField('Email', validators=[DataRequired(), email_validator])
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

# Caching helper functions
def get_cached_user_tenants(user_id):
    if not redis_client:
        return fetch_user_tenants_from_db(user_id)
    cache_key = f"user_tenants:{user_id}"
    try:
        cached_data = redis_client.get(cache_key)
        if cached_data:
            return json.loads(cached_data)
    except Exception as e:
        logger.warning(f"Redis error in get_cached_user_tenants: {e}")
    tenant_data = fetch_user_tenants_from_db(user_id)
    try:
        redis_client.setex(cache_key, 300, json.dumps(tenant_data))  # Cache for 5 minutes
    except Exception as e:
        logger.warning(f"Failed to cache user tenants: {e}")
    return tenant_data

def fetch_user_tenants_from_db(user_id):
    tenants = db.session.query(Tenant).join(TenantUser).filter(TenantUser.user_id == user_id).all()
    return [
        {
            'id': t.id,
            'name': t.name,
            'subdomain': t.subdomain,
            'status': t.status,
            'plan': t.plan,
            'created_at': t.created_at.strftime('%Y-%m-%d') if t.created_at else None
        }
        for t in tenants
    ]

def get_cached_admin_stats():
    if not redis_client:
        return fetch_admin_stats_from_db()
    cache_key = "admin_stats"
    try:
        cached_data = redis_client.get(cache_key)
        if cached_data:
            return json.loads(cached_data)
    except Exception as e:
        logger.warning(f"Redis error in get_cached_admin_stats: {e}")
    stats = fetch_admin_stats_from_db()
    try:
        redis_client.setex(cache_key, 300, json.dumps(stats))  # Cache for 5 minutes
    except Exception as e:
        logger.warning(f"Failed to cache admin stats: {e}")
    return stats

def fetch_admin_stats_from_db():
    return {
        'total_tenants': Tenant.query.count(),
        'active_tenants': Tenant.query.filter_by(status='active').count(),
        'total_users': SaasUser.query.count(),
        'worker_instances': WorkerInstance.query.count()
    }

@track_errors('database_creation')
async def create_database(db_name, username='admin', password='admin', modules=None):
    if redis_client:
        cache_key = f"db_creation_status:{db_name}"
        try:
            redis_client.set(cache_key, "pending")
        except Exception as e:
            logger.warning(f"Failed to set Redis status for {db_name}: {e}")
    
    default_modules = ['base', 'web', 'auth_signup']
    if modules is None:
        modules = default_modules
    else:
        modules = list(set(modules) | set(default_modules))
    
    try:
        if redis_client:
            redis_client.set(cache_key, "in_progress")
        
        logger.info(f"Creating database {db_name}")
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
            if redis_client:
                redis_client.set(cache_key, "failed")
            return False
        
        logger.info(f"Database {db_name} created successfully")
            
        common = xmlrpc.client.ServerProxy(f"{os.environ.get('ODOO_URL', 'http://odoo_master:8069')}/xmlrpc/2/common")
        uid = common.authenticate(db_name, username, password, {})
        
        if not uid:
            logger.error(f"Authentication failed for database {db_name}")
            if redis_client:
                redis_client.set(cache_key, "failed")
            return False
        
        models = xmlrpc.client.ServerProxy(f"{os.environ.get('ODOO_URL', 'http://odoo_master:8069')}/xmlrpc/2/object")
        
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
        
        logger.info(f"Database {db_name} created and configured successfully")
        if redis_client:
            redis_client.set(cache_key, "completed")
        return True
    
    except requests.exceptions.Timeout:
        logger.error(f"Database creation timed out for {db_name}")
        error_tracker.log_error(Exception("Database creation timeout"), {'database_name': db_name})
        if redis_client:
            redis_client.set(cache_key, "failed")
        return False
        
    except Exception as e:
        logger.error(f"Error creating database {db_name}: {str(e)}")
        error_tracker.log_error(e, {'database_name': db_name})
        if redis_client:
            redis_client.set(cache_key, "failed")
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
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
@track_errors('login_route')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    form = LoginForm()
    if form.validate_on_submit():
        try:
            user = SaasUser.query.filter_by(username=form.username.data).first()
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

@app.route('/dashboard')
@login_required
@track_errors('dashboard_route')
def dashboard():
    try:
        user_tenants = get_cached_user_tenants(current_user.id)
        stats = {}
        if current_user.is_admin:
            stats = get_cached_admin_stats()
        return render_template('dashboard.html', tenants=user_tenants, stats=stats)
    except Exception as e:
        error_tracker.log_error(e, {'user_id': current_user.id})
        flash('Error loading dashboard. Please try again.', 'error')
        return render_template('dashboard.html', tenants=[], stats={})

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
            
            subscription_plan = SubscriptionPlan.query.filter_by(name=form.plan.data).first()
            plan_modules = subscription_plan.modules if subscription_plan.modules else []
            
            executor = ThreadPoolExecutor(max_workers=1)
            executor.submit(run_async_in_background, create_database(db_name, admin_username, admin_password, plan_modules))
            executor.shutdown(wait=False)
            
            tenant = Tenant(
                name=form.name.data,
                subdomain=form.subdomain.data,
                database_name=db_name,
                plan=form.plan.data,
                admin_username=admin_username,
                status='pending'
            )
            tenant.set_admin_password(admin_password)
            
            db.session.add(tenant)
            db.session.flush()
            
            tenant_user = TenantUser(tenant_id=tenant.id, user_id=current_user.id, role='admin')
            db.session.add(tenant_user)
            worker.current_tenants += 1
            db.session.commit()
            
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
        modules = odoo.get_installed_applications_count(tenant.database_name, tenant.admin_username, tenant.get_admin_password())
        storage_usage = odoo.get_database_storage_usage(tenant.database_name)['total_size_human']
        uptime = odoo.get_tenant_uptime(tenant.database_name)['uptime_human']
        odoo_user = odoo.get_users_count(tenant.database_name, tenant.admin_username, tenant.get_admin_password())['total_users']
        return render_template('manage_tenant.html', tenant=tenant, modules=modules, storage_usage=storage_usage, uptime=uptime, odoo_user=odoo_user)
    except Exception as e:
        error_tracker.log_error(e, {'tenant_id': tenant_id, 'user_id': current_user.id})
        flash('Error accessing tenant. Please try again.', 'error')
        return redirect(url_for('dashboard'))

@app.route('/admin/tenants')
@admin_required
@track_errors('admin_tenants_route')
def admin_tenants():
    try:
        tenants = Tenant.query.all()
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
        tenant_url = f"http://{tenant_subdomain}.{domain}"
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
        tenant_url = f"http://{tenant_subdomain}.{domain}"
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
        tenant_url = f"http://{tenant_subdomain}.{domain}"
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
            target_url = f"http://{subdomain}.{os.environ.get('DOMAIN', 'odoo-bangladesh.com')}/web"
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
        return jsonify({
            'id': tenant.id,
            'name': tenant.name,
            'subdomain': tenant.subdomain,
            'status': tenant.status,
            'plan': tenant.plan,
            'created_at': tenant.created_at.isoformat()
        })
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

@app.route('/tenant/<int:tenant_id>/delete', methods=['POST'])
@login_required
@track_errors('delete_tenant_route')
def delete_tenant(tenant_id):
    tenant = Tenant.query.get_or_404(tenant_id)
    try:
        logger.info(f"Deleting tenant: {tenant.name} (ID: {tenant.id})")
        TenantUser.query.filter_by(tenant_id=tenant.id).delete()
        CredentialAccess.query.filter_by(tenant_id=tenant.id).delete()
        db.session.delete(tenant)
        db.session.commit()
        odoo.delete(tenant.database_name)
        flash('Tenant deleted successfully.', 'success')
    except Exception as e:
        flash(f'Deletion failed: {e}', 'danger')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    logger.info(f"Starting Flask application on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)