# System Architecture Diagrams

## WhatsApp Integration Architecture

### High-Level Flow

```
┌─────────────────┐
│   User WhatsApp │
│   (Customer)    │
└────────┬────────┘
         │ Sends message
         ▼
┌─────────────────────────┐
│   Meta Cloud API        │
│   (WhatsApp Business)   │
└────────┬────────────────┘
         │ Webhook POST
         ▼
┌─────────────────────────┐
│   Railway Webhook       │
│   (FastAPI Service)     │
│   - Parse message       │
│   - Validate sender     │
│   - Extract info        │
└────────┬────────────────┘
         │
         ├─────────────────┐
         │                 │
         ▼                 ▼
┌─────────────────┐  ┌──────────────┐
│  AI Agent       │  │  CRM Store   │
│  (DeepSeek/     │  │  (GitHub or  │
│   Gemini)       │  │   Postgres)  │
│  - Parse text   │  │              │
│  - Extract      │  │  - Find/     │
│    contact info │  │    Create    │
│  - Update fields│  │  - Update    │
└─────────┬───────┘  └──────┬───────┘
         │                 │
         └────────┬────────┘
                  │
                  ▼
         ┌─────────────────┐
         │  Save to CRM    │
         │  - Add comment  │
         │  - Update status│
         └────────┬────────┘
                  │
                  ├──────────────────┐
                  │                  │
                  ▼                  ▼
         ┌─────────────────┐  ┌──────────────┐
         │  Auto-reply     │  │  Streamlit   │
         │  (Optional)     │  │  App         │
         │  "Got it! ✅"   │  │  - Display   │
         └─────────────────┘  │  - Manage    │
                              │  - Reply     │
                              └──────────────┘
```

### Data Flow

```
Incoming Message:
{
  "from": "919876543210",
  "name": "Rajesh Kumar",
  "text": "Hi, interested in your product. Budget 50L. Need demo.",
  "timestamp": "2024-06-10T10:30:00Z"
}
         ↓
AI Parsing:
{
  "name": "Rajesh Kumar",
  "phone": "+919876543210",
  "notes": "Interested in product. Budget 50L. Needs demo.",
  "budget": "50L",
  "status": "new",
  "source": "whatsapp"
}
         ↓
CRM Record:
{
  "id": "cnt_abc123",
  "name": "Rajesh Kumar",
  "phone": "+919876543210",
  "status": "new",
  "deal_status": "open",
  "source": "whatsapp",
  "notes": "Interested in product. Budget 50L. Needs demo.",
  "comments": [
    {
      "author": "Rajesh Kumar",
      "body": "Hi, interested in your product. Budget 50L. Need demo.",
      "source": "whatsapp",
      "created_at": "2024-06-10T10:30:00Z"
    }
  ],
  "created_at": "2024-06-10T10:30:00Z",
  "updated_at": "2024-06-10T10:30:00Z"
}
```

### Deployment Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     Production Setup                      │
└──────────────────────────────────────────────────────────┘

┌─────────────────┐         ┌─────────────────┐
│  Meta Cloud API │◄────────┤  Your WhatsApp  │
│  (Facebook)     │         │  Business Number│
└────────┬────────┘         └─────────────────┘
         │
         │ HTTPS Webhook
         │
         ▼
┌─────────────────────────────────────────────┐
│           Railway (Free Tier)                │
│  ┌─────────────────────────────────────┐   │
│  │  FastAPI Webhook Service            │   │
│  │  - whatsapp_webhook.py              │   │
│  │  - Auto-scales to zero              │   │
│  │  - 500 hours/month free             │   │
│  └─────────────────────────────────────┘   │
└────────┬────────────────────────────────────┘
         │
         │ GitHub API / Postgres
         │
         ▼
┌─────────────────────────────────────────────┐
│           CRM Storage                        │
│  ┌─────────────────┐  ┌─────────────────┐  │
│  │  GitHub Repo    │  │  Postgres DB    │  │
│  │  (Free)         │  │  (Supabase)     │  │
│  │  - contacts.json│  │  - contacts tbl │  │
│  │  - Version ctrl │  │  - Scalable     │  │
│  └─────────────────┘  └─────────────────┘  │
└────────┬────────────────────────────────────┘
         │
         │ Read/Write
         │
         ▼
