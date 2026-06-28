"""Cloud SQL PostgreSQL CRM store (psycopg2).

Production persistence for the shared CRM database used by the Leads Agent,
WhatsApp webhook REST API, and the Flutter mobile app.

Schema: db/schema_cloudsql.sql — flat `contacts` + `interactions` +
`whatsapp_accounts` tables (matches Supabase).

Multi-tenancy: shared tables, one row per tenant in `organizations`, every
tenant-owned row carries `organization_id`. Every read/write below takes it
as an explicit argument (never read off a client-supplied dict field) so a
caller can't spoof which tenant's data it touches. Callers that don't pass
one fall back to DEFAULT_ORG_ID — the single tenant this database held
before multi-tenancy existed. Row-level security is not enforced yet; this
column is the application-level guard for the first pass.

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

# Tenant every row belonged to before organization_id existed; also the
# fallback for callers (Streamlit pages, scripts) not yet org-aware.
DEFAULT_ORG_ID = "default"


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
    contact: dict[str, Any] = {
        "id": row.get("id"),
        "organization_id": row.get("organization_id") or "",
    }
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
        "organization_id": row.get("organization_id") or "",
    }


def _upsert_rows(
    cur,
    contacts: list[dict[str, Any]],
    *,
    merge_mobile_fields: bool,
    organization_id: str,
) -> None:
    update_cols = list(_WRITE_COLS) + ["updated_at"]
    if not merge_mobile_fields:
        update_cols = list(_ALL_DATA_COLS) + ["updated_at"]

    insert_cols = ["id", "organization_id", *_ALL_DATA_COLS, "created_at", "updated_at"]
    placeholders = ", ".join(["%s"] * len(insert_cols))
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
    # The WHERE guard means a conflicting id owned by a *different* org is
    # left untouched instead of being overwritten with this org's data.
    sql = (
        f"INSERT INTO contacts ({', '.join(insert_cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT (id) DO UPDATE SET {updates} "
        f"WHERE contacts.organization_id = EXCLUDED.organization_id"
    )

    rows = []
    for contact in contacts:
        if not contact.get("id"):
            continue
        parsed = _to_row(contact)
        rows.append([
            parsed["id"],
            organization_id,
            *(parsed[c] for c in _WRITE_COLS),
            parsed["sentiment"],
            parsed["notes"],
            parsed["tags"],
            parsed["created_at"],
            parsed["updated_at"],
        ])

    if rows:
        execute_batch(cur, sql, rows, page_size=200)


def load_all_contacts(organization_id: str = DEFAULT_ORG_ID) -> list[dict[str, Any]]:
    with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM contacts WHERE organization_id = %s ORDER BY updated_at DESC",
            (organization_id,),
        )
        return [_row_to_contact(r) for r in cur.fetchall()]


def get_contact(contact_id: str, organization_id: str = DEFAULT_ORG_ID) -> dict[str, Any] | None:
    with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM contacts WHERE id = %s AND organization_id = %s",
            (contact_id, organization_id),
        )
        row = cur.fetchone()
    return _row_to_contact(row) if row else None


def _all_ids(organization_id: str) -> set[str]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM contacts WHERE organization_id = %s", (organization_id,))
        return {r[0] for r in cur.fetchall()}


def count_contacts(organization_id: str = DEFAULT_ORG_ID) -> int:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM contacts WHERE organization_id = %s", (organization_id,))
        return int(cur.fetchone()[0])


def bulk_upsert(
    contacts: list[dict[str, Any]],
    organization_id: str = DEFAULT_ORG_ID,
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
            _upsert_rows(
                cur, valid,
                merge_mobile_fields=merge_mobile_fields,
                organization_id=organization_id,
            )
        conn.commit()
    return len(valid)


def delete_contacts(ids: list[str], organization_id: str = DEFAULT_ORG_ID) -> None:
    clean = [i for i in ids if i]
    if not clean:
        return
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM contacts WHERE id = ANY(%s) AND organization_id = %s",
            (clean, organization_id),
        )
        conn.commit()


def replace_all_contacts(
    contacts: list[dict[str, Any]], organization_id: str = DEFAULT_ORG_ID,
) -> int:
    """Upsert everything in `contacts`, then delete rows absent from the list.

    Guard: an empty incoming list deletes NOTHING — a failed/empty load must
    never be able to wipe the shared database. Both the upsert and the
    delete-set are scoped to organization_id, so this can never touch another
    tenant's rows.
    """
    incoming_ids = {c["id"] for c in contacts if c.get("id")}
    if not incoming_ids:
        return 0
    bulk_upsert(contacts, organization_id, merge_mobile_fields=True)
    to_delete = list(_all_ids(organization_id) - incoming_ids)
    if to_delete:
        delete_contacts(to_delete, organization_id)
    return len(incoming_ids)


# ── Interactions (WhatsApp message/status history) ────────────────────────────
_INTERACTION_COLS = (
    "author", "body", "kind", "subject", "meeting_link", "source",
    "direction", "message_id", "status", "campaign_id", "template_name", "error",
)


def _row_to_interaction(row: dict[str, Any]) -> dict[str, Any]:
    interaction: dict[str, Any] = {
        "id": row.get("id") or "",
        "contact_id": row.get("contact_id") or "",
        "organization_id": row.get("organization_id") or "",
    }
    for c in _INTERACTION_COLS:
        interaction[c] = row.get(c) or ""
    interaction["created_at"] = _iso(row.get("created_at"))
    return interaction


def load_interactions(
    contact_id: str, organization_id: str = DEFAULT_ORG_ID,
) -> list[dict[str, Any]]:
    with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM interactions WHERE contact_id = %s AND organization_id = %s "
            "ORDER BY created_at ASC",
            (contact_id, organization_id),
        )
        return [_row_to_interaction(r) for r in cur.fetchall()]


def message_id_exists(message_id: str) -> bool:
    """Durable de-dupe check — has this WhatsApp message id already been stored?"""
    mid = (message_id or "").strip()
    if not mid:
        return False
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM interactions WHERE message_id = %s LIMIT 1", (mid,))
        return cur.fetchone() is not None


def insert_interaction(
    interaction: dict[str, Any],
    organization_id: str = DEFAULT_ORG_ID,
    *,
    processed: bool = False,
) -> bool:
    """Insert one interaction row. Returns False if message_id is a duplicate
    (caught by the partial unique index, not a round-trip existence check —
    safe against concurrent webhook retries).

    processed=True stamps processed_at=now() so the daily AI batch skips this
    row — used when the inbound message was already folded into the CRM record
    in real time (INBOUND_LLM_MODE=realtime). In batch mode the webhook leaves
    it False so the daily job picks it up.
    """
    contact_id = str(interaction.get("contact_id") or "").strip()
    if not contact_id:
        raise ValueError("contact_id is required")

    values = {
        "id": interaction.get("id") or str(uuid.uuid4()),
        "contact_id": contact_id,
        "organization_id": organization_id,
        "kind": str(interaction.get("kind") or "comment"),
        "created_at": interaction.get("created_at") or utc_now_iso(),
        "processed_at": utc_now_iso() if processed else None,
    }
    for c in _INTERACTION_COLS:
        if c not in values:
            values[c] = str(interaction.get(c) or "")

    cols = ["id", "contact_id", "organization_id", *_INTERACTION_COLS,
            "created_at", "processed_at"]
    sql = (
        f"INSERT INTO interactions ({', '.join(cols)}) "
        f"VALUES ({', '.join(f'%({c})s' for c in cols)}) "
        "ON CONFLICT (message_id) WHERE message_id <> '' DO NOTHING"
    )
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, values)
        inserted = cur.rowcount > 0
        conn.commit()
    return inserted


# ── Daily AI batch queue (scripts/process_inbound_daily.py) ───────────────────
def org_ids_with_unprocessed_inbound() -> list[str]:
    """Orgs that have at least one inbound message the daily batch hasn't folded
    into a CRM record yet — so the job only does work for active tenants."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT organization_id FROM interactions "
            "WHERE processed_at IS NULL AND direction = 'inbound'"
        )
        return [r[0] for r in cur.fetchall()]


