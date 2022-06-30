# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from datetime import datetime
from odoo import api, models, fields, _
from odoo.exceptions import UserError

from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from odoo.tools import float_is_zero, float_compare, float_round, pycompat, date_utils

class AccountInvoice(models.Model):
    _inherit = 'account.invoice'
    pairs_total = fields.Integer('Total pairs', compute='_compute_pairs')
    dest_partner_id = fields.Many2one('res.partner', string='Partner', track_visibility='always', ondelete='restrict', help="You can find a contact by its Name, TIN, Email or Internal Reference.")
    # type = fields.Selection([
            # ('out_invoice','Customer Invoice'),
            # ('in_invoice','Vendor Bill'),
            # ('out_refund','Customer Credit Note'),
            # ('in_refund','Vendor Credit Note'),
            # ('out_move','Additional Move'),
        # ], readonly=True, states={'draft': [('readonly', False)]}, index=True, change_default=True,
        # default=lambda self: self._context.get('type', 'out_invoice'),
        # track_visibility='always')

    @api.depends('invoice_line_ids.pairs_total')
    def _compute_pairs(self):
        pairs=0
        for inv in self:
            for line in inv.invoice_line_ids:
                pairs += line.pairs_total
            inv.update({
                'pairs_total': pairs,
            })

    @api.multi
    def get_taxes_values(self):
        tax_grouped = {}
        round_curr = self.currency_id.round


        for line in self.invoice_line_ids:
            if not line.account_id:
                continue
            ### TEST PAIR
            if line.product_id.is_kit:
                i = 0
                bom_id = line.env['mrp.bom'].search([('product_tmpl_id', '=', line.product_id.product_tmpl_id.id)])
                if bom_id:
                    bom_ids = line.env['mrp.bom.line'].search([('bom_id', '=', bom_id[0].id)])
                    if bom_ids:
                        for bom_line in bom_ids:
                            i = i + int(bom_line.product_qty) * line.quantity
                line.pairs_total = i
            else:
                line.pairs_total = line.quantity
            ###

            price_unit = float_round(line.price_unit * (1 - (line.discount or 0.0) / 100.0),2,0,'HALF-UP')
            taxes = line.invoice_line_tax_ids.compute_all(price_unit, self.currency_id, line.pairs_total, line.product_id, self.partner_id)['taxes']
            for tax in taxes:
                val = self._prepare_tax_line_vals(line, tax)
                key = self.env['account.tax'].browse(tax['id']).get_grouping_key(val)

                if key not in tax_grouped:
                    tax_grouped[key] = val
                    tax_grouped[key]['base'] = round_curr(val['base'])
                else:
                    tax_grouped[key]['amount'] += val['amount']
                    tax_grouped[key]['base'] += round_curr(val['base'])
        return tax_grouped

