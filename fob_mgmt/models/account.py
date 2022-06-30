# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from datetime import datetime, timedelta
from odoo import api, models, fields, _
from odoo.exceptions import UserError

from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from odoo.tools import float_is_zero, float_compare, float_round, pycompat, date_utils
from dateutil.relativedelta import relativedelta

class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    proforma_number = fields.Char('N°Prefattura')
    client_order_ref = fields.Char('Cust.ord.N°')
    container_no = fields.Char('Container')
    tipo_container = fields.Char('Tipo container')
    seal_no = fields.Char('Sigillo')
    bl_code = fields.Char('BL')
    route = fields.Char('Route')
    incoterms = fields.Char('INCOTERMS')
    incoterm_id = fields.Many2one(comodel_name='fob.incoterms', string='Incoterms', )
    origin_goods = fields.Char('Origin of goods')
    loading_port_id = fields.Many2one(comodel_name='fob.harbour', string='Loading port',)
    destination_port_id = fields.Many2one(comodel_name='fob.harbour', string='Destination port',)
    etd_date = fields.Date('ETD Date')
    eta_date = fields.Date('ETA Date')
    loading_date = fields.Date('Date of loading')
    lcno = fields.Char('LC No.')
    deposit_amount = fields.Monetary('Deposit amount')
    shipped = fields.Boolean('Shipped')
    partner_bank = fields.Many2one('res.partner.bank', string='Bank Account')

    default_currency_id = fields.Many2one("res.currency", compute='_compute_currency_id', string="Currency")

    invoice_accounts = fields.One2many('fob.order.accounts', 'invoice_id', 'Invoice accounts')

    no_claim_discount = fields.Float('No claim discount(%)')
    total_discount = fields.Float('Total discount')
    total_discount_value = fields.Float('Total discount(value)')
    deposit_expected = fields.Monetary('Dep. expected')
    deposit_received = fields.Monetary('Dep. received')
    deposit_pending_balance = fields.Monetary('Dep.Pending balance')
    total_pending_balance = fields.Monetary('Tot.Pending balance')
    # rec_balance = fields.Monetary('Rec. balance')
    # currency_selection_id = fields.Many2one('res.currency', string='Currency')

    packs_total = fields.Integer('Total packs') #, compute='_compute_packs'

    total_amount_in_value =fields.Float('Value total amount')
    total_discounted_amount = fields.Float('Total amount(w/no claim discount)')

    total_value_price = fields.Monetary("Value price", compute='_compute_total_value_price')

    pi_order_id = fields.Many2one(comodel_name='fob.order', string='PI', readonly=True)

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
        for line in self.invoice_line_ids:
            line._compute_price()
            total_amount = total_amount + line._compute_price_without_discount()['price_subtotal']

        #if self.no_claim_discount > 0:
        self.total_discount = total_amount - self.amount_total #* self.no_claim_discount/100
        self.total_discounted_amount = total_amount - self.total_discount
        deposit_received = 0
        total_received = 0
        if self.payment_term_id:
            self.deposit_expected = (self.amount_total) * (self.payment_term_id.line_ids[0].value_amount / 100)
            for acc in self.invoice_accounts:
                if acc.received and acc.is_deposit:
                    deposit_received += acc.deposit
                if acc.received and not acc.is_deposit:
                    total_received += acc.deposit
            self.deposit_received = deposit_received
            self.deposit_pending_balance = self.deposit_expected - deposit_received
            self.total_pending_balance = self.amount_total - total_received - deposit_received
            self.payment_start_date = self.etd_date + timedelta(days=self.payment_term_id.line_ids[0].days)
        else:
            for acc in self.invoice_accounts:
                if acc.received and acc.is_deposit:
                    deposit_received += acc.deposit
                if acc.received and not acc.is_deposit:
                    total_received += acc.deposit
            self.deposit_received = deposit_received
            self.deposit_pending_balance = self.deposit_expected - deposit_received
            self.total_pending_balance = self.amount_total - total_received - deposit_received
            self.payment_start_date = self.etd_date + timedelta(days=self.payment_term_id.line_ids[0].days)

        convert_to_usd = self.env['res.currency'].search([('name', '=', 'USD')])

        usd_rate = convert_to_usd[0].rate

        rate = usd_rate
        if self.currency_id.name == 'EUR':
            self.total_discount_value = self.total_discount * rate
            self.total_amount_in_value = self.total_discounted_amount * rate
        else:
            self.total_discount_value = self.total_discount / rate
            self.total_amount_in_value = self.total_discounted_amount / rate

        # ACCONTO / TOT.FATTURA * TOTALE RIGA
        # rows_no = 0
        # if self.deposit_received > 0:
        #     for row in self.invoice_line_ids:
        #         rows_no = rows_no + 1
        #         assign_balance = self.deposit_received / self.amount_total * row.price_subtotal
        #         if assign_balance > 0:
        #             row.deposit_amount = assign_balance
        #             row.deposit_received = 1
        #             row.amount_in_value = row.price_subtotal * rate

        if self.pi_order_id:
            self.pi_order_id.tipo_container = self.tipo_container
            self.pi_order_id.container_no = self.container_no
            self.pi_order_id.seal_no = self.seal_no
            self.pi_order_id.bl_code = self.bl_code
            self.pi_order_id.route = self.route
            self.pi_order_id.loading_port_id = self.loading_port_id
            self.pi_order_id.destination_port_id = self.destination_port_id
            self.pi_order_id.etd_date = self.etd_date
            self.pi_order_id.eta_date = self.eta_date

    def compute_accounts(self):
        if self.payment_term_id and not self.order_accounts:
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
                    self.invoice_accounts.create({'order_id': self.id, 'date': data, 'deposit': amount, 'is_deposit': 1})
                else:
                    self.invoice_accounts.create({'order_id': self.id, 'date': data, 'deposit': amount})

    def set_rows(self):
        for row in self.invoice_line_ids:
            row.container_no = self.container_no
            row.tipo_container = self.tipo_container
            row.seal_no = self.seal_no
            # row.discount = self.discount
            # row.product_brand_id = self.product_brand_id
            # row.client_order_ref = self.client_order_ref

    def _compute_currency_id(self):
        curr = self.env['res.currency']
        currency_convert_to = curr.browse(1)
        self.default_currency_id = currency_convert_to

    def _compute_total_value_price(self):
        currency = self.currency_id or None
        self.total_value_price = currency._convert(self.amount_total, self.default_currency_id, self.company_id or self.env.user.company_id, self.date_invoice or fields.Date.today())

    @api.onchange('shipped')
    def onchange_shipped(self):
        for rows in self.invoice_line_ids:
            if self.shipped:
                if rows.shortage_qty > 0:
                    rows.shipping_state = 'shortage'
                    rows.qty_delivered = rows.pairs_total - rows.shortage_qty
                else:
                    rows.shipping_state = 'shipped'
                    rows.qty_delivered = rows.pairs_total - rows.unshipped_qty
                pi_rows = self.env['fob.order.line'].search([('id', '=', rows.pi_id.id)])
                for pi in pi_rows:
                    pi.write({'shipping_state': rows.shipping_state, 'shortage_qty': rows.shortage_qty, 'unshipped_qty': rows.unshipped_qty, 'qty_delivered': rows.qty_delivered})
                po_rows = self.env['fob.po.order.line'].search([('id', '=', rows.pi_id.id)])
                for po in pi_rows:
                    po.write({'shipping_state': rows.shipping_state, 'shortage_qty': rows.shortage_qty, 'unshipped_qty': rows.unshipped_qty, 'qty_delivered': rows.qty_delivered})
            else:
                rows.shipping_state = 'unshipped'
                pi_rows = self.env['fob.order.line'].search([('id', '=', rows.pi_id.id)])
                for pi in pi_rows:
                    pi.write({'shipping_state': 'unshipped'})
                po_rows = self.env['fob.po.order.line'].search([('pi_id', '=', rows.pi_id.id)])
                for po in po_rows:
                    po.write({'shipping_state': 'unshipped'})

