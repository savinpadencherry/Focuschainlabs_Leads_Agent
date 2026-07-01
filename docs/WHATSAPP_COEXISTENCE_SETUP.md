# WhatsApp Business app coexistence setup

This CRM uses Meta Embedded Signup to connect a WhatsApp Business mobile-app
number to the shared CRM. The QR/linking screen is rendered by Meta inside its
popup; the CRM does not generate the QR code itself.

The green connect button appears only when the CRM Cloud Run service has all of
these values:

```text
META_APP_ID
META_CONFIG_ID
WA_CONNECT_SECRET
WEBHOOK_PUBLIC_URL
```

The webhook service must separately have:

```text
META_APP_ID
META_APP_SECRET
WA_CONNECT_SECRET
APP_PUBLIC_URL
WHATSAPP_VERIFY_TOKEN
```

Both services must also point to the same organisation-scoped Postgres/Cloud SQL
database through `DATABASE_URL` or `CLOUD_SQL_CONNECTION_NAME`.

## 1. Check GCP before changing anything

Open Google Cloud Shell from the correct project and run:

```bash
chmod +x scripts/check_whatsapp_setup.sh
./scripts/check_whatsapp_setup.sh
```

The script prints only setting names and service URLs. It never prints secret
values. The repository deploys these Cloud Run services in `asia-south1`:

```text
crm-app       Streamlit CRM
crm-webhook   FastAPI Meta webhook and Embedded Signup completion endpoint
```

From the script output, copy these two URLs:

```text
APP_PUBLIC_URL=https://crm-app-....run.app
WEBHOOK_PUBLIC_URL=https://crm-webhook-....run.app
```

Use the actual browser origin for `APP_PUBLIC_URL`. If users open the CRM through
a custom domain, use that custom origin. Multiple origins can be comma-separated.

## 2. Configure the Meta developer app

Meta changes dashboard labels periodically, but the required objects are stable.
Use the Meta app that owns the WhatsApp integration.

### A. Confirm the app and business portfolio

1. Open Meta for Developers and select the app.
2. The app should be a Business-type app or an app with the WhatsApp business
   use case enabled.
3. Link the app to the correct Meta Business Portfolio.
4. Add the **WhatsApp** product/use case if it is not already present.
5. Copy the numeric **App ID**. This becomes `META_APP_ID`.
6. Open **App settings → Basic** and copy the **App secret**. This becomes
   `META_APP_SECRET`; never put it in GitHub or a plain command history.

### B. Configure the app domain

In the app's basic settings / Facebook Login for Business settings:

1. Add the CRM hostname to **App domains**.
2. Add a Website platform/site URL if Meta asks for one.
3. Use the exact HTTPS CRM origin shown by Cloud Run or your custom domain.
4. Save the changes.

Example hostname only:

```text
crm-app-abc123.asia-south1.run.app
```

Do not include `/crm`, `/webhook`, query strings, or a trailing path in App
Domains.

### C. Create an Embedded Signup configuration

Depending on the current Meta dashboard, this is usually under **Facebook Login
for Business → Configurations** or the WhatsApp Embedded Signup setup area.

1. Create a new configuration for WhatsApp Embedded Signup.
2. Select the WhatsApp Business assets/business portfolio that should be
   onboarded.
3. Enable the permissions/scopes requested by the WhatsApp Embedded Signup flow,
   normally including WhatsApp business management and messaging permissions.
4. Choose the onboarding option intended for an existing WhatsApp Business app
   number/coexistence, not a migration that removes the number from the phone.
5. Save the configuration.
6. Copy its numeric **Configuration ID**. This becomes `META_CONFIG_ID`.

The CRM launches Meta with this feature value:

```text
META_EMBEDDED_SIGNUP_FEATURE_TYPE=whatsapp_business_app_onboarding
```

If Meta has supplied a different coexistence feature value for your account,
set that exact value instead.

### D. Configure Meta's webhook

In **WhatsApp → Configuration**:

