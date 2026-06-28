"""
Intel briefing local cache.

Briefings are ephemeral intelligence snapshots — important insights
are pushed to the CRM thread (GitHub-backed). Local cache is fine
for the freshness guard; it resets on Streamlit Cloud restarts.

Multi-tenant: the cache file is namespaced per organization_id so one tenant's
briefings can never appear in another tenant's Intel view. The default tenant
keeps the original (pre-multi-tenant) path so existing data isn't orphaned.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

_BASE_DIR = "data/intel"
_DEFAULT_ORG_ID = "default"
_MAX_PER_COMPANY = 5   # keep the N most recent briefings per company


def _path(organization_id: str = _DEFAULT_ORG_ID) -> str:
    """Per-tenant cache file. Default org keeps the legacy filename so its
    existing briefings.json is preserved; every other tenant gets its own."""
    org = re.sub(r"[^a-zA-Z0-9_-]", "_", (organization_id or _DEFAULT_ORG_ID).strip())
    org = org or _DEFAULT_ORG_ID
    if org == _DEFAULT_ORG_ID:
        return f"{_BASE_DIR}/briefings.json"
    return f"{_BASE_DIR}/briefings_{org}.json"


def load_briefings(organization_id: str = _DEFAULT_ORG_ID) -> list[dict[str, Any]]:
    path = _path(organization_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get("briefings", data) if isinstance(data, dict) else data
        return raw if isinstance(raw, list) else []
    except Exception:
        return []


def save_briefings(
    briefings: list[dict[str, Any]], organization_id: str = _DEFAULT_ORG_ID,
) -> None:
    path = _path(organization_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "briefings": briefings}, f,
                  indent=2, ensure_ascii=False)
        f.write("\n")


def upsert_briefings(
    new: list[dict[str, Any]], organization_id: str = _DEFAULT_ORG_ID,
) -> list[dict[str, Any]]:
    """
    Merge new briefings into the tenant's store.
    Keeps the _MAX_PER_COMPANY most recent entries per company.
    Returns the merged list.
    """
    existing = load_briefings(organization_id)

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
    save_briefings(merged, organization_id)
    return merged


def mark_pushed(briefing_id: str, organization_id: str = _DEFAULT_ORG_ID) -> None:
    """Flag a briefing as pushed to CRM."""
    briefings = load_briefings(organization_id)
    for b in briefings:
        if b.get("id") == briefing_id:
            b["pushed_to_crm"] = True
            break
    save_briefings(briefings, organization_id)
