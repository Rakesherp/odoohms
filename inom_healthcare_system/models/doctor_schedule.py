from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class DoctorSchedule(models.Model):
    """Weekly recurring clinic schedule template for a doctor.

    Each row = one session (Morning / Afternoon / Evening) the doctor runs
    on a given weekday. This is the template used to:
      1. Validate that an appointment is booked inside a real consulting
         window (see oeh.appointment._check_doctor_availability).
      2. Cap the number of tokens per session (max_tokens) so the front
         desk / online booking cannot overbook a session.
    Actual token numbering (with the daily reset) lives on oeh.queue,
    scoped by (doctor_id, queue_date, session) - see models/queue.py.
    """

    _name = 'doctor.schedule'
    _description = 'Doctor Weekly Session Schedule'
    _rec_name = 'doctor_id'
    _order = 'doctor_id, day, session'

    doctor_id = fields.Many2one(
        'oeh.doctor',
        required=True,
        ondelete='cascade',
        index=True,
    )

    day = fields.Selection([
        ('mon', 'Monday'),
        ('tue', 'Tuesday'),
        ('wed', 'Wednesday'),
        ('thu', 'Thursday'),
        ('fri', 'Friday'),
        ('sat', 'Saturday'),
        ('sun', 'Sunday'),
    ], required=True)

    session = fields.Selection([
        ('morning', 'Morning'),
        ('afternoon', 'Afternoon'),
        ('evening', 'Evening'),
    ], required=True, default='morning',
        help="A doctor can run separate Morning / Afternoon / Evening "
             "sessions on the same day, each with its own token series.")

    start_time = fields.Float(required=True, help="24h format, e.g. 9.5 = 9:30 AM")

    end_time = fields.Float(required=True, help="24h format, e.g. 13.0 = 1:00 PM")

    max_tokens = fields.Integer(
        string='Max Tokens',
        default=30,
        help="Maximum patients this doctor will see in this session. "
             "Used to warn / block booking once the session is full.")

    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('doctor_day_session_uniq',
         'unique(doctor_id, day, session)',
         'This doctor already has a schedule for this day and session. '
         'Edit the existing row instead of creating a duplicate.'),
    ]

    @api.constrains('start_time', 'end_time')
    def _check_time_window(self):
        for rec in self:
            if rec.start_time >= rec.end_time:
                raise ValidationError(_(
                    "Session end time must be after the start time (%s).")
                    % rec.doctor_id.name)
            if not (0.0 <= rec.start_time < 24.0) or not (0.0 < rec.end_time <= 24.0):
                raise ValidationError(_("Times must be between 0:00 and 24:00."))

    @api.depends('doctor_id', 'day', 'session')
    def _compute_display_name(self):
        # Odoo 19: name_get() is deprecated - use _compute_display_name instead.
        day_labels = dict(self._fields['day'].selection)
        session_labels = dict(self._fields['session'].selection)
        for rec in self:
            rec.display_name = "%s - %s (%s)" % (
                rec.doctor_id.name or '',
                day_labels.get(rec.day, ''),
                session_labels.get(rec.session, ''),
            )
