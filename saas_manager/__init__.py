#!/usr/bin/env python3
"""
SaaS Manager Initialization Script
This script initializes the database, creates default admin user, and sets up initial configuration
Run this when Docker container starts for the first time or restarts
"""

import os
import sys
import logging
import time
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from datetime import datetime
from werkzeug.security import generate_password_hash

# Setup basic logging for initialization
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - INIT - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/app/logs/init.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

class SaaSManagerInitializer:
    """Initialize SaaS Manager with database setup and admin user creation"""
    
    def __init__(self):
        self.db_config = {
            'host': os.environ.get('POSTGRES_HOST', 'postgres'),
            'port': os.environ.get('POSTGRES_PORT', '5432'),
            'user': os.environ.get('POSTGRES_USER', 'odoo_master'),
            'password': os.environ.get('POSTGRES_PASSWORD', 'secure_password_123'),
            'database': 'saas_manager'
        }
        
        self.admin_config = {
            'username': os.environ.get('ADMIN_USERNAME', 'admin'),
            'email': os.environ.get('ADMIN_EMAIL', 'admin@saas-manager.com'),
            'password': os.environ.get('ADMIN_PASSWORD', 'admin123')
        }
        
        self.max_retries = 30
        self.retry_delay = 2
    
    def wait_for_postgres(self):
        """Wait for PostgreSQL to be ready"""
        logger.info("Waiting for PostgreSQL to be ready...")
        
        for attempt in range(self.max_retries):
            try:
                # Try to connect to postgres database first
                conn = psycopg2.connect(
                    host=self.db_config['host'],
                    port=self.db_config['port'],
                    user=self.db_config['user'],
                    password=self.db_config['password'],
                    database='postgres'
                )
                conn.close()
                logger.info("PostgreSQL is ready!")
                return True
                
            except psycopg2.OperationalError as e:
                logger.info(f"Attempt {attempt + 1}/{self.max_retries}: PostgreSQL not ready yet - {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    logger.error("PostgreSQL failed to become ready within timeout")
                    return False
            except Exception as e:
                logger.error(f"Unexpected error waiting for PostgreSQL: {e}")
                return False
        
        return False
    
    def create_saas_manager_database(self):
        """Create the saas_manager database if it doesn't exist"""
        logger.info("Creating saas_manager database if it doesn't exist...")
        
        try:
            # Connect to postgres database to create saas_manager database
            conn = psycopg2.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                database='postgres'
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cursor = conn.cursor()
            
            # Check if database exists
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (self.db_config['database'],))
            if cursor.fetchone():
                logger.info(f"Database {self.db_config['database']} already exists")
            else:
                # Create database
                cursor.execute(f'CREATE DATABASE "{self.db_config["database"]}" OWNER {self.db_config["user"]}')
                cursor.execute(f'GRANT ALL PRIVILEGES ON DATABASE "{self.db_config["database"]}" TO {self.db_config["user"]}')
                logger.info(f"Database {self.db_config['database']} created successfully")
            
            cursor.close()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Failed to create saas_manager database: {e}")
            return False
    
    def initialize_flask_app(self):
        logger.info("Initializing Flask application and database tables...")
        try:
            # Add timeout mechanism
            import signal
            def timeout_handler(signum, frame):
                raise TimeoutError("Flask initialization timed out")
            
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(30)  # 30 second timeout
            
            sys.path.insert(0, '/app')
            from app import app, db
            from models import SaasUser, SubscriptionPlan, WorkerInstance
            
            with app.app_context():
                # Test database connection - SQLAlchemy 2.0+ compatible
                try:
                    # Method 1: Using text() and execute()
                    from sqlalchemy import text
                    with db.engine.connect() as connection:
                        result = connection.execute(text('SELECT 1'))
                        result.fetchone()
                    logger.info("Database connection verified")
                except Exception as e:
                    logger.error(f"Database connection test failed: {e}")
                    # Alternative method - just try to create tables
                    logger.info("Attempting to proceed with table creation...")
                
                # Create tables
                db.create_all()
                logger.info("Database tables created successfully")
                
                # Create default data
                self.create_default_subscription_plans(db, SubscriptionPlan)
                self.create_default_worker_instance(db, WorkerInstance)
                self.create_admin_user(db, SaasUser)
                
                # Commit all changes
                db.session.commit()
                logger.info("Database initialization completed successfully")
                
            signal.alarm(0)  # Cancel timeout
            return True
            
        except TimeoutError:
            logger.error("Flask initialization timed out after 30 seconds")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize Flask app: {e}")
            # More detailed error logging
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def create_default_subscription_plans(self, db, SubscriptionPlan):
        """
        Creates default subscription plans in the database if they don't already exist.
        
        Args:
            db: SQLAlchemy instance
            SubscriptionPlan: SQLAlchemy model class for subscription_plans table
        """
        logger.info("Creating default subscription plans...")
        
        default_plans = [
            {
                'name': 'Basic',
                'price': 10.00,
                'features': {'support': 'email', 'storage': '10GB', 'custom_domain': False},
                'max_users': 5,
                'storage_limit': 1024,  # Added storage_limit
                'is_active': True
            },
            {
                'name': 'Pro',
                'price': 30.00,
                'features': {'support': 'email and chat', 'storage': '50GB', 'custom_domain': True},
                'max_users': 20,
                'storage_limit': 5120,  # Added storage_limit
                'is_active': True
            },
            {
                'name': 'Enterprise',
                'price': 100.00,
                'features': {
                    'support': '24/7 phone',
                    'storage': 'unlimited',
                    'custom_domain': True,
                    'dedicated_manager': True
                },
                'max_users': 1000,  # High number to represent "unlimited"
                'storage_limit': 102400,  # Added storage_limit (100GB)
                'is_active': True
            }
        ]
        
        for plan_data in default_plans:
            # Check if plan already exists by name
            existing_plan = SubscriptionPlan.query.filter_by(name=plan_data['name']).first()
            if not existing_plan:
                # Create new plan if it doesn't exist
                new_plan = SubscriptionPlan(
                    name=plan_data['name'],
                    price=plan_data['price'],
                    features=plan_data['features'],
                    max_users=plan_data['max_users'],
                    storage_limit=plan_data['storage_limit'],  # Added storage_limit
                    is_active=plan_data['is_active'],
                    created_at=datetime.utcnow()  # Explicitly set for clarity
                )
                db.session.add(new_plan)
                logger.info(f"Created subscription plan: {plan_data['name']}")
            else:
                logger.info(f"Subscription plan already exists: {plan_data['name']}")
        
        # Commit all changes to the database
        db.session.commit()
        logger.info("Default subscription plans creation completed.")
    
    def create_default_worker_instance(self, db, WorkerInstance):
        """Create default worker instance"""
        logger.info("Creating default worker instance...")
        
        existing_worker = WorkerInstance.query.filter_by(name='default-worker').first()
        if not existing_worker:
            worker = WorkerInstance(
                name='default-worker',
                container_name='odoo_master',
                port=8069,
                status='running',
                current_tenants=0,
                max_tenants=10,
                last_health_check=datetime.utcnow()
            )
            db.session.add(worker)
            logger.info("Created default worker instance")
        else:
            logger.info("Default worker instance already exists")
    
    def create_admin_user(self, db, SaasUser):
        """Create or update admin user with proper password hash"""
        logger.info("Creating/updating admin user...")
        
        try:
            # Check if admin user exists
            admin = SaasUser.query.filter_by(username=self.admin_config['username']).first()
            
            # Generate proper password hash
            password_hash = generate_password_hash(self.admin_config['password'])
            
            if admin:
                # Update existing admin user
                admin.password_hash = password_hash
                admin.email = self.admin_config['email']
                admin.is_admin = True
                logger.info(f"Updated existing admin user: {self.admin_config['username']}")
            else:
                # Create new admin user
                admin = SaasUser(
                    username=self.admin_config['username'],
                    email=self.admin_config['email'],
                    password_hash=password_hash,
                    is_admin=True,
                    created_at=datetime.utcnow()
                )
                db.session.add(admin)
                logger.info(f"Created new admin user: {self.admin_config['username']}")
            
            # Verify password hash format
            if not password_hash.startswith(('pbkdf2:', 'scrypt:', 'argon2:')):
                logger.warning(f"Password hash format may be invalid: {password_hash[:20]}...")
            else:
                logger.info("Password hash format verified successfully")
                
        except Exception as e:
            logger.error(f"Failed to create/update admin user: {e}")
            raise
    
    def verify_admin_login(self):
        """Verify that admin user can be authenticated"""
        logger.info("Verifying admin user authentication...")
        
        try:
            sys.path.insert(0, '/app')
            from app import app
            from models import SaasUser
            from werkzeug.security import check_password_hash
            
            with app.app_context():
                admin = SaasUser.query.filter_by(username=self.admin_config['username']).first()
                
                if not admin:
                    logger.error("Admin user not found during verification")
                    return False
                
                if not admin.password_hash:
                    logger.error("Admin user has empty password hash")
                    return False
                
                # Test password verification
                is_valid = check_password_hash(admin.password_hash, self.admin_config['password'])
                
                if is_valid:
                    logger.info("Admin user authentication verified successfully")
                    logger.info(f"Admin details - Username: {admin.username}, Email: {admin.email}, Is Admin: {admin.is_admin}")
                    return True
                else:
                    logger.error("Admin user password verification failed")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to verify admin login: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def create_lock_file(self):
        """Create initialization lock file to prevent re-initialization"""
        try:
            lock_file = '/app/logs/.init_complete'
            with open(lock_file, 'w') as f:
                f.write(f"Initialization completed at: {datetime.utcnow().isoformat()}\n")
                f.write(f"Admin user: {self.admin_config['username']}\n")
                f.write(f"Admin email: {self.admin_config['email']}\n")
            logger.info(f"Created initialization lock file: {lock_file}")
        except Exception as e:
            logger.warning(f"Failed to create lock file: {e}")
    
    def is_already_initialized(self):
        """Check if initialization has already been completed"""
        lock_file = '/app/logs/.init_complete'
        if os.path.exists(lock_file):
            logger.info("Initialization lock file found - skipping initialization")
            try:
                with open(lock_file, 'r') as f:
                    logger.info(f"Previous initialization details:\n{f.read()}")
            except:
                pass
            return True
        return False
    
    def run(self, force=False):
        """Run the complete initialization process"""
        logger.info("=" * 60)
        logger.info("STARTING SAAS MANAGER INITIALIZATION")
        logger.info("=" * 60)
        
        # Check if already initialized (unless forced)
        if not force and self.is_already_initialized():
            logger.info("SaaS Manager already initialized. Use force=True to reinitialize.")
            return True
        
        start_time = datetime.utcnow()
        
        try:
            # Step 1: Wait for PostgreSQL
            if not self.wait_for_postgres():
                logger.error("Failed to connect to PostgreSQL")
                return False
            
            # Step 2: Create saas_manager database
            if not self.create_saas_manager_database():
                logger.error("Failed to create saas_manager database")
                return False
            
            # Step 3: Initialize Flask app and create tables
            if not self.initialize_flask_app():
                logger.error("Failed to initialize Flask application")
                return False
            
            # Step 4: Verify admin login
            if not self.verify_admin_login():
                logger.error("Failed to verify admin user login")
                return False
            
            # Step 5: Create lock file
            self.create_lock_file()
            
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            logger.info("=" * 60)
            logger.info("SAAS MANAGER INITIALIZATION COMPLETED SUCCESSFULLY")
            logger.info(f"Duration: {duration:.2f} seconds")
            logger.info(f"Admin Username: {self.admin_config['username']}")
            logger.info(f"Admin Password: {self.admin_config['password']}")
            logger.info("=" * 60)
            
            return True
            
        except Exception as e:
            logger.error(f"Initialization failed with error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

def main():
    """Main initialization function"""
    # Parse command line arguments
    force_init = '--force' in sys.argv
    
    initializer = SaaSManagerInitializer()
    success = initializer.run(force=force_init)
    
    if success:
        logger.info("Initialization completed successfully")
        sys.exit(0)
    else:
        logger.error("Initialization failed")
        sys.exit(1)

if __name__ == "__main__":
    main()