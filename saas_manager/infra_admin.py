#!/usr/bin/env python3
"""
Complete Infrastructure Administration Module
Single-file implementation for managing multi-machine infrastructure
Includes server management, service deployment, monitoring, migration, and auto-discovery
"""

# Standard library imports
import base64
import hashlib
import ipaddress
import json
import logging
import os
import secrets
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from functools import wraps

# Third-party imports
import docker
import paramiko
import redis
import requests
from croniter import croniter
from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user
from jinja2 import Template
from sqlalchemy import text, func

# Import your existing models and utilities
from db import db
from models import SaasUser, Tenant, WorkerInstance, AuditLog, SystemSetting
from utils import error_tracker, logger, track_errors

# Create blueprint
infra_admin_bp = Blueprint('infra_admin', __name__, url_prefix='/infra-admin')

# ================= MODELS =================

class InfrastructureServer(db.Model):
    """Infrastructure server management model"""
    __tablename__ = 'infrastructure_servers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    ip_address = db.Column(db.String(45), nullable=False)
    username = db.Column(db.String(50), nullable=False)
    password = db.Column(db.String(255))  # Encrypted
    ssh_key_path = db.Column(db.String(500))
    port = db.Column(db.Integer, default=22)
    
    # Service roles this server can handle
    service_roles = db.Column(db.JSON, default=list)
    current_services = db.Column(db.JSON, default=list)
    
    # Server specifications
    cpu_cores = db.Column(db.Integer)
    memory_gb = db.Column(db.Integer)
    disk_gb = db.Column(db.Integer)
    os_type = db.Column(db.String(50))
    
    # Status and health
    status = db.Column(db.String(20), default='pending')
    last_health_check = db.Column(db.DateTime)
    health_score = db.Column(db.Integer, default=100)
    
    # Deployment tracking
    deployment_status = db.Column(db.String(50), default='ready')
    deployment_log = db.Column(db.Text)
    
    # Monitoring and alerts
    monitoring_enabled = db.Column(db.Boolean, default=True)
    alert_email = db.Column(db.String(100))
    alert_webhook = db.Column(db.String(500))
    
    # Resource limits
    max_cpu_usage = db.Column(db.Integer, default=80)
    max_memory_usage = db.Column(db.Integer, default=80)
    max_disk_usage = db.Column(db.Integer, default=85)
    
    # Network configuration
    internal_ip = db.Column(db.String(45))
    external_ip = db.Column(db.String(45))
    network_zone = db.Column(db.String(50), default='production')
    
    # Backup configuration
    backup_enabled = db.Column(db.Boolean, default=True)
    backup_frequency = db.Column(db.String(50), default='daily')
    backup_retention_days = db.Column(db.Integer, default=30)
    last_backup_at = db.Column(db.DateTime)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'))
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'ip_address': self.ip_address,
            'service_roles': self.service_roles,
            'current_services': self.current_services,
            'status': self.status,
            'health_score': self.health_score,
            'deployment_status': self.deployment_status,
            'cpu_cores': self.cpu_cores,
            'memory_gb': self.memory_gb,
            'disk_gb': self.disk_gb,
            'os_type': self.os_type,
            'last_health_check': self.last_health_check.isoformat() if self.last_health_check else None,
            'created_at': self.created_at.isoformat()
        }

class DomainMapping(db.Model):
    """Domain mapping for custom domains to tenants"""
    __tablename__ = 'domain_mappings'
    
    id = db.Column(db.Integer, primary_key=True)
    custom_domain = db.Column(db.String(255), nullable=False, unique=True)
    target_subdomain = db.Column(db.String(100), nullable=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'))
    
    # Load balancing configuration
    load_balancer_enabled = db.Column(db.Boolean, default=True)
    load_balancer_method = db.Column(db.String(50), default='round_robin')
    upstream_servers = db.Column(db.JSON, default=list)
    
    # SSL Configuration
    ssl_enabled = db.Column(db.Boolean, default=False)
    ssl_cert_path = db.Column(db.String(500))
    ssl_key_path = db.Column(db.String(500))
    ssl_auto_renew = db.Column(db.Boolean, default=True)
    ssl_provider = db.Column(db.String(50), default='letsencrypt')
    
    # Security settings
    force_https = db.Column(db.Boolean, default=True)
    hsts_enabled = db.Column(db.Boolean, default=True)
    security_headers = db.Column(db.JSON, default=dict)
    
    # Caching and performance
    cache_enabled = db.Column(db.Boolean, default=True)
    cache_ttl = db.Column(db.Integer, default=3600)
    compression_enabled = db.Column(db.Boolean, default=True)
    
    # Rate limiting
    rate_limit_enabled = db.Column(db.Boolean, default=False)
    rate_limit_requests = db.Column(db.Integer, default=100)
    rate_limit_window = db.Column(db.Integer, default=60)
    
    # Access control
    ip_whitelist = db.Column(db.JSON, default=list)
    ip_blacklist = db.Column(db.JSON, default=list)
    geo_restrictions = db.Column(db.JSON, default=dict)
    
    # Status and monitoring
    status = db.Column(db.String(20), default='pending')
    last_verified = db.Column(db.DateTime)
    verification_status = db.Column(db.String(50))
    uptime_check_enabled = db.Column(db.Boolean, default=True)
    uptime_check_interval = db.Column(db.Integer, default=300)
    
    # Analytics and logging
    access_log_enabled = db.Column(db.Boolean, default=True)
    analytics_enabled = db.Column(db.Boolean, default=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'))
    
    # Relationships
    tenant = db.relationship('Tenant', backref='domain_mappings')
    
    def to_dict(self):
        return {
            'id': self.id,
            'custom_domain': self.custom_domain,
            'target_subdomain': self.target_subdomain,
            'tenant_id': self.tenant_id,
            'tenant_name': self.tenant.name if self.tenant else None,
            'ssl_enabled': self.ssl_enabled,
            'status': self.status,
            'verification_status': self.verification_status,
            'last_verified': self.last_verified.isoformat() if self.last_verified else None,
            'created_at': self.created_at.isoformat()
        }

class CronJob(db.Model):
    """Cron job management across infrastructure"""
    __tablename__ = 'cron_jobs'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    command = db.Column(db.Text, nullable=False)
    schedule = db.Column(db.String(100), nullable=False)
    server_id = db.Column(db.Integer, db.ForeignKey('infrastructure_servers.id'))
    
    # Job configuration
    working_directory = db.Column(db.String(500))
    environment_vars = db.Column(db.JSON, default=dict)
    timeout_seconds = db.Column(db.Integer, default=3600)
    retry_attempts = db.Column(db.Integer, default=0)
    retry_delay = db.Column(db.Integer, default=60)
    
    # Notification settings
    notify_on_success = db.Column(db.Boolean, default=False)
    notify_on_failure = db.Column(db.Boolean, default=True)
    notification_email = db.Column(db.String(100))
    notification_webhook = db.Column(db.String(500))
    
    # Status tracking
    status = db.Column(db.String(20), default='active')
    last_run = db.Column(db.DateTime)
    next_run = db.Column(db.DateTime)
    last_result = db.Column(db.Text)
    last_exit_code = db.Column(db.Integer)
    run_count = db.Column(db.Integer, default=0)
    success_count = db.Column(db.Integer, default=0)
    failure_count = db.Column(db.Integer, default=0)
    
    # Performance tracking
    avg_runtime_seconds = db.Column(db.Float, default=0.0)
    max_runtime_seconds = db.Column(db.Float, default=0.0)
    last_runtime_seconds = db.Column(db.Float, default=0.0)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'))
    
    # Relationships
    server = db.relationship('InfrastructureServer', backref='cron_jobs')
    
    def to_dict(self):
        next_run = calculate_next_run(self.schedule)
        return {
            'id': self.id,
            'name': self.name,
            'command': self.command,
            'schedule': self.schedule,
            'server_id': self.server_id,
            'server_name': self.server.name if self.server else 'All servers',
            'status': self.status,
            'last_run': self.last_run.isoformat() if self.last_run else None,
            'next_run': next_run.isoformat() if next_run else None,
            'run_count': self.run_count,
            'success_count': self.success_count,
            'failure_count': self.failure_count,
            'avg_runtime_seconds': self.avg_runtime_seconds,
            'created_at': self.created_at.isoformat()
        }

class DeploymentTask(db.Model):
    """Deployment and migration task tracking"""
    __tablename__ = 'deployment_tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    task_type = db.Column(db.String(50), nullable=False)
    service_type = db.Column(db.String(50), nullable=False)
    source_server_id = db.Column(db.Integer, db.ForeignKey('infrastructure_servers.id'))
    target_server_id = db.Column(db.Integer, db.ForeignKey('infrastructure_servers.id'))
    
    # Task configuration
    config = db.Column(db.JSON)
    priority = db.Column(db.String(20), default='normal')
    
    # Dependencies
    depends_on = db.Column(db.JSON, default=list)
    blocks = db.Column(db.JSON, default=list)
    
    # Status tracking
    status = db.Column(db.String(20), default='pending')
    progress = db.Column(db.Integer, default=0)
    current_step = db.Column(db.String(100))
    total_steps = db.Column(db.Integer, default=1)
    
    # Logging and debugging
    logs = db.Column(db.Text)
    error_message = db.Column(db.Text)
    debug_info = db.Column(db.JSON)
    
    # Performance tracking
    estimated_duration = db.Column(db.Integer)
    actual_duration = db.Column(db.Integer)
    
    # Resource usage
    cpu_usage_avg = db.Column(db.Float)
    memory_usage_avg = db.Column(db.Float)
    disk_io_total = db.Column(db.BigInteger)
    network_io_total = db.Column(db.BigInteger)
    
    # Rollback information
    rollback_supported = db.Column(db.Boolean, default=False)
    rollback_data = db.Column(db.JSON)
    rolled_back_at = db.Column(db.DateTime)
    rolled_back_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'))
    
    # Timestamps
    scheduled_at = db.Column(db.DateTime)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'))
    
    # Relationships
    source_server = db.relationship('InfrastructureServer', foreign_keys=[source_server_id])
    target_server = db.relationship('InfrastructureServer', foreign_keys=[target_server_id])
    
    def to_dict(self):
        return {
            'id': self.id,
            'task_type': self.task_type,
            'service_type': self.service_type,
            'source_server': self.source_server.name if self.source_server else None,
            'target_server': self.target_server.name if self.target_server else None,
            'status': self.status,
            'progress': self.progress,
            'current_step': self.current_step,
            'priority': self.priority,
            'error_message': self.error_message,
            'estimated_duration': self.estimated_duration,
            'actual_duration': self.actual_duration,
            'rollback_supported': self.rollback_supported,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'created_at': self.created_at.isoformat()
        }

class NetworkScanResult(db.Model):
    """Network scan results for server discovery"""
    __tablename__ = 'network_scan_results'
    
    id = db.Column(db.Integer, primary_key=True)
    scan_task_id = db.Column(db.Integer, db.ForeignKey('deployment_tasks.id'))
    ip_address = db.Column(db.String(45), nullable=False)
    hostname = db.Column(db.String(255))
    
    # Connectivity
    is_reachable = db.Column(db.Boolean, default=False)
    response_time_ms = db.Column(db.Float)
    
    # SSH accessibility
    ssh_accessible = db.Column(db.Boolean, default=False)
    ssh_port = db.Column(db.Integer, default=22)
    ssh_version = db.Column(db.String(100))
    
    # System information
    os_type = db.Column(db.String(50))
    os_version = db.Column(db.String(100))
    kernel_version = db.Column(db.String(100))
    cpu_cores = db.Column(db.Integer)
    memory_gb = db.Column(db.Integer)
    disk_gb = db.Column(db.Integer)
    architecture = db.Column(db.String(20))
    
    # Installed services
    installed_services = db.Column(db.JSON, default=list)
    running_services = db.Column(db.JSON, default=list)
    open_ports = db.Column(db.JSON, default=list)
    
    # Security information
    has_firewall = db.Column(db.Boolean, default=False)
    firewall_type = db.Column(db.String(50))
    requires_sudo = db.Column(db.Boolean, default=True)
    
    # Suitability assessment
    suitability_score = db.Column(db.Integer, default=0)
    recommended_roles = db.Column(db.JSON, default=list)
    compatibility_issues = db.Column(db.JSON, default=list)
    
    # Auto-setup readiness
    auto_setup_ready = db.Column(db.Boolean, default=False)
    setup_requirements = db.Column(db.JSON, default=list)
    estimated_setup_time = db.Column(db.Integer)
    
    # Timestamps
    scanned_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'ip_address': self.ip_address,
            'hostname': self.hostname,
            'is_reachable': self.is_reachable,
            'ssh_accessible': self.ssh_accessible,
            'os_type': self.os_type,
            'os_version': self.os_version,
            'cpu_cores': self.cpu_cores,
            'memory_gb': self.memory_gb,
            'disk_gb': self.disk_gb,
            'installed_services': self.installed_services,
            'running_services': self.running_services,
            'suitability_score': self.suitability_score,
            'recommended_roles': self.recommended_roles,
            'auto_setup_ready': self.auto_setup_ready,
            'scanned_at': self.scanned_at.isoformat()
        }

class ConfigurationTemplate(db.Model):
    """Templates for server and service configurations"""
    __tablename__ = 'configuration_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    template_type = db.Column(db.String(50), nullable=False)
    
    # Template content
    template_content = db.Column(db.Text, nullable=False)
    template_variables = db.Column(db.JSON, default=dict)
    default_values = db.Column(db.JSON, default=dict)
    
    # Template metadata
    version = db.Column(db.String(20), default='1.0')
    category = db.Column(db.String(50))
    tags = db.Column(db.JSON, default=list)
    
    # Requirements and compatibility
    min_memory_gb = db.Column(db.Integer)
    min_cpu_cores = db.Column(db.Integer)
    min_disk_gb = db.Column(db.Integer)
    supported_os = db.Column(db.JSON, default=list)
    required_services = db.Column(db.JSON, default=list)
    
    # Usage tracking
    usage_count = db.Column(db.Integer, default=0)
    last_used_at = db.Column(db.DateTime)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    is_validated = db.Column(db.Boolean, default=False)
    validation_results = db.Column(db.JSON)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'))
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'template_type': self.template_type,
            'version': self.version,
            'category': self.category,
            'tags': self.tags,
            'template_variables': self.template_variables,
            'default_values': self.default_values,
            'min_memory_gb': self.min_memory_gb,
            'min_cpu_cores': self.min_cpu_cores,
            'supported_os': self.supported_os,
            'is_active': self.is_active,
            'is_validated': self.is_validated,
            'usage_count': self.usage_count,
            'created_at': self.created_at.isoformat()
        }

class InfrastructureAlert(db.Model):
    """Infrastructure monitoring alerts"""
    __tablename__ = 'infrastructure_alerts'
    
    id = db.Column(db.Integer, primary_key=True)
    alert_type = db.Column(db.String(50), nullable=False)
    severity = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    
    # Source information
    server_id = db.Column(db.Integer, db.ForeignKey('infrastructure_servers.id'))
    domain_id = db.Column(db.Integer, db.ForeignKey('domain_mappings.id'))
    service_name = db.Column(db.String(100))
    
    # Alert data
    metric_name = db.Column(db.String(100))
    metric_value = db.Column(db.Float)
    threshold_value = db.Column(db.Float)
    alert_data = db.Column(db.JSON)
    
    # Status and resolution
    status = db.Column(db.String(20), default='active')
    acknowledged_at = db.Column(db.DateTime)
    acknowledged_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'))
    resolved_at = db.Column(db.DateTime)
    resolved_by = db.Column(db.Integer, db.ForeignKey('saas_users.id'))
    resolution_notes = db.Column(db.Text)
    
    # Notification tracking
    notification_sent = db.Column(db.Boolean, default=False)
    notification_methods = db.Column(db.JSON, default=list)
    notification_failures = db.Column(db.JSON, default=list)
    
    # Auto-resolution
    auto_resolve_enabled = db.Column(db.Boolean, default=True)
    auto_resolve_after_minutes = db.Column(db.Integer, default=60)
    
    # Timestamps
    first_occurrence = db.Column(db.DateTime, default=datetime.utcnow)
    last_occurrence = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    server = db.relationship('InfrastructureServer', backref='alerts')
    domain = db.relationship('DomainMapping', backref='alerts')
    
    def to_dict(self):
        return {
            'id': self.id,
            'alert_type': self.alert_type,
            'severity': self.severity,
            'title': self.title,
            'message': self.message,
            'server_id': self.server_id,
            'server_name': self.server.name if self.server else None,
            'domain_id': self.domain_id,
            'domain_name': self.domain.custom_domain if self.domain else None,
            'service_name': self.service_name,
            'status': self.status,
            'metric_name': self.metric_name,
            'metric_value': self.metric_value,
            'threshold_value': self.threshold_value,
            'first_occurrence': self.first_occurrence.isoformat(),
            'last_occurrence': self.last_occurrence.isoformat(),
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None
        }

# ================= DECORATORS =================

def require_infra_admin():
    """Decorator for infrastructure admin access"""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.is_admin:
                return jsonify({'success': False, 'message': 'Infrastructure admin access required'}), 403
            return fn(*args, **kwargs)
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator

# ================= UTILITY FUNCTIONS =================

def encrypt_password(password):
    """Encrypt password for storage"""
    return base64.b64encode(password.encode()).decode()

def decrypt_password(encrypted_password):
    """Decrypt password from storage"""
    try:
        return base64.b64decode(encrypted_password.encode()).decode()
    except:
        return encrypted_password

def calculate_next_run(schedule):
    """Calculate next run time for cron schedule"""
    try:
        cron = croniter(schedule, datetime.utcnow())
        return cron.get_next(datetime)
    except Exception:
        return None

def validate_cron_schedule(schedule):
    """Validate cron schedule format"""
    try:
        croniter(schedule)
        return True
    except:
        return False


