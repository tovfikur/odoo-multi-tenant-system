from odoo import api, fields, models
from odoo.exceptions import AccessError


class HideSettingConfig(models.Model):
    _name = 'hide.setting.config'
    _description = 'Hide Setting Configuration'
    _rec_name = 'is_active'

    is_active = fields.Boolean(
        string='Hide Settings from UI',
        default=False,
        help='When enabled, Settings menu will be hidden from UI but accessible via API'
    )
    
    activated_by = fields.Many2one(
        'res.users',
        string='Activated By',
        readonly=True,
        help='User who last changed this setting'
    )
    
    activation_date = fields.Datetime(
        string='Last Changed',
        readonly=True,
        help='Date when this setting was last changed'
    )
    
    @api.model
    def get_hide_setting_status(self):
        """Get current hide setting status - API accessible method"""
        config = self.sudo().search([], limit=1)
        return {
            'is_active': config.is_active if config else False,
            'activated_by': config.activated_by.name if config and config.activated_by else '',
            'activation_date': config.activation_date.isoformat() if config and config.activation_date else '',
        }
    
    @api.model
    def toggle_hide_setting(self, is_active):
        """Toggle hide setting status - API accessible method"""
        if not self.env.user.has_group('base.group_system'):
            raise AccessError('Only system administrators can modify this setting')
        
        config = self.sudo().search([], limit=1)
        if not config:
            config = self.sudo().create({})
        
        config.write({
            'is_active': is_active,
            'activated_by': self.env.user.id,
            'activation_date': fields.Datetime.now(),
        })
        
        return {
            'success': True,
            'message': f'Hide setting {"enabled" if is_active else "disabled"} successfully',
            'is_active': is_active
        }
    
    @api.model
    def is_settings_hidden(self):
        """Check if settings should be hidden - used by frontend"""
        config = self.sudo().search([], limit=1)
        return config.is_active if config else False

    @api.model_create_multi
    def create(self, vals_list):
        # Ensure only one record exists
        existing = self.sudo().search([])
        if existing:
            existing.unlink()
        return super().create(vals_list)
    
    def write(self, vals):
        # Update activation info
        if 'is_active' in vals:
            vals.update({
                'activated_by': self.env.user.id,
                'activation_date': fields.Datetime.now(),
            })
        return super().write(vals)