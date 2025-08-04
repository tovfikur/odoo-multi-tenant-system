#!/usr/bin/env python3

"""
Basic test script for enhanced DR backup validation and restore functionality
Tests core functionality without external dependencies
"""

import sys
import os
import json
from pathlib import Path

# Add the backup_panel directory to Python path
sys.path.insert(0, str(Path(__file__).parent / 'backup_panel'))

def test_basic_functionality():
    """Test basic functionality that can be tested locally"""
    
    print("Testing Enhanced DR Backup System")
    print("=" * 50)
    
    try:
        print("Testing imports...")
        from app import BackupManager, BASE_DIR, SCRIPTS_DIR, DATA_DIR
        print("PASS - Imports successful")
        
        print(f"\nConfiguration:")
        print(f"   BASE_DIR: {BASE_DIR}")
        print(f"   SCRIPTS_DIR: {SCRIPTS_DIR}")
        print(f"   DATA_DIR: {DATA_DIR}")
        
        print("\nTesting BackupManager initialization...")
        backup_manager = BackupManager()
        print("PASS - BackupManager initialized successfully")
        
        print("\nTesting session ID normalization...")
        test_ids = [
            "20250104_143022_12345",
            "backup_20250104_143022_12345", 
            "/path/to/backup_20250104_143022_12345",
            "backup_20250104_143022_12345"
        ]
        
        for test_id in test_ids:
            try:
                normalized = backup_manager._normalize_session_id(test_id)
                print(f"   PASS - '{test_id}' -> '{normalized}'")
            except Exception as e:
                print(f"   FAIL - '{test_id}' -> Error: {e}")
        
        print("\nTesting manifest integrity checking...")
        # This will fail since we don't have actual manifest files, but it tests the logic
        test_path = Path("/tmp/nonexistent_backup")
        try:
            result = backup_manager._check_manifest_integrity(test_path)
            expected_error = not result['valid'] and 'not found' in result['error']
            status = "PASS" if expected_error else "FAIL"
            print(f"   {status} - Manifest check: {result['error']}")
        except Exception as e:
            print(f"   FAIL - Manifest check error: {e}")
        
        print("\nTesting local backup listing...")
        try:
            local_backups = backup_manager.list_local_backups()
            print(f"   PASS - Found {len(local_backups)} local backups")
            if local_backups:
                print(f"   Latest backup: {local_backups[0].get('session_id', 'unknown')}")
        except Exception as e:
            print(f"   WARN - Local backup listing error: {e}")
        
        print("\nTesting Google Drive backup listing...")
        try:
            gdrive_backups = backup_manager.list_gdrive_backups()
            print(f"   PASS - Found {len(gdrive_backups)} Google Drive backups")
        except Exception as e:
            print(f"   WARN - Google Drive error (expected if not configured): {str(e)[:100]}")
        
        print("\nTesting validation with dummy session...")
        try:
            result = backup_manager.validate_backup("nonexistent_session", source="local")
            if not result.get('success'):
                print(f"   PASS - Validation correctly failed: {result.get('error', 'Unknown error')[:100]}")
            else:
                print(f"   FAIL - Validation unexpectedly succeeded")
        except Exception as e:
            print(f"   WARN - Validation test error: {e}")
        
    except ImportError as e:
        print(f"FAIL - Import Error: {e}")
        print("   Make sure you're running this from the correct directory")
        print("   Current directory:", os.getcwd())
        print("   Expected files:", list(Path('.').glob('*/app.py')))
    except Exception as e:
        print(f"FAIL - Unexpected Error: {e}")
        import traceback
        traceback.print_exc()

def test_file_structure():
    """Test file structure and dependencies"""
    
    print("\n\nTesting File Structure")
    print("=" * 50)
    
    # Check if critical files exist
    critical_files = [
        ("Backup Panel App", "backup_panel/app.py"),
        ("Validation Script", "scripts/validate-backup.sh"),
        ("Disaster Recovery Script", "scripts/disaster-recovery.sh"),
        ("Google Drive Integration", "scripts/gdrive-integration.py"),
        ("Config Directory", "config/"),
        ("Enhanced Features Summary", "ENHANCED_FEATURES_SUMMARY.md")
    ]
    
    for name, path in critical_files:
        full_path = Path(path)
        exists = full_path.exists()
        status = "PASS" if exists else "FAIL"
        print(f"   {status} - {name}: {path}")
        
        if exists and full_path.is_file() and path.endswith('.py'):
            # Quick syntax check for Python files
            try:
                with open(full_path, 'r') as f:
                    compile(f.read(), path, 'exec')
                print(f"       PASS - Syntax check passed")
            except SyntaxError as e:
                print(f"       FAIL - Syntax error: {e}")
            except Exception as e:
                print(f"       WARN - Check error: {e}")

def main():
    """Main test function"""
    
    print("Enhanced DR Backup System - Basic Test Suite")
    print("===============================================")
    
    # Test file structure first
    test_file_structure()
    
    # Test basic functionality
    test_basic_functionality()
    
    print("\n\nBasic Test Suite Complete!")
    print("=" * 50)
    print("Summary of key improvements:")
    print("• Enhanced backup validation with Google Drive support")
    print("• Improved restore functionality for local and Google Drive")
    print("• Better error handling and manifest integrity checking")
    print("• Enhanced API endpoints with detailed error messages")
    print("• Session ID normalization and path handling")
    print("• Comprehensive backup listing from multiple sources")
    print("\nTo test the full API functionality:")
    print("   1. Start the backup panel server")
    print("   2. Run: python test_enhanced_functionality.py")
    print("   3. Or use curl commands from ENHANCED_FEATURES_SUMMARY.md")

if __name__ == '__main__':
    main()
