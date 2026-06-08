"""Agentic CRM intake — turn a typed (or transcribed-from-voice) blurb into a
clean contact.

The user describes a lead in natural language; Gemini extracts the structured
CRM fields, flags any critical gaps, and writes a short, friendly follow-up
question asking only for what's genuinely missing. One Gemini call per review
(budget-guarded). Voice capture uses the device's own keyboard/OS dictation
(no AI, no quota) — the user always sees and edits plain text before this
agent ever runs over it.
"""

from __future__ import annotations

import re

from utils.crm_models import CRM_SOURCE_OPTIONS, CRM_STATUSES, DEAL_STATUSES
from utils.gemini import generate_json

# Fields the agent is allowed to populate. Mirrors the CRM contact shape so the
# result drops straight into normalize_contact().
_FIELDS = [
    "company", "name", "title", "email", "phone", "industry",
    "owner", "value", "client", "status", "deal_status", "source", "notes",
    "next_follow_up",
]

_STATUSES = CRM_STATUSES
_DEAL_STATES = DEAL_STATUSES
_SOURCES = CRM_SOURCE_OPTIONS

# A record is usable if it has SOMETHING to call it and SOME way to reach it.
_IDENTITY_FIELDS = ("company", "name")
_CHANNEL_FIELDS = ("phone", "email")


def _prompt(today: str, existing: dict | None) -> str:
    existing_block = ""
    if existing:
        filled = {k: v for k, v in existing.items() if v and k in _FIELDS}
        if filled:
            existing_block = (
                "\nThe user already provided these fields earlier — keep them unless "
                f"the new input clearly corrects them:\n{filled}\n"
            )
    return f"""You are the intake assistant for a B2B sales CRM. Today is {today}.
Extract the fields from the text the user wrote.
{existing_block}
Return ONLY a JSON object (no prose, no markdown fences) with this exact shape:
{{
  "fields": {{
    "company": "", "name": "", "title": "", "email": "", "phone": "",
    "industry": "", "owner": "", "value": "", "client": "",
    "status": one of {_STATUSES},
    "deal_status": one of {_DEAL_STATES},
    "source": one of {_SOURCES},
    "notes": "any context, requirement, objection, or next step mentioned",
    "next_follow_up": "YYYY-MM-DD if a follow-up date/relative time was mentioned, else empty"
  }},
  "missing": ["list of critical fields still missing"],
  "follow_up": "one short, warm question asking ONLY for the missing critical fields, or empty if nothing critical is missing",
  "summary": "one short sentence confirming who this lead is"
}}

Rules:
- Only fill a field if the input actually contains it. Never invent emails, phones, or names.
- A record is complete enough when it has at least one of {list(_IDENTITY_FIELDS)} AND at least one of {list(_CHANNEL_FIELDS)}.
- Normalise phone numbers to a clean format; keep country code if given (assume +91 India only if clearly an Indian number without code).
- Resolve relative dates ("next Tuesday", "in 3 days") against today's date into YYYY-MM-DD.
- Default status to "new", deal_status to "open", source to "other" unless the input implies otherwise.
- Keep "follow_up" friendly and specific, e.g. "Got Rajesh at Prestige Group — what's the best phone or email to reach him?"
"""


def _clean_fields(raw: dict) -> dict:
    fields = {k: "" for k in _FIELDS}
    incoming = raw.get("fields") if isinstance(raw.get("fields"), dict) else {}
    for k in _FIELDS:
        v = incoming.get(k, "")
        fields[k] = str(v).strip() if v is not None else ""
    # Constrain enumerated fields to known values.
    if fields["status"] not in _STATUSES:
        fields["status"] = "new"
    if fields["deal_status"] not in _DEAL_STATES:
        fields["deal_status"] = "open"
    if fields["source"] not in _SOURCES:
        fields["source"] = "other"
    return fields


def _critical_missing(fields: dict) -> list[str]:
    """Deterministic gate — don't trust the model alone for completeness."""
    missing: list[str] = []
    if not any(fields.get(f) for f in _IDENTITY_FIELDS):
        missing.append("company or name")
    if not any(fields.get(f) for f in _CHANNEL_FIELDS):
        missing.append("phone or email")
    return missing


def intake_completeness(fields: dict) -> tuple[int, int, list[str]]:
    """Return (filled_count, total_count, human labels for gaps)."""
    tracked = [
        ("company", "Company"),
        ("name", "Contact name"),
        ("phone", "Phone"),
        ("email", "Email"),
        ("title", "Title"),
        ("industry", "Industry"),
        ("owner", "Owner"),
        ("client", "Client"),
        ("value", "Value"),
        ("source", "Source"),
        ("status", "Stage"),
        ("deal_status", "Deal state"),
        ("next_follow_up", "Follow-up date"),
        ("notes", "Notes"),
    ]
    filled = sum(1 for key, _ in tracked if fields.get(key))
    gaps: list[str] = []
    if not any(fields.get(f) for f in _IDENTITY_FIELDS):
        gaps.append("company or contact name")
    if not any(fields.get(f) for f in _CHANNEL_FIELDS):
        gaps.append("phone or email")
    return filled, len(tracked), gaps


