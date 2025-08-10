"""
Unified Worker Service

This service consolidates all worker deployment logic to eliminate code duplication
and provide a consistent interface for both local and remote worker operations.
"""

import logging
import requests
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass

from db import db
from models import WorkerInstance, InfrastructureServer, DeploymentTask, AuditLog
from shared_utils import get_docker_client, log_error_with_context
from utils import error_tracker

logger = logging.getLogger(__name__)


@dataclass
class WorkerConfig:
    """Configuration for worker deployment"""
    name: Optional[str] = None
    port: int = 8069
    max_tenants: int = 10
    postgres_host: str = '192.168.50.152'
    postgres_port: int = 5432
    postgres_database: str = 'postgres'
    postgres_user: str = 'odoo_master'
    postgres_password: str = 'secure_password_123'
    
    def __post_init__(self):
        """Generate default worker name if not provided"""
        if not self.name:
            self.name = f"odoo_worker_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


@dataclass
class RemoteWorkerConfig(WorkerConfig):
    """Configuration for remote worker deployment"""
    server_id: int = None


class WorkerValidationService:
    """Service for validating worker configurations and parameters"""
    
    @staticmethod
    def validate_worker_data(data: Dict[str, Any]) -> WorkerConfig:
        """
        Validate and create WorkerConfig from request data
        
        Args:
            data: Raw request data dictionary
            
        Returns:
            WorkerConfig: Validated configuration object
            
        Raises:
            ValueError: If validation fails
        """
        try:
            config = WorkerConfig(
                name=data.get('name'),
                port=int(data.get('port', 8069)),
                max_tenants=int(data.get('max_tenants', 10)),
                postgres_host=data.get('postgres_host', '192.168.50.152'),
                postgres_port=int(data.get('postgres_port', 5432)),
                postgres_database=data.get('postgres_database', 'postgres'),
                postgres_user=data.get('postgres_user', 'odoo_master'),
                postgres_password=data.get('postgres_password', 'secure_password_123')
            )
            
            # Validation rules
            if config.port < 1024 or config.port > 65535:
                raise ValueError("Port must be between 1024 and 65535")
                
            if config.max_tenants < 1 or config.max_tenants > 100:
                raise ValueError("Max tenants must be between 1 and 100")
                
            if not config.postgres_host:
                raise ValueError("PostgreSQL host is required")
                
            return config
            
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid worker configuration: {str(e)}")
    
    @staticmethod
    def validate_remote_worker_data(data: Dict[str, Any]) -> RemoteWorkerConfig:
        """
        Validate and create RemoteWorkerConfig from request data
        
        Args:
            data: Raw request data dictionary
            
        Returns:
            RemoteWorkerConfig: Validated configuration object
            
        Raises:
            ValueError: If validation fails
        """
        config = WorkerValidationService.validate_worker_data(data)
        server_id = data.get('server_id')
        
        if not server_id:
            raise ValueError("Server ID is required for remote deployment")
            
        try:
            server_id = int(server_id)
        except (ValueError, TypeError):
            raise ValueError("Server ID must be a valid integer")
        
        return RemoteWorkerConfig(
            name=config.name,
            port=config.port,
            max_tenants=config.max_tenants,
            postgres_host=config.postgres_host,
            postgres_port=config.postgres_port,
            postgres_database=config.postgres_database,
            postgres_user=config.postgres_user,
            postgres_password=config.postgres_password,
            server_id=server_id
        )


class WorkerDatabaseService:
    """Service for worker database operations"""
    
    @staticmethod
    def create_worker_instance(config: WorkerConfig, server_id: Optional[int] = None, 
                             status: str = 'running') -> WorkerInstance:
        """
        Create and persist a WorkerInstance in the database
        
        Args:
            config: Worker configuration
            server_id: Optional server ID for remote workers
            status: Initial worker status
            
        Returns:
            WorkerInstance: The created worker instance
        """
        try:
            db_worker = WorkerInstance(
                name=config.name,
                container_name=config.name,
                port=config.port,
                max_tenants=config.max_tenants,
                status=status,
                server_id=server_id
            )
            
            db.session.add(db_worker)
            db.session.commit()
            
            logger.info(f"Created WorkerInstance record for {config.name} (ID: {db_worker.id})")
            return db_worker
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to create WorkerInstance for {config.name}: {str(e)}")
            raise
    
    @staticmethod
    def update_server_services(server: InfrastructureServer, config: WorkerConfig):
        """
        Update server's current services list with new worker
        
        Args:
            server: Infrastructure server instance
            config: Worker configuration
        """
        try:
            if server.current_services is None:
                server.current_services = []
            
            service_info = {
                'type': 'odoo_worker',
                'name': config.name,
                'port': config.port,
                'status': 'running',
                'max_tenants': config.max_tenants
            }
            
            server.current_services.append(service_info)
            db.session.commit()
            
            logger.info(f"Updated server {server.name} services with worker {config.name}")
            
        except Exception as e:
            logger.error(f"Failed to update server services for {server.name}: {str(e)}")
            raise


