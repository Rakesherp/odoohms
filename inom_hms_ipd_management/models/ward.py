from odoo import fields, models


class OEWardPhase23(models.Model):
    _inherit = 'oeh.ward'

    nurse_in_charge_id = fields.Many2one(
        'hr.employee',
        string='Ward Nurse In-Charge',
        tracking=True,
        domain=[('active', '=', True)],
    )
