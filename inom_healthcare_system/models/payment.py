from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class OEPayment(models.Model):

    _name = 'oeh.payment'
    _description = 'Payments'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'payment_date desc, id desc'

    # ---- Existing fields (preserved) ----
    invoice_id = fields.Many2one(
        'account.move',
        string='Customer Invoice',
        required=True,
        domain=[('move_type', '=', 'out_invoice')],
    )

    billing_id = fields.Many2one(
        'oeh.billing', string='Hospital Bill', ondelete='set null', index=True,
    )
    standard_payment_id = fields.Many2one(
        'account.payment', string='Odoo Payment', readonly=True, copy=False,
    )

    payment_date = fields.Date(required=True, default=fields.Date.context_today)

    amount = fields.Float(required=True)

    payment_method = fields.Selection([
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('upi', 'UPI'),
        ('bank', 'Bank')
    ], required=True)

    reference = fields.Char()

    # ---- Professional additions ----
    name = fields.Char(
        string='Receipt No', default='New', readonly=True, copy=False,
        index=True, tracking=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancel', 'Cancelled'),
    ], default='draft', tracking=True, copy=False)

    payment_kind = fields.Selection([
        ('regular', 'Regular'),
        ('advance', 'Advance'),
        ('refund', 'Refund'),
    ], string='Type', default='regular', tracking=True)

    patient_id = fields.Many2one(
        'oeh.patient', compute='_compute_patient', store=True, readonly=True)

    @api.depends('invoice_id.partner_id')
    def _compute_patient(self):
        Patient = self.env['oeh.patient']
        for rec in self:
            rec.patient_id = Patient.search([('partner_id', '=', rec.invoice_id.partner_id.id)], limit=1) if rec.invoice_id.partner_id else False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') in (False, 'New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'oeh.payment') or 'New'
        return super().create(vals_list)

    @api.depends('name', 'amount', 'invoice_id')
    def _compute_display_name(self):
        for rec in self:
            if rec.name and rec.name != 'New':
                rec.display_name = '%s (%s)' % (rec.name, rec.amount)
            elif rec.invoice_id:
                rec.display_name = rec.invoice_id.display_name
            else:
                rec.display_name = _('New Payment')

    @api.constrains('amount')
    def _check_amount_positive(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_("Payment amount must be greater than zero."))

    # ---- Workflow ----
    def action_post(self):
        for rec in self:
            if rec.state != 'draft':
                continue
            invoice = rec.invoice_id
            if invoice.state == 'draft':
                invoice.action_post()
            if invoice.move_type != 'out_invoice':
                raise ValidationError(_('Only customer invoices can receive hospital payments.'))
            if rec.amount > invoice.amount_residual + 0.0001:
                raise ValidationError(_(
                    'Payment amount (%(payment)s) cannot exceed the invoice balance (%(balance)s).'
                ) % {'payment': rec.amount, 'balance': invoice.amount_residual})
            journal_type = 'cash' if rec.payment_method == 'cash' else 'bank'
            journal = self.env['account.journal'].search([
                ('company_id', '=', invoice.company_id.id),
                ('type', '=', journal_type),
            ], order='sequence, id', limit=1)
            if not journal:
                raise ValidationError(_(
                    'No %(type)s journal is configured for company %(company)s.'
                ) % {'type': journal_type, 'company': invoice.company_id.name})
            method_line = journal.inbound_payment_method_line_ids[:1]
            if not method_line:
                raise ValidationError(_(
                    'No inbound payment method is configured on journal %(journal)s.'
                ) % {'journal': journal.display_name})
            payment = self.env['account.payment'].create({
                'payment_type': 'inbound',
                'partner_type': 'customer',
                'partner_id': invoice.partner_id.id,
                'amount': rec.amount,
                'date': rec.payment_date,
                'journal_id': journal.id,
                'payment_method_line_id': method_line.id,
                'memo': rec.reference or rec.name,
            })
            payment.action_post()
            receivable_invoice = invoice.line_ids.filtered(
                lambda line: line.account_id.account_type == 'asset_receivable' and not line.reconciled
            )
            receivable_payment = payment.move_id.line_ids.filtered(
                lambda line: line.account_id.account_type == 'asset_receivable' and not line.reconciled
            )
            if receivable_invoice and receivable_payment:
                (receivable_invoice + receivable_payment).reconcile()
            rec.write({'state': 'posted', 'standard_payment_id': payment.id})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_reset(self):
        self.write({'state': 'draft'})
