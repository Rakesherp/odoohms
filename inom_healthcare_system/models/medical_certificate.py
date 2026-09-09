from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class MedicalCertificate(models.Model):

    _name = 'oeh.certificate'
    _description = 'Medical Certificate'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'patient_id'
    _order = 'id desc'

    # ---- Existing fields (preserved) ----
    patient_id = fields.Many2one('oeh.patient', required=True, tracking=True)
    issue_date = fields.Date(tracking=True)
    valid_until = fields.Date(tracking=True)
    from_date = fields.Date(string='From Date', tracking=True)
    to_date = fields.Date(string='To Date', tracking=True)
    details = fields.Html()

    # ---- Professional additions ----
    name = fields.Char(string='Certificate No.', default='New', readonly=True, copy=False, index=True)
    doctor_id = fields.Many2one('oeh.doctor', string='Issuing Doctor', tracking=True)
    certificate_type = fields.Selection([
        ('fitness', 'Fitness Certificate'),
        ('sick', 'Sick Leave'),
        ('medical_leave', 'Medical Leave'),
    ], default='sick', tracking=True)
    reason = fields.Char(string='Reason / Diagnosis')
    leave_days = fields.Integer(string='No. of Days', compute='_compute_leave_days', store=True, readonly=False)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('issued', 'Issued'),
        ('expired', 'Expired'),
        ('cancel', 'Cancelled'),
    ], default='draft', tracking=True)

    is_expired = fields.Boolean(compute='_compute_is_expired', store=True)

    # Reference / signature structure
    reference = fields.Char(string='Verification Reference', copy=False,
                            help="QR / verification reference for authenticity checks")
    signed_by = fields.Char(string='Signed By')
    signed_date = fields.Date()
    signature = fields.Binary(string='Digital Signature', attachment=True)

    @api.depends('from_date', 'to_date', 'issue_date', 'valid_until')
    def _compute_leave_days(self):
        for rec in self:
            start = rec.from_date or rec.issue_date
            end = rec.to_date or rec.valid_until
            rec.leave_days = (end - start).days + 1 if start and end and end >= start else 0

    @api.depends('valid_until')
    def _compute_is_expired(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_expired = bool(rec.valid_until and rec.valid_until < today)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') in (False, 'New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('oeh.certificate') or 'New'
        return super().create(vals_list)

    @api.constrains('issue_date', 'valid_until', 'from_date', 'to_date')
    def _check_dates(self):
        for rec in self:
            if rec.issue_date and rec.valid_until and rec.valid_until < rec.issue_date:
                raise ValidationError(_("Valid-until date cannot be earlier than the issue date."))

    # ---- Workflow ----
    def action_issue(self):
        for rec in self:
            if not rec.doctor_id:
                raise ValidationError(_("Assign an issuing doctor before issuing the certificate."))
            vals = {'state': 'issued'}
            if rec.from_date and not rec.issue_date:
                vals['issue_date'] = rec.from_date
            if rec.to_date and not rec.valid_until:
                vals['valid_until'] = rec.to_date
            if rec.doctor_id and not rec.signed_by:
                vals['signed_by'] = rec.doctor_id.name
            if not rec.signed_date:
                vals['signed_date'] = fields.Date.context_today(rec)
            if not rec.issue_date:
                vals['issue_date'] = fields.Date.context_today(self)
            if not rec.reference:
                vals['reference'] = rec.name
            rec.write(vals)

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_reset(self):
        self.write({'state': 'draft'})
