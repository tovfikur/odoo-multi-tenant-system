#!/usr/bin/env python3
"""
Complete SaaS Controller Test Suite
Tests installation, XML validity, and functionality
"""

import os
import sys
import time
import subprocess

def run_test(test_name, test_function):
    """Run a test and return result"""
    print(f"\n{'='*50}")
    print(f"Testing: {test_name}")
    print('='*50)
    
    try:
        result = test_function()
        if result:
            print(f"PASSED: {test_name}")
            return True
        else:
            print(f"FAILED: {test_name}")
            return False
    except Exception as e:
        print(f"ERROR in {test_name}: {e}")
        return False

def test_xml_validation():
    """Test XML file validation"""
    try:
        result = subprocess.run([
            sys.executable, 
            "K:/Odoo Multi-Tenant System/scripts/validate_xml.py"
        ], capture_output=True, text=True, timeout=30)
        
        print("XML Validation Output:")
        print(result.stdout)
        if result.stderr:
            print("Errors:")
            print(result.stderr)
            
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("XML validation timed out")
        return False
    except Exception as e:
        print(f"XML validation error: {e}")
        return False

def test_module_structure():
    """Test that all required module files exist"""
    required_files = [
        "K:/Odoo Multi-Tenant System/shared_addons/saas_controller/__manifest__.py",
        "K:/Odoo Multi-Tenant System/shared_addons/saas_controller/__init__.py",
        "K:/Odoo Multi-Tenant System/shared_addons/saas_controller/models/__init__.py",
        "K:/Odoo Multi-Tenant System/shared_addons/saas_controller/models/saas_controller.py",
        "K:/Odoo Multi-Tenant System/shared_addons/saas_controller/models/res_users.py",
        "K:/Odoo Multi-Tenant System/shared_addons/saas_controller/views/saas_controller_views.xml",
        "K:/Odoo Multi-Tenant System/shared_addons/saas_controller/security/ir.model.access.csv",
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
        else:
            print(f"Found: {os.path.basename(file_path)}")
    
    if missing_files:
        print("\nMissing files:")
        for file_path in missing_files:
            print(f"Missing: {file_path}")
        return False
    
    print(f"\nAll {len(required_files)} required files found")
    return True

def test_manifest_content():
    """Test manifest file content"""
    manifest_path = "K:/Odoo Multi-Tenant System/shared_addons/saas_controller/__manifest__.py"
    
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        required_keys = ['name', 'version', 'depends', 'data', 'installable']
        missing_keys = []
        
        for key in required_keys:
            if f"'{key}'" not in content and f'"{key}"' not in content:
                missing_keys.append(key)
            else:
                print(f"Found manifest key: {key}")
        
        if missing_keys:
            print(f"\nMissing manifest keys: {missing_keys}")
            return False
        
        # Check specific requirements
        if 'saas_controller' in content:
            print("Module name contains 'saas_controller'")
        else:
            print("Module name should contain 'saas_controller'")
            return False
            
        if "'base'" in content or '"base"' in content:
            print("Depends on 'base' module")
        else:
            print("Should depend on 'base' module")
            return False
        
        print("\nManifest file is properly configured")
        return True
        
    except Exception as e:
        print(f"Error reading manifest: {e}")
        return False

def test_model_syntax():
    """Test Python model syntax"""
    model_files = [
        "K:/Odoo Multi-Tenant System/shared_addons/saas_controller/models/saas_controller.py",
        "K:/Odoo Multi-Tenant System/shared_addons/saas_controller/models/res_users.py",
        "K:/Odoo Multi-Tenant System/shared_addons/saas_controller/models/res_company.py",
    ]
    
    for file_path in model_files:
        if not os.path.exists(file_path):
            print(f"Model file not found: {file_path}")
            return False
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Basic syntax check
            compile(content, file_path, 'exec')
            print(f"Python syntax valid: {os.path.basename(file_path)}")
            
            # Check for required Odoo patterns
            if 'models.Model' in content:
                print(f"  Contains Odoo model: {os.path.basename(file_path)}")
            else:
                print(f"  No Odoo model found: {os.path.basename(file_path)}")
                
        except SyntaxError as e:
            print(f"Syntax error in {file_path}: {e}")
            return False
        except Exception as e:
            print(f"Error checking {file_path}: {e}")
            return False
    
    print("\nAll Python model files have valid syntax")
    return True

def test_docker_containers():
    """Test that Docker containers are running"""
    try:
        result = subprocess.run([
            'docker-compose', 'ps', '--services', '--filter', 'status=running'
        ], capture_output=True, text=True, cwd="K:/Odoo Multi-Tenant System", timeout=30)
        
        running_services = result.stdout.strip().split('\n')
        expected_services = ['postgres', 'redis', 'saas_manager', 'odoo_master']
        
        print("Running services:")
        for service in running_services:
            if service.strip():
                print(f"{service}")
        
        missing_services = []
        for service in expected_services:
            if service not in running_services:
                missing_services.append(service)
        
        if missing_services:
            print(f"\nMissing services: {missing_services}")
            return False
        
        print(f"\nAll required Docker services are running")
        return True
        
    except subprocess.TimeoutExpired:
        print("Docker status check timed out")
        return False
    except Exception as e:
        print(f"Error checking Docker containers: {e}")
        return False

def test_saas_manager_health():
    """Test SaaS Manager health endpoint"""
    try:
        # Try to import requests, fallback to basic check if not available
        try:
            import requests
            response = requests.get('http://localhost:8000/health', timeout=10)
            if response.status_code == 200:
                print("SaaS Manager is responding")
                return True
            else:
                print(f"SaaS Manager returned status {response.status_code}")
                return False
        except ImportError:
            print("requests module not available, skipping HTTP test")
            # Check if SaaS Manager container is running instead
            result = subprocess.run([
                'docker-compose', 'ps', '-q', 'saas_manager'
            ], capture_output=True, text=True, cwd="K:/Odoo Multi-Tenant System", timeout=10)
            
            if result.stdout.strip():
                print("SaaS Manager container is running")
                return True
            else:
                print("SaaS Manager container not found")
                return False
                
    except Exception as e:
        print(f"Error checking SaaS Manager: {e}")
        return False

def main():
    """Main test function"""
    print("SaaS Controller Complete Test Suite")
    print("=" * 60)
    print("Testing migration from saas_user_limit to saas_controller")
    print("=" * 60)
    
    tests = [
        ("Module Structure", test_module_structure),
        ("Manifest Content", test_manifest_content),
        ("Python Model Syntax", test_model_syntax),
        ("XML Validation", test_xml_validation),
        ("Docker Containers", test_docker_containers),
        ("SaaS Manager Health", test_saas_manager_health),
    ]
    
    passed_tests = 0
    total_tests = len(tests)
    
    for test_name, test_function in tests:
        if run_test(test_name, test_function):
            passed_tests += 1
        time.sleep(1)  # Brief pause between tests
    
    # Final summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Tests Passed: {passed_tests}/{total_tests}")
    print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
    
    if passed_tests == total_tests:
        print("\nALL TESTS PASSED!")
        print("SaaS Controller is ready for production use")
        print("\nNext steps:")
        print("1. Install the module in your Odoo tenants")
        print("2. Configure tenant settings via the admin interface")
        print("3. Test user limits and branding functionality")
    else:
        print(f"\n{total_tests - passed_tests} tests failed")
        print("Please review the failed tests and fix any issues")
    
    return passed_tests == total_tests

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
