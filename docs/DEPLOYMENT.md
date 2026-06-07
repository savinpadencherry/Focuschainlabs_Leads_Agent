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

### C. Flip the backend on
Set `CRM_BACKEND=postgres` and `DATABASE_URL=...`. `utils/crm_store_pg.py` then
handles search/filter/pagination in SQL (indexed for 10k+ rows). For SN Realtors'
10k-record import, use `crm_store_pg.bulk_upsert(contacts)`.

> Requires one extra dependency when you adopt this backend:
> `pip install 'psycopg[binary]>=3.1'` (add it to requirements.txt then).

---

## 6. What's already built for this
- `db/schema.sql` — indexed Postgres schema (trigram + JSONB GIN for fast search).
- `utils/crm_store_pg.py` — scale store: server-side search/sort/paginate + bulk ingest.
- `Dockerfile` + `.dockerignore` — Cloud Run-ready container.
- CRM UI already paginates (25/50/100 per page) so thousands of rows never render at once.

Still to wire when you adopt Postgres: an `org`/login layer to select the tenant
DB, and a backend switch in the UI's data calls (currently the GitHub-JSON store).
