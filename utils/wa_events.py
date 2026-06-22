"""WhatsApp delivery + interaction events stored on CRM contacts.

Outbound broadcasts store Meta `wamid` message IDs so status webhooks
(sent → delivered → read → failed) can update the right lead. Inbound
button/list replies map to pipeline actions.
"""

from __future__ import annotations

from typing import Any

from utils.crm_models import new_contact_id, normalize_status, utc_now_iso
from utils.whatsapp import phone_variants

# Button / list payload id → CRM stage (customise per campaign template).
INTERACTION_STAGE_MAP: dict[str, str] = {
    "interested": "qualified",
    "yes": "qualified",
    "book_demo": "qualified",
    "not_interested": "lost",
    "no": "lost",
    "stop": "lost",
}

# Status rank — only advance forward (read implies delivered).
_STATUS_RANK = {"sent": 1, "delivered": 2, "read": 3, "failed": 0}


def normalize_wa_event(raw: dict[str, Any]) -> dict[str, Any]:
    now = utc_now_iso()
    history = raw.get("status_history") or []
    if not isinstance(history, list):
        history = []
    return {
        "id": raw.get("id") or new_contact_id(),
        "message_id": str(raw.get("message_id") or "").strip(),
        "direction": (raw.get("direction") or "outbound").strip(),
        "body": str(raw.get("body") or "").strip(),
        "status": (raw.get("status") or "sent").strip(),
        "campaign_id": str(raw.get("campaign_id") or "").strip(),
        "template_name": str(raw.get("template_name") or "").strip(),
        "interaction_id": str(raw.get("interaction_id") or "").strip(),
        "interaction_title": str(raw.get("interaction_title") or "").strip(),
        "error": str(raw.get("error") or "").strip(),
        "status_history": history,
        "created_at": raw.get("created_at") or now,
        "updated_at": raw.get("updated_at") or now,
    }


def find_contact_by_message_id(contacts: list[dict], message_id: str) -> int:
    mid = (message_id or "").strip()
    if not mid:
        return -1
    for i, c in enumerate(contacts):
        for ev in c.get("wa_events") or []:
            if isinstance(ev, dict) and (ev.get("message_id") or "") == mid:
                return i
    return -1


def find_contact_by_phone(contacts: list[dict], wa_number: str) -> int:
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


def append_outbound_event(
    contact: dict,
    *,
    message_id: str,
    body: str,
    campaign_id: str = "",
    template_name: str = "",
) -> dict:
    """Record an outbound WA send on the contact for status webhook matching."""
    event = normalize_wa_event({
        "message_id": message_id,
        "direction": "outbound",
        "body": body,
        "status": "sent",
        "campaign_id": campaign_id,
        "template_name": template_name,
        "status_history": [{"status": "sent", "at": utc_now_iso()}],
    })
    contact.setdefault("wa_events", [])
    contact["wa_events"] = list(contact.get("wa_events") or []) + [event]
    contact["updated_at"] = utc_now_iso()
    return contact


def apply_status_update(contact: dict, message_id: str, status: str, *, error: str = "") -> bool:
    """Update wa_event status from Meta webhook. Returns True if matched."""
    mid = (message_id or "").strip()
    new_status = (status or "").strip().lower()
    events = contact.get("wa_events") or []
    updated = False
    for ev in events:
        if not isinstance(ev, dict) or (ev.get("message_id") or "") != mid:
            continue
        old = (ev.get("status") or "sent").lower()
        if new_status != "failed" and _STATUS_RANK.get(new_status, 0) < _STATUS_RANK.get(old, 0):
            continue
        ev["status"] = new_status
        ev["updated_at"] = utc_now_iso()
        if error:
            ev["error"] = error
        hist = list(ev.get("status_history") or [])
        hist.append({"status": new_status, "at": utc_now_iso(), "error": error or None})
        ev["status_history"] = hist
        updated = True
        break
    if not updated:
        return False

    contact["wa_events"] = events
    contact["updated_at"] = utc_now_iso()

    # CRM automation from engagement
    tags = list(contact.get("tags") or [])
    if new_status == "read" and "wa-read" not in tags:
        tags.append("wa-read")
        contact["tags"] = tags
    if new_status == "read" and normalize_status(contact.get("status") or "new") == "new":
        contact["status"] = "contacted"
    if new_status == "failed":
        contact.setdefault("comments", []).append({
            "id": new_contact_id(),
            "author": "WhatsApp",
            "body": f"Message delivery failed: {error or 'unknown error'}",
            "source": "whatsapp",
            "created_at": utc_now_iso(),
        })
    return True


def apply_interaction(
    contact: dict,
    *,
    interaction_id: str,
    interaction_title: str,
    inbound_message_id: str = "",
) -> dict:
    """Map a button/list reply to CRM stage + log interaction."""
    iid = (interaction_id or interaction_title or "").strip().lower().replace(" ", "_")
    title = (interaction_title or interaction_id or "").strip()
    stage = INTERACTION_STAGE_MAP.get(iid)
    if not stage:
        for key, val in INTERACTION_STAGE_MAP.items():
            if key in iid:
                stage = val
                break

    event = normalize_wa_event({
        "message_id": inbound_message_id,
        "direction": "inbound",
        "body": title,
        "status": "received",
        "interaction_id": interaction_id,
        "interaction_title": title,
        "status_history": [{"status": "received", "at": utc_now_iso()}],
    })
    contact.setdefault("wa_events", [])
    contact["wa_events"] = list(contact.get("wa_events") or []) + [event]

    contact.setdefault("comments", []).append({
        "id": new_contact_id(),
        "author": contact.get("name") or "Lead",
        "body": f"WhatsApp reply: {title}",
        "source": "whatsapp",
        "created_at": utc_now_iso(),
    })

    if stage:
        contact["status"] = normalize_status(stage)
        if stage in {"won", "lost"}:
            contact["deal_status"] = stage

    tags = list(contact.get("tags") or [])
    tag = f"wa-click:{iid}" if iid else "wa-reply"
    if tag not in tags:
        tags.append(tag)
    contact["tags"] = tags
    contact["updated_at"] = utc_now_iso()
    return contact


def campaign_summary(contacts: list[dict], campaign_id: str) -> dict[str, int]:
    """Aggregate delivery stats for a broadcast campaign id."""
    stats = {"sent": 0, "delivered": 0, "read": 0, "failed": 0, "total": 0}
    cid = (campaign_id or "").strip()
    for c in contacts:
        for ev in c.get("wa_events") or []:
            if not isinstance(ev, dict):
                continue
            if cid and (ev.get("campaign_id") or "") != cid:
                continue
            if (ev.get("direction") or "") != "outbound":
                continue
            stats["total"] += 1
            st = (ev.get("status") or "sent").lower()
            if st in stats:
                stats[st] += 1
    return stats
