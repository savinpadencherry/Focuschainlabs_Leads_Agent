#!/usr/bin/env python3
"""One-shot migration of existing CRM leads into Supabase.

The app also auto-migrates on first connect, but this script lets you run the
transfer explicitly and see a before/after count.

Usage:
    export SUPABASE_URL='https://<ref>.supabase.co'
    export SUPABASE_KEY='<service-role-key>'
    python scripts/migrate_to_supabase.py            # migrate data/crm/contacts.json
    python scripts/migrate_to_supabase.py path.json  # migrate a specific file

Prereq: run db/schema.sql once in the Supabase SQL editor to create the tables.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from utils import crm_store_supabase as sb  # noqa: E402


def main() -> int:
    if not sb.supabase_configured():
        print("✗ SUPABASE_URL / SUPABASE_KEY are not set. Export them and retry.")
        return 1

    path = sys.argv[1] if len(sys.argv) > 1 else os.getenv(
        "CRM_DATA_PATH", "data/crm/contacts.json"
    )
    if not os.path.exists(path):
        print(f"✗ Source file not found: {path}")
        return 1

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    contacts = [c for c in (data.get("contacts") or []) if isinstance(c, dict)]
    print(f"• Source file:        {path}")
    print(f"• Leads in file:      {len(contacts)}")

    try:
        before = sb.count_contacts()
    except Exception as exc:  # noqa: BLE001
        print(f"✗ Could not reach Supabase / read `contacts` table: {exc}")
        print("  Did you run db/schema.sql in the Supabase SQL editor?")
        return 1
    print(f"• Rows in Supabase:   {before} (before)")

    upserted = sb.bulk_upsert(contacts)
    after = sb.count_contacts()
    print(f"• Upserted:           {upserted}")
    print(f"• Rows in Supabase:   {after} (after)")
    print("✓ Migration complete. New leads created by the app will now land here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
