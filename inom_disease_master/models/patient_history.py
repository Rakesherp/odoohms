from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PatientHistory(models.Model):
    _inherit = 'patient.history'

    disease_id = fields.Many2one(
        'oeh.disease',
        string='Disease',
        index=True,
        ondelete='restrict',
        domain=[('active', '=', True)],
        help='Select the disease from the Disease Master.',
    )

    @api.onchange('disease_id')
    def _onchange_disease_id(self):
        """Keep the legacy required Char field in sync with Disease Master."""
        for record in self:
            if record.disease_id:
                record.disease = record.disease_id.name

    @api.model_create_multi
    def create(self, vals_list):
        """Populate the legacy required `disease` field from `disease_id`.

        The original patient.history model has a required Char field named
        `disease`. We keep it for backward compatibility while exposing the
        new Disease Master Many2one in the UI.
        """
        for vals in vals_list:
            disease_id = vals.get('disease_id')
            if disease_id and not vals.get('disease'):
                disease = self.env['oeh.disease'].browse(disease_id)
                if disease.exists():
                    vals['disease'] = disease.name
            elif not disease_id and vals.get('disease'):
                disease = self.env['oeh.disease'].search([('name', '=', vals['disease']), ('active', '=', True)], limit=1)
                if disease:
                    vals['disease_id'] = disease.id
            if not vals.get('disease_id'):
                raise ValidationError('Please select a Disease from Disease Master.')
        return super().create(vals_list)

    def write(self, vals):
        """Keep the legacy disease text synchronized when Disease changes."""
        if vals.get('disease_id'):
            disease = self.env['oeh.disease'].browse(vals['disease_id'])
            if disease.exists():
                vals = dict(vals)
                vals['disease'] = disease.name
        return super().write(vals)
