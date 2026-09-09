from datetime import timedelta

from odoo import api, fields, models


class PharmacyFlashDashboard(models.Model):
    _name = 'oeh.pharmacy.flash.dashboard'
    _description = 'Pharmacy Flash Dashboard'

    @api.model
    def get_dashboard_data(self):
        Product = self.env['product.product']
        Lot = self.env['stock.lot']
        Quant = self.env['stock.quant']

        today = fields.Date.context_today(self)

        # ================================================================
        # MEDICINES
        # ================================================================

        medicines = Product.search([
            ('is_medicine', '=', True),
            ('is_storable', '=', True),
        ])

        # ================================================================
        # LOW STOCK
        # ================================================================

        low_stock = medicines.filtered(
            lambda p: p.qty_available <= p.min_stock
        ).sorted(
            key=lambda p: (
                p.qty_available,
                p.name or ''
            )
        )[:30]

        low_stock_items = []

        for product in low_stock:

            qty = float(
                product.qty_available or 0.0
            )

            minimum = float(
                product.min_stock or 0.0
            )

            if minimum <= 0 or qty <= minimum * 0.25:
                level = 'critical'
                label = 'Critical'
            else:
                level = 'warning'
                label = 'Low'

            low_stock_items.append({
                'id': product.id,
                'name': product.display_name,
                'generic_name': product.generic_name or '',
                'strength': product.strength or '',
                'on_hand': qty,
                'min_stock': minimum,
                'uom': product.uom_id.name or 'Units',
                'level': level,
                'level_label': label,
            })

        # ================================================================
        # EXPIRING / EXPIRED MEDICINE LOTS
        # ================================================================

        # Show lots expiring within the next 90 days.
        cutoff = today + timedelta(days=90)

        lots = Lot.search([
            ('product_id.is_medicine', '=', True),
            ('expiration_date', '!=', False),
            ('expiration_date', '<=', cutoff),
        ], order='expiration_date asc, product_id asc, name asc')

        # ---------------------------------------------------------------
        # Calculate quantity available for each lot from internal stock.
        # ---------------------------------------------------------------

        lot_qty = {}

        if lots:

            quants = Quant.search([
                ('lot_id', 'in', lots.ids),
                ('location_id.usage', '=', 'internal'),
            ])

            for quant in quants:

                if not quant.lot_id:
                    continue

                lot_id = quant.lot_id.id

                lot_qty[lot_id] = (
                    lot_qty.get(lot_id, 0.0)
                    + float(quant.quantity or 0.0)
                )

        # ---------------------------------------------------------------
        # Build expiry dashboard items.
        # ---------------------------------------------------------------

        expiry_items = []

        for lot in lots:

            quantity = lot_qty.get(
                lot.id,
                0.0
            )

            # Only show lots that currently have stock.
            if quantity <= 0:
                continue

            # -----------------------------------------------------------
            # IMPORTANT FIX:
            #
            # Odoo stock.lot.expiration_date = Datetime
            # fields.Date.context_today() = Date
            #
            # Convert the Datetime to Date before subtraction.
            # -----------------------------------------------------------

            expiration_date = lot.expiration_date

            if hasattr(expiration_date, 'date'):
                expiration_date = expiration_date.date()

            days_left = (
                expiration_date - today
            ).days

            # -----------------------------------------------------------
            # Expiry severity
            # -----------------------------------------------------------

            if days_left < 0:
                level = 'expired'
                label = 'Expired'

            elif days_left <= 7:
                level = 'critical'
                label = 'Urgent'

            elif days_left <= 30:
                level = 'warning'
                label = 'Expiring Soon'

            else:
                level = 'notice'
                label = 'Upcoming'

            expiry_items.append({
                'id': lot.id,

                'lot_name':
                    lot.name or '',

                'medicine':
                    lot.product_id.display_name,

                'expiry_date':
                    fields.Date.to_string(
                        expiration_date
                    ),

                'quantity':
                    quantity,

                'uom':
                    lot.product_id.uom_id.name or 'Units',

                'days_left':
                    days_left,

                'level':
                    level,

                'level_label':
                    label,
            })

            if len(expiry_items) >= 30:
                break

        # ================================================================
        # RETURN DASHBOARD DATA
        # ================================================================

        return {
            'today':
                fields.Date.to_string(today),

            'total_medicines':
                len(medicines),

            'low_stock': {
                'count':
                    len(low_stock_items),

                'items':
                    low_stock_items,
            },

            'expiry': {
                'count':
                    len(expiry_items),

                'items':
                    expiry_items,
            },
        }

    @api.model
    def action_open_expiry_batches(self):
        """Open standard Odoo medicine lots.

        Uses stock.lot instead of the legacy custom medicine batch model.
        """

        today = fields.Date.context_today(self)

        cutoff = today + timedelta(days=90)

        return {
            'type': 'ir.actions.act_window',

            'name':
                'Expiring / Expired Medicine Lots',

            'res_model':
                'stock.lot',

            'view_mode':
                'list,form',

            'views': [
                [False, 'list'],
                [False, 'form'],
            ],

            'domain': [
                ('product_id.is_medicine', '=', True),
                ('expiration_date', '!=', False),
                ('expiration_date', '<=', cutoff),
            ],

            'target':
                'current',
        }