from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class OehLabTestType(models.Model):
    _name = 'oeh.lab.test.type'
    _description = 'Laboratory Test Type'
    _order = 'name'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    product_id = fields.Many2one(
        'product.product',
        string='Invoice Product',
        domain=[('sale_ok', '=', True)],
        help='Service/product used when creating the laboratory invoice.'
    )
    fee = fields.Float(
        string='Test Fee',
        related='product_id.list_price',
        store=True
    )
    active = fields.Boolean(default=True)
    case_ids = fields.One2many(
        'oeh.lab.test.case',
        'test_type_id',
        string='Test Cases'
    )
    notes = fields.Text()

    _sql_constraints = [
        (
            'lab_test_type_code_unique',
            'unique(code)',
            'Laboratory test code must be unique.'
        ),
    ]


class OehLabTestCase(models.Model):
    _name = 'oeh.lab.test.case'
    _description = 'Laboratory Test Case'
    _order = 'test_type_id, sequence, id'

    sequence = fields.Integer(default=10)
    test_type_id = fields.Many2one(
        'oeh.lab.test.type',
        required=True,
        ondelete='cascade'
    )
    name = fields.Char(
        required=True,
        string='Analyte / Test Case'
    )
    normal_range = fields.Char(string='Normal Range')
    units = fields.Char(string='Units')
    active = fields.Boolean(default=True)


class OELaboratory(models.Model):
    _name = 'oeh.laboratory'
    _description = 'Laboratory Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'request_date desc, id desc'

    name = fields.Char(
        string='Lab Request No',
        required=True,
        copy=False,
        default='New',
        tracking=True
    )
    patient_id = fields.Many2one(
        'oeh.patient',
        string='Patient',
        required=True,
        tracking=True
    )
    doctor_id = fields.Many2one(
        'oeh.doctor',
        string='Doctor',
        tracking=True
    )
    test_type_id = fields.Many2one(
        'oeh.lab.test.type',
        string='Test Type',
        required=True,
        tracking=True
    )
    test_name = fields.Char(
        string='Test Name',
        related='test_type_id.name',
        store=True
    )
    request_date = fields.Datetime(
        string='Date Requested',
        default=fields.Datetime.now,
        required=True,
        tracking=True
    )
    test_date = fields.Date(
        string='Analysis Date',
        default=fields.Date.context_today
    )
    invoice_to_insurance = fields.Boolean(string='Invoice to Insurance')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('tested', 'Tested'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)
    result_id = fields.Many2one(
        'oeh.lab.test.result',
        string='Lab Test Result',
        readonly=True,
        copy=False
    )
    invoice_id = fields.Many2one(
        'account.move',
        string='Invoice',
        readonly=True,
        copy=False
    )
    result = fields.Selection(
        related='result_id.result',
        string='Result Summary',
        readonly=True
    )
    status = fields.Selection(
        related='state',
        string='Status',
        readonly=True
    )
    notes = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('oeh.lab.request')
                    or 'LAB/REQ/0001'
                )
        return super().create(vals_list)

    def action_create_lab_test(self):
        self.ensure_one()
        if self.state == 'cancel':
            raise UserError(_('Cancelled lab requests cannot be tested.'))

        if self.result_id:
            return self._open_result()

        result = self.env['oeh.lab.test.result'].create({
            'request_id': self.id,
            'patient_id': self.patient_id.id,
            'doctor_id': self.doctor_id.id,
            'test_type_id': self.test_type_id.id,
            'date_analysis': fields.Datetime.now(),
        })

        self.result_id = result.id
        # Request remains Draft until the laboratory actually marks
        # the result as Tested.
        self.state = 'draft'
        return self._open_result()

    def action_open_lab_test(self):
        self.ensure_one()
        if not self.result_id:
            return self.action_create_lab_test()
        return self._open_result()

    def _open_result(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Lab Test Result'),
            'res_model': 'oeh.lab.test.result',
            'view_mode': 'form',
            'res_id': self.result_id.id,
            'target': 'current',
        }

    def action_create_lab_invoice(self):
        self.ensure_one()

        if self.invoice_id:
            return self._open_invoice()

        partner = self.patient_id._get_or_create_partner()
        product = self.test_type_id.product_id

        if not product:
            raise UserError(_(
                'Please configure an Invoice Product on laboratory test type "%s".'
            ) % self.test_type_id.name)

        if not product.lst_price:
            raise UserError(_(
                'The invoice product "%s" has no sales price.'
            ) % product.display_name)

        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_date': fields.Date.context_today(self),
            'invoice_origin': self.name,
            'ref': self.name,
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id,
                'quantity': 1.0,
                'price_unit': product.lst_price,
                'name': self.test_type_id.name,
                'tax_ids': [(6, 0, product.taxes_id.ids)],
            })],
        })

        self.invoice_id = invoice.id
        return self._open_invoice()

    def _open_invoice(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Customer Invoice'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.invoice_id.id,
            'target': 'current',
        }

    def action_cancel(self):
        for rec in self:
            if rec.state == 'tested':
                raise UserError(_(
                    'A tested laboratory request cannot be cancelled. '
                    'Cancel the laboratory result first.'
                ))
        self.write({'state': 'cancel'})

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})
        for rec in self:
            if rec.result_id and rec.result_id.state != 'cancel':
                rec.result_id.state = 'draft'


