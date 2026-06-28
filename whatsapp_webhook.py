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

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from utils import budget
from utils import obs
from utils.crm_models import (
    contact_fingerprint,
    merge_contacts,
    new_contact_id,
    normalize_comment,
    normalize_contact,
    normalize_status,
    utc_now_iso,
)
from utils.crm_store import load_crm, save_crm
from utils.whatsapp import (
    extract_sent_message_id,
    parse_webhook_messages,
    parse_webhook_statuses,
    phone_variants,
    send_whatsapp_text,
    verify_signature,
    whatsapp_configured,
)
from utils.wa_events import (
    apply_interaction,
    apply_status_update,
    append_outbound_event,
    find_contact_by_message_id,
)

app = FastAPI(title="FocusChain CRM — WhatsApp webhook")

# The Embedded Signup popup (served inside the Streamlit app) POSTs the connect
# result here cross-origin, so allow the app's browser origin. Restrict to the
# configured app URL(s); fall back to "*" only if none are set (dev). The connect
# endpoint authenticates via a signed state, not cookies, so this is safe.
_cors_origins = [
    o.strip() for o in (os.getenv("APP_PUBLIC_URL") or "").split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or ["*"],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# Meta retries deliveries; remember recent message ids so a retry can't
# double-log a conversation. In-memory is fine: retries land within minutes.
_SEEN_IDS: OrderedDict[str, None] = OrderedDict()
_SEEN_MAX = 2000


def _already_seen(msg_id: str) -> bool:
    """True if this WhatsApp message id has already been processed.

    Checked against the durable `interactions.message_id` unique index first
    (so a retry is caught even across Cloud Run restarts or multiple
    instances), with the in-memory set as a fast path and as the fallback
    when no Postgres backend is configured.
    """
    if not msg_id:
        return False
    if msg_id in _SEEN_IDS:
        return True

    from utils import crm_store_postgres as pg

    if pg.postgres_configured():
        try:
            if pg.message_id_exists(msg_id):
                _SEEN_IDS[msg_id] = None
                return True
        except Exception:  # noqa: BLE001 - DB hiccup; insert-time ON CONFLICT
            pass            # still guards against an actual duplicate write

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


def _batch_llm_mode() -> bool:
    """True when per-message LLM enrichment is deferred to the daily AI batch.

    INBOUND_LLM_MODE=batch (the cost-optimized SaaS default for high lead
    volumes) makes the webhook store messages cheaply without an LLM call; the
    once-a-day job (scripts/process_inbound_daily.py) then makes one call per
    active contact. Default 'realtime' keeps the original per-message behaviour.
    """
    return (os.getenv("INBOUND_LLM_MODE") or "realtime").strip().lower() == "batch"


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


def _resolve_org(phone_number_id: str) -> str | None:
    """Which Cloud SQL tenant this inbound WhatsApp number belongs to.

    Looks up whatsapp_accounts.phone_number_id → organization_id — never trusts
    the payload to name a tenant. Returns None for a number that isn't registered
    to any tenant: such traffic is REJECTED (skipped), not quietly filed under the
    default tenant, so one tenant's stray/unconfigured number can't dump data into
    another. Non-Postgres backends (single-tenant GitHub JSON / Supabase) have no
    registry, so they use the default tenant. DB errors propagate so the caller
    returns 5xx and Meta retries (rather than silently dropping the message).
    """
    from utils import crm_store_postgres as pg

    if not pg.postgres_configured():
        return pg.DEFAULT_ORG_ID
    return pg.resolve_org_for_phone_number_id(phone_number_id)


def _account_credentials(phone_number_id: str) -> dict:
    """The connected number's OWN credentials (access_token, phone_number_id) for
    sending outbound on that same number. Returns {} when unavailable — the
    caller then falls back to the global env token (single-tenant mode)."""
    from utils import crm_store_postgres as pg

    if not phone_number_id or not pg.postgres_configured():
        return {}
    try:
        return pg.get_whatsapp_account_by_pid(phone_number_id) or {}
    except Exception:  # noqa: BLE001 - outbound is best-effort
        return {}


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


def _handle_status_postgres(st: dict, pg) -> str:
    """Update the matching outbound interaction row, then apply tag/stage
    side effects directly to that one contact — no need to load/replace the
    whole contacts table for a single delivery receipt."""
    updated = pg.update_interaction_status(
        st.get("id") or "", st.get("status") or "", error=st.get("error") or "",
    )
    if not updated:
        return "status_orphan"

    contact_id = updated.get("contact_id") or ""
    organization_id = updated.get("organization_id") or pg.DEFAULT_ORG_ID
    contact = pg.get_contact(contact_id, organization_id) if contact_id else None
    if not contact:
        return "status_orphan"

    status = (st.get("status") or "").strip().lower()
    tags = list(contact.get("tags") or [])
    if status == "read" and "wa-read" not in tags:
        tags.append("wa-read")
        contact["tags"] = tags
    if status == "read" and normalize_status(contact.get("status") or "new") == "new":
        contact["status"] = "contacted"
    contact["updated_at"] = utc_now_iso()
    pg.bulk_upsert([contact], organization_id, merge_mobile_fields=False)

    if status == "failed":
        pg.insert_interaction({
            "contact_id": contact_id,
            "author": "WhatsApp",
            "body": f"Message delivery failed: {st.get('error') or 'unknown error'}",
            "kind": "comment",
            "source": "whatsapp",
        }, organization_id)
    return f"status_{st.get('status')}"


def _handle_status(st: dict) -> str:
    """Apply delivery/read/failed status to the matching outbound message."""
    from utils import crm_store_postgres as pg

    if pg.postgres_configured():
        return _handle_status_postgres(st, pg)

    # Non-Postgres backends (GitHub JSON / Supabase) still keep delivery
    # status on the contact's nested wa_events list.
    org = _org()
    db, meta = load_crm(org=org)
    if meta.get("error"):
        raise RuntimeError(f"CRM load failed: {meta['error']}")

    contacts = list(db.get("contacts") or [])
    idx = find_contact_by_message_id(contacts, st.get("id") or "")
    if idx < 0:
        return "status_orphan"

    contact = dict(contacts[idx])
    if not apply_status_update(
        contact,
        st.get("id") or "",
        st.get("status") or "",
        error=st.get("error") or "",
    ):
        return "status_skip"

    contacts[idx] = contact
    db["contacts"] = contacts
    result = save_crm(
        db,
        sha=meta.get("sha"),
        message=f"CRM: WhatsApp {st.get('status')} for {contact.get('name') or st.get('recipient_id')}",
        org=org,
    )
    if result.get("error") and not result.get("committed"):
        raise RuntimeError(f"CRM save failed: {result['error']}")
    return f"status_{st.get('status')}"


def _handle_interactive(msg: dict, organization_id: str) -> tuple[str, str]:
    """Store button/list reply and advance CRM stage when mapped.

    organization_id is resolved by the caller (from the receiving number) so an
    unregistered number is rejected before we ever touch a tenant's data.
    Returns (action, contact_id) — contact_id lets the caller record an
    outbound ack against the right interactions row.
    """
    org = _org()
    db, meta = load_crm(org=org, organization_id=organization_id)
    if meta.get("error"):
        raise RuntimeError(f"CRM load failed: {meta['error']}")

    contacts = list(db.get("contacts") or [])
    idx = _find_contact(contacts, msg["from"])

    if idx >= 0:
        contact = dict(contacts[idx])
        apply_interaction(
            contact,
            interaction_id=msg.get("interaction_id") or "",
            interaction_title=msg.get("interaction_title") or msg.get("text") or "",
            inbound_message_id=msg.get("id") or "",
        )
        contact = _llm_refresh(contact, msg.get("text") or msg.get("interaction_title") or "")
        contacts[idx] = contact
        action = "interaction"
        display = contact.get("name") or msg["from"]
    else:
        # New lead replying to a broadcast button
        contact = normalize_contact({
            "id": new_contact_id(),
            "name": msg.get("name") or "",
            "phone": f"+{msg['from']}" if not msg["from"].startswith("+") else msg["from"],
            "status": "new",
            "deal_status": "open",
            "source": "whatsapp",
            "tags": ["whatsapp-inbound"],
        })
        apply_interaction(
            contact,
            interaction_id=msg.get("interaction_id") or "",
            interaction_title=msg.get("interaction_title") or msg.get("text") or "",
            inbound_message_id=msg.get("id") or "",
        )
        contacts.append(contact)
        action = "interaction_new"
        display = contact.get("name") or msg["from"]

    contact_id = contact["id"]
    db["contacts"] = contacts
    result = save_crm(
        db, sha=meta.get("sha"), message=f"CRM: WhatsApp interaction from {display}",
        org=org, organization_id=organization_id,
    )
    if result.get("error") and not result.get("committed"):
        raise RuntimeError(f"CRM save failed: {result['error']}")

    from utils import crm_store_postgres as pg

    if pg.postgres_configured():
        # Button/list replies are handled live (stage advance), so they never
        # need the daily LLM pass — mark processed so the batch skips them.
        pg.insert_interaction({
            "contact_id": contact_id,
            "author": display,
            "body": msg.get("interaction_title") or msg.get("text") or "",
            "kind": "whatsapp_interaction",
            "source": "whatsapp",
            "direction": "inbound",
            "message_id": msg.get("id") or "",
            "status": "received",
        }, organization_id, processed=True)
    obs.log_event(
        "inbound_interaction", organization_id=organization_id,
        action=action, contact_id=contact_id, channel="whatsapp",
    )
    return action, contact_id


def _should_run_llm(text: str, is_new_contact: bool) -> bool:
    """Triage gate — only burn LLM tokens when a message is worth processing.

    New contacts always get LLM so we can extract name/company/intent.
    For existing contacts we apply simple rules: long messages or messages
    that contain intent-signal keywords trigger the LLM; short ack/filler
    messages ("ok", "thanks", "noted") are just stored as-is.

    This cuts LLM calls by ~80% for active conversations.
    """
    if is_new_contact:
        return True

    text = (text or "").strip()

    # Long messages almost always carry meaningful info.
    if len(text) > 80:
        return True

    # Intent / status-change keywords (case-insensitive).
    _TRIGGERS = {
        # buying signals
        "interested", "want to", "would like", "let's meet", "lets meet",
        "schedule", "meeting", "call", "demo", "proposal", "quote", "price",
        "budget", "cost", "how much", "confirm", "book", "proceed",
        # negative signals
        "not interested", "no thanks", "cancel", "drop", "stop",
        "not now", "later", "busy",
        # info the LLM should capture
        "my name", "i am", "i'm", "company", "requirement", "looking for",
        "project", "deadline", "urgent", "asap",
    }
    lower = text.lower()
    return any(kw in lower for kw in _TRIGGERS)


def _handle_message(msg: dict, organization_id: str) -> tuple[str, str]:
    """Store one WhatsApp message into the CRM.

    organization_id is resolved by the caller (from the receiving number) so an
    unregistered number is rejected before we ever touch a tenant's data.
    Returns (action, contact_id) — contact_id lets the caller record an
    outbound ack against the right interactions row.
    """
    org = _org()
    db, meta = load_crm(org=org, organization_id=organization_id)
    if meta.get("error"):
        raise RuntimeError(f"CRM load failed: {meta['error']}")

    contacts = list(db.get("contacts") or [])
    idx = _find_contact(contacts, msg["from"])
    is_new = idx < 0

    comment = normalize_comment({
        "author": msg.get("name") or msg["from"],
        "body": msg["text"],
        "source": "whatsapp",
        "created_at": utc_now_iso(),
    })

    # Which of our registered numbers received this message.
    wa_pid = (msg.get("phone_number_id") or "").strip()

    # Decide once whether this message warrants LLM processing. In batch mode we
    # store the message cheaply and let the daily AI job enrich it later, so the
    # per-message webhook path stays free of LLM calls.
    batch_mode = _batch_llm_mode()
    run_llm = (not batch_mode) and _should_run_llm(msg["text"], is_new_contact=is_new)
    if not run_llm:
        why = "deferred to daily batch" if batch_mode else "short/filler message"
        print(f"[whatsapp] triage: skipping realtime LLM ({why}) from {msg['from']}")

    if idx >= 0:
        contact = dict(contacts[idx])
        contact.setdefault("comments", [])
        contact["comments"] = list(contact.get("comments") or []) + [comment]
        # Track which agent number this lead talks to (first-seen wins).
        if wa_pid and not contact.get("wa_phone_number_id"):
            contact["wa_phone_number_id"] = wa_pid
        if run_llm:
            contact = _llm_refresh(contact, msg["text"])
        contact["updated_at"] = utc_now_iso()
        contacts[idx] = contact
        action = "updated"
        display = contact.get("name") or contact.get("company") or msg["from"]
        contact_id = contact["id"]
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
            "wa_phone_number_id": wa_pid,
        })
        if run_llm:  # always True for new contacts
            contact = _llm_refresh(contact, msg["text"])
        contact_id = contact["id"]
        # Guard against the LLM "merging" into an existing record's identity.
        fp = contact_fingerprint(contact)
        for i, existing in enumerate(contacts):
            if contact_fingerprint(existing) == fp:
                contacts[i] = merge_contacts(existing, contact)
                contact_id = contacts[i]["id"]
                break
        else:
            contacts.append(contact)
        action = "created"
        display = contact.get("name") or msg["from"]

    db["contacts"] = contacts
    result = save_crm(
        db, sha=meta.get("sha"), message=f"CRM: WhatsApp message from {display}",
        org=org, organization_id=organization_id,
    )
    if result.get("error") and not result.get("committed"):
        raise RuntimeError(f"CRM save failed: {result['error']}")

    from utils import crm_store_postgres as pg

    if pg.postgres_configured():
        # In realtime mode we already folded this message into the record, so
        # mark it processed; in batch mode leave it for the daily AI job.
        pg.insert_interaction({
            "contact_id": contact_id,
            "author": display,
            "body": msg["text"],
            "kind": "whatsapp_message",
            "source": "whatsapp",
            "direction": "inbound",
            "message_id": msg["id"],
            "status": "received",
        }, organization_id, processed=not batch_mode)
    obs.log_event(
        "inbound_message", organization_id=organization_id,
        action=action, contact_id=contact_id, channel="whatsapp",
    )
    return action, contact_id


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


