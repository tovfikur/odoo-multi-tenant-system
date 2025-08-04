# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright Domiup (<http://domiup.com>).
#
##############################################################################

from odoo import api, models, fields, _
import logging

_logger = logging.getLogger(__name__)


class MultiApprovalType(models.Model):
    _name = 'multi.approval.type'
    _description = 'Multi Approval Type'

    name = fields.Char(string='Name', required=True)
    description = fields.Char(string='Description')
    image = fields.Binary(attachment=True)
    active = fields.Boolean(string='Active', default=True, readonly=False)
    line_ids = fields.One2many(
        'multi.approval.type.line', 'type_id', string="Approvers",
        required=True)
    approval_minimum = fields.Integer(
        string='Minimum Approvers', compute='_get_approval_minimum',
        readonly=True)
    document_opt = fields.Selection(
        [('Required', 'Required'),
         ('Optional', 'Optional'),
         ], string="Document", default='Optional')
    contact_opt = fields.Selection(
        [('Required', 'Required'),
         ('Optional', 'Optional'),
         ('None', 'None'),
         ], string="Contact", default='None')
    date_opt = fields.Selection(
        [('Required', 'Required'),
         ('Optional', 'Optional'),
         ('None', 'None'),
         ], string="Date", default='None')
    period_opt = fields.Selection(
        [('Required', 'Required'),
         ('Optional', 'Optional'),
         ('None', 'None'),
         ], string="Period", default='None')
    item_opt = fields.Selection(
        [('Required', 'Required'),
         ('Optional', 'Optional'),
         ('None', 'None'),
         ], string="Item", default='None')
    quantity_opt = fields.Selection(
        [('Required', 'Required'),
         ('Optional', 'Optional'),
         ('None', 'None'),
         ], string="Quantity", default='None')
    amount_opt = fields.Selection(
        [('Required', 'Required'),
         ('Optional', 'Optional'),
         ('None', 'None'),
         ], string="Amount", default='None')
    reference_opt = fields.Selection(
        [('Required', 'Required'),
         ('Optional', 'Optional'),
         ('None', 'None'),
         ], string="Reference", default='None')
    payment_opt = fields.Selection(
        [('Required', 'Required'),
         ('Optional', 'Optional'),
         ('None', 'None'),
         ], string="Payment", default='None')
    location_opt = fields.Selection(
        [('Required', 'Required'),
         ('Optional', 'Optional'),
         ('None', 'None'),
         ], string="Location", default='None')
    submitted_nb = fields.Integer(
        string="To Review",
        compute="_get_submitted_request", search="_search_approval_request_submitted")
    
    my_request_nb = fields.Integer(
        string="My Request",
        compute="_get_submitted_request", search="_search_approval_request_myrequest")
    
    all_request_nb = fields.Integer(
        string="All Request",
        compute="_get_submitted_request")

    have_update = fields.Integer(string='HaveUpdate')

    @api.depends("have_update")
    def _get_submitted_request(self):
        for r in self:
            r.submitted_nb = self.env['multi.approval'].search_count(
                [('type_id', '=', r.id), ('state', '=', 'Submitted'), ('pic_id', '=', self.env.user.id)])
            r.my_request_nb = self.env['multi.approval'].search_count(
                [('type_id', '=', r.id), ('user_id', '=', self.env.user.id)])
            r.all_request_nb = self.env['multi.approval'].search_count(
                [('type_id', '=', r.id)])

    @api.model
    def _search_approval_request_submitted(self, operator, value):
        approval_requests = self.env["multi.approval"].search(
            [('state', '=', 'Submitted'), ('pic_id', '=', self.env.user.id)]
        )
        return [("id", "in", approval_requests.mapped('type_id').ids)]
    
    @api.model
    def _search_approval_request_myrequest(self, operator, value):
        approval_requests = self.env["multi.approval"].search(
            [('user_id', '=', self.env.user.id)]
        )
        return [("id", "in", approval_requests.mapped('type_id').ids)]

    @api.depends('line_ids')
    def _get_approval_minimum(self):
        for rec in self:
            required_lines = rec.line_ids.filtered(
                lambda l: l.require_opt == 'Required')
            rec.approval_minimum = len(required_lines)

    def create_request(self):
        self.ensure_one()
        view_id = self.env.ref(
            'multi_level_approval.multi_approval_view_form', False)
        return {
            'name': _('New Request'),
            'view_mode': 'form',
            'res_model': 'multi.approval',
            'view_id': view_id and view_id.id or False,
            'type': 'ir.actions.act_window',
            'context': {
                'default_type_id': self.id,
            }
        }

    def open_submitted_request(self):
        self.ensure_one()
        view_id = self.env.ref(
            'multi_level_approval.multi_approval_view_form', False)
        return {
            'name': _('Submitted Requests'),
            'view_mode': 'tree,form',
            'res_model': 'multi.approval',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('type_id', '=', self.id), ('state', '=', 'Submitted')],
            'context': {
                'default_type_id': self.id,
            }
        }
    

    def open_my_request(self):
        self.ensure_one()
        view_id = self.env.ref(
            'multi_level_approval.multi_approval_view_form', False)
        return {
            'name': _('My Requests'),
            'view_mode': 'tree,form',
            'res_model': 'multi.approval',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('type_id', '=', self.id), ('user_id', '=', self.env.user.id)],
            'context': {
                'default_type_id': self.id,
            }
        }
    
    def open_all_request(self):
        self.ensure_one()
        view_id = self.env.ref(
            'multi_level_approval.multi_approval_view_form', False)
        return {
            'name': _('My Requests'),
            'view_mode': 'tree,form',
            'res_model': 'multi.approval',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('type_id', '=', self.id)],
            'context': {
                'default_type_id': self.id,
            }
        }