class OehLabTestResult(models.Model):
    _name = 'oeh.lab.test.result'
    _description = 'Laboratory Test Result'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_analysis desc, id desc'

    name = fields.Char(
        string='Test ID',
        required=True,
        copy=False,
        default='New',
        tracking=True
    )

    request_id = fields.Many2one(
        'oeh.laboratory',
        string='Lab Request',
        ondelete='set null',
        tracking=True
    )

    patient_id = fields.Many2one(
        'oeh.patient',
        string='Patient',
        required=True,
        tracking=True
    )

    doctor_id = fields.Many2one(
        'oeh.doctor',
        string='Physician',
        tracking=True
    )

    pathologist_id = fields.Many2one(
        'res.users',
        string='Pathologist',
        default=lambda self: self.env.user
    )

    test_type_id = fields.Many2one(
        'oeh.lab.test.type',
        string='Test Type',
        required=True,
        tracking=True
    )

    date_analysis = fields.Datetime(
        string='Date of the Analysis',
        default=fields.Datetime.now,
        required=True,
        tracking=True
    )

    date_requested = fields.Datetime(
        string='Date Requested',
        related='request_id.request_date',
        readonly=True
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Tested'),
        ('cancel', 'Cancelled'),
    ], default='draft', string='Status', tracking=True)

    line_ids = fields.One2many(
        'oeh.lab.test.result.line',
        'result_id',
        string='Test Cases'
    )

    result = fields.Selection([
        ('normal', 'Normal'),
        ('abnormal', 'Abnormal'),
        ('critical', 'Critical'),
        ('pending', 'Pending'),
    ], string='Results', default='pending', tracking=True)

    diagnosis = fields.Text()
    remarks = fields.Text()

    invoice_id = fields.Many2one(
        'account.move',
        related='request_id.invoice_id',
        string='Invoice',
        readonly=True
    )

    # ---------------------------------------------------------
    # ONCHANGE
    # ---------------------------------------------------------

    @api.onchange('test_type_id')
    def _onchange_test_type_id(self):
        """
        When the user changes the Lab Test Type manually,
        automatically load the active test cases.
        """
        if not self.test_type_id:
            self.line_ids = [(5, 0, 0)]
            return

        self.line_ids = [
            (0, 0, {
                'sequence': case.sequence,
                'name': case.name,
                'normal_range': case.normal_range,
                'units': case.units,
            })
            for case in self.test_type_id.case_ids.filtered('active')
        ]

    # ---------------------------------------------------------
    # CREATE
    # ---------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
    
        for vals in vals_list:
    
            # Generate Test ID
            if vals.get('name', 'New') == 'New':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('oeh.lab.result')
                    or 'LAB/TEST/0001'
                )
    
            # Automatically create test result lines
            if vals.get('test_type_id') and not vals.get('line_ids'):
    
                test_type = self.env['oeh.lab.test.type'].browse(
                    vals['test_type_id']
                )
    
                if test_type.exists():
    
                    line_commands = []
    
                    for case in test_type.case_ids.filtered('active'):
    
                        if not case.name:
                            continue
    
                        line_commands.append(
                            (0, 0, {
                                'sequence': case.sequence,
                                'name': case.name,
                                'normal_range': case.normal_range or '',
                                'units': case.units or '',
                            })
                        )
    
                    vals['line_ids'] = line_commands
    
        return super().create(vals_list)

    # ---------------------------------------------------------
    # MARK AS TESTED
    # ---------------------------------------------------------

    def action_mark_tested(self):
        for rec in self:

            if not rec.line_ids:
                raise UserError(_(
                    'Add at least one test case/result line before '
                    'marking the test as Tested.'
                ))

            if any(not line.result_text for line in rec.line_ids):
                raise UserError(_(
                    'Enter a result for every test case before marking '
                    'the laboratory test as Tested.'
                ))

            if rec.result == 'pending':
                raise UserError(_(
                    'Select the overall Result before marking the test as Tested.'
                ))

            rec.state = 'done'

            if rec.request_id:
                rec.request_id.state = 'tested'
                rec.request_id.test_date = rec.date_analysis.date()

    # ---------------------------------------------------------
    # INVOICE
    # ---------------------------------------------------------

    def action_create_lab_invoice(self):
        self.ensure_one()

        if not self.request_id:
            raise UserError(_(
                'This laboratory result is not linked to a lab request.'
            ))

        return self.request_id.action_create_lab_invoice()

    # ---------------------------------------------------------
    # CANCEL
    # ---------------------------------------------------------

    def action_cancel(self):
        self.write({'state': 'cancel'})

        for rec in self:
            if rec.request_id:
                rec.request_id.state = 'cancel'

    # ---------------------------------------------------------
    # RESET TO DRAFT
    # ---------------------------------------------------------

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})

        for rec in self:
            if rec.request_id:
                rec.request_id.state = 'draft'


