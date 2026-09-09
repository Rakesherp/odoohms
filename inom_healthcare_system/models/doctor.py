from odoo import models, fields
from datetime import datetime, time


class HMSDoctor(models.Model):
    _name = 'oeh.doctor'
    _description = 'Doctor'
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        required=True,
        tracking=True
    )

    specialization = fields.Selection([
        ('general_medicine', 'General Medicine'),
        ('general_surgery', 'General Surgery'),
        ('cardiology', 'Cardiology'),
        ('dermatology', 'Dermatology'),
        ('ent', 'ENT'),
        ('gastroenterology', 'Gastroenterology'),
        ('gynecology', 'Gynecology'),
        ('obstetrics', 'Obstetrics'),
        ('neurology', 'Neurology'),
        ('neurosurgery', 'Neurosurgery'),
        ('oncology', 'Oncology'),
        ('ophthalmology', 'Ophthalmology'),
        ('orthopedics', 'Orthopedics'),
        ('pediatrics', 'Pediatrics'),
        ('psychiatry', 'Psychiatry'),
        ('pulmonology', 'Pulmonology'),
        ('radiology', 'Radiology'),
        ('urology', 'Urology'),
        ('nephrology', 'Nephrology'),
        ('endocrinology', 'Endocrinology'),
        ('dentistry', 'Dentistry'),
        ('anesthesiology', 'Anesthesiology'),
        ('pathology', 'Pathology'),
        ('physiotherapy', 'Physiotherapy'),
        ('other', 'Other'),
    ], string='Specialization', index=True)

    phone = fields.Char()

    email = fields.Char()

    schedule_ids = fields.One2many(
        'doctor.schedule',
        'doctor_id'
    )

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee'
    )

    # ------------------------------------------------------------------
    # Portal / self-service access: lets a doctor log into Odoo and see
    # only their own appointments/queue ("My Appointments" filters use
    # this field). Without it there is no way to scope data per-doctor.
    # ------------------------------------------------------------------
    user_id = fields.Many2one(
        'res.users',
        string='User Account',
        tracking=True,
        help="Odoo user account for this doctor. Required for the doctor "
             "to log in and see their own appointment/queue lists filtered "
             "to just their patients.",
    )

    consultation_fee = fields.Float(
        string='Consulting Fee',
        help="Doctor's standard consultation fee. Used to auto-generate "
             "the consultation bill/invoice when one of this doctor's "
             "appointments is marked Done.",
    )

    avg_consult_minutes = fields.Integer(
        string='Avg. Consultation (min)',
        default=15,
        help="Used to detect overlapping/double-booked appointments for "
             "this doctor.",
    )

    active = fields.Boolean(default=True)

    attendance_count = fields.Integer(
        compute='_compute_attendance'
    )

    leave_count = fields.Integer(
        compute='_compute_leave'
    )

    today_token_count = fields.Integer(
        string="Today's Tokens",
        compute='_compute_today_stats',
    )

    now_serving_token = fields.Integer(
        string='Now Serving',
        compute='_compute_today_stats',
        help="Token number currently being consulted (In Progress) today.",
    )

    def _compute_attendance(self):
        for rec in self:
            rec.attendance_count = self.env[
                'hr.attendance'
            ].search_count([
                ('employee_id', '=', rec.employee_id.id)
            ])

    def _compute_leave(self):
        for rec in self:
            rec.leave_count = self.env[
                'hr.leave'
            ].search_count([
                ('employee_id', '=', rec.employee_id.id)
            ])

    def _compute_today_stats(self):
        Queue = self.env['oeh.queue']
        today = fields.Date.context_today(self)
        for rec in self:
            tokens = Queue.search([
                ('doctor_id', '=', rec.id),
                ('queue_date', '=', today),
            ])
            rec.today_token_count = len(tokens)
            in_progress = tokens.filtered(lambda t: t.state == 'in_progress')
            rec.now_serving_token = in_progress[:1].token_no if in_progress else 0

    def action_view_attendance(self):
        self.ensure_one()
        action = self.env.ref(
            'hr_attendance.hr_attendance_action'
        ).read()[0]
        action['domain'] = [
            ('employee_id', '=', self.employee_id.id)
        ]
        return action

    def action_view_leave(self):
        self.ensure_one()
        action = self.env.ref(
            'hr_holidays.hr_leave_action_action_approve_department'
        ).read()[0]
        action['domain'] = [
            ('employee_id', '=', self.employee_id.id)
        ]
        return action

    def action_view_today_appointments(self):
        """Doctor's own 'Today + upcoming' worklist, opened from their profile."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        day_start = fields.Datetime.to_string(datetime.combine(today, time.min))
        return {
            'type': 'ir.actions.act_window',
            'name': "Today's Appointments",
            'res_model': 'oeh.appointment',
            'view_mode': 'list,form,calendar',
            'domain': [
                ('doctor_id', '=', self.id),
                ('appointment_date', '>=', day_start),
                ('state', '!=', 'cancel'),
            ],
            'context': {'default_doctor_id': self.id},
        }
