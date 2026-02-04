import os
from odoo import models, fields, api
from ..services.ai_classifier import analyze_text, analyze_priority_only


class Ticket(models.Model):
    _name = 'community.ticket'
    _description = 'Ticket'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    title = fields.Char(string='Title',required=True, tracking=True)
    description = fields.Text(string='Description', tracking=True)
    ref = fields.Char(default="New", readonly=True, copy=False, index=True)
    tag_ids = fields.Many2many('res.partner.category','community_ticket_tag_rel','ticket_id', 'res_partner_category_id', string='Tags')
    ai_priority = fields.Selection([('high','High'), ('medium','Medium'), ('low','Low')], string='Priority', tracking=True)
    ai_needs_review = fields.Boolean(string='Needs Review', tracking=True)
    ai_confidence = fields.Float(string='Confidence', tracking=True)
    ai_summary = fields.Text(string='AI Summary', readonly=True)
    ai_suggested_reply = fields.Text(string='AI Suggested Reply', tracking=True)
    ai_error = fields.Text(string='Error')
    ai_mock_mode = fields.Boolean(string='AI Demo Mode',default=True, tracking=True)
    spoc_id = fields.Many2one('res.partner', string='SPOC Name')
    ai_priority_level = fields.Selection(
        [("0", "None"), ("1", "Low"), ("2", "Medium"), ("3", "High")],
        string="Priority",
        default="0",
        tracking=True,
    )

    def action_toggle_demo_mode(self):
        for rec in self:
            rec.ai_mock_mode = not rec.ai_mock_mode

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)

        for rec in records:
            if rec.ref == "New":
                rec.ref = self.env["ir.sequence"].next_by_code("community.ticket") or "New"

        threshold_str = os.getenv("COMMUNITY_TICKET_AI_THRESHOLD", "0.60")
        try:
            threshold = float(threshold_str)
        except Exception:
            threshold = 0.60

        priority_map = {"High": "high", "Medium": "medium", "Low": "low"}
        level_map = {"High": "3", "Medium": "2", "Low": "1"}

        for rec in records:
            if not rec.ai_mock_mode:
                continue

            title = (rec.title or "").strip()
            description = (rec.description or "").strip()
            tags = rec.tag_ids.mapped("name") if rec.tag_ids else []

            result = analyze_priority_only(
                title=title,
                description=description,
                tags=tags,
                auto_apply_threshold=threshold,
            )

            rec.write({
                "ai_priority": priority_map.get(result.get("priority"), "low"),
                "ai_priority_level": level_map.get(result.get("priority"), "1"),
                "ai_confidence": float(result.get("confidence") or 0.0),
                "ai_needs_review": bool(result.get("needs_review", True)),
                "ai_error": result.get("error") or False,
            })

        return records


    def action_generate_ai_draft(self):
        """
        Button: Generate AI Summary + Suggested Reply (no priority changes).
        Only runs when Demo/Mock mode is OFF.
        """
        api_key = self.env["ir.config_parameter"].sudo().get_param(
            "community_ticket_ai.openai_api_key", ""
        )
        model = os.getenv("COMMUNITY_TICKET_AI_MODEL", "gpt-4o-mini")
        threshold_str = os.getenv("COMMUNITY_TICKET_AI_THRESHOLD", "0.60")
        try:
            threshold = float(threshold_str)
        except Exception:
            threshold = 0.60

        for rec in self:
            title = (rec.title or "").strip()
            description = (rec.description or "").strip()
            tags = rec.tag_ids.mapped("name") if rec.tag_ids else []

            result = analyze_text(
                title=title,
                description=description,
                tags=tags,
                api_key=api_key or None,
                model=model,
                auto_apply_threshold=threshold,
            )

            rec.write({
                "ai_summary": result.get("summary", "") or "",
                "ai_suggested_reply": result.get("suggested_reply", "") or "",
                "ai_error": result.get("error") or False,
            })

        return True

    def action_open_reply_composer(self):
        self.ensure_one()

        body = (self.ai_suggested_reply or "").strip()
        if not body:
            body = "Hello,\n\n"

        subject = f"[{self.title or ''}]"

        ctx = {
            "default_model": self._name,
            "default_res_id": self.id,
            "default_composition_mode": "comment",
            "default_is_log": False,
            "default_subject": subject,
            "default_body": body,
        }

        return {
            "type": "ir.actions.act_window",
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": ctx,
        }
