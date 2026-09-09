from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class OEMedicineBatch(models.Model):

    _name = 'oeh.medicine.batch'
    _description = 'Medicine Batch'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'batch_no'
    _order = 'expiry_date asc'

    batch_no = fields.Char(required=True, tracking=True)

    # Medicine batches are linked directly to product.product
    product_id = fields.Many2one(
        'product.product',
        string='Medicine',
        required=True,
        ondelete='cascade',
        tracking=True,
        domain=[('is_medicine', '=', True)],
    )

    mfg_date = fields.Date(string='Mfg. Date')
    expiry_date = fields.Date(string='Expiry Date', required=True, tracking=True)
    quantity = fields.Float(string='Batch Qty', required=True)

    status = fields.Selection([
        ('available', 'Available'),
        ('exhausted', 'Exhausted'),
        ('quarantine', 'Quarantine'),
        ('returned', 'Returned'),
    ], default='available', tracking=True)

    is_expired = fields.Boolean(compute='_compute_is_expired')

    expiry_status = fields.Selection([
        ('ok', 'OK'),
        ('near', 'Expiring Soon'),
        ('expired', 'Expired'),
    ], compute='_compute_expiry_status')

    @api.depends('expiry_date')
    def _compute_is_expired(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_expired = bool(rec.expiry_date and rec.expiry_date < today)

    @api.depends('expiry_date')
    def _compute_expiry_status(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.expiry_date:
                rec.expiry_status = 'ok'
                continue
            delta = (rec.expiry_date - today).days
            if delta < 0:
                rec.expiry_status = 'expired'
            elif delta <= 90:
                rec.expiry_status = 'near'
            else:
                rec.expiry_status = 'ok'

    @api.constrains('quantity')
    def _check_quantity(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError(_('Batch quantity must be greater than zero.'))