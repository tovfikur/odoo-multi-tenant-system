"""
User Notification System
Provides real-time notifications for users via WebSocket and database storage
"""

import json
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict, Optional

from db import db
from models import SaasUser

logger = logging.getLogger(__name__)

class NotificationType(Enum):
    """Notification types"""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    TENANT_UPDATE = "tenant_update"
    SYSTEM_MAINTENANCE = "system_maintenance"
    SECURITY_ALERT = "security_alert"
    BILLING_UPDATE = "billing_update"

class NotificationPriority(Enum):
    """Notification priority levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class UserNotification(db.Model):
    """Database model for storing user notifications"""
    __tablename__ = 'user_notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('saas_users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.Enum(NotificationType), nullable=False, default=NotificationType.INFO)
    priority = db.Column(db.Enum(NotificationPriority), nullable=False, default=NotificationPriority.LOW)
    
    is_read = db.Column(db.Boolean, default=False)
    is_dismissed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime)
    dismissed_at = db.Column(db.DateTime)
    
    # Optional metadata
    action_url = db.Column(db.String(500))  # URL for action button
    action_label = db.Column(db.String(100))  # Label for action button
    extra_data = db.Column(db.JSON)  # Additional notification data
    expires_at = db.Column(db.DateTime)  # Expiration date for temporary notifications
    
    # Relationships
    user = db.relationship('SaasUser', backref='notifications')
    
    def to_dict(self):
        """Convert notification to dictionary"""
        return {
            'id': self.id,
            'title': self.title,
            'message': self.message,
            'type': self.type.value,
            'priority': self.priority.value,
            'is_read': self.is_read,
            'is_dismissed': self.is_dismissed,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'read_at': self.read_at.isoformat() if self.read_at else None,
            'dismissed_at': self.dismissed_at.isoformat() if self.dismissed_at else None,
            'action_url': self.action_url,
            'action_label': self.action_label,
            'metadata': self.extra_data,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None
        }

class NotificationService:
    """Service for managing user notifications"""
    
    def __init__(self, ws_manager=None, redis_client=None):
        self.ws_manager = ws_manager
        self.redis_client = redis_client
    
    def create_notification(self, 
                          user_id: int,
                          title: str,
                          message: str,
                          notification_type: NotificationType = NotificationType.INFO,
                          priority: NotificationPriority = NotificationPriority.LOW,
                          action_url: Optional[str] = None,
                          action_label: Optional[str] = None,
                          metadata: Optional[Dict] = None,
                          expires_at: Optional[datetime] = None,
                          send_realtime: bool = True) -> UserNotification:
        """Create a new notification for a user"""
        try:
            notification = UserNotification(
                user_id=user_id,
                title=title,
                message=message,
                type=notification_type,
                priority=priority,
                action_url=action_url,
                action_label=action_label,
                extra_data=metadata,
                expires_at=expires_at
            )
            
            db.session.add(notification)
            db.session.commit()
            
            # Send real-time notification via WebSocket
            if send_realtime and self.ws_manager:
                self.send_realtime_notification(user_id, notification)
            
            logger.info(f"Created notification {notification.id} for user {user_id}")
            return notification
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to create notification for user {user_id}: {str(e)}")
            raise
    
    def send_realtime_notification(self, user_id: int, notification: UserNotification):
        """Send real-time notification via WebSocket"""
        if not self.ws_manager:
            return
        
        try:
            notification_data = notification.to_dict()
            self.ws_manager.emit_to_user(user_id, 'new_notification', notification_data)
            logger.debug(f"Sent real-time notification {notification.id} to user {user_id}")
        except Exception as e:
            logger.error(f"Failed to send real-time notification: {str(e)}")
    
    def broadcast_notification(self,
                             user_ids: List[int],
                             title: str,
                             message: str,
                             notification_type: NotificationType = NotificationType.INFO,
                             priority: NotificationPriority = NotificationPriority.LOW,
                             action_url: Optional[str] = None,
                             action_label: Optional[str] = None,
                             metadata: Optional[Dict] = None,
                             expires_at: Optional[datetime] = None) -> List[UserNotification]:
        """Create and broadcast notification to multiple users"""
        notifications = []
        
        try:
            for user_id in user_ids:
                notification = UserNotification(
                    user_id=user_id,
                    title=title,
                    message=message,
                    type=notification_type,
                    priority=priority,
                    action_url=action_url,
                    action_label=action_label,
                    extra_data=metadata,
                    expires_at=expires_at
                )
                db.session.add(notification)
                notifications.append(notification)
            
            db.session.commit()
            
            # Send real-time notifications
            if self.ws_manager:
                for notification in notifications:
                    self.send_realtime_notification(notification.user_id, notification)
            
            logger.info(f"Broadcast notification to {len(user_ids)} users")
            return notifications
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to broadcast notification: {str(e)}")
            raise
    
    def get_user_notifications(self, 
                             user_id: int,
                             include_read: bool = True,
                             include_dismissed: bool = False,
                             limit: int = 50,
                             offset: int = 0) -> List[UserNotification]:
        """Get user's notifications"""
        try:
            query = UserNotification.query.filter_by(user_id=user_id)
            
            if not include_read:
                query = query.filter_by(is_read=False)
            
            if not include_dismissed:
                query = query.filter_by(is_dismissed=False)
            
            # Filter out expired notifications
            query = query.filter(
                (UserNotification.expires_at.is_(None)) | 
                (UserNotification.expires_at > datetime.utcnow())
            )
            
            notifications = query.order_by(
                UserNotification.created_at.desc()
            ).limit(limit).offset(offset).all()
            
            return notifications
            
        except Exception as e:
            logger.error(f"Failed to get notifications for user {user_id}: {str(e)}")
            return []
    
    def mark_as_read(self, notification_id: int, user_id: int) -> bool:
        """Mark notification as read"""
        try:
            notification = UserNotification.query.filter_by(
                id=notification_id,
                user_id=user_id
            ).first()
            
            if not notification:
                return False
            
            notification.is_read = True
            notification.read_at = datetime.utcnow()
            db.session.commit()
            
            # Send real-time update
            if self.ws_manager:
                self.ws_manager.emit_to_user(user_id, 'notification_read', {
                    'notification_id': notification_id
                })
            
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to mark notification {notification_id} as read: {str(e)}")
            return False
    
    def dismiss_notification(self, notification_id: int, user_id: int) -> bool:
        """Dismiss notification"""
        try:
            notification = UserNotification.query.filter_by(
                id=notification_id,
                user_id=user_id
            ).first()
            
            if not notification:
                return False
            
            notification.is_dismissed = True
            notification.dismissed_at = datetime.utcnow()
            db.session.commit()
            
            # Send real-time update
            if self.ws_manager:
                self.ws_manager.emit_to_user(user_id, 'notification_dismissed', {
                    'notification_id': notification_id
                })
            
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to dismiss notification {notification_id}: {str(e)}")
            return False
    
    def mark_all_as_read(self, user_id: int) -> int:
        """Mark all user's unread notifications as read"""
        try:
            count = UserNotification.query.filter_by(
                user_id=user_id,
                is_read=False
            ).update({
                'is_read': True,
                'read_at': datetime.utcnow()
            })
            
            db.session.commit()
            
            # Send real-time update
            if self.ws_manager:
                self.ws_manager.emit_to_user(user_id, 'all_notifications_read', {
                    'count': count
                })
            
            logger.info(f"Marked {count} notifications as read for user {user_id}")
            return count
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to mark all notifications as read for user {user_id}: {str(e)}")
            return 0
    
    def get_notification_counts(self, user_id: int) -> Dict[str, int]:
        """Get notification counts for user"""
        try:
            total = UserNotification.query.filter_by(
                user_id=user_id,
                is_dismissed=False
            ).filter(
                (UserNotification.expires_at.is_(None)) |
                (UserNotification.expires_at > datetime.utcnow())
            ).count()
            
            unread = UserNotification.query.filter_by(
                user_id=user_id,
                is_read=False,
                is_dismissed=False
            ).filter(
                (UserNotification.expires_at.is_(None)) |
                (UserNotification.expires_at > datetime.utcnow())
            ).count()
            
            urgent = UserNotification.query.filter_by(
                user_id=user_id,
                is_read=False,
                is_dismissed=False,
                priority=NotificationPriority.URGENT
            ).filter(
                (UserNotification.expires_at.is_(None)) |
                (UserNotification.expires_at > datetime.utcnow())
            ).count()
            
            return {
                'total': total,
                'unread': unread,
                'urgent': urgent
            }
            
        except Exception as e:
            logger.error(f"Failed to get notification counts for user {user_id}: {str(e)}")
            return {'total': 0, 'unread': 0, 'urgent': 0}
    
    def cleanup_expired_notifications(self):
        """Clean up expired notifications"""
        try:
            deleted_count = UserNotification.query.filter(
                UserNotification.expires_at < datetime.utcnow()
            ).delete()
            
            db.session.commit()
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} expired notifications")
            
            return deleted_count
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to cleanup expired notifications: {str(e)}")
            return 0

