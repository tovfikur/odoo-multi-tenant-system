"""
Remote Worker Management Service

Handles deployment, management, and monitoring of Odoo workers on remote VPS servers.
Integrates with InfrastructureServer model and provides comprehensive remote worker lifecycle management.
"""

import logging
import paramiko
import time
import json
import subprocess
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass

from models import db, InfrastructureServer, WorkerInstance, AuditLog
from services.nginx_service import NginxLoadBalancerService
from shared_utils import log_action
from utils import track_errors, error_tracker

logger = logging.getLogger(__name__)


@dataclass
class RemoteWorkerConfig:
    """Configuration for remote worker deployment"""
    name: str
    server_id: int
    port: int
    max_tenants: int
    cpu_cores: Optional[int] = None
    memory_gb: Optional[int] = None
    postgres_host: Optional[str] = None
    postgres_port: Optional[int] = 5432
    postgres_db: Optional[str] = None
    postgres_user: Optional[str] = None
    postgres_password: Optional[str] = None
    addons_path: Optional[str] = '/mnt/extra-addons'
    data_dir: Optional[str] = '/var/lib/odoo'
    log_level: Optional[str] = 'info'
    environment_vars: Optional[Dict[str, str]] = None


class RemoteWorkerService:
    """Service for managing Odoo workers on remote VPS servers"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.nginx_service = NginxLoadBalancerService()
        self.ssh_timeout = 30
        self.deployment_timeout = 300  # 5 minutes
        
    def create_remote_worker(self, config: RemoteWorkerConfig, user_id: int, 
                           ip_address: str = None) -> Dict[str, Any]:
        """
        Deploy a new Odoo worker on a remote VPS server
        
        Args:
            config: Remote worker configuration
            user_id: ID of the user creating the worker
            ip_address: IP address of the request
            
        Returns:
            Dict containing operation result
        """
        try:
            # Get server details
            server = InfrastructureServer.query.get(config.server_id)
            if not server:
                return {'success': False, 'message': 'Server not found'}
            
            if server.status != 'active':
                return {'success': False, 'message': 'Server is not active'}
            
            self.logger.info(f"Starting remote worker deployment: {config.name} on {server.name}")
            
            # Check if worker name already exists
            existing_worker = WorkerInstance.query.filter_by(name=config.name).first()
            if existing_worker:
                return {'success': False, 'message': f'Worker {config.name} already exists'}
            
            # Test server connection first
            connection_test = self._test_server_connection(server)
            if not connection_test['success']:
                return connection_test
            
            # Deploy worker on remote server
            deployment_result = self._deploy_odoo_worker(server, config)
            if not deployment_result['success']:
                return deployment_result
            
            # Create database record
            db_worker = self._create_worker_record(config, server, deployment_result)
            
            # Add to nginx load balancer
            nginx_result = self._add_to_load_balancer(server, config, deployment_result)
            
            # Log the action
            self._log_worker_action(
                user_id, 'WORKER: remote_worker_created', 
                {
                    'worker_name': config.name,
                    'server_name': server.name,
                    'server_ip': server.ip_address,
                    'port': config.port,
                    'max_tenants': config.max_tenants
                },
                ip_address
            )
            
            self.logger.info(f"Successfully created remote worker: {config.name}")
            
            return {
                'success': True,
                'message': f'Remote worker {config.name} deployed successfully',
                'worker_id': db_worker.id,
                'server_name': server.name,
                'server_ip': server.ip_address,
                'worker_url': f"http://{server.ip_address}:{config.port}",
                'nginx_status': nginx_result.get('message', 'Not added to load balancer'),
                'deployment_details': deployment_result.get('details', {})
            }
            
        except Exception as e:
            error_tracker.log_error(e, {'user_id': user_id, 'server_id': config.server_id})
            self.logger.error(f"Failed to create remote worker {config.name}: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def _test_server_connection(self, server: InfrastructureServer) -> Dict[str, Any]:
        """Test SSH connection to remote server"""
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            connect_kwargs = {
                'hostname': server.ip_address,
                'port': server.port,
                'username': server.username,
                'timeout': self.ssh_timeout
            }
            
            # Use SSH key if available, otherwise password
            if server.ssh_key_path and server.ssh_key_path.strip():
                connect_kwargs['key_filename'] = server.ssh_key_path
            else:
                connect_kwargs['password'] = server.password  # This should be decrypted
            
            client.connect(**connect_kwargs)
            
            # Test basic command execution
            stdin, stdout, stderr = client.exec_command('echo "Connection test successful"')
            output = stdout.read().decode('utf-8').strip()
            
            client.close()
            
            if "Connection test successful" in output:
                return {'success': True, 'message': 'Server connection verified'}
            else:
                return {'success': False, 'message': 'Server connection test failed'}
                
        except Exception as e:
            self.logger.error(f"Server connection test failed for {server.name}: {str(e)}")
            return {'success': False, 'message': f'Connection failed: {str(e)}'}
    
    def _deploy_odoo_worker(self, server: InfrastructureServer, 
                           config: RemoteWorkerConfig) -> Dict[str, Any]:
        """Deploy Odoo worker container on remote server"""
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect to server
            if server.ssh_key_path and server.ssh_key_path.strip():
                client.connect(
                    hostname=server.ip_address,
                    port=server.port,
                    username=server.username,
                    key_filename=server.ssh_key_path,
                    timeout=self.ssh_timeout
                )
            else:
                client.connect(
                    hostname=server.ip_address,
                    port=server.port,
                    username=server.username,
                    password=server.password,
                    timeout=self.ssh_timeout
                )
            
            # Check if Docker is installed
            docker_check = self._execute_ssh_command(client, 'docker --version')
            if not docker_check['success']:
                return {'success': False, 'message': 'Docker is not installed on the remote server'}
            
            # Create worker directory structure
            setup_commands = self._generate_setup_commands(config)
            for cmd in setup_commands:
                result = self._execute_ssh_command(client, cmd)
                if not result['success']:
                    return {'success': False, 'message': f'Setup failed: {result["error"]}'}
            
            # Generate Odoo configuration
            odoo_config = self._generate_odoo_config(config, server)
            config_upload = self._upload_config_file(client, config, odoo_config)
            if not config_upload['success']:
                return config_upload
            
            # Deploy Odoo container
            docker_command = self._generate_docker_run_command(config, server)
            deployment_result = self._execute_ssh_command(client, docker_command, timeout=120)
            
            if not deployment_result['success']:
                return {'success': False, 'message': f'Container deployment failed: {deployment_result["error"]}'}
            
            # Wait for container to be ready
            health_check = self._wait_for_worker_ready(client, config)
            if not health_check['success']:
                self.logger.warning(f"Worker {config.name} deployed but health check failed: {health_check['message']}")
            
            client.close()
            
            return {
                'success': True,
                'message': f'Worker {config.name} deployed successfully',
                'container_id': deployment_result.get('output', '').strip()[:12],
                'details': {
                    'server_ip': server.ip_address,
                    'worker_port': config.port,
                    'container_name': config.name,
                    'health_status': health_check.get('message', 'Unknown')
                }
            }
            
        except Exception as e:
            self.logger.error(f"Worker deployment failed: {str(e)}")
            return {'success': False, 'message': f'Deployment error: {str(e)}'}
    
    def _generate_setup_commands(self, config: RemoteWorkerConfig) -> List[str]:
        """Generate setup commands for worker deployment"""
        commands = [
            f"mkdir -p /opt/odoo-workers/{config.name}/config",
            f"mkdir -p /opt/odoo-workers/{config.name}/addons",
            f"mkdir -p /opt/odoo-workers/{config.name}/data",
            f"mkdir -p /opt/odoo-workers/{config.name}/logs",
            f"chmod 755 /opt/odoo-workers/{config.name}",
            f"chown -R 101:101 /opt/odoo-workers/{config.name}/data",
            f"chown -R 101:101 /opt/odoo-workers/{config.name}/logs"
        ]
        return commands
    
    def _generate_odoo_config(self, config: RemoteWorkerConfig, 
                             server: InfrastructureServer) -> str:
        """Generate Odoo configuration file content"""
        odoo_config = f"""[options]
