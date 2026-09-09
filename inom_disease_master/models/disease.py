from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class Disease(models.Model):
    _name = 'oeh.disease'
    _description = 'Disease Master'
    _order = 'name'
    _rec_name = 'name'

    code = fields.Char(
        string='Disease Code',
        required=True,
        index=True,
        help='ICD-10-style disease code used for the disease master.'
    )
    name = fields.Char(
        string='Disease Name',
        required=True,
        index=True,
    )
    category = fields.Char(
        string='Disease Category',
        required=True,
        index=True,
        help='Legacy text category retained for backward compatibility.',
    )
    category_id = fields.Many2one(
        'oeh.disease.category',
        string='Disease Category Master',
        index=True,
        ondelete='restrict',
        domain=[('active', '=', True)],
    )
    description = fields.Text(string='Description')
    active = fields.Boolean(string='Active', default=True)

    _sql_constraints = [
        (
            'disease_code_uniq',
            'unique(code)',
            'Disease code must be unique.'
        ),
    ]

    @api.onchange('category_id')
    def _onchange_category_id(self):
        if self.category_id:
            self.category = self.category_id.name

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('category_id') and not vals.get('category'):
                category = self.env['oeh.disease.category'].browse(vals['category_id']).exists()
                if category:
                    vals['category'] = category.name
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('category_id'):
            category = self.env['oeh.disease.category'].browse(vals['category_id']).exists()
            if category:
                vals = dict(vals)
                vals['category'] = category.name
        return super().write(vals)

    @api.constrains('code', 'name')
    def _check_required_text(self):
        for record in self:
            if not record.code or not record.code.strip():
                raise ValidationError(_('Disease Code cannot be empty.'))
            if not record.name or not record.name.strip():
                raise ValidationError(_('Disease Name cannot be empty.'))


class DiseaseCategory(models.Model):
    _name = 'oeh.disease.category'
    _description = 'Disease Category'
    _order = 'name'

    name = fields.Char(required=True, index=True)
    description = fields.Text()
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('disease_category_name_uniq', 'unique(name)', 'Disease category must be unique.'),
    ]
