"""
Services package for the SAAS Manager

This package contains all service layer classes that handle business logic
and provide consistent interfaces for various system operations.
"""

from .worker_service import (
    UnifiedWorkerService,
    WorkerConfig,
    RemoteWorkerConfig,
    WorkerValidationService,
    WorkerDatabaseService,
    DockerConfigurationService,
    WorkerLoggingService,
    NetworkDiscoveryService
)

from .worker_deployment_service import (
    WorkerDeploymentService,
    WorkerDeploymentConfig
)

try:
    from .nginx_service import NginxLoadBalancerService
except ImportError:
    # nginx_service might not exist or be empty
    pass

__all__ = [
    'UnifiedWorkerService',
    'WorkerConfig', 
    'RemoteWorkerConfig',
    'WorkerValidationService',
    'WorkerDatabaseService',
    'DockerConfigurationService',
    'WorkerLoggingService',
    'NetworkDiscoveryService',
    'WorkerDeploymentService',
    'WorkerDeploymentConfig'
]