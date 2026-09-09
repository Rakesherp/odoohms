from odoo import fields, models


class MedicalCertificatePhase23(models.Model):
    _inherit = 'oeh.certificate'

    ipd_id = fields.Many2one(
        'oeh.ipd',
        string='IPD Admission',
        tracking=True,
        index=True,
    )
    certificate_language = fields.Selection([
        ('en', 'English'),
        ('ta', 'Tamil'),
    ], string='Language', default='en')
    purpose = fields.Char(
        string='Purpose',
        help='Purpose for which the certificate is issued.',
    )