# Notification helper functions
def notify_tenant_created(user_ids: List[int], tenant_name: str, tenant_subdomain: str, 
                         notification_service: NotificationService):
    """Send notification when tenant is created"""
    notification_service.broadcast_notification(
        user_ids=user_ids,
        title="New Tenant Created",
        message=f"Your tenant '{tenant_name}' has been successfully created and is ready to use.",
        notification_type=NotificationType.SUCCESS,
        priority=NotificationPriority.MEDIUM,
        action_url=f"/tenant/{tenant_subdomain}",
        action_label="Access Tenant",
        metadata={'tenant_name': tenant_name, 'tenant_subdomain': tenant_subdomain}
    )

def notify_tenant_status_change(user_ids: List[int], tenant_name: str, old_status: str, 
                               new_status: str, notification_service: NotificationService):
    """Send notification when tenant status changes"""
    notification_type = NotificationType.INFO
    priority = NotificationPriority.MEDIUM
    
    if new_status == 'suspended':
        notification_type = NotificationType.WARNING
        priority = NotificationPriority.HIGH
    elif new_status == 'terminated':
        notification_type = NotificationType.ERROR
        priority = NotificationPriority.URGENT
    
    notification_service.broadcast_notification(
        user_ids=user_ids,
        title="Tenant Status Updated",
        message=f"Your tenant '{tenant_name}' status has changed from {old_status} to {new_status}.",
        notification_type=notification_type,
        priority=priority,
        metadata={'tenant_name': tenant_name, 'old_status': old_status, 'new_status': new_status}
    )

def notify_system_maintenance(user_ids: List[int], maintenance_message: str, 
                            start_time: datetime, end_time: datetime,
                            notification_service: NotificationService):
    """Send system maintenance notification"""
    notification_service.broadcast_notification(
        user_ids=user_ids,
        title="Scheduled System Maintenance",
        message=maintenance_message,
        notification_type=NotificationType.SYSTEM_MAINTENANCE,
        priority=NotificationPriority.HIGH,
        metadata={
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat()
        },
        expires_at=end_time + timedelta(hours=1)
    )

def notify_security_alert(user_id: int, alert_message: str, alert_details: Dict,
                         notification_service: NotificationService):
    """Send security alert notification"""
    notification_service.create_notification(
        user_id=user_id,
        title="Security Alert",
        message=alert_message,
        notification_type=NotificationType.SECURITY_ALERT,
        priority=NotificationPriority.URGENT,
        action_url="/user/security",
        action_label="Review Security",
        metadata=alert_details
    )

# Export main classes and functions
__all__ = [
    'NotificationType',
    'NotificationPriority', 
    'UserNotification',
    'NotificationService',
    'notify_tenant_created',
    'notify_tenant_status_change',
    'notify_system_maintenance',
    'notify_security_alert'
]