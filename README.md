# FocusChain LeadGen

AI-powered B2B lead generation agent for Focus Chain Labs.
Finds companies showing active buying signals, scores them,
finds the right decision maker, and outputs a ranked Excel file.

## Setup

1. Clone the repo and install dependencies:
   pip install -r requirements.txt

2. Copy .env.example to .env and fill in your API keys:
   cp .env.example .env

3. API keys (where to get them):
   - GEMINI_API_KEY     → aistudio.google.com (free)
   - SERPER_API_KEY     → serper.dev (free — 2,500 searches)
   - APOLLO_API_KEY     → apollo.io (free — 100 credits/month)
   - PROXYCURL_API_KEY  → nubela.co/proxycurl (optional, paid)
   - TRACXN_API_KEY     → tracxn.com (optional, paid)

## Run

Command line:
  python main.py

Streamlit UI:
  streamlit run streamlit_app.py

## Add a new client / ICP

Create a new JSON file in /config/ following the same schema
as icp_digital_transformation.json. The agent will pick it up
automatically in the Streamlit dropdown. No code changes needed.

## Cost

Pilot mode (free tiers only): ₹0 – ₹500/month
Steady state (all APIs): ₹10,000 – ₹12,000/month

## Clients

- Focus Chain Labs: digital transformation consulting
- Cadabams WeNest: senior living B2B referral partners
