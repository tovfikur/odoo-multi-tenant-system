# Code Deduplication Implementation Guide

This document outlines the shared utilities created to eliminate code duplication and provides recommendations for implementing them across the multi-tenant Odoo system.

## 1. Database Connection Utility (`saas_manager/db_utils.py`)

### Overview
Consolidates the repetitive psycopg2 connection patterns found across 12+ files in the saas_manager directory.

### Key Features
- **Connection Pooling**: Threaded connection pools for better performance
- **Context Managers**: Automatic connection/cursor cleanup
- **Error Handling**: Consistent error handling and logging
- **Flexible API**: Support for both postgres and tenant databases
- **Autocommit Support**: Optional autocommit for DDL operations

### Migration Examples

#### Before (OdooDatabaseManager.py):
```python
conn = psycopg2.connect(
    dbname='postgres',
    user=self.pg_user,
    password=self.pg_password,
    host=self.pg_host,
    port=self.pg_port
)
conn.autocommit = True
cur = conn.cursor()
cur.execute("SELECT datallowconn FROM pg_database WHERE datname = %s", (db_name,))
result = cur.fetchone()
conn.close()
```

#### After:
```python
from .db_utils import postgres_cursor

with postgres_cursor(autocommit=True) as cursor:
    cursor.execute("SELECT datallowconn FROM pg_database WHERE datname = %s", (db_name,))
    result = cursor.fetchone()
```

### Files to Update
- `OdooDatabaseManager.py` (5 connections)
- `TenantLogManager.py` (2 connections)  
- `__init__.py` (2 connections)
- `app.py` (1 connection)
- `add_reset_token_fields.py` (1 connection)

## 2. Muk Web User Preferences Base Mixin

### Overview
Eliminates duplication in muk_web extension modules by providing a common base mixin for user preference patterns.

### Key Features
- **Abstract Base**: Common pattern for SELF_READABLE_FIELDS and SELF_WRITEABLE_FIELDS
- **Helper Methods**: Standardized field creation utilities
- **Inheritance Ready**: Easy to integrate into existing modules

### Migration Examples

#### Before (muk_web_dialog/models/res_users.py):
```python
class ResUsers(models.Model):
    _inherit = 'res.users'
    
    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['dialog_size']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['dialog_size']

    dialog_size = fields.Selection(...)
```

#### After:
```python
from odoo.addons.muk_web_base.models.res_users_mixin import ResUsersMukWebMixin

class ResUsers(ResUsersMukWebMixin):
    _inherit = 'res.users'
    
    def get_preference_fields(self):
        return ['dialog_size']

    dialog_size = self._create_preference_field(
        'dialog_size',
        [('minimize', 'Minimize'), ('maximize', 'Maximize')],
        'minimize'
    )
```

### Files to Update
- `muk_web_dialog/models/res_users.py`
- `muk_web_appsbar/models/res_users.py`
- `muk_web_chatter/models/res_users.py`

## 3. Module Duplication Analysis and Recommendations

### Complete Duplications Found

#### Rolling Key Auth Module
**Status**: Complete duplication across shared_addons, odoo_master, odoo_workers

**Recommendation**: **Use symlinks** - This module appears to be identical across all instances.

**Implementation**:
```bash
# Keep the authoritative version in shared_addons
# Create symlinks in odoo_master and odoo_workers
cd odoo_master
rmdir rolling_key_auth
mklink /D rolling_key_auth ..\shared_addons\rolling_key_auth

cd ..\odoo_workers
rmdir rolling_key_auth  
mklink /D rolling_key_auth ..\shared_addons\rolling_key_auth
```

#### Log Transfer API Module
**Status**: Complete duplication between odoo_master and odoo_workers (not in shared_addons)

**Recommendation**: **Move to shared_addons** - No architectural reason for duplication.

**Implementation**:
```bash
# Move to shared_addons
mv odoo_master/log_transfer_api shared_addons/
cd odoo_master
mklink /D log_transfer_api ..\shared_addons\log_transfer_api

cd ..\odoo_workers
rmdir log_transfer_api
mklink /D log_transfer_api ..\shared_addons\log_transfer_api
```

#### Smile Redis Session Store Module
**Status**: Complete duplication between odoo_master and odoo_workers

**Recommendation**: **Move to shared_addons** - Session management should be consistent.

**Implementation**:
```bash
# Move to shared_addons
mv odoo_master/smile_redis_session_store shared_addons/
cd odoo_master  
mklink /D smile_redis_session_store ..\shared_addons\smile_redis_session_store

cd ..\odoo_workers
rmdir smile_redis_session_store
mklink /D smile_redis_session_store ..\shared_addons\smile_redis_session_store
```

### Symlink Considerations for Multi-Tenant Architecture

**Advantages**:
- Eliminates duplication completely
- Single source of truth for module updates
- Consistent behavior across instances
- Reduced disk usage

**Potential Issues**:
- Windows symlink permissions (may require admin rights)
- Docker volume mounting behavior
- Git handling of symlinks

**Alternative Approach**: If symlinks cause issues, consider:
- Git submodules for shared components
- Automated deployment scripts to copy files
- Build process that creates the duplication from a single source

## 4. Implementation Plan

### Phase 1: Database Utility Migration
1. Test `db_utils.py` with a single file (e.g., `add_reset_token_fields.py`)
2. Gradually migrate other files
3. Update initialization code to use `init_db_manager()`

### Phase 2: Muk Web Mixin Implementation  
1. Add `muk_web_base` to dependencies of muk_web modules
2. Migrate one module at a time (start with `muk_web_dialog`)
3. Test functionality after each migration

### Phase 3: Module Deduplication
1. Create backups of all affected directories
2. Test symlink creation on development environment
3. Implement symlinks or shared library approach
4. Update Docker configurations if needed

## 5. Testing Checklist

### Database Utility Testing
- [ ] Connection pooling works correctly
- [ ] Context managers properly clean up resources
- [ ] Error handling doesn't break existing functionality
- [ ] Multi-threaded access works safely
- [ ] Both postgres and tenant database connections work

### Muk Web Mixin Testing  
- [ ] User preferences still save/load correctly
- [ ] Field visibility is maintained
- [ ] No breaking changes to existing functionality
- [ ] All three modules work after migration

### Module Deduplication Testing
- [ ] Symlinks work correctly in Docker environment
- [ ] Odoo can load modules from symlinked directories
- [ ] No module loading conflicts
- [ ] All functionality preserved after deduplication

## 6. Rollback Plan

If issues arise:
1. **Database Utility**: Revert individual files by removing import and restoring original connection code
2. **Muk Web Mixin**: Remove dependency and restore original code in each module
3. **Module Deduplication**: Remove symlinks and restore original directory copies

## 7. Monitoring and Maintenance

- Monitor database connection pool usage
- Watch for any performance impacts from shared utilities
- Ensure symlinked modules stay in sync during updates
- Document any module-specific customizations that prevent sharing
