"""
Base mixin for muk_web user preferences to eliminate code duplication.
Provides common pattern for extending user preferences with UI customization fields.
"""

from odoo import models, fields
from abc import ABC, abstractmethod


class MukWebUserPreferenceMixin(models.AbstractModel):
    """
    Abstract base mixin for muk_web user preference extensions.
    
    This mixin provides the common pattern for extending res.users
    with custom preference fields that need to be self-readable and
    self-writeable by users.
    
    Subclasses must implement get_preference_fields() to define
    their specific preference field names.
    """
    
    _name = 'muk.web.user.preference.mixin'
    _description = 'Muk Web User Preference Base Mixin'
    
    # Properties to be extended by inheriting models
    @property
    def SELF_READABLE_FIELDS(self):
        """Extend SELF_READABLE_FIELDS with preference fields."""
        base_fields = super().SELF_READABLE_FIELDS if hasattr(super(), 'SELF_READABLE_FIELDS') else []
        return base_fields + self.get_preference_fields()

    @property
    def SELF_WRITEABLE_FIELDS(self):
        """Extend SELF_WRITEABLE_FIELDS with preference fields."""
        base_fields = super().SELF_WRITEABLE_FIELDS if hasattr(super(), 'SELF_WRITEABLE_FIELDS') else []
        return base_fields + self.get_preference_fields()

    @abstractmethod
    def get_preference_fields(self):
        """
        Return list of preference field names to be added to SELF_READABLE_FIELDS
        and SELF_WRITEABLE_FIELDS.
        
        Must be implemented by subclasses.
        
        Returns:
            list: List of field names (strings)
        """
        pass

    @classmethod
    def _create_preference_field(cls, field_name, selection_options, default_value, help_text=None):
        """
        Helper method to create standardized preference selection fields.
        
        Args:
            field_name (str): Name of the field
            selection_options (list): List of (value, label) tuples for selection
            default_value (str): Default value for the field
            help_text (str, optional): Help text for the field
        
        Returns:
            fields.Selection: Configured selection field
        """
        field_config = {
            'selection': selection_options,
            'string': field_name.replace('_', ' ').title(),
            'default': default_value,
            'required': True,
        }
        
        if help_text:
            field_config['help'] = help_text
            
        return fields.Selection(**field_config)


class ResUsersMukWebMixin(models.AbstractModel):
    """
    Convenience mixin that inherits res.users and MukWebUserPreferenceMixin.
    Use this as a base for muk_web user preference extensions.
    """
    
    _name = 'res.users.muk.web.mixin'
    _inherit = ['res.users', 'muk.web.user.preference.mixin']
    _description = 'Res Users Muk Web Preference Mixin'
