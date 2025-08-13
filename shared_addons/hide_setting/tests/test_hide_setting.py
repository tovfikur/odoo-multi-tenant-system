from odoo.tests.common import TransactionCase
from odoo.exceptions import AccessError


class TestHideSetting(TransactionCase):

    def setUp(self):
        super(TestHideSetting, self).setUp()
        self.hide_config_model = self.env['hide.setting.config']
        
    def test_create_hide_setting_config(self):
        """Test creating hide setting configuration"""
        config = self.hide_config_model.create({
            'is_active': True
        })
        self.assertTrue(config.is_active)
        self.assertTrue(config.activated_by)
        self.assertTrue(config.activation_date)
        
    def test_get_hide_setting_status(self):
        """Test getting hide setting status via API"""
        # Create config
        self.hide_config_model.create({'is_active': True})
        
        # Test API method
        status = self.hide_config_model.get_hide_setting_status()
        self.assertTrue(status['is_active'])
        self.assertIn('activated_by', status)
        self.assertIn('activation_date', status)
        
    def test_toggle_hide_setting(self):
        """Test toggling hide setting via API"""
        # Test enabling
        result = self.hide_config_model.toggle_hide_setting(True)
        self.assertTrue(result['success'])
        self.assertTrue(result['is_active'])
        
        # Test disabling
        result = self.hide_config_model.toggle_hide_setting(False)
        self.assertTrue(result['success'])
        self.assertFalse(result['is_active'])
        
    def test_is_settings_hidden(self):
        """Test checking if settings should be hidden"""
        # Initially should be False
        self.assertFalse(self.hide_config_model.is_settings_hidden())
        
        # Enable hiding
        self.hide_config_model.create({'is_active': True})
        self.assertTrue(self.hide_config_model.is_settings_hidden())
        
    def test_only_one_config_record(self):
        """Test that only one configuration record can exist"""
        # Create first record
        config1 = self.hide_config_model.create({'is_active': True})
        
        # Create second record (should replace first)
        config2 = self.hide_config_model.create({'is_active': False})
        
        # Should only have one record
        all_configs = self.hide_config_model.search([])
        self.assertEqual(len(all_configs), 1)
        self.assertEqual(all_configs.id, config2.id)