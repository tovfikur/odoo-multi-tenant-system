#!/bin/bash
set -e

# Set PostgreSQL password environment variable
source /etc/odoo/.env
export PGPASSWORD=$POSTGRES_PASSWORD

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
until pg_isready -h postgres -p 5432 -U odoo_master -d postgres; do
  echo "PostgreSQL not ready yet, waiting..."
  sleep 2
done
echo "PostgreSQL is ready."

# Check if odoo_master database is initialized
psql -h postgres -U odoo_master -d odoo_master -c "\dt" | grep -q ir_module_module
if [ $? -ne 0 ]; then
  echo "Initializing odoo_master database..."
  odoo -c /etc/odoo/odoo.conf -d odoo_master -i base,web --stop-after-init
  psql -h postgres -U odoo_master -d postgres -c \"UPDATE pg_database SET datallowconn = false WHERE datname = 'tenant_template'
  echo "odoo_master database initialized."
else
  echo "odoo_master database already initialized."
fi

# Check if tenant_template database is initialized
psql -h postgres -U odoo_master -d tenant_template -c "\dt" | grep -q ir_module_module
if [ $? -ne 0 ]; then
  echo "Initializing tenant_template database..."
  odoo -c /etc/odoo/odoo.conf -d tenant_template -i base,web,sale --stop-after-init
  psql -h postgres -U odoo_master -d postgres -c \"UPDATE pg_database SET datallowconn = false WHERE datname = 'tenant_template'
  echo "tenant_template database initialized."
else
  echo "tenant_template database already initialized."
fi

# Unset PGPASSWORD for security
unset PGPASSWORD

# Execute the original command (start Odoo)
exec "$@"