def load_unprocessed_inbound(
    organization_id: str = DEFAULT_ORG_ID, limit: int = 5000,
) -> list[dict[str, Any]]:
    """Pending inbound messages for one tenant, grouped by contact (oldest
    first), so the batch can make a single LLM call per contact."""
    with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT id, contact_id, body, created_at FROM interactions "
            "WHERE organization_id = %s AND processed_at IS NULL "
            "AND direction = 'inbound' "
            "ORDER BY contact_id, created_at ASC LIMIT %s",
            (organization_id, limit),
        )
        return [
            {
                "id": r.get("id"),
                "contact_id": r.get("contact_id") or "",
                "body": r.get("body") or "",
                "created_at": _iso(r.get("created_at")),
            }
            for r in cur.fetchall()
        ]


def mark_interactions_processed(interaction_ids: list[str]) -> int:
    """Stamp processed_at=now() on the given rows. Keyed by globally-unique id,
    so this is intentionally not org-scoped. Returns the number updated."""
    ids = [i for i in interaction_ids if i]
    if not ids:
        return 0
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE interactions SET processed_at = now() "
            "WHERE id = ANY(%s) AND processed_at IS NULL",
            (ids,),
        )
        n = cur.rowcount
        conn.commit()
    return n


def update_interaction_status(
    message_id: str, status: str, *, error: str = "",
) -> dict[str, Any] | None:
    """Update an outbound interaction's delivery status by wamid.

    Returns {"contact_id", "status", "organization_id"} of the matched row,
    or None if no interaction was ever recorded for this message id (orphan
    status receipt). message_id (Meta's wamid) is globally unique, so this
    intentionally isn't org-scoped — the caller uses the returned
    organization_id for any follow-up lookups.
    """
    mid = (message_id or "").strip()
    if not mid:
        return None
    with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "UPDATE interactions SET status = %s, error = %s "
            "WHERE message_id = %s RETURNING contact_id, status, organization_id",
            (status, error, mid),
        )
        row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


