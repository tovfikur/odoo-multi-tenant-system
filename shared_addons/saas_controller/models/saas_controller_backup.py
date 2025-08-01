# -*- coding: utf-8 -*-

import logging
import requests
from odoo import models, fields, api, exceptions, _

_logger = logging.getLogger(__name__)


class SaasController(models.Model):
    _name = 'saas.controller'
    _description = 'SaaS Controller Configuration'
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
    
    # Branding Controls
    remove_odoo_branding = fields.Boolean('Remove Odoo Branding', default=False, help="Hide Odoo branding throughout the system")
    custom_company_name = fields.Char('Custom Company Name', help="Override company name")
    custom_app_name = fields.Char('Custom App Name', default='Business Manager', help="Custom application name")
    hide_poweredby = fields.Boolean('Hide Powered By', default=False, help="Hide 'Powered by Odoo' footer")
    custom_favicon = fields.Binary('Custom Favicon')
    custom_logo = fields.Binary('Custom Logo')
    
    # Color Schema
    primary_color = fields.Char('Primary Color', default='#017e84', help="Main brand color (hex)")
    secondary_color = fields.Char('Secondary Color', default='#875a7b', help="Secondary brand color (hex)")
    accent_color = fields.Char('Accent Color', default='#017e84', help="Accent color for highlights (hex)")
    background_color = fields.Char('Background Color', default='#ffffff', help="Main background color (hex)")
    text_color = fields.Char('Text Color', default='#212529', help="Primary text color (hex)")
    link_color = fields.Char('Link Color', default='#017e84', help="Link color (hex)")
    
    # Feature Controls
    disable_apps_menu = fields.Boolean('Disable Apps Menu', default=False, help="Hide the apps menu")
    disable_settings_menu = fields.Boolean('Disable Settings Menu', default=False, help="Restrict access to settings")
    disable_debug_mode = fields.Boolean('Disable Debug Mode', default=False, help="Prevent debug mode activation")
    custom_login_message = fields.Text('Custom Login Message', help="Custom message on login page")
    
    # Resource Controls
    max_storage_mb = fields.Integer('Max Storage (MB)', default=1024, help="Maximum storage in MB")
    max_email_per_day = fields.Integer('Max Emails/Day', default=100, help="Maximum emails per day")
    allowed_modules = fields.Text('Allowed Modules', help="Comma-separated list of allowed modules")
    
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
            config.sync_with_saas_manager()
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
                        'primary_color': data.get('primary_color', self.primary_color),
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

    def apply_branding_config(self):
        """Apply branding configuration to the system"""
        try:
            # Update company information
            company = self.env.company
            if self.custom_company_name:
                company.name = self.custom_company_name
            if self.custom_logo:
                company.logo = self.custom_logo
            if self.custom_favicon:
                company.favicon = self.custom_favicon
                
            # Apply color schema
            self._apply_color_schema()
            
            # Apply branding removal
            if self.remove_odoo_branding:
                self._remove_odoo_branding()
                
            _logger.info(f"Applied branding configuration for {self.database_name}")
            return True
        except Exception as e:
            _logger.error(f"Error applying branding configuration: {e}")
            return False

    def _apply_color_schema(self):
        """Apply custom color schema"""
        try:
            # Create or update custom CSS
            css_content = self._generate_custom_css()
            
            # Find or create custom view
            view = self.env['ir.ui.view'].search([
                ('name', '=', 'SaaS Controller Custom Styles'),
                ('type', '=', 'qweb')
            ], limit=1)
            
            if not view:
                view = self.env['ir.ui.view'].create({
                    'name': 'SaaS Controller Custom Styles',
                    'type': 'qweb',
                    'key': 'saas_controller.custom_styles',
                    'arch_db': f'<t><style>{css_content}</style></t>',
                })
            else:
                view.arch_db = f'<t><style>{css_content}</style></t>'
                
        except Exception as e:
            _logger.error(f"Error applying color schema: {e}")

    def _generate_custom_css(self):
        """Generate custom CSS based on configuration"""
        return f"""
        :root {{
            --primary-color: {self.primary_color or '#017e84'};
            --secondary-color: {self.secondary_color or '#875a7b'};
            --accent-color: {self.accent_color or '#017e84'};
            --background-color: {self.background_color or '#ffffff'};
            --text-color: {self.text_color or '#212529'};
            --link-color: {self.link_color or '#017e84'};
        }}
        
        .o_main_navbar {{
            background-color: var(--primary-color) !important;
        }}
        
        .btn-primary {{
            background-color: var(--primary-color) !important;
            border-color: var(--primary-color) !important;
        }}
        
        .btn-secondary {{
            background-color: var(--secondary-color) !important;
            border-color: var(--secondary-color) !important;
        }}
        
        a {{
            color: var(--link-color) !important;
        }}
        
        .o_form_view .o_form_sheet {{
            background-color: var(--background-color) !important;
        }}
        
        body {{
            color: var(--text-color) !important;
        }}
        """

    def _remove_odoo_branding(self):
        """Remove Odoo branding from the system"""
        try:
            # Hide Odoo branding in various places and replace icons
            branding_css = """
            .o_sub_menu_footer, 
            .powered_by,
            [data-section="about"] .oe_instance_title,
            .oe_instance_title {
                display: none !important;
            }
            
            """
            
            # Update the custom CSS view
            view = self.env['ir.ui.view'].search([
                ('name', '=', 'SaaS Controller Custom Styles'),
            ], limit=1)
            
            if view:
                current_css = view.arch_db
                if '<style>' in current_css:
                    css_content = current_css.replace('</style>', f'{branding_css}</style>')
                    view.arch_db = css_content
                    
        except Exception as e:
            _logger.error(f"Error removing Odoo branding: {e}")

    @api.model
    def cron_sync_configurations(self):
        """Cron job to sync configurations periodically"""
        configs = self.search([('is_active', '=', True)])
        for config in configs:
            config.sync_with_saas_manager()
