#!/usr/bin/env python3
"""One-shot migration of existing CRM leads into Cloud SQL PostgreSQL.

Usage:
    export DATABASE_URL='postgresql://focuschain_user:PASSWORD@35.244.58.226/focuschain?sslmode=require'
    python scripts/migrate_to_cloudsql.py                        # migrate data/crm/contacts.json into the default tenant
    python scripts/migrate_to_cloudsql.py path.json              # migrate a specific file
    python scripts/migrate_to_cloudsql.py path.json --org-id acme  # migrate into a specific tenant

Prereq: apply db/schema_cloudsql.sql once against the Cloud SQL instance.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from utils import crm_store_postgres as pg  # noqa: E402


def main() -> int:
    if not pg.postgres_configured():
        print("✗ CLOUD_SQL_CONNECTION_NAME / DATABASE_URL is not set. Export and retry.")
        return 1

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path", nargs="?",
        default=os.getenv("CRM_DATA_PATH", "data/crm/contacts.json"),
        help="JSON file to migrate (default: data/crm/contacts.json)",
    )
    parser.add_argument(
        "--org-id", default=os.getenv("CRM_ORG_ID", pg.DEFAULT_ORG_ID),
        help=f"Tenant to migrate into (default: {pg.DEFAULT_ORG_ID})",
    )
    args = parser.parse_args()
    path, org_id = args.path, args.org_id

    if not os.path.exists(path):
        print(f"✗ Source file not found: {path}")
        return 1

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    contacts = [c for c in (data.get("contacts") or []) if isinstance(c, dict)]
    print(f"• Source file:        {path}")
    print(f"• Target tenant:      {org_id}")
    print(f"• Leads in file:      {len(contacts)}")

    try:
        before = pg.count_contacts(org_id)
    except Exception as exc:  # noqa: BLE001
        print(f"✗ Could not reach Cloud SQL / read `contacts` table: {exc}")
        print("  Did you apply db/schema_cloudsql.sql?")
        return 1
    print(f"• Rows in Cloud SQL:  {before} (before)")

    upserted = pg.bulk_upsert(contacts, org_id, merge_mobile_fields=False)
    after = pg.count_contacts(org_id)
    print(f"• Upserted:           {upserted}")
    print(f"• Rows in Cloud SQL:  {after} (after)")
    print("✓ Migration complete. New leads created by the app will now land here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
