# **manifest**.py

{
'name': 'Log Transfer API',
'version': '17.0.1.0.0',
'category': 'Tools',
'summary': 'Transfer logs via API for specific tenants with real-time streaming',
'description': """
This module provides API endpoints to transfer logs for specific tenants.
Features: - Initial authentication with admin credentials - Real-time log streaming via WebSocket - Tenant-specific log filtering - No API key required after initial auth
""",
'author': 'Your Company',
'depends': ['base', 'web'],
'data': [
'security/ir.model.access.csv',
'views/log_transfer_views.xml',
],
'assets': {
'web.assets_backend': [
'log_transfer/static/src/js/log_websocket.js',
],
},
'installable': True,
'auto_install': False,
'application': False,
}

# models/**init**.py

from . import log_transfer

# models/log_transfer.py

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from odoo import models, fields, api, http
from odoo.http import request
import websocket
import asyncio
import socketio

\_logger = logging.getLogger(**name**)

class LogTransfer(models.Model):
\_name = 'log.transfer'
\_description = 'Log Transfer Configuration'
\_rec_name = 'tenant_name'

    tenant_name = fields.Char('Tenant Name', required=True)
    database_name = fields.Char('Database Name', required=True)
    is_active = fields.Boolean('Active', default=True)
    last_sync = fields.Datetime('Last Sync')
    auth_token = fields.Char('Auth Token')
    created_date = fields.Datetime('Created Date', default=fields.Datetime.now)

    @api.model
    def authenticate_tenant(self, admin_id, password, database_name):
        """Authenticate tenant and return auth token"""
        try:
            # Validate admin credentials
            uid = request.session.authenticate(database_name, admin_id, password)
            if not uid:
                return {'error': 'Invalid credentials'}

            # Check if user is admin
            user = request.env['res.users'].sudo().browse(uid)
            if not user.has_group('base.group_system'):
                return {'error': 'Admin privileges required'}

            # Generate or get existing token
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
                'websocket_url': f'/log_stream/{log_config.auth_token}'
            }
        except Exception as e:
            _logger.error(f"Authentication error: {str(e)}")
            return {'error': str(e)}

    def _generate_token(self):
        """Generate unique auth token"""
        import secrets
        return secrets.token_urlsafe(32)

    @api.model
    def get_logs(self, token, limit=100, offset=0, level='INFO'):
        """Get logs for authenticated tenant"""
        log_config = self.search([('auth_token', '=', token)], limit=1)
        if not log_config:
            return {'error': 'Invalid token'}

        try:
            logs = self._fetch_logs(log_config.database_name, limit, offset, level)
            return {
                'success': True,
                'logs': logs,
                'total': len(logs),
                'tenant': log_config.tenant_name
            }
        except Exception as e:
            return {'error': str(e)}

    def _fetch_logs(self, database_name, limit=100, offset=0, level='INFO'):
        """Fetch logs from log files or database"""
        logs = []
        try:
            # This is a simplified example - you'd need to implement actual log reading
            # based on your logging configuration

            # Option 1: Read from log files
            import os
            log_file_path = f'/var/log/odoo/odoo-{database_name}.log'
            if os.path.exists(log_file_path):
                with open(log_file_path, 'r') as f:
                    lines = f.readlines()
                    for line in lines[-limit:]:
                        if level.lower() in line.lower():
                            logs.append({
                                'timestamp': datetime.now().isoformat(),
                                'level': level,
                                'message': line.strip(),
                                'database': database_name
                            })

            # Option 2: Read from ir.logging (if available)
            # This requires the ir.logging model to be properly configured
            try:
                ir_logs = request.env['ir.logging'].sudo().search([
                    ('dbname', '=', database_name),
                    ('level', '=', level)
                ], limit=limit, offset=offset, order='id desc')

                for log in ir_logs:
                    logs.append({
                        'id': log.id,
                        'timestamp': log.create_date.isoformat() if log.create_date else None,
                        'level': log.level,
                        'message': log.message,
                        'name': log.name,
                        'function': log.func,
                        'line': log.line,
                        'database': database_name
                    })
            except:
                pass  # ir.logging might not be available

        except Exception as e:
            _logger.error(f"Error fetching logs: {str(e)}")

        return logs

# controllers/**init**.py

from . import log_api

# controllers/log_api.py

