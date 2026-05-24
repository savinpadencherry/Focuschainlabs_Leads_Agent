# FocusChain LeadGen

Prompt-driven B2B lead generation agent.
Take a natural-language brief, scan the web for active buying signals,
score every match with Gemini, find the right decision maker, and
output a ranked Excel sheet ready for outreach.

## How it works

```
your prompt
  └─ Plan      Gemini turns the brief into search keywords + titles + hypotheses
  └─ Search    Serper · Reddit · Tracxn · ProxyCurl · Naukri (in parallel)
  └─ Dedupe    against the exclusion list + lowercase name set
  └─ Research  homepage + news + Reddit chatter + LinkedIn posts per company
  └─ Score     Gemini ranks 0-100 across fit / trigger / reachability / recency
  └─ Enrich    Apollo finds the decision maker + their recent LinkedIn posts
  └─ Pitch     Gemini writes a 1-line opener that references real, recent activity
  └─ Excel     ranked, colour-coded, frozen header — open in Excel or Sheets
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in your keys
streamlit run streamlit_app.py
```

### API keys

| Variable             | Source                           | Cost                | Required |
| -------------------- | -------------------------------- | ------------------- | -------- |
| `GEMINI_API_KEY`     | aistudio.google.com              | free tier           | yes      |
| `SERPER_API_KEY`     | serper.dev                       | 2,500 free searches | yes      |
| `APOLLO_API_KEY`     | apollo.io                        | 100 free credits/mo | yes      |
| `PROXYCURL_API_KEY`  | nubela.co/proxycurl              | paid                | optional |
| `TRACXN_API_KEY`     | tracxn.com                       | paid                | optional |

The app degrades gracefully — every optional source skips silently
when its key is missing.

## Run

```bash
# UI
streamlit run streamlit_app.py

# CLI
python main.py
```

## Streamlit Cloud deployment

1. Push this repo to GitHub.
2. Go to share.streamlit.io → New app → point at `streamlit_app.py`.
3. In **Secrets**, paste your `.env` contents (TOML-friendly: `KEY = "value"`).
4. Deploy.

## Add a new client / ICP

Drop a JSON file into `/config/` following the same schema as
`icp_digital_transformation.json`. The dropdown picks it up
automatically. No code changes.

## Cost

| Mode          | Estimate       | What runs                                 |
| ------------- | -------------- | ----------------------------------------- |
| `PILOT_MODE=true`  (default) | ₹0 – ₹500/mo  | free tiers only, caps Serper to 20 calls, Apollo to 5 enrichments |
| `PILOT_MODE=false`           | ₹10k – ₹12k/mo | full sweep across all sources             |

## Bundled clients

- **Focus Chain Labs** — digital transformation consulting (Bangalore mid-market)
- **Cadabams WeNest** — senior living B2B referral partners (Bangalore corporate HR + healthcare)
