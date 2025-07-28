# log_transfer_api/models/log_transfer.py

# Standard library imports
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta

# Third-party imports
import psycopg2
from psycopg2.extras import RealDictCursor

# Odoo imports
from odoo import models, fields, api, http
from odoo.http import request

_logger = logging.getLogger(__name__)

class LogTransfer(models.Model):
    _name = 'log.transfer'
    _description = 'Log Transfer Configuration'
    _rec_name = 'tenant_name'

    tenant_name = fields.Char('Tenant Name', required=True)
    database_name = fields.Char('Database Name', required=True)
    is_active = fields.Boolean('Active', default=True)
    last_sync = fields.Datetime('Last Sync')
    auth_token = fields.Char('Auth Token')
    created_date = fields.Datetime('Created Date', default=fields.Datetime.now)
    
    log_level_filter = fields.Selection([
        ('DEBUG', 'Debug'),
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
        ('CRITICAL', 'Critical')
    ], string='Minimum Log Level', default='INFO')
    
    include_system_logs = fields.Boolean('Include System Logs', default=True)
    include_access_logs = fields.Boolean('Include Access Logs', default=True)
    include_sql_logs = fields.Boolean('Include SQL Logs', default=False)

    @api.model
    def authenticate_tenant(self, admin_id, password, database_name):
        """Enhanced authentication with database validation"""
        try:
            if not self._validate_database_exists(database_name):
                return {'error': f'Database {database_name} does not exist'}

            uid = self._authenticate_user(admin_id, password, database_name)
            if not uid:
                return {'error': 'Invalid credentials'}

            if not self._check_admin_privileges(uid, database_name):
                return {'error': 'Admin privileges required'}

            log_config = self.search([('database_name', '=', database_name)], limit=1)
            if not log_config:
                log_config = self.create({
                    'tenant_name': database_name,
                    'database_name': database_name,
                    'auth_token': self._generate_token(),
                })

            return {
                'success': True,
                'token': log_config.auth_token,
                'tenant_id': log_config.id,
                'websocket_url': f'/log_stream/{log_config.auth_token}',
                'database_name': database_name,
                'available_log_sources': self._get_available_log_sources(database_name)
            }
        except Exception as e:
            _logger.error(f"Authentication error: {str(e)}")
            return {'error': str(e)}

    def _validate_database_exists(self, database_name):
        try:
            import odoo.tools.config as config
            db_host = config.get('db_host', 'localhost')
            db_port = config.get('db_port', 5432)
            db_user = config.get('db_user', 'odoo')
            db_password = config.get('db_password', '')
            
            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                database='postgres'
            )
            
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database_name,))
                exists = cur.fetchone() is not None
            
            conn.close()
            return exists
            
        except Exception as e:
            _logger.error(f"Database validation error: {str(e)}")
            return False

    def _authenticate_user(self, admin_id, password, database_name):
        try:
            from odoo.modules.registry import Registry
            from odoo.api import Environment
            import odoo.tools.config as config
            
            db_host = config.get('db_host', 'localhost')
            db_port = config.get('db_port', 5432)
            db_user = config.get('db_user', 'odoo')
            db_password = config.get('db_password', '')
            
            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                database=database_name
            )
            
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, password FROM res_users WHERE login = %s AND active = true",
                    (admin_id,)
                )
                user_record = cur.fetchone()
                
                if user_record:
                    from passlib.context import CryptContext
                    pwd_context = CryptContext(schemes=['pbkdf2_sha512'], deprecated='auto')
                    
                    if pwd_context.verify(password, user_record['password']):
                        return user_record['id']
            
            conn.close()
            return None
            
        except Exception as e:
            _logger.error(f"User authentication error: {str(e)}")
            return None

    def _check_admin_privileges(self, uid, database_name):
        try:
            import odoo.tools.config as config
            
            db_host = config.get('db_host', 'localhost')
            db_port = config.get('db_port', 5432)
            db_user = config.get('db_user', 'odoo')
            db_password = config.get('db_password', '')
            
            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                database=database_name
            )
            
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 1 FROM res_groups_users_rel rgur
                    JOIN res_groups rg ON rgur.gid = rg.id
                    WHERE rgur.uid = %s AND rg.name = 'Access Rights'
                """, (uid,))
                
                is_admin = cur.fetchone() is not None
            
            conn.close()
            return is_admin
            
        except Exception as e:
            _logger.error(f"Admin privilege check error: {str(e)}")
            return False

    def _get_available_log_sources(self, database_name):
        sources = []
        
        log_paths = [
            f'/var/log/odoo/odoo-{database_name}.log',
            f'/var/log/odoo/{database_name}.log',
            f'/opt/odoo/logs/{database_name}.log',
            '/var/log/odoo/odoo.log'
        ]
        
        for path in log_paths:
            if os.path.exists(path):
                sources.append({
                    'type': 'file',
                    'path': path,
                    'size': os.path.getsize(path)
                })
        
        try:
            if self._check_ir_logging_exists(database_name):
                sources.append({
                    'type': 'database',
                    'table': 'ir_logging'
                })
        except:
            pass
            
        return sources

    def _check_ir_logging_exists(self, database_name):
        try:
            import odoo.tools.config as config
            
            db_host = config.get('db_host', 'localhost')
            db_port = config.get('db_port', 5432)
            db_user = config.get('db_user', 'odoo')
            db_password = config.get('db_password', '')
            
            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                database=database_name
            )
            
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'ir_logging'
                    )
                """)
                table_exists = cur.fetchone()[0]
                
                if table_exists:
                    cur.execute("SELECT COUNT(*) FROM ir_logging LIMIT 1")
                    has_data = cur.fetchone()[0] > 0
                    return has_data
            
            conn.close()
            return False
            
        except Exception as e:
            _logger.error(f"ir.logging check error: {str(e)}")
            return False

    @api.model
    def get_logs(self, token, limit=100, offset=0, level='INFO', start_date=None, end_date=None):
        log_config = self.search([('auth_token', '=', token)], limit=1)
        if not log_config:
            return {'error': 'Invalid token'}

        try:
            all_logs = []
            
            db_logs = self._fetch_database_logs(
                log_config.database_name, limit, offset, level, start_date, end_date
            )
            all_logs.extend(db_logs)
            
            file_logs = self._fetch_file_logs(
                log_config.database_name, limit, offset, level, start_date, end_date
            )
            all_logs.extend(file_logs)
            
            if log_config.include_system_logs:
                system_logs = self._fetch_system_logs(
                    log_config.database_name, limit, offset, level
                )
                all_logs.extend(system_logs)
            
            all_logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            if limit:
                all_logs = all_logs[:limit]
            
            return {
                'success': True,
                'logs': all_logs,
                'total': len(all_logs),
                'tenant': log_config.tenant_name,
                'database': log_config.database_name,
                'sources_checked': ['database', 'files', 'system']
            }
            
        except Exception as e:
            _logger.error(f"Error fetching logs: {str(e)}")
            return {'error': str(e)}

    def _fetch_database_logs(self, database_name, limit=100, offset=0, level='INFO', start_date=None, end_date=None):
        logs = []
        try:
            import odoo.tools.config as config
            
            db_host = config.get('db_host', 'localhost')
            db_port = config.get('db_port', 5432)
            db_user = config.get('db_user', 'odoo')
            db_password = config.get('db_password', '')
            
            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                database=database_name
            )
            
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = """
                    SELECT id, create_date, name, level, message, path, func, line, dbname
                    FROM ir_logging 
                    WHERE 1=1
                """
                params = []
                
                if level and level != 'ALL':
                    level_order = {'DEBUG': 0, 'INFO': 1, 'WARNING': 2, 'ERROR': 3, 'CRITICAL': 4}
                    min_level = level_order.get(level, 1)
                    query += " AND CASE "
                    query += " WHEN level = 'DEBUG' THEN 0"
                    query += " WHEN level = 'INFO' THEN 1"
                    query += " WHEN level = 'WARNING' THEN 2"
                    query += " WHEN level = 'ERROR' THEN 3"
                    query += " WHEN level = 'CRITICAL' THEN 4"
                    query += " ELSE 1 END >= %s"
                    params.append(min_level)
                
                if start_date:
                    query += " AND create_date >= %s"
                    params.append(start_date)
                    
                if end_date:
                    query += " AND create_date <= %s"
                    params.append(end_date)
                
                query += " ORDER BY create_date DESC"
                
                if limit:
                    query += " LIMIT %s"
                    params.append(limit)
                    
                if offset:
                    query += " OFFSET %s"
                    params.append(offset)
                
                cur.execute(query, params)
                records = cur.fetchall()
                
                for record in records:
                    logs.append({
                        'id': record['id'],
                        'timestamp': record['create_date'].isoformat() if record['create_date'] else None,
                        'level': record['level'],
                        'message': record['message'],
                        'logger_name': record['name'],
                        'function': record['func'],
                        'line': record['line'],
                        'path': record['path'],
                        'database': record['dbname'] or database_name,
                        'source': 'database'
                    })
            
            conn.close()
            
        except Exception as e:
            _logger.error(f"Database log fetch error: {str(e)}")
            
        return logs

    def _fetch_file_logs(self, database_name, limit=100, offset=0, level='INFO', start_date=None, end_date=None):
        logs = []
        
        log_paths = [
            f'/var/log/odoo/odoo-{database_name}.log',
            f'/var/log/odoo/{database_name}.log',
            f'/opt/odoo/logs/{database_name}.log',
            '/var/log/odoo/odoo.log'
        ]
        
        for log_path in log_paths:
            if os.path.exists(log_path):
                try:
                    logs.extend(self._parse_log_file(
                        log_path, database_name, limit, level, start_date, end_date
                    ))
                except Exception as e:
                    _logger.error(f"Error parsing log file {log_path}: {str(e)}")
        
        return logs

    def _parse_log_file(self, log_path, database_name, limit=100, level='INFO', start_date=None, end_date=None):
        logs = []
        
        log_pattern = re.compile(
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) '  # timestamp
            r'(\d+) '  # process id
            r'(\w+) '  # log level
            r'([^\s]+) '  # logger name
            r'(.+)'  # message
        )
        
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                
                for line in reversed(lines[-10000:]):
                    line = line.strip()
                    if not line:
                        continue
                    
                    match = log_pattern.match(line)
                    if match:
                        timestamp_str, pid, log_level, logger_name, message = match.groups()
                        
                        try:
                            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                        except:
                            timestamp = datetime.now()
                        
                        level_order = {'DEBUG': 0, 'INFO': 1, 'WARNING': 2, 'ERROR': 3, 'CRITICAL': 4}
                        if level != 'ALL':
                            min_level = level_order.get(level, 1)
                            current_level = level_order.get(log_level, 1)
                            if current_level < min_level:
                                continue
                        
                        if start_date and timestamp < datetime.fromisoformat(start_date):
                            continue
                        if end_date and timestamp > datetime.fromisoformat(end_date):
                            continue
                        
                        if database_name.lower() in message.lower() or database_name in logger_name:
                            logs.append({
                                'timestamp': timestamp.isoformat(),
                                'level': log_level,
                                'message': message,
                                'logger_name': logger_name,
                                'pid': pid,
                                'database': database_name,
                                'source': 'file',
                                'file_path': log_path
                            })
                            
                            if len(logs) >= limit:
                                break
                    
        except Exception as e:
            _logger.error(f"Log file parsing error: {str(e)}")
        
        return logs

    def _fetch_system_logs(self, database_name, limit=50, offset=0, level='INFO'):
        logs = []
        
        try:
            import subprocess
            
            cmd = [
                'journalctl',
                '-u', 'odoo*',
                '--output=json',
                '--lines', str(limit),
                '--grep', database_name
            ]
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    for line in result.stdout.strip().split('\n'):
                        if line:
                            try:
                                log_entry = json.loads(line)
                                logs.append({
                                    'timestamp': log_entry.get('__REALTIME_TIMESTAMP'),
                                    'level': 'INFO',
                                    'message': log_entry.get('MESSAGE', ''),
                                    'service': log_entry.get('_SYSTEMD_UNIT', ''),
                                    'database': database_name,
                                    'source': 'systemd'
                                })
                            except json.JSONDecodeError:
                                continue
            except subprocess.TimeoutExpired:
                _logger.warning("System log fetch timed out")
            except FileNotFoundError:
                _logger.info("journalctl not available")
                
        except Exception as e:
            _logger.error(f"System log fetch error: {str(e)}")
        
        return logs

    def _generate_token(self):
        import secrets
        return secrets.token_urlsafe(32)

    @api.model
    def get_log_statistics(self, token):
        log_config = self.search([('auth_token', '=', token)], limit=1)
        if not log_config:
            return {'error': 'Invalid token'}
        
        try:
            stats = {
                'database_name': log_config.database_name,
                'tenant_name': log_config.tenant_name,
                'total_logs': 0,
                'logs_by_level': {},
                'logs_by_source': {},
                'last_24h': 0,
                'last_week': 0
            }
            
            db_stats = self._get_database_log_stats(log_config.database_name)
            stats.update(db_stats)
            
            return {
                'success': True,
                'statistics': stats
            }
            
        except Exception as e:
            return {'error': str(e)}

    def _get_database_log_stats(self, database_name):
        stats = {
            'total_logs': 0,
            'logs_by_level': {},
            'last_24h': 0,
            'last_week': 0
        }
        
        try:
            import odoo.tools.config as config
            
            db_host = config.get('db_host', 'localhost')
            db_port = config.get('db_port', 5432)
            db_user = config.get('db_user', 'odoo')
            db_password = config.get('db_password', '')
            
            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                database=database_name
            )
            
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM ir_logging")
                stats['total_logs'] = cur.fetchone()[0]
                
                cur.execute("SELECT level, COUNT(*) FROM ir_logging GROUP BY level")
                for level, count in cur.fetchall():
                    stats['logs_by_level'][level] = count
                
                cur.execute("""
                    SELECT COUNT(*) FROM ir_logging 
                    WHERE create_date >= NOW() - INTERVAL '24 hours'
                """)
                stats['last_24h'] = cur.fetchone()[0]
                
                cur.execute("""
                    SELECT COUNT(*) FROM ir_logging 
                    WHERE create_date >= NOW() - INTERVAL '7 days'
                """)
                stats['last_week'] = cur.fetchone()[0]
            
            conn.close()
            
        except Exception as e:
            _logger.error(f"Database stats error: {str(e)}")
        
        return stats