1. Callback URL:

   ```text
   https://YOUR_CRM_WEBHOOK_RUN_URL/webhook
   ```

2. Verify token: use the same private value stored in GCP as
   `WHATSAPP_VERIFY_TOKEN`.
3. Verify and save the callback.
4. Subscribe the app/WABA to the **messages** webhook field.

The webhook Cloud Run service must remain publicly reachable because Meta calls
it from outside GCP. Application-level signature and tenant checks remain in the
code.

### E. Development versus Live mode

While the Meta app is in development mode, only app administrators, developers,
testers, and permitted business assets may complete the flow. For real client
users, switch to Live mode after Meta's required business verification, access
verification, and app review steps are complete.

## 3. Prepare the WhatsApp Business mobile number

For coexistence onboarding:

1. The phone number must be active in the **WhatsApp Business** mobile app, not
   only the consumer WhatsApp app.
2. Update WhatsApp Business to the latest available version.
3. Keep the phone nearby, online, and able to open WhatsApp Business during the
   Meta popup.
4. Use the Meta account/business portfolio that is authorised to manage the
   business and number.
5. Complete every Meta popup step. The QR/linking instruction appears inside
   Meta's flow only after Embedded Signup is correctly configured.

Do not manually enter Cloud API credentials in the CRM unless the number is
already configured as a normal Cloud API number and coexistence is not required.

## 4. Configure Secret Manager and Cloud Run

Set the project and region:

```bash
PROJECT_ID="$(gcloud config get-value project)"
REGION="asia-south1"
APP_SERVICE="crm-app"
WEBHOOK_SERVICE="crm-webhook"

APP_URL="$(gcloud run services describe "$APP_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format='value(status.url)')"

WEBHOOK_URL="$(gcloud run services describe "$WEBHOOK_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format='value(status.url)')"

printf 'CRM:     %s\nWebhook: %s\n' "$APP_URL" "$WEBHOOK_URL"
```

Enter values without echoing the private ones:

```bash
read -rp "Meta App ID: " META_APP_ID
read -rp "Meta Embedded Signup Configuration ID: " META_CONFIG_ID
read -rsp "Meta App Secret: " META_APP_SECRET; echo
read -rsp "Choose a webhook verify token: " WHATSAPP_VERIFY_TOKEN; echo
WA_CONNECT_SECRET="$(openssl rand -hex 32)"
```

Create or update Secret Manager values:

```bash
upsert_secret() {
  local name="$1"
  local value="$2"
  if gcloud secrets describe "$name" --project="$PROJECT_ID" >/dev/null 2>&1; then
    printf %s "$value" | gcloud secrets versions add "$name" \
      --project="$PROJECT_ID" --data-file=-
  else
    printf %s "$value" | gcloud secrets create "$name" \
      --project="$PROJECT_ID" --replication-policy=automatic --data-file=-
  fi
}

upsert_secret meta-app-secret "$META_APP_SECRET"
upsert_secret wa-connect-secret "$WA_CONNECT_SECRET"
upsert_secret whatsapp-verify-token "$WHATSAPP_VERIFY_TOKEN"
```

Get the runtime service accounts and grant access to the secrets:

```bash
APP_SA="$(gcloud run services describe "$APP_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format='value(spec.template.spec.serviceAccountName)')"
WEBHOOK_SA="$(gcloud run services describe "$WEBHOOK_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format='value(spec.template.spec.serviceAccountName)')"

# If either value is blank, open Cloud Run → service → Security and note the
# runtime service account, then set APP_SA / WEBHOOK_SA manually.

for SECRET in wa-connect-secret; do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --project="$PROJECT_ID" \
    --member="serviceAccount:$APP_SA" \
    --role="roles/secretmanager.secretAccessor"
done

for SECRET in meta-app-secret wa-connect-secret whatsapp-verify-token; do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --project="$PROJECT_ID" \
    --member="serviceAccount:$WEBHOOK_SA" \
    --role="roles/secretmanager.secretAccessor"
done
```

