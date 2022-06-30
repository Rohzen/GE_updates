# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from datetime import datetime
from odoo import api, models, fields, _
from odoo.exceptions import UserError

from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT

# class ProductWizard(models.TransientModel):
    # _name = 'product.wizard'

    # range_start = fields.Integer('range_start')
    # range_end = fields.Integer('range_end')
    # range_dist = fields.Char('range_dist')

    # @api.multi
    # def create_set(self):
        # context = dict(self._context or {})
        # raise UserError(_("TEST REPORT"))

class AssortmentWizard(models.TransientModel): 
    _name ="wizard.assortment"

    image = fields.Binary(string="Image")
    product_id = fields.Many2one('product.product', string='Product', change_default = True, required = True, domain=[('is_base', '=', True)]) #domain=[('purchase_ok', '=', True)], , domain=[('is_kit', '=', False)]
    #['|', ('product_id', '=', product_id),('product_id', '=', False)]
    #name = fields.Char('Assortment')
    #code = fields.Char('Code', size=3,required=False)

    assortment_id = fields.Many2one(comodel_name='product.assortment', string='Assortment', required = True)
    
    range_start = fields.Integer('range_start', required = True)
    range_end = fields.Integer('range_end', required = True)

    pairs_size = fields.Char('Pairs (Sz.)', compute='_compute_pairs_size') #Aggiungere compute
    pairs_total = fields.Integer('Pairs', compute='_compute_pairs_total') #Aggiungere compute

    @api.depends('assortment_id','range_start','range_end') #,'range_start','range_end'
    def _compute_pairs_size(self):
        range_end = 0
        for rec in self:
            if rec.range_start == 0:
                rec.range_start = 25

            pair_sizes = ''
            i = -1
            if rec.assortment_id:
                composition_quantities_sizes = rec.assortment_id.name.split('-')
                composition_sizes = rec.range_end - rec.range_start
                if len(composition_quantities_sizes) != composition_sizes + 1 and composition_sizes>0:
                    rec.pairs_size = 'Missing sizes: %s pairs found on %s sizes'%(str(len(composition_quantities_sizes)),str(composition_sizes + 1))
                    return

                for size_qty in composition_quantities_sizes:
                    i = i +1
                    tot_qty = int(size_qty) #*int(rec.product_qty)
                    pair_sizes += str(tot_qty) + '(' + str(rec.range_start + i) + ')' + '-'
                    range_end = rec.range_start + i

                rec.range_end = range_end
                rec.pairs_size = pair_sizes[:-1]

    @api.depends('assortment_id')
    def _compute_pairs_total(self):
        for rec in self:
            rec.pairs_total =1
            pair_sizes = ''
            i = 0
            if rec.assortment_id:
                composition_quantities_sizes = rec.assortment_id.name.split('-')
                composition_sizes = rec.range_end - rec.range_start
                # if len(composition_quantities_sizes) != composition_sizes + 1:
                    # return

                #try:
                for size_qty in composition_quantities_sizes:
                    i = i + int(size_qty) #*rec.product_qty
                #except:
                #        i = 0

                rec.pairs_total = i

    @api.multi
    #@api.onchange('assortment_id')
    def create_pset(self):
        if not self.product_id:
            raise UserError(_("E' necessario selezionare un item"))
        if self.product_id.is_kit:
            raise UserError(_("Per usare questa funzione e' necessario selezionare un item singolo"))
        #out_file = open("c:\\temp\dev.txt","w")
        base_variant = self.product_id #00 variant
        product_id = self.product_id
        product_name = self.product_id.name #self.product_id.display_name
        template_name = self.product_id.product_tmpl_id.display_name
        product_image = self.product_id.image
        product_tmpl_id = self.product_id.product_tmpl_id
        default_template_code = self.product_id.default_code
        product_brand_id = self.product_id.product_brand_id.id
        
        if not default_template_code:
            raise UserError(_("Error: [cod. art] is empty. Please set one in the item page."))

        if not (len(default_template_code)>3):
            raise UserError(_("Length must be at least 4 digits"))

        comp_start = self.range_start
        comp_end = self.range_end
        composition_detail = self.assortment_id.name

        composition_lenght = comp_end - comp_start
        composition_quantities_sizes = composition_detail.split('-')
        composition_quantities_lenght = len(composition_quantities_sizes)

        if  (composition_quantities_lenght != composition_lenght+1):
             raise UserError(_("Cannot create a new set, invalid range of sizes:%s on: %s")%(str(composition_quantities_lenght),str(composition_lenght)))

        # Nome:   183150 BLACK
        # Codice: 183150 01 00

        # Cod.Assortimento:  18315001[B14]
        # Nome Assortimento: 183150 BLACK (30-35)

        #next_seq = self.env['ir.sequence'].next_by_code('composition') #composition
        next_seq = default_template_code + '-' + self.assortment_id.code
        assortment_barcode = next_seq.replace('-','.').replace('-','.') + '.' + product_name + str(comp_start) + str(comp_end)
        composition_name =  product_name + '(' + str(comp_start) + '-' + str(comp_end) + ')'
        
        
        #ADD 'product_brand_id': product_brand_id,
        id_set_tmpl = self.env['product.template'].create({'name': composition_name,'product_brand_id': product_brand_id,'default_code': next_seq, 'barcode': assortment_barcode,'type':'consu', 'categ_id':product_tmpl_id.categ_id.id, 'uom_id':product_tmpl_id.uom_po_id.id, 'uom_po_id':product_tmpl_id.uom_po_id.id, 'responsible_id':1, 'tracking':'none', 'sale_line_warn':'no-message', 'purchase_line_warn':'no-message', 'sale_ok':True, 'purchase_ok':True, 'is_kit':True,'purchase_method':'purchase', 'active':True,'image':product_image,'range_start': self.range_start,'range_end': self.range_end,'assortment_id': self.assortment_id.id})
        id_set = None
        product_product_ids = self.env['product.product'].search([('product_tmpl_id',  '=',  id_set_tmpl.id)])
        for newproduct in product_product_ids:
            id_set = self.env['product.product'].browse(newproduct.id)
            id_set.range_start = self.range_start
            id_set.range_end = self.range_end
            id_set.assortment_id = self.assortment_id
        id_bom = self.env['mrp.bom'].create({'type': 'phantom', 'product_tmpl_id':id_set_tmpl.id, 'product_qty':1, 'product_uom_id':product_tmpl_id.uom_id.id, 'ready_to_produce':'asap', 'company_id':1})

        attribute_id = 0
        product_attribute_ids = self.env['product.attribute'].search([('name',  '=', 'Size')])
        if not product_attribute_ids:
            raise UserError(_("You have to create attribute named: Size"))
        for attribute in product_attribute_ids:
            attribute_id = attribute.id

        i=-1
        for size in range(comp_start,comp_end+1):
            product_template_attribute_line_id = None
            i = i +1 #generic counter
            quantity = composition_quantities_sizes[i]

            attribute_ids = self.env['product.attribute.value'].search([('name',  '=', str(size))])
            if not len(attribute_ids) >0: #Check if attribute exist (must exist)
                product_attribute_value_id = self.env['product.attribute.value'].create({'name': str(size),'attribute.id':attribute_id})[0]
                attribute_ids = self.env['product.attribute.value'].search([('name',  '=', str(size))])

            for o in attribute_ids:
                product_attribute_value_id = o.id #Abbiamo trovato l'id prodotto variante
                attribute_list = self.env.cr.execute('select product_product_id from product_attribute_value_product_product_rel where product_attribute_value_id = %s' % (o.id))
                try:
                    id = self.env.cr.fetchone()[0]
                    product_id = self.env['product.product'].browse(id)
                    if product_id.product_tmpl_id == product_tmpl_id:
                        #out_file.write('FIND HERE: product_id:%s product_attribute_value_id:%s\n'%(str(product_id),str(product_attribute_value_id)))
                        break
                    else:
                        product_id = None
                except:
                    product_id = None

            if not product_id:
                product_template_attribute_line_ids = self.env['product.template.attribute.line'].search([('product_tmpl_id','=',product_tmpl_id.id),('attribute_id','=',attribute_id)])
                for p in product_template_attribute_line_ids:
                    product_template_attribute_line_id = p.id

                notexist = self.env.cr.execute('select product_template_attribute_line_id from public.product_attribute_value_product_template_attribute_line_rel where product_template_attribute_line_id = %s and product_attribute_value_id = %s' % (product_template_attribute_line_id,product_attribute_value_id))
                try:
                    exist = self.env.cr.fetchone()[0]
                except:
                    exist = None

                if not exist:
                    product_attribute_value_product_template_attribute_line_rel = self.env.cr.execute('INSERT INTO public.product_attribute_value_product_template_attribute_line_rel(product_template_attribute_line_id, product_attribute_value_id) VALUES (%s, %s)' % (product_template_attribute_line_id,product_attribute_value_id))
                ### Double check for barcode
                product_barcode_ids = self.env['product.product'].search([('barcode','=',default_template_code+'.'+str(size))])
                ###out_file.write('BARCODE:%s RESULTS:%s\n'%(default_template_code+str(size),str(product_barcode_ids)))
                if not product_barcode_ids:
                   ### Qui creiamo il prodotto con un codice barcode diverso per ogni taglia
                   product_id = self.env['product.product'].create({'product_tmpl_id':product_tmpl_id.id, 'default_code':default_template_code,'barcode': default_template_code+'.'+str(size),'weight':base_variant.weight,'volume':base_variant.volume,})
                   product_attribute_value_product_product_rel = self.env.cr.execute('INSERT INTO public.product_attribute_value_product_product_rel(product_product_id, product_attribute_value_id) VALUES (%s, %s)' % (product_id.id,product_attribute_value_id))
                else:
                   product_id = self.env['product.product'].browse(product_barcode_ids[0].id)

            #Alla fine qui inseriamo il dettaglio della bom/kit
            #try:
            id_bom_line = self.env['mrp.bom.line'].create({'product_id': product_id.id, 'product_qty':quantity, 'product_uom_id':product_tmpl_id.uom_id.id, 'bom_id':id_bom.id})
            #except:
            #    print ('Non creato.')

        #line = self.env['purchase.order.line'].browse(self.id)
        #line.write({'product_id':id_set.id,'name':id_set.display_name,'product_uom':product_tmpl_id.uom_po_id.id})

    @api.onchange('product_id')
    def onchange_product_id(self):
        result = {}
        if not self.product_id:
            return result

        #order_partner_id = self.order_id.partner_id

        # external_code = None
        # for e in self.product_id.external_codes:
            # if e.partner_id == order_partner_id:
                # external_code = e.name

        vals = {}
        # if external_code:
            # self.external_code = external_code

        self.image = self.product_id.image_medium
        #self.range_start = self.product_id.range_start
        #self.range_end = self.product_id.range_end
        #self.assortment_id =self.product_id.assortment_id
        # Reset date, price and quantity since _onchange_quantity will provide default values
        #self.date_planned = datetime.today().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        #self.price_unit = self.product_qty = 0.0
        #if self.product_id.is_kit:
        #    self.product_uom = self.product_id.uom_po_id or self.product_id.uom_id
        #else:
        #    self.product_uom = self.product_id.uom_id
        #result['domain'] = {'product_uom': [('category_id', '=', self.product_id.uom_id.category_id.id)]}

        # product_lang = self.product_id.with_context(
            # lang=self.partner_id.lang,
            # partner_id=self.partner_id.id,
        # )
        # self.name = product_lang.display_name
        # if product_lang.description_purchase:
            # self.name += '\n' + product_lang.description_purchase

        # self._compute_tax_id()

        # self._suggest_quantity()
        # self._onchange_quantity()

        return result

class Assortment(models.Model): 
    _name ="product.assortment"

    name = fields.Char('Assortment')
    code = fields.Char('Code', size=3,required=False)

    @api.multi
    def name_get(self):
        # Prefetch the fields used by the `name_get`, so `browse` doesn't fetch other fields
        self.browse(self.ids).read(['name', 'code'])
        return [(assortment.id, '%s%s' % (assortment.code and '[%s] ' % assortment.code or '', assortment.name))
                for assortment in self]

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
        if not args:
            args = []
        assortment_ids = self._search(args + [('code', operator, name)], limit=limit)
        if not assortment_ids:
            assortment_ids = self._search(args + [('name', operator, name)], limit=limit)
        # if name:
            # positive_operators = ['=', 'ilike', '=ilike', 'like', '=like']
            # assortment_ids = []
            # if operator in positive_operators:
                # assortment_ids = self._search([('code', '=', name)] + args, limit=limit, access_rights_uid=name_get_uid)
                # if not assortment_ids:
                    # assortment_ids = self._search([('name', '=', name)] + args, limit=limit, access_rights_uid=name_get_uid)
        # else:
            # assortment_ids = self._search(args, limit=limit, access_rights_uid=name_get_uid)
        return self.browse(assortment_ids).name_get()
