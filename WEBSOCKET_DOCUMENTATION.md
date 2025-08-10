# WebSocket Documentation

## Overview

The Odoo Multi-Tenant System provides real-time communication through WebSockets using Socket.IO. This enables real-time notifications, live data updates, and interactive features for users.

## Connection Setup

### JavaScript/Browser Client
```javascript
// Include Socket.IO client library
<script src="/static/js/socket.io.min.js"></script>

// Connect to WebSocket
const socket = io({
  transports: ['websocket', 'polling'],
  upgrade: true
});

// Connection event handlers
socket.on('connect', function() {
  console.log('Connected to WebSocket server');
});

socket.on('disconnect', function() {
  console.log('Disconnected from WebSocket server');
});

socket.on('connect_error', function(error) {
  console.error('Connection error:', error);
});
```

### Authentication

WebSocket connections require user authentication. Users must be logged in to establish a WebSocket connection. Unauthenticated connection attempts will be automatically disconnected.

## Events Reference

### Connection Events

#### `connect`
Emitted when the client successfully connects to the server.

**Server Response:**
```javascript
{
  "user_id": 123,
  "timestamp": "2024-01-20T14:30:00Z",
  "message": "Connected successfully"
}
```

#### `disconnect`
Emitted when the client disconnects from the server.

### Subscription Events

#### `subscribe_tenant_updates`
Subscribe to updates for a specific tenant.

**Client Emit:**
```javascript
socket.emit('subscribe_tenant_updates', {
  tenant_id: 1
});
```

**Server Response:**
```javascript
{
  "tenant_id": 1,
  "message": "Subscribed to tenant 1 updates"
}
```

#### `unsubscribe_tenant_updates`
Unsubscribe from updates for a specific tenant.

**Client Emit:**
```javascript
socket.emit('unsubscribe_tenant_updates', {
  tenant_id: 1
});
```

**Server Response:**
```javascript
{
  "tenant_id": 1,
  "message": "Unsubscribed from tenant 1 updates"
}
```

### Data Refresh Events

#### `request_data_refresh`
Request fresh data from the server.

**Client Emit:**
```javascript
socket.emit('request_data_refresh', {
  type: 'tenants',           // 'tenants', 'notifications', 'admin_stats'
  force_refresh: true        // Optional: bypass cache
});
```

**Server Response (`data_refreshed`):**
```javascript
{
  "type": "tenants",
  "data": { /* refreshed data */ },
  "timestamp": "2024-01-20T14:30:00Z"
}
```

### Notification Events

#### `get_notification_counts`
Get current notification counts for the user.

**Client Emit:**
```javascript
socket.emit('get_notification_counts');
```

**Server Response (`notification_counts`):**
```javascript
{
  "total": 5,
  "unread": 3,
  "urgent": 1
}
```

#### `mark_notification_read`
Mark a notification as read via WebSocket.

**Client Emit:**
```javascript
socket.emit('mark_notification_read', {
  notification_id: 123
});
```

**Server Response (`notification_action_completed`):**
```javascript
{
  "action": "read",
  "notification_id": 123,
  "success": true
}
```

#### `dismiss_notification`
Dismiss a notification via WebSocket.

**Client Emit:**
```javascript
socket.emit('dismiss_notification', {
  notification_id: 123
});
```

**Server Response (`notification_action_completed`):**
```javascript
{
  "action": "dismiss",
  "notification_id": 123,
  "success": true
}
```

### Server-to-Client Events

#### `new_notification`
Emitted when a new notification is created for the user.

**Data:**
```javascript
{
  "id": 456,
  "title": "New Tenant Created",
  "message": "Your tenant 'My Company' has been successfully created.",
  "type": "success",
  "priority": "medium",
  "is_read": false,
  "is_dismissed": false,
  "created_at": "2024-01-20T14:30:00Z",
  "action_url": "/tenant/mycompany",
  "action_label": "Access Tenant",
  "metadata": {
    "tenant_name": "My Company"
  }
}
```

#### `notification_read`
Emitted when a notification is marked as read.

**Data:**
```javascript
{
  "notification_id": 123
}
```

#### `notification_dismissed`
Emitted when a notification is dismissed.

**Data:**
```javascript
{
  "notification_id": 123
}
```

#### `all_notifications_read`
Emitted when all notifications are marked as read.

**Data:**
```javascript
{
  "count": 5
}
```

#### `tenant_created`
Emitted when a new tenant is created.

