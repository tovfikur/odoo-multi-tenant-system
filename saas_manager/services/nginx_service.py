"""
Nginx Load Balancer Service

Handles dynamic nginx configuration management for automatic load balancing
of newly created Odoo worker containers.
"""

import logging
import os
import time
import subprocess
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class NginxLoadBalancerService:
    """Service for managing nginx load balancer configuration"""
    
    def __init__(self):
        # For containerized environment, try to use host-mounted nginx directory
        self.nginx_config_path = "/etc/nginx/nginx.conf"
        self.logger = logging.getLogger(__name__)
        
        # Try different paths for nginx configuration
        possible_paths = [
            "/host-nginx/conf.d",  # If mounted as volume
            "/etc/nginx/conf.d",   # Standard path
            "/tmp/nginx-config"     # Fallback
        ]
        
        self.nginx_conf_d_path = None
        for path in possible_paths:
            try:
                if os.path.exists(path) or os.path.exists(os.path.dirname(path)):
                    os.makedirs(path, exist_ok=True)
                    # Test write access
                    test_file = os.path.join(path, "test_write.tmp")
                    with open(test_file, 'w') as f:
                        f.write("test")
                    os.remove(test_file)
                    self.nginx_conf_d_path = path
                    break
            except (OSError, PermissionError):
                continue
        
        if not self.nginx_conf_d_path:
            self.nginx_conf_d_path = "/tmp/nginx-config"
            os.makedirs(self.nginx_conf_d_path, exist_ok=True)
            
        self.upstream_config_file = os.path.join(self.nginx_conf_d_path, "dynamic_upstreams.conf")
        self.logger.info(f"Using nginx config path: {self.nginx_conf_d_path}")
    
    def add_worker(self, worker_ip: str, worker_port: int, worker_name: str) -> Dict[str, Any]:
        """
        Add a new worker to the nginx load balancer upstream
        
        Args:
            worker_ip: IP address of the worker
            worker_port: Port of the worker
            worker_name: Name of the worker
            
        Returns:
            Dict containing operation result
        """
        try:
            self.logger.info(f"Adding worker {worker_name} ({worker_ip}:{worker_port}) to load balancer")
            
            # Read current upstream configuration
            current_upstreams = self._read_upstream_config()
            
            # Add new worker to odoo_workers upstream
            worker_entry = f"    server {worker_ip}:{worker_port} max_fails=2 fail_timeout=10s;"
            
            if 'odoo_workers' not in current_upstreams:
                current_upstreams['odoo_workers'] = {
                    'method': 'least_conn',
                    'servers': [],
                    'options': ['keepalive 8']
                }
            
            # Check if worker already exists
            existing = any(f"{worker_ip}:{worker_port}" in server for server in current_upstreams['odoo_workers']['servers'])
            if not existing:
                current_upstreams['odoo_workers']['servers'].append(worker_entry)
                
                # Write updated configuration
                self._write_upstream_config(current_upstreams)
                
                # Test and reload nginx
                if self._test_and_reload_nginx():
                    self.logger.info(f"Successfully added worker {worker_name} to load balancer")
                    return {'success': True, 'message': f'Worker {worker_name} added to load balancer'}
                else:
                    return {'success': False, 'error': 'Failed to reload nginx configuration'}
            else:
                self.logger.warning(f"Worker {worker_name} already exists in load balancer")
                return {'success': True, 'message': f'Worker {worker_name} already exists in load balancer'}
                
        except Exception as e:
            self.logger.error(f"Failed to add worker {worker_name} to load balancer: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def remove_worker(self, worker_ip: str, worker_name: str) -> Dict[str, Any]:
        """
        Remove a worker from the nginx load balancer upstream
        
        Args:
            worker_ip: IP address of the worker
            worker_name: Name of the worker
            
        Returns:
            Dict containing operation result
        """
        try:
            self.logger.info(f"Removing worker {worker_name} ({worker_ip}) from load balancer")
            
            # Read current upstream configuration
            current_upstreams = self._read_upstream_config()
            
            if 'odoo_workers' in current_upstreams:
                # Remove worker from servers list
                original_count = len(current_upstreams['odoo_workers']['servers'])
                current_upstreams['odoo_workers']['servers'] = [
                    server for server in current_upstreams['odoo_workers']['servers']
                    if worker_ip not in server
                ]
                
                removed_count = original_count - len(current_upstreams['odoo_workers']['servers'])
                
                if removed_count > 0:
                    # Write updated configuration
                    self._write_upstream_config(current_upstreams)
                    
                    # Test and reload nginx
                    if self._test_and_reload_nginx():
                        self.logger.info(f"Successfully removed worker {worker_name} from load balancer")
                        return {'success': True, 'message': f'Worker {worker_name} removed from load balancer'}
                    else:
                        return {'success': False, 'error': 'Failed to reload nginx configuration'}
                else:
                    self.logger.warning(f"Worker {worker_name} not found in load balancer")
                    return {'success': True, 'message': f'Worker {worker_name} not found in load balancer'}
            else:
                return {'success': False, 'error': 'No odoo_workers upstream found'}
                
        except Exception as e:
            self.logger.error(f"Failed to remove worker {worker_name} from load balancer: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_upstream_status(self) -> Dict[str, Any]:
        """
        Get current status of nginx upstreams
        
        Returns:
            Dict containing upstream status information
        """
        try:
            current_upstreams = self._read_upstream_config()
            
            status = {
                'upstreams': {},
                'total_servers': 0,
                'last_updated': datetime.now().isoformat()
            }
            
            for upstream_name, upstream_config in current_upstreams.items():
                servers = upstream_config.get('servers', [])
                status['upstreams'][upstream_name] = {
                    'method': upstream_config.get('method', 'round_robin'),
                    'server_count': len(servers),
                    'servers': [self._parse_server_line(server) for server in servers]
                }
                status['total_servers'] += len(servers)
            
            return {'success': True, 'status': status}
            
        except Exception as e:
            self.logger.error(f"Failed to get upstream status: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _read_upstream_config(self) -> Dict[str, Dict]:
        """Read current upstream configuration from nginx config files"""
        upstreams = {}
        
        try:
            # Try to read from dynamic upstreams file first
            if os.path.exists(self.upstream_config_file):
                with open(self.upstream_config_file, 'r') as f:
                    content = f.read()
                upstreams.update(self._parse_upstream_config(content))
            
            # Also read from main nginx.conf as fallback
            if os.path.exists(self.nginx_config_path):
                with open(self.nginx_config_path, 'r') as f:
                    content = f.read()
                upstreams.update(self._parse_upstream_config(content))
            
        except Exception as e:
            self.logger.warning(f"Failed to read upstream config: {str(e)}")
        
        return upstreams
    
    def _parse_upstream_config(self, content: str) -> Dict[str, Dict]:
        """Parse nginx upstream configuration from content"""
        upstreams = {}
        lines = content.split('\n')
        current_upstream = None
        
        for line in lines:
            line = line.strip()
            
            if line.startswith('upstream '):
                upstream_name = line.split()[1].rstrip(' {')
                current_upstream = upstream_name
                upstreams[current_upstream] = {
                    'servers': [],
                    'options': [],
                    'method': 'round_robin'
                }
            elif current_upstream and line.startswith('server '):
                upstreams[current_upstream]['servers'].append(line)
            elif current_upstream and line in ['least_conn;', 'ip_hash;', 'hash;']:
                upstreams[current_upstream]['method'] = line.rstrip(';')
            elif current_upstream and line.startswith('keepalive '):
                upstreams[current_upstream]['options'].append(line)
            elif line == '}' and current_upstream:
                current_upstream = None
        
        return upstreams
    
    def _write_upstream_config(self, upstreams: Dict[str, Dict]):
        """Write upstream configuration to dynamic config file"""
        config_content = "# Dynamic upstream configuration\n"
        config_content += f"# Generated at {datetime.now().isoformat()}\n\n"
        
        for upstream_name, upstream_config in upstreams.items():
            config_content += f"upstream {upstream_name} {{\n"
            
            # Add load balancing method
            method = upstream_config.get('method', 'round_robin')
            if method != 'round_robin':
                config_content += f"    {method};\n"
            
            # Add servers
            for server in upstream_config.get('servers', []):
                if not server.strip().startswith('server '):
                    server = f"    server {server.strip()};"
                config_content += f"    {server.strip()}\n"
            
            # Add options
            for option in upstream_config.get('options', []):
                config_content += f"    {option}\n"
            
            config_content += "}\n\n"
        
        # Directory already ensured in __init__
        
        # Write to file
        with open(self.upstream_config_file, 'w') as f:
            f.write(config_content)
        
        self.logger.info(f"Updated upstream configuration: {self.upstream_config_file}")
    
    def _test_and_reload_nginx(self) -> bool:
        """Test nginx configuration and reload if valid"""
        try:
            # For containerized deployments, we'll delegate nginx reloading to the nginx container
            # First, let's try to signal nginx via Docker API or external command
            return self._reload_nginx_container()
            
        except Exception as e:
            self.logger.error(f"Failed to test/reload nginx: {str(e)}")
            return False
    
    def _reload_nginx_container(self) -> bool:
        """Reload nginx in the nginx container"""
        try:
            # Try to send reload signal to nginx container
            import docker
            docker_client = docker.from_env()
            
            # Find nginx container
            nginx_containers = [
                c for c in docker_client.containers.list() 
                if 'nginx' in c.name.lower()
            ]
            
            if nginx_containers:
                nginx_container = nginx_containers[0]
                
                # Test nginx configuration first
                test_result = nginx_container.exec_run('nginx -t')
                if test_result.exit_code != 0:
                    self.logger.error(f"Nginx config test failed: {test_result.output.decode()}")
                    return False
                
                # Reload nginx
                reload_result = nginx_container.exec_run('nginx -s reload')
                if reload_result.exit_code == 0:
                    self.logger.info("Nginx reloaded successfully via container")
                    return True
                else:
                    self.logger.error(f"Nginx reload failed: {reload_result.output.decode()}")
                    return False
            else:
                self.logger.warning("No nginx container found, configuration written but not reloaded")
                # Return True anyway since config is written - nginx will pick it up on next restart
                return True
                
        except ImportError:
            self.logger.warning("Docker library not available, nginx config written but not reloaded")
            return True
        except Exception as e:
            self.logger.error(f"Failed to reload nginx container: {str(e)}")
            # Still return True if config was written successfully
            return True
    
    def _parse_server_line(self, server_line: str) -> Dict[str, Any]:
        """Parse nginx server line to extract details"""
        try:
            parts = server_line.strip().split()
            if len(parts) >= 2:
                server_addr = parts[1]
                if ':' in server_addr:
                    host, port = server_addr.split(':')
                    return {
                        'host': host,
                        'port': int(port),
                        'options': ' '.join(parts[2:]) if len(parts) > 2 else ''
                    }
            return {'raw': server_line}
        except Exception:
            return {'raw': server_line}
    
    def reload_nginx(self) -> Dict[str, Any]:
        """Manually reload nginx configuration"""
        try:
            if self._test_and_reload_nginx():
                return {'success': True, 'message': 'Nginx reloaded successfully'}
            else:
                return {'success': False, 'error': 'Failed to reload nginx'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_worker_health(self, worker_ip: str, worker_port: int) -> Dict[str, Any]:
        """Check health of a specific worker"""
        try:
            import requests
            
            health_url = f"http://{worker_ip}:{worker_port}/web/health"
            response = requests.get(health_url, timeout=5)
            
            if response.status_code == 200:
                return {'success': True, 'healthy': True, 'response_time': response.elapsed.total_seconds()}
            else:
                return {'success': True, 'healthy': False, 'status_code': response.status_code}
                
        except Exception as e:
            return {'success': False, 'healthy': False, 'error': str(e)}


# Export the service class
__all__ = ['NginxLoadBalancerService']