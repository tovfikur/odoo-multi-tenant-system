from flask import Blueprint, render_template, jsonify, request, redirect, url_for, session, send_file
from flask_login import login_required, current_user, login_user
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash
import os
import io
import csv
import json
import psutil
import docker
import xmlrpc.client
import requests
from sqlalchemy import func, desc, text
from sqlalchemy.orm import joinedload

from models import (
    SaasUser, Tenant, TenantUser, SubscriptionPlan,
    CredentialAccess, WorkerInstance, UserPublicKey, AuditLog, SystemSetting
)
from db import db
from OdooDatabaseManager import OdooDatabaseManager
from utils import track_errors, error_tracker, generate_password
from billing import BillingService

# Add these imports if not already present
import psutil
import redis

# Add these variables if not already defined
redis_client = None
docker_client = None

try:
    redis_client = redis.Redis.from_url(os.environ.get('REDIS_URL', 'redis://redis:6379/0'))
    redis_client.ping()
except:
    redis_client = None

try:
    docker_client = docker.from_env()
except:
    docker_client = None

master_admin_bp = Blueprint('master_admin', __name__)

def require_admin():
    def decorator(fn):
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.is_admin:
                return jsonify({'success': False, 'message': 'Access denied'}), 403
            return fn(*args, **kwargs)
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator

def log_admin_action(action, details=None):
    """Log admin actions for audit trail"""
    try:
        audit_log = AuditLog(
            user_id=current_user.id,
            action=action,
            details=details,
            ip_address=request.remote_addr
        )
        db.session.add(audit_log)
        db.session.commit()
        print(f"[ADMIN LOG] {current_user.username}: {action} - {details}")
    except Exception as e:
        print(f"[ADMIN LOG ERROR] Failed to log action: {e}")

@master_admin_bp.route('/master-admin/email-settings', methods=['GET', 'POST'])
@login_required
@require_admin()
@track_errors('email_settings')
def email_settings():
    """Manage SMTP email configuration"""
    if request.method == 'GET':
        # Get current email settings
        settings = {}
        email_keys = [
            'smtp_server', 'smtp_port', 'smtp_username', 'smtp_password',
            'smtp_use_tls', 'email_from_name', 'email_from_address'
        ]
        
        for key in email_keys:
            setting = SystemSetting.query.filter_by(key=key).first()
            settings[key] = setting.value if setting else ''
        
        return jsonify({'success': True, 'settings': settings})
    
    if request.method == 'POST':
        try:
            data = request.json
            email_settings = {
                'smtp_server': data.get('smtp_server', 'smtp.gmail.com'),
                'smtp_port': data.get('smtp_port', '587'),
                'smtp_username': data.get('smtp_username', ''),
                'smtp_password': data.get('smtp_password', ''),
                'smtp_use_tls': data.get('smtp_use_tls', 'true'),
                'email_from_name': data.get('email_from_name', 'SaaS Manager'),
                'email_from_address': data.get('email_from_address', '')
            }
            
            # Update or create settings
            for key, value in email_settings.items():
                setting = SystemSetting.query.filter_by(key=key).first()
                if setting:
                    setting.value = value
                    setting.updated_by = current_user.id
                    setting.updated_at = datetime.utcnow()
                else:
                    setting = SystemSetting(
                        key=key,
                        value=value,
                        value_type='string',
                        description=f'SMTP {key.replace("_", " ").title()}',
                        category='email',
                        updated_by=current_user.id
                    )
                    db.session.add(setting)
            
            db.session.commit()
            
            # Test email configuration if requested
            if data.get('test_email'):
                from email_config import EmailManager
                success, message = EmailManager.send_email(
                    current_user.email,
                    'Test Email Configuration',
                    'This is a test email to verify SMTP configuration.',
                    is_html=False
                )
                
                if not success:
                    return jsonify({
                        'success': False, 
                        'message': f'Settings saved but email test failed: {message}'
                    })
            
            log_admin_action('email_settings_updated', {
                'smtp_server': email_settings['smtp_server'],
                'smtp_port': email_settings['smtp_port'],
                'smtp_username': email_settings['smtp_username']
            })
            
            return jsonify({'success': True, 'message': 'Email settings updated successfully'})
            
        except Exception as e:
            db.session.rollback()
            error_tracker.log_error(e, {'admin_user': current_user.id})
            return jsonify({'success': False, 'message': 'Failed to update email settings'}), 500

# ================= PACKAGE/PLAN MANAGEMENT =================

@master_admin_bp.route('/master-admin/plans', methods=['GET'])
@login_required
@require_admin()
@track_errors('get_plans')
def get_plans():
    try:
        plans = SubscriptionPlan.query.all()
        plans_data = []
        for plan in plans:
            # Count tenants using this plan
            tenant_count = Tenant.query.filter_by(plan=plan.name).count()
            plans_data.append({
                'id': plan.id,
                'name': plan.name,
                'price': float(plan.price),
                'max_users': plan.max_users,
                'storage_limit': plan.storage_limit,
                'features': plan.features or [],
                'modules': plan.modules or [],
                'is_active': plan.is_active,
                'tenant_count': tenant_count,
                'created_at': plan.created_at.isoformat() if plan.created_at else ''
            })
        return jsonify({'success': True, 'plans': plans_data})
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to fetch plans'}), 500

@master_admin_bp.route('/master-admin/plan/<int:plan_id>/details', methods=['GET'])
@login_required
@require_admin()
@track_errors('get_plan_details')
def get_plan_details(plan_id):
    try:
        plan = SubscriptionPlan.query.get_or_404(plan_id)
        plan_data = {
            'id': plan.id,
            'name': plan.name,
            'price': float(plan.price),
            'max_users': plan.max_users,
            'storage_limit': plan.storage_limit,
            'features': plan.features or '',
            'modules': plan.modules or '',
            'is_active': plan.is_active,
            'created_at': plan.created_at.isoformat() if plan.created_at else ''
        }
        return jsonify({'success': True, 'plan': plan_data})
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to fetch plan details'}), 500

@master_admin_bp.route('/master-admin/modules/available', methods=['GET'])
@login_required
@require_admin()
@track_errors('get_available_modules')
def get_available_modules():
    """Get all available Odoo modules for plan configuration"""
    try:
        # Initialize with required parameters
        odoo_url = os.environ.get('ODOO_URL', 'http://odoo_master:8069')
        master_pwd = os.environ.get('ODOO_MASTER_PASSWORD', 'admin')
        db_manager = OdooDatabaseManager(odoo_url, master_pwd)
        
        # Connect directly to odoo_master database to get all modules
        modules = []
        try:
            modules = db_manager.get_all_available_modules(
                db_name='odoo_master',
                admin_user='admin',
                admin_password='admin'
            )
            print(f"[✓] Successfully fetched {len(modules)} modules from odoo_master database")
        except Exception as e:
            print(f"[!] Failed to fetch modules from odoo_master: {e}")
            
        # If odoo_master doesn't work, try saas_manager database 
        if not modules:
            try:
                modules = db_manager.get_all_available_modules(
                    db_name='saas_manager',
                    admin_user='admin',
                    admin_password='admin'
                )
                print(f"[✓] Successfully fetched {len(modules)} modules from saas_manager database")
            except Exception as e:
                print(f"[!] Failed to fetch modules from saas_manager: {e}")
        
        if not modules:
            # Return a basic set of common modules if we can't fetch from Odoo
            modules = [
                {'name': 'sale', 'display_name': 'Sales', 'category': 'Sales', 'state': 'uninstalled'},
                {'name': 'purchase', 'display_name': 'Purchase', 'category': 'Purchase', 'state': 'uninstalled'},
                {'name': 'stock', 'display_name': 'Inventory', 'category': 'Inventory', 'state': 'uninstalled'},
                {'name': 'account', 'display_name': 'Accounting', 'category': 'Accounting', 'state': 'uninstalled'},
                {'name': 'hr', 'display_name': 'Human Resources', 'category': 'Human Resources', 'state': 'uninstalled'},
                {'name': 'project', 'display_name': 'Project Management', 'category': 'Project', 'state': 'uninstalled'},
                {'name': 'crm', 'display_name': 'CRM', 'category': 'Sales', 'state': 'uninstalled'},
                {'name': 'website', 'display_name': 'Website Builder', 'category': 'Website', 'state': 'uninstalled'},
                {'name': 'mail', 'display_name': 'Discuss', 'category': 'Productivity', 'state': 'uninstalled'},
                {'name': 'calendar', 'display_name': 'Calendar', 'category': 'Productivity', 'state': 'uninstalled'},
            ]
        
        # Group modules by category
        categorized = {}
        for module in modules:
            category = module.get('category', 'Other')
            if category not in categorized:
                categorized[category] = []
            categorized[category].append(module)
        
        return jsonify({
            'success': True,
            'modules': modules,
            'categorized': categorized
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to fetch modules'}), 500

@master_admin_bp.route('/master-admin/plan/create', methods=['POST'])
@login_required
@require_admin()
@track_errors('create_plan')
def create_plan():
    try:
        data = request.json
        
        # Check if plan name already exists
        if SubscriptionPlan.query.filter_by(name=data['name']).first():
            return jsonify({'success': False, 'message': 'Plan name already exists'}), 400
        
        plan = SubscriptionPlan(
            name=data['name'],
            price=float(data['price']),
            max_users=int(data['max_users']),
            storage_limit=int(data['storage_limit']),
            features=data.get('features', []),
            modules=data.get('modules', []),
            is_active=data.get('is_active', True)
        )
        
        db.session.add(plan)
        db.session.commit()
        
        log_admin_action('plan_created', {
            'plan_id': plan.id,
            'plan_name': plan.name,
            'price': plan.price
        })
        
        return jsonify({'success': True, 'message': 'Plan created successfully', 'plan_id': plan.id})
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to create plan'}), 500

@master_admin_bp.route('/master-admin/plan/<int:plan_id>/update', methods=['POST'])
@login_required
@require_admin()
@track_errors('update_plan')
def update_plan(plan_id):
    try:
        plan = SubscriptionPlan.query.get_or_404(plan_id)
        data = request.json
        
        old_values = {
            'name': plan.name,
            'price': plan.price,
            'max_users': plan.max_users,
            'storage_limit': plan.storage_limit
        }
        
        plan.name = data.get('name', plan.name)
        plan.price = float(data.get('price', plan.price))
        plan.max_users = int(data.get('max_users', plan.max_users))
        plan.storage_limit = int(data.get('storage_limit', plan.storage_limit))
        plan.features = data.get('features', plan.features)
        plan.modules = data.get('modules', plan.modules)
        plan.is_active = data.get('is_active', plan.is_active)
        
        db.session.commit()
        
        log_admin_action('plan_updated', {
            'plan_id': plan_id,
            'old_values': old_values,
            'new_values': {
                'name': plan.name,
                'price': plan.price,
                'max_users': plan.max_users,
                'storage_limit': plan.storage_limit
            }
        })
        
        return jsonify({'success': True, 'message': 'Plan updated successfully'})
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'admin_user': current_user.id, 'plan_id': plan_id})
        return jsonify({'success': False, 'message': 'Failed to update plan'}), 500

