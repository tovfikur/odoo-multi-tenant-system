# websocket_handler.py

# Standard library imports
import json
import logging
import threading
from datetime import datetime

# Third-party imports
import redis
from flask import request
from flask_login import current_user
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect

logger = logging.getLogger(__name__)

class WebSocketManager:
    """Manages WebSocket connections and real-time updates"""
    
    def __init__(self, socketio: SocketIO, redis_client: redis.Redis):
        self.socketio = socketio
        self.redis_client = redis_client
        self.connected_users = {}  # {user_id: [session_ids]}
        self.session_users = {}    # {session_id: user_id}
        
        # Start Redis subscriber thread
        if redis_client:
            self.start_redis_subscriber()
    
    def start_redis_subscriber(self):
        """Start Redis subscriber for real-time updates"""
        def redis_subscriber():
            try:
                pubsub = self.redis_client.pubsub()
                pubsub.subscribe('realtime_updates')
                
                for message in pubsub.listen():
                    if message['type'] == 'message':
                        try:
                            data = json.loads(message['data'])
                            self.handle_redis_message(data)
                        except Exception as e:
                            logger.error(f"Failed to process Redis message: {e}")
                            
            except Exception as e:
                logger.error(f"Redis subscriber error: {e}")
        
        thread = threading.Thread(target=redis_subscriber, daemon=True)
        thread.start()
        logger.info("Started Redis subscriber thread")
    
    def handle_redis_message(self, data):
        """Handle messages from Redis and broadcast to WebSocket clients"""
        event_type = data.get('event')
        event_data = data.get('data', {})
        user_ids = data.get('user_ids')
        
        if user_ids:
            # Send to specific users
            for user_id in user_ids:
                self.emit_to_user(user_id, event_type, event_data)
        else:
            # Broadcast to all connected users
            self.socketio.emit(event_type, event_data)
    
    def emit_to_user(self, user_id, event, data):
        """Emit event to specific user's sessions"""
        if user_id in self.connected_users:
            for session_id in self.connected_users[user_id]:
                self.socketio.emit(event, data, room=session_id)
    
    def add_user_session(self, user_id, session_id):
        """Add user session to tracking"""
        if user_id not in self.connected_users:
            self.connected_users[user_id] = []
        
        if session_id not in self.connected_users[user_id]:
            self.connected_users[user_id].append(session_id)
        
        self.session_users[session_id] = user_id
        logger.debug(f"Added session {session_id} for user {user_id}")
    
    def remove_user_session(self, session_id):
        """Remove user session from tracking"""
        if session_id in self.session_users:
            user_id = self.session_users[session_id]
            
            if user_id in self.connected_users:
                if session_id in self.connected_users[user_id]:
                    self.connected_users[user_id].remove(session_id)
                
                # Clean up empty user entries
                if not self.connected_users[user_id]:
                    del self.connected_users[user_id]
            
            del self.session_users[session_id]
            logger.debug(f"Removed session {session_id} for user {user_id}")

