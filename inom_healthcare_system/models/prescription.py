from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import urllib.parse


class Prescription(models.Model):
    """
    Prescription header.

    Flow:
        Draft → Verified → Issued
                                └─► stock.picking (delivery) auto-created → stock reduced
                                └─► account.move (customer invoice) auto-created

    medicine_id on lines now points to product.product (is_medicine=True).
    Medicines are stored on product.product.
    """

    _name = 'oeh.prescription'
    _description = 'Prescription'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Prescription No.', default='New',
        readonly=True, copy=False, index=True, tracking=True,
    )
    patient_id = fields.Many2one('oeh.patient', required=True, tracking=True, index=True)
    doctor_id = fields.Many2one('oeh.doctor', required=True, tracking=True)
    appointment_id = fields.Many2one('oeh.appointment', string='Appointment', tracking=True)
    date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    diagnosis_id = fields.Many2one('oeh.icd', string='Diagnosis (ICD)')

    line_ids = fields.One2many('oeh.prescription.line', 'prescription_id', string='Medicines')
    line_count = fields.Integer(compute='_compute_line_count')

    instruction = fields.Text(string='General Instructions')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('verified', 'Verified'),
        ('issued', 'Issued'),
    ], default='draft', tracking=True)

    verified_by = fields.Many2one('res.users', string='Verified By', readonly=True, copy=False)
    verified_date = fields.Datetime(readonly=True, copy=False)

    allergy_warning = fields.Text(
        string='Allergy / Interaction Notes',
        compute='_compute_allergy_warning', store=True, readonly=False,
    )

    refill_allowed = fields.Boolean()
    refill_count = fields.Integer(string='Refills', default=0)

    # ── Stock picking ────────────────────────────────────────────────
    picking_id = fields.Many2one(
        'stock.picking', string='Delivery Order', readonly=True, copy=False,
    )
    picking_state = fields.Selection(
        related='picking_id.state', string='Delivery State', readonly=True,
    )

    # ── Invoice ──────────────────────────────────────────────────────
    invoice_id = fields.Many2one(
        'account.move', string='Invoice', readonly=True, copy=False,
    )
    invoice_state = fields.Selection(
        related='invoice_id.state', string='Invoice State', readonly=True,
    )
    invoice_amount_total = fields.Monetary(
        related='invoice_id.amount_total', string='Invoice Total',
        readonly=True, currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id,
    )

    prescription_count = fields.Integer(compute='_compute_prescription_count')

    # ── Computes ──────────────────────────────────────────────────────

    @api.depends('patient_id', 'patient_id.allergy_ids')
    def _compute_allergy_warning(self):
        for rec in self:
            if rec.patient_id and rec.patient_id.allergy_ids:
                allergies = ', '.join(rec.patient_id.allergy_ids.mapped('allergy_name'))
                rec.allergy_warning = _('Recorded allergies: %s') % allergies
            elif not rec.allergy_warning:
                rec.allergy_warning = False

    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    def _compute_prescription_count(self):
        for rec in self:
            rec.prescription_count = (
                self.search_count([('patient_id', '=', rec.patient_id.id)])
                if rec.patient_id else 0
            )

    @api.depends('name', 'patient_id')
    def _compute_display_name(self):
        for rec in self:
            if rec.name and rec.name != 'New':
                rec.display_name = '%s – %s' % (rec.name, rec.patient_id.name or '')
            else:
                rec.display_name = rec.patient_id.name or _('Prescription')

    # ── CRUD ──────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') in (False, 'New'):
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('oeh.prescription') or 'New'
                )
        return super().create(vals_list)

    # ── Workflow ──────────────────────────────────────────────────────

    def action_verify(self):
        for rec in self:
            if not rec.line_ids:
                raise ValidationError(_('Add at least one medicine before verifying.'))
            rec.write({
                'state': 'verified',
                'verified_by': self.env.user.id,
                'verified_date': fields.Datetime.now(),
            })

    def action_issue(self):
        for rec in self:
            if rec.state == 'issued':
                continue
            if not rec.line_ids:
                raise ValidationError(_('Add at least one medicine before issuing.'))
            if rec.state == 'draft':
                rec.action_verify()
            rec._check_stock()
            picking = rec._create_stock_picking()
            rec.picking_id = picking.id
            picking.action_confirm()
            if picking.state != 'done':
                picking.button_validate()
            invoice = rec._create_invoice()
            rec.invoice_id = invoice.id
            rec.state = 'issued'
            rec.message_post(body=_(
                'Issued. Delivery: <a href="#" data-oe-model="stock.picking" '
                'data-oe-id="%s">%s</a> | Invoice: <a href="#" '
                'data-oe-model="account.move" data-oe-id="%s">%s</a>'
            ) % (picking.id, picking.name, invoice.id, invoice.name))

    def action_reset(self):
        for rec in self:
            if rec.picking_id and rec.picking_id.state == 'done':
                raise UserError(_(
                    'Cannot reset: delivery %s is already done. '
                    'Create a return from Inventory if needed.') % rec.picking_id.name)
        self.write({'state': 'draft'})

    # ── Stock helpers ─────────────────────────────────────────────────

    def _check_stock(self):
        self.ensure_one()
        pharmacy_location = self._get_pharmacy_location()
        for line in self.line_ids:
            if not line.product_id or not line.total_qty:
                continue
            quant = self.env['stock.quant'].search([
                ('product_id', '=', line.product_id.id),
                ('location_id', '=', pharmacy_location.id),
            ], limit=1)
            available = quant.quantity if quant else 0.0
            if line.total_qty > available:
                raise ValidationError(_(
                    'Insufficient stock for %s. '
                    'Required: %s, Available in Pharmacy: %s'
                ) % (line.product_id.name, line.total_qty, available))

    def _create_stock_picking(self):
        self.ensure_one()
        pharmacy_location = self._get_pharmacy_location()
        customer_location = self.env.ref('stock.stock_location_customers')
        picking_type = self._get_pharmacy_out_picking_type()

        move_lines = []
        for line in self.line_ids:
            if not line.product_id or not (line.total_qty or 0) > 0:
                continue
            move_lines.append((0, 0, {
                #'name': line.product_id.name,
                'product_id': line.product_id.id,
                'product_uom': line.product_id.uom_id.id,
                'product_uom_qty': line.total_qty,
                'location_id': pharmacy_location.id,
                'location_dest_id': customer_location.id,
            }))

        if not move_lines:
            raise ValidationError(_(
                'No medicines with a valid total quantity. '
                'Check that each line has a dosage and duration set.'
            ))

        return self.env['stock.picking'].sudo().create({
            'picking_type_id': picking_type.id,
            'location_id': pharmacy_location.id,
            'location_dest_id': customer_location.id,
            'origin': self.name,
            'move_ids': move_lines,
            'note': 'Prescription: %s | Patient: %s | Dr. %s' % (
                self.name, self.patient_id.name, self.doctor_id.name,
            ),
        })

    def _create_invoice(self):
        self.ensure_one()
        partner = self._get_or_create_patient_partner()
        journal = self.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', self.env.company.id)],
            limit=1,
        )
        if not journal:
            raise UserError(_('No Sales journal found. Configure one in Accounting.'))

        invoice_lines = []
        for line in self.line_ids:
            if not line.product_id:
                continue
            invoice_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'name': '%s | %s | %s %s' % (
                    line.product_id.name,
                    line.frequency_display or '',
                    line.duration_value or '',
                    line.duration_uom or '',
                ),
                'quantity': line.total_qty or 1,
                'price_unit': line.product_id.list_price,
                'tax_ids': line.product_id.taxes_id.ids,
            }))

        return self.env['account.move'].sudo().create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_date': self.date,
            'journal_id': journal.id,
            'ref': self.name,
            'invoice_origin': self.name,
            'invoice_line_ids': invoice_lines,
        })

    def _get_pharmacy_location(self):
        Location = self.env['stock.location'].sudo()
        loc = Location.search([
            ('name', 'ilike', 'Pharmacy'),
            ('usage', '=', 'internal'),
            ('company_id', 'in', [self.env.company.id, False]),
        ], limit=1)
        if not loc:
            parent = self.env.ref('stock.stock_location_stock', raise_if_not_found=False)
            loc = Location.create({
                'name': 'Pharmacy',
                'usage': 'internal',
                'location_id': (
                    parent.id if parent
                    else self.env.ref('stock.stock_location_locations').id
                ),
                'company_id': self.env.company.id,
            })
        return loc

    def _get_pharmacy_out_picking_type(self):
        PickingType = self.env['stock.picking.type'].sudo()
        pt = PickingType.search([
            ('name', 'ilike', 'Pharmacy'),
            ('code', '=', 'outgoing'),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not pt:
            pt = PickingType.search([
                ('code', '=', 'outgoing'),
                ('company_id', '=', self.env.company.id),
            ], limit=1)
        return pt

    def _get_or_create_patient_partner(self):
        self.ensure_one()
        patient = self.patient_id
        if patient.partner_id:
            return patient.partner_id
        Partner = self.env['res.partner'].sudo()
        if patient.phone:
            partner = Partner.search([('phone', '=', patient.phone)], limit=1)
            if partner:
                patient.partner_id = partner.id
                return partner
        partner = Partner.create({
            'name': patient.name,
            'phone': patient.phone,
            'email': patient.email or False,
            'customer_rank': 1,
        })
        patient.partner_id = partner.id
        return partner

    # ── Smart buttons ─────────────────────────────────────────────────

    def action_view_picking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Delivery Order'),
            'res_model': 'stock.picking',
            'res_id': self.picking_id.id,
            'view_mode': 'form',
        }

    def action_view_invoice(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoice'),
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
        }

    def action_view_history(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Prescription History'),
            'res_model': 'oeh.prescription',
            'view_mode': 'list,form',
            'domain': [('patient_id', '=', self.patient_id.id)],
        }

    def action_print_prescription(self):
        return self.env.ref(
            'inom_healthcare_system.action_report_prescription'
        ).report_action(self)

    def action_send_whatsapp(self):
        self.ensure_one()

        phone = self.patient_id.phone
        if not phone:
            raise UserError(
                _('Patient %s has no phone number.') % self.patient_id.name
            )

        # ---------------------------------------------------------
        # Clean phone number
        # ---------------------------------------------------------
        clean = (
            phone.replace(' ', '')
            .replace('-', '')
            .replace('+', '')
            .replace('(', '')
            .replace(')', '')
        )

        # India number handling
        if len(clean) == 10:
            clean = '91' + clean

        # ---------------------------------------------------------
        # Prescription message
        # ---------------------------------------------------------
        lines_text = ''

        for idx, line in enumerate(self.line_ids, 1):
            lines_text += '\n%d. %s – %s, %s %s, %s' % (
                idx,
                line.product_id.name if line.product_id else '',
                line.frequency_display or '',
                line.duration_value or '',
                line.duration_uom or '',
                dict(
                    line._fields['food_timing'].selection
                ).get(
                    line.food_timing,
                    ''
                ),
            )

        message = (
                      'Dear %s,\n\n'
                      'Prescription from *Dr. %s* dated %s:\n'
                      '%s\n\n'
                      '*Instructions:* %s\n\n'
                      'Prescription No: %s\n'
                      'Thank you.'
                  ) % (
                      self.patient_id.name,
                      self.doctor_id.name,
                      self.date,
                      lines_text,
                      self.instruction or 'As advised by doctor.',
                      self.name,
                  )

        # ---------------------------------------------------------
        # WhatsApp URL
        # ---------------------------------------------------------
        whatsapp_url = (
                'https://web.whatsapp.com/send?phone=%s&text=%s'
                % (
                    clean,
                    urllib.parse.quote(message),
                )
        )

        # ---------------------------------------------------------
        # Prescription PDF URL
        #
        # Get the report_name dynamically from the existing
        # action_report_prescription report action.
        # ---------------------------------------------------------
        report_action = self.env.ref(
            'inom_healthcare_system.action_report_prescription'
        )

        pdf_url = '/report/pdf/%s/%s' % (
            report_action.report_name,
            self.id,
        )

        # Add the database origin so the URL works correctly
        # when Odoo is accessed through another hostname/port.
        base_url = self.env['ir.config_parameter'].sudo().get_param(
            'web.base.url'
        )

        pdf_url = '%s%s' % (
            base_url.rstrip('/'),
            pdf_url,
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'open_whatsapp',
            'params': {
                'whatsapp_url': whatsapp_url,
                'pdf_url': pdf_url,
                'prescription_id': self.id,
                'prescription_name': self.name,
            },
        }