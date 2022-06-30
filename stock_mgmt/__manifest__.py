# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Stock Advance Management for Prosaber',
    'version': '1.0',
    'category': 'Warehouse',
    'summary': 'Stock Advance Management',
    'author': 'Roberto Zanardo per ProSaber',
    'website': 'https://www.prosaber.com/',
    'description': """
Manage advance Stock
===========================

This module adds inventory function for better packages management

""",
    'depends': ['sale_purchase', 'sale_stock','l10n_it_ddt','purchase','mrp','product_brand'],
    'data': [
        'data/stock_data.xml',
        'views/account.xml',
        'views/sale_order_views.xml',
        'views/purchase_order_views.xml',
        'views/product_views.xml',
        'views/stock_views.xml',
        'views/stock_cron.xml',
        'views/image_in_orderline.xml',
        'views/tree_image.xml',
        'views/ddt_view.xml',
        'views/company.xml',
        'views/assortments.xml',
        'report/report_purchaseorder.xml',
        'report/report_purchaseorder2.xml',
        'report/report_saleorder.xml',
        'report/report_saleorder2.xml',
        'report/report_saleorder_NOSCARPE.xml',
        'report/report_ddt.xml',
        'report/report_ddt2.xml',
        'report/report_ddt_noscarpe.xml',
        'report/report_invoice.xml',
        'report/report_invoice_noscarpe.xml',
        'security/ir.model.access.csv',], #'data/stock_data.xml', 
    'qweb': ['static/src/xml/widget.xml', ],
    'installable': True,
    'auto_install': False,
    "application": True,
}
