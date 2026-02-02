from odoo import models, fields, api, _

class Ticket(models.Model):
    _name = 'ticket.ticket'
    _description = 'Ticket'
    _inherit = ['mail.thread', 'mail.activity.mixin']