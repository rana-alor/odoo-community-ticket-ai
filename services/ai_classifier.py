from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_AUTO_APPLY_THRESHOLD = 0.60

REQUIRED_KEYS = {"priority", "confidence", "summary", "suggested_reply"}
ALLOWED_PRIORITIES = {"Low", "Medium", "High"}

_MODULE_DIR = Path(__file__).resolve().parent
_ADDON_DIR = _MODULE_DIR.parent
_PROMPTS_DIR = _ADDON_DIR / "prompts"

SYSTEM_PROMPT_PATH = _PROMPTS_DIR / "priority_prompt.txt"
SCHEMA_EXAMPLE_PATH = _PROMPTS_DIR / "ai_output_schema.json"

def _load_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def load_system_prompt(prompt_path: Optional[Path] = None) -> str:
    path = prompt_path or SYSTEM_PROMPT_PATH
    return _load_text_file(path)

def load_output_schema_example(path: Optional[Path] = None) -> dict:
    """
    For reference/debugging only. Not needed for runtime.
    """
    schema_path = path or SCHEMA_EXAMPLE_PATH
    return json.loads(_load_text_file(schema_path))

def build_user_input(title: str, description: str) -> str:
    return f"Title: {title}\n\nDescription:\n{description}"

def validate_output(data: dict) -> None:
    if not isinstance(data, dict):
        raise ValueError("Output is not a JSON object")

    keys = set(data.keys())
    if keys != REQUIRED_KEYS:
        raise ValueError(f"Output keys mismatch. Got {keys}, expected {REQUIRED_KEYS}")

    if data["priority"] not in ALLOWED_PRIORITIES:
        raise ValueError("Invalid priority value")

    conf = data["confidence"]
    if not isinstance(conf, (int, float)) or conf < 0.0 or conf > 1.0:
        raise ValueError("Invalid confidence value")

    if not isinstance(data["summary"], str):
        raise ValueError("Summary must be a string")

    if not isinstance(data["suggested_reply"], str):
        raise ValueError("Suggested reply must be a string")

def add_needs_review(data: dict, threshold: float) -> dict:
    out = dict(data)
    out["needs_review"] = float(out["confidence"]) < float(threshold)
    return out

def mock_analyze(title: str, description: str, tags=None) -> dict:
    tags = tags or []

    text = f"{title} {description}".lower()
    tokens = set(text.split())
    tokens |= {t.lower() for t in tags}

    priority_keywords = {
        "High": {"down", "blocked", "error", "urgent", "crash", "users", "production"},
        "Medium": {"slow", "issue", "bug", "problem", "delay"},
        "Low": {"question", "request", "info", "feature", "enhancement"},
    }

    scores = {}
    for priority, words in priority_keywords.items():
        scores[priority] = len(tokens & words)

    best_priority = max(scores, key=scores.get)
    best_score = scores[best_priority]

    total_hits = sum(scores.values())
    if total_hits == 0:
        raise ValueError(
            "Mock classification failed: no keywords found in title, description, or tags."
        )
    else:
        confidence = min(0.95, best_score / total_hits)

    return {
        "priority": best_priority,
        "confidence": round(confidence, 2),
        "summary": f"Classified as {best_priority} priority based on detected signals.",
        "suggested_reply": (
            "Thanks for reporting this. We’re prioritizing it and will update you shortly."
            if best_priority == "High"
            else "Thanks for the details. We’ll look into this and get back to you."
        ),
    }


def analyze_text(
    title: str,
    description: str,
    tags=None,
    *,
    api_key: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    auto_apply_threshold: float = DEFAULT_AUTO_APPLY_THRESHOLD,
    mock_mode: Optional[bool] = None,
    prompt_path: Optional[Path] = None,
) -> Dict[str, Any]:

    """
    Main function to call from Odoo.

    Returns:
      {
        "priority": "Low|Medium|High",
        "confidence": float 0..1,
        "summary": str,
        "suggested_reply": str,
        "needs_review": bool,
        "error": str
      }

    Notes:
    - No automatic sending. This only produces suggestions.
    - mock_mode can be passed explicitly; if None, reads env COMMUNITY_TICKET_AI_MOCK=1 for dev convenience.
    """

    if (not title or not title.strip()) and (not description or not description.strip()):
        return {
            "priority": "Low",
            "confidence": 0.0,
            "summary": "",
            "suggested_reply": "",
            "needs_review": True,
            "error": "Missing title and description; analysis not run.",
        }

    if mock_mode is None:
        mock_mode = os.getenv("COMMUNITY_TICKET_AI_MOCK", "0") == "1"

    if mock_mode:
        try:
            data = mock_analyze(title, description, tags)

            if not description or not description.strip():
                data["confidence"] = min(float(data["confidence"]), 0.40)

            data = add_needs_review(data, threshold=auto_apply_threshold)
            data["error"] = ""
            return data

        except Exception as e:
            return {
                "priority": "Low",
                "confidence": 0.0,
                "summary": "",
                "suggested_reply": "",
                "needs_review": True,
                "error": str(e),
            }

    if OpenAI is None:
        return {
            "priority": "Low",
            "confidence": 0.0,
            "summary": "",
            "suggested_reply": "",
            "needs_review": True,
            "error": "OpenAI SDK not installed. Add 'openai' to requirements and install it.",
        }

    if not api_key:
        return {
            "priority": "Low",
            "confidence": 0.0,
            "summary": "",
            "suggested_reply": "",
            "needs_review": True,
            "error": "Missing API key. Provide api_key from Odoo config (env or system parameter).",
        }

    system_prompt = load_system_prompt(prompt_path=prompt_path)
    user_input = build_user_input(title, description)

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "priority": {"type": "string", "enum": ["Low", "Medium", "High"]},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "summary": {"type": "string"},
            "suggested_reply": {"type": "string"},
        },
        "required": ["priority", "confidence", "summary", "suggested_reply"],
    }

    try:
        client = OpenAI(api_key=api_key)

        resp = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "analysis_result",
                    "schema": schema,
                    "strict": True,
                }
            },
        )

        raw = resp.output_text
        data = json.loads(raw)
        validate_output(data)

        if not description or not description.strip():
            data["confidence"] = min(float(data["confidence"]), 0.40)

        data = add_needs_review(data, threshold=auto_apply_threshold)
        data["error"] = ""
        return data

    except Exception as e:
        return {
            "priority": "Low",
            "confidence": 0.0,
            "summary": "",
            "suggested_reply": "",
            "needs_review": True,
            "error": f"AI failure: {type(e).__name__}: {e}",
        }
