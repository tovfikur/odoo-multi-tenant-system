# -*- coding: utf-8 -*-
{
    'name': 'SaaS User Limit Enforcer',
    'version': '17.0.1.0.0',
    'category': 'Administration',
    'summary': 'Enforce user limits for SaaS tenants',
    'description': """
SaaS User Limit Enforcer
========================

This module enforces user limits for SaaS tenants by:
- Checking user count before creating new users
- Preventing user creation when limit is reached
- Providing API endpoints to check/update user limits
- Integrating with SaaS Manager user limits

Features:
---------
* Automatic user limit enforcement
* Integration with SaaS Manager
* Real-time user count validation
* Admin override capabilities
* User limit management interface
    """,
    'author': 'SaaS Manager',
    'website': 'https://your-saas-domain.com',
    'depends': [
        'base',
        'web',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/saas_config_views.xml',
        'views/res_users_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