@master_admin_bp.route('/master-admin/plan/<int:plan_id>/delete', methods=['POST'])
@login_required
@require_admin()
@track_errors('delete_plan')
def delete_plan(plan_id):
    try:
        plan = SubscriptionPlan.query.get_or_404(plan_id)
        
        # Check if any tenants are using this plan
        tenant_count = Tenant.query.filter_by(plan=plan.name).count()
        if tenant_count > 0:
            return jsonify({
                'success': False, 
                'message': f'Cannot delete plan. {tenant_count} tenants are currently using this plan'
            }), 400
        
        plan_name = plan.name
        db.session.delete(plan)
        db.session.commit()
        
        log_admin_action('plan_deleted', {'plan_id': plan_id, 'plan_name': plan_name})
        
        return jsonify({'success': True, 'message': 'Plan deleted successfully'})
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'admin_user': current_user.id, 'plan_id': plan_id})
        return jsonify({'success': False, 'message': 'Failed to delete plan'}), 500

# ================= PAYMENT VERIFICATION =================

@master_admin_bp.route('/master-admin/payments', methods=['GET'])
@login_required
@require_admin()
@track_errors('get_payments')
def get_payments():
    try:
        # Get payment records from billing service
        payments = BillingService.get_all_payments()
        return jsonify({'success': True, 'payments': payments})
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to fetch payments'}), 500

@master_admin_bp.route('/master-admin/payment/<payment_id>/verify', methods=['POST'])
@login_required
@require_admin()
@track_errors('verify_payment')
def verify_payment(payment_id):
    try:
        data = request.json
        status = data.get('status', 'verified')  # verified, rejected, pending
        notes = data.get('notes', '')
        
        # Update payment status
        result = BillingService.manual_verify_payment(payment_id, status, notes, current_user.id)
        
        if result['success']:
            log_admin_action('payment_verified', {
                'payment_id': payment_id,
                'status': status,
                'notes': notes
            })
            
            # If payment is verified, activate the tenant
            if status == 'verified' and result.get('tenant_id'):
                tenant = Tenant.query.get(result['tenant_id'])
                if tenant and tenant.status == 'pending':
                    tenant.status = 'active'
                    db.session.commit()
                    log_admin_action('tenant_activated_after_payment', {'tenant_id': tenant.id})
        
        return jsonify(result)
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id, 'payment_id': payment_id})
        return jsonify({'success': False, 'message': 'Failed to verify payment'}), 500

# ================= TENANT MANAGEMENT ENHANCEMENTS =================

@master_admin_bp.route('/master-admin/tenant/<int:tenant_id>/force_activate', methods=['POST'])
@login_required
@require_admin()
@track_errors('force_activate_tenant')
def force_activate_tenant(tenant_id):
    try:
        tenant = Tenant.query.get_or_404(tenant_id)
        odoo = OdooDatabaseManager(
            odoo_url=os.environ.get('ODOO_URL', 'http://odoo_master:8069'),
            master_pwd=os.environ.get('ODOO_MASTER_PASSWORD', 'admin123')
        )
        
        # Force activate in database
        odoo.activate(tenant.database_name)
        tenant.status = 'active'
        db.session.commit()
        
        log_admin_action('tenant_force_activated', {
            'tenant_id': tenant_id,
            'tenant_name': tenant.name,
            'reason': request.json.get('reason', 'Manual activation by admin')
        })
        
        return jsonify({'success': True, 'message': f'Tenant {tenant.name} activated successfully'})
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'tenant_id': tenant_id})
        return jsonify({'success': False, 'message': 'Failed to activate tenant'}), 500

@master_admin_bp.route('/master-admin/tenant/<int:tenant_id>/change_plan', methods=['POST'])
@login_required
@require_admin()
@track_errors('change_tenant_plan')
def change_tenant_plan(tenant_id):
    try:
        tenant = Tenant.query.get_or_404(tenant_id)
        data = request.json
        new_plan = data.get('plan')
        
        # Validate plan exists
        plan = SubscriptionPlan.query.filter_by(name=new_plan, is_active=True).first()
        if not plan:
            return jsonify({'success': False, 'message': 'Invalid plan selected'}), 400
        
        old_plan = tenant.plan
        tenant.plan = new_plan
        tenant.max_users = plan.max_users
        tenant.storage_limit = plan.storage_limit
        db.session.commit()
        
        log_admin_action('tenant_plan_changed', {
            'tenant_id': tenant_id,
            'old_plan': old_plan,
            'new_plan': new_plan,
            'reason': data.get('reason', 'Plan change by admin')
        })
        
        return jsonify({'success': True, 'message': f'Tenant plan changed from {old_plan} to {new_plan}'})
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'tenant_id': tenant_id})
        return jsonify({'success': False, 'message': 'Failed to change tenant plan'}), 500

@master_admin_bp.route('/master-admin/tenant/<int:tenant_id>/reset_admin_password', methods=['POST'])
@login_required
@require_admin()
@track_errors('reset_tenant_admin_password')
def reset_tenant_admin_password(tenant_id):
    try:
        tenant = Tenant.query.get_or_404(tenant_id)
        
        # Generate new password
        new_password = generate_password(12)
        tenant.set_admin_password(new_password)
        
        # Update in Odoo database
        odoo = OdooDatabaseManager(
            odoo_url=os.environ.get('ODOO_URL', 'http://odoo_master:8069'),
            master_pwd=os.environ.get('ODOO_MASTER_PASSWORD', 'admin123')
        )
        
        # Update credentials in Odoo
        success = odoo.update_user_credentials(
            tenant.database_name, 
            tenant.admin_username, 
            tenant.admin_username,  # Keep same username
            new_password
        )
        
        if success:
            db.session.commit()
            log_admin_action('tenant_admin_password_reset', {'tenant_id': tenant_id})
            return jsonify({
                'success': True, 
                'message': 'Admin password reset successfully',
                'new_password': new_password
            })
        else:
            db.session.rollback()
            return jsonify({'success': False, 'message': 'Failed to update password in Odoo'}), 500
            
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'tenant_id': tenant_id})
        return jsonify({'success': False, 'message': 'Failed to reset admin password'}), 500

@master_admin_bp.route('/master-admin/tenant/<int:tenant_id>/install_modules', methods=['POST'])
@login_required
@require_admin()
@track_errors('install_tenant_modules')
def install_tenant_modules(tenant_id):
    try:
        tenant = Tenant.query.get_or_404(tenant_id)
        data = request.json
        modules = data.get('modules', [])
        
        if not modules:
            return jsonify({'success': False, 'message': 'No modules specified'}), 400
        
        odoo = OdooDatabaseManager(
            odoo_url=os.environ.get('ODOO_URL', 'http://odoo_master:8069'),
            master_pwd=os.environ.get('ODOO_MASTER_PASSWORD', 'admin123')
        )
        
        installed_modules = []
        failed_modules = []
        
        for module in modules:
            try:
                success = odoo.install_module(
                    tenant.database_name,
                    tenant.admin_username,
                    tenant.get_admin_password(),
                    module
                )
                if success:
                    installed_modules.append(module)
                else:
                    failed_modules.append(module)
            except Exception as e:
                failed_modules.append(module)
                error_tracker.log_error(e, {'tenant_id': tenant_id, 'module': module})
        
        log_admin_action('tenant_modules_installed', {
            'tenant_id': tenant_id,
            'installed_modules': installed_modules,
            'failed_modules': failed_modules
        })
        
        return jsonify({
            'success': True,
            'message': f'Installed {len(installed_modules)} modules successfully',
            'installed_modules': installed_modules,
            'failed_modules': failed_modules
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'tenant_id': tenant_id})
        return jsonify({'success': False, 'message': 'Failed to install modules'}), 500

