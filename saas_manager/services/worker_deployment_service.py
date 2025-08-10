"""
Worker Deployment Service
Handles deployment of Odoo workers on remote infrastructure servers
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class WorkerDeploymentConfig:
    """Configuration for worker deployment"""
    worker_name: str
    worker_port: int
    max_tenants: int
    postgres_host: str
    postgres_port: int
    postgres_database: str
    postgres_user: str
    postgres_password: str
    server_id: int


class WorkerDeploymentService:
    """Service class for deploying Odoo workers on remote servers"""
    
    def __init__(self, db_session, error_tracker):
        self.db = db_session
        self.error_tracker = error_tracker
        self.logger = logging.getLogger(__name__)
    
    def deploy_remote_worker(self, config: WorkerDeploymentConfig, current_user_id: int) -> Dict[str, Any]:
        """
        Deploy Odoo worker on remote infrastructure server
        
        Args:
            config: WorkerDeploymentConfig object with deployment parameters
            current_user_id: ID of the user initiating the deployment
            
        Returns:
            Dict containing deployment result
        """
        try:
            # Import here to avoid circular imports
            from models import InfrastructureServer, DeploymentTask, WorkerInstance
            
            # Get the target server
            server = InfrastructureServer.query.get(config.server_id)
            if not server:
                return {'success': False, 'error': 'Server not found'}
            
            # Validate server
            validation_result = self._validate_server(server)
            if not validation_result['success']:
                return validation_result
            
            self.logger.info(
                f"Deploying worker {config.worker_name} to server {server.name} "
                f"({server.ip_address}) by user {current_user_id}"
            )
            
            # Create deployment task
            deployment_task = self._create_deployment_task(config, server, current_user_id)
            
            try:
                # Execute deployment steps
                worker_instance = self._execute_deployment(deployment_task, config, server)
                
                # Update Nginx load balancer
                self._update_load_balancer(server, config)
                
                # Setup monitoring
                self._setup_monitoring(server, config)
                
                # Complete deployment task
                self._complete_deployment_task(deployment_task)
                
                self.logger.info(f"Successfully deployed worker {config.worker_name} to server {server.name}")
                
                return {
                    'success': True,
                    'message': f'Worker {config.worker_name} deployed successfully to {server.name}',
                    'worker_id': worker_instance.id,
                    'deployment_task_id': deployment_task.id,
                    'worker_details': {
                        'name': config.worker_name,
                        'port': config.worker_port,
                        'server': server.name,
                        'server_ip': server.ip_address,
                        'max_tenants': config.max_tenants
                    }
                }
                
            except Exception as e:
                # Mark deployment as failed
                self._fail_deployment_task(deployment_task, str(e))
                self.logger.error(f"Failed to deploy worker {config.worker_name} to server {server.name}: {str(e)}")
                raise e
                
        except Exception as e:
            self.error_tracker.log_error(e, {
                'admin_user': current_user_id,
                'server_id': config.server_id,
                'worker_name': config.worker_name
            })
            return {'success': False, 'message': str(e)}
    
    def _validate_server(self, server) -> Dict[str, Any]:
        """Validate server is ready for deployment"""
        if not server:
            return {'success': False, 'error': 'Server object is None'}
            
        if server.status != 'active':
            return {
                'success': False, 
                'error': f'Server is not active (status: {server.status})'
            }
        
        # Check service roles - allow if None/empty or contains odoo_worker
        service_roles = server.service_roles or []
        if service_roles and 'odoo_worker' not in service_roles:
            return {
                'success': False, 
                'error': 'Server is not configured for Odoo workers'
            }
        
        return {'success': True}
    
    def _create_deployment_task(self, config: WorkerDeploymentConfig, server, current_user_id):
        """Create deployment task record"""
        from models import DeploymentTask
        
        deployment_task = DeploymentTask(
            task_type='deploy',
            service_type='odoo_worker',
            target_server_id=config.server_id,
            config={
                'worker_name': config.worker_name,
                'worker_port': config.worker_port,
                'max_tenants': config.max_tenants,
                'postgres_host': config.postgres_host,
                'postgres_port': config.postgres_port,
                'postgres_database': config.postgres_database,
                'postgres_user': config.postgres_user,
                'postgres_password': config.postgres_password
            },
            priority='normal',
            status='running',
            current_step='Preparing deployment',
            total_steps=6,
            created_by=current_user_id,
            started_at=datetime.utcnow()
        )
        self.db.session.add(deployment_task)
        self.db.session.commit()
        
        return deployment_task
    
    def _execute_deployment(self, deployment_task, config: WorkerDeploymentConfig, server):
        """Execute the actual deployment steps"""
        try:
            from utils.ssh_utils import execute_ssh_command
        except ImportError:
            # Fallback implementation if ssh_utils not available
            def execute_ssh_command(server, command):
                import paramiko
                try:
                    client = paramiko.SSHClient()
                    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    client.connect(
                        hostname=server.ip_address,
                        username=server.username,
                        password=server.password,
                        port=getattr(server, 'port', 22)
                    )
                    stdin, stdout, stderr = client.exec_command(command)
                    output = stdout.read().decode('utf-8')
                    error = stderr.read().decode('utf-8')
                    exit_code = stdout.channel.recv_exit_status()
                    client.close()
                    
                    return {
                        'success': exit_code == 0,
                        'output': output,
                        'error': error,
                        'exit_code': exit_code
                    }
                except Exception as e:
                    return {
                        'success': False,
                        'error': str(e),
                        'output': '',
                        'exit_code': -1
                    }
        
        from models import WorkerInstance
        
        # Step 1: Check Docker availability
        self._update_deployment_progress(deployment_task, 'Checking Docker availability', 15)
        
        docker_check = execute_ssh_command(server, "docker --version")
        if not docker_check['success']:
            raise Exception("Docker is not available on target server")
        
        # Step 2: Check network availability
        self._update_deployment_progress(deployment_task, 'Checking Docker network', 25)
        
        network_check = execute_ssh_command(server, "docker network ls --filter name=odoo_network")
        if not network_check['success'] or 'odoo_network' not in network_check['output']:
            # Create network if it doesn't exist
            create_network = execute_ssh_command(server, "docker network create odoo_network")
            if not create_network['success']:
                self.logger.warning("Failed to create Docker network, proceeding without network")
        
        # Step 3: Prepare deployment script
        self._update_deployment_progress(deployment_task, 'Preparing deployment script', 40)
        
        deployment_script = self._generate_deployment_script(config)
        
        # Step 4: Upload and execute deployment script
        self._update_deployment_progress(deployment_task, 'Executing deployment', 60)
        
        script_path = f"/tmp/deploy_{config.worker_name}.sh"
        
        # Upload script with proper escaping
        escaped_script = deployment_script.replace('"', '\"').replace('$', '\$')
        script_upload = execute_ssh_command(
            server, 
            f'cat > {script_path} << "EOF"\n{deployment_script}\nEOF'
        )
        if not script_upload['success']:
            raise Exception(f"Failed to upload deployment script: {script_upload.get('error', 'Unknown error')}")
        
        # Make executable and run with timeout
        chmod_result = execute_ssh_command(server, f"chmod +x {script_path}")
        if not chmod_result['success']:
            raise Exception("Failed to make deployment script executable")
        
        self.logger.info(f"Executing deployment script for {config.worker_name}")
        deploy_result = execute_ssh_command(server, f"timeout 300 bash {script_path}")
        if not deploy_result['success']:
            error_msg = deploy_result.get('error', 'Unknown deployment error')
            output_msg = deploy_result.get('output', '')
            full_error = f"Deployment failed: {error_msg}\nOutput: {output_msg}"
            raise Exception(full_error)
        
        # Step 5: Verify deployment
        self._update_deployment_progress(deployment_task, 'Verifying deployment', 80)
        
        verify_result = execute_ssh_command(
            server, 
            f"docker ps --filter name={config.worker_name} --format '{{{{.Status}}}}'"
        )
        if not verify_result['success'] or 'Up' not in verify_result['output']:
            raise Exception("Worker container is not running after deployment")
        
        # Step 6: Register worker in database
        self._update_deployment_progress(deployment_task, 'Registering worker', 90)
        
        # Create WorkerInstance record
        db_worker = WorkerInstance(
            name=config.worker_name,
            container_name=config.worker_name,
            port=config.worker_port,
            max_tenants=config.max_tenants,
            status='running',
            server_id=config.server_id,
            created_at=datetime.utcnow()
        )
        self.db.session.add(db_worker)
        
        # Update server's current services safely
        try:
            if server.current_services is None:
                server.current_services = []
            
            service_info = {
                'type': 'odoo_worker',
                'name': config.worker_name,
                'port': config.worker_port,
                'status': 'running',
                'deployed_at': datetime.utcnow().isoformat(),
                'max_tenants': config.max_tenants
            }
            server.current_services.append(service_info)
            
            self.db.session.commit()
            self.logger.info(f"Successfully registered worker {config.worker_name} in database")
            
        except Exception as db_error:
            self.db.session.rollback()
            self.logger.error(f"Failed to register worker in database: {db_error}")
            raise
        
        # Clean up temporary files
        execute_ssh_command(server, f"rm -f {script_path}")
        
        return db_worker
    
    def _generate_deployment_script(self, config: WorkerDeploymentConfig) -> str:
        """Generate the bash deployment script"""
        return f"""#!/bin/bash
