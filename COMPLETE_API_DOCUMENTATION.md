# Complete Mobile App API Documentation

## Overview

This document provides comprehensive API documentation for the complete mobile application functionality covering ALL website features. The API provides full feature parity with the web application.

## Table of Contents

1. [Authentication & Public APIs](#authentication--public-apis)
2. [User Profile Management](#user-profile-management)
3. [Tenant Management](#tenant-management)
4. [Billing & Subscriptions](#billing--subscriptions)
5. [Support & Communication](#support--communication)
6. [Notifications & Real-time Updates](#notifications--real-time-updates)
7. [WebSocket Events](#websocket-events)
8. [Error Handling](#error-handling)
9. [Mobile App Examples](#mobile-app-examples)

## Authentication & Public APIs

### User Registration
**Endpoint:** `POST /api/public/register`

**Request Body:**
```json
{
  "username": "john_doe",
  "email": "john@example.com",
  "password": "SecurePass123",
  "full_name": "John Doe",
  "company": "Tech Corp",
  "phone": "+1-555-0123"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Registration successful",
  "user": {
    "id": 1,
    "username": "john_doe",
    "email": "john@example.com",
    "full_name": "John Doe",
    "company": "Tech Corp",
    "created_at": "2024-01-20T14:30:00Z"
  }
}
```

### User Login
**Endpoint:** `POST /api/public/login`

**Request Body:**
```json
{
  "username": "john_doe",
  "password": "SecurePass123",
  "remember_me": false
}
```

**Response:**
```json
{
  "success": true,
  "message": "Login successful",
  "user": {
    "id": 1,
    "username": "john_doe",
    "email": "john@example.com",
    "full_name": "John Doe",
    "is_admin": false,
    "last_login": "2024-01-20T14:30:00Z"
  }
}
```

### Password Reset Flow

#### Initiate Password Reset
**Endpoint:** `POST /api/public/forgot-password`

**Request Body:**
```json
{
  "email": "john@example.com"
}
```

#### Reset Password with Token
**Endpoint:** `POST /api/public/reset-password`

**Request Body:**
```json
{
  "token": "reset_token_here",
  "new_password": "NewSecurePass123"
}
```

### Validation APIs

#### Check Username Availability
**Endpoint:** `POST /api/public/check-username`

**Request Body:**
```json
{
  "username": "desired_username"
}
```

**Response:**
```json
{
  "success": true,
  "available": true,
  "username": "desired_username"
}
```

#### Validate Subdomain
**Endpoint:** `POST /api/public/validate-subdomain`

**Request Body:**
```json
{
  "subdomain": "mycompany"
}
```

**Response:**
```json
{
  "success": true,
  "available": true,
  "valid": true,
  "subdomain": "mycompany"
}
```

## User Profile Management

### Get Complete Profile
**Endpoint:** `GET /api/user/profile`

**Response:**
```json
{
  "success": true,
  "user": {
    "id": 1,
    "username": "john_doe",
    "email": "john@example.com",
    "full_name": "John Doe",
    "bio": "Software Developer",
    "company": "Tech Corp",
    "location": "San Francisco, CA",
    "website": "https://johndoe.com",
    "phone": "+1-555-0123",
    "timezone": "America/Los_Angeles",
    "language": "en",
    "profile_picture_url": "/static/uploads/profiles/avatar.jpg",
    "avatar_initials": "JD",
    "is_active": true,
    "created_at": "2024-01-15T10:30:00Z",
    "last_login": "2024-01-20T14:25:00Z",
    "notification_preferences": {
      "email": true,
      "sms": false,
      "push_notifications": true,
      "marketing_emails": false
    },
    "two_factor_enabled": false,
    "last_password_change": "2024-01-15T10:30:00Z"
  }
}
```

### Avatar Management

#### Upload Avatar
**Endpoint:** `POST /api/user/avatar`

**Request:** Multipart form data with file field named 'file'

#### Delete Avatar
**Endpoint:** `DELETE /api/user/avatar`

### Security Settings
**Endpoint:** `GET /api/user/security`

**Response:**
```json
{
  "success": true,
  "security": {
    "two_factor_enabled": false,
    "last_password_change": "2024-01-15T10:30:00Z",
    "failed_login_attempts": 0,
    "account_locked": false,
    "public_keys_count": 2,
    "public_keys": [
      {
        "id": 1,
        "name": "Work Laptop",
        "fingerprint": "SHA256:abc123...",
        "created_at": "2024-01-15T10:30:00Z",
        "last_used": "2024-01-20T09:15:00Z"
      }
    ],
    "login_history": [
      {
        "timestamp": "2024-01-20T14:25:00Z",
        "ip_address": "192.168.1.100",
        "user_agent": "Mobile App iOS",
        "success": true
      }
    ]
  }
}
```

## Tenant Management

### Create New Tenant
**Endpoint:** `POST /api/tenant/create`

**Request Body:**
```json
{
  "name": "My Company",
  "subdomain": "mycompany",
  "plan": "basic",
  "admin_username": "admin",
  "admin_password": "SecureAdminPass123",
  "modules": ["crm", "sales", "inventory"],
  "metadata": {
    "industry": "Technology",
    "company_size": "10-50"
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "Tenant created successfully",
  "tenant": {
    "id": 1,
    "name": "My Company",
    "subdomain": "mycompany",
    "database_name": "mycompany_db",
    "status": "created",
    "plan": "basic",
    "admin_username": "admin",
    "admin_password": "SecureAdminPass123",
    "url": "https://mycompany.yourdomain.com",
    "created_at": "2024-01-20T14:30:00Z",
    "role": "owner"
  }
}
```

### Get Tenant Status
**Endpoint:** `GET /api/tenant/{tenant_id}/status`

**Response:**
```json
{
  "success": true,
  "status": {
    "tenant_id": 1,
    "name": "My Company",
    "subdomain": "mycompany",
    "status": "active",
    "is_active": true,
    "health_status": "healthy",
    "database_status": "connected",
    "storage_used": 256,
    "storage_limit": 5120,
    "user_count": 5,
    "max_users": 10,
    "url": "https://mycompany.yourdomain.com",
    "last_activity": "2024-01-20T13:45:00Z",
    "uptime": "99.9%",
    "response_time": "120ms"
  }
}
```

### Tenant User Management

#### Invite User to Tenant
**Endpoint:** `POST /api/tenant/{tenant_id}/invite-user`

**Request Body:**
```json
{
  "email": "user@example.com",
  "role": "manager",
  "access_level": "admin"
}
```

#### Get Tenant Users
**Endpoint:** `GET /api/tenant/{tenant_id}/users`

### Backup Management
**Endpoint:** `POST /api/tenant/{tenant_id}/backup`

**Response:**
```json
{
  "success": true,
  "message": "Backup created successfully",
  "backup_info": {
    "tenant_id": 1,
    "created_at": "2024-01-20T14:30:00Z",
    "status": "completed",
    "size": "45.2MB",
    "backup_id": "backup_20240120_143000"
  }
}
```

## Billing & Subscriptions

### Get Available Plans
**Endpoint:** `GET /api/billing/plans`

**Response:**
```json
{
  "success": true,
  "plans": {
    "free": {
      "name": "Free Plan",
      "price": 0.00,
      "billing_cycle": "monthly",
      "max_users": 3,
      "storage_limit": 1024,
      "features": [
        "Basic CRM functionality",
        "Email support",
        "Basic reporting"
      ],
      "limitations": [
        "Limited to 3 users",
        "1GB storage"
      ]
    },
    "basic": {
      "name": "Basic Plan",
      "price": 29.99,
      "billing_cycle": "monthly",
      "max_users": 10,
      "storage_limit": 5120,
      "features": [
        "Full CRM functionality",
        "Email & chat support",
        "Advanced reporting",
        "API access"
      ]
    }
  }
}
```

### Get Tenant Billing Info
**Endpoint:** `GET /api/billing/tenant/{tenant_id}`

**Response:**
```json
{
  "success": true,
  "billing_info": {
    "tenant_id": 1,
    "tenant_name": "My Company",
    "current_plan": {
      "id": "basic",
      "name": "Basic Plan",
      "price": 29.99,
      "billing_cycle": "monthly"
    },
    "usage": {
      "current_users": 5,
      "max_users": 10,
      "storage_used": 256,
      "storage_limit": 5120,
      "usage_percentage": {
        "users": 50,
        "storage": 5
      }
    },
    "billing": {
      "status": "active",
      "next_billing_date": "2024-02-20T00:00:00Z",
      "days_until_billing": 15,
      "last_payment_date": "2024-01-20T00:00:00Z",
      "payment_method": {
        "type": "card",
        "last4": "4242",
        "brand": "visa"
      }
    },
    "features": ["Full CRM functionality", "Email & chat support"],
    "limitations": ["Limited to 10 users", "5GB storage"]
  }
}
```

### Upgrade Plan
**Endpoint:** `POST /api/billing/tenant/{tenant_id}/upgrade`

**Request Body:**
```json
{
  "plan_id": "professional"
}
```

### Calculate Billing Cost
**Endpoint:** `POST /api/billing/calculate`

**Request Body:**
```json
{
  "plan_id": "basic",
  "billing_cycle": "annual",
  "additional_users": 5,
  "additional_storage": 10
}
```

**Response:**
```json
{
  "success": true,
  "calculation": {
    "plan_id": "basic",
    "plan_name": "Basic Plan",
    "base_price": 29.99,
    "additional_users": 5,
    "user_cost": 25.00,
    "additional_storage": 10,
    "storage_cost": 20.00,
    "subtotal": 74.99,
    "discount": 14.99,
    "tax_rate": 0.10,
    "tax_amount": 6.00,
    "total": 66.00,
    "billing_cycle": "annual",
    "annual_total": 792.00,
    "currency": "USD"
  }
}
```

### Payment Methods
**Endpoint:** `GET /api/billing/payment-methods`

### Billing History
**Endpoint:** `GET /api/billing/invoices`

## Support & Communication

### Create Support Ticket
**Endpoint:** `POST /api/support/tickets`

**Request Body:**
```json
{
  "subject": "Unable to access tenant dashboard",
  "description": "I'm getting a 500 error when trying to access my tenant dashboard. This started happening this morning.",
  "category": "technical",
  "priority": "high",
  "tenant_id": 1,
  "metadata": {
    "browser": "Safari",
    "os": "iOS 17.2",
    "app_version": "1.2.0"
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "Support ticket created successfully",
  "ticket": {
    "id": 1,
    "ticket_number": "TK-20240120-ABC123",
    "subject": "Unable to access tenant dashboard",
    "description": "I'm getting a 500 error...",
    "category": "technical",
    "priority": "high",
    "status": "open",
    "assigned_to": null,
    "created_at": "2024-01-20T14:30:00Z",
    "tenant_id": 1,
    "message_count": 0
  }
}
```

### Get Support Tickets
**Endpoint:** `GET /api/support/tickets`

**Query Parameters:**
- `page` (int): Page number
- `per_page` (int): Items per page
- `status` (string): Filter by status
- `category` (string): Filter by category

### Get Specific Ticket
**Endpoint:** `GET /api/support/tickets/{ticket_id}`

**Response:**
```json
{
  "success": true,
  "ticket": {
    "id": 1,
    "ticket_number": "TK-20240120-ABC123",
    "subject": "Unable to access tenant dashboard",
    "status": "in_progress",
    "assigned_to": "support_agent_1",
    "created_at": "2024-01-20T14:30:00Z",
    "updated_at": "2024-01-20T15:45:00Z",
    "messages": [
      {
        "id": 1,
        "message": "I'm getting a 500 error when trying to access my tenant dashboard.",
        "is_from_support": false,
        "created_at": "2024-01-20T14:30:00Z",
        "attachments": []
      },
      {
        "id": 2,
        "message": "Thank you for contacting support. I'm looking into this issue now.",
        "is_from_support": true,
        "created_at": "2024-01-20T15:45:00Z",
        "attachments": []
      }
    ]
  }
}
```

### Add Message to Ticket
**Endpoint:** `POST /api/support/tickets/{ticket_id}/messages`

**Request Body:**
```json
{
  "message": "I tried clearing my browser cache as suggested, but the issue persists.",
  "attachments": [
    "/uploads/screenshot_error.png"
  ]
}
```

### Support System Info

#### Get Categories
**Endpoint:** `GET /api/support/categories`

#### Get Priorities
**Endpoint:** `GET /api/support/priorities`

#### Check Chat Availability
**Endpoint:** `GET /api/support/chat/available`

**Response:**
```json
{
  "success": true,
  "available": true,
  "message": "Live chat is available during business hours (9 AM - 5 PM UTC)",
  "business_hours": {
    "start": "09:00 UTC",
    "end": "17:00 UTC",
    "timezone": "UTC"
  }
}
```

#### Knowledge Base
**Endpoint:** `GET /api/support/knowledge-base`

**Query Parameters:**
- `search` (string): Search query
- `category` (string): Filter by category

## Notifications & Real-time Updates

### Get Notifications
**Endpoint:** `GET /api/user/notifications`

**Query Parameters:**
- `page` (int): Page number
- `per_page` (int): Items per page
- `include_read` (bool): Include read notifications
- `include_dismissed` (bool): Include dismissed notifications

**Response:**
```json
{
  "success": true,
  "notifications": [
    {
      "id": 1,
      "title": "Tenant Created Successfully",
      "message": "Your tenant 'My Company' has been created and is ready to use.",
      "type": "success",
      "priority": "medium",
      "is_read": false,
      "is_dismissed": false,
      "created_at": "2024-01-20T14:30:00Z",
      "action_url": "/tenant/1/manage",
      "action_label": "Access Tenant",
      "metadata": {
        "tenant_id": 1,
        "tenant_name": "My Company"
      }
    },
    {
      "id": 2,
      "title": "Payment Due Soon",
      "message": "Your subscription for 'My Company' will renew in 3 days.",
      "type": "billing_update",
      "priority": "high",
      "is_read": false,
      "action_url": "/billing/tenant/1",
      "action_label": "View Billing",
      "created_at": "2024-01-20T10:00:00Z"
    },
    {
      "id": 3,
      "title": "Support Reply",
      "message": "Our support team has replied to your ticket TK-20240120-ABC123.",
      "type": "info",
      "priority": "medium",
      "is_read": true,
      "action_url": "/support/ticket/1",
      "action_label": "View Ticket",
      "created_at": "2024-01-20T08:30:00Z"
    }
  ],
  "counts": {
    "total": 15,
    "unread": 8,
    "urgent": 2
  },
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 15
  }
}
```

### Notification Management

#### Mark as Read
**Endpoint:** `POST /api/user/notifications/{notification_id}/read`

#### Dismiss Notification
**Endpoint:** `POST /api/user/notifications/{notification_id}/dismiss`

#### Mark All as Read
**Endpoint:** `POST /api/user/notifications/mark-all-read`

#### Get Counts
**Endpoint:** `GET /api/user/notifications/counts`

## WebSocket Events

### Connection Events
```javascript
// Connect to WebSocket
const socket = io();

// Listen for connection confirmation
socket.on('connected', (data) => {
  console.log('Connected:', data);
});

// Listen for new notifications
socket.on('new_notification', (notification) => {
  showNotification(notification);
  updateNotificationBadge();
});
```

### Notification Events
```javascript
// Mark notification as read via WebSocket
socket.emit('mark_notification_read', {
  notification_id: 123
});

// Listen for notification updates
socket.on('notification_read', (data) => {
  updateNotificationUI(data.notification_id);
});

// Get real-time notification counts
socket.emit('get_notification_counts');
socket.on('notification_counts', (counts) => {
  updateBadge(counts.unread);
});
```

### Tenant Events
```javascript
// Subscribe to tenant updates
socket.emit('subscribe_tenant_updates', {
  tenant_id: 1
});

// Listen for tenant status changes
socket.on('tenant_status_changed', (data) => {
  if (data.tenant.status === 'suspended') {
    showAlert('Tenant suspended: ' + data.message);
  }
});

// Listen for billing alerts
socket.on('billing_alert', (data) => {
  if (data.type === 'payment_overdue') {
    showUrgentAlert('Payment overdue!');
  }
});
```

## Error Handling

### Standard Error Response
```json
{
  "success": false,
  "error": "Error message",
  "error_code": "VALIDATION_ERROR",
  "details": {
    "field": "email",
    "message": "Invalid email format"
  },
  "timestamp": "2024-01-20T14:30:00Z"
}
```

### HTTP Status Codes
| Status | Code | Description |
|--------|------|-------------|
| 200 | OK | Success |
| 201 | CREATED | Resource created |
| 400 | BAD_REQUEST | Invalid request |
| 401 | UNAUTHORIZED | Authentication required |
| 403 | FORBIDDEN | Access denied |
| 404 | NOT_FOUND | Resource not found |
| 409 | CONFLICT | Resource conflict |
| 422 | UNPROCESSABLE_ENTITY | Validation error |
| 423 | LOCKED | Account locked |
| 429 | TOO_MANY_REQUESTS | Rate limited |
| 500 | INTERNAL_SERVER_ERROR | Server error |

## Mobile App Examples

### React Native Implementation

#### Authentication Service
```javascript
class AuthService {
  constructor() {
    this.baseURL = 'https://your-api-domain.com';
    this.token = null;
  }

  async register(userData) {
    const response = await fetch(`${this.baseURL}/api/public/register`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(userData)
    });
    
    const data = await response.json();
    if (!data.success) {
      throw new Error(data.error);
    }
    
    return data.user;
  }

  async login(credentials) {
    const response = await fetch(`${this.baseURL}/api/public/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify(credentials)
    });
    
    const data = await response.json();
    if (!data.success) {
      throw new Error(data.error);
    }
    
    // Store user data
    await AsyncStorage.setItem('user', JSON.stringify(data.user));
    return data.user;
  }

  async checkAuth() {
    const response = await fetch(`${this.baseURL}/api/public/check-auth`, {
      credentials: 'include'
    });
    
    const data = await response.json();
    return data.authenticated ? data.user : null;
  }
}
```

#### Tenant Management Service
```javascript
class TenantService {
  constructor() {
    this.baseURL = 'https://your-api-domain.com';
  }

  async createTenant(tenantData) {
    const response = await fetch(`${this.baseURL}/api/tenant/create`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify(tenantData)
    });
    
    const data = await response.json();
    if (!data.success) {
      throw new Error(data.error);
    }
    
    return data.tenant;
  }

  async getTenants() {
    const response = await fetch(`${this.baseURL}/api/user/tenants`, {
      credentials: 'include'
    });
    
    const data = await response.json();
    if (!data.success) {
      throw new Error(data.error);
    }
    
    return data.tenants;
  }

  async getTenantStatus(tenantId) {
    const response = await fetch(`${this.baseURL}/api/tenant/${tenantId}/status`, {
      credentials: 'include'
    });
    
    const data = await response.json();
    if (!data.success) {
      throw new Error(data.error);
    }
    
    return data.status;
  }
}
```

#### Notification Service with WebSocket
```javascript
class NotificationService {
  constructor() {
    this.baseURL = 'https://your-api-domain.com';
    this.socket = null;
    this.listeners = new Map();
  }

  async connect() {
    this.socket = io(this.baseURL, {
      transports: ['websocket']
    });
    
    this.socket.on('connect', () => {
      console.log('Connected to notification service');
    });
    
    this.socket.on('new_notification', (notification) => {
      this.handleNewNotification(notification);
    });
    
    this.socket.on('notification_counts', (counts) => {
      this.emit('counts_updated', counts);
    });
  }

  async getNotifications(page = 1) {
    const response = await fetch(
      `${this.baseURL}/api/user/notifications?page=${page}&per_page=20`,
      { credentials: 'include' }
    );
    
    const data = await response.json();
    if (!data.success) {
      throw new Error(data.error);
    }
    
    return data;
  }

  async markAsRead(notificationId) {
    // Use WebSocket for real-time update
    if (this.socket) {
      this.socket.emit('mark_notification_read', {
        notification_id: notificationId
      });
    }
    
    // Also make HTTP request as fallback
    const response = await fetch(
      `${this.baseURL}/api/user/notifications/${notificationId}/read`,
      {
        method: 'POST',
        credentials: 'include'
      }
    );
    
    return response.json();
  }

  handleNewNotification(notification) {
    // Show push notification
    if (notification.priority === 'urgent') {
      this.showPushNotification(notification);
    }
    
    // Update UI
    this.emit('new_notification', notification);
  }

  showPushNotification(notification) {
    // Implementation depends on your push notification service
    // (Firebase, OneSignal, etc.)
  }

  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    this.listeners.get(event).push(callback);
  }

  emit(event, data) {
    const callbacks = this.listeners.get(event) || [];
    callbacks.forEach(callback => callback(data));
  }
}
```

#### Usage in React Native Component
```javascript
import React, { useState, useEffect } from 'react';
import { View, Text, FlatList, TouchableOpacity, Alert } from 'react-native';

const NotificationsScreen = () => {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [counts, setCounts] = useState({ total: 0, unread: 0 });

  useEffect(() => {
    loadNotifications();
    
    // Listen for real-time updates
    NotificationService.on('new_notification', (notification) => {
      setNotifications(prev => [notification, ...prev]);
      updateCounts();
    });
    
    NotificationService.on('counts_updated', (newCounts) => {
      setCounts(newCounts);
    });
    
    return () => {
      // Cleanup listeners
    };
  }, []);

  const loadNotifications = async () => {
    try {
      const data = await NotificationService.getNotifications();
      setNotifications(data.notifications);
      setCounts(data.counts);
    } catch (error) {
      Alert.alert('Error', error.message);
    } finally {
      setLoading(false);
    }
  };

  const handleNotificationPress = async (notification) => {
    if (!notification.is_read) {
      await NotificationService.markAsRead(notification.id);
    }
    
    // Navigate based on action_url
    if (notification.action_url) {
      // Handle navigation
    }
  };

  const renderNotification = ({ item }) => (
    <TouchableOpacity
      style={[
        styles.notificationItem,
        !item.is_read && styles.unreadNotification
      ]}
      onPress={() => handleNotificationPress(item)}
    >
      <View style={styles.notificationHeader}>
        <Text style={styles.notificationTitle}>{item.title}</Text>
        <Text style={styles.notificationTime}>
          {formatTime(item.created_at)}
        </Text>
      </View>
      <Text style={styles.notificationMessage}>{item.message}</Text>
      {item.priority === 'urgent' && (
        <View style={styles.urgentBadge}>
          <Text style={styles.urgentText}>URGENT</Text>
        </View>
      )}
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Notifications</Text>
        <Text style={styles.headerCount}>
          {counts.unread} unread of {counts.total}
        </Text>
      </View>
      
      <FlatList
        data={notifications}
        renderItem={renderNotification}
        keyExtractor={item => item.id.toString()}
        refreshing={loading}
        onRefresh={loadNotifications}
      />
    </View>
  );
};
```

### iOS Swift Implementation

#### API Service
```swift
class APIService {
    static let shared = APIService()
    private let baseURL = "https://your-api-domain.com"
    
    func register(userData: [String: Any]) async throws -> User {
        let url = URL(string: "\(baseURL)/api/public/register")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: userData)
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 201 else {
            throw APIError.invalidResponse
        }
        
        let result = try JSONDecoder().decode(APIResponse<UserResponse>.self, from: data)
        
        if result.success {
            return result.data!.user
        } else {
            throw APIError.serverError(result.error ?? "Unknown error")
        }
    }
    
    func getTenants() async throws -> [Tenant] {
        let url = URL(string: "\(baseURL)/api/user/tenants")!
        var request = URLRequest(url: url)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let (data, _) = try await URLSession.shared.data(for: request)
        let result = try JSONDecoder().decode(TenantsResponse.self, from: data)
        
        if result.success {
            return result.tenants
        } else {
            throw APIError.serverError(result.error ?? "Failed to get tenants")
        }
    }
}
```

This comprehensive API provides complete mobile app functionality with:

✅ **Full User Registration & Authentication**
✅ **Complete Tenant Lifecycle Management**  
✅ **Comprehensive Billing & Subscription System**
✅ **Full-Featured Support System**
✅ **Smart Notification System with Real-time Updates**
✅ **WebSocket Integration for Live Features**
✅ **Mobile-Optimized Endpoints**
✅ **Complete Error Handling**
✅ **Production-Ready Examples**

Your mobile app now has complete API coverage for ALL website features!