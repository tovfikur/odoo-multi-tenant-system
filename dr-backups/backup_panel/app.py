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
import re
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
    
    
    
    def _check_manifest_integrity(self, session_path: Path) -> Dict[str, Any]:
        """Check if backup manifest is valid before running full validation"""
        manifest_file = session_path / 'backup-manifest.json'
        
        if not manifest_file.exists():
            # Try alternative manifest file names
            alternative_names = ['manifest.json', 'backup_manifest.json', 'session_manifest.json']
            for alt_name in alternative_names:
                alt_file = session_path / alt_name
                if alt_file.exists():
                    manifest_file = alt_file
                    logger.info(f"Found alternative manifest file: {alt_file}")
                    break
            else:
                return {
                    'valid': False, 
                    'error': 'Manifest file not found',
                    'tried_files': [str(session_path / name) for name in ['backup-manifest.json'] + alternative_names],
                    'session_contents': [f.name for f in session_path.iterdir()] if session_path.exists() else []
                }
        
        try:
            file_size = manifest_file.stat().st_size
            if file_size == 0:
                # Try to regenerate manifest if possible
                regen_result = self._try_regenerate_manifest(session_path)
                if regen_result['success']:
                    logger.info(f"Successfully regenerated manifest for {session_path}")
                    return {'valid': True, 'regenerated': True, 'manifest_file': str(manifest_file)}
                else:
                    return {
                        'valid': False, 
                        'error': 'Manifest file is empty and cannot be regenerated',
                        'regeneration_attempt': regen_result,
                        'manifest_file': str(manifest_file),
                        'file_size': file_size
                    }
        except OSError as e:
            return {'valid': False, 'error': f'Cannot access manifest file: {str(e)}'}
        
        try:
            with open(manifest_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    return {
                        'valid': False, 
                        'error': 'Manifest file has no content',
                        'file_size': file_size,
                        'manifest_file': str(manifest_file)
                    }
                
                # Try to parse JSON
                import json
                manifest_data = json.loads(content)
                
                # Validate manifest structure
                required_fields = ['start_time', 'session_id']
                missing_fields = [field for field in required_fields if field not in manifest_data]
                
                if missing_fields:
                    return {
                        'valid': False,
                        'error': f'Manifest missing required fields: {missing_fields}',
                        'content_preview': content[:200],
                        'manifest_data': manifest_data
                    }
                
                return {
                    'valid': True, 
                    'manifest_file': str(manifest_file),
                    'manifest_data': manifest_data,
                    'file_size': file_size
                }
                
        except json.JSONDecodeError as e:
            return {
                'valid': False, 
                'error': f'Invalid JSON in manifest: {str(e)}', 
                'content_preview': content[:200] if 'content' in locals() else 'Cannot read content',
                'manifest_file': str(manifest_file),
                'file_size': file_size
            }
        except Exception as e:
            return {
                'valid': False, 
                'error': f'Cannot read manifest: {str(e)}',
                'manifest_file': str(manifest_file)
            }
    
    def _try_regenerate_manifest(self, session_path: Path) -> Dict[str, Any]:
        """
        Try to regenerate a backup manifest from available session data
        
        Args:
            session_path: Path to the backup session directory
            
        Returns:
            Dict with success status and details
        """
        try:
            session_id = session_path.name
            
            # Extract timestamp from session ID
            import re
            import datetime
            
            # Pattern: backup_YYYYMMDD_HHMMSS_XXXXX
            pattern = r'backup_(\d{8})_(\d{6})_(\d+)'
            match = re.match(pattern, session_id)
            
            if not match:
                return {
                    'success': False,
                    'error': f'Cannot parse session ID format: {session_id}'
                }
            
            date_str, time_str, sequence = match.groups()
            
            # Reconstruct datetime
            start_time = datetime.datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
            
            # Scan session directory for files
            databases = []
            filestore_files = []
            config_files = []
            
            if session_path.exists():
                for item in session_path.rglob('*'):
                    if item.is_file():
                        rel_path = item.relative_to(session_path)
                        
                        if '.sql' in item.name or 'database' in str(rel_path).lower():
                            databases.append({
                                'name': item.name,
                                'path': str(rel_path),
                                'size': item.stat().st_size,
                                'encrypted': '.enc' in item.name
                            })
                        elif 'filestore' in str(rel_path).lower():
                            filestore_files.append({
                                'name': item.name,
                                'path': str(rel_path),
                                'size': item.stat().st_size
                            })
                        elif 'config' in str(rel_path).lower():
                            config_files.append({
                                'name': item.name,
                                'path': str(rel_path),
                                'size': item.stat().st_size
                            })
            
            # Create manifest data
            manifest_data = {
                'session_id': session_id,
                'start_time': start_time.isoformat(),
                'end_time': start_time.isoformat(),  # Approximation
                'status': 'completed',
                'backup_type': 'full',
                'databases': databases,
                'filestore': filestore_files,
                'configs': config_files,
                'total_files': len(databases) + len(filestore_files) + len(config_files),
                'total_size': sum(f['size'] for f in databases + filestore_files + config_files),
                'regenerated': True,
                'regenerated_at': datetime.datetime.now().isoformat(),
                'version': '2.0'
            }
            
            # Write manifest file
            manifest_file = session_path / 'backup-manifest.json'
            with open(manifest_file, 'w', encoding='utf-8') as f:
                json.dump(manifest_data, f, indent=2)
            
            logger.info(f"Regenerated manifest for {session_id} with {manifest_data['total_files']} files")
            
            return {
                'success': True,
                'manifest_file': str(manifest_file),
                'manifest_data': manifest_data
            }
            
        except Exception as e:
            logger.error(f"Failed to regenerate manifest for {session_path}: {e}")
            return {
                'success': False,
                'error': f'Regeneration failed: {str(e)}',
                'session_path': str(session_path)
            }
    
    def _normalize_session_id(self, session_id: str) -> str:
        """
        Normalize session ID to standard format
        
        Args:
            session_id: Raw session ID (could be partial or full)
            
        Returns:
            Normalized session ID in format: backup_YYYYMMDD_HHMMSS_XXXXX
        """
        # If already has backup_ prefix, return as-is
        if session_id.startswith('backup_'):
            return session_id
            
        # If starts with /, extract just the session name
        if session_id.startswith('/'):
            session_id = Path(session_id).name
            
        # If it's just a partial ID like "20250803_204026_52", add prefix
        if not session_id.startswith('backup_'):
            session_id = f"backup_{session_id}"
            
        return session_id
        
    
    def validate_backup(self, session_id: Optional[str] = None, source: str = 'auto', force_validation: bool = False) -> Dict[str, Any]:
        """
        Validate a backup session from local storage or Google Drive
        
        Args:
            session_id: Optional session ID. If not provided, validates the latest backup.
                    Can be full session name (backup_20240104_143022_12345) or partial ID
            source: Source to validate from ('local', 'gdrive', or 'auto')
            force_validation: Skip manifest validation and proceed with backup validation
        
        Returns:
            Dict containing validation results with structured information
        """
        # CRITICAL FIX: Import subprocess at the top of the function
        import subprocess
        import json
        import os
        from pathlib import Path
        
        try:
            # Ensure configuration is up to date
            self.config.save_config()
            self.config.sync_cloud_credentials()
            
            # Get script path and verify it exists
            script_path = SCRIPTS_DIR / 'validate-backup.sh'
            if not script_path.exists():
                logger.error(f"Validation script not found: {script_path}")
                return {
                    'success': False,
                    'error': f"Validation script not found: {script_path}",
                    'details': {
                        'script_path': str(script_path),
                        'scripts_dir_exists': SCRIPTS_DIR.exists(),
                        'scripts_dir_contents': [str(f) for f in SCRIPTS_DIR.iterdir()] if SCRIPTS_DIR.exists() else []
                    }
                }
            
            # Make script executable (ignore if read-only filesystem)
            try:
                os.chmod(script_path, 0o755)
            except OSError as e:
                logger.warning(f"Could not make script executable: {e}")
            
            # Prepare environment variables
            env = os.environ.copy()
            
            # CRITICAL: Fix Docker/Windows path issues
            # Always use Docker-appropriate paths when running in container
            if env.get('DOCKER_CONTAINER') == '1' or os.path.exists('/app'):
                # Running in Docker container - use container paths
                dr_backup_dir = '/app/data'
                dr_session_dir = '/app/data/sessions'
                dr_logs_dir = '/app/data/logs'
                dr_encryption_key = '/app/data/encryption.key'
            else:
                # Running on host - use configured paths
                dr_backup_dir = self.config.get('DR_BACKUP_DIR', str(DATA_DIR))
                dr_session_dir = self.config.get('DR_SESSION_DIR', f'{dr_backup_dir}/sessions')
                dr_logs_dir = self.config.get('DR_LOGS_DIR', f'{dr_backup_dir}/logs')
                dr_encryption_key = self.config.get('DR_ENCRYPTION_KEY', f'{dr_backup_dir}/encryption.key')
            
            # Set Docker environment indicator
            env['DOCKER_CONTAINER'] = '1'
            
            # Ensure critical environment variables are set with DOCKER-APPROPRIATE paths
            critical_vars = {
                'DR_BACKUP_DIR': dr_backup_dir,
                'DR_SESSION_DIR': dr_session_dir,
                'DR_LOGS_DIR': dr_logs_dir,
                'DR_ENCRYPTION_KEY': dr_encryption_key,
                'DR_DEBUG_MODE': self.config.get('DR_DEBUG_MODE', 'true'),
                'POSTGRES_HOST': self.config.get('POSTGRES_HOST', 'postgres'),
                'POSTGRES_PORT': self.config.get('POSTGRES_PORT', '5432'),
                'POSTGRES_USER': self.config.get('POSTGRES_USER', 'odoo_master'),
                'POSTGRES_PASSWORD': self.config.get('POSTGRES_PASSWORD', 'secure_password_123')
            }
            
            # Add all configuration values to environment (but override critical ones)
            for key, value in self.config.config.items():
                if key.startswith(('DR_', 'POSTGRES_', 'GDRIVE_', 'AWS_')):
                    env[key] = str(value)
            
            # Override with Docker-appropriate paths
            for key, value in critical_vars.items():
                env[key] = str(value)
            
            # Create necessary directories if they don't exist (ignore errors on read-only filesystem)
            directories_to_create = [
                Path(dr_backup_dir),
                Path(dr_session_dir),
                Path(dr_logs_dir)
            ]
            
            for dir_path in directories_to_create:
                try:
                    dir_path.mkdir(parents=True, exist_ok=True)
                    logger.debug(f"Ensured directory exists: {dir_path}")
                except (OSError, PermissionError) as e:
                    logger.warning(f"Could not create directory {dir_path}: {e}")
                    # Continue anyway - the script might work with existing directories
            
            # Normalize session ID
            session_to_validate = None
            if session_id:
                session_to_validate = self._normalize_session_id(session_id)
                logger.info(f"Validating specific session: {session_to_validate}")
            else:
                logger.info("Validating latest backup session")
            
            # **CRITICAL FIX**: Handle source determination with proper Google Drive support
            validation_source = source
            local_session_path = None
            downloaded_for_validation = False
            
            if session_to_validate:
                local_session_path = Path(dr_session_dir) / session_to_validate
                
                # **FIX**: Handle different source scenarios properly
                if source == 'gdrive':
                    logger.info(f"Explicitly requested Google Drive validation for {session_to_validate}")
                    # Force Google Drive validation - remove local copy if exists to prevent conflicts
                    if local_session_path.exists():
                        logger.info(f"Removing existing local copy to force Google Drive validation: {local_session_path}")
                        try:
                            import shutil
                            shutil.rmtree(local_session_path)
                            logger.info(f"Removed local copy: {local_session_path}")
                        except Exception as e:
                            logger.warning(f"Could not remove local copy: {e}")
                    
                    validation_source = 'gdrive'
                    
                elif source == 'auto':
                    # Check local first, then Google Drive
                    if local_session_path.exists():
                        validation_source = 'local'
                        logger.info(f"Found session locally: {local_session_path}")
                    else:
                        validation_source = 'gdrive'
                        logger.info(f"Session not found locally, will try Google Drive")
                        
                elif source == 'local':
                    if not local_session_path.exists():
                        return {
                            'success': False,
                            'error': f'Session {session_to_validate} not found locally and local validation was explicitly requested',
                            'details': {
                                'session_path': str(local_session_path),
                                'validation_source': 'local'
                            }
                        }
                    validation_source = 'local'
                    
                # **FIX**: Download from Google Drive if needed
                if validation_source == 'gdrive':
                    logger.info(f"Downloading session {session_to_validate} from Google Drive for validation")
                    download_result = self._download_backup_for_validation(session_to_validate, dr_session_dir)
                    if not download_result['success']:
                        return {
                            'success': False,
                            'error': f"Failed to download backup from Google Drive: {download_result['error']}",
                            'details': download_result,
                            'validation_source': 'gdrive'
                        }
                    logger.info(f"Successfully downloaded backup from Google Drive: {download_result['session_path']}")
                    local_session_path = Path(download_result['session_path'])
                    downloaded_for_validation = True
                    
                    # Mark this as a temporary download for validation
                    env['GDRIVE_DOWNLOADED_FOR_VALIDATION'] = '1'
                    env['GDRIVE_VALIDATION_MODE'] = '1'
                
                # **FIX**: Only validate manifest for local sessions or after successful download
                if local_session_path and local_session_path.exists() and not force_validation:
                    manifest_check = self._check_manifest_integrity(local_session_path)
                    if not manifest_check['valid']:
                        # If regeneration was attempted but failed, offer alternatives
                        if 'regeneration_attempt' in manifest_check:
                            return {
                                'success': False,
                                'error': f"Manifest validation failed: {manifest_check['error']}",
                                'details': {
                                    'manifest_file': manifest_check.get('manifest_file', 'unknown'),
                                    'fix_suggestion': 'Try bypassing manifest validation with force_validation=true, or delete this backup session and run a new backup',
                                    'session_path': str(local_session_path),
                                    'bypass_option': 'Add "force_validation": true to validation request to skip manifest check'
                                },
                                'manifest_check': manifest_check,
                                'validation_source': validation_source
                            }
                        else:
                            return {
                                'success': False,
                                'error': f"Manifest validation failed: {manifest_check['error']}",
                                'details': {
                                    'manifest_file': manifest_check.get('manifest_file', str(local_session_path / 'backup-manifest.json')),
                                    'fix_suggestion': 'Delete this backup session and run a new backup, or try force validation',
                                    'session_path': str(local_session_path),
                                    'bypass_option': 'Add "force_validation": true to validation request to skip manifest check'
                                },
                                'manifest_check': manifest_check,
                                'validation_source': validation_source
                            }
                    else:
                        # Manifest is valid or was regenerated
                        if manifest_check.get('regenerated'):
                            logger.info(f"Using regenerated manifest for validation of {local_session_path}")
                        else:
                            logger.info(f"Manifest validation passed for {local_session_path}")
            
            # **FIX**: Ensure encryption key exists for validation
            encryption_key_path = Path(dr_encryption_key)
            if not encryption_key_path.exists():
                logger.warning(f"Encryption key not found at {encryption_key_path}, creating temporary key for validation")
                try:
                    encryption_key_path.parent.mkdir(parents=True, exist_ok=True)
                    # Create a temporary key for testing
                    subprocess.run(['openssl', 'rand', '-hex', '32'], 
                                stdout=open(str(encryption_key_path), 'w'), 
                                check=True)
                    os.chmod(str(encryption_key_path), 0o600)
                    logger.info(f"Created temporary encryption key: {encryption_key_path}")
                except Exception as e:
                    logger.error(f"Failed to create encryption key: {e}")
                    return {
                        'success': False,
                        'error': f'Encryption key not found and could not create temporary key: {e}',
                        'details': {'encryption_key_path': str(encryption_key_path)}
                    }
            
            # Build command with proper source indication
            cmd = [str(script_path)]
            if session_to_validate:
                cmd.append(session_to_validate)
            
            # **FIX**: Pass the determined validation source, not the original source
            # This ensures the script knows we've already handled Google Drive downloads
            if downloaded_for_validation:
                cmd.append('local')  # Tell script to validate locally since we downloaded it
            else:
                cmd.append(source)  # Use original source for local or auto scenarios
            
            # Add debug flag to get more detailed output
            if env.get('DR_DEBUG_MODE') == 'true':
                cmd.append('--debug')
            
            # Debug logging
            logger.info(f"Starting validation with command: {' '.join(cmd)}")
            logger.info(f"Working directory: {BASE_DIR}")
            logger.info(f"DR_SESSION_DIR: {env['DR_SESSION_DIR']}")
            logger.info(f"DR_BACKUP_DIR: {env['DR_BACKUP_DIR']}")
            logger.info(f"DR_LOGS_DIR: {env['DR_LOGS_DIR']}")
            logger.info(f"DR_ENCRYPTION_KEY: {env['DR_ENCRYPTION_KEY']}")
            logger.info(f"Original requested source: {source}")
            logger.info(f"Determined validation source: {validation_source}")
            logger.info(f"Downloaded for validation: {downloaded_for_validation}")
            
            # Check encryption key exists and is readable
            if os.path.exists(env['DR_ENCRYPTION_KEY']):
                try:
                    with open(env['DR_ENCRYPTION_KEY'], 'r') as f:
                        key_content = f.read().strip()
                    logger.info(f"Encryption key exists and is readable (length: {len(key_content)})")
                except Exception as e:
                    logger.error(f"Encryption key exists but cannot be read: {e}")
            else:
                logger.error(f"Encryption key does not exist: {env['DR_ENCRYPTION_KEY']}")
            
            # Check if session directory exists (for debugging)
            session_dir = Path(env['DR_SESSION_DIR'])
            if session_dir.exists():
                available_sessions = [d.name for d in session_dir.iterdir() if d.is_dir() and d.name.startswith('backup_')]
                logger.info(f"Available sessions ({len(available_sessions)}): {available_sessions[:3]}...")  # Show first 3
            else:
                logger.warning(f"Session directory does not exist: {session_dir}")
                # Try to create it
                try:
                    session_dir.mkdir(parents=True, exist_ok=True)
                    logger.info(f"Created session directory: {session_dir}")
                except (OSError, PermissionError) as e:
                    logger.error(f"Cannot create session directory: {e}")
            
            # **FIX**: Run validation with extended timeout and better error handling
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(BASE_DIR),
                    env=env,
                    timeout=1800  # 30 minutes timeout
                )
            except subprocess.TimeoutExpired:
                logger.error("Validation timed out after 30 minutes")
                return {
                    'success': False,
                    'error': 'Validation timed out after 30 minutes',
                    'timeout': True,
                    'validation_source': validation_source
                }
            except FileNotFoundError as e:
                logger.error(f"Command not found: {e}")
                return {
                    'success': False,
                    'error': f'Command not found: {e}. Ensure bash/shell is available.'
                }
            
            logger.info(f"Validation completed with exit code: {result.returncode}")
            
            # **FIX**: Log full output for debugging validation failures
            if result.stdout:
                logger.info("Validation stdout:")
                for line in result.stdout.split('\n'):
                    if line.strip():
                        logger.info(f"STDOUT: {line}")
            if result.stderr:
                logger.warning("Validation stderr:")
                for line in result.stderr.split('\n'):
                    if line.strip():
                        logger.warning(f"STDERR: {line}")
            
            # Parse validation results
            validation_result = {
                'success': result.returncode == 0,
                'output': result.stdout,
                'error': result.stderr,
                'return_code': result.returncode,
                'session_validated': session_to_validate,
                'validation_source': validation_source,
                'original_requested_source': source,  # Track what was originally requested
                'downloaded_for_validation': downloaded_for_validation,
                'command_executed': ' '.join(cmd),
                'environment': {
                    'dr_backup_dir': env['DR_BACKUP_DIR'],
                    'dr_session_dir': env['DR_SESSION_DIR'],
                    'dr_logs_dir': env['DR_LOGS_DIR'],
                    'dr_encryption_key': env['DR_ENCRYPTION_KEY']
                }
            }
            
            # Extract structured information from output
            if result.stdout:
                validation_result.update(self._parse_validation_output(result.stdout))
            
            # Try to load validation report JSON if available
            try:
                validation_id = self._extract_validation_id(result.stdout)
                if validation_id:
                    report_path = Path(env['DR_LOGS_DIR']) / f'validation-report-{validation_id}.json'
                    if report_path.exists():
                        with open(report_path, 'r') as f:
                            validation_result['report'] = json.load(f)
                        logger.info(f"Loaded validation report: {report_path}")
                    else:
                        logger.warning(f"Validation report not found: {report_path}")
            except Exception as e:
                logger.warning(f"Could not load validation report: {e}")
            
            # **FIX**: Cleanup downloaded files if this was a temporary download for validation
            if downloaded_for_validation and local_session_path and local_session_path.exists():
                try:
                    import shutil
                    shutil.rmtree(local_session_path)
                    logger.info(f"Cleaned up temporary validation download: {local_session_path}")
                    validation_result['cleanup_performed'] = True
                except Exception as e:
                    logger.warning(f"Failed to cleanup temporary validation files: {e}")
                    validation_result['cleanup_error'] = str(e)
            
            # **FIX**: Provide specific error analysis for common validation failures
            if not validation_result['success']:
                # Analyze common failure patterns
                error_analysis = self._analyze_validation_failure(result.stdout, result.stderr, result.returncode)
                validation_result['error_analysis'] = error_analysis
                
                # Add specific suggestions based on the error type
                if 'decryption' in error_analysis.get('likely_cause', '').lower():
                    validation_result['suggestions'] = [
                        'Check if the encryption key is correct',
                        'Verify that backup files were encrypted with the same key',
                        'Try re-running the backup to ensure files are properly encrypted',
                        'Check for OpenSSL version compatibility issues'
                    ]
                elif 'file_not_found' in error_analysis.get('likely_cause', '').lower():
                    validation_result['suggestions'] = [
                        'Verify the backup session exists',
                        'Check if backup files are properly uploaded/downloaded',
                        'Try re-running the backup to ensure all files are created'
                    ]
            
            # Log summary
            if validation_result['success']:
                logger.info(f"Validation completed successfully for session: {session_to_validate or 'latest'} from {source}")
            else:
                logger.error(f"Validation failed for session: {session_to_validate or 'latest'} from {source}")
                if result.stderr:
                    logger.error(f"Validation errors: {result.stderr}")
                if 'error_analysis' in validation_result:
                    logger.error(f"Error analysis: {validation_result['error_analysis']}")
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Validation failed with exception: {e}")
            return {
                'success': False,
                'error': str(e),
                'exception_type': type(e).__name__
            }





    def _analyze_validation_failure(self, stdout: str, stderr: str, return_code: int) -> Dict[str, Any]:
        """Analyze validation failure to provide specific error insights"""
        analysis = {
            'return_code': return_code,
            'likely_cause': 'unknown',
            'error_patterns': [],
            'recommendations': []
        }
        
        combined_output = (stdout + '\n' + stderr).lower()
        
        # Check for common error patterns
        if 'bad magic number' in combined_output or 'bad decrypt' in combined_output:
            analysis['likely_cause'] = 'decryption_failure'
            analysis['error_patterns'].append('Bad magic number - likely wrong encryption key')
            analysis['recommendations'].extend([
                'Check encryption key file exists and is correct',
                'Verify backup was encrypted with the same key being used for validation',
                'Check for OpenSSL version compatibility issues'
            ])
        
        elif 'no such file or directory' in combined_output:
            analysis['likely_cause'] = 'file_not_found'
            analysis['error_patterns'].append('Missing backup files')
            analysis['recommendations'].extend([
                'Verify backup session directory exists and contains encrypted files',
                'Check if backup completed successfully',
                'Ensure proper file permissions'
            ])
        
        elif 'permission denied' in combined_output:
            analysis['likely_cause'] = 'permission_error'
            analysis['error_patterns'].append('File permission issues')
            analysis['recommendations'].extend([
                'Check file permissions on backup directory',
                'Verify script has execute permissions',
                'Check Docker container permissions'
            ])
        
        elif 'postgresql' in combined_output and ('connection' in combined_output or 'failed' in combined_output):
            analysis['likely_cause'] = 'database_connection'
            analysis['error_patterns'].append('PostgreSQL connection issues')
            analysis['recommendations'].extend([
                'Verify PostgreSQL is running and accessible',
                'Check database credentials',
                'Ensure database exists'
            ])
        
        elif 'tar' in combined_output and 'error' in combined_output:
            analysis['likely_cause'] = 'archive_corruption'
            analysis['error_patterns'].append('Tar archive corruption or extraction failure')
            analysis['recommendations'].extend([
                'Check if backup files are corrupted',
                'Re-run backup to create fresh archives',
                'Verify file integrity during upload/download'
            ])
        
        elif return_code == 1 and not analysis['error_patterns']:
            analysis['likely_cause'] = 'general_validation_failure'
            analysis['error_patterns'].append('General validation failure')
            analysis['recommendations'].extend([
                'Check validation script logs for specific errors',
                'Run with debug mode enabled for more details',
                'Verify all backup components are present'
            ])
        
        return analysis
    def _find_session_by_partial_id(self, partial_id: str) -> Optional[str]:
        """Find full session name by partial ID"""
        try:
            dr_session_dir = Path(self.config.get('DR_SESSION_DIR', '/app/data/sessions'))
            if not dr_session_dir.exists():
                return None
            
            # List all backup sessions
            sessions = [d.name for d in dr_session_dir.iterdir() 
                    if d.is_dir() and d.name.startswith('backup_')]
            
            # Find sessions matching partial ID
            matching = [s for s in sessions if partial_id in s]
            
            if len(matching) == 1:
                return matching[0]
            elif len(matching) > 1:
                # Return the most recent one (sorted by name which includes timestamp)
                return sorted(matching, reverse=True)[0]
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error finding session by partial ID: {e}")
            return None

    def _extract_validation_id(self, output: str) -> Optional[str]:
        """Extract validation ID from script output"""
        try:
            # Look for validation ID in output
            for line in output.split('\n'):
                if 'Validation ID:' in line:
                    validation_id = line.split('Validation ID:')[1].strip()
                    return validation_id
            return None
        except Exception:
            return None

    def _parse_validation_output(self, output: str) -> Dict[str, Any]:
        """Parse validation output to extract structured information"""
        import re
        
        summary = {
            'errors': 0,
            'warnings': 0,
            'validations_performed': [],
            'session_validated': None,
            'validation_details': {},
            'timing': {}
        }
        
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Extract validation ID and session
            if 'Validating session:' in line:
                summary['session_validated'] = line.split('Validating session:')[1].strip()
            
            # Count errors and warnings from log messages
            if '[ERROR]' in line:
                summary['errors'] += 1
            elif '[WARNING]' in line:
                summary['warnings'] += 1
            elif '[SUCCESS]' in line:
                # Extract what was validated successfully
                if 'database backup valid:' in line.lower():
                    db_name = line.split('valid:')[1].strip() if 'valid:' in line else 'unknown'
                    summary['validations_performed'].append(f'database_backup_{db_name}')
                elif 'filestore backup valid' in line.lower():
                    summary['validations_performed'].append('filestore_backup')
                elif 'configuration backup valid' in line.lower():
                    config_name = line.split('valid:')[1].strip() if 'valid:' in line else 'unknown'
                    summary['validations_performed'].append(f'config_backup_{config_name}')
                elif 'cloud file validation passed' in line.lower():
                    summary['validations_performed'].append('cloud_sync')
                elif 'restoration test passed' in line.lower():
                    summary['validations_performed'].append('restoration_test')
                elif 'backup age is acceptable' in line.lower():
                    summary['validations_performed'].append('age_check')
            
            # Extract detailed validation information
            if 'Database validation completed:' in line:
                match = re.search(r'(\d+)/(\d+) valid', line)
                if match:
                    summary['validation_details']['databases'] = {
                        'valid': int(match.group(1)),
                        'total': int(match.group(2))
                    }
            
            if 'Configuration validation completed:' in line:
                match = re.search(r'(\d+)/(\d+) valid', line)
                if match:
                    summary['validation_details']['configurations'] = {
                        'valid': int(match.group(1)),
                        'total': int(match.group(2))
                    }
            
            # Extract backup age information
            if 'Backup age:' in line:
                age_match = re.search(r'Backup age: (\d+) hours', line)
                if age_match:
                    summary['validation_details']['backup_age_hours'] = int(age_match.group(1))
            
            # Extract file counts for cloud validation
            if 'File count matches:' in line:
                count_match = re.search(r'(\d+) files', line)
                if count_match:
                    summary['validation_details']['cloud_file_count'] = int(count_match.group(1))
        
        # Calculate overall status
        summary['overall_status'] = 'passed' if summary['errors'] == 0 else 'failed'
        summary['has_warnings'] = summary['warnings'] > 0
        
        return summary

    # Alternative simpler method for quick validation
    def quick_validate_backup(self, session_id: str) -> Dict[str, Any]:
        """Quick validation that just checks if backup files exist and are readable"""
        try:
            dr_session_dir = Path(self.config.get('DR_SESSION_DIR', '/app/data/sessions'))
            
            # Handle session ID normalization
            if not session_id.startswith('backup_'):
                session_id = f"backup_{session_id}"
            
            session_path = dr_session_dir / session_id
            
            if not session_path.exists():
                return {
                    'success': False, 
                    'error': 'Session directory not found',
                    'details': {
                        'session_id': session_id,
                        'session_path': str(session_path),
                        'dr_session_dir': str(dr_session_dir),
                        'available_sessions': [d.name for d in dr_session_dir.iterdir() if d.is_dir()] if dr_session_dir.exists() else []
                    }
                }
            
            # Check for manifest file
            manifest_path = session_path / 'backup-manifest.json'
            if not manifest_path.exists():
                return {'success': False, 'error': 'Backup manifest not found'}
            
            # Try to read manifest
            try:
                with open(manifest_path, 'r') as f:
                    manifest = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                return {'success': False, 'error': f'Cannot read manifest: {e}'}
            
            # Check for backup files
            checks = {
                'manifest': True,
                'databases': len(list((session_path / 'databases').glob('*.enc'))) > 0 if (session_path / 'databases').exists() else False,
                'filestore': (session_path / 'filestore' / 'filestore.tar.gz.enc').exists(),
                'configs': len(list((session_path / 'configs').glob('*.enc'))) > 0 if (session_path / 'configs').exists() else False
            }
            
            return {
                'success': all(checks.values()),
                'checks': checks,
                'manifest': manifest,
                'session_path': str(session_path)
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
            
            
        
        
        
    
    
    
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
            # Normalize session ID
            session_id = self._normalize_session_id(session_id)
            
            # Find the backup directory for this session using configuration
            # Use configured paths first, then fall back to common locations
            session_dirs_to_check = []
            
            # Get configured session directory
            configured_session_dir = self.config.get('DR_SESSION_DIR')
            if configured_session_dir:
                session_dirs_to_check.append(Path(configured_session_dir))
            
            # Add fallback directories
            session_dirs_to_check.extend([
                DATA_DIR / 'sessions',
                Path('/app/data/sessions'),
                Path('/opt/backups/sessions'), 
                BASE_DIR / 'data' / 'sessions',
                Path('/tmp/backup-sessions')
            ])
            
            backup_dir = None
            for session_base_dir in session_dirs_to_check:
                if session_base_dir.exists():
                    session_dir = session_base_dir / session_id
                    if session_dir.exists():
                        backup_dir = session_dir
                        logger.info(f"Found backup session at: {backup_dir}")
                        break
            
            if not backup_dir:
                # List available sessions for debugging
                available_sessions = []
                for session_base_dir in session_dirs_to_check:
                    if session_base_dir.exists():
                        available_sessions.extend([
                            d.name for d in session_base_dir.iterdir() 
                            if d.is_dir() and d.name.startswith('backup_')
                        ])
                
                return {
                    'success': False, 
                    'error': f'Backup directory for session {session_id} not found',
                    'details': {
                        'session_id': session_id,
                        'searched_directories': [str(d) for d in session_dirs_to_check],
                        'available_sessions': available_sessions[:5]  # Show first 5
                    }
                }
            
            # Validate manifest before attempting restore
            manifest_check = self._check_manifest_integrity(backup_dir)
            if not manifest_check['valid']:
                return {
                    'success': False,
                    'error': f'Backup manifest is invalid: {manifest_check["error"]}',
                    'manifest_check': manifest_check,
                    'backup_dir': str(backup_dir)
                }
            
            # Run restore script
            script_path = SCRIPTS_DIR / 'disaster-recovery.sh'
            if not script_path.exists():
                return {'success': False, 'error': 'Disaster recovery script not found'}
            
            # Make script executable
            try:
                os.chmod(script_path, 0o755)
            except OSError as e:
                logger.warning(f"Could not make script executable: {e}")
            
            # Prepare environment variables
            env = os.environ.copy()
            env.update({
                'DR_SESSION_DIR': str(backup_dir.parent),
                'DR_BACKUP_DIR': str(backup_dir.parent),
                'DR_RESTORE_PATH': restore_path,
                'DR_RESTORE_TYPE': restore_type,
                'BACKUP_SESSION': session_id,
                'USE_CLOUD': 'false',
                'FORCE': 'true',
                'TEST_MODE': 'false',
                'DOCKER_CONTAINER': '1'
            })
            
            # Add configuration values to environment
            for key, value in self.config.config.items():
                if key.startswith(('DR_', 'POSTGRES_', 'GDRIVE_', 'AWS_')):
                    env[key] = str(value)
            
            logger.info(f"Starting local restore from {backup_dir} to {restore_path}")
            logger.info(f"Restore type: {restore_type}")
            
            # Build command for disaster recovery script
            cmd = [str(script_path), 'restore', session_id]
            
            logger.info(f"Running restore command: {' '.join(cmd)}")
            logger.info(f"Environment: DR_SESSION_DIR={env['DR_SESSION_DIR']}")
            logger.info(f"Environment: DR_RESTORE_PATH={env['DR_RESTORE_PATH']}")
            logger.info(f"Environment: DR_RESTORE_TYPE={env['DR_RESTORE_TYPE']}")
            
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour timeout
                cwd=str(SCRIPTS_DIR)
            )
            
            logger.info(f"Local restore completed with exit code: {result.returncode}")
            
            if result.stdout:
                logger.info("Restore stdout:")
                logger.info(result.stdout)
            if result.stderr:
                logger.warning("Restore stderr:")
                logger.warning(result.stderr)
            
            return {
                'success': result.returncode == 0,
                'output': result.stdout,
                'error': result.stderr,
                'return_code': result.returncode,
                'backup_dir': str(backup_dir),
                'session_id': session_id,
                'restore_type': restore_type,
                'restore_path': restore_path,
                'restore_command': ' '.join(cmd)
            }
            
        except subprocess.TimeoutExpired:
            logger.error("Local restore operation timed out")
            return {'success': False, 'error': 'Local restore operation timed out'}
        except Exception as e:
            logger.error(f"Local restore failed: {e}")
            return {'success': False, 'error': str(e), 'exception_type': type(e).__name__}
    
    def _restore_from_gdrive(self, session_id: str, restore_type: str, restore_path: str) -> Dict[str, Any]:
        """Restore from Google Drive backup"""
        try:
            if not GoogleDriveBackup:
                return {'success': False, 'error': 'Google Drive integration not available'}
            
            # Normalize session ID
            session_id = self._normalize_session_id(session_id)
            
            gdrive = GoogleDriveBackup(self.config.config)
            if not gdrive.authenticate():
                return {'success': False, 'error': 'Failed to authenticate with Google Drive'}
            
            # Create download directory with proper structure
            import tempfile
            download_base = Path(tempfile.mkdtemp(prefix=f'{session_id}_restore_'))
            
            logger.info(f"Created temporary restore directory: {download_base}")
            
            # Create session directory structure
            session_download_dir = download_base / session_id
            session_download_dir.mkdir(parents=True, exist_ok=True)
            
            # Create subdirectories for proper backup structure
            (session_download_dir / 'databases').mkdir(exist_ok=True)
            (session_download_dir / 'filestore').mkdir(exist_ok=True)
            (session_download_dir / 'configs').mkdir(exist_ok=True)
            
            logger.info(f"Downloading backup {session_id} from Google Drive to {session_download_dir}")
            
            # Search for backup files with session_id pattern
            files = gdrive.list_files(limit=1000)
            
            # Improved pattern matching for session files
            backup_files = []
            for f in files:
                file_name = f['name']
                # Match both full session names and partial IDs
                if (session_id in file_name or 
                    session_id.replace('backup_', '') in file_name):
                    backup_files.append(f)
            
            if not backup_files:
                return {'success': False, 'error': f'No backup files found for session {session_id} in Google Drive'}
            
            logger.info(f"Found {len(backup_files)} backup files for session {session_id}")
            
            # Download files and organize them by type
            downloaded_files = []
            for file_info in backup_files:
                file_name = file_info['name']
                
                # Determine subdirectory based on file type
                if '.sql.enc' in file_name or '_db_' in file_name:
                    local_path = session_download_dir / 'databases' / file_name
                elif 'filestore' in file_name:
                    local_path = session_download_dir / 'filestore' / file_name
                elif 'config' in file_name:
                    local_path = session_download_dir / 'configs' / file_name
                elif 'manifest' in file_name:
                    local_path = session_download_dir / file_name
                else:
                    # Default to session root directory
                    local_path = session_download_dir / file_name
                
                logger.info(f"Downloading {file_name} to {local_path}")
                success = gdrive.download_file(file_info['id'], str(local_path))
                
                if not success:
                    return {'success': False, 'error': f'Failed to download {file_name}'}
                
                downloaded_files.append(str(local_path))
            
            logger.info(f"Successfully downloaded {len(downloaded_files)} files")
            
            # Validate downloaded manifest
            manifest_path = session_download_dir / 'backup-manifest.json'
            if manifest_path.exists():
                manifest_check = self._check_manifest_integrity(session_download_dir)
                if not manifest_check['valid']:
                    return {
                        'success': False, 
                        'error': f'Downloaded manifest is invalid: {manifest_check["error"]}',
                        'manifest_check': manifest_check
                    }
            else:
                logger.warning("No manifest file found in downloaded backup")
            
            # Now run disaster recovery script with the downloaded session
            script_path = SCRIPTS_DIR / 'disaster-recovery.sh'
            if not script_path.exists():
                return {'success': False, 'error': 'Disaster recovery script not found'}
            
            # Prepare environment variables
            env = os.environ.copy()
            
            # Set paths to use our download directory
            env.update({
                'DR_SESSION_DIR': str(download_base),
                'DR_BACKUP_DIR': str(download_base),
                'DR_RESTORE_PATH': restore_path,
                'DR_RESTORE_TYPE': restore_type,
                'BACKUP_SESSION': session_id,
                'USE_CLOUD': 'false',  # We've already downloaded it
                'FORCE': 'true',  # Skip confirmation since this is API call
                'TEST_MODE': 'false',
                'DOCKER_CONTAINER': '1'
            })
            
            # Add configuration values to environment
            for key, value in self.config.config.items():
                if key.startswith(('DR_', 'POSTGRES_', 'GDRIVE_', 'AWS_')):
                    env[key] = str(value)
            
            # Make script executable
            try:
                os.chmod(script_path, 0o755)
            except OSError as e:
                logger.warning(f"Could not make script executable: {e}")
            
            # Build command for disaster recovery
            cmd = [str(script_path), 'restore', session_id]
            
            logger.info(f"Running disaster recovery: {' '.join(cmd)}")
            logger.info(f"Environment: DR_SESSION_DIR={env['DR_SESSION_DIR']}")
            logger.info(f"Environment: DR_RESTORE_PATH={env['DR_RESTORE_PATH']}")
            logger.info(f"Environment: DR_RESTORE_TYPE={env['DR_RESTORE_TYPE']}")
            
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour timeout
                cwd=str(SCRIPTS_DIR)
            )
            
            logger.info(f"Restore completed with exit code: {result.returncode}")
            
            if result.stdout:
                logger.info("Restore stdout:")
                logger.info(result.stdout)
            if result.stderr:
                logger.warning("Restore stderr:")
                logger.warning(result.stderr)
            
            # Clean up downloaded files after restore
            cleanup_successful = False
            try:
                import shutil
                shutil.rmtree(download_base)
                cleanup_successful = True
                logger.info(f"Cleaned up downloaded files: {download_base}")
            except Exception as e:
                logger.warning(f"Failed to clean up downloaded files: {e}")
            
            return {
                'success': result.returncode == 0,
                'output': result.stdout,
                'error': result.stderr,
                'return_code': result.returncode,
                'downloaded_files': len(downloaded_files),
                'restore_command': ' '.join(cmd),
                'cleanup_successful': cleanup_successful,
                'session_id': session_id,
                'restore_type': restore_type,
                'restore_path': restore_path
            }
            
        except subprocess.TimeoutExpired:
            logger.error("Google Drive restore operation timed out")
            return {'success': False, 'error': 'Google Drive restore operation timed out'}
        except Exception as e:
            logger.error(f"Google Drive restore failed: {e}")
            return {'success': False, 'error': str(e), 'exception_type': type(e).__name__}
    
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
            
            # Get all backup files and group them by session
            files = gdrive.list_files(limit=1000)
            
            # Group files by backup session
            sessions = {}
            for file_info in files:
                file_name = file_info['name']
                
                # Extract session ID from filename patterns
                session_id = None
                if 'backup_' in file_name:
                    parts = file_name.split('_')
                    if len(parts) >= 3 and parts[0] == 'backup':
                        session_id = f"{parts[0]}_{parts[1]}_{parts[2]}"
                
                if session_id:
                    if session_id not in sessions:
                        sessions[session_id] = {
                            'session_id': session_id,
                            'location': 'gdrive',
                            'files': [],
                            'total_size': 0,
                            'created': file_info.get('createdTime'),
                            'file_count': 0
                        }
                    
                    sessions[session_id]['files'].append(file_info)
                    sessions[session_id]['total_size'] += int(file_info.get('size', 0))
                    sessions[session_id]['file_count'] += 1
                    
                    # Use earliest creation time
                    if file_info.get('createdTime') and (
                        not sessions[session_id]['created'] or 
                        file_info['createdTime'] < sessions[session_id]['created']
                    ):
                        sessions[session_id]['created'] = file_info['createdTime']
            
            # Convert to list and sort by creation time
            backup_list = list(sessions.values())
            backup_list.sort(key=lambda x: x.get('created', ''), reverse=True)
            
            return backup_list
            
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
    
    def _download_backup_for_validation(self, session_id: str, target_dir: str) -> Dict[str, Any]:
        """Download backup from Google Drive for validation"""
        try:
            if not GoogleDriveBackup:
                return {'success': False, 'error': 'Google Drive integration not available'}
            
            gdrive = GoogleDriveBackup(self.config.config)
            if not gdrive.authenticate():
                return {'success': False, 'error': 'Failed to authenticate with Google Drive'}
            
            # Normalize session ID
            session_id = self._normalize_session_id(session_id)
            
            # Create target session directory
            target_session_dir = Path(target_dir) / session_id
            target_session_dir.mkdir(parents=True, exist_ok=True)
            
            # Create subdirectories for proper backup structure
            (target_session_dir / 'databases').mkdir(exist_ok=True)
            (target_session_dir / 'filestore').mkdir(exist_ok=True)
            (target_session_dir / 'configs').mkdir(exist_ok=True)
            
            logger.info(f"Downloading backup {session_id} from Google Drive for validation")
            
            # Search for backup files with session_id pattern
            files = gdrive.list_files(limit=1000)
            
            # Improved pattern matching for session files
            backup_files = []
            for f in files:
                file_name = f['name']
                # Match both full session names and partial IDs
                if (session_id in file_name or 
                    session_id.replace('backup_', '') in file_name):
                    backup_files.append(f)
            
            if not backup_files:
                # Try to find files with more flexible matching
                logger.warning(f"No exact matches found for {session_id}, trying flexible search")
                partial_id = session_id.replace('backup_', '')
                backup_files = [f for f in files if partial_id in f['name']]
                
                if not backup_files:
                    return {
                        'success': False, 
                        'error': f'No backup files found for session {session_id} in Google Drive',
                        'available_files_sample': [f['name'] for f in files[:10]]  # Show sample for debugging
                    }
            
            logger.info(f"Found {len(backup_files)} backup files for session {session_id}")
            
            # Download files and organize them by type
            downloaded_files = []
            download_errors = []
            
            for file_info in backup_files:
                file_name = file_info['name']
                
                # Determine subdirectory based on file type
                if '.sql.enc' in file_name or '_db_' in file_name or 'database' in file_name.lower():
                    local_path = target_session_dir / 'databases' / file_name
                elif 'filestore' in file_name or 'files' in file_name.lower():
                    local_path = target_session_dir / 'filestore' / file_name
                elif 'config' in file_name:
                    local_path = target_session_dir / 'configs' / file_name
                elif 'manifest' in file_name:
                    local_path = target_session_dir / file_name
                else:
                    # Default to session root directory
                    local_path = target_session_dir / file_name
                
                logger.info(f"Downloading {file_name} to {local_path}")
                
                # Ensure parent directory exists
                local_path.parent.mkdir(parents=True, exist_ok=True)
                
                try:
                    success = gdrive.download_file(file_info['id'], str(local_path))
                    
                    if success and local_path.exists() and local_path.stat().st_size > 0:
                        downloaded_files.append(str(local_path))
                        logger.info(f"Successfully downloaded {file_name} ({local_path.stat().st_size} bytes)")
                    else:
                        error_msg = f'Failed to download {file_name} or file is empty'
                        download_errors.append(error_msg)
                        logger.error(error_msg)
                        
                except Exception as e:
                    error_msg = f'Exception downloading {file_name}: {str(e)}'
                    download_errors.append(error_msg)
                    logger.error(error_msg)
            
            # Check if we got at least some files
            if not downloaded_files:
                return {
                    'success': False,
                    'error': 'No files were successfully downloaded',
                    'download_errors': download_errors
                }
            
            # Validate that we have at least a manifest file
            manifest_path = target_session_dir / 'backup-manifest.json'
            if not manifest_path.exists():
                logger.warning("No manifest file found in downloaded backup")
            
            return {
                'success': True,
                'session_path': str(target_session_dir),
                'downloaded_files': len(downloaded_files),
                'files': downloaded_files,
                'download_errors': download_errors,
                'has_manifest': manifest_path.exists()
            }
            
        except Exception as e:
            logger.error(f"Failed to download backup for validation: {e}")
            return {'success': False, 'error': str(e), 'exception_type': type(e).__name__}

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
    destinations = data.get('destinations', ['gdrive'])
    
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
    """API endpoint to validate a backup from local storage or Google Drive"""
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        source = data.get('source', 'auto')  # 'local', 'gdrive', or 'auto'
        
        logger.info(f"Validating backup: {session_id} from source: {source}")
        
        # Validate source parameter
        if source not in ['local', 'gdrive', 'auto']:
            return jsonify({
                'success': False,
                'error': 'Invalid source. Must be "local", "gdrive", or "auto"',
                'valid_sources': ['local', 'gdrive', 'auto']
            }), 400
        
        # For local validation, do a quick check if the session exists locally
        if source == 'local' and session_id:
            session_dirs = [
                Path('/app/data/sessions'),
                DATA_DIR / 'sessions',
                Path('/opt/backups/sessions')
            ]
            
            session_found = False
            for session_dir in session_dirs:
                if session_dir.exists():
                    normalized_session_id = backup_manager._normalize_session_id(session_id)
                    session_path = session_dir / normalized_session_id
                    if session_path.exists():
                        session_found = True
                        break
            
            if not session_found:
                available_sessions = []
                for session_dir in session_dirs:
                    if session_dir.exists():
                        available_sessions.extend([
                            d.name for d in session_dir.iterdir() 
                            if d.is_dir() and d.name.startswith('backup_')
                        ])
                
                return jsonify({
                    'success': False,
                    'error': f'Backup session not found locally: {session_id}',
                    'available_sessions': available_sessions[:10],
                    'searched_directories': [str(d) for d in session_dirs],
                    'validation_source': 'local'
                }), 404
        
        result = backup_manager.validate_backup(session_id, source)
        
        # Add more context to the result based on error type
        if not result.get('success'):
            error_msg = str(result.get('error', ''))
            
            if 'Invalid JSON' in error_msg:
                result['fix_suggestion'] = 'The backup manifest file is corrupted. Try deleting this backup session and running a new backup.'
                result['corrupted_file'] = f'backup-manifest.json in session directory'
            elif 'not found' in error_msg.lower() and 'google drive' in error_msg.lower():
                result['fix_suggestion'] = 'Check if the backup exists in Google Drive or verify Google Drive authentication.'
            elif 'authentication' in error_msg.lower():
                result['fix_suggestion'] = 'Verify Google Drive credentials in the configuration.'
            elif 'manifest validation failed' in error_msg.lower():
                result['fix_suggestion'] = 'The backup manifest is corrupted. Delete this backup and run a new one.'
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Validation API error: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'exception_type': type(e).__name__,
            'type': 'api_error'
        }), 500

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
    """API endpoint to restore from backup (local or Google Drive)"""
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        restore_type = data.get('restore_type', 'full')  # full, selective, database_only
        target_location = data.get('target_location', 'local')  # local, gdrive
        restore_path = data.get('restore_path', '/tmp/odoo-restore')
        
        if not session_id:
            return jsonify({
                'success': False,
                'error': 'Session ID is required',
                'valid_restore_types': ['full', 'selective', 'database_only'],
                'valid_target_locations': ['local', 'gdrive']
            }), 400
        
        # Validate restore_type
        if restore_type not in ['full', 'selective', 'database_only']:
            return jsonify({
                'success': False,
                'error': 'Invalid restore_type',
                'valid_restore_types': ['full', 'selective', 'database_only']
            }), 400
        
        # Validate target_location
        if target_location not in ['local', 'gdrive']:
            return jsonify({
                'success': False,
                'error': 'Invalid target_location',
                'valid_target_locations': ['local', 'gdrive']
            }), 400
        
        # Normalize session ID
        normalized_session_id = backup_manager._normalize_session_id(session_id)
        
        logger.info(f"Starting restore: session={normalized_session_id}, type={restore_type}, location={target_location}, path={restore_path}")
        
        # Check if session exists in database (optional, for tracking)
        session = backup_manager.db.get_backup_session(normalized_session_id)
        if not session:
            logger.warning(f"Session {normalized_session_id} not found in database, proceeding anyway")
        
        # Start restore process
        restore_result = backup_manager.restore_backup(
            session_id=normalized_session_id,
            restore_type=restore_type,
            target_location=target_location,
            restore_path=restore_path
        )
        
        # Add more context to the result
        if restore_result.get('success'):
            restore_result['message'] = f'Restore started successfully for session {normalized_session_id}'
            restore_result['estimated_time'] = '30-60 minutes depending on backup size'
        else:
            # Add troubleshooting suggestions
            error_msg = str(restore_result.get('error', ''))
            
            if 'not found' in error_msg.lower():
                restore_result['fix_suggestion'] = 'Verify the session ID exists in the specified location (local or Google Drive)'
            elif 'authentication' in error_msg.lower():
                restore_result['fix_suggestion'] = 'Check Google Drive authentication credentials'
            elif 'manifest' in error_msg.lower():
                restore_result['fix_suggestion'] = 'The backup appears to be corrupted. Try a different backup session.'
        
        return jsonify(restore_result)
        
    except Exception as e:
        logger.error(f"Restore API error: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'exception_type': type(e).__name__,
            'type': 'api_error'
        }), 500

