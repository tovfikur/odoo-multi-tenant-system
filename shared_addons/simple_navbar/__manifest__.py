# -*- coding: utf-8 -*-
{
    'name': 'Simple Navbar Styling',
    'version': '17.0.1.0.0',
    'category': 'Web',
    'summary': 'Simple navbar background and font styling',
    'description': """
Simple Navbar Styling
=====================

A minimal module that changes:
* Navbar background color
* Navbar brand font to Google Caveat
    """,
    'author': 'Your Company',
    'depends': [
        'web',
    ],
    'assets': {
        'web.assets_backend': [
            'simple_navbar/static/src/css/navbar_style.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
