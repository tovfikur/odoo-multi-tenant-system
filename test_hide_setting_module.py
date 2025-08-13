#!/usr/bin/env python3
"""
Test script for hide_setting module
"""

import xmlrpc.client
import json

# Configuration
URL = 'http://localhost:8069'
DB = 'odoo_master'  # Master database
USERNAME = 'admin'
PASSWORD = 'admin'

def test_hide_setting_module():
    print("Testing Hide Setting Module...")
    
    try:
        # Connect to Odoo
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        print(f"Connecting to {URL}...")
        
        # Authenticate
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        if not uid:
            print("❌ Authentication failed!")
            return False
        
        print(f"✅ Authenticated as user ID: {uid}")
        
        # Create model proxy
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object', allow_none=True)
        
        # Test 1: Check if hide.setting.config model exists
        print("\n1. Testing model existence...")
        try:
            result = models.execute_kw(DB, uid, PASSWORD, 
                'hide.setting.config', 'get_hide_setting_status', [])
            print("✅ hide.setting.config model is accessible")
            print(f"   Current status: {result}")
        except Exception as e:
            print(f"❌ Model not accessible: {e}")
            return False
        
        # Test 2: Test API methods
        print("\n2. Testing API methods...")
        
        # Enable hiding
        try:
            result = models.execute_kw(DB, uid, PASSWORD,
                'hide.setting.config', 'toggle_hide_setting', [True])
            print("✅ Successfully enabled hide setting")
            print(f"   Result: {result}")
        except Exception as e:
            print(f"❌ Failed to enable: {e}")
            return False
        
        # Check status
        try:
            status = models.execute_kw(DB, uid, PASSWORD,
                'hide.setting.config', 'get_hide_setting_status', [])
            print(f"✅ Current status: {status}")
            
            if status.get('is_active'):
                print("✅ Hide setting is active")
            else:
                print("❌ Hide setting should be active but isn't")
                return False
                
        except Exception as e:
            print(f"❌ Failed to get status: {e}")
            return False
        
        # Test is_settings_hidden
        try:
            hidden = models.execute_kw(DB, uid, PASSWORD,
                'hide.setting.config', 'is_settings_hidden', [])
            print(f"✅ is_settings_hidden returned: {hidden}")
        except Exception as e:
            print(f"❌ is_settings_hidden failed: {e}")
            return False
        
        # Disable hiding
        try:
            result = models.execute_kw(DB, uid, PASSWORD,
                'hide.setting.config', 'toggle_hide_setting', [False])
            print("✅ Successfully disabled hide setting")
            print(f"   Result: {result}")
        except Exception as e:
            print(f"❌ Failed to disable: {e}")
            return False
        
        print("\n✅ All tests passed! Module is working correctly.")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False

def test_module_installation():
    """Check if the module is installed"""
    print("\n3. Checking module installation...")
    
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        
        if not uid:
            return False
        
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object', allow_none=True)
        
        # Search for the module
        modules = models.execute_kw(DB, uid, PASSWORD,
            'ir.module.module', 'search_read',
            [[['name', '=', 'hide_setting']]],
            {'fields': ['name', 'state', 'installed_version']})
        
        if modules:
            module = modules[0]
            print(f"✅ Module found: {module['name']}")
            print(f"   State: {module['state']}")
            print(f"   Version: {module.get('installed_version', 'N/A')}")
            
            if module['state'] == 'installed':
                print("✅ Module is installed")
                return True
            else:
                print(f"❌ Module state is: {module['state']}")
                return False
        else:
            print("❌ Module not found in database")
            return False
            
    except Exception as e:
        print(f"❌ Module check failed: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("HIDE SETTING MODULE TEST")
    print("=" * 50)
    
    # First check if module is installed
    if test_module_installation():
        # Then test functionality
        test_hide_setting_module()
    else:
        print("\n❌ Module is not installed. Please install the 'hide_setting' module first.")
        print("\nTo install:")
        print("1. Go to Apps in Odoo")
        print("2. Search for 'Hide Settings'")  
        print("3. Click Install")
    
    print("\n" + "=" * 50)