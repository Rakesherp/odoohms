from odoo import fields, models


class OEInsurancePhase23(models.Model):
    _inherit = 'oeh.insurance.claim'

    patient_card_number = fields.Char(string='Insurance / Member ID')
    eligibility_verified = fields.Boolean(string='Eligibility Verified', tracking=True)
    eligibility_verified_date = fields.Date(string='Eligibility Verified Date', tracking=True)
    expected_approval_date = fields.Date(string='Expected Approval Date')
    documents_complete = fields.Boolean(string='Documents Complete', tracking=True)
