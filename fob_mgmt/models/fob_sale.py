# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from datetime import datetime, timedelta

from odoo import api, models, fields, _
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, float_compare
from odoo.exceptions import UserError
from odoo.tools import float_is_zero, float_compare, float_round, pycompat, date_utils
from dateutil.relativedelta import relativedelta

class FobSaleOrder(models.Model):
    _inherit = 'fob.order'

    @api.model
    def _default_pi_date(self):
        return datetime.now().date()

    customer_ref = fields.Char(related='partner_id.ref', depends=['partner_id'], store=True, string='Codice cliente', readonly=True)
    packs_total = fields.Integer('Total packs', compute='_compute_packs')
    pairs_total = fields.Integer('Total pairs', compute='_compute_pairs')
    # Fob
    container_no = fields.Char('Container')
    tipo_container = fields.Char('Tipo container')
    seal_no = fields.Char('Sigillo')
    bl_code = fields.Char('BL')
    route = fields.Char('Route')

    season_id = fields.Many2one(comodel_name='fob.season', string='Stagione')
    loading_port_id = fields.Many2one(comodel_name='fob.harbour', string='Loading port',)
    destination_port_id = fields.Many2one(comodel_name='fob.harbour', string='Destination port',)
    incoterm_id = fields.Many2one(comodel_name='fob.incoterms', string='Incoterms', )
    pi_date = fields.Date('PI Date', default=_default_pi_date)
    etd_date = fields.Date('ETD Date')
    eta_date = fields.Date('ETA Date')
    payment_start_date = fields.Date('Data decorrenza pagamento')
    partner_bank_id = fields.Many2one('res.partner.bank', string='Bank Account')
    # partner_bank_id = fields.Many2one('account.journal', string='Bank Account') #, domain={'partner_bank_id': [('id', 'in', partner_id.bank_ids.ids)]}
    lcno = fields.Char('LC No.')
    no_claim_discount = fields.Float('No claim discount(%)', copy=False)
    total_discount = fields.Float('Total discount', copy=False)
    total_discount_value = fields.Float('Total discount(value)', copy=False)
    discount = fields.Float('Sconto(%)', copy=False)
    product_brand_id = fields.Many2one('product.brand', string='Brand', help='Select a brand for this product')

    deposit_expected = fields.Monetary('Dep. expected', copy=False)
    deposit_received = fields.Monetary('Dep. received', copy=False)
    deposit_pending_balance = fields.Monetary('Dep.Pending balance', copy=False)
    total_pending_balance = fields.Monetary('Tot.Pending balance', copy=False)
    rec_balance = fields.Monetary('Rec. balance', copy=False)
    currency_selection_id = fields.Many2one('res.currency', string='Currency')

    total_amount_in_value =fields.Float('Value total amount', copy=False)
    total_discounted_amount = fields.Float('Total discounted amount', copy=False)

    order_accounts = fields.One2many('fob.order.accounts', 'order_id', 'Order accounts')

    @api.onchange('etd_date')
    def _onchange_etd_date(self):
        self.payment_start_date = self.etd_date

    # @api.multi
    def set_rows(self):
        for row in self.order_line:
            row.loading_port_id = self.loading_port_id
            row.etd_date = self.etd_date
            row.lcno = self.lcno
            row.discount = self.discount
            row.product_brand_id = self.product_brand_id
            row.client_order_ref = self.client_order_ref

    @api.one
    def compute_account_dates(self, payment_term, value, date_ref):
        payment_term = self.env['account.payment.term'].browse(payment_term)
        type = ''
        date_ref = date_ref or fields.Date.today()
        amount = value
        sign = value < 0 and -1 or 1
        result = []
        types = []
        if self.env.context.get('currency_id'):
            currency = self.env['res.currency'].browse(self.env.context['currency_id'])
        else:
            currency = self.env.user.company_id.currency_id
        for line in payment_term.line_ids:
            types.append(line.value)
            if line.value == 'fixed':
                amt = sign * currency.round(line.value_amount)
                type = 'fixed'
            elif line.value == 'percent':
                amt = currency.round(value * (line.value_amount / 100.0))
                type = 'percent'
            elif line.value == 'balance':
                amt = currency.round(amount)
                type = 'balance'
            if amt:
                next_date = fields.Date.from_string(date_ref)
                if line.option == 'day_after_invoice_date':
                    next_date += relativedelta(days=line.days)
                    if line.day_of_the_month > 0:
                        months_delta = (line.day_of_the_month < next_date.day) and 1 or 0
                        next_date += relativedelta(day=line.day_of_the_month, months=months_delta)
                elif line.option == 'after_invoice_month':
                    next_first_date = next_date + relativedelta(day=1, months=1)  # Getting 1st of next month
                    next_date = next_first_date + relativedelta(days=line.days - 1)
                elif line.option == 'day_following_month':
                    next_date += relativedelta(day=line.days, months=1)
                elif line.option == 'day_current_month':
                    next_date += relativedelta(day=line.days, months=0)
                result.append((fields.Date.to_string(next_date), amt))
                amount = amount - amt
        amount = sum(amt for _, amt in result)
        dist = currency.round(value - amount)
        if dist:
            last_date = result and result[-1][0] or fields.Date.today()
            result.append((last_date, dist))
        return result, types

    #@api.onchange('no_claim_discount')
    def compute_balance(self):
        total_amount = 0
        for line in self.order_line:
            line._compute_amount()
            total_amount = total_amount + line._compute_amount_without_discount()['price_subtotal']

        #if self.no_claim_discount > 0:
        self.total_discount = total_amount - self.amount_total #* self.no_claim_discount/100
        self.total_discounted_amount = total_amount - self.total_discount
        deposit_received = 0
        total_received = 0
        if self.payment_term_id:
            self.deposit_expected = (self.amount_total) * (self.payment_term_id.line_ids[0].value_amount / 100)
            for acc in self.order_accounts:
                if acc.received and acc.is_deposit:
                    deposit_received += acc.deposit
                if acc.received and not acc.is_deposit:
                    total_received += acc.deposit
            self.deposit_received = deposit_received
            self.deposit_pending_balance = self.deposit_expected - deposit_received
            self.total_pending_balance = self.amount_total - total_received - deposit_received
            self.payment_start_date = self.etd_date + timedelta(days=self.payment_term_id.line_ids[0].days)
        else:
            for acc in self.order_accounts:
                if acc.received and acc.is_deposit:
                    deposit_received += acc.deposit
                if acc.received and not acc.is_deposit:
                    total_received += acc.deposit
            self.deposit_received = deposit_received
            self.deposit_pending_balance = self.deposit_expected - deposit_received
            self.total_pending_balance = self.amount_total - total_received - deposit_received
            self.payment_start_date = self.etd_date #+ timedelta(days=self.payment_term_id.line_ids[0].days)

        convert_to_usd = self.env['res.currency'].search([('name', '=', 'USD')])

        usd_rate = convert_to_usd[0].rate

        rate = usd_rate
        if self.pricelist_id.currency_id.name == 'EUR':
            self.total_discount_value = self.total_discount * rate
            self.total_amount_in_value = self.total_discounted_amount * rate
        else:
            self.total_discount_value = self.total_discount / rate
            self.total_amount_in_value = self.total_discounted_amount / rate

        # ACCONTO / TOT.FATTURA * TOTALE RIGA
        rows_no = 0
        if self.deposit_received>0:
            for row in self.order_line:
                rows_no = rows_no + 1
                assign_balance = self.deposit_received / self.amount_total * row.price_subtotal
                if assign_balance > 0:
                    row.deposit_amount = assign_balance
                    row.deposit_received = 1
                    row.amount_in_value = row.price_subtotal * rate

    def compute_accounts(self):
        if self.payment_term_id and not self.order_accounts:
            if not (self.total_discounted_amount>0):
                self.compute_balance()
            payment_term_list = self.compute_account_dates(self.payment_term_id.id, self.total_discounted_amount, self.payment_start_date)
            accounts = payment_term_list[0][0]
            types = payment_term_list[0][1]
            r = -1
            for pay in accounts:
                r = r + 1
                data = pay[0]
                amount = pay[1]
                type = types[r]
                if type == 'percent':
                    self.order_accounts.create({'order_id': self.id, 'date': data, 'deposit': amount, 'is_deposit': 1})
                else:
                    self.order_accounts.create({'order_id': self.id, 'date': data, 'deposit': amount})

    @api.depends('order_line.product_uom_qty')
    def _compute_packs(self):
        packs = 0
        gross_weight = 0
        weight_total = 0
        volume_total = 0.0
        for order in self:
            for line in order.order_line:
                packs += line.product_uom_qty

                if line.product_id.is_kit:
                    bom_id = self.env['mrp.bom'].search([('product_tmpl_id', '=', line.product_id.product_tmpl_id.id)])
                    if bom_id:
                        bom_ids = self.env['mrp.bom.line'].search([('bom_id', '=', bom_id[0].id)])
                        if bom_ids:
                            for bom_line in bom_ids:
                                gross_weight += bom_line.product_id.weight_gross * bom_line.product_qty
                                weight_total += bom_line.product_id.weight * bom_line.product_qty
                                volume_total += bom_line.product_id.volume * bom_line.product_qty
                else:
                    gross_weight += line.product_id.weight_gross * line.product_uom_qty
                    weight_total += line.product_id.weight * line.product_uom_qty
                    volume_total += line.product_id.volume * line.product_uom_qty

            order.update({
                'packs_total': packs,
            })
            # order.update({
            #     'packs_total': packs,'weight': weight_total,'gross_weight': gross_weight,'volume': volume_total,
            # })

    @api.depends('order_line.pairs_total')
    def _compute_pairs(self):
        pairs = 0
        for order in self:
            for line in order.order_line:
                pairs += line.pairs_total
            order.update({
                'pairs_total': pairs,
            })

    def create_inv_from_fob_order(self):
        invoice_obj = self.env['account.invoice']
        invoice_line_obj = self.env['account.invoice.line']
        so_obj = self.env['fob.order']
        so_line_obj = self.env['fob.order.line']

        # FOB order
        fob_order = so_obj.browse(self.id)

        last_seq = self.env['ir.sequence'].next_by_code('fob.account.invoice')

        invoice_id = invoice_obj.create({
            'origin': fob_order.name,
            #'journal_id': self.journal_id.id,
            'type': 'out_invoice',
            'proforma_number': last_seq,
            'reference': fob_order.name,
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
            'no_claim_discount': fob_order.no_claim_discount,
            'deposit_expected': fob_order.deposit_expected,
            'deposit_received': fob_order.deposit_received,
            'deposit_pending_balance': fob_order.deposit_pending_balance,
            'total_pending_balance': fob_order.total_pending_balance,
            'total_amount_in_value': fob_order.total_amount_in_value,
            'total_discounted_amount': fob_order.total_discounted_amount,
            'total_discount': fob_order.total_discount,
            'total_discount_value': fob_order.total_discount_value,
            'pi_order_id': self.id,
            'currency_id': self.currency_id.id,
            'packs_total': self.packs_total,
        })

        vat = 0
        for fob_id in fob_order.order_line:
            fob_line = so_line_obj.browse(fob_id.id)
            if fob_line.tax_id:
                tax_ids = [fob_line.tax_id.id]
                vat = [(6, 0, tax_ids)]
            # if self.use_shortage:
            #     qty_to_invoice = fob_line.shortage_qty
            # else:
            qty_to_invoice = fob_line.pairs_total
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
                'deposit_received': fob_line.deposit_received,
                'deposit_amount': fob_line.deposit_amount,
                'no_claim_discount': fob_line.no_claim_discount,
                'pairs_in_pack': fob_line.pairs_in_pack,
                'product_qty': qty_to_invoice,
                'quantity': qty_to_invoice,
                'product_uom': fob_line.product_uom.id,
                'price_unit': fob_line.price_unit,
                'origin': fob_order.name,
                'account_id': 103,
                'discount': fob_line.discount,
                'uom_id': fob_line.product_uom.id,
                'invoice_line_tax_ids': vat,
            })
            fob_line.write({'invoice_status': 'invoiced', 'invoice_id': invoice_id.id, 'inv_name': invoice_obj.name,'qty_invoiced': fob_line.qty_invoiced + qty_to_invoice})
            invoice_line._compute_price()
        invoice_obj = self.env['account.invoice'].browse(invoice_id.id)
        invoice_obj.compute_taxes()

        for accounts in self.order_accounts:
            accounts.write({'invoice_id': invoice_id.id})

        return {
            'context': self.env.context,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.invoice',
            'res_id': invoice_id.id,
            'view_id': 	self.env.ref('account.invoice_form').id,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }

