# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from datetime import datetime, timedelta

from odoo import api, models, fields, _
from odoo.exceptions import UserError, AccessError


class FobSeason(models.Model):
    _name = "fob.season"

    name = fields.Char('Stagione', help='[SS/AA] SS=Collection AA=Year')


class FobHarbour(models.Model):
    _name = "fob.harbour"

    name = fields.Char('Porto')


class FobIncoterms(models.Model):
    _name = "fob.incoterms"

    name = fields.Char('Incoterm')
    incoterms = fields.Text('Incoterms')


class FobPO(models.TransientModel):
    _name = 'fob.order.line.confirm'
    _description = 'Create purchase orders'

    supplier_id = fields.Many2one('res.partner', string='Fornitore', index=True)
    journal_id = fields.Many2one('account.journal', string='Registro fatture')
    use_shortage = fields.Boolean('Usa quantità da shortage')

    @api.multi
    def create_po_from_fob(self):
        self.ensure_one()

        fob_ids = self.env.context.get('active_ids')

        po_obj = self.env['fob.po.order']
        so_obj = self.env['fob.order']
        po_line_obj = self.env['fob.po.order.line']
        so_line_obj = self.env['fob.order.line']

        # First FOB order line
        first_fob_order_line = so_line_obj.browse(fob_ids[0])
        fob_order = so_obj.browse(first_fob_order_line.order_id.id)
        # Last seq
        last_seq = self.env['ir.sequence'].next_by_code('fob.po.order')
        supplier_ref = ''
        if self.supplier_id.ref:
            supplier_ref = self.supplier_id.ref
        # mettiamo qui la logica di creazione nome
        order_name = fob_order.name + ' ' + fob_order.season_id.name + ' ' + ' ' + fob_order.client_order_ref + ' ' + supplier_ref + ' ' + last_seq # CODICE PI + STAGIONE + PRODUCT_EXT_CODE  + 000

        order = po_obj.create({
            'date_order': datetime.now(),
            'partner_id': self.supplier_id.id,
            'client_order_ref': fob_order.partner_id.ref,
            'name': order_name,
            'eta_date': fob_order.eta_date,
            'etd_date': fob_order.etd_date,
            'incoterm_id': fob_order.incoterm_id.id,
            'lcno': fob_order.lcno,
            'season_id': fob_order.season_id.id,
            'product_brand_id': fob_order.product_brand_id.id,
            'pricelist_id': fob_order.pricelist_id.id,
            'payment_term_id': fob_order.payment_term_id.id,
            'partner_bank_id': fob_order.partner_bank_id.id,
            'loading_port_id': fob_order.loading_port_id.id,
            'destination_port_id': fob_order.destination_port_id.id,
        })

        vat = 0
        for fob_id in fob_ids:
            fob_line = so_line_obj.browse(fob_id)
            if fob_line.tax_id:
                tax_ids = [fob_line.tax_id.id]
                vat = [(6, 0, tax_ids)]
            if self.use_shortage:
                qty_to_invoice = fob_line.shortage_qty
            else:
                qty_to_invoice = fob_line.product_uom_qty #pairs_total

            order_line = po_line_obj.create({
                'order_id': order.id,
                'pi_id': fob_line.id,
                'name': fob_line.name,
                'external_code': fob_line.external_code,
                'internal_code': fob_line.internal_code,
                'product_brand_id': fob_line.product_brand_id.id,
                'assortment_id': fob_line.assortment_id.id,
                'range_start': fob_line.range_start,
                'range_end': fob_line.range_end,
                'season_id': order.season_id.id,
                'loading_port_id': fob_line.loading_port_id.id,
                'eta_date': order.eta_date,
                'etd_date': order.etd_date,
                'lcno': fob_line.lcno,
                'product_qty': qty_to_invoice,
                'product_uom': fob_line.product_uom.id,
                'price_unit': fob_line.price_unit,
                'date_planned': order.date_planned,
                'client_order_ref': fob_line.client_order_ref,
                'taxes_id': vat,
            })
            fob_line.write({'po_state': 'assigned', 'po_id': order.id, 'po_name': order.name, 'supplier_id': self.supplier_id.id})

    @api.multi
    def create_inv_from_fob_order_line(self):
        self.ensure_one()

        if not self.journal_id:
            raise UserError("E' necessario selezionare il registro fatture")

        fob_ids = self.env.context.get('active_ids')

        invoice_obj = self.env['account.invoice']
        invoice_line_obj = self.env['account.invoice.line']
        so_obj = self.env['fob.order']
        so_line_obj = self.env['fob.order.line']

        #Check partner id per capire se sono selezionati più clienti
        partner_id = -1
        number_of_partners = 0
        for fob_id in fob_ids:
            fob_line = so_line_obj.browse(fob_id)
            if fob_line.order_id.partner_id != partner_id:
                partner_id = fob_line.order_id.partner_id
                number_of_partners = number_of_partners + 1

        if number_of_partners > 1:
            raise UserError("Le righe selezionate fanno riferimento a più clienti")

        # First FOB order line
        first_fob_order_line = so_line_obj.browse(fob_ids[0])
        fob_order = so_obj.browse(first_fob_order_line.order_id.id)
        last_seq = self.env['ir.sequence'].next_by_code('fob.account.invoice')

        invoice_id = invoice_obj.create({
            #'origin': fob_order.name,
            'journal_id': self.journal_id.id,
            'type': 'out_invoice',
            'proforma_number': last_seq,
            #'reference': fob_order.name,
            'account_id': fob_order.partner_id.property_account_receivable_id.id,
            'partner_id': fob_order.partner_id.id,
            'payment_term_id': fob_order.payment_term_id.id,
            'partner_bank': fob_order.partner_bank_id.id,
            'partner_shipping_id': fob_order.partner_shipping_id.id,
            'client_order_ref': fob_order.client_order_ref,
            'destination_port_id': fob_order.destination_port_id.id,
            'incoterm_id': fob_order.incoterm_id.id,
            'eta_date': fob_order.eta_date,
            'etd_date': fob_order.etd_date,
            'lcno': fob_order.lcno,
            'product_brand_id': fob_order.product_brand_id.id,
            'fiscal_position_id': fob_order.partner_id.property_account_position_id.id,
            'user_id': fob_order.user_id.id,
            'state': 'draft',
            'loading_port_id': fob_order.loading_port_id.id,
            'packs_total': fob_order.packs_total,
        })

        vat = 0
        deposit_amount = 0
        origin = ''
        for fob_id in fob_ids:
            fob_line = so_line_obj.browse(fob_id)
            if fob_line.tax_id:
                tax_ids = [fob_line.tax_id.id]
                vat = [(6, 0, tax_ids)]
            if self.use_shortage:
                qty_to_invoice = fob_line.shortage_qty
            else:
                qty_to_invoice = fob_line.pairs_total
            origin = origin + fob_line.order_id.name + ' '
            invoice_line = invoice_line_obj.create({
                'invoice_id': invoice_id.id,
                'pi_id': fob_line.id,
                'name': fob_line.name,
                'external_code': fob_line.external_code,
                'product_brand_id': fob_line.product_brand_id.id,
                'assortment_id': fob_line.assortment_id.id,
                'range_start': fob_line.range_start,
                'range_end': fob_line.range_end,
                'loading_port_id': fob_line.loading_port_id.id,
                'etd_date': fob_line.etd_date,
                'lcno': fob_line.lcno,
                'product_qty': qty_to_invoice,
                'quantity': qty_to_invoice,
                'product_uom': fob_line.product_uom.id,
                'price_unit': fob_line.price_unit,
                'origin': fob_order.name,
                'account_id': 103,
                'pair_in_packs': fob_line.pair_in_packs,
                #'journal_id': self.journal_id,
                'deposit_received': fob_line.deposit_received,
                'deposit_amount': fob_line.deposit_amount,
                'no_claim_discount': fob_line.no_claim_discount,
                'discount': fob_line.discount,
                'uom_id': fob_line.product_uom.id,
                'invoice_line_tax_ids': vat,
                #'account_analytic_id': self.order_id.analytic_account_id.id,
                #'analytic_tag_ids': [(6, 0, self.analytic_tag_ids.ids)],
                #'display_type': fob_line.display_type,
            })
            deposit_amount = deposit_amount + fob_line.deposit_amount
            #pi_list = pi_list + fob_line.name + ' '
            fob_line.write({'invoice_status': 'invoiced', 'invoice_id': invoice_id.id, 'inv_name': invoice_obj.name, 'qty_invoiced': fob_line.qty_invoiced + qty_to_invoice})
            invoice_line._compute_price()
        invoice_obj = self.env['account.invoice'].browse(invoice_id.id)
        invoice_obj.write({'origin': origin, 'reference': origin})
        invoice_obj.compute_taxes()
        if deposit_amount>0:
            invoice_obj.invoice_accounts.create({'invoice_id': invoice_id.id, 'name': 'Totale acconti riportati da: ' + origin, 'deposit': deposit_amount, 'is_deposit': 1, 'received': 1})


class FobPI(models.TransientModel):
    _name = 'fob.order.confirm'
    _description = 'Create invoice from orders'

    journal_id = fields.Many2one('account.journal', string='Registro fatture', required=True)

    # @api.multi
    # def create_invoice_from_pi(self):
    #     self.ensure_one()
    #
    #     fob_ids = self.env.context.get('active_ids')
    #
    #     pi_obj = self.env['fob.order']
    #     for order_id in fob_ids:
    #         order = pi_obj.browse(order_id)
    #         order.action_invoice_create(self.journal_id.id)

class FobPO(models.TransientModel):
    _name = 'fob.po.order.confirm'
    _description = 'Create invoice from orders'

    journal_id = fields.Many2one('account.journal', string='Registro fatture', required=True )

    # @api.multi
    # def create_invoice_from_po(self):
    #     self.ensure_one()
    #
    #     fob_ids = self.env.context.get('active_ids')
    #
    #     po_obj = self.env['fob.po.order']
    #     for order_id in fob_ids:
    #         order = po_obj.browse(order_id)
    #         order.action_invoice_create(self.journal_id.id)
    #         #order.action_view_invoice()
