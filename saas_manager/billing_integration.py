# Billing System Integration Guide
"""
This file shows how to integrate the billing system with your main Flask application.

INTEGRATION STEPS:

1. Import and register the billing blueprint
2. Start the background scheduler
3. Add required dependencies
4. Run database migration
5. Configure cron job endpoint

"""

# Step 1: Add to your main Flask app (app.py or wherever you create your Flask app)
"""
from billing_routes import billing_bp
from cron_setup import start_billing_scheduler

# Register the billing blueprint
app.register_blueprint(billing_bp)

# Start the billing scheduler (add this after app creation)
with app.app_context():
    start_billing_scheduler()
"""

# Step 2: Add these dependencies to your requirements.txt
REQUIRED_DEPENDENCIES = """
schedule==1.2.0
"""

# Step 3: Example of how to integrate with your existing app structure
def integrate_billing_system(app):
    """
    Integration function to add billing system to existing Flask app
    
    Args:
        app: Flask application instance
    """
    
    # Import billing components
    from billing_routes import billing_bp
    from cron_setup import start_billing_scheduler
    
    # Register blueprint
    app.register_blueprint(billing_bp)
    
    # Start scheduler in app context
    with app.app_context():
        start_billing_scheduler()
    
    print("✅ Billing system integrated successfully")

# Step 4: Environment variables to add to your .env file
ENVIRONMENT_VARIABLES = """
# Billing System Configuration
BILLING_ENABLED=true
DEFAULT_PANEL_PRICE=50.00
BILLING_CURRENCY=USD
CRON_TOKEN=your-secure-random-token-here

# Payment Gateway (if using external gateway)
STRIPE_PUBLIC_KEY=pk_test_...
STRIPE_SECRET_KEY=sk_test_...
PAYPAL_CLIENT_ID=your_paypal_client_id
PAYPAL_CLIENT_SECRET=your_paypal_client_secret
"""

# Step 5: Cron job setup for production (optional - scheduler handles this automatically)
CRON_JOB_SETUP = """
# Add this to your server's crontab for backup/redundancy
# This will trigger hourly tracking via HTTP endpoint

# Edit crontab: crontab -e
# Add this line (adjust URL and token):
0 * * * * curl -X POST -H "X-Cron-Token: your-secure-token" http://localhost:5000/billing/cron/hourly-tracking

# For testing, run every 5 minutes:
*/5 * * * * curl -X POST -H "X-Cron-Token: your-secure-token" http://localhost:5000/billing/cron/hourly-tracking
"""

# Step 6: Database migration commands
DATABASE_MIGRATION_COMMANDS = """
# Run these commands to set up the billing system database:

# 1. Run the migration script
python database_migration.py

# 2. Or manually create tables in Python shell:
from app import app
from db import db
from models import *

with app.app_context():
    db.create_all()
    print("Tables created successfully")
"""

# Step 7: Testing the system
TESTING_GUIDE = """
# Testing the billing system:

1. Create a test tenant
2. Check billing info endpoint: GET /billing/panel/{tenant_id}/info
3. Manually trigger hourly tracking: POST /billing/cron/hourly-tracking
4. Test payment flow: GET /billing/panel/{tenant_id}/payment
5. Check admin logs: GET /billing/admin/logs

# Python testing script:
from billing_service import BillingService

billing_service = BillingService()

# Test creating a billing cycle
cycle = billing_service.create_billing_cycle(tenant_id=1)

# Test manual usage tracking
billing_service.track_hourly_usage()

# Test getting billing info
info = billing_service.get_tenant_billing_info(tenant_id=1)
print(info)
"""

if __name__ == "__main__":
    print("🚀 Billing System Integration Guide")
    print("=" * 50)
    
    print("\n📋 Required Dependencies:")
    print(REQUIRED_DEPENDENCIES)
    
    print("\n🔧 Environment Variables:")
    print(ENVIRONMENT_VARIABLES)
    
    print("\n⏰ Cron Job Setup:")
    print(CRON_JOB_SETUP)
    
    print("\n🗃️  Database Migration:")
    print(DATABASE_MIGRATION_COMMANDS)
    
    print("\n🧪 Testing Guide:")
    print(TESTING_GUIDE)
    
    print("\n✅ Integration complete! Check the billing system documentation for more details.")
