"""
CMS Helper for Template Integration
"""

import psycopg2
from functools import lru_cache

class CMSHelper:
    """Helper class to integrate CMS content into templates"""
    
    def __init__(self):
        self.db_config = {
            'host': 'postgres',
            'database': 'saas_manager',
            'user': 'odoo_master',
            'password': 'secure_password_123'
        }
    
    def get_db_connection(self):
        """Get database connection"""
        return psycopg2.connect(**self.db_config)
    
    def get_content(self, identifier, default_content=""):
        """Get content by identifier"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT content FROM cms_content 
                WHERE identifier = %s AND is_active = true
            """, (identifier,))
            
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if result:
                return result[0] or default_content
            return default_content
            
        except Exception as e:
            print(f"Error getting content for {identifier}: {e}")
            return default_content
    
    def get_setting(self, key, default_value=""):
        """Get setting by key"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT value, value_type FROM site_settings 
                WHERE key = %s AND is_active = true
            """, (key,))
            
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if result:
                value, value_type = result
                return self._parse_value(value, value_type) or default_value
            return default_value
            
        except Exception as e:
            print(f"Error getting setting for {key}: {e}")
            return default_value
    
    def _parse_value(self, value, value_type):
        """Parse value based on type"""
        if value is None:
            return None
        
        try:
            if value_type == 'boolean':
                return value.lower() in ('true', '1', 'yes', 'on')
            elif value_type == 'integer':
                return int(value)
            elif value_type == 'float':
                return float(value)
            elif value_type == 'json':
                import json
                return json.loads(value)
            else:
                return value
        except (ValueError, TypeError):
            return value
    
    def clear_cache(self):
        """Clear all cached content - no caching in use"""
        pass

# Global instance
cms_helper = CMSHelper()