"""System Admin Module

Provides comprehensive system administration functionality including:
- Worker management (local and remote)
- System monitoring and resource usage
- Database operations (PostgreSQL, Redis)
- Load balancing and health checks
- VPS server management
"""

# Standard library imports
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

# Third-party imports
import psutil
import psycopg2
import requests
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from sqlalchemy import text, func

# Local application imports
from db import db
from models import SaasUser, Tenant, WorkerInstance, AuditLog, InfrastructureServer
from services import UnifiedWorkerService
from services.nginx_service import NginxLoadBalancerService
from utils import track_errors, error_tracker
from shared_utils import (
    get_redis_client, get_docker_client, safe_execute, 
    database_transaction, log_error_with_context
)

system_admin_bp = Blueprint('system_admin', __name__, url_prefix='/system-admin')

# Initialize connections using shared utilities
redis_client = get_redis_client()
docker_client = get_docker_client()

def require_super_admin():
    """Decorator for super admin access"""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.is_admin:
                return jsonify({
                    'success': False, 
                    'message': 'Super admin access required'
                }), 403
            return fn(*args, **kwargs)
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator

def log_system_action(action: str, details: Optional[Dict[str, Any]] = None):
    """Log system admin actions with proper error handling"""
    try:
        audit_log = AuditLog(
            user_id=current_user.id,
            action=f"SYSTEM: {action}",
            details=details,
            ip_address=request.remote_addr
        )
        db.session.add(audit_log)
        db.session.commit()
        logging.info(f"Logged system action: {action} by user {current_user.id}")
    except Exception as e:
        logging.error(f"Failed to log system action '{action}': {e}")
        # Don't fail the main operation due to logging issues

# ================= MAIN DASHBOARD =================

@system_admin_bp.route('/dashboard')
@login_required
@require_super_admin()
@track_errors('system_admin_dashboard')
def dashboard():
    """System Admin Dashboard"""
    return render_template('system_admin/dashboard.html')


@system_admin_bp.route('/workers')
@login_required
@require_super_admin()
def unified_workers():
    """Unified worker management interface for both local and remote workers"""
    try:
        # Get all workers (both local and remote)
        all_workers = WorkerInstance.query.all()
        
        # Get all available servers for remote deployment
        servers = InfrastructureServer.query.filter_by(status='active').all()
        
        # Enhance workers with server information
        workers_data = []
        for worker in all_workers:
            worker_data = {
                'id': worker.id,
                'name': worker.name,
                'container_name': worker.container_name,
                'port': worker.port,
                'status': worker.status,
                'current_tenants': worker.current_tenants or 0,
                'max_tenants': worker.max_tenants,
                'server_id': worker.server_id,
                'created_at': worker.created_at,
                'last_health_check': worker.last_health_check,
                'server': None
            }
            
            # Add server information for remote workers
            if worker.server_id:
                server = InfrastructureServer.query.get(worker.server_id)
                if server:
                    worker_data['server'] = {
                        'id': server.id,
                        'name': server.name,
                        'ip_address': server.ip_address,
                        'status': server.status,
                        'cpu_cores': server.cpu_cores,
                        'memory_gb': server.memory_gb,
                        'cpu_usage_percent': getattr(server, 'cpu_usage_percent', 0),
                        'memory_usage_percent': getattr(server, 'memory_usage_percent', 0)
                    }
            
            workers_data.append(worker_data)
        
        # Prepare servers data for deployment options
        servers_data = []
        for server in servers:
            servers_data.append({
                'id': server.id,
                'name': server.name,
                'ip_address': server.ip_address,
                'status': server.status,
                'cpu_cores': server.cpu_cores,
                'memory_gb': server.memory_gb,
                'service_roles': server.service_roles or []
            })
        
        return render_template('system_admin/unified_workers.html', 
                             all_workers=workers_data, 
                             servers=servers_data)
                             
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return render_template('system_admin/unified_workers.html', 
                             all_workers=[], 
                             servers=[],
                             error=str(e))

# ================= WORKER MANAGEMENT =================

