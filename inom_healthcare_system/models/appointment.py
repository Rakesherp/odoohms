from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import timedelta

import pytz


class Appointment(models.Model):

    _name = 'oeh.appointment'
    _description = 'Appointment'
    _rec_name = 'appointment_no'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'appointment_date desc'

    appointment_no = fields.Char(
        default='New',
        readonly=True,
        copy=False,
        tracking=True
    )

    patient_id = fields.Many2one(
        'oeh.patient',
        required=True,
        tracking=True
    )

    doctor_id = fields.Many2one(
        'oeh.doctor',
        required=True,
        tracking=True
    )

    appointment_date = fields.Datetime(
        required=True,
        tracking=True
    )

    # Calendar views in Odoo require either a date_stop or a date_delay
    # field alongside date_start - a single point-in-time isn't enough for
    # it to draw an event block. Computed from the doctor's average
    # consultation length (oeh.doctor.avg_consult_minutes), so the
    # calendar shows a realistically-sized slot instead of a fixed guess.
    appointment_date_end = fields.Datetime(
        string='Ends At', compute='_compute_appointment_date_end', store=True,
    )

    # Derived, stored copy of the date part - used to group/filter by day
    # and to scope the queue token search (see _generate_queue_token).
    appointment_day = fields.Date(
        compute='_compute_appointment_day',
        store=True,
        index=True,
    )

    # ------------------------------------------------------------------
    # SESSION: a doctor can run Morning / Afternoon / Evening sessions on
    # the same day. This drives which token series (see oeh.queue) the
    # patient is added to. Auto-suggested from the doctor's weekly
    # schedule based on the appointment time, but always editable.
    # ------------------------------------------------------------------
    session = fields.Selection([
        ('morning', 'Morning'),
        ('afternoon', 'Afternoon'),
        ('evening', 'Evening'),
    ], tracking=True, help="Consulting session this appointment falls in. "
        "Determines which token series the patient joins - each session "
        "has its own token numbering that starts fresh at 1.")

    chief_complaint = fields.Text()

    followup_date = fields.Date()

    # Kept for backward compatibility with existing data/reports; now
    # populated automatically from the linked queue token instead of
    # being typed in manually.
    queue_no = fields.Integer(
        string='Token No.', compute='_compute_queue_no', store=True,
        help="Auto-generated when the appointment is confirmed (Check-in). "
             "Resets per doctor/day/session - see oeh.queue.",
    )

    queue_id = fields.Many2one(
        'oeh.queue', string='Queue Token', readonly=True, copy=False)

    meeting_id = fields.Many2one(
        'calendar.event',
        string='Meeting'
    )

    prescription_ids = fields.One2many(
        'oeh.prescription', 'appointment_id', string='Prescriptions')
    prescription_count = fields.Integer(compute='_compute_prescription_count')

    invoice_partner_id = fields.Many2one(
        'res.partner', string='Bill To',
        help="Customer the consultation invoice is billed to. Defaults to "
             "the patient's linked Contact (auto-created from the patient's "
             "name/phone/email if none exists yet), but can be overridden "
             "before the appointment is marked Done.",
    )
    invoice_id = fields.Many2one(
        'account.move', string='Invoice', readonly=True, copy=False,
        help="Customer Invoice (account.move) auto-created for the "
             "doctor's consulting fee when the appointment is marked Done.",
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Confirmed'),
        ('progress', 'In Progress'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')
    ], default='draft', tracking=True)

    @api.depends('appointment_date')
    def _compute_appointment_day(self):
        for rec in self:
            if not rec.appointment_date:
                rec.appointment_day = False
                continue
            tz_name = rec.env.company.partner_id.tz or rec.env.user.tz or 'UTC'
            local_dt = pytz.UTC.localize(rec.appointment_date).astimezone(pytz.timezone(tz_name))
            rec.appointment_day = local_dt.date()

    @api.model
    def _hospital_timezone(self):
        return pytz.timezone(self.env.company.partner_id.tz or self.env.user.tz or 'UTC')

    def _get_schedule_for_datetime(self, appointment_date, doctor=None, session=None):
        """Return the doctor's active weekly schedule matching local date/time/session."""
        self.ensure_one()
        doctor = doctor or self.doctor_id
        appointment_date = fields.Datetime.to_datetime(appointment_date) if appointment_date else False
        if not doctor or not appointment_date:
            return self.env['doctor.schedule']
        local_dt = pytz.UTC.localize(appointment_date).astimezone(self._hospital_timezone())
        day_map = {0: 'mon', 1: 'tue', 2: 'wed', 3: 'thu', 4: 'fri', 5: 'sat', 6: 'sun'}
        weekday = day_map[local_dt.weekday()]
        hour = local_dt.hour + local_dt.minute / 60.0
        domain = [
            ('doctor_id', '=', doctor.id),
            ('day', '=', weekday),
            ('active', '=', True),
            ('start_time', '<=', hour),
            ('end_time', '>=', hour + (0.0001 if local_dt.minute else 0)),
        ]
        if session:
            domain.append(('session', '=', session))
        return self.env['doctor.schedule'].search(domain, order='start_time', limit=1)

    @api.depends('appointment_date', 'doctor_id.avg_consult_minutes')
    def _compute_appointment_date_end(self):
        for rec in self:
            if rec.appointment_date:
                minutes = rec.doctor_id.avg_consult_minutes or 15
                rec.appointment_date_end = rec.appointment_date + timedelta(minutes=minutes)
            else:
                rec.appointment_date_end = False

    @api.depends('queue_id.token_no')
    def _compute_queue_no(self):
        for rec in self:
            rec.queue_no = rec.queue_id.token_no or 0

    def _compute_prescription_count(self):
        for rec in self:
            rec.prescription_count = len(rec.prescription_ids)

    @api.onchange('patient_id')
    def _onchange_patient_invoice_partner(self):
        """Default the billing customer from the patient's Contact, without
        overwriting a value staff already picked manually."""
        if self.patient_id and not self.invoice_partner_id:
            self.invoice_partner_id = self.patient_id.partner_id

    @api.onchange('doctor_id', 'appointment_date')
    def _onchange_suggest_session(self):
        if not (self.doctor_id and self.appointment_date):
            return
        schedule = self._get_schedule_for_datetime(self.appointment_date)
        self.session = schedule.session if schedule else False

    # ------------------------------------------------------------------
    # VALIDATION: no double-booking for a doctor
    # ------------------------------------------------------------------
    @api.constrains('doctor_id', 'appointment_date', 'session', 'state')
    def _check_doctor_availability(self):
        for rec in self:
            if not (rec.doctor_id and rec.appointment_date) or rec.state == 'cancel':
                continue
            schedule = rec._get_schedule_for_datetime(
                rec.appointment_date, rec.doctor_id, rec.session
            )
