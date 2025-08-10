#!/usr/bin/env python3
"""
Shared Utilities Module
Centralized utilities to reduce code duplication across SaaS Manager modules
"""

import logging
import os
import traceback
from functools import wraps
from typing import Optional

import docker
import redis
from flask import current_app, has_app_context
from sqlalchemy import text

# Configure logging
logger = logging.getLogger(__name__)

# ================= CONNECTION MANAGERS =================

class DockerClientManager:
    """Manages Docker client connection with error handling"""
    _instance = None
    _client = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_client(self):
        """Get Docker client, creating if necessary"""
        if self._client is None:
            try:
                self._client = docker.from_env()
                self._client.ping()
                logger.info("Docker client initialized successfully")
            except docker.errors.DockerException as e:
                logger.error(f"Docker initialization failed: {e}")
                self._client = None
            except Exception as e:
                logger.error(f"Unexpected Docker error: {e}")
                self._client = None
        return self._client
    
    def is_available(self) -> bool:
        """Check if Docker is available"""
        return self.get_client() is not None
    
    def reset_connection(self):
        """Reset the Docker connection"""
        if self._client:
            try:
                self._client.close()
            except Exception as e:
                logger.warning(f"Error closing Docker client: {e}")
            self._client = None

class RedisClientManager:
    """Manages Redis client connection with error handling"""
    _instance = None
    _client = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_client(self):
        """Get Redis client, creating if necessary"""
        if self._client is None:
            try:
                redis_url = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
                self._client = redis.Redis.from_url(redis_url)
                self._client.ping()
                logger.info("Redis client initialized successfully")
            except redis.ConnectionError as e:
                logger.error(f"Redis connection failed: {e}")
                self._client = None
            except Exception as e:
                logger.error(f"Unexpected Redis error: {e}")
                self._client = None
        return self._client
    
    def is_available(self) -> bool:
        """Check if Redis is available"""
        return self.get_client() is not None
    
    def reset_connection(self):
        """Reset the Redis connection"""
        if self._client:
            try:
                self._client.close()
            except Exception as e:
                logger.warning(f"Error closing Redis client: {e}")
            self._client = None

# Singleton instances
docker_manager = DockerClientManager()
redis_manager = RedisClientManager()

def get_docker_client():
    """Get Docker client instance"""
    return docker_manager.get_client()

def get_redis_client():
    """Get Redis client instance"""
    return redis_manager.get_client()

# ================= ERROR HANDLING DECORATORS =================

def safe_execute(operation_name: str = "operation", log_errors: bool = True):
    """
    Decorator for safe execution with error logging
    
    Args:
        operation_name: Name of the operation for logging
        log_errors: Whether to log errors
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_errors:
                    logger.error(f"Error in {operation_name} ({func.__name__}): {e}")
                    logger.debug(f"Traceback: {traceback.format_exc()}")
                return None
        return wrapper
    return decorator

def database_transaction(rollback_on_error: bool = True):
    """
    Decorator for database transaction management
    
    Args:
        rollback_on_error: Whether to rollback on error
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not has_app_context():
                logger.error(f"No Flask app context for {func.__name__}")
                return None
            
            try:
                result = func(*args, **kwargs)
                if hasattr(current_app, 'db') and current_app.db:
                    current_app.db.session.commit()
                return result
            except Exception as e:
                logger.error(f"Database error in {func.__name__}: {e}")
                logger.debug(f"Traceback: {traceback.format_exc()}")
                
                if rollback_on_error and hasattr(current_app, 'db') and current_app.db:
                    try:
                        current_app.db.session.rollback()
                        logger.info("Database transaction rolled back")
                    except Exception as rollback_error:
                        logger.error(f"Rollback failed: {rollback_error}")
                
                raise
        return wrapper
    return decorator

# ================= COMMON UTILITIES =================

