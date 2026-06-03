"""CRM contact schema and conversions from agent lead records."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


# Simple pipeline — easy to scan at a glance
CRM_STATUSES = [
    "new",
    "contacted",
    "interested",
    "won",
    "lost",
]

STATUS_LABELS = {
    "new": "New",
    "contacted": "Contacted",
    "interested": "Interested",
    "won": "Won",
    "lost": "Lost",
}

# Map legacy / agent statuses into the simple set
_STATUS_ALIASES = {
    "qualified": "interested",
    "meeting": "interested",
    "proposal": "interested",
    "nurture": "contacted",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_contact_id() -> str:
    return str(uuid.uuid4())


def empty_crm_db() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": utc_now_iso(),
        "contacts": [],
    }


def normalize_status(raw: str) -> str:
    s = (raw or "new").lower().strip()
    s = _STATUS_ALIASES.get(s, s)
    return s if s in CRM_STATUSES else "new"


def normalize_contact(raw: dict[str, Any]) -> dict[str, Any]:
    """Ensure all CRM fields exist with sane defaults."""
    now = utc_now_iso()
    status = normalize_status(raw.get("status") or "new")

    tags = raw.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    source = (raw.get("source") or "manual").strip()
    if source == "agent" and "agent-import" not in tags:
        tags = ["agent-import"] + tags

    return {
        "id": raw.get("id") or new_contact_id(),
        "name": (raw.get("name") or raw.get("contact_name") or "").strip(),
        "company": (raw.get("company") or raw.get("company_name") or "").strip(),
        "phone": (raw.get("phone") or "").strip(),
        "email": (raw.get("email") or "").strip(),
        "client": (raw.get("client") or "").strip(),
        "status": status,
        "notes": (raw.get("notes") or "").strip(),
        "next_follow_up": (raw.get("next_follow_up") or "").strip(),
        "source": source,
        "tags": tags,
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
            "status": "new",
            "notes": "\n".join(note_lines),
            "source": "agent",
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
    for key in ("name", "phone", "email", "company", "client"):
        if not (existing.get(key) or "").strip() and (incoming.get(key) or "").strip():
            merged[key] = incoming[key]
    merged["status"] = existing.get("status") or "new"
    if incoming.get("notes") and not existing.get("notes"):
        merged["notes"] = incoming["notes"]
    merged["created_at"] = existing.get("created_at") or incoming.get("created_at")
    merged["updated_at"] = utc_now_iso()
    merged["tags"] = list(dict.fromkeys((existing.get("tags") or []) + (incoming.get("tags") or [])))
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
    src = (contact.get("source") or "").lower()
    if src == "agent" or "agent-import" in (contact.get("tags") or []):
        return "Agent"
    return "Manual"