def _persist_outbound_ack(contact_id: str, resp: dict, body: str, organization_id: str) -> None:
    """Record the auto-ack send so the later delivery-status webhook has an
    interactions row to match against. Best-effort — an ack is a courtesy."""
    if not contact_id:
        return
    from utils import crm_store_postgres as pg

    if not pg.postgres_configured():
        return
    try:
        mid = extract_sent_message_id(resp)
        if not mid:
            return
        pg.insert_interaction({
            "contact_id": contact_id,
            "author": "FocusChain CRM",
            "body": body,
            "kind": "whatsapp_message",
            "source": "whatsapp",
            "direction": "outbound",
            "message_id": mid,
            "status": "sent",
        }, organization_id)
    except Exception:  # noqa: BLE001
        pass


@app.post("/webhook")
async def receive(request: Request) -> Response:
    """Receive WhatsApp messages and store them as CRM activity.

    Returns 200 once every message/status in this delivery was durably
    stored. If persisting any of them raised (e.g. a transient Cloud SQL
    outage), returns 500 so Meta retries the whole delivery — safe to retry
    because already-stored messages are skipped via the message_id de-dupe.

    Authenticity: when META_APP_SECRET is set, the X-Hub-Signature-256 HMAC over
    the raw body is verified first — an unsigned or forged delivery is rejected
    with 403 before any processing.
    """
    raw = await request.body()
    app_secret = (os.getenv("META_APP_SECRET") or "").strip()
    if app_secret:
        if not verify_signature(raw, request.headers.get("X-Hub-Signature-256", ""), app_secret):
            print("[whatsapp] REJECTED delivery: bad X-Hub-Signature-256")
            return Response(status_code=403, content='{"error":"bad signature"}',
                            media_type="application/json")
    else:
        print("[whatsapp] WARNING: META_APP_SECRET not set — webhook signature unverified")

    try:
        payload = json.loads(raw or b"{}")
    except (ValueError, json.JSONDecodeError):
        return Response(status_code=400, content='{"error":"invalid json"}',
                        media_type="application/json")

    budget.reset()  # each delivery is its own "run" for the LLM budget guard
    handled = 0
    status_handled = 0
    rejected = 0
    failed = False

    for st in parse_webhook_statuses(payload):
        try:
            action = _handle_status(st)
            if action != "status_orphan":
                status_handled += 1
            print(f"[whatsapp] {action}: {st.get('id', '')[:24]}… → {st.get('status')}")
        except Exception as exc:  # noqa: BLE001
            failed = True
            print(f"[whatsapp] ERROR status {st.get('id')}: {exc}")

    for msg in parse_webhook_messages(payload):
        if _already_seen(msg["id"]):
            continue
        is_interactive = (msg.get("type") == "interactive") or bool(msg.get("interaction_id"))
        if not msg.get("text") and not is_interactive:
            continue
        try:
            pid = msg.get("phone_number_id") or ""
            organization_id = _resolve_org(pid)
            if organization_id is None:
                # Number isn't registered to any tenant — reject, don't default it.
                rejected += 1
                obs.log_event("rejected_unregistered_number", phone_number_id=pid,
                              severity="WARNING")
                print(f"[whatsapp] REJECTED message from unregistered number (pid={pid[:18]})")
                continue
            if is_interactive:
                action, contact_id = _handle_interactive(msg, organization_id)
            else:
                action, contact_id = _handle_message(msg, organization_id)
            handled += 1
            if (
                not is_interactive
                and whatsapp_configured()
                and (os.getenv("WHATSAPP_SEND_ACK", "").lower() == "true")
            ):
                try:
                    ack_text = "Got it — noted in our CRM. We'll get back to you shortly. ✅"
                    creds = _account_credentials(pid)
                    resp = send_whatsapp_text(
                        msg["from"], ack_text,
                        phone_number_id=pid or None,
                        access_token=creds.get("access_token") or None,
                    )
                    _persist_outbound_ack(contact_id, resp, ack_text, organization_id)
                except Exception:  # noqa: BLE001 - ack is a courtesy only
                    pass
            print(f"[whatsapp] {action}: {msg['from']} ({len(msg.get('text') or '')} chars)")
        except Exception as exc:  # noqa: BLE001
            failed = True
            print(f"[whatsapp] ERROR storing message {msg['id']}: {exc}")
    if handled == 0 and status_handled == 0:
        print(f"[whatsapp] delivery received, stored nothing — {_summarize_delivery(payload)}")

    body = {"status": "partial_failure" if failed else "ok",
            "handled": handled, "statuses": status_handled, "rejected": rejected}
    return Response(
        content=json.dumps(body), media_type="application/json",
        status_code=500 if failed else 200,
    )


