# Multi-Tenancy & Auth Audit

Scope: verify that the `organization_id` multi-tenancy work and the Phase 1
Google-auth layer actually isolate each tenant's data, with no cross-tenant
leakage paths. Audited against `main` @ PR #39 (Phase 1 merged).

TL;DR: the **core data path is correct** — all CRM, interactions, WhatsApp
account, and mobile-API reads/writes are `organization_id`-scoped. The audit
found **two real isolation gaps in secondary paths** (non-Cloud-SQL backends and
the Intel briefings cache), both now **fixed**, plus three operational notes.

---

## ✅ Verified correct

| Area | Finding |
|---|---|
| CRM contacts (Cloud SQL) | Every `SELECT/INSERT/UPDATE/DELETE` on `contacts` filters/stamps `organization_id`. `ON CONFLICT` updates carry a `WHERE contacts.organization_id = EXCLUDED.organization_id` guard, so a colliding global PK from another org is never overwritten. |
| Interactions | `load_interactions` and `insert_interaction` are org-scoped. |
| WhatsApp accounts | `load`/`upsert`/`delete` org-scoped; upsert has the same cross-org conflict guard. |
| `replace_all_contacts` | Both the upsert **and** the delete-set are scoped to the org, so a save can never delete another tenant's rows. |
| Mobile REST API | Every `/api/*` route resolves `organization_id` from the bearer token (`API_KEYS` → org) and passes it to the store. |
| Auth gate | Tenant is derived from the **verified** Google email domain only; unknown domains are denied; the manual org-switcher is hidden under auth so tenants can't be hand-switched. |
| Streamlit UI | All `load_crm`/`save_crm` calls in `crm_ui`, `reach_ui`, `intel_ui`, `finance_ui`, `proposal_ui` pass the signed-in org's `organization_id`. |

### Intentionally global queries (safe)
Three queries are deliberately **not** org-scoped because they key on
globally-unique identifiers and never expose another tenant's row data:

- `message_id_exists(wamid)` — boolean de-dupe check on Meta's globally-unique `wamid`.
- `update_interaction_status(wamid, …)` — updates by `wamid` and `RETURNING organization_id` so the caller can re-scope downstream work.
- `resolve_org_for_phone_number_id(pid)` — *is* the tenant-resolution lookup; returns only the org id for routing.

---

## 🔴 Gaps found and fixed

### F1 — Non-Cloud-SQL backends gave zero isolation  (High → fixed)
`load_crm()`/`save_crm()` fall back to Supabase (a single shared `contacts`
table) or GitHub-JSON / local file (a single shared document) when Cloud SQL
isn't configured. None of those carry `organization_id`, so with auth enabled
but Cloud SQL absent, **every tenant would read and write the same store.**

**Fix:** `auth.require_auth()` now **fails closed** — if auth is enabled but the
org-scoped Cloud SQL backend isn't configured (`postgres_configured()` is
False), the app shows a configuration screen and `st.stop()`s instead of serving
shared data. Dev mode (auth disabled, single tenant) is unaffected and still
runs on GitHub/local. See `utils/auth.py::_multitenant_backend_ready`.

### F2 — Intel briefings cache was not org-scoped  (High → fixed)
`utils/intel_store.py` read/wrote a single shared `data/intel/briefings.json`,
so both orgs saw each other's Intel briefings.

**Fix:** the cache file is now namespaced per `organization_id`
(`briefings_<org>.json`; the `default` tenant keeps the legacy filename so
existing data isn't orphaned). The org id is sanitised to prevent path
traversal. `intel_ui` threads the signed-in org through `load_briefings`,
`upsert_briefings`, and `mark_pushed`. Covered by `tests/test_intel_store_tenancy.py`.

---

## 🟡 Operational notes (not code bugs)

### F3 — Existing data lives under `organization_id = "default"`
All leads created before multi-tenancy carry `organization_id = "default"`.
After auth, `focuschainlabs` / `sn_realtors` users see **empty** CRMs until that
data is assigned to the right tenant. One-time reassignment, e.g.:

```sql
-- assign all current default-org leads to focuschainlabs
UPDATE contacts     SET organization_id = 'focuschainlabs' WHERE organization_id = 'default';
UPDATE interactions SET organization_id = 'focuschainlabs' WHERE organization_id = 'default';
```

(Or migrate a fresh export per tenant with `scripts/migrate_to_cloudsql.py --org-id <org>`.)
The exact mapping is a business decision — documented in the architecture PDF.

### F4 — `feedback_store` is global by design (accepted)
Product feedback from the in-app floater is stored in a single shared
`data/crm/feedback.json`. This is internal product feedback for the FocusChain
team, not tenant business data, so a shared store is acceptable. Flagged for
visibility; revisit if feedback ever needs per-tenant separation.

### F5 — Dev smoke scripts are unscoped (accepted)
`scripts/test_github_crm.py` and `scripts/test_ai_intake.py` call `load_crm`
without an org. They are developer smoke tests against the GitHub backend, never
run in the multi-tenant production path. No action.

---

## Test coverage added by this audit
- `tests/test_intel_store_tenancy.py` — briefings isolation, path sanitisation, org-scoped `mark_pushed`.
- Auth backend fail-closed verified via the auth smoke harness.

Suite after the audit: **86 passed**, 1 pre-existing unrelated failure
(`test_feedback_store::test_normalize_entry_defaults`, present on `main` before
this work).
