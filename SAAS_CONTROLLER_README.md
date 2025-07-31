# SaaS Controller - Complete Tenant Management System

The **SaaS Controller** is an advanced replacement for the `saas_user_limit` module, providing comprehensive tenant management capabilities including user limits, debranding, color customization, and feature controls.

## 🚀 Features

### User Management
- **User Limit Enforcement**: Set maximum users per tenant with real-time validation
- **User Type Control**: Differentiate between internal and portal users
- **Real-time Monitoring**: Track current vs maximum users
- **API Integration**: Sync limits with SaaS Manager

### Branding & Customization
- **Complete Debranding**: Remove all Odoo branding elements
- **Custom App Names**: Replace "Odoo" with your brand name
- **Logo Customization**: Upload custom logos and favicons
- **Login Page Customization**: Add custom messages and branding

### Color Schema & Theming
- **Full Color Control**: Customize primary, secondary, and accent colors
- **Real-time Application**: Changes apply immediately across the system
- **CSS Variable System**: Modern CSS custom properties for consistent theming
- **Responsive Design**: Works on all device sizes

### Feature Controls
- **Menu Restrictions**: Hide apps menu, settings menu
- **Debug Mode Control**: Disable debug mode for security
- **Module Restrictions**: Control which modules can be installed
- **Resource Limits**: Set storage and email sending limits

## 📁 Module Structure

```
shared_addons/saas_controller/
├── __manifest__.py              # Module configuration
├── __init__.py                  # Module initialization
├── models/
│   ├── __init__.py
│   ├── saas_controller.py       # Main controller model
│   ├── res_users.py             # User limit enforcement
│   ├── res_company.py           # Company branding integration
│   └── ir_ui_view.py            # View customizations
├── views/
│   ├── saas_controller_views.xml # Main configuration interface
│   ├── res_users_views.xml      # User management enhancements
│   └── branding_views.xml       # Branding templates
├── security/
│   └── ir.model.access.csv      # Access permissions
├── data/
│   └── default_config.xml       # Default configuration
└── static/src/css/
    └── saas_controller.css      # Custom styling
```

## 🔧 Installation

### 1. Automatic Installation (Recommended)

```bash
# Run the installation script
python scripts/install_saas_controller.py
```

### 2. Manual Installation

1. **Start your Docker environment**:
   ```bash
   docker-compose up -d
   ```

2. **Access Odoo** at http://localhost:8069

3. **Install the module**:
   - Go to Apps menu
   - Search for "SaaS Controller"
   - Click "Install"

4. **Configure settings**:
   - Go to SaaS Controller > Configuration
   - Set your preferences
   - Click "Apply Configuration"

## ⚙️ Configuration

### User Limits

```python
# Example configuration
{
    'user_limit_enabled': True,
    'max_users': 25,
    'current_users': 12,  # Automatically calculated
}
```

### Branding Settings

```python
{
    'remove_odoo_branding': True,
    'custom_app_name': 'MyBusiness Manager',
    'custom_company_name': 'My Company Inc.',
    'hide_poweredby': True,
}
```

### Color Schema

```python
{
    'primary_color': '#2c3e50',      # Main brand color
    'secondary_color': '#34495e',    # Secondary elements
    'accent_color': '#e74c3c',       # Highlights and accents
    'background_color': '#ffffff',   # Main background
    'text_color': '#2c3e50',         # Primary text
    'link_color': '#3498db',         # Links
}
```

## 🔗 API Integration

### SaaS Manager Endpoints

The module integrates with SaaS Manager through these API endpoints:

#### Get Tenant Configuration
```
GET /api/tenant/{subdomain}/config
```

Response:
```json
{
    "success": true,
    "max_users": 25,
    "user_limit_enabled": true,
    "remove_branding": true,
    "primary_color": "#2c3e50",
    "secondary_color": "#34495e",
    "custom_app_name": "Business Manager"
}
```

#### Get User Limits
```
GET /api/tenant/{subdomain}/user-limit
```

