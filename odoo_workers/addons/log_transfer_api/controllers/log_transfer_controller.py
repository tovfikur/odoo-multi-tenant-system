from odoo import http
from odoo.http import request

class LogTransferController(http.Controller):
    @http.route('/api/logs', type='json', auth='none', methods=['GET'])
    def get_logs(self, token, limit=100, offset=0, level='INFO', start_date=None, end_date=None):
        """Retrieve logs for a tenant via API endpoint.
        
        Args:
            token (str): Authentication token for the tenant.
            limit (int): Maximum number of log entries to return (default: 100).
            offset (int): Number of log entries to skip (default: 0).
            level (str): Minimum log level to filter by (default: 'INFO').
            start_date (str): ISO format start date for filtering logs (optional).
            end_date (str): ISO format end date for filtering logs (optional).
            
        Returns:
            dict: JSON response containing logs or error message.
        """
        if not token:
            return {'error': 'Token is required'}
        
        try:
            limit = int(limit)
            offset = int(offset)
        except ValueError:
            return {'error': 'Invalid limit or offset'}
        
        # Use sudo() since auth='none' means no user context; token validation ensures security
        log_transfer = request.env['log.transfer'].sudo()
        result = log_transfer.get_logs(
            token=token,
            limit=limit,
            offset=offset,
            level=level,
            start_date=start_date,
            end_date=end_date
        )
        return result