**Data:**
```javascript
{
  "tenant": {
    "id": 2,
    "name": "New Company",
    "subdomain": "newcompany",
    "status": "active"
  },
  "message": "New tenant 'New Company' created successfully"
}
```

#### `tenant_updated`
Emitted when a tenant is updated.

**Data:**
```javascript
{
  "tenant": {
    "id": 1,
    "name": "Updated Company",
    "status": "active"
  },
  "message": "Tenant 'Updated Company' updated successfully"
}
```

#### `tenant_status_changed`
Emitted when a tenant's status changes.

**Data:**
```javascript
{
  "tenant": {
    "id": 1,
    "name": "My Company",
    "status": "suspended"
  },
  "message": "Tenant 'My Company' status changed to suspended"
}
```

#### `error`
Emitted when an error occurs during WebSocket communication.

**Data:**
```javascript
{
  "message": "Error description",
  "error": "Detailed error information"
}
```

## Complete Client Implementation Example

```javascript
class WebSocketClient {
  constructor() {
    this.socket = null;
    this.connected = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000;
    
    this.init();
  }
  
  init() {
    this.socket = io({
      transports: ['websocket', 'polling'],
      upgrade: true
    });
    
    this.setupEventHandlers();
  }
  
  setupEventHandlers() {
    // Connection events
    this.socket.on('connect', () => {
      console.log('WebSocket connected');
      this.connected = true;
      this.reconnectAttempts = 0;
      this.onConnected();
    });
    
    this.socket.on('disconnect', (reason) => {
      console.log('WebSocket disconnected:', reason);
      this.connected = false;
      this.onDisconnected(reason);
      
      if (reason === 'io server disconnect') {
        // Server initiated disconnect, try to reconnect
        this.handleReconnection();
      }
    });
    
    this.socket.on('connect_error', (error) => {
      console.error('WebSocket connection error:', error);
      this.handleReconnection();
    });
    
    // Notification events
    this.socket.on('new_notification', (notification) => {
      this.handleNewNotification(notification);
    });
    
    this.socket.on('notification_counts', (counts) => {
      this.updateNotificationCounts(counts);
    });
    
    this.socket.on('notification_read', (data) => {
      this.markNotificationAsRead(data.notification_id);
    });
    
    this.socket.on('notification_dismissed', (data) => {
      this.removeNotification(data.notification_id);
    });
    
    this.socket.on('all_notifications_read', (data) => {
      this.markAllNotificationsAsRead(data.count);
    });
    
    // Tenant events
    this.socket.on('tenant_created', (data) => {
      this.handleTenantCreated(data);
    });
    
    this.socket.on('tenant_updated', (data) => {
      this.handleTenantUpdated(data);
    });
    
    this.socket.on('tenant_status_changed', (data) => {
      this.handleTenantStatusChanged(data);
    });
    
    // Data refresh events
    this.socket.on('data_refreshed', (data) => {
      this.handleDataRefreshed(data);
    });
    
    // Error handling
    this.socket.on('error', (error) => {
      console.error('WebSocket error:', error);
      this.handleError(error);
    });
  }
  
  // Connection management
  onConnected() {
    // Subscribe to tenant updates for current user's tenants
    this.subscribeToTenantUpdates();
    
    // Request initial notification counts
    this.getNotificationCounts();
  }
  
  onDisconnected(reason) {
    // Handle disconnection UI updates
    this.showConnectionStatus(false);
  }
  
  handleReconnection() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
      
      setTimeout(() => {
        console.log(`Attempting reconnection ${this.reconnectAttempts}/${this.maxReconnectAttempts}`);
        this.socket.connect();
      }, delay);
    } else {
      console.error('Max reconnection attempts reached');
      this.showReconnectionError();
    }
  }
  
  // Notification methods
  getNotificationCounts() {
    if (this.connected) {
      this.socket.emit('get_notification_counts');
    }
  }
  
  markNotificationRead(notificationId) {
    if (this.connected) {
      this.socket.emit('mark_notification_read', {
        notification_id: notificationId
      });
    }
  }
  
  dismissNotification(notificationId) {
    if (this.connected) {
      this.socket.emit('dismiss_notification', {
        notification_id: notificationId
      });
    }
  }
  
  // Data refresh methods
  refreshTenants(forceRefresh = false) {
    if (this.connected) {
      this.socket.emit('request_data_refresh', {
        type: 'tenants',
        force_refresh: forceRefresh
      });
    }
  }
  
  refreshNotifications(forceRefresh = false) {
    if (this.connected) {
      this.socket.emit('request_data_refresh', {
        type: 'notifications',
        force_refresh: forceRefresh
      });
    }
  }
  
  // Subscription methods
  subscribeToTenantUpdates(tenantId = null) {
    if (this.connected) {
      if (tenantId) {
        this.socket.emit('subscribe_tenant_updates', {
          tenant_id: tenantId
        });
      } else {
        // Subscribe to all user's tenants
        // This would typically be called with each tenant ID
        this.getUserTenants().forEach(tenant => {
          this.socket.emit('subscribe_tenant_updates', {
            tenant_id: tenant.id
          });
        });
      }
    }
  }
  
  unsubscribeFromTenantUpdates(tenantId) {
    if (this.connected) {
      this.socket.emit('unsubscribe_tenant_updates', {
        tenant_id: tenantId
      });
    }
  }
  
  // Event handlers (implement these based on your UI)
  handleNewNotification(notification) {
    // Add notification to UI
    console.log('New notification:', notification);
    this.addNotificationToUI(notification);
    this.playNotificationSound();
  }
  
  updateNotificationCounts(counts) {
    // Update notification badge/counter
    document.getElementById('notification-count').textContent = counts.unread;
    document.getElementById('urgent-count').textContent = counts.urgent;
  }
  
  handleTenantCreated(data) {
    // Handle new tenant creation
    console.log('Tenant created:', data);
    this.refreshTenantList();
  }
  
  handleTenantUpdated(data) {
    // Handle tenant update
    console.log('Tenant updated:', data);
    this.updateTenantInUI(data.tenant);
  }
  
  handleDataRefreshed(data) {
    // Handle refreshed data
    switch (data.type) {
      case 'tenants':
        this.updateTenantsList(data.data);
        break;
      case 'notifications':
        this.updateNotificationsList(data.data.notifications);
        this.updateNotificationCounts(data.data.counts);
        break;
    }
  }
  
  handleError(error) {
    // Show error message to user
    this.showErrorMessage(error.message);
  }
  
  // UI helper methods (implement these based on your frontend)
  addNotificationToUI(notification) {
    // Implementation depends on your UI framework
  }
  
  markNotificationAsRead(notificationId) {
    // Update UI to show notification as read
  }
  
  removeNotification(notificationId) {
    // Remove notification from UI
  }
  
  showConnectionStatus(connected) {
    // Show connection status indicator
  }
  
  showErrorMessage(message) {
    // Show error message to user
  }
  
  playNotificationSound() {
    // Play notification sound if enabled
  }
}

// Initialize WebSocket client
const wsClient = new WebSocketClient();

// Example usage
document.addEventListener('DOMContentLoaded', function() {
  // Mark notification as read when clicked
  document.addEventListener('click', function(e) {
    if (e.target.classList.contains('notification-item')) {
      const notificationId = e.target.dataset.notificationId;
      wsClient.markNotificationRead(parseInt(notificationId));
    }
  });
  
  // Refresh data button
  document.getElementById('refresh-tenants').addEventListener('click', function() {
    wsClient.refreshTenants(true);
  });
});
```