# WebSocket event handlers
def setup_websocket_handlers(socketio, ws_manager):
    """Setup WebSocket event handlers"""
    
    @socketio.on('connect')
    def handle_connect():
        """Handle client connection"""
        if not current_user.is_authenticated:
            logger.warning("Unauthenticated WebSocket connection attempt")
            disconnect()
            return False
        
        session_id = request.sid
        user_id = current_user.id
        
        # Join user-specific room
        join_room(f"user_{user_id}")
        ws_manager.add_user_session(user_id, session_id)
        
        # Send initial data
        emit('connected', {
            'user_id': user_id,
            'timestamp': datetime.utcnow().isoformat(),
            'message': 'Connected successfully'
        })
        
        logger.info(f"User {user_id} connected via WebSocket (session: {session_id})")
    
    @socketio.on('disconnect')
    def handle_disconnect(reason=None):
        """Handle client disconnection"""
        session_id = request.sid
        ws_manager.remove_user_session(session_id)
        logger.info(f"WebSocket session disconnected: {session_id}, reason: {reason}")
    
    @socketio.on('subscribe_tenant_updates')
    def handle_tenant_subscription(data):
        """Subscribe to tenant-specific updates"""
        if not current_user.is_authenticated:
            return
        
        tenant_id = data.get('tenant_id')
        if tenant_id:
            join_room(f"tenant_{tenant_id}")
            emit('subscribed', {
                'tenant_id': tenant_id,
                'message': f'Subscribed to tenant {tenant_id} updates'
            })
    
    @socketio.on('unsubscribe_tenant_updates')
    def handle_tenant_unsubscription(data):
        """Unsubscribe from tenant-specific updates"""
        if not current_user.is_authenticated:
            return
        
        tenant_id = data.get('tenant_id')
        if tenant_id:
            leave_room(f"tenant_{tenant_id}")
            emit('unsubscribed', {
                'tenant_id': tenant_id,
                'message': f'Unsubscribed from tenant {tenant_id} updates'
            })
    
    @socketio.on('request_data_refresh')
    def handle_data_refresh(data):
        """Handle request for data refresh"""
        if not current_user.is_authenticated:
            return
        
        data_type = data.get('type')
        force_refresh = data.get('force_refresh', False)
        
        try:
            if data_type == 'tenants':
                from cache_manager import get_cached_user_tenants
                tenants = get_cached_user_tenants(current_user.id, force_refresh)
                emit('data_refreshed', {
                    'type': 'tenants',
                    'data': tenants,
                    'timestamp': datetime.utcnow().isoformat()
                })
            
            elif data_type == 'admin_stats' and current_user.is_admin:
                from cache_manager import get_cached_admin_stats
                stats = get_cached_admin_stats(force_refresh)
                emit('data_refreshed', {
                    'type': 'admin_stats',
                    'data': stats,
                    'timestamp': datetime.utcnow().isoformat()
                })
            
            elif data_type == 'notifications':
                from user_notifications import NotificationService
                notification_service = NotificationService()
                notifications = notification_service.get_user_notifications(current_user.id, limit=10)
                counts = notification_service.get_notification_counts(current_user.id)
                
                emit('data_refreshed', {
                    'type': 'notifications',
                    'data': {
                        'notifications': [n.to_dict() for n in notifications],
                        'counts': counts
                    },
                    'timestamp': datetime.utcnow().isoformat()
                })
        
        except Exception as e:
            logger.error(f"Failed to refresh data for user {current_user.id}: {e}")
            emit('error', {
                'message': 'Failed to refresh data',
                'error': str(e)
            })
    
    @socketio.on('mark_notification_read')
    def handle_mark_notification_read(data):
        """Handle marking notification as read via WebSocket"""
        if not current_user.is_authenticated:
            return
        
        notification_id = data.get('notification_id')
        if not notification_id:
            emit('error', {'message': 'Notification ID required'})
            return
        
        try:
            from user_notifications import NotificationService
            notification_service = NotificationService(ws_manager)
            success = notification_service.mark_as_read(notification_id, current_user.id)
            
            if success:
                emit('notification_action_completed', {
                    'action': 'read',
                    'notification_id': notification_id,
                    'success': True
                })
            else:
                emit('error', {'message': 'Notification not found or access denied'})
        
        except Exception as e:
            logger.error(f"Failed to mark notification as read via WebSocket: {e}")
            emit('error', {'message': 'Failed to mark notification as read'})
    
    @socketio.on('dismiss_notification')
    def handle_dismiss_notification(data):
        """Handle dismissing notification via WebSocket"""
        if not current_user.is_authenticated:
            return
        
        notification_id = data.get('notification_id')
        if not notification_id:
            emit('error', {'message': 'Notification ID required'})
            return
        
        try:
            from user_notifications import NotificationService
            notification_service = NotificationService(ws_manager)
            success = notification_service.dismiss_notification(notification_id, current_user.id)
            
            if success:
                emit('notification_action_completed', {
                    'action': 'dismiss',
                    'notification_id': notification_id,
                    'success': True
                })
            else:
                emit('error', {'message': 'Notification not found or access denied'})
        
        except Exception as e:
            logger.error(f"Failed to dismiss notification via WebSocket: {e}")
            emit('error', {'message': 'Failed to dismiss notification'})
    
    @socketio.on('get_notification_counts')
    def handle_get_notification_counts():
        """Get notification counts via WebSocket"""
        if not current_user.is_authenticated:
            return
        
        try:
            from user_notifications import NotificationService
            notification_service = NotificationService()
            counts = notification_service.get_notification_counts(current_user.id)
            
            emit('notification_counts', counts)
        
        except Exception as e:
            logger.error(f"Failed to get notification counts via WebSocket: {e}")
            emit('error', {'message': 'Failed to get notification counts'})


# Update triggers for cache invalidation and real-time updates
class UpdateTrigger:
    """Handles cache invalidation and real-time updates when data changes"""
    
    def __init__(self, cache_manager, ws_manager):
        self.cache_manager = cache_manager
        self.ws_manager = ws_manager
    
    def tenant_created(self, tenant_data, user_ids):
        """Trigger updates when tenant is created"""
        # Invalidate cache
        self.cache_manager.invalidate_user_tenants_cache(user_ids)
        self.cache_manager.invalidate_admin_stats_cache()
        
        # Broadcast real-time update
        self.cache_manager.broadcast_update(
            'tenant_created',
            {
                'tenant': tenant_data,
                'message': f"New tenant '{tenant_data['name']}' created successfully"
            },
            user_ids
        )
    
    def tenant_updated(self, tenant_data, user_ids):
        """Trigger updates when tenant is updated"""
        # Invalidate cache
        self.cache_manager.invalidate_tenant_cache(tenant_data['id'])
        
        # Broadcast real-time update
        self.cache_manager.broadcast_update(
            'tenant_updated',
            {
                'tenant': tenant_data,
                'message': f"Tenant '{tenant_data['name']}' updated successfully"
            },
            user_ids
        )
    
    def tenant_deleted(self, tenant_data, user_ids):
        """Trigger updates when tenant is deleted"""
        # Invalidate cache
        self.cache_manager.invalidate_user_tenants_cache(user_ids)
        self.cache_manager.invalidate_admin_stats_cache()
        
        # Broadcast real-time update
        self.cache_manager.broadcast_update(
            'tenant_deleted',
            {
                'tenant_id': tenant_data['id'],
                'message': f"Tenant '{tenant_data['name']}' deleted successfully"
            },
            user_ids
        )
    
    def tenant_status_changed(self, tenant_data, user_ids):
        """Trigger updates when tenant status changes"""
        # Invalidate cache
        self.cache_manager.invalidate_tenant_cache(tenant_data['id'])
        
        # Broadcast real-time update
        self.cache_manager.broadcast_update(
            'tenant_status_changed',
            {
                'tenant': tenant_data,
                'message': f"Tenant '{tenant_data['name']}' status changed to {tenant_data['status']}"
            },
            user_ids
        )
    
    def user_stats_changed(self):
        """Trigger updates when user statistics change"""
        # Invalidate cache
        self.cache_manager.invalidate_admin_stats_cache()
        
        # Broadcast to admin users only
        self.cache_manager.broadcast_update(
            'admin_stats_updated',
            {
                'message': 'Admin statistics updated'
            }
        )