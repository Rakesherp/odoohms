{
    'name': 'Inom Disease Master',
    'version': '19.0.1.0.0',
    'category': 'Healthcare',
    'summary': 'Disease master with ICD-10-style codes for Inom HMS',
    'description': """
        Disease Master for Inom Health Care System.

        Features:
        - Disease code and disease name master.
        - Disease category and description.
        - Active/archive support.
        - Search and category grouping.
        - Initial General Medicine disease sample data.
    """,
    'author': 'Bytewerk',
    'license': 'LGPL-3',
    'depends': ['inom_healthcare_system'],
    'data': [
        'security/ir.model.access.csv',
        'data/disease_category_data.xml',
        'data/disease_data.xml',
        'views/disease_views.xml',
        'views/patient_history_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
