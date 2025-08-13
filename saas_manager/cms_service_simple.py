"""
Simple Content Management Service using raw SQL
"""

import os
import uuid
import psycopg2
from datetime import datetime
from typing import List, Dict, Optional, Any
from werkzeug.utils import secure_filename


class SimpleCMSService:
    """Simple CMS service using raw SQL to avoid import issues"""
    
    def __init__(self):
        self.allowed_extensions = {
            'image': {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'},
            'document': {'pdf', 'doc', 'docx', 'txt', 'rtf', 'odt'},
            'video': {'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm'},
            'audio': {'mp3', 'wav', 'ogg', 'm4a', 'flac'}
        }
    
    def get_db_connection(self):
        """Get database connection"""
        return psycopg2.connect(
            host='postgres',
            database='saas_manager', 
            user='odoo_master',
            password='secure_password_123'
        )
    
    # ===== CONTENT MANAGEMENT =====
    
    def get_content_blocks(self, category: str = None) -> List[Dict]:
        """Get all content blocks, optionally filtered by category"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            if category:
                cursor.execute("""
                    SELECT id, identifier, title, content, content_type, category, section, 
                           sort_order, is_active, is_editable, created_at, updated_at, updated_by 
                    FROM cms_content 
                    WHERE category = %s 
                    ORDER BY sort_order
                """, (category,))
            else:
                cursor.execute("""
                    SELECT id, identifier, title, content, content_type, category, section, 
                           sort_order, is_active, is_editable, created_at, updated_at, updated_by 
                    FROM cms_content 
                    ORDER BY sort_order
                """)
            
            rows = cursor.fetchall()
            content_blocks = []
            
            for row in rows:
                content_blocks.append({
                    'id': row[0],
                    'identifier': row[1],
                    'title': row[2],
                    'content': row[3] or '',
                    'content_type': row[4],
                    'category': row[5],
                    'section': row[6],
                    'sort_order': row[7],
                    'is_active': row[8],
                    'is_editable': row[9],
                    'created_at': row[10].isoformat() if row[10] else None,
                    'updated_at': row[11].isoformat() if row[11] else None,
                    'updated_by': row[12]
                })
            
            cursor.close()
            conn.close()
            return content_blocks
            
        except Exception as e:
            print(f"Error getting content blocks: {e}")
            return []
    
    def get_content_by_id(self, content_id: int) -> Optional[Dict]:
        """Get content block by ID"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, identifier, title, content, content_type, category, section, 
                       sort_order, is_active, is_editable, created_at, updated_at, updated_by 
                FROM cms_content 
                WHERE id = %s
            """, (content_id,))
            
            row = cursor.fetchone()
            if row:
                result = {
                    'id': row[0],
                    'identifier': row[1],
                    'title': row[2],
                    'content': row[3] or '',
                    'content_type': row[4],
                    'category': row[5],
                    'section': row[6],
                    'sort_order': row[7],
                    'is_active': row[8],
                    'is_editable': row[9],
                    'created_at': row[10].isoformat() if row[10] else None,
                    'updated_at': row[11].isoformat() if row[11] else None,
                    'updated_by': row[12]
                }
                cursor.close()
                conn.close()
                return result
            
            cursor.close()
            conn.close()
            return None
            
        except Exception as e:
            print(f"Error getting content by ID: {e}")
            return None
    
    def create_content_block(self, data: Dict, user_id: int) -> Dict:
        """Create a new content block"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO cms_content (identifier, title, content, content_type, category, section, 
                                       sort_order, is_active, is_editable, updated_by, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                data['identifier'],
                data['title'],
                data.get('content', ''),
                data.get('content_type', 'text'),
                data.get('category'),
                data.get('section'),
                data.get('sort_order', 0),
                data.get('is_active', True),
                data.get('is_editable', True),
                user_id,
                datetime.now(),
                datetime.now()
            ))
            
            content_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            conn.close()
            
            # Return the created content
            return self.get_content_by_id(content_id)
            
        except Exception as e:
            print(f"Error creating content block: {e}")
            raise
    
    def update_content_block(self, content_id: int, data: Dict, user_id: int) -> Optional[Dict]:
        """Update an existing content block"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE cms_content 
                SET title = %s, content = %s, content_type = %s, category = %s, section = %s, 
                    sort_order = %s, is_active = %s, updated_by = %s, updated_at = %s
                WHERE id = %s
            """, (
                data['title'],
                data.get('content', ''),
                data.get('content_type', 'text'),
                data.get('category'),
                data.get('section'),
                data.get('sort_order', 0),
                data.get('is_active', True),
                user_id,
                datetime.now(),
                content_id
            ))
            
            if cursor.rowcount > 0:
                conn.commit()
                cursor.close()
                conn.close()
                return self.get_content_by_id(content_id)
            
            cursor.close()
            conn.close()
            return None
            
        except Exception as e:
            print(f"Error updating content block: {e}")
            return None
    
    def delete_content_block(self, content_id: int) -> bool:
        """Delete a content block"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM cms_content WHERE id = %s AND is_editable = true", (content_id,))
            success = cursor.rowcount > 0
            
            conn.commit()
            cursor.close()
            conn.close()
            return success
            
        except Exception as e:
            print(f"Error deleting content block: {e}")
            return False
    
    # ===== PAGE MANAGEMENT =====
    
    def get_pages(self, status: str = None) -> List[Dict]:
        """Get all pages, optionally filtered by status"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            if status:
                cursor.execute("""
                    SELECT p.id, p.title, p.slug, p.status, p.created_at, p.updated_at, p.published_at, 
                           p.author_id, u.username as author_name
                    FROM cms_pages p 
                    LEFT JOIN saas_users u ON p.author_id = u.id
                    WHERE p.status = %s 
                    ORDER BY p.updated_at DESC
                """, (status,))
            else:
                cursor.execute("""
                    SELECT p.id, p.title, p.slug, p.status, p.created_at, p.updated_at, p.published_at, 
                           p.author_id, u.username as author_name
                    FROM cms_pages p 
                    LEFT JOIN saas_users u ON p.author_id = u.id
                    ORDER BY p.updated_at DESC
                """)
            
            rows = cursor.fetchall()
            pages = []
            
            for row in rows:
                pages.append({
                    'id': row[0],
                    'title': row[1],
                    'slug': row[2],
                    'status': row[3],
                    'created_at': row[4].isoformat() if row[4] else None,
                    'updated_at': row[5].isoformat() if row[5] else None,
                    'published_at': row[6].isoformat() if row[6] else None,
                    'author_id': row[7],
                    'author_name': row[8] or 'Unknown'
                })
            
            cursor.close()
            conn.close()
            return pages
            
        except Exception as e:
            print(f"Error getting pages: {e}")
            return []
    
    def create_page(self, data: Dict, user_id: int) -> Dict:
        """Create a new page"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Generate slug if not provided
            slug = data.get('slug', self._generate_slug(data['title'], cursor))
            
            cursor.execute("""
                INSERT INTO cms_pages (title, slug, content, meta_title, meta_description, meta_keywords,
                                     status, template, layout, featured_image, excerpt, author_id, 
                                     created_at, updated_at, published_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                data['title'],
                slug,
                data.get('content', ''),
                data.get('meta_title'),
                data.get('meta_description'),
                data.get('meta_keywords'),
                data.get('status', 'draft'),
                data.get('template', 'default'),
                data.get('layout', 'full-width'),
                data.get('featured_image'),
                data.get('excerpt'),
                user_id,
                datetime.now(),
                datetime.now(),
                datetime.now() if data.get('status') == 'published' else None
            ))
            
            page_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            conn.close()
            
            return {'id': page_id, 'title': data['title'], 'slug': slug, 'status': data.get('status', 'draft')}
            
        except Exception as e:
            print(f"Error creating page: {e}")
            raise
    
    # ===== SITE SETTINGS =====
    
    def get_settings(self, category: str = None) -> List[Dict]:
        """Get site settings, optionally filtered by category"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            if category:
                cursor.execute("""
                    SELECT id, key, value, value_type, category, label, description, is_required, is_system
                    FROM site_settings 
                    WHERE category = %s AND is_active = true
                    ORDER BY key
                """, (category,))
            else:
                cursor.execute("""
                    SELECT id, key, value, value_type, category, label, description, is_required, is_system
                    FROM site_settings 
                    WHERE is_active = true
                    ORDER BY category, key
                """)
            
            rows = cursor.fetchall()
            settings = []
            
            for row in rows:
                settings.append({
                    'id': row[0],
                    'key': row[1],
                    'value': self._parse_setting_value(row[2], row[3]),
                    'raw_value': row[2],
                    'value_type': row[3],
                    'category': row[4],
                    'label': row[5],
                    'description': row[6],
                    'is_required': row[7],
                    'is_system': row[8]
                })
            
            cursor.close()
            conn.close()
            return settings
            
        except Exception as e:
            print(f"Error getting settings: {e}")
            return []
    
    def update_setting(self, key: str, value: Any, value_type: str = 'string', user_id: int = 1) -> Dict:
        """Update or create a setting"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Check if setting exists
            cursor.execute("SELECT id FROM site_settings WHERE key = %s", (key,))
            existing = cursor.fetchone()
            
            if existing:
                cursor.execute("""
                    UPDATE site_settings 
                    SET value = %s, value_type = %s, updated_by = %s, updated_at = %s
                    WHERE key = %s
                """, (str(value), value_type, user_id, datetime.now(), key))
            else:
                cursor.execute("""
                    INSERT INTO site_settings (key, value, value_type, updated_by, created_at, updated_at, is_active, is_system)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (key, str(value), value_type, user_id, datetime.now(), datetime.now(), True, False))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return {'key': key, 'value': value, 'value_type': value_type}
            
        except Exception as e:
            print(f"Error updating setting: {e}")
            raise
    
    # ===== HELPER METHODS =====
    
    def _generate_slug(self, title: str, cursor) -> str:
        """Generate URL-friendly slug from title"""
        import re
        slug = title.lower().strip()
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        slug = re.sub(r'\s+', '-', slug)
        slug = slug.strip('-')
        
        # Ensure uniqueness
        base_slug = slug
        counter = 1
        while True:
            cursor.execute("SELECT id FROM cms_pages WHERE slug = %s", (slug,))
            if not cursor.fetchone():
                break
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        return slug
    
    def _parse_setting_value(self, value: str, value_type: str) -> Any:
        """Parse setting value based on type"""
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


# Global service instance
simple_cms_service = SimpleCMSService()