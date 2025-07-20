# cache_manager.py
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import redis
from flask import current_app
from models import Tenant, TenantUser, SaasUser, WorkerInstance

logger = logging.getLogger(__name__)

class CacheManager:
    """Enhanced cache manager with real-time updates and intelligent invalidation"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client
        self.cache_ttl = 300  # 5 minutes default TTL
        self.short_ttl = 60   # 1 minute for frequently changing data
        
    # Cache key generators
    def _user_tenants_key(self, user_id: int) -> str:
        return f"user_tenants:{user_id}"
    
    def _admin_stats_key(self) -> str:
        return "admin_stats"
    
    def _tenant_details_key(self, tenant_id: int) -> str:
        return f"tenant_details:{tenant_id}"
    
    def _tenant_status_key(self, tenant_id: int) -> str:
        return f"tenant_status:{tenant_id}"
    
    def _cache_version_key(self, cache_type: str) -> str:
        return f"cache_version:{cache_type}"
    
    # Cache versioning for invalidation
    def _get_cache_version(self, cache_type: str) -> int:
        """Get current cache version for a given cache type"""
        if not self.redis_client:
            return 0
        try:
            version = self.redis_client.get(self._cache_version_key(cache_type))
            return int(version) if version else 0
        except Exception as e:
            logger.warning(f"Failed to get cache version for {cache_type}: {e}")
            return 0
    
    def _increment_cache_version(self, cache_type: str) -> int:
        """Increment cache version to invalidate all related caches"""
        if not self.redis_client:
            return 0
        try:
            new_version = self.redis_client.incr(self._cache_version_key(cache_type))
            logger.info(f"Incremented cache version for {cache_type} to {new_version}")
            return new_version
        except Exception as e:
            logger.error(f"Failed to increment cache version for {cache_type}: {e}")
            return 0
    
    def _versioned_key(self, base_key: str, cache_type: str) -> str:
        """Generate versioned cache key"""
        version = self._get_cache_version(cache_type)
        return f"{base_key}:v{version}"
    
    # User tenants caching
    def get_user_tenants(self, user_id: int, force_refresh: bool = False) -> List[Dict]:
        """Get user tenants with caching and versioning"""
        cache_key = self._versioned_key(self._user_tenants_key(user_id), "tenants")
        
        if not force_refresh and self.redis_client:
            try:
                cached_data = self.redis_client.get(cache_key)
                if cached_data:
                    data = json.loads(cached_data)
                    logger.debug(f"Cache hit for user tenants: {user_id}")
                    return data
            except Exception as e:
                logger.warning(f"Redis error in get_user_tenants: {e}")
        
        # Fetch from database
        tenant_data = self._fetch_user_tenants_from_db(user_id)
        
        # Cache the result
        if self.redis_client:
            try:
                self.redis_client.setex(cache_key, self.cache_ttl, json.dumps(tenant_data))
                logger.debug(f"Cached user tenants for user {user_id}")
            except Exception as e:
                logger.warning(f"Failed to cache user tenants: {e}")
        
        return tenant_data
    
    def _fetch_user_tenants_from_db(self, user_id: int) -> List[Dict]:
        """Fetch user tenants from database"""
        from db import db
        tenants = db.session.query(Tenant).join(TenantUser).filter(
            TenantUser.user_id == user_id
        ).all()
        
        return [
            {
                'id': t.id,
                'name': t.name,
                'subdomain': t.subdomain,
                'status': t.status,
                'plan': t.plan,
                'is_active': t.status == 'active',
                'db_name': t.subdomain,
                'max_users': getattr(t, 'max_users', 'N/A'),
                'storage_limit': getattr(t, 'storage_limit', 'N/A'),
                'created_at': t.created_at.strftime('%Y-%m-%d') if t.created_at else None
            }
            for t in tenants
        ]
    
    # Admin stats caching
    def get_admin_stats(self, force_refresh: bool = False) -> Dict:
        """Get admin statistics with caching"""
        cache_key = self._versioned_key(self._admin_stats_key(), "admin_stats")
        
        if not force_refresh and self.redis_client:
            try:
                cached_data = self.redis_client.get(cache_key)
                if cached_data:
                    data = json.loads(cached_data)
                    logger.debug("Cache hit for admin stats")
                    return data
            except Exception as e:
                logger.warning(f"Redis error in get_admin_stats: {e}")
        
        # Fetch from database
        stats = self._fetch_admin_stats_from_db()
        
        # Cache the result
        if self.redis_client:
            try:
                self.redis_client.setex(cache_key, self.short_ttl, json.dumps(stats))
                logger.debug("Cached admin stats")
            except Exception as e:
                logger.warning(f"Failed to cache admin stats: {e}")
        
        return stats
    
    def _fetch_admin_stats_from_db(self) -> Dict:
        """Fetch admin stats from database"""
        return {
            'total_tenants': Tenant.query.count(),
            'active_tenants': Tenant.query.filter_by(status='active').count(),
            'total_users': SaasUser.query.count(),
            'worker_instances': WorkerInstance.query.count(),
            'last_updated': datetime.utcnow().isoformat()
        }
    
    # Tenant details caching
    def get_tenant_details(self, tenant_id: int, force_refresh: bool = False) -> Optional[Dict]:
        """Get tenant details with caching"""
        cache_key = self._versioned_key(self._tenant_details_key(tenant_id), "tenants")
        
        if not force_refresh and self.redis_client:
            try:
                cached_data = self.redis_client.get(cache_key)
                if cached_data:
                    return json.loads(cached_data)
            except Exception as e:
                logger.warning(f"Redis error in get_tenant_details: {e}")
        
        # Fetch from database
        from db import db
        tenant = db.session.query(Tenant).filter_by(id=tenant_id).first()
        if not tenant:
            return None
        
        tenant_data = {
            'id': tenant.id,
            'name': tenant.name,
            'subdomain': tenant.subdomain,
            'status': tenant.status,
            'plan': tenant.plan,
            'database_name': tenant.database_name,
            'admin_username': tenant.admin_username,
            'created_at': tenant.created_at.isoformat() if tenant.created_at else None,
            'updated_at': tenant.updated_at.isoformat() if tenant.updated_at else None
        }
        
        # Cache the result
        if self.redis_client:
            try:
                self.redis_client.setex(cache_key, self.cache_ttl, json.dumps(tenant_data))
            except Exception as e:
                logger.warning(f"Failed to cache tenant details: {e}")
        
        return tenant_data
    
    # Cache invalidation methods
    def invalidate_user_tenants_cache(self, user_ids: List[int] = None):
        """Invalidate user tenants cache for specific users or all users"""
        if user_ids:
            # Invalidate specific users
            for user_id in user_ids:
                self._invalidate_user_cache(user_id)
        else:
            # Invalidate all tenant-related caches
            self._increment_cache_version("tenants")
        
        logger.info(f"Invalidated user tenants cache for users: {user_ids or 'all'}")
    
    def invalidate_admin_stats_cache(self):
        """Invalidate admin statistics cache"""
        self._increment_cache_version("admin_stats")
        logger.info("Invalidated admin stats cache")
    
    def invalidate_tenant_cache(self, tenant_id: int):
        """Invalidate cache for a specific tenant"""
        if not self.redis_client:
            return
        
        try:
            # Find all users associated with this tenant
            from db import db
            tenant_users = db.session.query(TenantUser.user_id).filter_by(tenant_id=tenant_id).all()
            user_ids = [tu.user_id for tu in tenant_users]
            
            # Invalidate caches
            self.invalidate_user_tenants_cache(user_ids)
            self.invalidate_admin_stats_cache()
            
            # Invalidate specific tenant details
            cache_key = self._versioned_key(self._tenant_details_key(tenant_id), "tenants")
            self.redis_client.delete(cache_key)
            
        except Exception as e:
            logger.error(f"Failed to invalidate tenant cache for {tenant_id}: {e}")
    
    def _invalidate_user_cache(self, user_id: int):
        """Invalidate cache for a specific user"""
        if not self.redis_client:
            return
        
        try:
            # Delete all versions of user cache
            pattern = f"{self._user_tenants_key(user_id)}:*"
            keys = self.redis_client.keys(pattern)
            if keys:
                self.redis_client.delete(*keys)
        except Exception as e:
            logger.warning(f"Failed to invalidate user cache for {user_id}: {e}")
    
    # Real-time updates via WebSocket
    def broadcast_update(self, event_type: str, data: Dict, user_ids: List[int] = None):
        """Broadcast real-time updates via WebSocket"""
        if not self.redis_client:
            return
        
        try:
            update_data = {
                'event': event_type,
                'data': data,
                'timestamp': datetime.utcnow().isoformat(),
                'user_ids': user_ids
            }
            
            # Publish to Redis channel for WebSocket handler
            self.redis_client.publish('realtime_updates', json.dumps(update_data))
            logger.info(f"Broadcasted {event_type} update to users: {user_ids or 'all'}")
            
        except Exception as e:
            logger.error(f"Failed to broadcast update: {e}")
    
    # Bulk cache operations
    def warm_cache(self, user_ids: List[int] = None):
        """Warm up cache for specific users or all users"""
        if user_ids:
            for user_id in user_ids:
                self.get_user_tenants(user_id, force_refresh=True)
        
        # Warm admin stats
        self.get_admin_stats(force_refresh=True)
        logger.info(f"Warmed cache for users: {user_ids or 'admin stats only'}")
    
    def clear_all_cache(self):
        """Clear all application caches"""
        if not self.redis_client:
            return
        
        try:
            # Clear all cache versions
            self._increment_cache_version("tenants")
            self._increment_cache_version("admin_stats")
            
            # Clear specific patterns
            patterns = [
                "user_tenants:*",
                "admin_stats*",
                "tenant_details:*",
                "tenant_status:*"
            ]
            
            for pattern in patterns:
                keys = self.redis_client.keys(pattern)
                if keys:
                    self.redis_client.delete(*keys)
            
            logger.info("Cleared all application caches")
            
        except Exception as e:
            logger.error(f"Failed to clear all cache: {e}")


# Usage in your routes
def create_cache_manager(redis_client):
    """Factory function to create cache manager"""
    return CacheManager(redis_client)

# Modified cache helper functions for your app.py
def get_cached_user_tenants(user_id, force_refresh=False):
    """Updated function to use enhanced cache manager"""
    cache_manager = current_app.cache_manager
    return cache_manager.get_user_tenants(user_id, force_refresh)

def get_cached_admin_stats(force_refresh=False):
    """Updated function to use enhanced cache manager"""
    cache_manager = current_app.cache_manager
    return cache_manager.get_admin_stats(force_refresh)

def invalidate_tenant_cache(tenant_id):
    """Invalidate cache when tenant changes"""
    cache_manager = current_app.cache_manager
    cache_manager.invalidate_tenant_cache(tenant_id)

def invalidate_user_cache(user_ids):
    """Invalidate cache when user data changes"""
    cache_manager = current_app.cache_manager
    cache_manager.invalidate_user_tenants_cache(user_ids)