from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class OEBed(models.Model):
    _name = 'oeh.bed'
    _description = 'Hospital Bed'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    # ---- Existing fields (preserved) ----
    name = fields.Char(required=True, tracking=True)
    ward_id = fields.Many2one('oeh.ward', required=True, tracking=True)

    # NOTE: original keys (free/occupied/maintenance) kept for compatibility;
    # new professional states appended.
    status = fields.Selection([
        ('free', 'Free'),
        ('reserved', 'Reserved'),
        ('occupied', 'Occupied'),
        ('cleaning', 'Cleaning'),
        ('maintenance', 'Maintenance'),
    ], default='free', tracking=True)

    # ---- Professional additions ----
    code = fields.Char(string='Bed Ref', default='New', readonly=True, copy=False, index=True)
    bed_type = fields.Selection([
        ('standard', 'Standard'),
        ('electric', 'Electric'),
        ('icu', 'ICU'),
        ('pediatric', 'Pediatric'),
    ], default='standard')
    current_patient_id = fields.Many2one('oeh.patient', string='Current Patient', readonly=True)
    active = fields.Boolean(default=True)
    is_available = fields.Boolean(string='Available', compute='_compute_is_available')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') in (False, 'New'):
                vals['code'] = self.env['ir.sequence'].next_by_code('oeh.bed') or 'New'
        return super().create(vals_list)

    def _compute_is_available(self):
        for rec in self:
            rec.is_available = rec.active and rec.status == 'free'

    @api.constrains('ward_id', 'status', 'current_patient_id')
    def _check_bed_consistency(self):
        for rec in self:
            if rec.status == 'occupied' and not rec.current_patient_id:
                raise ValidationError(_('An occupied bed must have a current patient.'))
            if rec.status in ('free', 'reserved', 'cleaning', 'maintenance') and rec.current_patient_id:
                raise ValidationError(_('Only an occupied bed can have a current patient.'))
            if rec.ward_id and rec.ward_id.state != 'active' and rec.status in ('free', 'reserved'):
                # Closed/maintenance wards should not expose new beds for allocation.
                continue

    # ---- Bed allocation workflow ----
    def action_reserve(self):
        for rec in self:
            if rec.status == 'occupied':
                raise ValidationError(_("Bed %s is occupied and cannot be reserved.") % rec.name)
            rec.status = 'reserved'

    def action_occupy(self):
        for rec in self:
            if rec.status == 'occupied' and rec.current_patient_id:
                raise ValidationError(_(
                    "Bed %(bed)s is already occupied by %(patient)s.") % {
                    'bed': rec.name, 'patient': rec.current_patient_id.name})
        for rec in self:
            if not rec.active:
                raise ValidationError(_('Inactive beds cannot be occupied.'))
            if rec.status != 'free':
                raise ValidationError(_('Only a free bed can be occupied manually.'))
        self.write({'status': 'occupied'})

    def action_free(self):
        for rec in self:
            if rec.status == 'occupied':
                raise ValidationError(_('Discharge the patient before marking an occupied bed as free.'))
        self.write({'status': 'free', 'current_patient_id': False})

    def action_cleaning(self):
        self.write({'status': 'cleaning'})

    def action_maintenance(self):
        self.write({'status': 'maintenance'})
