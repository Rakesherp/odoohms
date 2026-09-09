from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

DURATION_UOM_DAYS = {'days': 1, 'weeks': 7, 'months': 30}


class PrescriptionLine(models.Model):
    """
    One medicine within a prescription.

    medicine_id now points directly to product.product
    (filtered to is_medicine = True), using the product.product medicine master.
    All other dosage logic is unchanged.
    """

    _name = 'oeh.prescription.line'
    _description = 'Prescription Line'
    _order = 'sequence, id'

    prescription_id = fields.Many2one(
        'oeh.prescription', required=True, ondelete='cascade', index=True,
    )
    sequence = fields.Integer(default=10)

    patient_id = fields.Many2one(
        related='prescription_id.patient_id', store=True, readonly=True,
    )

    # Medicine selection uses product.product directly.
    product_id = fields.Many2one(
        'product.product',
        string='Medicine',
        required=True,
        domain=[('is_medicine', '=', True)],
        help='Select from medicines (products flagged as Is Medicine).',
    )

    route = fields.Selection([
        ('oral', 'Oral (Tablet/Capsule/Syrup)'),
        ('topical', 'Topical (Cream/Ointment)'),
        ('injection', 'Injection'),
        ('drops', 'Drops (Eye/Ear/Nasal)'),
        ('inhalation', 'Inhalation'),
        ('other', 'Other'),
    ], required=True, default='oral')

    dose_morning = fields.Float(string='Morning', default=1.0)
    dose_afternoon = fields.Float(string='Afternoon', default=0.0)
    dose_evening = fields.Float(string='Evening', default=0.0)
    dose_night = fields.Float(string='Night', default=0.0)

    dose_uom = fields.Selection([
        ('tablet', 'Tablet(s)'),
        ('capsule', 'Capsule(s)'),
        ('ml', 'ml'),
        ('drop', 'Drop(s)'),
        ('unit', 'Unit(s)/Puff(s)'),
        ('application', 'Application(s)'),
    ], default='tablet', required=True)

    frequency_display = fields.Char(
        string='Frequency', compute='_compute_frequency_display', store=True,
    )

    food_timing = fields.Selection([
        ('before_food', 'Before Food'),
        ('after_food', 'After Food'),
        ('with_food', 'With Food'),
        ('empty_stomach', 'Empty Stomach'),
        ('anytime', 'Anytime'),
    ], required=True, default='after_food')

    is_sos = fields.Boolean(string='SOS / As Needed')

    duration_value = fields.Integer(string='Duration', default=5)
    duration_uom = fields.Selection([
        ('days', 'Day(s)'),
        ('weeks', 'Week(s)'),
        ('months', 'Month(s)'),
    ], default='days', required=True)

    total_qty = fields.Float(
        string='Total Qty',
        compute='_compute_total_qty',
        store=True,
    )

    instructions = fields.Char(string='Special Instructions')

    # ── Live inventory availability ───────────────────────────────────
    # Uses Odoo's standard product on-hand quantity (qty_available).
    # This is intentionally not stored so the prescription always shows
    # the latest available stock when the form/list is opened.
    on_hand_stock = fields.Float(
        string='On Hand Stock',
        compute='_compute_on_hand_stock',
        digits='Product Unit of Measure',
        readonly=True,
    )

    stock_status = fields.Selection([
        ('critical', 'Critical'),
        ('available', 'Available'),
    ], string='Stock Status', compute='_compute_on_hand_stock', readonly=True)

    # ── Computes ──────────────────────────────────────────────────────

    @api.depends('product_id', 'product_id.qty_available')
    def _compute_on_hand_stock(self):
        for rec in self:
            qty = rec.product_id.qty_available if rec.product_id else 0.0
            rec.on_hand_stock = qty
            if qty < rec.product_id.min_stock:
                rec.stock_status = 'critical'
            elif qty == rec.product_id.min_stock:
                rec.stock_status = 'critical'
            else:
                rec.stock_status = 'available'

    @api.depends('dose_morning', 'dose_afternoon', 'dose_evening', 'dose_night')
    def _compute_frequency_display(self):
        for rec in self:
            parts = [rec.dose_morning, rec.dose_afternoon,
                     rec.dose_evening, rec.dose_night]
            rec.frequency_display = '-'.join(
                (str(int(p)) if p == int(p) else str(p)) for p in parts
            )

    @api.depends('dose_morning', 'dose_afternoon', 'dose_evening', 'dose_night',
                 'duration_value', 'duration_uom', 'is_sos')
    def _compute_total_qty(self):
        for rec in self:
            if rec.is_sos:
                rec.total_qty = 0.0
                continue
            per_day = (rec.dose_morning + rec.dose_afternoon
                       + rec.dose_evening + rec.dose_night)
            days = (rec.duration_value or 0) * DURATION_UOM_DAYS.get(rec.duration_uom, 1)
            rec.total_qty = per_day * days

    @api.depends('product_id', 'frequency_display', 'food_timing')
    def _compute_display_name(self):
        food_labels = dict(self._fields['food_timing'].selection)
        for rec in self:
            rec.display_name = '%s (%s, %s)' % (
                rec.product_id.name or _('Medicine'),
                rec.frequency_display or '',
                food_labels.get(rec.food_timing, ''),
            )

    # ── Validation ────────────────────────────────────────────────────

    @api.constrains('dose_morning', 'dose_afternoon', 'dose_evening',
                    'dose_night', 'is_sos', 'duration_value')
    def _check_dosage(self):
        for rec in self:
            doses = [rec.dose_morning, rec.dose_afternoon,
                     rec.dose_evening, rec.dose_night]
            if any(d < 0 for d in doses):
                raise ValidationError(_('Dosage quantities cannot be negative.'))
            if not rec.is_sos and sum(doses) <= 0:
                raise ValidationError(_(
                    '%(med)s: enter dosage for at least one time of day, '
                    "or tick 'SOS / As Needed'.")
                    % {'med': rec.product_id.name or ''})
            if not rec.is_sos and rec.duration_value <= 0:
                raise ValidationError(_(
                    '%(med)s: duration must be greater than zero.')
                    % {'med': rec.product_id.name or ''})