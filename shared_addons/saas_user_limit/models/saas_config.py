# -*- coding: utf-8 -*-

import logging
import requests
from odoo import models, fields, api, exceptions, _

_logger = logging.getLogger(__name__)


class SaasConfig(models.Model):
    _name = 'saas.config'
    _description = 'SaaS Configuration'
    _rec_name = 'database_name'

    database_name = fields.Char('Database Name', required=True, default=lambda self: self.env.cr.dbname)
    max_users = fields.Integer('Maximum Users', default=10, help="Maximum number of users allowed in this tenant")
    current_users = fields.Integer('Current Users', compute='_compute_current_users', store=False)
    saas_manager_url = fields.Char('SaaS Manager URL', default='http://saas_manager:8000')
    last_sync = fields.Datetime('Last Sync', readonly=True)
    is_active = fields.Boolean('Active', default=True)
    
    @api.depends()
    def _compute_current_users(self):
        """Compute current active user count"""
        for record in self:
            # Count active internal users (excluding portal, public users)
            user_count = self.env['res.users'].search_count([
                ('active', '=', True),
                ('share', '=', False),  # Internal users only
                ('id', '!=', 1),  # Exclude admin user from count
            ])
            record.current_users = user_count

    def sync_with_saas_manager(self):
        """Sync user limits with SaaS Manager"""
        try:
            # Get database name (remove kdoo_ prefix if present)
            db_name = self.database_name
            if db_name.startswith('kdoo_'):
                tenant_subdomain = db_name[5:]  # Remove 'kdoo_' prefix
            else:
                tenant_subdomain = db_name
            
            url = f"{self.saas_manager_url}/api/tenant/{tenant_subdomain}/user-limit"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    self.max_users = data.get('max_users', self.max_users)
                    self.last_sync = fields.Datetime.now()
                    _logger.info(f"Synced user limit for {db_name}: {self.max_users}")
                    return True
            else:
                _logger.warning(f"Failed to sync with SaaS Manager: {response.status_code}")
        except Exception as e:
            _logger.error(f"Error syncing with SaaS Manager: {e}")
        return False

    @api.model
    def get_or_create_config(self):
        """Get or create SaaS configuration for current database"""
        config = self.search([('database_name', '=', self.env.cr.dbname)], limit=1)
        if not config:
            config = self.create({
                'database_name': self.env.cr.dbname,
                'max_users': 10,  # Default limit
            })
            # Try to sync with SaaS Manager on first creation
            config.sync_with_saas_manager()
        return config

    def check_user_limit(self):
        """Check if user limit has been reached"""
        self._compute_current_users()
        if self.current_users >= self.max_users:
            return False
        return True

    def get_remaining_users(self):
        """Get number of remaining user slots"""
        self._compute_current_users()
        return max(0, self.max_users - self.current_users)

    @api.model
    def cron_sync_user_limits(self):
        """Cron job to sync user limits periodically"""
        configs = self.search([('is_active', '=', True)])
        for config in configs:
            config.sync_with_saas_manager()
