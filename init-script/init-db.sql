-- Initialize databases for Odoo SaaS system
-- This script runs when PostgreSQL container starts for the first time

-- Ensure the odoo_master user has proper permissions
-- Note: The user is already created by POSTGRES_USER environment variable
DO $$
BEGIN
   -- Grant necessary permissions to existing user
   ALTER USER odoo_master CREATEDB;
   ALTER USER odoo_master WITH SUPERUSER;
   -- Ensure password matches environment variable
   ALTER USER odoo_master WITH PASSWORD 'secure_password_123';
   
   RAISE NOTICE 'User odoo_master configured successfully';
EXCEPTION
   WHEN OTHERS THEN
      -- Handle any errors gracefully
      RAISE NOTICE 'User already configured or error occurred: %', SQLERRM;
END
$$;

-- Create databases only if they don't exist
DO $$
BEGIN
    -- Create odoo_master database if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'odoo_master') THEN
        RAISE NOTICE 'Creating odoo_master database';
        PERFORM dblink_exec('host=localhost port=5432 dbname=postgres user=odoo_master password=secure_password_123', 
                           'CREATE DATABASE odoo_master OWNER odoo_master');
    ELSE
        RAISE NOTICE 'Database odoo_master already exists';
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Error or database already exists: %', SQLERRM;
END
$$;

-- Create databases using direct CREATE statements (this will fail if they exist, but that's OK)
CREATE DATABASE odoo_master OWNER odoo_master;
CREATE DATABASE saas_manager OWNER odoo_master;

-- Grant permissions to odoo_master user for all databases
GRANT ALL PRIVILEGES ON DATABASE odoo_master TO odoo_master;
GRANT ALL PRIVILEGES ON DATABASE saas_manager TO odoo_master;

-- Connect to odoo_master database and create necessary extensions
\c odoo_master;
CREATE EXTENSION IF NOT EXISTS "unaccent";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";



-- Connect to saas_manager database and create necessary extensions and tables
\c saas_manager;
CREATE EXTENSION IF NOT EXISTS "unaccent";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create tenants table
CREATE TABLE IF NOT EXISTS tenants (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    subdomain VARCHAR(50) NOT NULL UNIQUE,
    database_name VARCHAR(100) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    plan VARCHAR(50) DEFAULT 'basic',
    max_users INTEGER DEFAULT 10,
    storage_limit INTEGER DEFAULT 1024, -- in MB
    is_active BOOLEAN DEFAULT TRUE,
    admin_username VARCHAR(50) NOT NULL,
    admin_password VARCHAR(255) NOT NULL  -- Store hashed password
);

-- Create users table for SaaS management
CREATE TABLE IF NOT EXISTS saas_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT TIMESTAMP,
    last_login TIMESTAMP
);

-- Create tenant_users relationship table
CREATE TABLE IF NOT EXISTS tenant_users (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES saas_users(id) ON DELETE CASCADE,
    role VARCHAR(20) DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, user_id)
);

-- Create subscription plans table
CREATE TABLE IF NOT EXISTS subscription_plans (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    price DECIMAL(10,2) NOT NULL,    
    features JSONB,
    max_users INTEGER NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default subscription plans with proper JSONB casting
INSERT INTO subscription_plans (name, price, max_users, storage_limit, features) 
VALUES
    ('Basic', 29.99, 5, 1024, '{"custom_modules": false, "api_access": false, "priority_support": false}'::jsonb),
    ('Professional', 79.99, 25, 5120, '{"custom_modules": true, "api_access": true, "priority_support": false}'::jsonb),
    ('Enterprise', 199.99, 100, 20480, '{"custom_modules": true, "api_access": true, "priority_support": true}'::jsonb)
ON CONFLICT (name) DO NOTHING;

-- Create worker instances table
CREATE TABLE IF NOT EXISTS worker_instances (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    container_name VARCHAR(100) NOT NULL,
    port INTEGER NOT NULL,
    status VARCHAR(20) DEFAULT 'running',
    current_tenants INTEGER DEFAULT 0,
    max_tenants INTEGER DEFAULT 10,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_health_check TIMESTAMP
);

-- Insert default worker instances with correct container names
INSERT INTO worker_instances (name, container_name, port, max_tenants) 
VALUES
    ('worker1', 'odoo_worker1', 8069, 10),
    ('worker2', 'odoo_worker2', 8069, 10)
ON CONFLICT (name) DO NOTHING;

-- Create audit log table with CASCADE on foreign keys
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES saas_users(id) ON DELETE CASCADE,
    tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
    action VARCHAR(100) NOT NULL,
    details JSONB,
    ip_address INET,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_tenants_subdomain ON tenants(subdomain);
CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status);
CREATE INDEX IF NOT EXISTS idx_saas_users_email ON saas_users(email);
CREATE INDEX IF NOT EXISTS idx_tenant_users_tenant_id ON tenant_users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_worker_instances_status ON worker_instances(status);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);

-- Grant schema permissions to odoo_master
GRANT ALL ON SCHEMA public TO odoo_master;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO odoo_master;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO odoo_master;

-- Create default admin user (password: admin123) - only if no admin exists
-- Hash for 'admin123': $2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewE.3F4.7x2QzQ.y
INSERT INTO saas_users (username, email, password_hash, is_admin) 
VALUES ('admin', 'admin@example.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewE.3F4.7x2QzQ.y', TRUE)
ON CONFLICT (username) DO NOTHING;

-- Switch back to postgres database
\c postgres;

-- Display created databases and users
\l
\du

-- Final setup message
DO $$
BEGIN
    RAISE NOTICE '================================================';
    RAISE NOTICE 'Database initialization completed successfully!';
    RAISE NOTICE 'Master database: odoo_master';
    RAISE NOTICE 'SaaS Manager database: saas_manager';
    RAISE NOTICE 'Default admin user: admin / admin123';
    RAISE NOTICE '================================================';
END
$$;