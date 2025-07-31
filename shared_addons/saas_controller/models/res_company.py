# -*- coding: utf-8 -*-

import logging
from odoo import models, api, fields

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    saas_controller_id = fields.Many2one('saas.controller', string='SaaS Controller')

    @api.model
    def apply_saas_branding(self):
        """Apply SaaS controller branding to company"""
        saas_config = self.env['saas.controller'].get_or_create_config()
        company = self.env.company
        
        if saas_config.custom_company_name and saas_config.custom_company_name != company.name:
            company.name = saas_config.custom_company_name
            
        if saas_config.custom_logo and saas_config.custom_logo != company.logo:
            company.logo = saas_config.custom_logo
            
        if saas_config.custom_favicon and saas_config.custom_favicon != company.favicon:
            company.favicon = saas_config.custom_favicon
            
        # Link the company to the SaaS controller
        company.saas_controller_id = saas_config.id
        
        _logger.info(f"Applied SaaS branding to company {company.name}")
