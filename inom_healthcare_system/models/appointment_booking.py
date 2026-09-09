from datetime import datetime, date, time, timedelta

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class AppointmentBookingService(models.Model):
    _inherit = 'oeh.appointment'

    @api.model
    def _booking_timezone(self):
        return pytz.timezone(self.env.company.partner_id.tz or self.env.user.tz or 'UTC')

    @api.model
    def _local_to_utc(self, local_dt):
        tz = self._booking_timezone()
        if local_dt.tzinfo is None:
            local_dt = tz.localize(local_dt)
        return local_dt.astimezone(pytz.UTC).replace(tzinfo=None)

    @api.model
    def _utc_to_local(self, utc_dt):
        tz = self._booking_timezone()
        if not utc_dt:
            return False
        return pytz.UTC.localize(utc_dt).astimezone(tz)

    @api.model
    def _local_day_bounds_utc(self, day_value):
        if isinstance(day_value, str):
            day_value = fields.Date.to_date(day_value)
        start_local = datetime.combine(day_value, time.min)
        end_local = datetime.combine(day_value, time.max)
        return self._local_to_utc(start_local), self._local_to_utc(end_local)

    @api.model
    def _check_frontdesk_booking_access(self):
        if not (
            self.env.user.has_group('inom_healthcare_system.group_hospital_receptionist')
            or self.env.user.has_group('inom_healthcare_system.group_hospital_manager')
        ):
            raise UserError(_('Only Receptionist / Front Desk or Hospital Manager / Admin can book appointments for any doctor.'))

    @api.model
    def get_booking_setup(self, appointment_date=False, doctor_id=False, session=False):
        """Return doctor/session/slot information for the front-desk booking UI."""
        self._check_frontdesk_booking_access()
        today = fields.Date.context_today(self)
        if appointment_date:
            appointment_date = fields.Date.to_date(appointment_date)
        else:
            appointment_date = today

        Doctor = self.env['oeh.doctor']
        doctors = Doctor.search([('active', '=', True)], order='name')
        doctor_rows = [{
            'id': d.id,
            'name': d.name,
            'specialization': dict(d._fields['specialization'].selection).get(d.specialization, '') if d.specialization else '',
            'avg_minutes': d.avg_consult_minutes or 15,
        } for d in doctors]

        sessions = []
        slots = []
        selected_doctor = Doctor.browse(int(doctor_id)).exists() if doctor_id else Doctor
        if selected_doctor:
            day_map = {0: 'mon', 1: 'tue', 2: 'wed', 3: 'thu', 4: 'fri', 5: 'sat', 6: 'sun'}
            weekday = day_map[appointment_date.weekday()]
            schedules = self.env['doctor.schedule'].search([
                ('doctor_id', '=', selected_doctor.id),
                ('day', '=', weekday),
                ('active', '=', True),
            ], order='start_time')
            session_labels = dict(self.env['doctor.schedule']._fields['session'].selection)
            selected_schedule = False
            for schedule in schedules:
                row = {
                    'key': schedule.session,
                    'label': session_labels.get(schedule.session, schedule.session),
                    'start': self._float_to_time_label(schedule.start_time),
                    'end': self._float_to_time_label(schedule.end_time),
                    'max_tokens': schedule.max_tokens,
                }
                sessions.append(row)
                if session and schedule.session == session:
                    selected_schedule = schedule

            if selected_schedule:
                slots = self._build_slots(selected_doctor, appointment_date, selected_schedule)

        return {
            'today': fields.Date.to_string(today),
            'selected_date': fields.Date.to_string(appointment_date),
            'doctors': doctor_rows,
            'sessions': sessions,
            'slots': slots,
        }

    @api.model
    def _float_to_minutes(self, value):
        hours = int(value)
        minutes = int(round((value - hours) * 60))
        if minutes >= 60:
            hours += 1
            minutes -= 60
        return hours * 60 + minutes

    @api.model
    def _float_to_time_label(self, value):
        minutes = self._float_to_minutes(value)
        hour = (minutes // 60) % 24
        minute = minutes % 60
        return datetime(2000, 1, 1, hour, minute).strftime('%I:%M %p').lstrip('0')

    @api.model
    def _build_slots(self, doctor, appointment_date, schedule):
        duration = max(5, doctor.avg_consult_minutes or 15)
        start_minutes = self._float_to_minutes(schedule.start_time)
        end_minutes = self._float_to_minutes(schedule.end_time)
        if end_minutes <= start_minutes:
            return []

        day_start_utc, day_end_utc = self._local_day_bounds_utc(appointment_date)
        existing = self.search([
            ('doctor_id', '=', doctor.id),
            ('appointment_date', '>=', day_start_utc),
            ('appointment_date', '<=', day_end_utc),
            ('state', '!=', 'cancel'),
        ])
        booked = set()
        for appointment in existing:
            local = self._utc_to_local(appointment.appointment_date)
            if local:
                booked.add(local.strftime('%H:%M'))

        queue_count = self.env['oeh.queue'].search_count([
            ('doctor_id', '=', doctor.id),
            ('queue_date', '=', appointment_date),
            ('session', '=', schedule.session),
            ('state', '!=', 'cancel'),
        ])
        remaining_capacity = max(0, (schedule.max_tokens or 0) - queue_count) if schedule.max_tokens else None

        result = []
        cursor = start_minutes
        while cursor + duration <= end_minutes:
            hour, minute = divmod(cursor, 60)
            local_dt = datetime.combine(appointment_date, time(hour=hour, minute=minute))
            key = local_dt.strftime('%H:%M')
            is_booked = key in booked
            capacity_full = remaining_capacity is not None and remaining_capacity <= 0
            result.append({
                'key': key,
                'label': local_dt.strftime('%I:%M %p').lstrip('0'),
                'available': not is_booked and not capacity_full,
                'reason': 'Booked' if is_booked else ('Session Full' if capacity_full else ''),
            })
            cursor += duration
            if remaining_capacity is not None and not is_booked:
                remaining_capacity -= 1

        return result

    @api.model
    def search_booking_patients(self, search=''):
        self._check_frontdesk_booking_access()
        domain = [('active', '=', True)]
        search = (search or '').strip()
        if search:
            domain += ['|', '|',
                       ('name', 'ilike', search),
                       ('patient_id', 'ilike', search),
                       ('phone', 'ilike', search)]
        patients = self.env['oeh.patient'].search(domain, order='name', limit=12)
        return [{
            'id': p.id,
            'name': p.name,
            'code': p.patient_id or '',
            'phone': p.phone or '',
        } for p in patients]

    @api.model
    def book_from_frontdesk(self, patient_id, doctor_id, appointment_date, session, slot_key, chief_complaint=''):
        self._check_frontdesk_booking_access()
        Patient = self.env['oeh.patient']
        Doctor = self.env['oeh.doctor']
        patient = Patient.browse(int(patient_id)).exists()
        doctor = Doctor.browse(int(doctor_id)).exists()
        if not patient or not doctor:
            raise ValidationError(_('Please select a valid patient and doctor.'))
        if not appointment_date or not session or not slot_key:
            raise ValidationError(_('Please select date, session and appointment time.'))

        setup = self.get_booking_setup(appointment_date, doctor.id, session)
        slot = next((s for s in setup['slots'] if s['key'] == slot_key), None)
        if not slot:
            raise ValidationError(_('The selected time is not available for this doctor/session.'))
        if not slot['available']:
            raise ValidationError(_('The selected time is no longer available. Please choose another slot.'))

        day = fields.Date.to_date(appointment_date)
        hour, minute = [int(x) for x in slot_key.split(':')]
        local_dt = datetime.combine(day, time(hour=hour, minute=minute))
        appointment_dt = self._local_to_utc(local_dt)

        appointment = self.create({
            'patient_id': patient.id,
            'doctor_id': doctor.id,
            'appointment_date': appointment_dt,
            'session': session,
            'chief_complaint': chief_complaint or False,
            'state': 'draft',
        })
        # Reserve the token immediately so the booking is reflected in the
        # Doctor + Date + Session board. Check-in later changes Scheduled -> Waiting.
        appointment._generate_queue_token(state='scheduled')
        return {
            'appointment_id': appointment.id,
            'appointment_no': appointment.appointment_no,
            'patient': patient.name,
            'doctor': doctor.name,
            'date': fields.Date.to_string(day),
            'time': slot['label'],
            'session': dict(self._fields['session'].selection).get(session, session),
            'token': appointment.queue_no,
        }
