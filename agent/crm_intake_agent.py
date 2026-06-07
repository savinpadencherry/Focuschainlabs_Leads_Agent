"""Agentic CRM intake — turn a spoken or typed blurb into a clean contact.

The user describes a lead in natural language (voice or text); Gemini extracts
the structured CRM fields, flags any critical gaps, and writes a short, friendly
follow-up question asking only for what's genuinely missing. One Gemini call per
review (budget-guarded). Voice uses Streamlit's native audio_input piped straight
to Gemini — no separate speech-to-text service, no new dependency, no new cost.
"""

from __future__ import annotations

from utils.gemini import generate_json

# Fields the agent is allowed to populate. Mirrors the CRM contact shape so the
# result drops straight into normalize_contact().
_FIELDS = [
    "company", "name", "title", "email", "phone", "industry",
    "owner", "value", "client", "status", "deal_status", "source", "notes",
    "next_follow_up",
]

_STATUSES = ["new", "contacted", "qualified", "proposal", "won", "lost"]
_DEAL_STATES = ["open", "won", "lost"]
_SOURCES = ["linkedin", "referral", "inbound", "whatsapp", "event", "other"]

# A record is usable if it has SOMETHING to call it and SOME way to reach it.
_IDENTITY_FIELDS = ("company", "name")
_CHANNEL_FIELDS = ("phone", "email")


def _prompt(today: str, existing: dict | None, transcribe: bool) -> str:
    existing_block = ""
    if existing:
        filled = {k: v for k, v in existing.items() if v and k in _FIELDS}
        if filled:
            existing_block = (
                "\nThe user already provided these fields earlier — keep them unless "
                f"the new input clearly corrects them:\n{filled}\n"
            )
    audio_note = (
        "First transcribe the spoken audio, then extract the fields from your "
        "transcription. Put the verbatim transcription in \"transcript\".\n"
        if transcribe else
        "Extract the fields from the text the user wrote.\n"
    )
    return f"""You are the intake assistant for a B2B sales CRM. Today is {today}.
{audio_note}{existing_block}
Return ONLY a JSON object (no prose, no markdown fences) with this exact shape:
{{
  "transcript": "verbatim text of what the user said (empty if input was already text)",
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


def parse_contact(
    *,
    text: str = "",
    audio_bytes: bytes | None = None,
    mime_type: str = "audio/wav",
    today: str = "",
    existing: dict | None = None,
) -> dict:
    """Parse a spoken/typed lead description into a structured CRM record.

    Returns:
        {
          "ok": bool,                # False only if Gemini gave nothing usable
          "transcript": str,         # what the user said (for voice)
          "fields": {...},           # CRM-ready field dict
          "missing": [...],          # critical gaps (deterministic)
          "follow_up": str,          # warm question for the missing bits
          "summary": str,
        }
    """
    from datetime import date

    today = today or date.today().isoformat()
    transcribe = audio_bytes is not None
    prompt = _prompt(today, existing, transcribe)
    if not transcribe and text.strip():
        prompt += f"\nUser input:\n\"\"\"\n{text.strip()}\n\"\"\"\n"

    raw = generate_json(prompt, audio_bytes=audio_bytes, mime_type=mime_type)
    if not raw:
        return {
            "ok": False,
            "transcript": text.strip(),
            "fields": {k: "" for k in _FIELDS},
            "missing": ["company or name", "phone or email"],
            "follow_up": "I couldn't read that clearly — could you type the lead's name, company, and a phone or email?",
            "summary": "",
        }

    fields = _clean_fields(raw)
    # Merge anything the user already confirmed in a previous round.
    if existing:
        for k in _FIELDS:
            if not fields.get(k) and existing.get(k):
                fields[k] = str(existing[k]).strip()

    missing = _critical_missing(fields)
    follow_up = str(raw.get("follow_up") or "").strip()
    if missing and not follow_up:
        follow_up = f"Almost there — I still need the {', and '.join(missing)} for this lead. Can you add that?"
    if not missing:
        follow_up = ""

    return {
        "ok": True,
        "transcript": str(raw.get("transcript") or text or "").strip(),
        "fields": fields,
        "missing": missing,
        "follow_up": follow_up,
        "summary": str(raw.get("summary") or "").strip(),
    }
