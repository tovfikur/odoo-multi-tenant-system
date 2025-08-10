"""
Billing and Subscription API
Provides comprehensive billing management with smart notifications
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from db import db
from models import SaasUser, Tenant, TenantUser
from utils import track_errors
try:
    from user_notifications import (
        NotificationService, NotificationType, NotificationPriority,
        notify_tenant_status_change
    )
except ImportError:
    # Fallback if notifications not available
    NotificationService = None
    NotificationType = None
    NotificationPriority = None
    notify_tenant_status_change = None

# Create blueprint for billing API routes
billing_api_bp = Blueprint('billing_api', __name__)
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

# ================= SUBSCRIPTION PLANS =================

SUBSCRIPTION_PLANS = {
    'free': {
        'name': 'Free Plan',
        'price': 0.00,
        'billing_cycle': 'monthly',
        'max_users': 3,
        'storage_limit': 1024,  # MB
        'features': [
            'Basic CRM functionality',
            'Email support',
            'Basic reporting',
            'Community updates'
        ],
        'limitations': [
            'Limited to 3 users',
            '1GB storage',
            'Community support only'
        ]
    },
    'basic': {
        'name': 'Basic Plan',
        'price': 29.99,
        'billing_cycle': 'monthly',
        'max_users': 10,
        'storage_limit': 5120,  # MB
        'features': [
            'Full CRM functionality',
            'Email & chat support',
            'Advanced reporting',
            'API access',
            'Custom fields',
            'Weekly backups'
        ],
        'limitations': [
            'Limited to 10 users',
            '5GB storage'
        ]
    },
    'professional': {
        'name': 'Professional Plan',
        'price': 79.99,
        'billing_cycle': 'monthly',
        'max_users': 50,
        'storage_limit': 20480,  # MB
        'features': [
            'All Basic features',
            'Priority support',
            'Custom integrations',
            'Advanced workflows',
            'Daily backups',
            'Custom branding',
            'Advanced analytics'
        ],
        'limitations': [
            'Limited to 50 users',
            '20GB storage'
        ]
    },
    'enterprise': {
        'name': 'Enterprise Plan',
        'price': 199.99,
        'billing_cycle': 'monthly',
        'max_users': -1,  # Unlimited
        'storage_limit': -1,  # Unlimited
        'features': [
            'All Professional features',
            'Unlimited users',
            'Unlimited storage',
            '24/7 phone support',
            'Dedicated account manager',
            'Custom development',
            'On-premise deployment option',
            'SLA guarantee'
        ],
        'limitations': []
    }
}

@billing_api_bp.route('/api/billing/plans', methods=['GET'])
@track_errors('api_get_billing_plans')
def get_billing_plans():
    """Get available subscription plans"""
    try:
        return jsonify({
            'success': True,
            'plans': SUBSCRIPTION_PLANS
        })
        
    except Exception as e:
        logger.error(f"Get billing plans failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to get billing plans'}), 500

@billing_api_bp.route('/api/billing/calculate', methods=['POST'])
@track_errors('api_calculate_billing')
def calculate_billing():
    """Calculate billing cost for plan and options"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        plan_id = data.get('plan_id')
        billing_cycle = data.get('billing_cycle', 'monthly')
        additional_users = data.get('additional_users', 0)
        additional_storage = data.get('additional_storage', 0)  # in GB
        
        if plan_id not in SUBSCRIPTION_PLANS:
            return jsonify({'success': False, 'error': 'Invalid plan ID'}), 400
        
        plan = SUBSCRIPTION_PLANS[plan_id]
        base_price = Decimal(str(plan['price']))
        
        # Calculate additional costs
        user_cost = Decimal('5.00') * additional_users  # $5 per additional user
        storage_cost = Decimal('2.00') * additional_storage  # $2 per GB
        
        subtotal = base_price + user_cost + storage_cost
        
        # Apply annual discount (20% off)
        if billing_cycle == 'annual':
            discount = subtotal * Decimal('0.20')
            subtotal = subtotal - discount
            total_annual = subtotal * 12
        else:
            discount = Decimal('0.00')
            total_annual = subtotal * 12
        
        # Calculate taxes (example: 10% VAT)
        tax_rate = Decimal('0.10')
        tax_amount = subtotal * tax_rate
        total = subtotal + tax_amount
        
        return jsonify({
            'success': True,
            'calculation': {
                'plan_id': plan_id,
                'plan_name': plan['name'],
                'base_price': float(base_price),
                'additional_users': additional_users,
                'user_cost': float(user_cost),
                'additional_storage': additional_storage,
                'storage_cost': float(storage_cost),
                'subtotal': float(subtotal),
                'discount': float(discount),
                'tax_rate': float(tax_rate),
                'tax_amount': float(tax_amount),
                'total': float(total),
                'billing_cycle': billing_cycle,
                'annual_total': float(total_annual),
                'currency': 'USD'
            }
        })
        
    except Exception as e:
        logger.error(f"Billing calculation failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Billing calculation failed'}), 500

# ================= TENANT BILLING =================

@billing_api_bp.route('/api/billing/tenant/<int:tenant_id>', methods=['GET'])
@login_required
@require_user()
@track_errors('api_get_tenant_billing')
def get_tenant_billing(tenant_id):
    """Get billing information for a tenant"""
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
        
        # Get current plan information
        current_plan = SUBSCRIPTION_PLANS.get(tenant.plan, SUBSCRIPTION_PLANS['free'])
        
        # Calculate usage
        current_users = TenantUser.query.filter_by(tenant_id=tenant_id).count()
        storage_used = 0  # TODO: Calculate actual storage usage
        
        # Calculate billing status
        next_billing_date = datetime.utcnow() + timedelta(days=30)  # TODO: Get actual billing date
        days_until_billing = (next_billing_date - datetime.utcnow()).days
        
        # Determine billing status
        billing_status = 'active'
        if days_until_billing <= 3:
            billing_status = 'due_soon'
        elif days_until_billing < 0:
            billing_status = 'overdue'
        
        billing_info = {
            'tenant_id': tenant.id,
            'tenant_name': tenant.name,
            'current_plan': {
                'id': tenant.plan,
                'name': current_plan['name'],
                'price': current_plan['price'],
                'billing_cycle': current_plan['billing_cycle']
            },
            'usage': {
                'current_users': current_users,
                'max_users': current_plan['max_users'],
                'storage_used': storage_used,
                'storage_limit': current_plan['storage_limit'],
                'usage_percentage': {
                    'users': (current_users / max(current_plan['max_users'], 1)) * 100 if current_plan['max_users'] > 0 else 0,
                    'storage': (storage_used / max(current_plan['storage_limit'], 1)) * 100 if current_plan['storage_limit'] > 0 else 0
                }
            },
            'billing': {
                'status': billing_status,
                'next_billing_date': next_billing_date.isoformat(),
                'days_until_billing': days_until_billing,
                'last_payment_date': None,  # TODO: Get actual payment date
                'payment_method': None  # TODO: Get payment method
            },
            'features': current_plan['features'],
            'limitations': current_plan['limitations']
        }
        
        return jsonify({
            'success': True,
            'billing_info': billing_info
        })
        
    except Exception as e:
        logger.error(f"Get tenant billing failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to get billing information'}), 500

@billing_api_bp.route('/api/billing/tenant/<int:tenant_id>/upgrade', methods=['POST'])
@login_required
@require_user()
@track_errors('api_upgrade_tenant_plan')
def upgrade_tenant_plan(tenant_id):
    """Upgrade tenant subscription plan"""
    try:
        # Verify user has owner access to this tenant
        tenant_user = TenantUser.query.filter_by(
            user_id=current_user.id,
            tenant_id=tenant_id
        ).first()
        
        if not tenant_user or tenant_user.access_level != 'owner':
            return jsonify({'success': False, 'error': 'Owner access required'}), 403
        
        tenant = tenant_user.tenant
        if not tenant:
            return jsonify({'success': False, 'error': 'Tenant not found'}), 404
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        new_plan_id = data.get('plan_id')
        if not new_plan_id or new_plan_id not in SUBSCRIPTION_PLANS:
            return jsonify({'success': False, 'error': 'Invalid plan ID'}), 400
        
        old_plan = tenant.plan
        new_plan = SUBSCRIPTION_PLANS[new_plan_id]
        
        # Prevent downgrade (for now)
        plan_hierarchy = ['free', 'basic', 'professional', 'enterprise']
        if plan_hierarchy.index(new_plan_id) < plan_hierarchy.index(old_plan):
            return jsonify({'success': False, 'error': 'Plan downgrade not supported'}), 400
        
        # Update tenant plan
        tenant.plan = new_plan_id
        tenant.max_users = new_plan['max_users'] if new_plan['max_users'] > 0 else 999999
        tenant.storage_limit = new_plan['storage_limit'] if new_plan['storage_limit'] > 0 else 999999999
        tenant.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Send notification if available
        if NotificationService:
            try:
                notification_service = NotificationService()
                notification_service.create_notification(
                    user_id=current_user.id,
                    title="Plan Upgraded Successfully",
                    message=f"Your tenant '{tenant.name}' has been upgraded to {new_plan['name']}.",
                    notification_type=NotificationType.SUCCESS,
                    priority=NotificationPriority.HIGH,
                    action_url=f"/tenant/{tenant.id}/manage",
                    action_label="View Tenant",
                    metadata={
                        'tenant_id': tenant.id,
                        'old_plan': old_plan,
                        'new_plan': new_plan_id,
                        'upgrade_date': datetime.utcnow().isoformat()
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to send notification: {e}")
        
        logger.info(f"Tenant {tenant.id} upgraded from {old_plan} to {new_plan_id} by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'Plan upgraded successfully',
            'tenant': {
                'id': tenant.id,
                'name': tenant.name,
                'old_plan': old_plan,
                'new_plan': new_plan_id,
                'max_users': tenant.max_users,
                'storage_limit': tenant.storage_limit
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Plan upgrade failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Plan upgrade failed'}), 500

# ================= BILLING NOTIFICATIONS =================

class BillingNotificationService:
    """Service for handling billing-related notifications"""
    
    def __init__(self):
        if NotificationService:
            self.notification_service = NotificationService()
        else:
            self.notification_service = None
    
    def _send_notification_safe(self, **kwargs):
        """Safely send notification if service is available"""
        if self.notification_service:
            try:
                return self.notification_service.create_notification(**kwargs)
            except Exception as e:
                logger.warning(f"Failed to send notification: {e}")
        return None
    
    def check_subscription_renewals(self):
        """Check for upcoming subscription renewals and send notifications"""
        try:
            # Get all active tenants
            tenants = Tenant.query.filter_by(is_active=True).all()
            
            for tenant in tenants:
                # TODO: Get actual billing cycle data from database
                # For now, using mock data
                next_billing = datetime.utcnow() + timedelta(days=7)  # Mock: 7 days from now
                days_until = (next_billing - datetime.utcnow()).days
                
                if days_until <= 7 and days_until > 0:
                    self._send_renewal_reminder(tenant, days_until)
                elif days_until <= 0:
                    self._send_overdue_notice(tenant)
            
        except Exception as e:
            logger.error(f"Subscription renewal check failed: {str(e)}")
    
    def _send_renewal_reminder(self, tenant, days_until):
        """Send renewal reminder notification"""
        # Get tenant owner
        owner = TenantUser.query.filter_by(
            tenant_id=tenant.id,
            access_level='owner'
        ).first()
        
        if not owner:
            return
        
        plan = SUBSCRIPTION_PLANS.get(tenant.plan, SUBSCRIPTION_PLANS['free'])
        
        if days_until == 7:
            title = "Subscription Renewal Reminder"
            message = f"Your {plan['name']} subscription for '{tenant.name}' will renew in 7 days."
            priority = NotificationPriority.MEDIUM
        elif days_until <= 3:
            title = "Subscription Renewing Soon"
            message = f"Your {plan['name']} subscription for '{tenant.name}' will renew in {days_until} day{'s' if days_until != 1 else ''}."
            priority = NotificationPriority.HIGH
        else:
            return
        
        self._send_notification_safe(
            user_id=owner.user_id,
            title=title,
            message=message,
            notification_type=NotificationType.BILLING_UPDATE if NotificationType else None,
            priority=priority,
            action_url=f"/billing/tenant/{tenant.id}",
            action_label="View Billing",
            metadata={
                'tenant_id': tenant.id,
                'days_until_renewal': days_until,
                'plan': tenant.plan
            }
        )
    
    def _send_overdue_notice(self, tenant):
        """Send overdue payment notification"""
        owner = TenantUser.query.filter_by(
            tenant_id=tenant.id,
            access_level='owner'
        ).first()
        
        if not owner:
            return
        
        plan = SUBSCRIPTION_PLANS.get(tenant.plan, SUBSCRIPTION_PLANS['free'])
        
        self._send_notification_safe(
            user_id=owner.user_id,
            title="Payment Overdue - Action Required",
            message=f"Payment for your {plan['name']} subscription is overdue. Please update your payment method to avoid service interruption.",
            notification_type=NotificationType.ERROR if NotificationType else None,
            priority=NotificationPriority.URGENT if NotificationPriority else None,
            action_url=f"/billing/tenant/{tenant.id}/payment",
            action_label="Update Payment",
            metadata={
                'tenant_id': tenant.id,
                'plan': tenant.plan,
                'status': 'overdue'
            }
        )
    
    def send_usage_alert(self, tenant_id, usage_type, usage_percentage):
        """Send usage threshold alert"""
        tenant = Tenant.query.get(tenant_id)
        if not tenant:
            return
        
        owner = TenantUser.query.filter_by(
            tenant_id=tenant_id,
            access_level='owner'
        ).first()
        
        if not owner:
            return
        
        if usage_percentage >= 90:
            title = f"{usage_type.title()} Limit Nearly Reached"
            message = f"Your tenant '{tenant.name}' is using {usage_percentage:.1f}% of its {usage_type} limit. Consider upgrading your plan."
            priority = NotificationPriority.HIGH
            notification_type = NotificationType.WARNING
        elif usage_percentage >= 80:
            title = f"High {usage_type.title()} Usage"
            message = f"Your tenant '{tenant.name}' is using {usage_percentage:.1f}% of its {usage_type} limit."
            priority = NotificationPriority.MEDIUM
            notification_type = NotificationType.INFO
        else:
            return
        
        self._send_notification_safe(
            user_id=owner.user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            priority=priority,
            action_url=f"/billing/tenant/{tenant.id}/upgrade",
            action_label="Upgrade Plan",
            metadata={
                'tenant_id': tenant.id,
                'usage_type': usage_type,
                'usage_percentage': usage_percentage
            }
        )

@billing_api_bp.route('/api/billing/notifications/check', methods=['POST'])
@login_required
@require_user()
@track_errors('api_check_billing_notifications')
def check_billing_notifications():
    """Manually trigger billing notification check (admin only)"""
    try:
        if not current_user.is_admin:
            return jsonify({'success': False, 'error': 'Admin access required'}), 403
        
        billing_service = BillingNotificationService()
        billing_service.check_subscription_renewals()
        
        return jsonify({
            'success': True,
            'message': 'Billing notifications checked and processed'
        })
        
    except Exception as e:
        logger.error(f"Billing notification check failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Billing notification check failed'}), 500

# ================= PAYMENT METHODS =================

@billing_api_bp.route('/api/billing/payment-methods', methods=['GET'])
@login_required
@require_user()
@track_errors('api_get_payment_methods')
def get_payment_methods():
    """Get user's payment methods"""
    try:
        # TODO: Implement actual payment method storage and retrieval
        # For now, return mock data
        
        payment_methods = [
            {
                'id': 'pm_mock123',
                'type': 'card',
                'card': {
                    'brand': 'visa',
                    'last4': '4242',
                    'exp_month': 12,
                    'exp_year': 2025
                },
                'is_default': True,
                'created_at': '2024-01-15T10:30:00Z'
            }
        ]
        
        return jsonify({
            'success': True,
            'payment_methods': payment_methods
        })
        
    except Exception as e:
        logger.error(f"Get payment methods failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to get payment methods'}), 500

@billing_api_bp.route('/api/billing/invoices', methods=['GET'])
@login_required
@require_user()
@track_errors('api_get_invoices')
def get_invoices():
    """Get user's billing invoices"""
    try:
        # TODO: Implement actual invoice storage and retrieval
        # For now, return mock data
        
        invoices = [
            {
                'id': 'inv_mock123',
                'number': 'INV-2024-001',
                'status': 'paid',
                'amount': 29.99,
                'currency': 'USD',
                'created_at': '2024-01-15T10:30:00Z',
                'due_date': '2024-01-30T23:59:59Z',
                'paid_at': '2024-01-16T08:22:00Z',
                'description': 'Basic Plan - Monthly Subscription',
                'tenant_id': None  # Will be filled for specific tenant invoices
            }
        ]
        
        return jsonify({
            'success': True,
            'invoices': invoices,
            'total': len(invoices)
        })
        
    except Exception as e:
        logger.error(f"Get invoices failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to get invoices'}), 500

# Export blueprint
__all__ = ['billing_api_bp', 'BillingNotificationService']