## Best Practices

### Connection Management
1. **Automatic Reconnection**: Implement exponential backoff for reconnection attempts
2. **Connection Status**: Show users the connection status
3. **Graceful Degradation**: Provide fallback functionality when WebSocket is unavailable

### Error Handling
1. **Validate Events**: Always validate incoming event data
2. **Error Recovery**: Implement error recovery mechanisms
3. **User Feedback**: Provide clear error messages to users

### Performance
1. **Event Throttling**: Throttle high-frequency events to prevent UI freezing
2. **Memory Management**: Clean up event listeners to prevent memory leaks
3. **Selective Updates**: Only update UI elements that have actually changed

### Security
1. **Authentication**: Ensure all WebSocket connections are authenticated
2. **Data Validation**: Validate all incoming data from the server
3. **Rate Limiting**: Respect server-side rate limits

## Troubleshooting

### Common Issues

**Connection Fails:**
- Verify user is logged in
- Check network connectivity
- Ensure WebSocket endpoint is accessible

**Events Not Received:**
- Check if subscribed to the correct events
- Verify user has permissions for the data
- Check server logs for errors

**High Memory Usage:**
- Ensure event listeners are properly cleaned up
- Avoid storing large amounts of data in memory
- Use pagination for large datasets

### Debug Mode
Enable debug mode for detailed logging:

```javascript
localStorage.debug = 'socket.io-client:*';
```

This will provide detailed logging of all WebSocket communication in the browser console.