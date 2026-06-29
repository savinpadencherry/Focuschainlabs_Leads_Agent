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

import hashlib
import hmac
import os
import re
from typing import Any

import requests

_GRAPH = "https://graph.facebook.com/v21.0"
_SESSION_SENDER_PID = "wa_sender_phone_number_id"


def verify_signature(raw_body: bytes, signature_header: str, app_secret: str) -> bool:
    """Verify Meta's X-Hub-Signature-256 over the raw request body.

    Meta signs every webhook POST with HMAC-SHA256 keyed by the app secret. We
    recompute it over the exact bytes received and constant-time compare. Returns
    False (reject) when the secret is missing or the header is malformed — the
    caller must not process unsigned/forged deliveries in production.
    """
    if not app_secret:
        return False
    sig = (signature_header or "").strip()
    if not sig.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig[len("sha256="):], expected)


def _token() -> str:
    return (os.getenv("WHATSAPP_ACCESS_TOKEN") or "").strip()


def _phone_number_id() -> str:
    return (os.getenv("WHATSAPP_PHONE_NUMBER_ID") or "").strip()


def _postgres_store():
    """Return the configured Cloud SQL store, or None outside Postgres mode."""
    try:
        from utils import crm_store_postgres as pg

        return pg if pg.postgres_configured() else None
    except Exception:
        return None


def _streamlit_tenant_account(pg, *, required: bool) -> tuple[bool, dict[str, Any] | None]:
    """Resolve the active tenant's selected WhatsApp account.

    Returns ``(is_streamlit_context, account)``. In a Streamlit session, one
    active account is selected automatically. When several active accounts exist,
    an organisation admin must choose one in the WhatsApp connections panel; the
    choice is stored in ``st.session_state``. Outside Streamlit (the webhook
    container), callers must pass a phone_number_id explicitly.
    """
    try:
        import streamlit as st
        from utils import auth
    except Exception:
        return False, None

    try:
        organization_id = auth.active_org_id()
        accounts = [
            a for a in pg.load_whatsapp_accounts(organization_id)
            if a.get("active", True)
            and (a.get("phone_number_id") or "").strip()
            and (a.get("access_token") or "").strip()
        ]
    except Exception as exc:
        if required:
            raise RuntimeError(f"Could not load this organisation's WhatsApp accounts: {exc}") from exc
        return True, None

    selected_pid = str(st.session_state.get(_SESSION_SENDER_PID) or "").strip()
    if selected_pid:
        for account in accounts:
            if str(account.get("phone_number_id") or "").strip() == selected_pid:
                return True, account
        st.session_state.pop(_SESSION_SENDER_PID, None)

    if len(accounts) == 1:
        st.session_state[_SESSION_SENDER_PID] = str(accounts[0]["phone_number_id"])
        return True, accounts[0]

    if not accounts:
        if required:
            raise RuntimeError("No active WhatsApp number is connected for this organisation.")
        return True, None

    if required:
        if not auth.is_admin():
            raise RuntimeError(
                "Multiple WhatsApp numbers are connected. An organisation admin must select "
                "the sending number before broadcasts can be sent."
            )
        raise RuntimeError(
            "Multiple WhatsApp numbers are connected. Select the sending number in the "
            "WhatsApp connections panel before sending."
        )
    return True, None


def _resolve_credentials(
    *,
    phone_number_id: str | None = None,
    access_token: str | None = None,
) -> tuple[str, str]:
    """Resolve outbound credentials without crossing tenant boundaries.

    In Cloud SQL multi-tenant mode, the database is authoritative. A supplied
    phone_number_id must exist in ``whatsapp_accounts`` and its stored token is
    used. Streamlit broadcasts resolve the active organisation's selected account.
    Global WHATSAPP_* environment variables are only a legacy single-tenant
    fallback when Postgres is not configured.
    """
    pid = (phone_number_id or "").strip()
    token = (access_token or "").strip()
    pg = _postgres_store()

    if pg is not None:
        if pid:
            account = pg.get_whatsapp_account_by_pid(pid)
            if not account or not account.get("active", True):
                raise RuntimeError("WhatsApp phone_number_id is not registered as an active account.")
            stored_token = str(account.get("access_token") or "").strip()
            if not stored_token:
                raise RuntimeError("The registered WhatsApp account has no access token.")
            return str(account.get("phone_number_id") or pid).strip(), stored_token

        in_streamlit, account = _streamlit_tenant_account(pg, required=True)
        if in_streamlit and account:
            return (
                str(account.get("phone_number_id") or "").strip(),
                str(account.get("access_token") or "").strip(),
            )

        raise RuntimeError(
            "PostgreSQL multi-tenant mode requires a registered tenant WhatsApp account; "
            "global WHATSAPP_* credentials are never used as a fallback."
        )

    resolved_pid = pid or _phone_number_id()
    resolved_token = token or _token()
    if not resolved_pid or not resolved_token:
        raise RuntimeError("WhatsApp phone number ID and access token are not configured.")
    return resolved_pid, resolved_token


