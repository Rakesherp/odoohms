# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.
{
	"name":"Lot Expiry Track Report | Serial Expiry Track Report",
	"version":"19.0.0.0",
	"category":"Inventory",
	"summary":"Track Lot Expiry Report for Serial Number Expiry Report Track Products with Lot Serial Number Expiry Track Report on Lot Number Expiry Date Track on Serial Track Report Expiry on Lot Expiry Report Serial Number Track Report Product Wise Stock Expiry Report",
	"description":"""
		
		Lot Expiry Track Report Odoo App helps users to generate report of expiration of lot and serial number. User can easily track lot and serial number expiry and print expiry report in PDF format which is based on product and serial number.
	
	""",
	
	"author": "BROWSEINFO",
    	"website" : "https://www.browseinfo.com/demo-request?app=bi_lot_and_serial_expiry_report_track&version=19&edition=Community",
	"depends":["base","stock"],
	"data":[
			"security/ir.model.access.csv",
			"wizard/lot_serial_expiry_report_wizard_form.xml",
			"report/lot_serial_expiry_report_button.xml",
			"report/lot_serial_expiry_report_template_view.xml",
			"views/stock_menu_view.xml",
			],
	'license':'OPL-1',
	'installable': True,
	'auto_install': False,
	'live_test_url':'https://www.browseinfo.com/demo-request?app=bi_lot_and_serial_expiry_report_track&version=19&edition=Community',
	"images":['static/description/Lot-Expiry-Track-Report-Banner.gif'],
}