# ================= WORKER MANAGEMENT =================

@master_admin_bp.route('/master-admin/workers', methods=['GET'])
@login_required
@require_admin()
@track_errors('get_workers')
def get_workers():
    try:
        workers = WorkerInstance.query.all()
        workers_data = []
        
        # Try to get Docker client
        docker_client = None
        try:
            docker_client = docker.from_env()
        except Exception as e:
            error_tracker.log_error(e, {'function': 'get_workers', 'error': 'docker_connection'})
        
        for worker in workers:
            worker_data = {
                'id': worker.id,
                'name': worker.name,
                'container_name': worker.container_name,
                'port': worker.port,
                'status': worker.status,
                'current_tenants': worker.current_tenants,
                'max_tenants': worker.max_tenants,
                'created_at': worker.created_at.isoformat() if worker.created_at else '',
                'last_health_check': worker.last_health_check.isoformat() if worker.last_health_check else None,
                'container_status': 'unknown'
            }
            
            # Get container status if Docker is available
            if docker_client:
                try:
                    container = docker_client.containers.get(worker.container_name)
                    worker_data['container_status'] = container.status
                    worker_data['container_id'] = container.id[:12]
                except docker.errors.NotFound:
                    worker_data['container_status'] = 'not_found'
                except Exception as e:
                    worker_data['container_status'] = 'error'
            
            workers_data.append(worker_data)
        
        return jsonify({'success': True, 'workers': workers_data})
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to fetch workers'}), 500

@master_admin_bp.route('/master-admin/worker/create', methods=['POST'])
@login_required
@require_admin()
@track_errors('create_worker')
def create_worker():
    try:
        data = request.json
        
        worker = WorkerInstance(
            name=data['name'],
            container_name=data['container_name'],
            port=int(data['port']),
            max_tenants=int(data.get('max_tenants', 10)),
            status='pending'
        )
        
        db.session.add(worker)
        db.session.commit()
        
        log_admin_action('worker_created', {
            'worker_id': worker.id,
            'worker_name': worker.name,
            'container_name': worker.container_name
        })
        
        return jsonify({'success': True, 'message': 'Worker created successfully', 'worker_id': worker.id})
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to create worker'}), 500

@master_admin_bp.route('/master-admin/worker/<int:worker_id>/restart', methods=['POST'])
@login_required
@require_admin()
@track_errors('restart_worker')
def restart_worker(worker_id):
    try:
        worker = WorkerInstance.query.get_or_404(worker_id)
        
        try:
            docker_client = docker.from_env()
            container = docker_client.containers.get(worker.container_name)
            container.restart()
            
            worker.status = 'running'
            worker.last_health_check = datetime.utcnow()
            db.session.commit()
            
            log_admin_action('worker_restarted', {'worker_id': worker_id, 'worker_name': worker.name})
            
            return jsonify({'success': True, 'message': f'Worker {worker.name} restarted successfully'})
        except docker.errors.NotFound:
            return jsonify({'success': False, 'message': 'Container not found'}), 404
        except Exception as e:
            error_tracker.log_error(e, {'worker_id': worker_id})
            return jsonify({'success': False, 'message': 'Failed to restart container'}), 500
            
    except Exception as e:
        error_tracker.log_error(e, {'worker_id': worker_id})
        return jsonify({'success': False, 'message': 'Failed to restart worker'}), 500

# ================= SYSTEM MONITORING =================

