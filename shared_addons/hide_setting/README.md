# Hide Settings Module

## Overview

This Odoo module provides the functionality to hide the Settings menu from the user interface when activated, while keeping settings accessible through API calls.

## Features

- **UI/UX Control**: Hide settings menu from the Odoo interface
- **API Access**: Settings remain fully accessible through API calls
- **Security**: Only system administrators can toggle this setting
- **Real-time**: Changes take effect immediately without requiring restart
- **Flexible**: Can be enabled/disabled as needed

## Installation

1. Copy the `hide_setting` folder to your Odoo addons directory
2. Update the apps list in Odoo
3. Install the "Hide Settings" module

## Usage

### Through UI (before hiding):
1. Go to Settings → General Settings
2. Find "UI Security" section
3. Enable "Hide Settings from UI"
4. Save the configuration

### Through API:

#### Check current status:
```python
# XML-RPC example
import xmlrpc.client

url = 'http://your-odoo-instance'
db = 'your-database'
username = 'your-username'
password = 'your-password'

common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
uid = common.authenticate(db, username, password, {})

models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
result = models.execute_kw(db, uid, password, 'hide.setting.config', 'get_hide_setting_status', [])
```

#### Toggle setting:
```python
# Enable hiding
result = models.execute_kw(db, uid, password, 'hide.setting.config', 'toggle_hide_setting', [True])

# Disable hiding  
result = models.execute_kw(db, uid, password, 'hide.setting.config', 'toggle_hide_setting', [False])
```

#### Using HTTP API:
```bash
# Check status
curl -X POST \
  http://your-odoo-instance/web/dataset/call_kw/hide.setting.config/get_hide_setting_status \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "method": "call",
    "params": {
      "model": "hide.setting.config",
      "method": "get_hide_setting_status", 
      "args": [],
      "kwargs": {}
    }
  }'

# Toggle setting
curl -X POST \
  http://your-odoo-instance/web/dataset/call_kw/hide.setting.config/toggle_hide_setting \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "method": "call",
    "params": {
      "model": "hide.setting.config",
      "method": "toggle_hide_setting",
      "args": [true],
      "kwargs": {}
    }
  }'
```

## Security

- Only users in the "Administration / Settings" group can modify the hide setting
- Regular users can only read the current status
- The setting change is logged with timestamp and user information

## Technical Details

### Models:
- `hide.setting.config`: Main configuration model
- `res.config.settings`: Extended to include the hide setting option

### JavaScript:
- Frontend service that dynamically hides/shows settings menu
- CSS-based hiding for maximum compatibility
- Periodic checks to maintain state consistency

### API Methods:
- `get_hide_setting_status()`: Returns current configuration
- `toggle_hide_setting(is_active)`: Changes the setting
- `is_settings_hidden()`: Simple boolean check

## Compatibility

- Odoo 15.0+
- Works with both Community and Enterprise editions
- Compatible with custom themes and modules

## Troubleshooting

If settings remain visible after enabling:
1. Refresh the browser page
2. Clear browser cache
3. Check user permissions
4. Verify module installation

## Support

For issues or feature requests, please contact your system administrator.