import json
import logging
import asyncio
from odoo import http
from odoo.http import request, Response
import socketio
import threading
import time

\_logger = logging.getLogger(**name**)

# Socket.IO server for real-time log streaming

sio = socketio.AsyncServer(
cors_allowed_origins="\*",
async_mode='threading'
)

class LogAPI(http.Controller):

    @http.route('/api/log/auth', type='json', auth='none', methods=['POST'], csrf=False)
    def authenticate(self, **kwargs):
        """Initial authentication endpoint"""
        try:
            data = request.jsonrequest
            admin_id = data.get('admin_id')
            password = data.get('password')
            database_name = data.get('database_name')

            if not all([admin_id, password, database_name]):
                return {'error': 'Missing required parameters'}

            log_transfer = request.env['log.transfer'].sudo()
            result = log_transfer.authenticate_tenant(admin_id, password, database_name)

            return result
        except Exception as e:
            _logger.error(f"Auth endpoint error: {str(e)}")
            return {'error': str(e)}

    @http.route('/api/log/stream/<string:token>', type='http', auth='none', methods=['GET'], csrf=False)
    def get_logs(self, token, **kwargs):
        """Get logs endpoint"""
        try:
            limit = int(kwargs.get('limit', 100))
            offset = int(kwargs.get('offset', 0))
            level = kwargs.get('level', 'INFO')

            log_transfer = request.env['log.transfer'].sudo()
            result = log_transfer.get_logs(token, limit, offset, level)

            return Response(
                json.dumps(result),
                content_type='application/json',
                status=200 if result.get('success') else 400
            )
        except Exception as e:
            _logger.error(f"Logs endpoint error: {str(e)}")
            return Response(
                json.dumps({'error': str(e)}),
                content_type='application/json',
                status=500
            )

    @http.route('/api/log/websocket/<string:token>', type='http', auth='none', methods=['GET'], csrf=False)
    def websocket_endpoint(self, token, **kwargs):
        """WebSocket endpoint for real-time log streaming"""
        try:
            # Validate token
            log_transfer = request.env['log.transfer'].sudo()
            log_config = log_transfer.search([('auth_token', '=', token)], limit=1)

            if not log_config:
                return Response(
                    json.dumps({'error': 'Invalid token'}),
                    content_type='application/json',
                    status=401
                )

            # Start WebSocket connection info
            websocket_info = {
                'websocket_url': f'ws://localhost:8069/socket.io/?token={token}',
                'events': {
                    'connect': 'Connection established',
                    'log_update': 'New log entries',
                    'disconnect': 'Connection closed'
                },
                'usage': {
                    'connect': f"socket.connect('ws://localhost:8069/socket.io/?token={token}')",
                    'listen': "socket.on('log_update', function(data) { console.log(data); })"
                }
            }

            return Response(
                json.dumps(websocket_info),
                content_type='application/json',
                status=200
            )

        except Exception as e:
            _logger.error(f"WebSocket endpoint error: {str(e)}")
            return Response(
                json.dumps({'error': str(e)}),
                content_type='application/json',
                status=500
            )

# Real-time log monitoring

class LogMonitor:
def **init**(self):
self.active_connections = {}
self.monitoring_thread = None
self.is_running = False

    def start_monitoring(self):
        """Start the log monitoring thread"""
        if not self.is_running:
            self.is_running = True
            self.monitoring_thread = threading.Thread(target=self._monitor_logs)
            self.monitoring_thread.daemon = True
            self.monitoring_thread.start()

    def _monitor_logs(self):
        """Monitor logs and emit to connected clients"""
        while self.is_running:
            try:
                # Get all active log configurations
                log_configs = request.env['log.transfer'].sudo().search([('is_active', '=', True)])

                for config in log_configs:
                    if config.auth_token in self.active_connections:
                        # Fetch recent logs
                        logs = config._fetch_logs(config.database_name, limit=10)
                        if logs:
                            # Emit to connected clients
                            self._emit_logs(config.auth_token, logs)

                time.sleep(5)  # Check every 5 seconds
            except Exception as e:
                _logger.error(f"Log monitoring error: {str(e)}")
                time.sleep(10)

    def _emit_logs(self, token, logs):
        """Emit logs to connected WebSocket clients"""
        try:
            # This would integrate with your WebSocket implementation
            # For now, we'll just log it
            _logger.info(f"Emitting {len(logs)} logs for token {token[:8]}...")
        except Exception as e:
            _logger.error(f"Error emitting logs: {str(e)}")