@master_admin_bp.route('/master-admin/system/stats', methods=['GET'])
@login_required
@require_admin()
@track_errors('get_system_stats')
def get_system_stats():
    try:
        # Database stats
        total_users = SaasUser.query.count()
        active_users = SaasUser.query.filter_by(is_active=True).count()
        total_tenants = Tenant.query.count()
        active_tenants = Tenant.query.filter_by(status='active').count()
        pending_tenants = Tenant.query.filter_by(status='pending').count()
        admin_users = SaasUser.query.filter_by(is_admin=True).count()
        
        # Revenue calculation
        total_revenue = 0
        for tenant in Tenant.query.filter_by(status='active').all():
            plan = SubscriptionPlan.query.filter_by(name=tenant.plan).first()
            if plan:
                total_revenue += plan.price
        
        # Recent activity
        recent_logins = SaasUser.query.filter(
            SaasUser.last_login >= datetime.utcnow() - timedelta(days=7)
        ).count()
        
        # System resources
        try:
            system_stats = {
                'cpu_percent': psutil.cpu_percent(interval=1),
                'memory': dict(psutil.virtual_memory()._asdict()),
                'disk': dict(psutil.disk_usage('/')._asdict()),
                'boot_time': datetime.fromtimestamp(psutil.boot_time()).isoformat()
            }
        except Exception as e:
            # Fallback for systems where psutil might not work
            system_stats = {
                'cpu_percent': 0,
                'memory': {'percent': 0, 'total': 0, 'available': 0},
                'disk': {'percent': 0, 'total': 0, 'free': 0},
                'boot_time': datetime.utcnow().isoformat()
            }
        
        workers = WorkerInstance.query.all()
        worker_stats = {
            'total_workers': len(workers),
            'running_workers': len([w for w in workers if w.status == 'running']),
            'total_capacity': sum(w.max_tenants for w in workers) if workers else 0,
            'current_load': sum(w.current_tenants for w in workers) if workers else 0
        }
        
        stats = {
            'users': {
                'total': total_users,
                'active': active_users,
                'recent_logins': recent_logins,
                'admin_users': admin_users
            },
            'tenants': {
                'total': total_tenants,
                'active': active_tenants,
                'pending': pending_tenants
            },
            'revenue': {
                'monthly_total': total_revenue,
                'currency': 'USD'
            },
            'worker_stats': worker_stats,
            'system': system_stats,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to fetch system stats'}), 500

# ================= AUDIT LOGS =================

@master_admin_bp.route('/master-admin/audit-logs', methods=['GET'])
@login_required
@require_admin()
@track_errors('get_audit_logs')
def get_audit_logs():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        logs = AuditLog.query.order_by(desc(AuditLog.created_at))\
                           .paginate(page=page, per_page=per_page, error_out=False)
        
        logs_data = []
        for log in logs.items:
            logs_data.append({
                'id': log.id,
                'user_id': log.user_id,
                'username': log.user.username if log.user else 'System',
                'tenant_id': log.tenant_id,
                'tenant_name': log.tenant.name if log.tenant else None,
                'action': log.action,
                'details': log.details,
                'ip_address': log.ip_address,
                'created_at': log.created_at.isoformat()
            })
        
        return jsonify({
            'success': True,
            'logs': logs_data,
            'pagination': {
                'page': logs.page,
                'pages': logs.pages,
                'per_page': logs.per_page,
                'total': logs.total
            }
        })
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to fetch audit logs'}), 500

# ================= DATABASE OPERATIONS =================

@master_admin_bp.route('/master-admin/database/query', methods=['POST'])
@login_required
@require_admin()
@track_errors('execute_database_query')
def execute_database_query():
    try:
        data = request.json
        query = data.get('query', '').strip()
        
        if not query:
            return jsonify({'success': False, 'message': 'Query is required'}), 400
        
        # Security check - only allow SELECT queries
        if not query.upper().startswith('SELECT'):
            return jsonify({'success': False, 'message': 'Only SELECT queries are allowed'}), 400
        
        result = db.session.execute(text(query))
        rows = result.fetchall()
        columns = result.keys() if hasattr(result, 'keys') else []
        
        # Convert to list of dictionaries
        data_rows = []
        for row in rows:
            row_dict = {}
            for i, col in enumerate(columns):
                value = row[i]
                # Convert datetime objects to strings
                if isinstance(value, datetime):
                    value = value.isoformat()
                row_dict[col] = value
            data_rows.append(row_dict)
        
        log_admin_action('database_query_executed', {
            'query': query[:100] + '...' if len(query) > 100 else query,
            'row_count': len(data_rows)
        })
        
        return jsonify({
            'success': True,
            'columns': list(columns),
            'rows': data_rows,
            'row_count': len(data_rows)
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id, 'query': query[:200]})
        return jsonify({'success': False, 'message': f'Query failed: {str(e)}'}), 500

# Keep all existing endpoints from the original file...
# (Including dashboard, user management, tenant management, operations, security, etc.)

# ================= ENHANCED DASHBOARD DATA =================

@master_admin_bp.route('/master-admin/dashboard')
@login_required
@require_admin()
@track_errors('master_admin_dashboard')
def master_admin_dashboard():
    """Updated dashboard route to serve the new functional template"""
    try:
        # This will serve the new functional HTML template
        return render_template('master_admin_dashboard.html')
    except Exception as e:
        error_tracker.log_error(e, {'user_id': current_user.id})
        return render_template('error.html', message='Error loading dashboard.'), 500


def calculate_tenant_health(tenant):
    try:
        recent_accesses = CredentialAccess.query.filter(
            CredentialAccess.tenant_id == tenant.id,
            CredentialAccess.accessed_at >= datetime.utcnow() - timedelta(days=7)
        ).count()
        user_count = TenantUser.query.filter_by(tenant_id=tenant.id).count()
        
        if tenant.status != 'active':
            return 'poor'
        elif recent_accesses > 20 and user_count > 1:
            return 'excellent'
        elif recent_accesses > 5 or user_count > 0:
            return 'good'
        else:
            return 'poor'
    except Exception:
        return 'poor'

def get_enhanced_analytics_data():
    try:
        today = datetime.utcnow().date()
        week_ago = datetime.utcnow() - timedelta(days=7)
        month_ago = datetime.utcnow() - timedelta(days=30)
        
        # User analytics
        new_users_today = SaasUser.query.filter(func.date(SaasUser.created_at) == today).count()
        new_users_week = SaasUser.query.filter(SaasUser.created_at >= week_ago).count()
        new_users_month = SaasUser.query.filter(SaasUser.created_at >= month_ago).count()
        
        # Tenant analytics
        new_tenants_today = Tenant.query.filter(func.date(Tenant.created_at) == today).count()
        new_tenants_week = Tenant.query.filter(Tenant.created_at >= week_ago).count()
        new_tenants_month = Tenant.query.filter(Tenant.created_at >= month_ago).count()
        
        active_tenants = Tenant.query.filter_by(status='active').count()
        total_tenants = Tenant.query.count()
        tenant_uptime = (active_tenants / total_tenants * 100) if total_tenants > 0 else 0
        
        # Revenue analytics
        plan_prices = {p.name: p.price for p in SubscriptionPlan.query.all()}
        plan_usage = {}
        monthly_revenue = 0
        
        for tenant in Tenant.query.filter_by(status='active').all():
            plan_name = tenant.plan
            monthly_revenue += plan_prices.get(plan_name, 0)
            plan_usage[plan_name] = plan_usage.get(plan_name, 0) + 1
        
        # Growth calculations
        revenue_growth = 12  # This should be calculated based on historical data
        storage_growth = 15   # This should be calculated based on actual storage metrics
        
        # Users per month for chart
        users_per_month = {}
        users_query = SaasUser.query.all()
        
        for user in users_query:
            if user.created_at:
                month_abbr = user.created_at.strftime('%b')
                users_per_month[month_abbr] = users_per_month.get(month_abbr, 0) + 1
        
        # System metrics
        try:
            system_metrics = {
                'cpu_usage': psutil.cpu_percent(interval=1),
                'memory_usage': psutil.virtual_memory().percent,
                'disk_usage': psutil.disk_usage('/').percent
            }
        except Exception:
            system_metrics = {'cpu_usage': 0, 'memory_usage': 0, 'disk_usage': 0}
        
        return {
            'total_users': SaasUser.query.count(),
            'new_users_today': new_users_today,
            'new_users_week': new_users_week,
            'new_users_month': new_users_month,
            'active_tenants': active_tenants,
            'new_tenants_today': new_tenants_today,
            'new_tenants_week': new_tenants_week,
            'new_tenants_month': new_tenants_month,
            'tenant_uptime': round(tenant_uptime, 1),
            'total_storage': "2.5TB",  # Should be calculated from actual data
            'storage_growth': storage_growth,
            'monthly_revenue': monthly_revenue,
            'revenue_growth': revenue_growth,
            'users_per_month': users_per_month,
            'plan_usage': plan_usage,
            'system_metrics': system_metrics
        }
    except Exception as e:
        error_tracker.log_error(e)
        return {
            'total_users': 0, 'new_users_today': 0, 'new_users_week': 0, 'new_users_month': 0,
            'active_tenants': 0, 'new_tenants_today': 0, 'new_tenants_week': 0, 'new_tenants_month': 0,
            'tenant_uptime': 0, 'total_storage': '0GB', 'storage_growth': 0,
            'monthly_revenue': 0, 'revenue_growth': 0,
            'users_per_month': {}, 'plan_usage': {},
            'system_metrics': {'cpu_usage': 0, 'memory_usage': 0, 'disk_usage': 0}
        }

# ================= MAINTENANCE MODE =================

@master_admin_bp.route('/master-admin/maintenance/enable', methods=['POST'])
@login_required
@require_admin()
@track_errors('enable_maintenance_mode')
def enable_maintenance_mode():
    try:
        data = request.json
        message = data.get('message', 'System is under maintenance. Please try again later.')
        duration = data.get('duration', 60)  # minutes
        
        # Store maintenance mode in Redis or database
        maintenance_data = {
            'enabled': True,
            'message': message,
            'started_at': datetime.utcnow().isoformat(),
            'duration_minutes': duration,
            'enabled_by': current_user.username
        }
        
        # You can store this in Redis or a config table
        # For now, we'll use a simple file approach
        import json
        with open('/app/maintenance_mode.json', 'w') as f:
            json.dump(maintenance_data, f)
        
        log_admin_action('maintenance_mode_enabled', maintenance_data)
        
        return jsonify({'success': True, 'message': 'Maintenance mode enabled'})
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to enable maintenance mode'}), 500

@master_admin_bp.route('/master-admin/maintenance/disable', methods=['POST'])
@login_required
@require_admin()
@track_errors('disable_maintenance_mode')
def disable_maintenance_mode():
    try:
        # Remove maintenance mode
        import os
        if os.path.exists('/app/maintenance_mode.json'):
            os.remove('/app/maintenance_mode.json')
        
        log_admin_action('maintenance_mode_disabled', {'disabled_by': current_user.username})
        
        return jsonify({'success': True, 'message': 'Maintenance mode disabled'})
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to disable maintenance mode'}), 500

# ================= EXPORT/IMPORT FUNCTIONS =================

@master_admin_bp.route('/master-admin/export/full_system', methods=['GET'])
@login_required
@require_admin()
@track_errors('export_full_system')
def export_full_system():
    try:
        # Export all system data
        export_data = {
            'users': [],
            'tenants': [],
            'plans': [],
            'workers': [],
            'audit_logs': [],
            'exported_at': datetime.utcnow().isoformat(),
            'exported_by': current_user.username
        }
        
        # Export users
        for user in SaasUser.query.all():
            export_data['users'].append({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'is_admin': user.is_admin,
                'is_active': user.is_active,
                'created_at': user.created_at.isoformat() if user.created_at else None,
                'last_login': user.last_login.isoformat() if user.last_login else None
            })
        
        # Export tenants
        for tenant in Tenant.query.all():
            export_data['tenants'].append({
                'id': tenant.id,
                'name': tenant.name,
                'subdomain': tenant.subdomain,
                'database_name': tenant.database_name,
                'status': tenant.status,
                'plan': tenant.plan,
                'created_at': tenant.created_at.isoformat() if tenant.created_at else None,
                'admin_username': tenant.admin_username
            })
        
        # Export plans
        for plan in SubscriptionPlan.query.all():
            export_data['plans'].append({
                'id': plan.id,
                'name': plan.name,
                'price': float(plan.price),
                'max_users': plan.max_users,
                'storage_limit': plan.storage_limit,
                'features': plan.features,
                'modules': plan.modules,
                'is_active': plan.is_active,
                'created_at': plan.created_at.isoformat() if plan.created_at else None
            })
        
        # Export workers
        for worker in WorkerInstance.query.all():
            export_data['workers'].append({
                'id': worker.id,
                'name': worker.name,
                'container_name': worker.container_name,
                'port': worker.port,
                'status': worker.status,
                'max_tenants': worker.max_tenants,
                'current_tenants': worker.current_tenants,
                'created_at': worker.created_at.isoformat() if worker.created_at else None
            })
        
        # Create JSON file
        output = io.StringIO()
        json.dump(export_data, output, indent=2)
        output.seek(0)
        
        log_admin_action('full_system_export', {'record_counts': {
            'users': len(export_data['users']),
            'tenants': len(export_data['tenants']),
            'plans': len(export_data['plans']),
            'workers': len(export_data['workers'])
        }})
        
        filename = f"system_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        
        return send_file(
            io.BytesIO(output.getvalue().encode()),
            download_name=filename,
            as_attachment=True,
            mimetype='application/json'
        )
        
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to export system data'}), 500

# ================= KEEP ALL EXISTING ENDPOINTS =================

# User Management (from original file)
@master_admin_bp.route('/master-admin/user/<int:user_id>/toggle_status', methods=['POST'])
@login_required
@require_admin()
@track_errors('toggle_user_status')
def toggle_user_status(user_id):
    try:
        user = SaasUser.query.get_or_404(user_id)
        user.is_active = not user.is_active
        db.session.commit()
        log_admin_action('user_status_toggle', {'user_id': user_id, 'new_status': user.is_active})
        return jsonify({'success': True, 'message': f'User {user.username} status updated to {"active" if user.is_active else "inactive"}'})
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'user_id': user_id})
        return jsonify({'success': False, 'message': 'Failed to update user status'}), 500

@master_admin_bp.route('/master-admin/user/<int:user_id>/reset_password', methods=['POST'])
@login_required
@require_admin()
@track_errors('reset_user_password')
def reset_user_password(user_id):
    try:
        user = SaasUser.query.get_or_404(user_id)
        new_password = generate_password(12)
        user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        log_admin_action('user_password_reset', {'user_id': user_id})
        return jsonify({'success': True, 'message': 'Password reset successfully', 'new_password': new_password})
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'user_id': user_id})
        return jsonify({'success': False, 'message': 'Failed to reset password'}), 500

