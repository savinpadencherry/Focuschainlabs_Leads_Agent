"""Daily AI batch — fold pending inbound WhatsApp messages into CRM records.

The cost-control idea: instead of an LLM call per inbound message (expensive at
500+ leads/org), the webhook stores messages cheaply and this job makes **one**
call per *active* contact (a contact with new messages), once a day. A hard cap
(DAILY_LLM_BUDGET) bounds the spend per org per run, and processed messages are
stamped so re-runs are cheap and idempotent.

The heavy lifting (turning message text into CRM fields + stage) reuses the same
LLM the live intake path uses — agent.crm_intake_agent.parse_contact — so the
batch and realtime paths stay consistent.

See the architecture PDF for the budget math behind the defaults.
"""

from __future__ import annotations

import os
from typing import Any, Callable

from utils.crm_models import utc_now_iso


def _char_cap() -> int:
    """Max characters of concatenated message text per contact, to bound tokens."""
    try:
        return max(200, int(os.getenv("BATCH_MSG_CHARS", "4000")))
    except (TypeError, ValueError):
        return 4000


def _default_max_calls() -> int:
    """Per-org ceiling on LLM calls in one run (≈ active contacts).

    Default 500 keeps a tenant comfortably inside ~₹2,000/month on Gemini Flash
    (≈ ₹0.10–0.12 per call × 500/day × 30). It's a *ceiling*, not a target — a
    realistic day has far fewer active contacts; anything beyond the cap simply
    carries over to the next run (its messages stay unprocessed). Raise
    DAILY_LLM_BUDGET if a tenant's volume and budget allow."""
    try:
        return max(0, int(os.getenv("DAILY_LLM_BUDGET", "500")))
    except (TypeError, ValueError):
        return 500


def _merge_contact(contact: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any]:
    """Apply LLM-extracted fields without clobbering human-entered data.

    Mirrors the webhook's realtime _llm_refresh: only fill empty fields, and
    accumulate notes rather than overwrite — so the batch is safe to run over
    contacts an operator has already edited.
    """
    updated = dict(contact)
    for k, v in (fields or {}).items():
        if k == "notes":
            continue
        if v and str(v).strip() and not str(contact.get(k) or "").strip():
            updated[k] = str(v).strip()
    new_note = str((fields or {}).get("notes") or "").strip()
    old_note = str(contact.get("notes") or "").strip()
    if new_note and new_note not in old_note:
        updated["notes"] = f"{old_note}\n{new_note}".strip()
    updated["updated_at"] = utc_now_iso()
    return updated


def _group_by_contact(rows: list[dict[str, Any]]) -> dict[str, dict[str, list]]:
    """{contact_id: {"ids": [...], "bodies": [...]}} from a flat interaction list."""
    groups: dict[str, dict[str, list]] = {}
    for r in rows:
        cid = r.get("contact_id")
        if not cid:
            continue
        g = groups.setdefault(cid, {"ids": [], "bodies": []})
        g["ids"].append(r.get("id"))
        body = (r.get("body") or "").strip()
        if body:
            g["bodies"].append(body)
    return groups


def process_org(
    organization_id: str,
    *,
    pg: Any = None,
    parse: Callable[..., dict] | None = None,
    max_calls: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Process one tenant's pending inbound messages. Returns run stats.

    `pg` and `parse` are injectable for testing; in production they default to
    crm_store_postgres and the intake agent's parse_contact.
    """
    if pg is None:
        from utils import crm_store_postgres as pg  # type: ignore[no-redef]
    if parse is None:
        from agent.crm_intake_agent import parse_contact as parse  # type: ignore[assignment]

    max_calls = _default_max_calls() if max_calls is None else max_calls
    cap = _char_cap()

    rows = pg.load_unprocessed_inbound(organization_id)
    groups = _group_by_contact(rows)

    stats: dict[str, Any] = {
        "org": organization_id, "contacts": 0, "messages": 0, "llm_calls": 0,
        "updated": 0, "skipped_no_contact": 0, "budget_stopped": False,
    }

    for cid, g in groups.items():
        if stats["llm_calls"] >= max_calls:
            # Leave the rest unprocessed (processed_at stays NULL) for next run.
            stats["budget_stopped"] = True
            break

        stats["messages"] += len(g["ids"])
        contact = pg.get_contact(cid, organization_id)
        if not contact:
            # Orphaned messages (contact deleted) — stamp so we don't retry forever.
            if not dry_run:
                pg.mark_interactions_processed(g["ids"])
            stats["skipped_no_contact"] += 1
            continue

        stats["contacts"] += 1
        text = "\n".join(g["bodies"])[:cap]
        if text:
            res = parse(text=text, existing=contact) or {}
            stats["llm_calls"] += 1
            if res.get("ok"):
                merged = _merge_contact(contact, res.get("fields") or {})
                if not dry_run:
                    pg.bulk_upsert([merged], organization_id, merge_mobile_fields=False)
                stats["updated"] += 1

        if not dry_run:
            pg.mark_interactions_processed(g["ids"])

    return stats


def process_all(
    *,
    pg: Any = None,
    parse: Callable[..., dict] | None = None,
    max_calls: int | None = None,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Process every tenant that has pending inbound messages."""
    if pg is None:
        from utils import crm_store_postgres as pg  # type: ignore[no-redef]
    org_ids = pg.org_ids_with_unprocessed_inbound()
    return [
        process_org(o, pg=pg, parse=parse, max_calls=max_calls, dry_run=dry_run)
        for o in org_ids
    ]
