from odoo import api, fields, models, _
from odoo.exceptions import UserError


class QueueBoardService(models.Model):
    _inherit = 'oeh.queue'

    @api.model
    def _check_board_access(self):
        if not (
            self.env.user.has_group('inom_healthcare_system.group_hospital_receptionist')
            or self.env.user.has_group('inom_healthcare_system.group_hospital_manager')
            or self.env.user.has_group('inom_healthcare_system.group_hospital_doctor')
            or self.env.user.has_group('inom_healthcare_system.group_hospital_nurse')
        ):
            raise UserError(_('You do not have permission to open the Queue / Token Board.'))

    @api.model
    def get_board_data(self, queue_date=False, doctor_id=False, session=False):
        self._check_board_access()
        today = fields.Date.context_today(self)
        queue_date = fields.Date.to_date(queue_date) if queue_date else today

        is_doctor = self.env.user.has_group('inom_healthcare_system.group_hospital_doctor')
        if is_doctor and not self.env.user.has_group('inom_healthcare_system.group_hospital_manager'):
            doctor = self.env['oeh.doctor'].search([('user_id', '=', self.env.uid)], limit=1)
            doctor_id = doctor.id if doctor else False

        domain = [('queue_date', '=', queue_date), ('state', '!=', 'cancel')]
        if doctor_id:
            domain.append(('doctor_id', '=', int(doctor_id)))
        if session:
            domain.append(('session', '=', session))

        tokens = self.search(domain, order='doctor_id, session, token_no')
        doctors = self.env['oeh.doctor'].search([('active', '=', True)], order='name')
        if is_doctor and not self.env.user.has_group('inom_healthcare_system.group_hospital_manager'):
            doctors = doctors.filtered(lambda d: d.user_id.id == self.env.uid)

        groups = {}
        session_labels = dict(self._fields['session'].selection)
        state_labels = dict(self._fields['state'].selection)
        for token in tokens:
            key = '%s:%s' % (token.doctor_id.id, token.session)
            groups.setdefault(key, {
                'doctor_id': token.doctor_id.id,
                'doctor': token.doctor_id.name,
                'specialization': dict(token.doctor_id._fields['specialization'].selection).get(
                    token.doctor_id.specialization, ''
                ) if token.doctor_id.specialization else '',
                'session': token.session,
                'session_label': session_labels.get(token.session, token.session),
                'tokens': [],
            })
            groups[key]['tokens'].append({
                'id': token.id,
                'token': token.token_no,
                'patient_id': token.patient_id.id,
                'patient': token.patient_id.name,
                'patient_code': token.patient_id.patient_id or '',
                'appointment_id': token.appointment_id.id if token.appointment_id else False,
                'time': self._token_time(token),
                'state': token.state,
                'state_label': state_labels.get(token.state, token.state),
            })

        return {
            'date': fields.Date.to_string(queue_date),
            'today': fields.Date.to_string(today),
            'doctors': [{
                'id': d.id,
                'name': d.name,
                'specialization': dict(d._fields['specialization'].selection).get(d.specialization, '') if d.specialization else '',
            } for d in doctors],
            'groups': list(groups.values()),
            'summary': {
                'scheduled': sum(1 for t in tokens if t.state == 'scheduled'),
                'waiting': sum(1 for t in tokens if t.state == 'waiting'),
                'in_progress': sum(1 for t in tokens if t.state == 'in_progress'),
                'done': sum(1 for t in tokens if t.state == 'done'),
            },
        }

    @api.model
    def _token_time(self, token):
        if token.appointment_id and token.appointment_id.appointment_date:
            dt = fields.Datetime.context_timestamp(self, token.appointment_id.appointment_date)
            return dt.strftime('%I:%M %p').lstrip('0')
        return ''