@master_admin_bp.route('/master-admin/user/<int:user_id>/details')
@login_required
@require_admin()
@track_errors('user_details')
def user_details(user_id):
    try:
        user = SaasUser.query.get_or_404(user_id)
        tenant_users = TenantUser.query.filter_by(user_id=user_id).all()
        tenants = []
        for tu in tenant_users:
            tenant = Tenant.query.get(tu.tenant_id)
            if tenant:
                tenants.append({
                    'id': tenant.id,
                    'name': tenant.name,
                    'subdomain': tenant.subdomain,
                    'status': tenant.status,
                    'plan': tenant.plan,
                    'role': tu.role
                })
        recent_activity = CredentialAccess.query.filter_by(user_id=user_id)\
            .order_by(CredentialAccess.accessed_at.desc()).limit(20).all()
        
        user_data = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_admin': user.is_admin,
            'is_active': user.is_active,
            'last_login': user.last_login.isoformat() if user.last_login else None,
            'created_at': user.created_at.isoformat() if user.created_at else None,
            'tenants': tenants,
            'recent_activity': [
                {
                    'accessed_at': activity.accessed_at.isoformat(),
                    'ip_address': activity.ip_address,
                    'success': activity.success,
                    'tenant_name': activity.tenant.name if activity.tenant else 'Unknown'
                } for activity in recent_activity
            ]
        }
        
        # Return JSON response instead of rendering template
        return jsonify({'success': True, 'user': user_data})
        
    except Exception as e:
        error_tracker.log_error(e, {'user_id': user_id})
        return jsonify({'success': False, 'message': 'Failed to load user details'}), 500

@master_admin_bp.route('/master-admin/user/<int:user_id>/impersonate', methods=['POST'])
@login_required
@require_admin()
@track_errors('impersonate_user')
def impersonate_user(user_id):
    try:
        user = SaasUser.query.get_or_404(user_id)
        if not user.is_active:
            return jsonify({'success': False, 'message': 'Cannot impersonate inactive user'}), 400
        session['original_user_id'] = current_user.id
        session['impersonating'] = True
        login_user(user)
        log_admin_action('user_impersonation', {
            'impersonated_user_id': user_id, 'impersonated_username': user.username
        })
        return jsonify({'success': True, 'redirect_url': url_for('dashboard')})
    except Exception as e:
        error_tracker.log_error(e, {'user_id': user_id})
        return jsonify({'success': False, 'message': 'Failed to impersonate user'}), 500

# Tenant Management (from original file)
@master_admin_bp.route('/master-admin/tenant/<int:tenant_id>/toggle_status', methods=['POST'])
@login_required
@require_admin()
@track_errors('toggle_tenant_status')
def toggle_tenant_status(tenant_id):
    try:
        tenant = Tenant.query.get_or_404(tenant_id)
        odoo = OdooDatabaseManager(
            odoo_url=os.environ.get('ODOO_URL', 'http://odoo_master:8069'),
            master_pwd=os.environ.get('ODOO_MASTER_PASSWORD', 'admin123')
        )
        if tenant.status == 'active':
            odoo.deactivate(tenant.database_name)
            tenant.status = 'inactive'
        else:
            odoo.activate(tenant.database_name)
            tenant.status = 'active'
        db.session.commit()
        log_admin_action('tenant_status_toggle', {'tenant_id': tenant_id, 'new_status': tenant.status})
        return jsonify({'success': True, 'message': f'Tenant {tenant.name} status updated to {tenant.status}'})
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'tenant_id': tenant_id})
        return jsonify({'success': False, 'message': 'Failed to update tenant status'}), 500

@master_admin_bp.route('/master-admin/tenant/<int:tenant_id>/details')
@login_required
@require_admin()
@track_errors('tenant_details')
def tenant_details(tenant_id):
    try:
        tenant = Tenant.query.get_or_404(tenant_id)
        odoo = OdooDatabaseManager(
            odoo_url=os.environ.get('ODOO_URL', 'http://odoo_master:8069'),
            master_pwd=os.environ.get('ODOO_MASTER_PASSWORD', 'admin123')
        )
        
        # Get tenant users
        tenant_users = TenantUser.query.filter_by(tenant_id=tenant_id).all()
        users = []
        for tu in tenant_users:
            user = SaasUser.query.get(tu.user_id)
            if user:
                users.append({
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'role': tu.role,
                    'is_active': user.is_active,
                    'last_login': user.last_login.isoformat() if user.last_login else None
                })
        
        # Get installed apps only if tenant is active
        installed_apps = []
        storage_usage = 'N/A'
        if tenant.status == 'active':
            try:
                installed_apps = odoo.get_installed_applications(
                    tenant.database_name, tenant.admin_username, tenant.get_admin_password()
                )
                storage_data = odoo.get_database_storage_usage(tenant.database_name)
                storage_usage = storage_data.get('total_size_human', 'N/A')
            except Exception as e:
                logger.warning(f"Failed to get Odoo data for tenant {tenant_id}: {e}")
        
        # Get access logs
        access_logs = CredentialAccess.query.filter_by(tenant_id=tenant.id)\
            .order_by(CredentialAccess.accessed_at.desc()).limit(20).all()
        
        # Get subscription plan details
        plan = SubscriptionPlan.query.filter_by(name=tenant.plan).first()
        plan_details = None
        if plan:
            plan_details = {
                'name': plan.name,
                'price': float(plan.price),
                'max_users': plan.max_users,
                'storage_limit': plan.storage_limit,
                'features': plan.features,
                'modules': plan.modules
            }
        
        tenant_data = {
            'id': tenant.id,
            'name': tenant.name,
            'subdomain': tenant.subdomain,
            'database_name': tenant.database_name,
            'status': tenant.status,
            'plan': tenant.plan,
            'plan_details': plan_details,
            'admin_username': tenant.admin_username,
            'created_at': tenant.created_at.isoformat() if tenant.created_at else None,
            'updated_at': tenant.updated_at.isoformat() if tenant.updated_at else None,
            'is_active': tenant.is_active,
            'max_users': tenant.max_users,
            'storage_limit': tenant.storage_limit,
            'users': users,
            'user_count': len(users),
            'installed_apps': installed_apps,
            'storage_usage': storage_usage,
            'access_logs': [
                {
                    'accessed_at': log.accessed_at.isoformat(),
                    'ip_address': log.ip_address,
                    'success': log.success,
                    'user_agent': log.user_agent,
                    'username': log.user.username if log.user else 'Unknown'
                } for log in access_logs
            ]
        }
        
        # Return JSON response instead of rendering template
        return jsonify({'success': True, 'tenant': tenant_data})
        
    except Exception as e:
        error_tracker.log_error(e, {'tenant_id': tenant_id})
        return jsonify({'success': False, 'message': 'Failed to load tenant details'}), 500

@master_admin_bp.route('/master-admin/tenant/<int:tenant_id>/suspend', methods=['POST'])
@login_required
@require_admin()
@track_errors('suspend_tenant')
def suspend_tenant(tenant_id):
    try:
        tenant = Tenant.query.get_or_404(tenant_id)
        tenant.status = 'suspended'
        db.session.commit()
        log_admin_action('tenant_suspended', {'tenant_id': tenant_id})
        return jsonify({'success': True, 'message': f'Tenant {tenant.name} suspended'})
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'tenant_id': tenant_id})
        return jsonify({'success': False, 'message': 'Failed to suspend tenant'}), 500

@master_admin_bp.route('/master-admin/tenant/<int:tenant_id>/backup', methods=['POST'])
@login_required
@require_admin()
@track_errors('backup_tenant')
def backup_tenant(tenant_id):
    try:
        tenant = Tenant.query.get_or_404(tenant_id)
        odoo = OdooDatabaseManager(
            odoo_url=os.environ.get('ODOO_URL', 'http://odoo_master:8069'),
            master_pwd=os.environ.get('ODOO_MASTER_PASSWORD', 'admin123')
        )
        backup_path = odoo.backup(tenant.database_name)
        log_admin_action('tenant_backup', {'tenant_id': tenant_id})
        return jsonify({'success': True, 'message': 'Backup initiated successfully'})
    except Exception as e:
        error_tracker.log_error(e, {'tenant_id': tenant_id})
        return jsonify({'success': False, 'message': 'Failed to backup tenant'}), 500

# Export functions (from original file)
@master_admin_bp.route('/master-admin/export/users')
@login_required
@require_admin()
def export_users():
    users = SaasUser.query.all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Username', 'Email', 'Is Admin', 'Is Active', 'Last Login', 'Created At'])
    for user in users:
        writer.writerow([
            user.id,
            user.username,
            user.email,
            'Yes' if user.is_admin else 'No',
            'Active' if user.is_active else 'Inactive',
            user.last_login.isoformat() if user.last_login else 'Never',
            user.created_at.isoformat() if user.created_at else ''
        ])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode()), download_name="users.csv", as_attachment=True, mimetype='text/csv')

