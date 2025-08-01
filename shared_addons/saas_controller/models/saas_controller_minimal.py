# -*- coding: utf-8 -*-

import logging
import requests
from odoo import models, fields, api, exceptions, _

_logger = logging.getLogger(__name__)


class SaasController(models.Model):
    _name = 'saas.controller'
    _description = 'SaaS Controller Configuration - Minimal'
    _rec_name = 'database_name'

    # Basic Configuration
    database_name = fields.Char('Database Name', required=True, default=lambda self: self.env.cr.dbname)
    is_active = fields.Boolean('Active', default=True)
    saas_manager_url = fields.Char('SaaS Manager URL', default='http://saas_manager:8000')
    last_sync = fields.Datetime('Last Sync', readonly=True)
    
    # User Limits
    max_users = fields.Integer('Maximum Users', default=10, help="Maximum number of users allowed in this tenant")
    current_users = fields.Integer('Current Users', compute='_compute_current_users', store=False)
    user_limit_enabled = fields.Boolean('Enable User Limits', default=True)
    
    # Minimal Branding Controls
    remove_odoo_branding = fields.Boolean('Remove Odoo Branding', default=False, help="Hide Odoo branding (minimal approach)")
    replace_apps_icon = fields.Boolean('Replace Apps Icon', default=True, help="Replace apps icon with brain icon")
    custom_company_name = fields.Char('Custom Company Name', help="Override company name")
    
    # Basic Color Schema
    primary_color = fields.Char('Primary Color', default='#017e84', help="Main brand color (hex)")
    
    @api.depends()
    def _compute_current_users(self):
        """Compute current active user count"""
        for record in self:
            user_count = self.env['res.users'].search_count([
                ('active', '=', True),
                ('share', '=', False),  # Internal users only
                ('id', '!=', 1),  # Exclude admin user from count
            ])
            record.current_users = user_count

    @api.model
    def get_or_create_config(self):
        """Get or create SaaS configuration for current database"""
        config = self.search([('database_name', '=', self.env.cr.dbname)], limit=1)
        if not config:
            config = self.create({
                'database_name': self.env.cr.dbname,
            })
        return config

    def sync_with_saas_manager(self):
        """Sync configuration with SaaS Manager"""
        try:
            db_name = self.database_name
            if db_name.startswith('kdoo_'):
                tenant_subdomain = db_name[5:]
            else:
                tenant_subdomain = db_name
            
            url = f"{self.saas_manager_url}/api/tenant/{tenant_subdomain}/config"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    self.write({
                        'max_users': data.get('max_users', self.max_users),
                        'remove_odoo_branding': data.get('remove_branding', self.remove_odoo_branding),
                        'last_sync': fields.Datetime.now(),
                    })
                    _logger.info(f"Synced configuration for {db_name}")
                    return True
            else:
                _logger.warning(f"Failed to sync with SaaS Manager: {response.status_code}")
        except Exception as e:
            _logger.error(f"Error syncing with SaaS Manager: {e}")
        return False

    def check_user_limit(self):
        """Check if user limit has been reached"""
        if not self.user_limit_enabled:
            return True
        self._compute_current_users()
        return self.current_users < self.max_users

    def get_remaining_users(self):
        """Get number of remaining user slots"""
        if not self.user_limit_enabled:
            return 999
        self._compute_current_users()
        return max(0, self.max_users - self.current_users)

    @api.model
    def get_config_for_frontend(self):
        """Get configuration data for frontend use"""
        config = self.get_or_create_config()
        return {
            'remove_odoo_branding': config.remove_odoo_branding,
            'replace_apps_icon': config.replace_apps_icon,
            'primary_color': config.primary_color,
        }

    @api.model
    def cron_sync_configurations(self):
        """Cron job to sync configurations periodically"""
        configs = self.search([('is_active', '=', True)])
        for config in configs:
            config.sync_with_saas_manager()
