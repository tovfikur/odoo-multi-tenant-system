# Fix Storage Limit Migration

## Issue Fixed
The plan creation was failing with error: `int() argument must be a string, a bytes-like object or a real number, not 'NoneType'`

This happened because the frontend sends `storage_limit: null` for unlimited plans, but the backend was trying to convert it to integer.

## Code Changes Made
1. **Backend fixes in master_admin.py** - Added null handling in plan creation/update
2. **Model changes in models.py** - Changed storage_limit to nullable=True
3. **Database migration needed** - Update existing schema to allow nulls

## Commands to Run in Docker

```bash
# 1. Initialize Flask-Migrate (run inside Docker container)
flask --app app.py db init

# 2. Create migration for storage_limit change
flask --app app.py db migrate -m "Make storage_limit nullable for unlimited plans"

# 3. Apply the migration
flask --app app.py db upgrade

# 4. Verify the fix by testing plan creation with storage_limit: null
```

## Alternative: Manual Database Update

If migrations don't work, run this SQL directly in your PostgreSQL database:

```sql
ALTER TABLE subscription_plans ALTER COLUMN storage_limit DROP NOT NULL;
```

## Testing
After applying the fix, create a plan with these parameters:
- name: "Test Plan"
- price: 10
- max_users: 50
- storage_limit: null (for unlimited)
- modules: ["hr_attendance", "crm"]

The creation should now succeed without errors.

## What the Fix Does
- `storage_limit = null` means unlimited storage
- `storage_limit = 1000` means 1000 GB limit
- Backend now safely handles both cases