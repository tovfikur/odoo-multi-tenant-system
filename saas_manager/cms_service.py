"""
Content Management Service
Handles all CMS operations including pages, media, content, and settings
"""

import os
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any
from werkzeug.utils import secure_filename
from PIL import Image
from flask import current_app, url_for
from flask_login import current_user

from db import db

class ContentManagementService:
    """Service class for content management operations"""
    
    def __init__(self):
        self.allowed_extensions = {
            'image': {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'},
            'document': {'pdf', 'doc', 'docx', 'txt', 'rtf', 'odt'},
            'video': {'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm'},
            'audio': {'mp3', 'wav', 'ogg', 'm4a', 'flac'}
        }
    
    # ===== CONTENT MANAGEMENT =====
    
    def get_content_blocks(self, category: str = None) -> List[Dict]:
        """Get all content blocks, optionally filtered by category"""
        # Import here to avoid circular imports
        import psycopg2
        from datetime import datetime
        
        try:
            # Use raw SQL since model imports are problematic
            conn = psycopg2.connect(
                host='postgres',
                database='saas_manager', 
                user='odoo_master',
                password='secure_password_123'
            )
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
    
    def get_content_by_identifier(self, identifier: str) -> Optional[Dict]:
        """Get content block by identifier"""
        content = CmsContent.query.filter_by(identifier=identifier).first()
        return self._serialize_content(content) if content else None
    
    def get_content_by_id(self, content_id: int) -> Optional[Dict]:
        """Get content block by ID"""
        content = CmsContent.query.get(content_id)
        return self._serialize_content(content) if content else None
    
    def create_content_block(self, data: Dict) -> Dict:
        """Create a new content block"""
        content = CmsContent(
            identifier=data['identifier'],
            title=data['title'],
            content=data.get('content', ''),
            content_type=data.get('content_type', 'text'),
            category=data.get('category'),
            section=data.get('section'),
            sort_order=data.get('sort_order', 0),
            is_active=data.get('is_active', True),
            content_data=data.get('content_data'),
            updated_by=current_user.id
        )
        
        db.session.add(content)
        db.session.commit()
        
        return self._serialize_content(content)
    
    def update_content_block(self, content_id: int, data: Dict) -> Optional[Dict]:
        """Update an existing content block"""
        content = CmsContent.query.get(content_id)
        if not content:
            return None
        
        # Update fields
        for field in ['title', 'content', 'content_type', 'category', 'section', 'sort_order', 'is_active', 'content_data']:
            if field in data:
                setattr(content, field, data[field])
        
        content.updated_by = current_user.id
        content.updated_at = datetime.utcnow()
        
        db.session.commit()
        return self._serialize_content(content)
    
    def delete_content_block(self, content_id: int) -> bool:
        """Delete a content block"""
        content = CmsContent.query.get(content_id)
        if not content or not content.is_editable:
            return False
        
        db.session.delete(content)
        db.session.commit()
        return True
    
    # ===== PAGE MANAGEMENT =====
    
    def get_pages(self, status: str = None) -> List[Dict]:
        """Get all pages, optionally filtered by status"""
        query = CmsPage.query
        if status:
            query = query.filter_by(status=status)
        
        pages = query.order_by(CmsPage.updated_at.desc()).all()
        return [self._serialize_page(page) for page in pages]
    
    def get_page(self, page_id: int) -> Optional[Dict]:
        """Get a single page by ID"""
        page = CmsPage.query.get(page_id)
        return self._serialize_page(page) if page else None
    
    def get_page_by_slug(self, slug: str) -> Optional[Dict]:
        """Get a page by slug"""
        page = CmsPage.query.filter_by(slug=slug, status='published').first()
        return self._serialize_page(page) if page else None
    
    def create_page(self, data: Dict) -> Dict:
        """Create a new page"""
        # Generate slug if not provided
        slug = data.get('slug', self._generate_slug(data['title']))
        
        page = CmsPage(
            title=data['title'],
            slug=slug,
            content=data.get('content', ''),
            meta_title=data.get('meta_title'),
            meta_description=data.get('meta_description'),
            meta_keywords=data.get('meta_keywords'),
            status=data.get('status', 'draft'),
            template=data.get('template', 'default'),
            layout=data.get('layout', 'full-width'),
            featured_image=data.get('featured_image'),
            excerpt=data.get('excerpt'),
            author_id=current_user.id
        )
        
        if data.get('status') == 'published':
            page.published_at = datetime.utcnow()
        
        db.session.add(page)
        db.session.commit()
        
        return self._serialize_page(page)
    
    def update_page(self, page_id: int, data: Dict) -> Optional[Dict]:
        """Update an existing page"""
        page = CmsPage.query.get(page_id)
        if not page:
            return None
        
        # Update fields
        for field in ['title', 'slug', 'content', 'meta_title', 'meta_description', 'meta_keywords', 
                     'template', 'layout', 'featured_image', 'excerpt']:
            if field in data:
                setattr(page, field, data[field])
        
        # Handle status changes
        if 'status' in data:
            old_status = page.status
            page.status = data['status']
            if old_status != 'published' and data['status'] == 'published':
                page.published_at = datetime.utcnow()
        
        page.updated_at = datetime.utcnow()
        db.session.commit()
        
        return self._serialize_page(page)
    
    def delete_page(self, page_id: int) -> bool:
        """Delete a page"""
        page = CmsPage.query.get(page_id)
        if not page:
            return False
        
        db.session.delete(page)
        db.session.commit()
        return True
    
    # ===== MEDIA MANAGEMENT =====
    
    def get_media_files(self, folder: str = None, file_type: str = None) -> List[Dict]:
        """Get media files, optionally filtered by folder or type"""
        query = CmsMedia.query
        
        if folder:
            query = query.filter_by(folder=folder)
        if file_type:
            query = query.filter_by(file_type=file_type)
        
        media_files = query.order_by(CmsMedia.created_at.desc()).all()
        return [self._serialize_media(media) for media in media_files]
    
    def get_media_file(self, media_id: int) -> Optional[Dict]:
        """Get a single media file by ID"""
        media = CmsMedia.query.get(media_id)
        return self._serialize_media(media) if media else None
    
    def upload_media(self, file, title: str = None, alt_text: str = None, folder: str = '/') -> Dict:
        """Upload a media file"""
        if not file or not file.filename:
            raise ValueError("No file provided")
        
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
        # Determine file type
        file_type = self._get_file_type(file_ext)
        if not file_type:
            raise ValueError(f"File type not supported: {file_ext}")
        
        # Generate unique filename
        unique_filename = f"{uuid.uuid4().hex}.{file_ext}"
        
        # Create upload directory
        upload_dir = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'uploads'), 'media', folder.strip('/'))
        os.makedirs(upload_dir, exist_ok=True)
        
        # Save file
        file_path = os.path.join(upload_dir, unique_filename)
        file.save(file_path)
        
        # Get file info
        file_size = os.path.getsize(file_path)
        width, height = None, None
        
        # Process images
        if file_type == 'image' and file_ext != 'svg':
            try:
                with Image.open(file_path) as img:
                    width, height = img.size
                    # Create thumbnail if needed
                    # self._create_thumbnail(img, file_path)
            except Exception:
                pass  # Not a valid image or processing failed
        
        # Create database record
        media = CmsMedia(
            filename=unique_filename,
            original_filename=filename,
            file_path=file_path,
            file_size=file_size,
            mime_type=file.content_type,
            file_type=file_type,
            title=title or filename,
            alt_text=alt_text,
            width=width,
            height=height,
            folder=folder,
            uploaded_by=current_user.id
        )
        
        db.session.add(media)
        db.session.commit()
        
        return self._serialize_media(media)
    
    def update_media(self, media_id: int, data: Dict) -> Optional[Dict]:
        """Update media file metadata"""
        media = CmsMedia.query.get(media_id)
        if not media:
            return None
        
        for field in ['title', 'alt_text', 'caption', 'description', 'folder', 'tags']:
            if field in data:
                setattr(media, field, data[field])
        
        media.updated_at = datetime.utcnow()
        db.session.commit()
        
        return self._serialize_media(media)
    
    def delete_media(self, media_id: int) -> bool:
        """Delete a media file"""
        media = CmsMedia.query.get(media_id)
        if not media:
            return False
        
        # Delete physical file
        try:
            if os.path.exists(media.file_path):
                os.remove(media.file_path)
        except Exception:
            pass  # File might already be deleted
        
        db.session.delete(media)
        db.session.commit()
        return True
    
    # ===== SITE SETTINGS =====
    
    def get_settings(self, category: str = None) -> List[Dict]:
        """Get site settings, optionally filtered by category"""
        query = SiteSettings.query.filter_by(is_active=True)
        if category:
            query = query.filter_by(category=category)
        
        settings = query.order_by(SiteSettings.key).all()
        return [self._serialize_setting(setting) for setting in settings]
    
    def get_setting(self, key: str) -> Optional[Any]:
        """Get a single setting value by key"""
        setting = SiteSettings.query.filter_by(key=key, is_active=True).first()
        if not setting:
            return None
        
        return self._parse_setting_value(setting.value, setting.value_type)
    
    def update_setting(self, key: str, value: Any, value_type: str = 'string') -> Dict:
        """Update or create a setting"""
        setting = SiteSettings.query.filter_by(key=key).first()
        
        if setting:
            setting.value = str(value)
            setting.value_type = value_type
            setting.updated_by = current_user.id
            setting.updated_at = datetime.utcnow()
        else:
            setting = SiteSettings(
                key=key,
                value=str(value),
                value_type=value_type,
                updated_by=current_user.id
            )
            db.session.add(setting)
        
        db.session.commit()
        return self._serialize_setting(setting)
    
    def update_settings_batch(self, settings_data: Dict) -> List[Dict]:
        """Update multiple settings at once"""
        results = []
        for key, data in settings_data.items():
            if isinstance(data, dict):
                value = data.get('value')
                value_type = data.get('type', 'string')
            else:
                value = data
                value_type = 'string'
            
            result = self.update_setting(key, value, value_type)
            results.append(result)
        
        return results
    
    # ===== HELPER METHODS =====
    
    def _serialize_content(self, content: CmsContent) -> Dict:
        """Serialize content block to dict"""
        return {
            'id': content.id,
            'identifier': content.identifier,
            'title': content.title,
            'content': content.content,
            'content_type': content.content_type,
            'category': content.category,
            'section': content.section,
            'sort_order': content.sort_order,
            'is_active': content.is_active,
            'is_editable': content.is_editable,
            'content_data': content.content_data,
            'created_at': content.created_at.isoformat() if content.created_at else None,
            'updated_at': content.updated_at.isoformat() if content.updated_at else None,
            'updated_by': content.updated_by
        }
    
    def _serialize_page(self, page: CmsPage) -> Dict:
        """Serialize page to dict"""
        return {
            'id': page.id,
            'title': page.title,
            'slug': page.slug,
            'content': page.content,
            'meta_title': page.meta_title,
            'meta_description': page.meta_description,
            'meta_keywords': page.meta_keywords,
            'status': page.status,
            'is_homepage': page.is_homepage,
            'featured': page.featured,
            'template': page.template,
            'layout': page.layout,
            'featured_image': page.featured_image,
            'excerpt': page.excerpt,
            'created_at': page.created_at.isoformat() if page.created_at else None,
            'updated_at': page.updated_at.isoformat() if page.updated_at else None,
            'published_at': page.published_at.isoformat() if page.published_at else None,
            'author_id': page.author_id,
            'author_name': page.author.username if page.author else None
        }
    
    def _serialize_media(self, media: CmsMedia) -> Dict:
        """Serialize media file to dict"""
        return {
            'id': media.id,
            'filename': media.filename,
            'original_filename': media.original_filename,
            'file_path': media.file_path,
            'file_size': media.file_size,
            'mime_type': media.mime_type,
            'file_type': media.file_type,
            'title': media.title,
            'alt_text': media.alt_text,
            'caption': media.caption,
            'description': media.description,
            'width': media.width,
            'height': media.height,
            'folder': media.folder,
            'tags': media.tags,
            'created_at': media.created_at.isoformat() if media.created_at else None,
            'updated_at': media.updated_at.isoformat() if media.updated_at else None,
            'uploaded_by': media.uploaded_by,
            'uploader_name': media.uploader.username if media.uploader else None,
            'url': self._get_media_url(media)
        }
    
    def _serialize_setting(self, setting: SiteSettings) -> Dict:
        """Serialize setting to dict"""
        return {
            'id': setting.id,
            'key': setting.key,
            'value': self._parse_setting_value(setting.value, setting.value_type),
            'raw_value': setting.value,
            'value_type': setting.value_type,
            'category': setting.category,
            'label': setting.label,
            'description': setting.description,
            'is_required': setting.is_required,
            'is_system': setting.is_system,
            'created_at': setting.created_at.isoformat() if setting.created_at else None,
            'updated_at': setting.updated_at.isoformat() if setting.updated_at else None
        }
    
    def _generate_slug(self, title: str) -> str:
        """Generate URL-friendly slug from title"""
        import re
        slug = title.lower().strip()
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        slug = re.sub(r'\s+', '-', slug)
        slug = slug.strip('-')
        
        # Ensure uniqueness
        base_slug = slug
        counter = 1
        while CmsPage.query.filter_by(slug=slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        return slug
    
    def _get_file_type(self, file_ext: str) -> Optional[str]:
        """Determine file type based on extension"""
        for file_type, extensions in self.allowed_extensions.items():
            if file_ext in extensions:
                return file_type
        return None
    
    def _get_media_url(self, media: CmsMedia) -> str:
        """Generate URL for media file"""
        return f"/uploads/media/{media.folder.strip('/')}/{media.filename}"
    
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
cms_service = ContentManagementService()