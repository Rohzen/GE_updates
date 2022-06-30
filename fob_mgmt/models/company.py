# Copyright 2014 Davide Corio <davide.corio@abstract.it>

from odoo import fields, models, api

class AccountConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fob_journal_id = fields.Many2one('account.journal', string='Registro per fatture FOB', config_parameter='fob_mgmt.fob_journal_id')
    fob_tax_id = fields.Many2one('account.tax', string='Imposta predefinita', config_parameter='fob_mgmt.fob_tax_id')






