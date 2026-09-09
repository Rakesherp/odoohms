{
    'name': 'Inom Health Care System',

    'version': '19.0.5.0',

    'category': 'Healthcare',

    'summary': 'Comprehensive Odoo Healthcare & Hospital Management System — '
               'Patients, Doctors, Appointments, Pharmacy, Customer Invoicing, Laboratory, IPD, ICU',

    'description': """
        Hospital Management System — v2 Changes
        ========================================

        Prescription → Stock + Invoice (v2 behaviour)
        -----------------------------------------------
        - Issuing a prescription now automatically:
            1. Creates an Odoo stock.picking (delivery) from Pharmacy location
               → reduces medicine stock via standard Odoo Inventory.
            2. Creates an account.move (customer invoice) with one line
               per medicine — ready for GST/billing team to review and post.
        - Pharmacy uses product.product with Is Medicine enabled.
        - Prescription issuance uses standard Odoo stock and invoicing.
    """,

    'author': 'Bytewerk',
    'website': 'https://bytewerk.odoo.com',
    'maintainer': 'Bytewerk',
    'support': 'into@Bytewerk@gmail.com',
    'license': 'LGPL-3',

    'depends': [
        'base', 'web',
        'mail',
        'contacts',
        'account',
        'product',
        'stock',          # Required for stock.picking, stock.move, stock.quant
        'purchase',       # Optional but recommended for vendor receipts
        'hr',
        'hr_attendance',
        'hr_holidays',
        'crm',
        'calendar',
    ],

    'data': [

        # Security
        'security/hospital_security.xml',
        'security/ir.model.access.csv',

        # Sequences
        'data/patient_sequence.xml',
        'data/clinic_sequence.xml',
        'data/specialty_sequence.xml',
        'data/operations_sequence.xml',
        'data/finance_sequence.xml',

        # Reports referenced by form buttons must be loaded before those views.
        'report/finance_reports.xml',

        # Patient Management
        'views/patient_views.xml',
        'views/emr_views.xml',

        # Appointment & Consultation
        'views/doctor_views.xml',
        'views/appointment_views.xml',
        'views/appointment_booking_views.xml',
        'views/queue_views.xml',

        # Clinical
        'views/clinical_views.xml',
        'views/prescription_views.xml',
        'views/treatment_views.xml',
        'views/certificate_views.xml',
        'views/icd_views.xml',
        'views/consent_views.xml',

        # Diagnostics
        'report/laboratory_reports.xml',
        'views/laboratory_views.xml',
        'views/sample_views.xml',
        'views/radiology_views.xml',

        # Surgery
        'views/surgery_views.xml',
        'views/ot_schedule_views.xml',
        'views/anesthesia_views.xml',

        # Pharmacy — medicines use product.product; legacy pharmacy/dispense views removed
        'views/product_medicine_views.xml',
        'views/medicine_batch_views.xml',

        # Speciality Care
        'views/pediatric_views.xml',
        'views/therapy_views.xml',
        'views/dental_views.xml',
        'views/gynecology_views.xml',

        # Hospital
        'views/building_views.xml',
        'views/ward_views.xml',
        'views/bed_views.xml',
        'views/ipd_views.xml',
        'views/icu_views.xml',
        'views/emergency_views.xml',
        'views/nursing_views.xml',
        'views/campus_views.xml',

        # Finance
        'views/payment_views.xml',
        'views/insurance_claim_views.xml',
        'views/hcfa_edi_views.xml',
        'views/pre_authorization_views.xml',
        'report/clinic_reports.xml',

        # Communication
        'views/communication_views.xml',

        # User access - Boolean hospital role switches
        'views/res_users_views.xml',

        # Client actions must be loaded before menus that reference them
        'views/dashboard_views.xml',
        'views/doctor_dashboard_views.xml',

        # Menu always last
        'views/billing_views.xml',
        'views/menu.xml',
    ],

    'assets': {
        'web.assets_backend': [
            'inom_healthcare_system/static/src/css/dashboard.css',
            'inom_healthcare_system/static/src/js/dashboard.js',
            'inom_healthcare_system/static/src/js/doctor_dashboard.js',
            'inom_healthcare_system/static/src/js/appointment_booking.js',
            'inom_healthcare_system/static/src/js/queue_board.js',
            'inom_healthcare_system/static/src/js/whatsapp.js',
            'inom_healthcare_system/static/src/xml/dashboard.xml',
            'inom_healthcare_system/static/src/xml/doctor_dashboard.xml',
            'inom_healthcare_system/static/src/xml/appointment_booking.xml',
            'inom_healthcare_system/static/src/xml/queue_board.xml',
            'inom_healthcare_system/static/src/css/doctor_dashboard.css',
            'inom_healthcare_system/static/src/css/appointment_booking.css',
            'inom_healthcare_system/static/src/css/queue_board.css',
        ],
    },

    'images': [
        'static/description/icon.png',
    ],

    'application': True,
    'installable': True,
    'auto_install': False,
}
