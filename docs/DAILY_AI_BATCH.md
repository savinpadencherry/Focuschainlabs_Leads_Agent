# Daily AI Batch — cost-optimised inbound processing

Turning 500+ leads/org of WhatsApp chatter into updated CRM records **without**
an LLM call per message. The webhook stores messages cheaply; a once-a-day job
makes **one** Gemini Flash call per *active* contact.

## How it works

```
inbound WhatsApp message
   └─ webhook (INBOUND_LLM_MODE=batch): store row in `interactions`, processed_at = NULL   ← no LLM, ~free
                                              │
            (once a day) Cloud Scheduler ─────┼──> Cloud Run Job: scripts/process_inbound_daily.py --all
                                              │       ├─ group pending messages by contact
                                              │       ├─ ONE parse_contact() LLM call per contact
                                              │       ├─ merge fields + stage into the CRM record (fill-empties, accumulate notes)
                                              └───────┴─ stamp processed_at = now()   ← idempotent, cheap re-runs
```

- **One call per contact, not per message.** A contact who sent 8 messages
  yesterday costs **one** call, with all 8 messages concatenated (capped at
  `BATCH_MSG_CHARS`).
- **Per-org hard cap.** `DAILY_LLM_BUDGET` (default 500) bounds calls per org per
  run. Beyond it, messages simply carry to the next day (their `processed_at`
  stays NULL).
- **Idempotent.** Processed rows are stamped, so a re-run (or a crash mid-run)
  never double-charges.
- **Safe merges.** Only empty fields are filled and notes accumulate, so the
  batch never clobbers what an operator typed.

## Cost model (why it fits ~₹2,000/month/org)

| Item | Estimate |
|---|---|
| Model | Gemini 2.5 Flash |
| Tokens / call | ~1.5k in + ~0.3k out |
| Cost / call | ≈ ₹0.10–0.12 |
| Cap | 500 calls/org/day (`DAILY_LLM_BUDGET`) |
| Worst case | 500 × 30 × ₹0.11 ≈ **₹1,650/month/org** |
| Realistic | far fewer contacts are active on a given day → well under the cap |

The old path (LLM per inbound message, in the webhook) could fire thousands of
calls/day under load. Batching collapses that to "active contacts/day".

## Run it

```bash
# locally / ad-hoc
export DATABASE_URL='postgresql://…'
python scripts/process_inbound_daily.py --all            # every active tenant
python scripts/process_inbound_daily.py --org-id sn_realtors
python scripts/process_inbound_daily.py --all --dry-run  # report only, no writes
```

## Deploy (Cloud Run Job + Scheduler)

The job **reuses the webhook image** (the Dockerfile already ships `scripts/`),
just overriding the command. Full GCP-console walkthrough lives in the
architecture PDF; the CLI shape is:

```bash
# build is shared with the webhook; then create the job:
gcloud run jobs deploy crm-daily-batch \
  --image "$IMAGE_URI" \
  --region "$REGION" \
  --command python --args scripts/process_inbound_daily.py,--all \
  --set-env-vars INBOUND_LLM_MODE=batch,DAILY_LLM_BUDGET=500 \
  --set-cloudsql-instances "$CLOUD_SQL_CONNECTION_NAME"

# run it once a day at 02:00:
gcloud scheduler jobs create http crm-daily-batch-trigger \
  --schedule "0 2 * * *" --location "$REGION" \
  --uri "https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT/jobs/crm-daily-batch:run" \
  --http-method POST --oauth-service-account-email "$RUN_INVOKER_SA"
```

And set `INBOUND_LLM_MODE=batch` on the **webhook** service so messages defer to
the job instead of being enriched per-message.
