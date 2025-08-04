# -*- coding: utf-8 -*-
{
    'name': 'Odoo Approval',
    'version': '17.0.1.0',
    'category': 'Approvals',
    'description': """
Odoo Approval Module: Multi level approval - create and validate approvals requests.
Each request can be approve by many levels of different managers.
The managers wil review and approve sequentially
    """,
    'summary': '''
    Create and validate approval requests. Each request can be approved by many levels of different managers
    ''',
    'author': 'Domiup',
    'price': 31,
    'currency': 'EUR',
    'license': 'OPL-1',
    'support': 'domiup.contact@gmail.com',
    'website': '',
    'depends': [
        'mail',
        'product'
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',

        # wizard
        'wizard/refused_reason_views.xml',

        'views/multi_approval_type_views.xml',
        'views/multi_approval_views.xml',

        # Add actions after all views.
        'views/actions.xml',

        # Add menu after actions.
        'views/menu.xml',
        
    ],
    'images': ['static/description/banner.jpg'],
    'test': [],
    'demo': [],
    'installable': True,
    'active': False,
    'application': True,
}