Response:
```json
{
    "success": true,
    "max_users": 25,
    "current_users": 12,
    "remaining_users": 13,
    "tenant_status": "active"
}
```

## 🎨 Customization Examples

### 1. Corporate Blue Theme
```python
config = {
    'primary_color': '#1e3a8a',      # Corporate blue
    'secondary_color': '#3b82f6',    # Light blue
    'accent_color': '#60a5fa',       # Accent blue
    'background_color': '#f8fafc',   # Light gray
    'text_color': '#1e293b',         # Dark gray
    'link_color': '#2563eb',         # Blue links
}
```

### 2. Modern Dark Theme
```python
config = {
    'primary_color': '#1f2937',      # Dark gray
    'secondary_color': '#374151',    # Medium gray
    'accent_color': '#10b981',       # Green accent
    'background_color': '#111827',   # Very dark
    'text_color': '#f9fafb',         # Light text
    'link_color': '#34d399',         # Green links
}
```

### 3. Professional Green
```python
config = {
    'primary_color': '#059669',      # Professional green
    'secondary_color': '#10b981',    # Light green
    'accent_color': '#34d399',       # Accent green
    'background_color': '#ffffff',   # White
    'text_color': '#1f2937',         # Dark gray
    'link_color': '#047857',         # Deep green
}
```

## 🧪 Testing

### Run Tests
```bash
# Test SaaS Manager API integration
python scripts/test_saas_controller.py

# Test Odoo functionality manually through the interface
```

### Manual Testing Checklist

1. **User Limits**:
   - [ ] Create users up to the limit
   - [ ] Verify limit enforcement
   - [ ] Test portal vs internal users

2. **Branding**:
   - [ ] Enable debranding
   - [ ] Upload custom logo
   - [ ] Verify "Powered by" removal

3. **Colors**:
   - [ ] Change primary color
   - [ ] Apply configuration
   - [ ] Verify UI updates

4. **Features**:
   - [ ] Hide apps menu
   - [ ] Disable debug mode
   - [ ] Test menu restrictions

## 🔒 Security Features

- **User Validation**: Prevents bypassing user limits through API or UI
- **Debug Mode Control**: Can disable debug mode for production security
- **Menu Restrictions**: Hide sensitive menus from non-admin users
- **Resource Limits**: Enforce storage and email sending quotas

## 🚨 Troubleshooting

### Common Issues

1. **Module Not Found**:
   - Ensure `/shared_addons` is mounted in Docker
   - Check module is in correct directory
   - Restart Odoo containers

2. **User Limits Not Working**:
   - Verify `user_limit_enabled` is True
   - Check SaaS Manager API connectivity
   - Review user count calculation

3. **Colors Not Applying**:
   - Click "Apply Configuration" button
   - Clear browser cache
   - Check CSS is loading

4. **Branding Still Visible**:
   - Ensure `remove_odoo_branding` is True
   - Apply configuration
   - Check custom CSS injection

### Debug Mode

Enable logging for troubleshooting:
```python
import logging
logging.getLogger('odoo.addons.saas_controller').setLevel(logging.DEBUG)
```

## 🔄 Migration from saas_user_limit

The SaaS Controller automatically replaces `saas_user_limit`. To migrate:

1. **Backup your data**
2. **Uninstall** `saas_user_limit` module
3. **Install** `saas_controller` module
4. **Configure** new settings in SaaS Controller interface

The module will automatically import existing user limit configurations.

## 📞 Support

For issues or questions:
1. Check the troubleshooting section above
2. Review logs in `/saas_manager/logs/`
3. Test API endpoints with the provided scripts
4. Verify Docker container health

## 🔄 Updates

The module includes automatic sync with SaaS Manager every hour. Manual sync is available through the "Sync with SaaS Manager" button in the configuration interface.

---

**SaaS Controller** provides enterprise-grade tenant management for your Odoo multi-tenant system with complete control over branding, limits, and features.
