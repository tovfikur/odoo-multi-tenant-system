# -*- coding: utf-8 -*-
{
    'name': 'SaaS Controller',
    'version': '17.0.1.0.0',
    'category': 'Administration',
    'summary': 'Comprehensive SaaS tenant control system',
    'description': """
SaaS Controller
===============

Advanced SaaS tenant control system with comprehensive features:

Features:
---------
* User limit enforcement and management
* Complete debranding capabilities  
* Custom color schema and theming
* Tenant resource management
* Advanced configuration controls
* Integration with SaaS Manager
* Real-time monitoring and limits
* Custom branding override
* Theme customization interface
* Resource usage tracking

Controls Available:
------------------
* Maximum user limits
* Remove Odoo branding
* Custom color schemes
* Logo customization
* Company branding
* Module restrictions
* Feature toggles
* Resource quotas
    """,
    'author': 'SaaS Manager',
    'website': 'https://your-saas-domain.com',
    'depends': [
        'base',
        'web',
        'website',
        'mail',
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
        'web.assets_frontend': [
            'saas_controller/static/src/css/saas_controller.css',
            'saas_controller/static/src/js/saas_brand_enforcer.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