# ── WhatsApp accounts (multi-number Embedded Signup) ──────────────────────────
def load_whatsapp_accounts(organization_id: str = DEFAULT_ORG_ID) -> list[dict[str, Any]]:
    with _connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM whatsapp_accounts WHERE organization_id = %s "
            "ORDER BY connected_at DESC",
            (organization_id,),
        )
        return [_row_to_wa_account(r) for r in cur.fetchall()]


def upsert_whatsapp_account(
    account: dict[str, Any], organization_id: str = DEFAULT_ORG_ID,
) -> None:
    """Save or refresh a connected WhatsApp Business number.

    The WHERE guard on the conflict update means re-connecting a
    phone_number_id already owned by a different org leaves that row alone
    instead of handing the number to this org.
    """
    phone_number_id = str(account.get("phone_number_id") or "").strip()
    if not phone_number_id:
        raise ValueError("phone_number_id is required")

    row_id = (account.get("id") or "").strip() or str(uuid.uuid4())
    values = {
        "id": row_id,
        "phone_number_id": phone_number_id,
        "organization_id": organization_id,
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
            id, phone_number_id, organization_id, display_name, phone_number,
            waba_id, access_token, agent_name, connected_at, active
        ) VALUES (
            %(id)s, %(phone_number_id)s, %(organization_id)s, %(display_name)s,
            %(phone_number)s, %(waba_id)s, %(access_token)s, %(agent_name)s,
            %(connected_at)s, %(active)s
        )
        ON CONFLICT (phone_number_id) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            phone_number = EXCLUDED.phone_number,
            waba_id = EXCLUDED.waba_id,
            access_token = EXCLUDED.access_token,
            agent_name = EXCLUDED.agent_name,
            connected_at = EXCLUDED.connected_at,
            active = EXCLUDED.active
        WHERE whatsapp_accounts.organization_id = EXCLUDED.organization_id
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, values)
        conn.commit()


def delete_whatsapp_account(account_id: str, organization_id: str = DEFAULT_ORG_ID) -> None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM whatsapp_accounts WHERE id = %s AND organization_id = %s",
            (account_id, organization_id),
        )
        conn.commit()


def resolve_org_for_phone_number_id(phone_number_id: str) -> str | None:
    """Which tenant owns this WhatsApp Business number, or None if unknown.

    Used by the webhook to resolve organization_id for inbound traffic —
    deliberately keyed off our own whatsapp_accounts table rather than any
    field in the webhook payload, since payload contents come from Meta on
    behalf of the sender and must never be trusted to name a tenant.
    """
    pid = (phone_number_id or "").strip()
    if not pid:
        return None
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT organization_id FROM whatsapp_accounts WHERE phone_number_id = %s",
            (pid,),
        )
        row = cur.fetchone()
    return row[0] if row else None