# class FobPOrderAccountsLine(models.Model):
#     _name = 'account.invoice.accounts'
#     _description = 'Acconti fattura'
#
#     invoice_id = fields.Many2one('account.invoice', string='Order Reference')
#     currency_id = fields.Many2one(related='invoice_id.currency_id', depends=['invoice_id'], store=True, string='Currency', readonly=True)
#     name = fields.Text(string='Description')
#     date = fields.Date('Date')
#     deposit = fields.Monetary('Deposit')
#     received = fields.Boolean('Received')

class AccountInvoiceLine(models.Model):
    _inherit = "account.invoice.line"

    proforma_number = fields.Char(related='invoice_id.proforma_number', depends=['invoice_id'], store=True, readonly=True)
    container_no = fields.Char('Container')
    tipo_container = fields.Char('Tipo container')
    seal_no = fields.Char('Sigillo')
    journal_id = fields.Many2one('account.journal', related='invoice_id.journal_id')

    deposit_received = fields.Boolean('Deposit received', copy=False)
    deposit_amount = fields.Monetary('Deposit amount', copy=False)

    qty_delivered = fields.Integer('Qta consegnata')
    shipping_state = fields.Selection([
        ('unshipped', 'unshipped'),
        ('shipped', 'shipped'),
        ('shortage', 'shortage'),
    ], string='Shipping', readonly=False, index=True, copy=False, default='unshipped', track_visibility='onchange')
    shortage_qty = fields.Integer('shortage_qty')
    unshipped_qty = fields.Integer('Unshipped')

    pairs_in_pack = fields.Integer('Pairs in pack') #, compute='_compute_pairs_in_pack'

    default_currency_id = fields.Many2one(related='invoice_id.currency_id', string="Currency")
    # value_price = fields.Monetary(related='invoice_id.currency_id', string="Value price")
    # default_currency_id = fields.Many2one("res.currency", compute='_compute_currency_id', string="Currency")
    value_unit_price = fields.Float("Value price unit", compute='_compute_value_price', store=True)
    value_price = fields.Float("Value price", compute='_compute_value_price', store=True)
    no_claim_discount = fields.Float('Sconto NC(%)')
    pi_id = fields.Many2one(comodel_name='fob.order.line', string='Proforma invoice row id', )

    # def _compute_currency_id(self):
    #     curr = self.env['res.currency']
    #     currency_convert_to = curr.browse(1)
    #     self.default_currency_id = currency_convert_to
    #
    def compute_shortage(self):
        if self.invoice_id.shipped:
            if self.shortage_qty > 0:
                self.shipping_state = 'shortage'
                self.qty_delivered = self.pairs_total - self.shortage_qty
            else:
                self.shipping_state = 'shipped'
                self.qty_delivered = self.pairs_total - self.unshipped_qty

        if self.unshipped_qty > 0:
            self.shortage_qty = self.unshipped_qty
            self.shipping_state = 'shortage'

        pi_rows = self.env['fob.order.line'].search([('id', '=', self.pi_id.id)])
        for pi in pi_rows:
            pi.write({'shipping_state': self.shipping_state, 'shortage_qty': self.shortage_qty,
                      'unshipped_qty': self.unshipped_qty, 'qty_delivered': self.qty_delivered})
            pi._compute_amount()
            pi.order_id._amount_all()
        po_rows = self.env['fob.po.order.line'].search([('pi_id', '=', self.pi_id.id)])
        for po in po_rows:
            po.write({'shipping_state': self.shipping_state, 'shortage_qty': self.shortage_qty,
                      'unshipped_qty': self.unshipped_qty, 'qty_delivered': self.qty_delivered})
            po._compute_amount()
            po.order_id._amount_all()

    @api.depends('quantity', 'discount', 'default_currency_id')
    def _compute_value_price(self):
        for rec in self:
            #convert_to_eur = self.env['res.currency'].search([('name', '=', 'EUR')])
            convert_to_usd = self.env['res.currency'].search([('name', '=', 'USD')])

            #eur_rate = convert_to_eur[0].rate
            usd_rate = convert_to_usd[0].rate

            if rec.invoice_id.currency_id.name == 'EUR':
                rate = usd_rate
                rec.value_price = rec.price_subtotal * rate
                rec.value_unit_price = rec.price_unit * rate
            else:
                rate = usd_rate
                rec.value_price = rec.price_subtotal / rate
                rec.value_unit_price = rec.price_unit / rate


        # convert_to_eur = self.env['res.currency'].search([('name', '=', 'EUR')])
        # convert_to_usd = self.env['res.currency'].search([('name', '=', 'USD')])
        #
        # eur_rate = convert_to_eur[0].rate
        # usd_rate = convert_to_usd[0].rate
        #
        # if self.invoice_id.currency_id.name == 'EUR':
        #     rate = usd_rate
        # else:
        #     rate = eur_rate

        # self.value_price = self.price_subtotal * rate
        # self.value_unit_price = self.price_unit * rate

        # try:
        #     currency = self.invoice_id and self.invoice_id.currency_id or None
        #     self.value_price = currency._convert(self.price_subtotal, self.default_currency_id, self.company_id or self.env.user.company_id, self.invoice_id.date_invoice or fields.Date.today())
        #     self.value_unit_price = currency._convert(self.price_unit, self.default_currency_id, self.company_id or self.env.user.company_id, self.invoice_id.date_invoice or fields.Date.today())
        # except:
        #     pass #self.value_price = 0

    @api.one
    @api.depends('price_unit', 'discount', 'invoice_line_tax_ids', 'quantity',
        'invoice_id.partner_id', 'invoice_id.currency_id', 'invoice_id.company_id',
        'invoice_id.date', 'shortage_qty', 'shipping_state')
    def _compute_price(self):
        rows_no = 0
        no_claim = 1
        for line in self:
            if line.invoice_id.no_claim_discount > 0:
                rows_no = rows_no + 1
        if rows_no > 0:
            no_claim = (line.invoice_id.no_claim_discount/rows_no)/100
            line.update({'no_claim_discount': no_claim})
        currency = self.invoice_id and self.invoice_id.currency_id or None
        price = self.price_unit * (1 - (self.discount or 0.0) / 100.0)
        if no_claim != 1:
            price = price - (price * no_claim)
        taxes = False
        if self.invoice_line_tax_ids:
            taxes = self.invoice_line_tax_ids.compute_all(price, currency, (self.quantity - self.shortage_qty), product=self.product_id, partner=self.invoice_id.partner_id)
        self.price_subtotal = price_subtotal_signed = taxes['total_excluded'] if taxes else (self.quantity - self.shortage_qty) * price
        self.price_total = taxes['total_included'] if taxes else self.price_subtotal
        if self.invoice_id.currency_id and self.invoice_id.currency_id != self.invoice_id.company_id.currency_id:
            currency = self.invoice_id.currency_id
            date = self.invoice_id._get_currency_rate_date()
            price_subtotal_signed = currency._convert(price_subtotal_signed, self.invoice_id.company_id.currency_id, self.company_id or self.env.user.company_id, date or fields.Date.today())
        sign = self.invoice_id.type in ['in_refund', 'out_refund'] and -1 or 1
        self.price_subtotal_signed = price_subtotal_signed * sign

    def _compute_price_without_discount(self):
        currency = self.invoice_id and self.invoice_id.currency_id or None
        price = self.price_unit #* (1 - (self.discount or 0.0) / 100.0)
        taxes = False
        if self.invoice_line_tax_ids:
            taxes = self.invoice_line_tax_ids.compute_all(price, currency, (self.quantity - self.shortage_qty), product=self.product_id, partner=self.invoice_id.partner_id)
        price_subtotal = price_subtotal_signed = taxes['total_excluded'] if taxes else (self.quantity - self.shortage_qty) * price
        #self.price_total = taxes['total_included'] if taxes else self.price_subtotal
        # if self.invoice_id.currency_id and self.invoice_id.currency_id != self.invoice_id.company_id.currency_id:
        #     currency = self.invoice_id.currency_id
        #     date = self.invoice_id._get_currency_rate_date()
        #     price_subtotal_signed = currency._convert(price_subtotal_signed, self.invoice_id.company_id.currency_id, self.company_id or self.env.user.company_id, date or fields.Date.today())
        # sign = self.invoice_id.type in ['in_refund', 'out_refund'] and -1 or 1
        # self.price_subtotal_signed = price_subtotal_signed * sign
        return({
            'price_subtotal': price_subtotal,
        })
