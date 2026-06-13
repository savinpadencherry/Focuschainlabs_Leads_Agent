"""WhatsApp → CRM webhook service (runs alongside the Streamlit app).

Streamlit can't receive webhooks, so this tiny FastAPI app does: Meta's
WhatsApp Cloud API POSTs every incoming message here; we find-or-create the
lead by phone number, log the message into the contact's conversation thread,
let the FocusChain LLM refresh the record (notes, status, follow-up), and
optionally send a short acknowledgement back on WhatsApp.

Deploy to Cloud Run (scales to zero — see docs/DEPLOYMENT.md):
    uvicorn whatsapp_webhook:app --host 0.0.0.0 --port 8080

Secrets it needs (same values as the Streamlit app where they overlap):
  WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID / WHATSAPP_VERIFY_TOKEN
  GITHUB_TOKEN / GITHUB_REPO (or the org's DATABASE_URL for Postgres tenants)
  DEEPSEEK_API_KEY (or GEMINI_API_KEY)
  WHATSAPP_ORG_ID — optional; which CRM_ORGS tenant this number belongs to
  WHATSAPP_SEND_ACK — "true" to auto-reply a short confirmation
"""

from __future__ import annotations

import json
import os
from collections import OrderedDict

from fastapi import FastAPI, Request, Response

from utils import budget
from utils.crm_models import (
    contact_fingerprint,
    merge_contacts,
    new_contact_id,
    normalize_comment,
    normalize_contact,
    utc_now_iso,
)
from utils.crm_store import load_crm, save_crm
from utils.whatsapp import (
    parse_webhook_messages,
    phone_variants,
    send_whatsapp_text,
    whatsapp_configured,
)

app = FastAPI(title="FocusChain CRM — WhatsApp webhook")

# Meta retries deliveries; remember recent message ids so a retry can't
# double-log a conversation. In-memory is fine: retries land within minutes.
_SEEN_IDS: OrderedDict[str, None] = OrderedDict()
_SEEN_MAX = 2000


def _already_seen(msg_id: str) -> bool:
    if not msg_id:
        return False
    if msg_id in _SEEN_IDS:
        return True
    _SEEN_IDS[msg_id] = None
    while len(_SEEN_IDS) > _SEEN_MAX:
        _SEEN_IDS.popitem(last=False)
    return False


def _summarize_delivery(payload: dict) -> str:
    """One-line summary of a webhook delivery, for logs.

    Meta sends *status* receipts (sent/delivered/read) on the same "messages"
    field as inbound texts. Those carry no message body, so they store nothing —
    surfacing them here makes it obvious the endpoint is alive and receiving,
    even when no lead was created. Send an actual text TO the number to test."""
    statuses = msgs = 0
    types: set[str] = set()
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            statuses += len(value.get("statuses") or [])
            for m in value.get("messages") or []:
                msgs += 1
                types.add(m.get("type") or "?")
    bits = []
    if msgs:
        bits.append(f"{msgs} message(s) [{', '.join(sorted(types))}]")
    if statuses:
        bits.append(f"{statuses} status update(s)")
    return "; ".join(bits) or "no messages or statuses"


def _org() -> dict | None:
    """Resolve which tenant this WhatsApp number feeds (None = default/GitHub)."""
    org_id = (os.getenv("WHATSAPP_ORG_ID") or "").strip()
    if not org_id:
        return None
    try:
        for o in json.loads(os.getenv("CRM_ORGS") or "[]"):
            if isinstance(o, dict) and o.get("id") == org_id:
                return o
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def _find_contact(contacts: list[dict], wa_number: str) -> int:
    """Index of the contact whose phone matches the WhatsApp sender, else -1."""
    import re

    variants = phone_variants(wa_number)
    for i, c in enumerate(contacts):
        stored = re.sub(r"\D", "", str(c.get("phone") or ""))
        if not stored:
            continue
        for v in variants:
            if stored.endswith(v) or v.endswith(stored[-10:] if len(stored) >= 10 else stored):
                return i
    return -1


