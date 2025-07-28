# Standard library imports
import logging
import re
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Generator

# Third-party imports
import docker
import psycopg2

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TenantLogManager:
    def __init__(self, odoo_db_manager, db_name: Optional[str] = None):
        self.db_manager = odoo_db_manager
        self.db_name = db_name
        self.docker_client = docker.from_env()
        
        # Dynamically discover containers
        self.containers = self.discover_containers()
        
        # Log patterns for tenant identification
        self.tenant_patterns = [
            r"database\s+['\"]?(\w+)['\"]?",
            r"db[:\s]+['\"]?(\w+)['\"]?",
            r"Database\s+['\"]?(\w+)['\"]?",
            r"\[(\w+)\]",
            r"dbname=(\w+)",
            r"tenant_(\w+)"
        ]
        
        # Log level patterns
        self.level_patterns = {
            'ERROR': r'ERROR|CRITICAL|FATAL|Exception|Traceback',
            'WARNING': r'WARNING|WARN',
            'INFO': r'INFO|Starting|Stopping|Connected',
            'DEBUG': r'DEBUG',
            'SUCCESS': r'SUCCESS|SUCCESSFUL|Login successful'
        }
        
        # Cache for recent logs per tenant
        self.tenant_log_cache = defaultdict(lambda: deque(maxlen=1000))
        self.log_stats_cache = defaultdict(lambda: {
            'total': 0, 'error': 0, 'warning': 0, 
            'info': 0, 'success': 0, 'debug': 0
        })
        
        # Active monitoring threads
        self.monitoring_threads = {}
        self.active_tenants = set()

    def discover_containers(self) -> Dict[str, str]:
        """Dynamically discover running Docker containers"""
        try:
            containers = self.docker_client.containers.list()
            container_map = {}
            for container in containers:
                name = container.name
                if 'odoo' in name.lower():
                    if 'master' in name.lower():
                        container_map['odoo_master'] = name
                    elif 'worker' in name.lower():
                        container_map['odoo_worker'] = name
                elif 'postgres' in name.lower():
                    container_map['postgres'] = name
                elif 'nginx' in name.lower():
                    container_map['nginx'] = name
            logger.info(f"Discovered containers: {container_map}")
            if not container_map:
                logger.warning("No relevant containers found")
            return container_map
        except Exception as e:
            logger.error(f"Error discovering containers: {e}")
            return {}

    def extract_database_from_log(self, log_line: str) -> Optional[str]:
        """Extract database name from log line using various patterns"""
        for pattern in self.tenant_patterns:
            match = re.search(pattern, log_line, re.IGNORECASE)
            if match:
                db_name = match.group(1)
                logger.debug(f"Extracted database name: {db_name} from log: {log_line[:100]}")
                return db_name
        logger.debug(f"No tenant database found in log: {log_line[:100]}")
        return None
    
    def determine_log_level(self, log_line: str) -> str:
        """Determine log level from log content"""
        log_upper = log_line.upper()
        for level, pattern in self.level_patterns.items():
            if re.search(pattern, log_upper):
                return level.lower()
        return 'info'
    
    def parse_log_entry(self, log_line: str, container_name: str) -> Optional[Dict]:
        """Parse a single log entry into structured format"""
        if not log_line.strip():
            logger.debug("Skipping empty log line")
            return None
            
        timestamp_match = re.match(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)', log_line)
        timestamp = timestamp_match.group(1) if timestamp_match else datetime.utcnow().isoformat() + 'Z'
        
        db_name = self.extract_database_from_log(log_line)
        if not db_name:
            logger.debug(f"Skipping log without tenant DB: {log_line[:100]}")
            return None
            
        level = self.determine_log_level(log_line)
        
        parsed_log = {
            'timestamp': timestamp,
            'tenant_db': db_name,
            'service': container_name,
            'level': level,
            'message': log_line.strip(),
            'raw_log': log_line
        }
        logger.debug(f"Parsed log: {parsed_log}")
        return parsed_log
    
    def get_container_logs_stream(self, container_name: str, since_hours: int = 24) -> Generator[str, None, None]:
        """Stream logs from Docker container"""
        try:
            container = self.docker_client.containers.get(container_name)
            since_time = datetime.utcnow() - timedelta(hours=since_hours)
            logger.info(f"Streaming logs from container: {container_name}")
            
            for log_line in container.logs(stream=True, follow=True, since=since_time, timestamps=True):
                yield log_line.decode('utf-8').strip()
                
        except docker.errors.NotFound:
            logger.error(f"Container {container_name} not found")
        except Exception as e:
            logger.error(f"Error streaming logs from {container_name}: {e}")
    
    def get_logs(self, db_name: Optional[str] = None, hours: int = 24, level: str = None, limit: int = 1000) -> List[Dict]:
        """Get historical logs for specific tenant"""
        db_name = db_name or self.db_name
        if not db_name:
            logger.warning("No database name provided for get_logs")
            return []
        
        logs = []
        missing_containers = []
        
        for container_key, container_name in self.containers.items():
            try:
                container = self.docker_client.containers.get(container_name)
                since_time = datetime.utcnow() - timedelta(hours=hours)
                
                container_logs = container.logs(
                    since=since_time,
                    timestamps=True
                ).decode('utf-8').split('\n')
                
                for log_line in container_logs:
                    parsed_log = self.parse_log_entry(log_line, container_name)
                    if parsed_log and parsed_log['tenant_db'] == db_name:
                        if level and parsed_log['level'] != level:
                            continue
                        logs.append(parsed_log)
                        
            except docker.errors.NotFound:
                logger.error(f"Container {container_name} not found for {container_key}")
                missing_containers.append(container_name)
            except Exception as e:
                logger.error(f"Error getting logs from {container_name}: {e}")
        
        logs.sort(key=lambda x: x['timestamp'], reverse=True)
        logger.info(f"Retrieved {len(logs)} logs for tenant {db_name}")
        if missing_containers:
            logger.warning(f"Missing containers: {', '.join(missing_containers)}")
        return logs[:limit]
    
    def get_tenant_stats(self, db_name: str, hours: int = 24) -> Dict:
        """Get log statistics for specific tenant"""
        if db_name in self.log_stats_cache:
            return self.log_stats_cache[db_name]
            
        logs = self.get_logs(db_name=db_name, hours=hours, limit=10000)
        stats = {'total': 0, 'error': 0, 'warning': 0, 'info': 0, 'success': 0, 'debug': 0}
        
        for log in logs:
            stats['total'] += 1
            stats[log['level']] += 1
        
        stats['last_update'] = datetime.utcnow().isoformat() + 'Z'
        self.log_stats_cache[db_name] = stats
        logger.info(f"Stats for tenant {db_name}: {stats}")
        return stats
    
    def get_tenant_critical_alerts(self, db_name: str, hours: int = 24) -> List[Dict]:
        """Get critical alerts for specific tenant"""
        error_logs = self.get_logs(db_name=db_name, hours=hours, level='error', limit=50)
        
        alerts = []
        for log in error_logs:
            alert = {
                'timestamp': log['timestamp'],
                'severity': 'critical' if 'CRITICAL' in log['message'].upper() else 'high',
                'message': log['message'][:200] + '...' if len(log['message']) > 200 else log['message'],
                'service': log['service']
            }
            alerts.append(alert)
        
        logger.info(f"Retrieved {len(alerts)} critical alerts for tenant {db_name}")
        return alerts[:10]
    
    def get_database_query_logs(self, db_name: str, hours: int = 1) -> List[Dict]:
        """Get PostgreSQL query logs for specific database"""
        logs = []
        try:
            conn = psycopg2.connect(
                dbname='postgres',
                user=self.db_manager.pg_user,
                password=self.db_manager.pg_password,
                host=self.db_manager.pg_host,
                port=self.db_manager.pg_port
            )
            conn.autocommit = True
            cur = conn.cursor()
            
            # Check if pg_stat_statements is available in shared_preload_libraries
            cur.execute("SHOW shared_preload_libraries")
            preload_libs = cur.fetchone()[0]
            
            if 'pg_stat_statements' not in preload_libs:
                logger.warning(f"pg_stat_statements not in shared_preload_libraries for {db_name}. Using alternative approach.")
                # Fall back to pg_stat_activity for current queries
                return self._get_current_activity_logs(cur, db_name)
            
            # Check if pg_stat_statements extension is enabled
            cur.execute("""
                SELECT COUNT(*) 
                FROM pg_extension 
                WHERE extname = 'pg_stat_statements'
            """)
            extension_exists = cur.fetchone()[0] > 0
            
            if not extension_exists:
                # Attempt to enable pg_stat_statements
                try:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
                    logger.info(f"Enabled pg_stat_statements extension for tenant {db_name}")
                except Exception as e:
                    logger.warning(f"Failed to enable pg_stat_statements extension: {e}")
                    # Fall back to current activity
                    return self._get_current_activity_logs(cur, db_name)
            
            # Determine PostgreSQL version for correct column names
            cur.execute("SELECT version()")
            pg_version = cur.fetchone()[0]
            major_version = int(pg_version.split()[1].split('.')[0])
            
            # Use appropriate column names based on PostgreSQL version
            total_time_col = 'total_exec_time' if major_version >= 13 else 'total_time'
            mean_time_col = 'mean_exec_time' if major_version >= 13 else 'mean_time'
            
            # Query pg_stat_statements
            cur.execute(f"""
                SELECT query, calls, {total_time_col}, {mean_time_col}, rows
                FROM pg_stat_statements 
                WHERE dbid = (SELECT oid FROM pg_database WHERE datname = %s)
                ORDER BY {total_time_col} DESC LIMIT 50
            """, (db_name,))
            
            for row in cur.fetchall():
                logs.append({
                    'timestamp': datetime.utcnow().isoformat() + 'Z',
                    'tenant_db': db_name,
                    'service': 'postgres',
                    'level': 'info',
                    'message': f"Query: {row[0][:100]}..., Calls: {row[1]}, Time: {row[2]}ms",
                    'query_stats': {
                        'calls': row[1],
                        'total_time': row[2],
                        'mean_time': row[3],
                        'rows': row[4]
                    }
                })
            
            conn.close()
            logger.info(f"Retrieved {len(logs)} database query logs for tenant {db_name}")
            
        except Exception as e:
            logger.warning(f"Error getting database query logs for {db_name}: {str(e)}")
            # Try alternative approach if main method fails
            try:
                return self._get_current_activity_logs(cur, db_name)
            except:
                pass
        
        return logs

    def _get_current_activity_logs(self, cur, db_name: str) -> List[Dict]:
        """Alternative method to get current database activity when pg_stat_statements is not available"""
        logs = []
        try:
            # Get current active queries
            cur.execute("""
                SELECT 
                    query,
                    state,
                    query_start,
                    state_change,
                    application_name,
                    client_addr
                FROM pg_stat_activity 
                WHERE datname = %s 
                AND state != 'idle'
                AND query != '<IDLE>'
                AND query NOT LIKE '%%pg_stat_activity%%'
                ORDER BY query_start DESC
                LIMIT 20
            """, (db_name,))
            
            for row in cur.fetchall():
                logs.append({
                    'timestamp': datetime.utcnow().isoformat() + 'Z',
                    'tenant_db': db_name,
                    'service': 'postgres',
                    'level': 'info',
                    'message': f"Active Query: {row[0][:100]}..., State: {row[1]}",
                    'query_info': {
                        'query': row[0][:200],
                        'state': row[1],
                        'query_start': row[2].isoformat() if row[2] else None,
                        'state_change': row[3].isoformat() if row[3] else None,
                        'application_name': row[4],
                        'client_addr': str(row[5]) if row[5] else None
                    }
                })
            
            logger.info(f"Retrieved {len(logs)} current activity logs for tenant {db_name}")
            
        except Exception as e:
            logger.warning(f"Error getting current activity logs for {db_name}: {str(e)}")
        
        return logs

    def start_tenant_monitoring(self, db_name: str, socketio_instance, room_name: str):
        """Start real-time monitoring for specific tenant"""
        if db_name in self.monitoring_threads:
            logger.info(f"Monitoring already active for tenant {db_name}")
            return
        
        def monitor_tenant():
            logger.info(f"Starting monitoring for tenant: {db_name}")
            self.active_tenants.add(db_name)
            
            for container_name in self.containers.values():
                try:
                    for log_line in self.get_container_logs_stream(container_name):
                        if db_name not in self.active_tenants:
                            logger.info(f"Stopping monitoring for tenant {db_name}")
                            break
                        
                        parsed_log = self.parse_log_entry(log_line, container_name)
                        if parsed_log and parsed_log['tenant_db'] == db_name:
                            self.tenant_log_cache[db_name].append(parsed_log)
                            
                            stats = self.log_stats_cache[db_name]
                            stats['total'] += 1
                            stats[parsed_log['level']] += 1
                            stats['last_update'] = datetime.utcnow().isoformat() + 'Z'
                            
                            logger.debug(f"Emitting log for {db_name}: {parsed_log['message'][:50]}...")
                            socketio_instance.emit('new_log', parsed_log, room=room_name)
                            socketio_instance.emit('stats_update', stats, room=room_name)
                            
                except Exception as e:
                    logger.error(f"Error in tenant monitoring for {db_name}: {e}")
        
        thread = threading.Thread(target=monitor_tenant, daemon=True)
        thread.start()
        self.monitoring_threads[db_name] = thread
    
    def stop_tenant_monitoring(self, db_name: str):
        """Stop monitoring for specific tenant"""
        self.active_tenants.discard(db_name)
        if db_name in self.monitoring_threads:
            del self.monitoring_threads[db_name]
        logger.info(f"Stopped monitoring for tenant: {db_name}")
    
    def get_available_tenants(self, user_id: Optional[int] = None, is_admin: bool = False) -> List[str]:
        """Get list of available tenant databases, restricted to user's tenant unless admin"""
        try:
            conn = psycopg2.connect(
                dbname='postgres',
                user=self.db_manager.pg_user,
                password=self.db_manager.pg_password,
                host=self.db_manager.pg_host,
                port=self.db_manager.pg_port
            )
            
            cur = conn.cursor()
            if is_admin:
                cur.execute("""
                    SELECT datname FROM pg_database 
                    WHERE datname NOT IN ('postgres', 'template0', 'template1')
                    AND datallowconn = true
                    ORDER BY datname
                """)
            else:
                # Only return the tenant's database if user_id is provided and not admin
                if user_id and self.db_name:
                    cur.execute("""
                        SELECT datname FROM pg_database 
                        WHERE datname = %s AND datallowconn = true
                    """, (self.db_name,))
                else:
                    logger.warning("No user_id or db_name provided for non-admin tenant list")
                    return []
            
            tenants = [row[0] for row in cur.fetchall()]
            conn.close()
            logger.info(f"Retrieved {len(tenants)} available tenants for user_id={user_id}, is_admin={is_admin}")
            return tenants
            
        except Exception as e:
            logger.error(f"Error getting tenant list: {e}")
            return []