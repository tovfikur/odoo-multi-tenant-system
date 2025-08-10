"""
Public API Endpoints
Provides API endpoints for public access (registration, authentication, landing pages, etc.)
"""

import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import re

from db import db
from models import SaasUser, Tenant
from utils import track_errors

# Create blueprint for public API routes
public_api_bp = Blueprint('public_api', __name__)
logger = logging.getLogger(__name__)

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r'[A-Za-z]', password):
        return False, "Password must contain at least one letter"
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    return True, "Password is valid"

def validate_username(username):
    """Validate username format"""
    if len(username) < 3:
        return False, "Username must be at least 3 characters long"
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "Username can only contain letters, numbers, and underscores"
    return True, "Username is valid"

# ================= AUTHENTICATION ENDPOINTS =================

@public_api_bp.route('/api/public/register', methods=['POST'])
@track_errors('api_public_register')
def api_register():
    """User registration API endpoint"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        full_name = data.get('full_name')
        company = data.get('company')
        phone = data.get('phone')
        
        # Validate required fields
        if not username or not email or not password:
            return jsonify({
                'success': False,
                'error': 'Username, email, and password are required'
            }), 400
        
        # Validate username
        username_valid, username_msg = validate_username(username)
        if not username_valid:
            return jsonify({'success': False, 'error': username_msg}), 400
        
        # Validate email
        if not validate_email(email):
            return jsonify({'success': False, 'error': 'Invalid email format'}), 400
        
        # Validate password
        password_valid, password_msg = validate_password(password)
        if not password_valid:
            return jsonify({'success': False, 'error': password_msg}), 400
        
        # Check if username already exists
        if SaasUser.query.filter_by(username=username).first():
            return jsonify({'success': False, 'error': 'Username already exists'}), 409
        
        # Check if email already exists
        if SaasUser.query.filter_by(email=email).first():
            return jsonify({'success': False, 'error': 'Email already exists'}), 409
        
        # Create new user
        user = SaasUser(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            full_name=full_name,
            company=company,
            phone=phone,
            is_active=True
        )
        
        db.session.add(user)
        db.session.commit()
        
        logger.info(f"New user registered: {username} ({email})")
        
        # Return user data (without sensitive information)
        return jsonify({
            'success': True,
            'message': 'Registration successful',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'full_name': user.full_name,
                'company': user.company,
                'created_at': user.created_at.isoformat() if user.created_at else None
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Registration failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Registration failed'}), 500

@public_api_bp.route('/api/public/login', methods=['POST'])
@track_errors('api_public_login')
def api_login():
    """User login API endpoint"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        identifier = data.get('username') or data.get('email')
        password = data.get('password')
        remember_me = data.get('remember_me', False)
        
        if not identifier or not password:
            return jsonify({
                'success': False,
                'error': 'Username/email and password are required'
            }), 400
        
        # Find user by username or email
        user = SaasUser.query.filter(
            (SaasUser.username == identifier) | (SaasUser.email == identifier)
        ).first()
        
        if not user:
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
        
        # Check if account is locked
        if user.account_locked_until and user.account_locked_until > datetime.utcnow():
            return jsonify({
                'success': False,
                'error': 'Account is temporarily locked due to failed login attempts'
            }), 423
        
        # Verify password
        if not check_password_hash(user.password_hash, password):
            # Increment failed login attempts
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            
            # Lock account after 5 failed attempts
            if user.failed_login_attempts >= 5:
                user.account_locked_until = datetime.utcnow() + timedelta(hours=1)
                db.session.commit()
                return jsonify({
                    'success': False,
                    'error': 'Account locked due to too many failed login attempts'
                }), 423
            
            db.session.commit()
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
        
        # Check if account is active
        if not user.is_active:
            return jsonify({
                'success': False,
                'error': 'Account is deactivated. Please contact support.'
            }), 403
        
        # Successful login
        user.failed_login_attempts = 0
        user.account_locked_until = None
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        # Login user session
        login_user(user, remember=remember_me)
        
        logger.info(f"User logged in: {user.username}")
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'full_name': user.full_name,
                'is_admin': user.is_admin,
                'last_login': user.last_login.isoformat() if user.last_login else None
            }
        })
        
    except Exception as e:
        logger.error(f"Login failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Login failed'}), 500

@public_api_bp.route('/api/public/logout', methods=['POST'])
@track_errors('api_public_logout')
def api_logout():
    """User logout API endpoint"""
    try:
        if current_user.is_authenticated:
            username = current_user.username
            logout_user()
            logger.info(f"User logged out: {username}")
            return jsonify({'success': True, 'message': 'Logout successful'})
        else:
            return jsonify({'success': False, 'error': 'Not logged in'}), 401
            
    except Exception as e:
        logger.error(f"Logout failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Logout failed'}), 500

@public_api_bp.route('/api/public/check-auth', methods=['GET'])
@track_errors('api_public_check_auth')
def api_check_auth():
    """Check if user is authenticated"""
    try:
        if current_user.is_authenticated:
            return jsonify({
                'success': True,
                'authenticated': True,
                'user': {
                    'id': current_user.id,
                    'username': current_user.username,
                    'email': current_user.email,
                    'full_name': current_user.full_name,
                    'is_admin': current_user.is_admin
                }
            })
        else:
            return jsonify({
                'success': True,
                'authenticated': False,
                'user': None
            })
            
    except Exception as e:
        logger.error(f"Auth check failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Authentication check failed'}), 500

# ================= PASSWORD RESET ENDPOINTS =================

@public_api_bp.route('/api/public/forgot-password', methods=['POST'])
@track_errors('api_public_forgot_password')
def api_forgot_password():
    """Initiate password reset process"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        email = data.get('email')
        if not email:
            return jsonify({'success': False, 'error': 'Email is required'}), 400
        
        if not validate_email(email):
            return jsonify({'success': False, 'error': 'Invalid email format'}), 400
        
        user = SaasUser.query.filter_by(email=email).first()
        
        # Always return success to prevent email enumeration
        if user:
            # Generate reset token
            reset_token = user.generate_reset_token()
            db.session.commit()
            
            # TODO: Send email with reset link
            # For now, we'll just log it (in production, implement email sending)
            logger.info(f"Password reset requested for {email}, token: {reset_token}")
            
            # In a real implementation, you would send an email here
            # send_password_reset_email(user.email, reset_token)
        
        return jsonify({
            'success': True,
            'message': 'If the email exists, a password reset link has been sent'
        })
        
    except Exception as e:
        logger.error(f"Forgot password failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Password reset request failed'}), 500

@public_api_bp.route('/api/public/reset-password', methods=['POST'])
@track_errors('api_public_reset_password')
def api_reset_password():
    """Reset password with token"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        token = data.get('token')
        new_password = data.get('new_password')
        
        if not token or not new_password:
            return jsonify({
                'success': False,
                'error': 'Token and new password are required'
            }), 400
        
        # Validate new password
        password_valid, password_msg = validate_password(new_password)
        if not password_valid:
            return jsonify({'success': False, 'error': password_msg}), 400
        
        # Find user by token
        user = SaasUser.query.filter_by(reset_token=token).first()
        
        if not user or not user.verify_reset_token(token):
            return jsonify({
                'success': False,
                'error': 'Invalid or expired reset token'
            }), 400
        
        # Reset password
        user.password_hash = generate_password_hash(new_password)
        user.last_password_change = datetime.utcnow()
        user.failed_login_attempts = 0
        user.account_locked_until = None
        user.clear_reset_token()
        
        db.session.commit()
        
        logger.info(f"Password reset successful for user: {user.username}")
        
        return jsonify({
            'success': True,
            'message': 'Password reset successful'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Password reset failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Password reset failed'}), 500

@public_api_bp.route('/api/public/verify-reset-token', methods=['POST'])
@track_errors('api_public_verify_reset_token')
def api_verify_reset_token():
    """Verify if a reset token is valid"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        token = data.get('token')
        if not token:
            return jsonify({'success': False, 'error': 'Token is required'}), 400
        
        user = SaasUser.query.filter_by(reset_token=token).first()
        
        if user and user.verify_reset_token(token):
            return jsonify({
                'success': True,
                'valid': True,
                'email': user.email  # Show email for confirmation
            })
        else:
            return jsonify({
                'success': True,
                'valid': False,
                'error': 'Invalid or expired token'
            })
            
    except Exception as e:
        logger.error(f"Token verification failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Token verification failed'}), 500

# ================= PUBLIC INFORMATION ENDPOINTS =================

@public_api_bp.route('/api/public/check-username', methods=['POST'])
@track_errors('api_public_check_username')
def api_check_username():
    """Check if username is available"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        username = data.get('username')
        if not username:
            return jsonify({'success': False, 'error': 'Username is required'}), 400
        
        # Validate username format
        username_valid, username_msg = validate_username(username)
        if not username_valid:
            return jsonify({
                'success': True,
                'available': False,
                'reason': username_msg
            })
        
        # Check availability
        existing_user = SaasUser.query.filter_by(username=username).first()
        
        return jsonify({
            'success': True,
            'available': existing_user is None,
            'username': username
        })
        
    except Exception as e:
        logger.error(f"Username check failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Username check failed'}), 500

@public_api_bp.route('/api/public/check-email', methods=['POST'])
@track_errors('api_public_check_email')
def api_check_email():
    """Check if email is available"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        email = data.get('email')
        if not email:
            return jsonify({'success': False, 'error': 'Email is required'}), 400
        
        # Validate email format
        if not validate_email(email):
            return jsonify({
                'success': True,
                'available': False,
                'reason': 'Invalid email format'
            })
        
        # Check availability
        existing_user = SaasUser.query.filter_by(email=email).first()
        
        return jsonify({
            'success': True,
            'available': existing_user is None,
            'email': email
        })
        
    except Exception as e:
        logger.error(f"Email check failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Email check failed'}), 500

@public_api_bp.route('/api/public/validate-subdomain', methods=['POST'])
@track_errors('api_public_validate_subdomain')
def api_validate_subdomain():
    """Validate subdomain availability and format"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        subdomain = data.get('subdomain')
        if not subdomain:
            return jsonify({'success': False, 'error': 'Subdomain is required'}), 400
        
        # Validate subdomain format
        if not re.match(r'^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$', subdomain.lower()):
            return jsonify({
                'success': True,
                'available': False,
                'valid': False,
                'reason': 'Invalid subdomain format. Use lowercase letters, numbers, and hyphens only.'
            })
        
        # Check reserved subdomains
        reserved_subdomains = [
            'www', 'api', 'admin', 'mail', 'ftp', 'blog', 'shop', 'store',
            'support', 'help', 'docs', 'cdn', 'static', 'assets', 'media'
        ]
        
        if subdomain.lower() in reserved_subdomains:
            return jsonify({
                'success': True,
                'available': False,
                'valid': True,
                'reason': 'This subdomain is reserved'
            })
        
        # Check if subdomain is already taken
        existing_tenant = Tenant.query.filter_by(subdomain=subdomain.lower()).first()
        
        return jsonify({
            'success': True,
            'available': existing_tenant is None,
            'valid': True,
            'subdomain': subdomain.lower()
        })
        
    except Exception as e:
        logger.error(f"Subdomain validation failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Subdomain validation failed'}), 500

@public_api_bp.route('/api/public/system-status', methods=['GET'])
@track_errors('api_public_system_status')
def api_system_status():
    """Get public system status information"""
    try:
        # Get basic system stats (public information only)
        total_tenants = Tenant.query.filter_by(is_active=True).count()
        total_users = SaasUser.query.filter_by(is_active=True).count()
        
        return jsonify({
            'success': True,
            'system_status': {
                'status': 'operational',
                'total_active_tenants': total_tenants,
                'total_active_users': total_users,
                'api_version': '1.0',
                'maintenance_mode': False,  # You can implement this based on your needs
                'last_updated': datetime.utcnow().isoformat()
            }
        })
        
    except Exception as e:
        logger.error(f"System status check failed: {str(e)}")
        return jsonify({'success': False, 'error': 'System status check failed'}), 500

# Export blueprint
__all__ = ['public_api_bp']