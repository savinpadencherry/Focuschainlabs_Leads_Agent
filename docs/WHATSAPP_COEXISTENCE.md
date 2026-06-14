# WhatsApp Coexistence — Onboarding Runbook

Goal: run **one** business number on **both** the WhatsApp Business **app**
(Srikanth chats normally on his phone) **and** the **Cloud API** (every message
mirrors to our webhook → CRM). With this, replies from the app are captured too,
so "reply-from-CRM" becomes optional.

> I can't perform the Meta/phone steps for you (QR scans, OTPs, app installs) —
> this is the exact checklist. The code side is already done: the webhook
> handles Coexistence inbound and ignores our own echoed messages.

---

## ⚠️ The catch for YOUR situation (read first)

Coexistence is an **app-first** feature: you connect a number that is **already
live on the WhatsApp Business app** to the Cloud API. **Your number
+91 99383 41236 is currently Cloud-API-first** (registered straight to the API,
never on the app). So you have a decision:

### Option 1 — Use a number that's already on the WhatsApp Business app (recommended)
If Srikanth already runs the business on a WhatsApp Business app number (with
real chat history), onboard **that** number to Coexistence. It's eligible
immediately, keeps his history, and there's **no downtime**. Cleanest path.

### Option 2 — Convert +91 99383 41236 to Coexistence
Because it's currently API-only, you must move it onto the app first, which
**temporarily breaks the current API capture** until Coexistence is linked:
1. **Deregister** it from the Cloud API (Meta → WhatsApp → API Setup → the
   number → remove/deregister). ⛔ CRM capture stops here.
2. Install **WhatsApp Business app** on the phone with that SIM, register the
   number (OTP), and **use it for real conversations for ~7 days** (Meta checks
   activity/quality before allowing API re-attach).
3. Run the Coexistence onboarding below → API reconnects **alongside** the app →
   CRM capture resumes (now via Coexistence).

➡️ If this number is the one on your website/ads, you'll use Option 2 — just
schedule it as a short maintenance window and keep **reply-from-CRM** running in
the meantime so you don't miss leads.

---

## Prerequisites (Meta checklist)
- [ ] **WhatsApp Business app v2.24.17+** on a smartphone with a camera.
- [ ] The number has been **active on the Business app ≥7 days** with **real**
      customer conversations (no fresh/empty numbers — Meta rejects those).
- [ ] **Meta Business Manager verified**, no bans/violations on the number.
- [ ] You're an **admin** of the Meta app + Business portfolio.
- [ ] App is **Live/published** (you already did this).

## Onboarding steps (Embedded Signup → Coexistence)
1. Meta → your app → **WhatsApp → API Setup / Embedded Signup** → start the
   signup and choose **"Connect your existing WhatsApp Business App"**
   (the Coexistence path) — not "create a new number."
2. Select country code + enter the **Business app number**.
3. Meta shows a **QR code**, and the **WhatsApp Business app** on the phone gets
   a message with a **confirmation code** + a "scan QR" button.
4. On the phone: tap the button → **choose to share message history** (optional,
   syncs up to ~6 months) → **scan the QR** shown in the signup.
5. The Cloud API takes over and finishes registration. The number now shows
   under your **WhatsApp Business Account** with a **Phone Number ID**.

## After onboarding — point our system at it
1. **Phone Number ID may change** (it's a new registration). Copy the new
   Phone Number ID from API Setup and set it in the **HF Space →
   `WHATSAPP_PHONE_NUMBER_ID`**.
2. **Token:** your permanent token must have access to this WABA. If the WABA is
   the same (`2042622836631069`), your existing token works; otherwise generate a
   permanent token for the new WABA and update `WHATSAPP_ACCESS_TOKEN`.
3. **Webhook:** Configuration → confirm **Callback URL** = your `…hf.space/webhook`
   and **`messages`** is subscribed; subscribe this WABA
   (`POST /v21.0/<WABA_ID>/subscribed_apps`).
4. **Test:** from another phone, message the number → it should appear in the CRM
   (HF Logs: `[whatsapp] created: …`). Then have Srikanth **reply from the app**
   → the customer gets it, and (echo handling aside) the customer's side is in
   the CRM thread.

## Keep it alive
- **Open the WhatsApp Business app at least once every 13 days**, or Meta
  deactivates the Coexistence link.
- Group chats, view-once, and disappearing messages **do not** sync.

## What's already handled in code
- Inbound customer messages (Coexistence sends the same `messages` webhook) →
  parsed → Gemini → CRM. ✅ no change needed.
- **Echoes:** messages Srikanth sends from the app are echoed to the webhook with
  `from` == our own number; the parser now **skips** those so they don't create a
  self-lead. (Logging his app replies *into the customer's thread* as outbound is
  a follow-up — once we see a real echo payload in the HF logs I'll wire it up.)

## Honest recommendation
Coexistence is great for "Srikanth lives in the app." But for a multi-person,
AI-assisted, audited setup, the **Cloud-API + reply-from-CRM** model is actually
stronger (shared inbox, every agent, full history, automation). Many teams run
**both**: app for quick personal replies, CRM for the team + AI. You can start
with reply-from-CRM today (zero migration) and add Coexistence when ready.
