#!/usr/bin/env python3

"""
Disaster Recovery Backup Panel
Flask-based web interface for managing backups and disaster recovery
"""

import os
import sys
import json
import sqlite3
import subprocess
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import threading
import time

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
import schedule
import secrets
import base64
from urllib.parse import urlencode, urlparse, parse_qs
import requests

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent / 'scripts'))

try:
    from gdrive_integration import GoogleDriveBackup
except ImportError:
    GoogleDriveBackup = None

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dr-backup-panel-secret-key-change-me')

# Add custom Jinja2 filters
@app.template_filter('as_datetime')
def as_datetime_filter(value):
    """Convert ISO string to datetime object"""
    try:
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        return value
    except (ValueError, AttributeError):
        return None

# Configure detailed logging
log_format = '[%(asctime)s] [%(levelname)s] %(message)s'

# Create log handlers
handlers = [logging.StreamHandler(sys.stdout)]  # Console output

# Note: We'll configure the file handler after DATA_DIR is set up

logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=handlers
)
logger = logging.getLogger(__name__)

# Also set Flask's logger to be more verbose
logging.getLogger('werkzeug').setLevel(logging.INFO)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Configuration
# Initial path definitions (will be updated after path detection)
BASE_DIR = Path(__file__).parent.parent
CONFIG_FILE = BASE_DIR / 'config' / 'dr-config.env'
SCRIPTS_DIR = BASE_DIR / 'scripts'

# Fix paths for Windows/Docker environment
# Try to detect the correct base directory
possible_base_dirs = [
    Path("K:/Odoo Multi-Tenant System/dr-backups"),  # Windows absolute path
    Path(__file__).parent.parent,  # Relative to this script
    Path.cwd(),  # Current working directory
    Path.cwd().parent,  # Parent of current working directory
    Path("/app/dr-backups"),  # Docker path
    Path("/opt/dr-backups"),  # Alternative Docker path
]

# Find the correct base directory
BASE_DIR_FOUND = False
for potential_base in possible_base_dirs:
    if potential_base.exists() and (potential_base / 'scripts').exists():
        BASE_DIR = potential_base
        BASE_DIR_FOUND = True
        break

if not BASE_DIR_FOUND:
    # Fallback to default
    BASE_DIR = Path(__file__).parent.parent

# Update other paths based on the found base directory
SCRIPTS_DIR = BASE_DIR / 'scripts'

# Use writable data directory in Docker for persistent data
DATA_DIR = Path('/app/data')
CONFIG_FILE = DATA_DIR / 'dr-config.env'  # Save config to writable directory
DB_FILE = DATA_DIR / 'backup_panel.db'
LOGS_DIR = DATA_DIR / 'logs'
SESSIONS_DIR = DATA_DIR / 'sessions'

# Create necessary directories in the writable data volume
for directory in [DATA_DIR, LOGS_DIR, SESSIONS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Now configure file logging with the writable logs directory
try:
    log_file = LOGS_DIR / 'backup-panel.log'
    file_handler = logging.FileHandler(log_file, mode='a')
    file_handler.setFormatter(logging.Formatter(log_format))
    logging.getLogger().addHandler(file_handler)
except Exception as e:
    print(f"Warning: Could not create log file: {e}")

# Configure Flask session storage to use the writable sessions directory
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = str(SESSIONS_DIR)

# Log the final paths for debugging
print(f"DEBUG: BASE_DIR = {BASE_DIR}")
print(f"DEBUG: SCRIPTS_DIR = {SCRIPTS_DIR}")
print(f"DEBUG: SCRIPTS_DIR exists = {SCRIPTS_DIR.exists()}")
print(f"DEBUG: Enhanced backup script path = {SCRIPTS_DIR / 'enhanced-backup.sh'}")
print(f"DEBUG: Enhanced backup script exists = {(SCRIPTS_DIR / 'enhanced-backup.sh').exists()}")

class Config:
    """Configuration manager for the backup panel"""
    
    def __init__(self):
        self.config = {}
        self.load_config()
    
    def load_config(self):
        """Load configuration from dr-config.env (fallback to original location)"""
        # Try writable location first, then fallback to original read-only location
        config_paths = [CONFIG_FILE, BASE_DIR / 'config' / 'dr-config.env']
        
        for config_path in config_paths:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if '=' in line and not line.startswith('#'):
                            key, value = line.split('=', 1)
                            self.config[key.strip()] = value.strip().strip('"')
                break
        
        # Set defaults
        self.config.setdefault('DR_BACKUP_DESTINATIONS', 'gdrive')
        self.config.setdefault('DR_NOTIFICATION_EMAIL', '')
        self.config.setdefault('ADMIN_USERNAME', 'admin')
        self.config.setdefault('ADMIN_PASSWORD_HASH', generate_password_hash('admin'))
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any):
        """Set configuration value"""
        self.config[key] = value
    
    def save_config(self):
        """Save configuration back to file"""
        with open(CONFIG_FILE, 'w') as f:
            f.write("# Disaster Recovery Configuration\n")
            f.write("# Updated by Backup Panel\n\n")
            
            for key, value in self.config.items():
                if isinstance(value, str) and ' ' in value:
                    f.write(f'{key}="{value}"\n')
                else:
                    f.write(f'{key}={value}\n')
    
    def sync_cloud_credentials(self):
        """Sync cloud credentials from database to config file"""
        try:
            # Get Google Drive credentials from database
            gdrive_conn = db.get_cloud_connection('google_drive')
            logger.info(f"DEBUG: Retrieved Google Drive connection: {bool(gdrive_conn)}")
            if gdrive_conn and gdrive_conn.get('credentials'):
                creds = gdrive_conn['credentials']
                logger.info(f"DEBUG: Credentials keys: {list(creds.keys())}")
                
                # Update config with credentials
                if creds.get('client_id'):
                    self.set('GDRIVE_CLIENT_ID', creds['client_id'])
                    logger.info("DEBUG: Set GDRIVE_CLIENT_ID")
                if creds.get('client_secret'):
                    self.set('GDRIVE_CLIENT_SECRET', creds['client_secret'])
                    logger.info("DEBUG: Set GDRIVE_CLIENT_SECRET")
                if creds.get('access_token'):
                    self.set('GDRIVE_ACCESS_TOKEN', creds['access_token'])
                    logger.info("DEBUG: Set GDRIVE_ACCESS_TOKEN")
                if creds.get('refresh_token'):
                    self.set('GDRIVE_REFRESH_TOKEN', creds['refresh_token'])
                    logger.info("DEBUG: Set GDRIVE_REFRESH_TOKEN")
                
                # Save updated config
                self.save_config()
                logger.info("Synced Google Drive credentials from database to config file")
                return True
            else:
                logger.warning("No Google Drive credentials found in database")
        except Exception as e:
            logger.error(f"Failed to sync cloud credentials: {e}")
        return False

