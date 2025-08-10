# Email configuration management for SaaS Manager
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from models import SystemSetting

class EmailManager:
    """Centralized email management using SystemSetting for configuration"""
    
    @staticmethod
    def get_smtp_config():
        """Get SMTP configuration from SystemSetting model"""
        config = {}
        settings = {
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': '587',
            'smtp_username': '',
            'smtp_password': '',
            'smtp_use_tls': 'true',
            'email_from_name': 'SaaS Manager',
            'email_from_address': ''
        }
        
        for key, default in settings.items():
            setting = SystemSetting.query.filter_by(key=key).first()
            config[key] = setting.value if setting else default
            
        return config
    
    @staticmethod
    def send_email(to_email, subject, body, is_html=True):
        """Send email using configured SMTP settings"""
        try:
            config = EmailManager.get_smtp_config()
            
            if not config['smtp_username'] or not config['smtp_password']:
                raise Exception("SMTP credentials not configured in system settings")
            
            # Create message
            msg = MIMEMultipart('alternative' if is_html else 'mixed')
            msg['Subject'] = subject
            msg['From'] = f"{config['email_from_name']} <{config['email_from_address'] or config['smtp_username']}>"
            msg['To'] = to_email
            
            # Add body
            if is_html:
                msg.attach(MIMEText(body, 'html'))
            else:
                msg.attach(MIMEText(body, 'plain'))
            
            # Create SMTP session
            server = smtplib.SMTP(config['smtp_server'], int(config['smtp_port']))
            
            if config['smtp_use_tls'].lower() == 'true':
                server.starttls()
            
            server.login(config['smtp_username'], config['smtp_password'])
            server.send_message(msg)
            server.quit()
            
            return True, "Email sent successfully"
            
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def send_password_reset_email(user, reset_token):
        """Send password reset email to user"""
        from flask import url_for
        
        reset_url = url_for('reset_password', token=reset_token, _external=True)
        
        subject = "Password Reset Request"
        body = f"""
        <html>
        <body>
            <h2>Password Reset Request</h2>
            <p>Hello {user.username},</p>
            <p>You have requested to reset your password. Click the link below to reset it:</p>
            <p><a href="{reset_url}">Reset Password</a></p>
            <p>If you didn't request this, please ignore this email.</p>
            <p>This link will expire in 1 hour.</p>
        </body>
        </html>
        """
        
        return EmailManager.send_email(user.email, subject, body, is_html=True)
