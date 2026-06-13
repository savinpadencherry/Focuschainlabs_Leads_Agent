# WhatsApp Integration Guide

> 👉 **Just want a working demo fast?** Follow **[WHATSAPP_DEMO_SETUP.md](WHATSAPP_DEMO_SETUP.md)** —
> the test-number path on a free **Koyeb** host (no card, no business
> verification). This guide is the fuller reference.
>
> Note: Railway no longer offers a standing free tier; for free **always-on**
> webhook hosting use **Koyeb** (Render's free tier works too but sleeps when
> idle, which can make Meta's webhook verification time out).

## Architecture Overview

```
User WhatsApp → Meta Cloud API → Railway Webhook → CRM (GitHub/Postgres) → Streamlit App
                                       ↓
                                  AI Agent Parse
                                       ↓
                                  Auto-reply (optional)
```

## How It Works

1. **Incoming Message Flow:**
   - User sends WhatsApp message to your business number
   - Meta Cloud API receives message and POSTs to your webhook
   - Railway-hosted FastAPI service processes the webhook
   - AI agent extracts contact info (name, company, intent)
   - Contact is created/updated in CRM
   - Optional auto-reply sent back to user

2. **Outgoing Message Flow:**
   - Sales team views conversation in Streamlit CRM
   - Clicks "Send WhatsApp" button
   - Message sent via Meta Cloud API
   - Logged to CRM conversation thread

3. **Free Tier Compatibility:**
   - Meta: 1,000 free conversations/month
   - Railway: 500 hours/month (scales to zero)
   - GitHub: Unlimited for CRM storage
   - Streamlit Cloud: Community tier compatible

## Setup Instructions

### Step 1: Meta for Developers Setup

1. **Create Meta App:**
   - Go to https://developers.facebook.com/apps
   - Click "Create App" → "Business" type
   - Name: "YourCompany CRM"

2. **Add WhatsApp Product:**
   - In app dashboard, click "Add Product"
   - Select "WhatsApp" → "Set Up"
   - Choose "Business Account" or create new

3. **Get Test Number:**
   - Meta provides a test number for development
   - Add your personal WhatsApp to test recipients
   - Send test message to verify

4. **Get Credentials:**
   - **Phone Number ID:** Found in "API Setup" tab
   - **Access Token:** Temporary token (24h) or create permanent system user token
   - **Verify Token:** Create your own random string (e.g., `whatsapp_verify_2024_xyz`)

5. **Create Permanent Token (Production):**
   - Go to "System Users" in Business Settings
   - Create system user → Generate token
   - Permissions: `whatsapp_business_messaging`, `whatsapp_business_management`
   - Save token securely (shown only once)

### Step 2: Deploy Webhook to Railway

1. **Prepare Repository:**
   ```bash
   # Ensure these files exist in your repo:
   # - whatsapp_webhook.py
   # - requirements-webhook.txt
   # - Dockerfile.webhook (optional, Railway auto-detects Python)
   ```

2. **Deploy to Railway:**
   - Go to https://railway.app
   - Sign in with GitHub
   - Click "New Project" → "Deploy from GitHub repo"
   - Select your repository
   - Railway auto-detects Python and installs dependencies

3. **Configure Environment Variables:**
   In Railway project settings, add:
   ```
   WHATSAPP_ACCESS_TOKEN=your_permanent_token
   WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
   WHATSAPP_VERIFY_TOKEN=your_random_verify_token
   GITHUB_TOKEN=your_github_pat
   GITHUB_REPO=username/crm-repo
   GEMINI_API_KEY=your_gemini_key
   WHATSAPP_SEND_ACK=true
   ```

4. **Get Railway URL:**
   - Railway generates URL: `https://your-app.railway.app`
   - Note this URL for webhook configuration

5. **Configure Start Command:**
   Railway should auto-detect, but if needed:
   ```
   uvicorn whatsapp_webhook:app --host 0.0.0.0 --port $PORT
   ```

### Step 3: Configure Meta Webhook

1. **Add Webhook URL:**
   - In Meta app → WhatsApp → Configuration
   - Click "Edit" next to Webhook
   - Callback URL: `https://your-app.railway.app/webhook`
   - Verify Token: (same as `WHATSAPP_VERIFY_TOKEN`)
   - Click "Verify and Save"

2. **Subscribe to Webhooks:**
   - Check "messages" field
   - Save changes

3. **Test Webhook:**
   - Send message to your WhatsApp business number
   - Check Railway logs: should see "handled: 1"
   - Check CRM: contact should appear

### Step 4: Configure Streamlit App

1. **Add Secrets to Streamlit Cloud:**
   In your Streamlit app settings → Secrets:
   ```toml
   WHATSAPP_ACCESS_TOKEN = "your_permanent_token"
   WHATSAPP_PHONE_NUMBER_ID = "your_phone_number_id"
   GITHUB_TOKEN = "your_github_pat"
   GITHUB_REPO = "username/crm-repo"
   ```

2. **Verify Integration:**
   - Open Streamlit CRM
   - Navigate to contact created via WhatsApp
   - Should see conversation thread
   - Test sending reply

## Usage

### Receiving Messages

1. Customer sends WhatsApp message
2. Webhook auto-creates/updates CRM contact
3. AI extracts: name, company, phone, intent
4. Optional auto-reply: "Got it — noted in our CRM. We'll get back to you shortly. ✅"
5. Sales team sees new lead in CRM with full context

### Sending Messages

1. Open contact in CRM
2. View conversation history
3. Click "Send WhatsApp" button
4. Type message → Send
5. Message logged to thread

## Troubleshooting

### Webhook Not Receiving Messages

**Check Railway Logs:**
```bash
# In Railway dashboard → Deployments → View Logs
# Should see: [whatsapp] created: +919876543210
```

**Common Issues:**
- ❌ Verify token mismatch → Check `WHATSAPP_VERIFY_TOKEN` matches Meta config
- ❌ URL not HTTPS → Railway provides HTTPS by default
- ❌ Port mismatch → Use `$PORT` environment variable
- ❌ Webhook not subscribed → Check "messages" field is checked in Meta

**Test Webhook Manually:**
```bash
curl https://your-app.railway.app/healthz
# Should return: {"ok": true, "whatsapp_configured": true}
```

### Messages Not Appearing in CRM

**Check GitHub/CRM:**
- Verify `GITHUB_TOKEN` has repo write access
- Check `GITHUB_REPO` format: `username/repo-name`
- Look for commit in GitHub repo (webhook creates commits)

**Check Railway Logs:**
```bash
# Should see successful save:
[whatsapp] created: Contact Name (123 chars)
```

### Cannot Send Messages from Streamlit

**Check Credentials:**
- `WHATSAPP_ACCESS_TOKEN` must be permanent token (not 24h temp)
- `WHATSAPP_PHONE_NUMBER_ID` must match your business number

**Check Phone Format:**
- Must be E.164 format: `+919876543210`
- No spaces, dashes, or parentheses

**Test API Directly:**
```bash
curl -X POST "https://graph.facebook.com/v21.0/YOUR_PHONE_ID/messages" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "to": "919876543210",
    "type": "text",
    "text": {"body": "Test message"}
  }'
```

### Rate Limits

**Meta Free Tier:**
- 1,000 conversations/month
- Conversation = 24-hour window after user message
- Replies within window are free

**Railway Free Tier:**
- 500 hours/month
- Scales to zero when idle
- Should be sufficient for most use cases

## Production Checklist

- [ ] Replace temporary token with permanent system user token
- [ ] Add production phone number (requires Meta Business Verification)
- [ ] Set up monitoring/alerts in Railway
- [ ] Configure backup CRM storage (Postgres for high volume)
- [ ] Test message delivery and CRM sync
- [ ] Train team on WhatsApp workflow
- [ ] Set up auto-reply templates
- [ ] Configure business hours for auto-replies

## Security Best Practices

1. **Never commit tokens to Git**
   - Use environment variables only
   - Add `.env` to `.gitignore`

2. **Verify webhook signatures** (optional enhancement)
   - Meta signs webhooks with `X-Hub-Signature-256`
   - Validate to prevent spoofing

3. **Rate limit webhook endpoint**
   - Prevent abuse
   - Railway has built-in DDoS protection

4. **Rotate tokens periodically**
   - Generate new system user token every 90 days
   - Update in Railway and Streamlit secrets

## Cost Breakdown

| Service | Free Tier | Paid Tier |
|---------|-----------|-----------|
| Meta WhatsApp | 1,000 conversations/mo | $0.005-0.09/conversation |
| Railway | 500 hours/mo | $5/mo for 500 hours |
| GitHub | Unlimited | N/A |
| Streamlit Cloud | Community (1 app) | $20/mo (3 apps) |

**Total Free:** $0/month for up to 1,000 conversations

## Support

- Meta WhatsApp Docs: https://developers.facebook.com/docs/whatsapp
- Railway Docs: https://docs.railway.app
- GitHub Issues: Report bugs in your repo