def ensure_encryption_key():
    """Ensure encryption key exists and is properly secured"""
    key_file = Path(config.get('DR_ENCRYPTION_KEY', '/app/data/encryption.key'))
    
    if not key_file.exists():
        logger.info(f"Creating encryption key: {key_file}")
        key_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Generate a secure 256-bit key
        import secrets
        key = secrets.token_hex(32)
        
        with open(key_file, 'w') as f:
            f.write(key)
        
        # Set restrictive permissions
        os.chmod(key_file, 0o600)
        logger.info("Encryption key created successfully")
    
    return str(key_file)

# Call this function after config initialization
config = Config()
ensure_encryption_key()

class User(UserMixin):
    """Simple user model for authentication"""
    
    def __init__(self, username: str):
        self.id = username
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    """Load user for Flask-Login"""
    if user_id == config.get('ADMIN_USERNAME'):
        return User(user_id)
    return None

class DatabaseManager:
    """Database manager for backup metadata"""
    
    def __init__(self):
        self.db_file = DB_FILE
        self.init_database()
    
    def init_database(self):
        """Initialize the database schema"""
        os.makedirs(os.path.dirname(self.db_file), exist_ok=True)
        
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            
            # Backup sessions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS backup_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP,
                    status TEXT NOT NULL DEFAULT 'running',
                    destinations TEXT,
                    errors INTEGER DEFAULT 0,
                    warnings INTEGER DEFAULT 0,
                    database_count INTEGER DEFAULT 0,
                    filestore_size INTEGER DEFAULT 0,
                    total_size INTEGER DEFAULT 0,
                    manifest_path TEXT,
                    log_file TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Backup schedules table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS backup_schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    cron_expression TEXT NOT NULL,
                    destinations TEXT NOT NULL,
                    enabled BOOLEAN DEFAULT 1,
                    last_run TIMESTAMP,
                    next_run TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Storage usage table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS storage_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    total_bytes INTEGER,
                    used_bytes INTEGER,
                    available_bytes INTEGER,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Cloud connections table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cloud_connections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'disconnected',
                    credentials TEXT,
                    metadata TEXT,
                    connected_at TIMESTAMP,
                    last_test TIMESTAMP,
                    last_test_status TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
    
    def add_backup_session(self, session_data: Dict[str, Any]) -> int:
        """Add a new backup session"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO backup_sessions 
                (session_id, start_time, destinations, manifest_path, log_file)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                session_data['session_id'],
                session_data['start_time'],
                session_data.get('destinations', ''),
                session_data.get('manifest_path', ''),
                session_data.get('log_file', '')
            ))
            return cursor.lastrowid
    
    def update_backup_session(self, session_id: str, updates: Dict[str, Any]):
        """Update an existing backup session"""
        if not updates:
            return
        
        set_clause = ', '.join([f"{key} = ?" for key in updates.keys()])
        values = list(updates.values()) + [session_id]
        
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute(f'''
                UPDATE backup_sessions 
                SET {set_clause}
                WHERE session_id = ?
            ''', values)
    
    def get_backup_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent backup sessions"""
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM backup_sessions 
                ORDER BY start_time DESC 
                LIMIT ?
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_backup_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific backup session"""
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM backup_sessions 
                WHERE session_id = ?
            ''', (session_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def save_cloud_connection(self, provider: str, credentials: Dict[str, Any], metadata: Dict[str, Any] = None):
        """Save cloud connection credentials"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            credentials_json = json.dumps(credentials)
            metadata_json = json.dumps(metadata or {})
            
            cursor.execute('''
                INSERT OR REPLACE INTO cloud_connections 
                (provider, status, credentials, metadata, connected_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (provider, 'connected', credentials_json, metadata_json, 
                  datetime.now().isoformat(), datetime.now().isoformat()))
            conn.commit()
    
    def get_cloud_connection(self, provider: str) -> Dict[str, Any]:
        """Get cloud connection details"""
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM cloud_connections WHERE provider = ?
            ''', (provider,))
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result.get('credentials'):
                    result['credentials'] = json.loads(result['credentials'])
                if result.get('metadata'):
                    result['metadata'] = json.loads(result['metadata'])
                return result
            return None
    
    def get_all_cloud_connections(self) -> List[Dict[str, Any]]:
        """Get all cloud connections"""
        with sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM cloud_connections ORDER BY provider')
            rows = cursor.fetchall()
            connections = []
            for row in rows:
                result = dict(row)
                if result.get('credentials'):
                    result['credentials'] = json.loads(result['credentials'])
                if result.get('metadata'):
                    result['metadata'] = json.loads(result['metadata'])
                connections.append(result)
            return connections
    
    def update_connection_test(self, provider: str, status: str):
        """Update connection test status"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE cloud_connections 
                SET last_test = ?, last_test_status = ?, updated_at = ?
                WHERE provider = ?
            ''', (datetime.now().isoformat(), status, datetime.now().isoformat(), provider))
            conn.commit()

db = DatabaseManager()

# Sync cloud credentials from database to config file on startup
try:
    config.sync_cloud_credentials()
    logger.info("Synced cloud credentials on startup")
except Exception as e:
    logger.warning(f"Failed to sync cloud credentials on startup: {e}")

class BackupManager:
    """Manager for backup operations"""
    
    def __init__(self):
        self.config = config
        self.db = db
        self.restore_sessions = {}  # Track ongoing restore operations
    
    def run_backup(self, destinations: Optional[List[str]] = None) -> Dict[str, Any]:
        """Run a backup operation"""
        try:
            # Prepare environment
            env = os.environ.copy()
            if destinations:
                env['DR_BACKUP_DESTINATIONS'] = ','.join(destinations)
            
            # Set Docker environment indicator
            env['DOCKER_CONTAINER'] = '1'
            
            # Get Google Drive credentials for command line arguments
            logger.info("DETAILED_DEBUG: === Starting Google Drive credential retrieval ===")
            gdrive_creds = {}
            try:
                logger.info("DETAILED_DEBUG: Calling db.get_cloud_connection('google_drive')")
                gdrive_conn = db.get_cloud_connection('google_drive')
                logger.info(f"DETAILED_DEBUG: db.get_cloud_connection result: {gdrive_conn}")
                
                if gdrive_conn and gdrive_conn.get('credentials'):
                    creds = gdrive_conn['credentials']
                    logger.info(f"DETAILED_DEBUG: Raw credentials from database: {creds}")
                    logger.info(f"DETAILED_DEBUG: Backup runtime credentials keys: {list(creds.keys())}")
                    
                    # Extract each credential with detailed logging
                    client_id = creds.get('client_id', '')
                    client_secret = creds.get('client_secret', '')
                    access_token = creds.get('access_token', '')
                    refresh_token = creds.get('refresh_token', '')
                    
                    logger.info(f"DETAILED_DEBUG: Extracted client_id: '{client_id}' (type: {type(client_id)}, len: {len(client_id)})")
                    logger.info(f"DETAILED_DEBUG: Extracted client_secret: '{client_secret}' (type: {type(client_secret)}, len: {len(client_secret)})")
                    logger.info(f"DETAILED_DEBUG: Extracted access_token: '{access_token[:50]}...' (type: {type(access_token)}, len: {len(access_token)})")
                    logger.info(f"DETAILED_DEBUG: Extracted refresh_token: '{refresh_token[:50]}...' (type: {type(refresh_token)}, len: {len(refresh_token)})")
                    
                    gdrive_creds = {
                        'client_id': client_id,
                        'client_secret': client_secret,
                        'access_token': access_token,
                        'refresh_token': refresh_token
                    }
                    
                    logger.info(f"DETAILED_DEBUG: Final gdrive_creds dictionary: {gdrive_creds}")
                    logger.info(f"DETAILED_DEBUG: Google Drive credentials prepared for script arguments")
                else:
                    logger.warning("DETAILED_DEBUG: No Google Drive connection found in database during backup")
            except Exception as e:
                logger.warning(f"Failed to add Google Drive credentials to environment: {e}")
            
            # Set database connection info for Docker
            env['POSTGRES_HOST'] = 'postgres'
            env['POSTGRES_PORT'] = '5432'
            env['POSTGRES_USER'] = 'odoo_master'
            env['POSTGRES_PASSWORD'] = 'secure_password_123'
            
            # Ensure logs directory exists
            LOGS_DIR.mkdir(exist_ok=True)
            logger.info(f"Logs directory ensured: {LOGS_DIR}")
            
            # Run enhanced backup script
            script_path = SCRIPTS_DIR / 'enhanced-backup.sh'
            
            logger.info(f"Starting backup with destinations: {destinations}")
            logger.info(f"Script path: {script_path}")
            logger.info(f"Working directory: {BASE_DIR}")
            
            # Check if script exists
            if not script_path.exists():
                logger.error(f"Backup script not found: {script_path}")
                logger.error(f"BASE_DIR: {BASE_DIR}")
                logger.error(f"SCRIPTS_DIR: {SCRIPTS_DIR}")
                logger.error(f"Current working directory: {os.getcwd()}")
                logger.error(f"Directory contents: {list(SCRIPTS_DIR.iterdir()) if SCRIPTS_DIR.exists() else 'SCRIPTS_DIR does not exist'}")
                return {
                    'success': False,
                    'error': f'Backup script not found: {script_path}. Check logs for details.',
                    'session_id': None
                }
            
            # Determine shell command based on OS and add Google Drive credentials as arguments
            if os.name == 'nt':  # Windows
                cmd = ['bash', str(script_path)]
            else:  # Unix-like
                cmd = [str(script_path)]
            
            # Add Google Drive credentials as command line arguments if available
            logger.info("DETAILED_DEBUG: === Preparing command line arguments ===")
            logger.info(f"DETAILED_DEBUG: gdrive_creds exists: {bool(gdrive_creds)}")
            logger.info(f"DETAILED_DEBUG: any(gdrive_creds.values()): {any(gdrive_creds.values()) if gdrive_creds else False}")
            
            if gdrive_creds and any(gdrive_creds.values()):
                client_id_arg = gdrive_creds.get('client_id', '')
                client_secret_arg = gdrive_creds.get('client_secret', '')
                access_token_arg = gdrive_creds.get('access_token', '')
                refresh_token_arg = gdrive_creds.get('refresh_token', '')
                
                logger.info(f"DETAILED_DEBUG: Command arg values before adding to cmd:")
                logger.info(f"DETAILED_DEBUG:   client_id_arg: '{client_id_arg}' (len={len(client_id_arg)})")
                logger.info(f"DETAILED_DEBUG:   client_secret_arg: '{client_secret_arg}' (len={len(client_secret_arg)})")
                logger.info(f"DETAILED_DEBUG:   access_token_arg: '{access_token_arg[:50]}...' (len={len(access_token_arg)})")
                logger.info(f"DETAILED_DEBUG:   refresh_token_arg: '{refresh_token_arg[:50]}...' (len={len(refresh_token_arg)})")
                
                cmd.extend([
                    '--gdrive-client-id', client_id_arg,
                    '--gdrive-client-secret', client_secret_arg,
                    '--gdrive-access-token', access_token_arg,
                    '--gdrive-refresh-token', refresh_token_arg
                ])
                
                logger.info(f"DETAILED_DEBUG: Added Google Drive credentials as command line arguments")
                logger.info(f"DETAILED_DEBUG: Full command (sanitized): {cmd[0]} {cmd[1] if len(cmd) > 1 and not cmd[1].startswith('--') else ''} --gdrive-client-id [REDACTED] --gdrive-client-secret [REDACTED] --gdrive-access-token [REDACTED] --gdrive-refresh-token [REDACTED]")
            else:
                logger.warning("DETAILED_DEBUG: No Google Drive credentials to add to command line arguments")
            
            logger.info(f"Executing command: {cmd[0]} {cmd[1] if len(cmd) > 1 and not cmd[1].startswith('--') else ''} [with credential args]")
            
            # Start backup process with detailed output capture
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                cwd=str(BASE_DIR),
                bufsize=1,  # Line buffered
                universal_newlines=True
            )
            
            # Stream output in real-time
            output_lines = []
            session_id = None
            
            logger.info("=== BACKUP SCRIPT OUTPUT START ===")
            
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                
                line = line.rstrip('\n\r')
                output_lines.append(line)
                
                # Log every single line from the backup script
                logger.info(f"BACKUP> {line}")
                
                # Extract session ID
                if 'Session ID:' in line:
                    session_id = line.split('Session ID:')[1].strip()
                    logger.info(f"Detected Session ID: {session_id}")
                    # Add to database
                    session_data = {
                        'session_id': session_id,
                        'start_time': datetime.now().isoformat(),
                        'destinations': ','.join(destinations) if destinations else ''
                    }
                    self.db.add_backup_session(session_data)
                
                # Log progress indicators
                if any(indicator in line.lower() for indicator in [
                    'backing up', 'uploading', 'encrypting', 'compressing', 
                    'validating', 'starting', 'completed', 'success', 'failed', 'error'
                ]):
                    logger.info(f"PROGRESS> {line}")
            
            # Wait for completion
            return_code = process.wait()
            logger.info("=== BACKUP SCRIPT OUTPUT END ===")
            logger.info(f"Backup script exit code: {return_code}")
            
            result = {
                'success': return_code == 0,
                'session_id': session_id,
                'output': '\n'.join(output_lines),
                'return_code': return_code
            }
            
            # Update database
            if session_id:
                updates = {
                    'end_time': datetime.now().isoformat(),
                    'status': 'success' if return_code == 0 else 'failed'
                }
                self.db.update_backup_session(session_id, updates)
                logger.info(f"Updated session {session_id} with status: {'success' if return_code == 0 else 'failed'}")
            
            return result
            
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'session_id': None
            }
    
    def validate_backup(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Validate a backup"""
        try:
            script_path = SCRIPTS_DIR / 'validate-backup.sh'
            
            cmd = [str(script_path)]
            if session_id:
                session_path = SESSIONS_DIR / session_id
                cmd.append(str(session_path))
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(BASE_DIR)
            )
            
            return {
                'success': result.returncode == 0,
                'output': result.stdout,
                'error': result.stderr,
                'return_code': result.returncode
            }
            
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_storage_usage(self) -> Dict[str, Any]:
        """Get storage usage for all configured destinations"""
        usage = {}
        
        destinations = self.config.get('DR_BACKUP_DESTINATIONS', '').split(',')
        
        for dest in destinations:
            dest = dest.strip()
            
            if dest == 'aws':
                usage['aws'] = self._get_aws_storage_usage()
            elif dest == 'gdrive':
                usage['gdrive'] = self._get_gdrive_storage_usage()
        
        return usage
    
    def _get_aws_storage_usage(self) -> Dict[str, Any]:
        """Get AWS S3 storage usage"""
        try:
            bucket = self.config.get('DR_CLOUD_BUCKET', '').replace('s3://', '')
            if not bucket:
                return {'error': 'AWS S3 bucket not configured'}
            
            # Use AWS CLI to get bucket size
            result = subprocess.run(
                ['aws', 's3api', 'list-objects-v2', '--bucket', bucket, '--query', 'sum(Contents[].Size)'],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                used_bytes = int(result.stdout.strip() or '0')
                return {
                    'provider': 'AWS S3',
                    'bucket': bucket,
                    'used': used_bytes,
                    'used_gb': round(used_bytes / 1024**3, 2)
                }
            else:
                return {'error': f'AWS CLI error: {result.stderr}'}
                
        except Exception as e:
            return {'error': str(e)}
    
    def _get_gdrive_storage_usage(self) -> Dict[str, Any]:
        """Get Google Drive storage usage"""
        try:
            if not GoogleDriveBackup:
                return {'error': 'Google Drive integration not available'}
            
            gdrive = GoogleDriveBackup(self.config.config)
            if gdrive.authenticate():
                return gdrive.get_storage_usage()
            else:
                return {'error': 'Failed to authenticate with Google Drive'}
                
        except Exception as e:
            return {'error': str(e)}
    
    def restore_backup(self, session_id: str, restore_type: str = 'full', 
                      target_location: str = 'local', restore_path: str = '/tmp/odoo-restore') -> Dict[str, Any]:
        """Restore from backup"""
        try:
            import uuid
            restore_id = str(uuid.uuid4())
            
            # Get backup session details
            session = self.db.get_backup_session(session_id)
            if not session:
                return {'success': False, 'error': 'Backup session not found'}
            
            # Track restore session
            self.restore_sessions[restore_id] = {
                'id': restore_id,
                'session_id': session_id,
                'restore_type': restore_type,
                'target_location': target_location,
                'restore_path': restore_path,
                'status': 'starting',
                'start_time': datetime.now().isoformat(),
                'progress': 0
            }
            
            # Start restore in background thread
            def run_restore():
                try:
                    self.restore_sessions[restore_id]['status'] = 'running'
                    
                    if target_location == 'gdrive':
                        result = self._restore_from_gdrive(session_id, restore_type, restore_path)
                    else:
                        result = self._restore_from_local(session_id, restore_type, restore_path)
                    
                    self.restore_sessions[restore_id].update({
                        'status': 'completed' if result['success'] else 'failed',
                        'end_time': datetime.now().isoformat(),
                        'progress': 100,
                        'result': result
                    })
                    
                except Exception as e:
                    logger.error(f"Restore thread error: {e}")
                    self.restore_sessions[restore_id].update({
                        'status': 'failed',
                        'end_time': datetime.now().isoformat(),
                        'error': str(e),
                        'progress': 0
                    })
            
            thread = threading.Thread(target=run_restore)
            thread.daemon = True
            thread.start()
            
            return {
                'success': True,
                'restore_id': restore_id,
                'message': 'Restore started successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to start restore: {e}")
            return {'success': False, 'error': str(e)}
    
    def _restore_from_local(self, session_id: str, restore_type: str, restore_path: str) -> Dict[str, Any]:
        """Restore from local backup"""
        try:
            # Find the backup directory for this session
            backup_dirs = [
                Path('/app/backups'),
                Path('/opt/backups'),
                BASE_DIR / 'backups',
                Path('/tmp/backups')
            ]
            
            backup_dir = None
            for bd in backup_dirs:
                if bd.exists():
                    session_dir = bd / session_id
                    if session_dir.exists():
                        backup_dir = session_dir
                        break
            
            if not backup_dir:
                return {'success': False, 'error': f'Backup directory for session {session_id} not found'}
            
            # Run restore script
            script_path = SCRIPTS_DIR / 'disaster-recovery.sh'
            if not script_path.exists():
                return {'success': False, 'error': 'Restore script not found'}
            
            env = os.environ.copy()
            env.update({
                'DR_RESTORE_PATH': restore_path,
                'DR_RESTORE_TYPE': restore_type,
                'DR_BACKUP_DIR': str(backup_dir)
            })
            
            logger.info(f"Starting local restore from {backup_dir} to {restore_path}")
            
            cmd = [str(script_path), 'restore', str(backup_dir), restore_path]
            
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            return {
                'success': result.returncode == 0,
                'output': result.stdout,
                'error': result.stderr,
                'return_code': result.returncode
            }
            
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Restore operation timed out'}
        except Exception as e:
            logger.error(f"Local restore failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _restore_from_gdrive(self, session_id: str, restore_type: str, restore_path: str) -> Dict[str, Any]:
        """Restore from Google Drive backup"""
        try:
            if not GoogleDriveBackup:
                return {'success': False, 'error': 'Google Drive integration not available'}
            
            gdrive = GoogleDriveBackup(self.config.config)
            if not gdrive.authenticate():
                return {'success': False, 'error': 'Failed to authenticate with Google Drive'}
            
            # Download backup from Google Drive
            download_path = f'/tmp/{session_id}_download'
            os.makedirs(download_path, exist_ok=True)
            
            logger.info(f"Downloading backup {session_id} from Google Drive")
            
            # Find and download backup files
            backup_files = gdrive.list_backups(session_id)
            if not backup_files:
                return {'success': False, 'error': f'No backup files found for session {session_id}'}
            
            for file_info in backup_files:
                local_path = os.path.join(download_path, file_info['name'])
                success = gdrive.download_file(file_info['id'], local_path)
                if not success:
                    return {'success': False, 'error': f'Failed to download {file_info["name"]}'}
            
            # Run local restore on downloaded files
            return self._restore_from_local(session_id, restore_type, restore_path)
            
        except Exception as e:
            logger.error(f"Google Drive restore failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def list_local_backups(self) -> List[Dict[str, Any]]:
        """List available local backups"""
        try:
            backup_dirs = [
                Path('/app/backups'),
                Path('/opt/backups'),
                BASE_DIR / 'backups',
                Path('/tmp/backups')
            ]
            
            backups = []
            for backup_dir in backup_dirs:
                if backup_dir.exists():
                    for session_dir in backup_dir.iterdir():
                        if session_dir.is_dir():
                            manifest_file = session_dir / 'manifest.json'
                            if manifest_file.exists():
                                try:
                                    with open(manifest_file, 'r') as f:
                                        manifest = json.loads(f.read())
                                    
                                    backup_info = {
                                        'session_id': session_dir.name,
                                        'location': 'local',
                                        'path': str(session_dir),
                                        'size': self._get_directory_size(session_dir),
                                        'created': manifest.get('start_time'),
                                        'databases': manifest.get('databases', []),
                                        'manifest': manifest
                                    }
                                    backups.append(backup_info)
                                    
                                except (json.JSONDecodeError, IOError) as e:
                                    logger.warning(f"Failed to read manifest for {session_dir}: {e}")
            
            # Sort by creation time, newest first
            backups.sort(key=lambda x: x.get('created', ''), reverse=True)
            return backups
            
        except Exception as e:
            logger.error(f"Failed to list local backups: {e}")
            return []
    
    def list_gdrive_backups(self) -> List[Dict[str, Any]]:
        """List available Google Drive backups"""
        try:
            if not GoogleDriveBackup:
                return []
            
            gdrive = GoogleDriveBackup(self.config.config)
            if not gdrive.authenticate():
                return []
            
            return gdrive.list_backups()
            
        except Exception as e:
            logger.error(f"Failed to list Google Drive backups: {e}")
            return []
    
    def get_restore_status(self, restore_id: str) -> Dict[str, Any]:
        """Get restore operation status"""
        return self.restore_sessions.get(restore_id, {'error': 'Restore session not found'})
    
    def _get_directory_size(self, path: Path) -> int:
        """Get total size of directory"""
        try:
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    if os.path.exists(filepath):
                        total_size += os.path.getsize(filepath)
            return total_size
        except Exception:
            return 0

backup_manager = BackupManager()

# Routes

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        admin_username = config.get('ADMIN_USERNAME')
        admin_password_hash = config.get('ADMIN_PASSWORD_HASH')
        
        if username == admin_username and check_password_hash(admin_password_hash, password):
            user = User(username)
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Logout"""
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    """Main dashboard"""
    # Get recent backup sessions
    sessions = db.get_backup_sessions(10)
    
    # Get storage usage
    storage_usage = backup_manager.get_storage_usage()
    
    # Get system status
    system_status = get_system_status()
    
    return render_template('dashboard.html', 
                         sessions=sessions,
                         storage_usage=storage_usage,
                         system_status=system_status)

@app.route('/backups')
@login_required
def backups():
    """Backup history page"""
    sessions = db.get_backup_sessions(100)
    return render_template('backups.html', sessions=sessions)

@app.route('/backups/<session_id>')
@login_required
def backup_detail(session_id):
    """Backup detail page"""
    session_data = db.get_backup_session(session_id)
    if not session_data:
        flash('Backup session not found')
        return redirect(url_for('backups'))
    
    return render_template('backup_detail.html', session=session_data)

@app.route('/api/backup/start', methods=['POST'])
@login_required
def api_start_backup():
    """API endpoint to start a backup"""
    data = request.get_json() or {}
    destinations = data.get('destinations', ['aws'])
    
    # Start backup in background
    def run_backup_async():
        backup_manager.run_backup(destinations)
    
    thread = threading.Thread(target=run_backup_async)
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'message': 'Backup started'})

@app.route('/api/backup/validate', methods=['POST'])
@login_required
def api_validate_backup():
    """API endpoint to validate a backup"""
    data = request.get_json() or {}
    session_id = data.get('session_id')
    
    result = backup_manager.validate_backup(session_id)
    return jsonify(result)

@app.route('/api/storage/usage')
@login_required
def api_storage_usage():
    """API endpoint to get storage usage"""
    usage = backup_manager.get_storage_usage()
    return jsonify(usage)

@app.route('/api/system/status')
@login_required
def api_system_status():
    """API endpoint to get system status"""
    status = get_system_status()
    return jsonify(status)

@app.route('/api/logs/live')
@login_required
def api_live_logs():
    """API endpoint to get live backup logs"""
    try:
        log_file = LOGS_DIR / 'backup-panel.log'
        if log_file.exists():
            # Read last 100 lines
            with open(log_file, 'r') as f:
                lines = f.readlines()
                recent_lines = lines[-100:] if len(lines) > 100 else lines
                
            # Filter for backup-related logs
            backup_logs = []
            for line in recent_lines:
                if any(keyword in line for keyword in ['BACKUP>', 'PROGRESS>', 'Starting backup', 'Session ID']):
                    backup_logs.append(line.strip())
            
            return jsonify({
                'success': True,
                'logs': backup_logs[-50:],  # Last 50 backup-related lines
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Log file not found',
                'logs': []
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'logs': []
        })

@app.route('/settings')
@login_required
def settings():
    """Settings page"""
    return render_template('settings.html', config=config.config)

@app.route('/demo/cloud-connections')
def demo_cloud_connections():
    """Demo page for cloud connections UI"""
    return render_template('cloud_connections_demo.html')

@app.route('/api/settings', methods=['POST'])
@login_required
def api_update_settings():
    """API endpoint to update settings"""
    data = request.get_json() or {}
    
    # Update configuration
    for key, value in data.items():
        if key.startswith('DR_') or key in ['ADMIN_USERNAME', 'ADMIN_PASSWORD_HASH']:
            config.set(key, value)
    
    # Save configuration
    config.save_config()
    
    return jsonify({'success': True, 'message': 'Settings updated'})

def get_system_status() -> Dict[str, Any]:
    """Get overall system status"""
    try:
        # Check if Docker services are running
        docker_compose_file = str(BASE_DIR.parent / 'docker-compose.yml')
        
        # Try different docker-compose commands
        docker_cmd = None
        for cmd in ['docker-compose', 'docker compose']:
            try:
                result = subprocess.run(
                    cmd.split() + ['-f', docker_compose_file, 'ps'],
                    capture_output=True,
                    text=True,
                    cwd=str(BASE_DIR.parent),
                    timeout=10
                )
                docker_cmd = cmd
                break
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
        
        if not docker_cmd:
            # Fallback: assume services are running
            services_running = True
        else:
            services_running = 'Up' in result.stdout
        
        # Check latest backup
        sessions = db.get_backup_sessions(1)
        latest_backup = sessions[0] if sessions else None
        
        backup_status = 'unknown'
        if latest_backup:
            backup_age_hours = (datetime.now() - datetime.fromisoformat(latest_backup['start_time'])).total_seconds() / 3600
            if backup_age_hours < 24:
                backup_status = 'recent'
            elif backup_age_hours < 48:
                backup_status = 'warning'
            else:
                backup_status = 'old'
        
        return {
            'services_running': services_running,
            'backup_status': backup_status,
            'latest_backup': latest_backup,
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get system status: {e}")
        return {
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }

# ============= Cloud Connection Routes =============

@app.route('/api/connect/google-drive/start')
@login_required
def google_drive_oauth_start():
    """Start Google Drive OAuth flow"""
    try:
        # Get client credentials from database or config
        connection = db.get_cloud_connection('google_drive')
        if not connection or not connection.get('credentials', {}).get('client_id'):
            return jsonify({'error': 'Google Drive client credentials not configured'}), 400
        
        # Generate state parameter for security
        state = secrets.token_urlsafe(32)
        session['oauth_state'] = state
        
        client_id = connection['credentials']['client_id']
        
        # Google OAuth2 configuration
        google_oauth_url = "https://accounts.google.com/o/oauth2/v2/auth"
        params = {
            'client_id': client_id,
            'redirect_uri': url_for('google_drive_oauth_callback', _external=True),
            'scope': 'https://www.googleapis.com/auth/drive.file',
            'response_type': 'code',
            'state': state,
            'access_type': 'offline',
            'prompt': 'consent'
        }
        
        auth_url = f"{google_oauth_url}?{urlencode(params)}"
        return jsonify({'auth_url': auth_url})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/oauth/google-drive/callback')
def google_drive_oauth_callback():
    """Handle Google Drive OAuth callback"""
    try:
        # Verify state parameter
        if request.args.get('state') != session.get('oauth_state'):
            flash('Invalid OAuth state. Please try again.', 'error')
            return redirect(url_for('settings'))
        
        # Exchange code for token
        code = request.args.get('code')
        if not code:
            flash('OAuth authorization failed.', 'error')
            return redirect(url_for('settings'))
        
        # Get stored credentials
        connection = db.get_cloud_connection('google_drive')
        if not connection:
            flash('Google Drive credentials not found.', 'error')
            return redirect(url_for('settings'))
        
        # Exchange code for access token
        logger.info("DETAILED_DEBUG: === OAuth callback processing ===")
        logger.info(f"DETAILED_DEBUG: Received code: {code}")
        logger.info(f"DETAILED_DEBUG: State verification passed")
        logger.info(f"DETAILED_DEBUG: Connection credentials keys: {list(connection['credentials'].keys())}")
        
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            'client_id': connection['credentials']['client_id'],
            'client_secret': connection['credentials']['client_secret'],
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': url_for('google_drive_oauth_callback', _external=True)
        }
        
        logger.info(f"DETAILED_DEBUG: Token exchange request data: {dict(token_data)}")
        logger.info(f"DETAILED_DEBUG: Making POST request to: {token_url}")
        
        token_response = requests.post(token_url, data=token_data)
        logger.info(f"DETAILED_DEBUG: Token response status: {token_response.status_code}")
        logger.info(f"DETAILED_DEBUG: Token response headers: {dict(token_response.headers)}")
        
        token_response.raise_for_status()
        token_info = token_response.json()
        logger.info(f"DETAILED_DEBUG: Token info received: {list(token_info.keys())}")
        logger.info(f"DETAILED_DEBUG: Access token length: {len(token_info.get('access_token', ''))}")
        logger.info(f"DETAILED_DEBUG: Refresh token length: {len(token_info.get('refresh_token', ''))}")
        
        # Update credentials with tokens
        credentials = connection['credentials'].copy()
        logger.info(f"DETAILED_DEBUG: Original credentials before update: {list(credentials.keys())}")
        
        credentials.update({
            'access_token': token_info['access_token'],
            'refresh_token': token_info.get('refresh_token'),
            'token_type': token_info.get('token_type', 'Bearer'),
            'expires_in': token_info.get('expires_in')
        })
        
        logger.info(f"DETAILED_DEBUG: Updated credentials after merge: {list(credentials.keys())}")
        logger.info(f"DETAILED_DEBUG: Final credential lengths:")
        logger.info(f"DETAILED_DEBUG:   client_id: {len(credentials.get('client_id', ''))}")
        logger.info(f"DETAILED_DEBUG:   client_secret: {len(credentials.get('client_secret', ''))}")
        logger.info(f"DETAILED_DEBUG:   access_token: {len(credentials.get('access_token', ''))}")
        logger.info(f"DETAILED_DEBUG:   refresh_token: {len(credentials.get('refresh_token', ''))}")
        
        # Save updated credentials
        db.save_cloud_connection('google_drive', credentials, {'status': 'connected'})
        
        # Sync credentials to config file for backup script
        config.sync_cloud_credentials()
        db.update_connection_test('google_drive', 'success')
        
        flash('Google Drive connected successfully!', 'success')
        return redirect(url_for('settings'))
        
    except Exception as e:
        flash(f'Google Drive connection failed: {str(e)}', 'error')
        return redirect(url_for('settings'))

@app.route('/api/connect/aws-s3', methods=['POST'])
@login_required
def connect_aws_s3():
    """Connect to AWS S3"""
    try:
        data = request.get_json() or {}
        
        # Validate required fields
        required_fields = ['access_key_id', 'secret_access_key', 'region', 'bucket_name']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Test AWS S3 connection
        try:
            import boto3
            from botocore.exceptions import ClientError
            
            s3_client = boto3.client(
                's3',
                aws_access_key_id=data['access_key_id'],
                aws_secret_access_key=data['secret_access_key'],
                region_name=data['region']
            )
            
            # Test connection by checking bucket
            s3_client.head_bucket(Bucket=data['bucket_name'])
            
        except ImportError:
            return jsonify({'error': 'boto3 library not installed'}), 500
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchBucket':
                return jsonify({'error': 'Bucket not found or access denied'}), 400
            elif error_code == 'InvalidAccessKeyId':
                return jsonify({'error': 'Invalid access key ID'}), 400
            elif error_code == 'SignatureDoesNotMatch':
                return jsonify({'error': 'Invalid secret access key'}), 400
            else:
                return jsonify({'error': f'AWS error: {error_code}'}), 400
        
        # Save connection
        credentials = {
            'access_key_id': data['access_key_id'],
            'secret_access_key': data['secret_access_key'],
            'region': data['region'],
            'bucket_name': data['bucket_name']
        }
        
        metadata = {
            'bucket_name': data['bucket_name'],
            'region': data['region']
        }
        
        db.save_cloud_connection('aws_s3', credentials, metadata)
        db.update_connection_test('aws_s3', 'success')
        
        return jsonify({'message': 'AWS S3 connected successfully'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/connect/google-drive', methods=['POST'])
@login_required
def connect_google_drive_manual():
    """Connect to Google Drive with manual credentials"""
    try:
        data = request.get_json() or {}
        
        # Validate required fields
        required_fields = ['client_id', 'client_secret']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Save partial connection (will be completed via OAuth)
        credentials = {
            'client_id': data['client_id'],
            'client_secret': data['client_secret']
        }
        
        db.save_cloud_connection('google_drive', credentials, {'status': 'pending_oauth'})
        
        # Sync partial credentials to config file
        config.sync_cloud_credentials()
        
        return jsonify({'message': 'Credentials saved. Use "Connect" button to complete OAuth flow.'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug-credentials')
@login_required
def debug_credentials():
    """Debug endpoint to check credentials"""
    try:
        gdrive_conn = db.get_cloud_connection('google_drive')
        if gdrive_conn:
            # Remove sensitive data for debug output
            debug_info = {
                'connection_exists': True,
                'credentials_keys': list(gdrive_conn.get('credentials', {}).keys()) if gdrive_conn.get('credentials') else [],
                'has_client_id': bool(gdrive_conn.get('credentials', {}).get('client_id')),
                'has_client_secret': bool(gdrive_conn.get('credentials', {}).get('client_secret')),
                'has_access_token': bool(gdrive_conn.get('credentials', {}).get('access_token')),
                'has_refresh_token': bool(gdrive_conn.get('credentials', {}).get('refresh_token')),
                'config_values': {
                    'GDRIVE_CLIENT_ID': bool(config.get('GDRIVE_CLIENT_ID')),
                    'GDRIVE_CLIENT_SECRET': bool(config.get('GDRIVE_CLIENT_SECRET')),
                    'GDRIVE_ACCESS_TOKEN': bool(config.get('GDRIVE_ACCESS_TOKEN')),
                    'GDRIVE_REFRESH_TOKEN': bool(config.get('GDRIVE_REFRESH_TOKEN'))
                }
            }
            return jsonify(debug_info)
        else:
            return jsonify({'connection_exists': False})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/sync-credentials', methods=['POST'])
@login_required
def sync_credentials():
    """Sync cloud credentials from database to config file"""
    try:
        success = config.sync_cloud_credentials()
        if success:
            return jsonify({'message': 'Credentials synced successfully'})
        else:
            return jsonify({'error': 'Failed to sync credentials'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/restore', methods=['POST'])
@login_required
def api_restore_backup():
    """API endpoint to restore from backup"""
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        restore_type = data.get('restore_type', 'full')  # full, selective, database_only
        target_location = data.get('target_location', 'local')  # local, gdrive
        restore_path = data.get('restore_path', '/tmp/odoo-restore')
        
        if not session_id:
            return jsonify({'error': 'Session ID is required'}), 400
        
        # Get backup session details
        session = db.get_backup_session(session_id)
        if not session:
            return jsonify({'error': 'Backup session not found'}), 404
        
        # Start restore process
        restore_result = backup_manager.restore_backup(
            session_id=session_id,
            restore_type=restore_type,
            target_location=target_location,
            restore_path=restore_path
        )
        
        return jsonify(restore_result)
        
    except Exception as e:
        logger.error(f"Restore API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/restore/list-backups')
@login_required
def api_list_restore_backups():
    """API endpoint to list available backups for restore"""
    try:
        source = request.args.get('source', 'local')  # local, gdrive
        
        if source == 'local':
            backups = backup_manager.list_local_backups()
        elif source == 'gdrive':
            backups = backup_manager.list_gdrive_backups()
        else:
            return jsonify({'error': 'Invalid source specified'}), 400
        
        return jsonify({'backups': backups})
        
    except Exception as e:
        logger.error(f"List backups API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/restore/status/<restore_id>')
@login_required
def api_restore_status(restore_id):
    """API endpoint to get restore status"""
    try:
        status = backup_manager.get_restore_status(restore_id)
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"Restore status API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/connections')
@login_required
def get_connections():
    """Get all cloud connections status"""
    try:
        connections = db.get_all_cloud_connections()
        
        # Add status information without exposing credentials
        for connection in connections:
            # Remove sensitive data from response
            connection.pop('credentials', None)
        
        return jsonify({'connections': connections})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/connections/<provider>/test')
@login_required
def test_connection(provider):
    """Test a cloud connection"""
    try:
        connection = db.get_cloud_connection(provider)
        if not connection:
            return jsonify({'error': 'Connection not found'}), 404
        
        if provider == 'aws_s3':
            # Test AWS S3 connection
            try:
                import boto3
                from botocore.exceptions import ClientError
                
                creds = connection['credentials']
                s3_client = boto3.client(
                    's3',
                    aws_access_key_id=creds['access_key_id'],
                    aws_secret_access_key=creds['secret_access_key'],
                    region_name=creds['region']
                )
                
                s3_client.head_bucket(Bucket=creds['bucket_name'])
                db.update_connection_test(provider, 'success')
                return jsonify({'status': 'success', 'message': 'Connection test successful'})
                
            except ImportError:
                return jsonify({'error': 'boto3 library not installed'}), 500
            except ClientError as e:
                error_msg = f"AWS error: {e.response['Error']['Code']}"
                db.update_connection_test(provider, 'failed')
                return jsonify({'error': error_msg}), 400
            
        elif provider == 'google_drive':
            # Test Google Drive connection
            creds = connection['credentials']
            if not creds.get('access_token'):
                return jsonify({'error': 'OAuth not completed. Please reconnect.'}), 400
                
            # Test Google Drive API access
            try:
                headers = {'Authorization': f"Bearer {creds['access_token']}"}
                response = requests.get('https://www.googleapis.com/drive/v3/about?fields=user', headers=headers)
                response.raise_for_status()
                
                db.update_connection_test(provider, 'success')
                return jsonify({'status': 'success', 'message': 'Connection test successful'})
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    return jsonify({'error': 'Token expired. Please reconnect.'}), 400
                else:
                    return jsonify({'error': f'Google Drive API error: {e.response.status_code}'}), 400
        
        else:
            return jsonify({'error': 'Unknown provider'}), 400
            
    except Exception as e:
        db.update_connection_test(provider, 'failed')
        return jsonify({'error': str(e)}), 500

@app.route('/api/connections/<provider>/disconnect', methods=['POST'])
@login_required
def disconnect_provider(provider):
    """Disconnect a cloud provider"""
    try:
        with sqlite3.connect(db.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM cloud_connections WHERE provider = ?', (provider,))
            conn.commit()
        
        return jsonify({'message': f'{provider} disconnected successfully'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Create necessary directories
    os.makedirs(BASE_DIR / 'backup_panel' / 'static', exist_ok=True)
    os.makedirs(BASE_DIR / 'backup_panel' / 'templates', exist_ok=True)
    
    # Run development server
    app.run(host='0.0.0.0', port=5000, debug=True)