class FobOrderAccountsLine(models.Model):
    _name = 'fob.order.accounts'
    _description = 'Acconti ordine'

    invoice_id = fields.Many2one('account.invoice', string='Invoice Reference')
    order_id = fields.Many2one('fob.order', string='Order Reference')
    currency_id = fields.Many2one(related='order_id.currency_id', depends=['order_id'], store=True, string='Currency', readonly=True)
    name = fields.Text(string='Description')
    date = fields.Date('Date')
    deposit = fields.Monetary('Deposit')
    received = fields.Boolean('Received')
    is_deposit = fields.Boolean('Is deposit')

class FobSaleOrderLine(models.Model):
    _inherit = "fob.order.line"

    # name = fields.Related()
    order_name = fields.Char(related='order_id.name', string='Ordine', store=True, readonly=True)
    supplier_id = fields.Many2one('res.partner', string='Supplier', index=True, track_visibility='always',
                                  track_sequence=1)
    external_code = fields.Char('Ext.code')
    internal_code = fields.Char('Int.code')
    client_order_ref = fields.Char('Cust.Ref.N°')
    # purchase_line_ids = fields.One2many('purchase.order.line', 'sale_line_id')
    range_start = fields.Integer('range_start')
    range_end = fields.Integer('range_end')
    range_dist = fields.Char('range_dist')

    image = fields.Binary(string="Image")

    assortment_id = fields.Many2one(comodel_name='product.assortment', string='Assortment', )
    pairs_size = fields.Char('Pairs (Sz.)', compute='_compute_pairs_size')
    pairs_in_pack = fields.Integer('Pairs in pack', compute='_compute_pairs_in_pack')
    pairs_total = fields.Integer('Pairs', compute='_compute_pairs_total')
    shortage_qty = fields.Integer('Shortage', copy=False)
    unshipped_qty = fields.Integer('Unshipped', copy=False)
    qty_invoiced = fields.Float(string='Invoiced Quantity', compute='_compute_invoiced_qty')

    loading_port_id = fields.Many2one(comodel_name='fob.harbour', string='Loading port', )
    etd_date = fields.Date('ETD Date')
    lcno = fields.Char('LC No.')

    discount = fields.Float('Sconto(%)', copy=False)
    no_claim_discount = fields.Float('Sconto NC(%)', copy=False)
    product_brand_id = fields.Many2one('product.brand', string='Brand', help='Select a brand for this product')

    deposit_received = fields.Boolean('Deposit received', copy=False)
    deposit_amount = fields.Monetary('Deposit amount', copy=False)

    shipping_state = fields.Selection([
        ('unshipped', 'unshipped'),
        ('shipped', 'shipped'),
        ('shortage', 'shortage'),
    ], string='Shipping', readonly=False, index=True, copy=False, default='unshipped', track_visibility='onchange')

    po_state = fields.Selection([
        ('new', 'To Assign'),
        ('assigned', 'Assigned'),
        ('invoiced', 'Invoiced'),
        ('cancel', 'Cancelled')
    ], string='Status', readonly=False, index=True, copy=False, default='new', track_visibility='onchange')

    po_name = fields.Char('PO ref number', copy=False)
    inv_name = fields.Char('INV ref number', copy=False)

    price_unit_value = fields.Float('Price unit(v))',compute='_compute_value')
    amount_in_value = fields.Float('Value amount', compute='_compute_value')

    po_id = fields.Many2one(comodel_name='fob.po.order', string='FOB PO Order', copy=False )
    invoice_id = fields.Many2one(comodel_name='account.invoice', string='FOB Invoice', copy=False )

    @api.depends('shortage_qty', 'qty_delivered','pairs_total')
    def _compute_invoiced_qty(self):
        """
        Compute the amounts of the SO line.
        """
        for line in self:
            if line.shortage_qty > 0:
                line.qty_invoiced = line.qty_delivered - line.shortage_qty
                # line.update({
                #     'qty_invoiced': taxes['total_excluded'],
                # })

    @api.depends('product_uom_qty', 'discount', 'price_unit', 'tax_id')
    def _compute_amount(self):
        """
        Compute the amounts of the SO line.
        """
        #Se c'è un no claim contiamo le righe per la media ponderata:
        rows_no = 0
        no_claim = 1
        for line in self:
            if line.order_id.no_claim_discount > 0:
                rows_no = rows_no + 1
        if rows_no > 0:
            no_claim = (line.order_id.no_claim_discount/rows_no)/100
            line.update({'no_claim_discount': no_claim})
        for line in self:
            price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            if no_claim != 1:
                price = price - (price * no_claim)
            taxes = line.tax_id.compute_all(price, line.order_id.currency_id, (line.pairs_total - line.shortage_qty) , product=line.product_id, partner=line.order_id.partner_shipping_id)
            line.update({
                'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                'price_total': taxes['total_included'],
                'price_subtotal': taxes['total_excluded'],
            })

    #@api.depends('product_uom_qty', 'discount', 'price_unit', 'tax_id')
    def _compute_amount_without_discount(self):
        """
        Compute the amounts of the SO line.
        """
        price = self.price_unit
        taxes = self.tax_id.compute_all(price, self.order_id.currency_id, (self.pairs_total - self.shortage_qty), product=self.product_id, partner=self.order_id.partner_shipping_id)
        return({
            'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
            'price_total': taxes['total_included'],
            'price_subtotal': taxes['total_excluded'],
        })

    @api.depends('discount', 'pairs_total', 'product_uom_qty')
    def _compute_value(self):
        for rec in self:
            #convert_to_eur = self.env['res.currency'].search([('name', '=', 'EUR')])
            convert_to_usd = self.env['res.currency'].search([('name', '=', 'USD')])

            #eur_rate = convert_to_eur[0].rate
            usd_rate = convert_to_usd[0].rate

            if rec.order_id.pricelist_id.currency_id.name == 'EUR':
                rate = usd_rate
                rec.amount_in_value = rec.price_subtotal * rate
                rec.price_unit_value = rec.price_unit * rate
            else:
                rate = usd_rate
                rec.amount_in_value = rec.price_subtotal / rate
                rec.price_unit_value = rec.price_unit / rate

            # self.order_id.total_discount_value = self.order_id.total_discount * rate
            # self.order_id.total_amount_in_value = self.order_id.total_discounted_amount * rate
            # rec.amount_in_value = rec.price_subtotal * rate
            # rec.price_unit_value = rec.price_unit_value * rate
        #self[0].order_id.compute_balance()

    def open_pi(self):
        return {
            'context': self.env.context,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'fob.order',
            'res_id': self.order_id.id,
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }

    def open_po(self):
        return {
            'context': self.env.context,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'fob.po.order',
            'res_id': self.po_id.id,
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }

    def open_invoice(self):
        return {
            'context': self.env.context,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.invoice',
            'res_id': self.invoice_id.id,
            'view_id': 	self.env.ref('account.invoice_form').id,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }

    @api.depends('assortment_id', 'range_start', 'range_end')  # ,'range_start','range_end'
    def _compute_pairs_size(self):
        for rec in self:
            pair_sizes = ''
            i = -1
            if rec.assortment_id:
                composition_quantities_sizes = rec.assortment_id.name.split('-')
                composition_sizes = rec.range_end - rec.range_start
                if len(composition_quantities_sizes) != composition_sizes + 1:
                    rec.pairs_size = 'Missing sizes ' + 'No(Pr.):' + str(
                        len(composition_quantities_sizes)) + 'No(Sz.):' + str(composition_sizes + 1) + ' '
                    return

                for size_qty in composition_quantities_sizes:
                    i = i + 1
                    tot_qty = int(size_qty) * int(rec.product_uom_qty)
                    pair_sizes += str(tot_qty) + '(' + str(rec.range_start + i) + ')' + '-'

                rec.pairs_size = pair_sizes[:-1]
            else:
                rec.pairs_size = rec.product_uom_qty

    @api.depends('assortment_id', 'range_start', 'range_end')
    def _compute_pairs_in_pack(self):
        for rec in self:
            # rec.pairs_total =1
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

    @api.depends('assortment_id', 'range_start', 'range_end', 'product_uom_qty')
    def _compute_pairs_total(self):
        # rec.pairs_total =1
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
                        i = i + int(size_qty) * rec.product_uom_qty
                except:
                    i = 0

                rec.pairs_total = i
                rec.qty_delivered = rec.pairs_total
            else:
                rec.pairs_total = rec.product_uom_qty
                rec.qty_delivered = rec.pairs_total

    # @api.onchange('product_uom_qty', 'qty_delivered')
    # def onchange_quantities(self):
    #     self.shortage_qty = self.pairs_total - self.qty_delivered

