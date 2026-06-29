# WhatsApp webhook service — deploy to Cloud Run (scales to zero).
#   gcloud run deploy crm-whatsapp --source . --dockerfile Dockerfile.webhook
FROM python:3.12-slim

WORKDIR /app

COPY requirements-webhook.txt .
RUN pip install --no-cache-dir -r requirements-webhook.txt

COPY utils/ utils/
COPY agent/ agent/
COPY scripts/ scripts/
COPY whatsapp_webhook.py .
COPY secure_webhook_app.py .

# The daily AI batch (scripts/process_inbound_daily.py) reuses this same image —
# the Cloud Run Job just overrides the command with:
#   python scripts/process_inbound_daily.py --all
ENV PORT=8080
CMD exec uvicorn secure_webhook_app:app --host 0.0.0.0 --port ${PORT}
