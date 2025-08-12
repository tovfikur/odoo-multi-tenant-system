import logging
import hashlib
import time
import urllib.parse
from odoo import http, api, SUPERUSER_ID
from odoo.http import request
from odoo.exceptions import AccessDenied

_logger = logging.getLogger(__name__)

class SSOController(http.Controller):

    @http.route('/sso/auth', type='http', auth="none", methods=['POST'], csrf=False)
    def sso_authenticate(self, **kwargs):
        """
        SSO Authentication endpoint that accepts credentials and returns a session
        """
        try:
            # Get parameters
            username = kwargs.get('username')
            password = kwargs.get('password') 
            database = kwargs.get('database')
            token = kwargs.get('token')
            
            if not all([username, password, database]):
                return self._error_response("Missing required parameters")
            
            _logger.info(f"SSO authentication attempt for {username} on database {database}")
            
            # Verify database exists  
            if database != request.db:
                return self._error_response(f"Database mismatch: expected {request.db}, got {database}")
            
            # Attempt authentication
            try:
                uid = request.session.authenticate(database, username, password)
                
                if uid:
                    _logger.info(f"SSO authentication successful for {username} (UID: {uid})")
                    
                    # Return success with redirect URL
                    return self._success_response({
                        'success': True,
                        'uid': uid,
                        'username': username,
                        'database': database,
                        'session_id': request.session.sid,
                        'redirect_url': '/web'
                    })
                else:
                    return self._error_response("Authentication failed: Invalid credentials")
                    
            except AccessDenied:
                return self._error_response("Authentication failed: Access denied")
                
        except Exception as e:
            _logger.error(f"SSO authentication error: {e}")
            return self._error_response(f"Internal error: {str(e)}")
    
    @http.route('/sso/login', type='http', auth="none", methods=['GET', 'POST'], csrf=False)  
    def sso_login_page(self, **kwargs):
        """
        SSO login page that accepts credentials via GET parameters and logs in
        """
        try:
            # Parse query string manually to handle passwords with & symbols
            query_string = request.httprequest.query_string.decode('utf-8')
            _logger.info(f"SSO login query string: {query_string}")
            _logger.info(f"SSO login request method: {request.httprequest.method}")
            _logger.info(f"SSO login kwargs: {kwargs}")
            _logger.info(f"SSO login request args: {request.httprequest.args}")
            
            # Parse parameters more carefully
            parsed_params = {}
            if query_string:
                # Split by & but be careful about password content
                parts = query_string.split('&')
                current_key = None
                current_value = ""
                
                for part in parts:
                    if '=' in part and not current_key:
                        key, value = part.split('=', 1)
                        parsed_params[key] = urllib.parse.unquote_plus(value)
                        if key == 'password':
                            current_key = key
                            current_value = parsed_params[key]
                    elif current_key == 'password' and 'database=' not in part:
                        # This is likely part of the password
                        current_value += '&' + part
                        parsed_params[current_key] = current_value
                    elif '=' in part:
                        current_key = None
                        key, value = part.split('=', 1)
                        parsed_params[key] = urllib.parse.unquote_plus(value)
                    elif current_key == 'password':
                        current_value += '&' + part
                        parsed_params[current_key] = current_value
            
            # Extract credentials with fallback to kwargs
            username = parsed_params.get('username') or kwargs.get('username') or kwargs.get('login')
            password = parsed_params.get('password') or kwargs.get('password')
            database = parsed_params.get('database') or kwargs.get('database') or kwargs.get('db')
            
            _logger.info(f"SSO login parsed - Username: {username}, Database: {database}, Password present: {bool(password)}")
            
            if username and password and database:
                _logger.info(f"SSO direct login attempt for {username} on {database}")
                
                # Verify this is the correct database
                if database == request.db:
                    try:
                        uid = request.session.authenticate(database, username, password)
                        
                        if uid:
                            _logger.info(f"SSO direct login successful for {username}")
                            # Redirect to main web interface
                            return request.redirect('/web')
                        else:
                            _logger.warning(f"SSO direct login failed for {username}")
                            return self._login_form(error="Invalid username or password")
                            
                    except Exception as e:
                        _logger.error(f"SSO direct login error: {e}")
                        return self._login_form(error=f"Login error: {str(e)}")
                else:
                    return self._login_form(error=f"Database mismatch")
            
            # Show login form if credentials not provided
            return self._login_form()
            
        except Exception as e:
            _logger.error(f"SSO login page error: {e}")
            return self._login_form(error=f"System error: {str(e)}")
    
    def _success_response(self, data):
        """Return JSON success response"""
        response = request.make_response(
            http.json.dumps(data), 
            headers=[('Content-Type', 'application/json')]
        )
        return response
    
    def _error_response(self, message):
        """Return JSON error response"""
        response = request.make_response(
            http.json.dumps({'success': False, 'error': message}),
            headers=[('Content-Type', 'application/json')]
        )
        response.status_code = 400
        return response
    
    def _login_form(self, error=None):
        """Return a simple login form for SSO"""
        error_html = f'<div style="color: red; margin: 10px 0;">{error}</div>' if error else ''
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>SSO Login - {request.db}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
                .form-container {{ max-width: 400px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .form-group {{ margin: 15px 0; }}
                label {{ display: block; margin-bottom: 5px; font-weight: bold; }}
                input {{ width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }}
                button {{ background: #007cba; color: white; padding: 12px 20px; border: none; border-radius: 4px; cursor: pointer; width: 100%; font-size: 16px; }}
                button:hover {{ background: #005a87; }}
                .error {{ color: red; margin: 10px 0; padding: 10px; background: #fee; border: 1px solid red; border-radius: 4px; }}
                .info {{ color: #666; margin: 10px 0; font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="form-container">
                <h2>SSO Login</h2>
                <div class="info">Database: <strong>{request.db}</strong></div>
                {error_html}
                <form method="post" action="/sso/login">
                    <div class="form-group">
                        <label>Username:</label>
                        <input type="text" name="username" required />
                    </div>
                    <div class="form-group">
                        <label>Password:</label>
                        <input type="password" name="password" required />
                    </div>
                    <input type="hidden" name="database" value="{request.db}" />
                    <button type="submit">Login</button>
                </form>
                <div class="info">
                    <p>This is an SSO authentication endpoint for the SaaS Manager.</p>
                </div>
            </div>
        </body>
        </html>
        """
        return html