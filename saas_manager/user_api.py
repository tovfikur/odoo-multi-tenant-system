"""
User API Endpoints
Provides comprehensive REST API endpoints for regular users (non-admin)
"""

import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import os
import secrets

from db import db
from models import SaasUser, Tenant, TenantUser, UserPublicKey, AuditLog
from utils import track_errors

# Create blueprint for user API routes
user_api_bp = Blueprint('user_api', __name__)
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

# ================= USER PROFILE MANAGEMENT =================

@user_api_bp.route('/api/user/profile', methods=['GET'])
@login_required
@require_user()
@track_errors('api_get_user_profile')
def get_user_profile():
    """Get current user's profile information"""
    try:
        user_data = {
            'id': current_user.id,
            'username': current_user.username,
            'email': current_user.email,
            'full_name': current_user.full_name,
            'bio': current_user.bio,
            'company': current_user.company,
            'location': current_user.location,
            'website': current_user.website,
            'phone': current_user.phone,
            'timezone': current_user.timezone,
            'language': current_user.language,
            'profile_picture_url': current_user.get_profile_picture_url(),
            'avatar_initials': current_user.get_avatar_initials(),
            'is_active': current_user.is_active,
            'created_at': current_user.created_at.isoformat() if current_user.created_at else None,
            'last_login': current_user.last_login.isoformat() if current_user.last_login else None,
            'notification_preferences': current_user.notification_preferences or {},
            'two_factor_enabled': current_user.two_factor_enabled,
            'last_password_change': current_user.last_password_change.isoformat() if current_user.last_password_change else None
        }
        
        return jsonify({
            'success': True,
            'user': user_data
        })
        
    except Exception as e:
        logger.error(f"Failed to get user profile for user {current_user.id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@user_api_bp.route('/api/user/profile', methods=['PUT'])
@login_required
@require_user()
@track_errors('api_update_user_profile')
def update_user_profile():
    """Update current user's profile information"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        # Update allowed fields
        updatable_fields = [
            'full_name', 'bio', 'company', 'location', 'website', 
            'phone', 'timezone', 'language', 'notification_preferences'
        ]
        
        updated_fields = []
        for field in updatable_fields:
            if field in data:
                setattr(current_user, field, data[field])
                updated_fields.append(field)
        
        # Update timestamp
        current_user.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Log the update
        audit_log = AuditLog(
            user_id=current_user.id,
            action="PROFILE_UPDATED",
            details={'updated_fields': updated_fields},
            ip_address=request.remote_addr
        )
        db.session.add(audit_log)
        db.session.commit()
        
        logger.info(f"User {current_user.id} updated profile: {updated_fields}")
        
        return jsonify({
            'success': True,
            'message': 'Profile updated successfully',
            'updated_fields': updated_fields
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update profile for user {current_user.id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@user_api_bp.route('/api/user/password', methods=['PUT'])
@login_required
@require_user()
@track_errors('api_change_password')
def change_password():
    """Change user's password"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        
        if not current_password or not new_password:
            return jsonify({
                'success': False, 
                'error': 'Current password and new password are required'
            }), 400
        
        # Verify current password
        if not check_password_hash(current_user.password_hash, current_password):
            return jsonify({'success': False, 'error': 'Current password is incorrect'}), 400
        
        # Validate new password strength
        if len(new_password) < 8:
            return jsonify({
                'success': False, 
                'error': 'New password must be at least 8 characters long'
            }), 400
        
        # Update password
        current_user.password_hash = generate_password_hash(new_password)
        current_user.last_password_change = datetime.utcnow()
        db.session.commit()
        
        # Log the password change
        audit_log = AuditLog(
            user_id=current_user.id,
            action="PASSWORD_CHANGED",
            details={'changed_at': datetime.utcnow().isoformat()},
            ip_address=request.remote_addr
        )
        db.session.add(audit_log)
        db.session.commit()
        
        logger.info(f"User {current_user.id} changed password")
        
        return jsonify({
            'success': True,
            'message': 'Password changed successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to change password for user {current_user.id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@user_api_bp.route('/api/user/avatar', methods=['POST'])
@login_required
@require_user()
@track_errors('api_upload_avatar')
def upload_avatar():
    """Upload user avatar image"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        # Validate file type
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
        if not ('.' in file.filename and 
                file.filename.rsplit('.', 1)[1].lower() in allowed_extensions):
            return jsonify({
                'success': False, 
                'error': 'Invalid file type. Allowed: png, jpg, jpeg, gif'
            }), 400
        
        # Generate secure filename
        filename = secure_filename(f"{current_user.id}_{secrets.token_hex(8)}_{file.filename}")
        
        # Create upload directory if it doesn't exist
        upload_dir = os.path.join('static', 'uploads', 'profiles')
        os.makedirs(upload_dir, exist_ok=True)
        
        # Save file
        file_path = os.path.join(upload_dir, filename)
        file.save(file_path)
        
        # Remove old profile picture if exists
        if current_user.profile_picture:
            old_file_path = os.path.join(upload_dir, current_user.profile_picture)
            if os.path.exists(old_file_path):
                os.remove(old_file_path)
        
        # Update user profile
        current_user.profile_picture = filename
        db.session.commit()
        
        # Log the upload
        audit_log = AuditLog(
            user_id=current_user.id,
            action="AVATAR_UPLOADED",
            details={'filename': filename},
            ip_address=request.remote_addr
        )
        db.session.add(audit_log)
        db.session.commit()
        
        logger.info(f"User {current_user.id} uploaded new avatar: {filename}")
        
        return jsonify({
            'success': True,
            'message': 'Avatar uploaded successfully',
            'avatar_url': current_user.get_profile_picture_url()
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to upload avatar for user {current_user.id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@user_api_bp.route('/api/user/avatar', methods=['DELETE'])
@login_required
@require_user()
@track_errors('api_delete_avatar')
def delete_avatar():
    """Delete user's avatar image"""
    try:
        if not current_user.profile_picture:
            return jsonify({'success': False, 'error': 'No avatar to delete'}), 400
        
        # Remove file from filesystem
        upload_dir = os.path.join('static', 'uploads', 'profiles')
        file_path = os.path.join(upload_dir, current_user.profile_picture)
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Update database
        current_user.profile_picture = None
        db.session.commit()
        
        # Log the deletion
        audit_log = AuditLog(
            user_id=current_user.id,
            action="AVATAR_DELETED",
            details={},
            ip_address=request.remote_addr
        )
        db.session.add(audit_log)
        db.session.commit()
        
        logger.info(f"User {current_user.id} deleted avatar")
        
        return jsonify({
            'success': True,
            'message': 'Avatar deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete avatar for user {current_user.id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ================= USER TENANTS MANAGEMENT =================

@user_api_bp.route('/api/user/tenants', methods=['GET'])
@login_required
@require_user()
@track_errors('api_get_user_tenants')
def get_user_tenants():
    """Get all tenants accessible to the current user"""
    try:
        tenant_users = TenantUser.query.filter_by(user_id=current_user.id).all()
        
        tenants_data = []
        for tenant_user in tenant_users:
            tenant = tenant_user.tenant
            tenant_data = {
                'id': tenant.id,
                'name': tenant.name,
                'subdomain': tenant.subdomain,
                'database_name': tenant.database_name,
                'status': tenant.status,
                'plan': tenant.plan,
                'max_users': tenant.max_users,
                'storage_limit': tenant.storage_limit,
                'is_active': tenant.is_active,
                'created_at': tenant.created_at.isoformat() if tenant.created_at else None,
                'updated_at': tenant.updated_at.isoformat() if tenant.updated_at else None,
                'last_backup_at': tenant.last_backup_at.isoformat() if tenant.last_backup_at else None,
                'role': tenant_user.role,
                'access_level': tenant_user.access_level,
                'joined_at': tenant_user.created_at.isoformat() if tenant_user.created_at else None
            }
            tenants_data.append(tenant_data)
        
        return jsonify({
            'success': True,
            'tenants': tenants_data,
            'total': len(tenants_data)
        })
        
    except Exception as e:
        logger.error(f"Failed to get tenants for user {current_user.id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@user_api_bp.route('/api/user/tenants/<int:tenant_id>', methods=['GET'])
@login_required
@require_user()
@track_errors('api_get_user_tenant')
def get_user_tenant(tenant_id):
    """Get detailed information about a specific tenant"""
    try:
        # Verify user has access to this tenant
        tenant_user = TenantUser.query.filter_by(
            user_id=current_user.id, 
            tenant_id=tenant_id
        ).first()
        
        if not tenant_user:
            return jsonify({'success': False, 'error': 'Access denied to this tenant'}), 403
        
        tenant = tenant_user.tenant
        tenant_data = {
            'id': tenant.id,
            'name': tenant.name,
            'subdomain': tenant.subdomain,
            'database_name': tenant.database_name,
            'status': tenant.status,
            'plan': tenant.plan,
            'max_users': tenant.max_users,
            'storage_limit': tenant.storage_limit,
            'is_active': tenant.is_active,
            'created_at': tenant.created_at.isoformat() if tenant.created_at else None,
            'updated_at': tenant.updated_at.isoformat() if tenant.updated_at else None,
            'last_backup_at': tenant.last_backup_at.isoformat() if tenant.last_backup_at else None,
            'my_role': tenant_user.role,
            'my_access_level': tenant_user.access_level,
            'my_joined_at': tenant_user.created_at.isoformat() if tenant_user.created_at else None,
            'url': f"https://{tenant.subdomain}.{request.host.split(':')[0]}"
        }
        
        # Get all users in this tenant (if user has appropriate access)
        if tenant_user.access_level in ['admin', 'manager']:
            all_tenant_users = TenantUser.query.filter_by(tenant_id=tenant_id).all()
            tenant_data['users'] = [{
                'id': tu.user.id,
                'username': tu.user.username,
                'email': tu.user.email,
                'full_name': tu.user.full_name,
                'role': tu.role,
                'access_level': tu.access_level,
                'joined_at': tu.created_at.isoformat() if tu.created_at else None,
                'is_active': tu.user.is_active
            } for tu in all_tenant_users]
        
        return jsonify(tenant_data)
        
    except Exception as e:
        logger.error(f"Failed to get tenant {tenant_id} for user {current_user.id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ================= USER ACTIVITY AND AUDIT LOGS =================

@user_api_bp.route('/api/user/activity', methods=['GET'])
@login_required
@require_user()
@track_errors('api_get_user_activity')
def get_user_activity():
    """Get user's activity/audit logs"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        
        # Get user's audit logs
        logs_query = AuditLog.query.filter_by(user_id=current_user.id).order_by(
            AuditLog.created_at.desc()
        )
        
        logs_paginated = logs_query.paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        logs_data = []
        for log in logs_paginated.items:
            log_data = {
                'id': log.id,
                'action': log.action,
                'details': log.details,
                'ip_address': log.ip_address,
                'created_at': log.created_at.isoformat() if log.created_at else None
            }
            logs_data.append(log_data)
        
        return jsonify({
            'success': True,
            'logs': logs_data,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': logs_paginated.total,
                'pages': logs_paginated.pages,
                'has_next': logs_paginated.has_next,
                'has_prev': logs_paginated.has_prev
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get activity for user {current_user.id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ================= USER SECURITY SETTINGS =================

@user_api_bp.route('/api/user/security', methods=['GET'])
@login_required
@require_user()
@track_errors('api_get_security_settings')
def get_security_settings():
    """Get user's security settings and status"""
    try:
        # Get user's public keys
        public_keys = UserPublicKey.query.filter_by(user_id=current_user.id).all()
        
        security_data = {
            'two_factor_enabled': current_user.two_factor_enabled,
            'last_password_change': current_user.last_password_change.isoformat() if current_user.last_password_change else None,
            'failed_login_attempts': current_user.failed_login_attempts,
            'account_locked': current_user.account_locked_until is not None and current_user.account_locked_until > datetime.utcnow(),
            'public_keys_count': len(public_keys),
            'public_keys': [{
                'id': key.id,
                'name': key.name,
                'fingerprint': key.fingerprint,
                'created_at': key.created_at.isoformat() if key.created_at else None,
                'last_used': key.last_used.isoformat() if key.last_used else None
            } for key in public_keys]
        }
        
        return jsonify({
            'success': True,
            'security': security_data
        })
        
    except Exception as e:
        logger.error(f"Failed to get security settings for user {current_user.id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ================= USER PREFERENCES =================

@user_api_bp.route('/api/user/preferences', methods=['GET'])
@login_required
@require_user()
@track_errors('api_get_user_preferences')
def get_user_preferences():
    """Get user's preferences and settings"""
    try:
        preferences = {
            'timezone': current_user.timezone,
            'language': current_user.language,
            'notifications': current_user.notification_preferences or {},
            'theme': 'light',  # Default theme - can be extended
            'dashboard_layout': 'default'  # Default layout - can be extended
        }
        
        return jsonify({
            'success': True,
            'preferences': preferences
        })
        
    except Exception as e:
        logger.error(f"Failed to get preferences for user {current_user.id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@user_api_bp.route('/api/user/preferences', methods=['PUT'])
@login_required
@require_user()
@track_errors('api_update_user_preferences')
def update_user_preferences():
    """Update user's preferences and settings"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        updated_fields = []
        
        if 'timezone' in data:
            current_user.timezone = data['timezone']
            updated_fields.append('timezone')
        
        if 'language' in data:
            current_user.language = data['language']
            updated_fields.append('language')
        
        if 'notifications' in data:
            current_user.notification_preferences = data['notifications']
            updated_fields.append('notifications')
        
        db.session.commit()
        
        # Log the update
        audit_log = AuditLog(
            user_id=current_user.id,
            action="PREFERENCES_UPDATED",
            details={'updated_fields': updated_fields},
            ip_address=request.remote_addr
        )
        db.session.add(audit_log)
        db.session.commit()
        
        logger.info(f"User {current_user.id} updated preferences: {updated_fields}")
        
        return jsonify({
            'success': True,
            'message': 'Preferences updated successfully',
            'updated_fields': updated_fields
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update preferences for user {current_user.id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ================= USER NOTIFICATIONS =================

@user_api_bp.route('/api/user/notifications', methods=['GET'])
@login_required
@require_user()
@track_errors('api_get_user_notifications')
def get_user_notifications():
    """Get user's notifications"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        include_read = request.args.get('include_read', 'true').lower() == 'true'
        include_dismissed = request.args.get('include_dismissed', 'false').lower() == 'true'
        
        from user_notifications import UserNotification, NotificationService
        
        # Calculate offset
        offset = (page - 1) * per_page
        
        # Get notifications
        notification_service = NotificationService()
        notifications = notification_service.get_user_notifications(
            user_id=current_user.id,
            include_read=include_read,
            include_dismissed=include_dismissed,
            limit=per_page,
            offset=offset
        )
        
        # Get counts
        counts = notification_service.get_notification_counts(current_user.id)
        
        # Convert to dictionaries
        notifications_data = [notification.to_dict() for notification in notifications]
        
        return jsonify({
            'success': True,
            'notifications': notifications_data,
            'counts': counts,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': counts['total']
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get notifications for user {current_user.id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@user_api_bp.route('/api/user/notifications/counts', methods=['GET'])
@login_required
@require_user()
@track_errors('api_get_notification_counts')
def get_notification_counts():
    """Get notification counts for user"""
    try:
        from user_notifications import NotificationService
        
        notification_service = NotificationService()
        counts = notification_service.get_notification_counts(current_user.id)
        
        return jsonify({
            'success': True,
            'counts': counts
        })
        
    except Exception as e:
        logger.error(f"Failed to get notification counts for user {current_user.id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@user_api_bp.route('/api/user/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
@require_user()
@track_errors('api_mark_notification_read')
def mark_notification_read(notification_id):
    """Mark notification as read"""
    try:
        from user_notifications import NotificationService
        
        notification_service = NotificationService()
        success = notification_service.mark_as_read(notification_id, current_user.id)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Notification marked as read'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Notification not found or access denied'
            }), 404
        
    except Exception as e:
        logger.error(f"Failed to mark notification {notification_id} as read for user {current_user.id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@user_api_bp.route('/api/user/notifications/<int:notification_id>/dismiss', methods=['POST'])
@login_required
@require_user()
@track_errors('api_dismiss_notification')
def dismiss_notification(notification_id):
    """Dismiss notification"""
    try:
        from user_notifications import NotificationService
        
        notification_service = NotificationService()
        success = notification_service.dismiss_notification(notification_id, current_user.id)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Notification dismissed'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Notification not found or access denied'
            }), 404
        
    except Exception as e:
        logger.error(f"Failed to dismiss notification {notification_id} for user {current_user.id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@user_api_bp.route('/api/user/notifications/mark-all-read', methods=['POST'])
@login_required
@require_user()
@track_errors('api_mark_all_notifications_read')
def mark_all_notifications_read():
    """Mark all user's notifications as read"""
    try:
        from user_notifications import NotificationService
        
        notification_service = NotificationService()
        count = notification_service.mark_all_as_read(current_user.id)
        
        return jsonify({
            'success': True,
            'message': f'Marked {count} notifications as read',
            'count': count
        })
        
    except Exception as e:
        logger.error(f"Failed to mark all notifications as read for user {current_user.id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Export blueprint
__all__ = ['user_api_bp']