┌─────────────────────────────────────────────┐
│      Streamlit Cloud (Community)             │
│  ┌─────────────────────────────────────┐   │
│  │  Main CRM App                       │   │
│  │  - streamlit_app.py                 │   │
│  │  - View conversations               │   │
│  │  - Send replies                     │   │
│  │  - Manage contacts                  │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

## Google Meet Integration Architecture

### Meeting Scheduling Flow

```
┌─────────────────┐
│  CRM Contact    │
│  Detail Page    │
└────────┬────────┘
         │ Click "Schedule Meeting"
         ▼
┌─────────────────────────┐
│  Meeting Scheduler UI   │
│  - Date picker          │
│  - Time picker          │
│  - Duration selector    │
│  - Agenda text area     │
└────────┬────────────────┘
         │ Click "Generate Link"
         ▼
┌─────────────────────────┐
│  Generate Meet Link     │
│  - Random code          │
│  - Format: meet.google  │
│    .com/abc-defg-hij    │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Store in CRM           │
│  - Add comment          │
│  - Meeting details      │
│  - Link + agenda        │
└────────┬────────────────┘
         │
         ├──────────────────┐
         │                  │
         ▼                  ▼
┌─────────────────┐  ┌──────────────┐
│  Send           │  │  Display in  │
│  Notification   │  │  CRM Thread  │
│  - Email        │  │              │
│  - WhatsApp     │  │  ✓ Clickable │
│  - SMS          │  │  ✓ Copyable  │
└─────────────────┘  └──────────────┘
```

### Meeting Execution Flow

```
┌─────────────────┐
│  Meeting Time   │
│  Approaches     │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│  Reminder Sent          │
│  - 1 day before         │
│  - 1 hour before        │
│  - Include link         │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Both Parties Join      │
│  - Click Meet link      │
│  - Video call starts    │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  During Meeting         │
│  - Take notes           │
│  - Mark key points      │
│  - Record actions       │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Post-Meeting           │
│  - Add notes to CRM     │
│  - AI summary           │
│  - Extract actions      │
│  - Update status        │
└─────────────────────────┘
```

### Optional: Calendar API Integration

```
┌─────────────────────────┐
│  Google Calendar API    │
│  (Optional Enhancement) │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  Enhanced Features:                      │
│  ┌─────────────────────────────────┐   │
│  │  1. Auto-create calendar event  │   │
│  │  2. Send email invites          │   │
│  │  3. Sync with team calendar     │   │
│  │  4. Automatic reminders         │   │
│  │  5. Conflict detection          │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Service Account        │
│  - JSON credentials     │
│  - Calendar access      │
│  - API calls            │
└─────────────────────────┘
```

## System Integration Overview

### Complete CRM Ecosystem

```
┌────────────────────────────────────────────────────────────────┐
│                    FocusChain CRM System                        │
└────────────────────────────────────────────────────────────────┘

┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  Lead Sources   │  │  Communication  │  │  Scheduling     │
├─────────────────┤  ├─────────────────┤  ├─────────────────┤
│ • Scout Agent   │  │ • WhatsApp      │  │ • Google Meet   │
│ • Manual Entry  │  │ • Email         │  │ • Calendar      │
│ • LinkedIn      │  │ • Phone         │  │ • Reminders     │
│ • Referrals     │  │ • SMS           │  │                 │
│ • Events        │  │                 │  │                 │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                     │
         └────────────────────┼─────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   CRM Core      │
                    │   (GitHub/PG)   │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  Reach Agent    │  │  Intel Agent    │  │  Proposal Agent │
│  - Email seq    │  │  - Research     │  │  - Generate     │
│  - Follow-ups   │  │  - Insights     │  │  - Customize    │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

## Technology Stack

```
┌────────────────────────────────────────────────────────────┐
│                      Tech Stack                             │
└────────────────────────────────────────────────────────────┘

Frontend:
  • Streamlit (Python web framework)
  • Custom CSS (Premium UI)
  • Responsive design

Backend:
  • FastAPI (Webhook service)
  • Python 3.11+
  • Async operations

AI/ML:
  • DeepSeek (Primary LLM)
  • Gemini (Fallback)
  • Contact parsing
  • Meeting summaries

Storage:
  • GitHub (Version control + storage)
  • PostgreSQL (Optional, scalable)
  • JSON (Lightweight)

