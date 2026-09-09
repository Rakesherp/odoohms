from odoo import fields, models


class OENursingPhase23(models.Model):
    _inherit = 'oeh.nursing'

    ipd_id = fields.Many2one(
        'oeh.ipd',
        string='IPD Admission',
        tracking=True,
        index=True,
    )
    nurse_in_charge_id = fields.Many2one(
        'hr.employee',
        string='Nurse In-Charge',
        tracking=True,
        domain=[('active', '=', True)],
    )
    handover_notes = fields.Text(
        string='Shift Handover',
        help='Important information to pass to the next nursing shift.',
    )
    pain_score = fields.Integer(string='Pain Score', help='0 = no pain, 10 = worst pain')
    fluid_balance_notes = fields.Text(string='Fluid Balance / I&O Notes')
    fall_risk = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ], string='Fall Risk', default='low')
    isolation_precaution = fields.Boolean(string='Isolation Precaution')
