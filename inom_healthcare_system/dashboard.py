from odoo import models, fields, api
from datetime import timedelta


class OehDashboard(models.TransientModel):
    _name = 'oeh.dashboard'
    _description = 'Hospital Dashboard'

    @api.model
    def get_dashboard_data(self):
        """Return all aggregated data for the clinic dashboard.

        Read-only: exposes counts/totals/small lists, never full record
        data, so it works the same regardless of the logged-in user's
        role-based access.
        """
        env = self.env(su=True)
        Patient = env['oeh.patient']
        Doctor = env['oeh.doctor']
        Appointment = env['oeh.appointment']
        Queue = env['oeh.queue']
        Prescription = env['oeh.prescription']
        Lab = env['oeh.laboratory']
        Invoice = env['account.move']
        Product = env['product.product']
        Lot = env['stock.lot']
        Quant = env['stock.quant']

        def count(model, domain=None):
            return env[model].search_count(domain or [])

        def total(model, field, domain=None):
            recs = env[model].search(domain or [])
            return round(sum(recs.mapped(field) or [0.0]), 2)

        today = fields.Date.context_today(self)

        # ---- Greeting / current user as "doctor" if applicable --------
        doctor = Doctor.search([('user_id', '=', self.env.uid)], limit=1)

        # ---- Top KPI strip ---------------------------------------------
        appts_today = Appointment.search([
            ('appointment_day', '=', today),
            ('state', '!=', 'cancel'),
        ])
        queue_today = Queue.search([('queue_date', '=', today)])
        prescriptions_pending = Prescription.search_count([('state', 'in', ('draft', 'verified'))])
        lab_pending = Lab.search_count([('status', '!=', 'done')]) if 'status' in Lab._fields else 0
        followups_due = Appointment.search_count([
            ('followup_date', '=', today),
        ])
        # Customer invoices only. Journal entries and vendor bills are excluded
        # by move_type='out_invoice'.
        customer_invoice_domain = [('move_type', '=', 'out_invoice')]
        invoices_today = Invoice.search(customer_invoice_domain + [
            ('state', '=', 'posted'),
        ])

        kpis = {
            'patients_today': len(appts_today.mapped('patient_id')),
            'appointments_today': len(appts_today),
            'waiting_patients': len(queue_today.filtered(lambda q: q.state == 'waiting')),
            'in_consultation': len(queue_today.filtered(lambda q: q.state == 'in_progress')),
            'followups_due': followups_due,
            'pending_prescriptions': prescriptions_pending,
            'lab_pending': lab_pending,
            'today_revenue': round(sum(invoices_today.mapped('amount_total')), 2),
        }

        # ---- Today's appointments (worklist table) ----------------------
        todays_list = []
        for a in appts_today.sorted('appointment_date')[:10]:
            todays_list.append({
                'time': fields.Datetime.context_timestamp(self, a.appointment_date).strftime('%I:%M %p'),
                'patient': a.patient_id.name,
                'doctor': a.doctor_id.name,
                'session': dict(a._fields['session'].selection).get(a.session, '') if a.session else '',
                'state': a.state,
            })

        # ---- Patient queue status (today, across all doctors) -----------
        queue_counts = {
            'waiting': len(queue_today.filtered(lambda q: q.state == 'waiting')),
            'in_progress': len(queue_today.filtered(lambda q: q.state == 'in_progress')),
            'done': len(queue_today.filtered(lambda q: q.state == 'done')),
            'no_show': len(queue_today.filtered(lambda q: q.state == 'no_show')),
        }
        queue_total = sum(queue_counts.values()) or 1

        waits = []
        for q in queue_today:
            if q.check_in_time and (q.called_time or q.done_time):
                end = q.called_time or q.done_time
                waits.append((end - q.check_in_time).total_seconds() / 60.0)
        avg_wait = round(sum(waits) / len(waits), 0) if waits else 0
        max_wait = round(max(waits), 0) if waits else 0

        # ---- Doctor / consultant status table ----------------------------
        doctor_rows = []
        for d in Doctor.search([], limit=8):
            d_tokens = queue_today.filtered(lambda q: q.doctor_id.id == d.id)
            in_progress = d_tokens.filtered(lambda q: q.state == 'in_progress')
            waiting_count = len(d_tokens.filtered(lambda q: q.state == 'waiting'))
            next_appt = Appointment.search([
                ('doctor_id', '=', d.id),
                ('appointment_day', '=', today),
                ('state', 'in', ('draft', 'confirm')),
                ('appointment_date', '>=', fields.Datetime.now()),
            ], order='appointment_date', limit=1)
            if in_progress:
                status_label, status_key = 'In Consultation', 'progress'
            elif waiting_count:
                status_label, status_key = 'Waiting', 'waiting'
            else:
                status_label, status_key = 'Available', 'available'
            doctor_rows.append({
                'name': d.name,
                'specialization': d.specialization or '-',
                'current_patient': in_progress[:1].patient_id.name if in_progress else '-',
                'waiting': waiting_count,
                'status_label': status_label,
                'status_key': status_key,
                'next_appointment': (
                    fields.Datetime.context_timestamp(self, next_appt.appointment_date).strftime('%I:%M %p')
                    if next_appt else '-'
                ),
            })

        # ---- Clinical worklist ------------------------------------------
        worklist = [
            {'label': 'Pending Prescriptions', 'count': prescriptions_pending, 'model': 'oeh.prescription',
             'icon': 'fa-file-text-o', 'domain': [('state', 'in', ('draft', 'verified'))]},
            {'label': 'Lab Reports to Review', 'count': lab_pending, 'model': 'oeh.laboratory',
             'icon': 'fa-flask', 'domain': [('status', '!=', 'done')]},
            {'label': 'Follow-ups Due Today', 'count': followups_due, 'model': 'oeh.appointment',
             'icon': 'fa-calendar-check-o', 'domain': [('followup_date', '=', today)]},
            {'label': 'Medical Certificates Pending', 'count': count('oeh.certificate'),
             'model': 'oeh.certificate', 'icon': 'fa-certificate', 'domain': []},
        ]

        # ---- Clinical alerts: allergies, overdue follow-ups, low stock,
        #      expiring medicines - the two explicitly asked for are the
        #      Low Stock and Expiry panels below. -----------------------
        overdue_followups = Appointment.search_count([
            ('followup_date', '<', today),
            ('followup_date', '!=', False),
        ])
        severe_allergy_patients = env['patient.allergy'].search_count([('severity', '=', 'high')]) \
            if 'patient.allergy' in env else 0

        alerts = [
            {'label': 'Follow-ups Overdue', 'count': overdue_followups, 'icon': 'fa-calendar-times-o',
             'level': 'danger', 'model': 'oeh.appointment', 'domain': [('followup_date', '<', today)]},
            {'label': 'Severe Allergy Alerts', 'count': severe_allergy_patients, 'icon': 'fa-exclamation-circle',
             'level': 'warning', 'model': 'patient.allergy', 'domain': [('severity', '=', 'high')]},
        ]

        # ---- Pharmacy: low stock + expiring batches (explicitly requested) --
        medicine_products = Product.search([
            ('is_medicine', '=', True),
            ('is_storable', '=', True),
        ])
        low_stock_products = medicine_products.filtered(
            lambda p: p.qty_available <= p.min_stock
        ).sorted(key=lambda p: (p.qty_available, p.name or ''))[:8]
        low_stock_list = [{
            'name': p.name,
            'on_hand': p.qty_available,
            'min_stock': p.min_stock,
        } for p in low_stock_products]

        expiry_cutoff = today + timedelta(days=90)

        # Standard Odoo Inventory expiration tracking.
        # Use stock.lot.expiration_date and stock.quant.quantity instead of
        # the legacy oeh.medicine.batch model.
        medicine_lots = Lot.search([
            ('product_id.is_medicine', '=', True),
            ('expiration_date', '!=', False),
            ('expiration_date', '<=', expiry_cutoff),
        ], order='expiration_date asc, product_id asc, name asc')

        lot_qty = {}
        if medicine_lots:
            quants = Quant.search([
                ('lot_id', 'in', medicine_lots.ids),
                ('location_id.usage', '=', 'internal'),
            ])
            for quant in quants:
                lot_qty[quant.lot_id.id] = (
                    lot_qty.get(quant.lot_id.id, 0.0)
                    + float(quant.quantity or 0.0)
                )

        expiring_list = []
        for lot in medicine_lots:
            quantity = lot_qty.get(lot.id, 0.0)
            if quantity <= 0:
                continue
            days_left = (lot.expiration_date - today).days
            expiring_list.append({
                'lot_id': lot.id,
                'lot_no': lot.name,
                'batch_no': lot.name,  # compatibility with existing template
                'medicine': lot.product_id.name,
                'expiry_date': lot.expiration_date.strftime('%d-%b-%Y'),
                'quantity': quantity,
                'days_left': days_left,
                'expired': days_left < 0,
            })
            if len(expiring_list) >= 8:
                break

        pharmacy = {
            'total_medicines': len(medicine_products),
            'low_stock_count': len(medicine_products.filtered(
                lambda p: p.qty_available <= p.min_stock
            )),
            'expiring_count': len(expiring_list),
            'low_stock_list': low_stock_list,
            'expiring_list': expiring_list,
        }

        # ---- Financial summary (today) -----------------------------------
        consultation_invoices = invoices_today.filtered(lambda inv: inv.is_consultation_bill)
        other_invoices = invoices_today - consultation_invoices
        pending_invoices = Invoice.search(customer_invoice_domain + [
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial', 'in_payment')),
        ])
        finance = {
            'consultation_revenue': round(sum(consultation_invoices.mapped('amount_total')), 2),
            'other_revenue': round(sum(other_invoices.mapped('amount_total')), 2),
            'total_collection': round(sum(invoices_today.mapped('amount_total')), 2),
            'pending_payments': round(sum(pending_invoices.mapped('amount_residual')), 2),
        }

        # ---- Patients by specialization / age / gender -------------------
        by_specialization = {}
        for a in Appointment.search([('appointment_day', '>=', today - timedelta(days=30))]):
            key = a.doctor_id.specialization or 'General'
            by_specialization.setdefault(key, set()).add(a.patient_id.id)
        specialization_list = [
            {'label': k, 'count': len(v)} for k, v in
            sorted(by_specialization.items(), key=lambda kv: -len(kv[1]))
        ][:6]

        age_buckets = [('0-18', 0, 18), ('19-30', 19, 30), ('31-45', 31, 45),
                        ('46-60', 46, 60), ('60+', 61, 200)]
        age_list = []
        for label, lo, hi in age_buckets:
            age_list.append({
                'label': label,
                'count': Patient.search_count([('age', '>=', lo), ('age', '<=', hi)]),
            })

        gender_selection = dict(Patient._fields['gender'].selection) if 'gender' in Patient._fields else {}
        gender_list = [{
            'label': label,
            'count': Patient.search_count([('gender', '=', key)]),
        } for key, label in gender_selection.items()]

        # ---- 7-day trend: new patient registrations + appointments -------
        trend = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            trend.append({
                'date': d.strftime('%b %d'),
                'new_patients': count('oeh.patient', [
                    ('create_date', '>=', d.strftime('%Y-%m-%d') + ' 00:00:00'),
                    ('create_date', '<=', d.strftime('%Y-%m-%d') + ' 23:59:59'),
                ]),
                'appointments': count('oeh.appointment', [('appointment_day', '=', d)]),
            })

        currency = env.company.currency_id

        return {
            'company': env.company.name,
            'user_name': self.env.user.name,
            'doctor_specialization': doctor.specialization if doctor else False,
            'today_label': fields.Date.to_string(today),
            'currency_symbol': currency.symbol or '',
            'currency_position': currency.position or 'before',
            'kpis': kpis,
            'todays_appointments': todays_list,
            'queue_counts': queue_counts,
            'queue_total': queue_total,
            'avg_wait': avg_wait,
            'max_wait': max_wait,
            'doctor_rows': doctor_rows,
            'worklist': worklist,
            'alerts': alerts,
            'pharmacy': pharmacy,
            'finance': finance,
            'specialization_list': specialization_list,
            'age_list': age_list,
            'gender_list': gender_list,
            'trend': trend,
            'total_patients': count('oeh.patient'),
        }
