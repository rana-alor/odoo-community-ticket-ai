import os
from odoo import models, fields, api
from ..services.ai_classifier import analyze_text

class Ticket(models.Model):
    _name = 'community.ticket'
    _description = 'Ticket'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    title = fields.Char(string='Title',required=True, tracking=True)
    description = fields.Text(string='Description', tracking=True)
    spoc_name = fields.Char(string='SPOC Name', tracking=True)
    tag_ids = fields.Many2many('res.partner.category','community_ticket_tag_rel','ticket_id', 'res_partner_category_id', string='Tags')
    ai_priority = fields.Selection([('high','High'), ('medium','Medium'), ('low','Low')], string='AI Priority', tracking=True)
    ai_needs_review = fields.Boolean(string='AI Needs Review', tracking=True)
    ai_confidence = fields.Float(string='AI Confidence', tracking=True)
    ai_summary = fields.Text(string='AI Summary', readonly=True)
    ai_suggested_reply = fields.Text(string='AI Suggested Reply', tracking=True)
    ai_error = fields.Text(string='AI Error')
    ai_mock_mode = fields.Boolean(string='AI Mock Mode',default=True, tracking=True)

    def action_toggle_demo_mode(self):
        for rec in self:
            rec.ai_mock_mode = not rec.ai_mock_mode

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        api_key = self.env["ir.config_parameter"].sudo().get_param(
            "community_ticket_ai.openai_api_key", ""
        )
        model = os.getenv("COMMUNITY_TICKET_AI_MODEL", "gpt-4o-mini")
        threshold_str = os.getenv("COMMUNITY_TICKET_AI_THRESHOLD", "0.60")
        priority_map = {"High": "high","Medium": "medium","Low": "low"}

        try:
            threshold = float(threshold_str)
        except Exception:
            threshold = 0.60

        for rec in records:
            title = (rec.title or "").strip()
            description = (rec.description or "").strip()
            tags = rec.tag_ids.mapped("name")

            result = analyze_text(
                title=title,
                description=description,
                tags=tags,
                api_key=api_key or None,
                model=model,
                auto_apply_threshold=threshold,
                mock_mode=bool(rec.ai_mock_mode),
            )

            rec.write({
                "ai_priority": priority_map.get(result.get("priority"), "low"),
                "ai_confidence": float(result.get("confidence") or 0.0),
                "ai_summary": result.get("summary", "") or "",
                "ai_suggested_reply": result.get("suggested_reply", "") or "",
                "ai_needs_review": bool(result.get("needs_review", True)),
                "ai_error": result.get("error", "") or "",
            })

        return records