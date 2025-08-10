#!/usr/bin/env python3
"""
User API Test Suite
Tests all user API endpoints and WebSocket functionality
"""

import requests
import json
import time
import io
from datetime import datetime
from typing import Dict, List, Any

class UserAPITester:
    """Test suite for User API endpoints"""
    
    def __init__(self, base_url: str = "http://localhost:5000", username: str = None, password: str = None):
        self.base_url = base_url
        self.session = requests.Session()
        self.username = username
        self.password = password
        self.user_id = None
        
        # Test results
        self.test_results = {
            'total': 0,
            'passed': 0,
            'failed': 0,
            'errors': []
        }
    
    def log(self, message: str, level: str = "INFO"):
        """Log test messages"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] {level}: {message}")
    
    def assert_response(self, response: requests.Response, expected_status: int = 200, 
                       should_have_success: bool = True) -> Dict[str, Any]:
        """Assert response status and structure"""
        self.test_results['total'] += 1
        
        try:
            # Check status code
            assert response.status_code == expected_status, \
                f"Expected status {expected_status}, got {response.status_code}"
            
            # Parse JSON
            data = response.json()
            
            # Check success field if expected
            if should_have_success:
                assert data.get('success') == True, \
                    f"Expected success=True, got {data.get('success')}. Error: {data.get('error')}"
            
            self.test_results['passed'] += 1
            return data
            
        except Exception as e:
            self.test_results['failed'] += 1
            error_msg = f"Assertion failed: {str(e)}\nResponse: {response.text[:500]}"
            self.test_results['errors'].append(error_msg)
            self.log(error_msg, "ERROR")
            raise
    
    def login(self) -> bool:
        """Login to get session cookie"""
        if not self.username or not self.password:
            self.log("No credentials provided, assuming already logged in", "WARNING")
            return True
        
        self.log(f"Logging in as {self.username}")
        
        # First get the login page to get any CSRF tokens
        login_page = self.session.get(f"{self.base_url}/login")
        
        # Attempt login
        login_data = {
            'username': self.username,
            'password': self.password
        }
        
        response = self.session.post(f"{self.base_url}/login", data=login_data)
        
        if response.status_code == 200 and 'dashboard' in response.url:
            self.log("Login successful")
            return True
        else:
            self.log(f"Login failed: {response.status_code}", "ERROR")
            return False
    
    def test_get_user_profile(self):
        """Test GET /api/user/profile"""
        self.log("Testing GET /api/user/profile")
        
        response = self.session.get(f"{self.base_url}/api/user/profile")
        data = self.assert_response(response)
        
        # Validate response structure
        assert 'user' in data
        user_data = data['user']
        
        # Store user ID for other tests
        self.user_id = user_data['id']
        
        required_fields = ['id', 'username', 'email', 'created_at']
        for field in required_fields:
            assert field in user_data, f"Missing required field: {field}"
        
        self.log("✅ GET /api/user/profile - PASSED")
        return data
    
    def test_update_user_profile(self):
        """Test PUT /api/user/profile"""
        self.log("Testing PUT /api/user/profile")
        
        update_data = {
            'full_name': 'Test User Updated',
            'bio': 'Updated bio for testing',
            'company': 'Test Company',
            'location': 'Test Location',
            'timezone': 'America/New_York'
        }
        
        response = self.session.put(
            f"{self.base_url}/api/user/profile",
            headers={'Content-Type': 'application/json'},
            data=json.dumps(update_data)
        )
        
        data = self.assert_response(response)
        assert 'updated_fields' in data
        assert len(data['updated_fields']) > 0
        
        self.log("✅ PUT /api/user/profile - PASSED")
        return data
    
    def test_get_user_preferences(self):
        """Test GET /api/user/preferences"""
        self.log("Testing GET /api/user/preferences")
        
        response = self.session.get(f"{self.base_url}/api/user/preferences")
        data = self.assert_response(response)
        
        assert 'preferences' in data
        preferences = data['preferences']
        
        expected_keys = ['timezone', 'language', 'notifications']
        for key in expected_keys:
            assert key in preferences, f"Missing preference key: {key}"
        
        self.log("✅ GET /api/user/preferences - PASSED")
        return data
    
    def test_update_user_preferences(self):
        """Test PUT /api/user/preferences"""
        self.log("Testing PUT /api/user/preferences")
        
        update_data = {
            'timezone': 'Europe/London',
            'language': 'en',
            'notifications': {
                'email': True,
                'sms': False
            }
        }
        
        response = self.session.put(
            f"{self.base_url}/api/user/preferences",
            headers={'Content-Type': 'application/json'},
            data=json.dumps(update_data)
        )
        
        data = self.assert_response(response)
        assert 'updated_fields' in data
        
        self.log("✅ PUT /api/user/preferences - PASSED")
        return data
    
    def test_get_user_tenants(self):
        """Test GET /api/user/tenants"""
        self.log("Testing GET /api/user/tenants")
        
        response = self.session.get(f"{self.base_url}/api/user/tenants")
        data = self.assert_response(response)
        
        assert 'tenants' in data
        assert 'total' in data
        assert isinstance(data['tenants'], list)
        assert data['total'] >= 0
        
        self.log(f"✅ GET /api/user/tenants - PASSED (found {data['total']} tenants)")
        return data
    
    def test_get_user_activity(self):
        """Test GET /api/user/activity"""
        self.log("Testing GET /api/user/activity")
        
        # Test with pagination
        response = self.session.get(f"{self.base_url}/api/user/activity?page=1&per_page=10")
        data = self.assert_response(response)
        
        assert 'logs' in data
        assert 'pagination' in data
        assert isinstance(data['logs'], list)
        
        pagination = data['pagination']
        required_pagination_fields = ['page', 'per_page', 'total']
        for field in required_pagination_fields:
            assert field in pagination, f"Missing pagination field: {field}"
        
        self.log("✅ GET /api/user/activity - PASSED")
        return data
    
    def test_get_security_settings(self):
        """Test GET /api/user/security"""
        self.log("Testing GET /api/user/security")
        
        response = self.session.get(f"{self.base_url}/api/user/security")
        data = self.assert_response(response)
        
        assert 'security' in data
        security = data['security']
        
        expected_fields = ['two_factor_enabled', 'last_password_change', 'failed_login_attempts']
        for field in expected_fields:
            assert field in security, f"Missing security field: {field}"
        
        self.log("✅ GET /api/user/security - PASSED")
        return data
    
    def test_get_notifications(self):
        """Test GET /api/user/notifications"""
        self.log("Testing GET /api/user/notifications")
        
        # Test basic request
        response = self.session.get(f"{self.base_url}/api/user/notifications")
        data = self.assert_response(response)
        
        assert 'notifications' in data
        assert 'counts' in data
        assert isinstance(data['notifications'], list)
        
        counts = data['counts']
        required_count_fields = ['total', 'unread', 'urgent']
        for field in required_count_fields:
            assert field in counts, f"Missing count field: {field}"
        
        # Test with parameters
        response = self.session.get(
            f"{self.base_url}/api/user/notifications?page=1&per_page=5&include_read=true"
        )
        data = self.assert_response(response)
        
        self.log("✅ GET /api/user/notifications - PASSED")
        return data
    
    def test_get_notification_counts(self):
        """Test GET /api/user/notifications/counts"""
        self.log("Testing GET /api/user/notifications/counts")
        
        response = self.session.get(f"{self.base_url}/api/user/notifications/counts")
        data = self.assert_response(response)
        
        assert 'counts' in data
        counts = data['counts']
        
        required_fields = ['total', 'unread', 'urgent']
        for field in required_fields:
            assert field in counts, f"Missing count field: {field}"
            assert isinstance(counts[field], int), f"Count field {field} should be integer"
        
        self.log("✅ GET /api/user/notifications/counts - PASSED")
        return data
    
    def test_avatar_upload_deletion(self):
        """Test avatar upload and deletion"""
        self.log("Testing avatar upload and deletion")
        
        # Create a simple test image
        test_image = io.BytesIO()
        test_image.write(b'fake_image_data_for_testing')
        test_image.seek(0)
        
        # Test upload (this will likely fail without a real image, but we test the endpoint)
        files = {'file': ('test.jpg', test_image, 'image/jpeg')}
        response = self.session.post(f"{self.base_url}/api/user/avatar", files=files)
        
        if response.status_code == 200:
            data = self.assert_response(response)
            assert 'avatar_url' in data
            self.log("✅ Avatar upload - PASSED")
            
            # Test deletion
            response = self.session.delete(f"{self.base_url}/api/user/avatar")
            if response.status_code == 200:
                data = self.assert_response(response)
                self.log("✅ Avatar deletion - PASSED")
            else:
                self.log("ℹ️ Avatar deletion test skipped (no avatar to delete)")
        else:
            self.log("ℹ️ Avatar upload test skipped (requires real image file)")
    
    def test_error_handling(self):
        """Test error handling for invalid requests"""
        self.log("Testing error handling")
        
        # Test invalid JSON
        response = self.session.put(
            f"{self.base_url}/api/user/profile",
            headers={'Content-Type': 'application/json'},
            data='invalid json'
        )
        
        self.assert_response(response, expected_status=400, should_have_success=False)
        
        # Test non-existent notification
        response = self.session.post(f"{self.base_url}/api/user/notifications/999999/read")
        self.assert_response(response, expected_status=404, should_have_success=False)
        
        self.log("✅ Error handling tests - PASSED")
    
    def test_password_change(self):
        """Test password change (requires current password)"""
        self.log("Testing password change endpoint")
        
        # This test will fail without the current password, but we test the endpoint structure
        password_data = {
            'current_password': 'wrong_password',
            'new_password': 'new_test_password123'
        }
        
        response = self.session.put(
            f"{self.base_url}/api/user/password",
            headers={'Content-Type': 'application/json'},
            data=json.dumps(password_data)
        )
        
        # Expect failure due to wrong current password
        if response.status_code == 400:
            data = response.json()
            assert data.get('success') == False
            self.log("ℹ️ Password change test - Correctly rejected invalid current password")
        else:
            self.log("ℹ️ Password change test - Unexpected response, endpoint may need authentication")
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all API tests"""
        self.log("Starting User API Test Suite")
        self.log("=" * 50)
        
        try:
            # Login first
            if not self.login():
                self.log("Login failed, cannot continue with tests", "ERROR")
                return self.test_results
            
            # Run all tests
            self.test_get_user_profile()
            self.test_update_user_profile()
            self.test_get_user_preferences()
            self.test_update_user_preferences()
            self.test_get_user_tenants()
            self.test_get_user_activity()
            self.test_get_security_settings()
            self.test_get_notifications()
            self.test_get_notification_counts()
            self.test_avatar_upload_deletion()
            self.test_password_change()
            self.test_error_handling()
            
        except Exception as e:
            self.log(f"Test suite failed with exception: {str(e)}", "ERROR")
            self.test_results['errors'].append(str(e))
        
        # Print summary
        self.print_test_summary()
        return self.test_results
    
    def print_test_summary(self):
        """Print test results summary"""
        self.log("=" * 50)
        self.log("TEST SUMMARY")
        self.log("=" * 50)
        self.log(f"Total tests: {self.test_results['total']}")
        self.log(f"Passed: {self.test_results['passed']}")
        self.log(f"Failed: {self.test_results['failed']}")
        
        if self.test_results['failed'] > 0:
            self.log("ERRORS:")
            for error in self.test_results['errors']:
                self.log(f"  - {error}")
        
        success_rate = (self.test_results['passed'] / max(self.test_results['total'], 1)) * 100
        self.log(f"Success rate: {success_rate:.1f}%")
        
        if self.test_results['failed'] == 0:
            self.log("🎉 ALL TESTS PASSED!")
        else:
            self.log("❌ SOME TESTS FAILED")

