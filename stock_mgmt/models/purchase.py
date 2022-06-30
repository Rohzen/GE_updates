# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from datetime import datetime
from odoo import api, models, fields, _
from odoo.addons import decimal_precision as dp
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare

from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT

class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    packs_total = fields.Integer('Total packs', compute='_compute_packs')
    pairs_total = fields.Integer('Total pairs', compute='_compute_pairs')
    change = fields.Float('Change')

    @api.depends('order_line.product_qty')
    def _compute_packs(self):
        packs=0
        for order in self:
            for line in order.order_line:
                packs += line.product_qty
            order.update({
                'packs_total': packs,
            })

    @api.depends('order_line.pairs_total')
    def _compute_pairs(self):
        pairs=0
        for order in self:
            for line in order.order_line:
                pairs += line.pairs_total
            order.update({
                'pairs_total': pairs,
            })

class ProductComposition(models.Model):
    _name ="product.assortment.line"
    
    asrt_code_id = fields.Integer('External ID')
    #name = fields.Text('External code')
    size_id = fields.Many2one(comodel_name='product.sizes', string='Size', )
    qty = fields.Integer('Qty')

class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    external_code = fields.Char('External code')
    range_start = fields.Integer('range_start')
    range_end = fields.Integer('range_end')
    range_dist = fields.Char('range_dist')

    image = fields.Binary(string="Image")

    assortment_id = fields.Many2one(comodel_name='product.assortment', string='Assortment', )
    pairs_size = fields.Char('Pairs (Sz.)', compute='_compute_pairs_size')
    pairs_in_pack = fields.Integer('Pairs in pack', compute='_compute_pairs_in_pack')
    pairs_total = fields.Integer('Pairs total', compute='_compute_pairs_total')

    pack_weight_gross = fields.Float('Pack gross weight', digits=dp.get_precision('Stock Weight'))
    pack_volume = fields.Float('Pack volume', digits=dp.get_precision('Stock Volume'))
    material_id = fields.Many2one(comodel_name='product.material', string='Material', )

    @api.depends('assortment_id','range_start','range_end')
    def _compute_pairs_size(self):
        for rec in self:
            # rec.pairs_total =1
            pair_sizes = ''
            i = -1
            if rec.assortment_id:
                composition_quantities_sizes = rec.assortment_id.name.split('-')
                composition_sizes = rec.range_end - rec.range_start
                if len(composition_quantities_sizes) != composition_sizes + 1:
                    rec.pairs_size = 'Missing sizes '+ 'No(Pr.):' + str(len(composition_quantities_sizes)) + 'No(Sz.):' + str(composition_sizes + 1) + ' '
                    return

                for size_qty in composition_quantities_sizes:
                    i = i +1
                    tot_qty = int(size_qty)*int(rec.product_qty)
                    pair_sizes += str(tot_qty) + '(' + str(rec.range_start + i) + ')' + '-'

                rec.pairs_size = pair_sizes[:-1]
            else:
                rec.pairs_size = rec.product_qty

    @api.depends('assortment_id','range_start','range_end')
    def _compute_pairs_in_pack(self):
        for rec in self:
            #rec.pairs_total =1
            pair_sizes = ''
            i = 0
            if rec.assortment_id:
                composition_quantities_sizes = rec.assortment_id.name.split('-')
                composition_sizes = rec.range_end - rec.range_start
                if len(composition_quantities_sizes) != composition_sizes + 1:
                    return

                try:
                    for size_qty in composition_quantities_sizes:
                        i = i + int(size_qty)
                except:
                        i = 0
                rec.pairs_in_pack = i
            else:
                rec.pairs_in_pack = rec.product_qty

    @api.depends('assortment_id','range_start','range_end','product_qty')
    def _compute_pairs_total(self):
        #rec.pairs_total =1
        for rec in self:
            pair_sizes = ''
            i = 0
            if rec.assortment_id:
                composition_quantities_sizes = rec.assortment_id.name.split('-')
                composition_sizes = rec.range_end - rec.range_start
                if len(composition_quantities_sizes) != composition_sizes + 1:
                    return

                try:
                    for size_qty in composition_quantities_sizes:
                        i = i + int(size_qty)*rec.product_qty
                except:
                        i = 0
                rec.pairs_total = i
            else:
                rec.pairs_total = rec.product_qty

    def _prepare_compute_all_values(self):
        # Hook method to returns the different argument values for the
        # compute_all method, due to the fact that discounts mechanism
        # is not implemented yet on the purchase orders.
        # This method should disappear as soon as this feature is
        # also introduced like in the sales module.
        self.ensure_one()
        return {
            'price_unit': self.price_unit,
            'currency_id': self.order_id.currency_id,
            'product_qty': self.pairs_total, #product_qty
            'product': self.product_id,
            'partner': self.order_id.partner_id,
        }

    @api.onchange('product_id')
    def onchange_product_id(self):
        result = {}
        if not self.product_id:
            return result

        order_partner_id = self.order_id.partner_id

        external_code = None
        for e in self.product_id.external_codes:
            if e.partner_id == order_partner_id:
                external_code = e.name

        vals = {}
        if external_code:
            self.external_code = external_code

        self.image = self.product_id.image_medium
        self.range_start = self.product_id.range_start
        self.range_end = self.product_id.range_end
        self.assortment_id =self.product_id.assortment_id
        # Reset date, price and quantity since _onchange_quantity will provide default values
        self.date_planned = datetime.today().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        #self.price_unit = self.product_qty = 0.0
        if self.product_id.is_kit:
            self.product_uom = self.product_id.uom_po_id or self.product_id.uom_id
        else:
            self.product_uom = self.product_id.uom_id
        result['domain'] = {'product_uom': [('category_id', '=', self.product_id.uom_id.category_id.id)]}

        product_lang = self.product_id.with_context(
            lang=self.partner_id.lang,
            partner_id=self.partner_id.id,
        )
        self.name = product_lang.display_name
        if product_lang.description_purchase:
            self.name += '\n' + product_lang.description_purchase

        self._compute_tax_id()

        self._suggest_quantity()
        self._onchange_quantity()

        self.price_subtotal = self.pairs_total * self.price_unit
        return result

    @api.multi
    def open_wizard(self):
        return {
            'name': _('Open item detail'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'product.wizard',
            'target': 'new',
            'context': self.env.context,
        }

class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    def _prepare_invoice_line_from_po_line(self, line):
        if line.product_id.purchase_method == 'purchase':
            qty = line.product_qty - line.qty_invoiced
        else:
            qty = line.qty_received - line.qty_invoiced
        if float_compare(qty, 0.0, precision_rounding=line.product_uom.rounding) <= 0:
            qty = 0.0

        qty = line.pairs_total

        taxes = line.taxes_id
        invoice_line_tax_ids = line.order_id.fiscal_position_id.map_tax(taxes, line.product_id, line.order_id.partner_id)
        invoice_line = self.env['account.invoice.line']
        date = self.date or self.date_invoice
        data = {
            'purchase_line_id': line.id,
            'name': line.order_id.name + ': ' + line.name,
            'origin': line.order_id.origin,
            'uom_id': line.product_uom.id,
            'product_id': line.product_id.id,
            'account_id': invoice_line.with_context({'journal_id': self.journal_id.id, 'type': 'in_invoice'})._default_account(),
            'price_unit': line.order_id.currency_id._convert(
                line.price_unit, self.currency_id, line.company_id, date or fields.Date.today(), round=False),
            'quantity': qty,
            'discount': 0.0,
            'account_analytic_id': line.account_analytic_id.id,
            'analytic_tag_ids': line.analytic_tag_ids.ids,
            'invoice_line_tax_ids': invoice_line_tax_ids.ids
        }
        account = invoice_line.get_invoice_line_account('in_invoice', line.product_id, line.order_id.fiscal_position_id, self.env.user.company_id)
        if account:
            data['account_id'] = account.id
        return data

