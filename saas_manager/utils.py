# utils.py
import logging
import sys
import traceback
import inspect
from datetime import datetime
from functools import wraps
from werkzeug.routing import BuildError
class ErrorTracker:
    def __init__(self, logger):
        self.logger = logger
    
    def log_error(self, error, context=None, request_info=None):
        error_info = {
            'timestamp': datetime.utcnow().isoformat(),
            'error_type': type(error).__name__,
            'error_message': str(error),
            'context': context or {},
        }
        
        frame = inspect.currentframe()
        if frame and frame.f_back:
            caller_frame = frame.f_back
            error_info['caller_file'] = caller_frame.f_code.co_filename
            error_info['caller_function'] = caller_frame.f_code.co_name
            error_info['caller_line'] = caller_frame.f_lineno
        
        tb_lines = traceback.format_exception(type(error), error, error.__traceback__)
        error_info['full_traceback'] = ''.join(tb_lines)
        
        stack_trace = []
        for line in tb_lines:
            if 'File "' in line:
                stack_trace.append(line.strip())
        error_info['stack_trace'] = stack_trace
        
        if request_info:
            error_info['request'] = request_info
        
        self.logger.error(f"DETAILED ERROR REPORT: {error_info}")
        
        return error_info
    
    def get_request_info(self):
        try:
            from flask import request as current_request
            return {
                'method': current_request.method,
                'url': current_request.url,
                'endpoint': current_request.endpoint,
                'remote_addr': current_request.remote_addr,
                'user_agent': str(current_request.user_agent),
                'form_data': dict(current_request.form) if current_request.method == 'POST' else None,
                'args': dict(current_request.args)
            }
        except Exception:
            return None

def setup_enhanced_logging():
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(funcName)s() - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    return root_logger

logger = setup_enhanced_logging()
error_tracker = ErrorTracker(logger)

def track_errors(context_name=None):
    """Decorator to track errors in functions with detailed information"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                context = {
                    'function': func.__name__,
                    'context_name': context_name,
                    'args': str(args)[:200],
                    'kwargs': str(kwargs)[:200]
                }
                
                request_info = error_tracker.get_request_info()
                error_info = error_tracker.log_error(e, context, request_info)
                
                raise type(e)(f"Error in {func.__name__}: {str(e)}") from e
        return wrapper
    return decorator