"""WhatsApp Cloud API (Meta) helpers — send messages, normalise numbers.

Uses Meta's official WhatsApp Business Cloud API (graph.facebook.com).
Free for replies within the 24-hour customer-service window, which covers
the CRM's use case: leads message you first, the agent logs and replies.

Secrets (Meta for Developers → your app → WhatsApp → API Setup):
  WHATSAPP_ACCESS_TOKEN     — permanent system-user token (or temp dev token)
  WHATSAPP_PHONE_NUMBER_ID  — the "Phone number ID" shown in API Setup
  WHATSAPP_VERIFY_TOKEN     — any random string YOU choose; pasted both here
                              and in the webhook config on Meta's dashboard
"""

from __future__ import annotations

import os
import re

import requests

_GRAPH = "https://graph.facebook.com/v21.0"


def _token() -> str:
    return (os.getenv("WHATSAPP_ACCESS_TOKEN") or "").strip()


def _phone_number_id() -> str:
    return (os.getenv("WHATSAPP_PHONE_NUMBER_ID") or "").strip()


def whatsapp_configured() -> bool:
    return bool(_token() and _phone_number_id())


def normalize_wa_phone(raw: str) -> str:
    """Digits-only E.164-ish form WhatsApp uses, e.g. '919876543210'."""
    digits = re.sub(r"\D", "", raw or "")
    # WhatsApp 'from' already includes the country code; keep as-is.
    return digits


def phone_variants(wa_number: str) -> list[str]:
    """Candidate strings to match a WhatsApp number against stored CRM phones.

    Stored phones vary: '+91 98765 43210', '09876543210', '9876543210'…
    We match on the trailing 10 digits (national number) to be robust.
    """
    digits = normalize_wa_phone(wa_number)
    out = [digits]
    if len(digits) > 10:
        out.append(digits[-10:])
    return out


def send_whatsapp_text(to: str, body: str) -> dict:
    """Send a plain text message. Returns the Graph API response dict.

    Raises for transport errors; callers treat a failed ack as non-fatal
    (the lead is already stored — the reply is a courtesy).

    Note: free-form text only works inside Meta's 24-hour customer-service
    window (user messaged you first). For cold promotions use
    send_whatsapp_template() with an approved template.
    """
    resp = requests.post(
        f"{_GRAPH}/{_phone_number_id()}/messages",
        headers={
            "Authorization": f"Bearer {_token()}",
            "Content-Type": "application/json",
        },
        json={
            "messaging_product": "whatsapp",
            "to": normalize_wa_phone(to),
            "type": "text",
            "text": {"body": body[:4096]},
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def send_whatsapp_template(
    to: str,
    template_name: str,
    *,
    language_code: str = "en",
    body_params: list[str] | None = None,
) -> dict:
    """Send an approved WhatsApp template (required for marketing/promotions).

    Template must be created and approved in Meta Business Manager →
    WhatsApp Manager → Message templates.
    """
    components = []
    if body_params:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": p[:1024]} for p in body_params],
        })
    payload: dict = {
        "messaging_product": "whatsapp",
        "to": normalize_wa_phone(to),
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
        },
    }
    if components:
        payload["template"]["components"] = components
    resp = requests.post(
        f"{_GRAPH}/{_phone_number_id()}/messages",
        headers={
            "Authorization": f"Bearer {_token()}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def broadcast_feasibility(selected: list[dict]) -> dict:
    """Summarise whether a WhatsApp broadcast to selected leads is viable."""
    with_phone = [c for c in selected if (c.get("phone") or "").strip()]
    with_wa_source = [c for c in selected if normalize_source_label(c.get("source") or "") == "whatsapp"]
    return {
        "total": len(selected),
        "with_phone": len(with_phone),
        "whatsapp_source": len(with_wa_source),
        "free_text_window": (
            "Free-form text only works within 24h of the customer's last inbound message. "
            "For cold promotions you need an approved Meta template + opt-in."
        ),
        "recommendation": (
            "Use approved template messages for promotions; use free-text only for "
            "leads who recently messaged you on WhatsApp (your webhook already captures them)."
        ),
    }


def normalize_source_label(source: str) -> str:
    s = (source or "").strip().lower()
    return "whatsapp" if s in {"whatsapp", "wa", "whats_app"} else s


def parse_webhook_messages(payload: dict) -> list[dict]:
    """Flatten Meta's nested webhook payload into simple message dicts.

    Returns [{"id", "from", "name", "text", "timestamp"}] — only text
    messages; media/status updates are skipped.
    """
    out: list[dict] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            names = {
                (c.get("wa_id") or ""): ((c.get("profile") or {}).get("name") or "")
                for c in value.get("contacts") or []
            }
            # Our own number. In Coexistence, messages the business sends from the
            # WhatsApp Business app are echoed back here with from == this number.
            biz = re.sub(r"\D", "", (value.get("metadata") or {}).get("display_phone_number") or "")
            for msg in value.get("messages") or []:
                if msg.get("type") != "text":
                    continue
                sender = msg.get("from") or ""
                # Skip our own echoed/outbound messages so we never self-create a lead.
                if biz and re.sub(r"\D", "", sender) == biz:
                    continue
                out.append({
                    "id": msg.get("id") or "",
                    "from": sender,
                    "name": names.get(sender, ""),
                    "text": ((msg.get("text") or {}).get("body") or "").strip(),
                    "timestamp": msg.get("timestamp") or "",
                })
    return out
