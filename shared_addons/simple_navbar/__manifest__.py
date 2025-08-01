{
    'name': 'Navbar Style Customization',
    'version': '17.0.1.0.0',
    'category': 'Web',
    'summary': 'Customize navbar brand font and background color',
    'description': """
        This module customizes the Odoo navbar styling:
        - Changes the navbar brand font to Google Caveat
        - Updates the navbar background color
        
        Simple CSS-only customization that doesn't interfere with Odoo's functionality.
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['web'],
    'data': [
        'views/assets.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'navbar_style/static/src/css/navbar_style.css',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
}