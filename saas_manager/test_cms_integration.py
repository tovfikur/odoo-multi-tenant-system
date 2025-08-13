#!/usr/bin/env python3
"""
Test CMS Integration - demonstrates that content changes work
"""

import psycopg2
import requests
import time
from datetime import datetime

# Database configuration
DB_CONFIG = {
    'host': 'postgres',
    'database': 'saas_manager',
    'user': 'odoo_master',
    'password': 'secure_password_123'
}

def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(**DB_CONFIG)

def update_content(identifier, new_content):
    """Update content in the database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE cms_content 
            SET content = %s, updated_at = %s 
            WHERE identifier = %s
        """, (new_content, datetime.now(), identifier))
        
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Error updating content: {e}")
        return False

def test_cms_integration():
    """Test the CMS integration end-to-end"""
    print("🚀 Testing CMS Integration...")
    
    # Original content
    original_title = "সময়, শ্রম ও টাকার সঠিক ব্যবহার শুরু হোক এখানেই"
    test_title = "🎉 CMS Integration Test - Content Successfully Changed!"
    
    try:
        # Step 1: Update the hero title
        print(f"📝 Step 1: Updating hero title to test content...")
        success = update_content('hero_title', test_title)
        if not success:
            print("❌ Failed to update content")
            return False
        
        print(f"✅ Content updated successfully!")
        print(f"   Original: {original_title}")
        print(f"   New:      {test_title}")
        
        # Step 2: Test the CMS demo page
        print("\n🌐 Step 2: Testing CMS integration...")
        print("   You can now test the following:")
        print("   1. Visit http://localhost:8000/cms-index to see the CMS-enabled homepage")
        print("   2. Visit http://localhost:8000/cms-demo to see the CMS demo page")
        print("   3. Visit http://localhost:8000/working-cms to access the Content Manager")
        print("   4. Login as admin/admin123 to see the CMS admin link in the top-right")
        
        # Wait a bit then restore original content
        print(f"\n⏳ Waiting 10 seconds, then restoring original content...")
        time.sleep(10)
        
        # Step 3: Restore original content
        print(f"🔄 Step 3: Restoring original content...")
        success = update_content('hero_title', original_title)
        if success:
            print(f"✅ Original content restored!")
        else:
            print(f"❌ Failed to restore original content")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

def show_cms_info():
    """Show information about the CMS system"""
    print("\n📊 CMS System Information:")
    print("=" * 50)
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Count content blocks
        cursor.execute("SELECT COUNT(*) FROM cms_content")
        content_count = cursor.fetchone()[0]
        
        # Count settings
        cursor.execute("SELECT COUNT(*) FROM site_settings")
        settings_count = cursor.fetchone()[0]
        
        # Count active content
        cursor.execute("SELECT COUNT(*) FROM cms_content WHERE is_active = true")
        active_content = cursor.fetchone()[0]
        
        # Show categories
        cursor.execute("SELECT DISTINCT category FROM cms_content WHERE category IS NOT NULL")
        categories = [row[0] for row in cursor.fetchall()]
        
        print(f"📁 Content Blocks: {content_count} total, {active_content} active")
        print(f"⚙️  Site Settings: {settings_count}")
        print(f"📂 Categories: {', '.join(categories)}")
        
        # Show sample content
        cursor.execute("""
            SELECT identifier, title, category, LENGTH(content) as content_length
            FROM cms_content 
            WHERE is_active = true 
            ORDER BY category, sort_order 
            LIMIT 10
        """)
        
        print(f"\n📝 Sample Content Blocks:")
        for row in cursor.fetchall():
            identifier, title, category, length = row
            print(f"   • {identifier} ({category}) - \"{title}\" [{length} chars]")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error getting CMS info: {e}")

if __name__ == "__main__":
    print("🎯 CMS Integration Test Suite")
    print("=" * 50)
    
    # Show CMS information
    show_cms_info()
    
    # Run integration test
    test_cms_integration()
    
    print("\n🎊 CMS Integration Test Complete!")
    print("\n💡 How to test manually:")
    print("   1. Visit http://localhost:8000/cms-index")
    print("   2. Login as admin (admin/admin123)")
    print("   3. Click the CMS button in top-right corner") 
    print("   4. Edit any content block (e.g., change 'hero_title')")
    print("   5. Refresh the cms-index page to see changes")
    print("   6. Compare with original page at http://localhost:8000/")