# User API Documentation

## Overview

This document provides comprehensive documentation for the user API endpoints and WebSocket functionality in the Odoo Multi-Tenant System. The API is designed for regular users (non-admin) and provides full CRUD operations for user management, tenant access, notifications, and real-time updates.

## Authentication

All API endpoints require authentication using Flask-Login session authentication. Users must be logged in to access any API endpoint.

### Authentication Headers

```
Cookie: session=<session-cookie>
```

### Response Format

All API responses follow a consistent format:

**Success Response:**

```json
{
  "success": true,
  "data": { ... },
  "message": "Optional success message"
}
```

**Error Response:**

```json
{
  "success": false,
  "error": "Error message",
  "details": { ... }  // Optional additional details
}
```

## User Profile Management

### Get User Profile

Get the current user's profile information.

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
    "timezone": "UTC",
    "language": "en",
    "profile_picture_url": "/static/uploads/profiles/avatar.jpg",
    "avatar_initials": "JD",
    "is_active": true,
    "created_at": "2024-01-15T10:30:00Z",
    "last_login": "2024-01-20T14:25:00Z",
    "notification_preferences": {
      "email": true,
      "sms": false
    },
    "two_factor_enabled": false,
    "last_password_change": "2024-01-15T10:30:00Z"
  }
}
```

### Update User Profile

Update the current user's profile information.

**Endpoint:** `PUT /api/user/profile`

**Request Body:**

```json
{
  "full_name": "John Smith",
  "bio": "Senior Software Developer",
  "company": "New Tech Corp",
  "location": "New York, NY",
  "website": "https://johnsmith.com",
  "phone": "+1-555-0456",
  "timezone": "America/New_York",
  "language": "en",
  "notification_preferences": {
    "email": true,
    "sms": true
  }
}
```

**Response:**

```json
{
  "success": true,
  "message": "Profile updated successfully",
  "updated_fields": ["full_name", "bio", "company", "location"]
}
```

### Change Password

Change the current user's password.

**Endpoint:** `PUT /api/user/password`

**Request Body:**

```json
{
  "current_password": "current_password_here",
  "new_password": "new_secure_password"
}
```

**Response:**

```json
{
  "success": true,
  "message": "Password changed successfully"
}
```

### Upload Avatar

Upload a profile picture for the current user.

**Endpoint:** `POST /api/user/avatar`

**Request:** Multipart form data with file field named 'file'

**Supported file types:** PNG, JPG, JPEG, GIF

**Response:**

```json
{
  "success": true,
  "message": "Avatar uploaded successfully",
  "avatar_url": "/static/uploads/profiles/1_abc123_avatar.jpg"
}
```

### Delete Avatar

Delete the current user's profile picture.

**Endpoint:** `DELETE /api/user/avatar`

**Response:**

```json
{
  "success": true,
  "message": "Avatar deleted successfully"
}
```

## Tenant Management

### Get User's Tenants

Get all tenants accessible to the current user.

**Endpoint:** `GET /api/user/tenants`

**Response:**

```json
{
  "success": true,
  "tenants": [
    {
      "id": 1,
      "name": "My Company",
      "subdomain": "mycompany",
      "database_name": "mycompany_db",
      "status": "active",
      "plan": "premium",
      "max_users": 50,
      "storage_limit": 5120,
      "is_active": true,
      "created_at": "2024-01-10T09:00:00Z",
      "updated_at": "2024-01-20T10:30:00Z",
      "last_backup_at": "2024-01-19T02:00:00Z",
      "role": "admin",
      "access_level": "admin",
      "joined_at": "2024-01-10T09:00:00Z"
    }
  ],
  "total": 1
}
```

### Get Specific Tenant

Get detailed information about a specific tenant.

**Endpoint:** `GET /api/user/tenants/{tenant_id}`

**Response:**

```json
{
  "id": 1,
  "name": "My Company",
  "subdomain": "mycompany",
  "database_name": "mycompany_db",
  "status": "active",
  "plan": "premium",
  "max_users": 50,
  "storage_limit": 5120,
  "is_active": true,
  "created_at": "2024-01-10T09:00:00Z",
  "updated_at": "2024-01-20T10:30:00Z",
  "last_backup_at": "2024-01-19T02:00:00Z",
  "my_role": "admin",
  "my_access_level": "admin",
  "my_joined_at": "2024-01-10T09:00:00Z",
  "url": "https://mycompany.yourdomain.com",
  "users": [
    {
      "id": 1,
      "username": "john_doe",
      "email": "john@example.com",
      "full_name": "John Doe",
      "role": "admin",
      "access_level": "admin",
      "joined_at": "2024-01-10T09:00:00Z",
      "is_active": true
    }
  ]
}
```

## Activity and Audit Logs

### Get User Activity

Get the current user's activity/audit logs.

**Endpoint:** `GET /api/user/activity`

**Query Parameters:**

- `page` (int, default: 1): Page number
- `per_page` (int, default: 20, max: 100): Items per page

**Response:**

```json
{
  "success": true,
  "logs": [
    {
      "id": 123,
      "action": "PROFILE_UPDATED",
      "details": {
        "updated_fields": ["full_name", "email"]
      },
      "ip_address": "192.168.1.100",
      "created_at": "2024-01-20T14:30:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 45,
    "pages": 3,
    "has_next": true,
    "has_prev": false
  }
}
```

## Security Settings

### Get Security Settings

Get the current user's security settings and status.

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
    ]
  }
}
```

## User Preferences

### Get User Preferences

Get the current user's preferences and settings.

**Endpoint:** `GET /api/user/preferences`

**Response:**

```json
{
  "success": true,
  "preferences": {
    "timezone": "America/New_York",
    "language": "en",
    "notifications": {
      "email": true,
      "sms": false
    },
    "theme": "light",
    "dashboard_layout": "default"
  }
}
```

### Update User Preferences

Update the current user's preferences and settings.

**Endpoint:** `PUT /api/user/preferences`

**Request Body:**

```json
{
  "timezone": "Europe/London",
  "language": "en",
  "notifications": {
    "email": true,
    "sms": true
  }
}
```

**Response:**

```json
{
  "success": true,
  "message": "Preferences updated successfully",
  "updated_fields": ["timezone", "language", "notifications"]
}
```

## Notifications

### Get User Notifications

Get the current user's notifications.

**Endpoint:** `GET /api/user/notifications`

**Query Parameters:**

- `page` (int, default: 1): Page number
- `per_page` (int, default: 20, max: 100): Items per page
- `include_read` (bool, default: true): Include read notifications
- `include_dismissed` (bool, default: false): Include dismissed notifications

**Response:**

```json
{
  "success": true,
  "notifications": [
    {
      "id": 1,
      "title": "New Tenant Created",
      "message": "Your tenant 'My Company' has been successfully created and is ready to use.",
      "type": "success",
      "priority": "medium",
      "is_read": false,
      "is_dismissed": false,
      "created_at": "2024-01-20T10:30:00Z",
      "read_at": null,
      "dismissed_at": null,
      "action_url": "/tenant/mycompany",
      "action_label": "Access Tenant",
      "metadata": {
        "tenant_name": "My Company",
        "tenant_subdomain": "mycompany"
      },
      "expires_at": null
    }
  ],
  "counts": {
    "total": 5,
    "unread": 3,
    "urgent": 1
  },
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 5
  }
}
```

### Get Notification Counts

Get notification counts for the current user.

**Endpoint:** `GET /api/user/notifications/counts`

**Response:**

```json
{
  "success": true,
  "counts": {
    "total": 5,
    "unread": 3,
    "urgent": 1
  }
}
```

### Mark Notification as Read

Mark a specific notification as read.

**Endpoint:** `POST /api/user/notifications/{notification_id}/read`

**Response:**

```json
{
  "success": true,
  "message": "Notification marked as read"
}
```

### Dismiss Notification

Dismiss a specific notification.

**Endpoint:** `POST /api/user/notifications/{notification_id}/dismiss`

**Response:**

```json
{
  "success": true,
  "message": "Notification dismissed"
}
```

### Mark All Notifications as Read

Mark all user's notifications as read.

**Endpoint:** `POST /api/user/notifications/mark-all-read`

**Response:**

```json
{
  "success": true,
  "message": "Marked 3 notifications as read",
  "count": 3
}
```

## Error Codes

| HTTP Status | Error Code            | Description                                     |
| ----------- | --------------------- | ----------------------------------------------- |
| 400         | BAD_REQUEST           | Invalid request data or missing required fields |
| 401         | UNAUTHORIZED          | Authentication required                         |
| 403         | FORBIDDEN             | Access denied (insufficient permissions)        |
| 404         | NOT_FOUND             | Resource not found                              |
| 409         | CONFLICT              | Resource already exists or conflict             |
| 422         | UNPROCESSABLE_ENTITY  | Validation error                                |
| 429         | TOO_MANY_REQUESTS     | Rate limit exceeded                             |
| 500         | INTERNAL_SERVER_ERROR | Server error                                    |

## Rate Limiting

API endpoints are rate-limited to prevent abuse:

- General endpoints: 100 requests per minute per user
- Authentication endpoints: 10 requests per minute per IP
- File upload endpoints: 10 requests per minute per user

## Pagination

List endpoints support pagination with the following parameters:

- `page`: Page number (starts from 1)
- `per_page`: Items per page (max 100)

Pagination response includes:

```json
{
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 150,
    "pages": 8,
    "has_next": true,
    "has_prev": false
  }
}
```

## Content Types

**Request Content-Type:**

- JSON endpoints: `application/json`
- File upload endpoints: `multipart/form-data`

**Response Content-Type:**

- All endpoints: `application/json`

## Example Usage

### JavaScript/Fetch Example

```javascript
// Get user profile
const response = await fetch("/api/user/profile", {
  method: "GET",
  credentials: "include", // Include session cookie
  headers: {
    "Content-Type": "application/json",
  },
});

const data = await response.json();
if (data.success) {
  console.log("User profile:", data.user);
} else {
  console.error("Error:", data.error);
}

// Update user profile
const updateResponse = await fetch("/api/user/profile", {
  method: "PUT",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    full_name: "John Smith",
    bio: "Senior Developer",
  }),
});

const updateData = await updateResponse.json();
console.log(
  updateData.success ? "Profile updated!" : "Error: " + updateData.error
);
```

### cURL Examples

```bash
# Get user profile
curl -X GET "http://localhost:5000/api/user/profile" \
  -H "Content-Type: application/json" \
  --cookie "session=your_session_cookie"

# Update user profile
curl -X PUT "http://localhost:5000/api/user/profile" \
  -H "Content-Type: application/json" \
  --cookie "session=your_session_cookie" \
  -d '{"full_name": "John Smith", "bio": "Senior Developer"}'

# Upload avatar
curl -X POST "http://localhost:5000/api/user/avatar" \
  --cookie "session=your_session_cookie" \
  -F "file=@avatar.jpg"

# Get notifications
curl -X GET "http://localhost:5000/api/user/notifications?page=1&per_page=10" \
  -H "Content-Type: application/json" \
  --cookie "session=your_session_cookie"
```