@safe_execute("Docker container stats")
def get_container_stats(container_name: str) -> Optional[dict]:
    """Get Docker container statistics"""
    client = get_docker_client()
    if not client:
        return None
    
    try:
        container = client.containers.get(container_name)
        if container.status == 'running':
            stats = container.stats(stream=False)
            return {
                'cpu_percent': calculate_cpu_percent(stats),
                'memory_usage': stats['memory_stats'].get('usage', 0),
                'memory_limit': stats['memory_stats'].get('limit', 0),
                'memory_percent': calculate_memory_percent(stats),
                'status': container.status,
                'container': container
            }
    except docker.errors.NotFound:
        logger.warning(f"Container {container_name} not found")
    except Exception as e:
        logger.error(f"Error getting stats for {container_name}: {e}")
    
    return None

def calculate_cpu_percent(stats: dict) -> float:
    """Calculate CPU percentage from Docker stats"""
    try:
        cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                   stats['precpu_stats']['cpu_usage']['total_usage']
        system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                      stats['precpu_stats']['system_cpu_usage']
        
        if system_delta > 0:
            cpu_percent = (cpu_delta / system_delta) * \
                         len(stats['cpu_stats']['cpu_usage']['percpu_usage']) * 100
            return round(cpu_percent, 2)
        return 0.0
    except (KeyError, ZeroDivisionError, TypeError):
        return 0.0

def calculate_memory_percent(stats: dict) -> float:
    """Calculate memory percentage from Docker stats"""
    try:
        memory_usage = stats['memory_stats'].get('usage', 0)
        memory_limit = stats['memory_stats'].get('limit', 0)
        if memory_limit > 0:
            return round((memory_usage / memory_limit) * 100, 2)
        return 0.0
    except (KeyError, ZeroDivisionError, TypeError):
        return 0.0

@safe_execute("Database health check")
def check_database_health() -> bool:
    """Check database connectivity"""
    if not has_app_context():
        return False
    
    try:
        if hasattr(current_app, 'db') and current_app.db:
            current_app.db.session.execute(text('SELECT 1'))
            return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
    
    return False

@safe_execute("Redis health check")
def check_redis_health() -> bool:
    """Check Redis connectivity"""
    client = get_redis_client()
    if not client:
        return False
    
    try:
        client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False

@safe_execute("Docker health check")
def check_docker_health() -> bool:
    """Check Docker connectivity"""
    client = get_docker_client()
    if not client:
        return False
    
    try:
        client.ping()
        return True
    except Exception as e:
        logger.error(f"Docker health check failed: {e}")
        return False

# ================= VALIDATION UTILITIES =================

def validate_ip_address(ip: str) -> bool:
    """Validate IP address format"""
    try:
        import ipaddress
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False

def validate_port(port: int) -> bool:
    """Validate port number"""
    return isinstance(port, int) and 1 <= port <= 65535

def validate_ssh_key(key_content: str) -> bool:
    """Validate SSH key format"""
    if not key_content or not isinstance(key_content, str):
        return False
    
    key_markers = ['-----BEGIN', 'ssh-rsa', 'ssh-ed25519', 'ssh-ecdsa']
    return any(marker in key_content for marker in key_markers)

# ================= SECURITY UTILITIES =================

def is_safe_command(command: str) -> bool:
    """Check if a command is safe to execute"""
    if not command or not isinstance(command, str):
        return False
    
    dangerous_patterns = [
        'rm -rf', 'format', 'mkfs', 'dd if=', 'shutdown', 'reboot',
        '> /dev/', 'rm -f', 'chmod 777', 'chown -R', ':(){ :|:& };:',
        'curl http', 'wget http', 'nc ', 'netcat', 'ncat'
    ]
    
    command_lower = command.lower()
    return not any(pattern in command_lower for pattern in dangerous_patterns)

