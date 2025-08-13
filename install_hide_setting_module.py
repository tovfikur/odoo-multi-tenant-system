#!/usr/bin/env python3
"""
Install hide_setting module via API
"""

import xmlrpc.client
import time

# Configuration
URL = 'http://localhost:8069'
DB = 'odoo_master'
USERNAME = 'admin'
PASSWORD = 'admin'

def install_hide_setting_module():
    print("Installing Hide Setting Module...")
    
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
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        
        # Find the module
        print("🔍 Searching for hide_setting module...")
        modules = models.execute_kw(DB, uid, PASSWORD,
            'ir.module.module', 'search_read',
            [[['name', '=', 'hide_setting']]],
            {'fields': ['name', 'state', 'installed_version']})
        
        if not modules:
            print("❌ Module not found!")
            return False
        
        module = modules[0]
        print(f"✅ Found module: {module['name']} (state: {module['state']})")
        
        if module['state'] == 'installed':
            print("✅ Module is already installed!")
            return True
        elif module['state'] == 'to upgrade':
            print("⚠️  Module needs upgrade...")
            # Trigger upgrade
            models.execute_kw(DB, uid, PASSWORD,
                'ir.module.module', 'button_immediate_upgrade', [module['id']])
            print("✅ Module upgrade initiated!")
        elif module['state'] in ['uninstalled', 'uninstallable']:
            print("📦 Installing module...")
            # Install module
            models.execute_kw(DB, uid, PASSWORD,
                'ir.module.module', 'button_immediate_install', [module['id']])
            print("✅ Module installation initiated!")
        
        # Wait a bit for installation to complete
        print("⏳ Waiting for installation to complete...")
        time.sleep(5)
        
        # Check final status
        updated_modules = models.execute_kw(DB, uid, PASSWORD,
            'ir.module.module', 'search_read',
            [[['name', '=', 'hide_setting']]],
            {'fields': ['name', 'state', 'installed_version']})
        
        if updated_modules:
            final_module = updated_modules[0]
            print(f"📊 Final status: {final_module['state']}")
            
            if final_module['state'] == 'installed':
                print("🎉 Module successfully installed!")
                return True
            else:
                print(f"⚠️  Module state: {final_module['state']}")
                return False
        
        return False
        
    except Exception as e:
        print(f"❌ Installation failed: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("HIDE SETTING MODULE INSTALLER")
    print("=" * 50)
    
    success = install_hide_setting_module()
    
    if success:
        print("\n🎉 Installation completed successfully!")
        print("\nNext steps:")
        print("1. Go to Settings → Administration → UI Security Settings")
        print("2. Enable 'Hide Settings from UI'")
        print("3. Settings will be hidden from the interface")
        print("4. Use API to manage settings after that")
    else:
        print("\n❌ Installation failed. Please try manually:")
        print("1. Go to http://localhost:8069")
        print("2. Login as admin")
        print("3. Go to Apps → Update Apps List")
        print("4. Search for 'Hide Settings'")
        print("5. Click Install")
    
    print("\n" + "=" * 50)