#             if not schedule:
#                 raise ValidationError(_(
#                     "Dr. %(doctor)s is not scheduled for a %(session)s consultation at %(time)s on %(date)s. Please select an available session/time."
#                 ) % {
#                     'doctor': rec.doctor_id.name,
#                     'session': dict(rec._fields['session'].selection).get(rec.session, rec.session or 'selected'),
#                     'time': fields.Datetime.context_timestamp(rec, rec.appointment_date).strftime('%I:%M %p').lstrip('0'),
#                     'date': rec.appointment_day or '',
#                 })

            slot_minutes = rec.doctor_id.avg_consult_minutes or 15
            local_dt = pytz.UTC.localize(rec.appointment_date).astimezone(rec._hospital_timezone())
            local_minutes = local_dt.hour * 60 + local_dt.minute
            start_minutes = int(schedule.start_time * 60)
            end_minutes = int(schedule.end_time * 60)
#             if local_minutes < start_minutes or local_minutes + slot_minutes > end_minutes:
#                 raise ValidationError(_(
#                     "The appointment time is outside Dr. %(doctor)s's %(session)s session (%(start)s - %(end)s)."
#                 ) % {
#                     'doctor': rec.doctor_id.name,
#                     'session': dict(rec._fields['session'].selection).get(rec.session, rec.session or ''),
#                     'start': rec._float_time_label(schedule.start_time),
#                     'end': rec._float_time_label(schedule.end_time),
#                 })

            overlapping = self.search([
                ('id', '!=', rec.id),
                ('doctor_id', '=', rec.doctor_id.id),
                ('state', '!=', 'cancel'),
                ('appointment_date', '>=', rec.appointment_date - timedelta(minutes=slot_minutes - 1)),
                ('appointment_date', '<=', rec.appointment_date + timedelta(minutes=slot_minutes - 1)),
            ], limit=1)
            if overlapping:
                raise ValidationError(_(
                    "Dr. %(doctor)s already has an appointment at %(time)s (Ref: %(ref)s)."
                ) % {
                    'doctor': rec.doctor_id.name,
                    'time': fields.Datetime.context_timestamp(rec, overlapping.appointment_date).strftime('%I:%M %p').lstrip('0'),
                    'ref': overlapping.appointment_no,
                })

    @staticmethod
    def _float_time_label(value):
        total = int(round(value * 60))
        hour, minute = divmod(total, 60)
        return f"{hour % 24:02d}:{minute:02d}"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('appointment_no', 'New') == 'New':
                vals['appointment_no'] = self.env['ir.sequence'].next_by_code('oeh.appointment') or 'New'
            doctor_id = vals.get('doctor_id')
            appointment_date = vals.get('appointment_date')
            if doctor_id and appointment_date and not vals.get('session'):
                temp = self.new({'doctor_id': doctor_id, 'appointment_date': appointment_date})
                schedule = temp._get_schedule_for_datetime(appointment_date)
                if schedule:
                    vals['session'] = schedule.session
        records = super().create(vals_list)
        for rec in records:
            if not rec.queue_id:
                rec._generate_queue_token(state='scheduled')
        return records

    def write(self, vals):
        protected = {'doctor_id', 'appointment_date', 'session'} & set(vals)
        if protected:
            for rec in self:
                if rec.queue_id and rec.queue_id.state in ('waiting', 'in_progress', 'done'):
                    raise ValidationError(_(
                        "Doctor, appointment time and session cannot be changed after the patient has checked in. Cancel/reschedule the appointment instead."
                    ))
        result = super().write(vals)
        if protected:
            for rec in self:
                if rec.queue_id and rec.queue_id.state == 'scheduled':
                    # A rescheduled booking gets a new token series entry; the old token is cancelled.
                    rec.queue_id.action_cancel()
                    rec.queue_id = False
                    rec._generate_queue_token(state='scheduled')
        return result

    # ------------------------------------------------------------------
    # WORKFLOW
    # ------------------------------------------------------------------
    def action_confirm(self):
        """Check in the patient. A booking may already have a reserved
        token in Scheduled state; check-in changes that token to Waiting."""
        for rec in self:

            rec.state = 'confirm'

            if not rec.session:
                rec._onchange_suggest_session()

            if not rec.queue_id:
                rec._generate_queue_token(state='waiting')
            elif rec.queue_id.state in ('scheduled', 'waiting'):
                rec.queue_id.write({
                    'state': 'waiting',
                    'check_in_time': fields.Datetime.now(),
                })

            if (
                rec.appointment_date
                and not rec.meeting_id
            ):

                start = rec.appointment_date

                stop = (
                    rec.appointment_date
                    + timedelta(hours=1)
                )

                meeting = self.env[
                    'calendar.event'
                ].create({

                    'name':
                    'Appointment - %s'
                    % rec.patient_id.name,

                    'start': start,

                    'stop': stop,

                })

                rec.meeting_id = meeting.id

    def _generate_queue_token(self, state='waiting'):
        """Create (or reuse) this appointment's queue token. Token number
        is assigned automatically by oeh.queue, scoped per doctor/day/
        session - see models/queue.py."""
        for rec in self:
            if rec.queue_id:
                continue
            token = self.env['oeh.queue'].create({
                'patient_id': rec.patient_id.id,
                'doctor_id': rec.doctor_id.id,
                'queue_date': rec.appointment_day or fields.Date.context_today(rec),
                'session': rec.session or 'morning',
                'appointment_id': rec.id,
                'state': state,
            })
            rec.queue_id = token.id

    def action_progress(self):
        self.state = 'progress'
        for rec in self:
            if rec.queue_id and rec.queue_id.state == 'waiting':
                rec.queue_id.action_start()

    def action_done(self):
        self.state = 'done'
        for rec in self:
            if rec.queue_id and rec.queue_id.state in ('waiting', 'in_progress'):
                rec.queue_id.action_done()
            rec._create_consultation_invoice()

    def _create_consultation_invoice(self):
        """Auto-create the Customer Invoice (account.move, standard Odoo 19
        CE Accounting) for the doctor's consulting fee once the appointment
        is Done. Idempotent: skipped if this appointment already has an
        invoice, or if the doctor has no consulting fee configured.

        Billing customer: invoice_partner_id if staff picked one, else the
        patient's linked Contact - auto-created from the patient's name/
        phone/email if the patient doesn't have one yet.

        Invoice line: the product flagged 'Consultation Bill' (is_consultation_bill
        = True on product.product), if one is configured; otherwise a plain
        text line naming the doctor.
        """
        for rec in self:
            if rec.invoice_id:
                continue
            fee = rec.doctor_id.consultation_fee or 0.0
            if fee <= 0:
                continue

            partner = rec.invoice_partner_id
            if not partner:
                partner = rec.patient_id._get_or_create_partner()
                rec.invoice_partner_id = partner.id

            product = self.env['product.product'].search(
                [('is_consultation_bill', '=', True)], limit=1)

            line_vals = {'quantity': 1, 'price_unit': fee}
            if product:
                line_vals['product_id'] = product.id
                line_vals['name'] = product.name
            else:
                line_vals['name'] = _(
                    'Consultation Fee - Dr. %s') % rec.doctor_id.name

            invoice = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': partner.id,
                'invoice_date': fields.Date.context_today(rec),
                'invoice_origin': rec.appointment_no,
                'is_consultation_bill': True,
                'invoice_line_ids': [(0, 0, line_vals)],
            })
            rec.invoice_id = invoice.id

    def action_cancel(self):
        self.state = 'cancel'
        for rec in self:
            if rec.queue_id and rec.queue_id.state not in ('done', 'cancel'):
                rec.queue_id.action_cancel()

    def action_open_meeting(self):

        self.ensure_one()

        if not self.meeting_id:
            return

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'calendar.event',
            'res_id': self.meeting_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_consultation(self):
        """Open the single clinical consultation workspace for this appointment.
        Create it automatically when the doctor starts the consultation."""
        self.ensure_one()
        Clinical = self.env['oeh.clinical']
        consultation = Clinical.search([
            ('appointment_id', '=', self.id),
        ], limit=1)
        if not consultation:
            consultation = Clinical.create({
                'patient_id': self.patient_id.id,
                'appointment_id': self.id,
                'doctor_id': self.doctor_id.id,
                'symptoms': self.chief_complaint or False,
                'chief_complaint': self.chief_complaint or False,
            })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Consultation'),
            'res_model': 'oeh.clinical',
            'res_id': consultation.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_prescription(self):
        """Open a new prescription pre-filled from this appointment, so
        the doctor never has to re-type patient/doctor/diagnosis."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('New Prescription'),
            'res_model': 'oeh.prescription',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_appointment_id': self.id,
                'default_patient_id': self.patient_id.id,
                'default_doctor_id': self.doctor_id.id,
            },
        }

    def action_view_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            return
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_prescriptions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Prescriptions'),
            'res_model': 'oeh.prescription',
            'view_mode': 'list,form',
            'domain': [('appointment_id', '=', self.id)],
            'context': {'default_appointment_id': self.id,
                        'default_patient_id': self.patient_id.id,
                        'default_doctor_id': self.doctor_id.id},
        }