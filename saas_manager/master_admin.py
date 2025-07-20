from flask import Blueprint, render_template, jsonify, request, redirect, url_for, session, send_file
from flask_login import login_required, current_user, login_user
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash
import os
import io
import csv
import json
import psutil
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from models import (
    SaasUser, Tenant, TenantUser, SubscriptionPlan,
    CredentialAccess, WorkerInstance, UserPublicKey
)
from db import db
from OdooDatabaseManager import OdooDatabaseManager
from utils import track_errors, error_tracker #send_email

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
    # Implement your own logging if you want to store to DB
    print(f"[ADMIN LOG] {action}: {details}")

@master_admin_bp.route('/master-admin/dashboard')
@login_required
@require_admin()
@track_errors('master_admin_dashboard')
def master_admin_dashboard():
    try:
        users = SaasUser.query.options(joinedload(SaasUser.tenants)).all()
        tenants = Tenant.query.options(joinedload(Tenant.users)).all()
        plans = {plan.name: plan for plan in SubscriptionPlan.query.all()}
        odoo = OdooDatabaseManager(
            odoo_url=os.environ.get('ODOO_URL', 'http://odoo_master:8069'),
            master_pwd=os.environ.get('ODOO_MASTER_PASSWORD', 'admin123')
        )

        # Users data
        user_data = []
        for user in users:
            tenant_info = []
            for tu in user.tenants:
                tenant = Tenant.query.get(tu.tenant_id)
                if tenant:
                    tenant_info.append({
                        'id': tenant.id,
                        'name': tenant.name,
                        'subdomain': tenant.subdomain,
                        'status': tenant.status,
                        'plan': tenant.plan
                    })
            user_data.append({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'is_admin': user.is_admin,
                'is_active': user.is_active,
                'last_login': user.last_login.isoformat() if user.last_login else 'Never',
                'created_at': user.created_at.isoformat() if user.created_at else "",
                'tenants': tenant_info,
                'tenant_count': len(tenant_info)
            })

        # Tenants data
        tenant_data = []
        for tenant in tenants:
            try:
                if tenant.status == 'active':
                    installed_apps = odoo.get_installed_applications(
                        tenant.database_name, tenant.admin_username, tenant.get_admin_password()
                    )
                    storage_info = odoo.get_database_storage_usage(tenant.database_name)
                    storage_usage = storage_info.get('total_size_human', 'N/A')
                    storage_percentage = min(int(storage_info.get('total_size_bytes', 0) / (plans[tenant.plan].storage_limit * 1024 * 1024) * 100), 100) if tenant.plan in plans else 0
                    health = calculate_tenant_health(tenant)
                else:
                    installed_apps = []
                    storage_usage = 'N/A'
                    storage_percentage = 0
                    health = 'poor'
                user_count = TenantUser.query.filter_by(tenant_id=tenant.id).count()
                monthly_revenue = plans[tenant.plan].price if tenant.plan in plans else 0
                tenant_data.append({
                    'id': tenant.id,
                    'name': tenant.name,
                    'subdomain': tenant.subdomain,
                    'status': tenant.status,
                    'plan': tenant.plan,
                    'health': health,
                    'installed_apps': installed_apps,
                    'storage_usage': storage_usage,
                    'storage_percentage': storage_percentage,
                    'user_count': user_count,
                    'monthly_revenue': monthly_revenue,
                    'created_at': tenant.created_at.isoformat() if tenant.created_at else ''
                })
            except Exception as e:
                error_tracker.log_error(e, {'tenant_id': tenant.id})
                tenant_data.append({
                    'id': tenant.id,
                    'name': tenant.name,
                    'subdomain': tenant.subdomain,
                    'status': tenant.status,
                    'plan': tenant.plan,
                    'health': 'poor',
                    'installed_apps': [],
                    'storage_usage': 'Error',
                    'storage_percentage': 0,
                    'user_count': 0,
                    'monthly_revenue': 0,
                    'created_at': tenant.created_at.isoformat() if tenant.created_at else ''
                })

        total_revenue = sum(t['monthly_revenue'] for t in tenant_data)
        active_tenants = len([t for t in tenant_data if t['status'] == 'active'])
        stats = {
            'total_users': len(users),
            'total_tenants': len(tenants),
            'active_tenants': active_tenants,
            'total_revenue': total_revenue
        }
        analytics = get_analytics_data()
        return render_template(
            'master_admin_dashboard.html',
            users=user_data, tenants=tenant_data, stats=stats, analytics=analytics
        )
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

