"""Supabase-backed CRM store (PostgREST over HTTPS).

This is the production persistence backend and the SHARED database that the
Flutter mobile app (Focuschainlabs_mobile) also reads/writes — so both the Leads
Agent and the phone app see one source of truth.

It targets the flat `contacts` schema the mobile app provisioned
(supabase/schema.sql in that repo), NOT a JSONB document. Columns:

    id, name, company, industry, phone, email, status, deal_status, value,
    owner, source, sentiment, next_follow_up, notes, tags[], created_at,
    updated_at

Activity/comments live in a separate `interactions` table (not synced here yet).

Config (env vars or Streamlit secrets):
    SUPABASE_URL   = https://<ref>.supabase.co        (or NEXT_PUBLIC_SUPABASE_URL)
    SUPABASE_KEY   = <service-role JWT>                (preferred — bypasses RLS;
                                                        the anon/publishable key
                                                        also works under the UAT
                                                        RLS policies)

Safety: because this DB has more than one writer, saves are NON-destructive.
We upsert the contacts we know about and only delete rows the app explicitly
removed — never a blanket "delete everything not in my list" — and we never
overwrite the mobile-managed columns (sentiment / notes / tags).
"""

from __future__ import annotations

import os
from typing import Any, Iterable

import requests

from utils.crm_models import utc_now_iso

# Columns this app owns and writes. We deliberately omit sentiment / notes /
# tags so our saves never clobber values the mobile app set (PostgREST's
# merge-duplicates only updates the columns we send).
_WRITE_COLS = (
    "name", "company", "industry", "phone", "email",
    "status", "deal_status", "value", "owner", "source", "next_follow_up",
    "wa_phone_number_id",
)
# Extra columns we read back for display but never write.
_READ_EXTRA = ("sentiment", "notes", "tags")

_TIMEOUT = 30


# ── Config ────────────────────────────────────────────────────────────────────
def _url() -> str:
    raw = (os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").strip()
    return raw.rstrip("/")


def _key() -> str:
    for name in (
        "SUPABASE_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_SERVICE_KEY",
        "SUPABASE_ANON_KEY",
        "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
        "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    ):
        val = (os.getenv(name) or "").strip()
        if val:
            return val
    return ""


def supabase_configured() -> bool:
    return bool(_url() and _key())


def _rest(path: str) -> str:
    return f"{_url()}/rest/v1/{path}"


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    key = _key()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


# ── Mapping between the app's contact dict and table rows ─────────────────────
def _to_row(contact: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {"id": contact["id"]}
    for c in _WRITE_COLS:
        if c == "next_follow_up":
            row[c] = contact.get("next_follow_up") or None
        else:
            # value may arrive as a number; the column is text.
            row[c] = str(contact.get(c) or "")
    row["updated_at"] = utc_now_iso()
    return row


def _row_to_contact(row: dict[str, Any]) -> dict[str, Any]:
    contact: dict[str, Any] = {"id": row.get("id")}
    for c in _WRITE_COLS:
        if c == "next_follow_up":
            contact[c] = row.get("next_follow_up") or ""
        else:
            contact[c] = row.get(c) or ""
    contact["sentiment"] = row.get("sentiment") or ""
    contact["notes"] = row.get("notes") or ""
    contact["wa_phone_number_id"] = row.get("wa_phone_number_id") or ""
    tags = row.get("tags")
    contact["tags"] = tags if isinstance(tags, list) else []
    return contact


def _chunks(seq: list[Any], size: int) -> Iterable[list[Any]]:
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


# ── Reads ─────────────────────────────────────────────────────────────────────
def load_all_contacts() -> list[dict[str, Any]]:
    resp = requests.get(
        _rest("contacts"),
        headers=_headers(),
        params={"select": "*", "order": "updated_at.desc"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return [_row_to_contact(r) for r in resp.json()]


def _all_ids() -> set[str]:
    resp = requests.get(
        _rest("contacts"), headers=_headers(),
        params={"select": "id"}, timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return {r["id"] for r in resp.json() if r.get("id")}


def count_contacts() -> int:
    resp = requests.get(
        _rest("contacts"),
        headers=_headers({"Prefer": "count=exact", "Range-Unit": "items", "Range": "0-0"}),
        params={"select": "id"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    content_range = resp.headers.get("Content-Range", "")  # e.g. "0-0/39"
    if "/" in content_range:
        total = content_range.split("/")[-1]
        if total.isdigit():
            return int(total)
    return len(resp.json())


# ── Writes ────────────────────────────────────────────────────────────────────
def bulk_upsert(contacts: list[dict[str, Any]]) -> int:
    """Insert-or-update contacts by primary key `id` (merge — never deletes)."""
    rows = [_to_row(c) for c in contacts if c.get("id")]
    if not rows:
        return 0
    for batch in _chunks(rows, 200):
        resp = requests.post(
            _rest("contacts"),
            headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
            params={"on_conflict": "id"},
            json=batch,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
    return len(rows)


def delete_contacts(ids: list[str]) -> None:
    for batch in _chunks([i for i in ids if i], 100):
        quoted = ",".join(f'"{i}"' for i in batch)
        resp = requests.delete(
            _rest("contacts"),
            headers=_headers({"Prefer": "return=minimal"}),
            params={"id": f"in.({quoted})"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()


def replace_all_contacts(contacts: list[dict[str, Any]]) -> int:
    """Persist the app's current contact list to the SHARED table, safely.

    Upserts everything in `contacts`, then deletes only rows that exist in
    Supabase but are absent from this list (i.e. the user deleted them here).

    Guard: an empty incoming list deletes NOTHING — a failed/empty load must
    never be able to wipe the shared database.
    """
    incoming_ids = {c["id"] for c in contacts if c.get("id")}
    if not incoming_ids:
        return 0
    bulk_upsert(contacts)
    to_delete = list(_all_ids() - incoming_ids)
    if to_delete:
        delete_contacts(to_delete)
    return len(incoming_ids)
