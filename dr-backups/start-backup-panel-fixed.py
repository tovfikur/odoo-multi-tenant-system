#!/usr/bin/env python3

"""
Fixed startup script for DR Backup Panel
Ensures correct paths are set before starting the Flask app
"""

import os
import sys
from pathlib import Path

# Ensure we're in the right directory
script_dir = Path(__file__).parent
os.chdir(script_dir)

# Add the scripts directory to Python path
scripts_dir = script_dir / 'scripts'
if scripts_dir.exists():
    sys.path.insert(0, str(scripts_dir))

# Set environment variables for the Flask app
os.environ['DR_BASE_DIR'] = str(script_dir)
os.environ['DR_SCRIPTS_DIR'] = str(scripts_dir)

print(f"Starting DR Backup Panel...")
print(f"Base directory: {script_dir}")
print(f"Scripts directory: {scripts_dir}")
print(f"Working directory: {os.getcwd()}")

# Check if critical files exist
backup_script = scripts_dir / 'enhanced-backup.sh'
app_file = script_dir / 'backup_panel' / 'app.py'

print(f"Backup script exists: {backup_script.exists()}")
print(f"App file exists: {app_file.exists()}")

if not backup_script.exists():
    print("❌ ERROR: Backup script not found!")
    print(f"   Expected: {backup_script}")
    sys.exit(1)

if not app_file.exists():
    print("❌ ERROR: Flask app not found!")
    print(f"   Expected: {app_file}")
    sys.exit(1)

print("✅ All files found, starting Flask app...")
print("Access the panel at: http://localhost:5000")
print()

# Import and run the Flask app
sys.path.insert(0, str(script_dir / 'backup_panel'))

try:
    from app import app
    app.run(host='0.0.0.0', port=5000, debug=False)
except ImportError as e:
    print(f"❌ ERROR: Failed to import Flask app: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ ERROR: Failed to start Flask app: {e}")
    sys.exit(1)
