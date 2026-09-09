from odoo import models, fields


class ProductProductConsultation(models.Model):
    _inherit = 'product.product'

    is_consultation_bill = fields.Boolean(
        string='Consultation Bill',
        help="Mark this as the standard product used on the invoice line "
             "when a doctor consultation invoice is auto-generated from an "
             "appointment marked Done. Mark exactly one product - if none "
             "is marked, the invoice line falls back to a plain text line "
             "naming the doctor.",
    )


class AccountMoveConsultation(models.Model):
    _inherit = 'account.move'

    is_consultation_bill = fields.Boolean(
        string='Consultation Bill', readonly=True, copy=False,
        help="Automatically set when this Customer Invoice was "
             "auto-generated from an appointment marked Done (doctor "
             "consulting fee).",
    )
