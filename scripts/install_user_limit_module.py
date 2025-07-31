#!/usr/bin/env python3
"""
Helper script to install saas_user_limit module via XML-RPC
"""

import xmlrpc.client
import sys
import os

def install_module(db_name, username, password, odoo_url="http://localhost:8069"):
    """Install saas_user_limit module in specified database"""
    
    print(f"Installing saas_user_limit module in database: {db_name}")
    print(f"Odoo URL: {odoo_url}")
    print(f"Username: {username}")
    
    try:
        # Connect to Odoo
        common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common")
        
        # Test connection
        version = common.version()
        print(f"Connected to Odoo {version['server_version']}")
        
        # Authenticate
        uid = common.authenticate(db_name, username, password, {})
        if not uid:
            print("ERROR: Authentication failed!")
            return False
        
        print(f"Authenticated as user ID: {uid}")
        
        # Connect to object service
        models = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/object")
        
        # Search for the module
        module_ids = models.execute_kw(
            db_name, uid, password,
            'ir.module.module', 'search',
            [[['name', '=', 'saas_user_limit']]]
        )
        
        if not module_ids:
            print("ERROR: saas_user_limit module not found in addons path!")
            print("Make sure the module is properly mounted and accessible.")
            return False
        
        module_id = module_ids[0]
        print(f"Found module with ID: {module_id}")
        
        # Get module info
        module_info = models.execute_kw(
            db_name, uid, password,
            'ir.module.module', 'read',
            [module_id], {'fields': ['name', 'state', 'summary']}
        )[0]
        
        print(f"Module state: {module_info['state']}")
        print(f"Module summary: {module_info['summary']}")
        
        if module_info['state'] == 'installed':
            print("SUCCESS: Module is already installed!")
            return True
        elif module_info['state'] in ['uninstalled', 'uninstallable']:
            print("Installing module...")
            
            # Install the module
            models.execute_kw(
                db_name, uid, password,
                'ir.module.module', 'button_immediate_install',
                [module_id]
            )
            
            print("SUCCESS: Module installation initiated!")
            print("Note: Installation may take a moment to complete.")
            return True
        else:
            print(f"Module is in state: {module_info['state']}")
            return False
            
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def check_module_availability(odoo_url="http://localhost:8069"):
    """Check if module is available in any database"""
    print("Checking module availability...")
    
    try:
        # Try to connect to a common database
        test_dbs = ["postgres", "odoo_master"]
        
        for db_name in test_dbs:
            try:
                common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common")
                uid = common.authenticate(db_name, "admin", "admin", {})
                
                if uid:
                    models = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/object")
                    
                    # Check if module exists
                    module_ids = models.execute_kw(
                        db_name, uid, "admin",
                        'ir.module.module', 'search',
                        [[['name', '=', 'saas_user_limit']]]
                    )
                    
                    if module_ids:
                        print(f"SUCCESS: Module found in database '{db_name}'")
                        return True
                    else:
                        print(f"Module not found in database '{db_name}'")
                        
            except Exception as e:
                print(f"Could not check database '{db_name}': {e}")
                
        print("Module not found in any accessible database")
        return False
        
    except Exception as e:
        print(f"ERROR checking module availability: {e}")
        return False

def main():
    """Main function"""
    print("SaaS User Limit Module Installer")
    print("=" * 40)
    
    if len(sys.argv) < 4:
        print("Usage: python install_user_limit_module.py <db_name> <username> <password> [odoo_url]")
        print("Example: python install_user_limit_module.py kdoo_test admin admin123")
        print()
        print("Checking module availability first...")
        check_module_availability()
        return
    
    db_name = sys.argv[1]
    username = sys.argv[2]
    password = sys.argv[3]
    odoo_url = sys.argv[4] if len(sys.argv) > 4 else "http://localhost:8069"
    
    # Install the module
    success = install_module(db_name, username, password, odoo_url)
    
    if success:
        print("\n" + "=" * 40)
        print("INSTALLATION COMPLETE!")
        print()
        print("Next steps:")
        print("1. Refresh your browser")
        print("2. Go to Apps menu")
        print("3. Search for 'saas_user_limit'")
        print("4. Verify it shows as 'Installed'")
        print("5. Try creating a user to test the limit")
    else:
        print("\n" + "=" * 40)
        print("INSTALLATION FAILED!")
        print()
        print("Troubleshooting:")
        print("1. Make sure Docker containers are running")
        print("2. Verify shared_addons volume is mounted")
        print("3. Check Odoo logs for errors")
        print("4. Ensure the database exists and credentials are correct")

if __name__ == "__main__":
    main()
