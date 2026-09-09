from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

from psycopg2 import IntegrityError


class QueueToken(models.Model):
    """Doctor's session token board.

    TOKEN AUTO-NUMBERING / DAILY RESET
    -----------------------------------
    Token numbers are NOT a single global counter. They are computed
    per (doctor_id, queue_date, session) group:

        next token = count of existing tokens for that
                     doctor + date + session, + 1

    This is what gives you the reset behaviour you asked for: Dr. A's
    Morning session and Dr. A's Evening session on the SAME day both
    start at token 1 automatically, because they are different groups.
    Tomorrow, every session starts at 1 again for the same reason.
    No manual "reset" button is needed - and because it is scoped per
    doctor, Dr. A running 20 tokens in the morning has zero effect on
    Dr. B, who might only be on token 12.

    A DB-level unique constraint on (doctor_id, queue_date, session,
    token_no) guarantees two receptionists creating a token at the same
    moment can never end up with the same number for the same doctor/
    session/day.
    """

    _name = 'oeh.queue'
    _description = 'Queue Token'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'token_no'
    _order = 'queue_date desc, session, token_no'

    token_no = fields.Integer(
        readonly=True,
        copy=False,
        tracking=True,
        help="Auto-generated. Resets to 1 for every new doctor/date/session "
             "combination - see model docstring.",
    )

    queue_date = fields.Date(
        required=True,
        default=fields.Date.context_today,
        tracking=True,
        index=True,
    )

    session = fields.Selection([
        ('morning', 'Morning'),
        ('afternoon', 'Afternoon'),
        ('evening', 'Evening'),
    ], required=True, default='morning', tracking=True)

    patient_id = fields.Many2one(
        'oeh.patient',
        string='Patient',
        required=True,
        tracking=True,
    )

    doctor_id = fields.Many2one(
        'oeh.doctor',
        string='Doctor',
        required=True,
        tracking=True,
        index=True,
    )

    appointment_id = fields.Many2one(
        'oeh.appointment',
        string='Appointment',
        copy=False,
        help="Set automatically when the token is generated from a "
             "confirmed appointment. Empty for walk-in tokens issued "
             "directly at the front desk.",
    )

    check_in_time = fields.Datetime(readonly=True)
    called_time = fields.Datetime(readonly=True, copy=False)
    done_time = fields.Datetime(readonly=True, copy=False)

    state = fields.Selection([
        ('scheduled', 'Scheduled'),
        ('waiting', 'Waiting'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('no_show', 'No Show'),
        ('cancel', 'Cancelled'),
    ], default='waiting', tracking=True)

    _sql_constraints = [
        ('token_doctor_date_session_uniq',
         'unique(doctor_id, queue_date, session, token_no)',
         'This token number is already used for this doctor on this date '
         'and session.'),
    ]

    @api.model
    def _next_token_no(self, doctor_id, queue_date, session):
        """Compute the next token number for a doctor/date/session group."""
        last = self.search([
            ('doctor_id', '=', doctor_id),
            ('queue_date', '=', queue_date),
            ('session', '=', session),
        ], order='token_no desc', limit=1)
        return (last.token_no or 0) + 1

    @api.model_create_multi
    def create(self, vals_list):
        records = self.env[self._name].browse()
        for original_vals in vals_list:
            vals = dict(original_vals)
            doctor_id = vals.get('doctor_id')
            queue_date = vals.get('queue_date') or fields.Date.context_today(self)
            session = vals.get('session') or 'morning'
            if not doctor_id:
                raise ValidationError(_('Doctor is required before a token can be created.'))
            if not vals.get('token_no'):
                vals['token_no'] = self._next_token_no(doctor_id, queue_date, session)
            if vals.get('state') == 'scheduled':
                vals['check_in_time'] = False
            else:
                vals.setdefault('check_in_time', fields.Datetime.now())
            try:
                with self.env.cr.savepoint():
                    record = super(QueueToken, self).create([vals])
                    records |= record
            except IntegrityError:
                vals['token_no'] = self._next_token_no(doctor_id, queue_date, session)
                record = super(QueueToken, self).create([vals])
                records |= record
        return records

    @api.constrains('doctor_id', 'queue_date', 'session')
    def _check_session_capacity(self):
        Schedule = self.env['doctor.schedule']
        day_map = {'0': 'mon', '1': 'tue', '2': 'wed', '3': 'thu',
                   '4': 'fri', '5': 'sat', '6': 'sun'}
        for rec in self:
            weekday = day_map.get(str(rec.queue_date.weekday())) if rec.queue_date else False
            schedule = Schedule.search([
                ('doctor_id', '=', rec.doctor_id.id),
                ('day', '=', weekday),
                ('session', '=', rec.session),
            ], limit=1)
            if schedule and schedule.max_tokens:
                count = self.search_count([
                    ('doctor_id', '=', rec.doctor_id.id),
                    ('queue_date', '=', rec.queue_date),
                    ('session', '=', rec.session),
                    ('state', '!=', 'cancel'),
                ])
                if count > schedule.max_tokens:
                    raise ValidationError(_(
                        "%(doctor)s's %(session)s session on %(date)s is full "
                        "(max %(max)s tokens). Please choose another session "
                        "or override the capacity on the schedule.") % {
                        'doctor': rec.doctor_id.name,
                        'session': dict(rec._fields['session'].selection).get(rec.session),
                        'date': rec.queue_date,
                        'max': schedule.max_tokens,
                    })

    # ---- Workflow ----
    def action_call_next(self):
        self.ensure_one()
        if self.state != 'waiting':
            raise UserError(_('Only a waiting token can be called.'))
        current = self.search([
            ('id', '!=', self.id),
            ('doctor_id', '=', self.doctor_id.id),
            ('queue_date', '=', self.queue_date),
            ('session', '=', self.session),
            ('state', '=', 'in_progress'),
        ], limit=1)
        if current:
            current.write({'state': 'done', 'done_time': fields.Datetime.now()})
        self.write({'state': 'in_progress', 'called_time': fields.Datetime.now()})

    def action_check_in(self):
        for rec in self:
            if rec.state != 'scheduled':
                raise UserError(_('Only a scheduled token can be checked in.'))
            rec.write({'state': 'waiting', 'check_in_time': fields.Datetime.now()})

    def action_start(self):
        now = fields.Datetime.now()
        for rec in self:
            if rec.state != 'waiting':
                raise UserError(_('Only a waiting token can be started.'))
            current = self.search([
                ('id', '!=', rec.id),
                ('doctor_id', '=', rec.doctor_id.id),
                ('queue_date', '=', rec.queue_date),
                ('session', '=', rec.session),
                ('state', '=', 'in_progress'),
            ], limit=1)
            if current:
                raise UserError(_(
                    "Dr. %(doctor)s already has Token #%(token)s in consultation. Complete it before starting another token."
                ) % {'doctor': rec.doctor_id.name, 'token': current.token_no})
            rec.write({'state': 'in_progress', 'called_time': now})

    def action_done(self):
        for rec in self:
            rec.write({'state': 'done', 'done_time': fields.Datetime.now()})

    def action_no_show(self):
        self.write({'state': 'no_show'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_reset(self):
        self.write({'state': 'waiting', 'called_time': False, 'done_time': False})
