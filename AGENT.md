# AGENT.md - Odoo Multi-Tenant System

## Build/Test/Lint Commands
- **Build**: `docker-compose build` (builds all services)
- **Start system**: `docker-compose up -d` (starts all services)
- **Run SaaS Manager**: `python saas_manager/app.py` (Flask dev server)
- **Health checks**: `curl http://localhost:8000/health` (SaaS Manager), `curl http://localhost:8069/web/health` (Odoo)
- **No formal tests**: Add pytest to requirements.txt and create test files for testing
- **Logs**: `docker-compose logs <service_name>` or check `saas_manager/logs/`

## Architecture
- **Multi-service Docker**: PostgreSQL, Redis, Nginx, SaaS Manager (Flask), Odoo Master, Odoo Workers
- **SaaS Manager**: Flask app on port 8000 managing tenants via Docker API and Odoo XML-RPC
- **Databases**: PostgreSQL with separate DBs per tenant, Redis for session/caching
- **Load balancing**: Nginx reverse proxy distributing to Odoo workers
- **File storage**: Shared odoo_filestore volume across instances

## Code Style & Conventions
- **Python**: PEP8 style, snake_case variables, CamelCase classes
- **Imports**: Standard library first, then third-party, then local imports
- **Error handling**: Comprehensive try/catch with logging via utils.error_tracker
- **Models**: SQLAlchemy ORM with db.Model inheritance, relationships defined
- **Flask**: Blueprints pattern, Flask-Login for auth, WTForms for validation
- **Docker**: Multi-stage builds with health checks and detailed logging
- **Config**: Environment variables for secrets, .conf files for Odoo settings
