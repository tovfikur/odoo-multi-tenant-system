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
        saas_config = self.env['saas.controller'].get_or_create_config()
        
        if saas_config.user_limit_enabled:
            # Count how many new internal users we're trying to create
            new_internal_users = 0
            for vals in vals_list:
                # Check if this is an internal user (not portal/public)
                if not vals.get('share', False):
                    new_internal_users += 1
            
            if new_internal_users > 0:
                # Check if we have enough remaining slots
                remaining_users = saas_config.get_remaining_users()
                if new_internal_users > remaining_users:
                    raise exceptions.ValidationError(
                        _("Cannot create %d user(s). User limit reached. "
                          "Maximum users: %d, Current users: %d, Available slots: %d") % (
                            new_internal_users,
                            saas_config.max_users,
                            saas_config.current_users,
                            remaining_users
                        )
                    )
        
        return super(ResUsers, self).create(vals_list)

    def write(self, vals):
        """Override user modification to prevent bypassing limits"""
        
        if 'share' in vals:
            saas_config = self.env['saas.controller'].get_or_create_config()
            
            if saas_config.user_limit_enabled:
                # Check if we're changing portal users to internal users
                becoming_internal = []
                for user in self:
                    if user.share and not vals.get('share', True):
                        becoming_internal.append(user)
                
                if becoming_internal:
                    remaining_users = saas_config.get_remaining_users()
                    if len(becoming_internal) > remaining_users:
                        raise exceptions.ValidationError(
                            _("Cannot convert %d portal user(s) to internal users. "
                              "User limit would be exceeded. Available slots: %d") % (
                                len(becoming_internal), remaining_users
                            )
                        )
        
        return super(ResUsers, self).write(vals)

    @api.model
    def get_user_limit_info(self):
        """Get user limit information for current tenant"""
        saas_config = self.env['saas.controller'].get_or_create_config()
        return {
            'max_users': saas_config.max_users,
            'current_users': saas_config.current_users,
            'remaining_users': saas_config.get_remaining_users(),
            'limit_enabled': saas_config.user_limit_enabled,
        }
