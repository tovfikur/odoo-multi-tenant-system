# 🚀 SaaS Controller - Installation Guide

## Quick Installation

### Method 1: Automated Installation (Recommended)

```bash
# 1. Ensure Docker containers are running
docker-compose up -d

# 2. Run the installation script
python scripts/install_saas_controller.py
```

### Method 2: Manual Installation

1. **Access Odoo Admin Panel**
   - Go to `http://localhost:8069` (or your Odoo URL)
   - Log in as admin

2. **Install the Module**
   - Navigate to **Apps** menu
   - Search for `saas_controller`
   - Click **Install**

3. **Configure Settings**
   - Go to **SaaS Controller** → **Configuration**
   - Set your preferences:
     - Max users
     - Branding options
     - Color schema
     - Feature controls
   - Click **Apply Configuration**

---

## ✅ Verification Steps

### 1. Check Module Installation
```bash
# Verify module files exist
ls -la shared_addons/saas_controller/

# Validate XML files
python scripts/validate_xml.py
```

### 2. Test Basic Functionality
- Create a new user (should respect user limits)
- Check if branding changes apply
- Verify color schema updates

### 3. API Integration Test
```bash
# Test SaaS Manager API
curl http://localhost:8000/api/tenant/demo/config
curl http://localhost:8000/api/tenant/demo/user-limit
```

---

## 🎨 Configuration Examples

### Basic Setup
```python
{
    'max_users': 10,
    'user_limit_enabled': True,
    'remove_odoo_branding': False,
    'primary_color': '#017e84'
}
```

### Professional Branding
```python
{
    'max_users': 25,
    'remove_odoo_branding': True,
    'custom_app_name': 'Business Manager',
    'custom_company_name': 'Your Company',
    'primary_color': '#2c3e50',
    'hide_poweredby': True
}
```

### Full Customization
```python
{
    'max_users': 50,
    'remove_odoo_branding': True,
    'custom_app_name': 'Enterprise Suite',
    'primary_color': '#1e3a8a',
    'secondary_color': '#3b82f6',
    'disable_apps_menu': False,
    'disable_debug_mode': True
}
```

---

## 🔧 Troubleshooting

### Common Issues

1. **Module Not Found**
   ```bash
   # Check if shared_addons is mounted
   docker-compose exec odoo_master ls -la /mnt/shared-addons/
   
   # Restart Odoo containers
   docker-compose restart odoo_master odoo_worker1 odoo_worker2
   ```

2. **Installation Fails**
   ```bash
   # Check Odoo logs
   docker-compose logs odoo_master
   
   # Validate XML syntax
   python scripts/validate_xml.py
   ```

3. **User Limits Not Working**
   - Verify `user_limit_enabled` is True
   - Check SaaS Manager API connectivity
   - Ensure tenant configuration exists

4. **Branding Not Applying**
   - Click "Apply Configuration" button
   - Clear browser cache
   - Check if custom CSS is loading

### Debug Mode
```bash
# Enable detailed logging
docker-compose logs -f saas_manager | grep saas_controller
```

---

## 📊 Features Overview

| Feature | Description | Status |
|---------|-------------|---------|
| **User Limits** | Enforce maximum users per tenant | ✅ Ready |
| **Debranding** | Remove Odoo branding elements | ✅ Ready |
| **Color Schema** | Custom color themes | ✅ Ready |
| **Feature Controls** | Hide menus, disable debug | ✅ Ready |
| **API Integration** | Sync with SaaS Manager | ✅ Ready |
| **Resource Limits** | Storage and email quotas | 🔄 Framework |

---

## 📞 Support

1. **Check Documentation**: [`SAAS_CONTROLLER_README.md`](SAAS_CONTROLLER_README.md)
2. **Run Tests**: `python scripts/test_saas_controller_complete.py`
3. **Validate XML**: `python scripts/validate_xml.py`
4. **View Logs**: `docker-compose logs saas_manager`

---

**🎯 Installation Complete!** Your SaaS Controller is ready for enterprise-grade tenant management.
