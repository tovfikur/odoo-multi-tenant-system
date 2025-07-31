#!/usr/bin/env python3
"""
Test script for SaaS Controller functionality
"""

import sys
import os
import time

try:
    import requests
except ImportError:
    print("WARNING: requests module not available, skipping API tests")
    requests = None

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_saas_manager_api():
    """Test SaaS Manager API endpoints"""
    if not requests:
        print("WARNING: Skipping API tests - requests module not available")
        return
        
    base_url = "http://localhost:8000"
    
    print("Testing SaaS Manager API endpoints...")
    
    # Test config endpoint
    try:
        response = requests.get(f"{base_url}/api/tenant/demo/config", timeout=10)
        print(f"Config API Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print("Config Data:", data)
        else:
            print("Response:", response.text)
    except Exception as e:
        print(f"Config API Error: {e}")
    
    # Test user limit endpoint
    try:
        response = requests.get(f"{base_url}/api/tenant/demo/user-limit", timeout=10)
        print(f"User Limit API Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print("User Limit Data:", data)
        else:
            print("Response:", response.text)
    except Exception as e:
        print(f"User Limit API Error: {e}")

def test_odoo_integration():
    """Test Odoo integration with SaaS Controller"""
    print("\nTesting Odoo integration...")
    
    # This would require XML-RPC connection to Odoo
    # For now, we'll just print the test plan
    
    test_plan = [
        "1. Install saas_controller module in Odoo",
        "2. Create SaaS Controller configuration",
        "3. Test user limit enforcement",
        "4. Test branding configuration",
        "5. Test color schema application",
        "6. Test sync with SaaS Manager",
    ]
    
    for step in test_plan:
        print(f"  {step}")
    
    print("\nTo test Odoo integration manually:")
    print("1. Go to Odoo Admin > Apps > Search 'saas_controller'")
    print("2. Install the module")
    print("3. Go to SaaS Controller > Configuration")
    print("4. Configure settings and click 'Apply Configuration'")
    print("5. Test user creation with limits enabled")

def main():
    """Main test function"""
    print("SaaS Controller Test Suite")
    print("=" * 50)
    
    test_saas_manager_api()
    test_odoo_integration()
    
    print("\n" + "=" * 50)
    print("Test completed!")
    print("\nNext steps:")
    print("1. Start your Docker containers: docker-compose up -d")
    print("2. Install saas_controller module in Odoo")
    print("3. Configure your tenant settings")
    print("4. Test user limits and branding")

if __name__ == "__main__":
    main()
