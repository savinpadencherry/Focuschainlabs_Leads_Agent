"""
Intel briefing local cache.

Briefings are ephemeral intelligence snapshots — important insights
are pushed to the CRM thread (GitHub-backed). Local cache is fine
for the freshness guard; it resets on Streamlit Cloud restarts.
"""

from __future__ import annotations

import json
import os
from typing import Any

_PATH = "data/intel/briefings.json"
_MAX_PER_COMPANY = 5   # keep the N most recent briefings per company


def load_briefings() -> list[dict[str, Any]]:
    if not os.path.exists(_PATH):
        return []
    try:
        with open(_PATH, encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get("briefings", data) if isinstance(data, dict) else data
        return raw if isinstance(raw, list) else []
    except Exception:
        return []


def save_briefings(briefings: list[dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)
    with open(_PATH, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "briefings": briefings}, f,
                  indent=2, ensure_ascii=False)
        f.write("\n")


def upsert_briefings(new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Merge new briefings into existing store.
    Keeps the _MAX_PER_COMPANY most recent entries per company.
    Returns the merged list.
    """
    existing = load_briefings()

    by_company: dict[str, list[dict]] = {}
    for b in existing:
        key = (b.get("company") or "").lower().strip()
        by_company.setdefault(key, []).append(b)

    for b in new:
        key = (b.get("company") or "").lower().strip()
        if not key:
            continue
        by_company.setdefault(key, []).append(b)
        by_company[key] = sorted(
            by_company[key],
            key=lambda x: x.get("ran_at", ""),
            reverse=True,
        )[:_MAX_PER_COMPANY]

    merged = [b for group in by_company.values() for b in group]
    save_briefings(merged)
    return merged


def mark_pushed(briefing_id: str) -> None:
    """Flag a briefing as pushed to CRM."""
    briefings = load_briefings()
    for b in briefings:
        if b.get("id") == briefing_id:
            b["pushed_to_crm"] = True
            break
    save_briefings(briefings)
