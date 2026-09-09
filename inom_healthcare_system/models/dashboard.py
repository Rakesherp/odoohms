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

        # ------------------------------------------------------------------
        # Helper methods
        # ------------------------------------------------------------------

        def count(model, domain=None):
            return env[model].search_count(domain or [])

        def total(model, field, domain=None):
            recs = env[model].search(domain or [])
            return round(sum(recs.mapped(field) or [0.0]), 2)

        today = fields.Date.context_today(self)

        # ------------------------------------------------------------------
        # Greeting / current user as doctor if applicable
        # ------------------------------------------------------------------

        doctor = Doctor.search([
            ('user_id', '=', self.env.uid)
        ], limit=1)

        # ------------------------------------------------------------------
        # Top KPI strip
        # ------------------------------------------------------------------

        appts_today = Appointment.search([
            ('appointment_day', '=', today),
            ('state', '!=', 'cancel'),
        ])

        queue_today = Queue.search([
            ('queue_date', '=', today)
        ])

        prescriptions_pending = Prescription.search_count([
            ('state', 'in', ('draft', 'verified'))
        ])

        lab_pending = (
            Lab.search_count([
                ('status', '!=', 'done')
            ])
            if 'status' in Lab._fields
            else 0
        )

        followups_due = Appointment.search_count([
            ('followup_date', '=', today),
        ])

        # Customer invoices only.
        # Vendor bills and journal entries are excluded.
        customer_invoice_domain = [
            ('move_type', '=', 'out_invoice')
        ]

        invoices_today = Invoice.search(
            customer_invoice_domain + [
                ('state', '=', 'posted'),
            ]
        )

        kpis = {
            'patients_today': len(
                appts_today.mapped('patient_id')
            ),
            'appointments_today': len(appts_today),
            'waiting_patients': len(
                queue_today.filtered(
                    lambda q: q.state == 'waiting'
                )
            ),
            'in_consultation': len(
                queue_today.filtered(
                    lambda q: q.state == 'in_progress'
                )
            ),
            'followups_due': followups_due,
            'pending_prescriptions': prescriptions_pending,
            'lab_pending': lab_pending,
            'today_revenue': round(
                sum(invoices_today.mapped('amount_total')),
                2
            ),
        }

        # ------------------------------------------------------------------
        # Today's appointments
        # ------------------------------------------------------------------

        todays_list = []

        for appointment in appts_today.sorted(
            'appointment_date'
        )[:10]:

            appointment_time = ''

            if appointment.appointment_date:
                appointment_time = (
                    fields.Datetime
                    .context_timestamp(
                        self,
                        appointment.appointment_date
                    )
                    .strftime('%I:%M %p')
                )

            session_label = ''

            if appointment.session:
                session_label = dict(
                    appointment._fields['session'].selection
                ).get(
                    appointment.session,
                    ''
                )

            todays_list.append({
                'time': appointment_time,
                'patient': appointment.patient_id.name,
                'doctor': appointment.doctor_id.name,
                'session': session_label,
                'state': appointment.state,
            })

        # ------------------------------------------------------------------
        # Patient queue status
        # ------------------------------------------------------------------

        queue_counts = {
            'waiting': len(
                queue_today.filtered(
                    lambda q: q.state == 'waiting'
                )
            ),
            'in_progress': len(
                queue_today.filtered(
                    lambda q: q.state == 'in_progress'
                )
            ),
            'done': len(
                queue_today.filtered(
                    lambda q: q.state == 'done'
                )
            ),
            'no_show': len(
                queue_today.filtered(
                    lambda q: q.state == 'no_show'
                )
            ),
        }

        queue_total = sum(queue_counts.values()) or 1

        # ------------------------------------------------------------------
        # Waiting time
        # ------------------------------------------------------------------

        waits = []

        for queue in queue_today:

            if queue.check_in_time and (
                queue.called_time or queue.done_time
            ):
                end = queue.called_time or queue.done_time

                waits.append(
                    (
                        end - queue.check_in_time
                    ).total_seconds() / 60.0
                )

        avg_wait = (
            round(sum(waits) / len(waits), 0)
            if waits
            else 0
        )

        max_wait = (
            round(max(waits), 0)
            if waits
            else 0
        )

        # ------------------------------------------------------------------
        # Doctor / consultant status table
        # ------------------------------------------------------------------

        doctor_rows = []

        for doctor_record in Doctor.search([], limit=8):

            doctor_tokens = queue_today.filtered(
                lambda q:
                    q.doctor_id.id == doctor_record.id
            )

            in_progress = doctor_tokens.filtered(
                lambda q:
                    q.state == 'in_progress'
            )

            waiting_count = len(
                doctor_tokens.filtered(
                    lambda q:
                        q.state == 'waiting'
                )
            )

            next_appt = Appointment.search([
                ('doctor_id', '=', doctor_record.id),
                ('appointment_day', '=', today),
                ('state', 'in', ('draft', 'confirm')),
                (
                    'appointment_date',
                    '>=',
                    fields.Datetime.now()
                ),
            ], order='appointment_date', limit=1)

            if in_progress:
                status_label = 'In Consultation'
                status_key = 'progress'

            elif waiting_count:
                status_label = 'Waiting'
                status_key = 'waiting'

            else:
                status_label = 'Available'
                status_key = 'available'

            next_appointment = '-'

            if next_appt and next_appt.appointment_date:
                next_appointment = (
                    fields.Datetime
                    .context_timestamp(
                        self,
                        next_appt.appointment_date
                    )
                    .strftime('%I:%M %p')
                )

            doctor_rows.append({
                'name': doctor_record.name,
                'specialization':
                    doctor_record.specialization or '-',

                'current_patient':
                    (
                        in_progress[:1].patient_id.name
                        if in_progress
                        else '-'
                    ),

                'waiting': waiting_count,

                'status_label': status_label,
                'status_key': status_key,

                'next_appointment':
                    next_appointment,
            })

        # ------------------------------------------------------------------
        # Clinical worklist
        # ------------------------------------------------------------------

        worklist = [
            {
                'label': 'Pending Prescriptions',
                'count': prescriptions_pending,
                'model': 'oeh.prescription',
                'icon': 'fa-file-text-o',
                'domain': [
                    ('state', 'in', ('draft', 'verified'))
                ],
            },
            {
                'label': 'Lab Reports to Review',
                'count': lab_pending,
                'model': 'oeh.laboratory',
                'icon': 'fa-flask',
                'domain': [
                    ('status', '!=', 'done')
                ],
            },
            {
                'label': 'Follow-ups Due Today',
                'count': followups_due,
                'model': 'oeh.appointment',
                'icon': 'fa-calendar-check-o',
                'domain': [
                    ('followup_date', '=', today)
                ],
            },
            {
                'label': 'Medical Certificates Pending',
                'count': count('oeh.certificate'),
                'model': 'oeh.certificate',
                'icon': 'fa-certificate',
                'domain': [],
            },
        ]

        # ------------------------------------------------------------------
        # Clinical alerts
        # ------------------------------------------------------------------

        overdue_followups = Appointment.search_count([
            ('followup_date', '<', today),
            ('followup_date', '!=', False),
        ])

        severe_allergy_patients = (
            env['patient.allergy'].search_count([
                ('severity', '=', 'high')
            ])
            if 'patient.allergy' in env
            else 0
        )

        alerts = [
            {
                'label': 'Follow-ups Overdue',
                'count': overdue_followups,
                'icon': 'fa-calendar-times-o',
                'level': 'danger',
                'model': 'oeh.appointment',
                'domain': [
                    ('followup_date', '<', today)
                ],
            },
            {
                'label': 'Severe Allergy Alerts',
                'count': severe_allergy_patients,
                'icon': 'fa-exclamation-circle',
                'level': 'warning',
                'model': 'patient.allergy',
                'domain': [
                    ('severity', '=', 'high')
                ],
            },
        ]

        # ------------------------------------------------------------------
        # Pharmacy
        # ------------------------------------------------------------------

        medicine_products = Product.search([
            ('is_medicine', '=', True),
            ('is_storable', '=', True),
        ])

        low_stock_products = medicine_products.filtered(
            lambda product:
                product.qty_available <= product.min_stock
        ).sorted(
            key=lambda product:
                (
                    product.qty_available,
                    product.name or ''
                )
        )[:8]

        low_stock_list = []

        for product in low_stock_products:
            low_stock_list.append({
                'name': product.name,
                'on_hand': product.qty_available,
                'min_stock': product.min_stock,
            })

        # ------------------------------------------------------------------
        # Expiring medicines
        #
        # Standard Odoo 19:
        # stock.lot.expiration_date is a Datetime.
        #
        # today is a Date.
        #
        # Therefore convert expiration_date to date before subtraction.
        # ------------------------------------------------------------------

        expiry_cutoff = today + timedelta(days=90)

        medicine_lots = Lot.search([
            ('product_id.is_medicine', '=', True),
            ('expiration_date', '!=', False),
            ('expiration_date', '<=', expiry_cutoff),
        ], order='expiration_date asc, product_id asc, name asc')

        # Calculate available quantity per lot from internal locations.
        lot_qty = {}

        if medicine_lots:

            quants = Quant.search([
                ('lot_id', 'in', medicine_lots.ids),
                ('location_id.usage', '=', 'internal'),
            ])

            for quant in quants:

                if not quant.lot_id:
                    continue

                lot_id = quant.lot_id.id

                lot_qty[lot_id] = (
                    lot_qty.get(lot_id, 0.0)
                    + float(quant.quantity or 0.0)
                )

        expiring_list = []

        for lot in medicine_lots:

            quantity = lot_qty.get(
                lot.id,
                0.0
            )

            # Do not display lots which have no available
            # internal stock.
            if quantity <= 0:
                continue

            # --------------------------------------------------------------
            # IMPORTANT FIX
            #
            # Odoo stock.lot.expiration_date is Datetime.
            # fields.Date.context_today() returns Date.
            #
            # Convert Datetime -> Date before subtraction.
            # --------------------------------------------------------------

            expiration_date = lot.expiration_date

            if hasattr(expiration_date, 'date'):
                expiration_date = expiration_date.date()

            days_left = (
                expiration_date - today
            ).days

            expiring_list.append({
                'lot_id': lot.id,

                'lot_no':
                    lot.name or '',

                # Backward-compatible template key.
                'batch_no':
                    lot.name or '',

                'medicine':
                    lot.product_id.name,

                'expiry_date':
                    expiration_date.strftime(
                        '%d-%b-%Y'
                    ),

                'quantity':
                    quantity,

                'days_left':
                    days_left,

                'expired':
                    days_left < 0,
            })

            if len(expiring_list) >= 8:
                break

        pharmacy = {
            'total_medicines':
                len(medicine_products),

            'low_stock_count':
                len(
                    medicine_products.filtered(
                        lambda product:
                            product.qty_available
                            <= product.min_stock
                    )
                ),

            'expiring_count':
                len(expiring_list),

            'low_stock_list':
                low_stock_list,

            'expiring_list':
                expiring_list,
        }

        # ------------------------------------------------------------------
        # Financial summary
        # ------------------------------------------------------------------

        consultation_invoices = invoices_today.filtered(
            lambda invoice:
                invoice.is_consultation_bill
        )

        other_invoices = (
            invoices_today - consultation_invoices
        )

        pending_invoices = Invoice.search(
            customer_invoice_domain + [
                ('state', '=', 'posted'),
                (
                    'payment_state',
                    'in',
                    (
                        'not_paid',
                        'partial',
                        'in_payment'
                    )
                ),
            ]
        )

        finance = {
            'consultation_revenue':
                round(
                    sum(
                        consultation_invoices
                        .mapped('amount_total')
                    ),
                    2
                ),

            'other_revenue':
                round(
                    sum(
                        other_invoices
                        .mapped('amount_total')
                    ),
                    2
                ),

            'total_collection':
                round(
                    sum(
                        invoices_today
                        .mapped('amount_total')
                    ),
                    2
                ),

            'pending_payments':
                round(
                    sum(
                        pending_invoices
                        .mapped('amount_residual')
                    ),
                    2
                ),
        }

        # ------------------------------------------------------------------
        # Patients by specialization
        # ------------------------------------------------------------------

        by_specialization = {}

        recent_appointments = Appointment.search([
            (
                'appointment_day',
                '>=',
                today - timedelta(days=30)
            )
        ])

        for appointment in recent_appointments:

            key = (
                appointment.doctor_id.specialization
                or 'General'
            )

            by_specialization.setdefault(
                key,
                set()
            ).add(
                appointment.patient_id.id
            )

        specialization_list = [
            {
                'label': key,
                'count': len(patient_ids)
            }
            for key, patient_ids in sorted(
                by_specialization.items(),
                key=lambda item:
                    -len(item[1])
            )
        ][:6]

        # ------------------------------------------------------------------
        # Patients by age
        # ------------------------------------------------------------------

        age_buckets = [
            ('0-18', 0, 18),
            ('19-30', 19, 30),
            ('31-45', 31, 45),
            ('46-60', 46, 60),
            ('60+', 61, 200),
        ]

        age_list = []

        for label, low, high in age_buckets:

            age_list.append({
                'label': label,

                'count': Patient.search_count([
                    ('age', '>=', low),
                    ('age', '<=', high),
                ]),
            })

        # ------------------------------------------------------------------
        # Patients by gender
        # ------------------------------------------------------------------

        gender_selection = (
            dict(
                Patient._fields['gender'].selection
            )
            if 'gender' in Patient._fields
            else {}
        )

        gender_list = [
            {
                'label': label,
                'count': Patient.search_count([
                    ('gender', '=', key)
                ]),
            }
            for key, label in gender_selection.items()
        ]

        # ------------------------------------------------------------------
        # 7-day trend
        # ------------------------------------------------------------------

        trend = []

        for i in range(6, -1, -1):

            date_value = (
                today - timedelta(days=i)
            )

            trend.append({
                'date':
                    date_value.strftime('%b %d'),

                'new_patients':
                    count(
                        'oeh.patient',
                        [
                            (
                                'create_date',
                                '>=',
                                date_value.strftime(
                                    '%Y-%m-%d'
                                ) + ' 00:00:00'
                            ),
                            (
                                'create_date',
                                '<=',
                                date_value.strftime(
                                    '%Y-%m-%d'
                                ) + ' 23:59:59'
                            ),
                        ]
                    ),

                'appointments':
                    count(
                        'oeh.appointment',
                        [
                            (
                                'appointment_day',
                                '=',
                                date_value
                            )
                        ]
                    ),
            })

        # ------------------------------------------------------------------
        # Currency
        # ------------------------------------------------------------------

        currency = env.company.currency_id

        # ------------------------------------------------------------------
        # Final dashboard response
        # ------------------------------------------------------------------

        return {
            'company':
                env.company.name,

            'user_name':
                self.env.user.name,

            'doctor_specialization':
                doctor.specialization
                if doctor
                else False,

            'today_label':
                fields.Date.to_string(today),

            'currency_symbol':
                currency.symbol or '',

            'currency_position':
                currency.position or 'before',

            'kpis':
                kpis,

            'todays_appointments':
                todays_list,

            'queue_counts':
                queue_counts,

            'queue_total':
                queue_total,

            'avg_wait':
                avg_wait,

            'max_wait':
                max_wait,

            'doctor_rows':
                doctor_rows,

            'worklist':
                worklist,

            'alerts':
                alerts,

            'pharmacy':
                pharmacy,

            'finance':
                finance,

            'specialization_list':
                specialization_list,

            'age_list':
                age_list,

            'gender_list':
                gender_list,

            'trend':
                trend,

            'total_patients':
                count('oeh.patient'),
        }