"""
Support and Communication API
Provides ticket management, support chat, and communication features
"""

import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from enum import Enum

from db import db
from models import SaasUser
from utils import track_errors
try:
    from user_notifications import (
        NotificationService, NotificationType, NotificationPriority
    )
except ImportError:
    # Fallback if notifications not available
    NotificationService = None
    NotificationType = None
    NotificationPriority = None

# Create blueprint for support API routes
support_api_bp = Blueprint('support_api', __name__)
logger = logging.getLogger(__name__)

class TicketStatus(Enum):
    """Support ticket status"""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_FOR_CUSTOMER = "waiting_for_customer"
    RESOLVED = "resolved"
    CLOSED = "closed"

class TicketPriority(Enum):
    """Support ticket priority"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class TicketCategory(Enum):
    """Support ticket categories"""
    TECHNICAL = "technical"
    BILLING = "billing"
    ACCOUNT = "account"
    FEATURE_REQUEST = "feature_request"
    BUG_REPORT = "bug_report"
    GENERAL = "general"

class SupportTicket(db.Model):
    """Support ticket model"""
    __tablename__ = 'api_support_tickets'
    
    id = db.Column(db.Integer, primary_key=True)
    ticket_number = db.Column(db.String(20), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('saas_users.id'), nullable=False)
    
    subject = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.Enum(TicketCategory), nullable=False, default=TicketCategory.GENERAL)
    priority = db.Column(db.Enum(TicketPriority), nullable=False, default=TicketPriority.MEDIUM)
    status = db.Column(db.Enum(TicketStatus), nullable=False, default=TicketStatus.OPEN)
    
    # Assignment
    assigned_to = db.Column(db.String(100))  # Support agent username/email
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)
    closed_at = db.Column(db.DateTime)
    
    # Metadata
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'))  # Optional tenant context
    extra_data = db.Column(db.JSON)  # Additional context data
    
    # Relationships
    user = db.relationship('SaasUser', backref='support_tickets')
    messages = db.relationship('TicketMessage', backref='ticket', cascade='all, delete-orphan')
    
    def to_dict(self):
        """Convert ticket to dictionary"""
        return {
            'id': self.id,
            'ticket_number': self.ticket_number,
            'subject': self.subject,
            'description': self.description,
            'category': self.category.value,
            'priority': self.priority.value,
            'status': self.status.value,
            'assigned_to': self.assigned_to,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
            'tenant_id': self.tenant_id,
            'metadata': self.extra_data,
            'message_count': len(self.messages) if self.messages else 0
        }

class TicketMessage(db.Model):
    """Support ticket message model"""
    __tablename__ = 'ticket_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('support_tickets.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('saas_users.id'))  # Null for support agent messages
    
    message = db.Column(db.Text, nullable=False)
    is_internal = db.Column(db.Boolean, default=False)  # Internal notes not visible to customer
    is_from_support = db.Column(db.Boolean, default=False)  # Message from support team
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # File attachments (stored as JSON array of file paths/URLs)
    attachments = db.Column(db.JSON)
    
    def to_dict(self):
        """Convert message to dictionary"""
        return {
            'id': self.id,
            'ticket_id': self.ticket_id,
            'message': self.message,
            'is_internal': self.is_internal,
            'is_from_support': self.is_from_support,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'attachments': self.attachments or []
        }

def require_user():
    """Decorator to require authenticated user access"""
    def decorator(f):
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({'success': False, 'error': 'Authentication required'}), 401
            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator

def generate_ticket_number():
    """Generate unique ticket number"""
    import secrets
    timestamp = datetime.utcnow().strftime('%Y%m%d')
    random_suffix = secrets.token_hex(3).upper()
    return f"TK-{timestamp}-{random_suffix}"

# ================= SUPPORT TICKET MANAGEMENT =================

@support_api_bp.route('/api/support/tickets', methods=['GET'])
@login_required
@require_user()
@track_errors('api_get_support_tickets')
def get_support_tickets():
    """Get user's support tickets"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        status = request.args.get('status')
        category = request.args.get('category')
        
        # Build query
        query = SupportTicket.query.filter_by(user_id=current_user.id)
        
        if status:
            try:
                status_enum = TicketStatus(status)
                query = query.filter_by(status=status_enum)
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid status'}), 400
        
        if category:
            try:
                category_enum = TicketCategory(category)
                query = query.filter_by(category=category_enum)
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid category'}), 400
        
        # Paginate
        tickets_paginated = query.order_by(
            SupportTicket.updated_at.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)
        
        tickets_data = [ticket.to_dict() for ticket in tickets_paginated.items]
        
        return jsonify({
            'success': True,
            'tickets': tickets_data,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': tickets_paginated.total,
                'pages': tickets_paginated.pages,
                'has_next': tickets_paginated.has_next,
                'has_prev': tickets_paginated.has_prev
            }
        })
        
    except Exception as e:
        logger.error(f"Get support tickets failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to get support tickets'}), 500

@support_api_bp.route('/api/support/tickets', methods=['POST'])
@login_required
@require_user()
@track_errors('api_create_support_ticket')
def create_support_ticket():
    """Create a new support ticket"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        subject = data.get('subject')
        description = data.get('description')
        category = data.get('category', 'general')
        priority = data.get('priority', 'medium')
        tenant_id = data.get('tenant_id')
        
        if not subject or not description:
            return jsonify({
                'success': False,
                'error': 'Subject and description are required'
            }), 400
        
        # Validate category and priority
        try:
            category_enum = TicketCategory(category)
            priority_enum = TicketPriority(priority)
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid category or priority'}), 400
        
        # Generate ticket number
        ticket_number = generate_ticket_number()
        
        # Ensure unique ticket number
        while SupportTicket.query.filter_by(ticket_number=ticket_number).first():
            ticket_number = generate_ticket_number()
        
        # Create ticket
        ticket = SupportTicket(
            ticket_number=ticket_number,
            user_id=current_user.id,
            subject=subject,
            description=description,
            category=category_enum,
            priority=priority_enum,
            tenant_id=tenant_id,
            extra_data=data.get('metadata', {})
        )
        
        db.session.add(ticket)
        db.session.commit()
        
        # Send notification to user if available
        if NotificationService:
            try:
                notification_service = NotificationService()
                notification_service.create_notification(
                    user_id=current_user.id,
                    title="Support Ticket Created",
                    message=f"Your support ticket #{ticket_number} has been created. We'll get back to you soon!",
                    notification_type=NotificationType.SUCCESS,
                    priority=NotificationPriority.MEDIUM,
                    action_url=f"/support/ticket/{ticket.id}",
                    action_label="View Ticket",
                    metadata={
                        'ticket_id': ticket.id,
                        'ticket_number': ticket_number
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to send notification: {e}")
        
        logger.info(f"Support ticket {ticket_number} created by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'Support ticket created successfully',
            'ticket': ticket.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Create support ticket failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to create support ticket'}), 500

@support_api_bp.route('/api/support/tickets/<int:ticket_id>', methods=['GET'])
@login_required
@require_user()
@track_errors('api_get_support_ticket')
def get_support_ticket(ticket_id):
    """Get specific support ticket with messages"""
    try:
        ticket = SupportTicket.query.filter_by(
            id=ticket_id,
            user_id=current_user.id
        ).first()
        
        if not ticket:
            return jsonify({'success': False, 'error': 'Ticket not found'}), 404
        
        # Get ticket messages (exclude internal notes)
        messages = TicketMessage.query.filter_by(
            ticket_id=ticket_id,
            is_internal=False
        ).order_by(TicketMessage.created_at.asc()).all()
        
        ticket_data = ticket.to_dict()
        ticket_data['messages'] = [msg.to_dict() for msg in messages]
        
        return jsonify({
            'success': True,
            'ticket': ticket_data
        })
        
    except Exception as e:
        logger.error(f"Get support ticket failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to get support ticket'}), 500

@support_api_bp.route('/api/support/tickets/<int:ticket_id>/messages', methods=['POST'])
@login_required
@require_user()
@track_errors('api_add_ticket_message')
def add_ticket_message(ticket_id):
    """Add a message to support ticket"""
    try:
        ticket = SupportTicket.query.filter_by(
            id=ticket_id,
            user_id=current_user.id
        ).first()
        
        if not ticket:
            return jsonify({'success': False, 'error': 'Ticket not found'}), 404
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        message_text = data.get('message')
        if not message_text:
            return jsonify({'success': False, 'error': 'Message is required'}), 400
        
        # Create message
        message = TicketMessage(
            ticket_id=ticket_id,
            user_id=current_user.id,
            message=message_text,
            is_from_support=False,
            attachments=data.get('attachments', [])
        )
        
        db.session.add(message)
        
        # Update ticket status if it was waiting for customer
        if ticket.status == TicketStatus.WAITING_FOR_CUSTOMER:
            ticket.status = TicketStatus.OPEN
        
        ticket.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Send notification to support team (mock)
        logger.info(f"New message added to ticket {ticket.ticket_number} by customer")
        
        return jsonify({
            'success': True,
            'message': 'Message added successfully',
            'ticket_message': message.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Add ticket message failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to add message'}), 500

@support_api_bp.route('/api/support/tickets/<int:ticket_id>/close', methods=['POST'])
@login_required
@require_user()
@track_errors('api_close_support_ticket')
def close_support_ticket(ticket_id):
    """Close a support ticket"""
    try:
        ticket = SupportTicket.query.filter_by(
            id=ticket_id,
            user_id=current_user.id
        ).first()
        
        if not ticket:
            return jsonify({'success': False, 'error': 'Ticket not found'}), 404
        
        if ticket.status == TicketStatus.CLOSED:
            return jsonify({'success': False, 'error': 'Ticket is already closed'}), 400
        
        # Close ticket
        ticket.status = TicketStatus.CLOSED
        ticket.closed_at = datetime.utcnow()
        ticket.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Send confirmation notification if available
        if NotificationService:
            try:
                notification_service = NotificationService()
                notification_service.create_notification(
                    user_id=current_user.id,
                    title="Support Ticket Closed",
                    message=f"Your support ticket #{ticket.ticket_number} has been closed.",
                    notification_type=NotificationType.INFO,
                    priority=NotificationPriority.LOW,
                    metadata={
                        'ticket_id': ticket.id,
                        'ticket_number': ticket.ticket_number
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to send notification: {e}")
        
        logger.info(f"Support ticket {ticket.ticket_number} closed by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'Ticket closed successfully',
            'ticket': ticket.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Close support ticket failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to close ticket'}), 500

# ================= SUPPORT SYSTEM INFORMATION =================

@support_api_bp.route('/api/support/categories', methods=['GET'])
@track_errors('api_get_support_categories')
def get_support_categories():
    """Get available support categories"""
    try:
        categories = [
            {
                'id': cat.value,
                'name': cat.value.replace('_', ' ').title(),
                'description': {
                    'technical': 'Technical issues, bugs, and system problems',
                    'billing': 'Billing questions, payment issues, and subscriptions',
                    'account': 'Account settings, access, and user management',
                    'feature_request': 'Suggestions for new features or improvements',
                    'bug_report': 'Report bugs and unexpected behavior',
                    'general': 'General questions and other inquiries'
                }.get(cat.value, '')
            }
            for cat in TicketCategory
        ]
        
        return jsonify({
            'success': True,
            'categories': categories
        })
        
    except Exception as e:
        logger.error(f"Get support categories failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to get categories'}), 500

@support_api_bp.route('/api/support/priorities', methods=['GET'])
@track_errors('api_get_support_priorities')
def get_support_priorities():
    """Get available support priorities"""
    try:
        priorities = [
            {
                'id': pri.value,
                'name': pri.value.title(),
                'description': {
                    'low': 'General questions, non-urgent issues',
                    'medium': 'Standard issues affecting normal operation',
                    'high': 'Important issues affecting business operations',
                    'urgent': 'Critical issues requiring immediate attention'
                }.get(pri.value, ''),
                'response_time': {
                    'low': '48 hours',
                    'medium': '24 hours',
                    'high': '4 hours',
                    'urgent': '1 hour'
                }.get(pri.value, '')
            }
            for pri in TicketPriority
        ]
        
        return jsonify({
            'success': True,
            'priorities': priorities
        })
        
    except Exception as e:
        logger.error(f"Get support priorities failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to get priorities'}), 500

@support_api_bp.route('/api/support/stats', methods=['GET'])
@login_required
@require_user()
@track_errors('api_get_support_stats')
def get_support_stats():
    """Get user's support ticket statistics"""
    try:
        total_tickets = SupportTicket.query.filter_by(user_id=current_user.id).count()
        open_tickets = SupportTicket.query.filter_by(
            user_id=current_user.id,
            status=TicketStatus.OPEN
        ).count()
        resolved_tickets = SupportTicket.query.filter_by(
            user_id=current_user.id,
            status=TicketStatus.RESOLVED
        ).count()
        closed_tickets = SupportTicket.query.filter_by(
            user_id=current_user.id,
            status=TicketStatus.CLOSED
        ).count()
        
        # Get recent activity
        recent_tickets = SupportTicket.query.filter_by(
            user_id=current_user.id
        ).order_by(
            SupportTicket.updated_at.desc()
        ).limit(5).all()
        
        stats = {
            'total_tickets': total_tickets,
            'open_tickets': open_tickets,
            'resolved_tickets': resolved_tickets,
            'closed_tickets': closed_tickets,
            'recent_tickets': [ticket.to_dict() for ticket in recent_tickets]
        }
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        logger.error(f"Get support stats failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to get support stats'}), 500

# ================= SUPPORT CHAT (MOCK IMPLEMENTATION) =================

@support_api_bp.route('/api/support/chat/available', methods=['GET'])
@track_errors('api_chat_availability')
def get_chat_availability():
    """Check if support chat is available"""
    try:
        # Mock implementation - in reality, this would check agent availability
        from datetime import time
        current_time = datetime.utcnow().time()
        business_hours = time(9, 0) <= current_time <= time(17, 0)  # 9 AM - 5 PM UTC
        
        return jsonify({
            'success': True,
            'available': business_hours,
            'message': 'Live chat is available during business hours (9 AM - 5 PM UTC)' if business_hours else 'Live chat is currently unavailable. Please submit a ticket for assistance.',
            'business_hours': {
                'start': '09:00 UTC',
                'end': '17:00 UTC',
                'timezone': 'UTC'
            }
        })
        
    except Exception as e:
        logger.error(f"Get chat availability failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to check chat availability'}), 500

# ================= KNOWLEDGE BASE =================

@support_api_bp.route('/api/support/knowledge-base', methods=['GET'])
@track_errors('api_get_knowledge_base')
def get_knowledge_base():
    """Get knowledge base articles"""
    try:
        # Mock knowledge base articles
        articles = [
            {
                'id': 1,
                'title': 'Getting Started with Your Tenant',
                'summary': 'Learn how to set up and configure your new tenant',
                'category': 'getting-started',
                'views': 1250,
                'helpful_votes': 95,
                'updated_at': '2024-01-15T10:30:00Z'
            },
            {
                'id': 2,
                'title': 'Managing User Access and Permissions',
                'summary': 'How to invite users and manage their access levels',
                'category': 'user-management',
                'views': 820,
                'helpful_votes': 78,
                'updated_at': '2024-01-12T14:20:00Z'
            },
            {
                'id': 3,
                'title': 'Billing and Subscription Management',
                'summary': 'Understanding plans, billing cycles, and payments',
                'category': 'billing',
                'views': 650,
                'helpful_votes': 85,
                'updated_at': '2024-01-10T09:15:00Z'
            },
            {
                'id': 4,
                'title': 'Backup and Data Export',
                'summary': 'How to backup your data and export information',
                'category': 'data-management',
                'views': 420,
                'helpful_votes': 72,
                'updated_at': '2024-01-08T16:45:00Z'
            }
        ]
        
        search_query = request.args.get('search', '').lower()
        category = request.args.get('category')
        
        filtered_articles = articles
        
        if search_query:
            filtered_articles = [
                article for article in articles
                if search_query in article['title'].lower() or 
                   search_query in article['summary'].lower()
            ]
        
        if category:
            filtered_articles = [
                article for article in filtered_articles
                if article['category'] == category
            ]
        
        return jsonify({
            'success': True,
            'articles': filtered_articles,
            'total': len(filtered_articles)
        })
        
    except Exception as e:
        logger.error(f"Get knowledge base failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to get knowledge base'}), 500

# Export blueprint
__all__ = ['support_api_bp', 'SupportTicket', 'TicketMessage']