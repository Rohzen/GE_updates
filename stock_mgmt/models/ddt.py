# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models, fields, _
from odoo.addons import decimal_precision as dp
from odoo.exceptions import UserError
import os
from odoo.tools import float_is_zero

class SaleOrder(models.Model):

    _inherit = 'sale.order'

    weight = fields.Float('Weight', digits=dp.get_precision('Stock Weight'),
        help="Weight of the product, packaging not included. The unit of measure can be changed in the general settings")
    gross_weight = fields.Float('Gross weight', digits=dp.get_precision('Stock Weight'),
        help="Weight of the product, packaging not included. The unit of measure can be changed in the general settings")
    volume = fields.Float('Pack Volume', help="The volume in m3.", digits=dp.get_precision('Stock Volume'))

class AccountInvoice(models.Model):

    _inherit = 'account.invoice'

    weight = fields.Float('Weight', digits=dp.get_precision('Stock Weight'),
        help="Weight of the product, packaging not included. The unit of measure can be changed in the general settings")
    gross_weight = fields.Float('Gross weight', digits=dp.get_precision('Stock Weight'),
        help="Weight of the product, packaging not included. The unit of measure can be changed in the general settings")
    volume = fields.Float('Pack Volume', help="The volume in m3.", digits=dp.get_precision('Stock Volume'))

class ddtCustom(models.Model):
    _inherit = 'stock.picking.package.preparation'

    order_line_ids = fields.Many2many('sale.order.line',  compute='_compute_order_lines',  string='Order Lines')
    pairs_total = fields.Char('Pairs (Sz.)', compute='_compute_pairs_total') #Aggiungere compute
    packs_total = fields.Integer('Pairs', compute='_compute_packs_total') #Aggiungere compute

    weight = fields.Float('Weight', digits=dp.get_precision('Stock Weight'),
        help="Weight of the product, packaging not included. The unit of measure can be changed in the general settings")
    gross_weight = fields.Float('Gross weight', digits=dp.get_precision('Stock Weight'),
        help="Weight of the product, packaging not included. The unit of measure can be changed in the general settings")
    volume = fields.Float('Pack Volume', help="The volume in m3.", digits=dp.get_precision('Stock Volume'))

    @api.one
    def _compute_order_lines(self):
        # weight_total = 0
        # volume_total = 0.0
        #out_file = open("c:\\temp\dev.txt","w")
        #self.ensure_one()
        for ddt in self:
            order = ddt._get_sale_order_ref()
        if order:
            order_lines = set()
            res_ids = self.env['sale.order.line'].search([['order_id',  '=', order.id]])
            for o in res_ids: 
                order_lines.add(o.id)

                # if o.product_id.is_kit:
                    # bom_id = self.env['mrp.bom'].search([('product_tmpl_id',  '=', o.product_id.product_tmpl_id.id)])
                    # if bom_id:
                        # bom_ids = self.env['mrp.bom.line'].search([('bom_id',  '=',  bom_id[0].id)])
                        # if bom_ids:
                            # for bom_line in bom_ids:
                                # self.weight += bom_line.product_id.weight
                                # self.volume += bom_line.product_id.volume
                # else:
                    # self.weight += o.product_id.weight
                    # self.volume += o.product_id.volume

            self.order_line_ids = list(order_lines)

        # self.weight = weight_total
        # self.volume = volume_total

    @api.one
    def _compute_pairs_total(self):
        for ddt in self:
            order = ddt._get_sale_order_ref()
            
            self.pairs_total = order.pairs_total

    @api.one
    def _compute_packs_total(self):
        for ddt in self:
            order = ddt._get_sale_order_ref()
            
            self.packs_total = order.packs_total

class DdtCreateInvoiceSuper(models.TransientModel):
    _inherit = "ddt.create.invoice"
    # _description = "Create invoice from TD"

    def _get_ddt_ids(self):
        return self.env['stock.picking.package.preparation'].browse(
            self.env.context['active_ids'])

    ddt_ids = fields.Many2many(
        'stock.picking.package.preparation', default=_get_ddt_ids)


