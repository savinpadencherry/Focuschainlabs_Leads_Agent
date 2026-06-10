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
            for msg in value.get("messages") or []:
                if msg.get("type") != "text":
                    continue
                sender = msg.get("from") or ""
                out.append({
                    "id": msg.get("id") or "",
                    "from": sender,
                    "name": names.get(sender, ""),
                    "text": ((msg.get("text") or {}).get("body") or "").strip(),
                    "timestamp": msg.get("timestamp") or "",
                })
    return out