@system_admin_bp.route('/api/workers/list')
@login_required
@require_super_admin()
@track_errors('get_workers_detailed')
def get_workers_detailed():
    """Get detailed worker information"""
    try:
        workers_data = []
        
        if docker_client:
            # Get all containers
            containers = docker_client.containers.list(all=True)
            
            # Clean up orphaned database records first
            try:
                all_container_names = [c.name for c in containers]
                orphaned_workers = WorkerInstance.query.filter(
                    ~WorkerInstance.container_name.in_(all_container_names)
                ).all()
                
                for worker in orphaned_workers:
                    db.session.delete(worker)
                
                if orphaned_workers:
                    db.session.commit()
                    logging.info(f"Cleaned up {len(orphaned_workers)} orphaned worker records")
                   
            except Exception as e:
                logging.error(f"Database cleanup failed: {e}")
           
            for container in containers:
                # Include all Odoo containers that are workers or custom workers
                if ('odoo' in container.name.lower() and 'worker' in container.name.lower()) or \
                   (container.name.startswith('odoo_worker') or container.name.startswith('test')):
                    
                    # Get container stats
                    try:
                        if container.status == 'running':
                            stats = container.stats(stream=False)
                            cpu_percent = calculate_cpu_percent(stats)
                            memory_usage = stats['memory_stats'].get('usage', 0)
                            memory_limit = stats['memory_stats'].get('limit', 0)
                            memory_percent = (memory_usage / memory_limit * 100) if memory_limit > 0 else 0
                        else:
                            cpu_percent = 0
                            memory_percent = 0
                            memory_usage = 0
                    except Exception as e:
                        logging.warning(f"Failed to get stats for container {container.name}: {e}")
                        cpu_percent = 0
                        memory_percent = 0
                        memory_usage = 0
                    
                    # Get logs
                    try:
                        if container.status == 'running':
                            logs = container.logs(tail=50, timestamps=True).decode('utf-8')
                            log_lines = logs.split('\n')[-10:]  # Last 10 lines
                            # Filter out empty lines
                            log_lines = [line for line in log_lines if line.strip()]
                        else:
                            log_lines = ["Container is not running"]
                    except Exception as e:
                        logging.warning(f"Failed to fetch logs for container {container.name}: {e}")
                        log_lines = ["Unable to fetch logs"]
                    
                    # Check if worker is in database
                    db_worker = WorkerInstance.query.filter_by(container_name=container.name).first()
                    
                    # Auto-create database record if missing for worker containers
                    if not db_worker and ('worker' in container.name.lower() or container.name.startswith('odoo_worker')):
                        try:
                            db_worker = WorkerInstance(
                                name=container.name,
                                container_name=container.name,
                                port=8069,
                                max_tenants=10,  # Default value
                                status=container.status
                            )
                            db.session.add(db_worker)
                            db.session.commit()
                            logging.info(f"Auto-created DB record for container: {container.name}")
                        except Exception as e:
                            logging.error(f"Failed to create DB record for {container.name}: {e}")
                    
                    # Update status if database record exists
                    if db_worker and db_worker.status != container.status:
                        try:
                            db_worker.status = container.status
                            db.session.commit()
                        except Exception as e:
                            logging.error(f"Failed to update status for {container.name}: {e}")
                    
                    workers_data.append({
                        'container_name': container.name,
                        'container_id': container.id[:12],
                        'status': container.status,
                        'image': container.image.tags[0] if container.image.tags else 'unknown',
                        'created': container.attrs['Created'],
                        'ports': container.ports,
                        'cpu_percent': round(cpu_percent, 2),
                        'memory_percent': round(memory_percent, 2),
                        'memory_usage_mb': round(memory_usage / 1024 / 1024, 2),
                        'recent_logs': log_lines,
                        'db_worker_id': db_worker.id if db_worker else None,
                        'db_current_tenants': db_worker.current_tenants if db_worker else 0,
                        'db_max_tenants': db_worker.max_tenants if db_worker else 0,
                        'health_check': check_worker_health(container.name)
                    })
                    
        return jsonify({'success': True, 'workers': workers_data})
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

@system_admin_bp.route('/api/workers/create', methods=['POST'])
@login_required
@require_super_admin()
@track_errors('create_worker_container')
def create_worker_container():
    """Create a new local worker container using unified service"""
    worker_service = UnifiedWorkerService()
    
    result = worker_service.create_local_worker(
        data=request.json or {},
        user_id=current_user.id,
        ip_address=request.remote_addr
    )
    
    # If worker creation was successful, add to nginx load balancer
    if result['success'] and 'worker_details' in result:
        try:
            nginx_service = NginxLoadBalancerService()
            worker_details = result['worker_details']
            
            # Add worker to load balancer (use container name for Docker networks)
            nginx_result = nginx_service.add_worker(
                worker_ip=worker_details['name'],  # Use container name
                worker_port=8069,  # Internal Odoo port
                worker_name=worker_details['name']
            )
            
            if nginx_result['success']:
                result['load_balancer'] = 'added'
                logging.info(f"Worker {worker_details['name']} added to load balancer")
            else:
                result['load_balancer'] = 'failed'
                result['load_balancer_error'] = nginx_result.get('error')
                
        except Exception as nginx_error:
            logging.warning(f"Nginx integration failed: {nginx_error}")
            result['load_balancer'] = 'error'
    
    status_code = 200 if result['success'] else 500
    return jsonify(result), status_code

