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
CONFIG_FILE = BASE_DIR / 'config' / 'dr-config.env'
SCRIPTS_DIR = BASE_DIR / 'scripts'

# Use writable data directory in Docker for persistent data
DATA_DIR = Path('/app/data')
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
        """Load configuration from dr-config.env"""
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r') as f:
                for line in f:
                    line = line.strip()
                    if '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        self.config[key.strip()] = value.strip().strip('"')
        
        # Set defaults
        self.config.setdefault('DR_BACKUP_DESTINATIONS', 'aws')
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

config = Config()

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

db = DatabaseManager()

class BackupManager:
    """Manager for backup operations"""
    
    def __init__(self):
        self.config = config
        self.db = db
    
    def run_backup(self, destinations: Optional[List[str]] = None) -> Dict[str, Any]:
        """Run a backup operation"""
        try:
            # Prepare environment
            env = os.environ.copy()
            if destinations:
                env['DR_BACKUP_DESTINATIONS'] = ','.join(destinations)
            
            # Set Docker environment indicator
            env['DOCKER_CONTAINER'] = '1'
            
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
            
            # Determine shell command based on OS
            if os.name == 'nt':  # Windows
                cmd = ['bash', str(script_path)]
            else:  # Unix-like
                cmd = [str(script_path)]
            
            logger.info(f"Executing command: {' '.join(cmd)}")
            
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

if __name__ == '__main__':
    # Create necessary directories
    os.makedirs(BASE_DIR / 'backup_panel' / 'static', exist_ok=True)
    os.makedirs(BASE_DIR / 'backup_panel' / 'templates', exist_ok=True)
    
    # Run development server
    app.run(host='0.0.0.0', port=5000, debug=True)
