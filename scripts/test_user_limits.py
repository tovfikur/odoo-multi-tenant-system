#!/usr/bin/env python3
"""
Test script to verify user limit functionality is working
"""

import os

def test_user_limit_api():
    """Check if API endpoints are implemented"""
    print("🔍 Checking User Limit API implementation...")
    
    # Check if API endpoints are in app.py
    app_py_path = "k:/Odoo Multi-Tenant System/saas_manager/app.py"
    
    if not os.path.exists(app_py_path):
        print("❌ app.py not found")
        return False
    
    with open(app_py_path, 'r') as f:
        content = f.read()
    
    endpoints = [
        "/api/tenant/<subdomain>/user-limit",
        "get_tenant_user_limit_api",
        "update_tenant_user_limit_api"
    ]
    
    all_found = True
    for endpoint in endpoints:
        if endpoint in content:
            print(f"✅ Found: {endpoint}")
        else:
            print(f"❌ Missing: {endpoint}")
            all_found = False
    
    return all_found

def check_module_files():
    """Check if all required module files exist"""
    print("\n📁 Checking module files...")
    
    import os
    base_path = "k:/Odoo Multi-Tenant System/shared_addons/saas_user_limit"
    
    required_files = [
        "__manifest__.py",
        "__init__.py",
        "models/__init__.py",
        "models/saas_config.py",
        "models/res_users.py",
        "security/ir.model.access.csv",
        "views/saas_config_views.xml",
        "views/res_users_views.xml"
    ]
    
    all_exist = True
    for file_path in required_files:
        full_path = os.path.join(base_path, file_path)
        if os.path.exists(full_path):
            print(f"✅ {file_path}")
        else:
            print(f"❌ Missing: {file_path}")
            all_exist = False
    
    return all_exist

def check_docker_volumes():
    """Check if Docker volumes are properly configured"""
    print("\n🐳 Checking Docker configuration...")
    
    import os
    docker_compose_path = "k:/Odoo Multi-Tenant System/docker-compose.yml"
    
    if not os.path.exists(docker_compose_path):
        print("❌ docker-compose.yml not found")
        return False
    
    with open(docker_compose_path, 'r') as f:
        content = f.read()
    
    if "./shared_addons:/mnt/shared-addons" in content:
        print("✅ Shared addons volume mounted in docker-compose.yml")
        return True
    else:
        print("❌ Shared addons volume NOT mounted in docker-compose.yml")
        return False

def check_odoo_config():
    """Check if Odoo config includes shared addons path"""
    print("\n⚙️  Checking Odoo configuration...")
    
    import os
    
    configs = [
        "k:/Odoo Multi-Tenant System/odoo_master/config/odoo.conf",
        "k:/Odoo Multi-Tenant System/odoo_workers/config/odoo.conf"
    ]
    
    all_good = True
    for config_path in configs:
        config_name = "master" if "master" in config_path else "workers"
        
        if not os.path.exists(config_path):
            print(f"❌ {config_name} config not found")
            all_good = False
            continue
        
        with open(config_path, 'r') as f:
            content = f.read()
        
        if "/mnt/shared-addons" in content:
            print(f"✅ {config_name} config includes shared addons path")
        else:
            print(f"❌ {config_name} config missing shared addons path")
            all_good = False
    
    return all_good

def main():
    """Run all tests"""
    print("User Limit System Test\n" + "="*50)
    
    tests = [
        ("Module Files", check_module_files),
        ("Docker Volumes", check_docker_volumes),
        ("Odoo Config", check_odoo_config),
        ("API Endpoints", test_user_limit_api)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        result = test_func()
        results.append((test_name, result))
    
    print("\n" + "="*50)
    print("📊 Test Results:")
    all_passed = True
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {test_name}: {status}")
        if not result:
            all_passed = False
    
    print(f"\n🎯 Overall Status: {'✅ ALL SYSTEMS GO!' if all_passed else '❌ ISSUES FOUND'}")
    
    if all_passed:
        print("\n🚀 Next steps:")
        print("1. Run 'docker-compose up -d --build' to rebuild with new configuration")
        print("2. Check Odoo module installation: Apps > Search 'saas_user_limit' > Install")
        print("3. Test user creation in tenant databases")

if __name__ == "__main__":
    main()
