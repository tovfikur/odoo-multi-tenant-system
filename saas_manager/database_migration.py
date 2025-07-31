# Database Migration for Billing System
from flask import Flask
from flask_migrate import Migrate
from db import db
from models import *  # Import all models including new billing models

def create_migration_app():
    """Create Flask app for migration purposes"""
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://username:password@localhost/saas_manager'  # Update with your DB config
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(app)
    migrate = Migrate(app, db)
    
    return app, migrate

def create_billing_tables():
    """Create billing system tables"""
    try:
        # Create all tables
        db.create_all()
        print("✅ Successfully created billing system tables:")
        print("   - billing_cycles")
        print("   - usage_tracking")
        print("   - payment_history") 
        print("   - billing_notifications")
        
    except Exception as e:
        print(f"❌ Error creating billing tables: {str(e)}")
        raise

def migrate_existing_tenants():
    """Create initial billing cycles for existing tenants"""
    try:
        from billing_service import BillingService
        billing_service = BillingService()
        
        # Get all existing tenants
        tenants = Tenant.query.all()
        
        for tenant in tenants:
            # Check if tenant already has a billing cycle
            existing_cycle = BillingCycle.query.filter_by(tenant_id=tenant.id).first()
            
            if not existing_cycle:
                # Create initial billing cycle
                billing_service.create_billing_cycle(tenant.id)
                print(f"✅ Created billing cycle for tenant: {tenant.name}")
            else:
                print(f"ℹ️  Billing cycle already exists for tenant: {tenant.name}")
        
        print(f"✅ Successfully processed {len(tenants)} tenants")
        
    except Exception as e:
        print(f"❌ Error migrating existing tenants: {str(e)}")
        raise

def add_billing_system_settings():
    """Add billing system settings to database"""
    try:
        settings = [
            {
                'key': 'billing_enabled',
                'value': 'true',
                'value_type': 'bool',
                'description': 'Enable usage-based billing system',
                'category': 'billing'
            },
            {
                'key': 'default_billing_hours',
                'value': '360',
                'value_type': 'int',
                'description': 'Default hours per billing cycle (30 days * 12 hours)',
                'category': 'billing'
            },
            {
                'key': 'billing_reminder_threshold',
                'value': '84',
                'value_type': 'int',
                'description': 'Hours remaining when to send reminder (7 days * 12 hours)',
                'category': 'billing'
            },
            {
                'key': 'default_panel_price',
                'value': '50.00',
                'value_type': 'float',
                'description': 'Default price for panel renewal',
                'category': 'billing'
            },
            {
                'key': 'billing_currency',
                'value': 'USD',
                'value_type': 'string',
                'description': 'Default currency for billing',
                'category': 'billing'
            }
        ]
        
        for setting_data in settings:
            # Check if setting already exists
            existing = SystemSetting.query.filter_by(key=setting_data['key']).first()
            
            if not existing:
                setting = SystemSetting(**setting_data)
                db.session.add(setting)
                print(f"✅ Added billing setting: {setting_data['key']}")
            else:
                print(f"ℹ️  Setting already exists: {setting_data['key']}")
        
        db.session.commit()
        print("✅ Successfully added billing system settings")
        
    except Exception as e:
        print(f"❌ Error adding billing settings: {str(e)}")
        db.session.rollback()
        raise

if __name__ == "__main__":
    print("🚀 Starting billing system database migration...")
    
    # Create Flask app context
    app, migrate = create_migration_app()
    
    with app.app_context():
        try:
            # Step 1: Create billing tables
            print("\n📋 Step 1: Creating billing system tables...")
            create_billing_tables()
            
            # Step 2: Migrate existing tenants
            print("\n👥 Step 2: Migrating existing tenants...")
            migrate_existing_tenants()
            
            # Step 3: Add system settings
            print("\n⚙️  Step 3: Adding billing system settings...")
            add_billing_system_settings()
            
            print("\n🎉 Billing system migration completed successfully!")
            print("\n📝 Next steps:")
            print("   1. Register billing routes in your main Flask app")
            print("   2. Start the billing scheduler (cron_setup.py)")
            print("   3. Configure payment gateway settings")
            print("   4. Test the billing system with a test tenant")
            
        except Exception as e:
            print(f"\n💥 Migration failed: {str(e)}")
            print("Please check the error and try again.")
