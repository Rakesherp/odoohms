from odoo import models, fields, api


class OEPatient(models.Model):

    _name = 'oeh.patient'
    _description = 'Patient'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    _sql_constraints = [
        ('patient_id_uniq', 'unique(patient_id)',
         'Patient ID must be unique - this ID is already assigned to another patient.'),
    ]

    patient_id = fields.Char(
        string='Patient ID',
        readonly=True,
        default='New',
        copy=False
    )

    name = fields.Char(
        string='Patient Name',
        required=True,
        tracking=True
    )

    image_1920 = fields.Image()

    dob = fields.Date(tracking=True)

    age = fields.Integer(
        compute='_compute_age', store=True, readonly=False,
        help="Auto-calculated from Date of Birth. Editable only when DOB "
             "is unknown (e.g. unregistered infant / unconscious patient "
             "brought to Emergency).",
    )

    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other')
    ])

    blood_group = fields.Selection([
        ('a+', 'A+'),
        ('a-', 'A-'),
        ('b+', 'B+'),
        ('b-', 'B-'),
        ('o+', 'O+'),
        ('o-', 'O-'),
        ('ab+', 'AB+'),
        ('ab-', 'AB-')
    ])

    phone = fields.Char()

    email = fields.Char()

    address = fields.Text()

    emergency_contact = fields.Char()

    # -------------------------
    # Vitals
    # -------------------------

    bp_systolic = fields.Integer(
        string='Blood Pressure – Systolic',
        help='Systolic blood pressure in mmHg.',
        tracking=True,
    )

    bp_diastolic = fields.Integer(
        string='Blood Pressure – Diastolic',
        help='Diastolic blood pressure in mmHg.',
        tracking=True,
    )

    pulse_rate = fields.Integer(
        string='Pulse / Heart Rate',
        help='Heart rate in beats per minute (bpm).',
        tracking=True,
    )

    temperature = fields.Float(
        string='Temperature',
        digits=(5, 2),
        help='Body temperature in °C.',
        tracking=True,
    )

    spo2 = fields.Float(
        string='SpO₂',
        digits=(5, 2),
        help='Peripheral oxygen saturation in percentage.',
        tracking=True,
    )

    respiratory_rate = fields.Integer(
        string='Respiratory Rate',
        help='Respiratory rate in breaths per minute.',
        tracking=True,
    )

    weight = fields.Float(
        string='Weight',
        digits=(6, 2),
        help='Body weight in kilograms.',
        tracking=True,
    )

    height = fields.Float(
        string='Height',
        digits=(6, 2),
        help='Height in centimetres.',
        tracking=True,
    )

    bmi = fields.Float(
        string='BMI',
        digits=(6, 2),
        compute='_compute_bmi',
        store=True,
        readonly=True,
        help='Body Mass Index, automatically calculated from weight and height.',
    )

    blood_glucose = fields.Float(
        string='Blood Glucose',
        digits=(7, 2),
        help='Blood glucose level in mg/dL.',
        tracking=True,
    )

    family_member_ids = fields.Many2many(
        'oeh.patient',
        'oeh_patient_family_rel',
        'patient_id',
        'family_id',
        string="Family Members"
    )
    

    allergy_ids = fields.One2many(
        'patient.allergy',
        'patient_id'
    )

    history_ids = fields.One2many(
        'patient.history',
        'patient_id'
    )

    vaccination_ids = fields.One2many(
        'patient.vaccination',
        'patient_id'
    )

    visit_ids = fields.One2many(
        'patient.visit',
        'patient_id'
    )

    consultation_ids = fields.One2many(
        'oeh.clinical',
        'patient_id',
        string='Consultations',
    )

    consultation_count = fields.Integer(
        string='Consultations',
        compute='_compute_consultation_count',
    )

    active = fields.Boolean(
        default=True
    )

    # -------------------------
    # Community ERP Features
    # -------------------------

    partner_id = fields.Many2one(
        'res.partner',
        string='Contact'
    )

    # crm_lead_id = fields.Many2one(
    #     'crm.lead',
    #     string='CRM Lead'
    # )
    billing_count = fields.Integer(
        string="Billing Count",
        compute="_compute_billing_count",
        store=False,
    )

    def _compute_billing_count(self):
        for patient in self:
            patient.billing_count = 0

    @api.depends('weight', 'height')
    def _compute_bmi(self):
        for rec in self:
            if rec.weight and rec.height and rec.height > 0:
                height_m = rec.height / 100.0
                rec.bmi = rec.weight / (height_m * height_m)
            else:
                rec.bmi = 0.0

    @api.depends('dob')
    def _compute_age(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.dob:
                years = today.year - rec.dob.year - (
                    (today.month, today.day) < (rec.dob.month, rec.dob.day))
                rec.age = max(years, 0)
            # No DOB: leave 'age' as whatever was manually entered.

    appointment_count = fields.Integer(
        compute='_compute_appointment_count'
    )

    visit_count = fields.Integer(
        compute='_compute_visit_count'
    )

    prescription_count = fields.Integer(
        string='Prescriptions',
        compute='_compute_prescription_count',
    )

    insurance_count = fields.Integer(
        string='Insurance',
        compute='_compute_insurance_count',
    )

    lab_count = fields.Integer(
        string='Lab Requests',
        compute='_compute_lab_count',
    )

    radiology_count = fields.Integer(
        string='Radiology',
        compute='_compute_radiology_count',
    )

    @api.depends()
    def _compute_appointment_count(self):

        for rec in self:

            rec.appointment_count = self.env[
                'oeh.appointment'
            ].search_count([
                ('patient_id', '=', rec.id)
            ])


    @api.depends()
    def _compute_visit_count(self):

        for rec in self:

            rec.visit_count = self.env[
                'patient.visit'
            ].search_count([
                ('patient_id', '=', rec.id)
            ])


    def action_view_appointments(self):

        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Appointments',
            'res_model': 'oeh.appointment',
            'view_mode': 'list,form',
            'domain': [
                ('patient_id', '=', self.id)
            ]
        }


    def action_view_visits(self):

        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Visits',
            'res_model': 'patient.visit',
            'view_mode': 'list,form',
            'domain': [
                ('patient_id', '=', self.id)
            ]
        }

    @api.depends('consultation_ids')
    def _compute_consultation_count(self):
        for rec in self:
            rec.consultation_count = len(rec.consultation_ids)

    def action_view_consultations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Clinical Consultations',
            'res_model': 'oeh.clinical',
            'view_mode': 'list,form',
            'domain': [('patient_id', '=', self.id)],
            'context': {'default_patient_id': self.id},
        }

    @api.depends()
    def _compute_prescription_count(self):
        Prescription = self.env['oeh.prescription']
        for rec in self:
            rec.prescription_count = Prescription.search_count([
                ('patient_id', '=', rec.id)
            ])

    def _compute_insurance_count(self):
        Claim = self.env['oeh.insurance.claim']
        for rec in self:
            rec.insurance_count = Claim.search_count([
                ('patient_id', '=', rec.id)
            ])

    @api.depends()
    def _compute_lab_count(self):
        Lab = self.env['oeh.laboratory']
        for rec in self:
            rec.lab_count = Lab.search_count([
                ('patient_id', '=', rec.id)
            ])

    @api.depends()
    def _compute_radiology_count(self):
        Radiology = self.env['oeh.radiology']
        for rec in self:
            rec.radiology_count = Radiology.search_count([
                ('patient_id', '=', rec.id)
            ])

    def action_view_insurance_claims(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Insurance',
            'res_model': 'oeh.insurance.claim',
            'view_mode': 'list,form',
            'domain': [('patient_id', '=', self.id)],
            'context': {'default_patient_id': self.id},
        }

    def action_view_prescriptions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Prescriptions',
            'res_model': 'oeh.prescription',
            'view_mode': 'list,form',
            'domain': [('patient_id', '=', self.id)],
            'context': {
                'default_patient_id': self.id,
            },
        }

    def action_view_labs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Laboratory Requests',
            'res_model': 'oeh.laboratory',
            'view_mode': 'list,form',
            'domain': [('patient_id', '=', self.id)],
            'context': {
                'default_patient_id': self.id,
            },
        }

    def action_view_radiology(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Radiology',
            'res_model': 'oeh.radiology',
            'view_mode': 'list,form',
            'domain': [('patient_id', '=', self.id)],
            'context': {
                'default_patient_id': self.id,
            },
        }


    def _get_or_create_partner(self):
        """Return this patient's linked Contact (res.partner), creating one
        from the patient's name/phone/email if none exists yet, and storing
        it back on partner_id so it's reused for every future invoice."""
        self.ensure_one()
        if self.partner_id:
            return self.partner_id
        partner = self.env['res.partner'].create({
            'name': self.name,
            'phone': self.phone,
            'email': self.email,
        })
        self.partner_id = partner.id
        return partner


    @api.model_create_multi
    def create(self, vals_list):

        for vals in vals_list:

            if vals.get(
                'patient_id',
                'New'
            ) == 'New':

                vals['patient_id'] = self.env[
                    'ir.sequence'
                ].next_by_code(
                    'oeh.patient'
                ) or 'New'

        return super().create(vals_list)

    @api.depends('name', 'patient_id')
    def _compute_display_name(self):
        # Odoo 19: name_get() is deprecated/unsupported - use
        # _compute_display_name instead (matches the pattern already used
        # in prescription.py / prescription_dispense.py).
        for rec in self:
            rec.display_name = "%s [%s]" % (rec.name or '', rec.patient_id or '')