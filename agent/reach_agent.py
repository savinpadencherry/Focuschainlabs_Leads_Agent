"""
Reach Agent — AI-powered email composer for B2B outreach.

Generates a personalised cold email + 2-step follow-up sequence for a CRM
contact using the context captured by the Scout Agent (opening_line, signal,
notes). Optionally sends via Gmail SMTP (App Password) or returns draft text.
"""

from __future__ import annotations

import json
import os
import re
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from utils.llm import generate_content_text


_COMPOSE_PROMPT = """\
You are a senior B2B sales consultant ghostwriting a cold outreach sequence for \
{sender_name} ({sender_title}) at {sender_company}.

RECIPIENT:
  Name:          {contact_name}
  Title:         {contact_title}
  Company:       {company}
  Industry:      {industry}
  Key signal:    {signal}
  Opening hook:  {opening_line}
  Notes:         {notes}

WHAT WE OFFER:
  {offering}

RULES — read carefully:
• Every email must feel like one person writing to another person, NOT a
  marketing template or a pitch deck in email form.
• Email 1 (cold outreach): lead with a specific observation about THEM, not us.
  3-5 sentences. End with one low-friction ask (a 15-min call).
• Email 2 (Day 3 follow-up): 2-3 sentences, different angle, never "just
  following up".
• Email 3 (Day 7 follow-up): 1-2 sentences, graceful close, keep the door open.
• Subject line: max 8 words, conversational, specific to their situation.
  No clickbait. No "Quick question" or "Touching base".
• No bullet points inside email bodies.
• No jargon: "leverage", "synergy", "value proposition", "seamless".

Return ONLY valid JSON — no markdown fences, no explanation:
{{
  "subject": "...",
  "email_1": "...",
  "email_2": "...",
  "email_3": "..."
}}
"""


def compose_outreach(
    contact: dict[str, Any],
    *,
    sender_name: str = "",
    sender_title: str = "",
    sender_company: str = "",
    offering: str = "",
) -> dict[str, str]:
    """
    Return {subject, email_1, email_2, email_3} for a CRM contact.
    Raises on Gemini error so the caller can surface it to the user.
    """
    prompt = _COMPOSE_PROMPT.format(
        contact_name   = (contact.get("name") or contact.get("contact_name") or "there").strip(),
        contact_title  = (contact.get("title") or "").strip(),
        company        = (contact.get("company") or "").strip(),
        industry       = (contact.get("industry") or "").strip(),
        signal         = (contact.get("signal") or "").strip(),
        opening_line   = (contact.get("opening_line") or "").strip(),
        notes          = (contact.get("notes") or "").strip(),
        sender_name    = (sender_name or "the team").strip(),
        sender_title   = (sender_title or "").strip(),
        sender_company = (sender_company or "FocusChain Labs").strip(),
        offering       = (offering or "B2B growth automation and AI agent services").strip(),
    )

    raw = generate_content_text(prompt)

    # Strip markdown fences if the model added them
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    raw = re.sub(r"\s*```\s*$", "", raw.strip(), flags=re.MULTILINE)
    raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = _extract_fallback(raw)

    return {
        "subject": str(data.get("subject") or ""),
        "email_1": str(data.get("email_1") or ""),
        "email_2": str(data.get("email_2") or ""),
        "email_3": str(data.get("email_3") or ""),
    }


def _extract_fallback(raw: str) -> dict[str, str]:
    """Regex extraction when JSON.loads fails."""
    result: dict[str, str] = {}
    for key in ("subject", "email_1", "email_2", "email_3"):
        m = re.search(rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"', raw, re.DOTALL)
        if m:
            result[key] = m.group(1).replace("\\n", "\n").replace('\\"', '"')
    return result


# ── Gmail SMTP sending ────────────────────────────────────────────────────────

def smtp_configured() -> bool:
    return bool(os.getenv("SMTP_FROM_EMAIL") and os.getenv("SMTP_APP_PASSWORD"))


def send_email_smtp(
    to_email: str,
    subject: str,
    body: str,
    *,
    from_email: str = "",
    app_password: str = "",
    reply_to: str = "",
) -> dict[str, Any]:
    """
    Send via Gmail SMTP (TLS port 587).
    Returns {"ok": True} on success or {"ok": False, "error": "..."} on failure.
    """
    from_email   = (from_email   or os.getenv("SMTP_FROM_EMAIL",   "")).strip()
    app_password = (app_password or os.getenv("SMTP_APP_PASSWORD", "")).strip()

    if not from_email or not app_password:
        return {
            "ok":    False,
            "error": (
                "SMTP not configured. Add SMTP_FROM_EMAIL and SMTP_APP_PASSWORD "
                "to your Streamlit secrets to enable direct sending."
            ),
        }
    if not to_email or "@" not in to_email:
        return {"ok": False, "error": "Invalid recipient email address."}

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_email
    msg["To"]      = to_email
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.login(from_email, app_password)
            server.sendmail(from_email, to_email, msg.as_string())
        return {"ok": True}
    except smtplib.SMTPAuthenticationError:
        return {
            "ok":    False,
            "error": (
                "Gmail auth failed. Make sure SMTP_APP_PASSWORD is a Gmail App Password "
                "(not your account password). Generate one at: "
                "Google Account → Security → 2-Step Verification → App Passwords."
            ),
        }
    except smtplib.SMTPRecipientsRefused:
        return {"ok": False, "error": f"Recipient refused: {to_email}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
