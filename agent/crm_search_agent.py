"""AI-assisted CRM search and quick status-update intent parsing.

Turns natural-language queries like "qualified leads due this week" or
"move Radhakrishna to contacted" into structured filters the CRM UI can apply
without scanning thousands of cards. Falls back to fast local substring search
when no LLM key is configured.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from utils.crm_models import (
    CRM_SOURCE_OPTIONS,
    CRM_STATUSES,
    DEAL_STATUSES,
    display_name,
    next_pipeline_status,
    normalize_deal_status,
    normalize_source,
    normalize_status,
)
from utils.llm import generate_json, llm_configured

# Heuristic: queries with these tokens benefit from LLM parsing.
_NL_HINTS = re.compile(
    r"\b(show|find|list|due|overdue|follow.?up|stage|status|source|whatsapp|"
    r"qualified|contacted|proposal|move|advance|update|set|mark|promotion|"
    r"broadcast|this week|next week|owner)\b",
    re.I,
)


def _contact_blob(contact: dict[str, Any]) -> str:
    return " ".join(
        str(contact.get(k) or "")
        for k in (
            "id", "name", "phone", "email", "company", "industry",
            "owner", "value", "client", "notes", "status", "deal_status", "source",
        )
    ).lower()


def local_search(contacts: list[dict], query: str) -> list[dict]:
    """Fast substring search across common lead fields."""
    needle = (query or "").strip().lower()
    if not needle:
        return list(contacts)
    tokens = [t for t in re.split(r"\s+", needle) if t]
    out: list[dict] = []
    for c in contacts:
        blob = _contact_blob(c)
        if all(tok in blob for tok in tokens):
            out.append(c)
    return out


def _apply_structured_filters(contacts: list[dict], spec: dict) -> list[dict]:
    out = list(contacts)
    stage = spec.get("stage")
    if stage and stage != "all":
        out = [c for c in out if normalize_status(c.get("status") or "new") == stage]
    deal = spec.get("deal_status")
    if deal and deal != "all":
        out = [
            c for c in out
            if normalize_deal_status(
                c.get("deal_status") or "",
                stage=normalize_status(c.get("status") or "new"),
            ) == deal
        ]
    source = spec.get("source")
    if source and source != "all":
        out = [c for c in out if normalize_source(c.get("source") or "other") == source]
    follow_up = spec.get("follow_up")
    today = date.today()
    if follow_up == "due":
        out = [c for c in out if _is_due(c, today)]
    elif follow_up == "week":
        end = today + timedelta(days=7)
        out = [c for c in out if _follow_up_between(c, today, end)]
    elif follow_up == "none":
        out = [c for c in out if not (c.get("next_follow_up") or "").strip()]
    owner = (spec.get("owner") or "").strip().lower()
    if owner:
        out = [c for c in out if owner in (c.get("owner") or "").lower()]
    text = (spec.get("text") or "").strip().lower()
    if text:
        out = local_search(out, text)
    return out


def _is_due(contact: dict, today: date) -> bool:
    raw = (contact.get("next_follow_up") or "").strip()[:10]
    if not raw:
        return False
    try:
        return date.fromisoformat(raw) <= today
    except ValueError:
        return False


def _follow_up_between(contact: dict, start: date, end: date) -> bool:
    raw = (contact.get("next_follow_up") or "").strip()[:10]
    if not raw:
        return False
    try:
        d = date.fromisoformat(raw)
    except ValueError:
        return False
    return start <= d <= end


def _prompt(today: str, query: str) -> str:
    return f"""You optimise CRM lead search queries. Today is {today}.
The user typed: {query!r}

Return ONLY JSON (no markdown) with this shape:
{{
  "mode": "filter" | "status_update",
  "filters": {{
    "text": "optional name/company substring",
    "stage": "all" | one of {CRM_STATUSES},
    "deal_status": "all" | one of {DEAL_STATUSES},
    "source": "all" | one of {CRM_SOURCE_OPTIONS},
    "follow_up": "all" | "due" | "week" | "none",
    "owner": ""
  }},
  "status_update": {{
    "match_text": "name or company to find one lead",
    "new_status": "one of {CRM_STATUSES} or empty",
    "advance_next": true
  }},
  "summary": "short human-readable description of what you understood"
}}