class OehLabTestResultLine(models.Model):
    _name = 'oeh.lab.test.result.line'
    _description = 'Laboratory Test Result Line'
    _order = 'sequence, id'

    result_id = fields.Many2one(
        'oeh.lab.test.result',
        string='Lab Test Result',
        required=True,
        ondelete='cascade'
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10
    )

    name = fields.Char(
        string='Name',
        required=True
    )

    result_text = fields.Char(
        string='Result Text'
    )

    normal_range = fields.Char(
        string='Normal Range'
    )

    units = fields.Char(
        string='Units'
    )

    notes = fields.Char(
        string='Notes'
    )

    @api.model_create_multi
    def create(self, vals_list):
        """
        Ensure every result line gets its required Name,
        Normal Range and Units from the selected Lab Test Type.
        """

        for vals in vals_list:

            result_id = vals.get('result_id')

            if result_id:
                result = self.env['oeh.lab.test.result'].browse(result_id)

                if result.exists() and result.test_type_id:

                    test_type = result.test_type_id

                    # Find matching test case by sequence
                    test_case = test_type.case_ids.filtered(
                        lambda case: (
                            case.active
                            and case.sequence == vals.get('sequence', 10)
                        )
                    )[:1]

                    if test_case:

                        # Fill missing Name
                        if not vals.get('name'):
                            vals['name'] = test_case.name

                        # Fill missing Normal Range
                        if not vals.get('normal_range'):
                            vals['normal_range'] = test_case.normal_range

                        # Fill missing Units
                        if not vals.get('units'):
                            vals['units'] = test_case.units

            # Final protection
            if not vals.get('name'):
                raise UserError(_(
                    'Laboratory Result Line Name is missing. '
                    'Please configure the Analyte / Test Case '
                    'for this laboratory test.'
                ))

        return super().create(vals_list)
