"""
Enhanced Notification System
Provides comprehensive notification management including subscription renewals,
support ticket updates, billing alerts, system maintenance, and more.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from enum import Enum

from db import db
from models import SaasUser, Tenant, TenantUser
try:
    from user_notifications import (
        NotificationService, NotificationType, NotificationPriority, UserNotification
    )
except ImportError:
    # Fallback if notifications not available
    NotificationService = None
    NotificationType = None
    NotificationPriority = None
    UserNotification = None

try:
    from support_api import SupportTicket, TicketStatus
except ImportError:
    # Fallback if support API not available
    SupportTicket = None
    TicketStatus = None

logger = logging.getLogger(__name__)

class EnhancedNotificationService:
    """Enhanced notification service with smart automation"""
    
    def __init__(self, ws_manager=None, redis_client=None):
        if NotificationService:
            self.notification_service = NotificationService(ws_manager, redis_client)
        else:
            self.notification_service = None
    
    def create_notification(self, **kwargs):
        """Safely create notification if service is available"""
        if self.notification_service:
            try:
                return self.notification_service.create_notification(**kwargs)
            except Exception as e:
                logger.warning(f"Failed to send notification: {e}")
        return None
    
    # ================= SUBSCRIPTION NOTIFICATIONS =================
    
    def check_subscription_renewals(self):
        """Check for upcoming subscription renewals and send notifications"""
        try:
            # Get all active tenants
            tenants = Tenant.query.filter_by(is_active=True).all()
            
            for tenant in tenants:
                self._check_tenant_renewal(tenant)
                self._check_usage_limits(tenant)
                
        except Exception as e:
            logger.error(f"Subscription renewal check failed: {str(e)}")
    
    def _check_tenant_renewal(self, tenant):
        """Check individual tenant renewal status"""
        try:
            # Mock billing date - in production, get from actual billing system
            next_billing = datetime.utcnow() + timedelta(days=7)  # 7 days from now
            days_until = (next_billing - datetime.utcnow()).days
            
            # Get tenant owner
            owner = TenantUser.query.filter_by(
                tenant_id=tenant.id,
                access_level='owner'
            ).first()
            
            if not owner:
                return
            
            if days_until == 7:
                self._send_7_day_renewal_reminder(tenant, owner)
            elif days_until == 3:
                self._send_3_day_renewal_reminder(tenant, owner)
            elif days_until == 1:
                self._send_1_day_renewal_reminder(tenant, owner)
            elif days_until <= 0:
                self._send_overdue_notice(tenant, owner)
                
        except Exception as e:
            logger.error(f"Tenant renewal check failed for {tenant.id}: {str(e)}")
    
    def _send_7_day_renewal_reminder(self, tenant, owner):
        """Send 7-day renewal reminder"""
        self.create_notification(
            user_id=owner.user_id,
            title="Subscription Renewal Reminder",
            message=f"Your {tenant.plan.title()} subscription for '{tenant.name}' will renew in 7 days.",
            notification_type=NotificationType.BILLING_UPDATE if NotificationType else None,
            priority=NotificationPriority.MEDIUM if NotificationPriority else None,
            action_url=f"/billing/tenant/{tenant.id}",
            action_label="View Billing",
            metadata={
                'tenant_id': tenant.id,
                'days_until_renewal': 7,
                'plan': tenant.plan,
                'type': 'renewal_reminder'
            }
        )
    
    def _send_3_day_renewal_reminder(self, tenant, owner):
        """Send 3-day renewal reminder"""
        self.create_notification(
            user_id=owner.user_id,
            title="Subscription Renewing Soon",
            message=f"Your {tenant.plan.title()} subscription for '{tenant.name}' will renew in 3 days. Please ensure your payment method is up to date.",
            notification_type=NotificationType.BILLING_UPDATE if NotificationType else None,
            priority=NotificationPriority.HIGH if NotificationPriority else None,
            action_url=f"/billing/tenant/{tenant.id}/payment",
            action_label="Update Payment",
            metadata={
                'tenant_id': tenant.id,
                'days_until_renewal': 3,
                'plan': tenant.plan,
                'type': 'renewal_urgent'
            }
        )
    
    def _send_1_day_renewal_reminder(self, tenant, owner):
        """Send final renewal reminder"""
        self.create_notification(
            user_id=owner.user_id,
            title="Subscription Renews Tomorrow",
            message=f"Your {tenant.plan.title()} subscription for '{tenant.name}' will renew tomorrow. Your account will be charged automatically.",
            notification_type=NotificationType.BILLING_UPDATE if NotificationType else None,
            priority=NotificationPriority.HIGH if NotificationPriority else None,
            action_url=f"/billing/tenant/{tenant.id}",
            action_label="View Billing Details",
            metadata={
                'tenant_id': tenant.id,
                'days_until_renewal': 1,
                'plan': tenant.plan,
                'type': 'renewal_final'
            }
        )
    
    def _send_overdue_notice(self, tenant, owner):
        """Send overdue payment notification"""
        self.create_notification(
            user_id=owner.user_id,
            title="Payment Overdue - Action Required",
            message=f"Payment for your {tenant.plan.title()} subscription is overdue. Please update your payment method to avoid service interruption.",
            notification_type=NotificationType.ERROR if NotificationType else None,
            priority=NotificationPriority.URGENT if NotificationPriority else None,
            action_url=f"/billing/tenant/{tenant.id}/payment",
            action_label="Update Payment Now",
            metadata={
                'tenant_id': tenant.id,
                'plan': tenant.plan,
                'status': 'overdue',
                'type': 'payment_overdue'
            }
        )
    
    # ================= USAGE LIMIT NOTIFICATIONS =================
    
    def _check_usage_limits(self, tenant):
        """Check tenant usage limits and send alerts"""
        try:
            # Get usage statistics
            current_users = TenantUser.query.filter_by(tenant_id=tenant.id).count()
            storage_used = 0  # TODO: Calculate actual storage usage
            
            # Check user limits
            if tenant.max_users > 0:
                user_percentage = (current_users / tenant.max_users) * 100
                if user_percentage >= 90:
                    self._send_usage_alert(tenant, 'users', user_percentage, current_users, tenant.max_users)
                elif user_percentage >= 80:
                    self._send_usage_warning(tenant, 'users', user_percentage, current_users, tenant.max_users)
            
            # Check storage limits
            if tenant.storage_limit > 0:
                storage_percentage = (storage_used / tenant.storage_limit) * 100
                if storage_percentage >= 90:
                    self._send_usage_alert(tenant, 'storage', storage_percentage, storage_used, tenant.storage_limit)
                elif storage_percentage >= 80:
                    self._send_usage_warning(tenant, 'storage', storage_percentage, storage_used, tenant.storage_limit)
                    
        except Exception as e:
            logger.error(f"Usage limit check failed for tenant {tenant.id}: {str(e)}")
    
    def _send_usage_alert(self, tenant, usage_type, percentage, current, limit):
        """Send critical usage alert"""
        owner = TenantUser.query.filter_by(tenant_id=tenant.id, access_level='owner').first()
        if not owner:
            return
        
        unit = 'users' if usage_type == 'users' else 'MB'
        
        self.create_notification(
            user_id=owner.user_id,
            title=f"{usage_type.title()} Limit Nearly Reached",
            message=f"Your tenant '{tenant.name}' is using {percentage:.1f}% of its {usage_type} limit ({current:,} of {limit:,} {unit}). Consider upgrading your plan to avoid service disruption.",
            notification_type=NotificationType.WARNING if NotificationType else None,
            priority=NotificationPriority.HIGH if NotificationPriority else None,
            action_url=f"/billing/tenant/{tenant.id}/upgrade",
            action_label="Upgrade Plan",
            metadata={
                'tenant_id': tenant.id,
                'usage_type': usage_type,
                'percentage': percentage,
                'current': current,
                'limit': limit,
                'type': 'usage_critical'
            }
        )
    
    def _send_usage_warning(self, tenant, usage_type, percentage, current, limit):
        """Send usage warning"""
        owner = TenantUser.query.filter_by(tenant_id=tenant.id, access_level='owner').first()
        if not owner:
            return
        
        unit = 'users' if usage_type == 'users' else 'MB'
        
        self.create_notification(
            user_id=owner.user_id,
            title=f"High {usage_type.title()} Usage",
            message=f"Your tenant '{tenant.name}' is using {percentage:.1f}% of its {usage_type} limit ({current:,} of {limit:,} {unit}).",
            notification_type=NotificationType.INFO if NotificationType else None,
            priority=NotificationPriority.MEDIUM if NotificationPriority else None,
            action_url=f"/tenant/{tenant.id}/manage",
            action_label="Manage Tenant",
            metadata={
                'tenant_id': tenant.id,
                'usage_type': usage_type,
                'percentage': percentage,
                'current': current,
                'limit': limit,
                'type': 'usage_warning'
            }
        )
    
    # ================= SUPPORT NOTIFICATIONS =================
    
    def notify_support_ticket_reply(self, ticket_id, reply_message):
        """Notify user when support replies to their ticket"""
        try:
            ticket = SupportTicket.query.get(ticket_id)
            if not ticket:
                return
            
            self.create_notification(
                user_id=ticket.user_id,
                title="Support Team Reply",
                message=f"Our support team has replied to your ticket #{ticket.ticket_number}. \"{reply_message[:100]}{'...' if len(reply_message) > 100 else ''}\"",
                notification_type=NotificationType.INFO if NotificationType else None,
                priority=NotificationPriority.MEDIUM if NotificationPriority else None,
                action_url=f"/support/ticket/{ticket.id}",
                action_label="View Reply",
                metadata={
                    'ticket_id': ticket.id,
                    'ticket_number': ticket.ticket_number,
                    'type': 'support_reply'
                }
            )
            
        except Exception as e:
            logger.error(f"Support reply notification failed: {str(e)}")
    
    def notify_ticket_status_change(self, ticket_id, old_status, new_status):
        """Notify user when ticket status changes"""
        try:
            ticket = SupportTicket.query.get(ticket_id)
            if not ticket:
                return
            
            status_messages = {
                TicketStatus.IN_PROGRESS: "is now being worked on by our support team",
                TicketStatus.WAITING_FOR_CUSTOMER: "is waiting for your response",
                TicketStatus.RESOLVED: "has been resolved",
                TicketStatus.CLOSED: "has been closed"
            }
            
            message = f"Your support ticket #{ticket.ticket_number} {status_messages.get(new_status, f'status changed to {new_status.value}')}."
            
            priority = NotificationPriority.MEDIUM if NotificationPriority else None
            notification_type = NotificationType.INFO if NotificationType else None
            
            if new_status == TicketStatus.RESOLVED:
                priority = NotificationPriority.HIGH if NotificationPriority else None
                notification_type = NotificationType.SUCCESS if NotificationType else None
            elif new_status == TicketStatus.WAITING_FOR_CUSTOMER:
                priority = NotificationPriority.HIGH if NotificationPriority else None
                notification_type = NotificationType.WARNING if NotificationType else None
            
            self.create_notification(
                user_id=ticket.user_id,
                title="Ticket Status Updated",
                message=message,
                notification_type=notification_type,
                priority=priority,
                action_url=f"/support/ticket/{ticket.id}",
                action_label="View Ticket",
                metadata={
                    'ticket_id': ticket.id,
                    'ticket_number': ticket.ticket_number,
                    'old_status': old_status.value,
                    'new_status': new_status.value,
                    'type': 'ticket_status_change'
                }
            )
            
        except Exception as e:
            logger.error(f"Ticket status notification failed: {str(e)}")
    
    # ================= SYSTEM NOTIFICATIONS =================
    
    def notify_system_maintenance(self, start_time, end_time, description):
        """Notify all users about scheduled maintenance"""
        try:
            users = SaasUser.query.filter_by(is_active=True).all()
            
            duration = end_time - start_time
            duration_text = f"{duration.seconds // 3600} hours" if duration.seconds >= 3600 else f"{duration.seconds // 60} minutes"
            
            for user in users:
                self.create_notification(
                    user_id=user.id,
                    title="Scheduled System Maintenance",
                    message=f"We will be performing system maintenance from {start_time.strftime('%B %d, %Y at %I:%M %p')} to {end_time.strftime('%I:%M %p UTC')} (approximately {duration_text}). {description}",
                    notification_type=NotificationType.SYSTEM_MAINTENANCE if NotificationType else None,
                    priority=NotificationPriority.HIGH if NotificationPriority else None,
                    expires_at=end_time + timedelta(hours=1),
                    metadata={
                        'start_time': start_time.isoformat(),
                        'end_time': end_time.isoformat(),
                        'duration': duration_text,
                        'type': 'system_maintenance'
                    }
                )
            
            logger.info(f"System maintenance notification sent to {len(users)} users")
            
        except Exception as e:
            logger.error(f"System maintenance notification failed: {str(e)}")
    
    def notify_service_disruption(self, service_name, issue_description, estimated_resolution=None):
        """Notify users about service disruptions"""
        try:
            users = SaasUser.query.filter_by(is_active=True).all()
            
            message = f"We are currently experiencing issues with {service_name}. {issue_description}"
            if estimated_resolution:
                message += f" We expect to resolve this issue by {estimated_resolution.strftime('%I:%M %p UTC')}."
            
            for user in users:
                self.create_notification(
                    user_id=user.id,
                    title="Service Disruption Notice",
                    message=message,
                    notification_type=NotificationType.ERROR if NotificationType else None,
                    priority=NotificationPriority.URGENT if NotificationPriority else None,
                    expires_at=estimated_resolution + timedelta(hours=2) if estimated_resolution else None,
                    metadata={
                        'service': service_name,
                        'issue': issue_description,
                        'estimated_resolution': estimated_resolution.isoformat() if estimated_resolution else None,
                        'type': 'service_disruption'
                    }
                )
            
            logger.info(f"Service disruption notification sent to {len(users)} users")
            
        except Exception as e:
            logger.error(f"Service disruption notification failed: {str(e)}")
    
    # ================= SECURITY NOTIFICATIONS =================
    
    def notify_security_alert(self, user_id, alert_type, alert_details):
        """Send security alert to user"""
        try:
            alert_messages = {
                'suspicious_login': "We detected a suspicious login attempt to your account.",
                'password_changed': "Your password has been changed successfully.",
                'account_locked': "Your account has been temporarily locked due to multiple failed login attempts.",
                'new_device': "Your account was accessed from a new device or location.",
                'api_key_compromised': "One of your API keys may have been compromised."
            }
            
            message = alert_messages.get(alert_type, "Security alert for your account.")
            
            self.create_notification(
                user_id=user_id,
                title="Security Alert",
                message=message,
                notification_type=NotificationType.SECURITY_ALERT if NotificationType else None,
                priority=NotificationPriority.URGENT if NotificationPriority else None,
                action_url="/user/security",
                action_label="Review Security",
                metadata={
                    'alert_type': alert_type,
                    'details': alert_details,
                    'type': 'security_alert'
                }
            )
            
        except Exception as e:
            logger.error(f"Security alert notification failed: {str(e)}")
    
    # ================= TENANT LIFECYCLE NOTIFICATIONS =================
    
    def notify_tenant_creation_complete(self, tenant_id):
        """Notify when tenant creation is complete"""
        try:
            tenant = Tenant.query.get(tenant_id)
            if not tenant:
                return
            
            owner = TenantUser.query.filter_by(tenant_id=tenant_id, access_level='owner').first()
            if not owner:
                return
            
            self.create_notification(
                user_id=owner.user_id,
                title="Your Tenant is Ready!",
                message=f"Great news! Your tenant '{tenant.name}' has been created successfully and is ready to use. You can now access your Odoo instance and start configuring your business processes.",
                notification_type=NotificationType.SUCCESS if NotificationType else None,
                priority=NotificationPriority.HIGH if NotificationPriority else None,
                action_url=f"https://{tenant.subdomain}.yourdomain.com",
                action_label="Access Your Tenant",
                metadata={
                    'tenant_id': tenant.id,
                    'tenant_name': tenant.name,
                    'subdomain': tenant.subdomain,
                    'admin_username': tenant.admin_username,
                    'type': 'tenant_ready'
                }
            )
            
        except Exception as e:
            logger.error(f"Tenant creation notification failed: {str(e)}")
    
    def notify_tenant_backup_completed(self, tenant_id, backup_info):
        """Notify when tenant backup is completed"""
        try:
            tenant = Tenant.query.get(tenant_id)
            if not tenant:
                return
            
            # Get all users with access to this tenant
            tenant_users = TenantUser.query.filter_by(tenant_id=tenant_id).all()
            
            for tenant_user in tenant_users:
                if tenant_user.access_level in ['owner', 'admin']:
                    self.create_notification(
                        user_id=tenant_user.user_id,
                        title="Backup Completed",
                        message=f"A backup of your tenant '{tenant.name}' has been completed successfully. Backup size: {backup_info.get('size', 'N/A')}.",
                        notification_type=NotificationType.SUCCESS if NotificationType else None,
                        priority=NotificationPriority.LOW if NotificationPriority else None,
                        action_url=f"/tenant/{tenant.id}/backups",
                        action_label="View Backups",
                        metadata={
                            'tenant_id': tenant.id,
                            'backup_id': backup_info.get('backup_id'),
                            'size': backup_info.get('size'),
                            'type': 'backup_completed'
                        }
                    )
            
        except Exception as e:
            logger.error(f"Backup notification failed: {str(e)}")
    
    # ================= NOTIFICATION CLEANUP =================
    
    def cleanup_old_notifications(self, days_old=30):
        """Clean up old notifications"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            
            # Delete old read notifications
            deleted_count = UserNotification.query.filter(
                UserNotification.is_read == True,
                UserNotification.created_at < cutoff_date
            ).delete()
            
            # Delete expired notifications
            expired_count = UserNotification.query.filter(
                UserNotification.expires_at < datetime.utcnow()
            ).delete()
            
            db.session.commit()
            
            total_deleted = deleted_count + expired_count
            if total_deleted > 0:
                logger.info(f"Cleaned up {total_deleted} old notifications")
            
            return total_deleted
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Notification cleanup failed: {str(e)}")
            return 0

# ================= NOTIFICATION SCHEDULER =================

class NotificationScheduler:
    """Handles scheduled notification checks"""
    
    def __init__(self):
        self.notification_service = EnhancedNotificationService()
    
    def run_daily_checks(self):
        """Run daily notification checks"""
        logger.info("Starting daily notification checks")
        
        try:
            # Check subscription renewals
            self.notification_service.check_subscription_renewals()
            
            # Cleanup old notifications
            self.notification_service.cleanup_old_notifications()
            
            logger.info("Daily notification checks completed")
            
        except Exception as e:
            logger.error(f"Daily notification checks failed: {str(e)}")
    
    def run_hourly_checks(self):
        """Run hourly notification checks"""
        logger.info("Starting hourly notification checks")
        
        try:
            # Check for urgent renewals
            self.notification_service.check_subscription_renewals()
            
            logger.info("Hourly notification checks completed")
            
        except Exception as e:
            logger.error(f"Hourly notification checks failed: {str(e)}")

# Export classes
__all__ = [
    'EnhancedNotificationService',
    'NotificationScheduler'
]