set -e

echo "=== Odoo 17.0 Worker Deployment ==="
echo "Worker Name: {config.worker_name}"
echo "Worker Port: {config.worker_port}"
echo "PostgreSQL Host: {config.postgres_host}"
echo "PostgreSQL Port: {config.postgres_port}"
echo "PostgreSQL Database: {config.postgres_database}"
echo "PostgreSQL User: {config.postgres_user}"
echo "Max Tenants: {config.max_tenants}"

# Test PostgreSQL connectivity first
echo "Testing PostgreSQL connectivity..."
if command -v pg_isready &> /dev/null; then
    pg_isready -h {config.postgres_host} -p {config.postgres_port} -U {config.postgres_user}
    if [ $? -eq 0 ]; then
        echo "✓ PostgreSQL is ready and accepting connections"
    else
        echo "⚠ Warning: PostgreSQL connectivity test failed, but proceeding with deployment"
    fi
else
    echo "⚠ pg_isready not available, skipping connectivity test"
fi

# Create Odoo configuration directory
echo "Creating Odoo configuration directory..."
mkdir -p /opt/odoo/config/{config.worker_name}
mkdir -p /opt/odoo/addons
mkdir -p /opt/odoo/logs

# Create Odoo configuration file
echo "Creating Odoo configuration file..."
cat > /opt/odoo/config/{config.worker_name}/odoo.conf << EOF
[options]
; Database settings
db_host = {config.postgres_host}
db_port = {config.postgres_port}
db_user = {config.postgres_user}
db_password = {config.postgres_password}
db_template = template0
db_maxconn = 64