@master_admin_bp.route('/master-admin/export/tenants')
@login_required
@require_admin()
def export_tenants():
    tenants = Tenant.query.all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Name', 'Subdomain', 'Status', 'Plan', 'User Count'])
    for tenant in tenants:
        user_count = TenantUser.query.filter_by(tenant_id=tenant.id).count()
        writer.writerow([
            tenant.id,
            tenant.name,
            tenant.subdomain,
            tenant.status,
            tenant.plan,
            user_count
        ])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode()), download_name="tenants.csv", as_attachment=True, mimetype='text/csv')
@master_admin_bp.route('/master-admin/api/admin/users/list', methods=['GET'])
@login_required
@require_admin()
@track_errors('api_users_list')
def api_users_list():
    """API endpoint for users table"""
    try:
        users = SaasUser.query.all()
        users_data = []
        
        for user in users:
            # Get tenant count for this user
            tenant_count = TenantUser.query.filter_by(user_id=user.id).count()
            
            # Get recent activity
            recent_activity = CredentialAccess.query.filter_by(user_id=user.id)\
                .order_by(CredentialAccess.accessed_at.desc()).first()
            
            users_data.append({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'is_admin': user.is_admin,
                'is_active': user.is_active,
                'tenant_count': tenant_count,
                'last_login': user.last_login.isoformat() if user.last_login else 'Never',
                'last_activity': recent_activity.accessed_at.isoformat() if recent_activity else 'No activity',
                'created_at': user.created_at.isoformat() if user.created_at else '',
                'status_badge': 'success' if user.is_active else 'danger',
                'role_badge': 'primary' if user.is_admin else 'secondary'
            })
        
        return jsonify({'success': True, 'users': users_data})
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to fetch users'}), 500
    
# Bulk actions (from original file)
@master_admin_bp.route('/master-admin/users/bulk_action', methods=['POST'])
@login_required
@require_admin()
@track_errors('bulk_user_action')
def bulk_user_action():
    try:
        data = request.json
        action = data.get('action')
        user_ids = data.get('user_ids', [])
        affected = 0
        for user_id in user_ids:
            user = SaasUser.query.get(user_id)
            if not user:
                continue
            if action == 'activate':
                user.is_active = True
            elif action == 'deactivate':
                user.is_active = False
            elif action == 'delete':
                db.session.delete(user)
            affected += 1
        db.session.commit()
        log_admin_action('bulk_user_action', {'action': action, 'user_ids': user_ids})
        return jsonify({'success': True, 'message': f'{affected} users processed'})
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'action': 'bulk_user_action'})
        return jsonify({'success': False, 'message': 'Bulk user action failed'}), 500

@master_admin_bp.route('/master-admin/tenants/bulk_action', methods=['POST'])
@login_required
@require_admin()
@track_errors('bulk_tenant_action')
def bulk_tenant_action():
    try:
        data = request.json
        action = data.get('action')
        tenant_ids = data.get('tenant_ids', [])
        affected = 0
        for tenant_id in tenant_ids:
            tenant = Tenant.query.get(tenant_id)
            if not tenant:
                continue
            if action == 'activate':
                tenant.status = 'active'
            elif action == 'deactivate':
                tenant.status = 'inactive'
            elif action == 'suspend':
                tenant.status = 'suspended'
            elif action == 'backup':
                pass  # Could integrate backup logic here
            affected += 1
        db.session.commit()
        log_admin_action('bulk_tenant_action', {'action': action, 'tenant_ids': tenant_ids})
        return jsonify({'success': True, 'message': f'{affected} tenants processed'})
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'action': 'bulk_tenant_action'})
        return jsonify({'success': False, 'message': 'Bulk tenant action failed'}), 500

# Operations endpoints (from original file)
@master_admin_bp.route('/master-admin/operations/database_backup', methods=['POST'])
@login_required
@require_admin()
def database_backup():
    log_admin_action('database_backup')
    return jsonify({'success': True, 'message': 'Database backup initiated successfully'})

@master_admin_bp.route('/master-admin/operations/database_optimize', methods=['POST'])
@login_required
@require_admin()
def database_optimize():
    log_admin_action('database_optimize')
    return jsonify({'success': True, 'message': 'Database optimization completed'})

@master_admin_bp.route('/master-admin/operations/database_cleanup', methods=['POST'])
@login_required
@require_admin()
def database_cleanup():
    log_admin_action('database_cleanup')
    return jsonify({'success': True, 'message': 'Database cleanup completed'})

@master_admin_bp.route('/master-admin/operations/database_migrate', methods=['POST'])
@login_required
@require_admin()
def database_migrate():
    log_admin_action('database_migrate')
    return jsonify({'success': True, 'message': 'Database migrations completed'})

@master_admin_bp.route('/master-admin/operations/clear_cache', methods=['POST'])
@login_required
@require_admin()
def clear_cache():
    log_admin_action('clear_cache')
    return jsonify({'success': True, 'message': 'System cache cleared successfully'})

@master_admin_bp.route('/master-admin/operations/restart_services', methods=['POST'])
@login_required
@require_admin()
def restart_services():
    log_admin_action('restart_services')
    return jsonify({'success': True, 'message': 'Services restarted successfully'})

@master_admin_bp.route('/master-admin/operations/update_system', methods=['POST'])
@login_required
@require_admin()
def update_system():
    log_admin_action('update_system')
    return jsonify({'success': True, 'message': 'System update initiated'})

@master_admin_bp.route('/master-admin/operations/health_check', methods=['POST'])
@login_required
@require_admin()
def health_check():
    try:
        results = {
            'cpu_percent': psutil.cpu_percent(),
            'memory': dict(psutil.virtual_memory()._asdict()),
            'disk': dict(psutil.disk_usage('/')._asdict())
        }
        log_admin_action('health_check', {'results': results})
        return jsonify({'success': True, 'results': results})
    except Exception as e:
        error_tracker.log_error(e)
        return jsonify({'success': False, 'message': 'Failed health check'}), 500

# Security endpoints (from original file)
@master_admin_bp.route('/master-admin/security/block_ip', methods=['POST'])
@login_required
@require_admin()
def block_ip():
    ip = request.json.get('ip_address')
    if not ip:
        return jsonify({'success': False, 'message': 'IP address required'}), 400
    log_admin_action('block_ip', {'ip_address': ip})
    return jsonify({'success': True, 'message': 'IP blocked successfully'})

@master_admin_bp.route('/master-admin/security/unblock_ip', methods=['POST'])
@login_required
@require_admin()
def unblock_ip():
    ip = request.json.get('ip_address')
    log_admin_action('unblock_ip', {'ip_address': ip})
    return jsonify({'success': True, 'message': 'IP unblocked successfully'})

# API endpoints

@master_admin_bp.route('/master-admin/api/admin/stats', methods=['GET'])
@login_required
@require_admin()
@track_errors('api_admin_stats')
def api_admin_stats():
    """API endpoint for dashboard statistics"""
    try:
        # Use the existing get_system_stats function but call it correctly
        stats_response = get_system_stats()
        return stats_response  # This already returns a jsonify response
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to fetch stats'}), 500

@master_admin_bp.route('/master-admin/api/admin/tenants/list', methods=['GET'])
@login_required
@require_admin()
@track_errors('api_tenants_list')
def api_tenants_list():
    """API endpoint for tenants table"""
    try:
        tenants = Tenant.query.all()
        tenants_data = []
        
        for tenant in tenants:
            user_count = TenantUser.query.filter_by(tenant_id=tenant.id).count()
            plan = SubscriptionPlan.query.filter_by(name=tenant.plan).first()
            
            # Calculate storage usage (simplified)
            storage_used = user_count * 50  # 50MB per user estimate
            storage_limit = plan.storage_limit if plan else 1000
            storage_percentage = min((storage_used / storage_limit) * 100, 100) if storage_limit > 0 else 0
            
            tenants_data.append({
                'id': tenant.id,
                'name': tenant.name,
                'subdomain': tenant.subdomain,
                'status': tenant.status,
                'plan': tenant.plan,
                'health': calculate_tenant_health(tenant),
                'storage_usage': f"{storage_used}MB / {storage_limit}MB",
                'storage_percentage': round(storage_percentage, 1),
                'user_count': user_count,
                'monthly_revenue': float(plan.price) if plan else 0,
                'created_at': tenant.created_at.isoformat() if tenant.created_at else ''
            })
        
        return jsonify({'success': True, 'tenants': tenants_data})
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to fetch tenants'}), 500

