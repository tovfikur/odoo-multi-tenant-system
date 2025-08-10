#!/usr/bin/env python3
"""
Database migration script to add user notifications table
"""

import os
import sys
from datetime import datetime

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app import app, db
    from models import SaasUser
    from user_notifications import UserNotification
    
    def migrate_notifications():
        """Create the user notifications table"""
        print("🔄 Starting user notifications migration...")
        
        with app.app_context():
            try:
                # Create the user_notifications table
                db.create_all()
                
                print("✅ User notifications table created successfully")
                
                # Check if table exists and show structure
                inspector = db.inspect(db.engine)
                if 'user_notifications' in inspector.get_table_names():
                    columns = inspector.get_columns('user_notifications')
                    print(f"📋 Table structure ({len(columns)} columns):")
                    for col in columns:
                        print(f"  - {col['name']}: {col['type']}")
                
                print("🎉 Migration completed successfully!")
                
            except Exception as e:
                print(f"❌ Migration failed: {str(e)}")
                raise
    
    if __name__ == "__main__":
        migrate_notifications()
        
except ImportError as e:
    print(f"❌ Import error: {str(e)}")
    print("Make sure you're running this from the saas_manager directory")
    sys.exit(1)