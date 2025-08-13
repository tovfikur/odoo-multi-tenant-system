{
    'name': 'Hide Settings',
    'version': '1.0.0',
    'summary': 'Hide Odoo Settings from UI when activated',
    'description': """
Hide Settings Module
===================

This module provides functionality to hide the Odoo Settings menu from the user interface
when the 'hide_setting' option is activated. When enabled:

- Settings menu becomes invisible in the UI/UX
- Settings remain accessible through API calls
- Only system administrators can toggle this setting
- Enhances security by limiting UI access to sensitive configurations

Features:
- Simple on/off toggle for hiding settings
- API-only access when enabled
- User group-based permissions
- Clean UI without settings menu clutter
    """,
    'author': 'Your Company',
    'website': 'https://yourcompany.com',
    'category': 'Administration',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/hide_setting_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hide_setting/static/src/js/hide_settings_menu.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}