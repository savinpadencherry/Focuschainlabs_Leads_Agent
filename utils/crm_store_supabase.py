"""Supabase-backed CRM store (PostgREST over HTTPS).

This is the production persistence backend. Unlike utils/crm_store_pg.py (which
needs a raw Postgres connection string + psycopg), this talks to Supabase's
auto-generated REST API using the project's service-role key — so it works with
just the URL + key the dashboard hands you, no DB password and no extra deps
beyond `requests`.

Config (env vars or Streamlit secrets):
    SUPABASE_URL   = https://<ref>.supabase.co        (or NEXT_PUBLIC_SUPABASE_URL)
    SUPABASE_KEY   = <service-role JWT>                (preferred — bypasses RLS)

The table is the `contacts` table from db/schema.sql ("hot columns + JSONB"):
filterable fields are real columns; the rest of each contact lives in `data`.
Run db/schema.sql once in the Supabase SQL editor to create it.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any, Iterable

import requests

from utils.crm_models import contact_fingerprint

# Hot columns extracted from each contact dict for indexed querying. Everything
# else is preserved in the JSONB `data` column. Mirrors crm_store_pg._HOT_COLS.
_HOT_COLS = (
    "company", "name", "email", "phone", "industry", "owner",
    "client", "value", "status", "deal_status", "source",
)

_TIMEOUT = 30


# ── Config ────────────────────────────────────────────────────────────────────
def _url() -> str:
    raw = (
        os.getenv("SUPABASE_URL")
        or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
        or ""
    ).strip()
    return raw.rstrip("/")


def _key() -> str:
    # Prefer the service-role key (bypasses Row Level Security for server-side
    # writes). Fall back to any other configured key.
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
    hot = {c: (contact.get(c) or "") for c in _HOT_COLS}
    follow = contact.get("next_follow_up") or None
    data = {
        k: v for k, v in contact.items()
        if k not in _HOT_COLS and k not in ("id", "next_follow_up")
    }
    row = {"id": contact["id"], **hot, "next_follow_up": follow, "data": data}
    row["fingerprint"] = contact.get("fingerprint") or contact_fingerprint(contact)
    return row


def _row_to_contact(row: dict[str, Any]) -> dict[str, Any]:
    contact = dict(row.get("data") or {})
    contact["id"] = row.get("id")
    for c in _HOT_COLS:
        contact[c] = row.get(c) or ""
    nf = row.get("next_follow_up")
    contact["next_follow_up"] = nf.isoformat() if isinstance(nf, date) else (nf or "")
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


def _all_ids() -> list[str]:
    resp = requests.get(
        _rest("contacts"), headers=_headers(),
        params={"select": "id"}, timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return [r["id"] for r in resp.json() if r.get("id")]


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
    """Insert-or-update many contacts by primary key `id`."""
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


def _delete_ids(ids: list[str]) -> None:
    for batch in _chunks(ids, 100):
        quoted = ",".join(f'"{i}"' for i in batch)
        resp = requests.delete(
            _rest("contacts"),
            headers=_headers({"Prefer": "return=minimal"}),
            params={"id": f"in.({quoted})"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()


def replace_all_contacts(contacts: list[dict[str, Any]]) -> int:
    """Make the table mirror exactly this list — upsert all, delete the rest.

    Mirrors the GitHub-JSON store's "overwrite the whole file" semantics so
    save_crm() can dispatch here with no behaviour change for callers.
    """
    incoming_ids = {c["id"] for c in contacts if c.get("id")}
    if contacts:
        bulk_upsert(contacts)
    existing = set(_all_ids())
    to_delete = list(existing - incoming_ids)
    if to_delete:
        _delete_ids(to_delete)
    return len(incoming_ids)