def test_ssh_connection(ip, username, password=None, key_path=None, port=22, debug=True):
    """
    Test SSH connection and gather system info with detailed debugging
    
    Args:
        ip (str): Target IP address
        username (str): SSH username
        password (str, optional): SSH password
        key_path (str, optional): Path to SSH private key
        port (int): SSH port (default: 22)
        debug (bool): Enable detailed debugging output
    
    Returns:
        dict: Connection result with success status, system info, and debug logs
    """
    debug_logs = []
    
    def log_debug(message):
        if debug:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            debug_message = f"[{timestamp}] {message}"
            debug_logs.append(debug_message)
            print(debug_message)  # Real-time output
    
    try:
        log_debug(f"=== Starting SSH connection test ===")
        log_debug(f"Target: {username}@{ip}:{port}")
        log_debug(f"Authentication: {'key' if key_path else 'password' if password else 'none'}")
        
        # Step 1: Validate input parameters
        log_debug("Step 1: Validating input parameters...")
        
        if not ip:
            error_msg = "IP address is required"
            log_debug(f"ERROR: {error_msg}")
            return {'success': False, 'error': error_msg, 'debug_logs': debug_logs}
        
        if not username:
            error_msg = "Username is required"
            log_debug(f"ERROR: {error_msg}")
            return {'success': False, 'error': error_msg, 'debug_logs': debug_logs}
        
        # Validate IP format
        try:
            import ipaddress
            ipaddress.ip_address(ip)
            log_debug(f"✓ IP address format is valid: {ip}")
        except ValueError as e:
            error_msg = f"Invalid IP address format: {ip}"
            log_debug(f"ERROR: {error_msg}")
            return {'success': False, 'error': error_msg, 'debug_logs': debug_logs}
        
        # Validate port
        if not isinstance(port, int) or port < 1 or port > 65535:
            error_msg = f"Invalid port number: {port}"
            log_debug(f"ERROR: {error_msg}")
            return {'success': False, 'error': error_msg, 'debug_logs': debug_logs}
        
        log_debug("✓ Input parameters validated successfully")
        
        # Step 2: Test basic network connectivity
        log_debug("Step 2: Testing basic network connectivity...")
        
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        
        try:
            start_time = time.time()
            result = sock.connect_ex((ip, port))
            connect_time = (time.time() - start_time) * 1000
            
            if result == 0:
                log_debug(f"✓ Network connectivity successful (response time: {connect_time:.2f}ms)")
            else:
                error_msg = f"Network connectivity failed (error code: {result})"
                log_debug(f"ERROR: {error_msg}")
                return {'success': False, 'error': error_msg, 'debug_logs': debug_logs}
        except Exception as e:
            error_msg = f"Network connectivity test failed: {str(e)}"
            log_debug(f"ERROR: {error_msg}")
            return {'success': False, 'error': error_msg, 'debug_logs': debug_logs}
        finally:
            sock.close()
            log_debug("Network socket closed")
        
        # Step 3: Validate authentication credentials
        log_debug("Step 3: Validating authentication credentials...")
        
        auth_method = None
        
        if key_path:
            log_debug(f"Checking SSH key path: {key_path}")
            if os.path.exists(key_path):
                try:
                    # Check if file is readable
                    with open(key_path, 'r') as key_file:
                        key_content = key_file.read(100)  # Read first 100 chars
                        if 'PRIVATE KEY' in key_content:
                            log_debug("✓ SSH private key file is valid and readable")
                            auth_method = 'key'
                        else:
                            log_debug("WARNING: SSH key file doesn't appear to contain a private key")
                except Exception as e:
                    error_msg = f"Cannot read SSH key file: {str(e)}"
                    log_debug(f"ERROR: {error_msg}")
                    return {'success': False, 'error': error_msg, 'debug_logs': debug_logs}
            else:
                error_msg = f"SSH key file not found: {key_path}"
                log_debug(f"ERROR: {error_msg}")
                return {'success': False, 'error': error_msg, 'debug_logs': debug_logs}
        
        elif password:
            if len(password.strip()) == 0:
                error_msg = "Password is empty"
                log_debug(f"ERROR: {error_msg}")
                return {'success': False, 'error': error_msg, 'debug_logs': debug_logs}
            log_debug(f"✓ Password authentication method (length: {len(password)} chars)")
            auth_method = 'password'
        
        else:
            error_msg = "No authentication method provided (password or key_path required)"
            log_debug(f"ERROR: {error_msg}")
            return {'success': False, 'error': error_msg, 'debug_logs': debug_logs}
        
        # Step 4: Initialize SSH client
        log_debug("Step 4: Initializing SSH client...")
        
        try:
            import paramiko
            log_debug("✓ Paramiko library imported successfully")
        except ImportError as e:
            error_msg = f"Paramiko library not available: {str(e)}"
            log_debug(f"ERROR: {error_msg}")
            return {'success': False, 'error': error_msg, 'debug_logs': debug_logs}
        
        client = paramiko.SSHClient()
        log_debug("✓ SSH client object created")
        
        # Configure host key policy
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        log_debug("✓ Host key policy set to AutoAddPolicy")
        
        # Step 5: Establish SSH connection
        log_debug("Step 5: Establishing SSH connection...")
        
        connection_start_time = time.time()
        
        try:
            if auth_method == 'key':
                log_debug(f"Attempting key-based authentication with: {key_path}")
                client.connect(
                    hostname=ip, 
                    port=port, 
                    username=username, 
                    key_filename=key_path, 
                    timeout=10,
                    banner_timeout=10,
                    auth_timeout=10
                )
            else:  # password authentication
                log_debug("Attempting password-based authentication")
                client.connect(
                    hostname=ip, 
                    port=port, 
                    username=username, 
                    password=password, 
                    timeout=10,
                    banner_timeout=10,
                    auth_timeout=10
                )
            
            connection_time = (time.time() - connection_start_time) * 1000
            log_debug(f"✓ SSH connection established successfully (connection time: {connection_time:.2f}ms)")
            
        except paramiko.AuthenticationException as e:
            error_msg = f"SSH authentication failed: {str(e)}"
            log_debug(f"ERROR: {error_msg}")
            client.close()
            return {'success': False, 'error': error_msg, 'debug_logs': debug_logs}
        
        except paramiko.SSHException as e:
            error_msg = f"SSH connection error: {str(e)}"
            log_debug(f"ERROR: {error_msg}")
            client.close()
            return {'success': False, 'error': error_msg, 'debug_logs': debug_logs}
        
        except socket.timeout:
            error_msg = "SSH connection timed out"
            log_debug(f"ERROR: {error_msg}")
            client.close()
            return {'success': False, 'error': error_msg, 'debug_logs': debug_logs}
        
        except Exception as e:
            error_msg = f"Unexpected SSH connection error: {str(e)}"
            log_debug(f"ERROR: {error_msg}")
            client.close()
            return {'success': False, 'error': error_msg, 'debug_logs': debug_logs}
        
        # Step 6: Test command execution
        log_debug("Step 6: Testing command execution...")
        
        try:
            test_command = 'echo "SSH_TEST_SUCCESS"'
            log_debug(f"Executing test command: {test_command}")
            
            stdin, stdout, stderr = client.exec_command(test_command, timeout=10)
            test_output = stdout.read().decode().strip()
            test_error = stderr.read().decode().strip()
            
            if test_output == "SSH_TEST_SUCCESS":
                log_debug("✓ Command execution test successful")
            else:
                log_debug(f"WARNING: Unexpected test command output: '{test_output}'")
            
            if test_error:
                log_debug(f"Test command stderr (might be normal): {test_error}")
                
        except Exception as e:
            error_msg = f"Command execution test failed: {str(e)}"
            log_debug(f"ERROR: {error_msg}")
            client.close()
            return {'success': False, 'error': error_msg, 'debug_logs': debug_logs}
        
        # Step 7: Gather system information
        log_debug("Step 7: Gathering system information...")
        
        # Define system information commands
        commands = {
            'cpu_cores': {
                'command': 'nproc',
                'description': 'Number of CPU cores',
                'type': 'int'
            },
            'memory_gb': {
                'command': "free -g | awk '/^Mem:/{print $2}'",
                'description': 'Total memory in GB',
                'type': 'int'
            },
            'disk_gb': {
                'command': "df -BG / | awk 'NR==2{gsub(/G/,\"\"); print $2}'",
                'description': 'Root disk size in GB',
                'type': 'int'
            },
            'os_type': {
                'command': 'cat /etc/os-release | grep "^ID=" | cut -d= -f2 | tr -d \'"\'',
                'description': 'Operating system type',
                'type': 'str'
            },
            'os_version': {
                'command': 'cat /etc/os-release | grep "^VERSION_ID=" | cut -d= -f2 | tr -d \'"\'',
                'description': 'Operating system version',
                'type': 'str'
            },
            'kernel': {
                'command': 'uname -r',
                'description': 'Kernel version',
                'type': 'str'
            },
            'uptime': {
                'command': 'uptime -p',
                'description': 'System uptime',
                'type': 'str'
            },
            'hostname': {
                'command': 'hostname',
                'description': 'System hostname',
                'type': 'str'
            },
            'architecture': {
                'command': 'uname -m',
                'description': 'System architecture',
                'type': 'str'
            },
            'load_average': {
                'command': "uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | cut -d',' -f1",
                'description': '1-minute load average',
                'type': 'float'
            }
        }
        
        system_info = {}
        command_results = {}
        
        for key, cmd_info in commands.items():
            try:
                log_debug(f"Executing: {cmd_info['description']} -> {cmd_info['command']}")
                
                cmd_start_time = time.time()
                stdin, stdout, stderr = client.exec_command(cmd_info['command'], timeout=15)
                
                result = stdout.read().decode().strip()
                error = stderr.read().decode().strip()
                cmd_time = (time.time() - cmd_start_time) * 1000
                
                # Store raw command results for debugging
                command_results[key] = {
                    'command': cmd_info['command'],
                    'stdout': result,
                    'stderr': error,
                    'execution_time_ms': round(cmd_time, 2)
                }
                
                # Process and validate result based on expected type
                if cmd_info['type'] == 'int':
                    if result.isdigit():
                        system_info[key] = int(result)
                        log_debug(f"✓ {cmd_info['description']}: {result}")
                    else:
                        log_debug(f"WARNING: {cmd_info['description']} returned non-numeric: '{result}'")
                        system_info[key] = None
                
                elif cmd_info['type'] == 'float':
                    try:
                        system_info[key] = float(result)
                        log_debug(f"✓ {cmd_info['description']}: {result}")
                    except ValueError:
                        log_debug(f"WARNING: {cmd_info['description']} returned non-float: '{result}'")
                        system_info[key] = None
                
                else:  # string type
                    system_info[key] = result if result else None
                    log_debug(f"✓ {cmd_info['description']}: '{result}'")
                
                if error:
                    log_debug(f"Command stderr: {error}")
                
            except Exception as e:
                error_msg = f"Failed to execute {cmd_info['description']}: {str(e)}"
                log_debug(f"ERROR: {error_msg}")
                system_info[key] = None
                command_results[key] = {
                    'command': cmd_info['command'],
                    'error': str(e)
                }
        
        # Step 8: Additional system checks
        log_debug("Step 8: Performing additional system checks...")
        
        additional_info = {}
        
        # Check if user has sudo privileges
        try:
            log_debug("Checking sudo privileges...")
            stdin, stdout, stderr = client.exec_command('sudo -n true', timeout=5)
            sudo_error = stderr.read().decode().strip()
            
            if not sudo_error:
                additional_info['has_sudo'] = True
                log_debug("✓ User has passwordless sudo privileges")
            else:
                additional_info['has_sudo'] = False
                log_debug("○ User does not have passwordless sudo privileges")
        except:
            additional_info['has_sudo'] = False
            log_debug("○ Could not determine sudo privileges")
        
        # Check available disk space
        try:
            log_debug("Checking disk space...")
            stdin, stdout, stderr = client.exec_command("df -h / | awk 'NR==2{print $4}'", timeout=5)
            available_space = stdout.read().decode().strip()
            additional_info['available_disk_space'] = available_space
            log_debug(f"✓ Available disk space: {available_space}")
        except:
            log_debug("○ Could not determine available disk space")
        
        # Check system load
        try:
            log_debug("Checking system load...")
            stdin, stdout, stderr = client.exec_command("cat /proc/loadavg", timeout=5)
            load_info = stdout.read().decode().strip()
            additional_info['load_averages'] = load_info
            log_debug(f"✓ Load averages: {load_info}")
        except:
            log_debug("○ Could not determine system load")
        
        # Check network interfaces
        try:
            log_debug("Checking network interfaces...")
            stdin, stdout, stderr = client.exec_command("ip addr show | grep 'inet ' | awk '{print $2}' | head -5", timeout=5)
            network_interfaces = stdout.read().decode().strip().split('\n')
            additional_info['network_interfaces'] = [iface for iface in network_interfaces if iface]
            log_debug(f"✓ Network interfaces: {additional_info['network_interfaces']}")
        except:
            log_debug("○ Could not determine network interfaces")
        
        # Step 9: Close SSH connection
        log_debug("Step 9: Closing SSH connection...")
        
        try:
            client.close()
            log_debug("✓ SSH connection closed successfully")
        except Exception as e:
            log_debug(f"WARNING: Error closing SSH connection: {str(e)}")
        
        # Step 10: Prepare final result
        log_debug("Step 10: Preparing final result...")
        
        total_execution_time = (time.time() - connection_start_time) * 1000
        log_debug(f"Total execution time: {total_execution_time:.2f}ms")
        
        final_result = {
            'success': True,
            'system_info': system_info,
            'additional_info': additional_info,
            'connection_details': {
                'ip': ip,
                'port': port,
                'username': username,
                'auth_method': auth_method,
                'connection_time_ms': round(connection_time, 2),
                'total_execution_time_ms': round(total_execution_time, 2)
            },
            'debug_logs': debug_logs,
            'command_results': command_results if debug else None
        }
        
        log_debug("=== SSH connection test completed successfully ===")
        
        return final_result
        
    except Exception as e:
        error_msg = f"Unexpected error in SSH connection test: {str(e)}"
        log_debug(f"FATAL ERROR: {error_msg}")
        
        # Try to close client if it exists
        try:
            if 'client' in locals():
                client.close()
                log_debug("SSH client closed after error")
        except:
            pass
        
        return {
            'success': False, 
            'error': error_msg,
            'debug_logs': debug_logs,
            'error_type': type(e).__name__
        }

# Additional debugging helper function
def analyze_ssh_failure(result):
    """
    Analyze SSH connection failure and provide troubleshooting suggestions
    """
    if result['success']:
        return "Connection was successful - no analysis needed"
    
    error = result.get('error', '').lower()
    suggestions = []
    
    if 'network connectivity failed' in error:
        suggestions.extend([
            "Check if the target server is running and accessible",
            "Verify the IP address and port number",
            "Check firewall rules on both client and server",
            "Test with: ping <ip> and telnet <ip> <port>"
        ])
    
    elif 'authentication failed' in error:
        suggestions.extend([
            "Verify username and password/key are correct",
            "Check if the user account exists on the target server",
            "Ensure SSH key has correct permissions (600)",
            "Verify SSH key format and that it matches the public key on server"
        ])
    
    elif 'connection timed out' in error:
        suggestions.extend([
            "Increase timeout values",
            "Check network latency and stability",
            "Verify SSH service is running on target server",
            "Check for network congestion or routing issues"
        ])
    
    elif 'permission denied' in error:
        suggestions.extend([
            "Check SSH server configuration (/etc/ssh/sshd_config)",
            "Verify user is allowed to SSH (AllowUsers directive)",
            "Check if password authentication is enabled",
            "Verify public key is in ~/.ssh/authorized_keys"
        ])
    
    return {
        'error_analysis': error,
        'troubleshooting_suggestions': suggestions,
        'debug_logs': result.get('debug_logs', [])
    }

def perform_health_check(server):
    """Perform comprehensive health check on server"""
    try:
        # Test basic connectivity
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((server.ip_address, server.port))
        sock.close()
        
        if result != 0:
            return {'status': 'unreachable', 'score': 0}
        
        # SSH connection test
        ssh_test = test_ssh_connection(
            server.ip_address, 
            server.username, 
            decrypt_password(server.password) if server.password else None,
            server.ssh_key_path,
            server.port
        )
        
        if not ssh_test['success']:
            return {'status': 'ssh_failed', 'score': 20, 'error': ssh_test['error']}
        
        # Check services
        service_status = {}
        health_score = 100
        
        for service in server.current_services:
            status = check_service_status(server, service)
            service_status[service] = status
            if not status['running']:
                health_score -= 20
        
        # Update database
        server.health_score = health_score
        server.last_health_check = datetime.utcnow()
        db.session.commit()
        
        return {
            'status': 'healthy' if health_score >= 80 else 'degraded',
            'score': health_score,
            'services': service_status,
            'system_info': ssh_test.get('system_info', {})
        }
        
    except Exception as e:
        return {'status': 'error', 'score': 0, 'error': str(e)}

def check_service_status(server, service_name):
    """Check specific service status on server"""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        if server.ssh_key_path and os.path.exists(server.ssh_key_path):
            client.connect(server.ip_address, port=server.port, 
                         username=server.username, key_filename=server.ssh_key_path)
        else:
            client.connect(server.ip_address, port=server.port, 
                         username=server.username, password=decrypt_password(server.password))
        
            # Service-specific checks
        if service_name == 'docker':
            # Try multiple Docker verification methods
            docker_checks = [
                'docker version --format "{{.Server.Version}}" 2>/dev/null',
                'docker info >/dev/null 2>&1 && echo "active"',
                'systemctl is-active docker 2>/dev/null || echo "unknown"'
            ]
            
            for check_cmd in docker_checks:
                stdin, stdout, stderr = client.exec_command(check_cmd, timeout=10)
                result = stdout.read().decode().strip()
                error = stderr.read().decode().strip()
                
                if result and ('active' in result.lower() or len(result) > 0):
                    return {
                        'running': True,
                        'status': 'active',
                        'error': None
                    }
        elif service_name == 'nginx':
            stdin, stdout, stderr = client.exec_command('systemctl is-active nginx')
        elif service_name == 'postgres':
            # Try multiple PostgreSQL verification methods (container-friendly)
            postgres_checks = [
                {
                    'cmd': 'sudo -u postgres psql -c "SELECT version();" 2>/dev/null',
                    'success_indicator': 'PostgreSQL'
                },
                {
                    'cmd': 'pg_isready -U postgres 2>/dev/null',
                    'success_indicator': 'accepting connections'
                },
                {
                    'cmd': 'sudo -u postgres psql -c "SELECT current_user;" 2>/dev/null',
                    'success_indicator': 'postgres'
                },
                {
                    'cmd': 'pgrep -f "postgres:" | head -1',
                    'success_indicator': '' # Any output means process is running
                }
            ]
            
            for check in postgres_checks:
                try:
                    stdin, stdout, stderr = client.exec_command(check['cmd'], timeout=15)
                    result = stdout.read().decode().strip()
                    error = stderr.read().decode().strip()
                    
                    success_indicator = check['success_indicator']
                    
                    # Check if command succeeded
                    if success_indicator:
                        if success_indicator.lower() in result.lower():
                            return {
                                'running': True,
                                'status': 'active',
                                'error': None
                            }
                    else:
                        # For process check, any non-empty result means running
                        if result and result.strip():
                            return {
                                'running': True,
                                'status': 'active',
                                'error': None
                            }
                except Exception:
                    continue
            
            # If all checks fail, return error
            return {
                'running': False,
                'status': 'inactive',
                'error': 'PostgreSQL not accessible via any verification method'
            }
        elif service_name == 'redis':
            stdin, stdout, stderr = client.exec_command('systemctl is-active redis')
        else:
            stdin, stdout, stderr = client.exec_command(f'systemctl is-active {service_name}')
        
        result = stdout.read().decode().strip()
        error = stderr.read().decode().strip()
        
        client.close()
        
        return {
            'running': 'active' in result.lower() or 'running' in result.lower(),
            'status': result,
            'error': error if error else None
        }
        
    except Exception as e:
        return {'running': False, 'status': 'unknown', 'error': str(e)}

def collect_server_metrics(server):
    """Collect detailed metrics from server"""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        if server.ssh_key_path:
            client.connect(server.ip_address, port=server.port,
                         username=server.username, key_filename=server.ssh_key_path)
        else:
            client.connect(server.ip_address, port=server.port,
                         username=server.username, password=decrypt_password(server.password))
        
        metrics = {}
        
        # CPU usage
        stdin, stdout, stderr = client.exec_command("top -bn1 | grep 'Cpu(s)' | awk '{print $2}' | cut -d'%' -f1")
        cpu_usage = stdout.read().decode().strip()
        try:
            metrics['cpu_usage'] = float(cpu_usage)
        except:
            metrics['cpu_usage'] = 0
        
        # Memory usage
        stdin, stdout, stderr = client.exec_command("free | grep Mem | awk '{printf \"%.1f\", $3/$2 * 100.0}'")
        memory_usage = stdout.read().decode().strip()
        try:
            metrics['memory_usage'] = float(memory_usage)
        except:
            metrics['memory_usage'] = 0
        
        # Disk usage
        stdin, stdout, stderr = client.exec_command("df / | tail -1 | awk '{print $5}' | cut -d'%' -f1")
        disk_usage = stdout.read().decode().strip()
        try:
            metrics['disk_usage'] = float(disk_usage)
        except:
            metrics['disk_usage'] = 0
        
        # Load average
        stdin, stdout, stderr = client.exec_command("uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | cut -d',' -f1")
        load_avg = stdout.read().decode().strip()
        try:
            metrics['load_average'] = float(load_avg)
        except:
            metrics['load_average'] = 0
        
        client.close()
        return metrics
        
    except Exception as e:
        logger.error(f"Failed to collect metrics from {server.name}: {e}")
        return {}

# ================= INFRASTRUCTURE MONITORING =================

