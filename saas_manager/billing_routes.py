# Billing Routes for Usage-Based Billing System
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import uuid
from datetime import datetime
from billing_service import BillingService
from models import Tenant, BillingCycle, PaymentHistory, BillingNotification, SaasUser, TenantUser
from db import db
import logging

billing_bp = Blueprint('billing', __name__, url_prefix='/billing')
logger = logging.getLogger(__name__)

# Initialize billing service lazily to avoid import-time issues
billing_service = None

def get_billing_service():
    """Get billing service instance, create if needed"""
    global billing_service
    if billing_service is None:
        billing_service = BillingService()
    return billing_service

@billing_bp.route('/panel/<int:tenant_id>/info')
@login_required
def panel_billing_info(tenant_id):
    """Get billing information for a specific panel"""
    try:
        # Check if user has access to this tenant
        if not current_user.is_admin:
            tenant_user = TenantUser.query.filter_by(
                user_id=current_user.id,
                tenant_id=tenant_id
            ).first()
            if not tenant_user:
                return jsonify({'error': 'Access denied'}), 403
        
        billing_info = get_billing_service().get_tenant_billing_info(tenant_id)
        
        if not billing_info:
            return jsonify({'error': 'Billing information not found'}), 404
        
        return jsonify(billing_info)
        
    except Exception as e:
        logger.error(f"Error getting billing info: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@billing_bp.route('/panel/<int:tenant_id>/payment')
@login_required
def initiate_payment(tenant_id):
    """Initiate payment for panel renewal"""
    try:
        # Check access
        if not current_user.is_admin:
            tenant_user = TenantUser.query.filter_by(
                user_id=current_user.id,
                tenant_id=tenant_id
            ).first()
            if not tenant_user:
                flash('Access denied', 'error')
                return redirect(url_for('main.dashboard'))
        
        tenant = Tenant.query.get(tenant_id)
        if not tenant:
            flash('Panel not found', 'error')
            return redirect(url_for('main.dashboard'))
        
        billing_info = get_billing_service().get_tenant_billing_info(tenant_id)
        
        # Get payment amount from plan or default
        amount = 50.00  # Default amount, you can make this configurable
        
        return render_template('billing/payment.html', 
                             tenant=tenant, 
                             billing_info=billing_info,
                             amount=amount)
        
    except Exception as e:
        logger.error(f"Error initiating payment: {str(e)}")
        flash('Error initiating payment', 'error')
        return redirect(url_for('main.dashboard'))

@billing_bp.route('/panel/<int:tenant_id>/payment/process', methods=['POST'])
@login_required
def process_payment(tenant_id):
    """Process payment submission"""
    try:
        # Check access
        if not current_user.is_admin:
            tenant_user = TenantUser.query.filter_by(
                user_id=current_user.id,
                tenant_id=tenant_id
            ).first()
            if not tenant_user:
                return jsonify({'error': 'Access denied'}), 403
        
        # Get form data
        amount = float(request.form.get('amount', 50.00))
        payment_method = request.form.get('payment_method', 'stripe')
        
        # Generate unique payment ID
        payment_id = f"pay_{uuid.uuid4().hex[:16]}"
        
        # For demo purposes, we'll simulate successful payment
        # In production, integrate with actual payment gateway
        
        payment_data = {
            'payment_id': payment_id,
            'amount': amount,
            'currency': 'USD',
            'method': payment_method,
            'transaction_id': f"txn_{uuid.uuid4().hex[:12]}",
            'response': {
                'status': 'success',
                'gateway': payment_method,
                'processed_at': datetime.utcnow().isoformat()
            }
        }
        
        # Process the payment
        payment = get_billing_service().process_payment(tenant_id, payment_data)
        
        flash('Payment processed successfully! Your panel has been reactivated.', 'success')
        return redirect(url_for('main.dashboard'))
        
    except Exception as e:
        logger.error(f"Error processing payment: {str(e)}")
        flash('Payment processing failed. Please try again.', 'error')
        return redirect(url_for('billing.initiate_payment', tenant_id=tenant_id))

@billing_bp.route('/panel/<int:tenant_id>/payment/callback', methods=['POST'])
def payment_callback(tenant_id):
    """Handle payment gateway callback"""
    try:
        # This would handle real payment gateway callbacks
        # For now, just log the callback
        callback_data = request.get_json() or request.form.to_dict()
        
        logger.info(f"Payment callback for tenant {tenant_id}: {callback_data}")
        
        # Verify callback authenticity (implement based on your gateway)
        # Process the payment result
        
        if callback_data.get('status') == 'success':
            payment_data = {
                'payment_id': callback_data.get('payment_id'),
                'amount': float(callback_data.get('amount', 0)),
                'currency': callback_data.get('currency', 'USD'),
                'method': callback_data.get('method'),
                'transaction_id': callback_data.get('transaction_id'),
                'response': callback_data
            }
            
            get_billing_service().process_payment(tenant_id, payment_data)
            
        return jsonify({'status': 'received'})
        
    except Exception as e:
        logger.error(f"Error in payment callback: {str(e)}")
        return jsonify({'error': 'Callback processing failed'}), 500

@billing_bp.route('/notifications/<int:tenant_id>')
@login_required
def get_notifications(tenant_id):
    """Get billing notifications for a tenant"""
    try:
        # Check access
        if not current_user.is_admin:
            tenant_user = TenantUser.query.filter_by(
                user_id=current_user.id,
                tenant_id=tenant_id
            ).first()
            if not tenant_user:
                return jsonify({'error': 'Access denied'}), 403
        
        notifications = BillingNotification.query.filter_by(
            tenant_id=tenant_id,
            is_read=False
        ).order_by(BillingNotification.sent_at.desc()).all()
        
        notification_data = []
        for notif in notifications:
            notification_data.append({
                'id': notif.id,
                'type': notif.notification_type,
                'message': notif.message,
                'sent_at': notif.sent_at.isoformat() if notif.sent_at else None,
                'support_ticket_id': notif.support_ticket_id
            })
        
        return jsonify({'notifications': notification_data})
        
    except Exception as e:
        logger.error(f"Error getting notifications: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@billing_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """Mark a notification as read"""
    try:
        notification = BillingNotification.query.get(notification_id)
        if not notification:
            return jsonify({'error': 'Notification not found'}), 404
        
        # Check access
        if not current_user.is_admin:
            tenant_user = TenantUser.query.filter_by(
                user_id=current_user.id,
                tenant_id=notification.tenant_id
            ).first()
            if not tenant_user:
                return jsonify({'error': 'Access denied'}), 403
        
        notification.is_read = True
        notification.viewed_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({'status': 'success'})
        
    except Exception as e:
        logger.error(f"Error marking notification as read: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@billing_bp.route('/admin/logs')
@login_required
def admin_billing_logs():
    """Admin panel for viewing billing logs"""
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('main.dashboard'))
    
    try:
        # Get filter parameters
        tenant_id = request.args.get('tenant_id')
        
        # Get billing logs
        logs = get_billing_service().get_admin_billing_logs(tenant_id)
        
        # Get all tenants for filter dropdown
        tenants = Tenant.query.order_by(Tenant.name).all()
        
        return render_template('billing/admin_logs.html', 
                             logs=logs, 
                             tenants=tenants,
                             selected_tenant_id=int(tenant_id) if tenant_id else None)
        
    except Exception as e:
        logger.error(f"Error loading admin billing logs: {str(e)}")
        flash('Error loading billing logs', 'error')
        return redirect(url_for('main.admin_dashboard'))

@billing_bp.route('/admin/tenant/<int:tenant_id>/billing')
@login_required
def admin_tenant_billing(tenant_id):
    """Detailed billing view for a specific tenant"""
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        tenant = Tenant.query.get(tenant_id)
        if not tenant:
            return jsonify({'error': 'Tenant not found'}), 404
        
        # Get billing cycles
        cycles = BillingCycle.query.filter_by(tenant_id=tenant_id).order_by(
            BillingCycle.cycle_start.desc()
        ).all()
        
        # Get payment history
        payments = PaymentHistory.query.filter_by(tenant_id=tenant_id).order_by(
            PaymentHistory.created_at.desc()
        ).all()
        
        # Get usage logs for current cycle
        current_cycle = BillingCycle.query.filter_by(
            tenant_id=tenant_id,
            status='active'
        ).first()
        
        usage_logs = []
        if current_cycle:
            usage_logs = current_cycle.usage_logs[-168:]  # Last 7 days (168 hours)
        
        # Get notifications
        notifications = BillingNotification.query.filter_by(
            tenant_id=tenant_id
        ).order_by(BillingNotification.sent_at.desc()).limit(10).all()
        
        billing_data = {
            'tenant': {
                'id': tenant.id,
                'name': tenant.name,
                'status': tenant.status,
                'created_at': tenant.created_at.isoformat() if tenant.created_at else None
            },
            'cycles': [{
                'id': cycle.id,
                'start': cycle.cycle_start.isoformat() if cycle.cycle_start else None,
                'end': cycle.cycle_end.isoformat() if cycle.cycle_end else None,
                'hours_used': cycle.hours_used,
                'hours_remaining': cycle.hours_remaining,
                'status': cycle.status,
                'reminder_sent': cycle.reminder_sent,
                'auto_deactivated': cycle.auto_deactivated
            } for cycle in cycles],
            'payments': [{
                'id': payment.id,
                'amount': payment.amount,
                'currency': payment.currency,
                'status': payment.status,
                'paid_at': payment.paid_at.isoformat() if payment.paid_at else None,
                'payment_method': payment.payment_method
            } for payment in payments],
            'usage_logs': [{
                'recorded_at': log.recorded_at.isoformat() if log.recorded_at else None,
                'database_active': log.database_active,
                'uptime_hours': log.uptime_hours,
                'downtime_reason': log.downtime_reason
            } for log in usage_logs],
            'notifications': [{
                'id': notif.id,
                'type': notif.notification_type,
                'message': notif.message,
                'sent_at': notif.sent_at.isoformat() if notif.sent_at else None,
                'is_read': notif.is_read
            } for notif in notifications]
        }
        
        return jsonify(billing_data)
        
    except Exception as e:
        logger.error(f"Error getting tenant billing details: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@billing_bp.route('/cron/hourly-tracking', methods=['POST'])
def cron_hourly_tracking():
    """Endpoint for cron job to trigger hourly usage tracking"""
    try:
        # Add basic authentication for cron job if needed
        auth_token = request.headers.get('X-Cron-Token')
        expected_token = 'your-secure-cron-token'  # Set this in environment variables
        
        if auth_token != expected_token:
            return jsonify({'error': 'Unauthorized'}), 401
        
        get_billing_service().track_hourly_usage()
        
        return jsonify({
            'status': 'success',
            'message': 'Hourly usage tracking completed',
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error in cron hourly tracking: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500
