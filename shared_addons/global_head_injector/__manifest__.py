{
    'name': 'Global Head Injector',
    'version': '17.0.1.0.0',
    'category': 'Base',
    'summary': 'Inject custom CSS and JS into Odoo head globally',
    'description': """
        Simple module that injects custom CSS and JS files into the head section of Odoo.
        Adds:
        - /static/css/odoo.css
        - /static/js/odoo.js
        
        No dependencies, works globally across all Odoo interfaces.
    """,
    'author': 'Custom Development',
    'website': '',
    'depends': [],
    'data': [
        'views/head_inject.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}