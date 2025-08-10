# Billing Service for Usage-Based Billing System
from datetime import datetime, timedelta
import logging
from db import db
from models import (
    Tenant, BillingCycle, UsageTracking, PaymentHistory, 
    BillingNotification, SupportTicket, SaasUser, PaymentTransaction
)
from OdooDatabaseManager import OdooDatabaseManager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BillingService:
    """Service to handle usage-based billing operations"""
    
    def __init__(self):
        self.db_manager = None  # Initialize lazily when needed
    
    def get_db_manager(self):
        """Get database manager, initialize if needed"""
        if self.db_manager is None:
            try:
                # Initialize with default values or from config
                from flask import current_app
                odoo_url = current_app.config.get('ODOO_MASTER_URL', 'http://odoo_master:8069')
                master_pwd = current_app.config.get('ODOO_MASTER_PASSWORD', 'admin')
                self.db_manager = OdooDatabaseManager(odoo_url, master_pwd)
            except Exception as e:
                logger.warning(f"Could not initialize OdooDatabaseManager: {e}")
                self.db_manager = None
        return self.db_manager
    
    def create_billing_cycle(self, tenant_id):
        """Create a new billing cycle for a tenant"""
        try:
            tenant = Tenant.query.get(tenant_id)
            if not tenant:
                raise ValueError(f"Tenant {tenant_id} not found")
            
            # Check if there's already an active cycle
            existing_cycle = BillingCycle.query.filter_by(
                tenant_id=tenant_id, 
                status='active'
            ).first()
            
            if existing_cycle:
                logger.warning(f"Active billing cycle already exists for tenant {tenant_id}")
                return existing_cycle
            
            # Create new cycle
            cycle = BillingCycle(
                tenant_id=tenant_id,
                cycle_start=datetime.utcnow(),
                cycle_end=datetime.utcnow() + timedelta(days=30),
                total_hours_allowed=360,
                hours_used=0.0,
                status='active'
            )
            
            db.session.add(cycle)
            db.session.commit()
            
            logger.info(f"Created new billing cycle for tenant {tenant_id}")
            return cycle
            
        except Exception as e:
            logger.error(f"Error creating billing cycle: {str(e)}")
            db.session.rollback()
            raise
    
    def track_hourly_usage(self):
        """Main method to track usage for all active tenants"""
        try:
            logger.info("Starting hourly usage tracking...")
            
            # Get all active tenants
            active_tenants = Tenant.query.filter_by(status='active').all()
            
            for tenant in active_tenants:
                self._track_tenant_usage(tenant)
                
            # Check for notifications and deactivations
            self._process_billing_alerts()
            
            logger.info(f"Completed hourly usage tracking for {len(active_tenants)} tenants")
            
        except Exception as e:
            logger.error(f"Error in hourly usage tracking: {str(e)}")
            raise
    
    def _track_tenant_usage(self, tenant):
        """Track usage for a single tenant"""
        try:
            # Get or create active billing cycle
            cycle = self._get_or_create_active_cycle(tenant.id)
            
            if not cycle:
                return
            
            # Check if database is active
            is_db_active = self._check_database_status(tenant)
            
            # Calculate uptime hours (assuming 1 hour = 1.0 if active, 0.0 if not)
            uptime_hours = 1.0 if is_db_active else 0.0
            downtime_reason = None if is_db_active else self._get_downtime_reason(tenant)
            
            # Record usage
            usage_log = UsageTracking(
                tenant_id=tenant.id,
                billing_cycle_id=cycle.id,
                database_active=is_db_active,
                uptime_hours=uptime_hours,
                downtime_reason=downtime_reason
            )
            
            db.session.add(usage_log)
            
            # Update billing cycle hours
            if is_db_active:
                cycle.hours_used += uptime_hours
                
                # Check if limit reached
                if cycle.hours_used >= cycle.total_hours_allowed:
                    self._auto_deactivate_tenant(tenant, cycle)
            
            db.session.commit()
            
            logger.debug(f"Tracked usage for tenant {tenant.name}: {uptime_hours} hours, total: {cycle.hours_used}/{cycle.total_hours_allowed}")
            
        except Exception as e:
            logger.error(f"Error tracking usage for tenant {tenant.id}: {str(e)}")
            db.session.rollback()
    
    def _get_or_create_active_cycle(self, tenant_id):
        """Get the active billing cycle for a tenant or create one"""
        cycle = BillingCycle.query.filter_by(
            tenant_id=tenant_id,
            status='active'
        ).first()
        
        if not cycle:
            cycle = self.create_billing_cycle(tenant_id)
        
        return cycle
    
    def _check_database_status(self, tenant):
        """Check if tenant's database is active and accessible"""
        try:
            # Check if tenant is marked as active
            if not tenant.is_active or tenant.status != 'active':
                return False
            
            # Try to ping the database
            db_manager = self.get_db_manager()
            if db_manager:
                return db_manager.check_database_exists(tenant.database_name)
            else:
                # If db_manager not available, fall back to checking status
                return tenant.is_active and tenant.status == 'active'
            
        except Exception as e:
            logger.warning(f"Could not check database status for {tenant.name}: {str(e)}")
            return False
    
    def _get_downtime_reason(self, tenant):
        """Determine reason for downtime"""
        if not tenant.is_active:
            return 'user_deactivated'
        elif tenant.status != 'active':
            return 'maintenance'
        else:
            return 'unknown'
    
    def _auto_deactivate_tenant(self, tenant, cycle):
        """Auto-deactivate tenant when billing limit is reached"""
        try:
            if cycle.auto_deactivated:
                return  # Already deactivated
            
            # Mark tenant as inactive
            tenant.is_active = False
            tenant.status = 'billing_expired'
            
            # Mark cycle as expired
            cycle.status = 'expired'
            cycle.auto_deactivated = True
            
            # Create notification
            self._create_expiry_notification(tenant, cycle)
            
            logger.info(f"Auto-deactivated tenant {tenant.name} - billing limit reached")
            
        except Exception as e:
            logger.error(f"Error auto-deactivating tenant {tenant.id}: {str(e)}")
            raise
    
    def _process_billing_alerts(self):
        """Process billing alerts and notifications"""
        try:
            # Get cycles that need reminders
            cycles_for_reminder = BillingCycle.query.filter(
                BillingCycle.status == 'active',
                BillingCycle.reminder_sent == False,
                BillingCycle.hours_used >= (BillingCycle.total_hours_allowed - 84)  # 7 days warning
            ).all()
            
            for cycle in cycles_for_reminder:
                self._send_billing_reminder(cycle)
                
        except Exception as e:
            logger.error(f"Error processing billing alerts: {str(e)}")
    
    def _send_billing_reminder(self, cycle):
        """Send 7-day billing reminder"""
        try:
            tenant = cycle.tenant
            days_remaining = max(0, int(cycle.hours_remaining / 12))  # Convert hours to days
            
            # Create support ticket
            user = SaasUser.query.join(tenant.users).filter(
                tenant.users.any(role='admin')
            ).first()
            
            if not user:
                logger.warning(f"No admin user found for tenant {tenant.id}")
                return
            
            ticket = SupportTicket(
                user_id=user.id,
                subject=f"Billing Reminder: {tenant.name} - {days_remaining} days remaining",
                message=f"Your current billing cycle will end in {days_remaining} days. Please renew to continue uninterrupted access.",
                priority='medium',
                status='open'
            )
            
            db.session.add(ticket)
            db.session.flush()  # Get ticket ID
            
            # Create billing notification
            notification = BillingNotification(
                tenant_id=tenant.id,
                billing_cycle_id=cycle.id,
                support_ticket_id=ticket.id,
                notification_type='reminder',
                message=ticket.message
            )
            
            db.session.add(notification)
            
            # Mark reminder as sent
            cycle.reminder_sent = True
            
            db.session.commit()
            
            logger.info(f"Sent billing reminder for tenant {tenant.name}")
            
        except Exception as e:
            logger.error(f"Error sending billing reminder: {str(e)}")
            db.session.rollback()
    
    def _create_expiry_notification(self, tenant, cycle):
        """Create expiry notification when tenant is auto-deactivated"""
        try:
            user = SaasUser.query.join(tenant.users).filter(
                tenant.users.any(role='admin')
            ).first()
            
            if not user:
                return
            
            ticket = SupportTicket(
                user_id=user.id,
                subject=f"Panel Deactivated: {tenant.name} - Payment Required",
                message="Your panel has been deactivated due to billing limit reached. Please make a payment to reactivate your service.",
                priority='high',
                status='open'
            )
            
            db.session.add(ticket)
            db.session.flush()
            
            notification = BillingNotification(
                tenant_id=tenant.id,
                billing_cycle_id=cycle.id,
                support_ticket_id=ticket.id,
                notification_type='expiry',
                message=ticket.message
            )
            
            db.session.add(notification)
            
        except Exception as e:
            logger.error(f"Error creating expiry notification: {str(e)}")
    
    def process_payment(self, tenant_id, payment_data):
        """Process successful payment and reactivate tenant"""
        try:
            tenant = Tenant.query.get(tenant_id)
            if not tenant:
                raise ValueError(f"Tenant {tenant_id} not found")
            
            # Get expired cycle
            expired_cycle = BillingCycle.query.filter_by(
                tenant_id=tenant_id,
                status='expired'
            ).order_by(BillingCycle.created_at.desc()).first()
            
            # Create payment record
            payment = PaymentHistory(
                tenant_id=tenant_id,
                billing_cycle_id=expired_cycle.id if expired_cycle else None,
                payment_id=payment_data.get('payment_id'),
                amount=payment_data.get('amount'),
                currency=payment_data.get('currency', 'USD'),
                payment_method=payment_data.get('method'),
                status='completed',
                gateway_transaction_id=payment_data.get('transaction_id'),
                gateway_response=payment_data.get('response'),
                paid_at=datetime.utcnow()
            )
            
            db.session.add(payment)
            
            # Reactivate tenant
            tenant.is_active = True
            tenant.status = 'active'
            
            # Create new billing cycle
            new_cycle = self.create_billing_cycle(tenant_id)
            
            # Update payment to link with new cycle
            payment.billing_cycle_id = new_cycle.id
            
            # Add paid update to related tickets
            if expired_cycle:
                self._update_billing_tickets(tenant_id, expired_cycle.id)
            
            db.session.commit()
            
            logger.info(f"Processed payment and reactivated tenant {tenant.name}")
            return payment
            
        except Exception as e:
            logger.error(f"Error processing payment: {str(e)}")
            db.session.rollback()
            raise
    
    def _update_billing_tickets(self, tenant_id, cycle_id):
        """Update billing-related tickets with payment confirmation"""
        try:
            notifications = BillingNotification.query.filter_by(
                tenant_id=tenant_id,
                billing_cycle_id=cycle_id
            ).all()
            
            for notification in notifications:
                if notification.support_ticket:
                    ticket = notification.support_ticket
                    ticket.status = 'closed'
                    ticket.admin_notes = f"Resolved: Payment received on {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
            
        except Exception as e:
            logger.error(f"Error updating billing tickets: {str(e)}")
    
    def get_tenant_billing_info(self, tenant_id):
        """Get comprehensive billing information for a tenant"""
        try:
            tenant = Tenant.query.get(tenant_id)
            if not tenant:
                return None
            
            active_cycle = BillingCycle.query.filter_by(
                tenant_id=tenant_id,
                status='active'
            ).first()
            
            if not active_cycle:
                return {
                    'tenant_name': tenant.name,
                    'status': 'no_active_cycle',
                    'requires_payment': True
                }
            
            return {
                'tenant_name': tenant.name,
                'cycle_start': active_cycle.cycle_start,
                'cycle_end': active_cycle.cycle_end,
                'hours_used': active_cycle.hours_used,
                'hours_remaining': active_cycle.hours_remaining,
                'days_remaining': active_cycle.days_remaining,
                'total_hours_allowed': active_cycle.total_hours_allowed,
                'status': active_cycle.status,
                'is_expired': active_cycle.is_expired,
                'reminder_sent': active_cycle.reminder_sent,
                'auto_deactivated': active_cycle.auto_deactivated,
                'requires_payment': active_cycle.is_expired
            }
            
        except Exception as e:
            logger.error(f"Error getting billing info: {str(e)}")
            return None
    
    def get_admin_billing_logs(self, tenant_id=None):
        """Get billing logs for admin panel"""
        try:
            # Create a comprehensive billing logs view
            logs = []
            
            # Get basic tenant and billing cycle information
            base_query = db.session.query(Tenant).outerjoin(BillingCycle, Tenant.id == BillingCycle.tenant_id)
            
            if tenant_id:
                base_query = base_query.filter(Tenant.id == tenant_id)
            
            tenants_data = base_query.all()
            
            for tenant in tenants_data:
                # Get payment transactions for this tenant
                payment_transactions = PaymentTransaction.query.filter_by(tenant_id=tenant.id).order_by(PaymentTransaction.created_at.desc()).all()
                
                # Get payment history for this tenant
                payment_history = PaymentHistory.query.filter_by(tenant_id=tenant.id).order_by(PaymentHistory.created_at.desc()).all()
                
                # Get billing cycles for this tenant
                billing_cycles = BillingCycle.query.filter_by(tenant_id=tenant.id).order_by(BillingCycle.cycle_start.desc()).all()
                
                # Get notifications for this tenant
                notifications = BillingNotification.query.filter_by(tenant_id=tenant.id).order_by(BillingNotification.sent_at.desc()).all()
                
                # Create log entries for payment transactions
                for pt in payment_transactions:
                    logs.append({
                        'tenant_name': tenant.name,
                        'tenant_id': tenant.id,
                        'type': 'payment_transaction',
                        'message': f'Payment transaction {pt.transaction_id} - {pt.status}',
                        'amount': pt.amount,
                        'currency': pt.currency,
                        'status': pt.status,
                        'timestamp': pt.created_at,
                        'level': 'INFO' if pt.status == 'VALIDATED' else 'WARNING' if pt.status == 'PENDING' else 'ERROR'
                    })
                
                # Create log entries for payment history
                for ph in payment_history:
                    logs.append({
                        'tenant_name': tenant.name,
                        'tenant_id': tenant.id,
                        'type': 'payment_history',
                        'message': f'Payment history entry - {ph.status}',
                        'amount': ph.amount,
                        'currency': ph.currency,
                        'status': ph.status,
                        'timestamp': ph.created_at,
                        'level': 'INFO' if ph.status == 'completed' else 'WARNING' if ph.status == 'pending' else 'ERROR'
                    })
                
                # Create log entries for billing cycles
                for bc in billing_cycles:
                    logs.append({
                        'tenant_name': tenant.name,
                        'tenant_id': tenant.id,
                        'type': 'billing_cycle',
                        'message': f'Billing cycle {bc.status} - {bc.hours_used:.1f}h/{bc.total_hours_allowed}h used',
                        'amount': None,
                        'currency': None,
                        'status': bc.status,
                        'timestamp': bc.cycle_start,
                        'level': 'INFO' if bc.status == 'active' else 'WARNING' if bc.status == 'expired' else 'INFO'
                    })
                
                # Create log entries for notifications
                for notif in notifications:
                    logs.append({
                        'tenant_name': tenant.name,
                        'tenant_id': tenant.id,
                        'type': 'notification',
                        'message': f'{notif.notification_type}: {notif.message}',
                        'amount': None,
                        'currency': None,
                        'status': notif.notification_type,
                        'timestamp': notif.sent_at,
                        'level': 'WARNING' if notif.notification_type == 'reminder' else 'ERROR' if notif.notification_type == 'expiry' else 'INFO'
                    })
            
            # Sort all logs by timestamp, most recent first
            logs.sort(key=lambda x: x['timestamp'] or datetime.min, reverse=True)
            
            return logs
            
        except Exception as e:
            logger.error(f"Error getting admin billing logs: {str(e)}")
            return []
