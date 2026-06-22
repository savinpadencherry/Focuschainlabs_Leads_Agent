# WhatsApp Coexistence, Broadcast & CRM Tracking — Complete Guide

**FocusChain Labs · Leads Agent CRM**  
**Version:** June 2026  
**Audience:** Srikanth / ops team setting up Meta Developers + CRM broadcasts

---

## Table of contents

1. [Executive summary — is this possible?](#1-executive-summary--is-this-possible)
2. [What you already have](#2-what-you-already-have)
3. [Architecture diagrams](#3-architecture-diagrams)
4. [Part A — WhatsApp Coexistence (detailed Meta steps)](#part-a--whatsapp-coexistence-detailed-meta-steps)
5. [Part B — Mass broadcast from CRM](#part-b--mass-broadcast-from-crm)
6. [Part C — Track interactions & auto-update CRM](#part-c--track-interactions--auto-update-crm)
7. [Part D — What you must do (checklist)](#part-d--what-you-must-do-checklist)
8. [Part E — Template creation for promotions](#part-e--template-creation-for-promotions)
9. [Part F — Troubleshooting](#part-f--troubleshooting)
10. [Appendix — Environment variables](#appendix--environment-variables)

---

## 1. Executive summary — is this possible?

**Yes.** Meta’s WhatsApp Cloud API supports:

| Capability | Possible? | How |
|------------|-----------|-----|
| Inbound messages → Gemini → CRM | ✅ Already built | `whatsapp_webhook.py` |
| Coexistence (app + API same number) | ✅ Yes | Meta Embedded Signup → “Connect existing Business App” |
| Send messages from CRM | ✅ Yes | `send_whatsapp_text()` / `send_whatsapp_template()` |
| Mass broadcast to selected leads | ✅ Yes (with rules) | CRM multi-select → template or 24h window |
| Track delivered / read | ✅ Yes | Status webhooks → `wa_events` on contact |
| Track button clicks | ✅ Yes | Interactive webhooks → stage mapping |
| Auto-update CRM on interaction | ✅ Yes (now coded) | `utils/wa_events.py` + webhook |

**What is NOT possible:** WhatsApp Business App-style “broadcast lists” to unlimited cold contacts without **approved templates** and **opt-in**. Meta enforces this at the API level.

---

## 2. What you already have

```
Customer WhatsApp  →  Meta Cloud API  →  POST /webhook  →  whatsapp_webhook.py
                                                              ↓
                                                         Gemini (LLM intake)
                                                              ↓
                                                    CRM save (GitHub / Supabase / Postgres)
                                                              ↓
                                              Streamlit CRM + Flutter app (shared DB)
```

**Deployed service:** FastAPI webhook (`whatsapp_webhook.py`) on Render/Koyeb/HuggingFace Space.  
**Secrets:** `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`, `GEMINI_API_KEY` or `DEEPSEEK_API_KEY`.

---

## 3. Architecture diagrams

### 3.1 Coexistence — one number, two clients

```
┌─────────────────────┐         ┌──────────────────────┐
│ WhatsApp Business   │         │  Meta Cloud API      │
│ App (Srikanth phone)│◄───────►│  (your WABA)         │
└──────────┬──────────┘         └──────────┬───────────┘
           │                               │
           │    Coexistence link           │ webhooks
           │                               ▼
           │                    ┌──────────────────────┐
           │                    │ whatsapp_webhook.py  │
           │                    │  /webhook            │
           │                    └──────────┬───────────┘
           │                               │
           └──────── chat history ─────────┤
                                           ▼
                                  ┌──────────────────────┐
                                  │ Supabase contacts    │
                                  │ + CRM comments       │
                                  └──────────────────────┘
```

### 3.2 Broadcast + tracking flow (new)

```
CRM: Select leads → Compose / AI draft → Send WhatsApp
                           │
                           ▼
              Meta returns wamid (message id)
                           │
                           ▼
              Store on contact.wa_events[] (campaign_id)
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
    status: sent    status: delivered   status: read
         │                 │                 │
         └─────────────────┴─────────────────┘
                           │
              Webhook POST /webhook (statuses array)
                           │
                           ▼
              apply_status_update() → CRM contact
              · tag wa-read
              · new → contacted on read
                           │
              Customer taps template button
                           │
                           ▼
              Webhook (interactive message)
                           │
                           ▼
              apply_interaction() → qualified / lost
```

---

## Part A — WhatsApp Coexistence (detailed Meta steps)

Coexistence lets Srikanth keep using the **WhatsApp Business app** on his phone while your **Cloud API webhook** still receives every customer message.

### A.0 Before you start — pick your path

| Your situation | Recommended path |
|--------------|------------------|
| Number already on WhatsApp Business app ≥7 days with real chats | **Option 1** — onboard via Coexistence (no downtime) |
| Number registered API-only (never on app) | **Option 2** — deregister → register on app → wait ~7 days → Coexistence |

> Your number +91 99383 41236 was API-first. If you need Coexistence on that exact number, schedule a maintenance window (see `docs/WHATSAPP_COEXISTENCE.md`).

### A.1 Prerequisites checklist

- [ ] [Meta Business Manager](https://business.facebook.com/) verified
- [ ] Admin access to your Meta app + WhatsApp Business Account (WABA)
- [ ] App status: **Live** (not Development-only for production number)
- [ ] WhatsApp Business app **v2.24.17+** on primary phone
- [ ] Number active on Business app **≥7 days** with real customer conversations
- [ ] Webhook already working: `GET https://YOUR-HOST/healthz` returns `whatsapp_configured: true`

### A.2 Meta Developers — open your app

1. Go to **https://developers.facebook.com/apps**
2. Select your app (e.g. “FocusChain CRM” / your business app name)
3. Left sidebar → **WhatsApp** → **API Setup**
4. Note these values (copy to a secure note):
   - **WhatsApp Business Account ID** (WABA ID)
   - **Phone number ID** (may change after Coexistence)
   - **Temporary access token** (for testing only)

### A.3 Start Embedded Signup with Coexistence

> Meta calls this flow **“Onboard WhatsApp Business app users”** (Coexistence).

**If you use Meta’s dashboard directly (no custom Embedded Signup UI):**

1. **WhatsApp** → **API Setup** or **Getting Started**
2. Look for **“Connect your existing WhatsApp Business App”** or **“Connect WhatsApp Business account”**
   - Do **NOT** choose “Get a new phone number” if you want Coexistence
3. Click **Connect existing WhatsApp Business App**

**If you embed signup in your own product (developers):**

In your Facebook Login `FB.login` extras, set:

```javascript
extras: {
  featureType: 'whatsapp_business_app_onboarding',
  sessionInfoVersion: 2
}
```

Reference: https://developers.facebook.com/docs/whatsapp/embedded-signup/custom-flows/onboarding-business-app-users/

### A.4 Step-by-step on screen (what you’ll see)

| Step | Where | Action |
|------|-------|--------|
| 1 | Meta popup | Choose **Connect your existing WhatsApp Business App** |
| 2 | Business Portfolio | Select existing portfolio or create new |
| 3 | Phone entry | Enter country **+91** and your Business app number |
| 4 | QR code | Meta shows QR on desktop |
| 5 | Phone — WhatsApp Business app | Message from **Facebook Business** arrives → tap **Connect** |
| 6 | Phone | Tap **Connect to Business Platform** |
| 7 | Phone | Optional: **Share chat history** (recommended, up to ~6 months) |
| 8 | Phone | Tap **Scan QR code** → scan desktop QR |
| 9 | Phone | Confirm permissions |
| 10 | Meta popup | Finish signup — copy new **Phone Number ID** if it changed |

### A.5 After Coexistence — reconnect your stack

1. **Update Phone Number ID** in all hosts:
   - Webhook service (Render/Koyeb/HF): `WHATSAPP_PHONE_NUMBER_ID`
   - Streamlit secrets: same variable
2. **Token:** ensure permanent system-user token has `whatsapp_business_messaging` on this WABA
3. **Webhook configuration:**
   - Meta → WhatsApp → **Configuration**
   - Callback URL: `https://YOUR-HOST/webhook`
   - Verify token: matches `WHATSAPP_VERIFY_TOKEN`
   - Subscribe to field: **`messages`** (includes inbound + status updates)
4. **Subscribe WABA to app** (if needed):
   ```bash
   curl -X POST "https://graph.facebook.com/v21.0/<WABA_ID>/subscribed_apps" \
     -H "Authorization: Bearer <PERMANENT_TOKEN>"
   ```
5. **Test inbound:** message the business number from a personal phone → CRM should show new lead
6. **Test coexistence:** Srikanth replies from Business app → customer receives it (echo handling skips self-leads)

### A.6 Keep Coexistence alive

- Open WhatsApp Business app **at least once every 13 days**
- Do **not** uninstall the app after linking
- Group chats, view-once, disappearing messages **do not** sync to API

---

## Part B — Mass broadcast from CRM

### B.1 Two legal send modes

| Mode | When to use | API function | Cost |
|------|-------------|--------------|------|
| **Session message** | Customer messaged you in last **24 hours** | `send_whatsapp_text()` | Free in service window |
| **Template message** | Cold outreach, promotions, re-engagement | `send_whatsapp_template()` | Per Meta pricing (marketing category) |

### B.2 How to broadcast in your CRM (today)

1. Open **Streamlit CRM** → **Find leads**
2. Click **Select leads** → select page / all / individuals
3. Toolbar → **WhatsApp** popover
4. Choose:
   - **Free text** — only for leads who recently messaged you
   - **Use approved template** — check box, enter template name (e.g. `summer_promo`)
5. Optional: **AI draft** for copy
6. Click **Send WhatsApp**

Each send stores:
- `wamid` message ID
- `campaign_id` (e.g. `wa_20260622_143052`)
- Body / template name on `contact.wa_events[]`

### B.3 Rate limits & best practices

- Send **sequentially** (CRM does this) — Meta throttles burst traffic
- For >100 recipients, add 1–2 second delay between sends (future enhancement)
- Collect **opt-in** on website/forms: “I agree to receive WhatsApp updates”
- Honour **STOP** replies — map to `lost` stage (configure in `INTERACTION_STAGE_MAP`)

---

## Part C — Track interactions & auto-update CRM

### C.1 What gets tracked automatically

| Event | Webhook source | CRM update |
|-------|----------------|------------|
| Message sent | Status `sent` | `wa_events.status = sent` |
| Delivered to device | Status `delivered` | status updated |
| Read in chat | Status `read` | tag `wa-read`, `new` → `contacted` |
| Delivery failed | Status `failed` | error logged in comments |
| Button “Interested” | Interactive `button_reply` | `status` → `qualified` |
| Button “Not interested” | Interactive | `status` → `lost` |
| Free-text reply | Inbound message | Gemini intake + comment thread |

### C.2 Customize button → stage mapping

Edit `utils/wa_events.py`:

```python
INTERACTION_STAGE_MAP = {
    "interested": "qualified",
    "book_demo": "qualified",
    "not_interested": "lost",
    "stop": "lost",
}
```

Button IDs must match what you define in the **Meta message template**.

### C.3 View campaign stats in CRM

After a broadcast, the WhatsApp popover shows last campaign stats:

`X read · Y delivered · Z failed`

Full per-lead detail is on each contact’s `wa_events` array (visible in GitHub/Postgres CRM; Supabase flat sync omits nested fields — use GitHub or Postgres for full tracking).

---

## Part D — What you must do (checklist)

### From your end — one-time setup

- [ ] **Meta Business verification** complete
- [ ] **Permanent system user token** (not 24h temp token)
- [ ] **Webhook deployed** and HTTPS URL in Meta Configuration
- [ ] **`messages` webhook field** subscribed
- [ ] **Coexistence onboarded** (if Srikanth uses Business app)
- [ ] **Streamlit secrets** + **webhook env** aligned (same token + phone ID)

### For promotional broadcasts

- [ ] Create **message template** in Meta Business Suite → WhatsApp Manager → Message templates
- [ ] Wait for template **APPROVED** status
- [ ] Add opt-in on website / lead forms
- [ ] Use CRM → Select leads → WhatsApp → **Use approved template** → enter template name
- [ ] Optional: add **Quick Reply buttons** to template for tracked interactions

### For tracking

- [ ] Ensure webhook receives status events (send test message, check logs for `status_delivered`)
- [ ] Confirm `wa_events` populated after CRM broadcast (check `data/crm/contacts.json` or Postgres JSONB)

---

## Part E — Template creation for promotions

### E.1 Where to go

1. **https://business.facebook.com/** → **WhatsApp Manager**
2. Left menu → **Account tools** → **Message templates**
3. Click **Create template**

### E.2 Recommended template structure

| Field | Example |
|-------|---------|
| Name | `summer_promo` (lowercase, underscores) |
| Category | **Marketing** (for promotions) |
| Language | English |
| Body | `Hi {{1}}, we're offering 20% off interior design packages this month. Reply INTERESTED for details.` |
| Buttons | Quick reply: `INTERESTED`, `NOT INTERESTED` |

> Button payload IDs become `interaction_id` in webhooks — map them in `INTERACTION_STAGE_MAP`.

### E.3 Submit & wait

- Review time: minutes to 48 hours
- Status webhook field `message_template_status_update` notifies when approved (optional subscribe)

### E.4 Send from CRM

1. Select leads with phone numbers
2. WhatsApp popover → check **Use approved template**
3. Template name: `summer_promo`
4. Body param: personalized line (AI draft fills this)
5. Send

---

## Part F — Troubleshooting

| Problem | Fix |
|---------|-----|
| Webhook verify fails | `WHATSAPP_VERIFY_TOKEN` must match Meta Configuration exactly |
| Inbound works, no status updates | Same `messages` subscription covers both — check logs for `status_` lines |
| Broadcast fails immediately | Token expired → regenerate permanent token |
| Template send fails (#132000) | Template not approved or wrong name/language |
| Free text fails (#131047) | Outside 24h window → use template |
| Coexistence QR fails | App version < 2.24.17 or number < 7 days on app |
| CRM not updating on read | Message ID not stored — ensure broadcast sent from CRM (stores wamid) |
| Status shows orphan in logs | Message sent from phone app, not CRM — no wamid on file |

### Health check

```bash
curl https://YOUR-WEBHOOK-HOST/healthz
# {"ok": true, "whatsapp_configured": true}
```

### Test status tracking

1. Send WhatsApp broadcast to your own phone from CRM
2. Open message on phone (triggers `read`)
3. Check webhook logs: `[whatsapp] status_read: wamid…`
4. Open lead in CRM — status should show `contacted`, tag `wa-read`

---

## Appendix — Environment variables

| Variable | Where | Purpose |
|----------|-------|---------|
| `WHATSAPP_ACCESS_TOKEN` | Webhook + Streamlit | Send messages |
| `WHATSAPP_PHONE_NUMBER_ID` | Webhook + Streamlit | Your business number |
| `WHATSAPP_VERIFY_TOKEN` | Webhook only | Meta webhook handshake |
| `WHATSAPP_SEND_ACK` | Webhook | Auto-reply on inbound (`true`/`false`) |
| `WHATSAPP_ORG_ID` | Webhook | Multi-tenant CRM org |
| `GEMINI_API_KEY` / `DEEPSEEK_API_KEY` | Webhook | LLM intake |
| `GITHUB_TOKEN` / `SUPABASE_*` | Webhook + CRM | Persistence |

---

## Code reference (this repo)

| File | Role |
|------|------|
| `whatsapp_webhook.py` | Inbound, status, interactive handlers |
| `utils/whatsapp.py` | Send API + webhook parsers |
| `utils/wa_events.py` | CRM event model + auto-updates |
| `crm_ui.py` | Multi-select broadcast UI |
| `docs/WHATSAPP_COEXISTENCE.md` | Original coexistence runbook |

---

**FocusChain Labs** — Questions? Open an issue on the Leads Agent repo or check webhook logs first.
