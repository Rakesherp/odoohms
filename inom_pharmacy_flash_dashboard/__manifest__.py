{
    'name': 'Inom Pharmacy Flash Dashboard',
    'version': '19.0.1.0.1',
    'category': 'Healthcare',
    'summary': 'Live pharmacy low-stock and batch-expiry flash dashboard for Inom HMS',
    'description': """
        Pharmacy Flash Dashboard for Inom Health Care System.

        Features:
        - Live Low Stock Medicines alert ticker.
        - Live Expiring / Expired Batches alert ticker.
        - One-item-at-a-time round-robin rotation instead of dense tables.
        - Visual severity colors and stock / expiry indicators.
        - Auto refresh and manual refresh.
        - Click-through to the related medicine or batch records.
    """,
    'author': 'Bytewerk',
    'website': 'https://bytewerk.odoo.com',
    'license': 'LGPL-3',
    'depends': ['inom_healthcare_system'],
    'data': [
        'security/ir.model.access.csv',
        'views/dashboard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'inom_pharmacy_flash_dashboard/static/src/css/pharmacy_flash_dashboard.css',
            'inom_pharmacy_flash_dashboard/static/src/js/pharmacy_flash_dashboard.js',
            'inom_pharmacy_flash_dashboard/static/src/xml/pharmacy_flash_dashboard.xml',
        ],
    },
    'application': True,
    'installable': True,
    'auto_install': False,
}
