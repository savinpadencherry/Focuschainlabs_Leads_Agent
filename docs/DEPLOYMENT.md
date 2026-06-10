# Deployment & Cost — FocusChain Leads Agent (multi-tenant)

This is the plan to run the app for **multiple client organisations** (FocusChain
Labs, SN Realtors, …) under one subscription, **ultra cost-optimised**, in ₹.
All prices are **asia-south1 (Mumbai)**, rounded, ≈ ₹83.5/US$ — confirm live rates
on the [GCP](https://cloud.google.com/products/calculator) / [Neon](https://neon.tech/pricing) pricing pages.

---

## 1. Architecture (recommended)

```
                         ┌───────────────────────────────────────┐
   Browser (voice/text)  │   Cloud Run — Streamlit container      │
   ───────────────────►  │   focuschain-leads-agent              │
                         │   scales 0 → N · pay only when in use  │
                         └───────────────┬───────────────────────┘
                                         │  org login routes to that org's DB
                         ┌───────────────┼────────────────────────┐
                         ▼                                         ▼
              ┌────────────────────┐                  ┌────────────────────┐
              │  focuschainlabs_db │                  │   sn_realtors_db    │
              │  contacts/invoices │                  │  contacts/invoices  │
              └─────────┬──────────┘                  └─────────┬──────────┘
                        └──────────────────┬────────────────────┘
                                           ▼
                       ┌────────────────────────────────────────┐
                       │  ONE Postgres server (Neon, autosuspend)│
                       │  one DATABASE per tenant = hard isolation│
                       └────────────────────────────────────────┘
            external APIs (per-tenant keys): Gemini · Serper · Apify
            stored in Secret Manager — each client pays their own usage
```

**Key idea:** one Cloud Run service + one Postgres server. Tenants are separated
by **database** (`focuschainlabs_db`, `sn_realtors_db`), not by duplicated
infrastructure. Add a tenant = create a database + a login, not a new server.

---

## 2. Resources & why

| Resource | Why we need it | Pricing | ₹/month (realistic) |
|---|---|---|---|
| **Cloud Run** | Runs the Streamlit app. It's stateful (WebSocket per user) so it needs a long-running server, not a "function". Scales to zero = ₹0 when idle. | Free: 180K vCPU-s + 360K GiB-s + 2M req/mo, then ~$0.000024/vCPU-s | ₹0 idle → ~₹400–700 per *actively used* org |
| **Neon Postgres** | CRM data is relational (contacts → invoices → line items). Neon autosuspends compute to zero when idle — matches the "never overspend" rule. One DB per tenant. | Free tier (0.5 GB) → Launch $19 (10 GB) | ₹0 (free) → ~₹1,600 once you outgrow free |
| **Artifact Registry** | Stores the container image Cloud Run pulls. | $0.10/GB/mo (0.5 GB free) | ~₹10–40 |
| **Secret Manager** | Per-tenant API keys + DB URLs, never in code. | $0.06/secret-version/mo | ~₹50–150 |
| **Cloud Build** *(optional)* | Builds the image on git push (or use GitHub Actions). | 120 build-min/day free | ~₹0 |
| **Logging/Monitoring** | Observability, errors, usage. | 50 GiB/mo free | ~₹0 |

### Why Neon over Cloud SQL
Cloud SQL is **always-on** — the smallest instance costs **~₹920/month even at 3 AM
with zero users**. Neon **suspends to zero** and bills only for actual query time
+ storage, exactly like Cloud Run does for compute. Same Postgres, same SQL, no
GCP lock-in lost (Cloud Run connects to it with a standard connection string).

---

## 3. All-in monthly estimate (₹)

| Stage | Total ₹/month |
|---|---|
| You + 1–2 pilot clients, light use | **₹0 – ₹500** (mostly free tiers) |
| 3–5 active client orgs | **₹1,000 – ₹2,500** |
| 10 active orgs, daily use | **₹2,500 – ₹5,000** |

> The third-party APIs (Gemini / Serper / Apify) sit **on top** of this and are
> already hard-capped per run by `utils/budget.py`, so they can never run away.
> Store each client's own API keys so they pay for their own usage.

---

## 4. The "1 instance per org" question, answered
You do **not** want N Postgres *servers* (N × always-on cost). You want **N
databases on one server** — `focuschainlabs_db`, `sn_realtors_db`, … — each fully
isolated, selected at login via that tenant's `DATABASE_URL`. If one enterprise
client later contractually demands a dedicated server, spin one up for *just them*
without pre-paying that isolation for everyone.

---

## 5. Steps to deploy

### A. Build & ship the container
```bash
gcloud artifacts repositories create focuschain --repository-format=docker --location=asia-south1
gcloud builds submit --tag asia-south1-docker.pkg.dev/PROJECT/focuschain/leads-agent
gcloud run deploy focuschain-leads-agent \
  --image asia-south1-docker.pkg.dev/PROJECT/focuschain/leads-agent \
  --region asia-south1 --allow-unauthenticated \
  --min-instances=0 --max-instances=4 --cpu=1 --memory=512Mi \
  --set-secrets=GEMINI_API_KEY=gemini-key:latest,DATABASE_URL=fcl-db-url:latest
```
> `--min-instances=0` is the cost-optimal setting (scale to zero; ~3–5 s cold
> start). Only set `=1` for your busiest tenant if cold starts bother them
> (a warm instance ≈ ₹4,000/mo, so avoid unless needed).

### B. Provision each tenant's database (Neon)
1. Create a Neon project (free) → one **database/branch per org**.
2. Apply the schema: `psql "$DATABASE_URL" -f db/schema.sql`
3. Store each org's `DATABASE_URL` in Secret Manager.

### C. Add the org and point it at its database
Set the `CRM_ORGS` secret (see `.streamlit/secrets.example.toml` for the exact
format) — list each client with `"backend": "github"` or `"backend": "postgres"`.
A `postgres` org needs its own `database_url_env` secret holding its connection
string. The CRM page then shows an **org switcher** (only when 2+ orgs are
configured) and routes every load/save to that tenant's database — automatically,
with zero code changes per client.

> Requires one extra dependency when ANY org uses the postgres backend:
> `pip install 'psycopg[binary]>=3.1'` (add it to requirements.txt then).

For SN Realtors' 10k-record import, run once after applying the schema:
```python
from utils import crm_store_pg as pg
pg.bulk_upsert(your_10k_contacts, database_url=os.environ["SN_REALTORS_DATABASE_URL"])
```

---

## 6. What's already built and wired
- `utils/tenancy.py` — org config, switcher UI, per-org backend + database resolution.
- `utils/crm_store.py` — `load_crm`/`save_crm` dispatch per-org to GitHub or Postgres,
  with the SAME contract either way (zero changes needed in the rest of the CRM UI).
- `db/schema.sql` — indexed Postgres schema (trigram + JSONB GIN for fast search).
- `utils/crm_store_pg.py` — full store: upsert/bulk-ingest/replace-all + server-side
  search/sort/paginate (`search_contacts`) for when a tenant outgrows "load all".
- `Dockerfile` + `.dockerignore` — Cloud Run-ready container.
- CRM UI paginates (25/50/100 per page) so thousands of rows never render at once,
  and shows a live "{Org} · Postgres/GitHub · N records" badge on the CRM header.

### How the dispatch keeps things safe at scale
Today, `load_crm`/`save_crm` load/replace a tenant's *entire* contact list each
visit/save — identical semantics to the GitHub-JSON store, so the existing CRM UI
(editing, filters, pagination) needed no rewrite and carries zero regression risk.
This comfortably handles 10k records (a few MB of JSON). If a tenant grows past
that, swap the CRM page's data access to `crm_store_pg.search_contacts(...)`
directly — it pushes filtering to indexed SQL so only one page of rows ever
reaches Python. The function is already written and ready for that next step.

## 7. FocusChain LLM layer (engine-agnostic)

All agents call `utils/llm.py` — no agent (or screen) knows which provider is
underneath. Provider chain:

1. **Primary** — DeepSeek `deepseek-chat` via its OpenAI-compatible API
   (`DEEPSEEK_API_KEY`). Prepaid credits, roughly **₹25 / million tokens**;
   a full Scout run uses well under ₹2.
2. **Fallback** — Gemini Flash (`GEMINI_API_KEY`), used automatically when the
   primary key is absent or a call fails. Free tier.

One budget guard covers both: `LLM_BUDGET` (default 80 calls per run;
`GEMINI_BUDGET` still honoured for older deployments).

## 8. WhatsApp → CRM

Streamlit can't receive webhooks, so a tiny FastAPI service
(`whatsapp_webhook.py`) runs beside the app and does the listening:

```
Lead's WhatsApp ──▶ Meta Cloud API ──▶ Cloud Run webhook (scales to zero)
                                         │  find-or-create lead by phone
                                         │  log message into contact thread
                                         │  FocusChain LLM refreshes the record
                                         ▼
                                   tenant's CRM store (GitHub JSON / Postgres)
```

### Setup (one-time, ~20 minutes)

1. **Meta app** — developers.facebook.com → Create App → Business → add the
   **WhatsApp** product. The API Setup page gives you a test number, a
   temporary access token and the **Phone number ID**.
2. **Deploy the webhook**:
   ```bash
   gcloud run deploy crm-whatsapp \
     --source . --region asia-south1 --allow-unauthenticated \
     --set-env-vars "WHATSAPP_VERIFY_TOKEN=...,WHATSAPP_ACCESS_TOKEN=...,WHATSAPP_PHONE_NUMBER_ID=...,GITHUB_TOKEN=...,GITHUB_REPO=...,DEEPSEEK_API_KEY=..."
   ```
   (Build uses `Dockerfile.webhook`; set it via `gcloud run deploy --dockerfile`
   or a `cloudbuild.yaml`.)
3. **Wire the webhook** — Meta dashboard → WhatsApp → Configuration →
   Webhook URL `https://<cloud-run-url>/webhook`, Verify token = your
   `WHATSAPP_VERIFY_TOKEN`, subscribe to the **messages** field.
4. **Go permanent** — create a System User token (Business Settings → System
   Users) so the access token doesn't expire, and register your real business
   number in place of the test number.

### Cost

Meta: **free** for user-initiated ("service") conversations — the exact CRM
use case. Cloud Run: free tier covers ~2M requests/month; a webhook that
scales to zero costs **₹0–10/month** in practice.

Per-tenant: deploy one webhook per org (set `WHATSAPP_ORG_ID`), or one shared
webhook per WhatsApp number — each number maps to one tenant.
