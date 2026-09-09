from odoo import api, fields, models, _


class OEBedPhase23(models.Model):
    _inherit = 'oeh.bed'

    current_ipd_id = fields.Many2one(
        'oeh.ipd',
        string='Current Admission',
        compute='_compute_current_ipd',
    )
    last_cleaned_at = fields.Datetime(string='Last Cleaned')
    housekeeping_note = fields.Char(string='Housekeeping Note')

    @api.depends('status', 'current_patient_id')
    def _compute_current_ipd(self):
        IPD = self.env['oeh.ipd']
        for bed in self:
            if bed.status != 'occupied':
                bed.current_ipd_id = False
                continue
            admission = IPD.search([
                ('bed_id', '=', bed.id),
                ('status', 'in', ('admitted', 'under_treatment', 'discharge_pending')),
            ], order='admission_date desc, id desc', limit=1)
            bed.current_ipd_id = admission

    def action_ready_for_patient(self):
        for bed in self:
            bed.write({
                'status': 'free',
                'current_patient_id': False,
                'last_cleaned_at': fields.Datetime.now(),
            })

    def action_open_current_admission(self):
        self.ensure_one()
        if not self.current_ipd_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Current Admission'),
            'res_model': 'oeh.ipd',
            'res_id': self.current_ipd_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
