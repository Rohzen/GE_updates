# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'FOB Management',
    'version': '12.0.0.1.1',
    'category': 'Sale',
    'summary': 'FOB Management',
    'author': 'Roberto Zanardo per ProSaber',
    'website': 'https://www.prosaber.com/',
    'description': """

Manage FOB orders
===========================

This module adds FOB management for orders

""",
    'depends': ['sale', 'sale_purchase', 'sale_stock', 'purchase', 'product_brand', 'stock_mgmt','l10n_it_fatturapa', ],
    'data': [
        'views/fob_sale.xml',
        'views/fob_purchase.xml',
        'views/fob_common.xml',
        'views/config.xml',
        'views/account.xml',
        'report/sale_report.xml',
        'report/sale_report_templates.xml',
        'report/purchase_quotation_templates.xml',
        'report/purchase_reports.xml',
        'security/ir.model.access.csv',
        ],
    'installable': True,
    'auto_install': False,
    "application": True,
}