; Server settings
http_port = 8069
workers = 2
max_cron_threads = 1
limit_memory_hard = 2684354560
limit_memory_soft = 2147483648
limit_request = 8192
limit_time_cpu = 600
limit_time_real = 1200

; Logging
logfile = /var/log/odoo/{config.worker_name}.log
log_level = info
log_handler = :INFO

; Security
admin_passwd = {config.postgres_password}
list_db = False

; Addons
addons_path = /mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons
EOF

echo "✓ Odoo configuration file created"

# Check if container already exists and remove it
if [ $(docker ps -a -q -f name={config.worker_name}) ]; then
    echo "Removing existing container {config.worker_name}..."
    docker stop {config.worker_name} || true
    docker rm {config.worker_name} || true
fi

# Create worker container
echo "Creating Odoo 17.0 worker container..."
docker run -d \\
  --name {config.worker_name} \\
  --restart unless-stopped \\
  -p {config.worker_port}:8069 \\
  -e POSTGRES_HOST={config.postgres_host} \\
  -e POSTGRES_PORT={config.postgres_port} \\
  -e POSTGRES_DB={config.postgres_database} \\
  -e POSTGRES_USER={config.postgres_user} \\
  -e POSTGRES_PASSWORD={config.postgres_password} \\
  -v /opt/odoo/config/{config.worker_name}:/etc/odoo \\
  -v odoo_filestore_{config.worker_name}:/var/lib/odoo \\
  -v /opt/odoo/logs:/var/log/odoo \\
  --network odoo_network \\
  odoo:17.0 \\
  odoo -c /etc/odoo/odoo.conf --logfile=/var/log/odoo/{config.worker_name}.log

# Wait for container to start
echo "Waiting for container to start..."
sleep 5

# Check if container is running
if [ $(docker ps -q -f name={config.worker_name}) ]; then
    echo "✓ Worker {config.worker_name} deployed successfully"
else
    echo "✗ Worker {config.worker_name} failed to start"
    docker logs {config.worker_name}
    exit 1
