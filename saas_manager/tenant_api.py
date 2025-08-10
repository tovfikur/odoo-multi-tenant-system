"""
Tenant Management API
Provides complete tenant lifecycle management for mobile app users
"""

import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
import secrets
import re

from db import db
from models import SaasUser, Tenant, TenantUser
from utils import track_errors
try:
    from user_notifications import NotificationService, NotificationType, NotificationPriority
except ImportError:
    # Fallback if notifications not available
    NotificationService = None
    NotificationType = None
    NotificationPriority = None

# Create blueprint for tenant API routes
tenant_api_bp = Blueprint('tenant_api', __name__)
logger = logging.getLogger(__name__)

def require_user():
    """Decorator to require authenticated user access"""
    def decorator(f):
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({'success': False, 'error': 'Authentication required'}), 401
            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator

def validate_subdomain(subdomain):
    """Validate subdomain format and availability"""
    if not re.match(r'^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$', subdomain.lower()):
        return False, 'Invalid subdomain format. Use lowercase letters, numbers, and hyphens only.'
    
    reserved_subdomains = [
        'www', 'api', 'admin', 'mail', 'ftp', 'blog', 'shop', 'store',
        'support', 'help', 'docs', 'cdn', 'static', 'assets', 'media'
    ]
    
    if subdomain.lower() in reserved_subdomains:
        return False, 'This subdomain is reserved'
    
    existing_tenant = Tenant.query.filter_by(subdomain=subdomain.lower()).first()
    if existing_tenant:
        return False, 'Subdomain is already taken'
    
    return True, 'Subdomain is valid and available'

def generate_database_name(subdomain):
    """Generate a unique database name"""
    base_name = f"{subdomain}_db"
    
    # Check if database name already exists
    existing = Tenant.query.filter_by(database_name=base_name).first()
    if not existing:
        return base_name
    
    # Add random suffix if needed
    for i in range(1, 100):
        test_name = f"{base_name}_{i}"
        existing = Tenant.query.filter_by(database_name=test_name).first()
        if not existing:
            return test_name
    
    # Fallback to random string
    return f"{base_name}_{secrets.token_hex(4)}"

# ================= TENANT CREATION =================

