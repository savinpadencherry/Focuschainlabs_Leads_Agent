"""CRM contact schema and conversions from agent lead records."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any


# Default sales pipeline shown as the Stage dropdown in the CRM UI.
CRM_STATUSES = [
    "new",
    "contacted",
    "qualified",
    "proposal",
    "won",
    "lost",
]

STATUS_LABELS = {
    "new": "New",
    "contacted": "Contacted",
    "qualified": "Qualified",
    "proposal": "Proposal",
    "won": "Won",
    "lost": "Lost",
}

CRM_SOURCE_OPTIONS = [
    "linkedin",
    "referral",
    "inbound",
    "whatsapp",
    "event",
    "other",
]

SOURCE_LABELS = {
    "linkedin": "LinkedIn",
    "referral": "Referral",
    "inbound": "Inbound",
    "whatsapp": "WhatsApp",
    "event": "Event",
    "other": "Other",
}

DEAL_STATUSES = ["open", "won", "lost"]

DEAL_STATUS_LABELS = {
    "open": "Open",
    "won": "Won",
    "lost": "Lost",
}

# Map legacy / alternate wording into the default set
_STATUS_ALIASES = {
    # Legacy from earlier UI versions
    "interested": "qualified",
    # Common variants / typos
    "meeting": "qualified",
    "meeting_booked": "qualified",
    "meeting_scheduled": "qualified",
    "proposal_sent": "proposal",
    "nurture": "contacted",
    "nurturing": "contacted",
}

_STATUS_SLUG_RE = re.compile(r"[^a-z0-9]+")

_SOURCE_ALIASES = {
    "agent": "other",
    "manual": "other",
    "website": "inbound",
    "web": "inbound",
    "wa": "whatsapp",
    "whats_app": "whatsapp",
}

_DEAL_STATUS_ALIASES = {
    "active": "open",
    "new": "open",
    "contacted": "open",
    "qualified": "open",
    "proposal": "open",
    "closed_won": "won",
    "closed_lost": "lost",
}


def _slugify_status(raw: str) -> str:
    s = (raw or "").lower().strip()
    s = _STATUS_SLUG_RE.sub("_", s).strip("_")
    s = re.sub(r"_+", "_", s)
    return s


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_contact_id() -> str:
    return str(uuid.uuid4())


def empty_crm_db() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": utc_now_iso(),
        "contacts": [],
        "custom_statuses": [],
    }


def normalize_status(raw: str) -> str:
    """Normalize the Stage dropdown value, falling back to ``new``."""
    s = _slugify_status(raw or "new")
    s = _STATUS_ALIASES.get(s, s)
    return s if s in CRM_STATUSES else "new"


def normalize_source(raw: str) -> str:
    """Normalize the lead Source dropdown value."""
    s = _slugify_status(raw or "other")
    s = _SOURCE_ALIASES.get(s, s)
    return s if s in CRM_SOURCE_OPTIONS else "other"


def normalize_deal_status(raw: str, *, stage: str = "") -> str:
    """Normalize overall deal Status: Open, Won, or Lost."""
    if not raw and stage in {"won", "lost"}:
        return stage
    s = _slugify_status(raw or "open")
    s = _DEAL_STATUS_ALIASES.get(s, s)
    return s if s in DEAL_STATUSES else "open"


def normalize_email_event(raw: dict) -> dict:
    now = utc_now_iso()
    return {
        "id": raw.get("id") or new_contact_id(),
        "direction": (raw.get("direction") or "sent").strip().lower(),
        "sent_at": str(raw.get("sent_at") or raw.get("date") or now).strip(),
        "from_addr": (raw.get("from_addr") or raw.get("from") or raw.get("sender") or "").strip(),
        "to": (raw.get("to") or raw.get("recipient") or "").strip(),
        "subject": (raw.get("subject") or "").strip(),
        "body": (raw.get("body") or raw.get("message") or "").strip(),
        "summary": (raw.get("summary") or raw.get("insight") or "").strip(),
        "source": (raw.get("source") or "manual").strip(),
        "created_at": raw.get("created_at") or now,
    }


def normalize_comment(raw: dict) -> dict:
    return {
        "id": raw.get("id") or new_contact_id(),
        "created_at": raw.get("created_at") or utc_now_iso(),
        "author": (raw.get("author") or raw.get("owner") or "").strip(),
        "body": (raw.get("body") or raw.get("comment") or raw.get("note") or "").strip(),
        "type": "comment",
    }


def normalize_contact_person(raw: dict) -> dict:
    return {
        "id": raw.get("id") or new_contact_id(),
        "name": (raw.get("name") or raw.get("contact_name") or "").strip(),
        "title": (raw.get("title") or raw.get("contact_title") or "").strip(),
        "email": (raw.get("email") or raw.get("contact_email") or "").strip(),
        "phone": (raw.get("phone") or "").strip(),
        "created_at": raw.get("created_at") or utc_now_iso(),
    }


def normalize_contact(raw: dict[str, Any]) -> dict[str, Any]:
    """Ensure all CRM fields exist with sane defaults."""
    now = utc_now_iso()
    status = normalize_status(raw.get("status") or raw.get("stage") or "new")
    deal_status = normalize_deal_status(raw.get("deal_status") or raw.get("deal_state") or "", stage=status)

    tags = raw.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    original_source = (raw.get("source") or "").strip().lower()
    source = normalize_source(raw.get("source") or raw.get("lead_source") or "other")
    if original_source == "agent" and "agent-import" not in tags:
        tags = ["agent-import"] + tags

    raw_email_events = raw.get("email_events") or raw.get("emails") or []
    if not isinstance(raw_email_events, list):
        raw_email_events = []
    email_events = [
        normalize_email_event(event)
        for event in raw_email_events
        if isinstance(event, dict)
    ]

    return {
        "id": raw.get("id") or new_contact_id(),
        "name": (raw.get("name") or raw.get("contact_name") or "").strip(),
        "company": (raw.get("company") or raw.get("company_name") or "").strip(),
        "industry": (raw.get("industry") or "").strip(),
        "phone": (raw.get("phone") or "").strip(),
        "email": (raw.get("email") or raw.get("contact_email") or "").strip(),
        "client": (raw.get("client") or "").strip(),
        "owner": (raw.get("owner") or "").strip(),
        "value": str(raw.get("value") or raw.get("deal_value") or "").strip(),
        "status": status,
        "deal_status": deal_status,
        "notes": (raw.get("notes") or "").strip(),
        "next_follow_up": (raw.get("next_follow_up") or "").strip(),
        "source": source,
        "tags": tags,
        "email_events": email_events,
        "created_at": raw.get("created_at") or now,
        "updated_at": raw.get("updated_at") or now,
        # Kept in storage but hidden from simple UI — agent import extras
        "title": (raw.get("title") or raw.get("contact_title") or "").strip(),
        "linkedin_url": (raw.get("linkedin_url") or "").strip(),
        "website": (raw.get("website") or "").strip(),
        "score": int(raw.get("score") or raw.get("total_score") or 0),
        "signal": (raw.get("signal") or raw.get("primary_signal") or "").strip(),
        "opening_line": (raw.get("opening_line") or "").strip(),
        "agent_run_id": (raw.get("agent_run_id") or "").strip(),
        "comments": [normalize_comment(c) for c in (raw.get("comments") or []) if isinstance(c, dict)],
        "contact_people": [normalize_contact_person(p) for p in (raw.get("contact_people") or []) if isinstance(p, dict)],
    }


def lead_to_contact(lead: dict[str, Any], *, agent_run_id: str = "") -> dict[str, Any]:
    """Map agent lead → simple CRM contact. Agent fluff goes into notes, not columns."""
    note_lines = []
    if lead.get("pain_point"):
        note_lines.append(str(lead["pain_point"]))
    if lead.get("opening_line"):
        note_lines.append(f"Opener: {lead['opening_line']}")
    if lead.get("selection_note"):
        note_lines.append(str(lead["selection_note"]))

    return normalize_contact(
        {
            "name": lead.get("contact_name", ""),
            "company": lead.get("company_name", ""),
            "phone": lead.get("phone", ""),
            "email": lead.get("email", ""),
            "client": lead.get("client", ""),
            "industry": lead.get("industry", ""),
            "owner": lead.get("owner", ""),
            "value": lead.get("value", ""),
            "status": "new",
            "deal_status": "open",
            "notes": "\n".join(note_lines),
            "source": lead.get("source", "other"),
            "tags": ["agent-import"],
            "title": lead.get("contact_title", ""),
            "linkedin_url": lead.get("linkedin_url", ""),
            "website": lead.get("website", ""),
            "score": lead.get("total_score", 0),
            "signal": lead.get("primary_signal", ""),
            "opening_line": lead.get("opening_line", ""),
            "agent_run_id": agent_run_id,
        }
    )


def contact_fingerprint(contact: dict[str, Any]) -> str:
    email = (contact.get("email") or "").lower().strip()
    if email and "@" in email and "manual" not in email:
        return f"email:{email}"
    name = (contact.get("name") or "").lower().strip()
    company = (contact.get("company") or "").lower().strip()
    phone = "".join(ch for ch in (contact.get("phone") or "") if ch.isdigit())[-10:]
    if phone:
        return f"phone:{phone}:{name or company}"
    if name and company:
        return f"nameco:{name}:{company}"
    if name:
        return f"name:{name}"
    if company:
        return f"company:{company}"
    return f"id:{contact.get('id', '')}"


def merge_contacts(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = normalize_contact({**existing, **incoming, "id": existing["id"]})
    for key in ("name", "phone", "email", "company", "client", "industry", "owner", "value"):
        existing_value = str(existing.get(key) or "").strip()
        incoming_value = str(incoming.get(key) or "").strip()
        if not existing_value and incoming_value:
            merged[key] = incoming_value
    merged["status"] = normalize_status(existing.get("status") or "new")
    merged["deal_status"] = normalize_deal_status(
        existing.get("deal_status") or incoming.get("deal_status") or "",
        stage=merged["status"],
    )
    if incoming.get("notes") and not existing.get("notes"):
        merged["notes"] = incoming["notes"]
    merged["created_at"] = existing.get("created_at") or incoming.get("created_at")
    merged["updated_at"] = utc_now_iso()
    merged["tags"] = list(dict.fromkeys((existing.get("tags") or []) + (incoming.get("tags") or [])))
    merged["email_events"] = [
        normalize_email_event(event)
        for event in (existing.get("email_events") or []) + (incoming.get("email_events") or [])
        if isinstance(event, dict)
    ]
    merged["comments"] = (existing.get("comments") or []) + [
        c for c in (incoming.get("comments") or [])
        if c.get("id") not in {x.get("id") for x in (existing.get("comments") or [])}
    ]
    merged["contact_people"] = (existing.get("contact_people") or []) + [
        p for p in (incoming.get("contact_people") or [])
        if p.get("id") not in {x.get("id") for x in (existing.get("contact_people") or [])}
    ]
    return merged


def display_name(contact: dict[str, Any]) -> str:
    return contact.get("name") or contact.get("company") or "Unnamed"


def display_subtitle(contact: dict[str, Any]) -> str:
    parts = []
    if contact.get("name") and contact.get("company"):
        parts.append(contact["company"])
    if contact.get("phone"):
        parts.append(contact["phone"])
    elif contact.get("email"):
        parts.append(contact["email"])
    if contact.get("client"):
        parts.append(contact["client"])
    return " · ".join(parts) or "No phone or email yet"


def source_label(contact: dict[str, Any]) -> str:
    src = normalize_source(contact.get("source") or "other")
    return SOURCE_LABELS.get(src, "Other")