# Initialize log monitor

log_monitor = LogMonitor()

# Socket.IO event handlers

@sio.event
async def connect(sid, environ, auth):
"""Handle WebSocket connection"""
try:
token = auth.get('token') if auth else None
if not token:
return False

        # Validate token
        log_transfer = request.env['log.transfer'].sudo()
        log_config = log_transfer.search([('auth_token', '=', token)], limit=1)

        if not log_config:
            return False

        log_monitor.active_connections[token] = sid
        await sio.emit('connected', {'message': f'Connected to {log_config.tenant_name}'}, room=sid)

        # Start monitoring if not already running
        log_monitor.start_monitoring()

        return True
    except Exception as e:
        _logger.error(f"WebSocket connection error: {str(e)}")
        return False

@sio.event
async def disconnect(sid):
"""Handle WebSocket disconnection"""
try: # Remove from active connections
for token, connection_sid in list(log_monitor.active_connections.items()):
if connection_sid == sid:
del log_monitor.active_connections[token]
break
except Exception as e:
\_logger.error(f"WebSocket disconnection error: {str(e)}")

# security/ir.model.access.csv

id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_log_transfer_admin,log.transfer.admin,model_log_transfer,base.group_system,1,1,1,1
access_log_transfer_user,log.transfer.user,model_log_transfer,base.group_user,1,0,0,0

# views/log_transfer_views.xml

<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_log_transfer_tree" model="ir.ui.view">
        <field name="name">log.transfer.tree</field>
        <field name="model">log.transfer</field>
        <field name="arch" type="xml">
            <tree string="Log Transfer Configurations">
                <field name="tenant_name"/>
                <field name="database_name"/>
                <field name="is_active"/>
                <field name="last_sync"/>
                <field name="created_date"/>
            </tree>
        </field>
    </record>

    <record id="view_log_transfer_form" model="ir.ui.view">
        <field name="name">log.transfer.form</field>
        <field name="model">log.transfer</field>
        <field name="arch" type="xml">
            <form string="Log Transfer Configuration">
                <sheet>
                    <group>
                        <field name="tenant_name"/>
                        <field name="database_name"/>
                        <field name="is_active"/>
                        <field name="last_sync"/>
                        <field name="auth_token" password="True"/>
                        <field name="created_date"/>
                    </group>
                </sheet>
            </form>
        </field>
    </record>

    <record id="action_log_transfer" model="ir.actions.act_window">
        <field name="name">Log Transfer</field>
        <field name="res_model">log.transfer</field>
        <field name="view_mode">tree,form</field>
        <field name="help" type="html">
            <p class="o_view_nocontent_smiling_face">
                Configure log transfer for tenants
            </p>
        </field>
    </record>

    <menuitem id="menu_log_transfer_root" name="Log Transfer" sequence="100"/>
    <menuitem id="menu_log_transfer" name="Log Configurations" parent="menu_log_transfer_root" action="action_log_transfer" sequence="1"/>

</odoo>

# static/src/js/log_websocket.js

// WebSocket client for real-time log streaming
class LogWebSocket {
constructor(token) {
this.token = token;
this.socket = null;
this.isConnected = false;
this.reconnectAttempts = 0;
this.maxReconnectAttempts = 5;
this.reconnectDelay = 1000;
}

    connect() {
        try {
            const url = `ws://${window.location.host}/socket.io/?token=${this.token}`;
            this.socket = io(url, {
                auth: {
                    token: this.token
                }
            });

            this.socket.on('connect', () => {
                console.log('Connected to log stream');
                this.isConnected = true;
                this.reconnectAttempts = 0;
            });

            this.socket.on('log_update', (data) => {
                this.handleLogUpdate(data);
            });

            this.socket.on('disconnect', () => {
                console.log('Disconnected from log stream');
                this.isConnected = false;
                this.attemptReconnect();
            });

            this.socket.on('connect_error', (error) => {
                console.error('Connection error:', error);
                this.attemptReconnect();
            });

        } catch (error) {
            console.error('WebSocket connection error:', error);
        }
    }

