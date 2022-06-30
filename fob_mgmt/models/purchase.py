# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.osv import expression
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from odoo.tools.float_utils import float_compare
from odoo.exceptions import UserError, AccessError
from odoo.tools.misc import formatLang
from odoo.addons import decimal_precision as dp


class PurchaseOrder(models.Model):
    _name = "fob.po.order"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _description = "Purchase Order"
    _order = 'date_order desc, id desc'

    @api.depends('order_line.price_total')
    def _amount_all(self):
        for order in self:
            amount_untaxed = amount_tax = 0.0
            for line in order.order_line:
                amount_untaxed += line.price_subtotal
                amount_tax += line.price_tax
            order.update({
                'amount_untaxed': order.currency_id.round(amount_untaxed),
                'amount_tax': order.currency_id.round(amount_tax),
                'amount_total': amount_untaxed + amount_tax,
            })

    # @api.depends('order_line.date_planned', 'date_order')
    # def _compute_date_planned(self):
    #     for order in self:
    #         min_date = False
    #         for line in order.order_line:
    #             if not min_date or line.date_planned < min_date:
    #                 min_date = line.date_planned
    #         if min_date:
    #             order.date_planned = min_date
    #         else:
    #             order.date_planned = order.date_order

    @api.depends('state', 'order_line.qty_invoiced', 'order_line.qty_received', 'order_line.product_qty')
    def _get_invoiced(self):
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for order in self:
            if order.state not in ('purchase', 'done'):
                order.invoice_status = 'no'
                continue

            if any(float_compare(line.qty_invoiced, line.product_qty if line.product_id.purchase_method == 'purchase' else line.qty_received, precision_digits=precision) == -1 for line in order.order_line):
                order.invoice_status = 'to invoice'
            elif all(float_compare(line.qty_invoiced, line.product_qty if line.product_id.purchase_method == 'purchase' else line.qty_received, precision_digits=precision) >= 0 for line in order.order_line) and order.invoice_ids:
                order.invoice_status = 'invoiced'
            else:
                order.invoice_status = 'no'

    @api.depends('order_line.invoice_lines.invoice_id')
    def _compute_invoice(self):
        for order in self:
            invoices = self.env['account.invoice']
            for line in order.order_line:
                invoices |= line.invoice_lines.mapped('invoice_id')
            order.invoice_ids = invoices
            order.invoice_count = len(invoices)

    READONLY_STATES = {
        'purchase': [('readonly', True)],
        'done': [('readonly', True)],
        'cancel': [('readonly', True)],
    }

    name = fields.Char('Order Reference', required=True, index=True, copy=False, default='New')
    origin = fields.Char('Source Document', copy=False,
        help="Reference of the document that generated this purchase order "
             "request (e.g. a sales order)")
    partner_ref = fields.Char('Vendor Reference', copy=False,
        help="Reference of the sales order or bid sent by the vendor. "
             "It's used to do the matching when you receive the "
             "products as this reference is usually written on the "
             "delivery order sent by your vendor.")
    date_order = fields.Datetime('Order Date', required=True, states=READONLY_STATES, index=True, copy=False, default=fields.Datetime.now,\
        help="Depicts the date where the Quotation should be validated and converted into a purchase order.")
    date_approve = fields.Date('Approval Date', readonly=1, index=True, copy=False)
    partner_id = fields.Many2one('res.partner', string='Vendor', required=True, states=READONLY_STATES, change_default=True, track_visibility='always', help="You can find a vendor by its Name, TIN, Email or Internal Reference.")
    dest_address_id = fields.Many2one('res.partner', string='Drop Ship Address', states=READONLY_STATES,
        help="Put an address if you want to deliver directly from the vendor to the customer. "
             "Otherwise, keep empty to deliver to your own company.")
    currency_id = fields.Many2one('res.currency', 'Currency', required=True, states=READONLY_STATES,
        default=lambda self: self.env.user.company_id.currency_id.id)
    state = fields.Selection([
        ('draft', 'RFQ'),
        ('sent', 'RFQ Sent'),
        ('to approve', 'To Approve'),
        ('purchase', 'Purchase Order'),
        ('done', 'Locked'),
        ('cancel', 'Cancelled')
    ], string='Status', readonly=True, index=True, copy=False, default='draft', track_visibility='onchange')
    order_line = fields.One2many('fob.po.order.line', 'order_id', string='Order Lines', states={'cancel': [('readonly', True)], 'done': [('readonly', True)]}, copy=True)
    notes = fields.Text('Terms and Conditions')

    invoice_count = fields.Integer(compute="_compute_invoice", string='Bill Count', copy=False, default=0, store=True)
    invoice_ids = fields.Many2many('account.invoice', compute="_compute_invoice", string='Bills', copy=False, store=True)
    invoice_status = fields.Selection([
        ('no', 'Nothing to Bill'),
        ('to invoice', 'Waiting Bills'),
        ('invoiced', 'No Bill to Receive'),
    ], string='Billing Status', compute='_get_invoiced', store=True, readonly=True, copy=False, default='no')

    # There is no inverse function on purpose since the date may be different on each line
    # date_planned = fields.Datetime(string='Scheduled Date', compute='_compute_date_planned', store=True, index=True)
    date_planned = fields.Datetime(string='Scheduled Date', store=True, index=True)

    amount_untaxed = fields.Monetary(string='Untaxed Amount', store=True, readonly=True, compute='_amount_all', track_visibility='always')
    amount_tax = fields.Monetary(string='Taxes', store=True, readonly=True, compute='_amount_all')
    amount_total = fields.Monetary(string='Total', store=True, readonly=True, compute='_amount_all')

    fiscal_position_id = fields.Many2one('account.fiscal.position', string='Fiscal Position', oldname='fiscal_position')
    payment_term_id = fields.Many2one('account.payment.term', 'Payment Terms')
    incoterm_id = fields.Many2one('account.incoterms', 'Incoterm', states={'done': [('readonly', True)]}, help="International Commercial Terms are a series of predefined commercial terms used in international transactions.")

    product_id = fields.Many2one('product.product', related='order_line.product_id', string='Product', readonly=False)
    user_id = fields.Many2one('res.users', string='Purchase Representative', index=True, track_visibility='onchange', default=lambda self: self.env.user)
    company_id = fields.Many2one('res.company', 'Company', required=True, index=True, states=READONLY_STATES, default=lambda self: self.env.user.company_id.id)

    def _compute_access_url(self):
        super(PurchaseOrder, self)._compute_access_url()
        for order in self:
            order.access_url = '/my/purchase/%s' % (order.id)

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
        args = args or []
        domain = []
        if name:
            domain = ['|', ('name', operator, name), ('partner_ref', operator, name)]
        purchase_order_ids = self._search(expression.AND([domain, args]), limit=limit, access_rights_uid=name_get_uid)
        return self.browse(purchase_order_ids).name_get()

    @api.multi
    @api.depends('name', 'partner_ref')
    def name_get(self):
        result = []
        for po in self:
            name = po.name
            if po.partner_ref:
                name += ' (' + po.partner_ref + ')'
            if self.env.context.get('show_total_amount') and po.amount_total:
                name += ': ' + formatLang(self.env, po.amount_total, currency_obj=po.currency_id)
            result.append((po.id, name))
        return result

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('fob.po.order') or '/'
        return super(PurchaseOrder, self).create(vals)

    @api.multi
    def unlink(self):
        for order in self:
            if not order.state == 'cancel':
                raise UserError(_('In order to delete a purchase order, you must cancel it first.'))
        return super(PurchaseOrder, self).unlink()

    @api.multi
    def copy(self, default=None):
        new_po = super(PurchaseOrder, self).copy(default=default)
        for line in new_po.order_line:
            seller = line.product_id._select_seller(
                partner_id=line.partner_id, quantity=line.product_qty,
                date=line.order_id.date_order and line.order_id.date_order.date(), uom_id=line.product_uom)
            line.date_planned = line._get_date_planned(seller)
        return new_po

    @api.multi
    def _track_subtype(self, init_values):
        self.ensure_one()
        if 'state' in init_values and self.state == 'purchase':
            return 'purchase.mt_rfq_approved'
        elif 'state' in init_values and self.state == 'to approve':
            return 'purchase.mt_rfq_confirmed'
        elif 'state' in init_values and self.state == 'done':
            return 'purchase.mt_rfq_done'
        return super(PurchaseOrder, self)._track_subtype(init_values)

    @api.onchange('partner_id', 'company_id')
    def onchange_partner_id(self):
        if not self.partner_id:
            self.fiscal_position_id = False
            self.payment_term_id = False
            self.currency_id = self.env.user.company_id.currency_id.id
        else:
            self.fiscal_position_id = self.env['account.fiscal.position'].with_context(company_id=self.company_id.id).get_fiscal_position(self.partner_id.id)
            self.payment_term_id = self.partner_id.property_supplier_payment_term_id.id
            self.currency_id = self.partner_id.property_purchase_currency_id.id or self.env.user.company_id.currency_id.id
        return {}

    @api.onchange('fiscal_position_id')
    def _compute_tax_id(self):
        """
        Trigger the recompute of the taxes if the fiscal position is changed on the PO.
        """
        for order in self:
            order.order_line._compute_tax_id()

    @api.onchange('partner_id')
    def onchange_partner_id_warning(self):
        if not self.partner_id:
            return
        warning = {}
        title = False
        message = False

        partner = self.partner_id

        # If partner has no warning, check its company
        if partner.purchase_warn == 'no-message' and partner.parent_id:
            partner = partner.parent_id

        if partner.purchase_warn and partner.purchase_warn != 'no-message':
            # Block if partner only has warning but parent company is blocked
            if partner.purchase_warn != 'block' and partner.parent_id and partner.parent_id.purchase_warn == 'block':
                partner = partner.parent_id
            title = _("Warning for %s") % partner.name
            message = partner.purchase_warn_msg
            warning = {
                'title': title,
                'message': message
            }
            if partner.purchase_warn == 'block':
                self.update({'partner_id': False})
            return {'warning': warning}
        return {}

    @api.multi
    def action_rfq_send(self):
        '''
        This function opens a window to compose an email, with the edi purchase template message loaded by default
        '''
        self.ensure_one()
        ir_model_data = self.env['ir.model.data']
        try:
            if self.env.context.get('send_rfq', False):
                template_id = ir_model_data.get_object_reference('purchase', 'email_template_edi_purchase')[1]
            else:
                template_id = ir_model_data.get_object_reference('purchase', 'email_template_edi_purchase_done')[1]
        except ValueError:
            template_id = False
        try:
            compose_form_id = ir_model_data.get_object_reference('mail', 'email_compose_message_wizard_form')[1]
        except ValueError:
            compose_form_id = False
        ctx = dict(self.env.context or {})
        ctx.update({
            'default_model': 'fob.po.order',
            'default_res_id': self.ids[0],
            'default_use_template': bool(template_id),
            'default_template_id': template_id,
            'default_composition_mode': 'comment',
            'custom_layout': "mail.mail_notification_paynow",
            'force_email': True,
            'mark_rfq_as_sent': True,
        })

        # In the case of a RFQ or a PO, we want the "View..." button in line with the state of the
        # object. Therefore, we pass the model description in the context, in the language in which
        # the template is rendered.
        lang = self.env.context.get('lang')
        if {'default_template_id', 'default_model', 'default_res_id'} <= ctx.keys():
            template = self.env['mail.template'].browse(ctx['default_template_id'])
            if template and template.lang:
                lang = template._render_template(template.lang, ctx['default_model'], ctx['default_res_id'])

        self = self.with_context(lang=lang)
        if self.state in ['draft', 'sent']:
            ctx['model_description'] = _('Request for Quotation')
        else:
            ctx['model_description'] = _('Purchase Order')

        return {
            'name': _('Compose Email'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form_id, 'form')],
            'view_id': compose_form_id,
            'target': 'new',
            'context': ctx,
        }

    @api.multi
    @api.returns('mail.message', lambda value: value.id)
    def message_post(self, **kwargs):
        if self.env.context.get('mark_rfq_as_sent'):
            self.filtered(lambda o: o.state == 'draft').write({'state': 'sent'})
        return super(PurchaseOrder, self.with_context(mail_post_autofollow=True)).message_post(**kwargs)

    @api.multi
    def print_quotation(self):
        self.write({'state': "sent"})
        return self.env.ref('purchase.report_purchase_quotation').report_action(self)

    @api.multi
    def button_approve(self, force=False):
        self.write({'state': 'purchase', 'date_approve': fields.Date.context_today(self)})
        self.filtered(lambda p: p.company_id.po_lock == 'lock').write({'state': 'done'})
        return {}

    @api.multi
    def button_draft(self):
        self.write({'state': 'draft'})
        return {}

    @api.multi
    def button_confirm(self):
        for order in self:
            if order.state not in ['draft', 'sent']:
                continue
            #order._add_supplier_to_product()
            # Deal with double validation process
            if order.company_id.po_double_validation == 'one_step'\
                    or (order.company_id.po_double_validation == 'two_step'\
                        and order.amount_total < self.env.user.company_id.currency_id._convert(
                            order.company_id.po_double_validation_amount, order.currency_id, order.company_id, order.date_order or fields.Date.today()))\
                    or order.user_has_groups('purchase.group_purchase_manager'):
                order.button_approve()
            else:
                order.write({'state': 'to approve'})
        return True

    @api.multi
    def button_cancel(self):
        for order in self:
            for inv in order.invoice_ids:
                if inv and inv.state not in ('cancel', 'draft'):
                    raise UserError(_("Unable to cancel this purchase order. You must first cancel the related vendor bills."))

        self.write({'state': 'cancel'})

    @api.multi
    def button_unlock(self):
        self.write({'state': 'purchase'})

    @api.multi
    def button_done(self):
        self.write({'state': 'done'})

    @api.multi
    def _add_supplier_to_product(self):
        # Add the partner in the supplier list of the product if the supplier is not registered for
        # this product. We limit to 10 the number of suppliers for a product to avoid the mess that
        # could be caused for some generic products ("Miscellaneous").
        for line in self.order_line:
            # Do not add a contact as a supplier
            partner = self.partner_id if not self.partner_id.parent_id else self.partner_id.parent_id
            if partner not in line.product_id.seller_ids.mapped('name') and len(line.product_id.seller_ids) <= 10:
                currency = partner.property_purchase_currency_id or self.env.user.company_id.currency_id
                supplierinfo = {
                    'name': partner.id,
                    'sequence': max(line.product_id.seller_ids.mapped('sequence')) + 1 if line.product_id.seller_ids else 1,
                    'product_uom': line.product_uom.id,
                    'min_qty': 0.0,
                    'price': self.currency_id._convert(line.price_unit, currency, line.company_id, line.date_order or fields.Date.today(), round=False),
                    'currency_id': currency.id,
                    'delay': 0,
                }
                # In case the order partner is a contact address, a new supplierinfo is created on
                # the parent company. In this case, we keep the product name and code.
                seller = line.product_id._select_seller(
                    partner_id=line.partner_id,
                    quantity=line.product_qty,
                    date=line.order_id.date_order and line.order_id.date_order.date(),
                    uom_id=line.product_uom)
                if seller:
                    supplierinfo['product_name'] = seller.product_name
                    supplierinfo['product_code'] = seller.product_code
                vals = {
                    'seller_ids': [(0, 0, supplierinfo)],
                }
                try:
                    line.product_id.write(vals)
                except AccessError:  # no write access rights -> just ignore
                    break

    # @api.multi
    # def action_view_invoice(self):
    #     '''
    #     This function returns an action that display existing vendor bills of given purchase order ids.
    #     When only one found, show the vendor bill immediately.
    #     '''
    #     action = self.env.ref('account.action_vendor_bill_template')
    #     result = action.read()[0]
    #     create_bill = self.env.context.get('create_bill', False)
    #     # override the context to get rid of the default filtering
    #     result['context'] = {
    #         'type': 'out_invoice',
    #         'default_purchase_id': self.id,
    #         'default_currency_id': self.currency_id.id,
    #         'default_company_id': self.company_id.id,
    #         'company_id': self.company_id.id
    #     }
    #     # choose the view_mode accordingly
    #     if len(self.invoice_ids) > 1 and not create_bill:
    #         result['domain'] = "[('id', 'in', " + str(self.invoice_ids.ids) + ")]"
    #     else:
    #         res = self.env.ref('account.invoice_supplier_form', False)
    #         result['views'] = [(res and res.id or False, 'form')]
    #         # Do not set an invoice_id if we want to create a new bill.
    #         if not create_bill:
    #             result['res_id'] = self.invoice_ids.id or False
    #     result['context']['default_origin'] = self.name
    #     result['context']['default_reference'] = self.partner_ref
    #     return result

    @api.multi
    def action_set_date_planned(self):
        for order in self:
            order.order_line.update({'date_planned': order.date_planned})

    @api.multi
    def _prepare_invoice(self, journal_id):
        """
        Prepare the dict of values to create the new invoice for a sales order. This method may be
        overridden to implement custom invoice generation (making sure to call super() to establish
        a clean extension chain).
        """
        self.ensure_one()
        company_id = self.company_id.id
        #journal_id = self.env['ir.config_parameter'].sudo().get_param('fob_mgmt.fob_journal_id')
        if not journal_id:
            raise UserError(_('Please define an accounting sales journal in FOB configuration.'))
        invoice_vals = {
            'name': '',
            'origin': self.name,
            'type': 'out_invoice',
            'account_id': self.partner_id.property_account_receivable_id.id,
            'partner_id': self.partner_id.id,
            'lcno': self.lcno,
            'etd_date': self.etd_date,
            'eta_date': self.eta_date,
            'loading_port_id': self.loading_port_id.id,
            #'partner_shipping_id': self.partner_shipping_id.id,
            'journal_id': journal_id,
            'currency_id': self.currency_id.id,
            'comment': self.notes,
            'payment_term_id': self.payment_term_id.id,
            'fiscal_position_id': self.fiscal_position_id.id or self.partner_id.property_account_position_id.id,
            'company_id': company_id,
            'user_id': self.user_id and self.user_id.id,
            'team_id': self.user_id.id,
            #'transaction_ids': [(6, 0, self.transaction_ids.ids)],
        }
        return invoice_vals

    @api.multi
    def print_quotation(self):
        self.filtered(lambda s: s.state == 'draft').write({'state': 'sent'})

        return self.env.ref('sale.action_report_saleorder')\
            .with_context(discard_logo_check=True).report_action(self)

    @api.multi
    def action_view_invoice(self):
        invoices = self.mapped('invoice_ids')
        action = self.env.ref('account.action_invoice_tree1').read()[0]
        if len(invoices) > 1:
            action['domain'] = [('id', 'in', invoices.ids)]
        elif len(invoices) == 1:
            action['views'] = [(self.env.ref('account.invoice_form').id, 'form')]
            action['res_id'] = invoices.ids[0]
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

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
            # Use additional field helper function (for account extensions)
            #for line in invoice.invoice_line_ids:
            #    line._set_additional_fields(invoice)
            # Necessary to force computation of taxes. In account_invoice, they are triggered
            # by onchanges, which are not triggered when doing a create.
            invoice.compute_taxes()
            # Idem for partner
            so_payment_term_id = invoice.payment_term_id.id
            #invoice._onchange_partner_id()
            # To keep the payment terms set on the SO
            invoice.payment_term_id = so_payment_term_id
            invoice.message_post_with_view('mail.message_origin_link',
                values={'self': invoice, 'origin': references[invoice]},
                subtype_id=self.env.ref('mail.mt_note').id)

    @api.multi
    def action_invoice_create(self, journal_id, grouped=False, final=False):
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
            group_key = order.id if grouped else (order.partner_id.id, order.currency_id.id)

            # We only want to create sections that have at least one invoiceable line
            pending_section = None

            # Create lines in batch to avoid performance problems
            line_vals_list = []
            # sequence is the natural order of order_lines
            for line in order.order_line:
                # if line.display_type == 'line_section':
                #     pending_section = line
                #     continue
                # if float_is_zero(line.qty_to_invoice, precision_digits=precision):
                #     continue
                if group_key not in invoices:
                    inv_data = order._prepare_invoice(journal_id)
                    invoice = inv_obj.create(inv_data)
                    references[invoice] = order
                    invoices[group_key] = invoice
                    invoices_origin[group_key] = [invoice.origin]
                    invoices_name[group_key] = [invoice.name]
                elif group_key in invoices:
                    if order.name not in invoices_origin[group_key]:
                        invoices_origin[group_key].append(order.name)
                    # if order.client_order_ref and order.client_order_ref not in invoices_name[group_key]:
                    #     invoices_name[group_key].append(order.client_order_ref)

                if line.product_qty > 0 or (line.product_qty < 0 and final):
                    if pending_section:
                        section_invoice = pending_section.invoice_line_create_vals(
                            invoices[group_key].id,
                            pending_section.pairs_total
                        )
                        inv_line_sequence += 1
                        section_invoice[0]['sequence'] = inv_line_sequence
                        line_vals_list.extend(section_invoice)
                        pending_section = None

                    inv_line_sequence += 1
                    inv_line = line.invoice_line_create_vals(
                        invoices[group_key].id, line.pairs_total
                    )
                    inv_line[0]['sequence'] = inv_line_sequence
                    line_vals_list.extend(inv_line)

            if references.get(invoices.get(group_key)):
                if order not in references[invoices[group_key]]:
                    references[invoices[group_key]] |= order

            self.env['account.invoice.line'].create(line_vals_list)

        for group_key in invoices:
            invoices[group_key].write({'name': ', '.join(invoices_name[group_key]),
                                       'origin': ', '.join(invoices_origin[group_key])})
            # sale_orders = references[invoices[group_key]]
            # if len(sale_orders) == 1:
            #     invoices[group_key].reference = sale_orders.reference

        if not invoices:
            raise UserError(_('There is no invoiceable line. If a product has a Delivered quantities invoicing policy, please make sure that a quantity has been delivered.'))

        self._finalize_invoices(invoices, references)
        return [inv.id for inv in invoices.values()]


