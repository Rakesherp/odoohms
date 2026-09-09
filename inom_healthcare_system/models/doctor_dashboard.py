from odoo import models, fields, api, _
from datetime import datetime, time, timedelta


class OehDoctorDashboard(models.TransientModel):
    _name = 'oeh.doctor.dashboard'
    _description = 'Doctor Dashboard'

    @api.model
    def get_dashboard_data(self):
        Doctor = self.env['oeh.doctor']
        Appointment = self.env['oeh.appointment']
        Queue = self.env['oeh.queue']
        Patient = self.env['oeh.patient']
        Prescription = self.env['oeh.prescription']
        Lab = self.env['oeh.laboratory']
        Allergy = self.env['patient.allergy']

        today = fields.Date.context_today(self)
        now = fields.Datetime.now()
        doctor = Doctor.search([('user_id', '=', self.env.uid)], limit=1)

        if not doctor:
            return {
                'doctor_found': False,
                'user_name': self.env.user.name,
                'today_label': fields.Date.to_string(today),
                'today': fields.Date.to_string(today),
                'doctor': {},
                'kpis': {
                    'appointments': 0,
                    'waiting': 0,
                    'in_consultation': 0,
                    'completed': 0,
                    'followups': 0,
                    'pending_labs': 0,
                },
                'appointments': [],
                'queue': [],
                'patients': [],
                'alerts': [],
            }

        day_start = datetime.combine(today, time.min)
        day_end = datetime.combine(today, time.max)

        appointments = Appointment.search([
            ('doctor_id', '=', doctor.id),
            ('appointment_date', '>=', fields.Datetime.to_string(day_start)),
            ('appointment_date', '<=', fields.Datetime.to_string(day_end)),
            ('state', '!=', 'cancel'),
        ], order='appointment_date asc')

        queues = Queue.search([
            ('doctor_id', '=', doctor.id),
            ('queue_date', '=', today),
            ('state', '!=', 'cancel'),
        ], order='token_no asc')

        waiting = queues.filtered(lambda q: q.state == 'waiting')
        in_progress = queues.filtered(lambda q: q.state == 'in_progress')
        done = queues.filtered(lambda q: q.state == 'done')

        followups = Appointment.search_count([
            ('doctor_id', '=', doctor.id),
            ('followup_date', '=', today),
        ])

        pending_labs = Lab.search_count([
            ('doctor_id', '=', doctor.id),
            ('state', '!=', 'tested'),
            ('state', '!=', 'cancel'),
        ])

        appointment_rows = []
        for appointment in appointments[:12]:
            queue = appointment.queue_id
            appointment_rows.append({
                'id': appointment.id,
                'patient_id': appointment.patient_id.id,
                'patient': appointment.patient_id.name,
                'patient_code': appointment.patient_id.patient_id or '',
                'time': fields.Datetime.context_timestamp(
                    self, appointment.appointment_date
                ).strftime('%I:%M %p'),
                'state': appointment.state,
                'state_label': dict(
                    appointment._fields['state'].selection
                ).get(appointment.state, ''),
                'token': queue.token_no if queue else appointment.queue_no or '',
                'has_allergy': bool(appointment.patient_id.allergy_ids),
                'chief_complaint': appointment.chief_complaint or '',
            })

        queue_rows = []
        for token in queues[:12]:
            queue_rows.append({
                'id': token.id,
                'token': token.token_no,
                'patient_id': token.patient_id.id,
                'patient': token.patient_id.name,
                'patient_code': token.patient_id.patient_id or '',
                'state': token.state,
                'state_label': dict(
                    token._fields['state'].selection
                ).get(token.state, ''),
                'check_in': fields.Datetime.context_timestamp(
                    self, token.check_in_time
                ).strftime('%I:%M %p') if token.check_in_time else '',
            })

        patient_ids = appointments.mapped('patient_id')
        patient_rows = []
        seen = set()
        for patient in patient_ids:
            if patient.id in seen:
                continue
            seen.add(patient.id)
            last_appointment = appointments.filtered(
                lambda a, p=patient: a.patient_id == p
            )[:1]
            allergies = patient.allergy_ids
            patient_rows.append({
                'id': patient.id,
                'name': patient.name,
                'patient_code': patient.patient_id or '',
                'age': patient.age or 0,
                'gender': dict(
                    patient._fields['gender'].selection
                ).get(patient.gender, '') if patient.gender else '',
                'blood_group': patient.blood_group or '',
                'phone': patient.phone or '',
                'has_allergy': bool(allergies),
                'allergy_names': ', '.join(allergies.mapped('allergy_name')),
                'last_time': (
                    fields.Datetime.context_timestamp(
                        self, last_appointment.appointment_date
                    ).strftime('%I:%M %p')
                    if last_appointment else ''
                ),
            })

        # Latest/current clinical alerts for this doctor's patients.
        severe_allergy_count = Allergy.search_count([
            ('severity', '=', 'high'),
            ('patient_id', 'in', patient_ids.ids),
        ]) if patient_ids else 0

        overdue_followups = Appointment.search_count([
            ('doctor_id', '=', doctor.id),
            ('followup_date', '<', today),
            ('followup_date', '!=', False),
            ('state', '!=', 'cancel'),
        ])

        alerts = []
        if severe_allergy_count:
            alerts.append({
                'key': 'allergy',
                'level': 'danger',
                'icon': 'fa-exclamation-triangle',
                'title': 'Severe allergy alerts',
                'count': severe_allergy_count,
                'text': 'Review allergy information before prescribing.',
            })
        if overdue_followups:
            alerts.append({
                'key': 'followup',
                'level': 'warning',
                'icon': 'fa-calendar-times-o',
                'title': 'Overdue follow-ups',
                'count': overdue_followups,
                'text': 'Patients have follow-up dates that need attention.',
            })
        if pending_labs:
            alerts.append({
                'key': 'lab',
                'level': 'info',
                'icon': 'fa-flask',
                'title': 'Pending laboratory requests',
                'count': pending_labs,
                'text': 'Review or complete pending investigations.',
            })

        current_patient = in_progress[:1].patient_id if in_progress else False

        return {
            'doctor_found': True,
            'user_name': self.env.user.name,
            'today_label': fields.Date.to_string(today),
            'today': fields.Date.to_string(today),
            'doctor': {
                'id': doctor.id,
                'name': doctor.name,
                'specialization': dict(
                    doctor._fields['specialization'].selection
                ).get(doctor.specialization, '') if doctor.specialization else '',
                'current_patient_id': current_patient.id if current_patient else False,
                'current_patient': current_patient.name if current_patient else '',
                'now_serving': in_progress[:1].token_no if in_progress else 0,
            },
            'kpis': {
                'appointments': len(appointments),
                'waiting': len(waiting),
                'in_consultation': len(in_progress),
                'completed': len(done),
                'followups': followups,
                'pending_labs': pending_labs,
            },
            'appointments': appointment_rows,
            'queue': queue_rows,
            'patients': patient_rows[:10],
            'alerts': alerts,
        }
