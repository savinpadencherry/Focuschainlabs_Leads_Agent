# Observability — seeing focuschainlabs vs SN Realtors in GCP

In the **shared multi-tenant** model there's one `crm-app` and one `crm-webhook`
serving every tenant — so you don't separate orgs by *resource*, you separate
them by **label** (per service/component) and by **`organization_id` in the
logs** (per tenant). This doc covers both.

## 1. Resource labels (what each thing is)

Every Cloud Run deploy is labelled by the CI workflows:

| Resource | Labels |
|---|---|
| `crm-app` (Streamlit) | `app=focuschain-crm, component=app, env=prod, tenant-model=shared, managed-by=github-actions` |
| `crm-webhook` (FastAPI) | `app=focuschain-crm, component=webhook, env=prod, tenant-model=shared, managed-by=github-actions` |
| `crm-daily-batch` (Job) | set the same labels when you create it (see DAILY_AI_BATCH.md) |

These power **billing breakdowns** (Billing → Reports → Group by *label*) and
filtering in the Cloud Run console. Filter the console list with
`labels.app:focuschain-crm`.

## 2. Per-tenant logs (focuschainlabs vs sn_realtors)

The app, webhook, and batch emit structured JSON via `utils/obs.py`, so Cloud
Logging exposes `jsonPayload.organization_id`. Example Logs Explorer queries:

```
# All inbound WhatsApp activity for one tenant
jsonPayload.event="inbound_message"
jsonPayload.organization_id="focuschainlabs"

# Daily batch cost/volume per tenant (one line per org per run)
jsonPayload.event="daily_batch"
jsonPayload.organization_id="sn_realtors"
```

Events emitted today: `inbound_message`, `inbound_interaction` (webhook),
`daily_batch` (job). Add more with `obs.log_event("name", organization_id=…, …)`.

## 3. Per-org log-based metrics

Turn those logs into charts (Logging → **Log-based Metrics** → Create):

- **Inbound volume per org** — counter metric, filter
  `jsonPayload.event="inbound_message"`, add a **label** `organization_id` from
  `jsonPayload.organization_id`. Now one metric, broken out per tenant.
- **Daily LLM calls per org** — distribution metric on
  `jsonPayload.event="daily_batch"`, value `jsonPayload.llm_calls`, label
  `organization_id`. This is your **cost watchdog** against the ₹2,000 budget.

## 4. Dashboard

Monitoring → Dashboards → Create, then add charts grouped by the
`organization_id` metric label:

- Inbound messages / day per org
- Daily batch LLM calls per org (with a threshold line at `DAILY_LLM_BUDGET`)
- Cloud Run request count & p95 latency (per `component`)

## 5. Alerts worth setting

- Daily batch `llm_calls` for any org **> 0.8 × DAILY_LLM_BUDGET** → budget warning.
- Webhook 5xx rate > 0 for 5 min → Meta retries / DB outage.
- Any `daily_batch` line with `budget_stopped=true` → a tenant is shedding load
  (raise the cap or investigate volume).

All of this reads from labels + structured logs the code already emits — no
per-org infrastructure required.