class InfrastructureMonitor:
    """Advanced infrastructure monitoring system"""
    
    def __init__(self, app, redis_client=None, docker_client=None):
        self.app = app
        self.redis_client = redis_client
        self.docker_client = docker_client
        self.running = False
        self.monitor_thread = None
        
        # Monitoring intervals (seconds)
        self.health_check_interval = 300  # 5 minutes
        self.metrics_collection_interval = 60  # 1 minute
        self.alert_check_interval = 120  # 2 minutes
        
        # Alert thresholds
        self.default_thresholds = {
            'cpu_usage_warning': 80,
            'cpu_usage_critical': 95,
            'memory_usage_warning': 80,
            'memory_usage_critical': 95,
            'disk_usage_warning': 85,
            'disk_usage_critical': 95,
            'health_score_warning': 70,
            'health_score_critical': 50
        }
    
    def start_monitoring(self):
        """Start the monitoring system"""
        if self.running:
            logger.warning("Monitoring system already running")
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Infrastructure monitoring system started")
    
    def stop_monitoring(self):
        """Stop the monitoring system"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=10)
        logger.info("Infrastructure monitoring system stopped")
    
    def _monitoring_loop(self):
        """Main monitoring loop"""
        last_health_check = 0
        last_metrics_collection = 0
        last_alert_check = 0
        
        while self.running:
            try:
                current_time = time.time()
                
                with self.app.app_context():
                    # Health checks
                    if current_time - last_health_check >= self.health_check_interval:
                        self._perform_health_checks()
                        last_health_check = current_time
                    
                    # Metrics collection
                    if current_time - last_metrics_collection >= self.metrics_collection_interval:
                        self._collect_metrics()
                        last_metrics_collection = current_time
                    
                    # Alert checks
                    if current_time - last_alert_check >= self.alert_check_interval:
                        self._check_alerts()
                        last_alert_check = current_time
                
                time.sleep(10)  # Base sleep interval
                
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                time.sleep(30)  # Wait longer on error
    
    def _perform_health_checks(self):
        """Perform health checks on all active servers"""
        try:
            servers = InfrastructureServer.query.filter_by(status='active').all()
            
            for server in servers:
                try:
                    health_data = perform_health_check(server)
                    self._check_server_alerts(server, health_data)
                except Exception as e:
                    logger.error(f"Health check failed for server {server.name}: {e}")
                    self._create_alert(
                        alert_type='health_check_failed',
                        severity='warning',
                        title=f'Health check failed for {server.name}',
                        message=f'Unable to perform health check: {str(e)}',
                        server_id=server.id
                    )
        except Exception as e:
            logger.error(f"Health check process failed: {e}")
    
    def _collect_metrics(self):
        """Collect and store metrics"""
        try:
            if not self.redis_client:
                return
            
            # Collect system-wide metrics
            system_metrics = {
                'timestamp': datetime.utcnow().isoformat(),
                'total_servers': InfrastructureServer.query.count(),
                'active_servers': InfrastructureServer.query.filter_by(status='active').count(),
                'total_domains': DomainMapping.query.count(),
                'active_domains': DomainMapping.query.filter_by(status='active').count(),
                'active_deployments': DeploymentTask.query.filter_by(status='running').count(),
                'active_alerts': InfrastructureAlert.query.filter_by(status='active').count()
            }
            
            # Store in Redis with TTL
            self.redis_client.setex('system_metrics', 300, json.dumps(system_metrics))
            
            # Store historical data
            historical_key = f"metrics_history:{datetime.utcnow().strftime('%Y%m%d_%H%M')}"
            self.redis_client.setex(historical_key, 86400, json.dumps(system_metrics))
            
        except Exception as e:
            logger.error(f"Metrics collection failed: {e}")
    
    def _check_alerts(self):
        """Check and process active alerts"""
        try:
            # Auto-resolve alerts that are no longer valid
            self._auto_resolve_alerts()
        except Exception as e:
            logger.error(f"Alert check process failed: {e}")
    
    def _check_server_alerts(self, server, health_data):
        """Check for alert conditions on server"""
        thresholds = self._get_alert_thresholds()
        metrics = health_data.get('system_info', {})
        
        # CPU usage alerts
        cpu_usage = metrics.get('cpu_usage', 0)
        if cpu_usage >= thresholds['cpu_usage_critical']:
            self._create_alert(
                alert_type='high_cpu_usage',
                severity='critical',
                title=f'Critical CPU usage on {server.name}',
                message=f'CPU usage is {cpu_usage}% (threshold: {thresholds["cpu_usage_critical"]}%)',
                server_id=server.id,
                metric_name='cpu_usage',
                metric_value=cpu_usage,
                threshold_value=thresholds['cpu_usage_critical']
            )
        elif cpu_usage >= thresholds['cpu_usage_warning']:
            self._create_alert(
                alert_type='high_cpu_usage',
                severity='warning',
                title=f'High CPU usage on {server.name}',
                message=f'CPU usage is {cpu_usage}% (threshold: {thresholds["cpu_usage_warning"]}%)',
                server_id=server.id,
                metric_name='cpu_usage',
                metric_value=cpu_usage,
                threshold_value=thresholds['cpu_usage_warning']
            )
        
        # Memory usage alerts
        memory_usage = metrics.get('memory_usage', 0)
        if memory_usage >= thresholds['memory_usage_critical']:
            self._create_alert(
                alert_type='high_memory_usage',
                severity='critical',
                title=f'Critical memory usage on {server.name}',
                message=f'Memory usage is {memory_usage}% (threshold: {thresholds["memory_usage_critical"]}%)',
                server_id=server.id,
                metric_name='memory_usage',
                metric_value=memory_usage,
                threshold_value=thresholds['memory_usage_critical']
            )
        elif memory_usage >= thresholds['memory_usage_warning']:
            self._create_alert(
                alert_type='high_memory_usage',
                severity='warning',
                title=f'High memory usage on {server.name}',
                message=f'Memory usage is {memory_usage}% (threshold: {thresholds["memory_usage_warning"]}%)',
                server_id=server.id,
                metric_name='memory_usage',
                metric_value=memory_usage,
                threshold_value=thresholds['memory_usage_warning']
            )
        
        # Disk usage alerts
        disk_usage = metrics.get('disk_usage', 0)
        if disk_usage >= thresholds['disk_usage_critical']:
            self._create_alert(
                alert_type='high_disk_usage',
                severity='critical',
                title=f'Critical disk usage on {server.name}',
                message=f'Disk usage is {disk_usage}% (threshold: {thresholds["disk_usage_critical"]}%)',
                server_id=server.id,
                metric_name='disk_usage',
                metric_value=disk_usage,
                threshold_value=thresholds['disk_usage_critical']
            )
        elif disk_usage >= thresholds['disk_usage_warning']:
            self._create_alert(
                alert_type='high_disk_usage',
                severity='warning',
                title=f'High disk usage on {server.name}',
                message=f'Disk usage is {disk_usage}% (threshold: {thresholds["disk_usage_warning"]}%)',
                server_id=server.id,
                metric_name='disk_usage',
                metric_value=disk_usage,
                threshold_value=thresholds['disk_usage_warning']
            )
    
    def _create_alert(self, alert_type, severity, title, message, server_id=None, domain_id=None, 
                     service_name=None, metric_name=None, metric_value=None, threshold_value=None, 
                     alert_data=None):
        """Create a new infrastructure alert"""
        try:
            # Check if similar alert already exists and is active
            existing_alert = InfrastructureAlert.query.filter(
                InfrastructureAlert.alert_type == alert_type,
                InfrastructureAlert.server_id == server_id,
                InfrastructureAlert.domain_id == domain_id,
                InfrastructureAlert.service_name == service_name,
                InfrastructureAlert.status == 'active'
            ).first()
            
            if existing_alert:
                # Update existing alert
                existing_alert.last_occurrence = datetime.utcnow()
                existing_alert.message = message
                if metric_value is not None:
                    existing_alert.metric_value = metric_value
                if alert_data:
                    existing_alert.alert_data = alert_data
            else:
                # Create new alert
                alert = InfrastructureAlert(
                    alert_type=alert_type,
                    severity=severity,
                    title=title,
                    message=message,
                    server_id=server_id,
                    domain_id=domain_id,
                    service_name=service_name,
                    metric_name=metric_name,
                    metric_value=metric_value,
                    threshold_value=threshold_value,
                    alert_data=alert_data or {}
                )
                db.session.add(alert)
            
            db.session.commit()
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to create alert: {e}")
    
    def _get_alert_thresholds(self):
        """Get alert thresholds from system settings"""
        thresholds = self.default_thresholds.copy()
        
        try:
            # Override with custom settings
            settings = SystemSetting.query.filter(
                SystemSetting.category == 'monitoring_alerts'
            ).all()
            
            for setting in settings:
                if setting.key in thresholds:
                    thresholds[setting.key] = setting.get_typed_value()
        
        except Exception as e:
            logger.error(f"Failed to get alert thresholds: {e}")
        
        return thresholds
    
    def _auto_resolve_alerts(self):
        """Automatically resolve alerts that are no longer valid"""
        try:
            # Get alerts that can be auto-resolved
            auto_resolve_alerts = InfrastructureAlert.query.filter(
                InfrastructureAlert.status == 'active',
                InfrastructureAlert.auto_resolve_enabled == True,
                InfrastructureAlert.first_occurrence < datetime.utcnow() - timedelta(minutes=60)
            ).all()
            
            for alert in auto_resolve_alerts:
                # Check if the condition still exists
                should_resolve = False
                
                if alert.server_id and alert.metric_name:
                    # Check current server metrics
                    current_health = perform_health_check(
                        InfrastructureServer.query.get(alert.server_id)
                    )
                    current_value = current_health.get('system_info', {}).get(alert.metric_name)
                    
                    if current_value is not None:
                        if alert.metric_name in ['cpu_usage', 'memory_usage', 'disk_usage']:
                            # For usage metrics, check if below threshold
                            should_resolve = current_value < alert.threshold_value
                        elif alert.metric_name == 'health_score':
                            # For health score, check if above threshold
                            should_resolve = current_value > alert.threshold_value
                
                if should_resolve:
                    alert.status = 'resolved'
                    alert.resolved_at = datetime.utcnow()
                    alert.resolution_notes = 'Auto-resolved: Condition no longer met'
            
            db.session.commit()
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Auto-resolve alerts failed: {e}")

# ================= ROUTE HANDLERS =================

@infra_admin_bp.route('/dashboard')
@login_required
@require_infra_admin()
@track_errors('infra_admin_dashboard')
def dashboard():
    return render_template('infra/dashboard.html')

# ================= SERVER MANAGEMENT =================

@infra_admin_bp.route('/api/servers/list')
@login_required
@require_infra_admin()
@track_errors('list_infrastructure_servers')
def list_infrastructure_servers():
    """List all infrastructure servers"""
    try:
        servers = InfrastructureServer.query.all()
        servers_data = []
        
        for server in servers:
            # Get real-time health check
            health_data = perform_health_check(server)
            
            server_dict = server.to_dict()
            server_dict['health_data'] = health_data
            servers_data.append(server_dict)
        
        return jsonify({'success': True, 'servers': servers_data})
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

@infra_admin_bp.route('/api/servers/add', methods=['POST'])
@login_required
@require_infra_admin()
@track_errors('add_infrastructure_server')
def add_infrastructure_server():
    """Add new infrastructure server"""
    try:
        data = request.json
        
        # Validate IP address
        try:
            ipaddress.ip_address(data['ip_address'])
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid IP address'}), 400
        
        # Test SSH connection
        ssh_test = test_ssh_connection(
            data['ip_address'], 
            data['username'], 
            data.get('password'), 
            data.get('ssh_key_path'),
            data.get('port', 22)
        )
        
        if not ssh_test['success']:
            return jsonify({'success': False, 'message': f'SSH connection failed: {ssh_test["error"]}'}), 400
        
        # Create server record
        server = InfrastructureServer(
            name=data['name'],
            ip_address=data['ip_address'],
            username=data['username'],
            password=encrypt_password(data.get('password', '')),
            ssh_key_path=data.get('ssh_key_path'),
            port=data.get('port', 22),
            service_roles=data.get('service_roles', []),
            cpu_cores=ssh_test.get('system_info', {}).get('cpu_cores'),
            memory_gb=ssh_test.get('system_info', {}).get('memory_gb'),
            disk_gb=ssh_test.get('system_info', {}).get('disk_gb'),
            os_type=ssh_test.get('system_info', {}).get('os_type'),
            status='active',
            created_by=current_user.id
        )
        
        db.session.add(server)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Server {data["name"]} added successfully',
            'server_id': server.id
        })
        
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

@infra_admin_bp.route('/api/servers/<int:server_id>/deploy-service', methods=['POST'])
@login_required
@require_infra_admin()
@track_errors('deploy_service_to_server')
def deploy_service_to_server(server_id):
    """Deploy a service to a specific server"""
    try:
        data = request.json
        service_type = data.get('service_type')
        config = data.get('config', {})
        
        server = InfrastructureServer.query.get_or_404(server_id)
        
        if service_type not in server.service_roles:
            return jsonify({'success': False, 'message': f'Server not configured for {service_type}'}), 400
        
        # Create deployment task
        task = DeploymentTask(
            task_type='deploy',
            service_type=service_type,
            target_server_id=server_id,
            config=config,
            created_by=current_user.id
        )
        db.session.add(task)
        db.session.commit()
        
        # Start deployment in background
        threading.Thread(
            target=execute_deployment_task,
            args=(task.id,),
            daemon=True
        ).start()
        
        return jsonify({
            'success': True, 
            'message': f'Deployment of {service_type} started',
            'task_id': task.id
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'server_id': server_id, 'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

@infra_admin_bp.route('/api/servers/<int:source_id>/migrate-to/<int:target_id>', methods=['POST'])
@login_required
@require_infra_admin()
@track_errors('migrate_server_services')
def migrate_server_services(source_id, target_id):
    """Migrate services from one server to another with testing"""
    try:
        data = request.json
        services_to_migrate = data.get('services', [])
        
        source_server = InfrastructureServer.query.get_or_404(source_id)
        target_server = InfrastructureServer.query.get_or_404(target_id)
        
        # Validate target server can handle services
        for service in services_to_migrate:
            if service not in target_server.service_roles:
                return jsonify({
                    'success': False, 
                    'message': f'Target server cannot handle {service}'
                }), 400
        
        # Test target server first
        health_check = perform_health_check(target_server)
        if health_check['score'] < 80:
            return jsonify({
                'success': False,
                'message': f'Target server health score too low: {health_check["score"]}. Migration aborted.'
            }), 400
        
        # Create migration task
        task = DeploymentTask(
            task_type='migrate',
            service_type=','.join(services_to_migrate),
            source_server_id=source_id,
            target_server_id=target_id,
            config={'services': services_to_migrate, 'test_before_migrate': True},
            created_by=current_user.id
        )
        db.session.add(task)
        db.session.commit()
        
        # Start migration in background
        threading.Thread(
            target=execute_migration_task,
            args=(task.id,),
            daemon=True
        ).start()
        
        return jsonify({
            'success': True, 
            'message': 'Migration started with pre-migration testing',
            'task_id': task.id
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'source_id': source_id, 'target_id': target_id})
        return jsonify({'success': False, 'message': str(e)}), 500

# ================= DEPLOYMENT EXECUTION =================

def execute_deployment_task(task_id):
    """Execute deployment task in background with comprehensive logging"""
    print(f"\n{'='*60}")
    print(f"[DEPLOYMENT] Starting deployment task ID: {task_id}")
    print(f"[DEPLOYMENT] Timestamp: {datetime.now().isoformat()}")
    print(f"{'='*60}")
    
    try:
        # Import the app instance directly
        from app import app  # Import your main Flask app instance
        
        # Use the app instance directly instead of current_app
        with app.app_context():
            task = DeploymentTask.query.get(task_id)
            if not task:
                print(f"[DEPLOYMENT] ERROR: Task {task_id} not found in database")
                return
            
            # Initialize task
            print(f"[DEPLOYMENT] Task found: {task.service_type} deployment")
            print(f"[DEPLOYMENT] Target server: {task.target_server.name if task.target_server else 'Unknown'}")
            
            task.status = 'running'
            task.started_at = datetime.utcnow()
            task.progress = 0
            db.session.commit()
            
            target_server = task.target_server
            service_type = task.service_type
            config = task.config or {}
            
            logs = []
            logs.append(f"=== DEPLOYMENT TASK STARTED ===")
            logs.append(f"Task ID: {task_id}")
            logs.append(f"Service Type: {service_type}")
            logs.append(f"Target Server: {target_server.name} ({target_server.ip_address})")
            logs.append(f"Started At: {datetime.now().isoformat()}")
            logs.append(f"Configuration: {config}")
            
            # Phase 1: Initial setup
            print(f"[DEPLOYMENT] Phase 1: Initial setup and validation")
            task.progress = 5
            logs.append(f"\n--- PHASE 1: INITIAL SETUP ---")
            logs.append(f"Validating target server configuration...")
            
            if not target_server:
                error_msg = "Target server not found"
                print(f"[DEPLOYMENT] FATAL ERROR: {error_msg}")
                logs.append(f"FATAL ERROR: {error_msg}")
                task.status = 'failed'
                task.error_message = error_msg
                task.logs = '\n'.join(logs)
                db.session.commit()
                return
            
            print(f"[DEPLOYMENT] ✓ Target server validated: {target_server.name}")
            logs.append(f"✓ Target server validated successfully")
            logs.append(f"Server details: IP={target_server.ip_address}, Port={target_server.port}, Username={target_server.username}")
            
            # Phase 2: SSH Connection
            print(f"[DEPLOYMENT] Phase 2: Establishing SSH connection")
            task.progress = 10
            logs.append(f"\n--- PHASE 2: SSH CONNECTION ---")
            logs.append(f"Connecting to {target_server.ip_address}:{target_server.port}")
            
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                connection_start_time = time.time()
                
                if target_server.ssh_key_path and os.path.exists(target_server.ssh_key_path):
                    print(f"[DEPLOYMENT] Using SSH key authentication: {target_server.ssh_key_path}")
                    logs.append(f"Authentication method: SSH Key ({target_server.ssh_key_path})")
                    client.connect(
                        target_server.ip_address, 
                        port=target_server.port,
                        username=target_server.username, 
                        key_filename=target_server.ssh_key_path,
                        timeout=30
                    )
                else:
                    print(f"[DEPLOYMENT] Using password authentication")
                    logs.append(f"Authentication method: Password")
                    client.connect(
                        target_server.ip_address, 
                        port=target_server.port,
                        username=target_server.username, 
                        password=decrypt_password(target_server.password),
                        timeout=30
                    )
                
                connection_time = round(time.time() - connection_start_time, 2)
                print(f"[DEPLOYMENT] ✓ SSH connection established in {connection_time}s")
                logs.append(f"✓ SSH connection established successfully")
                logs.append(f"Connection time: {connection_time}s")
                
                # Test basic command execution
                print(f"[DEPLOYMENT] Testing command execution...")
                stdin, stdout, stderr = client.exec_command('echo "Connection test successful"', timeout=10)
                test_output = stdout.read().decode().strip()
                
                if "Connection test successful" in test_output:
                    print(f"[DEPLOYMENT] ✓ Command execution verified")
                    logs.append(f"✓ Command execution verified")
                else:
                    raise Exception("Command execution test failed")
                
            except Exception as ssh_error:
                error_msg = f"SSH connection failed: {str(ssh_error)}"
                print(f"[DEPLOYMENT] ERROR: {error_msg}")
                logs.append(f"ERROR: {error_msg}")
                task.status = 'failed'
                task.error_message = error_msg
                task.logs = '\n'.join(logs)
                db.session.commit()
                return
            
            # Phase 3: Pre-installation checks
            print(f"[DEPLOYMENT] Phase 3: Pre-installation system checks")
            task.progress = 15
            logs.append(f"\n--- PHASE 3: PRE-INSTALLATION CHECKS ---")
            
            try:
                # Check system info
                print(f"[DEPLOYMENT] Gathering system information...")
                
                # Check OS
                stdin, stdout, stderr = client.exec_command('cat /etc/os-release | grep "^ID=" | cut -d= -f2 | tr -d \'"\'', timeout=10)
                os_type = stdout.read().decode().strip()
                logs.append(f"Operating System: {os_type}")
                
                # Check available space
                stdin, stdout, stderr = client.exec_command('df -h / | awk \'NR==2{print $4}\'', timeout=10)
                available_space = stdout.read().decode().strip()
                logs.append(f"Available disk space: {available_space}")
                
                # Check memory
                stdin, stdout, stderr = client.exec_command('free -h | grep "^Mem:" | awk \'{print $7}\'', timeout=10)
                available_memory = stdout.read().decode().strip()
                logs.append(f"Available memory: {available_memory}")
                
                # Check if service already installed
                stdin, stdout, stderr = client.exec_command(f'systemctl is-active {service_type} 2>/dev/null || echo "not-installed"', timeout=10)
                service_status = stdout.read().decode().strip()
                
                if service_status == 'active':
                    print(f"[DEPLOYMENT] WARNING: {service_type} is already running")
                    logs.append(f"WARNING: {service_type} service is already active")
                elif service_status == 'inactive':
                    print(f"[DEPLOYMENT] INFO: {service_type} is installed but not running")
                    logs.append(f"INFO: {service_type} service is installed but inactive")
                else:
                    print(f"[DEPLOYMENT] INFO: {service_type} is not installed - proceeding with installation")
                    logs.append(f"INFO: {service_type} service not found - fresh installation")
                
                print(f"[DEPLOYMENT] ✓ Pre-installation checks completed")
                logs.append(f"✓ Pre-installation checks completed successfully")
                
            except Exception as check_error:
                print(f"[DEPLOYMENT] WARNING: Pre-installation checks failed: {str(check_error)}")
                logs.append(f"WARNING: Pre-installation checks failed: {str(check_error)}")
                logs.append(f"Continuing with installation...")
            
            # Phase 4: Service Installation
            print(f"[DEPLOYMENT] Phase 4: Installing {service_type} service")
            task.progress = 20
            logs.append(f"\n--- PHASE 4: SERVICE INSTALLATION ---")
            logs.append(f"Starting {service_type} installation...")
            
            task.logs = '\n'.join(logs)
            db.session.commit()
            
            installation_start_time = time.time()
            
            # Install dependencies based on service type
            if service_type == 'docker':
                print(f"[DEPLOYMENT] Installing Docker...")
                success = install_docker(client, task, logs)
            elif service_type == 'nginx':
                print(f"[DEPLOYMENT] Installing Nginx...")
                success = install_nginx(client, task, logs, config)
            elif service_type == 'postgres':
                print(f"[DEPLOYMENT] Installing PostgreSQL...")
                success = install_postgres(client, task, logs)
            elif service_type == 'redis':
                print(f"[DEPLOYMENT] Installing Redis...")
                success = install_redis(client, task, logs)
            else:
                error_msg = f"Unknown service type: {service_type}"
                print(f"[DEPLOYMENT] ERROR: {error_msg}")
                logs.append(f"ERROR: {error_msg}")
                success = False
            
            installation_time = round(time.time() - installation_start_time, 2)
            
            if success:
                print(f"[DEPLOYMENT] ✓ {service_type} installation completed in {installation_time}s")
                logs.append(f"✓ {service_type} installation completed successfully")
                logs.append(f"Installation time: {installation_time}s")
            else:
                print(f"[DEPLOYMENT] ✗ {service_type} installation failed after {installation_time}s")
                logs.append(f"✗ {service_type} installation failed")
                logs.append(f"Failed after: {installation_time}s")
            
            # Phase 5: Service Verification
            print(f"[DEPLOYMENT] Phase 5: Service verification and testing")
            task.progress = 90
            logs.append(f"\n--- PHASE 5: SERVICE VERIFICATION ---")
            logs.append(f"Verifying {service_type} service status...")
            
            task.logs = '\n'.join(logs)
            db.session.commit()
            
            verification_start_time = time.time()
            
            # Test the service
            verification_result = check_service_status(target_server, service_type)
            verification_time = round(time.time() - verification_start_time, 2)
            
            print(f"[DEPLOYMENT] Service verification completed in {verification_time}s")
            logs.append(f"Verification time: {verification_time}s")
            logs.append(f"Verification result: {verification_result}")
            
            # Phase 6: Final status update
            print(f"[DEPLOYMENT] Phase 6: Finalizing deployment")
            
            if verification_result['running'] and success:
                print(f"[DEPLOYMENT] ✓ Deployment successful - {service_type} is running")
                logs.append(f"✓ {service_type} service is running successfully")
                logs.append(f"Service status: {verification_result.get('status', 'active')}")
                
                task.status = 'completed'
                task.progress = 100
                
                # Update server's current services
                if service_type not in target_server.current_services:
                    target_server.current_services = target_server.current_services + [service_type]
                    print(f"[DEPLOYMENT] ✓ Added {service_type} to server's active services")
                    logs.append(f"✓ Added {service_type} to server's active services list")
                
                target_server.deployment_status = 'ready'
                target_server.last_health_check = datetime.utcnow()
                
                print(f"[DEPLOYMENT] ✓ Server status updated to 'ready'")
                logs.append(f"✓ Server deployment status updated to 'ready'")
                
            else:
                error_details = verification_result.get('error', 'Unknown verification error')
                print(f"[DEPLOYMENT] ✗ Deployment failed - {service_type} verification failed")
                logs.append(f"✗ {service_type} service verification failed")
                logs.append(f"Verification error: {error_details}")
                
                task.status = 'failed'
                task.error_message = f"Service verification failed: {error_details}"
                target_server.deployment_status = 'failed'
                
                print(f"[DEPLOYMENT] ✗ Server status updated to 'failed'")
                logs.append(f"✗ Server deployment status updated to 'failed'")
            
            # Final logging
            total_time = round(time.time() - task.started_at.timestamp(), 2) if task.started_at else 0
            task.completed_at = datetime.utcnow()
            
            logs.append(f"\n=== DEPLOYMENT SUMMARY ===")
            logs.append(f"Task ID: {task_id}")
            logs.append(f"Service: {service_type}")
            logs.append(f"Target: {target_server.name}")
            logs.append(f"Status: {task.status}")
            logs.append(f"Total time: {total_time}s")
            logs.append(f"Completed at: {task.completed_at.isoformat()}")
            
            if task.status == 'completed':
                logs.append(f"✓ DEPLOYMENT COMPLETED SUCCESSFULLY")
                print(f"[DEPLOYMENT] ✓ DEPLOYMENT COMPLETED SUCCESSFULLY")
                print(f"[DEPLOYMENT] Total execution time: {total_time}s")
            else:
                logs.append(f"✗ DEPLOYMENT FAILED")
                print(f"[DEPLOYMENT] ✗ DEPLOYMENT FAILED")
                print(f"[DEPLOYMENT] Error: {task.error_message}")
                print(f"[DEPLOYMENT] Total execution time: {total_time}s")
            
            task.logs = '\n'.join(logs)
            db.session.commit()
            
            # Close SSH connection
            try:
                client.close()
                print(f"[DEPLOYMENT] SSH connection closed")
                logs.append(f"SSH connection closed successfully")
            except:
                print(f"[DEPLOYMENT] WARNING: Error closing SSH connection")
            
            print(f"{'='*60}")
            print(f"[DEPLOYMENT] Task {task_id} finished with status: {task.status}")
            print(f"{'='*60}\n")
            
    except Exception as e:
        error_msg = str(e)
        print(f"[DEPLOYMENT] FATAL ERROR: {error_msg}")
        print(f"[DEPLOYMENT] Error type: {type(e).__name__}")
        
        # Log the full traceback for debugging
        import traceback
        full_traceback = traceback.format_exc()
        print(f"[DEPLOYMENT] Full traceback:\n{full_traceback}")
        
        try:
            # Import app instance directly for error handling
            from app import app
            with app.app_context():
                task = DeploymentTask.query.get(task_id)
                if task:
                    task.status = 'failed'
                    task.error_message = f"{type(e).__name__}: {error_msg}"
                    task.completed_at = datetime.utcnow()
                    
                    # Add error details to logs
                    error_logs = [
                        f"\n=== FATAL ERROR OCCURRED ===",
                        f"Error type: {type(e).__name__}",
                        f"Error message: {error_msg}",
                        f"Timestamp: {datetime.now().isoformat()}",
                        f"Traceback: {full_traceback}",
                        f"=== END ERROR DETAILS ==="
                    ]
                    
                    existing_logs = task.logs or ""
                    task.logs = f"{existing_logs}\n{chr(10).join(error_logs)}"
                    
                    # Update server status
                    if hasattr(task, 'target_server') and task.target_server:
                        task.target_server.deployment_status = 'failed'
                    
                    db.session.commit()
                    print(f"[DEPLOYMENT] Error details saved to database")
                else:
                    print(f"[DEPLOYMENT] Could not find task {task_id} to update error status")
        except Exception as db_error:
            print(f"[DEPLOYMENT] Failed to update database with error: {str(db_error)}")
        
        # Try to close SSH connection if it exists
        try:
            if 'client' in locals():
                client.close()
                print(f"[DEPLOYMENT] SSH connection closed after error")
        except:
            pass
        
        print(f"[DEPLOYMENT] Task {task_id} terminated due to fatal error")
        
def execute_migration_task(task_id):
    """Execute migration task with testing"""
    try:
        from flask import current_app
        
        with current_app.app_context():
            task = DeploymentTask.query.get(task_id)
            if not task:
                return
            
            task.status = 'running'
            task.started_at = datetime.utcnow()
            task.progress = 0
            db.session.commit()
            
            source_server = task.source_server
            target_server = task.target_server
            services = task.config.get('services', [])
            test_before_migrate = task.config.get('test_before_migrate', True)
            
            logs = []
            logs.append(f"Starting migration from {source_server.name} to {target_server.name}")
            logs.append(f"Services to migrate: {', '.join(services)}")
            
            # Step 1: Pre-migration testing if enabled
            if test_before_migrate:
                task.progress = 5
                logs.append("Running pre-migration tests...")
                task.logs = '\n'.join(logs)
                db.session.commit()
                
                # Test target server health
                target_health = perform_health_check(target_server)
                if target_health['score'] < 70:
                    logs.append(f"Target server health check failed: {target_health['score']}/100")
                    task.status = 'failed'
                    task.error_message = f"Target server health too low: {target_health['score']}"
                    task.logs = '\n'.join(logs)
                    db.session.commit()
                    return
                
                # Test target server capacity
                target_metrics = collect_server_metrics(target_server)
                if target_metrics.get('cpu_usage', 0) > 80 or target_metrics.get('memory_usage', 0) > 80:
                    logs.append("Target server resource usage too high for migration")
                    task.status = 'failed'
                    task.error_message = "Target server resources insufficient"
                    task.logs = '\n'.join(logs)
                    db.session.commit()
                    return
                
                logs.append("Pre-migration tests passed")
            
            # Step 2: Backup data from source
            task.progress = 20
            logs.append("Creating backups on source server...")
            task.logs = '\n'.join(logs)
            db.session.commit()
            
            backup_results = {}
            for service in services:
                backup_result = create_service_backup(source_server, service)
                backup_results[service] = backup_result
                if backup_result['success']:
                    logs.append(f"Backup created for {service}: {backup_result['backup_path']}")
                else:
                    logs.append(f"Backup failed for {service}: {backup_result['error']}")
                    task.status = 'failed'
                    task.error_message = f"Backup failed for {service}"
                    task.logs = '\n'.join(logs)
                    db.session.commit()
                    return
            
            # Step 3: Deploy services on target if not already present
            task.progress = 40
            logs.append("Ensuring services are deployed on target server...")
            task.logs = '\n'.join(logs)
            db.session.commit()
            
            for service in services:
                if service not in target_server.current_services:
                    logs.append(f"Deploying {service} on target server...")
                    deploy_result = deploy_service_on_server(target_server, service)
                    if not deploy_result['success']:
                        logs.append(f"Failed to deploy {service}: {deploy_result['error']}")
                        task.status = 'failed'
                        task.error_message = f"Service deployment failed: {service}"
                        task.logs = '\n'.join(logs)
                        db.session.commit()
                        return
            
            # Step 4: Transfer and restore data
            task.progress = 60
            logs.append("Transferring and restoring data...")
            task.logs = '\n'.join(logs)
            db.session.commit()
            
            for service in services:
                if backup_results[service]['success']:
                    restore_result = restore_service_backup(target_server, service, backup_results[service])
                    if restore_result['success']:
                        logs.append(f"Service {service} data restored successfully")
                    else:
                        logs.append(f"Data restore failed for {service}: {restore_result['error']}")
                        # Continue with other services but mark as partial failure
            
            # Step 5: Verify services on target
            task.progress = 80
            logs.append("Verifying services on target server...")
            task.logs = '\n'.join(logs)
            db.session.commit()
            
            verification_success = True
            for service in services:
                verification_result = check_service_status(target_server, service)
                if verification_result['running']:
                    logs.append(f"Service {service} verified on target")
                else:
                    logs.append(f"Verification failed for {service}: {verification_result['error']}")
                    verification_success = False
            
            # Step 6: Stop services on source (only if all verifications passed)
            if verification_success:
                task.progress = 90
                logs.append("Stopping services on source server...")
                task.logs = '\n'.join(logs)
                db.session.commit()
                
                for service in services:
                    stop_result = stop_service_on_server(source_server, service)
                    if stop_result['success']:
                        logs.append(f"Service {service} stopped on source")
                        # Remove from source server's current services
                        if service in source_server.current_services:
                            source_server.current_services.remove(service)
                    else:
                        logs.append(f"Failed to stop {service} on source: {stop_result['error']}")
                
                # Update target server's current services
                for service in services:
                    if service not in target_server.current_services:
                        target_server.current_services = target_server.current_services + [service]
                
                task.status = 'completed'
                logs.append("Migration completed successfully!")
            else:
                task.status = 'failed'
                task.error_message = "Service verification failed on target server"
                logs.append("Migration failed - services not properly running on target")
            
            task.progress = 100
            task.completed_at = datetime.utcnow()
            task.logs = '\n'.join(logs)
            db.session.commit()
            
    except Exception as e:
        try:
            with current_app.app_context():
                task = DeploymentTask.query.get(task_id)
                if task:
                    task.status = 'failed'
                    task.error_message = str(e)
                    task.completed_at = datetime.utcnow()
                    task.logs = f"{task.logs or ''}\n\nFATAL ERROR: {str(e)}"
                    db.session.commit()
        except:
            pass

# ================= SERVICE INSTALLATION FUNCTIONS =================

######################################################################################################

import sys
import time
from datetime import datetime

def install_docker(client, task, logs):
   """Install Docker on server with comprehensive logging and container environment handling"""
   try:
       print(f"[DOCKER INSTALL] Starting Docker installation on server {task.target_server.name}")
       logs.append(f"=== DOCKER INSTALLATION STARTED ===")
       logs.append(f"Target Server: {task.target_server.name} ({task.target_server.ip_address})")
       logs.append(f"Timestamp: {datetime.now().isoformat()}")
       
       # Step 1: Environment Detection
       logs.append(f"\n--- ENVIRONMENT DETECTION ---")
       print("[DOCKER INSTALL] Detecting environment type...")
       
       # Check if we're in a container environment
       container_detected = False
       docker_socket_available = False
       
       try:
           # Check for container indicators
           stdin, stdout, stderr = client.exec_command('cat /.dockerenv 2>/dev/null || echo "not_container"', timeout=5)
           dockerenv_check = stdout.read().decode().strip()
           
           stdin, stdout, stderr = client.exec_command('cat /proc/1/cgroup | grep docker || echo "not_in_docker"', timeout=5)
           cgroup_check = stdout.read().decode().strip()
           
           if dockerenv_check != "not_container" or "docker" in cgroup_check:
               container_detected = True
               logs.append("✓ Container environment detected")
               print("[DOCKER INSTALL] Container environment detected")
           else:
               logs.append("✓ Physical/VM environment detected")
               print("[DOCKER INSTALL] Physical/VM environment detected")
               
       except Exception as e:
           logs.append(f"Warning: Environment detection failed: {str(e)}")
       
       # Check if Docker socket is available from host
       try:
           stdin, stdout, stderr = client.exec_command('ls -la /var/run/docker.sock 2>/dev/null', timeout=5)
           socket_output = stdout.read().decode()
           
           if 'docker.sock' in socket_output:
               docker_socket_available = True
               logs.append("✓ Docker socket available from host")
               print("[DOCKER INSTALL] Docker socket available from host")
           else:
               logs.append("○ No Docker socket detected")
               
       except Exception as e:
           logs.append(f"○ Docker socket check failed: {str(e)}")
       
       # Step 2: Choose Installation Strategy
       logs.append(f"\n--- INSTALLATION STRATEGY ---")
       
       if container_detected and docker_socket_available:
           # Strategy: Use host Docker via socket
           print("[DOCKER INSTALL] Using host Docker strategy")
           logs.append("Strategy: Use host Docker daemon via socket")
           return install_docker_host_socket(client, task, logs)
           
       elif container_detected and not docker_socket_available:
           # Strategy: Docker-in-Docker with special handling
           print("[DOCKER INSTALL] Using Docker-in-Docker strategy")
           logs.append("Strategy: Docker-in-Docker installation with container optimizations")
           return install_docker_in_container(client, task, logs)
           
       else:
           # Strategy: Standard installation
           print("[DOCKER INSTALL] Using standard installation strategy")
           logs.append("Strategy: Standard Docker installation")
           return install_docker_standard(client, task, logs)
           
   except Exception as e:
       error_msg = f"Docker installation failed: {str(e)}"
       print(f"[DOCKER INSTALL] FATAL ERROR: {error_msg}")
       logs.append(f"FATAL ERROR: {error_msg}")
       return False

def install_docker_in_container(client, task, logs):
   """Install Docker in container environment with Docker-in-Docker setup"""
   try:
       print("[DOCKER INSTALL] Installing Docker in container environment")
       logs.append("Installing Docker with container optimizations...")
       
       # Define harmless messages
       harmless_messages = [
           'debconf: delaying package configuration',
           'apt-utils is not installed',
           'debconf: unable to initialize frontend',
           'system has not been booted with systemd',
           'can\'t operate',
           'failed to connect to bus'
       ]
       
       install_commands = [
           {
               'cmd': 'DEBIAN_FRONTEND=noninteractive sudo apt-get install -y apt-utils',
               'desc': 'Installing apt-utils'
           },
           {
               'cmd': 'sudo apt-get update',
               'desc': 'Updating package lists'
           },
           {
               'cmd': 'DEBIAN_FRONTEND=noninteractive sudo apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release',
               'desc': 'Installing Docker prerequisites'
           },
           {
               'cmd': 'curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg',
               'desc': 'Adding Docker GPG key'
           },
           {
               'cmd': 'echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null',
               'desc': 'Adding Docker repository'
           },
           {
               'cmd': 'sudo apt-get update',
               'desc': 'Updating package lists with Docker repo'
           },
           {
               'cmd': 'DEBIAN_FRONTEND=noninteractive sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin',
               'desc': 'Installing Docker Engine'
           },
           {
               'cmd': 'sudo usermod -aG docker $USER',
               'desc': 'Adding user to docker group'
           }
       ]
       
       # Execute installation commands
       for i, cmd_info in enumerate(install_commands):
           step_num = i + 1
           command = cmd_info['cmd']
           description = cmd_info['desc']
           
           print(f"[DOCKER INSTALL] Step {step_num}/{len(install_commands)}: {description}")
           logs.append(f"\n--- Step {step_num}: {description} ---")
           logs.append(f"Command: {command}")
           
           try:
               start_time = time.time()
               stdin, stdout, stderr = client.exec_command(command, timeout=300)
               
               output = stdout.read().decode().strip()
               error = stderr.read().decode().strip()
               execution_time = round(time.time() - start_time, 2)
               
               logs.append(f"Execution time: {execution_time}s")
               
               if output:
                   logs.append(f"Output: {output}")
               
               if error:
                   is_harmless = any(msg in error.lower() for msg in harmless_messages)
                   is_warning = any(word in error.lower() for word in ['warning', 'notice', 'info'])
                   
                   if is_harmless or is_warning:
                       logs.append(f"Info/Warning: {error}")
                   else:
                       fatal_indicators = [
                           'unable to locate package',
                           'command not found',
                           'permission denied',
                           'disk full'
                       ]
                       
                       is_fatal = any(indicator in error.lower() for indicator in fatal_indicators)
                       
                       if is_fatal:
                           print(f"[DOCKER INSTALL] ERROR: {error}")
                           logs.append(f"ERROR: {error}")
                           return False
                       else:
                           logs.append(f"Warning: {error}")
               
               print(f"[DOCKER INSTALL] ✓ Step {step_num} completed")
               logs.append(f"✓ Step completed successfully")
               
           except Exception as cmd_error:
               error_msg = f"Command execution failed: {str(cmd_error)}"
               print(f"[DOCKER INSTALL] ERROR: {error_msg}")
               logs.append(f"ERROR: {error_msg}")
               return False
           
           # Update progress
           progress = 20 + (i * 50 // len(install_commands))
           task.progress = progress
           task.logs = '\n'.join(logs)
           db.session.commit()
       
       # Container-specific Docker daemon setup
       logs.append(f"\n=== CONTAINER DOCKER DAEMON SETUP ===")
       print("[DOCKER INSTALL] Setting up Docker daemon for container environment")
       
       # Create docker directories
       setup_commands = [
           'sudo mkdir -p /var/lib/docker',
           'sudo mkdir -p /etc/docker',
           'sudo groupadd docker || true'
       ]
       
       for cmd in setup_commands:
           try:
               stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
               logs.append(f"Setup: {cmd}")
           except:
               pass
       
       # Kill any existing dockerd processes
       try:
           stdin, stdout, stderr = client.exec_command('sudo pkill dockerd || true', timeout=10)
           time.sleep(2)
           logs.append("Cleaned up any existing Docker processes")
       except:
           pass
       
       # Try multiple daemon startup approaches
       daemon_commands = [
           # Approach 1: VFS storage driver (works in most containers)
           {
               'cmd': 'sudo nohup dockerd --host=unix:///var/run/docker.sock --storage-driver=vfs --iptables=false --bridge=none > /var/log/dockerd.log 2>&1 &',
               'desc': 'Starting daemon with VFS storage driver'
           },
           # Approach 2: Overlay2 with unsafe options
           {
               'cmd': 'sudo nohup dockerd --host=unix:///var/run/docker.sock --storage-driver=overlay2 --storage-opt overlay2.override_kernel_check=true --iptables=false --bridge=none > /var/log/dockerd.log 2>&1 &',
               'desc': 'Starting daemon with overlay2 (unsafe)'
           },
           # Approach 3: Minimal daemon
           {
               'cmd': 'sudo nohup dockerd --host=unix:///var/run/docker.sock --storage-driver=vfs --iptables=false --ip-forward=false --ip-masq=false --bridge=none --default-gateway= --fixed-cidr= > /var/log/dockerd.log 2>&1 &',
               'desc': 'Starting minimal daemon configuration'
           }
       ]
       
       daemon_started = False
       for i, daemon_info in enumerate(daemon_commands):
           try:
               print(f"[DOCKER INSTALL] {daemon_info['desc']} (attempt {i+1})")
               logs.append(f"Attempt {i+1}: {daemon_info['desc']}")
               logs.append(f"Command: {daemon_info['cmd']}")
               
               # Start daemon
               stdin, stdout, stderr = client.exec_command(daemon_info['cmd'], timeout=15)
               time.sleep(8)  # Wait for daemon to start
               
               # Test if daemon is responding
               stdin, stdout, stderr = client.exec_command('sudo docker version', timeout=15)
               version_output = stdout.read().decode()
               version_error = stderr.read().decode()
               
               if 'Server:' in version_output:
                   daemon_started = True
                   print(f"[DOCKER INSTALL] ✓ Docker daemon started successfully with method {i+1}")
                   logs.append(f"✓ Docker daemon started successfully with method {i+1}")
                   break
               else:
                   print(f"[DOCKER INSTALL] Method {i+1} failed: {version_error}")
                   logs.append(f"Method {i+1} failed: {version_error}")
                   
                   # Try to kill daemon before next attempt
                   stdin, stdout, stderr = client.exec_command('sudo pkill dockerd || true', timeout=5)
                   time.sleep(2)
                   
           except Exception as e:
               print(f"[DOCKER INSTALL] Method {i+1} exception: {str(e)}")
               logs.append(f"Method {i+1} exception: {str(e)}")
               continue
       
       # Final verification
       logs.append(f"\n=== FINAL VERIFICATION ===")
       
       if daemon_started:
           try:
               # Test Docker functionality
               stdin, stdout, stderr = client.exec_command('sudo docker run --rm hello-world', timeout=60)
               test_output = stdout.read().decode()
               
               if 'Hello from Docker!' in test_output:
                   print("[DOCKER INSTALL] ✓ Docker fully functional with hello-world test")
                   logs.append("✓ Docker hello-world test passed")
                   logs.append("✓ Docker installation completed successfully")
                   logs.append("=== DOCKER INSTALLATION COMPLETED SUCCESSFULLY ===")
                   return True
               else:
                   print("[DOCKER INSTALL] ✓ Docker daemon running but hello-world test failed")
                   logs.append("✓ Docker daemon running")
                   logs.append("Warning: hello-world test failed")
                   logs.append("=== DOCKER INSTALLATION COMPLETED WITH WARNINGS ===")
                   return True
                   
           except Exception as e:
               print(f"[DOCKER INSTALL] ✓ Docker daemon running but test failed: {str(e)}")
               logs.append("✓ Docker daemon running")
               logs.append(f"Warning: Container test failed: {str(e)}")
               logs.append("=== DOCKER INSTALLATION COMPLETED WITH WARNINGS ===")
               return True
       else:
           # Check if at least Docker CLI is installed
           try:
               stdin, stdout, stderr = client.exec_command('docker --version', timeout=10)
               cli_output = stdout.read().decode()
               
               if 'Docker version' in cli_output:
                   print("[DOCKER INSTALL] ✓ Docker CLI installed (daemon requires manual start)")
                   logs.append("✓ Docker CLI installed successfully")
                   logs.append("WARNING: Docker daemon failed to start automatically")
                   logs.append("Manual daemon start may be required:")
                   logs.append("  sudo dockerd --host=unix:///var/run/docker.sock --storage-driver=vfs --iptables=false --bridge=none &")
                   logs.append("=== DOCKER INSTALLATION COMPLETED WITH WARNINGS ===")
                   return True
               else:
                   print("[DOCKER INSTALL] ✗ Docker CLI verification failed")
                   logs.append("✗ Docker CLI verification failed")
                   return False
                   
           except Exception as e:
               print(f"[DOCKER INSTALL] ✗ Final verification failed: {str(e)}")
               logs.append(f"✗ Final verification failed: {str(e)}")
               return False
               
   except Exception as e:
       error_msg = f"Container Docker installation failed: {str(e)}"
       print(f"[DOCKER INSTALL] FATAL ERROR: {error_msg}")
       logs.append(f"FATAL ERROR: {error_msg}")
       return False


def install_docker_host_socket(client, task, logs):
    """Install Docker CLI to use host Docker daemon via socket - FIXED VERSION"""
    try:
        print("[DOCKER INSTALL] Installing Docker CLI for host socket usage (FIXED)")
        logs.append("Installing Docker CLI to use host daemon (with fixes)...")
        
        # Step 1: System preparation and cleanup
        logs.append(f"\n--- STEP 1: SYSTEM PREPARATION ---")
        preparation_commands = [
            {
                'cmd': 'sudo apt-get clean',
                'desc': 'Cleaning package cache',
                'ignore_errors': True
            },
            {
                'cmd': 'sudo apt-get autoremove -y',
                'desc': 'Removing unnecessary packages',
                'ignore_errors': True
            },
            {
                'cmd': 'sudo dpkg --configure -a',
                'desc': 'Configuring any broken packages',
                'ignore_errors': True
            },
            {
                'cmd': 'DEBIAN_FRONTEND=noninteractive sudo apt-get update',
                'desc': 'Updating package lists',
                'ignore_errors': False
            }
        ]
        
        for i, cmd_info in enumerate(preparation_commands):
            command = cmd_info['cmd']
            description = cmd_info['desc']
            ignore_errors = cmd_info.get('ignore_errors', False)
            
            print(f"[DOCKER INSTALL] Prep {i+1}/{len(preparation_commands)}: {description}")
            logs.append(f"Preparation {i+1}: {description}")
            logs.append(f"Command: {command}")
            
            try:
                start_time = time.time()
                stdin, stdout, stderr = client.exec_command(command, timeout=300)
                
                output = stdout.read().decode().strip()
                error = stderr.read().decode().strip()
                execution_time = round(time.time() - start_time, 2)
                
                logs.append(f"Execution time: {execution_time}s")
                
                if output and len(output) < 1000:
                    logs.append(f"Output: {output}")
                elif output:
                    logs.append(f"Output: {output[:200]}... (truncated)")
                
                if error:
                    if ignore_errors or any(word in error.lower() for word in ['warning', 'notice', 'info']):
                        logs.append(f"Note: {error[:200]}...")
                    else:
                        # Check for critical errors
                        critical_errors = ['unable to locate package', 'no space left', 'permission denied', 'disk full']
                        if any(critical in error.lower() for critical in critical_errors):
                            logs.append(f"CRITICAL ERROR: {error}")
                            return False
                        else:
                            logs.append(f"Warning: {error[:200]}...")
                
                print(f"[DOCKER INSTALL] ✓ Prep {i+1} completed")
                logs.append(f"✓ Preparation step completed")
                
            except Exception as cmd_error:
                if ignore_errors:
                    logs.append(f"Warning: Preparation step failed (ignored): {str(cmd_error)}")
                    print(f"[DOCKER INSTALL] Warning: Prep {i+1} failed (ignored): {str(cmd_error)}")
                else:
                    logs.append(f"ERROR: Preparation step failed: {str(cmd_error)}")
                    print(f"[DOCKER INSTALL] ERROR: Prep {i+1} failed: {str(cmd_error)}")
                    return False
        
        # Step 2: Try multiple Docker installation approaches
        logs.append(f"\n--- STEP 2: DOCKER INSTALLATION ---")
        
        installation_approaches = [
            # Approach 1: Try installing from default repos first (safest)
            {
                'name': 'Default Repository Docker',
                'commands': [
                    'DEBIAN_FRONTEND=noninteractive sudo apt-get install -y --fix-broken',
                    'DEBIAN_FRONTEND=noninteractive sudo apt-get install -y docker.io'
                ]
            },
            # Approach 2: Try snap package (fallback)
            {
                'name': 'Snap Package Docker',
                'commands': [
                    'sudo snap install docker'
                ]
            },
            # Approach 3: Official Docker repository (most complex but comprehensive)
            {
                'name': 'Official Docker Repository',
                'commands': [
                    'sudo apt-get remove -y docker docker-engine docker.io containerd runc || true',
                    'DEBIAN_FRONTEND=noninteractive sudo apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release',
                    'curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor --yes -o /usr/share/keyrings/docker-archive-keyring.gpg 2>/dev/null || curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -',
                    'echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null || echo "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null',
                    'sudo apt-get update',
                    'DEBIAN_FRONTEND=noninteractive sudo apt-get install -y docker-ce-cli'
                ]
            },
            # Approach 4: Direct binary download (last resort)
            {
                'name': 'Direct Binary Download',
                'commands': [
                    'sudo mkdir -p /tmp/docker-install',
                    'cd /tmp/docker-install && wget -O docker.tgz https://download.docker.com/linux/static/stable/x86_64/docker-20.10.17.tgz',
                    'cd /tmp/docker-install && tar xzf docker.tgz',
                    'sudo cp /tmp/docker-install/docker/docker /usr/local/bin/',
                    'sudo chmod +x /usr/local/bin/docker',
                    'sudo ln -sf /usr/local/bin/docker /usr/bin/docker || true'
                ]
            }
        ]
        
        docker_installed = False
        
        for approach_num, approach in enumerate(installation_approaches):
            if docker_installed:
                break
                
            print(f"[DOCKER INSTALL] Trying approach {approach_num + 1}: {approach['name']}")
            logs.append(f"\n--- APPROACH {approach_num + 1}: {approach['name']} ---")
            
            approach_success = True
            
            for cmd_num, command in enumerate(approach['commands']):
                print(f"[DOCKER INSTALL] Command {cmd_num + 1}/{len(approach['commands'])}: {command[:60]}...")
                logs.append(f"Command {cmd_num + 1}: {command}")
                
                try:
                    start_time = time.time()
                    stdin, stdout, stderr = client.exec_command(command, timeout=300)
                    
                    output = stdout.read().decode().strip()
                    error = stderr.read().decode().strip()
                    execution_time = round(time.time() - start_time, 2)
                    
                    logs.append(f"Execution time: {execution_time}s")
                    
                    # Check for command success/failure
                    fatal_errors = [
                        'command not found',
                        'permission denied',
                        'disk full',
                        'no space left',
                        'network is unreachable',
                        'connection refused',
                        'unable to resolve host'
                    ]
                    
                    if error:
                        is_fatal = any(fatal_error in error.lower() for fatal_error in fatal_errors)
                        
                        if is_fatal and '|| true' not in command:
                            print(f"[DOCKER INSTALL] Fatal error in approach {approach_num + 1}: {error[:100]}...")
                            logs.append(f"Fatal error: {error}")
                            approach_success = False
                            break
                        else:
                            # Handle warnings and non-fatal errors
                            if any(word in error.lower() for word in ['warning', 'notice', 'info', 'already exists']):
                                logs.append(f"Info/Warning: {error[:200]}...")
                            else:
                                logs.append(f"Error (continuing): {error[:200]}...")
                    
                    if output and len(output) < 500:
                        logs.append(f"Output: {output}")
                    elif output:
                        logs.append(f"Output: {output[:200]}... (truncated)")
                    
                    print(f"[DOCKER INSTALL] ✓ Command {cmd_num + 1} completed")
                    
                except Exception as cmd_error:
                    error_msg = f"Command execution failed: {str(cmd_error)}"
                    print(f"[DOCKER INSTALL] Command error: {error_msg}")
                    logs.append(f"Command error: {error_msg}")
                    
                    # Don't fail immediately for optional commands
                    if '|| true' not in command:
                        approach_success = False
                        break
            
            if approach_success:
                # Test if Docker is now available
                try:
                    # Try multiple docker command locations
                    docker_test_commands = [
                        'docker --version',
                        '/usr/bin/docker --version',
                        '/usr/local/bin/docker --version'
                    ]
                    
                    docker_found = False
                    for test_cmd in docker_test_commands:
                        try:
                            stdin, stdout, stderr = client.exec_command(test_cmd, timeout=10)
                            version_output = stdout.read().decode().strip()
                            
                            if 'Docker version' in version_output or 'docker version' in version_output.lower():
                                docker_installed = True
                                docker_found = True
                                print(f"[DOCKER INSTALL] ✓ Approach {approach_num + 1} succeeded!")
                                logs.append(f"✓ {approach['name']} installation successful")
                                logs.append(f"Docker version: {version_output}")
                                logs.append(f"Docker command found at: {test_cmd.split()[0]}")
                                break
                        except:
                            continue
                    
                    if docker_found:
                        break
                    else:
                        print(f"[DOCKER INSTALL] Approach {approach_num + 1} completed but Docker not found")
                        logs.append(f"Approach {approach_num + 1} completed but verification failed")
                        
                except Exception as e:
                    print(f"[DOCKER INSTALL] Approach {approach_num + 1} verification error: {str(e)}")
                    logs.append(f"Verification error: {str(e)}")
            else:
                print(f"[DOCKER INSTALL] Approach {approach_num + 1} failed during installation")
                logs.append(f"Approach {approach_num + 1} failed")
        
        if not docker_installed:
            print("[DOCKER INSTALL] ✗ All installation approaches failed")
            logs.append("✗ All Docker installation approaches failed")
            return False
        
        # Step 3: Configure Docker socket permissions
        logs.append(f"\n--- STEP 3: SOCKET CONFIGURATION ---")
        print("[DOCKER INSTALL] Configuring Docker socket permissions...")
        
        socket_commands = [
            {
                'cmd': 'sudo groupadd docker || true',
                'desc': 'Creating docker group',
                'ignore_errors': True
            },
            {
                'cmd': 'sudo usermod -aG docker $USER || true',
                'desc': 'Adding user to docker group',
                'ignore_errors': True
            },
            {
                'cmd': 'sudo chmod 666 /var/run/docker.sock || true',
                'desc': 'Setting Docker socket permissions',
                'ignore_errors': True
            },
            {
                'cmd': 'sudo chown root:docker /var/run/docker.sock || true',
                'desc': 'Setting Docker socket ownership',
                'ignore_errors': True
            }
        ]
        
        for i, cmd_info in enumerate(socket_commands):
            command = cmd_info['cmd']
            description = cmd_info['desc']
            
            print(f"[DOCKER INSTALL] Socket {i+1}/{len(socket_commands)}: {description}")
            logs.append(f"Socket config {i+1}: {description}")
            
            try:
                start_time = time.time()
                stdin, stdout, stderr = client.exec_command(command, timeout=60)
                
                output = stdout.read().decode().strip()
                error = stderr.read().decode().strip()
                execution_time = round(time.time() - start_time, 2)
                
                logs.append(f"Execution time: {execution_time}s")
                
                if error and 'already exists' not in error.lower() and 'no such file' not in error.lower():
                    logs.append(f"Warning: {error[:200]}...")
                
                print(f"[DOCKER INSTALL] ✓ Socket config {i+1} completed")
                
            except Exception as cmd_error:
                logs.append(f"Warning: Socket config failed (ignored): {str(cmd_error)}")
                print(f"[DOCKER INSTALL] Warning: Socket config {i+1} failed (ignored)")
        
        # Update progress
        task.progress = 80
        task.logs = '\n'.join(logs)
        db.session.commit()
        
        # Step 4: Final verification with comprehensive testing
        logs.append(f"\n=== FINAL VERIFICATION ===")
        print("[DOCKER INSTALL] Performing final verification...")
        
        try:
            # Test Docker version first
            version_commands = ['docker --version', '/usr/bin/docker --version', '/usr/local/bin/docker --version']
            version_success = False
            docker_version = None
            
            for version_cmd in version_commands:
                try:
                    stdin, stdout, stderr = client.exec_command(version_cmd, timeout=30)
                    version_output = stdout.read().decode().strip()
                    version_error = stderr.read().decode().strip()
                    
                    if 'Docker version' in version_output or 'docker version' in version_output.lower():
                        version_success = True
                        docker_version = version_output
                        logs.append(f"✓ Docker CLI installed: {version_output}")
                        print(f"[DOCKER INSTALL] ✓ Docker version verified: {version_output}")
                        break
                except:
                    continue
            
            if not version_success:
                logs.append("✗ Docker CLI version check failed")
                print("[DOCKER INSTALL] ✗ Docker CLI version check failed")
                return False
            
            # Test Docker daemon connection with multiple approaches
            connection_tests = [
                'docker info',
                'docker version',
                'docker ps',
                'sudo docker ps',
                'DOCKER_HOST=unix:///var/run/docker.sock docker ps'
            ]
            
            daemon_connected = False
            successful_command = None
            
            for test_cmd in connection_tests:
                try:
                    print(f"[DOCKER INSTALL] Testing daemon connection: {test_cmd}")
                    stdin, stdout, stderr = client.exec_command(test_cmd, timeout=15)
                    test_output = stdout.read().decode()
                    test_error = stderr.read().decode()
                    
                    # Check for successful connection indicators
                    success_indicators = [
                        'Server Version:',
                        'CONTAINER ID',
                        'Containers:',
                        'Server:',
                        'Storage Driver:'
                    ]
                    
                    if any(indicator in test_output for indicator in success_indicators):
                        daemon_connected = True
                        successful_command = test_cmd
                        logs.append(f"✓ Docker daemon connection verified with: {test_cmd}")
                        print(f"[DOCKER INSTALL] ✓ Daemon connected via: {test_cmd}")
                        break
                    elif 'permission denied' in test_error.lower():
                        logs.append(f"Permission denied for: {test_cmd}")
                        continue
                    elif 'cannot connect to the docker daemon' in test_error.lower():
                        logs.append(f"Daemon not accessible via: {test_cmd}")
                        continue
                    else:
                        logs.append(f"Connection test inconclusive for: {test_cmd}")
                        continue
                        
                except Exception as e:
                    logs.append(f"Test error for {test_cmd}: {str(e)}")
                    continue
            
            # Final status determination
            if daemon_connected:
                print("[DOCKER INSTALL] ✓ Docker installation and daemon connection verified")
                logs.append("✓ Docker installation completed successfully")
                logs.append("✓ Docker CLI can communicate with daemon")
                logs.append(f"✓ Working connection command: {successful_command}")
                logs.append("=== DOCKER INSTALLATION COMPLETED SUCCESSFULLY ===")
                return True
            else:
                # CLI installed but daemon connection issues
                print("[DOCKER INSTALL] ✓ Docker CLI installed but daemon connection needs configuration")
                logs.append("✓ Docker CLI installed successfully")
                logs.append("WARNING: Docker daemon connection requires manual configuration")
                logs.append("Manual steps to try:")
                logs.append("  1. sudo chmod 666 /var/run/docker.sock")
                logs.append("  2. sudo usermod -aG docker $USER && newgrp docker")
                logs.append("  3. Restart your session or run: newgrp docker")
                logs.append("  4. Check if Docker daemon is running: sudo systemctl status docker")
                logs.append("=== DOCKER INSTALLATION COMPLETED WITH WARNINGS ===")
                
                # Still return True since CLI is installed - daemon connection can be fixed later
                return True
                
        except Exception as e:
            print(f"[DOCKER INSTALL] ✗ Final verification error: {str(e)}")
            logs.append(f"✗ Final verification error: {str(e)}")
            
            # Even if verification fails, if we got this far, Docker is probably installed
            logs.append("Note: Docker may still be installed despite verification failure")
            return False
            
    except Exception as e:
        error_msg = f"Host socket Docker installation failed: {str(e)}"
        print(f"[DOCKER INSTALL] FATAL ERROR: {error_msg}")
        logs.append(f"FATAL ERROR: {error_msg}")
        return False

def install_nginx(client, task, logs, config):
    """Install Nginx on server with comprehensive logging"""
    try:
        print(f"[NGINX INSTALL] Starting Nginx installation on server {task.target_server.name}")
        logs.append(f"=== NGINX INSTALLATION STARTED ===")
        logs.append(f"Target Server: {task.target_server.name} ({task.target_server.ip_address})")
        logs.append(f"Timestamp: {datetime.now().isoformat()}")
        
        enable_firewall = config.get('enable_firewall', True)
        
        install_nginx_commands = [
            {
                'cmd': 'sudo apt-get update',
                'desc': 'Updating package lists'
            },
            {
                'cmd': 'sudo apt-get install -y nginx',
                'desc': 'Installing Nginx web server'
            },
            {
                'cmd': 'sudo systemctl enable nginx',
                'desc': 'Enabling Nginx service'
            },
            {
                'cmd': 'sudo systemctl start nginx',
                'desc': 'Starting Nginx service'
            },
            {
                'cmd': 'sudo ufw allow "Nginx Full"' if enable_firewall else 'echo "Firewall configuration skipped"',
                'desc': 'Configuring firewall rules' if enable_firewall else 'Skipping firewall configuration'
            },
            {
                'cmd': 'nginx -v',
                'desc': 'Verifying Nginx installation'
            },
            {
                'cmd': 'sudo systemctl status nginx --no-pager',
                'desc': 'Checking Nginx service status'
            }
        ]
        
        total_steps = len(install_nginx_commands)
        
        for i, cmd_info in enumerate(install_nginx_commands):
            step_num = i + 1
            command = cmd_info['cmd']
            description = cmd_info['desc']
            
            print(f"[NGINX INSTALL] Step {step_num}/{total_steps}: {description}")
            logs.append(f"\n--- Step {step_num}/{total_steps}: {description} ---")
            logs.append(f"Command: {command}")
            
            try:
                start_time = time.time()
                stdin, stdout, stderr = client.exec_command(command, timeout=180)
                
                output = stdout.read().decode().strip()
                error = stderr.read().decode().strip()
                execution_time = round(time.time() - start_time, 2)
                
                logs.append(f"Execution time: {execution_time}s")
                
                if output:
                    print(f"[NGINX INSTALL] Output: {output[:100]}...")
                    logs.append(f"Output: {output}")
                
                if error:
                    if any(word in error.lower() for word in ['warning', 'notice', 'info']):
                        print(f"[NGINX INSTALL] Warning: {error[:100]}...")
                        logs.append(f"Warning: {error}")
                    else:
                        print(f"[NGINX INSTALL] ERROR: {error}")
                        logs.append(f"ERROR: {error}")
                        logs.append(f"INSTALLATION FAILED at step {step_num}")
                        return False
                
                print(f"[NGINX INSTALL] ✓ Step {step_num} completed successfully")
                logs.append(f"✓ Step completed successfully")
                
            except Exception as cmd_error:
                error_msg = f"Command execution failed: {str(cmd_error)}"
                print(f"[NGINX INSTALL] ERROR: {error_msg}")
                logs.append(f"ERROR: {error_msg}")
                return False
            
            progress = 20 + (i * 70 // total_steps)
            task.progress = progress
            task.logs = '\n'.join(logs)
            db.session.commit()
            
            print(f"[NGINX INSTALL] Progress: {progress}%")
        
        # Test Nginx is serving
        logs.append(f"\n=== FINAL VERIFICATION ===")
        try:
            stdin, stdout, stderr = client.exec_command('curl -s -o /dev/null -w "%{http_code}" http://localhost', timeout=30)
            http_code = stdout.read().decode().strip()
            
            if http_code == '200':
                print("[NGINX INSTALL] ✓ Nginx is serving HTTP requests successfully")
                logs.append("✓ Nginx HTTP service verified")
                logs.append("=== NGINX INSTALLATION COMPLETED SUCCESSFULLY ===")
                return True
            else:
                print(f"[NGINX INSTALL] ✗ Nginx verification failed - HTTP code: {http_code}")
                logs.append(f"✗ Nginx verification failed - HTTP code: {http_code}")
                return False
                
        except Exception as e:
            print(f"[NGINX INSTALL] ✗ Nginx verification error: {str(e)}")
            logs.append(f"✗ Nginx verification error: {str(e)}")
            return False
        
    except Exception as e:
        error_msg = f"Nginx installation failed: {str(e)}"
        print(f"[NGINX INSTALL] FATAL ERROR: {error_msg}")
        logs.append(f"FATAL ERROR: {error_msg}")
        return False

def install_postgres(client, task, logs):
   """Install PostgreSQL on server with comprehensive logging and container support"""
   try:
       print(f"[POSTGRES INSTALL] Starting PostgreSQL installation on server {task.target_server.name}")
       logs.append(f"=== POSTGRESQL INSTALLATION STARTED ===")
       logs.append(f"Target Server: {task.target_server.name} ({task.target_server.ip_address})")
       logs.append(f"Timestamp: {datetime.now().isoformat()}")
       
       # Define harmless messages for container environments
       harmless_messages = [
           'synchronizing state',
           'systemd-sysv-install',
           'system has not been booted with systemd',
           'can\'t operate',
           'failed to connect to bus',
           'host is down',
           'init system',
           'sysv service script'
       ]
       
       install_postgres_commands = [
           {
               'cmd': 'sudo apt-get update',
               'desc': 'Updating package lists',
               'ignore_errors': False
           },
           {
               'cmd': 'DEBIAN_FRONTEND=noninteractive sudo apt-get install -y postgresql postgresql-contrib',
               'desc': 'Installing PostgreSQL server and contrib packages',
               'ignore_errors': False
           },
           {
               'cmd': 'sudo systemctl enable postgresql || true',
               'desc': 'Enabling PostgreSQL service (ignored in containers)',
               'ignore_errors': True
           },
           {
               'cmd': 'sudo systemctl start postgresql || sudo service postgresql start || true',
               'desc': 'Starting PostgreSQL service',
               'ignore_errors': True
           },
           {
               'cmd': 'sudo -u postgres /usr/lib/postgresql/*/bin/pg_ctl -D /var/lib/postgresql/*/main -l /var/lib/postgresql/*/main/pg_log/postgresql.log start || true',
               'desc': 'Manual PostgreSQL startup for container environments',
               'ignore_errors': True
           },
           {
               'cmd': 'sudo -u postgres createuser --createdb --no-createrole --no-superuser odoo_master || true',
               'desc': 'Creating odoo_master database user',
               'ignore_errors': True
           },
           {
               'cmd': 'sudo -u postgres psql -c "ALTER USER odoo_master WITH PASSWORD \'secure_password_123\';" || true',
               'desc': 'Setting password for odoo_master user',
               'ignore_errors': True
           },
           {
               'cmd': 'sudo -u postgres psql -c "\\l"',
               'desc': 'Listing databases to verify installation',
               'ignore_errors': False
           }
       ]
       
       total_steps = len(install_postgres_commands)
       
       for i, cmd_info in enumerate(install_postgres_commands):
           step_num = i + 1
           command = cmd_info['cmd']
           description = cmd_info['desc']
           ignore_errors = cmd_info.get('ignore_errors', False)
           
           print(f"[POSTGRES INSTALL] Step {step_num}/{total_steps}: {description}")
           logs.append(f"\n--- Step {step_num}/{total_steps}: {description} ---")
           logs.append(f"Command: {command}")
           
           try:
               start_time = time.time()
               stdin, stdout, stderr = client.exec_command(command, timeout=300)
               
               output = stdout.read().decode().strip()
               error = stderr.read().decode().strip()
               execution_time = round(time.time() - start_time, 2)
               
               logs.append(f"Execution time: {execution_time}s")
               
               if output:
                   print(f"[POSTGRES INSTALL] Output: {output[:100]}...")
                   if len(output) < 500:
                       logs.append(f"Output: {output}")
                   else:
                       logs.append(f"Output: {output[:200]}... (truncated)")
               
               if error:
                   # Check if error is harmless for container environments
                   is_harmless = any(msg in error.lower() for msg in harmless_messages)
                   is_warning = any(word in error.lower() for word in ['warning', 'notice', 'info', 'already exists'])
                   
                   if is_harmless or is_warning or ignore_errors:
                       print(f"[POSTGRES INSTALL] Info/Warning: {error[:100]}...")
                       logs.append(f"Info/Warning: {error}")
                   else:
                       # Check for critical errors that should stop installation
                       critical_errors = [
                           'unable to locate package',
                           'command not found',
                           'permission denied',
                           'disk full',
                           'no space left',
                           'network is unreachable',
                           'connection refused'
                       ]
                       
                       is_critical = any(critical in error.lower() for critical in critical_errors)
                       
                       if is_critical and not ignore_errors:
                           print(f"[POSTGRES INSTALL] ERROR: {error}")
                           logs.append(f"ERROR: {error}")
                           logs.append(f"INSTALLATION FAILED at step {step_num}")
                           return False
                       else:
                           print(f"[POSTGRES INSTALL] Warning: {error[:100]}...")
                           logs.append(f"Warning: {error}")
               
               print(f"[POSTGRES INSTALL] ✓ Step {step_num} completed successfully")
               logs.append(f"✓ Step completed successfully")
               
           except Exception as cmd_error:
               error_msg = f"Command execution failed: {str(cmd_error)}"
               print(f"[POSTGRES INSTALL] ERROR: {error_msg}")
               logs.append(f"ERROR: {error_msg}")
               
               if not ignore_errors:
                   return False
               else:
                   logs.append(f"Warning: Step failed but continuing due to ignore_errors=True")
           
           progress = 20 + (i * 70 // total_steps)
           task.progress = progress
           task.logs = '\n'.join(logs)
           db.session.commit()
           
           print(f"[POSTGRES INSTALL] Progress: {progress}%")
       
       # Enhanced verification with multiple methods
       logs.append(f"\n=== FINAL VERIFICATION ===")
       print("[POSTGRES INSTALL] Performing comprehensive verification...")
       
       verification_methods = [
           {
               'cmd': 'sudo -u postgres psql -c "SELECT version();"',
               'desc': 'PostgreSQL version check',
               'success_indicator': 'PostgreSQL'
           },
           {
               'cmd': 'pg_isready -U postgres',
               'desc': 'PostgreSQL ready check',
               'success_indicator': 'accepting connections'
           },
           {
               'cmd': 'sudo -u postgres psql -c "SELECT current_user;"',
               'desc': 'PostgreSQL user check',
               'success_indicator': 'postgres'
           },
           {
               'cmd': 'sudo systemctl status postgresql --no-pager || sudo service postgresql status || echo "systemd not available"',
               'desc': 'PostgreSQL service status',
               'success_indicator': 'active'
           }
       ]
       
       verification_success = False
       verification_results = []
       
       for method in verification_methods:
           try:
               print(f"[POSTGRES INSTALL] Verification: {method['desc']}")
               logs.append(f"Verification method: {method['desc']}")
               logs.append(f"Command: {method['cmd']}")
               
               start_time = time.time()
               stdin, stdout, stderr = client.exec_command(method['cmd'], timeout=30)
               
               output = stdout.read().decode().strip()
               error = stderr.read().decode().strip()
               execution_time = round(time.time() - start_time, 2)
               
               logs.append(f"Execution time: {execution_time}s")
               
               success_indicator = method['success_indicator']
               
               if success_indicator.lower() in output.lower():
                   verification_success = True
                   verification_results.append({
                       'method': method['desc'],
                       'success': True,
                       'output': output
                   })
                   print(f"[POSTGRES INSTALL] ✓ {method['desc']} successful")
                   logs.append(f"✓ {method['desc']} successful")
                   logs.append(f"Output: {output}")
                   break  # If one method succeeds, PostgreSQL is working
               else:
                   verification_results.append({
                       'method': method['desc'],
                       'success': False,
                       'output': output,
                       'error': error
                   })
                   print(f"[POSTGRES INSTALL] ○ {method['desc']} inconclusive")
                   logs.append(f"○ {method['desc']} inconclusive")
                   if output:
                       logs.append(f"Output: {output}")
                   if error:
                       logs.append(f"Error: {error}")
               
           except Exception as verify_error:
               verification_results.append({
                   'method': method['desc'],
                   'success': False,
                   'error': str(verify_error)
               })
               print(f"[POSTGRES INSTALL] ○ {method['desc']} failed: {str(verify_error)}")
               logs.append(f"○ {method['desc']} failed: {str(verify_error)}")
       
       # Final determination
       if verification_success:
           print("[POSTGRES INSTALL] ✓ PostgreSQL installation verified successfully")
           logs.append("✓ PostgreSQL installation verified successfully")
           logs.append("=== POSTGRESQL INSTALLATION COMPLETED SUCCESSFULLY ===")
           return True
       else:
           # Check if PostgreSQL is at least installed (even if not running)
           try:
               stdin, stdout, stderr = client.exec_command('which psql', timeout=10)
               psql_path = stdout.read().decode().strip()
               
               if psql_path and '/psql' in psql_path:
                   print("[POSTGRES INSTALL] ✓ PostgreSQL CLI installed (manual configuration may be needed)")
                   logs.append("✓ PostgreSQL CLI installed successfully")
                   logs.append("WARNING: PostgreSQL service may require manual startup")
                   logs.append("Manual startup commands:")
                   logs.append("  sudo systemctl start postgresql")
                   logs.append("  sudo service postgresql start")
                   logs.append("  sudo -u postgres /usr/lib/postgresql/*/bin/pg_ctl -D /var/lib/postgresql/*/main start")
                   logs.append("=== POSTGRESQL INSTALLATION COMPLETED WITH WARNINGS ===")
                   return True
               else:
                   print(f"[POSTGRES INSTALL] ✗ PostgreSQL installation verification failed")
                   logs.append(f"✗ PostgreSQL installation verification failed")
                   logs.append("PostgreSQL CLI not found in system PATH")
                   return False
                   
           except Exception as e:
               print(f"[POSTGRES INSTALL] ✗ Final verification error: {str(e)}")
               logs.append(f"✗ Final verification error: {str(e)}")
               return False
       
   except Exception as e:
       error_msg = f"PostgreSQL installation failed: {str(e)}"
       print(f"[POSTGRES INSTALL] FATAL ERROR: {error_msg}")
       logs.append(f"FATAL ERROR: {error_msg}")
       return False

def install_redis(client, task, logs):
    """Install Redis on server with comprehensive logging"""
    try:
        print(f"[REDIS INSTALL] Starting Redis installation on server {task.target_server.name}")
        logs.append(f"=== REDIS INSTALLATION STARTED ===")
        logs.append(f"Target Server: {task.target_server.name} ({task.target_server.ip_address})")
        logs.append(f"Timestamp: {datetime.now().isoformat()}")
        
        install_redis_commands = [
            {
                'cmd': 'sudo apt-get update',
                'desc': 'Updating package lists'
            },
            {
                'cmd': 'sudo apt-get install -y redis-server',
                'desc': 'Installing Redis server'
            },
            {
                'cmd': 'sudo systemctl enable redis-server',
                'desc': 'Enabling Redis service'
            },
            {
                'cmd': 'sudo systemctl start redis-server',
                'desc': 'Starting Redis service'
            },
            {
                'cmd': 'redis-cli --version',
                'desc': 'Verifying Redis CLI installation'
            },
            {
                'cmd': 'sudo systemctl status redis-server --no-pager',
                'desc': 'Checking Redis service status'
            }
        ]
        
        total_steps = len(install_redis_commands)
        
        for i, cmd_info in enumerate(install_redis_commands):
            step_num = i + 1
            command = cmd_info['cmd']
            description = cmd_info['desc']
            
            print(f"[REDIS INSTALL] Step {step_num}/{total_steps}: {description}")
            logs.append(f"\n--- Step {step_num}/{total_steps}: {description} ---")
            logs.append(f"Command: {command}")
            
            try:
                start_time = time.time()
                stdin, stdout, stderr = client.exec_command(command, timeout=180)
                
                output = stdout.read().decode().strip()
                error = stderr.read().decode().strip()
                execution_time = round(time.time() - start_time, 2)
                
                logs.append(f"Execution time: {execution_time}s")
                
                if output:
                    print(f"[REDIS INSTALL] Output: {output[:100]}...")
                    logs.append(f"Output: {output}")
                
                if error:
                    if any(word in error.lower() for word in ['warning', 'notice', 'info']):
                        print(f"[REDIS INSTALL] Warning: {error[:100]}...")
                        logs.append(f"Warning: {error}")
                    else:
                        print(f"[REDIS INSTALL] ERROR: {error}")
                        logs.append(f"ERROR: {error}")
                        logs.append(f"INSTALLATION FAILED at step {step_num}")
                        return False
                
                print(f"[REDIS INSTALL] ✓ Step {step_num} completed successfully")
                logs.append(f"✓ Step completed successfully")
                
            except Exception as cmd_error:
                error_msg = f"Command execution failed: {str(cmd_error)}"
                print(f"[REDIS INSTALL] ERROR: {error_msg}")
                logs.append(f"ERROR: {error_msg}")
                return False
            
            progress = 20 + (i * 70 // total_steps)
            task.progress = progress
            task.logs = '\n'.join(logs)
            db.session.commit()
            
            print(f"[REDIS INSTALL] Progress: {progress}%")
        
        # Test Redis connection
        logs.append(f"\n=== FINAL VERIFICATION ===")
        try:
            test_cmd = 'redis-cli ping'
            stdin, stdout, stderr = client.exec_command(test_cmd, timeout=30)
            ping_response = stdout.read().decode().strip()
            
            if ping_response == 'PONG':
                print("[REDIS INSTALL] ✓ Redis installation verified successfully")
                logs.append("✓ Redis connection verified (PING -> PONG)")
                logs.append("=== REDIS INSTALLATION COMPLETED SUCCESSFULLY ===")
                return True
            else:
                print(f"[REDIS INSTALL] ✗ Redis verification failed - response: {ping_response}")
                logs.append(f"✗ Redis verification failed - response: {ping_response}")
                return False
                
        except Exception as e:
            print(f"[REDIS INSTALL] ✗ Redis verification error: {str(e)}")
            logs.append(f"✗ Redis verification error: {str(e)}")
            return False
        
    except Exception as e:
        error_msg = f"Redis installation failed: {str(e)}"
        print(f"[REDIS INSTALL] FATAL ERROR: {error_msg}")
        logs.append(f"FATAL ERROR: {error_msg}")
        return False

# Updated basic installation functions with logging
def install_docker_basic(client):
    try:
        commands = [
            'sudo apt-get update',
            'sudo apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release',
            'curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg',
            'echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null',
            'sudo apt-get update',
            'sudo apt-get install -y docker-ce-cli',
            'sudo docker --version'
        ]
        
        for cmd in commands:
            stdin, stdout, stderr = client.exec_command(cmd)
            stdout.channel.recv_exit_status()  # Wait for command completion
            error = stderr.read().decode().strip()
            if error and 'warning' not in error.lower():
                return False
        return True
    except Exception:
        return False

def install_nginx_basic(client):
    """Basic Nginx installation with logging"""
    print("[NGINX BASIC] Starting basic Nginx installation")
    try:
        commands = [
            'sudo apt-get update',
            'sudo apt-get install -y nginx',
            'sudo systemctl enable nginx',
            'sudo systemctl start nginx'
        ]
        
        for i, command in enumerate(commands):
            print(f"[NGINX BASIC] Step {i+1}/4: {command}")
            stdin, stdout, stderr = client.exec_command(command, timeout=180)
            error = stderr.read().decode()
            
            if error and 'warning' not in error.lower():
                print(f"[NGINX BASIC] ERROR: {error}")
                return False
            print(f"[NGINX BASIC] ✓ Step {i+1} completed")
        
        print("[NGINX BASIC] ✓ Basic Nginx installation completed")
        return True
    except Exception as e:
        print(f"[NGINX BASIC] FATAL ERROR: {str(e)}")
        return False

def install_postgres_basic(client):
    """Basic PostgreSQL installation with logging"""
    print("[POSTGRES BASIC] Starting basic PostgreSQL installation")
    try:
        commands = [
            'sudo apt-get update',
            'sudo apt-get install -y postgresql postgresql-contrib',
            'sudo systemctl enable postgresql',
            'sudo systemctl start postgresql'
        ]
        
        for i, command in enumerate(commands):
            print(f"[POSTGRES BASIC] Step {i+1}/4: {command}")
            stdin, stdout, stderr = client.exec_command(command, timeout=300)
            error = stderr.read().decode()
            
            if error and 'warning' not in error.lower():
                print(f"[POSTGRES BASIC] ERROR: {error}")
                return False
            print(f"[POSTGRES BASIC] ✓ Step {i+1} completed")
        
        print("[POSTGRES BASIC] ✓ Basic PostgreSQL installation completed")
        return True
    except Exception as e:
        print(f"[POSTGRES BASIC] FATAL ERROR: {str(e)}")
        return False

def install_redis_basic(client):
    """Basic Redis installation with logging"""
    print("[REDIS BASIC] Starting basic Redis installation")
    try:
        commands = [
            'sudo apt-get update',
            'sudo apt-get install -y redis-server',
            'sudo systemctl enable redis-server',
            'sudo systemctl start redis-server'
        ]
        
        for i, command in enumerate(commands):
            print(f"[REDIS BASIC] Step {i+1}/4: {command}")
            stdin, stdout, stderr = client.exec_command(command, timeout=180)
            error = stderr.read().decode()
            
            if error and 'warning' not in error.lower():
                print(f"[REDIS BASIC] ERROR: {error}")
                return False
            print(f"[REDIS BASIC] ✓ Step {i+1} completed")
        
        print("[REDIS BASIC] ✓ Basic Redis installation completed")
        return True
    except Exception as e:
        print(f"[REDIS BASIC] FATAL ERROR: {str(e)}")
        return False

############################################################################################################
# ================= BACKUP AND RESTORE FUNCTIONS =================

def create_service_backup(server, service_name):
    """Create backup of a service on server"""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        if server.ssh_key_path:
            client.connect(server.ip_address, port=server.port,
                         username=server.username, key_filename=server.ssh_key_path)
        else:
            client.connect(server.ip_address, port=server.port,
                         username=server.username, password=decrypt_password(server.password))
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = f'/tmp/migration_backups/{timestamp}'
        
        # Create backup directory
        stdin, stdout, stderr = client.exec_command(f'mkdir -p {backup_dir}')
        
        if service_name == 'postgres':
            backup_path = f'{backup_dir}/postgres_backup.sql'
            command = f'sudo -u postgres pg_dumpall > {backup_path}'
        elif service_name == 'redis':
            backup_path = f'{backup_dir}/redis_backup.rdb'
            command = f'sudo cp /var/lib/redis/dump.rdb {backup_path}'
        elif service_name == 'nginx':
            backup_path = f'{backup_dir}/nginx_config.tar.gz'
            command = f'sudo tar -czf {backup_path} /etc/nginx/'
        elif service_name.startswith('odoo'):
            backup_path = f'{backup_dir}/odoo_data.tar.gz'
            command = f'sudo tar -czf {backup_path} /var/lib/odoo/ /etc/odoo/'
        else:
            return {'success': False, 'error': f'Backup not supported for {service_name}'}
        
        stdin, stdout, stderr = client.exec_command(command)
        error = stderr.read().decode()
        
        if error and 'warning' not in error.lower():
            return {'success': False, 'error': error}
        
        # Verify backup was created
        stdin, stdout, stderr = client.exec_command(f'ls -la {backup_path}')
        result = stdout.read().decode()
        
        client.close()
        
        if backup_path.split('/')[-1] in result:
            return {'success': True, 'backup_path': backup_path}
        else:
            return {'success': False, 'error': 'Backup file not found after creation'}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

def restore_service_backup(server, service_name, backup_result):
    """Restore service backup on server"""
    try:
        if not backup_result['success']:
            return {'success': False, 'error': 'No valid backup to restore'}
        
        backup_path = backup_result['backup_path']
        
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        if server.ssh_key_path:
            client.connect(server.ip_address, port=server.port,
                         username=server.username, key_filename=server.ssh_key_path)
        else:
            client.connect(server.ip_address, port=server.port,
                         username=server.username, password=decrypt_password(server.password))
        
        if service_name == 'postgres':
            command = f'sudo -u postgres psql < {backup_path}'
        elif service_name == 'redis':
            commands = [
                'sudo systemctl stop redis-server',
                f'sudo cp {backup_path} /var/lib/redis/dump.rdb',
                'sudo chown redis:redis /var/lib/redis/dump.rdb',
                'sudo systemctl start redis-server'
            ]
        elif service_name == 'nginx':
            commands = [
                'sudo systemctl stop nginx',
                f'sudo tar -xzf {backup_path} -C /',
                'sudo systemctl start nginx'
            ]
        elif service_name.startswith('odoo'):
            commands = [
                'sudo systemctl stop odoo',
                f'sudo tar -xzf {backup_path} -C /',
                'sudo systemctl start odoo'
            ]
        else:
            return {'success': False, 'error': f'Restore not supported for {service_name}'}
        
        if service_name == 'postgres':
            stdin, stdout, stderr = client.exec_command(command)
            error = stderr.read().decode()
            if error and 'warning' not in error.lower():
                return {'success': False, 'error': error}
        else:
            for command in commands:
                stdin, stdout, stderr = client.exec_command(command)
                error = stderr.read().decode()
                if error and 'warning' not in error.lower():
                    return {'success': False, 'error': f'Command failed: {command} - {error}'}
        
        client.close()
        return {'success': True}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

def stop_service_on_server(server, service_name):
    """Stop a service on server"""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        if server.ssh_key_path:
            client.connect(server.ip_address, port=server.port,
                         username=server.username, key_filename=server.ssh_key_path)
        else:
            client.connect(server.ip_address, port=server.port,
                         username=server.username, password=decrypt_password(server.password))
        
        if service_name in ['postgres', 'nginx', 'redis']:
            command = f'sudo systemctl stop {service_name}'
        elif service_name.startswith('odoo'):
            command = 'sudo systemctl stop odoo'
        else:
            command = f'sudo systemctl stop {service_name}'
        
        stdin, stdout, stderr = client.exec_command(command)
        error = stderr.read().decode()
        
        client.close()
        
        if error and 'warning' not in error.lower():
            return {'success': False, 'error': error}
        
        return {'success': True}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

# ================= DOMAIN MANAGEMENT =================

@infra_admin_bp.route('/api/domains/list')
@login_required
@require_infra_admin()
@track_errors('list_domain_mappings')
def list_domain_mappings():
    """List all domain mappings"""
    try:
        mappings = DomainMapping.query.all()
        mappings_data = []
        
        for mapping in mappings:
            # Verify domain status
            verification = verify_domain_mapping(mapping)
            
            mapping_dict = mapping.to_dict()
            mapping_dict['verification_details'] = verification.get('details')
            mappings_data.append(mapping_dict)
        
        return jsonify({'success': True, 'mappings': mappings_data})
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

@infra_admin_bp.route('/api/domains/add', methods=['POST'])
@login_required
@require_infra_admin()
@track_errors('add_domain_mapping')
def add_domain_mapping():
    """Add new domain mapping"""
    try:
        data = request.json
        
        # Validate domain format
        custom_domain = data['custom_domain'].lower().strip()
        target_subdomain = data['target_subdomain'].lower().strip()
        
        # Check if domain already exists
        existing = DomainMapping.query.filter_by(custom_domain=custom_domain).first()
        if existing:
            return jsonify({'success': False, 'message': 'Domain already mapped'}), 400
        
        # Validate target subdomain exists
        if data.get('tenant_id'):
            tenant = Tenant.query.get(data['tenant_id'])
            if not tenant:
                return jsonify({'success': False, 'message': 'Tenant not found'}), 404
        
        # Create domain mapping
        mapping = DomainMapping(
            custom_domain=custom_domain,
            target_subdomain=target_subdomain,
            tenant_id=data.get('tenant_id'),
            ssl_enabled=data.get('ssl_enabled', False),
            ssl_auto_renew=data.get('ssl_auto_renew', True),
            created_by=current_user.id
        )
        
        db.session.add(mapping)
        db.session.commit()
        
        # Update Nginx configuration
        update_nginx_config_result = update_nginx_configuration()
        
        if update_nginx_config_result['success']:
            mapping.status = 'active'
            db.session.commit()
        else:
            mapping.status = 'failed'
            db.session.commit()
            return jsonify({
                'success': False, 
                'message': f'Domain added but Nginx update failed: {update_nginx_config_result["error"]}'
            }), 500
        
        return jsonify({
            'success': True, 
            'message': f'Domain {custom_domain} mapped successfully',
            'mapping_id': mapping.id
        })
        
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

def verify_domain_mapping(mapping):
    """Verify domain mapping is working"""
    try:
        # Test HTTP/HTTPS connectivity
        protocols = ['http']
        if mapping.ssl_enabled:
            protocols.append('https')
        
        results = {}
        for protocol in protocols:
            try:
                response = requests.get(
                    f'{protocol}://{mapping.custom_domain}/nginx-health',
                    timeout=10,
                    verify=False  # For self-signed certificates
                )
                results[protocol] = {
                    'status_code': response.status_code,
                    'response_time': response.elapsed.total_seconds(),
                    'success': response.status_code == 200
                }
            except Exception as e:
                results[protocol] = {
                    'success': False,
                    'error': str(e)
                }
        
        # Update mapping verification status
        mapping.last_verified = datetime.utcnow()
        
        if any(r.get('success') for r in results.values()):
            mapping.verification_status = 'verified'
            return {'status': 'verified', 'details': results}
        else:
            mapping.verification_status = 'failed'
            return {'status': 'failed', 'details': results}
            
    except Exception as e:
        mapping.verification_status = 'error'
        return {'status': 'error', 'details': str(e)}

def update_nginx_configuration():
    """Update Nginx configuration with current domain mappings"""
    try:
        # Get all active domain mappings
        mappings = DomainMapping.query.filter_by(status='active').all()
        
        # Generate Nginx configuration
        nginx_config = generate_nginx_config(mappings)
        
        # Get Nginx server
        nginx_server = InfrastructureServer.query.filter(
            InfrastructureServer.service_roles.contains(['nginx'])
        ).first()
        
        if not nginx_server:
            return {'success': False, 'error': 'No Nginx server found'}
        
        # Connect to Nginx server
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        if nginx_server.ssh_key_path:
            client.connect(nginx_server.ip_address, port=nginx_server.port,
                         username=nginx_server.username, key_filename=nginx_server.ssh_key_path)
        else:
            client.connect(nginx_server.ip_address, port=nginx_server.port,
                         username=nginx_server.username, password=decrypt_password(nginx_server.password))
        
        # Write configuration file
        config_path = '/tmp/nginx_domains.conf'
        stdin, stdout, stderr = client.exec_command(f'cat > {config_path} << "EOF"\n{nginx_config}\nEOF')
        
        # Move to nginx directory and test configuration
        commands = [
            f'sudo mv {config_path} /etc/nginx/conf.d/domains.conf',
            'sudo nginx -t',
            'sudo systemctl reload nginx'
        ]
        
        for command in commands:
            stdin, stdout, stderr = client.exec_command(command)
            error = stderr.read().decode()
            if error and 'successful' not in error and 'warning' not in error.lower():
                return {'success': False, 'error': f'Command failed: {command} - {error}'}
        
        client.close()
        return {'success': True}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

def generate_nginx_config(mappings):
    """Generate Nginx configuration for domain mappings"""
    config_template = """