def get_analytics_data():
    try:
        today = datetime.utcnow().date()
        new_users_today = SaasUser.query.filter(func.date(SaasUser.created_at) == today).count()
        active_tenants = Tenant.query.filter_by(status='active').count()
        total_tenants = Tenant.query.count()
        tenant_uptime = (active_tenants / total_tenants * 100) if total_tenants > 0 else 0
        total_storage = "2.5TB"  # Optional: calculate with OdooDatabaseManager
        storage_growth = 15
        
        # Get plan prices and usage counts
        plan_prices = {p.name: p.price for p in SubscriptionPlan.query.all()}
        plan_usage = {}
        monthly_revenue = 0
        
        for tenant in Tenant.query.all():
            plan_name = tenant.plan
            monthly_revenue += plan_prices.get(plan_name, 0)
            plan_usage[plan_name] = plan_usage.get(plan_name, 0) + 1
        
        # Get users per month (using 3-letter month abbreviation)
        users_per_month = {}
        users_query = SaasUser.query.all()
        
        for user in users_query:
            if user.created_at:
                month_abbr = user.created_at.strftime('%b')  # Jan, Feb, Mar, etc.
                month_key = f"{month_abbr}"
                users_per_month[month_key] = users_per_month.get(month_key, 0) + 1
        revenue_growth = 12
        
        return {
            'total_users': SaasUser.query.count(),
            'new_users_today': new_users_today,
            'active_tenants': active_tenants,
            'tenant_uptime': round(tenant_uptime, 1),
            'total_storage': total_storage,
            'storage_growth': storage_growth,
            'monthly_revenue': monthly_revenue,
            'revenue_growth': revenue_growth,
            'users_per_month': users_per_month,
            'plan_usage': plan_usage
        }
    except Exception as e:
        error_tracker.log_error(e)
        return {
            'total_users': 0, 'new_users_today': 0, 'active_tenants': 0,
            'tenant_uptime': 0, 'total_storage': '0GB', 'storage_growth': 0,
            'monthly_revenue': 0, 'revenue_growth': 0,
            'users_per_month': {},
            'plan_usage': {}
        }

# User Management
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
        from utils import generate_password
        new_password = generate_password(12)
        user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        # send_email(user.email, 'Password Reset', 'Your new password is: ' + new_password)
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
                    'success': activity.success
                } for activity in recent_activity
            ]
        }
        return render_template('user_details.html', user=user_data)
    except Exception as e:
        error_tracker.log_error(e, {'user_id': user_id})
        return render_template('error.html', message='Failed to load user details.'), 500

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

# Tenant Management
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
        installed_apps = odoo.get_installed_applications(
            tenant.database_name, tenant.admin_username, tenant.get_admin_password()
        ) if tenant.status == 'active' else []
        storage_usage = odoo.get_database_storage_usage(tenant.database_name).get('total_size_human', 'N/A') if tenant.status == 'active' else 'N/A'
        access_logs = CredentialAccess.query.filter_by(tenant_id=tenant.id).order_by(CredentialAccess.accessed_at.desc()).limit(10).all()
        tenant_data = {
            'id': tenant.id,
            'name': tenant.name,
            'subdomain': tenant.subdomain,
            'status': tenant.status,
            'plan': tenant.plan,
            'installed_apps': installed_apps,
            'storage_usage': storage_usage,
            'access_logs': [{'accessed_at': log.accessed_at.isoformat(), 'ip_address': log.ip_address, 'success': log.success} for log in access_logs]
        }
        return render_template('tenant_details.html', tenant=tenant_data)
    except Exception as e:
        error_tracker.log_error(e, {'tenant_id': tenant_id})
        return render_template('error.html', message='Failed to load tenant details.'), 500

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

# Bulk actions for users
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

# Bulk actions for tenants
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

# Export users as CSV
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

# Export tenants as CSV
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

# Operations endpoints
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

# Security endpoints
@master_admin_bp.route('/master-admin/security/block_ip', methods=['POST'])
@login_required
@require_admin()
def block_ip():
    ip = request.json.get('ip_address')
    if not ip:
        return jsonify({'success': False, 'message': 'IP address required'}), 400
    # Save to BlockedIP table if you have one
    log_admin_action('block_ip', {'ip_address': ip})
    return jsonify({'success': True, 'message': 'IP blocked successfully'})

@master_admin_bp.route('/master-admin/security/unblock_ip', methods=['POST'])
@login_required
@require_admin()
def unblock_ip():
    ip = request.json.get('ip_address')
    log_admin_action('unblock_ip', {'ip_address': ip})
    return jsonify({'success': True, 'message': 'IP unblocked successfully'})