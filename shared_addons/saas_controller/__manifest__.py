# -*- coding: utf-8 -*-
{
    'name': 'SaaS Controller - Minimal',
    'version': '17.0.1.0.0',
    'category': 'Administration',
    'summary': 'Minimal SaaS tenant control with icon replacement',
    'description': """
SaaS Controller - Minimal
=========================

Minimal SaaS tenant control system that doesn't break Odoo's design:

Features:
---------
* User limit enforcement
* Icon replacement (oi-apps → fa-brain)
* Minimal debranding (non-invasive)
* Tenant configuration management
* SaaS Manager integration

Key Benefits:
-------------
* Non-invasive approach
* Preserves Odoo's core design
* Minimal CSS/JS footprint
* Safe icon replacement
* Clean debranding implementation
    """,
    'author': 'SaaS Manager',
    'website': 'https://your-saas-domain.com',
    'depends': [
        'base',
        'web',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/saas_controller_views.xml',
        'views/res_users_views.xml',
        'views/branding_views.xml',
        'data/default_config.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'saas_controller/static/src/css/saas_controller.css',
            'saas_controller/static/src/js/saas_brand_enforcer.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
