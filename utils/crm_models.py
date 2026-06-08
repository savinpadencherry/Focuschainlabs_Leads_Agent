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

# Invoice lifecycle (Finance Agent). "overdue" is computed dynamically from the
# due date — it is never stored, so a paid invoice can never be flagged overdue.
INVOICE_STATUSES = ["draft", "sent", "paid", "cancelled"]

INVOICE_STATUS_LABELS = {
    "draft": "Draft",
    "sent": "Sent",
    "paid": "Paid",
    "overdue": "Overdue",
    "cancelled": "Cancelled",
}

_INVOICE_STATUS_ALIASES = {
    "issued": "sent",
    "unpaid": "sent",
    "pending": "sent",
    "settled": "paid",
    "complete": "paid",
    "completed": "paid",
    "void": "cancelled",
    "canceled": "cancelled",
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


def normalize_email_event(raw: dict[str, Any]) -> dict[str, Any]:
    """Store client email history as structured, LLM-ready CRM timeline data."""
    now = utc_now_iso()
    direction = (raw.get("direction") or "sent").strip().lower()
    if direction not in {"sent", "received"}:
        direction = "sent"
    return {
        "id": raw.get("id") or new_contact_id(),
        "direction": direction,
        "sent_at": str(raw.get("sent_at") or raw.get("date") or now).strip(),
        "from_addr": (raw.get("from_addr") or raw.get("from") or raw.get("sender") or "").strip(),
        "to": (raw.get("to") or raw.get("recipient") or "").strip(),
        "subject": (raw.get("subject") or "").strip(),
        "body": (raw.get("body") or raw.get("message") or "").strip(),
        "summary": (raw.get("summary") or raw.get("insight") or "").strip(),
        "source": (raw.get("source") or "manual").strip(),
        "created_at": raw.get("created_at") or now,
    }


def normalize_comment(raw: dict[str, Any]) -> dict[str, Any]:
    """Store CRM comments as timeline entries for account-level context."""
    now = utc_now_iso()
    comment = {
        "id": raw.get("id") or new_contact_id(),
        "created_at": raw.get("created_at") or now,
        "author": (raw.get("author") or raw.get("owner") or "").strip(),
        "body": (raw.get("body") or raw.get("comment") or raw.get("note") or "").strip(),
        "subject": (raw.get("subject") or "").strip(),
        "meeting_link": (raw.get("meeting_link") or "").strip(),
        "source": (raw.get("source") or "manual").strip(),
        "type": "comment",
    }
    return comment


def to_amount(raw: Any) -> float:
    """Parse a money value that may contain currency symbols, commas, or spaces."""
    if isinstance(raw, (int, float)):
        return round(float(raw), 2)
    s = re.sub(r"[^0-9.\-]", "", str(raw or ""))
    if not s or s in {"-", ".", "-."}:
        return 0.0
    try:
        return round(float(s), 2)
    except ValueError:
        return 0.0


def normalize_invoice_status(raw: str) -> str:
    """Normalize a stored invoice status (never returns the computed 'overdue')."""
    s = _slugify_status(raw or "draft")
    s = _INVOICE_STATUS_ALIASES.get(s, s)
    return s if s in INVOICE_STATUSES else "draft"


def normalize_invoice_line(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize one invoice line item, computing amount = qty × rate when absent."""
    qty  = to_amount(raw.get("qty") if raw.get("qty") not in (None, "") else 1)
    rate = to_amount(raw.get("rate") if raw.get("rate") not in (None, "") else raw.get("amount"))
    if raw.get("amount") not in (None, ""):
        amount = to_amount(raw.get("amount"))
    else:
        amount = round(qty * rate, 2)
    return {
        "item": (raw.get("item") or raw.get("description") or "").strip(),
        "description": (raw.get("description") or raw.get("detail") or "").strip(),
        "qty": qty,
        "rate": rate,
        "amount": amount,
    }


def normalize_invoice(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a stored invoice record. Totals are recomputed from line items so
    the stored numbers are always internally consistent.
    """
    now = utc_now_iso()
    lines = [
        normalize_invoice_line(li)
        for li in (raw.get("line_items") or [])
        if isinstance(li, dict)
    ]
    subtotal = round(sum(li["amount"] for li in lines), 2)
    tax_rate = to_amount(raw.get("tax_rate"))
    # Allow an explicit stored total (e.g. legacy import) but prefer recompute.
    if lines:
        tax_amount = round(subtotal * tax_rate / 100.0, 2)
        total = round(subtotal + tax_amount, 2)
    else:
        total = to_amount(raw.get("total"))
        tax_amount = to_amount(raw.get("tax_amount"))
        subtotal = round(total - tax_amount, 2)

    dunning = [
        {
            "level": int(d.get("level") or 1),
            "sent_at": str(d.get("sent_at") or d.get("date") or now),
            "to": (d.get("to") or "").strip(),
        }
        for d in (raw.get("dunning") or [])
        if isinstance(d, dict)
    ]

    return {
        "id": raw.get("id") or new_contact_id(),
        "number": (raw.get("number") or raw.get("invoice_number") or "").strip(),
        "contact_id": (raw.get("contact_id") or "").strip(),
        "company": (raw.get("company") or "").strip(),
        "currency": (raw.get("currency") or "INR").strip().upper(),
        "issue_date": (raw.get("issue_date") or raw.get("date") or now[:10]).strip(),
        "due_date": (raw.get("due_date") or "").strip(),
        "line_items": lines,
        "subtotal": subtotal,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "total": total,
        "status": normalize_invoice_status(raw.get("status")),
        "notes": (raw.get("notes") or "").strip(),
        "paid_at": (raw.get("paid_at") or "").strip(),
        "dunning": dunning,
        "created_at": raw.get("created_at") or now,
        "updated_at": raw.get("updated_at") or now,
    }


def invoice_is_overdue(invoice: dict[str, Any], *, today: str = "") -> bool:
    """An invoice is overdue if it's been sent (not paid/cancelled) and past due."""
    if normalize_invoice_status(invoice.get("status")) != "sent":
        return False
    due = (invoice.get("due_date") or "").strip()
    if not due:
        return False
    today = today or utc_now_iso()[:10]
    return due < today


def invoice_display_status(invoice: dict[str, Any], *, today: str = "") -> str:
    """Stored status, upgraded to 'overdue' when a sent invoice is past due."""
    if invoice_is_overdue(invoice, today=today):
        return "overdue"
    return normalize_invoice_status(invoice.get("status"))


def normalize_contact_person(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize additional people attached to the same client/account."""
    now = utc_now_iso()
    return {
        "id": raw.get("id") or new_contact_id(),
        "name": (raw.get("name") or raw.get("contact_name") or "").strip(),
        "title": (raw.get("title") or raw.get("contact_title") or "").strip(),
        "email": (raw.get("email") or raw.get("contact_email") or "").strip(),
        "phone": (raw.get("phone") or "").strip(),
        "role": (raw.get("role") or "").strip(),
        "created_at": raw.get("created_at") or now,
    }


def normalize_contact(raw: dict[str, Any]) -> dict[str, Any]:
    """Ensure all CRM fields exist with sane defaults."""
    now = utc_now_iso()
    status = normalize_status(raw.get("status") or raw.get("stage") or "new")
    deal_status = normalize_deal_status(raw.get("deal_status") or raw.get("deal_state") or "", stage=status)
    if status in {"won", "lost"}:
        deal_status = status
    elif deal_status in {"won", "lost"}:
        status = deal_status

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

    raw_comments = raw.get("comments") or raw.get("comment_thread") or []
    if not isinstance(raw_comments, list):
        raw_comments = []
    comments = [
        normalize_comment(comment)
        for comment in raw_comments
        if isinstance(comment, dict)
    ]

    raw_people = raw.get("contact_people") or raw.get("contacts") or []
    if not isinstance(raw_people, list):
        raw_people = []
    contact_people = [
        normalize_contact_person(person)
        for person in raw_people
        if isinstance(person, dict)
    ]

    raw_meetings = raw.get("meetings") or []
    if not isinstance(raw_meetings, list):
        raw_meetings = []
    meetings = [
        normalize_comment(m)
        for m in raw_meetings
        if isinstance(m, dict)
    ]

    raw_invoices = raw.get("invoices") or []
    if not isinstance(raw_invoices, list):
        raw_invoices = []
    invoices = [
        normalize_invoice(inv)
        for inv in raw_invoices
        if isinstance(inv, dict)
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
        "comments": comments,
        "contact_people": contact_people,
        "invoices": invoices,
        "meetings": meetings,
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


def _merge_nested_records(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    normalizer: Any,
) -> list[dict[str, Any]]:
    """Keep existing manual context when an import repeats the same nested record."""
    merged: dict[str, dict[str, Any]] = {}
    for raw in existing + incoming:
        if not isinstance(raw, dict):
            continue
        record = normalizer(raw)
        merged.setdefault(record["id"], record)
    return list(merged.values())


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
    merged["email_events"] = _merge_nested_records(
        existing.get("email_events") or [],
        incoming.get("email_events") or [],
        normalize_email_event,
    )
    merged["comments"] = _merge_nested_records(
        existing.get("comments") or [],
        incoming.get("comments") or [],
        normalize_comment,
    )
    merged["contact_people"] = _merge_nested_records(
        existing.get("contact_people") or [],
        incoming.get("contact_people") or [],
        normalize_contact_person,
    )
    merged["invoices"] = _merge_nested_records(
        existing.get("invoices") or [],
        incoming.get("invoices") or [],
        normalize_invoice,
    )
    merged["meetings"] = _merge_nested_records(
        existing.get("meetings") or [],
        incoming.get("meetings") or [],
        normalize_comment,
    )
    return normalize_contact(merged)


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