class DockerConfigurationService:
    """Service for generating Docker configurations"""
    
    @staticmethod
    def get_docker_environment(config: WorkerConfig) -> Dict[str, str]:
        """
        Generate Docker environment variables
        
        Args:
            config: Worker configuration
            
        Returns:
            Dict containing environment variables
        """
        return {
            'POSTGRES_HOST': config.postgres_host,
            'POSTGRES_PORT': str(config.postgres_port),
            'POSTGRES_DB': config.postgres_database,
            'POSTGRES_USER': config.postgres_user,
            'POSTGRES_PASSWORD': config.postgres_password
        }
    
    @staticmethod
    def get_docker_volumes() -> Dict[str, Dict[str, str]]:
        """
        Generate Docker volume mappings
        
        Returns:
            Dict containing volume mappings
        """
        return {
            'odoomulti-tenantsystem_odoo_filestore': {'bind': '/var/lib/odoo', 'mode': 'rw'},
            'odoomulti-tenantsystem_odoo_worker_logs': {'bind': '/var/log/odoo', 'mode': 'rw'}
        }
    
    @staticmethod
    def get_docker_command(config: WorkerConfig) -> str:
        """
        Generate Docker container command
        
        Args:
            config: Worker configuration
            
        Returns:
            Docker command string
        """
        return f'odoo -c /etc/odoo/odoo.conf --logfile=/var/log/odoo/{config.name}.log'
    
    @staticmethod
    def generate_odoo_config(config: WorkerConfig) -> str:
        """
        Generate Odoo configuration file content
        
        Args:
            config: Worker configuration
            
        Returns:
            String containing Odoo configuration
        """
        return f"""[options]
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
logfile = /var/log/odoo/{config.name}.log
log_level = info
log_handler = :INFO

; Security
admin_passwd = {config.postgres_password}
list_db = False

; Addons
addons_path = /mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons
"""


class WorkerLoggingService:
    """Service for worker-related logging operations"""
    
    @staticmethod
    def log_worker_action(user_id: int, action: str, details: Dict[str, Any], 
                         ip_address: str = None):
        """
        Log worker-related system actions
        
        Args:
            user_id: ID of user performing the action
            action: Description of the action
            details: Additional details about the action
            ip_address: IP address of the request
        """
        try:
            audit_log = AuditLog(
                user_id=user_id,
                action=f"WORKER: {action}",
                details=details,
                ip_address=ip_address
            )
            db.session.add(audit_log)
            db.session.commit()
            
            logger.info(f"Logged worker action: {action} by user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to log worker action: {str(e)}")


class NetworkDiscoveryService:
    """Service for Docker network discovery and management"""
    
    @staticmethod
    def discover_odoo_network() -> Optional[str]:
        """
        Discover the Odoo Docker network name
        
        Returns:
            Network name if found, None otherwise
        """
        docker_client = get_docker_client()
        if not docker_client:
            return None
            
        try:
            # Look for the network used by existing odoo containers
            for container in docker_client.containers.list():
                if 'odoo' in container.name.lower():
                    networks = container.attrs['NetworkSettings']['Networks']
                    for net_name in networks.keys():
                        if 'odoo' in net_name.lower():
                            logger.info(f"Discovered Odoo network: {net_name}")
                            return net_name
            
            # Fallback: list all networks and find the odoo one
            for network in docker_client.networks.list():
                if 'odoo' in network.name.lower():
                    logger.info(f"Found Odoo network by name: {network.name}")
                    return network.name
                    
        except Exception as e:
            logger.warning(f"Could not discover network: {e}")
        
        return None


