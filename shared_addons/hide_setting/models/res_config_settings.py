from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    hide_settings_ui = fields.Boolean(
        string='Hide Settings from UI',
        help='When enabled, Settings menu will be hidden from UI but accessible via API'
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        hide_config = self.env['hide.setting.config'].sudo().search([], limit=1)
        res['hide_settings_ui'] = hide_config.is_active if hide_config else False
        return res

    def set_values(self):
        super().set_values()
        hide_config = self.env['hide.setting.config'].sudo().search([], limit=1)
        if not hide_config:
            hide_config = self.env['hide.setting.config'].sudo().create({})
        
        hide_config.write({
            'is_active': self.hide_settings_ui,
            'activated_by': self.env.user.id,
            'activation_date': fields.Datetime.now(),
        })