@system_admin_bp.route('/api/workers/available-infrastructure-servers')
@login_required
@require_super_admin()
@track_errors('get_available_infrastructure_servers')
def get_available_infrastructure_servers():
    """Get available infrastructure servers for worker deployment"""
    try:
        # InfrastructureServer already imported at top
        
        # Get all active servers from infra-admin
        servers = InfrastructureServer.query.filter(
            InfrastructureServer.status.in_(['active', 'ready'])
        ).all()
        
        available_servers = []
        for server in servers:
            # Check if server can host workers (either explicitly set or inferred)
            can_host_workers = (
                server.service_roles and 'odoo_worker' in server.service_roles
            ) or (
                server.current_services and any('odoo' in service for service in server.current_services)
            ) or (
                # Default: assume any active server can potentially host workers
                server.status == 'active'
            )
            
            available_servers.append({
                'id': server.id,
                'name': server.name,
                'ip_address': server.ip_address,
                'health_score': server.health_score or 100,
                'current_services': server.current_services or [],
                'service_roles': server.service_roles or [],
                'cpu_cores': server.cpu_cores,
                'memory_gb': server.memory_gb,
                'disk_gb': server.disk_gb,
                'os_type': server.os_type,
                'status': server.status,
                'deployment_status': server.deployment_status,
                'last_health_check': server.last_health_check.isoformat() if server.last_health_check else None,
                'location': 'remote',
                'can_host_workers': can_host_workers,
                'network_zone': getattr(server, 'network_zone', 'production'),
                'internal_ip': getattr(server, 'internal_ip', server.ip_address),
                'external_ip': getattr(server, 'external_ip', server.ip_address)
            })
        
        # Sort by health score and status
        available_servers.sort(key=lambda x: (x['status'] == 'active', x['health_score']), reverse=True)
        
        return jsonify({
            'success': True,
            'servers': available_servers,
            'total_servers': len(available_servers),
            'active_servers': len([s for s in available_servers if s['status'] == 'active']),
            'worker_capable_servers': len([s for s in available_servers if s['can_host_workers']])
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

@system_admin_bp.route('/api/workers/create-remote', methods=['POST'])
@login_required
@require_super_admin()
@track_errors('create_remote_worker')
def create_remote_worker():
    """Create worker on remote infrastructure server using unified service"""
    worker_service = UnifiedWorkerService()
    
    result = worker_service.create_remote_worker(
        data=request.json or {},
        user_id=current_user.id,
        request_obj=request,
        ip_address=request.remote_addr
    )
    
    # If remote worker creation was successful, add to nginx load balancer
    if result['success'] and 'worker_details' in result:
        try:
            nginx_service = NginxLoadBalancerService()
            worker_details = result['worker_details']
            
            # For remote workers, use server IP and external port
            server_ip = worker_details.get('server_ip', 'localhost')
            worker_port = worker_details.get('port', 8069)
            
            nginx_result = nginx_service.add_worker(
                worker_ip=server_ip,
                worker_port=worker_port,
                worker_name=worker_details['name']
            )
            
            if nginx_result['success']:
                result['load_balancer'] = 'added'
                logging.info(f"Remote worker {worker_details['name']} added to load balancer")
            else:
                result['load_balancer'] = 'failed'
                result['load_balancer_error'] = nginx_result.get('error')
                
        except Exception as nginx_error:
            logging.warning(f"Nginx integration failed for remote worker: {nginx_error}")
            result['load_balancer'] = 'error'
    
    status_code = 200 if result['success'] else (
        400 if 'not found' in result.get('message', '').lower() or 
              'required' in result.get('message', '').lower()
        else 500
    )
    return jsonify(result), status_code

@system_admin_bp.route('/api/workers/<container_name>/action', methods=['POST'])
@login_required
@require_super_admin()
@track_errors('worker_action')
def worker_action(container_name):
    """Perform action on worker container"""
    try:
        action = request.json.get('action')
        
        if not docker_client:
            return jsonify({'success': False, 'message': 'Docker not available'}), 500
        
        container = docker_client.containers.get(container_name)
        
        if action == 'start':
            container.start()
            message = f'Worker {container_name} started'
        elif action == 'stop':
            container.stop()
            message = f'Worker {container_name} stopped'
        elif action == 'restart':
            container.restart()
            message = f'Worker {container_name} restarted'
        elif action == 'remove':
            container.remove(force=True)
            # Remove from database
            WorkerInstance.query.filter_by(container_name=container_name).delete()
            db.session.commit()
            message = f'Worker {container_name} removed'
        else:
            return jsonify({'success': False, 'message': 'Invalid action'}), 400
        
        log_system_action('worker_action', {
            'container_name': container_name,
            'action': action
        })
        
        return jsonify({'success': True, 'message': message})
        
    except Exception as e:
        error_tracker.log_error(e, {'container_name': container_name, 'action': action})
        return jsonify({'success': False, 'message': str(e)}), 500

@system_admin_bp.route('/api/workers/<container_name>/logs')
@login_required
@require_super_admin()
@track_errors('get_worker_logs')
def get_worker_logs(container_name):
    """Get worker container logs"""
    try:
        if not docker_client:
            return jsonify({'success': False, 'message': 'Docker not available'}), 500
        
        container = docker_client.containers.get(container_name)
        logs = container.logs(tail=200, timestamps=True).decode('utf-8')
        
        return jsonify({
            'success': True,
            'logs': logs.split('\n'),
            'container_status': container.status
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ================= REDIS OPERATIONS =================

@system_admin_bp.route('/api/redis/info')
@login_required
@require_super_admin()
@track_errors('redis_info')
def redis_info():
    """Get Redis information"""
    try:
        if not redis_client:
            return jsonify({'success': False, 'message': 'Redis not available'}), 500
        
        info = redis_client.info()
        
        # Get memory usage
        memory_info = {
            'used_memory': info.get('used_memory', 0),
            'used_memory_human': info.get('used_memory_human', '0B'),
            'used_memory_peak': info.get('used_memory_peak', 0),
            'used_memory_peak_human': info.get('used_memory_peak_human', '0B'),
            'maxmemory': info.get('maxmemory', 0)
        }
        
        # Get client info
        clients = redis_client.client_list()
        
        # Get database info
        db_info = {}
        for i in range(16):  # Redis default 16 databases
            try:
                size = redis_client.dbsize()
                if size > 0:
                    db_info[f'db{i}'] = size
            except Exception as e:
                logging.warning(f"Failed to get size for Redis DB {i}: {e}")
        
        return jsonify({
            'success': True,
            'server_info': {
                'version': info.get('redis_version'),
                'uptime_days': info.get('uptime_in_days'),
                'connected_clients': info.get('connected_clients'),
                'total_commands_processed': info.get('total_commands_processed'),
                'keyspace_hits': info.get('keyspace_hits'),
                'keyspace_misses': info.get('keyspace_misses')
            },
            'memory_info': memory_info,
            'clients': len(clients),
            'databases': db_info
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@system_admin_bp.route('/api/redis/keys')
@login_required
@require_super_admin()
@track_errors('redis_keys')
def redis_keys():
    """Get Redis keys"""
    try:
        if not redis_client:
            return jsonify({'success': False, 'message': 'Redis not available'}), 500
        
        pattern = request.args.get('pattern', '*')
        keys = redis_client.keys(pattern)
        
        keys_info = []
        for key in keys[:100]:  # Limit to 100 keys
            try:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                key_type = redis_client.type(key).decode('utf-8')
                ttl = redis_client.ttl(key)
                
                keys_info.append({
                    'key': key_str,
                    'type': key_type,
                    'ttl': ttl if ttl > 0 else None
                })
            except:
                continue
        
        return jsonify({
            'success': True,
            'keys': keys_info,
            'total_keys': len(keys),
            'showing': len(keys_info)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@system_admin_bp.route('/api/redis/flush', methods=['POST'])
@login_required
@require_super_admin()
@track_errors('redis_flush')
def redis_flush():
    """Flush Redis database"""
    try:
        if not redis_client:
            return jsonify({'success': False, 'message': 'Redis not available'}), 500
        
        db_num = request.json.get('database', 'all')
        
        if db_num == 'all':
            redis_client.flushall()
            message = 'All Redis databases flushed'
        else:
            redis_client.flushdb()
            message = f'Redis database {db_num} flushed'
        
        log_system_action('redis_flush', {'database': db_num})
        
        return jsonify({'success': True, 'message': message})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ================= POSTGRES OPERATIONS =================

@system_admin_bp.route('/api/postgres/info')
@login_required
@require_super_admin()
@track_errors('postgres_info')
def postgres_info():
    """Get PostgreSQL information"""
    try:
        # Get database list
        result = db.session.execute(text("""
            SELECT datname, pg_size_pretty(pg_database_size(datname)) as size
            FROM pg_database 
            WHERE datistemplate = false
            ORDER BY pg_database_size(datname) DESC
        """))
        databases = [{'name': row[0], 'size': row[1]} for row in result.fetchall()]
        
        # Get connection info
        result = db.session.execute(text("""
            SELECT count(*) as connections, 
                   state,
                   query_start 
            FROM pg_stat_activity 
            WHERE state IS NOT NULL 
            GROUP BY state, query_start
            ORDER BY connections DESC
        """))
        connections = [{'count': row[0], 'state': row[1]} for row in result.fetchall()]
        
        # Get table sizes for main database
        result = db.session.execute(text("""
            SELECT schemaname, tablename, 
                   pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) as size,
                   pg_relation_size(schemaname||'.'||tablename) as bytes
            FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY pg_relation_size(schemaname||'.'||tablename) DESC
            LIMIT 20
        """))
        tables = [{'schema': row[0], 'table': row[1], 'size': row[2], 'bytes': row[3]} for row in result.fetchall()]
        
        return jsonify({
            'success': True,
            'databases': databases,
            'connections': connections,
            'tables': tables
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@system_admin_bp.route('/api/postgres/query', methods=['POST'])
@login_required
@require_super_admin()
@track_errors('postgres_query')
def postgres_query():
    """Execute PostgreSQL query"""
    try:
        query = request.json.get('query', '').strip()
        
        if not query:
            return jsonify({'success': False, 'message': 'Query required'}), 400
        
        # Security check - only allow safe operations
        dangerous_keywords = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'CREATE', 'TRUNCATE']
        if any(keyword in query.upper() for keyword in dangerous_keywords):
            return jsonify({'success': False, 'message': 'Only SELECT queries allowed'}), 400
        
        result = db.session.execute(text(query))
        rows = result.fetchall()
        columns = result.keys() if hasattr(result, 'keys') else []
        
        data_rows = []
        for row in rows:
            row_dict = {}
            for i, col in enumerate(columns):
                value = row[i]
                if isinstance(value, datetime):
                    value = value.isoformat()
                row_dict[col] = value
            data_rows.append(row_dict)
        
        log_system_action('postgres_query', {'query': query[:100]})
        
        return jsonify({
            'success': True,
            'columns': list(columns),
            'rows': data_rows,
            'row_count': len(data_rows)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ================= NGINX OPERATIONS =================

@system_admin_bp.route('/api/nginx/status')
@login_required
@require_super_admin()
@track_errors('nginx_status')
def nginx_status():
    """Get Nginx status"""
    try:
        if not docker_client:
            return jsonify({'success': False, 'message': 'Docker not available'}), 500
        
        # Find nginx container
        nginx_container = None
        for container in docker_client.containers.list():
            if 'nginx' in container.name.lower():
                nginx_container = container
                break
        
        if not nginx_container:
            return jsonify({'success': False, 'message': 'Nginx container not found'}), 404
        
        # Get container stats
        stats = nginx_container.stats(stream=False)
        
        # Get logs
        logs = nginx_container.logs(tail=50, timestamps=True).decode('utf-8')
        
        return jsonify({
            'success': True,
            'container_id': nginx_container.id[:12],
            'status': nginx_container.status,
            'image': nginx_container.image.tags[0] if nginx_container.image.tags else 'unknown',
            'ports': nginx_container.ports,
            'logs': logs.split('\n')[-20:],  # Last 20 lines
            'memory_usage': stats['memory_stats'].get('usage', 0),
            'cpu_percent': calculate_cpu_percent(stats)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@system_admin_bp.route('/api/nginx/reload', methods=['POST'])
@login_required
@require_super_admin()
@track_errors('nginx_reload')
def nginx_reload():
    """Reload Nginx configuration"""
    try:
        if not docker_client:
            return jsonify({'success': False, 'message': 'Docker not available'}), 500
        
        # Find nginx container
        nginx_container = None
        for container in docker_client.containers.list():
            if 'nginx' in container.name.lower():
                nginx_container = container
                break
        
        if not nginx_container:
            return jsonify({'success': False, 'message': 'Nginx container not found'}), 404
        
        # Reload nginx
        result = nginx_container.exec_run('nginx -s reload')
        
        log_system_action('nginx_reload', {'exit_code': result.exit_code})
        
        if result.exit_code == 0:
            return jsonify({'success': True, 'message': 'Nginx reloaded successfully'})
        else:
            return jsonify({'success': False, 'message': f'Nginx reload failed: {result.output.decode()}'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ================= LOAD BALANCING =================

@system_admin_bp.route('/api/load-balancing/status')
@login_required
@require_super_admin()
@track_errors('load_balancing_status')
def load_balancing_status():
    """Check load balancing status"""
    try:
        workers = WorkerInstance.query.all()
        
        load_info = []
        for worker in workers:
            # Get actual tenant count from database
            tenant_count = Tenant.query.filter_by(status='active').count()
            
            # Calculate load percentage
            load_percent = (worker.current_tenants / worker.max_tenants * 100) if worker.max_tenants > 0 else 0
            
            # Check if worker is responding
            is_healthy = check_worker_health(worker.container_name)
            
            load_info.append({
                'worker_name': worker.name,
                'container_name': worker.container_name,
                'current_tenants': worker.current_tenants,
                'max_tenants': worker.max_tenants,
                'load_percent': round(load_percent, 1),
                'status': worker.status,
                'is_healthy': is_healthy,
                'last_health_check': worker.last_health_check.isoformat() if worker.last_health_check else None
            })
        
        # Calculate overall balance
        total_tenants = sum(w.current_tenants for w in workers)
        total_capacity = sum(w.max_tenants for w in workers)
        overall_load = (total_tenants / total_capacity * 100) if total_capacity > 0 else 0
        
        # Check if load is balanced
        loads = [w.current_tenants for w in workers if w.max_tenants > 0]
        load_variance = max(loads) - min(loads) if loads else 0
        is_balanced = load_variance <= 2  # Consider balanced if variance <= 2
        
        return jsonify({
            'success': True,
            'workers': load_info,
            'overall_load': round(overall_load, 1),
            'total_tenants': total_tenants,
            'total_capacity': total_capacity,
            'is_balanced': is_balanced,
            'load_variance': load_variance
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@system_admin_bp.route('/api/load-balancing/rebalance', methods=['POST'])
@login_required
@require_super_admin()
@track_errors('rebalance_load')
def rebalance_load():
    """Rebalance load across workers"""
    try:
        # This is a simplified rebalancing - in production you'd want more sophisticated logic
        workers = WorkerInstance.query.filter_by(status='running').all()
        
        if len(workers) < 2:
            return jsonify({'success': False, 'message': 'Need at least 2 workers for rebalancing'}), 400
        
        # Sort workers by current load
        workers.sort(key=lambda w: w.current_tenants)
        
        total_tenants = sum(w.current_tenants for w in workers)
        avg_tenants = total_tenants // len(workers)
        
        rebalanced = []
        for worker in workers:
            if worker.current_tenants > avg_tenants + 1:
                # Move some tenants from this worker
                excess = worker.current_tenants - avg_tenants
                worker.current_tenants = avg_tenants
                rebalanced.append(f"Reduced {worker.name} by {excess} tenants")
            elif worker.current_tenants < avg_tenants:
                # This worker can take more tenants
                deficit = avg_tenants - worker.current_tenants
                worker.current_tenants = avg_tenants
                rebalanced.append(f"Increased {worker.name} by {deficit} tenants")
        
        db.session.commit()
        
        log_system_action('load_rebalance', {'changes': rebalanced})
        
        return jsonify({
            'success': True,
            'message': 'Load rebalanced successfully',
            'changes': rebalanced
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

# ================= SYSTEM MONITORING =================

@system_admin_bp.route('/api/system/resources')
@login_required
@require_super_admin()
@track_errors('system_resources')
def system_resources():
   """Get system resource usage"""
   try:
       # CPU information
       cpu_info = {
           'percent': psutil.cpu_percent(interval=1),
           'count': psutil.cpu_count(),
           'load_avg': psutil.getloadavg() if hasattr(psutil, 'getloadavg') else [0, 0, 0]
       }
       
       # Memory information
       memory = psutil.virtual_memory()
       memory_info = {
           'total': memory.total,
           'available': memory.available,
           'used': memory.used,
           'percent': memory.percent,
           'total_gb': round(memory.total / 1024**3, 2),
           'used_gb': round(memory.used / 1024**3, 2),
           'available_gb': round(memory.available / 1024**3, 2)
       }
       
       # Disk information
       disk = psutil.disk_usage('/')
       disk_info = {
           'total': disk.total,
           'used': disk.used,
           'free': disk.free,
           'percent': round((disk.used / disk.total) * 100, 2),
           'total_gb': round(disk.total / 1024**3, 2),
           'used_gb': round(disk.used / 1024**3, 2),
           'free_gb': round(disk.free / 1024**3, 2)
       }
       
       # Network information
       network = psutil.net_io_counters()
       network_info = {
           'bytes_sent': network.bytes_sent,
           'bytes_recv': network.bytes_recv,
           'packets_sent': network.packets_sent,
           'packets_recv': network.packets_recv
       }
       
       # Container resource usage instead of system processes
       containers_usage = []
       if docker_client:
           try:
               containers = docker_client.containers.list()
               for container in containers:
                   try:
                       if container.status == 'running':
                           stats = container.stats(stream=False)
                           
                           # Calculate CPU percentage
                           cpu_percent = calculate_cpu_percent(stats)
                           
                           # Calculate memory usage
                           memory_usage = stats['memory_stats'].get('usage', 0)
                           memory_limit = stats['memory_stats'].get('limit', 0)
                           memory_percent = (memory_usage / memory_limit * 100) if memory_limit > 0 else 0
                           
                           # Calculate disk I/O
                           io_stats = stats.get('blkio_stats', {})
                           io_service_bytes = io_stats.get('io_service_bytes_recursive', [])
                           
                           read_bytes = 0
                           write_bytes = 0
                           for io in io_service_bytes:
                               if io.get('op') == 'Read':
                                   read_bytes += io.get('value', 0)
                               elif io.get('op') == 'Write':
                                   write_bytes += io.get('value', 0)
                           
                           # Calculate network I/O
                           networks = stats.get('networks', {})
                           rx_bytes = sum(net.get('rx_bytes', 0) for net in networks.values())
                           tx_bytes = sum(net.get('tx_bytes', 0) for net in networks.values())
                           
                           # Determine container type for better identification
                           container_type = 'other'
                           if 'odoo' in container.name.lower():
                               if 'worker' in container.name.lower():
                                   container_type = 'worker'
                               elif 'master' in container.name.lower():
                                   container_type = 'master'
                               else:
                                   container_type = 'odoo'
                           elif 'postgres' in container.name.lower():
                               container_type = 'database'
                           elif 'redis' in container.name.lower():
                               container_type = 'cache'
                           elif 'nginx' in container.name.lower():
                               container_type = 'proxy'
                           
                           containers_usage.append({
                               'name': container.name[:30],  # Truncate long names
                               'type': container_type,
                               'image': container.image.tags[0].split(':')[0] if container.image.tags else 'unknown',
                               'cpu_percent': round(cpu_percent, 1),
                               'memory_percent': round(memory_percent, 1),
                               'memory_mb': round(memory_usage / 1024 / 1024, 1),
                               'disk_read_mb': round(read_bytes / 1024 / 1024, 1),
                               'disk_write_mb': round(write_bytes / 1024 / 1024, 1),
                               'net_rx_mb': round(rx_bytes / 1024 / 1024, 1),
                               'net_tx_mb': round(tx_bytes / 1024 / 1024, 1),
                               'status': container.status,
                               'uptime': str(datetime.utcnow() - datetime.fromisoformat(container.attrs['Created'].replace('Z', '+00:00').replace('+00:00', ''))).split('.')[0]
                           })
                   except Exception as e:
                       logging.warning(f"Failed to get stats for {container.name}: {e}")
                   # Add container even if stats fail
                       containers_usage.append({
                           'name': container.name[:30],
                           'type': 'unknown',
                           'image': 'unknown',
                           'cpu_percent': 0,
                           'memory_percent': 0,
                           'memory_mb': 0,
                           'disk_read_mb': 0,
                           'disk_write_mb': 0,
                           'net_rx_mb': 0,
                           'net_tx_mb': 0,
                           'status': container.status,
                           'uptime': 'unknown'
                       })
                       continue
           except Exception as e:
               logging.error(f"Failed to get container stats: {e}")

       # Sort by CPU usage (highest first), then by memory usage
       containers_usage.sort(key=lambda x: (x['cpu_percent'], x['memory_percent']), reverse=True)
       top_containers = containers_usage[:10]  # Top 10 containers
       
       # Summary statistics for containers
       container_summary = {
           'total_containers': len(containers_usage),
           'running_containers': len([c for c in containers_usage if c['status'] == 'running']),
           'total_cpu_usage': round(sum(c['cpu_percent'] for c in containers_usage), 1),
           'total_memory_mb': round(sum(c['memory_mb'] for c in containers_usage), 1),
           'highest_cpu_container': max(containers_usage, key=lambda x: x['cpu_percent'])['name'] if containers_usage else 'None',
           'highest_memory_container': max(containers_usage, key=lambda x: x['memory_mb'])['name'] if containers_usage else 'None'
       }
       
       return jsonify({
           'success': True,
           'cpu': cpu_info,
           'memory': memory_info,
           'disk': disk_info,
           'network': network_info,
           'top_containers': top_containers,
           'container_summary': container_summary,
           'timestamp': datetime.utcnow().isoformat()
       })
       
   except Exception as e:
       return jsonify({'success': False, 'message': str(e)}), 500

# ================= HELPER FUNCTIONS =================
# Note: Many helper functions below could be moved to utility modules

def calculate_cpu_percent(stats: Dict[str, Any]) -> float:
    """Calculate CPU percentage from Docker stats
    
    Args:
        stats: Docker stats dictionary
        
    Returns:
        CPU percentage as float, 0 if calculation fails
    """
    try:
        cpu_delta = (
            stats['cpu_stats']['cpu_usage']['total_usage'] - 
            stats['precpu_stats']['cpu_usage']['total_usage']
        )
        system_delta = (
            stats['cpu_stats']['system_cpu_usage'] - 
            stats['precpu_stats']['system_cpu_usage']
        )
        
        if system_delta > 0 and cpu_delta >= 0:
            cpu_percent = (
                (cpu_delta / system_delta) * 
                len(stats['cpu_stats']['cpu_usage']['percpu_usage']) * 100
            )
            return round(cpu_percent, 2)
        return 0.0
    except (KeyError, TypeError, ZeroDivisionError) as e:
        logging.debug(f"CPU calculation error: {e}")
        return 0.0

def check_worker_health(container_name: str) -> bool:
    """Check if worker container is healthy
    
    Args:
        container_name: Name of the container to check
        
    Returns:
        True if worker is healthy, False otherwise
    """
    try:
        if not docker_client:
            logging.warning("Docker client not available for health check")
            return False
        
        container = docker_client.containers.get(container_name)
        if container.status != 'running':
            return False
        
        # Try to access health endpoint with timeout
        try:
            health_check = container.exec_run(
                'curl -f -m 5 http://localhost:8069/web/health',
                timeout=10
            )
            return health_check.exit_code == 0
        except Exception as e:
            logging.debug(f"Health check failed for {container_name}, falling back to status: {e}")
            return container.status == 'running'
            
    except Exception as e:
        logging.warning(f"Could not check health for container {container_name}: {e}")
        return False

# ================= VPS SERVER MANAGEMENT =================

@system_admin_bp.route('/api/vps/servers/list')
@login_required
@require_super_admin()
@track_errors('get_vps_servers')
def get_vps_servers():
    """Get list of all VPS servers from infrastructure admin"""
    try:
        # InfrastructureServer already imported at top
        
        # Get all servers with their details
        servers = InfrastructureServer.query.all()
        
        server_list = []
        for server in servers:
            # Test connection status
            connection_status = test_server_connection(server)
            
            server_data = {
                'id': server.id,
                'name': server.name,
                'ip_address': server.ip_address,
                'status': server.status,
                'health_score': server.health_score or 0,
                'current_services': server.current_services or [],
                'service_roles': server.service_roles or [],
                'cpu_cores': server.cpu_cores,
                'memory_gb': server.memory_gb,
                'disk_gb': server.disk_gb,
                'os_type': server.os_type,
                'deployment_status': server.deployment_status,
                'last_health_check': server.last_health_check.isoformat() if server.last_health_check else None,
                'created_at': server.created_at.isoformat() if server.created_at else None,
                'connection_status': connection_status,
                'network_zone': getattr(server, 'network_zone', 'production'),
                'monitoring_enabled': getattr(server, 'monitoring_enabled', True),
                'backup_enabled': getattr(server, 'backup_enabled', True),
                'internal_ip': getattr(server, 'internal_ip', server.ip_address),
                'external_ip': getattr(server, 'external_ip', server.ip_address)
            }
            server_list.append(server_data)
        
        # Group servers by status for summary
        status_summary = {}
        for server in server_list:
            status = server['status']
            if status not in status_summary:
                status_summary[status] = 0
            status_summary[status] += 1
        
        return jsonify({
            'success': True,
            'servers': server_list,
            'total_servers': len(server_list),
            'status_summary': status_summary,
            'online_servers': len([s for s in server_list if s['connection_status'] == 'online']),
            'worker_capable_servers': len([s for s in server_list if 'odoo_worker' in s['service_roles']])
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

@system_admin_bp.route('/api/vps/servers/<int:server_id>/connect', methods=['POST'])
@login_required
@require_super_admin()
@track_errors('connect_to_vps_server')
def connect_to_vps_server(server_id):
    """Test connection to specific VPS server and get system info"""
    try:
        # InfrastructureServer already imported at top
        
        server = InfrastructureServer.query.get(server_id)
        if not server:
            return jsonify({'success': False, 'message': 'Server not found'}), 404
        
        # Import SSH connection function from infra_admin
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from infra_admin import test_ssh_connection, decrypt_password
        
        # Test SSH connection with detailed info
        password = decrypt_password(server.password) if server.password else None
        
        connection_result = test_ssh_connection(
            ip=server.ip_address,
            username=server.username,
            password=password,
            key_path=server.ssh_key_path,
            port=server.port or 22,
            debug=True
        )
        
        if connection_result['success']:
            # Update server status and health check
            server.last_health_check = datetime.utcnow()
            server.status = 'active'
            server.health_score = 100
            db.session.commit()
            
            log_system_action('vps_connection_test', {
                'server_id': server_id,
                'server_name': server.name,
                'ip_address': server.ip_address,
                'success': True
            })
        
        return jsonify({
            'success': connection_result['success'],
            'server_info': connection_result,
            'server_name': server.name,
            'ip_address': server.ip_address
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id, 'server_id': server_id})
        return jsonify({'success': False, 'message': str(e)}), 500

@system_admin_bp.route('/api/vps/servers/<int:server_id>/workers')
@login_required
@require_super_admin()
@track_errors('get_vps_server_workers')
def get_vps_server_workers(server_id):
    """Get list of workers running on specific VPS server"""
    try:
        # InfrastructureServer already imported at top
        
        server = InfrastructureServer.query.get(server_id)
        if not server:
            return jsonify({'success': False, 'message': 'Server not found'}), 404
        
        # Get workers associated with this server
        workers = WorkerInstance.query.filter_by(server_id=server_id).all()
        
        worker_list = []
        for worker in workers:
            worker_data = {
                'id': worker.id,
                'name': worker.name,
                'container_name': worker.container_name,
                'port': worker.port,
                'status': worker.status,
                'current_tenants': worker.current_tenants,
                'max_tenants': worker.max_tenants,
                'created_at': worker.created_at.isoformat() if worker.created_at else None,
                'last_seen': worker.last_seen.isoformat() if worker.last_seen else None,
                'db_host': getattr(worker, 'db_host', None),
                'db_port': getattr(worker, 'db_port', None),
                'load_percentage': round((worker.current_tenants / worker.max_tenants * 100), 1) if worker.max_tenants > 0 else 0
            }
            worker_list.append(worker_data)
        
        return jsonify({
            'success': True,
            'server_name': server.name,
            'server_ip': server.ip_address,
            'workers': worker_list,
            'total_workers': len(worker_list),
            'running_workers': len([w for w in worker_list if w['status'] == 'running']),
            'total_tenants': sum(w['current_tenants'] for w in worker_list),
            'total_capacity': sum(w['max_tenants'] for w in worker_list)
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id, 'server_id': server_id})
        return jsonify({'success': False, 'message': str(e)}), 500

@system_admin_bp.route('/api/vps/servers/<int:server_id>/execute', methods=['POST'])
@login_required
@require_super_admin()
@track_errors('execute_command_on_vps')
def execute_command_on_vps(server_id):
    """Execute command on VPS server"""
    try:
        # InfrastructureServer already imported at top
        
        server = InfrastructureServer.query.get(server_id)
        if not server:
            return jsonify({'success': False, 'message': 'Server not found'}), 404
        
        data = request.json
        command = data.get('command', '').strip()
        
        if not command:
            return jsonify({'success': False, 'message': 'Command is required'}), 400
        
        # Security check - only allow safe commands
        dangerous_commands = ['rm -rf', 'format', 'mkfs', 'dd if=', 'shutdown', 'reboot', '> /dev/', 'rm -f']
        if any(dangerous in command.lower() for dangerous in dangerous_commands):
            return jsonify({'success': False, 'message': 'Command not allowed for security reasons'}), 400
        
        # Import SSH functions
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from infra_admin import setup_ssh_connection, decrypt_password
        
        # Establish SSH connection
        ssh_client = setup_ssh_connection(server)
        if not ssh_client:
            return jsonify({'success': False, 'message': 'Could not establish SSH connection'}), 500
        
        try:
            # Execute command
            stdin, stdout, stderr = ssh_client.exec_command(command, timeout=30)
            
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')
            exit_code = stdout.channel.recv_exit_status()
            
            ssh_client.close()
            
            log_system_action('vps_command_execution', {
                'server_id': server_id,
                'server_name': server.name,
                'command': command[:100],  # Log first 100 chars
                'exit_code': exit_code,
                'success': exit_code == 0
            })
            
            return jsonify({
                'success': True,
                'command': command,
                'output': output,
                'error': error,
                'exit_code': exit_code,
                'server_name': server.name
            })
            
        except Exception as e:
            ssh_client.close()
            return jsonify({'success': False, 'message': f'Command execution failed: {str(e)}'}), 500
        
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id, 'server_id': server_id})
        return jsonify({'success': False, 'message': str(e)}), 500

@system_admin_bp.route('/api/vps/servers/health-check', methods=['POST'])
@login_required
@require_super_admin()
@track_errors('bulk_health_check_vps')
def bulk_health_check_vps():
    """Perform health check on all VPS servers"""
    try:
        # InfrastructureServer already imported at top
        # ThreadPoolExecutor already imported at top
        
        servers = InfrastructureServer.query.all()
        
        def check_single_server(server):
            try:
                connection_status = test_server_connection(server)
                
                # Update server health
                if connection_status == 'online':
                    server.last_health_check = datetime.utcnow()
                    server.health_score = 100
                    server.status = 'active'
                else:
                    server.health_score = max(0, (server.health_score or 100) - 20)
                    if server.health_score <= 0:
                        server.status = 'offline'
                
                return {
                    'id': server.id,
                    'name': server.name,
                    'ip_address': server.ip_address,
                    'status': connection_status,
                    'health_score': server.health_score
                }
            except Exception as e:
                return {
                    'id': server.id,
                    'name': server.name,
                    'ip_address': server.ip_address,
                    'status': 'error',
                    'error': str(e)
                }
        
        # Use thread pool for parallel health checks (max 5 concurrent connections)
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(check_single_server, servers))
        
        # Commit all changes
        db.session.commit()
        
        # Summarize results
        online_count = len([r for r in results if r.get('status') == 'online'])
        offline_count = len([r for r in results if r.get('status') in ['offline', 'error']])
        
        log_system_action('bulk_vps_health_check', {
            'total_servers': len(servers),
            'online_servers': online_count,
            'offline_servers': offline_count
        })
        
        return jsonify({
            'success': True,
            'results': results,
            'summary': {
                'total_servers': len(servers),
                'online_servers': online_count,
                'offline_servers': offline_count,
                'health_check_time': datetime.utcnow().isoformat()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

# ================= HELPER FUNCTIONS FOR VPS =================

def test_server_connection(server):
    """Test basic connection to server (ping-like check)"""
    try:
        import socket
        
        # Test basic network connectivity
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        
        result = sock.connect_ex((server.ip_address, server.port or 22))
        sock.close()
        
        if result == 0:
            return 'online'
        else:
            return 'offline'
            
    except Exception:
        return 'error'

@system_admin_bp.route('/api/debug/containers')
@login_required
@require_super_admin()
def debug_containers():
    """Debug endpoint to check what containers exist"""
    try:
        if not docker_client:
            return jsonify({'success': False, 'message': 'Docker not available'})
        
        containers = docker_client.containers.list(all=True)
        container_info = []
        
        for container in containers:
            container_info.append({
                'name': container.name,
                'status': container.status,
                'image': container.image.tags[0] if container.image.tags else 'unknown',
                'is_odoo_worker': ('odoo' in container.name.lower() and 'worker' in container.name.lower()) or container.name.startswith('odoo_worker') or container.name.startswith('test')
            })
        
        # Also check database workers
        db_workers = WorkerInstance.query.all()
        db_worker_info = [{'id': w.id, 'name': w.name, 'container_name': w.container_name, 'status': w.status} for w in db_workers]
        
        return jsonify({
            'success': True,
            'total_containers': len(containers),
            'containers': container_info,
            'db_workers': db_worker_info,
            'docker_available': docker_client is not None
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})