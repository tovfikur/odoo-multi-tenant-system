import json
import logging
from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.main import Home

_logger = logging.getLogger(__name__)

class RollingKeyAuthController(http.Controller):
    
    @http.route('/auth/rolling_key', type='http', auth='none', methods=['POST'], csrf=False)
    def rolling_key_login(self, **kwargs):
        """Handle rolling key authentication"""
        try:
            special_key = kwargs.get('special_key')
            username = kwargs.get('username')  # Optional, for additional verification
            
            if not special_key:
                return json.dumps({'error': 'Special key is required'})
            
            # Get the rolling key auth model
            auth_model = request.env['rolling.key.auth'].sudo()
            
            # Verify the key and get user
            user = auth_model.verify_and_login(special_key, username)
            
            if user:
                # Perform the login
                request.session.authenticate(request.session.db, user.login, None)
                
                # Redirect to the main page or dashboard
                redirect_url = '/web'
                if kwargs.get('redirect'):
                    redirect_url = kwargs.get('redirect')
                
                return request.redirect(redirect_url)
            else:
                return json.dumps({'error': 'Authentication failed'})
                
        except Exception as e:
            _logger.error(f"Rolling key authentication error: {str(e)}")
            return json.dumps({'error': 'Authentication error'})
    
    @http.route('/auth/rolling_key_json', type='json', auth='none', methods=['POST'], csrf=False)
    def rolling_key_login_json(self, special_key, username=None, **kwargs):
        """JSON endpoint for rolling key authentication"""
        try:
            if not special_key:
                return {'success': False, 'error': 'Special key is required'}
            
            # Get the rolling key auth model
            auth_model = request.env['rolling.key.auth'].sudo()
            
            # Verify the key and get user
            user = auth_model.verify_and_login(special_key, username)
            
            if user:
                # Perform the login
                request.session.authenticate(request.session.db, user.login, None)
                return {'success': True, 'user_id': user.id, 'username': user.login}
            else:
                return {'success': False, 'error': 'Authentication failed'}
                
        except Exception as e:
            _logger.error(f"Rolling key authentication error: {str(e)}")
            return {'success': False, 'error': 'Authentication error'}
