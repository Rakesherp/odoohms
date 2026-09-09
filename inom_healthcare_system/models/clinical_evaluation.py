from odoo import models, fields, api, _


class ClinicalEvaluation(models.Model):
    _name = 'oeh.clinical'
    _description = 'Clinical Evaluation / Consultation'
    _rec_name = 'patient_id'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'consultation_date desc, id desc'

    patient_id = fields.Many2one(
        'oeh.patient',
        required=True,
        tracking=True,
    )

    appointment_id = fields.Many2one(
        'oeh.appointment',
        tracking=True,
        index=True,
    )

    doctor_id = fields.Many2one(
        'oeh.doctor',
        tracking=True,
        index=True,
    )

    consultation_date = fields.Datetime(
        string='Consultation Date',
        default=fields.Datetime.now,
        required=True,
        tracking=True,
        index=True,
    )

    patient_age = fields.Integer(related='patient_id.age', string='Age', readonly=True)
    patient_gender = fields.Selection(related='patient_id.gender', string='Gender', readonly=True)
    patient_blood_group = fields.Selection(related='patient_id.blood_group', string='Blood Group', readonly=True)
    patient_phone = fields.Char(related='patient_id.phone', string='Phone', readonly=True)
    patient_bp_systolic = fields.Integer(related='patient_id.bp_systolic', string='Systolic', readonly=True)
    patient_bp_diastolic = fields.Integer(related='patient_id.bp_diastolic', string='Diastolic', readonly=True)
    patient_pulse = fields.Integer(related='patient_id.pulse_rate', string='Pulse', readonly=True)
    patient_temperature = fields.Float(related='patient_id.temperature', string='Temperature', readonly=True)
    patient_spo2 = fields.Float(related='patient_id.spo2', string='SpO₂', readonly=True)
    patient_respiratory_rate = fields.Integer(related='patient_id.respiratory_rate', string='Respiratory Rate', readonly=True)
    patient_weight = fields.Float(related='patient_id.weight', string='Weight', readonly=True)
    patient_height = fields.Float(related='patient_id.height', string='Height', readonly=True)
    patient_bmi = fields.Float(related='patient_id.bmi', string='BMI', readonly=True)
    patient_blood_glucose = fields.Float(related='patient_id.blood_glucose', string='Blood Glucose', readonly=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Consultation'),
        ('done', 'Completed'),
    ], default='draft', tracking=True, string='Status')

    chief_complaint = fields.Text(
        string='Chief Complaint',
        help='Primary reason for today’s consultation.',
    )

    symptoms = fields.Text(
        string='History / Symptoms',
    )

    examination = fields.Html(
        string='Clinical Examination',
    )

    diagnosis_id = fields.Many2one(
        'oeh.icd',
        string='Primary Diagnosis',
        tracking=True,
    )

    diagnosis = fields.Text(
        string='Assessment / Diagnosis Notes',
    )

    plan = fields.Html(
        string='Treatment / Plan',
    )

    notes = fields.Html(
        string='Additional Notes',
    )

    followup_date = fields.Date(
        string='Follow-up Date',
    )

    allergy_warning = fields.Char(
        string='Allergy Alert',
        compute='_compute_allergy_warning',
    )

    prescription_count = fields.Integer(
        compute='_compute_related_counts',
    )

    lab_count = fields.Integer(
        compute='_compute_related_counts',
    )

    radiology_count = fields.Integer(
        compute='_compute_related_counts',
    )

    @api.depends('patient_id', 'patient_id.allergy_ids')
    def _compute_allergy_warning(self):
        for rec in self:
            allergies = rec.patient_id.allergy_ids
            if allergies:
                rec.allergy_warning = ', '.join(
                    '%s (%s)' % (
                        a.allergy_name,
                        dict(a._fields['severity'].selection).get(
                            a.severity, a.severity
                        ),
                    )
                    for a in allergies
                )
            else:
                rec.allergy_warning = False

    @api.depends('patient_id')
    def _compute_related_counts(self):
        Prescription = self.env['oeh.prescription']
        Lab = self.env['oeh.laboratory']
        Radiology = self.env['oeh.radiology']
        for rec in self:
            if not rec.patient_id:
                rec.prescription_count = 0
                rec.lab_count = 0
                rec.radiology_count = 0
                continue
            rec.prescription_count = Prescription.search_count([
                ('patient_id', '=', rec.patient_id.id),
                ('appointment_id', '=', rec.appointment_id.id),
            ]) if rec.appointment_id else Prescription.search_count([
                ('patient_id', '=', rec.patient_id.id),
            ])
            rec.lab_count = Lab.search_count([
                ('patient_id', '=', rec.patient_id.id),
                ('doctor_id', '=', rec.doctor_id.id),
            ]) if rec.doctor_id else 0
            rec.radiology_count = Radiology.search_count([
                ('patient_id', '=', rec.patient_id.id),
            ])

    def action_view_patient(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Patient 360'),
            'res_model': 'oeh.patient',
            'res_id': self.patient_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_start(self):
        self.write({'state': 'in_progress'})
        for rec in self:
            if rec.appointment_id and rec.appointment_id.state == 'confirm':
                rec.appointment_id.action_progress()

    def action_complete(self):
        for rec in self:
            rec.write({
                'state': 'done',
                'followup_date': rec.followup_date or (
                    rec.appointment_id.followup_date
                    if rec.appointment_id else False
                ),
            })
            if rec.appointment_id and rec.appointment_id.state == 'progress':
                # Keep appointment completion explicit; consultation completion
                # does not automatically create billing twice.
                rec.appointment_id.message_post(
                    body=_('Consultation completed from the Consultation Workspace.')
                )

    def action_view_prescriptions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Prescriptions'),
            'res_model': 'oeh.prescription',
            'view_mode': 'list,form',
            'domain': [('appointment_id', '=', self.appointment_id.id)]
            if self.appointment_id else [('patient_id', '=', self.patient_id.id)],
            'context': {
                'default_patient_id': self.patient_id.id,
                'default_doctor_id': self.doctor_id.id,
                'default_appointment_id': self.appointment_id.id if self.appointment_id else False,
            },
        }

    def action_new_prescription(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('New Prescription'),
            'res_model': 'oeh.prescription',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_patient_id': self.patient_id.id,
                'default_doctor_id': self.doctor_id.id,
                'default_appointment_id': self.appointment_id.id if self.appointment_id else False,
            },
        }

    def action_view_labs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Laboratory'),
            'res_model': 'oeh.laboratory',
            'view_mode': 'list,form',
            'domain': [('patient_id', '=', self.patient_id.id)],
            'context': {
                'default_patient_id': self.patient_id.id,
                'default_doctor_id': self.doctor_id.id,
            },
        }

    def action_view_radiology(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Radiology'),
            'res_model': 'oeh.radiology',
            'view_mode': 'list,form',
            'domain': [('patient_id', '=', self.patient_id.id)],
        }
