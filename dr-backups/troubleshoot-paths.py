#!/usr/bin/env python3

"""
Troubleshooting script to check DR backup panel paths
"""

import os
import sys
from pathlib import Path

print("=== DR Backup Panel Path Troubleshooting ===")
print()

# Current working directory
print(f"Current working directory: {os.getcwd()}")
print()

# Python script location
script_location = Path(__file__).parent
print(f"This script location: {script_location}")
print(f"This script location absolute: {script_location.resolve()}")
print()

# Check expected paths
base_dir = Path(__file__).parent
print(f"Expected BASE_DIR: {base_dir}")
print(f"BASE_DIR exists: {base_dir.exists()}")
print()

scripts_dir = base_dir / 'scripts'
print(f"Expected SCRIPTS_DIR: {scripts_dir}")
print(f"SCRIPTS_DIR exists: {scripts_dir.exists()}")
print()

if scripts_dir.exists():
    print("Contents of SCRIPTS_DIR:")
    for item in scripts_dir.iterdir():
        print(f"  - {item.name}")
    print()

# Check for enhanced-backup.sh
backup_script = scripts_dir / 'enhanced-backup.sh'
print(f"Backup script path: {backup_script}")
print(f"Backup script exists: {backup_script.exists()}")
print()

# Check alternative paths
alternative_paths = [
    Path("K:/Odoo Multi-Tenant System/dr-backups/scripts"),
    Path.cwd() / "scripts",
    Path.cwd().parent / "scripts",
    Path.cwd() / "dr-backups" / "scripts"
]

print("Checking alternative paths:")
for path in alternative_paths:
    exists = path.exists()
    script_exists = (path / 'enhanced-backup.sh').exists() if exists else False
    print(f"  {path}: exists={exists}, script_exists={script_exists}")
print()

# Check Flask app location
app_py = base_dir / 'backup_panel' / 'app.py'
print(f"Flask app location: {app_py}")
print(f"Flask app exists: {app_py.exists()}")
print()

# Environment info
print("Environment info:")
print(f"  OS: {os.name}")
print(f"  Platform: {sys.platform}")
print(f"  Python: {sys.version}")
print()

# Recommendations
print("=== Recommendations ===")
if not scripts_dir.exists():
    print("❌ SCRIPTS_DIR not found!")
    print("   Try running this script from: K:/Odoo Multi-Tenant System/dr-backups/")
else:
    print("✅ SCRIPTS_DIR found")

if not backup_script.exists():
    print("❌ enhanced-backup.sh not found!")
    print("   Check if the file exists at the expected location")
else:
    print("✅ enhanced-backup.sh found")

print()
print("To fix the backup panel:")
print("1. Make sure you're running from the correct directory")
print("2. Check that all files are in place")
print("3. Restart the backup panel after fixes")
