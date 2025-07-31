# -*- coding: utf-8 -*-

import logging
from odoo import models, api

_logger = logging.getLogger(__name__)


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    @api.model
    def apply_saas_customizations(self):
        """Apply SaaS controller customizations to views"""
        saas_config = self.env['saas.controller'].get_or_create_config()
        
        try:
            # Apply branding configuration
            saas_config.apply_branding_config()
            
            # Hide elements based on configuration
            if saas_config.disable_apps_menu:
                self._hide_apps_menu()
                
            if saas_config.disable_settings_menu:
                self._hide_settings_menu()
                
            _logger.info("Applied SaaS customizations to views")
            
        except Exception as e:
            _logger.error(f"Error applying SaaS customizations: {e}")

    def _hide_apps_menu(self):
        """Hide the apps menu"""
        try:
            # Create or update view to hide apps menu
            view_arch = """
            <xpath expr="//a[@data-menu='apps']" position="attributes">
                <attribute name="style">display: none !important;</attribute>
            </xpath>
            """
            self._create_or_update_inheritance_view(
                'saas_controller.hide_apps_menu',
                'web.menu',
                view_arch
            )
        except Exception as e:
            _logger.error(f"Error hiding apps menu: {e}")

    def _hide_settings_menu(self):
        """Hide settings menu for non-admin users"""
        try:
            # This would typically require more complex logic
            # For now, we'll add CSS to hide it
            pass
        except Exception as e:
            _logger.error(f"Error hiding settings menu: {e}")

    def _create_or_update_inheritance_view(self, key, inherit_id, arch):
        """Create or update an inheritance view"""
        try:
            view = self.search([('key', '=', key)], limit=1)
            if view:
                view.arch_db = arch
            else:
                inherit_view = self.search([('key', '=', inherit_id)], limit=1)
                if inherit_view:
                    self.create({
                        'name': f'SaaS Controller - {key}',
                        'key': key,
                        'type': 'qweb',
                        'inherit_id': inherit_view.id,
                        'arch_db': arch,
                    })
        except Exception as e:
            _logger.error(f"Error creating/updating inheritance view {key}: {e}")