# Fatturo da ordini di vendita assegnati (con numerazione/registro indipendente)
# Campi editabili:
# -	Nr di BL
# -	Nr CONTAINER e nr sigillo (sia in testata che per riga – suddivisione per righe in caso di + container su stessa fattura)
# -	Resa merce (INCOTERMS) (ad es FOB XIAMEN)
# -	Origin of goods
# -	Shipping: porto di imbarco + porto di arrivo
# -	Nome nave (campo Route)
# -	ETD ed ETA (date previste partenza nave e arrivo nave)
# -	Data caricamento merce da parte del fornitore (Date of loading): questa data viene poi riportata automaticamente nelle PO collegate alla fattura e viene utilizzata per calcolare le scadenze dei saldi dovuti ai fornitori e visibile nel PO REPORT
# Campi auto-compilati:
# -	Eventuale NR LC (riportato dalla PI)
# -	Importo eventuale acconto ricevuto (riportato in base alle registrazioni effettuate nella PI)
# Flag SHIPPED: la fattura viene generata diversi giorni prima della partenza effettiva della merce, questo flag serve a confermare che la merce effettivamente è partita e quindi solo con lo stato SHIPPED le qtà in tutti i documenti PI, PO e FATTURA diventano da UNSHIPPED a SHIPPED o SHORTAGE (si vedano anche i vari excel dei report)

class PAoutInherit(models.Model):
    _inherit = 'fatturapa.attachment.out'

    number = fields.Char('Number', compute='_compute_number', store=True)

    @api.depends('out_invoice_ids')
    def _compute_number(self):
        for rec in self:
            if rec.out_invoice_ids:
                rec.number = rec.out_invoice_ids[0].number
