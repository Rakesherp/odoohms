from odoo import models, fields, api


class ProductProductMedicine(models.Model):
    """
    Extends product.product with pharmacy / clinical fields.
    Uses product.product as the single medicine master.

    Why product.product (not product.template)?
    - Prescriptions and stock moves reference product.product (variant level).
    - Barcode, qty_available, and stock.move are all on product.product.
    - Using product.template would require an extra join for every stock check.

    The standard product fields we reuse directly (no duplication):
        name, barcode, uom_id, list_price, taxes_id, qty_available,
        default_code, categ_id, purchase_ok, sale_ok, type/is_storable
    """

    _inherit = 'product.product'

    # ── Clinical classification ──────────────────────────────────────
    is_medicine = fields.Boolean(
        string='Is Medicine',
        default=False,
        index=True,
        help='Mark this product as a dispensable medicine. '
             'Only medicines appear in prescription line medicine selector.',
    )
    medicine_type = fields.Selection([
        ('tablet', 'Tablet'),
        ('capsule', 'Capsule'),
        ('syrup', 'Syrup'),
        ('drops', 'Drops'),
        ('injection', 'Injection'),
        ('cream', 'Cream / Ointment'),
        ('inhaler', 'Inhaler'),
        ('powder', 'Powder'),
        ('other', 'Other'),
    ], string='Medicine Form', default='tablet')

    generic_name = fields.Char(string='Generic Name')
    brand_name = fields.Char(string='Brand Name')
    strength = fields.Char(string='Strength', help='e.g. 500 mg, 250 mg/5 ml')
    is_generic = fields.Boolean(string='Generic Medicine')

    drug_category = fields.Selection([
        ('antibiotic', 'Antibiotic'),
        ('analgesic', 'Analgesic'),
        ('antipyretic', 'Antipyretic'),
        ('antacid', 'Antacid'),
        ('antiseptic', 'Antiseptic'),
        ('vaccine', 'Vaccine'),
        ('supplement', 'Supplement'),
        ('other', 'Other'),
    ], default='other', string='Drug Category')

    is_controlled = fields.Boolean(
        string='Controlled Substance',
        help='Schedule H / H1 / X — requires special regulatory handling.',
    )
    dosage_info = fields.Char(string='Dosage Information')
    storage_instructions = fields.Text(string='Storage Instructions')
    manufacturer_id = fields.Many2one('res.partner', string='Manufacturer')

    # ── Stock threshold ──────────────────────────────────────────────
    min_stock = fields.Float(
        string='Min Stock Level',
        default=5.0,
    )
    
    is_low_stock = fields.Boolean(
        string='Low Stock',
        compute='_compute_is_low_stock',
        search='_search_is_low_stock',
        help='Live stock warning calculated from current on-hand quantity and minimum stock.',
    )

    # ── Batch tracking (optional clinical layer) ─────────────────────
    medicine_batch_ids = fields.One2many(
        'oeh.medicine.batch', 'product_id', string='Batches',
    )
    batch_count = fields.Integer(compute='_compute_batch_count', store=True)
    nearest_expiry = fields.Date(compute='_compute_nearest_expiry', store=True)

    # ── Prescription smart button ────────────────────────────────────
    prescription_line_count = fields.Integer(
        compute='_compute_prescription_line_count',
    )

    # ────────────────────────────────────────────────────────────────
    # Computes
    # ────────────────────────────────────────────────────────────────

    @api.depends('qty_available', 'min_stock', 'is_storable', 'is_medicine')
    def _compute_is_low_stock(self):
        for product in self:
            product.is_low_stock = bool(
                product.is_medicine
                and product.is_storable
                and product.qty_available <= product.min_stock
            )

    @api.model
    def _search_is_low_stock(self, operator, value):
        """Search the live low-stock flag without storing qty_available in SQL."""
        if operator not in ('=', '!='):
            return [('id', '=', 0)]
        want_true = bool(value)
        products = self.search([('is_medicine', '=', True)])
        low_stock_ids = products.filtered(
            lambda p: p.is_storable and p.qty_available <= p.min_stock
        ).ids
        if (operator == '=' and want_true) or (operator == '!=' and not want_true):
            return [('id', 'in', low_stock_ids)] if low_stock_ids else [('id', '=', 0)]
        return [('id', 'not in', low_stock_ids)] if low_stock_ids else [('id', '!=', 0)]

    @api.depends('medicine_batch_ids')
    def _compute_batch_count(self):
        for rec in self:
            rec.batch_count = len(rec.medicine_batch_ids)

    @api.depends('medicine_batch_ids.expiry_date', 'medicine_batch_ids.status')
    def _compute_nearest_expiry(self):
        for rec in self:
            valid = rec.medicine_batch_ids.filtered(
                lambda b: b.expiry_date and b.status == 'available'
            )
            rec.nearest_expiry = min(valid.mapped('expiry_date')) if valid else False

    def _compute_prescription_line_count(self):
        Line = self.env['oeh.prescription.line']
        for rec in self:
            rec.prescription_line_count = Line.search_count(
                [('product_id', '=', rec.id)]
            )

    # ────────────────────────────────────────────────────────────────
    # Smart button actions
    # ────────────────────────────────────────────────────────────────

    def action_view_stock_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Stock Moves',
            'res_model': 'stock.move',
            'view_mode': 'list,form',
            'domain': [('product_id', '=', self.id)],
        }

    def action_view_batches(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Batches',
            'res_model': 'oeh.medicine.batch',
            'view_mode': 'list,form',
            'domain': [('product_id', '=', self.id)],
            'context': {'default_product_id': self.id},
        }

    def action_view_prescription_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Prescription Lines',
            'res_model': 'oeh.prescription.line',
            'view_mode': 'list,form',
            'domain': [('product_id', '=', self.id)],
        }