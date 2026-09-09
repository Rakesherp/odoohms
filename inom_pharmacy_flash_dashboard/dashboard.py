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

        medicines = Product.search([
            ('is_medicine', '=', True),
            ('is_storable', '=', True),
        ])
        low_stock = medicines.filtered(
            lambda p: p.qty_available <= p.min_stock
        ).sorted(
            key=lambda p: (p.qty_available, p.name or '')
        )[:30]

        low_stock_items = []
        for product in low_stock:
            qty = float(product.qty_available or 0.0)
            minimum = float(product.min_stock or 0.0)
            if minimum <= 0 or qty <= minimum * 0.25:
                level, label = 'critical', 'Critical'
            else:
                level, label = 'warning', 'Low'
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

        cutoff = today + timedelta(days=90)
        lots = Lot.search([
            ('product_id.is_medicine', '=', True),
            ('expiration_date', '!=', False),
            ('expiration_date', '<=', cutoff),
        ], order='expiration_date asc, product_id asc, name asc')

        lot_qty = {}
        if lots:
            quants = Quant.search([
                ('lot_id', 'in', lots.ids),
                ('location_id.usage', '=', 'internal'),
            ])
            for quant in quants:
                lot_qty[quant.lot_id.id] = (
                    lot_qty.get(quant.lot_id.id, 0.0)
                    + float(quant.quantity or 0.0)
                )

        expiry_items = []
        for lot in lots:
            quantity = lot_qty.get(lot.id, 0.0)
            if quantity <= 0:
                continue

            days_left = (lot.expiration_date - today).days
            if days_left < 0:
                level, label = 'expired', 'Expired'
            elif days_left <= 7:
                level, label = 'critical', 'Urgent'
            elif days_left <= 30:
                level, label = 'warning', 'Expiring Soon'
            else:
                level, label = 'notice', 'Upcoming'

            expiry_items.append({
                'id': lot.id,
                'lot_name': lot.name or '',
                'medicine': lot.product_id.display_name,
                'expiry_date': fields.Date.to_string(lot.expiration_date),
                'quantity': quantity,
                'uom': lot.product_id.uom_id.name or 'Units',
                'days_left': days_left,
                'level': level,
                'level_label': label,
            })
            if len(expiry_items) >= 30:
                break

        return {
            'today': fields.Date.to_string(today),
            'total_medicines': len(medicines),
            'low_stock': {
                'count': len(low_stock_items),
                'items': low_stock_items,
            },
            'expiry': {
                'count': len(expiry_items),
                'items': expiry_items,
            },
        }

    @api.model
    def action_open_expiry_batches(self):
        today = fields.Date.context_today(self)
        cutoff = today + timedelta(days=90)

        # IMPORTANT: include an explicit views list. Odoo 19's client action
        # preprocessing expects action.views to be present.
        return {
            'type': 'ir.actions.act_window',
            'name': 'Expiring / Expired Medicine Lots',
            'res_model': 'stock.lot',
            'view_mode': 'list,form',
            'views': [
                [False, 'list'],
                [False, 'form'],
            ],
            'domain': [
                ('product_id.is_medicine', '=', True),
                ('expiration_date', '!=', False),
                ('expiration_date', '<=', cutoff),
            ],
            'target': 'current',
        }
