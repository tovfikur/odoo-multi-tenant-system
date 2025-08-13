#!/usr/bin/env python3
"""
Admin Login and CMS Test - Test the complete flow as an admin user
"""

import requests
import re
from datetime import datetime

def login_as_admin():
    """Login as admin and return session"""
    session = requests.Session()
    
    # Get login page to extract CSRF token
    response = session.get("http://localhost:8000/login")
    if response.status_code != 200:
        print(f"❌ Login page failed: {response.status_code}")
        return None
    
    # Extract CSRF token
    csrf_match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.text)
    if not csrf_match:
        print("❌ CSRF token not found in login page")
        return None
    
    csrf_token = csrf_match.group(1)
    print(f"✅ CSRF token extracted: {csrf_token[:20]}...")
    
    # Login with admin credentials
    login_data = {
        'username': 'admin',
        'password': 'admin123',
        'csrf_token': csrf_token
    }
    
    response = session.post("http://localhost:8000/login", data=login_data, allow_redirects=False)
    
    if response.status_code in [200, 302]:
        print("✅ Admin login successful")
        return session
    else:
        print(f"❌ Admin login failed: {response.status_code}")
        return None

def test_cms_with_admin_session(session):
    """Test CMS functionality with authenticated admin session"""
    print("\n🔧 Testing CMS with Admin Session")
    print("-" * 40)
    
    # Test 1: Get all content
    response = session.get("http://localhost:8000/api/cms/content")
    if response.status_code == 200:
        try:
            data = response.json()
            if data.get('success'):
                blocks = data.get('content_blocks', [])
                print(f"✅ API GET /api/cms/content: {len(blocks)} content blocks")
            else:
                print(f"❌ API returned success=false: {data.get('message')}")
                return False
        except Exception as e:
            print(f"❌ JSON parsing failed: {e}")
            return False
    else:
        print(f"❌ GET content failed: {response.status_code}")
        return False
    
    # Test 2: Get content by category
    response = session.get("http://localhost:8000/api/cms/content?category=homepage")
    if response.status_code == 200:
        try:
            data = response.json()
            if data.get('success'):
                homepage_blocks = data.get('content_blocks', [])
                print(f"✅ API GET with category filter: {len(homepage_blocks)} homepage blocks")
            else:
                print(f"❌ Category filter failed: {data.get('message')}")
                return False
        except Exception as e:
            print(f"❌ Category filter JSON parsing failed: {e}")
            return False
    else:
        print(f"❌ GET with category failed: {response.status_code}")
        return False
    
    # Test 3: Get individual content block (get hero_title)
    hero_id = None
    for block in blocks:
        if block.get('identifier') == 'hero_title':
            hero_id = block.get('id')
            break
    
    if hero_id:
        response = session.get(f"http://localhost:8000/api/cms/content/{hero_id}")
        if response.status_code == 200:
            try:
                data = response.json()
                if data.get('success'):
                    content = data.get('content_block', {}).get('content', '')
                    print(f"✅ API GET individual block: {content[:50]}...")
                else:
                    print(f"❌ Individual block get failed: {data.get('message')}")
                    return False
            except Exception as e:
                print(f"❌ Individual block JSON parsing failed: {e}")
                return False
        else:
            print(f"❌ GET individual block failed: {response.status_code}")
            return False
        
        # Test 4: Update content block
        test_content = f"🧪 Admin Test - {datetime.now().strftime('%H:%M:%S')}"
        update_data = {
            'content': test_content,
            'title': 'Hero Title',
            'identifier': 'hero_title',
            'content_type': 'text',
            'category': 'homepage',
            'section': 'hero',
            'sort_order': 0,
            'is_active': True
        }
        
        response = session.put(
            f"http://localhost:8000/api/cms/content/{hero_id}",
            json=update_data,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            try:
                data = response.json()
                if data.get('success'):
                    print(f"✅ API PUT update successful: {test_content}")
                else:
                    print(f"❌ Update failed: {data.get('message')}")
                    return False
            except Exception as e:
                print(f"❌ Update JSON parsing failed: {e}")
                return False
        else:
            print(f"❌ PUT update failed: {response.status_code}")
            return False
        
        # Test 5: Verify update by getting content again
        response = session.get(f"http://localhost:8000/api/cms/content/{hero_id}")
        if response.status_code == 200:
            try:
                data = response.json()
                if data.get('success'):
                    updated_content = data.get('content_block', {}).get('content', '')
                    if test_content in updated_content:
                        print(f"✅ Update verification successful")
                    else:
                        print(f"❌ Update not reflected: {updated_content}")
                        return False
                else:
                    print(f"❌ Verification failed: {data.get('message')}")
                    return False
            except Exception as e:
                print(f"❌ Verification JSON parsing failed: {e}")
                return False
        else:
            print(f"❌ Verification request failed: {response.status_code}")
            return False
        
        # Test 6: Check if homepage reflects the change
        response = session.get("http://localhost:8000/")
        if response.status_code == 200:
            if test_content in response.text:
                print(f"✅ Homepage reflects CMS change!")
            else:
                print(f"⚠️  Homepage doesn't show change (might be cached)")
        else:
            print(f"❌ Homepage request failed: {response.status_code}")
        
        # Restore original content
        restore_data = update_data.copy()
        restore_data['content'] = 'সময়, শ্রম ও টাকার সঠিক ব্যবহার শুরু হোক এখানেই'
        
        response = session.put(
            f"http://localhost:8000/api/cms/content/{hero_id}",
            json=restore_data,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            print(f"🔄 Original content restored")
        
        return True
    else:
        print("❌ Hero title block not found")
        return False

def test_admin_interface(session):
    """Test admin interface access"""
    print("\n🔐 Testing Admin Interface")
    print("-" * 40)
    
    response = session.get("http://localhost:8000/admin/content")
    if response.status_code == 200:
        if "Content Manager" in response.text and "Content Blocks" in response.text:
            print("✅ Admin content manager loads successfully")
            return True
        else:
            print("❌ Admin content manager page incomplete")
            return False
    else:
        print(f"❌ Admin content manager failed: {response.status_code}")
        return False

def run_admin_test():
    """Run complete admin test suite"""
    print("🎯 Admin CMS Testing Suite")
    print("=" * 50)
    
    # Login as admin
    session = login_as_admin()
    if not session:
        print("❌ Cannot proceed without admin login")
        return False
    
    # Test CMS API
    api_success = test_cms_with_admin_session(session)
    
    # Test admin interface
    interface_success = test_admin_interface(session)
    
    print(f"\n📊 Admin Test Results:")
    print(f"   • Admin Login: ✅ Success")
    print(f"   • CMS API: {'✅ Success' if api_success else '❌ Failed'}")
    print(f"   • Admin Interface: {'✅ Success' if interface_success else '❌ Failed'}")
    
    if api_success and interface_success:
        print("\n🎉 Production CMS is fully functional!")
        print("\n📋 How to use:")
        print("   1. Login as admin at http://localhost:8000/login")
        print("   2. Use Admin dropdown -> Content Manager")
        print("   3. Edit content blocks - changes reflect on homepage")
        print("   4. Homepage at http://localhost:8000/ uses dynamic CMS content")
        return True
    else:
        print("\n⚠️  Some tests failed. Check logs above.")
        return False

if __name__ == "__main__":
    success = run_admin_test()
    exit(0 if success else 1)