class StockPickingPackagePreparation(models.Model):
    _inherit = 'stock.picking.package.preparation'

    @api.multi
    def action_invoice_create(self):
        #raise UserError(_("TEST PREPARE."))
        """
        Create the invoice associated to the DDT.
        :returns: list of created invoices
        """
        inv_obj = self.env['account.invoice']
        invoices = {}
        references = {}
        for ddt in self:
            if not ddt.to_be_invoiced or ddt.invoice_id:
                continue
            order = ddt._get_sale_order_ref()

            if order:
                group_method = (
                    order and order.ddt_invoicing_group or 'shipping_partner')
                group_partner_invoice_id = order.partner_invoice_id.id
                group_currency_id = order.currency_id.id
            else:
                group_method = ddt.partner_shipping_id.ddt_invoicing_group
                group_partner_invoice_id = ddt.partner_id.id
                group_currency_id = ddt.partner_id.currency_id.id

            if group_method == 'billing_partner':
                group_key = (group_partner_invoice_id,
                             group_currency_id)
            elif group_method == 'shipping_partner':
                group_key = (ddt.partner_shipping_id.id,
                             ddt.company_id.currency_id.id)
            elif group_method == 'code_group':
                group_key = (ddt.partner_shipping_id.ddt_code_group,
                             group_partner_invoice_id)
            else:
                group_key = ddt.id

            for line in ddt.line_ids:
                #give the same description in the invoice as the product name
                line.name = line.product_id.display_name
               #line.pairs_total = line.product_uom_qty

                if group_key not in invoices:
                    inv_data = ddt._prepare_invoice()
                    invoice = inv_obj.create(inv_data)
                    references[invoice] = ddt
                    invoices[group_key] = invoice
                    ddt.invoice_id = invoice.id
                elif group_key in invoices:
                    vals = {}

                    origin = invoices[group_key].origin
                    if origin and ddt.ddt_number not in origin.split(', '):
                        vals['origin'] = invoices[
                            group_key].origin + ', ' + ddt.ddt_number
                    invoices[group_key].write(vals)
                    ddt.invoice_id = invoices[group_key].id

                if line.product_uom_qty > 0:
                    line.invoice_line_create(
                        invoices[group_key].id, line.product_uom_qty)
            if references.get(invoices.get(group_key)):
                if ddt not in references[invoices[group_key]]:
                    references[invoice] = references[invoice] | ddt

            # Allow additional operations from ddt
            ddt.other_operations_on_ddt(invoice)

        if not invoices:
            raise UserError(_('There is no invoiceable line.'))

        for invoice in list(invoices.values()):
            if not invoice.name:
                invoice.write({
                    'name': invoice.origin
                })
            if not invoice.invoice_line_ids:
                raise UserError(_('There is no invoiceable line.'))
            # If invoice is negative, do a refund invoice instead
            if invoice.amount_untaxed < 0:
                invoice.type = 'out_refund'
                for line in invoice.invoice_line_ids:
                    line.quantity = -line.quantity
            # Use additional field helper function (for account extensions)
            for line in invoice.invoice_line_ids:
                line._set_additional_fields(invoice)

            # Necessary to force computation of taxes. In account_invoice,
            # they are triggered
            # by onchanges, which are not triggered when doing a create.
            invoice.compute_taxes()
            invoice.message_post_with_view(
                'mail.message_origin_link',
                values={
                    'self': invoice, 'origin': references[invoice]},
                subtype_id=self.env.ref('mail.mt_note').id)
        return [inv.id for inv in list(invoices.values())]

class StockPickingPackagePreparationLine(models.Model):
    _inherit = 'stock.picking.package.preparation.line'

    @api.multi
    def invoice_line_create(self, invoice_id, qty):
        """
        :param invoice_id: integer
        :param qty: float quantity to invoice
        """
        precision = self.env['decimal.precision'].precision_get(
            'Product Unit of Measure')
        for line in self:
            if not float_is_zero(qty, precision_digits=precision):
                vals = line._prepare_invoice_line(
                     qty= qty, invoice_id=invoice_id)
                vals.update({'invoice_id': invoice_id})
                if line.sale_line_id:
                    vals.update(
                        {'sale_line_ids': [
                            (6, 0, [line.sale_line_id.id])
                        ]})

                self.env['account.invoice.line'].create(vals)
