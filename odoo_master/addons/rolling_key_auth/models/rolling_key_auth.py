import hashlib
import hmac
import time
import logging
from odoo import models, fields, api, http
from odoo.exceptions import AccessDenied

_logger = logging.getLogger(__name__)

class RollingKeyAuth(models.Model):
    _name = 'rolling.key.auth'
    _description = 'Rolling Key Authentication'
    
    name = fields.Char('Name', required=True)
    user_id = fields.Many2one('res.users', 'User', required=True)
    last_key_index = fields.Integer('Last Key Index', default=0)
    seed = fields.Char('Seed', required=True)
    is_active = fields.Boolean('Active', default=True)
    
    @api.model
    def generate_key(self, seed, index):
        """Generate a rolling key based on seed and index"""
        # Combine seed with index to create unique key
        combined = f"{seed}:{index}"
        # Use HMAC-SHA256 for secure key generation
        key = hmac.new(
            seed.encode('utf-8'),
            f"{index}:{int(time.time() // 300)}".encode('utf-8'),  # 5-minute window
            hashlib.sha256
        ).hexdigest()[:16]  # Take first 16 characters
        return key
    
    @api.model
    def verify_and_login(self, special_key, username=None):
        """Verify the special key and perform login"""
        try:
            # Find active auth records
            auth_records = self.search([('is_active', '=', True)])
            
            for auth_record in auth_records:
                # Check current and next possible keys (to handle slight timing differences)
                for offset in range(0, 3):  # Check current and next 2 keys
                    expected_key = self.generate_key(auth_record.seed, auth_record.last_key_index + offset)
                    
                    if expected_key == special_key:
                        # Key matches, update the index and perform login
                        auth_record.last_key_index += offset + 1
                        
                        # Get the user
                        user = auth_record.user_id
                        if user and user.active:
                            _logger.info(f"Rolling key authentication successful for user: {user.login}")
                            return user
                        else:
                            _logger.warning(f"User {user.login if user else 'Unknown'} is inactive")
                            break
            
            _logger.warning(f"Rolling key authentication failed for key: {special_key[:8]}...")
            return False
            
        except Exception as e:
            _logger.error(f"Error in rolling key authentication: {str(e)}")
            return False