Update `crm-app`:

```bash
gcloud run services update "$APP_SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --update-env-vars="META_APP_ID=$META_APP_ID,META_CONFIG_ID=$META_CONFIG_ID,WEBHOOK_PUBLIC_URL=$WEBHOOK_URL,META_EMBEDDED_SIGNUP_FEATURE_TYPE=whatsapp_business_app_onboarding" \
  --update-secrets="WA_CONNECT_SECRET=wa-connect-secret:latest"
```

Update `crm-webhook`:

```bash
gcloud run services update "$WEBHOOK_SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --update-env-vars="META_APP_ID=$META_APP_ID,APP_PUBLIC_URL=$APP_URL" \
  --update-secrets="META_APP_SECRET=meta-app-secret:latest,WA_CONNECT_SECRET=wa-connect-secret:latest,WHATSAPP_VERIFY_TOKEN=whatsapp-verify-token:latest"
```

If users access the CRM through a custom domain, replace `$APP_URL` in
`APP_PUBLIC_URL` with the custom HTTPS origin. For both origins:

```text
APP_PUBLIC_URL=https://custom.example.com,https://crm-app-....run.app
```

Do not overwrite the existing database or authentication environment variables.
`gcloud run services update --update-env-vars` and `--update-secrets` add/update
only the named entries.

## 5. Verify the deployment

Run the checker again:

```bash
./scripts/check_whatsapp_setup.sh
```

Then inspect the webhook:

```bash
curl -i "$WEBHOOK_URL/healthz"

gcloud run services logs read crm-webhook \
  --project="$PROJECT_ID" --region="$REGION" --limit=100
```

Reload the CRM completely. Open **CRM → WhatsApp connections**. The red missing
configuration box should be replaced by the green **Connect WhatsApp Business
app** button.

Click the button and finish Meta's popup. After Meta returns the WABA ID and phone
number ID, the browser posts them to:

```text
https://YOUR_WEBHOOK_URL/connect/whatsapp
```

The webhook exchanges Meta's temporary code using `META_APP_SECRET` and saves the
connected number into the shared organisation-scoped database.

## 6. Troubleshooting

### The CRM still lists all four settings as missing

The values are not attached to the latest `crm-app` revision. Run:

```bash
gcloud run services describe crm-app --region=asia-south1 --format=yaml
```

Look under the container environment section for `META_APP_ID`,
`META_CONFIG_ID`, `WA_CONNECT_SECRET`, and `WEBHOOK_PUBLIC_URL`.

### The button appears but Meta does not show coexistence/QR

- Confirm `META_CONFIG_ID` is the configuration ID for the coexistence-capable
  Embedded Signup configuration, not the App ID or WABA ID.
- Confirm the signed-in Meta account can manage the selected business portfolio.
- Confirm the number is active in WhatsApp Business mobile.
- Confirm the Meta app's domain/site URL includes the exact CRM hostname.
- Confirm the app user is an admin/developer/tester while the app is in
  development mode.
- Inspect the browser console for Meta SDK errors.

### The Meta popup finishes but the CRM remains disconnected

- Check `crm-webhook` logs for `/connect/whatsapp` errors.
- Confirm both services use exactly the same `WA_CONNECT_SECRET` value.
- Confirm both services connect to the same database.
- Confirm `META_APP_SECRET` belongs to the same app as `META_APP_ID`.
- Confirm `APP_PUBLIC_URL` matches the browser origin so CORS permits the POST.

### Meta webhook verification fails

- Callback URL must end in `/webhook`.
- The verify token entered in Meta must exactly match the GCP secret exposed as
  `WHATSAPP_VERIFY_TOKEN`.
- `crm-webhook` must allow unauthenticated internet requests.

### Outbound still says WhatsApp is not connected

A saved account is considered active only when it has both a phone-number ID and
an access token. Reload the page after onboarding and inspect the connected
numbers section.
