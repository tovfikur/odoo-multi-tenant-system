# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright Domiup (<http://domiup.com>).
#
##############################################################################

from odoo import api, models, fields
import logging

_logger = logging.getLogger(__name__)


class MultiApprovalLine(models.Model):
    _name = 'multi.approval.line'
    _description = 'Multi Aproval Line'
    _order = 'sequence'

    name = fields.Char(string='Title', required=True)
    user_id = fields.Many2one(string='User', comodel_name="res.users",
                              required=True)
    sequence = fields.Integer(string='Sequence')
    require_opt = fields.Selection(
        [('Required', 'Required'),
         ('Optional', 'Optional'),
         ], string="Type of Approval", default='Required')
    approval_id = fields.Many2one(
        string="Approval", comodel_name="multi.approval")
    state = fields.Selection(
        [('Draft', 'Draft'),
         ('Waiting for Approval', 'Waiting for Approval'),
         ('Approved', 'Approved'),
         ('Refused', 'Refused'),
         ('Cancel', 'Cancel'),
         ], default="Draft")
    refused_reason = fields.Text('Refused Reason')
    deadline = fields.Date(string='Deadline')