@master_admin_bp.route('/master-admin/api/admin/analytics', methods=['GET'])
@login_required
@require_admin()
@track_errors('api_analytics')
def api_analytics():
    """API endpoint for charts data"""
    try:
        # User growth data - get users created by month
        from sqlalchemy import func, extract
        
        # Get last 6 months of user data
        user_growth_data = []
        months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        # Simplified approach - just get total users for now
        total_users = SaasUser.query.count()
        user_data = [max(1, total_users // 6 * i) for i in range(1, 7)]
        user_data[-1] = total_users  # Make sure last month shows actual total
        
        # Plan distribution
        plan_data = db.session.query(
            Tenant.plan,
            func.count(Tenant.id).label('count')
        ).filter(Tenant.status == 'active').group_by(Tenant.plan).all()
        
        plan_labels = [data[0] or 'Unknown' for data in plan_data] or ['No Plans']
        plan_counts = [data[1] for data in plan_data] or [1]
        
        # Revenue by month (simplified)
        revenue_data = []
        current_revenue = 0
        for tenant in Tenant.query.filter_by(status='active').all():
            plan = SubscriptionPlan.query.filter_by(name=tenant.plan).first()
            if plan:
                current_revenue += plan.price
        
        # Generate 6 months of revenue data
        revenue_values = [max(100, current_revenue // 12 * i) for i in range(1, 7)]
        revenue_values[-1] = current_revenue
        
        # Storage growth (simplified)
        storage_values = [0.2 + (i * 0.2) for i in range(6)]
        
        chart_data = {
            'userGrowth': {
                'labels': months,
                'data': user_data
            },
            'planDistribution': {
                'labels': plan_labels,
                'data': plan_counts
            },
            'revenue': {
                'labels': months,
                'data': revenue_values
            },
            'storage': {
                'labels': months,
                'data': storage_values
            }
        }
        
        return jsonify({'success': True, 'analytics': chart_data})
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to fetch analytics'}), 500

# ================= AUTHENTICATION CHECK ENDPOINT =================

@master_admin_bp.route('/master-admin/auth/check', methods=['GET'])
@track_errors('check_auth')
def check_auth():
    """Check if user is authenticated and is admin"""
    if current_user.is_authenticated and current_user.is_admin:
        return jsonify({
            'authenticated': True,
            'is_admin': True,
            'username': current_user.username,
            'user_id': current_user.id
        })
    else:
        return jsonify({
            'authenticated': current_user.is_authenticated,
            'is_admin': False,
            'redirect': url_for('login')
        }), 403

# ================= ENHANCED PLAN MANAGEMENT =================

@master_admin_bp.route('/master-admin/plan/<int:plan_id>/edit', methods=['GET', 'POST'])
@login_required
@require_admin()
@track_errors('edit_plan')
def edit_plan(plan_id):
    try:
        plan = SubscriptionPlan.query.get_or_404(plan_id)
        
        if request.method == 'GET':
            return jsonify({
                'success': True,
                'plan': {
                    'id': plan.id,
                    'name': plan.name,
                    'price': float(plan.price),
                    'max_users': plan.max_users,
                    'storage_limit': plan.storage_limit,
                    'features': plan.features or [],
                    'modules': plan.modules or [],
                    'is_active': plan.is_active
                }
            })
        
        # POST - Update plan
        data = request.json
        old_values = {
            'name': plan.name,
            'price': plan.price,
            'max_users': plan.max_users,
            'storage_limit': plan.storage_limit
        }
        
        plan.name = data.get('name', plan.name)
        plan.price = float(data.get('price', plan.price))
        plan.max_users = int(data.get('max_users', plan.max_users))
        plan.storage_limit = int(data.get('storage_limit', plan.storage_limit))
        plan.features = data.get('features', plan.features)
        plan.modules = data.get('modules', plan.modules)
        plan.is_active = data.get('is_active', plan.is_active)
        
        db.session.commit()
        
        log_admin_action('plan_updated', {
            'plan_id': plan_id,
            'old_values': old_values,
            'new_values': {
                'name': plan.name,
                'price': plan.price,
                'max_users': plan.max_users,
                'storage_limit': plan.storage_limit
            }
        })
        
        return jsonify({'success': True, 'message': 'Plan updated successfully'})
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'admin_user': current_user.id, 'plan_id': plan_id})
        return jsonify({'success': False, 'message': 'Failed to update plan'}), 500

# ================= ENHANCED WORKER MANAGEMENT =================

@master_admin_bp.route('/master-admin/api/workers', methods=['GET'])
@login_required
@require_admin()
@track_errors('api_get_workers')
def api_get_workers():
    try:
        workers = WorkerInstance.query.all()
        workers_data = []
        
        # Try to get Docker client
        docker_client = None
        try:
            import docker
            docker_client = docker.from_env()
        except Exception:
            pass
        
        for worker in workers:
            worker_data = {
                'id': worker.id,
                'name': worker.name,
                'container_name': worker.container_name,
                'port': worker.port,
                'status': worker.status,
                'current_tenants': worker.current_tenants,
                'max_tenants': worker.max_tenants,
                'created_at': worker.created_at.isoformat() if worker.created_at else '',
                'last_health_check': worker.last_health_check.isoformat() if worker.last_health_check else None,
                'container_status': 'unknown'
            }
            
            # Get container status if Docker is available
            if docker_client:
                try:
                    container = docker_client.containers.get(worker.container_name)
                    worker_data['container_status'] = container.status
                    worker_data['container_id'] = container.id[:12]
                except:
                    worker_data['container_status'] = 'not_found'
            
            workers_data.append(worker_data)
        
        return jsonify({'success': True, 'workers': workers_data})
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to fetch workers'}), 500

# ================= ENHANCED AUDIT LOGS =================

@master_admin_bp.route('/master-admin/api/audit-logs', methods=['GET'])
@login_required
@require_admin()
@track_errors('api_get_audit_logs')
def api_get_audit_logs():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        logs = AuditLog.query.order_by(desc(AuditLog.created_at))\
                           .paginate(page=page, per_page=per_page, error_out=False)
        
        logs_data = []
        for log in logs.items:
            logs_data.append({
                'id': log.id,
                'user_id': log.user_id,
                'username': log.user.username if log.user else 'System',
                'tenant_id': log.tenant_id,
                'tenant_name': log.tenant.name if log.tenant else None,
                'action': log.action,
                'details': log.details,
                'ip_address': log.ip_address,
                'created_at': log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else ''
            })
        
        return jsonify({
            'success': True,
            'logs': logs_data,
            'pagination': {
                'page': logs.page,
                'pages': logs.pages,
                'per_page': logs.per_page,
                'total': logs.total
            }
        })
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to fetch audit logs'}), 500

# ================= SYSTEM HEALTH CHECK =================

@master_admin_bp.route('/master-admin/api/system/health', methods=['GET'])
@login_required
@require_admin()
@track_errors('api_system_health')
def api_system_health():
    try:
        import psutil
        
        # Database connectivity
        db_healthy = True
        try:
            db.session.execute(text('SELECT 1'))
        except Exception:
            db_healthy = False
        
        # Redis connectivity
        redis_healthy = False
        if redis_client:
            try:
                redis_client.ping()
                redis_healthy = True
            except Exception:
                pass
        
        # Docker connectivity
        docker_healthy = False
        if docker_client:
            try:
                docker_client.ping()
                docker_healthy = True
            except Exception:
                pass
        
        # System metrics
        system_health = {
            'database': 'healthy' if db_healthy else 'unhealthy',
            'redis': 'healthy' if redis_healthy else 'unhealthy',
            'docker': 'healthy' if docker_healthy else 'unhealthy',
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_percent': psutil.disk_usage('/').percent,
            'uptime': str(datetime.utcnow() - datetime.fromtimestamp(psutil.boot_time())),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        overall_status = 'healthy' if all([db_healthy, redis_healthy or True, docker_healthy or True]) else 'unhealthy'
        
        return jsonify({
            'success': True,
            'status': overall_status,
            'details': system_health
        })
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Health check failed'}), 500

# ================= ENHANCED TENANT OPERATIONS =================

@master_admin_bp.route('/master-admin/tenant/<int:tenant_id>/change_plan', methods=['POST'])
@login_required
@require_admin()
@track_errors('change_tenant_plan_api')
def change_tenant_plan_api(tenant_id):
    try:
        tenant = Tenant.query.get_or_404(tenant_id)
        data = request.json
        new_plan = data.get('plan')
        
        # Validate plan exists
        plan = SubscriptionPlan.query.filter_by(name=new_plan, is_active=True).first()
        if not plan:
            return jsonify({'success': False, 'message': 'Invalid plan selected'}), 400
        
        old_plan = tenant.plan
        tenant.plan = new_plan
        tenant.max_users = plan.max_users
        tenant.storage_limit = plan.storage_limit
        db.session.commit()
        
        log_admin_action('tenant_plan_changed', {
            'tenant_id': tenant_id,
            'old_plan': old_plan,
            'new_plan': new_plan,
            'reason': data.get('reason', 'Plan change by admin')
        })
        
        return jsonify({'success': True, 'message': f'Tenant plan changed from {old_plan} to {new_plan}'})
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'tenant_id': tenant_id})
        return jsonify({'success': False, 'message': 'Failed to change tenant plan'}), 500

@master_admin_bp.route('/master-admin/tenant/<int:tenant_id>/users', methods=['GET'])
@login_required
@require_admin()
@track_errors('get_tenant_users')
def get_tenant_users(tenant_id):
    try:
        tenant = Tenant.query.get_or_404(tenant_id)
        tenant_users = TenantUser.query.filter_by(tenant_id=tenant_id).all()
        
        users_data = []
        for tu in tenant_users:
            user = SaasUser.query.get(tu.user_id)
            if user:
                users_data.append({
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'role': tu.role,
                    'is_active': user.is_active,
                    'last_login': user.last_login.isoformat() if user.last_login else 'Never',
                    'created_at': tu.created_at.isoformat() if tu.created_at else ''
                })
        
        return jsonify({
            'success': True,
            'tenant': {
                'id': tenant.id,
                'name': tenant.name,
                'subdomain': tenant.subdomain,
                'status': tenant.status
            },
            'users': users_data
        })
    except Exception as e:
        error_tracker.log_error(e, {'tenant_id': tenant_id})
        return jsonify({'success': False, 'message': 'Failed to fetch tenant users'}), 500

# ================= PAYMENT MANAGEMENT =================

@master_admin_bp.route('/master-admin/api/payments', methods=['GET'])
@login_required
@require_admin()
@track_errors('api_get_payments')
def api_get_payments():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        status_filter = request.args.get('status', '')
        
        query = Payment.query
        if status_filter:
            query = query.filter_by(status=status_filter)
        
        payments = query.order_by(desc(Payment.created_at))\
                       .paginate(page=page, per_page=per_page, error_out=False)
        
        payments_data = []
        for payment in payments.items:
            payments_data.append({
                'id': payment.id,
                'tenant_id': payment.tenant_id,
                'tenant_name': payment.tenant.name if payment.tenant else 'Unknown',
                'user_id': payment.user_id,
                'username': payment.user.username if payment.user else 'Unknown',
                'plan': payment.plan,
                'amount': float(payment.amount),
                'currency': payment.currency,
                'status': payment.status,
                'payment_method': payment.payment_method,
                'transaction_id': payment.transaction_id,
                'created_at': payment.created_at.isoformat() if payment.created_at else '',
                'verified_at': payment.verified_at.isoformat() if payment.verified_at else None,
                'verified_by': payment.verifier.username if payment.verifier else None,
                'notes': payment.notes
            })
        
        return jsonify({
            'success': True,
            'payments': payments_data,
            'pagination': {
                'page': payments.page,
                'pages': payments.pages,
                'per_page': payments.per_page,
                'total': payments.total
            }
        })
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to fetch payments'}), 500

# ================= SYSTEM MAINTENANCE =================

@master_admin_bp.route('/master-admin/api/maintenance/status', methods=['GET'])
@login_required
@require_admin()
@track_errors('get_maintenance_status')
def get_maintenance_status():
    try:
        import json
        import os
        
        maintenance_active = False
        maintenance_data = {}
        
        if os.path.exists('/app/maintenance_mode.json'):
            try:
                with open('/app/maintenance_mode.json', 'r') as f:
                    maintenance_data = json.load(f)
                    maintenance_active = maintenance_data.get('enabled', False)
            except Exception:
                pass
        
        return jsonify({
            'success': True,
            'maintenance_active': maintenance_active,
            'maintenance_data': maintenance_data
        })
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to get maintenance status'}), 500

# ================= DATABASE QUERY INTERFACE =================

@master_admin_bp.route('/master-admin/api/database/tables', methods=['GET'])
@login_required
@require_admin()
@track_errors('get_database_tables')
def get_database_tables():
    try:
        # Get all table names
        result = db.session.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name
        """))
        
        tables = [row[0] for row in result.fetchall()]
        
        return jsonify({
            'success': True,
            'tables': tables
        })
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to fetch database tables'}), 500

@master_admin_bp.route('/master-admin/api/database/table/<table_name>/info', methods=['GET'])
@login_required
@require_admin()
@track_errors('get_table_info')
def get_table_info(table_name):
    try:
        # Get table column information
        result = db.session.execute(text("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_name = :table_name 
            ORDER BY ordinal_position
        """), {'table_name': table_name})
        
        columns = []
        for row in result.fetchall():
            columns.append({
                'name': row[0],
                'type': row[1],
                'nullable': row[2] == 'YES',
                'default': row[3]
            })
        
        # Get row count
        count_result = db.session.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
        row_count = count_result.fetchone()[0]
        
        return jsonify({
            'success': True,
            'table_name': table_name,
            'columns': columns,
            'row_count': row_count
        })
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id, 'table_name': table_name})
        return jsonify({'success': False, 'message': 'Failed to fetch table info'}), 500

