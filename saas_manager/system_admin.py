# Standard library imports
import json
import logging
import os
import subprocess
from datetime import datetime, timedelta

# Third-party imports
import docker
import psutil
import psycopg2
import redis
import requests
from flask import Blueprint, render_template, jsonify, request, redirect, url_for
from flask_login import login_required, current_user
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import text, func

# Local application imports
from db import db
from models import SaasUser, Tenant, WorkerInstance, AuditLog
from OdooDatabaseManager import OdooDatabaseManager
from utils import track_errors, error_tracker
system_admin_bp = Blueprint('system_admin', __name__, url_prefix='/system-admin')

# Initialize connections
redis_client = None
docker_client = None

try:
    redis_client = redis.Redis.from_url(os.environ.get('REDIS_URL', 'redis://redis:6379/0'))
    redis_client.ping()
except:
    redis_client = None

try:
    docker_client = docker.from_env()
    docker_client.ping()
except:
    docker_client = None

def require_super_admin():
    """Decorator for super admin access"""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.is_admin:
                return jsonify({'success': False, 'message': 'Super admin access required'}), 403
            # Add additional super admin check here if needed
            return fn(*args, **kwargs)
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator

def log_system_action(action, details=None):
    """Log system admin actions"""
    try:
        audit_log = AuditLog(
            user_id=current_user.id,
            action=f"SYSTEM: {action}",
            details=details,
            ip_address=request.remote_addr
        )
        db.session.add(audit_log)
        db.session.commit()
    except Exception as e:
        print(f"[SYSTEM LOG ERROR] {e}")

# ================= MAIN DASHBOARD =================

@system_admin_bp.route('/dashboard')
@login_required
@require_super_admin()
@track_errors('system_admin_dashboard')
def dashboard():
    """System Admin Dashboard"""
    return render_template('system_admin/dashboard.html')

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
                   print(f"Cleaned up {len(orphaned_workers)} orphaned worker records")
                   
           except Exception as e:
               print(f"Database cleanup failed: {e}")
           
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
                   except:
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
                   except:
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
                           print(f"Auto-created DB record for container: {container.name}")
                       except Exception as e:
                           print(f"Failed to create DB record for {container.name}: {e}")
                   
                   # Update status if database record exists
                   if db_worker and db_worker.status != container.status:
                       try:
                           db_worker.status = container.status
                           db.session.commit()
                       except Exception as e:
                           print(f"Failed to update status for {container.name}: {e}")
                   
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
    """Create a new worker container"""
    try:
        data = request.json
        worker_name = data.get('name', f"odoo_worker_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        worker_port = data.get('port', 8069)
        max_tenants = data.get('max_tenants', 10)
        
        if not docker_client:
            return jsonify({'success': False, 'message': 'Docker not available'}), 500
        
        # Get the correct network name from existing containers
        network_name = None
        try:
            # Look for the network used by existing odoo containers
            for container in docker_client.containers.list():
                if 'odoo' in container.name.lower():
                    networks = container.attrs['NetworkSettings']['Networks']
                    for net_name in networks.keys():
                        if 'odoo' in net_name.lower():
                            network_name = net_name
                            break
                    if network_name:
                        break
            
            # Fallback: list all networks and find the odoo one
            if not network_name:
                for network in docker_client.networks.list():
                    if 'odoo' in network.name.lower():
                        network_name = network.name
                        break
        except Exception as e:
            print(f"Warning: Could not determine network name: {e}")
        
        # Create container
        container = docker_client.containers.create(
            'odoo:17.0',
            name=worker_name,
            environment={
                'HOST': 'postgres',
                'USER': 'odoo_master',
                'PASSWORD': 'secure_password_123'
            },
            volumes={
                'odoomulti-tenantsystem_odoo_filestore': {'bind': '/var/lib/odoo', 'mode': 'rw'},
                'odoomulti-tenantsystem_odoo_worker_logs': {'bind': '/var/log/odoo', 'mode': 'rw'}
            },
            command=f'odoo -c /etc/odoo/odoo.conf --logfile=/var/log/odoo/{worker_name}.log',
            restart_policy={'Name': 'unless-stopped'}
        )
        
        # Connect to network if found
        if network_name:
            try:
                network = docker_client.networks.get(network_name)
                network.connect(container)
                print(f"Connected to network: {network_name}")
            except Exception as e:
                print(f"Warning: Could not connect to network {network_name}: {e}")
        
        # Start the container
        container.start()
        
        # Add to database
        db_worker = WorkerInstance(
            name=worker_name,
            container_name=worker_name,
            port=worker_port,
            max_tenants=max_tenants,
            status='running'
        )
        db.session.add(db_worker)
        db.session.commit()
        
        log_system_action('worker_created', {
            'worker_name': worker_name,
            'container_id': container.id,
            'max_tenants': max_tenants,
            'network': network_name
        })
        
        return jsonify({
            'success': True, 
            'message': f'Worker {worker_name} created successfully',
            'container_id': container.id,
            'worker_id': db_worker.id,
            'network': network_name
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

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
            except:
                pass
        
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
                       print(f"Failed to get stats for {container.name}: {e}")
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
               print(f"Failed to get container stats: {e}")

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

def calculate_cpu_percent(stats):
    """Calculate CPU percentage from Docker stats"""
    try:
        cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                   stats['precpu_stats']['cpu_usage']['total_usage']
        system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                      stats['precpu_stats']['system_cpu_usage']
        
        if system_delta > 0:
            cpu_percent = (cpu_delta / system_delta) * len(stats['cpu_stats']['cpu_usage']['percpu_usage']) * 100
            return round(cpu_percent, 2)
        return 0
    except:
        return 0

def check_worker_health(container_name):
    """Check if worker is healthy"""
    try:
        if not docker_client:
            return False
        
        container = docker_client.containers.get(container_name)
        if container.status != 'running':
            return False
        
        # Try to access health endpoint
        try:
            health_check = container.exec_run('curl -f http://localhost:8069/web/health')
            return health_check.exit_code == 0
        except:
            return container.status == 'running'
            
    except:
        return False