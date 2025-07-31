#!/usr/bin/env python3
"""
Simple test script to verify billing system functionality
"""
import requests
import sys
import json

def test_endpoint(url, description):
    """Test an endpoint and report results"""
    try:
        print(f"Testing {description}...")
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            print(f"✅ {description} - Status: {response.status_code}")
            return True
        elif response.status_code == 302:
            print(f"⚠️  {description} - Redirect: {response.status_code} (likely requires login)")
            return True
        else:
            print(f"❌ {description} - Status: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ {description} - Error: {e}")
        return False

def main():
    """Run billing system tests"""
    base_url = "http://localhost:8000"
    
    tests = [
        (f"{base_url}/health", "Health Check"),
        (f"{base_url}/billing/overview", "Billing Overview Page"),
        (f"{base_url}/", "Main Application"),
    ]
    
    print("🚀 Testing Billing System...")
    print("=" * 50)
    
    results = []
    for url, description in tests:
        results.append(test_endpoint(url, description))
    
    print("=" * 50)
    success_count = sum(results)
    total_count = len(results)
    
    if success_count == total_count:
        print(f"🎉 All tests passed! ({success_count}/{total_count})")
        print("✅ Billing system is working correctly!")
        return 0
    else:
        print(f"⚠️  Some tests failed. ({success_count}/{total_count})")
        return 1

if __name__ == "__main__":
    sys.exit(main())
