# ===== 1. support.py - User Support Routes =====
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime
from db import db
from models import SupportTicket, SupportReply
import json

support_bp = Blueprint('support', __name__, url_prefix='/support')

@support_bp.route('/')
@login_required
def tickets():
    """Display user's support tickets"""
    try:
        user_tickets = SupportTicket.query.filter_by(user_id=current_user.id)\
                                          .order_by(SupportTicket.created_at.desc()).all()
        return render_template('support/support.html', tickets=user_tickets)
    except Exception as e:
        flash(f'Error loading tickets: {str(e)}', 'error')
        return render_template('support/support.html', tickets=[])

@support_bp.route('/create', methods=['POST'])
@login_required
def create_ticket():
    """Create a new support ticket"""
    try:
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
        
        subject = data.get('subject', '').strip()
        message = data.get('message', '').strip()
        priority = data.get('priority', 'medium')
        
        if not subject:
            return jsonify({'success': False, 'error': 'Subject is required'}), 400
        if not message:
            return jsonify({'success': False, 'error': 'Message is required'}), 400
        
        ticket = SupportTicket(
            user_id=current_user.id,
            subject=subject[:200],
            message=message,
            priority=priority if priority in ['low', 'medium', 'high', 'urgent'] else 'medium'
        )
        
        db.session.add(ticket)
        db.session.commit()
        
        if request.is_json:
            return jsonify({
                'success': True,
                'ticket_id': ticket.id,
                'message': 'Support ticket created successfully'
            })
        else:
            flash('Support ticket created successfully!', 'success')
            return redirect(url_for('support.tickets'))
            
    except Exception as e:
        db.session.rollback()
        error_msg = f'Error creating ticket: {str(e)}'
        
        if request.is_json:
            return jsonify({'success': False, 'error': error_msg}), 500
        else:
            flash(error_msg, 'error')
            return redirect(url_for('support.tickets'))

@support_bp.route('/api/tickets')
@login_required
def api_tickets():
    """API endpoint to get user's tickets with replies count"""
    try:
        tickets = SupportTicket.query.filter_by(user_id=current_user.id)\
                                    .order_by(SupportTicket.created_at.desc()).all()
        
        tickets_data = []
        for ticket in tickets:
            ticket_dict = ticket.to_dict()
            ticket_dict['replies_count'] = len(ticket.replies)
            tickets_data.append(ticket_dict)
            
        return jsonify(tickets_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@support_bp.route('/ticket/<int:ticket_id>/replies')
@login_required
def ticket_replies(ticket_id):
    """Get replies for a specific ticket"""
    try:
        ticket = SupportTicket.query.filter_by(id=ticket_id, user_id=current_user.id).first_or_404()
        replies = SupportReply.query.filter_by(ticket_id=ticket_id)\
                                   .order_by(SupportReply.created_at.asc()).all()
        return jsonify([reply.to_dict() for reply in replies])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@support_bp.route('/reply/<int:ticket_id>', methods=['POST'])
@login_required
def user_reply(ticket_id):
    """User can reply to their own ticket"""
    try:
        ticket = SupportTicket.query.filter_by(id=ticket_id, user_id=current_user.id).first_or_404()
        data = request.get_json()
        
        message = data.get('message', '').strip()
        if not message:
            return jsonify({'success': False, 'error': 'Message is required'}), 400
        
        reply = SupportReply(
            ticket_id=ticket_id,
            user_id=current_user.id,
            message=message,
            is_admin=False
        )
        
        # Reopen ticket if it was closed
        if ticket.status == 'closed':
            ticket.status = 'open'
        
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