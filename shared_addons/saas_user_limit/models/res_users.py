# -*- coding: utf-8 -*-

import logging
from odoo import models, api, exceptions, _

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model_create_multi
    def create(self, vals_list):
        """Override user creation to enforce user limits"""
        # Get SaaS configuration
        saas_config = self.env['saas.config'].get_or_create_config()
        
        # Count how many internal users will be created
        internal_users_to_create = 0
        for vals in vals_list:
            # Check if this will be an internal user
            if not vals.get('share', False):  # Internal user
                internal_users_to_create += 1
        
        if internal_users_to_create > 0:
            # Check current user limit
            saas_config._compute_current_users()
            remaining_slots = saas_config.get_remaining_users()
            
            if internal_users_to_create > remaining_slots:
                # Try to sync with SaaS Manager to get latest limits
                saas_config.sync_with_saas_manager()
                remaining_slots = saas_config.get_remaining_users()
                
                if internal_users_to_create > remaining_slots:
                    if remaining_slots == 0:
                        raise exceptions.ValidationError(
                            _("User limit reached! This tenant is limited to %d users. "
                              "Please upgrade your plan to add more users.") % saas_config.max_users
                        )
                    else:
                        raise exceptions.ValidationError(
                            _("User limit exceeded! You can only create %d more user(s). "
                              "This tenant is limited to %d users total. "
                              "Please upgrade your plan to add more users.") % (remaining_slots, saas_config.max_users)
                        )
        
        # Proceed with user creation if limit check passes
        return super(ResUsers, self).create(vals_list)

    def write(self, vals):
        """Override user write to check if making users internal exceeds limit"""
        if 'share' in vals and not vals['share']:
            # User is being converted from portal/public to internal
            saas_config = self.env['saas.config'].get_or_create_config()
            
            # Count how many users will become internal
            users_becoming_internal = len(self.filtered(lambda u: u.share))
            
            if users_becoming_internal > 0:
                remaining_slots = saas_config.get_remaining_users()
                
                if users_becoming_internal > remaining_slots:
                    # Try to sync with SaaS Manager
                    saas_config.sync_with_saas_manager()
                    remaining_slots = saas_config.get_remaining_users()
                    
                    if users_becoming_internal > remaining_slots:
                        if remaining_slots == 0:
                            raise exceptions.ValidationError(
                                _("User limit reached! This tenant is limited to %d users. "
                                  "Please upgrade your plan to add more users.") % saas_config.max_users
                            )
                        else:
                            raise exceptions.ValidationError(
                                _("User limit exceeded! You can only convert %d more user(s) to internal users. "
                                  "This tenant is limited to %d users total.") % (remaining_slots, saas_config.max_users)
                            )
        
        return super(ResUsers, self).write(vals)

    @api.model
    def get_user_limit_info(self):
        """Get user limit information for display"""
        saas_config = self.env['saas.config'].get_or_create_config()
        saas_config._compute_current_users()
        
        return {
            'max_users': saas_config.max_users,
            'current_users': saas_config.current_users,
            'remaining_users': saas_config.get_remaining_users(),
            'percentage_used': round((saas_config.current_users / saas_config.max_users) * 100, 1) if saas_config.max_users > 0 else 0,
        }

    def action_show_user_limit_info(self):
        """Action to show user limit information"""
        info = self.get_user_limit_info()
        message = _(
            "User Limit Information:\n\n"
            "• Maximum Users: %d\n"
            "• Current Users: %d\n"
            "• Remaining Slots: %d\n"
            "• Usage: %s%%"
        ) % (info['max_users'], info['current_users'], info['remaining_users'], info['percentage_used'])
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('User Limit Status'),
                'message': message,
                'type': 'info',
                'sticky': False,
            }
        }