fi
"""
    
    def _update_deployment_progress(self, deployment_task, step: str, progress: int):
        """Update deployment task progress"""
        deployment_task.current_step = step
        deployment_task.progress = progress
        self.db.session.commit()
    
    def _update_load_balancer(self, server, config: WorkerDeploymentConfig):
        """Update Nginx load balancer configuration"""
        try:
            from services.nginx_service import NginxLoadBalancerService
            nginx_service = NginxLoadBalancerService()
            nginx_service.add_worker(server.ip_address, config.worker_port, config.worker_name)
            self.logger.info(f"Added worker {config.worker_name} to Nginx load balancer")
        except Exception as nginx_error:
            self.logger.warning(f"Failed to update Nginx load balancer for worker {config.worker_name}: {nginx_error}")
    
    def _setup_monitoring(self, server, config: WorkerDeploymentConfig):
        """Setup health monitoring for the worker"""
        try:
            # Try to import and setup monitoring service
            from services.monitoring_service import MonitoringService
            monitoring_service = MonitoringService()
            monitoring_service.setup_worker_monitoring(
                server, 
                config.worker_name, 
                config.worker_port
            )
            self.logger.info(f"Setup monitoring for worker {config.worker_name}")
        except ImportError:
            self.logger.info(f"Monitoring service not available for worker {config.worker_name}")
        except Exception as monitoring_error:
            self.logger.warning(f"Failed to setup monitoring for worker {config.worker_name}: {monitoring_error}")
    
    def _complete_deployment_task(self, deployment_task):
        """Mark deployment task as completed"""
        deployment_task.status = 'completed'
        deployment_task.progress = 100
        deployment_task.current_step = 'Deployment completed'
        deployment_task.completed_at = datetime.utcnow()
        self.db.session.commit()
    
    def _fail_deployment_task(self, deployment_task, error_message: str):
        """Mark deployment task as failed"""
        deployment_task.status = 'failed'
        deployment_task.error_message = error_message
        deployment_task.completed_at = datetime.utcnow()
        self.db.session.commit()
    
    def get_deployment_status(self, deployment_task_id: int) -> Optional[Dict[str, Any]]:
        """Get deployment task status"""
        from models import DeploymentTask
        
        task = DeploymentTask.query.get(deployment_task_id)
        if not task:
            return None
        
        return {
            'id': task.id,
            'status': task.status,
            'progress': task.progress,
            'current_step': task.current_step,
            'total_steps': task.total_steps,
            'error_message': task.error_message,
            'created_at': task.created_at.isoformat() if task.created_at else None,
            'started_at': task.started_at.isoformat() if task.started_at else None,
            'completed_at': task.completed_at.isoformat() if task.completed_at else None
        }
    
    def undeploy_worker(self, worker_name: str, server_id: int) -> Dict[str, Any]:
        """Undeploy a worker from remote server"""
        try:
            from models import InfrastructureServer, WorkerInstance
            from utils.ssh_utils import execute_ssh_command
            
            server = InfrastructureServer.query.get(server_id)
            if not server:
                return {'success': False, 'error': 'Server not found'}
            
            # Stop and remove container
            stop_result = execute_ssh_command(server, f"docker stop {worker_name}")
            remove_result = execute_ssh_command(server, f"docker rm {worker_name}")
            
            if not stop_result['success'] and not remove_result['success']:
                return {'success': False, 'error': 'Failed to remove worker container'}
            
            # Remove from database
            worker = WorkerInstance.query.filter_by(name=worker_name).first()
            if worker:
                self.db.session.delete(worker)
            
            # Update server's current services
            if server.current_services:
                server.current_services = [
                    service for service in server.current_services 
                    if service.get('name') != worker_name
                ]
            
            self.db.session.commit()
            
            # Remove from load balancer
            self._remove_from_load_balancer(server, worker_name)
            
            return {'success': True, 'message': f'Worker {worker_name} undeployed successfully'}
            
        except Exception as e:
            self.logger.error(f"Failed to undeploy worker {worker_name}: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _remove_from_load_balancer(self, server, worker_name: str):
        """Remove worker from Nginx load balancer"""
        try:
            from services.nginx_service import NginxLoadBalancerService
            nginx_service = NginxLoadBalancerService()
            nginx_service.remove_worker(server.ip_address, worker_name)
        except Exception as e:
            self.logger.warning(f"Failed to remove worker {worker_name} from load balancer: {e}")