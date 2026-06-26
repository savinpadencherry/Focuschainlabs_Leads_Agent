"""Cloud SQL PostgreSQL CRM store (psycopg2).

Production persistence for the shared CRM database used by the Leads Agent,
WhatsApp webhook REST API, and the Flutter mobile app.

Schema: db/schema_cloudsql.sql — flat `contacts` + `interactions` +
`whatsapp_accounts` tables (matches Supabase).

Connection modes:
  • Cloud Run: CLOUD_SQL_CONNECTION_NAME set → Unix socket at
    /cloudsql/{CLOUD_SQL_CONNECTION_NAME} (also needs DB_USER, DB_PASSWORD, DB_NAME)
  • Local dev: DATABASE_URL (standard postgresql:// connection string)
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch

from utils.crm_models import utc_now_iso

# Columns the Leads Agent owns on write. Omit sentiment / notes / tags so agent
# saves never clobber values the mobile app set.
_WRITE_COLS = (
    "name", "company", "industry", "phone", "email",
    "status", "deal_status", "value", "owner", "source", "next_follow_up",
    "wa_phone_number_id",
)
_MOBILE_COLS = ("sentiment", "notes", "tags")
_ALL_DATA_COLS = (*_WRITE_COLS, *_MOBILE_COLS)


def postgres_configured() -> bool:
    return bool(
        os.getenv("CLOUD_SQL_CONNECTION_NAME", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )


def _connect():
    cloud = os.getenv("CLOUD_SQL_CONNECTION_NAME", "").strip()
    if cloud:
        return psycopg2.connect(
            host=f"/cloudsql/{cloud}",
            user=(os.getenv("DB_USER") or "focuschain_user").strip(),
            password=(os.getenv("DB_PASSWORD") or "").strip(),
            dbname=(os.getenv("DB_NAME") or "focuschain").strip(),
        )
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError(
            "No Postgres connection — set CLOUD_SQL_CONNECTION_NAME (Cloud Run) "
            "or DATABASE_URL (local dev)."
        )
    return psycopg2.connect(url)


def _iso(val: Any) -> str:
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, date):
        return val.isoformat()
    return str(val or "")


def _parse_follow_up(raw: Any) -> date | None:
    if not raw:
        return None
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _tags(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(t) for t in raw]
    return []


def _to_row(contact: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {"id": contact["id"]}
    for c in _WRITE_COLS:
        if c == "next_follow_up":
            row[c] = _parse_follow_up(contact.get("next_follow_up"))
        else:
            row[c] = str(contact.get(c) or "")
    row["sentiment"] = str(contact.get("sentiment") or "")
    row["notes"] = str(contact.get("notes") or "")
    row["tags"] = _tags(contact.get("tags"))
    row["updated_at"] = contact.get("updated_at") or utc_now_iso()
    row["created_at"] = contact.get("created_at") or utc_now_iso()
    return row


def _row_to_contact(row: dict[str, Any]) -> dict[str, Any]:
    contact: dict[str, Any] = {"id": row.get("id")}
    for c in _WRITE_COLS:
        if c == "next_follow_up":
            contact[c] = _iso(row.get("next_follow_up"))
        else:
            contact[c] = row.get(c) or ""
    contact["sentiment"] = row.get("sentiment") or ""
    contact["notes"] = row.get("notes") or ""
    contact["wa_phone_number_id"] = row.get("wa_phone_number_id") or ""
    tags = row.get("tags")
    contact["tags"] = list(tags) if isinstance(tags, list) else []
    contact["created_at"] = _iso(row.get("created_at"))
    contact["updated_at"] = _iso(row.get("updated_at"))
    return contact


def _row_to_wa_account(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id") or "",
        "phone_number_id": row.get("phone_number_id") or "",
        "display_name": row.get("display_name") or "",
        "phone_number": row.get("phone_number") or "",
        "waba_id": row.get("waba_id") or "",
        "access_token": row.get("access_token") or "",
        "agent_name": row.get("agent_name") or "",
        "connected_at": _iso(row.get("connected_at")),
        "active": bool(row.get("active", True)),
    }


def _upsert_rows(
    cur,
    contacts: list[dict[str, Any]],
    *,
    merge_mobile_fields: bool,
) -> None:
    update_cols = list(_WRITE_COLS) + ["updated_at"]
    if not merge_mobile_fields:
        update_cols = list(_ALL_DATA_COLS) + ["updated_at"]

    insert_cols = ["id", *_ALL_DATA_COLS, "created_at", "updated_at"]
    placeholders = ", ".join(["%s"] * len(insert_cols))
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
    sql = (
        f"INSERT INTO contacts ({', '.join(insert_cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT (id) DO UPDATE SET {updates}"
    )

    rows = []
    for contact in contacts:
        if not contact.get("id"):
            continue
        parsed = _to_row(contact)
        rows.append([
            parsed["id"],
            *(parsed[c] for c in _WRITE_COLS),
            parsed["sentiment"],
            parsed["notes"],
            parsed["tags"],
            parsed["created_at"],
            parsed["updated_at"],
        ])

    if rows:
        execute_batch(cur, sql, rows, page_size=200)


def load_all_contacts() -> list[dict[str, Any]]:
    with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM contacts ORDER BY updated_at DESC")
        return [_row_to_contact(r) for r in cur.fetchall()]


def get_contact(contact_id: str) -> dict[str, Any] | None:
    with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM contacts WHERE id = %s", (contact_id,))
        row = cur.fetchone()
    return _row_to_contact(row) if row else None


def _all_ids() -> set[str]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM contacts")
        return {r[0] for r in cur.fetchall()}


def count_contacts() -> int:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM contacts")
        return int(cur.fetchone()[0])


def bulk_upsert(
    contacts: list[dict[str, Any]],
    *,
    merge_mobile_fields: bool = True,
) -> int:
    """Insert-or-update contacts by primary key `id` (merge — never deletes).

    When merge_mobile_fields is True (default), agent saves only touch _WRITE_COLS
    and leave sentiment / notes / tags untouched on conflict.
    """
    valid = [c for c in contacts if c.get("id")]
    if not valid:
        return 0
    with _connect() as conn:
        with conn.cursor() as cur:
            _upsert_rows(cur, valid, merge_mobile_fields=merge_mobile_fields)
        conn.commit()
    return len(valid)


def delete_contacts(ids: list[str]) -> None:
    clean = [i for i in ids if i]
    if not clean:
        return
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM contacts WHERE id = ANY(%s)", (clean,))
        conn.commit()


def replace_all_contacts(contacts: list[dict[str, Any]]) -> int:
    """Upsert everything in `contacts`, then delete rows absent from the list.

    Guard: an empty incoming list deletes NOTHING — a failed/empty load must
    never be able to wipe the shared database.
    """
    incoming_ids = {c["id"] for c in contacts if c.get("id")}
    if not incoming_ids:
        return 0
    bulk_upsert(contacts, merge_mobile_fields=True)
    to_delete = list(_all_ids() - incoming_ids)
    if to_delete:
        delete_contacts(to_delete)
    return len(incoming_ids)


# ── WhatsApp accounts (multi-number Embedded Signup) ──────────────────────────
def load_whatsapp_accounts() -> list[dict[str, Any]]:
    with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM whatsapp_accounts ORDER BY connected_at DESC"
        )
        return [_row_to_wa_account(r) for r in cur.fetchall()]


def upsert_whatsapp_account(account: dict[str, Any]) -> None:
    """Save or refresh a connected WhatsApp Business number."""
    phone_number_id = str(account.get("phone_number_id") or "").strip()
    if not phone_number_id:
        raise ValueError("phone_number_id is required")

    row_id = (account.get("id") or "").strip() or str(uuid.uuid4())
    values = {
        "id": row_id,
        "phone_number_id": phone_number_id,
        "display_name": str(account.get("display_name") or ""),
        "phone_number": str(account.get("phone_number") or ""),
        "waba_id": str(account.get("waba_id") or ""),
        "access_token": str(account.get("access_token") or ""),
        "agent_name": str(account.get("agent_name") or ""),
        "connected_at": account.get("connected_at") or utc_now_iso(),
        "active": account.get("active") if "active" in account else True,
    }

    sql = """
        INSERT INTO whatsapp_accounts (
            id, phone_number_id, display_name, phone_number, waba_id,
            access_token, agent_name, connected_at, active
        ) VALUES (
            %(id)s, %(phone_number_id)s, %(display_name)s, %(phone_number)s,
            %(waba_id)s, %(access_token)s, %(agent_name)s, %(connected_at)s,
            %(active)s
        )
        ON CONFLICT (phone_number_id) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            phone_number = EXCLUDED.phone_number,
            waba_id = EXCLUDED.waba_id,
            access_token = EXCLUDED.access_token,
            agent_name = EXCLUDED.agent_name,
            connected_at = EXCLUDED.connected_at,
            active = EXCLUDED.active
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, values)
        conn.commit()


def delete_whatsapp_account(account_id: str) -> None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM whatsapp_accounts WHERE id = %s", (account_id,))
        conn.commit()
