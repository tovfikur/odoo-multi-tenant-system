#!/usr/bin/env python3
"""
Database migration script to add password reset token fields to saas_users table
"""

import os
import sys
import psycopg2
from datetime import datetime

def add_reset_token_fields():
    """Add reset_token and reset_token_expires columns to saas_users table"""
    
    # Database connection parameters
    DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://odoo_master:secure_password_123@postgres:5432/saas_manager')
    
    # Parse the DATABASE_URL for Docker environment
    if DATABASE_URL.startswith('postgresql://'):
        # Extract connection parameters
        import urllib.parse
        parsed = urllib.parse.urlparse(DATABASE_URL)
        db_params = {
            'host': parsed.hostname or 'localhost',
            'port': parsed.port or 5432,
            'user': parsed.username,
            'password': parsed.password,
            'database': parsed.path[1:]  # Remove leading slash
        }
    else:
        # Fallback for direct connection
        db_params = {
            'host': 'localhost',
            'port': 5432,
            'user': 'odoo_master',
            'password': 'secure_password_123',
            'database': 'saas_manager'
        }
    
    try:
        # Connect to database
        print("Connecting to database...")
        conn = psycopg2.connect(**db_params)
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='saas_users' 
            AND column_name IN ('reset_token', 'reset_token_expires');
        """)
        
        existing_columns = [row[0] for row in cursor.fetchall()]
        
        # Add reset_token column if it doesn't exist
        if 'reset_token' not in existing_columns:
            print("Adding reset_token column...")
            cursor.execute("ALTER TABLE saas_users ADD COLUMN reset_token VARCHAR(100);")
        else:
            print("reset_token column already exists")
            
        # Add reset_token_expires column if it doesn't exist  
        if 'reset_token_expires' not in existing_columns:
            print("Adding reset_token_expires column...")
            cursor.execute("ALTER TABLE saas_users ADD COLUMN reset_token_expires TIMESTAMP;")
        else:
            print("reset_token_expires column already exists")
        
        # Commit changes
        conn.commit()
        print("✅ Database migration completed successfully!")
        
    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        if conn:
            conn.rollback()
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        print("Database connection closed.")

if __name__ == "__main__":
    print("🔄 Starting password reset token fields migration...")
    print(f"Timestamp: {datetime.now()}")
    add_reset_token_fields()
