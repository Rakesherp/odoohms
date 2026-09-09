from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class OEIPD(models.Model):
    _name = 'oeh.ipd'
    _description = 'IPD Admission'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    # ---- Existing fields (preserved) ----
    name = fields.Char(default='New', readonly=True, copy=False, tracking=True)
    patient_id = fields.Many2one('oeh.patient', required=True, tracking=True)
    bed_id = fields.Many2one(
        'oeh.bed', required=True, tracking=True,
        domain="[('status', '=', 'free'), ('active', '=', True)]"
    )
    admission_date = fields.Datetime(tracking=True)
    discharge_date = fields.Datetime(tracking=True)

    status = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Admission Confirmed'),
        ('admitted', 'Admitted'),
        ('under_treatment', 'Under Treatment'),
        ('discharge_pending', 'Discharge Initiated'),
        ('discharged', 'Discharged'),
        ('closed', 'Closed'),
    ], default='draft', tracking=True)

    admission_type = fields.Selection([
        ('planned', 'Planned'),
        ('emergency', 'Emergency'),
        ('transfer', 'Transfer'),
    ], string='Admission Type', default='planned', required=True, tracking=True)

    # ---- Professional additions ----
    ward_id = fields.Many2one(related='bed_id.ward_id', string='Ward', store=True, readonly=True)
    attending_doctor_id = fields.Many2one('oeh.doctor', string='Attending Doctor', tracking=True)
    # Keep the legacy text field for database compatibility; new UI uses the employee relation.
    nurse_in_charge = fields.Char(string='Nurse In-Charge (Legacy)', copy=False)
    nurse_in_charge_id = fields.Many2one(
        'hr.employee', string='Nurse In-Charge', tracking=True,
        domain=[('active', '=', True)])
    insurance_required = fields.Boolean(string='Insurance Required', default=False, tracking=True)
    insurance_partner_id = fields.Many2one(
        'res.partner', string='Insurance Company', tracking=True,
        domain=[('is_company', '=', True)])
    policy_number = fields.Char(string='Policy Number', tracking=True)
    insurance_claim_id = fields.Many2one('oeh.insurance.claim', string='Insurance Claim', tracking=True)
    pre_authorization_id = fields.Many2one('oeh.pre.authorization', string='Pre-Authorization', tracking=True)
    billing_id = fields.Many2one('oeh.billing', string='Hospital Bill', readonly=True, copy=False)
    allergy_alert = fields.Char(string='Allergy Alert', compute='_compute_allergy_alert', readonly=True)
    reason = fields.Text(string='Reason for Admission')
    diagnosis = fields.Text()
    discharge_summary = fields.Html(string='Discharge Summary')
    company_id = fields.Many2one(
        'res.company', string='Company', default=lambda self: self.env.company)

    invoice_id = fields.Many2one('account.move', string='Customer Invoice', copy=False, domain=[('move_type', '=', 'out_invoice')])
    invoice_count = fields.Integer(compute='_compute_invoice_count')
    stay_days = fields.Float(string='Length of Stay (Days)', compute='_compute_stay_days')
    is_active_admission = fields.Boolean(compute='_compute_is_active_admission')
    discharge_reason = fields.Text(string='Discharge Reason')

    @api.depends('patient_id', 'patient_id.allergy_ids.allergy_name')
    def _compute_allergy_alert(self):
        for rec in self:
            allergies = rec.patient_id.allergy_ids if rec.patient_id else self.env['patient.allergy']
            rec.allergy_alert = ', '.join(allergies.mapped('allergy_name')) if allergies else ''

    def _compute_stay_days(self):
        now = fields.Datetime.now()
        for rec in self:
            start = rec.admission_date
            end = rec.discharge_date or now
            if start and end and end >= start:
                rec.stay_days = (end - start).total_seconds() / 86400.0
            else:
                rec.stay_days = 0.0

    def _compute_is_active_admission(self):
        for rec in self:
            rec.is_active_admission = rec.status in ('admitted', 'under_treatment', 'discharge_pending')

    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = 1 if rec.invoice_id else 0

    @api.onchange('insurance_partner_id')
    def _onchange_insurance_partner(self):
        # The claim/pre-authorization models keep their own partner relation; this
        # field provides the insurance choice at admission level.
        return

    @api.constrains('insurance_required', 'insurance_partner_id', 'policy_number')
    def _check_insurance_details(self):
        for rec in self:
            if rec.insurance_required and not rec.insurance_partner_id and not rec.insurance_claim_id:
                raise ValidationError(_('Please select an Insurance Company or link an Insurance Claim when Insurance is required.'))

    def action_view_insurance(self):
        self.ensure_one()
        if self.insurance_claim_id:
            return {
                'type': 'ir.actions.act_window', 'name': _('Insurance Claim'),
                'res_model': 'oeh.insurance.claim', 'res_id': self.insurance_claim_id.id,
                'view_mode': 'form', 'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window', 'name': _('Insurance Claims'),
            'res_model': 'oeh.insurance.claim', 'view_mode': 'list,form',
            'domain': [('patient_id', '=', self.patient_id.id)],
            'context': {
                'default_patient_id': self.patient_id.id,
                'default_ipd_id': self.id,
                'default_insurance_partner_id': self.insurance_partner_id.id if self.insurance_partner_id else False,
                'default_policy_number': self.policy_number,
            },
        }

    def action_view_billing(self):
        self.ensure_one()
        if not self.billing_id:
            bill = self._create_hospital_bill()
            self.billing_id = bill.id
        return {
            'type': 'ir.actions.act_window', 'name': _('Hospital Bill'),
            'res_model': 'oeh.billing', 'res_id': self.billing_id.id,
            'view_mode': 'form', 'target': 'current',
        }

    def action_view_preauthorization(self):
        self.ensure_one()
        if self.pre_authorization_id:
            return {
                'type': 'ir.actions.act_window', 'name': _('Pre-Authorization'),
                'res_model': 'oeh.pre.authorization', 'res_id': self.pre_authorization_id.id,
                'view_mode': 'form', 'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window', 'name': _('Pre-Authorization'),
            'res_model': 'oeh.pre.authorization', 'view_mode': 'list,form',
            'domain': [('patient_id', '=', self.patient_id.id), ('ipd_id', '=', self.id)],
            'context': {
                'default_patient_id': self.patient_id.id,
                'default_ipd_id': self.id,
                'default_insurance_partner_id': self.insurance_partner_id.id if self.insurance_partner_id else False,
                'default_policy_number': self.policy_number,
            },
        }

    def action_create_insurance_claim(self):
        self.ensure_one()
        if not self.insurance_required:
            raise ValidationError(_('Enable Insurance Required before creating an insurance claim.'))
        if self.insurance_claim_id:
            return self.action_view_insurance()
        claim = self.env['oeh.insurance.claim'].create({
            'patient_id': self.patient_id.id,
            'ipd_id': self.id,
            'insurance_partner_id': self.insurance_partner_id.id if self.insurance_partner_id else False,
            'policy_number': self.policy_number,
        })
        self.insurance_claim_id = claim.id
        return {
            'type': 'ir.actions.act_window', 'name': _('Insurance Claim'),
            'res_model': 'oeh.insurance.claim', 'res_id': claim.id,
            'view_mode': 'form', 'target': 'current',
        }

    # ---- Existing create (preserved) ----
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('oeh.ipd') or 'New'
        return super().create(vals_list)

    def _assign_bed(self):
        """Occupy self.bed_id for self.patient_id, guarding against
        assigning a bed that already has a different patient in it."""
        self.ensure_one()
        bed = self.bed_id
        if bed.status == 'occupied' and bed.current_patient_id \
                and bed.current_patient_id != self.patient_id:
            raise ValidationError(_(
                "Bed %(bed)s is already occupied by %(patient)s. "
                "Choose a free bed or discharge the current patient first."
            ) % {'bed': bed.name, 'patient': bed.current_patient_id.name})
        bed.write({
            'status': 'occupied',
            'current_patient_id': self.patient_id.id,
        })

    @api.constrains('bed_id', 'status')
    def _check_bed_not_double_assigned(self):
        """Extra DB-level safety net: catches a bed being reassigned via a
        direct field edit (not just through action_admit/_assign_bed)."""
        for rec in self:
            if rec.status not in ('admitted', 'under_treatment') or not rec.bed_id:
                continue
            clash = self.search([
                ('id', '!=', rec.id),
                ('bed_id', '=', rec.bed_id.id),
                ('status', 'in', ('admitted', 'under_treatment')),
            ], limit=1)
            if clash:
                raise ValidationError(_(
                    "Bed %(bed)s is already assigned to admission %(other)s "
                    "(%(patient)s). A bed can only have one active admission "
                    "at a time.") % {
                    'bed': rec.bed_id.name, 'other': clash.name,
                    'patient': clash.patient_id.name})

    @api.constrains('admission_date', 'discharge_date')
    def _check_dates(self):
        for rec in self:
            if rec.admission_date and rec.discharge_date and rec.discharge_date < rec.admission_date:
                raise ValidationError(_("Discharge date cannot be earlier than admission date."))

    # ---- Admission lifecycle ---------------------------------------
    @api.constrains('patient_id', 'status')
    def _check_patient_active_admission(self):
        for rec in self:
            if rec.status not in ('admitted', 'under_treatment', 'discharge_pending') or not rec.patient_id:
                continue
            other = self.search([
                ('id', '!=', rec.id),
                ('patient_id', '=', rec.patient_id.id),
                ('status', 'in', ('admitted', 'under_treatment', 'discharge_pending')),
            ], limit=1)
            if other:
                raise ValidationError(_(
                    'Patient %(patient)s already has active IPD admission %(admission)s.'
                ) % {'patient': rec.patient_id.name, 'admission': other.name})

    def action_confirm_admission(self):
        for rec in self:
            if rec.status != 'draft':
                continue
            if rec.pre_authorization_id and rec.pre_authorization_id.status not in ('approved',):
                raise ValidationError(_('The linked pre-authorization must be approved before confirming this admission.'))
            rec.status = 'confirmed'

    def action_admit(self):
        for rec in self:
            if rec.status not in ('confirmed', 'draft'):
                continue
            if rec.status == 'draft':
                if rec.pre_authorization_id and rec.pre_authorization_id.status != 'approved':
                    raise ValidationError(_('The linked pre-authorization must be approved before admission.'))
                rec.status = 'confirmed'
            if rec.ward_id and rec.ward_id.state != 'active':
                raise ValidationError(_('Admission cannot be made to a ward that is not active.'))
            if not rec.bed_id or rec.bed_id.status != 'free':
                raise ValidationError(_('Please select a free bed before admitting the patient.'))
            if not rec.admission_date:
                rec.admission_date = fields.Datetime.now()
            if rec.bed_id:
                rec._assign_bed()
            rec.status = 'admitted'

    def action_start_treatment(self):
        for rec in self:
            if rec.status != 'admitted':
                raise ValidationError(_('Treatment can start only after the patient is admitted.'))
            rec.status = 'under_treatment'

    def action_cancel_admission(self):
        for rec in self:
            if rec.status not in ('draft', 'confirmed'):
                raise ValidationError(_('Only draft or confirmed admissions can be cancelled.'))
            rec.status = 'closed'

    def action_initiate_discharge(self):
        for rec in self:
            if rec.status not in ('admitted', 'under_treatment'):
                raise ValidationError(_('Discharge can be initiated only for an admitted patient.'))
            rec.status = 'discharge_pending'

    def action_discharge(self):
        for rec in self:
            if rec.status not in ('discharge_pending', 'admitted', 'under_treatment'):
                raise ValidationError(_('The admission is not ready for discharge.'))
            if not rec.discharge_summary and not rec.discharge_reason:
                raise ValidationError(_('Please enter a discharge summary or discharge reason before discharge.'))
            rec.status = 'discharged'
            if not rec.discharge_date:
                rec.discharge_date = fields.Datetime.now()
            if rec.bed_id:
                rec.bed_id.write({'status': 'cleaning', 'current_patient_id': False})
            if not rec.billing_id:
                rec._create_hospital_bill()
            if rec.billing_id and rec.insurance_claim_id:
                rec.billing_id.insurance_claim_id = rec.insurance_claim_id.id
                rec.billing_id.insurance_coverage = rec.insurance_claim_id.approved_amount or 0.0

    def action_close(self):
        for rec in self:
            if rec.status != 'discharged':
                raise ValidationError(_('Only a discharged admission can be closed.'))
            rec.status = 'closed'

    def action_reset(self):
        for rec in self:
            if rec.status in ('discharged', 'closed'):
                raise ValidationError(_('A discharged/closed admission cannot be reset. Create a new admission if the patient returns.'))
            rec.status = 'draft'
            if rec.bed_id and rec.bed_id.current_patient_id == rec.patient_id:
                rec.bed_id.write({'status': 'free', 'current_patient_id': False})

    def _create_hospital_bill(self):
        self.ensure_one()
        if self.billing_id:
            return self.billing_id
        Bill = self.env['oeh.billing']
        total = 0.0
        bill = Bill.create({
            'patient_id': self.patient_id.id,
            'ipd_id': self.id,
            'insurance_claim_id': self.insurance_claim_id.id if self.insurance_claim_id else False,
            'total_amount': total,
            'insurance_coverage': self.insurance_claim_id.approved_amount if self.insurance_claim_id else 0.0,
        })
        self.billing_id = bill.id
        return bill

    # ---- Billing integration (creates a finance bill; does not modify finance code) ----
    def action_create_invoice(self):
        self.ensure_one()
        bill = self._create_hospital_bill()
        if not bill.invoice_id:
            bill.action_create_invoice()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Customer Invoice'),
            'res_model': 'account.move',
            'res_id': bill.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_bed(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'oeh.bed',
            'res_id': self.bed_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
