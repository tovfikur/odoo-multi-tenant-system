# factory.py
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_moment import Moment
from db import db  # Import db from db.py
from utils import error_tracker
from models import SaasUser  # Assuming SaasUser is defined in models.py
from billing import register_billing_routes
from flask_wtf.csrf import CSRFProtect

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL', 
        'postgresql://odoo_master:' + os.environ.get('ODOO_MASTER_PASSWORD', 'admin123') + '@postgres:5432/saas_manager'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    csrf = CSRFProtect(app)
    # Initialize SQLAlchemy with the app
    db.init_app(app)
    register_billing_routes(app, csrf)
    
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    
    # Define user_loader
    @login_manager.user_loader
    def load_user(user_id):
        try:
            return SaasUser.query.get(int(user_id))
        except Exception as e:
            error_tracker.log_error(e, {'user_id': user_id, 'function': 'load_user'})
            return None
    
    # Initialize Flask-Moment
    moment = Moment(app)
    
    return app, csrf

def init_db(app):
    with app.app_context():
        db.create_all()