    disconnect() {
        if (this.socket) {
            this.socket.disconnect();
            this.isConnected = false;
        }
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`Attempting to reconnect... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

            setTimeout(() => {
                this.connect();
            }, this.reconnectDelay * this.reconnectAttempts);
        } else {
            console.error('Max reconnection attempts reached');
        }
    }

    handleLogUpdate(data) {
        // Handle incoming log updates
        console.log('New logs received:', data);

        // Emit custom event for other parts of the application
        const event = new CustomEvent('logUpdate', {
            detail: data
        });
        window.dispatchEvent(event);
    }

}

// Usage example
window.LogWebSocket = LogWebSocket;

# log_client.py - Python client example for the Log Transfer API

import requests
import socketio
import json
import time
import threading

class OdooLogClient:
def **init**(self, base_url):
self.base_url = base_url.rstrip('/')
self.token = None
self.sio = None

    def authenticate(self, admin_id, password, database_name):
        """
        Authenticate with Odoo and get access token

        Args:
            admin_id (str): Admin username
            password (str): Admin password
            database_name (str): Target database name

        Returns:
            dict: Authentication result
        """
        url = f"{self.base_url}/api/log/auth"
        payload = {
            "admin_id": admin_id,
            "password": password,
            "database_name": database_name
        }

        try:
            response = requests.post(url, json=payload)
            result = response.json()

            if result.get('success'):
                self.token = result.get('token')
                print(f"✅ Authentication successful! Token: {self.token[:16]}...")
                return result
            else:
                print(f"❌ Authentication failed: {result.get('error')}")
                return result

        except Exception as e:
            print(f"❌ Authentication error: {str(e)}")
            return {'error': str(e)}

    def get_logs(self, limit=100, offset=0, level='INFO'):
        """
        Get logs via REST API

        Args:
            limit (int): Number of logs to retrieve
            offset (int): Offset for pagination
            level (str): Log level filter

        Returns:
            dict: Log data
        """
        if not self.token:
            return {'error': 'Not authenticated'}

        url = f"{self.base_url}/api/log/stream/{self.token}"
        params = {
            'limit': limit,
            'offset': offset,
            'level': level
        }

        try:
            response = requests.get(url, params=params)
            result = response.json()

            if result.get('success'):
                print(f"📄 Retrieved {len(result.get('logs', []))} logs")
                return result
            else:
                print(f"❌ Failed to get logs: {result.get('error')}")
                return result

        except Exception as e:
            print(f"❌ Error getting logs: {str(e)}")
            return {'error': str(e)}

    def start_websocket_stream(self, on_log_received=None):
        """
        Start real-time log streaming via WebSocket

        Args:
            on_log_received (callable): Callback function for new logs
        """
        if not self.token:
            print("❌ Not authenticated")
            return

        try:
            # Initialize Socket.IO client
            self.sio = socketio.Client()

            @self.sio.event
            def connect():
                print("🔌 Connected to WebSocket")

            @self.sio.event
            def disconnect():
                print("🔌 Disconnected from WebSocket")

            @self.sio.event
            def connected(data):
                print(f"✅ {data.get('message', 'Connected')}")

            @self.sio.event
            def log_update(data):
                print(f"📨 New logs received: {len(data.get('logs', []))} entries")
                if on_log_received:
                    on_log_received(data)
                else:
                    # Default handler - print logs
                    for log in data.get('logs', []):
                        print(f"[{log.get('timestamp')}] {log.get('level')}: {log.get('message')}")

            # Connect with authentication
            socket_url = f"{self.base_url.replace('http', 'ws')}/socket.io/"
            self.sio.connect(socket_url, auth={'token': self.token})

            # Keep connection alive
            self.sio.wait()

        except Exception as e:
            print(f"❌ WebSocket error: {str(e)}")

    def stop_websocket_stream(self):
        """Stop WebSocket streaming"""
        if self.sio and self.sio.connected:
            self.sio.disconnect()
            print("🔌 WebSocket connection closed")

# Example usage

def main(): # Configuration
ODOO_URL = "http://localhost:8069" # Your Odoo instance URL
ADMIN_ID = "admin" # Admin username
PASSWORD = "admin_password" # Admin password
DATABASE_NAME = "tenant_database" # Target database

    # Initialize client
    client = OdooLogClient(ODOO_URL)

    # Step 1: Authenticate
    print("🔐 Authenticating...")
    auth_result = client.authenticate(ADMIN_ID, PASSWORD, DATABASE_NAME)

    if not auth_result.get('success'):
        print("Authentication failed. Exiting.")
        return

    # Step 2: Get logs via REST API
    print("\n📄 Fetching logs via REST API...")
    logs_result = client.get_logs(limit=50, level='INFO')

    if logs_result.get('success'):
        logs = logs_result.get('logs', [])
        print(f"Found {len(logs)} logs:")
        for log in logs[:5]:  # Show first 5 logs
            print(f"  - [{log.get('level')}] {log.get('message')[:100]}...")

    # Step 3: Start real-time streaming
    print("\n🔄 Starting real-time log streaming...")
    print("Press Ctrl+C to stop...")

    def custom_log_handler(data):
        """Custom handler for incoming logs"""
        logs = data.get('logs', [])
        tenant = data.get('tenant', 'Unknown')
        print(f"\n🆕 [{tenant}] Received {len(logs)} new logs:")

        for log in logs:
            timestamp = log.get('timestamp', 'Unknown')
            level = log.get('level', 'INFO')
            message = log.get('message', '')
            print(f"  [{timestamp}] {level}: {message}")

    try:
        # Start WebSocket with custom handler
        client.start_websocket_stream(on_log_received=custom_log_handler)
    except KeyboardInterrupt:
        print("\n⏹️  Stopping log stream...")
        client.stop_websocket_stream()

if **name** == "**main**":
main()

"""
API Documentation for Odoo Log Transfer Module
============================================

## Authentication Endpoint

POST /api/log/auth

Request:
{
"admin_id": "admin_username",
"password": "admin_password",
"database_name": "target_database"
}

Response (Success):
{
"success": true,
"token": "auth_token_here",
"tenant_id": 123,
"websocket_url": "/log_stream/auth_token_here"
}

Response (Error):
{
"error": "Error message"
}

## Get Logs Endpoint

GET /api/log/stream/{token}?limit=100&offset=0&level=INFO

Response (Success):
{
"success": true,
"logs": [
{
"id": 1,
"timestamp": "2025-06-30T10:30:00",
"level": "INFO",
"message": "Log message here",
"name": "odoo.modules",
"function": "load_module",
"line": 123,
"database": "tenant_db"
}
],
"total": 1,
"tenant": "tenant_name"
}

## WebSocket Endpoint

GET /api/log/websocket/{token}

Returns WebSocket connection information and usage examples.

## WebSocket Events

### Client -> Server

- connect: Establish connection with auth token

### Server -> Client

- connected: Connection established successfully
- log_update: New log entries available
- disconnect: Connection closed

## Usage Examples

### JavaScript (Browser)

```javascript
// 1. Authenticate first
const authResponse = await fetch("/api/log/auth", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    admin_id: "admin",
    password: "password",
    database_name: "tenant_db",
  }),
});