Rules:
- mode=filter when the user wants to find/list leads.
- mode=status_update when they want to move/advance/update a lead's stage.
- advance_next=true when they say "next status", "advance", or "move forward".
- Map conversational stage names (e.g. "in proposal") to pipeline slugs.
- Prefer filter.text for person/company names instead of over-filtering.
"""


def parse_query(query: str, *, today: date | None = None) -> dict:
    """Parse a search/status query. Returns spec dict with mode + filters."""
    q = (query or "").strip()
    today = today or date.today()
    base = {
        "mode": "filter",
        "filters": {"text": q, "stage": "all", "deal_status": "all", "source": "all", "follow_up": "all", "owner": ""},
        "status_update": {"match_text": "", "new_status": "", "advance_next": False},
        "summary": "",
        "used_llm": False,
    }
    if not q:
        return base

    if llm_configured() and _NL_HINTS.search(q):
        parsed = generate_json(_prompt(today.isoformat(), q))
        if parsed:
            base["used_llm"] = True
            mode = (parsed.get("mode") or "filter").strip().lower()
            if mode in {"filter", "status_update"}:
                base["mode"] = mode
            filt = parsed.get("filters") if isinstance(parsed.get("filters"), dict) else {}
            for key in base["filters"]:
                if key in filt and filt[key]:
                    val = str(filt[key]).strip()
                    if key == "stage":
                        base["filters"][key] = normalize_status(val) if val != "all" else "all"
                    elif key == "deal_status":
                        base["filters"][key] = normalize_deal_status(val) if val != "all" else "all"
                    elif key == "source":
                        base["filters"][key] = normalize_source(val) if val != "all" else "all"
                    elif key in {"follow_up"}:
                        base["filters"][key] = val if val in {"all", "due", "week", "none"} else "all"
                    else:
                        base["filters"][key] = val
            su = parsed.get("status_update") if isinstance(parsed.get("status_update"), dict) else {}
            base["status_update"]["match_text"] = str(su.get("match_text") or filt.get("text") or q).strip()
            ns = str(su.get("new_status") or "").strip()
            base["status_update"]["new_status"] = normalize_status(ns) if ns else ""
            base["status_update"]["advance_next"] = bool(su.get("advance_next"))
            base["summary"] = str(parsed.get("summary") or "").strip()
            return base

    # Local heuristics without LLM
    low = q.lower()
    if any(w in low for w in ("move", "advance", "update", "set", "mark")) and " to " in low:
        base["mode"] = "status_update"
        parts = re.split(r"\bto\b", q, maxsplit=1, flags=re.I)
        base["status_update"]["match_text"] = parts[0].strip()
        if len(parts) > 1:
            base["status_update"]["new_status"] = normalize_status(parts[1].strip())
    elif "next status" in low or "advance" in low:
        base["mode"] = "status_update"
        base["status_update"]["match_text"] = re.sub(
            r"(move|advance|update|set|mark|next status)", "", q, flags=re.I
        ).strip()
        base["status_update"]["advance_next"] = True
    return base


def search_contacts(contacts: list[dict], query: str) -> tuple[list[dict], dict]:
    """Return filtered contacts and the parsed query spec."""
    spec = parse_query(query)
    if spec["mode"] == "status_update":
        match_text = spec["status_update"]["match_text"] or query
        matched = local_search(contacts, match_text)
        spec["matched_for_update"] = matched
        return matched, spec
    filtered = _apply_structured_filters(contacts, spec["filters"])
    if not filtered and spec["filters"].get("text"):
        filtered = local_search(contacts, spec["filters"]["text"])
    return filtered, spec


def resolve_status_update(contact: dict, spec: dict) -> str | None:
    """Pick the target stage for a status-update intent."""
    su = spec.get("status_update") or {}
    if su.get("new_status"):
        return normalize_status(su["new_status"])
    if su.get("advance_next"):
        nxt = next_pipeline_status(contact.get("status") or "new")
        return nxt
    return None
