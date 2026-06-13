---
title: FocusChain WhatsApp Webhook
emoji: 💬
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# FocusChain WhatsApp → CRM webhook

Receives Meta WhatsApp Cloud API webhooks and writes leads into the
GitHub-backed CRM (`data/crm/contacts.json`). The Streamlit app reads that file.

**Endpoints**
- `GET /webhook` — Meta verification handshake
- `POST /webhook` — incoming messages → CRM
- `GET /healthz` — health check

Configure secrets under **Settings → Variables and secrets**:
`WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`,
`GITHUB_TOKEN`, `GITHUB_REPO`, `GITHUB_BRANCH` (and optionally
`WHATSAPP_SEND_ACK=true`, `DEEPSEEK_API_KEY`).

See `docs/WHATSAPP_DEMO_SETUP.md` in the main repo for the full walkthrough.
