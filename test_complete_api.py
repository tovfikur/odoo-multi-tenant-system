#!/usr/bin/env python3
"""
Complete API Test Suite
Comprehensive testing for all mobile app API endpoints
"""

import requests
import json
import time
import io
from datetime import datetime
from typing import Dict, List, Any

class CompleteAPITester:
    """Complete test suite for all API endpoints"""
    
    def __init__(self, base_url: str = "http://localhost:5000", username: str = None, password: str = None):
        self.base_url = base_url
        self.session = requests.Session()
        self.username = username
        self.password = password
        self.user_id = None
        self.test_tenant_id = None
        self.test_ticket_id = None
        
        # Test results
        self.test_results = {
            'total': 0,
            'passed': 0,
            'failed': 0,
            'skipped': 0,
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
    
    def skip_test(self, reason: str):
        """Skip a test"""
        self.test_results['skipped'] += 1
        self.log(f"SKIPPED: {reason}", "WARNING")
    
    # ================= PUBLIC API TESTS =================
    
    def test_public_registration(self):
        """Test user registration via public API"""
        self.log("Testing POST /api/public/register")
        
        import secrets
        unique_suffix = secrets.token_hex(4)
        
        registration_data = {
            'username': f'testuser_{unique_suffix}',
            'email': f'test_{unique_suffix}@example.com',
            'password': 'TestPassword123',
            'full_name': 'Test User',
            'company': 'Test Company',
            'phone': '+1-555-0123'
        }
        
        response = self.session.post(
            f"{self.base_url}/api/public/register",
            headers={'Content-Type': 'application/json'},
            data=json.dumps(registration_data)
        )
        
        data = self.assert_response(response, expected_status=201)
        assert 'user' in data
        assert data['user']['username'] == registration_data['username']
        
        self.log("✅ POST /api/public/register - PASSED")
        return data['user']
    
    def test_public_login(self):
        """Test user login via public API"""
        self.log("Testing POST /api/public/login")
        
        # First register a test user if we don't have credentials
        if not self.username:
            test_user = self.test_public_registration()
            login_data = {
                'username': test_user['username'],
                'password': 'TestPassword123'
            }
        else:
            login_data = {
                'username': self.username,
                'password': self.password
            }
        
        response = self.session.post(
            f"{self.base_url}/api/public/login",
            headers={'Content-Type': 'application/json'},
            data=json.dumps(login_data)
        )
        
        data = self.assert_response(response)
        assert 'user' in data
        
        # Store user ID for other tests
        self.user_id = data['user']['id']
        
        self.log("✅ POST /api/public/login - PASSED")
        return data
    
    def test_check_authentication(self):
        """Test authentication check"""
        self.log("Testing GET /api/public/check-auth")
        
        response = self.session.get(f"{self.base_url}/api/public/check-auth")
        data = self.assert_response(response)
        
        assert 'authenticated' in data
        
        self.log("✅ GET /api/public/check-auth - PASSED")
        return data
    
    def test_username_availability(self):
        """Test username availability check"""
        self.log("Testing POST /api/public/check-username")
        
        # Test with likely available username
        test_data = {'username': f'testuser_{int(time.time())}'}
        
        response = self.session.post(
            f"{self.base_url}/api/public/check-username",
            headers={'Content-Type': 'application/json'},
            data=json.dumps(test_data)
        )
        
        data = self.assert_response(response)
        assert 'available' in data
        
        self.log("✅ POST /api/public/check-username - PASSED")
        return data
    
    def test_subdomain_validation(self):
        """Test subdomain validation"""
        self.log("Testing POST /api/public/validate-subdomain")
        
        # Test with likely available subdomain
        test_data = {'subdomain': f'testcompany{int(time.time())}'}
        
        response = self.session.post(
            f"{self.base_url}/api/public/validate-subdomain",
            headers={'Content-Type': 'application/json'},
            data=json.dumps(test_data)
        )
        
        data = self.assert_response(response)
        assert 'available' in data
        assert 'valid' in data
        
        self.log("✅ POST /api/public/validate-subdomain - PASSED")
        return data
    
    def test_system_status(self):
        """Test system status endpoint"""
        self.log("Testing GET /api/public/system-status")
        
        response = self.session.get(f"{self.base_url}/api/public/system-status")
        data = self.assert_response(response)
        
        assert 'system_status' in data
        system_status = data['system_status']
        assert 'status' in system_status
        assert 'total_active_tenants' in system_status
        assert 'total_active_users' in system_status
        
        self.log("✅ GET /api/public/system-status - PASSED")
        return data
    
    # ================= TENANT API TESTS =================
    
    def test_create_tenant(self):
        """Test tenant creation"""
        self.log("Testing POST /api/tenant/create")
        
        if not self.user_id:
            self.test_public_login()
        
        import secrets
        unique_suffix = secrets.token_hex(4)
        
        tenant_data = {
            'name': f'Test Company {unique_suffix}',
            'subdomain': f'testco{unique_suffix}',
            'plan': 'basic',
            'admin_username': 'admin',
            'admin_password': 'SecureAdminPass123',
            'modules': ['crm', 'sales']
        }
        
        response = self.session.post(
            f"{self.base_url}/api/tenant/create",
            headers={'Content-Type': 'application/json'},
            data=json.dumps(tenant_data)
        )
        
        data = self.assert_response(response, expected_status=201)
        assert 'tenant' in data
        
        # Store tenant ID for other tests
        self.test_tenant_id = data['tenant']['id']
        
        self.log("✅ POST /api/tenant/create - PASSED")
        return data
    
    def test_get_tenant_status(self):
        """Test getting tenant status"""
        if not self.test_tenant_id:
            self.test_create_tenant()
        
        self.log(f"Testing GET /api/tenant/{self.test_tenant_id}/status")
        
        response = self.session.get(f"{self.base_url}/api/tenant/{self.test_tenant_id}/status")
        data = self.assert_response(response)
        
        assert 'status' in data
        status = data['status']
        assert 'tenant_id' in status
        assert 'health_status' in status
        
        self.log("✅ GET /api/tenant/{tenant_id}/status - PASSED")
        return data
    
    def test_tenant_backup(self):
        """Test tenant backup creation"""
        if not self.test_tenant_id:
            self.test_create_tenant()
        
        self.log(f"Testing POST /api/tenant/{self.test_tenant_id}/backup")
        
        response = self.session.post(f"{self.base_url}/api/tenant/{self.test_tenant_id}/backup")
        data = self.assert_response(response)
        
        assert 'backup_info' in data
        backup_info = data['backup_info']
        assert 'tenant_id' in backup_info
        assert 'created_at' in backup_info
        
        self.log("✅ POST /api/tenant/{tenant_id}/backup - PASSED")
        return data
    
    def test_get_tenant_users(self):
        """Test getting tenant users"""
        if not self.test_tenant_id:
            self.test_create_tenant()
        
        self.log(f"Testing GET /api/tenant/{self.test_tenant_id}/users")
        
        response = self.session.get(f"{self.base_url}/api/tenant/{self.test_tenant_id}/users")
        data = self.assert_response(response)
        
        assert 'users' in data
        assert 'total' in data
        assert isinstance(data['users'], list)
        
        self.log("✅ GET /api/tenant/{tenant_id}/users - PASSED")
        return data
    
    # ================= BILLING API TESTS =================
    
    def test_get_billing_plans(self):
        """Test getting billing plans"""
        self.log("Testing GET /api/billing/plans")
        
        response = self.session.get(f"{self.base_url}/api/billing/plans")
        data = self.assert_response(response)
        
        assert 'plans' in data
        plans = data['plans']
        
        # Check that basic plans exist
        expected_plans = ['free', 'basic', 'professional', 'enterprise']
        for plan in expected_plans:
            assert plan in plans, f"Missing plan: {plan}"
            assert 'name' in plans[plan]
            assert 'price' in plans[plan]
            assert 'features' in plans[plan]
        
        self.log("✅ GET /api/billing/plans - PASSED")
        return data
    
    def test_calculate_billing(self):
        """Test billing calculation"""
        self.log("Testing POST /api/billing/calculate")
        
        calculation_data = {
            'plan_id': 'basic',
            'billing_cycle': 'monthly',
            'additional_users': 5,
            'additional_storage': 10
        }
        
        response = self.session.post(
            f"{self.base_url}/api/billing/calculate",
            headers={'Content-Type': 'application/json'},
            data=json.dumps(calculation_data)
        )
        
        data = self.assert_response(response)
        assert 'calculation' in data
        
        calc = data['calculation']
        assert 'base_price' in calc
        assert 'total' in calc
        assert 'currency' in calc
        
        self.log("✅ POST /api/billing/calculate - PASSED")
        return data
    
    def test_get_tenant_billing(self):
        """Test getting tenant billing information"""
        if not self.test_tenant_id:
            self.test_create_tenant()
        
        self.log(f"Testing GET /api/billing/tenant/{self.test_tenant_id}")
        
        response = self.session.get(f"{self.base_url}/api/billing/tenant/{self.test_tenant_id}")
        data = self.assert_response(response)
        
        assert 'billing_info' in data
        billing = data['billing_info']
        assert 'current_plan' in billing
        assert 'usage' in billing
        assert 'billing' in billing
        
        self.log("✅ GET /api/billing/tenant/{tenant_id} - PASSED")
        return data
    
    def test_get_payment_methods(self):
        """Test getting payment methods"""
        self.log("Testing GET /api/billing/payment-methods")
        
        response = self.session.get(f"{self.base_url}/api/billing/payment-methods")
        data = self.assert_response(response)
        
        assert 'payment_methods' in data
        assert isinstance(data['payment_methods'], list)
        
        self.log("✅ GET /api/billing/payment-methods - PASSED")
        return data
    
    def test_get_invoices(self):
        """Test getting billing invoices"""
        self.log("Testing GET /api/billing/invoices")
        
        response = self.session.get(f"{self.base_url}/api/billing/invoices")
        data = self.assert_response(response)
        
        assert 'invoices' in data
        assert 'total' in data
        assert isinstance(data['invoices'], list)
        
        self.log("✅ GET /api/billing/invoices - PASSED")
        return data
    
    # ================= SUPPORT API TESTS =================
    
    def test_get_support_categories(self):
        """Test getting support categories"""
        self.log("Testing GET /api/support/categories")
        
        response = self.session.get(f"{self.base_url}/api/support/categories")
        data = self.assert_response(response)
        
        assert 'categories' in data
        categories = data['categories']
        assert isinstance(categories, list)
        assert len(categories) > 0
        
        # Check category structure
        for category in categories:
            assert 'id' in category
            assert 'name' in category
        
        self.log("✅ GET /api/support/categories - PASSED")
        return data
    
    def test_get_support_priorities(self):
        """Test getting support priorities"""
        self.log("Testing GET /api/support/priorities")
        
        response = self.session.get(f"{self.base_url}/api/support/priorities")
        data = self.assert_response(response)
        
        assert 'priorities' in data
        priorities = data['priorities']
        assert isinstance(priorities, list)
        
        self.log("✅ GET /api/support/priorities - PASSED")
        return data
    
    def test_create_support_ticket(self):
        """Test creating support ticket"""
        self.log("Testing POST /api/support/tickets")
        
        if not self.user_id:
            self.test_public_login()
        
        ticket_data = {
            'subject': 'Test ticket from API',
            'description': 'This is a test ticket created via API for testing purposes.',
            'category': 'technical',
            'priority': 'medium',
            'tenant_id': self.test_tenant_id,
            'metadata': {
                'test': True,
                'api_version': '1.0'
            }
        }
        
        response = self.session.post(
            f"{self.base_url}/api/support/tickets",
            headers={'Content-Type': 'application/json'},
            data=json.dumps(ticket_data)
        )
        
        data = self.assert_response(response, expected_status=201)
        assert 'ticket' in data
        
        ticket = data['ticket']
        assert 'id' in ticket
        assert 'ticket_number' in ticket
        assert ticket['subject'] == ticket_data['subject']
        
        # Store ticket ID for other tests
        self.test_ticket_id = ticket['id']
        
        self.log("✅ POST /api/support/tickets - PASSED")
        return data
    
    def test_get_support_tickets(self):
        """Test getting support tickets"""
        self.log("Testing GET /api/support/tickets")
        
        if not self.user_id:
            self.test_public_login()
        
        response = self.session.get(f"{self.base_url}/api/support/tickets")
        data = self.assert_response(response)
        
        assert 'tickets' in data
        assert 'pagination' in data
        assert isinstance(data['tickets'], list)
        
        self.log("✅ GET /api/support/tickets - PASSED")
        return data
    
    def test_get_specific_support_ticket(self):
        """Test getting specific support ticket"""
        if not self.test_ticket_id:
            self.test_create_support_ticket()
        
        self.log(f"Testing GET /api/support/tickets/{self.test_ticket_id}")
        
        response = self.session.get(f"{self.base_url}/api/support/tickets/{self.test_ticket_id}")
        data = self.assert_response(response)
        
        assert 'ticket' in data
        ticket = data['ticket']
        assert 'id' in ticket
        assert 'messages' in ticket
        
        self.log("✅ GET /api/support/tickets/{ticket_id} - PASSED")
        return data
    
    def test_add_ticket_message(self):
        """Test adding message to support ticket"""
        if not self.test_ticket_id:
            self.test_create_support_ticket()
        
        self.log(f"Testing POST /api/support/tickets/{self.test_ticket_id}/messages")
        
        message_data = {
            'message': 'This is a follow-up message added via API.',
            'attachments': []
        }
        
        response = self.session.post(
            f"{self.base_url}/api/support/tickets/{self.test_ticket_id}/messages",
            headers={'Content-Type': 'application/json'},
            data=json.dumps(message_data)
        )
        
        data = self.assert_response(response)
        assert 'ticket_message' in data
        
        self.log("✅ POST /api/support/tickets/{ticket_id}/messages - PASSED")
        return data
    
    def test_get_chat_availability(self):
        """Test getting chat availability"""
        self.log("Testing GET /api/support/chat/available")
        
        response = self.session.get(f"{self.base_url}/api/support/chat/available")
        data = self.assert_response(response)
        
        assert 'available' in data
        assert 'business_hours' in data
        
        self.log("✅ GET /api/support/chat/available - PASSED")
        return data
    
    def test_get_knowledge_base(self):
        """Test getting knowledge base"""
        self.log("Testing GET /api/support/knowledge-base")
        
        response = self.session.get(f"{self.base_url}/api/support/knowledge-base")
        data = self.assert_response(response)
        
        assert 'articles' in data
        assert 'total' in data
        assert isinstance(data['articles'], list)
        
        self.log("✅ GET /api/support/knowledge-base - PASSED")
        return data
    
    def test_get_support_stats(self):
        """Test getting support statistics"""
        self.log("Testing GET /api/support/stats")
        
        response = self.session.get(f"{self.base_url}/api/support/stats")
        data = self.assert_response(response)
        
        assert 'stats' in data
        stats = data['stats']
        assert 'total_tickets' in stats
        assert 'open_tickets' in stats
        
        self.log("✅ GET /api/support/stats - PASSED")
        return data
    
    # ================= NOTIFICATION API TESTS =================
    
    def test_get_notifications(self):
        """Test getting user notifications"""
        self.log("Testing GET /api/user/notifications")
        
        if not self.user_id:
            self.test_public_login()
        
        response = self.session.get(f"{self.base_url}/api/user/notifications")
        data = self.assert_response(response)
        
        assert 'notifications' in data
        assert 'counts' in data
        assert isinstance(data['notifications'], list)
        
        counts = data['counts']
        assert 'total' in counts
        assert 'unread' in counts
        assert 'urgent' in counts
        
        self.log("✅ GET /api/user/notifications - PASSED")
        return data
    
    def test_get_notification_counts(self):
        """Test getting notification counts"""
        self.log("Testing GET /api/user/notifications/counts")
        
        response = self.session.get(f"{self.base_url}/api/user/notifications/counts")
        data = self.assert_response(response)
        
        assert 'counts' in data
        counts = data['counts']
        assert 'total' in counts
        assert 'unread' in counts
        assert 'urgent' in counts
        
        self.log("✅ GET /api/user/notifications/counts - PASSED")
        return data
    
    # ================= USER PROFILE API TESTS =================
    
    def test_get_user_profile(self):
        """Test getting user profile"""
        self.log("Testing GET /api/user/profile")
        
        if not self.user_id:
            self.test_public_login()
        
        response = self.session.get(f"{self.base_url}/api/user/profile")
        data = self.assert_response(response)
        
        assert 'user' in data
        user = data['user']
        assert 'id' in user
        assert 'username' in user
        assert 'email' in user
        
        self.log("✅ GET /api/user/profile - PASSED")
        return data
    
    def test_get_user_tenants(self):
        """Test getting user's tenants"""
        self.log("Testing GET /api/user/tenants")
        
        response = self.session.get(f"{self.base_url}/api/user/tenants")
        data = self.assert_response(response)
        
        assert 'tenants' in data
        assert 'total' in data
        assert isinstance(data['tenants'], list)
        
        self.log("✅ GET /api/user/tenants - PASSED")
        return data
    
    def test_get_user_preferences(self):
        """Test getting user preferences"""
        self.log("Testing GET /api/user/preferences")
        
        response = self.session.get(f"{self.base_url}/api/user/preferences")
        data = self.assert_response(response)
        
        assert 'preferences' in data
        prefs = data['preferences']
        assert 'timezone' in prefs
        assert 'language' in prefs
        assert 'notifications' in prefs
        
        self.log("✅ GET /api/user/preferences - PASSED")
        return data
    
    def test_get_user_security(self):
        """Test getting user security settings"""
        self.log("Testing GET /api/user/security")
        
        response = self.session.get(f"{self.base_url}/api/user/security")
        data = self.assert_response(response)
        
        assert 'security' in data
        security = data['security']
        assert 'two_factor_enabled' in security
        assert 'failed_login_attempts' in security
        
        self.log("✅ GET /api/user/security - PASSED")
        return data
    
    def test_get_user_activity(self):
        """Test getting user activity logs"""
        self.log("Testing GET /api/user/activity")
        
        response = self.session.get(f"{self.base_url}/api/user/activity")
        data = self.assert_response(response)
        
        assert 'logs' in data
        assert 'pagination' in data
        assert isinstance(data['logs'], list)
        
        self.log("✅ GET /api/user/activity - PASSED")
        return data
    
    # ================= ERROR HANDLING TESTS =================
    
    def test_error_handling(self):
        """Test API error handling"""
        self.log("Testing error handling")
        
        # Test invalid JSON
        response = self.session.post(
            f"{self.base_url}/api/public/register",
            headers={'Content-Type': 'application/json'},
            data='invalid json'
        )
        self.assert_response(response, expected_status=400, should_have_success=False)
        
        # Test missing authentication
        self.session.cookies.clear()  # Clear authentication
        response = self.session.get(f"{self.base_url}/api/user/profile")
        self.assert_response(response, expected_status=401, should_have_success=False)
        
        # Test non-existent resource
        response = self.session.get(f"{self.base_url}/api/support/tickets/999999")
        # This might be 401 if not authenticated, or 404 if authenticated
        assert response.status_code in [401, 404]
        
        self.log("✅ Error handling tests - PASSED")
    
    # ================= MAIN TEST RUNNER =================
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all API tests"""
        self.log("Starting Complete API Test Suite")
        self.log("=" * 60)
        
        try:
            # Public API Tests
            self.log("Testing Public APIs...")
            self.test_public_registration()
            self.test_public_login()
            self.test_check_authentication()
            self.test_username_availability()
            self.test_subdomain_validation()
            self.test_system_status()
            
            # Tenant API Tests
            self.log("Testing Tenant APIs...")
            self.test_create_tenant()
            self.test_get_tenant_status()
            self.test_tenant_backup()
            self.test_get_tenant_users()
            
            # Billing API Tests
            self.log("Testing Billing APIs...")
            self.test_get_billing_plans()
            self.test_calculate_billing()
            self.test_get_tenant_billing()
            self.test_get_payment_methods()
            self.test_get_invoices()
            
            # Support API Tests
            self.log("Testing Support APIs...")
            self.test_get_support_categories()
            self.test_get_support_priorities()
            self.test_create_support_ticket()
            self.test_get_support_tickets()
            self.test_get_specific_support_ticket()
            self.test_add_ticket_message()
            self.test_get_chat_availability()
            self.test_get_knowledge_base()
            self.test_get_support_stats()
            
            # User Profile API Tests
            self.log("Testing User Profile APIs...")
            self.test_get_user_profile()
            self.test_get_user_tenants()
            self.test_get_user_preferences()
            self.test_get_user_security()
            self.test_get_user_activity()
            
            # Notification API Tests
            self.log("Testing Notification APIs...")
            self.test_get_notifications()
            self.test_get_notification_counts()
            
            # Error Handling Tests
            self.log("Testing Error Handling...")
            self.test_error_handling()
            
        except Exception as e:
            self.log(f"Test suite failed with exception: {str(e)}", "ERROR")
            self.test_results['errors'].append(str(e))
        
        # Print summary
        self.print_test_summary()
        return self.test_results
    
    def print_test_summary(self):
        """Print test results summary"""
        self.log("=" * 60)
        self.log("COMPLETE API TEST SUMMARY")
        self.log("=" * 60)
        self.log(f"Total tests: {self.test_results['total']}")
        self.log(f"Passed: {self.test_results['passed']}")
        self.log(f"Failed: {self.test_results['failed']}")
        self.log(f"Skipped: {self.test_results['skipped']}")
        
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

def main():
    """Main test function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test Complete API endpoints')
    parser.add_argument('--url', default='http://localhost:5000', help='Base URL for API')
    parser.add_argument('--username', help='Username for login')
    parser.add_argument('--password', help='Password for login')
    
    args = parser.parse_args()
    
    # Run complete API tests
    tester = CompleteAPITester(
        base_url=args.url,
        username=args.username,
        password=args.password
    )
    
    results = tester.run_all_tests()
    
    # Return exit code based on test results
    return 0 if results['failed'] == 0 else 1

if __name__ == '__main__':
    exit(main())