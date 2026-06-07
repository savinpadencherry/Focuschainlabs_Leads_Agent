"""PostgreSQL-backed CRM store — the scale path for large tenants (e.g. 10k+ records).

This is an OPTIONAL backend. The default app still uses the GitHub-JSON store
(utils/crm_store.py); nothing here runs unless you set DATABASE_URL and switch
CRM_BACKEND=postgres. It's written for scale: search, filter, sort and paginate
happen in SQL (indexed), so the UI never loads thousands of rows into memory.

Connection: set DATABASE_URL to any Postgres (Neon, Cloud SQL, Supabase, …):
    postgresql://user:pass@host/dbname?sslmode=require

One database per tenant (focuschainlabs_db, sn_realtors_db, …) gives hard
isolation on a single low-cost instance — point DATABASE_URL at the right one.

Requires: psycopg[binary]>=3.1  (install only when you adopt this backend).
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

try:  # psycopg is only needed when this backend is actually used.
    import psycopg
    from psycopg.rows import dict_row
    _HAS_PSYCOPG = True
except Exception:  # noqa: BLE001
    _HAS_PSYCOPG = False

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"

# Hot columns extracted from each contact dict for indexed querying. Everything
# else is preserved in the JSONB `data` column.
_HOT_COLS = (
    "company", "name", "email", "phone", "industry", "owner",
    "client", "value", "status", "deal_status", "source",
)


def pg_configured() -> bool:
    return _HAS_PSYCOPG and bool(os.getenv("DATABASE_URL", "").strip())


def _require() -> None:
    if not _HAS_PSYCOPG:
        raise RuntimeError("psycopg is not installed — run: pip install 'psycopg[binary]>=3.1'")
    if not os.getenv("DATABASE_URL", "").strip():
        raise RuntimeError("DATABASE_URL is not set — point it at your tenant's Postgres database.")


def _conn():
    _require()
    return psycopg.connect(os.getenv("DATABASE_URL"), row_factory=dict_row, autocommit=True)


def init_schema() -> None:
    """Create tables/indexes if they don't exist. Safe to run repeatedly."""
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(sql)


# ── Mapping between the app's contact dict and table rows ─────────────────────
def _split(contact: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], Any]:
    """Return (hot_columns, jsonb_data, next_follow_up) from a contact dict."""
    hot = {c: (contact.get(c) or "") for c in _HOT_COLS}
    follow = contact.get("next_follow_up") or None
    # data = everything not promoted to a hot column (keep id out of JSONB noise)
    data = {k: v for k, v in contact.items() if k not in _HOT_COLS and k not in ("id", "next_follow_up")}
    return hot, data, follow


def _row_to_contact(row: dict[str, Any]) -> dict[str, Any]:
    contact = dict(row.get("data") or {})
    contact["id"] = row["id"]
    for c in _HOT_COLS:
        contact[c] = row.get(c) or ""
    nf = row.get("next_follow_up")
    contact["next_follow_up"] = nf.isoformat() if isinstance(nf, date) else (nf or "")
    return contact


def upsert_contact(contact: dict[str, Any]) -> None:
    hot, data, follow = _split(contact)
    cols = ["id", *_HOT_COLS, "next_follow_up", "data", "fingerprint"]
    fingerprint = contact.get("fingerprint") or ""
    values = [contact["id"], *(hot[c] for c in _HOT_COLS), follow, json.dumps(data), fingerprint]
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in (*_HOT_COLS, "next_follow_up", "data", "fingerprint"))
    placeholders = ", ".join(["%s"] * len(cols))
    sql = (
        f"INSERT INTO contacts ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT (id) DO UPDATE SET {updates}"
    )
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(sql, values)


def bulk_upsert(contacts: list[dict[str, Any]]) -> int:
    """Ingest many contacts efficiently (e.g. SN Realtors' 10k import)."""
    if not contacts:
        return 0
    cols = ["id", *_HOT_COLS, "next_follow_up", "data", "fingerprint"]
    placeholders = ", ".join(["%s"] * len(cols))
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in (*_HOT_COLS, "next_follow_up", "data", "fingerprint"))
    sql = (
        f"INSERT INTO contacts ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT (id) DO UPDATE SET {updates}"
    )
    rows = []
    for contact in contacts:
        hot, data, follow = _split(contact)
        rows.append([contact["id"], *(hot[c] for c in _HOT_COLS), follow, json.dumps(data), contact.get("fingerprint") or ""])
    with _conn() as conn, conn.cursor() as cur:
        cur.executemany(sql, rows)
    return len(rows)


def get_contact(contact_id: str) -> dict[str, Any] | None:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM contacts WHERE id = %s", (contact_id,))
        row = cur.fetchone()
    return _row_to_contact(row) if row else None


def delete_contact(contact_id: str) -> None:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM contacts WHERE id = %s", (contact_id,))


def count_contacts() -> int:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM contacts")
        return int(cur.fetchone()["n"])


_SORTS = {
    "recent": "updated_at DESC",
    "name": "lower(name) ASC, lower(company) ASC",
    "follow_up": "next_follow_up ASC NULLS LAST, lower(name) ASC",
}


def search_contacts(
    *,
    query: str = "",
    status: str = "all",
    source: str = "all",
    deal_status: str = "all",
    sort: str = "recent",
    limit: int = 25,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Server-side search/filter/sort/paginate. Returns (page_rows, total_matches)."""
    where = ["1=1"]
    params: list[Any] = []
    if query.strip():
        where.append("(company ILIKE %s OR name ILIKE %s OR email ILIKE %s OR phone ILIKE %s OR data::text ILIKE %s)")
        like = f"%{query.strip()}%"
        params += [like, like, like, like, like]
    if status != "all":
        where.append("status = %s"); params.append(status)
    if source != "all":
        where.append("source = %s"); params.append(source)
    if deal_status != "all":
        where.append("deal_status = %s"); params.append(deal_status)
    where_sql = " AND ".join(where)
    order = _SORTS.get(sort, _SORTS["recent"])

    with _conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT count(*) AS n FROM contacts WHERE {where_sql}", params)
        total = int(cur.fetchone()["n"])
        cur.execute(
            f"SELECT * FROM contacts WHERE {where_sql} ORDER BY {order} LIMIT %s OFFSET %s",
            [*params, limit, offset],
        )
        rows = cur.fetchall()
    return [_row_to_contact(r) for r in rows], total
