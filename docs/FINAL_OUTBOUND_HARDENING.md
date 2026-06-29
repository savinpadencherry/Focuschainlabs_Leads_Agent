# Final multi-tenant outbound hardening

This patch closes the remaining production gaps before deploying the shared CRM app.

- WhatsApp text and template sends resolve credentials from the active tenant's `whatsapp_accounts` row.
- PostgreSQL multi-tenant mode never falls back to global WhatsApp credentials.
- A single active number is selected automatically; multiple active numbers require an organisation admin to choose a sender in the WhatsApp connections panel.
- The webhook production entrypoint supports `WEBHOOK_SIGNATURE_REQUIRED=true` and returns 503 if `META_APP_SECRET` is missing.
- Authentication, webhook, and tenant-isolation regression tests run before both Cloud Run deployment workflows build or deploy.

## Required production setting

Set both of these on the `crm-webhook` Cloud Run service:

```text
WEBHOOK_SIGNATURE_REQUIRED=true
META_APP_SECRET=<Meta app secret>
```

The Streamlit app continues to use the invite-only membership gate and Cloud SQL tenant scoping introduced in the previous hardening change.
