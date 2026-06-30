# WhatsApp Business app coexistence setup

The CRM now launches Meta Embedded Signup with the WhatsApp Business app
coexistence feature. This keeps the business number usable in the WhatsApp
Business mobile app while registering the same number for CRM messaging.

## 1. CRM app configuration

Set these as deployment secrets on the Streamlit/CRM service. Never commit real
values to the repository.

```text
DATABASE_URL or CLOUD_SQL_CONNECTION_NAME
META_APP_ID
META_CONFIG_ID
WA_CONNECT_SECRET
WEBHOOK_PUBLIC_URL
META_EMBEDDED_SIGNUP_FEATURE_TYPE=whatsapp_business_app_onboarding
```

`WA_CONNECT_SECRET` must be a long random value. `WEBHOOK_PUBLIC_URL` is the base
URL of the deployed `whatsapp_webhook.py` service, without a trailing slash.

## 2. Webhook service configuration

The webhook service must use the same database and the same tenant-signing
secret as the CRM app.

```text
DATABASE_URL or CLOUD_SQL_CONNECTION_NAME
META_APP_ID
META_APP_SECRET
WA_CONNECT_SECRET
APP_PUBLIC_URL
```

`APP_PUBLIC_URL` should be the public CRM origin allowed to call the connection
endpoint. The webhook exposes `POST /connect/whatsapp`; that endpoint verifies
the signed tenant state, exchanges Meta's authorization code, resolves the
phone number and stores it in the organisation-scoped `whatsapp_accounts` table.

## 3. Admin permission

Only organisation admins can connect, disconnect or select WhatsApp sender
accounts. The built-in FocusChain membership now gives
`srikant@focuschainlabs.com` the admin role so the tester shown in the reported
screenshots can operate the setup.

When production defines an `ORG_MEMBERS` secret, it replaces all built-in
members. Make sure Srikant's production entry is also:

```json
{"email":"srikant@focuschainlabs.com","org":"focuschainlabs","role":"admin"}
```

## 4. Connect the number

1. Sign in as an organisation admin.
2. Open **CRM → WhatsApp connections**.
3. Confirm the panel says **Not connected** and shows the green
   **Connect WhatsApp Business app** button.
4. Complete every Meta step. When Meta asks, link/scan using the WhatsApp
   Business mobile app that owns the number.
5. Return to the CRM. The panel should list the display number and phone-number
   ID and mark WhatsApp as ready.
6. Open a lead with a phone number and use
   **Activity → Send WhatsApp** for a test message.

## Troubleshooting

- **No Connect button:** the panel now lists the exact missing CRM settings, or
  explains that the signed-in user is not an admin.
- **Cloud SQL error:** the WhatsApp registry is tenant-scoped and intentionally
  refuses to use the shared JSON/Supabase fallback.
- **Meta popup opens the wrong onboarding:** verify
  `META_EMBEDDED_SIGNUP_FEATURE_TYPE` is unset or set to
  `whatsapp_business_app_onboarding`, and confirm `META_CONFIG_ID` belongs to the
  intended Embedded Signup configuration.
- **Connection finishes but no number appears:** check webhook logs and confirm
  the CRM and webhook use the same `WA_CONNECT_SECRET` and database.
- **Outbound still says not connected:** reload the CRM after signup and confirm
  the stored account has a phone-number ID and access token.
