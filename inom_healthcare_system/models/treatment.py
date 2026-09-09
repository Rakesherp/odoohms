from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class Treatment(models.Model):

    _name = 'oeh.treatment'
    _description = 'Treatment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'treatment_name'
    _order = 'id desc'

    # ---- Existing fields (preserved) ----
    patient_id = fields.Many2one('oeh.patient', required=True, tracking=True)
    treatment_name = fields.Char(required=True, tracking=True)
    procedure = fields.Text()
    notes = fields.Text()

    # ---- Professional additions ----
    name = fields.Char(string='Treatment Ref', default='New', readonly=True, copy=False, index=True)
    date = fields.Date(default=fields.Date.context_today, tracking=True)
    doctor_id = fields.Many2one('oeh.doctor', string='Doctor', tracking=True)
    diagnosis_id = fields.Many2one('oeh.icd', string='Diagnosis (ICD)')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('planned', 'Planned'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancel', 'Cancelled'),
    ], default='draft', tracking=True)

    treatment_plan = fields.Text()
    clinical_notes = fields.Text()
    followup_date = fields.Date(string='Follow-up Date')

    fee = fields.Float(string='Treatment Fee')
    invoice_id = fields.Many2one('account.move', string='Customer Invoice', copy=False, domain=[('move_type', '=', 'out_invoice')])
    invoice_count = fields.Integer(compute='_compute_invoice_count')
    treatment_count = fields.Integer(compute='_compute_treatment_count')

    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = 1 if rec.invoice_id else 0

    def _compute_treatment_count(self):
        for rec in self:
            rec.treatment_count = self.search_count([('patient_id', '=', rec.patient_id.id)]) \
                if rec.patient_id else 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') in (False, 'New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('oeh.treatment') or 'New'
        return super().create(vals_list)

    @api.constrains('fee')
    def _check_fee(self):
        for rec in self:
            if rec.fee < 0:
                raise ValidationError(_("Treatment fee cannot be negative."))

    # ---- Workflow ----
    def action_plan(self):
        self.write({'state': 'planned'})

    def action_start(self):
        self.write({'state': 'in_progress'})

    def action_complete(self):
        self.write({'state': 'completed'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_reset(self):
        self.write({'state': 'draft'})

    def action_view_history(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Treatment History'),
            'res_model': 'oeh.treatment', 'view_mode': 'list,form',
            'domain': [('patient_id', '=', self.patient_id.id)],
            'context': {'default_patient_id': self.patient_id.id},
        }

    def action_create_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            partner = self.patient_id.partner_id or self.patient_id._get_or_create_partner()
            invoice = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': partner.id,
                'invoice_date': fields.Date.context_today(self),
                'invoice_origin': self.name,
                'invoice_line_ids': [(0, 0, {
                    'name': self.treatment_name or _('Treatment'),
                    'quantity': 1,
                    'price_unit': self.fee or 0.0,
                })],
            })
            self.invoice_id = invoice.id
        return {
            'type': 'ir.actions.act_window', 'name': _('Customer Invoice'),
            'res_model': 'account.move', 'res_id': self.invoice_id.id,
            'view_mode': 'form', 'target': 'current',
        }
