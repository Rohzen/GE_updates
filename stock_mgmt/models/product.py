# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models, fields, _
from odoo.addons import decimal_precision as dp
from odoo.exceptions import UserError
import os

class Material(models.Model): 
    _name ="product.material"

    name = fields.Char('Material')

class ManifacturingType(models.Model): 
    _name ="product.manifacturing"

    name = fields.Char('Manifacturing code')

# class SeasonCollection(models.Model): 
    # _name ="product.collection"
    
    # name = fields.Char('Collection name', help='[SS/AA] SS=Collection AA=Year')

class ProductSizes(models.Model): 
    _name ="product.sizes"
    
    name = fields.Char('Size')
    size = fields.Integer('Size no.')

class ExternalCodes(models.Model): 
    _name ="product.externalcodes"

    ext_code_id = fields.Integer('External ID')
    partner_id = fields.Many2one('res.partner', string='Vendor', help="You can find a vendor by its Name, TIN, Email or Internal Reference.")
    name = fields.Char('External code')

# class ProductComposition(models.Model):
    # _name ="product.composition"
    
    # comp_id = fields.Integer('External ID')
    # #name = fields.Text('External code')
    # size_id = fields.Many2one(comodel_name='product.sizes', string='Size', )
    # qty = fields.Integer('Qty')

class ProductTemplate(models.Model):
    _inherit = "product.template"
    #is_base = fields.Boolean(string='Base product', )
    #default_code = fields.Char('Internal Reference', index=True)
    is_kit = fields.Boolean(string='Is a kit?', )
    # composition = fields.One2many('product.composition', 'comp_id', string='Composition', )

    material_id = fields.Many2one(comodel_name='product.material', string='Material', )
    manifacturing_id = fields.Many2one(comodel_name='product.manifacturing', string='Manifacturing Type', )
    # collection_id = fields.Many2one(comodel_name='product.collection', string='Collection name', )
    external_codes = fields.One2many('product.externalcodes', 'ext_code_id', string='External codes', )
    size_id = fields.Many2one(comodel_name='product.sizes', string='Size', )

    weight_gross = fields.Float('Gross weight', digits=dp.get_precision('Stock Weight'),
        help="Weight of the product, packaging not included. The unit of measure can be changed in the general settings")
    pack_volume = fields.Float('Pack Volume', help="The volume in m3.", digits=dp.get_precision('Stock Volume'))

    bom_id = fields.Integer('Bom',  compute='_compute_bom')
    bom_line_ids = fields.Many2many('mrp.bom.line',  compute='_compute_bom_lines',  string='Bom Lines')

    range_start = fields.Integer('range_start')
    range_end = fields.Integer('range_end')
    assortment_id = fields.Many2one(comodel_name='product.assortment', string='Assortment', )

    @api.one
    def _compute_bom(self): 
        res_ids = self.env['mrp.bom'].search([('product_tmpl_id',  '=', self.id)])
        for o in res_ids: 
            bom_id = o.id
            self.bom_id = bom_id

    @api.one
    @api.depends('bom_id')
    def _compute_bom_lines(self):
        #out_file = open("c:\\temp\dev.txt","w")
        #self.ensure_one()
        bom_lines = set()
        res_ids = self.env['mrp.bom.line'].search([['bom_id',  '=',  self.bom_id]])
        for o in res_ids: 
            bom_lines.add(o.id)
            #out_file.write(str(o))
            #order_id = self.env['sale.order'].browse(o.id)
        #out_file.close()
        self.bom_line_ids = list(bom_lines)

class ProductProduct(models.Model):
    _inherit = "product.product"

    is_base = fields.Boolean(string='Base product', )

    bom_id = fields.Integer('Bom',  compute='_compute_bom')
    bom_line_ids = fields.Many2many('mrp.bom.line',  compute='_compute_bom_lines',  string='Bom Lines')

    range_start = fields.Integer('range_start')
    range_end = fields.Integer('range_end')
    assortment_id = fields.Many2one(comodel_name='product.assortment', string='Assortment', )
    volume = fields.Float('Volume', help="The volume in m3.", digits=dp.get_precision('Stock Volume'))

    @api.one
    def _compute_bom(self): 
        res_ids = self.env['mrp.bom'].search([('product_tmpl_id',  '=', self.product_tmpl_id.id)])
        for o in res_ids: 
            bom_id = o.id
            self.bom_id = bom_id

    @api.one
    @api.depends('bom_id')
    def _compute_bom_lines(self):
        #out_file = open("c:\\temp\dev.txt","w")
        #self.ensure_one()
        bom_lines = set()
        res_ids = self.env['mrp.bom.line'].search([['bom_id',  '=',  self.bom_id]])
        for o in res_ids: 
            bom_lines.add(o.id)
            #out_file.write(str(o))
            #order_id = self.env['sale.order'].browse(o.id)
        #out_file.close()
        self.bom_line_ids = list(bom_lines)

# class ProductWizard(models.TransientModel):
    # _name = 'product.wizard'

    # range_start = fields.Integer('range_start')
    # range_end = fields.Integer('range_end')
    # range_dist = fields.Char('range_dist')

    # @api.multi
    # def create_set(self):
        # context = dict(self._context or {})
        # raise UserError(_("TEST REPORT"))