def whatsapp_configured() -> bool:
    """Whether WhatsApp sending is available in the current runtime context."""
    pg = _postgres_store()
    if pg is not None:
        in_streamlit, account = _streamlit_tenant_account(pg, required=False)
        if in_streamlit:
            return bool(account)
        # Webhook runtime: the receiving phone_number_id is supplied per request
        # and resolved against Cloud SQL at send time.
        return True
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


def send_whatsapp_text(
    to: str, body: str, *,
    phone_number_id: str | None = None,
    access_token: str | None = None,
) -> dict:
    """Send a plain text message. Returns the Graph API response dict.

    In multi-tenant Postgres mode the credentials always come from the matching
    ``whatsapp_accounts`` row. Streamlit broadcasts use the active organisation's
    selected number; webhook replies pass the receiving phone_number_id. There is
    no global-token fallback in multi-tenant mode.
    """
    resolved_pid, resolved_token = _resolve_credentials(
        phone_number_id=phone_number_id,
        access_token=access_token,
    )
    resp = requests.post(
        f"{_GRAPH}/{resolved_pid}/messages",
        headers={
            "Authorization": f"Bearer {resolved_token}",
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
    phone_number_id: str | None = None,
    access_token: str | None = None,
) -> dict:
    """Send an approved WhatsApp template using tenant-scoped credentials."""
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

    resolved_pid, resolved_token = _resolve_credentials(
        phone_number_id=phone_number_id,
        access_token=access_token,
    )
    resp = requests.post(
        f"{_GRAPH}/{resolved_pid}/messages",
        headers={
            "Authorization": f"Bearer {resolved_token}",
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


def extract_sent_message_id(api_response: dict) -> str:
    """Pull wamid from Graph API send response."""
    for msg in (api_response.get("messages") or []):
        if isinstance(msg, dict) and msg.get("id"):
            return str(msg["id"])
    return ""


def parse_webhook_statuses(payload: dict) -> list[dict]:
    """Flatten status webhooks for outbound message tracking.

    Returns [{"id", "status", "recipient_id", "timestamp", "error"}].
    """
    out: list[dict] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for st in value.get("statuses") or []:
                err = ""
                for e in st.get("errors") or []:
                    if isinstance(e, dict):
                        err = e.get("title") or e.get("message") or str(e)
                        break
                out.append({
                    "id": st.get("id") or "",
                    "status": (st.get("status") or "").strip().lower(),
                    "recipient_id": st.get("recipient_id") or "",
                    "timestamp": st.get("timestamp") or "",
                    "error": err,
                })
    return out


def _parse_interactive_body(msg: dict) -> tuple[str, str, str]:
    """Return (text, interaction_id, interaction_title) from inbound message."""
    itype = msg.get("type") or ""
    if itype == "text":
        return ((msg.get("text") or {}).get("body") or "").strip(), "", ""
    if itype != "interactive":
        return "", "", ""
    interactive = msg.get("interactive") or {}
    kind = interactive.get("type") or ""
    if kind == "button_reply":
        br = interactive.get("button_reply") or {}
        return (
            (br.get("title") or "").strip(),
            (br.get("id") or "").strip(),
            (br.get("title") or "").strip(),
        )
    if kind == "list_reply":
        lr = interactive.get("list_reply") or {}
        return (
            (lr.get("title") or "").strip(),
            (lr.get("id") or "").strip(),
            (lr.get("title") or "").strip(),
        )
    return "", "", ""


def parse_webhook_messages(payload: dict) -> list[dict]:
    """Flatten Meta's nested webhook payload into inbound message dicts.

    Returns [{"id", "from", "name", "text", "timestamp", "type",
              "interaction_id", "interaction_title", "phone_number_id"}].
    Text and interactive (button/list) messages are included.

    phone_number_id identifies WHICH of your registered numbers received the
    message — use this to assign the lead to the correct agent in multi-number
    setups.
    """
    out: list[dict] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            metadata = value.get("metadata") or {}
            phone_number_id = metadata.get("phone_number_id") or ""
            names = {
                (c.get("wa_id") or ""): ((c.get("profile") or {}).get("name") or "")
                for c in value.get("contacts") or []
            }
            biz = re.sub(r"\D", "", metadata.get("display_phone_number") or "")
            for msg in value.get("messages") or []:
                mtype = msg.get("type") or ""
                if mtype not in {"text", "interactive"}:
                    continue
                sender = msg.get("from") or ""
                if biz and re.sub(r"\D", "", sender) == biz:
                    continue
                text, iid, ititle = _parse_interactive_body(msg)
                if not text and not iid:
                    continue
                out.append({
                    "id": msg.get("id") or "",
                    "from": sender,
                    "name": names.get(sender, ""),
                    "text": text,
                    "timestamp": msg.get("timestamp") or "",
                    "type": mtype,
                    "interaction_id": iid,
                    "interaction_title": ititle,
                    "phone_number_id": phone_number_id,
                })
    return out
