from odoo import models, fields, api, _


class OEICU(models.Model):
    _name = 'oeh.icu'
    _description = 'ICU Critical Care'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'patient_id'

    # ---- Existing fields (preserved) ----
    patient_id = fields.Many2one('oeh.patient', required=True, tracking=True)
    apache_score = fields.Integer()
    sofa_score = fields.Integer()
    oxygen_level = fields.Float()
    notes = fields.Text()

    # ---- Professional additions ----
    name = fields.Char(string='ICU Ref', default='New', readonly=True, copy=False, index=True)
    bed_id = fields.Many2one('oeh.bed', string='ICU Bed', tracking=True)
    attending_doctor_id = fields.Many2one('oeh.doctor', string='Intensivist', tracking=True)
    nurse_in_charge = fields.Char(string='Nurse In-Charge')
    admission_date = fields.Datetime(default=fields.Datetime.now, tracking=True)

    status = fields.Selection([
        ('monitoring', 'Monitoring'),
        ('critical', 'Critical'),
        ('stable', 'Stable'),
        ('recovered', 'Recovered'),
        ('discharged', 'Discharged'),
    ], default='monitoring', tracking=True)
    is_critical = fields.Boolean(string='Critical Alert', tracking=True)

    # Equipment support structure
    on_ventilator = fields.Boolean(string='On Ventilator')
    on_monitor = fields.Boolean(string='On Monitor')

    # Vitals integration structure
    heart_rate = fields.Integer(string='Heart Rate (bpm)')
    bp_systolic = fields.Integer(string='BP Systolic')
    bp_diastolic = fields.Integer(string='BP Diastolic')
    temperature = fields.Float(string='Temperature (°C)')
    respiratory_rate = fields.Integer(string='Respiratory Rate')
    shift_notes = fields.Text(string='Shift Notes')
    vitals_history_ids = fields.One2many(
        'oeh.icu.vitals.history', 'icu_id', string='Vitals History', readonly=True
    )

    def _snapshot_vitals(self):
        History = self.env['oeh.icu.vitals.history']
        for rec in self:
            History.create({
                'icu_id': rec.id,
                'recorded_at': fields.Datetime.now(),
                'recorded_by': self.env.user.id,
                'heart_rate': rec.heart_rate,
                'bp_systolic': rec.bp_systolic,
                'bp_diastolic': rec.bp_diastolic,
                'temperature': rec.temperature,
                'respiratory_rate': rec.respiratory_rate,
                'oxygen_level': rec.oxygen_level,
                'notes': rec.shift_notes or False,
            })

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') in (False, 'New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('oeh.icu') or 'New'
        records = super().create(vals_list)
        # Keep the initial/current vital set as the first immutable history line.
        records._snapshot_vitals()
        return records

    def write(self, vals):
        vital_fields = {
            'heart_rate', 'bp_systolic', 'bp_diastolic', 'temperature',
            'respiratory_rate', 'oxygen_level', 'shift_notes'
        }
        changed = bool(vital_fields.intersection(vals))
        result = super().write(vals)
        if changed:
            self._snapshot_vitals()
        return result

    @api.depends('name', 'patient_id')
    def _compute_display_name(self):
        for rec in self:
            if rec.name and rec.name != 'New':
                rec.display_name = '%s - %s' % (rec.name, rec.patient_id.display_name or '')
            else:
                rec.display_name = rec.patient_id.display_name or _('ICU Record')

    # ---- Workflow ----
    def action_set_critical(self):
        self.write({'status': 'critical', 'is_critical': True})

    def action_set_stable(self):
        self.write({'status': 'stable', 'is_critical': False})

    def action_set_recovered(self):
        self.write({'status': 'recovered'})

    def action_discharge(self):
        for rec in self:
            rec.status = 'discharged'
            if rec.bed_id:
                rec.bed_id.write({'status': 'cleaning', 'current_patient_id': False})


class OEICUVitalsHistory(models.Model):
    _name = 'oeh.icu.vitals.history'
    _description = 'ICU Vitals History'
    _order = 'recorded_at desc, id desc'

    icu_id = fields.Many2one(
        'oeh.icu',
        string='ICU Record',
        required=True,
        ondelete='cascade',
        index=True,
    )
    recorded_at = fields.Datetime(
        string='Recorded At',
        required=True,
        default=fields.Datetime.now,
        readonly=True,
    )
    recorded_by = fields.Many2one(
        'res.users',
        string='Recorded By',
        required=True,
        readonly=True,
        default=lambda self: self.env.user,
    )
    heart_rate = fields.Integer(string='Heart Rate (bpm)', readonly=True)
    bp_systolic = fields.Integer(string='BP Systolic', readonly=True)
    bp_diastolic = fields.Integer(string='BP Diastolic', readonly=True)
    temperature = fields.Float(string='Temperature (°C)', readonly=True)
    respiratory_rate = fields.Integer(string='Respiratory Rate', readonly=True)
    oxygen_level = fields.Float(string='Oxygen / SpO₂ (%)', readonly=True)
    notes = fields.Text(string='Shift Notes', readonly=True)