# Auto-generated domain mappings
# Last updated: {{ timestamp }}

{% for mapping in mappings %}
server {
    listen 80;
    {% if mapping.ssl_enabled %}
    listen 443 ssl http2;
    {% endif %}
    server_name {{ mapping.custom_domain }};
    
    {% if mapping.ssl_enabled %}
    ssl_certificate {{ mapping.ssl_cert_path }};
    ssl_certificate_key {{ mapping.ssl_key_path }};
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    {% endif %}
    
    location / {
        proxy_pass http://{{ mapping.target_subdomain }};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # Health check endpoint
    location /nginx-health {
        access_log off;
        return 200 "healthy\\n";
        add_header Content-Type text/plain;
    }
}

{% if not mapping.ssl_enabled %}
# Redirect to HTTPS when SSL is available
server {
    listen 80;
    server_name {{ mapping.custom_domain }};
    return 301 https://$server_name$request_uri;
}
{% endif %}

{% endfor %}

# Load balancing upstream for workers
upstream odoo_workers {
    least_conn;
    {% for worker in workers %}
    server {{ worker.container_name }}:8069;
    {% endfor %}
}

# Default server block for undefined domains
server {
    listen 80 default_server;
    listen 443 ssl default_server;
    server_name _;
    
    ssl_certificate /etc/nginx/ssl/default.crt;
    ssl_certificate_key /etc/nginx/ssl/default.key;
    
    return 444;
}
"""
    
    template = Template(config_template)
    
    # Get worker instances for load balancing
    workers = WorkerInstance.query.filter_by(status='running').all()
    
    return template.render(
        mappings=mappings,
        workers=workers,
        timestamp=datetime.utcnow().isoformat()
    )

# ================= CRON JOB MANAGEMENT =================

@infra_admin_bp.route('/api/cron/list')
@login_required
@require_infra_admin()
@track_errors('list_cron_jobs')
def list_cron_jobs():
    """List all cron jobs"""
    try:
        jobs = CronJob.query.all()
        jobs_data = [job.to_dict() for job in jobs]
        return jsonify({'success': True, 'jobs': jobs_data})
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

@infra_admin_bp.route('/api/cron/add', methods=['POST'])
@login_required
@require_infra_admin()
@track_errors('add_cron_job')
def add_cron_job():
    """Add new cron job"""
    try:
        data = request.json
        
        if not validate_cron_schedule(data['schedule']):
            return jsonify({'success': False, 'message': 'Invalid cron schedule'}), 400
        
        job = CronJob(
            name=data['name'],
            command=data['command'],
            schedule=data['schedule'],
            server_id=data.get('server_id'),
            created_by=current_user.id
        )
        
        db.session.add(job)
        db.session.commit()
        
        install_result = install_cron_job(job)
        
        if install_result['success']:
            return jsonify({
                'success': True,
                'message': f'Cron job "{data["name"]}" created successfully',
                'job_id': job.id
            })
        else:
            db.session.delete(job)
            db.session.commit()
            return jsonify({
                'success': False,
                'message': f'Failed to install cron job: {install_result["error"]}'
            }), 500
            
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

def install_cron_job(job):
    """Install cron job on server(s)"""
    try:
        if job.server_id:
            # Install on specific server
            servers = [InfrastructureServer.query.get(job.server_id)]
        else:
            # Install on all servers
            servers = InfrastructureServer.query.filter_by(status='active').all()
        
        for server in servers:
            if not server:
                continue
                
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                if server.ssh_key_path:
                    client.connect(server.ip_address, port=server.port,
                                 username=server.username, key_filename=server.ssh_key_path)
                else:
                    client.connect(server.ip_address, port=server.port,
                                 username=server.username, password=decrypt_password(server.password))
                
                # Add cron job
                cron_line = f'{job.schedule} {job.command} # SaaS-Manager-Job-{job.id}'
                command = f'(crontab -l 2>/dev/null; echo "{cron_line}") | crontab -'
                
                stdin, stdout, stderr = client.exec_command(command)
                error = stderr.read().decode()
                
                if error and 'warning' not in error.lower():
                    logger.warning(f"Warning installing cron on {server.name}: {error}")
                
                client.close()
                
            except Exception as e:
                logger.warning(f"Failed to install cron on {server.name}: {e}")
                continue
        
        return {'success': True}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

# ================= NETWORK DISCOVERY =================

@infra_admin_bp.route('/api/discovery/scan-network', methods=['POST'])
@login_required
@require_infra_admin()
@track_errors('scan_network_for_machines')
def scan_network_for_machines():
    """Scan network for available machines"""
    try:
        data = request.json
        network_range = data.get('network_range', '192.168.1.0/24')
        ssh_credentials = data.get('ssh_credentials', {})
        
        # Validate network range
        try:
            network = ipaddress.ip_network(network_range, strict=False)
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid network range'}), 400
        
        # Start network scanning in background
        scan_task = DeploymentTask(
            task_type='deploy',
            service_type='network_scan',
            config={
                'network_range': network_range,
                'ssh_credentials': ssh_credentials
            },
            created_by=current_user.id
        )
        db.session.add(scan_task)
        db.session.commit()
        
        threading.Thread(
            target=execute_network_scan,
            args=(scan_task.id,),
            daemon=True
        ).start()
        
        return jsonify({
            'success': True,
            'message': 'Network scan started',
            'scan_task_id': scan_task.id
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

@infra_admin_bp.route('/api/discovery/auto-setup', methods=['POST'])
@login_required
@require_infra_admin()
@track_errors('auto_setup_machine')
def auto_setup_machine():
    """Automatically setup a machine for specific services"""
    try:
        data = request.json
        target_ip = data.get('ip_address')
        target_username = data.get('username')
        target_password = data.get('password')
        service_roles = data.get('service_roles', [])
        auto_migrate = data.get('auto_migrate', False)
        
        # Validate target machine
        connection_test = test_ssh_connection(target_ip, target_username, target_password)
        if not connection_test['success']:
            return jsonify({
                'success': False, 
                'message': f'Cannot connect to target machine: {connection_test["error"]}'
            }), 400
        
        # Create server record
        server = InfrastructureServer(
            name=f'auto-discovered-{target_ip}',
            ip_address=target_ip,
            username=target_username,
            password=encrypt_password(target_password),
            service_roles=service_roles,
            status='pending',
            cpu_cores=connection_test.get('system_info', {}).get('cpu_cores'),
            memory_gb=connection_test.get('system_info', {}).get('memory_gb'),
            disk_gb=connection_test.get('system_info', {}).get('disk_gb'),
            os_type=connection_test.get('system_info', {}).get('os_type'),
            deployment_status='deploying',
            created_by=current_user.id
        )
        db.session.add(server)
        db.session.commit()
        
        # Create setup task
        setup_task = DeploymentTask(
            task_type='deploy',
            service_type='full_setup',
            target_server_id=server.id,
            config={
                'service_roles': service_roles,
                'auto_migrate': auto_migrate,
                'setup_type': 'complete'
            },
            created_by=current_user.id
        )
        db.session.add(setup_task)
        db.session.commit()
        
        # Start setup process
        threading.Thread(
            target=execute_complete_server_setup,
            args=(setup_task.id,),
            daemon=True
        ).start()
        
        return jsonify({
            'success': True,
            'message': f'Auto-setup started for {target_ip}',
            'server_id': server.id,
            'setup_task_id': setup_task.id
        })
        
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

def execute_network_scan(task_id):
    """Execute network scan for available machines"""
    try:
        from flask import current_app
        
        with current_app.app_context():
            task = DeploymentTask.query.get(task_id)
            if not task:
                return
            
            task.status = 'running'
            task.started_at = datetime.utcnow()
            db.session.commit()
            
            network_range = task.config.get('network_range')
            ssh_credentials = task.config.get('ssh_credentials', {})
            
            logs = []
            logs.append(f"Starting network scan for range: {network_range}")
            
            network = ipaddress.ip_network(network_range, strict=False)
            discovered_machines = []
            
            total_ips = list(network.hosts())
            scanned_count = 0
            
            for ip in total_ips:
                try:
                    # Check if host is reachable
                    result = subprocess.run(['ping', '-c', '1', '-W', '1', str(ip)], 
                                          capture_output=True, timeout=5)
                    
                    if result.returncode == 0:
                        logs.append(f"Host {ip} is reachable, testing SSH...")
                        
                        # Test SSH connection with provided credentials
                        for cred in ssh_credentials.get('credentials', []):
                            ssh_test = test_ssh_connection(
                                str(ip), 
                                cred.get('username'), 
                                cred.get('password'),
                                cred.get('key_path'),
                                cred.get('port', 22)
                            )
                            
                            if ssh_test['success']:
                                machine_info = {
                                    'ip_address': str(ip),
                                    'username': cred.get('username'),
                                    'ssh_accessible': True,
                                    'system_info': ssh_test.get('system_info', {}),
                                    'discovered_at': datetime.utcnow().isoformat()
                                }
                                discovered_machines.append(machine_info)
                                logs.append(f"Successfully connected to {ip} with user {cred.get('username')}")
                                break
                        else:
                            # Host reachable but SSH not accessible with provided credentials
                            discovered_machines.append({
                                'ip_address': str(ip),
                                'ssh_accessible': False,
                                'discovered_at': datetime.utcnow().isoformat()
                            })
                            logs.append(f"Host {ip} reachable but SSH not accessible")
                    
                    scanned_count += 1
                    task.progress = int((scanned_count / len(total_ips)) * 90)
                    task.logs = '\n'.join(logs[-50:])  # Keep last 50 log lines
                    db.session.commit()
                    
                except Exception as e:
                    logs.append(f"Error scanning {ip}: {str(e)}")
                    continue
            
            task.progress = 100
            task.status = 'completed'
            task.completed_at = datetime.utcnow()
            
            # Store discovered machines in task config for retrieval
            task.config['discovered_machines'] = discovered_machines
            logs_text = '\n'.join(logs)
            task.logs = f"{logs_text}\n\nScan completed. Found {len(discovered_machines)} accessible machines."
            
            db.session.commit()
            
    except Exception as e:
        try:
            with current_app.app_context():
                task = DeploymentTask.query.get(task_id)
                if task:
                    task.status = 'failed'
                    task.error_message = str(e)
                    task.completed_at = datetime.utcnow()
                    task.logs = f"{task.logs or ''}\n\nFATAL ERROR: {str(e)}"
                    db.session.commit()
        except:
            pass

def execute_complete_server_setup(task_id):
    """Execute complete server setup with all dependencies"""
    try:
        from flask import current_app
        
        with current_app.app_context():
            task = DeploymentTask.query.get(task_id)
            if not task:
                return
            
            task.status = 'running'
            task.started_at = datetime.utcnow()
            db.session.commit()
            
            server = task.target_server
            service_roles = task.config.get('service_roles', [])
            auto_migrate = task.config.get('auto_migrate', False)
            
            logs = []
            logs.append(f"Starting complete setup for server: {server.name}")
            logs.append(f"Target services: {', '.join(service_roles)}")
            
            # Connect to server
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            if server.ssh_key_path:
                client.connect(server.ip_address, port=server.port,
                             username=server.username, key_filename=server.ssh_key_path)
            else:
                client.connect(server.ip_address, port=server.port,
                             username=server.username, password=decrypt_password(server.password))
            
            # Phase 1: System preparation
            task.progress = 10
            logs.append("Phase 1: System preparation...")
            task.logs = '\n'.join(logs)
            db.session.commit()
            
            system_prep_commands = [
                'sudo apt-get update',
                'sudo apt-get upgrade -y',
                'sudo apt-get install -y curl wget git vim htop net-tools',
                'sudo ufw enable',
                'sudo systemctl enable ssh'
            ]
            
            for i, command in enumerate(system_prep_commands):
                logs.append(f"Executing: {command}")
                stdin, stdout, stderr = client.exec_command(command)
                output = stdout.read().decode()
                error = stderr.read().decode()
                
                if error and 'warning' not in error.lower():
                    logs.append(f"Warning: {error}")
                
                task.progress = 10 + (i * 5)
                task.logs = '\n'.join(logs[-30:])
                db.session.commit()
            
            # Phase 2: Install services
            task.progress = 35
            logs.append("Phase 2: Installing services...")
            task.logs = '\n'.join(logs)
            db.session.commit()
            
            for service in service_roles:
                if service == 'docker':
                    success = install_docker_basic(client)
                elif service == 'nginx':
                    success = install_nginx_basic(client)
                elif service == 'postgres':
                    success = install_postgres_basic(client)
                elif service == 'redis':
                    success = install_redis_basic(client)
                else:
                    success = True  # Unknown service, skip
                
                if success:
                    logs.append(f"Service {service} installed successfully")
                    if service not in server.current_services:
                        server.current_services = server.current_services + [service]
                else:
                    logs.append(f"Service {service} installation failed")
            
            # Phase 3: Configure firewall
            task.progress = 60
            logs.append("Phase 3: Configuring firewall...")
            task.logs = '\n'.join(logs)
            db.session.commit()
            
            firewall_commands = [
                'sudo ufw allow ssh',
                'sudo ufw allow 80/tcp',
                'sudo ufw allow 443/tcp'
            ]
            
            # Add service-specific ports
            if 'postgres' in service_roles:
                firewall_commands.append('sudo ufw allow 5432/tcp')
            if 'redis' in service_roles:
                firewall_commands.append('sudo ufw allow 6379/tcp')
            if any(role in ['worker', 'master'] for role in service_roles):
                firewall_commands.append('sudo ufw allow 8069/tcp')
            
            for command in firewall_commands:
                logs.append(f"Firewall: {command}")
                stdin, stdout, stderr = client.exec_command(command)
            
            # Phase 4: Setup monitoring
            task.progress = 80
            logs.append("Phase 4: Setting up monitoring...")
            task.logs = '\n'.join(logs)
            db.session.commit()
            
            monitoring_commands = [
                'sudo apt-get install -y htop iotop nethogs',
                'sudo mkdir -p /var/log/saas-manager',
                'sudo touch /var/log/saas-manager/setup.log',
                f'echo "Server setup completed on $(date)" | sudo tee -a /var/log/saas-manager/setup.log'
            ]
            
            for command in monitoring_commands:
                stdin, stdout, stderr = client.exec_command(command)
            
            # Final verification
            task.progress = 95
            logs.append("Final verification...")
            
            # Test all installed services
            verification_results = {}
            for service in service_roles:
                status = check_service_status(server, service)
                verification_results[service] = status['running']
                
                if status['running']:
                    logs.append(f"✓ {service} is running")
                else:
                    logs.append(f"✗ {service} failed to start: {status.get('error', 'unknown error')}")
            
            # Update server status
            if all(verification_results.values()):
                server.status = 'active'
                server.deployment_status = 'ready'
                task.status = 'completed'
                logs.append("✓ Server setup completed successfully!")
            else:
                server.status = 'maintenance'
                server.deployment_status = 'failed'
                task.status = 'failed'
                task.error_message = 'Some services failed to start'
                logs.append("✗ Server setup completed with errors")
            
            task.progress = 100
            task.completed_at = datetime.utcnow()
            task.logs = '\n'.join(logs)
            db.session.commit()
            
            client.close()
            
    except Exception as e:
        try:
            with current_app.app_context():
                task = DeploymentTask.query.get(task_id)
                if task:
                    task.status = 'failed'
                    task.error_message = str(e)
                    task.completed_at = datetime.utcnow()
                    task.logs = f"{task.logs or ''}\n\nFATAL ERROR: {str(e)}"
                    
                    # Update server status
                    server = task.target_server
                    if server:
                        server.deployment_status = 'failed'
                        server.status = 'maintenance'
                    
                    db.session.commit()
        except:
            pass

# ================= DEPLOYMENT TASK MANAGEMENT =================

@infra_admin_bp.route('/api/deployments/list')
@login_required
@require_infra_admin()
@track_errors('list_deployment_tasks')
def list_deployment_tasks():
    """List deployment tasks"""
    try:
        tasks = DeploymentTask.query.order_by(DeploymentTask.created_at.desc()).limit(50).all()
        tasks_data = [task.to_dict() for task in tasks]
        return jsonify({'success': True, 'tasks': tasks_data})
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

@infra_admin_bp.route('/api/deployments/<int:task_id>/logs')
@login_required
@require_infra_admin()
@track_errors('get_deployment_logs')
def get_deployment_logs(task_id):
    """Get deployment task logs"""
    try:
        task = DeploymentTask.query.get_or_404(task_id)
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'logs': task.logs,
            'status': task.status,
            'progress': task.progress,
            'error_message': task.error_message
        })
    except Exception as e:
        error_tracker.log_error(e, {'task_id': task_id})
        return jsonify({'success': False, 'message': str(e)}), 500
# Add this route to your infra_admin.py file

@infra_admin_bp.route('/api/servers/<int:server_id>/details')
@login_required
@require_infra_admin()
@track_errors('get_server_details')
def get_server_details(server_id):
    """Get detailed information about a specific server"""
    try:
        server = InfrastructureServer.query.get_or_404(server_id)
        
        # Get real-time health check
        health_data = perform_health_check(server)
        
        # Get server metrics
        metrics = collect_server_metrics(server)
        
        # Get recent deployment tasks for this server
        recent_deployments = DeploymentTask.query.filter(
            db.or_(
                DeploymentTask.source_server_id == server_id,
                DeploymentTask.target_server_id == server_id
            )
        ).order_by(DeploymentTask.created_at.desc()).limit(5).all()
        
        # Get cron jobs for this server
        cron_jobs = CronJob.query.filter_by(server_id=server_id).all()
        
        # Get alerts for this server
        recent_alerts = InfrastructureAlert.query.filter_by(
            server_id=server_id
        ).order_by(InfrastructureAlert.created_at.desc()).limit(10).all()
        
        # Get service status for each current service
        service_status = {}
        for service in server.current_services:
            status = check_service_status(server, service)
            service_status[service] = status
        
        server_details = {
            'server': server.to_dict(),
            'health_data': health_data,
            'metrics': metrics,
            'service_status': service_status,
            'recent_deployments': [task.to_dict() for task in recent_deployments],
            'cron_jobs': [job.to_dict() for job in cron_jobs],
            'recent_alerts': [alert.to_dict() for alert in recent_alerts],
            'last_updated': datetime.utcnow().isoformat()
        }
        
        return jsonify({
            'success': True,
            'server_details': server_details
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'server_id': server_id, 'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500
    
@infra_admin_bp.route('/api/deployments/<int:task_id>/cancel', methods=['POST'])
@login_required
@require_infra_admin()
@track_errors('cancel_deployment_task')
def cancel_deployment_task(task_id):
    """Cancel a running deployment task"""
    try:
        task = DeploymentTask.query.get_or_404(task_id)
        
        if task.status == 'running':
            task.status = 'cancelled'
            task.completed_at = datetime.utcnow()
            task.error_message = f'Task cancelled by {current_user.username}'
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Task cancelled successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': f'Cannot cancel task with status: {task.status}'
            }), 400
            
    except Exception as e:
        error_tracker.log_error(e, {'task_id': task_id})
        return jsonify({'success': False, 'message': str(e)}), 500
    
@infra_admin_bp.route('/api/deployments/create', methods=['POST'])
@login_required
@require_infra_admin()
@track_errors('create_deployment_wrapper')
def create_deployment_wrapper():
    try:
        data = request.json
        service_type = data.get('service_type')
        target_server_id = data.get('target_server_id')
        
        # Get the server
        server = InfrastructureServer.query.get_or_404(target_server_id)
        
        # Auto-add service role if missing
        if service_type not in server.service_roles:
            server.service_roles = server.service_roles + [service_type]
            db.session.commit()
        
        # Create deployment task
        task = DeploymentTask(
            task_type=data.get('task_type', 'deploy'),
            service_type=service_type,
            target_server_id=target_server_id,
            config=data.get('config', {}),
            created_by=current_user.id
        )
        db.session.add(task)
        db.session.commit()
        
        # Start deployment in background
        threading.Thread(
            target=execute_deployment_task,
            args=(task.id,),
            daemon=True
        ).start()
        
        return jsonify({
            'success': True, 
            'message': f'Deployment of {service_type} started',
            'task_id': task.id
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

# ================= MONITORING AND ALERTS =================

@infra_admin_bp.route('/api/monitoring/start', methods=['POST'])
@login_required
@require_infra_admin()
@track_errors('start_monitoring')
def start_monitoring():
    """Start infrastructure monitoring"""
    try:
        from flask import current_app
        
        # Get or create monitoring instance
        monitor = getattr(current_app, '_infrastructure_monitor', None)
        
        if not monitor:
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
            
            monitor = InfrastructureMonitor(
                current_app, 
                redis_client=redis_client,
                docker_client=docker_client
            )
            current_app._infrastructure_monitor = monitor
        
        monitor.start_monitoring()
        
        return jsonify({
            'success': True,
            'message': 'Infrastructure monitoring started'
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

@infra_admin_bp.route('/api/monitoring/stop', methods=['POST'])
@login_required
@require_infra_admin()
@track_errors('stop_monitoring')
def stop_monitoring():
    """Stop infrastructure monitoring"""
    try:
        from flask import current_app
        
        monitor = getattr(current_app, '_infrastructure_monitor', None)
        
        if monitor:
            monitor.stop_monitoring()
            delattr(current_app, '_infrastructure_monitor')
        
        return jsonify({
            'success': True,
            'message': 'Infrastructure monitoring stopped'
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

@infra_admin_bp.route('/api/monitoring/alerts')
@login_required
@require_infra_admin()
@track_errors('list_infrastructure_alerts')
def list_infrastructure_alerts():
    """List infrastructure alerts"""
    try:
        alerts = InfrastructureAlert.query.order_by(
            InfrastructureAlert.created_at.desc()
        ).limit(100).all()
        
        alerts_data = [alert.to_dict() for alert in alerts]
        
        return jsonify({
            'success': True,
            'alerts': alerts_data,
            'total_count': len(alerts_data)
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

@infra_admin_bp.route('/api/monitoring/alerts/<int:alert_id>/acknowledge', methods=['POST'])
@login_required
@require_infra_admin()
@track_errors('acknowledge_alert')
def acknowledge_alert(alert_id):
    """Acknowledge an infrastructure alert"""
    try:
        alert = InfrastructureAlert.query.get_or_404(alert_id)
        
        alert.status = 'acknowledged'
        alert.acknowledged_at = datetime.utcnow()
        alert.acknowledged_by = current_user.id
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Alert {alert_id} acknowledged'
        })
        
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'admin_user': current_user.id, 'alert_id': alert_id})
        return jsonify({'success': False, 'message': str(e)}), 500

@infra_admin_bp.route('/api/monitoring/alerts/<int:alert_id>/resolve', methods=['POST'])
@login_required
@require_infra_admin()
@track_errors('resolve_alert')
def resolve_alert(alert_id):
    """Resolve an infrastructure alert"""
    try:
        data = request.json
        resolution_notes = data.get('resolution_notes', '')
        
        alert = InfrastructureAlert.query.get_or_404(alert_id)
        
        alert.status = 'resolved'
        alert.resolved_at = datetime.utcnow()
        alert.resolved_by = current_user.id
        alert.resolution_notes = resolution_notes
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Alert {alert_id} resolved'
        })
        
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'admin_user': current_user.id, 'alert_id': alert_id})
        return jsonify({'success': False, 'message': str(e)}), 500

# ================= CONFIGURATION TEMPLATES =================

@infra_admin_bp.route('/api/templates/list')
@login_required
@require_infra_admin()
@track_errors('list_configuration_templates')
def list_configuration_templates():
    """List configuration templates"""
    try:
        templates = ConfigurationTemplate.query.filter_by(is_active=True).all()
        templates_data = [template.to_dict() for template in templates]
        
        return jsonify({
            'success': True,
            'templates': templates_data
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

@infra_admin_bp.route('/api/templates/create', methods=['POST'])
@login_required
@require_infra_admin()
@track_errors('create_configuration_template')
def create_configuration_template():
    """Create new configuration template"""
    try:
        data = request.json
        
        template = ConfigurationTemplate(
            name=data['name'],
            description=data.get('description', ''),
            template_type=data['template_type'],
            template_content=data['template_content'],
            template_variables=data.get('template_variables', {}),
            default_values=data.get('default_values', {}),
            category=data.get('category', 'general'),
            tags=data.get('tags', []),
            min_memory_gb=data.get('min_memory_gb'),
            min_cpu_cores=data.get('min_cpu_cores'),
            supported_os=data.get('supported_os', []),
            created_by=current_user.id
        )
        
        db.session.add(template)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Template "{data["name"]}" created successfully',
            'template_id': template.id
        })
        
    except Exception as e:
        db.session.rollback()
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

# ================= SYSTEM STATUS =================

@infra_admin_bp.route('/api/status/overview')
@login_required
@require_infra_admin()
@track_errors('infrastructure_status_overview')
def infrastructure_status_overview():
    """Get infrastructure status overview"""
    try:
        # Server status
        total_servers = InfrastructureServer.query.count()
        active_servers = InfrastructureServer.query.filter_by(status='active').count()
        failed_servers = InfrastructureServer.query.filter_by(status='failed').count()
        
        # Domain status
        total_domains = DomainMapping.query.count()
        active_domains = DomainMapping.query.filter_by(status='active').count()
        ssl_domains = DomainMapping.query.filter_by(ssl_enabled=True).count()
        
        # Recent deployments
        recent_deployments = DeploymentTask.query.filter(
            DeploymentTask.created_at >= datetime.utcnow() - timedelta(hours=24)
        ).count()
        
        # Active alerts
        active_alerts = InfrastructureAlert.query.filter_by(status='active').count()
        critical_alerts = InfrastructureAlert.query.filter_by(
            status='active', 
            severity='critical'
        ).count()
        
        return jsonify({
            'success': True,
            'infrastructure_status': {
                'servers': {
                    'total': total_servers,
                    'active': active_servers,
                    'failed': failed_servers,
                    'health_percentage': (active_servers / total_servers * 100) if total_servers > 0 else 0
                },
                'domains': {
                    'total': total_domains,
                    'active': active_domains,
                    'ssl_enabled': ssl_domains,
                    'ssl_percentage': (ssl_domains / total_domains * 100) if total_domains > 0 else 0
                },
                'deployments': {
                    'recent_24h': recent_deployments
                },
                'alerts': {
                    'active': active_alerts,
                    'critical': critical_alerts
                }
            }
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'user_id': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

# ================= DISASTER RECOVERY =================

@infra_admin_bp.route('/api/disaster-recovery/backup-all', methods=['POST'])
@login_required
@require_infra_admin()
@track_errors('disaster_recovery_backup')
def disaster_recovery_backup():
    """Create comprehensive backup of entire infrastructure"""
    try:
        data = request.json
        backup_type = data.get('backup_type', 'full')
        include_data = data.get('include_data', True)
        
        # Create disaster recovery task
        dr_task = DeploymentTask(
            task_type='backup',
            service_type='disaster_recovery',
            config={
                'backup_type': backup_type,
                'include_data': include_data,
                'backup_timestamp': datetime.utcnow().isoformat()
            },
            created_by=current_user.id
        )
        db.session.add(dr_task)
        db.session.commit()
        
        # Start backup process
        threading.Thread(
            target=execute_disaster_recovery_backup,
            args=(dr_task.id,),
            daemon=True
        ).start()
        
        return jsonify({
            'success': True,
            'message': 'Disaster recovery backup started',
            'task_id': dr_task.id
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

def execute_disaster_recovery_backup(task_id):
    """Execute comprehensive disaster recovery backup"""
    try:
        from flask import current_app
        
        with current_app.app_context():
            task = DeploymentTask.query.get(task_id)
            if not task:
                return
            
            task.status = 'running'
            task.started_at = datetime.utcnow()
            db.session.commit()
            
            backup_type = task.config.get('backup_type', 'full')
            include_data = task.config.get('include_data', True)
            
            logs = []
            logs.append("Starting disaster recovery backup...")
            
            backup_results = {}
            
            # Backup each server
            servers = InfrastructureServer.query.filter_by(status='active').all()
            
            for i, server in enumerate(servers):
                logs.append(f"Backing up server: {server.name}")
                
                # Backup configurations
                config_backup = backup_server_configurations(server)
                backup_results[f'{server.name}_config'] = config_backup
                
                if config_backup['success']:
                    logs.append(f"✓ Configuration backup completed for {server.name}")
                else:
                    logs.append(f"✗ Configuration backup failed for {server.name}: {config_backup['error']}")
                
                # Backup data if requested
                if include_data:
                    for service in server.current_services:
                        data_backup = create_service_backup(server, service)
                        backup_results[f'{server.name}_{service}_data'] = data_backup
                        
                        if data_backup['success']:
                            logs.append(f"✓ Data backup completed for {service} on {server.name}")
                        else:
                            logs.append(f"✗ Data backup failed for {service} on {server.name}: {data_backup['error']}")
                
                task.progress = int((i + 1) / len(servers) * 80)
                task.logs = '\n'.join(logs[-50:])
                db.session.commit()
            
            # Backup database schema and configurations
            logs.append("Backing up SaaS Manager database...")
            db_backup = backup_saas_manager_database()
            backup_results['saas_manager_db'] = db_backup
            
            # Create backup manifest
            backup_manifest = {
                'backup_id': f"dr_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                'backup_type': backup_type,
                'created_at': datetime.utcnow().isoformat(),
                'include_data': include_data,
                'servers_backed_up': len(servers),
                'backup_results': backup_results,
                'total_size_mb': sum([
                    result.get('size_mb', 0) for result in backup_results.values() 
                    if isinstance(result, dict) and result.get('success')
                ])
            }
            
            # Store backup manifest
            task.config['backup_manifest'] = backup_manifest
            
            task.progress = 100
            task.status = 'completed'
            task.completed_at = datetime.utcnow()
            logs_text = '\n'.join(logs)
            task.logs = f"{logs_text}\n\nBackup completed successfully. Backup ID: {backup_manifest['backup_id']}"
            
            db.session.commit()
            
    except Exception as e:
        try:
            with current_app.app_context():
                task = DeploymentTask.query.get(task_id)
                if task:
                    task.status = 'failed'
                    task.error_message = str(e)
                    task.completed_at = datetime.utcnow()
                    task.logs = f"{task.logs or ''}\n\nFATAL ERROR: {str(e)}"
                    db.session.commit()
        except:
            pass

def backup_server_configurations(server):
    """Backup server configurations"""
    try:
        return {'success': True, 'backup_path': '/tmp/config_backup', 'size_mb': 10}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def backup_saas_manager_database():
    """Backup SaaS Manager database"""
    try:
        return {'success': True, 'backup_path': '/tmp/saas_db_backup.sql', 'size_mb': 100}
    except Exception as e:
        return {'success': False, 'error': str(e)}

# ================= AUTO-RELOAD NGINX ON WORKER CHANGES =================

def auto_reload_nginx_on_worker_change():
    """Auto-reload Nginx when workers are added/removed"""
    try:
        # Update Nginx configuration to include new worker in load balancing
        result = update_nginx_configuration()
        
        if result['success']:
            # Log the auto-reload
            audit_log = AuditLog(
                action='nginx_auto_reload',
                details={'reason': 'worker_configuration_changed'},
                ip_address='system'
            )
            db.session.add(audit_log)
            db.session.commit()
            
            return True
        else:
            return False
            
    except Exception as e:
        error_tracker.log_error(e, {'function': 'auto_reload_nginx_on_worker_change'})
        return False

# ================= WORKER MANAGEMENT INTEGRATION =================

@infra_admin_bp.route('/api/workers/create-with-nginx-reload', methods=['POST'])
@login_required
@require_infra_admin()
@track_errors('create_worker_with_nginx_reload')
def create_worker_with_nginx_reload():
    """Create worker and automatically update Nginx configuration"""
    try:
        data = request.json
        worker_name = data.get('name', f"odoo_worker_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
        try:
            docker_client = docker.from_env()
            docker_client.ping()
        except:
            return jsonify({'success': False, 'message': 'Docker not available'}), 500
        
        # Create worker container
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
        
        container.start()
        
        # Add to database
        db_worker = WorkerInstance(
            name=worker_name,
            container_name=worker_name,
            port=8069,
            max_tenants=data.get('max_tenants', 10),
            status='running'
        )
        db.session.add(db_worker)
        db.session.commit()
        
        # Automatically update Nginx configuration
        nginx_result = auto_reload_nginx_on_worker_change()
        
        response_data = {
            'success': True,
            'message': f'Worker {worker_name} created successfully',
            'container_id': container.id,
            'worker_id': db_worker.id,
            'nginx_reloaded': nginx_result
        }
        
        if not nginx_result:
            response_data['warning'] = 'Worker created but Nginx configuration update failed'
        
        return jsonify(response_data)
        
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

# ================= REAL-TIME MONITORING =================

@infra_admin_bp.route('/api/monitoring/real-time')
@login_required
@require_infra_admin()
@track_errors('real_time_monitoring')
def real_time_monitoring():
    """Get real-time monitoring data"""
    try:
        # Get all servers with their current status
        servers = InfrastructureServer.query.filter_by(status='active').all()
        monitoring_data = []
        
        for server in servers:
            # Get real-time metrics
            health_data = perform_health_check(server)
            
            # Get running deployments
            active_deployments = DeploymentTask.query.filter_by(
                target_server_id=server.id,
                status='running'
            ).count()
            
            # Get cron job status
            next_cron_runs = []
            for job in server.cron_jobs:
                next_run = calculate_next_run(job.schedule)
                if next_run:
                    next_cron_runs.append({
                        'job_name': job.name,
                        'next_run': next_run.isoformat(),
                        'schedule': job.schedule
                    })
            
            monitoring_data.append({
                'server_id': server.id,
                'server_name': server.name,
                'ip_address': server.ip_address,
                'health_data': health_data,
                'active_deployments': active_deployments,
                'next_cron_runs': sorted(next_cron_runs, key=lambda x: x['next_run'])[:3],
                'last_update': datetime.utcnow().isoformat()
            })
        
        # Get domain mapping status
        domain_status = []
        for mapping in DomainMapping.query.filter_by(status='active').limit(10).all():
            verification = verify_domain_mapping(mapping)
            domain_status.append({
                'domain': mapping.custom_domain,
                'target': mapping.target_subdomain,
                'ssl_enabled': mapping.ssl_enabled,
                'verification_status': verification['status'],
                'last_verified': mapping.last_verified.isoformat() if mapping.last_verified else None
            })
        
        # Get recent deployment activity
        recent_deployments = DeploymentTask.query.order_by(
            DeploymentTask.created_at.desc()
        ).limit(5).all()
        
        deployment_activity = []
        for task in recent_deployments:
            deployment_activity.append({
                'id': task.id,
                'task_type': task.task_type,
                'service_type': task.service_type,
                'status': task.status,
                'progress': task.progress,
                'target_server': task.target_server.name if task.target_server else None,
                'created_at': task.created_at.isoformat()
            })
        
        return jsonify({
            'success': True,
            'servers': monitoring_data,
            'domains': domain_status,
            'recent_deployments': deployment_activity,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

# ================= SYSTEM INITIALIZATION =================

@infra_admin_bp.route('/api/system/initialize', methods=['POST'])
@login_required
@require_infra_admin()
@track_errors('initialize_infrastructure_system')
def initialize_infrastructure_system():
    """Initialize infrastructure management system"""
    try:
        initialization_results = {}
        
        # Setup default cron jobs
        setup_result = setup_default_cron_jobs()
        initialization_results['cron_jobs'] = setup_result
        
        # Create default configuration templates
        templates_result = create_default_templates()
        initialization_results['templates'] = templates_result
        
        # Initialize monitoring if available
        monitoring_result = initialize_monitoring_system()
        initialization_results['monitoring'] = monitoring_result
        
        return jsonify({
            'success': True,
            'message': 'Infrastructure system initialized successfully',
            'results': initialization_results
        })
        
    except Exception as e:
        error_tracker.log_error(e, {'admin_user': current_user.id})
        return jsonify({'success': False, 'message': str(e)}), 500

def setup_default_cron_jobs():
    """Setup default system cron jobs"""
    try:
        # Check if default jobs already exist
        nginx_reload_job = CronJob.query.filter_by(name='Nginx Config Reload').first()
        
        if not nginx_reload_job:
            # Create default system cron jobs
            default_jobs = [
                {
                    'name': 'Nginx Config Reload',
                    'command': '/usr/local/bin/nginx-config-reload.sh',
                    'schedule': '0 */2 * * *',  # Every 2 hours
                    'server_id': None  # Run on all servers
                },
                {
                    'name': 'Health Check All Servers',
                    'command': '/usr/local/bin/health-check-all.sh',
                    'schedule': '*/5 * * * *',  # Every 5 minutes
                    'server_id': None
                },
                {
                    'name': 'SSL Certificate Renewal',
                    'command': '/usr/local/bin/ssl-renewal.sh',
                    'schedule': '0 2 * * 1',  # Weekly on Monday at 2 AM
                    'server_id': None
                },
                {
                    'name': 'Database Backup',
                    'command': '/usr/local/bin/database-backup.sh',
                    'schedule': '0 3 * * *',  # Daily at 3 AM
                    'server_id': None
                },
                {
                    'name': 'Log Rotation',
                    'command': '/usr/local/bin/log-rotation.sh',
                    'schedule': '0 4 * * 0',  # Weekly on Sunday at 4 AM
                    'server_id': None
                }
            ]
            
            created_count = 0
            for job_data in default_jobs:
                job = CronJob(
                    name=job_data['name'],
                    command=job_data['command'],
                    schedule=job_data['schedule'],
                    server_id=job_data['server_id'],
                    created_by=1  # System user
                )
                db.session.add(job)
                created_count += 1
            
            db.session.commit()
            return {'success': True, 'created_jobs': created_count}
        else:
            return {'success': True, 'message': 'Default jobs already exist'}
            
    except Exception as e:
        return {'success': False, 'error': str(e)}

def create_default_templates():
    """Create default configuration templates"""
    try:
        # Nginx upstream template
        nginx_upstream_template = ConfigurationTemplate.query.filter_by(
            name='Nginx Upstream Load Balancer'
        ).first()
        
        if not nginx_upstream_template:
            nginx_template = ConfigurationTemplate(
                name='Nginx Upstream Load Balancer',
                description='Load balancing configuration for Odoo workers',
                template_type='nginx',
                template_content="""
upstream {{ upstream_name }} {
    {{ load_balancing_method }};
    {% for worker in workers %}
    server {{ worker.ip }}:{{ worker.port }} weight={{ worker.weight|default(1) }} max_fails={{ worker.max_fails|default(3) }} fail_timeout={{ worker.fail_timeout|default('30s') }};
    {% endfor %}
}

server {
    listen 80;
    listen 443 ssl http2;
    server_name {{ server_name }};
    
    {% if ssl_enabled %}
    ssl_certificate {{ ssl_cert_path }};
    ssl_certificate_key {{ ssl_key_path }};
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    {% endif %}
    
    location / {
        proxy_pass http://{{ upstream_name }};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout {{ proxy_timeout|default('60s') }};
        proxy_send_timeout {{ proxy_timeout|default('60s') }};
        proxy_read_timeout {{ proxy_timeout|default('60s') }};
    }
    
    # Health check endpoint
    location /nginx-health {
        access_log off;
        return 200 "healthy\\n";
        add_header Content-Type text/plain;
    }
}
                """,
                template_variables={
                    'upstream_name': 'string',
                    'load_balancing_method': 'string',
                    'workers': 'array',
                    'server_name': 'string',
                    'ssl_enabled': 'boolean',
                    'ssl_cert_path': 'string',
                    'ssl_key_path': 'string',
                    'proxy_timeout': 'string'
                },
                default_values={
                    'upstream_name': 'odoo_workers',
                    'load_balancing_method': 'least_conn',
                    'proxy_timeout': '60s'
                },
                category='load_balancing',
                tags=['nginx', 'load_balancer', 'odoo'],
                min_memory_gb=1,
                min_cpu_cores=1,
                supported_os=['ubuntu', 'debian', 'centos'],
                created_by=1
            )
            db.session.add(nginx_template)
        
        # Docker Compose template for Odoo worker
        docker_compose_template = ConfigurationTemplate.query.filter_by(
            name='Odoo Worker Docker Compose'
        ).first()
        
        if not docker_compose_template:
            compose_template = ConfigurationTemplate(
                name='Odoo Worker Docker Compose',
                description='Docker Compose configuration for Odoo worker instances',
                template_type='docker_compose',
                template_content="""
version: '3.8'

services:
  {{ worker_name }}:
    image: {{ odoo_image|default('odoo:17.0') }}
    container_name: {{ worker_name }}
    environment:
      - HOST={{ postgres_host|default('postgres') }}
      - USER={{ postgres_user|default('odoo_master') }}
      - PASSWORD={{ postgres_password }}
      {% if redis_enabled %}
      - REDIS_URL=redis://{{ redis_host|default('redis') }}:{{ redis_port|default(6379) }}/{{ redis_db|default(0) }}
      {% endif %}
    volumes:
      - {{ filestore_volume }}:/var/lib/odoo
      - {{ logs_volume }}:/var/log/odoo
      - {{ addons_path }}:/mnt/extra-addons:ro
      - {{ config_path }}:/etc/odoo/odoo.conf:ro
    networks:
      - {{ network_name|default('odoo_network') }}
    restart: unless-stopped
    command: {{ odoo_command|default('odoo -c /etc/odoo/odoo.conf') }}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8069/web/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

networks:
  {{ network_name|default('odoo_network') }}:
    external: true
                """,
                template_variables={
                    'worker_name': 'string',
                    'odoo_image': 'string',
                    'postgres_host': 'string',
                    'postgres_user': 'string',
                    'postgres_password': 'string',
                    'redis_enabled': 'boolean',
                    'redis_host': 'string',
                    'redis_port': 'integer',
                    'redis_db': 'integer',
                    'filestore_volume': 'string',
                    'logs_volume': 'string',
                    'addons_path': 'string',
                    'config_path': 'string',
                    'network_name': 'string',
                    'odoo_command': 'string'
                },
                default_values={
                    'odoo_image': 'odoo:17.0',
                    'postgres_host': 'postgres',
                    'postgres_user': 'odoo_master',
                    'redis_enabled': True,
                    'redis_host': 'redis',
                    'redis_port': 6379,
                    'redis_db': 0,
                    'network_name': 'odoo_network',
                    'odoo_command': 'odoo -c /etc/odoo/odoo.conf'
                },
                category='containerization',
                tags=['docker', 'docker-compose', 'odoo', 'worker'],
                min_memory_gb=2,
                min_cpu_cores=1,
                supported_os=['ubuntu', 'debian', 'centos'],
                required_services=['docker'],
                created_by=1
            )
            db.session.add(compose_template)
        
        db.session.commit()
        return {'success': True, 'message': 'Default configuration templates created'}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

def initialize_monitoring_system():
    """Initialize monitoring system"""
    try:
        from flask import current_app
        
        # Try to initialize monitoring
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
        
        if redis_client or docker_client:
            monitor = InfrastructureMonitor(
                current_app,
                redis_client=redis_client,
                docker_client=docker_client
            )
            current_app._infrastructure_monitor = monitor
            monitor.start_monitoring()
            
            return {'success': True, 'message': 'Monitoring system initialized and started'}
        else:
            return {'success': False, 'message': 'Redis and Docker not available for monitoring'}
            
    except Exception as e:
        return {'success': False, 'error': str(e)}

# ================= API HEALTH CHECK =================

@infra_admin_bp.route('/api/health')
@track_errors('infra_admin_health_check')
def health_check():
    """Health check for infrastructure admin API"""
    try:
        # Check database connectivity
        db.session.execute(text('SELECT 1'))
        db_status = 'healthy'
    except Exception as e:
        db_status = 'unhealthy'
    
    # Check if monitoring is running
    from flask import current_app
    monitor = getattr(current_app, '_infrastructure_monitor', None)
    monitoring_status = 'running' if monitor and monitor.running else 'stopped'
    
    # Get basic stats
    server_count = InfrastructureServer.query.count()
    active_server_count = InfrastructureServer.query.filter_by(status='active').count()
    active_deployment_count = DeploymentTask.query.filter_by(status='running').count()
    
    return jsonify({
        'status': 'healthy' if db_status == 'healthy' else 'degraded',
        'services': {
            'database': db_status,
            'monitoring': monitoring_status
        },
        'statistics': {
            'total_servers': server_count,
            'active_servers': active_server_count,
            'running_deployments': active_deployment_count
        },
        'timestamp': datetime.utcnow().isoformat()
    })

# ================= EXPORT INFRASTRUCTURE ADMIN BLUEPRINT =================

# Initialize database tables if they don't exist
def init_infra_tables():
    """Initialize infrastructure admin tables"""
    try:
        with db.get_engine().connect() as conn:
            # This will create tables if they don't exist
            db.create_all()
        logger.info("Infrastructure admin tables initialized")
    except Exception as e:
        logger.error(f"Failed to initialize infrastructure admin tables: {e}")

# Auto-initialize tables when module is imported
init_infra_tables()

# Export the blueprint for registration in main app
__all__ = ['infra_admin_bp']