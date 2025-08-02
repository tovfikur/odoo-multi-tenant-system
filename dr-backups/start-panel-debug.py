#!/usr/bin/env python3

"""
Debug startup script for DR Backup Panel
Creates all necessary directories and shows detailed diagnostics
"""

import os
import sys
from pathlib import Path

def main():
    print("=== DR Backup Panel Debug Startup ===")
    print()
    
    # Get the base directory
    script_dir = Path(__file__).parent
    print(f"Script directory: {script_dir}")
    print(f"Absolute path: {script_dir.resolve()}")
    
    # Change to the correct working directory
    os.chdir(script_dir)
    print(f"Changed working directory to: {os.getcwd()}")
    print()
    
    # Create necessary directories
    directories = [
        script_dir / 'logs',
        script_dir / 'sessions',
        script_dir / 'backup_panel' / 'data',
        script_dir / 'tests'
    ]
    
    print("Creating necessary directories:")
    for directory in directories:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            print(f"  ✅ {directory}")
        except Exception as e:
            print(f"  ❌ {directory}: {e}")
    print()
    
    # Check critical files
    critical_files = [
        script_dir / 'scripts' / 'enhanced-backup.sh',
        script_dir / 'backup_panel' / 'app.py',
        script_dir / 'config' / 'dr-config.env'
    ]
    
    print("Checking critical files:")
    for file_path in critical_files:
        if file_path.exists():
            print(f"  ✅ {file_path}")
        else:
            print(f"  ❌ {file_path} - NOT FOUND!")
    print()
    
    # Check if app.py is importable
    app_dir = script_dir / 'backup_panel'
    if app_dir.exists():
        sys.path.insert(0, str(app_dir))
        try:
            print("Testing Flask app import...")
            from app import app, logger
            print("  ✅ Flask app imported successfully")
            
            # Test logging
            logger.info("Test log message from startup script")
            print("  ✅ Logging system working")
            
        except ImportError as e:
            print(f"  ❌ Failed to import Flask app: {e}")
            return 1
        except Exception as e:
            print(f"  ❌ Error with Flask app: {e}")
            return 1
    else:
        print("  ❌ backup_panel directory not found!")
        return 1
    
    print()
    print("=== Starting Flask Application ===")
    print("Access the panel at: http://localhost:5000")
    print("Default login: admin / admin")
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 50)
    
    try:
        # Start the Flask app with debug output
        app.run(
            host='0.0.0.0', 
            port=5000, 
            debug=True,  # Enable debug mode for better error messages
            use_reloader=False  # Disable reloader to avoid double startup
        )
    except KeyboardInterrupt:
        print("\n=== Server stopped by user ===")
        return 0
    except Exception as e:
        print(f"\n❌ Server error: {e}")
        return 1

if __name__ == '__main__':
    exit(main())
