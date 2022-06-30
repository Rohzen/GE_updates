# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from datetime import datetime, timedelta

from odoo import api, models, fields, _
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, float_compare
from odoo.exceptions import UserError
from odoo.tools import float_is_zero, float_compare, float_round, pycompat, date_utils

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

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
    pairs_size = fields.Char('Pairs (Sz.)', compute='_compute_pairs_size') #Aggiungere compute
    pairs_in_pack = fields.Integer('Pairs in pack', compute='_compute_pairs_in_pack')
    pairs_total = fields.Integer('Pairs', compute='_compute_pairs_total') #Aggiungere compute

    @api.depends('assortment_id','range_start','range_end') #,'range_start','range_end'
    def _compute_pairs_size(self):
        for rec in self:
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
                    tot_qty = int(size_qty)*int(rec.product_uom_qty)
                    pair_sizes += str(tot_qty) + '(' + str(rec.range_start + i) + ')' + '-'

                rec.pairs_size = pair_sizes[:-1]
            else:
                rec.pairs_size = rec.product_uom_qty

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
                rec.pairs_in_pack = rec.product_uom_qty

    @api.depends('assortment_id','range_start','range_end','product_uom_qty')
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
                        i = i + int(size_qty)*rec.product_uom_qty
                except:
                        i = 0

                rec.pairs_total = i
            else:
                rec.pairs_total = rec.product_uom_qty

    @api.depends('product_uom_qty', 'discount', 'price_unit', 'tax_id')
    def _compute_amount(self):
        """
        Compute the amounts of the SO line.
        """
        for line in self:
            price = float_round(line.price_unit * (1 - (line.discount or 0.0) / 100.0),2,0,'HALF-UP')
            taxes = line.tax_id.compute_all(price, line.order_id.currency_id, line.pairs_total, product=line.product_id, partner=line.order_id.partner_shipping_id)
            line.update({
                'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                'price_total': taxes['total_included'],
                'price_subtotal': taxes['total_excluded'],
            })

    @api.onchange('product_uom_qty', 'product_uom', 'route_id')
    def _onchange_product_id_check_availability(self):
        if not self.product_id or not self.product_uom_qty or not self.product_uom:
            self.product_packaging = False
            return {}

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

        ### Controllo disponibilità: disabilitato per casino sui magazzini

        if self.product_id.is_kit:
            precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
            bom_id = self.env['mrp.bom'].search([('product_tmpl_id',  '=',  self.product_id.product_tmpl_id.id)])
            if bom_id:
                bom_ids = self.env['mrp.bom.line'].search([('bom_id',  '=',  bom_id[0].id)])
                if bom_ids:
                    for bom_line in bom_ids:
                        product = bom_line.product_id.with_context(
                            warehouse=self.order_id.warehouse_id.id,
                            lang=self.order_id.partner_id.lang or self.env.user.lang or 'en_US'
                        )
                        product_qty = self.product_uom._compute_quantity(self.product_uom_qty, self.product_id.uom_id)
                        if float_compare(product.virtual_available, bom_line.product_qty, precision_digits=precision) == -1:
                            is_available = "True" ####self._check_routing()
                            if not is_available:
                                message =  _('You plan to sell %s %s of %s but you only have %s %s available in %s warehouse.') % \
                                        (self.product_uom_qty, self.product_uom.name, product.default_code + ' ' + product.name, product.virtual_available, product.uom_id.name, self.order_id.warehouse_id.name)
                                warning_mess = {
                                    'title': _('Not enough inventory!'),
                                    'message' : message
                                }
                                return {'warning': warning_mess}

        if self.product_id.type == 'product':
            precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
            product = self.product_id.with_context(
                warehouse=self.order_id.warehouse_id.id,
                lang=self.order_id.partner_id.lang or self.env.user.lang or 'en_US'
            )
            product_qty = self.product_uom._compute_quantity(self.product_uom_qty, self.product_id.uom_id)
            if float_compare(product.virtual_available, product_qty, precision_digits=precision) == -1:
                is_available = "True" ####self._check_routing()
                if not is_available:
                    message =  _('You plan to sell %s %s of %s but you only have %s %s available in %s warehouse.') % \
                            (self.product_uom_qty, self.product_uom.name, self.product_id.name, product.virtual_available, product.uom_id.name, self.order_id.warehouse_id.name)
                    # We check if some products are available in other warehouses.
                    if float_compare(product.virtual_available, self.product_id.virtual_available, precision_digits=precision) == -1:
                        message += _('\nThere are %s %s available across all warehouses.\n\n') % \
                                (self.product_id.virtual_available, product.uom_id.name)
                        for warehouse in self.env['stock.warehouse'].search([]):
                            quantity = self.product_id.with_context(warehouse=warehouse.id).virtual_available
                            if quantity > 0:
                                message += "%s: %s %s\n" % (warehouse.name, quantity, self.product_id.uom_id.name)
                    warning_mess = {
                        'title': _('Not enough inventory!'),
                        'message' : message
                    }
                    return {'warning': warning_mess}

        return {}

    @api.multi
    def _prepare_invoice_line(self, qty):
        """
        Prepare the dict of values to create the new invoice line for a sales order line.

        :param qty: float quantity to invoice
        """
        self.ensure_one()
        res = {}
        product = self.product_id.with_context(force_company=self.company_id.id)
        account = product.property_account_income_id or product.categ_id.property_account_income_categ_id

        if not account and self.product_id:
            raise UserError(_('Please define income account for this product: "%s" (id:%d) - or for its category: "%s".') %
                (self.product_id.name, self.product_id.id, self.product_id.categ_id.name))

        fpos = self.order_id.fiscal_position_id or self.order_id.partner_id.property_account_position_id
        if fpos and account:
            account = fpos.map_account(account)

        res = {
            'name': self.name,
            'sequence': self.sequence,
            'origin': self.order_id.name,
            'account_id': account.id,
            'price_unit': self.price_unit,
            'quantity': qty,
            'discount': self.discount,
            'uom_id': self.product_uom.id,
            'product_id': self.product_id.id or False,
            'invoice_line_tax_ids': [(6, 0, self.tax_id.ids)],
            'account_analytic_id': self.order_id.analytic_account_id.id,
            'analytic_tag_ids': [(6, 0, self.analytic_tag_ids.ids)],
            'display_type': self.display_type,
            'pairs_total':self.pairs_total,
            'external_code':self.external_code,
        }
        return res

    @api.multi
    def invoice_line_create(self, invoice_id, qty):
        """ Create an invoice line. The quantity to invoice can be positive (invoice) or negative (refund).

            .. deprecated:: 12.0
                Replaced by :func:`invoice_line_create_vals` which can be used for creating
                `account.invoice.line` records in batch

            :param invoice_id: integer
            :param qty: float quantity to invoice
            :returns recordset of account.invoice.line created
        """
        return self.env['account.invoice.line'].create(
            self.invoice_line_create_vals(invoice_id, qty))

    def invoice_line_create_vals(self, invoice_id, qty):
        """ Create an invoice line. The quantity to invoice can be positive (invoice) or negative
            (refund).

            :param invoice_id: integer
            :param qty: float quantity to invoice
            :returns list of dict containing creation values for account.invoice.line records
        """
        vals_list = []
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for line in self:
            if not float_is_zero(qty, precision_digits=precision) or not line.product_id:
                vals = line._prepare_invoice_line(qty=qty)
                vals.update({'invoice_id': invoice_id, 'sale_line_ids': [(6, 0, [line.id])]})
                vals_list.append(vals)
        return vals_list