class AccountInvoiceLine(models.Model):
    _inherit = "account.invoice.line"
    external_code = fields.Char('External code')
    # purchase_line_ids = fields.One2many('purchase.order.line', 'sale_line_id')
    range_start = fields.Integer('range_start')
    range_end = fields.Integer('range_end')
    range_dist = fields.Char('range_dist')

    image = fields.Binary(string="Image")

    range_start = fields.Integer('range_start')
    range_end = fields.Integer('range_end')
    range_dist = fields.Char('range_dist')

    assortment_id = fields.Many2one(comodel_name='product.assortment', string='Assortment', )
    pairs_size = fields.Char('Pairs (Sz.)') #, compute='_compute_pairs_size') #Aggiungere compute
    pairs_in_pack = fields.Integer('Pairs in pack') #, compute='_compute_pairs_in_pack')
    pairs_total = fields.Integer('Pairs')#, compute='_compute_pairs_total') #Aggiungere compute


    @api.one
    @api.depends('price_unit', 'discount', 'invoice_line_tax_ids', 'quantity',
        'product_id', 'invoice_id.partner_id', 'invoice_id.currency_id', 'invoice_id.company_id',
        'invoice_id.date_invoice', 'invoice_id.date')

    def _compute_price(self):
        currency = self.invoice_id and self.invoice_id.currency_id or None
        #price = self.price_unit * (1 - (self.discount or 0.0) / 100.0)
        price = float_round(self.price_unit * (1 - (self.discount or 0.0) / 100.0), 2, 0, 'HALF-UP')
        taxes = False

        ### TEST PAIR
        if self.product_id.is_kit:
            i = 0
            bom_id = self.env['mrp.bom'].search([('product_tmpl_id',  '=',  self.product_id.product_tmpl_id.id)])
            if bom_id:
                bom_ids = self.env['mrp.bom.line'].search([('bom_id',  '=',  bom_id[0].id)])
                if bom_ids:
                    for bom_line in bom_ids:
                        i = i + int(bom_line.product_qty)*self.quantity
            self.pairs_total = i
        else:
            self.pairs_total = self.quantity
        ###

        if self.invoice_line_tax_ids:
            #taxes = self.invoice_line_tax_ids.compute_all(price, currency, self.quantity, product=self.product_id, partner=self.invoice_id.partner_id)
            taxes = self.invoice_line_tax_ids.compute_all(price, currency, self.pairs_total, product=self.product_id, partner=self.invoice_id.partner_id)
        #self.price_subtotal = price_subtotal_signed = taxes['total_excluded'] if taxes else self.quantity * price
        self.price_subtotal = price_subtotal_signed = taxes['total_excluded'] if taxes else self.pairs_total * price
        self.price_total = taxes['total_included'] if taxes else self.price_subtotal
        if self.invoice_id.currency_id and self.invoice_id.currency_id != self.invoice_id.company_id.currency_id:
            currency = self.invoice_id.currency_id
            date = self.invoice_id._get_currency_rate_date()
            price_subtotal_signed = currency._convert(price_subtotal_signed, self.invoice_id.company_id.currency_id, self.company_id or self.env.user.company_id, date or fields.Date.today())
        sign = self.invoice_id.type in ['in_refund', 'out_refund'] and -1 or 1
        self.price_subtotal_signed = price_subtotal_signed * sign

    # @api.depends('assortment_id','range_start','range_end','quantity')
    # def _compute_pairs_size(self):
        # for rec in self:
            # pair_sizes = ''
            # i = -1
            # if rec.assortment_id:
                # composition_quantities_sizes = rec.assortment_id.name.split('-')
                # composition_sizes = rec.range_end - rec.range_start
                # if len(composition_quantities_sizes) != composition_sizes + 1:
                    # rec.pairs_size = 'Missing sizes '+ 'No(Pr.):' + str(len(composition_quantities_sizes)) + 'No(Sz.):' + str(composition_sizes + 1) + ' '
                    # return

                # for size_qty in composition_quantities_sizes:
                    # i = i +1
                    # tot_qty = int(size_qty)*int(rec.quantity)
                    # pair_sizes += str(tot_qty) + '(' + str(rec.range_start + i) + ')' + '-'
                # rec.pairs_size = pair_sizes[:-1]
            # else:
                # rec.pairs_size = rec.quantity

    # @api.depends('assortment_id','range_start','range_end','quantity')
    # def _compute_pairs_in_pack(self):
        # for rec in self:
            # #rec.pairs_total =1
            # pair_sizes = ''
            # i = 0
            # if rec.assortment_id:
                # composition_quantities_sizes = rec.assortment_id.name.split('-')
                # composition_sizes = rec.range_end - rec.range_start
                # if len(composition_quantities_sizes) != composition_sizes + 1:
                    # return

                # try:
                    # for size_qty in composition_quantities_sizes:
                        # i = i + int(size_qty)
                # except:
                        # i = 0
                # rec.pairs_in_pack = i
            # else:
                # rec.pairs_in_pack = rec.quantity

    @api.depends('assortment_id','range_start','range_end','quantity')
    def _compute_pairs_total(self):
        #rec.pairs_total =1
        for rec in self:
            pair_sizes = ''
            i = 0
            raise UserError(_("E' un kit:%s")%(str(rec.product_id.is_kit)))
            if rec.product_id.is_kit:
                bom_id = self.env['mrp.bom'].search([('product_tmpl_id',  '=',  rec.product_id.product_tmpl_id.id)])
                if bom_id:
                    bom_ids = self.env['mrp.bom.line'].search([('bom_id',  '=',  bom_id[0].id)])
                    if bom_ids:
                        for bom_line in bom_ids:
                            i = i + int(bom_line.product_qty)*rec.quantity
                
                #composition_quantities_sizes = rec.assortment_id.name.split('-')
                #composition_sizes = rec.range_end - rec.range_start
                #if len(composition_quantities_sizes) != composition_sizes + 1:
                #    return

                #try:
                #    for size_qty in composition_quantities_sizes:
                #        i = i + int(size_qty)*rec.quantity
                #except:
                #        i = 0
                rec.pairs_total = i
            else:
                rec.pairs_total = rec.quantity