APIs:
  • Meta WhatsApp Cloud API
  • Google Meet API
  • Google Calendar API (Optional)
  • Hunter.io (Email finding)

Deployment:
  • Streamlit Cloud (Main app)
  • Railway (Webhook service)
  • GitHub Actions (CI/CD)

Monitoring:
  • Railway logs
  • Streamlit metrics
  • Custom analytics
```

## Security Architecture

```
┌────────────────────────────────────────────────────────────┐
│                   Security Layers                           │
└────────────────────────────────────────────────────────────┘

1. Transport Security:
   ┌─────────────────────────────────────┐
   │  • HTTPS everywhere                 │
   │  • TLS 1.3                          │
   │  • Certificate validation           │
   └─────────────────────────────────────┘

2. Authentication:
   ┌─────────────────────────────────────┐
   │  • API tokens (Bearer)              │
   │  • Webhook verification             │
   │  • Service accounts                 │
   └─────────────────────────────────────┘

3. Authorization:
   ┌─────────────────────────────────────┐
   │  • Scoped permissions               │
   │  • Read-only where possible         │
   │  • Principle of least privilege     │
   └─────────────────────────────────────┘

4. Data Protection:
   ┌─────────────────────────────────────┐
   │  • Environment variables            │
   │  • No secrets in code               │
   │  • Encrypted at rest                │
   │  • Encrypted in transit             │
   └─────────────────────────────────────┘

5. Rate Limiting:
   ┌─────────────────────────────────────┐
   │  • API quotas                       │
   │  • Request throttling               │
   │  • DDoS protection (Railway)        │
   └─────────────────────────────────────┘
```

## Scalability Considerations

```
Current Setup (Free Tier):
  • 1,000 WhatsApp conversations/month
  • 500 Railway hours/month
  • Unlimited GitHub storage
  • 1 Streamlit app

Scaling Path:
  ┌─────────────────────────────────────┐
  │  Phase 1: Current (0-1K contacts)   │
  │  • GitHub storage                   │
  │  • Railway free tier                │
  │  • Streamlit Community              │
  └─────────────────────────────────────┘
                    │
                    ▼
  ┌─────────────────────────────────────┐
  │  Phase 2: Growth (1K-10K contacts)  │
  │  • Migrate to PostgreSQL            │
  │  • Railway Starter ($5/mo)          │
  │  • Streamlit Team ($20/mo)          │
  └─────────────────────────────────────┘
                    │
                    ▼
  ┌─────────────────────────────────────┐
  │  Phase 3: Scale (10K+ contacts)     │
  │  • Dedicated Postgres               │
  │  • Railway Pro                      │
  │  • Load balancing                   │
  │  • Caching layer                    │
  └─────────────────────────────────────┘
```

## Cost Breakdown

```
┌────────────────────────────────────────────────────────────┐
│                    Monthly Costs                            │
└────────────────────────────────────────────────────────────┘

Free Tier (Current):
  • Meta WhatsApp: $0 (1K conversations)
  • Railway: $0 (500 hours)
  • GitHub: $0 (unlimited)
  • Streamlit: $0 (Community)
  • DeepSeek: $0 (generous free tier)
  ─────────────────────────────────
  Total: $0/month

Paid Tier (If needed):
  • Meta WhatsApp: ~$5-50 (depends on volume)
  • Railway: $5 (Starter)
  • GitHub: $0 (still free)
  • Streamlit: $20 (Team)
  • DeepSeek: ~$10 (if exceeding free tier)
  ─────────────────────────────────
  Total: ~$40-85/month
```

---

## Quick Reference

### WhatsApp Setup
1. Create Meta app → Get credentials
2. Deploy to Railway → Get webhook URL
3. Configure Meta webhook → Test
4. Add secrets to Streamlit → Done

### Google Meet Setup
1. Already working! (Basic links)
2. Optional: Add Calendar API
3. Optional: Enhance UI
4. Optional: Add notifications

### Monitoring
- Railway: https://railway.app → Logs
- Meta: https://developers.facebook.com → Webhooks
- Streamlit: App metrics dashboard

### Support
- WhatsApp: `docs/WHATSAPP_INTEGRATION.md`
- Meet: `docs/GOOGLE_MEET_INTEGRATION.md`
- Railway: `docs/RAILWAY_DEPLOYMENT.md`