class ReportImage(models.Model):
    _inherit = 'sale.order'
    packs_total = fields.Integer('Total packs', compute='_compute_packs')
    pairs_total = fields.Integer('Total pairs', compute='_compute_pairs')
    discount = fields.Float('Sconto(%)', copy=False)

    # @api.multi
    def set_rows(self):
        for row in self.order_line:
            row.discount = self.discount

    @api.depends('order_line.product_uom_qty')
    def _compute_packs(self):
        packs=0
        gross_weight = 0
        weight_total = 0
        volume_total = 0.0
        for order in self:
            for line in order.order_line:
                packs += line.product_uom_qty

                if line.product_id.is_kit:
                    bom_id = self.env['mrp.bom'].search([('product_tmpl_id',  '=', line.product_id.product_tmpl_id.id)])
                    if bom_id:
                        bom_ids = self.env['mrp.bom.line'].search([('bom_id',  '=',  bom_id[0].id)])
                        if bom_ids:
                            for bom_line in bom_ids:
                                gross_weight += bom_line.product_id.weight_gross * bom_line.product_qty
                                weight_total += bom_line.product_id.weight * bom_line.product_qty
                                volume_total += bom_line.product_id.volume * bom_line.product_qty
                else:
                    gross_weight += line.product_id.weight_gross * line.product_uom_qty
                    weight_total += line.product_id.weight * line.product_uom_qty
                    volume_total += line.product_id.volume * line.product_uom_qty

            #self.weight = weight_total
            #self.volume = volume_total
            # order.update({
                # 'packs_total': packs,'weight': weight_total,'volume': volume_total,
            # })
            order.update({
                'packs_total': packs,'weight': weight_total,'gross_weight': gross_weight,'volume': volume_total,
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

    @api.multi
    def _prepare_invoice(self):
        """
        Prepare the dict of values to create the new invoice for a sales order. This method may be
        overridden to implement custom invoice generation (making sure to call super() to establish
        a clean extension chain).
        """
        self.ensure_one()
        company_id = self.company_id.id
        journal_id = (self.env['account.invoice'].with_context(company_id=company_id or self.env.user.company_id.id)
            .default_get(['journal_id'])['journal_id'])
        if not journal_id:
            raise UserError(_('Please define an accounting sales journal for this company.'))
        invoice_vals = {
            'name': self.client_order_ref or '',
            'origin': self.name,
            'type': 'out_invoice',
            'account_id': self.partner_invoice_id.property_account_receivable_id.id,
            'partner_id': self.partner_invoice_id.id,
            'partner_shipping_id': self.partner_shipping_id.id,
            'journal_id': journal_id,
            'currency_id': self.pricelist_id.currency_id.id,
            'comment': self.note,
            'payment_term_id': self.payment_term_id.id,
            'fiscal_position_id': self.fiscal_position_id.id or self.partner_invoice_id.property_account_position_id.id,
            'company_id': company_id,
            'user_id': self.user_id and self.user_id.id,
            'team_id': self.team_id.id,
            'transaction_ids': [(6, 0, self.transaction_ids.ids)],
        }
        return invoice_vals

    @api.multi
    def print_quotation(self):
        self.filtered(lambda s: s.state == 'draft').write({'state': 'sent'})
        return self.env['report'].get_action(self, 'sale_product_image.report_saleorder')

    def _finalize_invoices(self, invoices, references):
        """
        Invoked after creating invoices at the end of action_invoice_create.
        :param invoices: {group_key: invoice}
        :param references: {invoice: order}
        """
        for invoice in invoices.values():
            invoice.compute_taxes()
            if not invoice.invoice_line_ids:
                raise UserError(_(
                    'There is no invoiceable line. If a product has a Delivered quantities invoicing policy, please make sure that a quantity has been delivered.'))
            # If invoice is negative, do a refund invoice instead
            if invoice.amount_total < 0:
                invoice.type = 'out_refund'
                for line in invoice.invoice_line_ids:
                    line.quantity = -line.quantity
                    #line.quantity = line.pairs_total
            # Use additional field helper function (for account extensions)
            for line in invoice.invoice_line_ids:
                line._set_additional_fields(invoice)
            # Necessary to force computation of taxes. In account_invoice, they are triggered
            # by onchanges, which are not triggered when doing a create.
            invoice.compute_taxes()
            # Idem for partner
            so_payment_term_id = invoice.payment_term_id.id
            invoice._onchange_partner_id()
            # To keep the payment terms set on the SO
            invoice.payment_term_id = so_payment_term_id
            invoice.message_post_with_view('mail.message_origin_link',
                values={'self': invoice, 'origin': references[invoice]},
                subtype_id=self.env.ref('mail.mt_note').id)

    @api.multi
    def action_invoice_create(self, grouped=False, final=False):
        """
        Create the invoice associated to the SO.
        :param grouped: if True, invoices are grouped by SO id. If False, invoices are grouped by
                        (partner_invoice_id, currency)
        :param final: if True, refunds will be generated if necessary
        :returns: list of created invoices
        """
        inv_obj = self.env['account.invoice']
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        invoices = {}
        references = {}
        invoices_origin = {}
        invoices_name = {}

        # Keep track of the sequences of the lines
        # To keep lines under their section
        inv_line_sequence = 0
        for order in self:
            group_key = order.id if grouped else (order.partner_invoice_id.id, order.currency_id.id)

            # We only want to create sections that have at least one invoiceable line
            pending_section = None

            # Create lines in batch to avoid performance problems
            line_vals_list = []
            # sequence is the natural order of order_lines
            for line in order.order_line:
                if line.display_type == 'line_section':
                    pending_section = line
                    continue
                if float_is_zero(line.qty_to_invoice, precision_digits=precision):
                    continue
                if group_key not in invoices:
                    inv_data = order._prepare_invoice()
                    invoice = inv_obj.create(inv_data)
                    references[invoice] = order
                    invoices[group_key] = invoice
                    invoices_origin[group_key] = [invoice.origin]
                    invoices_name[group_key] = [invoice.name]
                elif group_key in invoices:
                    if order.name not in invoices_origin[group_key]:
                        invoices_origin[group_key].append(order.name)
                    if order.client_order_ref and order.client_order_ref not in invoices_name[group_key]:
                        invoices_name[group_key].append(order.client_order_ref)

                if line.qty_to_invoice > 0 or (line.qty_to_invoice < 0 and final):
                    if pending_section:
                        section_invoice = pending_section.invoice_line_create_vals(
                            invoices[group_key].id,
                            pending_section.qty_to_invoice
                        )
                        inv_line_sequence += 1
                        section_invoice[0]['sequence'] = inv_line_sequence
                        line_vals_list.extend(section_invoice)
                        pending_section = None

                    inv_line_sequence += 1
                    inv_line = line.invoice_line_create_vals(
                       invoices[group_key].id, line.qty_to_invoice
                    )
                    # inv_line = line.invoice_line_create_vals(
                        # invoices[group_key].id, line.pairs_total
                    # )

                    inv_line[0]['sequence'] = inv_line_sequence
                    #inv_line[0]['pairs_total'] = line.pairs_total
                    line_vals_list.extend(inv_line)

            if references.get(invoices.get(group_key)):
                if order not in references[invoices[group_key]]:
                    references[invoices[group_key]] |= order

            self.env['account.invoice.line'].create(line_vals_list)

        for group_key in invoices:
            invoices[group_key].write({'name': ', '.join(invoices_name[group_key]),
                                       'origin': ', '.join(invoices_origin[group_key])})
            sale_orders = references[invoices[group_key]]
            if len(sale_orders) == 1:
                invoices[group_key].reference = sale_orders.reference

        if not invoices:
            raise UserError(_('There is no invoiceable line. If a product has a Delivered quantities invoicing policy, please make sure that a quantity has been delivered.'))

        self._finalize_invoices(invoices, references)
        return [inv.id for inv in invoices.values()]
