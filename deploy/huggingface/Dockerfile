# Hugging Face Space — WhatsApp → CRM webhook (FREE, no credit card).
#
# This is the ONLY file you need in the Space (besides README.md). It pulls the
# webhook code straight from the public GitHub repo at build time, so you don't
# have to upload utils/, agent/, etc. by hand.
#
# NOTE: this works when the GitHub repo is PUBLIC. If your repo is private,
# use the Render path instead (render.yaml) — Render connects via OAuth and
# handles private repos for you.
FROM python:3.12-slim

# git is needed to fetch the code; remove apt lists afterwards to stay small.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Pull the webhook + its helpers from the PUBLIC repo's default branch (main).
# Merge PR #17 into main first so it includes the latest webhook.
RUN git clone --depth 1 \
    https://github.com/savinpadencherry/Focuschainlabs_Leads_Agent.git .

RUN pip install --no-cache-dir -r requirements-webhook.txt

# Hugging Face Spaces serve on port 7860.
EXPOSE 7860
CMD ["uvicorn", "whatsapp_webhook:app", "--host", "0.0.0.0", "--port", "7860"]
