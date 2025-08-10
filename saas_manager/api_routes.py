"""
Worker Management API Routes

This module provides RESTful API endpoints for worker management
that match the frontend expectations and provide consistent interfaces.
"""

import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user

from db import db
from models import WorkerInstance, InfrastructureServer, AuditLog
from services import UnifiedWorkerService
from services.nginx_service import NginxLoadBalancerService
from services.remote_worker_service import RemoteWorkerService
from shared_utils import get_docker_client
from utils import track_errors

# Create blueprint for API routes
api_bp = Blueprint('api', __name__)
logger = logging.getLogger(__name__)


def require_admin():
    """Decorator to require admin access"""
    def decorator(f):
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.is_admin:
                return jsonify({'success': False, 'error': 'Admin access required'}), 403
            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator


# ================= WORKER CRUD OPERATIONS =================

@api_bp.route('/api/worker', methods=['GET'])
@login_required
@require_admin()
@track_errors('api_list_workers')
def list_workers():
    """Get all workers with detailed information"""
    try:
        workers = WorkerInstance.query.all()
        docker_client = get_docker_client()
        
        workers_data = []
        for worker in workers:
            worker_info = {
                'id': worker.id,
                'name': worker.name,
                'container_name': worker.container_name,
                'port': worker.port,
                'max_tenants': worker.max_tenants,
                'current_tenants': getattr(worker, 'current_tenants', 0),
                'status': worker.status,
                'created_at': worker.created_at.isoformat() if worker.created_at else None,
                'last_health_check': worker.last_health_check.isoformat() if getattr(worker, 'last_health_check', None) else None,
                'server_id': getattr(worker, 'server_id', None)
            }
            
            # Get real-time Docker status if available
            if docker_client:
                try:
                    container = docker_client.containers.get(worker.container_name)
                    worker_info['docker_status'] = container.status
                    worker_info['docker_created'] = container.attrs['Created']
                    
                    # Get basic stats
                    if container.status == 'running':
                        stats = container.stats(stream=False)
                        worker_info['stats'] = {
                            'cpu_percent': _calculate_cpu_percent(stats),
                            'memory_usage': stats['memory_stats'].get('usage', 0),
                            'memory_limit': stats['memory_stats'].get('limit', 0)
                        }
                except Exception as e:
                    logger.warning(f"Failed to get Docker info for {worker.name}: {e}")
                    worker_info['docker_status'] = 'unknown'
            
            workers_data.append(worker_info)
        
        return jsonify({
            'success': True,
            'workers': workers_data,
            'total': len(workers_data)
        })
        
    except Exception as e:
        logger.error(f"Failed to list workers: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/api/worker/<int:worker_id>', methods=['GET'])
@login_required
@require_admin()
@track_errors('api_get_worker')
def get_worker(worker_id):
    """Get detailed information about a specific worker"""
    try:
        worker = WorkerInstance.query.get(worker_id)
        if not worker:
            return jsonify({'success': False, 'error': 'Worker not found'}), 404
        
        worker_info = {
            'id': worker.id,
            'name': worker.name,
            'container_name': worker.container_name,
            'port': worker.port,
            'max_tenants': worker.max_tenants,
            'current_tenants': getattr(worker, 'current_tenants', 0),
            'status': worker.status,
            'created_at': worker.created_at.isoformat() if worker.created_at else None,
            'last_health_check': worker.last_health_check.isoformat() if getattr(worker, 'last_health_check', None) else None,
            'server_id': getattr(worker, 'server_id', None)
        }
        
        # Get Docker information
        docker_client = get_docker_client()
        if docker_client:
            try:
                container = docker_client.containers.get(worker.container_name)
                worker_info['docker_info'] = {
                    'status': container.status,
                    'created': container.attrs['Created'],
                    'image': container.attrs['Config']['Image'],
                    'ports': container.attrs['NetworkSettings'].get('Ports', {}),
                    'networks': list(container.attrs['NetworkSettings'].get('Networks', {}).keys())
                }
                
                # Get detailed stats if running
                if container.status == 'running':
                    stats = container.stats(stream=False)
                    worker_info['detailed_stats'] = {
                        'cpu_percent': _calculate_cpu_percent(stats),
                        'memory_usage': stats['memory_stats'].get('usage', 0),
                        'memory_limit': stats['memory_stats'].get('limit', 0),
                        'network_rx': stats['networks'].get('eth0', {}).get('rx_bytes', 0) if 'networks' in stats else 0,
                        'network_tx': stats['networks'].get('eth0', {}).get('tx_bytes', 0) if 'networks' in stats else 0
                    }
            except Exception as e:
                worker_info['docker_error'] = str(e)
        
        return jsonify(worker_info)
        
    except Exception as e:
        logger.error(f"Failed to get worker {worker_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/api/worker', methods=['POST'])
@login_required
@require_admin()
@track_errors('api_create_worker')
def create_worker():
    print("Creating worker with unified service")
    """Create a new worker using the unified service"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        # Use the unified worker service
        worker_service = UnifiedWorkerService()
        
        # Check if this is a remote worker deployment
        if 'server_id' in data and data['server_id']:
            result = worker_service.create_remote_worker(
                data=data,
                user_id=current_user.id,
                ip_address=request.remote_addr
            )
        else:
            result = worker_service.create_local_worker(
                data=data,
                user_id=current_user.id,
                ip_address=request.remote_addr
            )
        
        # If worker creation was successful, add to nginx load balancer
        if result['success'] and 'worker_details' in result:
            try:
                nginx_service = NginxLoadBalancerService()
                worker_details = result['worker_details']
                
                # Add worker to load balancer (assuming local container)
                nginx_result = nginx_service.add_worker(
                    worker_ip=worker_details.get('name', 'localhost'),  # Use container name for Docker networks
                    worker_port=8069,  # Internal Odoo port
                    worker_name=worker_details['name']
                )
                
                if nginx_result['success']:
                    result['load_balancer'] = 'added'
                    logger.info(f"Worker {worker_details['name']} added to load balancer")
                else:
                    result['load_balancer'] = 'failed'
                    result['load_balancer_error'] = nginx_result.get('error', 'Unknown error')
                    logger.warning(f"Failed to add worker {worker_details['name']} to load balancer: {nginx_result.get('error')}")
                    
            except Exception as nginx_error:
                logger.warning(f"Nginx integration failed: {nginx_error}")
                result['load_balancer'] = 'error'
                result['load_balancer_error'] = str(nginx_error)
        
        status_code = 201 if result['success'] else 400
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"Failed to create worker: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/api/worker/<int:worker_id>', methods=['PUT'])
@login_required
@require_admin()
@track_errors('api_update_worker')
def update_worker(worker_id):
    """Update worker configuration"""
    try:
        worker = WorkerInstance.query.get(worker_id)
        if not worker:
            return jsonify({'success': False, 'error': 'Worker not found'}), 404
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        # Update worker fields
        if 'name' in data:
            worker.name = data['name']
        if 'max_tenants' in data:
            worker.max_tenants = int(data['max_tenants'])
        if 'port' in data:
            worker.port = int(data['port'])
        
        db.session.commit()
        
        # Log the update
        audit_log = AuditLog(
            user_id=current_user.id,
            action=f"WORKER_UPDATED: {worker.name}",
            details={
                'worker_id': worker.id,
                'changes': data
            },
            ip_address=request.remote_addr
        )
        db.session.add(audit_log)
        db.session.commit()
        
        logger.info(f"Worker {worker.name} updated by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': f'Worker {worker.name} updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update worker {worker_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/api/worker/<int:worker_id>', methods=['DELETE'])
@login_required
@require_admin()
@track_errors('api_delete_worker')
def delete_worker(worker_id):
    """Delete a worker and its container"""
    try:
        worker = WorkerInstance.query.get(worker_id)
        if not worker:
            return jsonify({'success': False, 'error': 'Worker not found'}), 404
        
        worker_name = worker.name
        container_name = worker.container_name
        
        # Stop and remove Docker container
        docker_client = get_docker_client()
        if docker_client:
            try:
                container = docker_client.containers.get(container_name)
                container.stop(timeout=10)
                container.remove()
                logger.info(f"Stopped and removed container {container_name}")
            except Exception as docker_error:
                logger.warning(f"Failed to remove container {container_name}: {docker_error}")
        
        # Remove from nginx load balancer
        try:
            nginx_service = NginxLoadBalancerService()
            nginx_result = nginx_service.remove_worker(
                worker_ip=worker_name,  # Use worker name to match
                worker_name=worker_name
            )
            if nginx_result['success']:
                logger.info(f"Removed worker {worker_name} from load balancer")
        except Exception as nginx_error:
            logger.warning(f"Failed to remove worker from load balancer: {nginx_error}")
        
        # Delete from database
        db.session.delete(worker)
        
        # Log the deletion
        audit_log = AuditLog(
            user_id=current_user.id,
            action=f"WORKER_DELETED: {worker_name}",
            details={
                'worker_id': worker_id,
                'container_name': container_name
            },
            ip_address=request.remote_addr
        )
        db.session.add(audit_log)
        db.session.commit()
        
        logger.info(f"Worker {worker_name} deleted by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': f'Worker {worker_name} deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete worker {worker_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ================= WORKER ACTIONS =================

@api_bp.route('/api/worker/<int:worker_id>/start', methods=['POST'])
@login_required
@require_admin()
@track_errors('api_start_worker')
def start_worker(worker_id):
    """Start a worker container"""
    return _worker_action(worker_id, 'start')


@api_bp.route('/api/worker/<int:worker_id>/stop', methods=['POST'])
@login_required
@require_admin()
@track_errors('api_stop_worker')
def stop_worker(worker_id):
    """Stop a worker container"""
    return _worker_action(worker_id, 'stop')


@api_bp.route('/api/worker/<int:worker_id>/restart', methods=['POST'])
@login_required
@require_admin()
@track_errors('api_restart_worker')
def restart_worker(worker_id):
    """Restart a worker container"""
    return _worker_action(worker_id, 'restart')


@api_bp.route('/api/worker/<int:worker_id>/health-check', methods=['POST'])
@login_required
@require_admin()
@track_errors('api_health_check_worker')
def health_check_worker(worker_id):
    """Perform health check on worker"""
    try:
        worker = WorkerInstance.query.get(worker_id)
        if not worker:
            return jsonify({'success': False, 'error': 'Worker not found'}), 404
        
        docker_client = get_docker_client()
        if not docker_client:
            return jsonify({'success': False, 'error': 'Docker not available'}), 500
        
        try:
            container = docker_client.containers.get(worker.container_name)
            
            if container.status == 'running':
                # Try to access health endpoint
                health_check = container.exec_run(
                    'curl -f -m 5 http://localhost:8069/web/health',
                    timeout=10
                )
                
                if health_check.exit_code == 0:
                    status = 'healthy'
                    worker.status = 'running'
                    worker.last_health_check = datetime.utcnow()
                else:
                    status = 'unhealthy'
                    worker.status = 'error'
            else:
                status = 'stopped'
                worker.status = 'stopped'
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'status': status,
                'container_status': container.status
            })
            
        except Exception as container_error:
            logger.error(f"Container error during health check: {container_error}")
            worker.status = 'error'
            db.session.commit()
            
            return jsonify({
                'success': False,
                'error': f'Container error: {str(container_error)}'
            }), 500
            
    except Exception as e:
        logger.error(f"Health check failed for worker {worker_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


def _worker_action(worker_id: int, action: str):
    """Common function for worker actions"""
    try:
        worker = WorkerInstance.query.get(worker_id)
        if not worker:
            return jsonify({'success': False, 'error': 'Worker not found'}), 404
        
        docker_client = get_docker_client()
        if not docker_client:
            return jsonify({'success': False, 'error': 'Docker not available'}), 500
        
        try:
            container = docker_client.containers.get(worker.container_name)
            
            if action == 'start':
                container.start()
                worker.status = 'running'
                message = f'Worker {worker.name} started successfully'
            elif action == 'stop':
                container.stop(timeout=10)
                worker.status = 'stopped'
                message = f'Worker {worker.name} stopped successfully'
            elif action == 'restart':
                container.restart(timeout=10)
                worker.status = 'running'
                message = f'Worker {worker.name} restarted successfully'
            else:
                return jsonify({'success': False, 'error': f'Unknown action: {action}'}), 400
            
            db.session.commit()
            
            # Log the action
            audit_log = AuditLog(
                user_id=current_user.id,
                action=f"WORKER_{action.upper()}: {worker.name}",
                details={'worker_id': worker.id},
                ip_address=request.remote_addr
            )
            db.session.add(audit_log)
            db.session.commit()
            
            logger.info(f"Worker {worker.name} {action} completed by user {current_user.id}")
            
            return jsonify({
                'success': True,
                'message': message
            })
            
        except Exception as container_error:
            logger.error(f"Container {action} failed: {container_error}")
            return jsonify({
                'success': False,
                'error': f'Container {action} failed: {str(container_error)}'
            }), 500
            
    except Exception as e:
        logger.error(f"Worker {action} failed for {worker_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ================= NGINX LOAD BALANCER MANAGEMENT =================

@api_bp.route('/api/load-balancer/status', methods=['GET'])
@login_required
@require_admin()
@track_errors('api_load_balancer_status')
def load_balancer_status():
    """Get nginx load balancer status"""
    try:
        nginx_service = NginxLoadBalancerService()
        return jsonify(nginx_service.get_upstream_status())
    except Exception as e:
        logger.error(f"Failed to get load balancer status: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/api/load-balancer/reload', methods=['POST'])
@login_required
@require_admin()
@track_errors('api_reload_load_balancer')
def reload_load_balancer():
    """Manually reload nginx load balancer"""
    try:
        nginx_service = NginxLoadBalancerService()
        result = nginx_service.reload_nginx()
        
        # Log the action
        audit_log = AuditLog(
            user_id=current_user.id,
            action="NGINX_RELOAD",
            details={'manual_reload': True},
            ip_address=request.remote_addr
        )
        db.session.add(audit_log)
        db.session.commit()
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Failed to reload load balancer: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ================= REMOTE WORKER MANAGEMENT =================

@api_bp.route('/api/worker/<worker_name>/status', methods=['GET'])
@login_required
@require_admin()
@track_errors('get_remote_worker_status')
def get_remote_worker_status(worker_name):
    """Get detailed status of a remote worker"""
    try:
        worker = WorkerInstance.query.filter_by(name=worker_name).first()
        if not worker:
            return jsonify({'success': False, 'message': 'Worker not found'}), 404
        
        # If it's a remote worker, get detailed status
        if worker.server_id:
            remote_worker_service = RemoteWorkerService()
            status = remote_worker_service.get_remote_worker_status(worker_name)
            return jsonify(status)
        
        # For local workers, fall back to basic info
        return jsonify({
            'success': True,
            'worker_name': worker.name,
            'server_name': 'Local',
            'server_ip': 'localhost',
            'port': worker.port,
            'status': worker.status,
            'container_status': worker.status,
            'health_status': 'Unknown',
            'last_checked': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Failed to get worker status for {worker_name}: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@api_bp.route('/api/worker/<worker_name>/stop', methods=['POST'])
@login_required
@require_admin()
@track_errors('stop_remote_worker')
def stop_remote_worker(worker_name):
    """Stop a remote worker"""
    try:
        worker = WorkerInstance.query.filter_by(name=worker_name).first()
        if not worker:
            return jsonify({'success': False, 'message': 'Worker not found'}), 404
        
        if worker.server_id:
            # Remote worker
            remote_worker_service = RemoteWorkerService()
            result = remote_worker_service.stop_remote_worker(worker_name, current_user.id)
            return jsonify(result)
        else:
            # Local worker - use existing Docker management
            docker_client = get_docker_client()
            if not docker_client:
                return jsonify({'success': False, 'message': 'Docker not available'}), 500
            
            container = docker_client.containers.get(worker_name)
            container.stop()
            
            worker.status = 'stopped'
            db.session.commit()
            
            return jsonify({'success': True, 'message': f'Worker {worker_name} stopped successfully'})
        
    except Exception as e:
        logger.error(f"Failed to stop worker {worker_name}: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@api_bp.route('/api/worker/<worker_name>/start', methods=['POST'])
@login_required
@require_admin()
@track_errors('start_remote_worker')
def start_remote_worker(worker_name):
    """Start a remote worker"""
    try:
        worker = WorkerInstance.query.filter_by(name=worker_name).first()
        if not worker:
            return jsonify({'success': False, 'message': 'Worker not found'}), 404
        
        if worker.server_id:
            # For remote workers, we need to start via SSH
            server = InfrastructureServer.query.get(worker.server_id)
            if not server:
                return jsonify({'success': False, 'message': 'Server not found'}), 404
            
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect to server
            if server.ssh_key_path:
                client.connect(server.ip_address, server.port, server.username, 
                             key_filename=server.ssh_key_path, timeout=30)
            else:
                client.connect(server.ip_address, server.port, server.username, 
                             password=server.password, timeout=30)
            
            # Start the container
            stdin, stdout, stderr = client.exec_command(f"docker start {worker_name}")
            exit_code = stdout.channel.recv_exit_status()
            
            client.close()
            
            if exit_code == 0:
                worker.status = 'running'
                db.session.commit()
                return jsonify({'success': True, 'message': f'Worker {worker_name} started successfully'})
            else:
                error = stderr.read().decode('utf-8')
                return jsonify({'success': False, 'message': f'Failed to start worker: {error}'})
        else:
            # Local worker
            docker_client = get_docker_client()
            if not docker_client:
                return jsonify({'success': False, 'message': 'Docker not available'}), 500
            
            container = docker_client.containers.get(worker_name)
            container.start()
            
            worker.status = 'running'
            db.session.commit()
            
            return jsonify({'success': True, 'message': f'Worker {worker_name} started successfully'})
        
    except Exception as e:
        logger.error(f"Failed to start worker {worker_name}: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@api_bp.route('/api/worker/<worker_name>/restart', methods=['POST'])
@login_required
@require_admin()
@track_errors('restart_remote_worker')
def restart_remote_worker(worker_name):
    """Restart a remote worker"""
    try:
        worker = WorkerInstance.query.filter_by(name=worker_name).first()
        if not worker:
            return jsonify({'success': False, 'message': 'Worker not found'}), 404
        
        if worker.server_id:
            # For remote workers, restart via SSH
            server = InfrastructureServer.query.get(worker.server_id)
            if not server:
                return jsonify({'success': False, 'message': 'Server not found'}), 404
            
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect to server
            if server.ssh_key_path:
                client.connect(server.ip_address, server.port, server.username, 
                             key_filename=server.ssh_key_path, timeout=30)
            else:
                client.connect(server.ip_address, server.port, server.username, 
                             password=server.password, timeout=30)
            
            # Restart the container
            stdin, stdout, stderr = client.exec_command(f"docker restart {worker_name}")
            exit_code = stdout.channel.recv_exit_status()
            
            client.close()
            
            if exit_code == 0:
                worker.status = 'running'
                db.session.commit()
                return jsonify({'success': True, 'message': f'Worker {worker_name} restarted successfully'})
            else:
                error = stderr.read().decode('utf-8')
                return jsonify({'success': False, 'message': f'Failed to restart worker: {error}'})
        else:
            # Local worker
            docker_client = get_docker_client()
            if not docker_client:
                return jsonify({'success': False, 'message': 'Docker not available'}), 500
            
            container = docker_client.containers.get(worker_name)
            container.restart()
            
            return jsonify({'success': True, 'message': f'Worker {worker_name} restarted successfully'})
        
    except Exception as e:
        logger.error(f"Failed to restart worker {worker_name}: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ================= UTILITY FUNCTIONS =================

def _calculate_cpu_percent(stats):
    """Calculate CPU percentage from Docker stats"""
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
    except (KeyError, TypeError, ZeroDivisionError):
        return 0.0


# Export blueprint
__all__ = ['api_bp']