; Database settings
db_host = {config.postgres_host or 'localhost'}
db_port = {config.postgres_port}
db_user = {config.postgres_user or 'odoo'}
db_password = {config.postgres_password or 'odoo'}

; Server settings
http_port = {config.port}
workers = {min(config.cpu_cores or 2, 4)}
max_cron_threads = 1

; Data directory
data_dir = {config.data_dir}

; Add-ons path
addons_path = /usr/lib/python3/dist-packages/odoo/addons,{config.addons_path}

; Logging
log_level = {config.log_level}
logfile = /var/log/odoo/odoo.log

; Session settings
server_wide_modules = base,web,redis_session_store
session_storage = redis
session_redis_host = redis
session_redis_port = 6379
session_redis_db = 1

; Security
proxy_mode = True
admin_passwd = $pbkdf2-sha512$600000$worker{config.name}admin

; Limits
limit_memory_hard = {(config.memory_gb or 2) * 1024 * 1024 * 1024}
limit_memory_soft = {int((config.memory_gb or 2) * 0.8) * 1024 * 1024 * 1024}
limit_time_cpu = 600
limit_time_real = 1200
"""
        return odoo_config
    
    def _upload_config_file(self, client: paramiko.SSHClient, 
                           config: RemoteWorkerConfig, odoo_config: str) -> Dict[str, Any]:
        """Upload Odoo configuration file to remote server"""
        try:
            # Create config file using echo command
            escaped_config = odoo_config.replace('"', '\\"').replace('$', '\\$')
            upload_cmd = f'cat > /opt/odoo-workers/{config.name}/config/odoo.conf << "EOF"\n{odoo_config}\nEOF'
            
            result = self._execute_ssh_command(client, upload_cmd)
            if result['success']:
                return {'success': True, 'message': 'Configuration uploaded successfully'}
            else:
                return {'success': False, 'message': f'Config upload failed: {result["error"]}'}
                
        except Exception as e:
            return {'success': False, 'message': f'Config upload error: {str(e)}'}
    
    def _generate_docker_run_command(self, config: RemoteWorkerConfig, 
                                    server: InfrastructureServer) -> str:
        """Generate Docker run command for Odoo worker"""
        
        # Environment variables
        env_vars = [
            f"HOST={config.postgres_host or 'localhost'}",
            f"USER={config.postgres_user or 'odoo'}",
            f"PASSWORD={config.postgres_password or 'odoo'}"
        ]
        
        if config.environment_vars:
            for key, value in config.environment_vars.items():
                env_vars.append(f"{key}={value}")
        
        env_string = " ".join([f"-e {var}" for var in env_vars])
        
        # Generate docker run command
        docker_cmd = f"""docker run -d \\
    --name {config.name} \\
    --restart unless-stopped \\
    -p {config.port}:{config.port} \\
    {env_string} \\
    -v /opt/odoo-workers/{config.name}/config/odoo.conf:/etc/odoo/odoo.conf:ro \\
    -v /opt/odoo-workers/{config.name}/data:/var/lib/odoo \\
    -v /opt/odoo-workers/{config.name}/logs:/var/log/odoo \\
    -v /opt/odoo-workers/{config.name}/addons:/mnt/extra-addons \\
    --memory={config.memory_gb or 2}g \\
    --cpus={config.cpu_cores or 2} \\
    odoo:17.0 \\
    odoo -c /etc/odoo/odoo.conf"""
        
        return docker_cmd
    
    def _execute_ssh_command(self, client: paramiko.SSHClient, command: str, 
                            timeout: int = 30) -> Dict[str, Any]:
        """Execute command via SSH and return result"""
        try:
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            
            output = stdout.read().decode('utf-8').strip()
            error = stderr.read().decode('utf-8').strip()
            
            if exit_code == 0:
                return {'success': True, 'output': output}
            else:
                return {'success': False, 'error': error or output, 'exit_code': exit_code}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _wait_for_worker_ready(self, client: paramiko.SSHClient, 
                              config: RemoteWorkerConfig, max_wait: int = 60) -> Dict[str, Any]:
        """Wait for worker to be ready and responsive"""
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                # Check container status
                container_check = self._execute_ssh_command(
                    client, f"docker inspect {config.name} --format='{{{{.State.Running}}}}'"
                )
                
                if container_check['success'] and 'true' in container_check['output']:
                    # Check if Odoo is responding
                    health_check = self._execute_ssh_command(
                        client, f"curl -f http://localhost:{config.port}/web/health || echo 'not ready'"
                    )
                    
                    if health_check['success'] and 'not ready' not in health_check['output']:
                        return {'success': True, 'message': 'Worker is ready and responding'}
                
                time.sleep(5)  # Wait 5 seconds before next check
                
            except Exception as e:
                self.logger.warning(f"Health check error: {str(e)}")
                time.sleep(5)
        
        return {'success': False, 'message': 'Worker failed to become ready within timeout'}
    
    def _create_worker_record(self, config: RemoteWorkerConfig, 
                             server: InfrastructureServer, 
                             deployment_result: Dict[str, Any]) -> WorkerInstance:
        """Create WorkerInstance database record"""
        try:
            db_worker = WorkerInstance(
                name=config.name,
                container_name=config.name,
                port=config.port,
                max_tenants=config.max_tenants,
                status='running',
                server_id=config.server_id
            )
            
            db.session.add(db_worker)
            db.session.commit()
            
            self.logger.info(f"Created WorkerInstance record for {config.name} (ID: {db_worker.id})")
            return db_worker
            
        except Exception as e:
            self.logger.error(f"Failed to create WorkerInstance record: {str(e)}")
            db.session.rollback()
            raise
    
    def _add_to_load_balancer(self, server: InfrastructureServer, 
                             config: RemoteWorkerConfig, 
                             deployment_result: Dict[str, Any]) -> Dict[str, Any]:
        """Add remote worker to nginx load balancer"""
        try:
            nginx_result = self.nginx_service.add_worker(
                worker_ip=server.ip_address,
                worker_port=config.port,
                worker_name=config.name
            )
            
            if nginx_result['success']:
                self.logger.info(f"Added remote worker {config.name} to load balancer")
            else:
                self.logger.warning(f"Failed to add {config.name} to load balancer: {nginx_result.get('error')}")
            
            return nginx_result
            
        except Exception as e:
            self.logger.error(f"Load balancer integration failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _log_worker_action(self, user_id: int, action: str, details: Dict[str, Any], 
                          ip_address: str = None):
        """Log worker management action"""
        try:
            log_action(
                user_id=user_id,
                action=action,
                details=json.dumps(details),
                ip_address=ip_address
            )
        except Exception as e:
            self.logger.error(f"Failed to log worker action: {str(e)}")
    
    def get_remote_worker_status(self, worker_name: str) -> Dict[str, Any]:
        """Get status of a remote worker"""
        try:
            worker = WorkerInstance.query.filter_by(name=worker_name).first()
            if not worker or not worker.server_id:
                return {'success': False, 'message': 'Worker not found'}
            
            server = InfrastructureServer.query.get(worker.server_id)
            if not server:
                return {'success': False, 'message': 'Server not found'}
            
            # Connect to server and check worker status
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            if server.ssh_key_path:
                client.connect(server.ip_address, server.port, server.username, 
                             key_filename=server.ssh_key_path, timeout=self.ssh_timeout)
            else:
                client.connect(server.ip_address, server.port, server.username, 
                             password=server.password, timeout=self.ssh_timeout)
            
            # Get container status
            container_status = self._execute_ssh_command(
                client, f"docker ps --filter name={worker_name} --format 'table {{{{.Status}}}}'"
            )
            
            # Get resource usage
            resource_usage = self._execute_ssh_command(
                client, f"docker stats {worker_name} --no-stream --format 'table {{{{.CPUPerc}}}}\t{{{{.MemUsage}}}}'"
            )
            
            # Health check
            health_check = self._execute_ssh_command(
                client, f"curl -s -f http://localhost:{worker.port}/web/health"
            )
            
            client.close()
            
            return {
                'success': True,
                'worker_name': worker_name,
                'server_name': server.name,
                'server_ip': server.ip_address,
                'port': worker.port,
                'container_status': container_status.get('output', 'Unknown'),
                'resource_usage': resource_usage.get('output', 'Unknown'),
                'health_status': 'Healthy' if health_check['success'] else 'Unhealthy',
                'last_checked': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def stop_remote_worker(self, worker_name: str, user_id: int) -> Dict[str, Any]:
        """Stop a remote worker"""
        try:
            worker = WorkerInstance.query.filter_by(name=worker_name).first()
            if not worker or not worker.server_id:
                return {'success': False, 'message': 'Worker not found'}
            
            server = InfrastructureServer.query.get(worker.server_id)
            if not server:
                return {'success': False, 'message': 'Server not found'}
            
            # Connect and stop container
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            if server.ssh_key_path:
                client.connect(server.ip_address, server.port, server.username, 
                             key_filename=server.ssh_key_path, timeout=self.ssh_timeout)
            else:
                client.connect(server.ip_address, server.port, server.username, 
                             password=server.password, timeout=self.ssh_timeout)
            
            stop_result = self._execute_ssh_command(client, f"docker stop {worker_name}")
            client.close()
            
            if stop_result['success']:
                worker.status = 'stopped'
                db.session.commit()
                
                # Remove from load balancer
                self.nginx_service.remove_worker(server.ip_address, worker_name)
                
                return {'success': True, 'message': f'Worker {worker_name} stopped successfully'}
            else:
                return {'success': False, 'message': f'Failed to stop worker: {stop_result["error"]}'}
                
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def delete_remote_worker(self, worker_name: str, user_id: int) -> Dict[str, Any]:
        """Delete a remote worker completely"""
        try:
            worker = WorkerInstance.query.filter_by(name=worker_name).first()
            if not worker:
                return {'success': False, 'message': 'Worker not found'}
            
            if worker.server_id:
                server = InfrastructureServer.query.get(worker.server_id)
                if server:
                    # Connect and remove container and data
                    client = paramiko.SSHClient()
                    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    
                    if server.ssh_key_path:
                        client.connect(server.ip_address, server.port, server.username, 
                                     key_filename=server.ssh_key_path, timeout=self.ssh_timeout)
                    else:
                        client.connect(server.ip_address, server.port, server.username, 
                                     password=server.password, timeout=self.ssh_timeout)
                    
                    # Stop and remove container
                    self._execute_ssh_command(client, f"docker stop {worker_name}")
                    self._execute_ssh_command(client, f"docker rm {worker_name}")
                    
                    # Remove worker directory
                    self._execute_ssh_command(client, f"rm -rf /opt/odoo-workers/{worker_name}")
                    
                    client.close()
                    
                    # Remove from load balancer
                    self.nginx_service.remove_worker(server.ip_address, worker_name)
            
            # Remove from database
            db.session.delete(worker)
            db.session.commit()
            
            return {'success': True, 'message': f'Worker {worker_name} deleted successfully'}
            
        except Exception as e:
            return {'success': False, 'message': str(e)}


# Export service
__all__ = ['RemoteWorkerService', 'RemoteWorkerConfig']