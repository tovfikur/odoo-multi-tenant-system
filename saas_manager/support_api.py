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
from models import (
    SaasUser, 
    SupportTicket as ExistingSupportTicket, 
    SupportReply as ExistingTicketMessage,
    Tenant
)
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

# Enhanced Enums for Support System
class TicketStatus(Enum):
    """Support ticket status - Enhanced from existing"""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_FOR_CUSTOMER = "waiting_for_customer"
    RESOLVED = "resolved"
    CLOSED = "closed"

class TicketPriority(Enum):
    """Support ticket priority - Enhanced from existing"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class TicketCategory(Enum):
    """Support ticket categories - New functionality"""
    TECHNICAL = "technical"
    BILLING = "billing"
    ACCOUNT = "account"
    FEATURE_REQUEST = "feature_request"
    BUG_REPORT = "bug_report"
    GENERAL = "general"

# Enhanced Support Ticket Model (extending existing functionality)
class ApiSupportTicket(db.Model):
    """Enhanced Support ticket model for API"""
    __tablename__ = 'api_support_tickets'
    
    id = db.Column(db.Integer, primary_key=True)
    ticket_number = db.Column(db.String(20), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('saas_users.id'), nullable=False)
    
    # Enhanced fields from API requirements
    subject = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.Enum(TicketCategory), nullable=False, default=TicketCategory.GENERAL)
    priority = db.Column(db.Enum(TicketPriority), nullable=False, default=TicketPriority.MEDIUM)
    status = db.Column(db.Enum(TicketStatus), nullable=False, default=TicketStatus.OPEN)
    
    # Assignment and management
    assigned_to = db.Column(db.String(100))  # Support agent username/email
    admin_notes = db.Column(db.Text)  # From existing model
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)
    closed_at = db.Column(db.DateTime)
    
    # Additional context and metadata
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'))
    extra_data = db.Column(db.JSON)  # Additional context data
    
    # Relationships
    user = db.relationship('SaasUser', backref='api_support_tickets')
    tenant = db.relationship('Tenant', backref='api_support_tickets')
    messages = db.relationship('ApiTicketMessage', backref='api_ticket', cascade='all, delete-orphan')
    
    def to_dict(self, include_messages=False):
        """Enhanced to_dict with flexible message inclusion"""
        ticket_data = {
            'id': self.id,
            'ticket_number': self.ticket_number,
            'subject': self.subject,
            'description': self.description,
            'category': self.category.value if self.category else 'general',
            'priority': self.priority.value if self.priority else 'medium',
            'status': self.status.value if self.status else 'open',
            'assigned_to': self.assigned_to,
            'admin_notes': self.admin_notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
            'tenant_id': self.tenant_id,
            'tenant_name': self.tenant.name if self.tenant else None,
            'user_email': self.user.email if self.user else None,
            'metadata': self.extra_data,
            'message_count': len(self.messages) if self.messages else 0
        }
        
        if include_messages:
            ticket_data['messages'] = [msg.to_dict() for msg in self.messages if not msg.is_internal]
        
        return ticket_data

class ApiTicketMessage(db.Model):
    """Enhanced ticket message model for API"""
    __tablename__ = 'api_ticket_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('api_support_tickets.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('saas_users.id'))  # Null for support agent messages
    
    message = db.Column(db.Text, nullable=False)
    is_internal = db.Column(db.Boolean, default=False)  # Internal notes not visible to customer
    is_from_support = db.Column(db.Boolean, default=False)  # Message from support team
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # File attachments (stored as JSON array of file paths/URLs)
    attachments = db.Column(db.JSON)
    
    # Relationships
    user = db.relationship('SaasUser', backref='api_ticket_messages')
    
    def to_dict(self):
        """Convert message to dictionary"""
        return {
            'id': self.id,
            'ticket_id': self.ticket_id,
            'message': self.message,
            'is_internal': self.is_internal,
            'is_from_support': self.is_from_support,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'attachments': self.attachments or [],
            'author_email': self.user.email if self.user else 'Support Team'
        }

# Helper Functions
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

def get_or_create_api_ticket(existing_ticket_id=None):
    """Helper to get or migrate existing ticket to API format"""
    if existing_ticket_id:
        # Check if already migrated
        api_ticket = ApiSupportTicket.query.filter_by(id=existing_ticket_id).first()
        if api_ticket:
            return api_ticket
            
        # Get existing ticket and create API version
        existing_ticket = ExistingSupportTicket.query.get(existing_ticket_id)
        if existing_ticket:
            # Migrate to API format
            api_ticket = ApiSupportTicket(
                id=existing_ticket.id,
                ticket_number=generate_ticket_number(),
                user_id=existing_ticket.user_id,
                subject=existing_ticket.subject,
                description=existing_ticket.message,
                priority=getattr(TicketPriority, existing_ticket.priority.upper(), TicketPriority.MEDIUM),
                status=getattr(TicketStatus, existing_ticket.status.upper(), TicketStatus.OPEN),
                admin_notes=existing_ticket.admin_notes,
                created_at=existing_ticket.created_at,
                updated_at=existing_ticket.updated_at
            )
            
            # Migrate existing replies to API messages
            for reply in existing_ticket.replies:
                api_message = ApiTicketMessage(
                    ticket_id=api_ticket.id,
                    user_id=reply.user_id,
                    message=reply.message,
                    is_from_support=reply.is_admin,
                    created_at=reply.created_at
                )
                api_ticket.messages.append(api_message)
            
            return api_ticket
    return None

# ================= SUPPORT TICKET MANAGEMENT =================

@support_api_bp.route('/api/support/tickets', methods=['GET'])
@login_required
@require_user()
@track_errors('api_get_support_tickets')
def get_support_tickets():
    """Get user's support tickets (both existing and API tickets)"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        status = request.args.get('status')
        category = request.args.get('category')
        include_legacy = request.args.get('include_legacy', 'true').lower() == 'true'
        
        tickets_data = []
        total_count = 0
        
        # Get API tickets
        api_query = ApiSupportTicket.query.filter_by(user_id=current_user.id)
        
        if status:
            try:
                status_enum = TicketStatus(status)
                api_query = api_query.filter_by(status=status_enum)
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid status'}), 400
        
        if category:
            try:
                category_enum = TicketCategory(category)
                api_query = api_query.filter_by(category=category_enum)
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid category'}), 400
        
        api_tickets = api_query.order_by(ApiSupportTicket.updated_at.desc()).all()
        tickets_data.extend([ticket.to_dict() for ticket in api_tickets])
        total_count += len(api_tickets)
        
        # Include legacy tickets if requested
        if include_legacy:
            legacy_query = ExistingSupportTicket.query.filter_by(user_id=current_user.id)
            if status:
                legacy_query = legacy_query.filter_by(status=status)
            
            legacy_tickets = legacy_query.order_by(ExistingSupportTicket.updated_at.desc()).all()
            for ticket in legacy_tickets:
                # Convert legacy ticket format
                legacy_data = ticket.to_dict()
                legacy_data['ticket_number'] = f"LEG-{ticket.id}"
                legacy_data['category'] = 'general'
                legacy_data['description'] = ticket.message
                legacy_data['is_legacy'] = True
                tickets_data.append(legacy_data)
            total_count += len(legacy_tickets)
        
        # Sort combined results by updated_at
        tickets_data.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
        
        # Manual pagination for combined results
        start = (page - 1) * per_page
        end = start + per_page
        paginated_tickets = tickets_data[start:end]
        
        return jsonify({
            'success': True,
            'tickets': paginated_tickets,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_count,
                'pages': (total_count + per_page - 1) // per_page,
                'has_next': end < total_count,
                'has_prev': page > 1
            },
            'stats': {
                'api_tickets': len(api_tickets),
                'legacy_tickets': len(legacy_tickets) if include_legacy else 0,
                'total': total_count
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
        
        # Validate tenant_id if provided
        if tenant_id:
            tenant = Tenant.query.get(tenant_id)
            if not tenant:
                return jsonify({'success': False, 'error': 'Invalid tenant ID'}), 400
            # Check if user has access to this tenant
            from models import TenantUser
            tenant_user = TenantUser.query.filter_by(
                tenant_id=tenant_id, 
                user_id=current_user.id
            ).first()
            if not tenant_user:
                return jsonify({'success': False, 'error': 'Access denied to specified tenant'}), 403
        
        # Generate unique ticket number
        ticket_number = generate_ticket_number()
        while ApiSupportTicket.query.filter_by(ticket_number=ticket_number).first():
            ticket_number = generate_ticket_number()
        
        # Create API ticket
        ticket = ApiSupportTicket(
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
                        'ticket_number': ticket_number,
                        'tenant_id': tenant_id
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to send notification: {e}")
        
        logger.info(f"API support ticket {ticket_number} created by user {current_user.id}")
        
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
        # Try to get API ticket first
        ticket = ApiSupportTicket.query.filter_by(
            id=ticket_id,
            user_id=current_user.id
        ).first()
        
        if ticket:
            return jsonify({
                'success': True,
                'ticket': ticket.to_dict(include_messages=True),
                'ticket_type': 'api'
            })
        
        # Fallback to legacy ticket
        legacy_ticket = ExistingSupportTicket.query.filter_by(
            id=ticket_id,
            user_id=current_user.id
        ).first()
        
        if not legacy_ticket:
            return jsonify({'success': False, 'error': 'Ticket not found'}), 404
        
        # Convert legacy ticket to API format for response
        ticket_data = legacy_ticket.to_dict()
        ticket_data['ticket_number'] = f"LEG-{legacy_ticket.id}"
        ticket_data['category'] = 'general'
        ticket_data['description'] = legacy_ticket.message
        ticket_data['is_legacy'] = True
        ticket_data['messages'] = [reply.to_dict() for reply in legacy_ticket.replies]
        
        return jsonify({
            'success': True,
            'ticket': ticket_data,
            'ticket_type': 'legacy'
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
        # Try API ticket first
        ticket = ApiSupportTicket.query.filter_by(
            id=ticket_id,
            user_id=current_user.id
        ).first()
        
        if not ticket:
            # Try legacy ticket
            legacy_ticket = ExistingSupportTicket.query.filter_by(
                id=ticket_id,
                user_id=current_user.id
            ).first()
            
            if not legacy_ticket:
                return jsonify({'success': False, 'error': 'Ticket not found'}), 404
            
            # Handle legacy ticket message
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'error': 'JSON data required'}), 400
            
            message_text = data.get('message')
            if not message_text:
                return jsonify({'success': False, 'error': 'Message is required'}), 400
            
            # Create legacy reply
            from models import SupportReply
            reply = SupportReply(
                ticket_id=ticket_id,
                user_id=current_user.id,
                message=message_text,
                is_admin=False
            )
            
            db.session.add(reply)
            legacy_ticket.updated_at = datetime.utcnow()
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Message added to legacy ticket successfully',
                'ticket_message': reply.to_dict(),
                'ticket_type': 'legacy'
            })
        
        # Handle API ticket message
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        message_text = data.get('message')
        if not message_text:
            return jsonify({'success': False, 'error': 'Message is required'}), 400
        
        # Create API message
        message = ApiTicketMessage(
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
        
        # Send notification to support team
        logger.info(f"New message added to API ticket {ticket.ticket_number} by customer")
        
        return jsonify({
            'success': True,
            'message': 'Message added successfully',
            'ticket_message': message.to_dict(),
            'ticket_type': 'api'
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
        # Try API ticket first
        ticket = ApiSupportTicket.query.filter_by(
            id=ticket_id,
            user_id=current_user.id
        ).first()
        
        if ticket:
            if ticket.status == TicketStatus.CLOSED:
                return jsonify({'success': False, 'error': 'Ticket is already closed'}), 400
            
            # Close API ticket
            ticket.status = TicketStatus.CLOSED
            ticket.closed_at = datetime.utcnow()
            ticket.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            # Send confirmation notification
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
            
            logger.info(f"API support ticket {ticket.ticket_number} closed by user {current_user.id}")
            
            return jsonify({
                'success': True,
                'message': 'Ticket closed successfully',
                'ticket': ticket.to_dict(),
                'ticket_type': 'api'
            })
        
        # Try legacy ticket
        legacy_ticket = ExistingSupportTicket.query.filter_by(
            id=ticket_id,
            user_id=current_user.id
        ).first()
        
        if not legacy_ticket:
            return jsonify({'success': False, 'error': 'Ticket not found'}), 404
        
        if legacy_ticket.status == 'closed':
            return jsonify({'success': False, 'error': 'Ticket is already closed'}), 400
        
        # Close legacy ticket
        legacy_ticket.status = 'closed'
        legacy_ticket.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        logger.info(f"Legacy support ticket {legacy_ticket.id} closed by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'Legacy ticket closed successfully',
            'ticket': legacy_ticket.to_dict(),
            'ticket_type': 'legacy'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Close support ticket failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to close ticket'}), 500

# ================= MIGRATION ENDPOINT =================

@support_api_bp.route('/api/support/tickets/<int:ticket_id>/migrate', methods=['POST'])
@login_required
@require_user()
@track_errors('api_migrate_support_ticket')
def migrate_legacy_ticket(ticket_id):
    """Migrate legacy ticket to API format"""
    try:
        # Check if already an API ticket
        if ApiSupportTicket.query.filter_by(id=ticket_id, user_id=current_user.id).first():
            return jsonify({'success': False, 'error': 'Ticket is already in API format'}), 400
        
        # Get legacy ticket
        legacy_ticket = ExistingSupportTicket.query.filter_by(
            id=ticket_id,
            user_id=current_user.id
        ).first()
        
        if not legacy_ticket:
            return jsonify({'success': False, 'error': 'Legacy ticket not found'}), 404
        
        # Create API ticket
        api_ticket = ApiSupportTicket(
            ticket_number=generate_ticket_number(),
            user_id=legacy_ticket.user_id,
            subject=legacy_ticket.subject,
            description=legacy_ticket.message,
            priority=getattr(TicketPriority, legacy_ticket.priority.upper(), TicketPriority.MEDIUM),
            status=getattr(TicketStatus, legacy_ticket.status.upper(), TicketStatus.OPEN),
            admin_notes=legacy_ticket.admin_notes,
            created_at=legacy_ticket.created_at,
            updated_at=legacy_ticket.updated_at,
            category=TicketCategory.GENERAL
        )
        
        db.session.add(api_ticket)
        db.session.flush()  # Get the ID
        
        # Migrate replies to messages
        for reply in legacy_ticket.replies:
            api_message = ApiTicketMessage(
                ticket_id=api_ticket.id,
                user_id=reply.user_id,
                message=reply.message,
                is_from_support=reply.is_admin,
                created_at=reply.created_at
            )
            db.session.add(api_message)
        
        db.session.commit()
        
        logger.info(f"Legacy ticket {ticket_id} migrated to API ticket {api_ticket.ticket_number}")
        
        return jsonify({
            'success': True,
            'message': 'Ticket migrated successfully',
            'api_ticket': api_ticket.to_dict(include_messages=True),
            'legacy_ticket_id': ticket_id
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Migrate support ticket failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to migrate ticket'}), 500

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
    """Get user's support ticket statistics (combined API and legacy)"""
    try:
        # API ticket stats
        api_tickets = ApiSupportTicket.query.filter_by(user_id=current_user.id)
        api_total = api_tickets.count()
        api_open = api_tickets.filter_by(status=TicketStatus.OPEN).count()
        api_resolved = api_tickets.filter_by(status=TicketStatus.RESOLVED).count()
        api_closed = api_tickets.filter_by(status=TicketStatus.CLOSED).count()
        
        # Legacy ticket stats
        legacy_tickets = ExistingSupportTicket.query.filter_by(user_id=current_user.id)
        legacy_total = legacy_tickets.count()
        legacy_open = legacy_tickets.filter_by(status='open').count()
        legacy_closed = legacy_tickets.filter_by(status='closed').count()
        
        # Combined stats
        total_tickets = api_total + legacy_total
        open_tickets = api_open + legacy_open
        resolved_tickets = api_resolved
        closed_tickets = api_closed + legacy_closed
        
        # Get recent activity (combined)
        recent_api_tickets = api_tickets.order_by(
            ApiSupportTicket.updated_at.desc()
        ).limit(3).all()
        
        recent_legacy_tickets = legacy_tickets.order_by(
            ExistingSupportTicket.updated_at.desc()
        ).limit(2).all()
        
        recent_tickets_data = []
        
        # Add API tickets
        for ticket in recent_api_tickets:
            recent_tickets_data.append({
                **ticket.to_dict(),
                'ticket_type': 'api'
            })
        
        # Add legacy tickets
        for ticket in recent_legacy_tickets:
            ticket_data = ticket.to_dict()
            ticket_data.update({
                'ticket_number': f"LEG-{ticket.id}",
                'category': 'general',
                'description': ticket.message,
                'is_legacy': True,
                'ticket_type': 'legacy'
            })
            recent_tickets_data.append(ticket_data)
        
        # Sort by updated_at
        recent_tickets_data.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
        recent_tickets_data = recent_tickets_data[:5]  # Limit to 5 most recent
        
        stats = {
            'total_tickets': total_tickets,
            'open_tickets': open_tickets,
            'resolved_tickets': resolved_tickets,
            'closed_tickets': closed_tickets,
            'recent_tickets': recent_tickets_data,
            'breakdown': {
                'api_tickets': {
                    'total': api_total,
                    'open': api_open,
                    'resolved': api_resolved,
                    'closed': api_closed
                },
                'legacy_tickets': {
                    'total': legacy_total,
                    'open': legacy_open,
                    'closed': legacy_closed
                }
            }
        }
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        logger.error(f"Get support stats failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to get support stats'}), 500

# ================= SUPPORT CHAT (ENHANCED IMPLEMENTATION) =================

@support_api_bp.route('/api/support/chat/available', methods=['GET'])
@track_errors('api_chat_availability')
def get_chat_availability():
    """Check if support chat is available"""
    try:
        from datetime import time
        current_time = datetime.utcnow().time()
        business_hours = time(9, 0) <= current_time <= time(17, 0)  # 9 AM - 5 PM UTC
        
        # Check if there are support agents online (mock implementation)
        agents_online = 2  # This would be dynamic in a real implementation
        
        return jsonify({
            'success': True,
            'available': business_hours and agents_online > 0,
            'agents_online': agents_online,
            'message': 'Live chat is available during business hours (9 AM - 5 PM UTC)' if business_hours else 'Live chat is currently unavailable. Please submit a ticket for assistance.',
            'business_hours': {
                'start': '09:00 UTC',
                'end': '17:00 UTC',
                'timezone': 'UTC'
            },
            'average_response_time': '5 minutes',
            'queue_position': None if business_hours else None
        })
        
    except Exception as e:
        logger.error(f"Get chat availability failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to check chat availability'}), 500

@support_api_bp.route('/api/support/chat/session', methods=['POST'])
@login_required
@require_user()
@track_errors('api_start_chat_session')
def start_chat_session():
    """Start a new support chat session"""
    try:
        data = request.get_json() or {}
        
        # Check if chat is available
        from datetime import time
        current_time = datetime.utcnow().time()
        business_hours = time(9, 0) <= current_time <= time(17, 0)
        
        if not business_hours:
            return jsonify({
                'success': False,
                'error': 'Chat is not available outside business hours',
                'alternative': 'Please create a support ticket instead'
            }), 400
        
        # Create a chat session (in a real implementation, this would integrate with a chat system)
        session_id = f"CHAT-{datetime.utcnow().strftime('%Y%m%d')}-{current_user.id}"
        
        # Mock chat session data
        chat_session = {
            'session_id': session_id,
            'user_id': current_user.id,
            'user_email': current_user.email,
            'status': 'waiting',
            'queue_position': 1,
            'estimated_wait_time': '2-3 minutes',
            'started_at': datetime.utcnow().isoformat(),
            'topic': data.get('topic', 'General Support'),
            'priority': data.get('priority', 'medium')
        }
        
        logger.info(f"Chat session {session_id} started for user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'Chat session started',
            'chat_session': chat_session
        })
        
    except Exception as e:
        logger.error(f"Start chat session failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to start chat session'}), 500

# ================= KNOWLEDGE BASE =================

@support_api_bp.route('/api/support/knowledge-base', methods=['GET'])
@track_errors('api_get_knowledge_base')
def get_knowledge_base():
    """Get knowledge base articles"""
    try:
        search_query = request.args.get('search', '').lower()
        category = request.args.get('category')
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 50)
        
        # Enhanced mock knowledge base articles
        all_articles = [
            {
                'id': 1,
                'title': 'Getting Started with Your Tenant',
                'summary': 'Learn how to set up and configure your new tenant',
                'content': 'Complete guide to tenant setup and initial configuration...',
                'category': 'getting-started',
                'tags': ['setup', 'tenant', 'beginner'],
                'views': 1250,
                'helpful_votes': 95,
                'unhelpful_votes': 8,
                'created_at': '2024-01-15T10:30:00Z',
                'updated_at': '2024-01-15T10:30:00Z',
                'author': 'Support Team'
            },
            {
                'id': 2,
                'title': 'Managing User Access and Permissions',
                'summary': 'How to invite users and manage their access levels',
                'content': 'Detailed guide on user management and permission systems...',
                'category': 'user-management',
                'tags': ['users', 'permissions', 'access'],
                'views': 820,
                'helpful_votes': 78,
                'unhelpful_votes': 5,
                'created_at': '2024-01-12T14:20:00Z',
                'updated_at': '2024-01-12T14:20:00Z',
                'author': 'Support Team'
            },
            {
                'id': 3,
                'title': 'Billing and Subscription Management',
                'summary': 'Understanding plans, billing cycles, and payments',
                'content': 'Everything you need to know about billing and subscriptions...',
                'category': 'billing',
                'tags': ['billing', 'payment', 'subscription'],
                'views': 650,
                'helpful_votes': 85,
                'unhelpful_votes': 3,
                'created_at': '2024-01-10T09:15:00Z',
                'updated_at': '2024-01-10T09:15:00Z',
                'author': 'Support Team'
            },
            {
                'id': 4,
                'title': 'Backup and Data Export',
                'summary': 'How to backup your data and export information',
                'content': 'Step-by-step guide for data backup and export procedures...',
                'category': 'data-management',
                'tags': ['backup', 'export', 'data'],
                'views': 420,
                'helpful_votes': 72,
                'unhelpful_votes': 2,
                'created_at': '2024-01-08T16:45:00Z',
                'updated_at': '2024-01-08T16:45:00Z',
                'author': 'Support Team'
            },
            {
                'id': 5,
                'title': 'Troubleshooting Common Issues',
                'summary': 'Solutions to frequently encountered problems',
                'content': 'Common problems and their solutions...',
                'category': 'troubleshooting',
                'tags': ['troubleshooting', 'problems', 'solutions'],
                'views': 980,
                'helpful_votes': 142,
                'unhelpful_votes': 7,
                'created_at': '2024-01-05T11:30:00Z',
                'updated_at': '2024-01-05T11:30:00Z',
                'author': 'Support Team'
            },
            {
                'id': 6,
                'title': 'API Documentation and Integration',
                'summary': 'How to integrate with our APIs',
                'content': 'Complete API documentation and integration examples...',
                'category': 'technical',
                'tags': ['api', 'integration', 'development'],
                'views': 1100,
                'helpful_votes': 156,
                'unhelpful_votes': 12,
                'created_at': '2024-01-03T13:45:00Z',
                'updated_at': '2024-01-03T13:45:00Z',
                'author': 'Development Team'
            }
        ]
        
        filtered_articles = all_articles
        
        # Filter by search query
        if search_query:
            filtered_articles = [
                article for article in all_articles
                if search_query in article['title'].lower() or 
                   search_query in article['summary'].lower() or
                   search_query in article['content'].lower() or
                   any(search_query in tag.lower() for tag in article['tags'])
            ]
        
        # Filter by category
        if category:
            filtered_articles = [
                article for article in filtered_articles
                if article['category'] == category
            ]
        
        # Pagination
        total_articles = len(filtered_articles)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_articles = filtered_articles[start:end]
        
        # Get available categories
        categories = list(set(article['category'] for article in all_articles))
        
        return jsonify({
            'success': True,
            'articles': paginated_articles,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_articles,
                'pages': (total_articles + per_page - 1) // per_page,
                'has_next': end < total_articles,
                'has_prev': page > 1
            },
            'categories': categories,
            'search_query': search_query,
            'selected_category': category
        })
        
    except Exception as e:
        logger.error(f"Get knowledge base failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to get knowledge base'}), 500

@support_api_bp.route('/api/support/knowledge-base/<int:article_id>', methods=['GET'])
@track_errors('api_get_knowledge_article')
def get_knowledge_article(article_id):
    """Get specific knowledge base article"""
    try:
        # Mock article data (in real implementation, this would come from database)
        articles = {
            1: {
                'id': 1,
                'title': 'Getting Started with Your Tenant',
                'summary': 'Learn how to set up and configure your new tenant',
                'content': '''# Getting Started with Your Tenant

Welcome to our platform! This guide will help you get started with your new tenant.

## Initial Setup

1. **Access Your Dashboard**: After logging in, you'll see your tenant dashboard
2. **Configure Basic Settings**: Update your tenant name, description, and contact information
3. **Set Up Users**: Invite team members and assign appropriate roles

## Key Features

- **User Management**: Control who has access to your tenant
- **Data Management**: Import and organize your data
- **Reporting**: Generate insights from your data
- **Security**: Configure security settings and permissions

## Next Steps

Once you've completed the initial setup, explore our other guides for advanced features.

Need help? Contact our support team!''',
                'category': 'getting-started',
                'tags': ['setup', 'tenant', 'beginner'],
                'views': 1251,  # Increment view count
                'helpful_votes': 95,
                'unhelpful_votes': 8,
                'created_at': '2024-01-15T10:30:00Z',
                'updated_at': '2024-01-15T10:30:00Z',
                'author': 'Support Team',
                'related_articles': [2, 3, 5]
            }
        }
        
        article = articles.get(article_id)
        if not article:
            return jsonify({'success': False, 'error': 'Article not found'}), 404
        
        # In a real implementation, you would increment the view count in the database
        logger.info(f"Knowledge base article {article_id} viewed")
        
        return jsonify({
            'success': True,
            'article': article
        })
        
    except Exception as e:
        logger.error(f"Get knowledge article failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to get article'}), 500

@support_api_bp.route('/api/support/knowledge-base/<int:article_id>/feedback', methods=['POST'])
@track_errors('api_knowledge_article_feedback')
def submit_article_feedback(article_id):
    """Submit feedback for a knowledge base article"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        helpful = data.get('helpful')  # True for helpful, False for not helpful
        feedback_text = data.get('feedback', '')
        
        if helpful is None:
            return jsonify({'success': False, 'error': 'helpful field is required'}), 400
        
        # In a real implementation, you would store this feedback in the database
        feedback_data = {
            'article_id': article_id,
            'helpful': helpful,
            'feedback_text': feedback_text,
            'user_id': current_user.id if current_user.is_authenticated else None,
            'submitted_at': datetime.utcnow().isoformat()
        }
        
        logger.info(f"Feedback submitted for article {article_id}: {'helpful' if helpful else 'not helpful'}")
        
        return jsonify({
            'success': True,
            'message': 'Thank you for your feedback!',
            'feedback': feedback_data
        })
        
    except Exception as e:
        logger.error(f"Submit article feedback failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to submit feedback'}), 500

# ================= ADMIN ENDPOINTS FOR SUPPORT MANAGEMENT =================

@support_api_bp.route('/api/admin/support/tickets', methods=['GET'])
@login_required
@track_errors('api_admin_get_all_tickets')
def admin_get_all_tickets():
    """Admin endpoint to get all support tickets"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        status = request.args.get('status')
        priority = request.args.get('priority')
        category = request.args.get('category')
        assigned_to = request.args.get('assigned_to')
        
        # Get API tickets
        api_query = ApiSupportTicket.query
        
        if status:
            try:
                status_enum = TicketStatus(status)
                api_query = api_query.filter_by(status=status_enum)
            except ValueError:
                pass
        
        if priority:
            try:
                priority_enum = TicketPriority(priority)
                api_query = api_query.filter_by(priority=priority_enum)
            except ValueError:
                pass
        
        if category:
            try:
                category_enum = TicketCategory(category)
                api_query = api_query.filter_by(category=category_enum)
            except ValueError:
                pass
        
        if assigned_to:
            api_query = api_query.filter_by(assigned_to=assigned_to)
        
        # Paginate API tickets
        api_tickets_paginated = api_query.order_by(
            ApiSupportTicket.updated_at.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)
        
        tickets_data = []
        for ticket in api_tickets_paginated.items:
            ticket_data = ticket.to_dict()
            ticket_data['ticket_type'] = 'api'
            tickets_data.append(ticket_data)
        
        return jsonify({
            'success': True,
            'tickets': tickets_data,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': api_tickets_paginated.total,
                'pages': api_tickets_paginated.pages,
                'has_next': api_tickets_paginated.has_next,
                'has_prev': api_tickets_paginated.has_prev
            },
            'filters': {
                'status': status,
                'priority': priority,
                'category': category,
                'assigned_to': assigned_to
            }
        })
        
    except Exception as e:
        logger.error(f"Admin get all tickets failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to get tickets'}), 500

@support_api_bp.route('/api/admin/support/tickets/<int:ticket_id>/assign', methods=['POST'])
@login_required
@track_errors('api_admin_assign_ticket')
def admin_assign_ticket(ticket_id):
    """Admin endpoint to assign ticket to agent"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'JSON data required'}), 400
        
        assigned_to = data.get('assigned_to')
        if not assigned_to:
            return jsonify({'success': False, 'error': 'assigned_to is required'}), 400
        
        # Try API ticket first
        ticket = ApiSupportTicket.query.get(ticket_id)
        
        if ticket:
            ticket.assigned_to = assigned_to
            if ticket.status == TicketStatus.OPEN:
                ticket.status = TicketStatus.IN_PROGRESS
            ticket.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            logger.info(f"API ticket {ticket.ticket_number} assigned to {assigned_to} by admin {current_user.id}")
            
            return jsonify({
                'success': True,
                'message': f'Ticket assigned to {assigned_to}',
                'ticket': ticket.to_dict()
            })
        
        return jsonify({'success': False, 'error': 'Ticket not found'}), 404
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Admin assign ticket failed: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to assign ticket'}), 500

# ================= UTILITY FUNCTIONS =================

def send_support_notification(user_id, title, message, ticket_data=None):
    """Send support-related notification to user"""
    if NotificationService:
        try:
            notification_service = NotificationService()
            notification_service.create_notification(
                user_id=user_id,
                title=title,
                message=message,
                notification_type=NotificationType.INFO,
                priority=NotificationPriority.MEDIUM,
                metadata=ticket_data or {}
            )
        except Exception as e:
            logger.warning(f"Failed to send support notification: {e}")

def get_ticket_metrics():
    """Get support ticket metrics for dashboard"""
    try:
        # API ticket metrics
        api_total = ApiSupportTicket.query.count()
        api_open = ApiSupportTicket.query.filter_by(status=TicketStatus.OPEN).count()
        api_in_progress = ApiSupportTicket.query.filter_by(status=TicketStatus.IN_PROGRESS).count()
        api_resolved = ApiSupportTicket.query.filter_by(status=TicketStatus.RESOLVED).count()
        
        # Legacy ticket metrics
        legacy_total = ExistingSupportTicket.query.count()
        legacy_open = ExistingSupportTicket.query.filter_by(status='open').count()
        
        return {
            'total_tickets': api_total + legacy_total,
            'open_tickets': api_open + legacy_open,
            'in_progress_tickets': api_in_progress,
            'resolved_tickets': api_resolved,
            'api_tickets': api_total,
            'legacy_tickets': legacy_total
        }
    except Exception as e:
        logger.error(f"Get ticket metrics failed: {str(e)}")
        return {}

# Export blueprint and models
__all__ = [
    'support_api_bp', 
    'ApiSupportTicket', 
    'ApiTicketMessage',
    'TicketStatus',
    'TicketPriority', 
    'TicketCategory',
    'get_ticket_metrics'
]