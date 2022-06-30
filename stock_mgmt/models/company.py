# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from datetime import datetime, timedelta

from odoo import api, models, fields, _
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, float_compare
from odoo.exceptions import UserError

# class ResPartnerModFE(models.Model):
    # _inherit = "res.partner"

    # max_invoice_in_xml = fields.Integer(string='Max Invoice # in XML', default=0)

class ResetDb(models.Model): 
    _inherit = 'res.company'

    #max_invoice_in_xml = fields.Integer(string='Max Invoice # in XML', default=0)


    @api.multi
    def reset_db(self):
        try:
            self.env.cr.execute('DELETE FROM public.delivery_carrier;')
            self.env.cr.execute('DELETE FROM public.stock_landed_cost_lines;')
        except:
            print ('')
        self.env.cr.execute('DELETE FROM public.wizard_assortment')
        self.env.cr.execute('DELETE FROM public.purchase_order;')
        self.env.cr.execute('DELETE FROM public.sale_order;')
        self.env.cr.execute('DELETE FROM public.account_invoice;')
        self.env.cr.execute('DELETE FROM public.stock_picking;')
        self.env.cr.execute('DELETE FROM public.stock_move;')
        self.env.cr.execute('DELETE FROM public.stock_move_line;')
        self.env.cr.execute('DELETE FROM public.stock_inventory;')
        self.env.cr.execute('DELETE FROM public.stock_quant;')
        self.env.cr.execute('DELETE FROM public.stock_production_lot;')
        self.env.cr.execute('DELETE FROM public.stock_scrap;')
        self.env.cr.execute('DELETE FROM public.mrp_bom')
        self.env.cr.execute('DELETE FROM public.mrp_bom_line')
        self.env.cr.execute('DELETE FROM public.product_attribute_value_product_template_attribute_line_rel')
        self.env.cr.execute('DELETE FROM public.product_attribute_value_product_product_rel')
        self.env.cr.execute('DELETE FROM public.product_product')



        #self.env.cr.execute('DELETE FROM public.product_template;')