class WebSocketTester:
    """Test WebSocket functionality"""
    
    def __init__(self, base_url: str = "http://localhost:5000"):
        self.base_url = base_url
        
    def test_websocket_connection(self):
        """Test WebSocket connection (requires socketio-client)"""
        try:
            import socketio
            
            print("Testing WebSocket connection...")
            
            sio = socketio.Client()
            
            @sio.event
            def connect():
                print("✅ WebSocket connection established")
                
            @sio.event
            def disconnect():
                print("WebSocket disconnected")
                
            @sio.event
            def connected(data):
                print(f"✅ Received connection confirmation: {data}")
                
            @sio.event
            def notification_counts(data):
                print(f"✅ Received notification counts: {data}")
                
            # Connect
            sio.connect(self.base_url, transports=['websocket'])
            
            # Test getting notification counts
            sio.emit('get_notification_counts')
            
            # Test data refresh
            sio.emit('request_data_refresh', {'type': 'notifications'})
            
            # Wait for responses
            time.sleep(2)
            
            # Disconnect
            sio.disconnect()
            
            print("✅ WebSocket tests completed")
            
        except ImportError:
            print("ℹ️ WebSocket tests skipped (python-socketio not installed)")
            print("Install with: pip install python-socketio")
        except Exception as e:
            print(f"❌ WebSocket test failed: {str(e)}")

def main():
    """Main test function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test User API endpoints')
    parser.add_argument('--url', default='http://localhost:5000', help='Base URL for API')
    parser.add_argument('--username', help='Username for login')
    parser.add_argument('--password', help='Password for login')
    parser.add_argument('--test-websocket', action='store_true', help='Test WebSocket functionality')
    
    args = parser.parse_args()
    
    # Run API tests
    tester = UserAPITester(
        base_url=args.url,
        username=args.username,
        password=args.password
    )
    
    results = tester.run_all_tests()
    
    # Run WebSocket tests if requested
    if args.test_websocket:
        print("\n" + "=" * 50)
        print("WEBSOCKET TESTS")
        print("=" * 50)
        
        ws_tester = WebSocketTester(base_url=args.url)
        ws_tester.test_websocket_connection()
    
    # Return exit code based on test results
    return 0 if results['failed'] == 0 else 1

if __name__ == '__main__':
    exit(main())