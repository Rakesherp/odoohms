# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from datetime import datetime, timedelta
from odoo.exceptions import UserError, ValidationError

class LotSerialExpiryReportWizard(models.TransientModel):
	_name="lot.serial.expiry.report.wizard"
	_description="Lot Serial Expiry Report Wizard"

	product_ids = fields.Many2many("product.product", string="Products")
	lot_serial_ids = fields.Many2many("stock.lot", string="Lot/Serial Number")
	expire_within = fields.Integer(string="Expire Within")
	selection_report = fields.Selection([
        ('product_wise', 'By Product Wise'),
		('lot_wise', 'By Lot/Serial Wise'),
        ],string="Selection of Report", default="product_wise")

	@api.onchange('selection_report')
	def onchange_lot_serial_wise(self):
		if self.selection_report == 'lot_wise':
			stock_production_lot_obj = self.env['stock.lot'].search([])
			self.lot_serial_ids = stock_production_lot_obj
			self.product_ids = False

	def action_expiry_report(self):
		product_list = []
		ir_module_module_obj = self.env['ir.module.module'].search([('name','=','product_expiry'),('state','=','installed')])

		if ir_module_module_obj:
			today = datetime.strftime(datetime.today(), '%Y-%m-%d')
			days_within = datetime.strftime((datetime.today() + timedelta(days=int(self.expire_within))),'%Y-%m-%d')
			
			if self.selection_report == 'product_wise':
				if self.expire_within > 0:
					for record in self.product_ids:
						stock_production_lot_obj = self.env['stock.lot'].search([('product_id','=', record.id)])
						for rec in stock_production_lot_obj:
							if rec.expiration_date:
								stock_lot_date = rec.filtered(lambda x: str(x.expiration_date) >= today)
								for rec in stock_lot_date:
									if str(rec.expiration_date.date()) <= days_within:
										vals_dict = {}
										vals_dict.update({
											'lot_serial_number':rec.name,
											'product_name':rec.product_id.name,
											'product_expiry_date': rec.expiration_date.date(),
											'product_expire_within': str((datetime.strptime(str(rec.expiration_date.date()), "%Y-%m-%d") - datetime.strptime(today, "%Y-%m-%d")).days),
											'product_qty':rec.product_qty,
												})
										product_list.append(vals_dict)
							else:
								raise ValidationError("Please go to Products --> Inventory Section --> Enable the By Lots Selection in Tracking Field --> Enable Expiration Date; After that Input the Expiration Date in Lots/Serial Numbers --> Dates Section")
					if not product_list:
						raise UserError("No record found for this selected products.")
				else:
					raise UserError("Please enter positive number.")

			if self.selection_report == 'lot_wise':
				if self.expire_within > 0:
					for rec in self.lot_serial_ids:
						if rec.expiration_date:
							stock_production_lot_obj = self.env['stock.lot'].browse([(rec)]).id
							stock_lot_date = stock_production_lot_obj.filtered(lambda x: str(x.expiration_date) >= today)
							for rec in stock_lot_date:
								if str(rec.expiration_date.date()) <= days_within:
									vals_dict = {}
									vals_dict.update({
										'lot_serial_number':rec.name,
										'product_name':rec.product_id.name,
										'product_expiry_date': rec.expiration_date.date(),
										'product_expire_within': str((datetime.strptime(str(rec.expiration_date.date()), "%Y-%m-%d") - datetime.strptime(today, "%Y-%m-%d")).days),
										'product_qty':rec.product_qty,
											})
									print('=========vals_dict======',vals_dict)
         
									product_list.append(vals_dict)
							if not product_list:
								raise UserError("No record found for this selected lot/Serial numbers.")
						else:
							raise ValidationError("Please go to Products --> Inventory Section --> Enable the By Lots Selection in Tracking Field --> Enable Expiration Date; After that Input the Expiration Date in Lots/Serial Numbers --> Dates Section")
				else:
					raise UserError("Please enter positive number.")
		else:
			raise ValidationError("Please Enable Settings --> Expiration Dates Option.")
		
		data = {
				'wizard_data':self.read()[0],
				'product_list':product_list
				}
		return self.env.ref('bi_lot_and_serial_expiry_report_track.action_lot_and_serial_expiry_report').report_action(self, data=data)