def _llm_refresh(contact: dict, message_text: str) -> dict:
    """Ask the LLM to update the record from the new message. Best-effort —
    on any failure the message is still logged and the contact unchanged."""
    try:
        from agent.crm_intake_agent import parse_contact

        res = parse_contact(text=message_text, existing=contact)
        if not res.get("ok"):
            return contact
        fields = res.get("fields") or {}
        updated = dict(contact)
        for k, v in fields.items():
            if v and str(v).strip() and not str(contact.get(k) or "").strip():
                updated[k] = str(v).strip()
        # Notes accumulate rather than overwrite.
        new_note = str(fields.get("notes") or "").strip()
        old_note = str(contact.get("notes") or "").strip()
        if new_note and new_note not in old_note:
            updated["notes"] = f"{old_note}\n{new_note}".strip()
        return updated
    except Exception:  # noqa: BLE001 - LLM is optional here
        return contact


def _handle_message(msg: dict) -> str:
    """Store one WhatsApp message into the CRM. Returns a short action label."""
    org = _org()
    db, meta = load_crm(org=org)
    if meta.get("error"):
        raise RuntimeError(f"CRM load failed: {meta['error']}")

    contacts = list(db.get("contacts") or [])
    idx = _find_contact(contacts, msg["from"])

    comment = normalize_comment({
        "author": msg.get("name") or msg["from"],
        "body": msg["text"],
        "source": "whatsapp",
        "created_at": utc_now_iso(),
    })

    if idx >= 0:
        contact = dict(contacts[idx])
        contact.setdefault("comments", [])
        contact["comments"] = list(contact.get("comments") or []) + [comment]
        contact = _llm_refresh(contact, msg["text"])
        contact["updated_at"] = utc_now_iso()
        contacts[idx] = contact
        action = "updated"
        display = contact.get("name") or contact.get("company") or msg["from"]
    else:
        contact = normalize_contact({
            "id": new_contact_id(),
            "name": msg.get("name") or "",
            "phone": f"+{msg['from']}" if not msg["from"].startswith("+") else msg["from"],
            "status": "new",
            "deal_status": "open",
            "source": "whatsapp",
            "notes": "",
            "tags": ["whatsapp-inbound"],
            "comments": [comment],
        })
        contact = _llm_refresh(contact, msg["text"])
        # Guard against the LLM "merging" into an existing record's identity.
        fp = contact_fingerprint(contact)
        for i, existing in enumerate(contacts):
            if contact_fingerprint(existing) == fp:
                contacts[i] = merge_contacts(existing, contact)
                break
        else:
            contacts.append(contact)
        action = "created"
        display = contact.get("name") or msg["from"]

    db["contacts"] = contacts
    result = save_crm(db, sha=meta.get("sha"),
                      message=f"CRM: WhatsApp message from {display}", org=org)
    if result.get("error") and not result.get("committed"):
        raise RuntimeError(f"CRM save failed: {result['error']}")
    return action


@app.get("/webhook")
async def verify(request: Request) -> Response:
    """Meta's one-time webhook verification handshake."""
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == (os.getenv("WHATSAPP_VERIFY_TOKEN") or "")
        and params.get("hub.challenge")
    ):
        return Response(content=params["hub.challenge"], media_type="text/plain")
    return Response(status_code=403)


@app.post("/webhook")
async def receive(request: Request) -> dict:
    """Receive WhatsApp messages and store them as CRM activity.

    Always returns 200 quickly — Meta retries aggressively on non-200, and a
    transient CRM failure shouldn't trigger a redelivery storm. Failures are
    logged; the retry (new delivery of the same id) is deduped anyway.
    """
    payload = await request.json()
    budget.reset()  # each delivery is its own "run" for the LLM budget guard
    handled = 0
    for msg in parse_webhook_messages(payload):
        if not msg["text"] or _already_seen(msg["id"]):
            continue
        try:
            action = _handle_message(msg)
            handled += 1
            if whatsapp_configured() and (os.getenv("WHATSAPP_SEND_ACK", "").lower() == "true"):
                try:
                    send_whatsapp_text(
                        msg["from"],
                        "Got it — noted in our CRM. We'll get back to you shortly. ✅",
                    )
                except Exception:  # noqa: BLE001 - ack is a courtesy only
                    pass
            print(f"[whatsapp] {action}: {msg['from']} ({len(msg['text'])} chars)")
        except Exception as exc:  # noqa: BLE001
            print(f"[whatsapp] ERROR storing message {msg['id']}: {exc}")
    if handled == 0:
        print(f"[whatsapp] delivery received, stored nothing — {_summarize_delivery(payload)}")
    return {"status": "ok", "handled": handled}


@app.get("/healthz")
async def health() -> dict:
    return {"ok": True, "whatsapp_configured": whatsapp_configured()}