def merge_intake_fields(existing: dict | None, incoming: dict) -> dict:
    """Merge a new parse into prior confirmed fields without dropping data."""
    merged = {k: "" for k in _FIELDS}
    for k in _FIELDS:
        new_val = str(incoming.get(k) or "").strip()
        old_val = str((existing or {}).get(k) or "").strip()
        merged[k] = new_val or old_val
    return merged


def friendly_ai_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if "429" in msg or "resource_exhausted" in msg or "depleted" in msg or "quota" in msg:
        return (
            "Gemini credits are used up. Top up at aistudio.google.com, "
            "or click Continue without AI to fill the form yourself from your text."
        )
    if "budget" in msg and "exhausted" in msg:
        return "Gemini call budget for this session is exhausted. Use **Continue without AI** or try again later."
    return f"AI unavailable ({exc}). Use **Continue without AI** or the manual **Add a lead** form below."


def basic_parse_from_text(*, text: str = "", existing: dict | None = None) -> dict:
    """Regex fallback when Gemini is unavailable — pulls email/phone and keeps the rest in notes."""
    raw = (text or "").strip()
    fields = merge_intake_fields(existing, {k: "" for k in _FIELDS})
    fields["notes"] = raw
    fields["status"] = fields["status"] or "new"
    fields["deal_status"] = fields["deal_status"] or "open"
    fields["source"] = fields["source"] or "other"

    email = re.search(r"[\w.+-]+@[\w.-]+\.\w+", raw)
    if email:
        fields["email"] = email.group(0)

    phone = re.search(r"(?:\+91[\s-]?)?[6-9]\d{9}", raw.replace(" ", "")) or re.search(
        r"\+?\d[\d\s\-()]{8,16}\d", raw
    )
    if phone:
        fields["phone"] = re.sub(r"[\s()-]", "", phone.group(0))

    # "Add Priya Nair, founder of Zenith Interiors" → name + company hints
    name_match = re.search(
        r"(?:add|met)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
        raw,
        re.IGNORECASE,
    )
    if name_match:
        fields["name"] = name_match.group(1).strip()

    company_match = re.search(
        r"(?:founder of|from|at|company)\s+([A-Z][A-Za-z0-9 &.-]{2,40})",
        raw,
        re.IGNORECASE,
    )
    if company_match:
        fields["company"] = company_match.group(1).strip().rstrip(",.")

    for client_hint in ("SN Realtors", "Cadabams", "FocusChain"):
        if client_hint.lower() in raw.lower():
            fields["client"] = client_hint

    missing = _critical_missing(fields)
    follow_up = ""
    if missing:
        follow_up = f"Fill in the {', and '.join(missing)} below — AI was skipped."

    return {
        "ok": True,
        "fields": fields,
        "missing": missing,
        "follow_up": follow_up,
        "summary": "Parsed without AI — please review the fields below.",
    }


def parse_contact(*, text: str = "", today: str = "", existing: dict | None = None) -> dict:
    """Parse a typed (or transcribed) lead description into a structured CRM record.

    Returns:
        {
          "ok": bool,                # False only if Gemini gave nothing usable
          "fields": {...},           # CRM-ready field dict
          "missing": [...],          # critical gaps (deterministic)
          "follow_up": str,          # warm question for the missing bits
          "summary": str,
        }
    """
    from datetime import date

    today = today or date.today().isoformat()
    prompt = _prompt(today, existing)
    if text.strip():
        prompt += f"\nUser input:\n\"\"\"\n{text.strip()}\n\"\"\"\n"

    raw = generate_json(prompt)
    if not raw:
        return {
            "ok": False,
            "fields": {k: "" for k in _FIELDS},
            "missing": ["company or name", "phone or email"],
            "follow_up": "I couldn't read that clearly — could you check the details and try again?",
            "summary": "",
        }

    fields = merge_intake_fields(existing, _clean_fields(raw))

    missing = _critical_missing(fields)
    follow_up = str(raw.get("follow_up") or "").strip()
    if missing and not follow_up:
        follow_up = f"Almost there — I still need the {', and '.join(missing)} for this lead. Can you add that?"
    if not missing:
        follow_up = ""

    return {
        "ok": True,
        "fields": fields,
        "missing": missing,
        "follow_up": follow_up,
        "summary": str(raw.get("summary") or "").strip(),
    }
