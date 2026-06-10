# Railway Deployment Guide for WhatsApp Webhook

## Quick Start

Deploy your WhatsApp webhook to Railway in under 5 minutes.

## Prerequisites

- GitHub account with your code repository
- Railway account (sign up at https://railway.app)
- Meta WhatsApp Business API credentials

## Step-by-Step Deployment

### 1. Prepare Your Repository

Ensure these files exist in your repo:

```
your-repo/
├── whatsapp_webhook.py          # FastAPI webhook service
├── requirements-webhook.txt      # Python dependencies
├── Dockerfile.webhook (optional) # Railway auto-detects Python
├── utils/
│   ├── whatsapp.py
│   ├── crm_store.py
│   └── crm_models.py
└── agent/
    └── crm_intake_agent.py
```

**requirements-webhook.txt** should contain:
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
requests==2.31.0
python-dotenv==1.0.0
PyGithub==2.1.1
```

### 2. Deploy to Railway

#### Option A: Deploy from GitHub (Recommended)

1. **Connect GitHub:**
   - Go to https://railway.app
   - Click "Login" → "Login with GitHub"
   - Authorize Railway

2. **Create New Project:**
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your repository
   - Railway will auto-detect Python

3. **Configure Service:**
   - Railway creates a service automatically
   - Click on the service to configure

4. **Set Start Command:**
   Railway should auto-detect, but verify:
   ```
   uvicorn whatsapp_webhook:app --host 0.0.0.0 --port $PORT
   ```
   
   If not set, add in Settings → Deploy → Start Command

#### Option B: Deploy from CLI

1. **Install Railway CLI:**
   ```bash
   npm i -g @railway/cli
   # or
   brew install railway
   ```

2. **Login:**
   ```bash
   railway login
   ```

3. **Initialize Project:**
   ```bash
   cd your-repo
   railway init
   ```

4. **Deploy:**
   ```bash
   railway up
   ```

### 3. Configure Environment Variables

In Railway dashboard → Your Service → Variables:

**Required Variables:**
```bash
WHATSAPP_ACCESS_TOKEN=EAAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
WHATSAPP_PHONE_NUMBER_ID=123456789012345
WHATSAPP_VERIFY_TOKEN=your_random_secret_token_here
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GITHUB_REPO=username/your-crm-repo
```

**Optional Variables:**
```bash
GEMINI_API_KEY=AIzaSyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
WHATSAPP_SEND_ACK=true
WHATSAPP_ORG_ID=your_org_id
DATABASE_URL=postgresql://user:pass@host:5432/db
```

**How to Add Variables:**
1. Click "Variables" tab
2. Click "New Variable"
3. Enter name and value
4. Click "Add"
5. Railway auto-redeploys

### 4. Get Your Webhook URL

1. **Generate Domain:**
   - Click "Settings" tab
   - Scroll to "Networking"
   - Click "Generate Domain"
   - Railway creates: `your-service-production.up.railway.app`

2. **Custom Domain (Optional):**
   - Add your own domain
   - Configure DNS CNAME record
   - Railway handles SSL automatically

3. **Note Your URL:**
   ```
   https://your-service-production.up.railway.app
   ```

### 5. Configure Meta Webhook

1. **Go to Meta for Developers:**
   - https://developers.facebook.com/apps
   - Select your app
   - WhatsApp → Configuration

2. **Edit Webhook:**
   - Click "Edit" button
   - Callback URL: `https://your-service-production.up.railway.app/webhook`
   - Verify Token: (same as `WHATSAPP_VERIFY_TOKEN` in Railway)
   - Click "Verify and Save"

3. **Subscribe to Fields:**
   - Check "messages"
   - Save

### 6. Test Your Deployment

1. **Health Check:**
   ```bash
   curl https://your-service-production.up.railway.app/healthz
   ```
   
   Should return:
   ```json
   {"ok": true, "whatsapp_configured": true}
   ```

2. **Send Test Message:**
   - Send WhatsApp message to your business number
   - Check Railway logs (see below)
   - Verify contact appears in CRM

3. **Check Logs:**
   - Railway dashboard → Deployments tab
   - Click "View Logs"
   - Should see:
   ```
   [whatsapp] created: +919876543210 (45 chars)
   ```

## Monitoring & Logs

### View Logs

**In Dashboard:**
1. Click your service
2. Click "Deployments" tab
3. Click "View Logs" on latest deployment
4. Logs stream in real-time

**Filter Logs:**
- Search for `[whatsapp]` to see webhook activity
- Search for `ERROR` to find issues
- Search for contact names/numbers

### Common Log Messages

**Success:**
```
[whatsapp] created: Contact Name (+919876543210)
[whatsapp] updated: Existing Contact
```

**Errors:**
```
[whatsapp] ERROR storing message abc123: CRM save failed
[whatsapp] ERROR storing message xyz789: Invalid token
```

### Set Up Alerts

Railway doesn't have built-in alerts, but you can:

1. **Use External Monitoring:**
   - UptimeRobot (free)
   - Pingdom
   - Better Uptime

2. **Monitor Endpoint:**
   ```
   https://your-service-production.up.railway.app/healthz
   ```

3. **Alert on Down:**
   - Email notification
   - Slack webhook
   - SMS alert

## Scaling & Performance

### Free Tier Limits

- **Execution Time:** 500 hours/month
- **Memory:** 512 MB (default)
- **CPU:** Shared
- **Bandwidth:** 100 GB/month

**Typical Usage:**
- Webhook processes in <100ms
- Scales to zero when idle
- Wakes up instantly on request
- Should handle 1000+ messages/month easily

### Upgrade if Needed

**Starter Plan ($5/month):**
- 500 hours included
- Additional hours: $0.01/hour
- More memory/CPU
- Priority support

**When to Upgrade:**
- Processing >500 hours/month
- Need more memory (>512 MB)
- Want faster cold starts
- Need dedicated resources

### Optimize Performance

1. **Reduce Cold Starts:**
   - Railway keeps service warm with traffic
   - Add health check pings every 5 minutes
   - Use cron job to ping `/healthz`

2. **Optimize Code:**
   - Cache CRM data when possible
   - Use async operations
   - Minimize external API calls

3. **Monitor Usage:**
   - Check "Metrics" tab in Railway
   - Watch memory usage
   - Track response times

## Troubleshooting

### Deployment Failed

**Check Build Logs:**
1. Deployments tab → Failed deployment
2. Click "View Logs"
3. Look for error messages

**Common Issues:**

❌ **Missing dependencies:**
```
ERROR: Could not find a version that satisfies the requirement
```
**Fix:** Add missing package to `requirements-webhook.txt`

❌ **Port binding error:**
```
Error: Address already in use
```
**Fix:** Use `$PORT` environment variable:
```python
uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
```

❌ **Import errors:**
```
ModuleNotFoundError: No module named 'utils'
```
**Fix:** Ensure all files are committed to Git

### Webhook Not Receiving Messages

**1. Check Railway Logs:**
- Should see POST requests to `/webhook`
- If no requests, Meta isn't sending

**2. Verify Meta Configuration:**
- Callback URL matches Railway domain
- Verify token matches environment variable
- "messages" field is subscribed

**3. Test Webhook Manually:**
```bash
# Test verification endpoint
curl "https://your-service.railway.app/webhook?hub.mode=subscribe&hub.verify_token=YOUR_TOKEN&hub.challenge=test123"

# Should return: test123
```

**4. Check Firewall/Network:**
- Railway provides public HTTPS by default
- No firewall configuration needed
- Meta can reach Railway directly

### High Memory Usage

**Monitor Memory:**
- Railway dashboard → Metrics
- Watch memory graph
- Check for memory leaks

**Optimize:**
```python
# Limit in-memory cache
_SEEN_IDS: OrderedDict[str, None] = OrderedDict()
_SEEN_MAX = 2000  # Reduce if needed

# Clear old entries
while len(_SEEN_IDS) > _SEEN_MAX:
    _SEEN_IDS.popitem(last=False)
```

### Slow Response Times

**Check Logs:**
- Look for slow operations
- Identify bottlenecks

**Common Causes:**
- GitHub API rate limits
- Large CRM file
- Slow LLM calls

**Solutions:**
- Cache CRM data
- Use Postgres instead of GitHub for high volume
- Make LLM calls async/optional

## Maintenance

### Update Code

**Automatic Deployment:**
1. Push to GitHub main branch
2. Railway auto-detects changes
3. Builds and deploys automatically
4. Zero downtime deployment

**Manual Deployment:**
```bash
railway up
```

### Update Environment Variables

1. Railway dashboard → Variables
2. Edit variable
3. Save
4. Railway auto-redeploys

### Rollback Deployment

1. Deployments tab
2. Find previous working deployment
3. Click "⋮" menu → "Redeploy"
4. Confirms rollback

### Backup Strategy

**CRM Data:**
- GitHub: Automatic version control
- Postgres: Set up automated backups
- Export contacts regularly

**Configuration:**
- Document all environment variables
- Keep backup of Railway settings
- Store credentials securely (1Password, etc.)

## Cost Optimization

### Stay on Free Tier

**Tips:**
- Service scales to zero when idle
- Only charged for active time
- 500 hours = ~20 days of 24/7 uptime
- Typical usage: <50 hours/month

**Monitor Usage:**
- Railway dashboard → Usage
- Set up budget alerts
- Track monthly consumption

### Reduce Costs

1. **Optimize Cold Starts:**
   - Don't ping too frequently
   - Let service sleep when idle

2. **Efficient Code:**
   - Fast webhook processing
   - Minimal memory usage
   - Quick response times

3. **Use Caching:**
   - Cache CRM data
   - Reduce API calls
   - Store frequently accessed data

## Security Best Practices

### Protect Credentials

1. **Never Commit Secrets:**
   ```bash
   # Add to .gitignore
   .env
   .env.local
   secrets.json
   ```

2. **Use Environment Variables:**
   - All secrets in Railway Variables
   - Never hardcode tokens
   - Rotate regularly

3. **Verify Webhook Signatures:**
   ```python
   # Optional: Verify Meta signature
   import hmac
   import hashlib
   
   def verify_signature(payload, signature, secret):
       expected = hmac.new(
           secret.encode(),
           payload,
           hashlib.sha256
       ).hexdigest()
       return hmac.compare_digest(f"sha256={expected}", signature)
   ```

### Network Security

- Railway provides HTTPS by default
- No additional SSL configuration needed
- Firewall not required (Railway handles)

### Access Control

- Limit GitHub token permissions
- Use read-only tokens where possible
- Rotate tokens every 90 days

## Support & Resources

- **Railway Docs:** https://docs.railway.app
- **Railway Discord:** https://discord.gg/railway
- **Railway Status:** https://status.railway.app
- **GitHub Issues:** Report bugs in your repo

## Checklist

- [ ] Repository prepared with all files
- [ ] Railway account created
- [ ] Service deployed from GitHub
- [ ] Environment variables configured
- [ ] Domain generated
- [ ] Meta webhook configured
- [ ] Test message sent successfully
- [ ] Logs verified
- [ ] Monitoring set up
- [ ] Documentation updated
- [ ] Team trained on deployment