def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe filesystem operations"""
    import re
    if not filename:
        return 'unnamed'
    
    # Remove or replace unsafe characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = re.sub(r'\.{2,}', '.', filename)  # Multiple dots
    filename = filename.strip('. ')
    
    return filename[:255] if filename else 'unnamed'

# ================= CACHE UTILITIES =================

@safe_execute("Cache operations")
def cache_set(key: str, value: str, expire: int = 3600) -> bool:
    """Set cache value with expiration"""
    client = get_redis_client()
    if not client:
        return False
    
    try:
        client.setex(key, expire, value)
        return True
    except Exception as e:
        logger.error(f"Cache set failed for key {key}: {e}")
        return False

@safe_execute("Cache operations")
def cache_get(key: str) -> Optional[str]:
    """Get cache value"""
    client = get_redis_client()
    if not client:
        return None
    
    try:
        value = client.get(key)
        return value.decode('utf-8') if value else None
    except Exception as e:
        logger.error(f"Cache get failed for key {key}: {e}")
        return None

@safe_execute("Cache operations")
def cache_delete(key: str) -> bool:
    """Delete cache value"""
    client = get_redis_client()
    if not client:
        return False
    
    try:
        client.delete(key)
        return True
    except Exception as e:
        logger.error(f"Cache delete failed for key {key}: {e}")
        return False

# ================= LOGGING UTILITIES =================

def log_action(action: str, details: dict = None, level: str = 'info'):
    """Log action with consistent format"""
    message = f"Action: {action}"
    if details:
        message += f" | Details: {details}"
    
    if level.lower() == 'error':
        logger.error(message)
    elif level.lower() == 'warning':
        logger.warning(message)
    elif level.lower() == 'debug':
        logger.debug(message)
    else:
        logger.info(message)

def log_error_with_context(error: Exception, context: dict = None, operation: str = "operation"):
    """Log error with full context"""
    error_details = {
        'operation': operation,
        'error_type': type(error).__name__,
        'error_message': str(error),
        'traceback': traceback.format_exc()
    }
    
    if context:
        error_details['context'] = context
    
    logger.error(f"Error in {operation}: {error_details}")
    return error_details

# ================= SYSTEM UTILITIES =================

def get_system_health() -> dict:
    """Get comprehensive system health status"""
    health = {
        'database': check_database_health(),
        'redis': check_redis_health(),
        'docker': check_docker_health(),
        'timestamp': str(logger.handlers[0].formatter.formatTime if logger.handlers else 'unknown')
    }
    
    # Calculate overall health
    components = ['database', 'redis', 'docker']
    healthy_count = sum(1 for component in components if health[component])
    health['overall'] = 'healthy' if healthy_count >= 2 else 'degraded' if healthy_count >= 1 else 'unhealthy'
    health['healthy_components'] = healthy_count
    health['total_components'] = len(components)
    
    return health

def format_bytes(bytes_value: int) -> str:
    """Format bytes to human readable string"""
    try:
        bytes_value = int(bytes_value)
        if bytes_value == 0:
            return "0 B"
        
        size_units = ["B", "KB", "MB", "GB", "TB"]
        unit_index = 0
        size = float(bytes_value)
        
        while size >= 1024 and unit_index < len(size_units) - 1:
            size /= 1024
            unit_index += 1
        
        return f"{size:.2f} {size_units[unit_index]}"
    except (ValueError, TypeError):
        return "0 B"

def format_duration(seconds: int) -> str:
    """Format seconds to human readable duration"""
    try:
        seconds = int(seconds)
        if seconds < 60:
            return f"{seconds} seconds"
        elif seconds < 3600:
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            return f"{minutes}m {remaining_seconds}s"
        elif seconds < 86400:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}h {minutes}m"
        else:
            days = seconds // 86400
            hours = (seconds % 86400) // 3600
            return f"{days}d {hours}h"
    except (ValueError, TypeError):
        return "0s"

# ================= CLEANUP UTILITIES =================

def cleanup_connections():
    """Cleanup all managed connections"""
    docker_manager.reset_connection()
    redis_manager.reset_connection()
    logger.info("Shared utility connections cleaned up")

# ================= INITIALIZATION =================

def initialize_shared_utils():
    """Initialize shared utilities with health checks"""
    logger.info("Initializing shared utilities...")
    
    # Test connections
    docker_available = docker_manager.is_available()
    redis_available = redis_manager.is_available()
    
    logger.info(f"Docker available: {docker_available}")
    logger.info(f"Redis available: {redis_available}")
    
    return {
        'docker': docker_available,
        'redis': redis_available,
        'initialized': True
    }

# Initialize on import
_initialization_status = initialize_shared_utils()
