from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class OEIPDPhase23(models.Model):
    _inherit = 'oeh.ipd'

    expected_discharge_date = fields.Datetime(
        string='Expected Discharge',
        tracking=True,
    )
    discharge_condition = fields.Selection([
        ('stable', 'Stable'),
        ('improved', 'Improved'),
        ('referred', 'Referred to Another Facility'),
        ('lama', 'Left Against Medical Advice'),
        ('deceased', 'Deceased'),
    ], string='Condition at Discharge', tracking=True)
    discharge_instructions = fields.Html(
        string='Discharge Instructions',
        help='Medicines, diet, activity, warning signs and follow-up instructions.',
    )
    followup_date = fields.Date(string='Follow-up Date', tracking=True)
    discharge_doctor_id = fields.Many2one(
        'oeh.doctor',
        string='Discharging Doctor',
        tracking=True,
    )

    insurance_verified = fields.Boolean(
        string='Insurance Verified',
        tracking=True,
        help='Confirm that the policy and patient eligibility were verified.',
    )
    insurance_verified_date = fields.Date(
        string='Verified Date',
        tracking=True,
    )
    insurance_remarks = fields.Text(string='Insurance Remarks')

    insurance_claim_count = fields.Integer(
        string='Claims',
        compute='_compute_phase23_counts',
    )
    nursing_plan_count = fields.Integer(
        string='Nursing Plans',
        compute='_compute_phase23_counts',
    )
    certificate_count = fields.Integer(
        string='Medical Certificates',
        compute='_compute_phase23_counts',
    )

    @api.depends('insurance_claim_id', 'patient_id', 'nurse_in_charge_id')
    def _compute_phase23_counts(self):
        Claim = self.env['oeh.insurance.claim']
        Nursing = self.env['oeh.nursing']
        Certificate = self.env['oeh.certificate']
        for rec in self:
            rec.insurance_claim_count = Claim.search_count([
                ('ipd_id', '=', rec.id),
            ])
            rec.nursing_plan_count = Nursing.search_count([
                ('ipd_id', '=', rec.id),
            ])
            rec.certificate_count = Certificate.search_count([
                ('ipd_id', '=', rec.id),
            ])

    @api.onchange('insurance_required')
    def _onchange_phase23_insurance_required(self):
        if not self.insurance_required:
            self.insurance_verified = False
            self.insurance_verified_date = False

    @api.constrains('insurance_verified', 'insurance_required', 'insurance_partner_id')
    def _check_phase23_insurance(self):
        for rec in self:
            if rec.insurance_verified and not rec.insurance_required:
                raise ValidationError(
                    _('Insurance cannot be marked verified when Insurance Required is disabled.')
                )
            if rec.insurance_verified and not rec.insurance_partner_id:
                raise ValidationError(
                    _('Select the Insurance Company before marking insurance as verified.')
                )

    @api.constrains('expected_discharge_date', 'admission_date')
    def _check_expected_discharge(self):
        for rec in self:
            if rec.expected_discharge_date and rec.admission_date:
                if rec.expected_discharge_date < rec.admission_date:
                    raise ValidationError(
                        _('Expected discharge cannot be earlier than admission date.')
                    )

    def action_mark_insurance_verified(self):
        for rec in self:
            if not rec.insurance_required:
                raise ValidationError(_('Enable Insurance Required first.'))
            if not rec.insurance_partner_id:
                raise ValidationError(_('Select the Insurance Company first.'))
            rec.write({
                'insurance_verified': True,
                'insurance_verified_date': fields.Date.context_today(rec),
            })

    def action_unverify_insurance(self):
        self.write({
            'insurance_verified': False,
            'insurance_verified_date': False,
        })

    def action_view_insurance_claims_phase23(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Insurance Claims'),
            'res_model': 'oeh.insurance.claim',
            'view_mode': 'list,form',
            'domain': [('ipd_id', '=', self.id)],
            'context': {
                'default_patient_id': self.patient_id.id,
                'default_ipd_id': self.id,
                'default_insurance_partner_id': self.insurance_partner_id.id
                if self.insurance_partner_id else False,
                'default_policy_number': self.policy_number,
            },
        }

    def action_view_nursing_plans_phase23(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Nursing Plans'),
            'res_model': 'oeh.nursing',
            'view_mode': 'list,form',
            'domain': [('ipd_id', '=', self.id)],
            'context': {
                'default_patient_id': self.patient_id.id,
                'default_ipd_id': self.id,
                'default_nurse_in_charge_id': self.nurse_in_charge_id.id
                if self.nurse_in_charge_id else False,
            },
        }

    def action_view_certificates_phase23(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Medical Certificates'),
            'res_model': 'oeh.certificate',
            'view_mode': 'list,form',
            'domain': [('ipd_id', '=', self.id)],
            'context': {
                'default_patient_id': self.patient_id.id,
                'default_ipd_id': self.id,
                'default_doctor_id': self.discharge_doctor_id.id
                if self.discharge_doctor_id else False,
            },
        }

    def action_create_nursing_plan_phase23(self):
        self.ensure_one()
        plan = self.env['oeh.nursing'].create({
            'patient_id': self.patient_id.id,
            'ipd_id': self.id,
            'nurse_in_charge_id': self.nurse_in_charge_id.id
            if self.nurse_in_charge_id else False,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Nursing Plan'),
            'res_model': 'oeh.nursing',
            'res_id': plan.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_discharge_certificate_phase23(self):
        self.ensure_one()
        certificate = self.env['oeh.certificate'].create({
            'patient_id': self.patient_id.id,
            'ipd_id': self.id,
            'doctor_id': self.discharge_doctor_id.id
            if self.discharge_doctor_id else self.attending_doctor_id.id
            if self.attending_doctor_id else False,
            'certificate_type': 'medical_leave',
            'from_date': self.admission_date.date() if self.admission_date else False,
            'to_date': self.discharge_date.date() if self.discharge_date else False,
            'reason': self.discharge_reason or self.reason or '',
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Medical Certificate'),
            'res_model': 'oeh.certificate',
            'res_id': certificate.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_phase23_discharge(self):
        """A safer discharge wrapper: require the discharge doctor and condition."""
        for rec in self:
            if rec.status != 'discharge_pending':
                raise ValidationError(_('Initiate discharge before completing discharge.'))
            if not rec.discharge_doctor_id:
                raise ValidationError(_('Select the Discharging Doctor before discharge.'))
            if not rec.discharge_condition:
                raise ValidationError(_('Select the Condition at Discharge before discharge.'))
            if not rec.discharge_summary and not rec.discharge_reason:
                raise ValidationError(_('Enter a Discharge Summary or Discharge Reason.'))
            rec.action_discharge()