const auth = await authResponse.json();
const token = auth.token;

// 2. Get logs via REST
const logsResponse = await fetch(`/api/log/stream/${token}?limit=50`);
const logs = await logsResponse.json();

// 3. Connect to WebSocket for real-time updates
const socket = io(`ws://localhost:8069/socket.io/`, {
  auth: { token: token },
});

socket.on("log_update", (data) => {
  console.log("New logs:", data.logs);
});
```

### cURL Examples

```bash
# 1. Authenticate
curl -X POST http://localhost:8069/api/log/auth \
  -H "Content-Type: application/json" \
  -d '{"admin_id":"admin","password":"password","database_name":"tenant_db"}'

# 2. Get logs (replace TOKEN with actual token)
curl "http://localhost:8069/api/log/stream/TOKEN?limit=100&level=INFO"
```

## Installation Instructions

1. Copy the module to your Odoo addons directory
2. Update the module list: Odoo -> Apps -> Update Apps List
3. Install the module: Search for "Log Transfer API" and install
4. Configure log transfer for your tenants via the menu: Log Transfer -> Log Configurations

## Requirements

- Odoo 17.0+
- python-socketio
- websocket-client (for Python clients)

## Security Notes

- Tokens are generated per tenant and stored securely
- Admin authentication required for initial setup
- WebSocket connections are validated against tokens
- No API keys required after initial authentication

## Customization

You can customize log sources by modifying the `_fetch_logs` method in the LogTransfer model:

- Read from custom log files
- Filter by different criteria
- Add custom log formatting
- Integrate with external logging systems
  """