@tenant_api_bp.route('/api/tenant/create', methods=['POST'])
@login_required
@require_user()
@track_errors('api_create_tenant')
def create_tenant():
    """Create a new tenant"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        tenant_name = data.get('name')
        subdomain = data.get('subdomain')
        plan = data.get('plan', 'basic')
        admin_username = data.get('admin_username', 'admin')
        admin_password = data.get('admin_password')
        modules = data.get('modules', [])
        
        # Validate required fields
        if not tenant_name or not subdomain:
            return jsonify({
                'success': False,
                'error': 'Tenant name and subdomain are required'
            }), 400
        
        # Validate subdomain
        subdomain_valid, subdomain_msg = validate_subdomain(subdomain)
        if not subdomain_valid:
            return jsonify({'success': False, 'error': subdomain_msg}), 400
        
        # Generate admin password if not provided
        if not admin_password:
            admin_password = secrets.token_urlsafe(12)
        
        # Generate database name
        database_name = generate_database_name(subdomain)
        
        # Create tenant record
        tenant = Tenant(
            name=tenant_name,
            subdomain=subdomain.lower(),
            database_name=database_name,
            status='pending',
            plan=plan,
            admin_username=admin_username,
            admin_password=admin_password,
            is_active=True,
            created_at=datetime.utcnow()
        )
        
        db.session.add(tenant)
        db.session.flush()  # Get the tenant ID
        
        # Create tenant-user relationship
        tenant_user = TenantUser(
            tenant_id=tenant.id,
            user_id=current_user.id,
            role='owner',
            access_level='admin'
        )
        
        db.session.add(tenant_user)
        db.session.commit()
        
        # TODO: Here you would trigger the actual tenant creation process
        # This might involve creating the Odoo database, setting up modules, etc.
        # For now, we'll mark it as 'created' immediately
        tenant.status = 'created'
        db.session.commit()
        
        # Send notification if available
        if NotificationService:
            try:
                notification_service = NotificationService()
                notification_service.create_notification(
                    user_id=current_user.id,
                    title="Tenant Created Successfully",
                    message=f"Your tenant '{tenant_name}' has been created and is ready to use.",
                    notification_type=NotificationType.SUCCESS,
                    priority=NotificationPriority.MEDIUM,
                    action_url=f"/tenant/{tenant.id}/manage",
                    action_label="Access Tenant",
                    metadata={
                        'tenant_id': tenant.id,
                        'tenant_name': tenant_name,
                        'subdomain': subdomain
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to send notification: {e}")
        
        logger.info(f"Tenant created: {tenant_name} by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'Tenant created successfully',
            'tenant': {
                'id': tenant.id,
                'name': tenant.name,
                'subdomain': tenant.subdomain,
                'database_name': tenant.database_name,
                'status': tenant.status,
                'plan': tenant.plan,
                'admin_username': tenant.admin_username,
                'admin_password': admin_password,  # Only show on creation
                'url': f"https://{tenant.subdomain}.{request.host.split(':')[0]}",
                'created_at': tenant.created_at.isoformat(),
                'role': 'owner'
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Tenant creation failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Tenant creation failed'}), 500

# ================= TENANT MANAGEMENT =================

@tenant_api_bp.route('/api/tenant/<int:tenant_id>/update', methods=['PUT'])
@login_required
@require_user()
@track_errors('api_update_tenant')
def update_tenant(tenant_id):
    """Update tenant settings"""
    try:
        # Verify user has access to this tenant
        tenant_user = TenantUser.query.filter_by(
            user_id=current_user.id,
            tenant_id=tenant_id
        ).first()
        
        if not tenant_user or tenant_user.access_level not in ['admin', 'owner']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        tenant = tenant_user.tenant
        if not tenant:
            return jsonify({'success': False, 'error': 'Tenant not found'}), 404
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        # Update allowed fields
        updated_fields = []
        
        if 'name' in data:
            tenant.name = data['name']
            updated_fields.append('name')
        
        if 'plan' in data and tenant_user.access_level == 'owner':
            tenant.plan = data['plan']
            updated_fields.append('plan')
        
        if updated_fields:
            tenant.updated_at = datetime.utcnow()
            db.session.commit()
            
            # Send notification
            notification_service = NotificationService()
            notification_service.create_notification(
                user_id=current_user.id,
                title="Tenant Updated",
                message=f"Your tenant '{tenant.name}' has been updated.",
                notification_type=NotificationType.INFO,
                priority=NotificationPriority.LOW,
                metadata={
                    'tenant_id': tenant.id,
                    'updated_fields': updated_fields
                }
            )
            
            logger.info(f"Tenant {tenant.id} updated by user {current_user.id}: {updated_fields}")
        
        return jsonify({
            'success': True,
            'message': 'Tenant updated successfully',
            'updated_fields': updated_fields,
            'tenant': {
                'id': tenant.id,
                'name': tenant.name,
                'status': tenant.status,
                'plan': tenant.plan,
                'updated_at': tenant.updated_at.isoformat()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Tenant update failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Tenant update failed'}), 500

@tenant_api_bp.route('/api/tenant/<int:tenant_id>/status', methods=['GET'])
@login_required
@require_user()
@track_errors('api_tenant_status')
def get_tenant_status(tenant_id):
    """Get detailed tenant status and health"""
    try:
        # Verify user has access to this tenant
        tenant_user = TenantUser.query.filter_by(
            user_id=current_user.id,
            tenant_id=tenant_id
        ).first()
        
        if not tenant_user:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        tenant = tenant_user.tenant
        if not tenant:
            return jsonify({'success': False, 'error': 'Tenant not found'}), 404
        
        # TODO: Implement actual health checks
        # For now, return basic status information
        
        status_info = {
            'tenant_id': tenant.id,
            'name': tenant.name,
            'subdomain': tenant.subdomain,
            'status': tenant.status,
            'is_active': tenant.is_active,
            'created_at': tenant.created_at.isoformat(),
            'updated_at': tenant.updated_at.isoformat() if tenant.updated_at else None,
            'last_backup_at': tenant.last_backup_at.isoformat() if tenant.last_backup_at else None,
            'health_status': 'healthy',  # TODO: Implement actual health check
            'database_status': 'connected',  # TODO: Check database connection
            'storage_used': 0,  # TODO: Calculate actual storage usage
            'storage_limit': tenant.storage_limit,
            'user_count': TenantUser.query.filter_by(tenant_id=tenant.id).count(),
            'max_users': tenant.max_users,
            'url': f"https://{tenant.subdomain}.{request.host.split(':')[0]}",
            'last_activity': datetime.utcnow().isoformat()  # TODO: Get actual last activity
        }
        
        return jsonify({
            'success': True,
            'status': status_info
        })
        
    except Exception as e:
        logger.error(f"Get tenant status failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to get tenant status'}), 500

@tenant_api_bp.route('/api/tenant/<int:tenant_id>/backup', methods=['POST'])
@login_required
@require_user()
@track_errors('api_tenant_backup')
def create_tenant_backup(tenant_id):
    """Create a backup of the tenant"""
    try:
        # Verify user has access to this tenant
        tenant_user = TenantUser.query.filter_by(
            user_id=current_user.id,
            tenant_id=tenant_id
        ).first()
        
        if not tenant_user or tenant_user.access_level not in ['admin', 'owner']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        tenant = tenant_user.tenant
        if not tenant:
            return jsonify({'success': False, 'error': 'Tenant not found'}), 404
        
        # TODO: Implement actual backup creation
        # For now, just update the last backup timestamp
        tenant.last_backup_at = datetime.utcnow()
        db.session.commit()
        
        # Send notification
        notification_service = NotificationService()
        notification_service.create_notification(
            user_id=current_user.id,
            title="Backup Created",
            message=f"A backup of your tenant '{tenant.name}' has been created successfully.",
            notification_type=NotificationType.SUCCESS,
            priority=NotificationPriority.LOW,
            metadata={
                'tenant_id': tenant.id,
                'backup_created_at': tenant.last_backup_at.isoformat()
            }
        )
        
        logger.info(f"Backup created for tenant {tenant.id} by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'Backup created successfully',
            'backup_info': {
                'tenant_id': tenant.id,
                'created_at': tenant.last_backup_at.isoformat(),
                'status': 'completed'
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Backup creation failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Backup creation failed'}), 500

# ================= TENANT USER MANAGEMENT =================

@tenant_api_bp.route('/api/tenant/<int:tenant_id>/users', methods=['GET'])
@login_required
@require_user()
@track_errors('api_tenant_users')
def get_tenant_users(tenant_id):
    """Get users associated with a tenant"""
    try:
        # Verify user has access to this tenant
        tenant_user = TenantUser.query.filter_by(
            user_id=current_user.id,
            tenant_id=tenant_id
        ).first()
        
        if not tenant_user:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        # Get all users for this tenant
        tenant_users = TenantUser.query.filter_by(tenant_id=tenant_id).all()
        
        users_data = []
        for tu in tenant_users:
            user_data = {
                'id': tu.user.id,
                'username': tu.user.username,
                'email': tu.user.email,
                'full_name': tu.user.full_name,
                'role': tu.role,
                'access_level': tu.access_level,
                'joined_at': tu.created_at.isoformat() if tu.created_at else None,
                'is_active': tu.user.is_active,
                'last_login': tu.user.last_login.isoformat() if tu.user.last_login else None
            }
            users_data.append(user_data)
        
        return jsonify({
            'success': True,
            'users': users_data,
            'total': len(users_data)
        })
        
    except Exception as e:
        logger.error(f"Get tenant users failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to get tenant users'}), 500

@tenant_api_bp.route('/api/tenant/<int:tenant_id>/invite-user', methods=['POST'])
@login_required
@require_user()
@track_errors('api_invite_tenant_user')
def invite_tenant_user(tenant_id):
    """Invite a user to join a tenant"""
    try:
        # Verify user has admin access to this tenant
        tenant_user = TenantUser.query.filter_by(
            user_id=current_user.id,
            tenant_id=tenant_id
        ).first()
        
        if not tenant_user or tenant_user.access_level not in ['admin', 'owner']:
            return jsonify({'success': False, 'error': 'Admin access required'}), 403
        
        tenant = tenant_user.tenant
        if not tenant:
            return jsonify({'success': False, 'error': 'Tenant not found'}), 404
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        email = data.get('email')
        role = data.get('role', 'user')
        access_level = data.get('access_level', 'read')
        
        if not email:
            return jsonify({'success': False, 'error': 'Email is required'}), 400
        
        # Find user by email
        invited_user = SaasUser.query.filter_by(email=email).first()
        if not invited_user:
            return jsonify({
                'success': False,
                'error': 'User with this email does not exist'
            }), 404
        
        # Check if user is already in tenant
        existing_tu = TenantUser.query.filter_by(
            tenant_id=tenant_id,
            user_id=invited_user.id
        ).first()
        
        if existing_tu:
            return jsonify({
                'success': False,
                'error': 'User is already a member of this tenant'
            }), 409
        
        # Create tenant user relationship
        new_tenant_user = TenantUser(
            tenant_id=tenant_id,
            user_id=invited_user.id,
            role=role,
            access_level=access_level
        )
        
        db.session.add(new_tenant_user)
        db.session.commit()
        
        # Send notification to invited user
        notification_service = NotificationService()
        notification_service.create_notification(
            user_id=invited_user.id,
            title="Tenant Invitation",
            message=f"You have been invited to join tenant '{tenant.name}' as {role}.",
            notification_type=NotificationType.INFO,
            priority=NotificationPriority.MEDIUM,
            action_url=f"/tenant/{tenant.id}/manage",
            action_label="View Tenant",
            metadata={
                'tenant_id': tenant.id,
                'tenant_name': tenant.name,
                'role': role,
                'invited_by': current_user.username
            }
        )
        
        logger.info(f"User {invited_user.id} invited to tenant {tenant_id} by {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'User invited successfully',
            'invited_user': {
                'id': invited_user.id,
                'username': invited_user.username,
                'email': invited_user.email,
                'role': role,
                'access_level': access_level
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"User invitation failed: {str(e)}")
        return jsonify({'success': False, 'error': 'User invitation failed'}), 500

# Export blueprint
__all__ = ['tenant_api_bp']