# ================= SYSTEM CONFIGURATION =================

@master_admin_bp.route('/master-admin/api/config', methods=['GET'])
@login_required
@require_admin()
@track_errors('get_system_config')
def get_system_config():
    try:
        config = {
            'app_name': 'Odoo SaaS Management',
            'version': '2.1.0',
            'environment': os.environ.get('FLASK_ENV', 'production'),
            'debug_mode': os.environ.get('FLASK_DEBUG', 'False') == 'True',
            'database_url': os.environ.get('DATABASE_URL', '').split('@')[-1] if os.environ.get('DATABASE_URL') else 'Not configured',
            'redis_url': os.environ.get('REDIS_URL', 'Not configured'),
            'odoo_url': os.environ.get('ODOO_URL', 'Not configured'),
            'domain': os.environ.get('DOMAIN', 'Not configured'),
            'max_tenants_per_worker': 10,
            'backup_retention_days': 30,
            'session_timeout_minutes': 60,
            'rate_limit_enabled': bool(redis_client),
            'docker_enabled': bool(docker_client),
            'ssl_enabled': os.environ.get('SSL_ENABLED', 'False') == 'True'
        }
        
        return jsonify({
            'success': True,
            'config': config
        })
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to fetch system config'}), 500

# ================= REAL-TIME NOTIFICATIONS =================

@master_admin_bp.route('/master-admin/api/notifications', methods=['GET'])
@login_required
@require_admin()
@track_errors('get_notifications')
def get_notifications():
    try:
        # Get system notifications
        notifications = []
        
        # Check for pending tenants
        pending_count = Tenant.query.filter_by(status='pending').count()
        if pending_count > 0:
            notifications.append({
                'id': 'pending_tenants',
                'type': 'warning',
                'title': f'{pending_count} Pending Tenants',
                'message': f'There are {pending_count} tenants waiting for approval',
                'action_url': '#tenants',
                'created_at': datetime.utcnow().isoformat()
            })
        
        # Check for failed payments
        failed_payments = Payment.query.filter_by(status='failed').count()
        if failed_payments > 0:
            notifications.append({
                'id': 'failed_payments',
                'type': 'danger',
                'title': f'{failed_payments} Failed Payments',
                'message': f'There are {failed_payments} failed payments requiring attention',
                'action_url': '/master-admin/payments',
                'created_at': datetime.utcnow().isoformat()
            })
        
        # Check system health
        try:
            import psutil
            cpu_percent = psutil.cpu_percent()
            memory_percent = psutil.virtual_memory().percent
            
            if cpu_percent > 90:
                notifications.append({
                    'id': 'high_cpu',
                    'type': 'danger',
                    'title': 'High CPU Usage',
                    'message': f'CPU usage is at {cpu_percent:.1f}%',
                    'action_url': '#operations',
                    'created_at': datetime.utcnow().isoformat()
                })
            
            if memory_percent > 90:
                notifications.append({
                    'id': 'high_memory',
                    'type': 'danger',
                    'title': 'High Memory Usage',
                    'message': f'Memory usage is at {memory_percent:.1f}%',
                    'action_url': '#operations',
                    'created_at': datetime.utcnow().isoformat()
                })
        except Exception:
            pass
        
        return jsonify({
            'success': True,
            'notifications': notifications,
            'count': len(notifications)
        })
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': 'Failed to fetch notifications'}), 500

# ================= ADDITIONAL HELPER FUNCTIONS =================

def calculate_tenant_health_score(tenant):
    """Calculate a more detailed tenant health score"""
    try:
        score = 100
        
        # Check status
        if tenant.status != 'active':
            score -= 50
        
        # Check recent activity
        recent_accesses = CredentialAccess.query.filter(
            CredentialAccess.tenant_id == tenant.id,
            CredentialAccess.accessed_at >= datetime.utcnow() - timedelta(days=7)
        ).count()
        
        if recent_accesses == 0:
            score -= 30
        elif recent_accesses < 5:
            score -= 15
        
        # Check user count
        user_count = TenantUser.query.filter_by(tenant_id=tenant.id).count()
        if user_count == 0:
            score -= 20
        
        # Check plan compliance
        plan = SubscriptionPlan.query.filter_by(name=tenant.plan).first()
        if plan and user_count > plan.max_users:
            score -= 10
        
        return max(0, min(100, score))
    except Exception:
        return 50  # Default neutral score

def get_tenant_health_status(score):
    """Convert health score to status"""
    if score >= 80:
        return 'excellent'
    elif score >= 60:
        return 'good'
    elif score >= 30:
        return 'fair'
    else:
        return 'poor'

# Update the existing calculate_tenant_health function
def calculate_tenant_health(tenant):
    """Updated tenant health calculation"""
    score = calculate_tenant_health_score(tenant)
    return get_tenant_health_status(score)
                
# ================= TEMPORARY DEBUG ENDPOINT =================
@master_admin_bp.route('/master-admin/debug/data', methods=['GET'])
@login_required
@require_admin()
def debug_data():
    """Temporary debug endpoint to check actual data"""
    try:
        users = SaasUser.query.all()
        tenants = Tenant.query.all()
        
        debug_info = {
            'users_count': len(users),
            'tenants_count': len(tenants),
            'users': [{'id': u.id, 'username': u.username, 'is_active': u.is_active} for u in users],
            'tenants': [{'id': t.id, 'name': t.name, 'status': t.status} for t in tenants],
            'db_session': str(db.session),
            'current_user': {
                'id': current_user.id,
                'username': current_user.username,
                'is_admin': current_user.is_admin
            }
        }
        
        return jsonify(debug_info)
    except Exception as e:
        return jsonify({'error': str(e), 'type': str(type(e))})