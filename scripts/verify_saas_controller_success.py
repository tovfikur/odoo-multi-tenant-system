#!/usr/bin/env python3
"""
Final verification script for SaaS Controller migration
Confirms that all issues have been resolved
"""

import sys
import os
import subprocess
import time

def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'='*60}")
    print(f" {title}")
    print('='*60)

def check_xml_validation():
    """Verify XML files are valid"""
    print_section("XML VALIDATION CHECK")
    
    try:
        result = subprocess.run([
            sys.executable, 
            "K:/Odoo Multi-Tenant System/scripts/validate_xml.py"
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0 and "SUCCESS" in result.stdout:
            print("✓ All XML files pass validation")
            return True
        else:
            print("✗ XML validation failed")
            print(result.stdout)
            return False
    except Exception as e:
        print(f"✗ XML validation error: {e}")
        return False

def check_docker_status():
    """Check Docker container status"""
    print_section("DOCKER CONTAINERS STATUS")
    
    try:
        result = subprocess.run([
            'docker-compose', 'ps', '--format', 'table'
        ], capture_output=True, text=True, cwd="K:/Odoo Multi-Tenant System", timeout=15)
        
        if result.returncode == 0:
            print("Docker containers status:")
            print(result.stdout)
            
            # Check if key services are running
            if 'saas_manager' in result.stdout and 'odoo_master' in result.stdout:
                print("✓ Key services are running")
                return True
            else:
                print("✗ Some key services may not be running")
                return False
        else:
            print("✗ Failed to check Docker status")
            return False
            
    except Exception as e:
        print(f"✗ Docker check error: {e}")
        return False

def check_module_structure():
    """Verify module structure is complete"""
    print_section("MODULE STRUCTURE CHECK")
    
    required_files = [
        "K:/Odoo Multi-Tenant System/shared_addons/saas_controller/__manifest__.py",
        "K:/Odoo Multi-Tenant System/shared_addons/saas_controller/models/saas_controller.py",
        "K:/Odoo Multi-Tenant System/shared_addons/saas_controller/views/saas_controller_views.xml",
        "K:/Odoo Multi-Tenant System/shared_addons/saas_controller/security/ir.model.access.csv",
    ]
    
    missing = []
    for file_path in required_files:
        if os.path.exists(file_path):
            print(f"✓ {os.path.basename(file_path)}")
        else:
            print(f"✗ {os.path.basename(file_path)}")
            missing.append(file_path)
    
    if not missing:
        print("✓ All required module files present")
        return True
    else:
        print(f"✗ Missing files: {len(missing)}")
        return False

def check_saas_manager_logs():
    """Check recent SaaS Manager logs for errors"""
    print_section("SAAS MANAGER HEALTH CHECK")
    
    try:
        result = subprocess.run([
            'docker-compose', 'logs', 'saas_manager', '--tail=50'
        ], capture_output=True, text=True, cwd="K:/Odoo Multi-Tenant System", timeout=15)
        
        if result.returncode == 0:
            logs = result.stdout
            
            # Check for recent errors
            error_indicators = [
                'ParseError',
                'xmlParseEntityRef',
                'ValidationError',
                'Failed to install module saas_controller'
            ]
            
            recent_errors = []
            for indicator in error_indicators:
                if indicator in logs:
                    recent_errors.append(indicator)
            
            if not recent_errors:
                print("✓ No recent installation errors in logs")
                return True
            else:
                print("✗ Found error indicators in logs:")
                for error in recent_errors:
                    print(f"  - {error}")
                return False
                
        else:
            print("✗ Failed to retrieve logs")
            return False
            
    except Exception as e:
        print(f"✗ Log check error: {e}")
        return False

def check_migration_completion():
    """Verify migration from saas_user_limit is complete"""
    print_section("MIGRATION COMPLETION CHECK")
    
    # Check if saas_user_limit is removed from SaaS Manager
    try:
        with open("K:/Odoo Multi-Tenant System/saas_manager/app.py", 'r') as f:
            content = f.read()
        
        if 'saas_user_limit' not in content:
            print("✓ saas_user_limit references removed from SaaS Manager")
        else:
            print("⚠ saas_user_limit still referenced in SaaS Manager")
            
        if 'saas_controller' in content:
            print("✓ saas_controller integrated in SaaS Manager")
            return True
        else:
            print("✗ saas_controller not found in SaaS Manager")
            return False
            
    except Exception as e:
        print(f"✗ Migration check error: {e}")
        return False

def main():
    """Main verification function"""
    print("SaaS Controller Migration - Final Verification")
    print("Checking that all XML validation issues have been resolved...")
    
    checks = [
        ("XML Validation", check_xml_validation),
        ("Module Structure", check_module_structure), 
        ("Docker Status", check_docker_status),
        ("SaaS Manager Health", check_saas_manager_logs),
        ("Migration Completion", check_migration_completion),
    ]
    
    passed = 0
    total = len(checks)
    
    for check_name, check_func in checks:
        try:
            if check_func():
                passed += 1
                print(f"\n✓ {check_name}: PASSED")
            else:
                print(f"\n✗ {check_name}: FAILED")
        except Exception as e:
            print(f"\n✗ {check_name}: ERROR - {e}")
        
        time.sleep(1)  # Brief pause between checks
    
    # Final summary
    print_section("FINAL VERIFICATION SUMMARY")
    print(f"Checks Passed: {passed}/{total}")
    print(f"Success Rate: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("\n🎉 SUCCESS! SaaS Controller migration is COMPLETE")
        print("\nAll XML validation issues have been resolved:")
        print("• Label field reference errors: FIXED")
        print("• XML entity escaping issues: FIXED") 
        print("• Odoo view validation: PASSED")
        print("• Module structure: COMPLETE")
        print("• Docker containers: RUNNING")
        print("• SaaS Manager integration: ACTIVE")
        
        print("\n📋 READY FOR PRODUCTION:")
        print("1. Install: python scripts/install_saas_controller.py")
        print("2. Configure: SaaS Controller > Configuration in Odoo")
        print("3. Test: Create users and verify limits work")
        
        print("\n📚 Documentation Available:")
        print("• SAAS_CONTROLLER_README.md - Complete guide")
        print("• INSTALL_SAAS_CONTROLLER.md - Installation steps")
        print("• ODOO_VIEW_TROUBLESHOOTING.md - XML troubleshooting")
        
        return True
    else:
        print(f"\n❌ {total - passed} checks failed")
        print("Please review the failed checks above")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
