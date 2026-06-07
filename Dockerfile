# FocusChain Leads Agent — container image for Cloud Run (or any container host).
# Build:   docker build -t focuschain-leads .
# Run:     docker run -p 8080:8080 --env-file .env focuschain-leads
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# Install deps first for better layer caching.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Cloud Run sends traffic to $PORT. Streamlit must bind 0.0.0.0 and disable CORS/XSRF
# behind the Cloud Run proxy. Headless avoids the email prompt on first boot.
EXPOSE 8080
CMD streamlit run streamlit_app.py \
    --server.port=${PORT} \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --browser.gatherUsageStats=false