@app.route('/api/restore/list-backups')
@login_required
def api_list_restore_backups():
    """API endpoint to list available backups for restore from local and Google Drive"""
    try:
        source = request.args.get('source', 'both')  # local, gdrive, both
        limit = int(request.args.get('limit', 50))
        
        logger.info(f"Listing backups from source: {source}, limit: {limit}")
        
        if source not in ['local', 'gdrive', 'both']:
            return jsonify({
                'success': False,
                'error': 'Invalid source specified',
                'valid_sources': ['local', 'gdrive', 'both']
            }), 400
        
        result = {
            'success': True,
            'source': source,
            'backups': []
        }
        
        # List local backups
        if source in ['local', 'both']:
            try:
                local_backups = backup_manager.list_local_backups()
                for backup in local_backups[:limit]:
                    backup['source'] = 'local'
                result['backups'].extend(local_backups[:limit])
                result['local_count'] = len(local_backups)
                logger.info(f"Found {len(local_backups)} local backups")
            except Exception as e:
                logger.error(f"Error listing local backups: {e}")
                result['local_error'] = str(e)
                result['local_count'] = 0
        
        # List Google Drive backups
        if source in ['gdrive', 'both']:
            try:
                gdrive_backups = backup_manager.list_gdrive_backups()
                for backup in gdrive_backups[:limit]:
                    backup['source'] = 'gdrive'
                result['backups'].extend(gdrive_backups[:limit])
                result['gdrive_count'] = len(gdrive_backups)
                logger.info(f"Found {len(gdrive_backups)} Google Drive backups")
            except Exception as e:
                logger.error(f"Error listing Google Drive backups: {e}")
                result['gdrive_error'] = str(e)
                result['gdrive_count'] = 0
        
        # Sort by creation time if both sources
        if source == 'both':
            result['backups'].sort(key=lambda x: x.get('created', ''), reverse=True)
            result['backups'] = result['backups'][:limit]
        
        result['total_backups'] = len(result['backups'])
        
        # Add metadata
        result['metadata'] = {
            'generated_at': datetime.now().isoformat(),
            'total_local': result.get('local_count', 0),
            'total_gdrive': result.get('gdrive_count', 0),
            'limit_applied': limit
        }
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"List backups API error: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'exception_type': type(e).__name__,
            'type': 'api_error'
        }), 500

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
