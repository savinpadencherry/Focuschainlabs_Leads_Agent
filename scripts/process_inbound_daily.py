#!/usr/bin/env python3
"""Daily AI batch — fold pending inbound WhatsApp messages into CRM records.

Designed to run once a day as a Cloud Run Job (triggered by Cloud Scheduler).
It makes one cheap LLM call per *active* contact (a contact with new messages),
hard-capped by DAILY_LLM_BUDGET per org, and stamps processed messages so
re-runs are idempotent and cheap.

Usage:
    export DATABASE_URL='postgresql://…'          # or CLOUD_SQL_CONNECTION_NAME on Cloud Run
    python scripts/process_inbound_daily.py --all
    python scripts/process_inbound_daily.py --org-id sn_realtors
    python scripts/process_inbound_daily.py --all --dry-run     # no writes, just report

Cost knobs (env):
    DAILY_LLM_BUDGET   max LLM calls per org per run (default 1000)
    BATCH_MSG_CHARS    max chars of message text fed to the model per contact (default 4000)
    INBOUND_LLM_MODE   set to "batch" on the webhook so messages defer to this job
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from utils import crm_store_postgres as pg  # noqa: E402
from utils import inbound_batch  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily inbound AI batch processor")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--all", action="store_true", help="process every active tenant")
    target.add_argument("--org-id", help="process a single tenant")
    parser.add_argument(
        "--max-contacts", type=int, default=None,
        help="cap LLM calls per org this run (default: DAILY_LLM_BUDGET)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="report only; make no writes",
    )
    args = parser.parse_args()

    if not pg.postgres_configured():
        print("✗ Cloud SQL not configured — set CLOUD_SQL_CONNECTION_NAME or DATABASE_URL.")
        return 1

    try:
        if args.all:
            results = inbound_batch.process_all(
                max_calls=args.max_contacts, dry_run=args.dry_run,
            )
        else:
            results = [inbound_batch.process_org(
                args.org_id, max_calls=args.max_contacts, dry_run=args.dry_run,
            )]
    except Exception as exc:  # noqa: BLE001
        print(f"✗ batch failed: {exc}")
        return 1

    if not results:
        print("• nothing to do — no tenant has pending inbound messages.")
        return 0

    total_calls = 0
    for r in results:
        total_calls += r["llm_calls"]
        flag = "  [budget stopped]" if r["budget_stopped"] else ""
        print(
            f"• {r['org']}: {r['contacts']} contacts · {r['messages']} msgs · "
            f"{r['llm_calls']} LLM calls · {r['updated']} updated"
            f"{(' · ' + str(r['skipped_no_contact']) + ' orphaned') if r['skipped_no_contact'] else ''}"
            f"{flag}"
        )
    mode = "DRY RUN — " if args.dry_run else ""
    print(f"✓ {mode}done — {total_calls} LLM call(s) across {len(results)} org(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
