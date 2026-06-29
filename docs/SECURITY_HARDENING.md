# Production hardening

Changes made before deploying `crm-app` to the public. Each item closes a way the
pre-hardening system could leak data, be impersonated, or be left open.

| # | Hardening | What it does | Switch |
|---|---|---|---|
| 1 | DB driver in app image | `psycopg2-binary` in requirements.txt so `crm-app` can reach Cloud SQL. | — |
| 2 | Webhook authenticity | Verify Meta's `X-Hub-Signature-256` (HMAC over the raw body) before processing. Unsigned/forged deliveries → 403. | `META_APP_SECRET` |
| 3 | Reject unknown numbers | An inbound `phone_number_id` not registered in `whatsapp_accounts` is **rejected**, never filed under the default tenant. DB errors → 5xx (Meta retries). | automatic when Cloud SQL is on |
| 4 | No token leakage | The WhatsApp `access_token` is stripped from every REST response. | automatic |
| 5 | Per-number outbound | Replies use the receiving number's **own** `access_token` + `phone_number_id`, not a shared global token. | automatic when Cloud SQL is on |
| 6 | Fail-closed auth | With `AUTH_REQUIRED=true` the app never runs unauthenticated — if sign-in isn't configured it locks instead of opening. | `AUTH_REQUIRED` |
| 7 | Invite-only membership + roles | Access is granted per **email** (not domain). Each user has a role (`admin`/`member`); only admins manage WhatsApp numbers. | `ORG_MEMBERS` |
| 8 | Mobile API off by default | The Flutter REST API is disabled until per-user token auth exists; the shared per-org key can't be left accidentally public. | `MOBILE_API_ENABLED` |

## Why membership is by email, not domain

SN Realtors signs in with **personal Gmail accounts** (`surajmetgud@gmail.com`,
`suhassalgatti71@gmail.com`) — there is no company domain to match. And even for
FocusChain Labs, a domain match alone is too broad. So the access gate is an
explicit invite list (`org_config.resolve_membership`): an address gets in only
if it's named, with the role it's given. Domain config now only drives branding.

Launch members (override with `ORG_MEMBERS`):

- **FocusChain Labs** — savin (admin), bhaskar (member), srikant (member)
- **SN Realtors** — surajmetgud (admin), suhassalgatti71 (member)

## Production env checklist

```
AUTH_REQUIRED=true
META_APP_SECRET=...            # on the webhook (signature verification)
# MOBILE_API_ENABLED stays unset (API off) until per-user auth ships
# ORG_MEMBERS only if you need to change the built-in invite list
```

## Tests

33 new tests cover signature verify (valid/forged/missing), unknown-number
rejection (unit + end-to-end), token redaction, per-account outbound token,
`AUTH_REQUIRED` fail-closed, invite-only membership + roles, and the mobile-API
gate. Full suite green (1 pre-existing unrelated feedback-store failure).
