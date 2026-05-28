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
3. In **Secrets**, paste TOML values using `.streamlit/secrets.example.toml` as the template.
4. Deploy.

Recommended Streamlit Cloud secrets shape:

```toml
GEMINI_API_KEY = "..."
SERPER_API_KEY = "..."
APOLLO_API_KEY = "..."
PROXYCURL_API_KEY = "..."
PILOT_MODE = "true"
MAX_LEADS_PER_RUN = "30"
MIN_SCORE_THRESHOLD = "60"
APOLLO_ENRICH_CAP = "30"
```

Notes:

- `GOOGLE_API_KEY` is also accepted as an alias for `GEMINI_API_KEY`.
- Keep real keys only in local `.env` or Streamlit Cloud Secrets. Never commit `.env` or `.streamlit/secrets.toml`.
- Community Cloud has resource limits, so keep `PILOT_MODE=true` while testing with teammates.
- If Apollo credits are limited, lower `APOLLO_ENRICH_CAP` to enrich fewer contacts while still exporting 30 researched companies.

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