@app.get("/healthz")
async def health() -> dict:
    return {"ok": True, "whatsapp_configured": whatsapp_configured()}


@app.get("/status")
async def status() -> dict:
    """Second health route — some Cloud Run / load-balancer front ends 404 on
    /healthz depending on routing config, so expose an identical check here."""
    return {"ok": True, "whatsapp_configured": whatsapp_configured()}


@app.post("/connect/whatsapp")
async def connect_whatsapp(request: Request) -> Response:
    """Complete WhatsApp Embedded Signup for a tenant.

    The Streamlit app's connect popup POSTs {code, state, waba_id,
    phone_number_id}. The tenant is taken from the HMAC-signed `state` (minted
    server-side by the app) — never from a plain browser field — so one tenant
    can't attach a number to another. We exchange the code for a business token,
    resolve the number from Meta, and store it under that org.
    """
    from utils import wa_embedded_signup as es

    if not es.exchange_configured():
        raise HTTPException(status_code=503, detail="WhatsApp connect not configured")

    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid JSON")

    organization_id = es.verify_state(str(body.get("state") or ""))
    if not organization_id:
        raise HTTPException(status_code=401, detail="Invalid or expired connect state")

    code = str(body.get("code") or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    try:
        result = es.complete_connection(
            organization_id=organization_id,
            code=code,
            waba_id=str(body.get("waba_id") or "").strip(),
            phone_number_id=str(body.get("phone_number_id") or "").strip(),
        )
    except Exception as exc:  # noqa: BLE001 - surface a clean error to the popup
        return Response(
            content=json.dumps({"ok": False, "error": str(exc)}),
            media_type="application/json", status_code=502,
        )

    print(f"[whatsapp] connected {result.get('phone_number_id')} → org {organization_id}")
    return Response(
        content=json.dumps({"ok": True, **result}),
        media_type="application/json", status_code=200,
    )


# ── REST API (Flutter mobile app) ─────────────────────────────────────────────
def _api_keys() -> dict[str, str]:
    """Map bearer token → organization_id.

    API_KEYS (JSON object, e.g. {"key-for-acme": "acme", "key-for-beta": "beta"})
    takes precedence so each tenant's mobile app gets its own key. Falls back
    to the single legacy API_SECRET_KEY mapped to the default tenant, so
    existing single-tenant deployments keep working unchanged.
    """
    raw = (os.getenv("API_KEYS") or "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {str(k): str(v) for k, v in parsed.items() if k and v}
        except (json.JSONDecodeError, TypeError):
            pass

    from utils import crm_store_postgres as pg

    legacy_key = (os.getenv("API_SECRET_KEY") or "").strip()
    return {legacy_key: pg.DEFAULT_ORG_ID} if legacy_key else {}


def _mobile_api_enabled() -> bool:
    """The Flutter REST API stays OFF until per-user token auth ships.

    Today it authenticates with a single shared per-org key, which is fine for a
    server-to-server integration but not for a public mobile app. Until each
    end-user has their own token, the API is disabled by default and only turns
    on with an explicit MOBILE_API_ENABLED=true — so it can never be left
    accidentally public.
    """
    return (os.getenv("MOBILE_API_ENABLED") or "").strip().lower() in ("1", "true", "yes")


def _require_api_key(request: Request) -> str:
    """Gate the API, validate the bearer token, return the scoped organization_id."""
    if not _mobile_api_enabled():
        raise HTTPException(status_code=503, detail="Mobile API disabled")
    keys = _api_keys()
    if not keys:
        raise HTTPException(status_code=503, detail="API not configured")
    auth = (request.headers.get("Authorization") or "").strip()
    token = auth[len("Bearer "):] if auth.startswith("Bearer ") else ""
    org_id = keys.get(token) if token else None
    if not org_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return org_id


def _pg():
    from utils import crm_store_postgres as pg

    if not pg.postgres_configured():
        raise HTTPException(status_code=503, detail="Database not configured")
    return pg


def _public_account(account: dict) -> dict:
    """Strip secrets (the WhatsApp access_token) before returning over the API."""
    return {k: v for k, v in account.items() if k != "access_token"}


@app.get("/api/contacts")
async def api_list_contacts(organization_id: str = Depends(_require_api_key)) -> list[dict]:
    return _pg().load_all_contacts(organization_id)


@app.get("/api/contacts/{contact_id}")
async def api_get_contact(
    contact_id: str, organization_id: str = Depends(_require_api_key),
) -> dict:
    pg = _pg()
    contact = pg.get_contact(contact_id, organization_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    contact["interactions"] = pg.load_interactions(contact_id, organization_id)
    return contact


@app.post("/api/contacts")
async def api_upsert_contact(
    request: Request, organization_id: str = Depends(_require_api_key),
) -> dict:
    body = await request.json()
    if not isinstance(body, dict) or not body.get("id"):
        raise HTTPException(status_code=400, detail="Contact dict with id required")
    _pg().bulk_upsert([body], organization_id, merge_mobile_fields=False)
    return {"ok": True, "id": body["id"]}


@app.put("/api/contacts/{contact_id}")
async def api_patch_contact(
    contact_id: str, request: Request, organization_id: str = Depends(_require_api_key),
) -> dict:
    patch = await request.json()
    if not isinstance(patch, dict):
        raise HTTPException(status_code=400, detail="JSON object required")
    pg = _pg()
    existing = pg.get_contact(contact_id, organization_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Contact not found")
    merged = {**existing, **patch, "id": contact_id}
    pg.bulk_upsert([merged], organization_id, merge_mobile_fields=False)
    return {"ok": True, "id": contact_id}


@app.delete("/api/contacts/{contact_id}")
async def api_delete_contact(
    contact_id: str, organization_id: str = Depends(_require_api_key),
) -> dict:
    pg = _pg()
    if not pg.get_contact(contact_id, organization_id):
        raise HTTPException(status_code=404, detail="Contact not found")
    pg.delete_contacts([contact_id], organization_id)
    return {"ok": True, "id": contact_id}


@app.post("/api/contacts/bulk")
async def api_bulk_contacts(
    request: Request, organization_id: str = Depends(_require_api_key),
) -> dict:
    body = await request.json()
    if not isinstance(body, list):
        raise HTTPException(status_code=400, detail="JSON array required")
    contacts = [c for c in body if isinstance(c, dict) and c.get("id")]
    n = _pg().bulk_upsert(contacts, organization_id, merge_mobile_fields=False)
    return {"ok": True, "upserted": n}


@app.get("/api/whatsapp-accounts")
async def api_list_whatsapp_accounts(
    organization_id: str = Depends(_require_api_key),
) -> list[dict]:
    # Never expose the WhatsApp access_token over the API.
    return [_public_account(a) for a in _pg().load_whatsapp_accounts(organization_id)]


@app.post("/api/whatsapp-accounts")
async def api_upsert_whatsapp_account(
    request: Request, organization_id: str = Depends(_require_api_key),
) -> dict:
    body = await request.json()
    if not isinstance(body, dict) or not body.get("phone_number_id"):
        raise HTTPException(
            status_code=400, detail="Account dict with phone_number_id required",
        )
    try:
        _pg().upsert_whatsapp_account(body, organization_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "phone_number_id": body["phone_number_id"]}


@app.delete("/api/whatsapp-accounts/{account_id}")
async def api_delete_whatsapp_account(
    account_id: str, organization_id: str = Depends(_require_api_key),
) -> dict:
    accounts = _pg().load_whatsapp_accounts(organization_id)
    if not any(a.get("id") == account_id for a in accounts):
        raise HTTPException(status_code=404, detail="WhatsApp account not found")
    _pg().delete_whatsapp_account(account_id, organization_id)
    return {"ok": True, "id": account_id}
