#!/usr/bin/env python3
"""
Installation script for SaaS Controller module
"""

import xmlrpc.client
import sys
import os

def install_saas_controller(url, db, username, password):
    """Install SaaS Controller module in Odoo"""
    
    try:
        # Connect to Odoo
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        uid = common.authenticate(db, username, password, {})
        
        if not uid:
            print(f"❌ Authentication failed for user '{username}'")
            return False
            
        print(f"✅ Connected to Odoo as {username}")
        
        # Get models proxy
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        # Check if module exists
        module_ids = models.execute_kw(db, uid, password,
            'ir.module.module', 'search',
            [[['name', '=', 'saas_controller']]])
        
        if not module_ids:
            print("❌ SaaS Controller module not found in addons path")
            print("Make sure the module is in shared_addons directory")
            return False
            
        # Get module info
        module = models.execute_kw(db, uid, password,
            'ir.module.module', 'read',
            [module_ids[0]], {'fields': ['name', 'state', 'summary']})
        
        print(f"📦 Found module: {module[0]['name']}")
        print(f"📝 Summary: {module[0]['summary']}")
        print(f"🔄 Current state: {module[0]['state']}")
        
        # Install module if not already installed
        if module[0]['state'] in ['uninstalled', 'uninstallable']:
            print("🚀 Installing SaaS Controller module...")
            
            models.execute_kw(db, uid, password,
                'ir.module.module', 'button_immediate_install',
                [module_ids])
            
            print("✅ SaaS Controller module installed successfully!")
            
            # Create initial configuration
            print("🔧 Creating initial configuration...")
            
            config_data = {
                'database_name': db,
                'max_users': 10,
                'user_limit_enabled': True,
                'custom_app_name': 'Business Manager',
                'primary_color': '#017e84',
                'secondary_color': '#875a7b',
            }
            
            config_id = models.execute_kw(db, uid, password,
                'saas.controller', 'create', [config_data])
            
            print(f"✅ Created initial configuration (ID: {config_id})")
            
        elif module[0]['state'] == 'installed':
            print("ℹ️ Module is already installed")
            
            # Get or create configuration
            config_ids = models.execute_kw(db, uid, password,
                'saas.controller', 'search',
                [[['database_name', '=', db]]])
            
            if config_ids:
                print("✅ SaaS Controller configuration already exists")
            else:
                print("🔧 Creating configuration...")
                config_data = {
                    'database_name': db,
                    'max_users': 10,
                    'user_limit_enabled': True,
                }
                
                config_id = models.execute_kw(db, uid, password,
                    'saas.controller', 'create', [config_data])
                
                print(f"✅ Created configuration (ID: {config_id})")
                
        else:
            print(f"⚠️ Module state: {module[0]['state']}")
            
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    """Main installation function"""
    print("SaaS Controller Installation Script")
    print("=" * 50)
    
    # Default configuration
    configs = [
        {
            'url': 'http://localhost:8069',
            'db': 'kdoo_demo',
            'username': 'admin',
            'password': 'admin'
        },
        # Add more tenant configurations as needed
    ]
    
    for config in configs:
        print(f"\n📡 Installing on database: {config['db']}")
        success = install_saas_controller(**config)
        
        if success:
            print(f"✅ Installation completed for {config['db']}")
        else:
            print(f"❌ Installation failed for {config['db']}")
    
    print("\n" + "=" * 50)
    print("Installation script completed!")
    print("\nTo access SaaS Controller:")
    print("1. Log in to Odoo as admin")
    print("2. Go to SaaS Controller > Configuration")
    print("3. Configure your tenant settings")

if __name__ == "__main__":
    main()