class PurchaseOrderLine(models.Model):
    _name = 'fob.po.order.line'
    _description = 'Purchase Order Line'
    _order = 'order_id, sequence, id'

    name = fields.Text(string='Description', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    product_qty = fields.Float(string='Quantity', digits=dp.get_precision('Product Unit of Measure'), required=True)
    product_uom_qty = fields.Float(string='Total Quantity', compute='_compute_product_uom_qty', store=True)
    date_planned = fields.Datetime(string='Scheduled Date', index=True)
    taxes_id = fields.Many2many('account.tax', string='Taxes', domain=['|', ('active', '=', False), ('active', '=', True)])
    product_uom = fields.Many2one('uom.uom', string='Product Unit of Measure', required=True)
    product_id = fields.Many2one('product.product', string='Product', domain=[('purchase_ok', '=', True)], change_default=True)
    product_image = fields.Binary(
        'Product Image', related="product_id.image", readonly=False,
        help="Non-stored related field to allow portal user to see the image of the product he has ordered")
    product_type = fields.Selection(related='product_id.type', readonly=True)
    price_unit = fields.Float(string='Unit Price', required=True, digits=dp.get_precision('Product Price'))

    price_subtotal = fields.Monetary(compute='_compute_amount', string='Subtotal', store=True)
    price_total = fields.Monetary(compute='_compute_amount', string='Total', store=True)
    price_tax = fields.Float(compute='_compute_amount', string='Tax', store=True)

    order_id = fields.Many2one('fob.po.order', string='Order Reference', index=True, required=True, ondelete='cascade')
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    analytic_tag_ids = fields.Many2many('account.analytic.tag', string='Analytic Tags')
    company_id = fields.Many2one('res.company', related='order_id.company_id', string='Company', store=True, readonly=True)
    state = fields.Selection(related='order_id.state', store=True, readonly=False)

    invoice_lines = fields.One2many('account.invoice.line', 'purchase_line_id', string="Bill Lines", readonly=True, copy=False)

    # Replace by invoiced Qty
    qty_invoiced = fields.Float(compute='_compute_qty_invoiced', string="Billed Qty", digits=dp.get_precision('Product Unit of Measure'), store=True)
    qty_received = fields.Float(string="Received Qty", digits=dp.get_precision('Product Unit of Measure'), copy=False)

    partner_id = fields.Many2one('res.partner', related='order_id.partner_id', string='Partner', readonly=True, store=True)
    currency_id = fields.Many2one(related='order_id.currency_id', store=True, string='Currency', readonly=True)
    date_order = fields.Datetime(related='order_id.date_order', string='Order Date', readonly=True)

    @api.depends('product_qty', 'price_unit', 'taxes_id')
    def _compute_amount(self):
        for line in self:
            vals = line._prepare_compute_all_values()
            taxes = line.taxes_id.compute_all(
                vals['price_unit'],
                vals['currency_id'],
                vals['product_qty'],
                vals['product'],
                vals['partner'])
            line.update({
                'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                'price_total': taxes['total_included'],
                'price_subtotal': taxes['total_excluded'],
            })

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
            'product_qty': self.pairs_total - self.shortage_qty, #self.product_qty,
            'product': self.product_id,
            'partner': self.order_id.partner_id,
        }

    @api.multi
    def _compute_tax_id(self):
        for line in self:
            fpos = line.order_id.fiscal_position_id or line.order_id.partner_id.property_account_position_id
            # If company_id is set, always filter taxes by the company
            taxes = line.product_id.supplier_taxes_id.filtered(lambda r: not line.company_id or r.company_id == line.company_id)
            line.taxes_id = fpos.map_tax(taxes, line.product_id, line.order_id.partner_id) if fpos else taxes

    @api.depends('invoice_lines.invoice_id.state', 'invoice_lines.quantity')
    def _compute_qty_invoiced(self):
        for line in self:
            qty = 0.0
            for inv_line in line.invoice_lines:
                if inv_line.invoice_id.state not in ['cancel']:
                    if inv_line.invoice_id.type == 'in_invoice':
                        qty += inv_line.uom_id._compute_quantity(inv_line.quantity, line.product_uom)
                    elif inv_line.invoice_id.type == 'in_refund':
                        qty -= inv_line.uom_id._compute_quantity(inv_line.quantity, line.product_uom)
            line.qty_invoiced = qty

    @api.model
    def create(self, values):
        line = super(PurchaseOrderLine, self).create(values)
        if line.order_id.state == 'purchase':
            msg = _("Extra line with %s ") % (line.product_id.display_name,)
            line.order_id.message_post(body=msg)
        return line

    @api.multi
    def write(self, values):
        if 'product_qty' in values:
            for line in self:
                if line.order_id.state == 'purchase':
                    line.order_id.message_post_with_view('purchase.track_po_line_template',
                                                         values={'line': line, 'product_qty': values['product_qty']},
                                                         subtype_id=self.env.ref('mail.mt_note').id)
        return super(PurchaseOrderLine, self).write(values)

    @api.multi
    def unlink(self):
        for line in self:
            if line.order_id.state in ['purchase', 'done']:
                raise UserError(_('Cannot delete a purchase order line which is in state \'%s\'.') % (line.state,))
        return super(PurchaseOrderLine, self).unlink()

    @api.model
    def _get_date_planned(self, seller, po=False):
        """Return the datetime value to use as Schedule Date (``date_planned``) for
           PO Lines that correspond to the given product.seller_ids,
           when ordered at `date_order_str`.

           :param Model seller: used to fetch the delivery delay (if no seller
                                is provided, the delay is 0)
           :param Model po: fob.po.order, necessary only if the PO line is
                            not yet attached to a PO.
           :rtype: datetime
           :return: desired Schedule Date for the PO line
        """
        date_order = po.date_order if po else self.order_id.date_order
        if date_order:
            return date_order + relativedelta(days=seller.delay if seller else 0)
        else:
            return datetime.today() + relativedelta(days=seller.delay if seller else 0)

    @api.depends('product_uom_qty', 'discount', 'price_unit', 'taxes_id')
    def _compute_amount(self):
        """
        Compute the amounts of the SO line.
        """
        for line in self:
            price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            taxes = line.taxes_id.compute_all(price, line.order_id.currency_id, (line.pairs_total - line.shortage_qty) , product=line.product_id, partner=line.order_id.partner_id)
            line.update({
                'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                'price_total': taxes['total_included'],
                'price_subtotal': taxes['total_excluded'],
            })

    # @api.depends('product_uom_qty', 'discount', 'price_unit', 'tax_id')
    # def _compute_amount(self):
    #     """
    #     Compute the amounts of the SO line.
    #     """
    #     for line in self:
    #         price = float_round(line.price_unit * (1 - (line.discount or 0.0) / 100.0),2,0,'HALF-UP')
    #         taxes = line.tax_id.compute_all(price, line.order_id.currency_id, line.pairs_total, product=line.product_id, partner=line.order_id.partner_shipping_id)
    #         line.update({
    #             'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
    #             'price_total': taxes['total_included'],
    #             'price_subtotal': taxes['total_excluded'],
    #         })
    #
    # @api.onchange('product_uom_qty', 'product_uom', 'route_id')
    # def _onchange_product_id_check_availability(self):
    #     if not self.product_id or not self.product_uom_qty or not self.product_uom:
    #         self.product_packaging = False
    #         return {}
    #
    #     order_partner_id = self.order_id.partner_id
    #
    #     external_code = None
    #     for e in self.product_id.external_codes:
    #         if e.partner_id == order_partner_id:
    #             external_code = e.name
    #
    #     vals = {}
    #     if external_code:
    #         self.external_code = external_code
    #
    #     self.image = self.product_id.image_medium
    #     self.range_start = self.product_id.range_start
    #     self.range_end = self.product_id.range_end
    #     self.assortment_id =self.product_id.assortment_id
    #
    #     ### Controllo disponibilità: disabilitato per casino sui magazzini
    #
    #     if self.product_id.is_kit:
    #         precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
    #         bom_id = self.env['mrp.bom'].search([('product_tmpl_id',  '=',  self.product_id.product_tmpl_id.id)])
    #         if bom_id:
    #             bom_ids = self.env['mrp.bom.line'].search([('bom_id',  '=',  bom_id[0].id)])
    #             if bom_ids:
    #                 for bom_line in bom_ids:
    #                     product = bom_line.product_id.with_context(
    #                         warehouse=self.order_id.warehouse_id.id,
    #                         lang=self.order_id.partner_id.lang or self.env.user.lang or 'en_US'
    #                     )
    #                     product_qty = self.product_uom._compute_quantity(self.product_uom_qty, self.product_id.uom_id)
    #                     if float_compare(product.virtual_available, bom_line.product_qty, precision_digits=precision) == -1:
    #                         is_available = "True" ####self._check_routing()
    #                         if not is_available:
    #                             message =  _('You plan to sell %s %s of %s but you only have %s %s available in %s warehouse.') % \
    #                                     (self.product_uom_qty, self.product_uom.name, product.default_code + ' ' + product.name, product.virtual_available, product.uom_id.name, self.order_id.warehouse_id.name)
    #                             warning_mess = {
    #                                 'title': _('Not enough inventory!'),
    #                                 'message' : message
    #                             }
    #                             return {'warning': warning_mess}
    #
    #     if self.product_id.type == 'product':
    #         precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
    #         product = self.product_id.with_context(
    #             warehouse=self.order_id.warehouse_id.id,
    #             lang=self.order_id.partner_id.lang or self.env.user.lang or 'en_US'
    #         )
    #         product_qty = self.product_uom._compute_quantity(self.product_uom_qty, self.product_id.uom_id)
    #         if float_compare(product.virtual_available, product_qty, precision_digits=precision) == -1:
    #             is_available = "True" ####self._check_routing()
    #             if not is_available:
    #                 message =  _('You plan to sell %s %s of %s but you only have %s %s available in %s warehouse.') % \
    #                         (self.product_uom_qty, self.product_uom.name, self.product_id.name, product.virtual_available, product.uom_id.name, self.order_id.warehouse_id.name)
    #                 # We check if some products are available in other warehouses.
    #                 if float_compare(product.virtual_available, self.product_id.virtual_available, precision_digits=precision) == -1:
    #                     message += _('\nThere are %s %s available across all warehouses.\n\n') % \
    #                             (self.product_id.virtual_available, product.uom_id.name)
    #                     for warehouse in self.env['stock.warehouse'].search([]):
    #                         quantity = self.product_id.with_context(warehouse=warehouse.id).virtual_available
    #                         if quantity > 0:
    #                             message += "%s: %s %s\n" % (warehouse.name, quantity, self.product_id.uom_id.name)
    #                 warning_mess = {
    #                     'title': _('Not enough inventory!'),
    #                     'message' : message
    #                 }
    #                 return {'warning': warning_mess}
    #
    #     return {}
    #
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
            'account_id': 103, #account.id,
            'price_unit': self.price_unit,
            'quantity': qty,
            'discount': self.discount,
            'uom_id': self.product_uom.id,
            #'product_id': self.product_id.id or False,
            'invoice_line_tax_ids': [(6, 0, self.taxes_id.ids)],
            #'account_analytic_id': self.order_id.analytic_account_id.id,
            #'analytic_tag_ids': [(6, 0, self.analytic_tag_ids.ids)],
            #'display_type': self.display_type,
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
            #if not float_is_zero(qty, precision_digits=precision) or not line.product_id:
            vals = line._prepare_invoice_line(qty=qty)
            #vals.update({'invoice_id': invoice_id, 'sale_line_ids': [(6, 0, [line.id])]})
            vals.update({'invoice_id': invoice_id})
            vals_list.append(vals)
        return vals_list


    # @api.onchange('product_id')
    # def onchange_product_id(self):
    #     result = {}
    #     if not self.product_id:
    #         return result
    #
    #     # Reset date, price and quantity since _onchange_quantity will provide default values
    #     self.date_planned = datetime.today().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
    #     self.price_unit = self.product_qty = 0.0
    #     self.product_uom = self.product_id.uom_po_id or self.product_id.uom_id
    #     result['domain'] = {'product_uom': [('category_id', '=', self.product_id.uom_id.category_id.id)]}
    #
    #     product_lang = self.product_id.with_context(
    #         lang=self.partner_id.lang,
    #         partner_id=self.partner_id.id,
    #     )
    #     self.name = product_lang.display_name
    #     if product_lang.description_purchase:
    #         self.name += '\n' + product_lang.description_purchase
    #
    #     self._compute_tax_id()
    #
    #     self._suggest_quantity()
    #     self._onchange_quantity()
    #
    #     return result
    #
    # @api.onchange('product_id')
    # def onchange_product_id_warning(self):
    #     if not self.product_id:
    #         return
    #     warning = {}
    #     title = False
    #     message = False
    #
    #     product_info = self.product_id
    #
    #     if product_info.purchase_line_warn != 'no-message':
    #         title = _("Warning for %s") % product_info.name
    #         message = product_info.purchase_line_warn_msg
    #         warning['title'] = title
    #         warning['message'] = message
    #         if product_info.purchase_line_warn == 'block':
    #             self.product_id = False
    #         return {'warning': warning}
    #     return {}

    @api.onchange('product_qty', 'product_uom')
    def _onchange_quantity(self):
        if not self.product_id:
            return
        params = {'order_id': self.order_id}
        seller = self.product_id._select_seller(
            partner_id=self.partner_id,
            quantity=self.product_qty,
            date=self.order_id.date_order and self.order_id.date_order.date(),
            uom_id=self.product_uom,
            params=params)

        if seller or not self.date_planned:
            self.date_planned = self._get_date_planned(seller).strftime(DEFAULT_SERVER_DATETIME_FORMAT)

        if not seller:
            if self.product_id.seller_ids.filtered(lambda s: s.name.id == self.partner_id.id):
                self.price_unit = 0.0
            return

        price_unit = self.env['account.tax']._fix_tax_included_price_company(seller.price, self.product_id.supplier_taxes_id, self.taxes_id, self.company_id) if seller else 0.0
        if price_unit and seller and self.order_id.currency_id and seller.currency_id != self.order_id.currency_id:
            price_unit = seller.currency_id._convert(
                price_unit, self.order_id.currency_id, self.order_id.company_id, self.date_order or fields.Date.today())

        if seller and self.product_uom and seller.product_uom != self.product_uom:
            price_unit = seller.product_uom._compute_price(price_unit, self.product_uom)

        self.price_unit = price_unit

    @api.multi
    @api.depends('product_uom', 'product_qty', 'product_id.uom_id')
    def _compute_product_uom_qty(self):
        for line in self:
            line.product_uom_qty = line.product_qty

    def _suggest_quantity(self):
        '''
        Suggest a minimal quantity based on the seller
        '''
        if not self.product_id:
            return
        seller_min_qty = self.product_id.seller_ids\
            .filtered(lambda r: r.name == self.order_id.partner_id and (not r.product_id or r.product_id == self.product_id))\
            .sorted(key=lambda r: r.min_qty)
        if seller_min_qty:
            self.product_qty = seller_min_qty[0].min_qty or 1.0
            self.product_uom = seller_min_qty[0].product_uom
        else:
            self.product_qty = 1.0
