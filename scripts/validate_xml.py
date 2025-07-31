#!/usr/bin/env python3
"""
XML Validation Script for SaaS Controller
"""

import xml.etree.ElementTree as ET
import os
import sys

def validate_xml_file(file_path):
    """Validate XML file syntax"""
    try:
        print(f"Validating: {file_path}")
        ET.parse(file_path)
        print(f"VALID: {os.path.basename(file_path)}")
        return True
    except ET.ParseError as e:
        print(f"INVALID: {os.path.basename(file_path)}")
        print(f"   Error: {e}")
        return False
    except Exception as e:
        print(f"ERROR: {os.path.basename(file_path)}")
        print(f"   Error: {e}")
        return False

def main():
    """Main validation function"""
    print("SaaS Controller XML Validation")
    print("=" * 50)
    
    # XML files to validate
    xml_files = [
        "K:/Odoo Multi-Tenant System/shared_addons/saas_controller/views/saas_controller_views.xml",
        "K:/Odoo Multi-Tenant System/shared_addons/saas_controller/views/res_users_views.xml",
        "K:/Odoo Multi-Tenant System/shared_addons/saas_controller/views/branding_views.xml",
        "K:/Odoo Multi-Tenant System/shared_addons/saas_controller/data/default_config.xml",
        "K:/Odoo Multi-Tenant System/shared_addons/saas_controller/security/ir.model.access.csv",
    ]
    
    valid_count = 0
    total_count = 0
    
    for file_path in xml_files:
        if os.path.exists(file_path):
            total_count += 1
            if file_path.endswith('.csv'):
                print(f"Skipping CSV file: {os.path.basename(file_path)}")
                valid_count += 1
                continue
                
            if validate_xml_file(file_path):
                valid_count += 1
        else:
            print(f"WARNING: File not found: {file_path}")
    
    print("\n" + "=" * 50)
    print(f"Validation Summary: {valid_count}/{total_count} files valid")
    
    if valid_count == total_count:
        print("SUCCESS: All XML files are valid!")
        return True
    else:
        print("ERROR: Some XML files have validation errors")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
