from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class OEPreAuth(models.Model):

    _name = 'oeh.pre.authorization'
    _description = 'Pre Authorization'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    # ---- Existing fields (preserved) ----
    patient_id = fields.Many2one(
        'oeh.patient',
        required=True
    )

    insurance_company = fields.Char(required=True)

    procedure_name = fields.Char(required=True)

    requested_amount = fields.Float(required=True)

    approved_amount = fields.Float()

    authorization_no = fields.Char()

    status = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    ], required=True, default='draft', tracking=True)

    notes = fields.Text()

    # ---- Professional additions ----
    name = fields.Char(
        string='Pre-Auth Ref', default='New', readonly=True, copy=False,
        index=True, tracking=True)

    doctor_id = fields.Many2one('oeh.doctor', string='Requesting Doctor')
    ipd_id = fields.Many2one('oeh.ipd', string='IPD Admission', tracking=True)
    claim_id = fields.Many2one('oeh.insurance.claim', string='Insurance Claim', readonly=True, copy=False)
    insurance_partner_id = fields.Many2one(
        'res.partner', string='Insurance Company', domain=[('is_company', '=', True)])
    policy_number = fields.Char()
    justification = fields.Text(string='Medical Justification')
    request_date = fields.Date(default=fields.Date.context_today, tracking=True)
    decision_date = fields.Date(tracking=True)
    valid_from = fields.Date()
    valid_until = fields.Date(tracking=True)
    is_expired = fields.Boolean(compute='_compute_is_expired')
    attachment_ids = fields.Many2many(
        'ir.attachment', 'oeh_preauth_attachment_rel',
        'preauth_id', 'attachment_id', string='Supporting Documents')

    def _compute_is_expired(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_expired = bool(rec.valid_until and rec.valid_until < today)


    @api.onchange('insurance_partner_id')
    def _onchange_insurance_partner(self):
        if self.insurance_partner_id:
            self.insurance_company = self.insurance_partner_id.name

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('insurance_partner_id') and not vals.get('insurance_company'):
                partner = self.env['res.partner'].browse(vals['insurance_partner_id']).exists()
                if partner:
                    vals['insurance_company'] = partner.name
            if vals.get('name', 'New') in (False, 'New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'oeh.pre.authorization') or 'New'
        return super().create(vals_list)

    @api.depends('name', 'procedure_name')
    def _compute_display_name(self):
        for rec in self:
            if rec.name and rec.name != 'New':
                rec.display_name = '%s - %s' % (rec.name, rec.procedure_name or '')
            else:
                rec.display_name = rec.procedure_name or _('New Request')

    @api.constrains('requested_amount', 'approved_amount')
    def _check_preauth_amounts(self):
        for rec in self:
            if rec.requested_amount < 0 or rec.approved_amount < 0:
                raise ValidationError(_("Amounts cannot be negative."))
            if rec.approved_amount > rec.requested_amount and rec.requested_amount:
                raise ValidationError(_(
                    "Approved amount cannot exceed the requested amount."))

    @api.constrains('valid_from', 'valid_until')
    def _check_validity_dates(self):
        for rec in self:
            if rec.valid_from and rec.valid_until and rec.valid_until < rec.valid_from:
                raise ValidationError(_(
                    "'Valid Until' cannot be earlier than 'Valid From'."))

    # ---- Workflow ----
    def action_submit(self):
        self.write({'status': 'pending', 'request_date': fields.Date.context_today(self)})

    def action_approve(self):
        for rec in self:
            vals = {'status': 'approved',
                    'decision_date': fields.Date.context_today(rec)}
            if not rec.authorization_no:
                vals['authorization_no'] = self.env['ir.sequence'].next_by_code(
                    'oeh.pre.authorization') or rec.name
            rec.write(vals)

    def action_create_claim(self):
        self.ensure_one()
        if self.status != 'approved':
            raise ValidationError(_('A claim can be created only from an approved pre-authorization.'))
        if self.claim_id:
            return {
                'type': 'ir.actions.act_window', 'res_model': 'oeh.insurance.claim',
                'res_id': self.claim_id.id, 'view_mode': 'form', 'target': 'current',
            }
        claim = self.env['oeh.insurance.claim'].create({
            'patient_id': self.patient_id.id,
            'insurance_company': self.insurance_company,
            'insurance_partner_id': self.insurance_partner_id.id if self.insurance_partner_id else False,
            'policy_number': self.policy_number,
            'claim_amount': self.requested_amount,
            'approved_amount': self.approved_amount,
            'ipd_id': self.ipd_id.id if self.ipd_id else False,
            'remarks': self.justification or self.notes or False,
        })
        self.claim_id = claim.id
        return {
            'type': 'ir.actions.act_window', 'res_model': 'oeh.insurance.claim',
            'res_id': claim.id, 'view_mode': 'form', 'target': 'current',
        }

    def action_reject(self):
        self.write({'status': 'rejected',
                    'decision_date': fields.Date.context_today(self)})

    def action_expire(self):
        self.write({'status': 'expired'})

    def action_reset(self):
        self.write({'status': 'draft'})
