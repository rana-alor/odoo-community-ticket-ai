from odoo import models, fields, api, _

class Ticket(models.Model):
    _name = 'community.ticket'
    _description = 'Ticket'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    title = fields.Char(string='Title',required=True, tracking=True)
    description = fields.Char(string='Description', tracking=True)
    ai_priority = fields.Selection([('high','High'), ('medium','Medium'), ('low','Low')], string='AI Priority', tracking=True)
    ai_needs_review = fields.Boolean(string='AI Needs Review', tracking=True)
    ai_summary = fields.Char(string='AI Summary', readonly=True)
    ai_suggested_reply = fields.Char(string='AI Suggested Reply', tracking=True)
    ai_mock_mode = fields.Boolean(string='AI Mock Mode', tracking=True)