
# ===== 2. support_admin.py - Admin Support Routes =====
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from db import db
from functools import wraps
from models import SupportTicket, SupportReply

support_admin_bp = Blueprint('support_admin', __name__, url_prefix='/admin/support')

def admin_required(f):
    """Decorator to require admin access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

@support_admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    """Admin support dashboard"""
    try:
        tickets = SupportTicket.query.order_by(SupportTicket.created_at.desc()).all()
        
        stats = {
            'total': len(tickets),
            'open': len([t for t in tickets if t.status == 'open']),
            'in_progress': len([t for t in tickets if t.status == 'in_progress']),
            'closed': len([t for t in tickets if t.status == 'closed']),
            'urgent': len([t for t in tickets if t.priority == 'urgent'])
        }
        
        return render_template('support/support_admin.html', tickets=tickets, stats=stats)
    except Exception as e:
        return render_template('support/support_admin.html', tickets=[], stats={
            'total': 0, 'open': 0, 'in_progress': 0, 'closed': 0, 'urgent': 0
        })

@support_admin_bp.route('/api/tickets')
@login_required
@admin_required
def api_tickets():
    """API endpoint to get all tickets for admin"""
    try:
        tickets = SupportTicket.query.order_by(SupportTicket.created_at.desc()).all()
        tickets_data = []
        
        for ticket in tickets:
            ticket_dict = ticket.to_dict()
            ticket_dict['replies_count'] = len(ticket.replies)
            tickets_data.append(ticket_dict)
            
        return jsonify(tickets_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@support_admin_bp.route('/update/<int:ticket_id>', methods=['POST'])
@login_required
@admin_required
def update_ticket(ticket_id):
    """Update a support ticket"""
    try:
        ticket = SupportTicket.query.get_or_404(ticket_id)
        data = request.get_json()
        
        if 'status' in data and data['status'] in ['open', 'in_progress', 'closed']:
            ticket.status = data['status']
            
        if 'priority' in data and data['priority'] in ['low', 'medium', 'high', 'urgent']:
            ticket.priority = data['priority']
            
        if 'admin_notes' in data:
            ticket.admin_notes = data['admin_notes']
            
        ticket.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Ticket updated successfully',
            'ticket': ticket.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@support_admin_bp.route('/reply/<int:ticket_id>', methods=['POST'])
@login_required
@admin_required
def reply_to_ticket(ticket_id):
    """Admin reply to a support ticket"""
    try:
        ticket = SupportTicket.query.get_or_404(ticket_id)
        data = request.get_json()
        
        message = data.get('message', '').strip()
        if not message:
            return jsonify({'success': False, 'error': 'Message is required'}), 400
        
        reply = SupportReply(
            ticket_id=ticket_id,
            user_id=current_user.id,
            message=message,
            is_admin=True
        )
        
        # Update ticket status if provided
        if 'status' in data and data['status'] in ['open', 'in_progress', 'closed']:
            ticket.status = data['status']
            
        ticket.updated_at = datetime.utcnow()
        
        db.session.add(reply)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Reply sent successfully',
            'reply': reply.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@support_admin_bp.route('/ticket/<int:ticket_id>/replies')
@login_required
@admin_required
def get_ticket_replies(ticket_id):
    """Get all replies for a specific ticket"""
    try:
        ticket = SupportTicket.query.get_or_404(ticket_id)
        replies = SupportReply.query.filter_by(ticket_id=ticket_id)\
                                   .order_by(SupportReply.created_at.asc()).all()
        return jsonify([reply.to_dict() for reply in replies])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@support_admin_bp.route('/stats')
@login_required
@admin_required
def get_stats():
    """Get support statistics"""
    try:
        tickets = SupportTicket.query.all()
        
        stats = {
            'total': len(tickets),
            'open': len([t for t in tickets if t.status == 'open']),
            'in_progress': len([t for t in tickets if t.status == 'in_progress']),
            'closed': len([t for t in tickets if t.status == 'closed']),
            'urgent': len([t for t in tickets if t.priority == 'urgent']),
            'by_status': {},
            'by_priority': {}
        }
        
        for status in ['open', 'in_progress', 'closed']:
            stats['by_status'][status] = len([t for t in tickets if t.status == status])
            
        for priority in ['low', 'medium', 'high', 'urgent']:
            stats['by_priority'][priority] = len([t for t in tickets if t.priority == priority])
        
        return jsonify(stats)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500