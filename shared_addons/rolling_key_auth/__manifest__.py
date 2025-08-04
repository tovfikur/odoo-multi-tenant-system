{
    'name': 'Rolling Key Authentication',
    'version': '1.0.0',
    'category': 'Authentication',
    'summary': 'Authentication using rolling keys without CSRF and passwords',
    'description': '''
        This module provides authentication using a rolling key system.
        Keys are generated using a seeded algorithm and can only be used once.
    ''',
    'author': 'Your Company',
    'depends': ['base', 'web'],
    'data': [
        'views/login_template.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
