"""Broadcast outreach — one message composed for many CRM leads."""

from __future__ import annotations

import json
import re
from typing import Any

from utils.llm import generate_content_text


_BROADCAST_PROMPT = """\
You are writing a short promotional broadcast for a B2B sales team.

AUDIENCE: {count} CRM leads in industries like {industries}.
CAMPAIGN GOAL: {goal}
TONE: {tone}

Return ONLY valid JSON (no markdown fences):
{{
  "subject": "email subject, max 8 words",
  "email_body": "plain-text email, 4-6 sentences, one clear CTA",
  "whatsapp_body": "WhatsApp version, max 320 chars, conversational, one CTA"
}}

Rules:
- Personalise the opening line pattern (e.g. "Hi {{name}}") but keep one template.
- No spammy ALL CAPS or excessive emojis.
- WhatsApp body must stay under 320 characters.
"""


def compose_broadcast(
    *,
    lead_count: int,
    industries: list[str],
    goal: str = "share a limited-time promotion",
    tone: str = "warm and professional",
) -> dict[str, str]:
    """Return subject + email_body + whatsapp_body for a bulk send."""
    ind = ", ".join(sorted({i for i in industries if i}))[:120] or "mixed B2B"
    prompt = _BROADCAST_PROMPT.format(
        count=lead_count,
        industries=ind,
        goal=goal.strip() or "share a limited-time promotion",
        tone=tone.strip() or "warm and professional",
    )
    raw = generate_content_text(prompt)
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    raw = re.sub(r"\s*```\s*$", "", raw.strip(), flags=re.MULTILINE)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {
            "subject": "A quick update from our team",
            "email_body": raw[:1200],
            "whatsapp_body": raw[:320],
        }
    return {
        "subject": str(data.get("subject") or "Update from our team").strip(),
        "email_body": str(data.get("email_body") or "").strip(),
        "whatsapp_body": str(data.get("whatsapp_body") or "").strip()[:320],
    }


def personalise(template: str, contact: dict[str, Any]) -> str:
    """Fill simple {{name}} / {{company}} placeholders."""
    name = (contact.get("name") or contact.get("company") or "there").strip()
    company = (contact.get("company") or "").strip()
    out = template.replace("{{name}}", name).replace("{{company}}", company)
    out = out.replace("{name}", name).replace("{company}", company)
    return out