class UnifiedWorkerService:
    """
    Unified service for all worker operations
    
    This service provides a consistent interface for creating both local and remote workers,
    eliminating code duplication across different routes.
    """
    
    def __init__(self):
        self.validation_service = WorkerValidationService()
        self.database_service = WorkerDatabaseService()
        self.docker_service = DockerConfigurationService()
        self.logging_service = WorkerLoggingService()
        self.network_service = NetworkDiscoveryService()
    
    def create_local_worker(self, data: Dict[str, Any], user_id: int, 
                          ip_address: str = None) -> Dict[str, Any]:
        """
        Create a local Docker worker
        
        Args:
            data: Request data containing worker configuration
            user_id: ID of the user creating the worker
            ip_address: IP address of the request
            
        Returns:
            Dict containing operation result
        """
        try:
            # Validate configuration
            config = self.validation_service.validate_worker_data(data)
            
            # Check Docker availability
            docker_client = get_docker_client()
            if not docker_client:
                return {'success': False, 'message': 'Docker not available'}
            
            # Discover network
            network_name = self.network_service.discover_odoo_network()
            
            # Create container
            container = self._create_local_container(docker_client, config, network_name)
            
            # Create database record
            db_worker = self.database_service.create_worker_instance(config)
            
            # Log action
            self.logging_service.log_worker_action(
                user_id, 
                'local_worker_created',
                {
                    'worker_name': config.name,
                    'container_id': container.id,
                    'max_tenants': config.max_tenants,
                    'network': network_name
                },
                ip_address
            )
            
            logger.info(f"Successfully created local worker: {config.name}")
            
            return {
                'success': True,
                'message': f'Worker {config.name} created successfully',
                'container_id': container.id,
                'worker_id': db_worker.id,
                'network': network_name,
                'worker_details': {
                    'name': config.name,
                    'port': config.port,
                    'max_tenants': config.max_tenants
                }
            }
            
        except ValueError as ve:
            logger.error(f"Validation error creating local worker: {str(ve)}")
            return {'success': False, 'message': str(ve)}
        except Exception as e:
            error_tracker.log_error(e, {'admin_user': user_id})
            logger.error(f"Unexpected error creating local worker: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def create_remote_worker(self, data: Dict[str, Any], user_id: int, 
                           request_obj=None, ip_address: str = None) -> Dict[str, Any]:
        """
        Create a remote worker on infrastructure server
        
        Args:
            data: Request data containing worker configuration
            user_id: ID of the user creating the worker
            request_obj: Flask request object (optional)
            ip_address: IP address of the request
            
        Returns:
            Dict containing operation result
        """
        try:
            # Use the comprehensive RemoteWorkerService
            from services.remote_worker_service import RemoteWorkerService, RemoteWorkerConfig
            
            # Create configuration object
            config = RemoteWorkerConfig(
                name=data['name'],
                server_id=int(data['server_id']),
                port=int(data.get('worker_port', 8069)),
                max_tenants=int(data.get('max_tenants', 10)),
                cpu_cores=data.get('cpu', 2),
                memory_gb=data.get('memory', 2),
                postgres_host=data.get('postgres_host'),
                postgres_port=int(data.get('postgres_port', 5432)),
                postgres_db=data.get('postgres_db'),
                postgres_user=data.get('postgres_user'),
                postgres_password=data.get('postgres_password'),
                addons_path=data.get('addons_path', '/mnt/extra-addons'),
                data_dir=data.get('data_dir', '/var/lib/odoo'),
                log_level=data.get('log_level', 'info'),
                environment_vars=data.get('environment_vars', {})
            )
            
            # Deploy remote worker
            remote_worker_service = RemoteWorkerService()
            result = remote_worker_service.create_remote_worker(config, user_id, ip_address)
            
            return result
            
        except KeyError as ke:
            logger.error(f"Missing required field for remote worker: {str(ke)}")
            return {'success': False, 'message': f'Missing required field: {str(ke)}'}
        except ValueError as ve:
            logger.error(f"Invalid value for remote worker: {str(ve)}")
            return {'success': False, 'message': f'Invalid value: {str(ve)}'}
        except Exception as e:
            error_tracker.log_error(e, {'admin_user': user_id, 'server_id': data.get('server_id')})
            logger.error(f"Unexpected error creating remote worker: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def _create_local_container(self, docker_client, config: WorkerConfig, 
                              network_name: Optional[str] = None):
        """
        Create local Docker container
        
        Args:
            docker_client: Docker client instance
            config: Worker configuration
            network_name: Optional Docker network name
            
        Returns:
            Docker container instance
        """
        try:
            # Create container
            container = docker_client.containers.create(
                'odoo:17.0',
                name=config.name,
                environment=self.docker_service.get_docker_environment(config),
                volumes=self.docker_service.get_docker_volumes(),
                command=self.docker_service.get_docker_command(config),
                restart_policy={'Name': 'unless-stopped'}
            )
            
            # Connect to network if available
            if network_name:
                try:
                    network = docker_client.networks.get(network_name)
                    network.connect(container)
                    logger.info(f"Connected container {config.name} to network: {network_name}")
                except Exception as e:
                    logger.warning(f"Could not connect to network {network_name}: {e}")
            
            # Start the container
            container.start()
            logger.info(f"Started container: {config.name}")
            
            return container
            
        except Exception as e:
            logger.error(f"Failed to create container {config.name}: {str(e)}")
            raise
    
    def get_deployment_status(self, deployment_task_id: int) -> Optional[Dict[str, Any]]:
        """
        Get deployment task status
        
        Args:
            deployment_task_id: ID of the deployment task
            
        Returns:
            Dict containing deployment status or None if not found
        """
        try:
            from services.worker_deployment_service import WorkerDeploymentService
            deployment_service = WorkerDeploymentService(db, error_tracker)
            return deployment_service.get_deployment_status(deployment_task_id)
        except Exception as e:
            logger.error(f"Failed to get deployment status for task {deployment_task_id}: {str(e)}")
            return None


# Export the main service class
__all__ = [
    'UnifiedWorkerService',
    'WorkerConfig',
    'RemoteWorkerConfig',
    'WorkerValidationService',
    'WorkerDatabaseService',
    'DockerConfigurationService',
    'WorkerLoggingService',
    'NetworkDiscoveryService'
]