#!/usr/bin/env bash
set -euo pipefail

PROJECT="${1:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-asia-south1}"
APP_SERVICE="${APP_SERVICE:-crm-app}"
WEBHOOK_SERVICE="${WEBHOOK_SERVICE:-crm-webhook}"

if [[ -z "${PROJECT}" || "${PROJECT}" == "(unset)" ]]; then
  echo "No GCP project is selected. Run: gcloud config set project YOUR_PROJECT_ID" >&2
  exit 1
fi

for command in gcloud jq; do
  command -v "${command}" >/dev/null || {
    echo "Missing command: ${command}" >&2
    exit 1
  }
done

service_json() {
  gcloud run services describe "$1" \
    --project="${PROJECT}" \
    --region="${REGION}" \
    --format=json
}

env_names() {
  jq -r '(.spec.template.spec.containers[0].env // [])[].name'
}

check_required() {
  local service="$1"
  shift
  local required=("$@")
  local json names

  echo
  echo "============================================================"
  echo "Cloud Run service: ${service}"
  echo "============================================================"

  if ! json="$(service_json "${service}" 2>/dev/null)"; then
    echo "MISSING SERVICE: ${service}"
    return 1
  fi

  echo "URL: $(jq -r '.status.url // "unknown"' <<<"${json}")"
  echo "Runtime service account: $(jq -r '.spec.template.spec.serviceAccountName // "default compute service account"' <<<"${json}")"
  names="$(env_names <<<"${json}")"

  echo
  echo "Configured environment names (values intentionally hidden):"
  if [[ -n "${names}" ]]; then
    sed 's/^/  - /' <<<"${names}"
  else
    echo "  (none)"
  fi

  echo
  echo "Required settings:"
  local missing=0
  for name in "${required[@]}"; do
    if grep -qx "${name}" <<<"${names}"; then
      echo "  OK       ${name}"
    else
      echo "  MISSING  ${name}"
      missing=1
    fi
  done

  if grep -Eq '^(DATABASE_URL|CLOUD_SQL_CONNECTION_NAME)$' <<<"${names}"; then
    echo "  OK       database connection"
  else
    echo "  MISSING  DATABASE_URL or CLOUD_SQL_CONNECTION_NAME"
    missing=1
  fi

  return "${missing}"
}

APP_OK=0
WEBHOOK_OK=0
check_required "${APP_SERVICE}" \
  META_APP_ID META_CONFIG_ID WA_CONNECT_SECRET WEBHOOK_PUBLIC_URL \
  META_EMBEDDED_SIGNUP_FEATURE_TYPE || APP_OK=$?

check_required "${WEBHOOK_SERVICE}" \
  META_APP_ID META_APP_SECRET WA_CONNECT_SECRET APP_PUBLIC_URL WHATSAPP_VERIFY_TOKEN || WEBHOOK_OK=$?

APP_URL="$(gcloud run services describe "${APP_SERVICE}" --project="${PROJECT}" --region="${REGION}" --format='value(status.url)' 2>/dev/null || true)"
WEBHOOK_URL="$(gcloud run services describe "${WEBHOOK_SERVICE}" --project="${PROJECT}" --region="${REGION}" --format='value(status.url)' 2>/dev/null || true)"

echo
echo "============================================================"
echo "Values to use while configuring the services"
echo "============================================================"
echo "APP_PUBLIC_URL=${APP_URL:-SERVICE_NOT_FOUND}"
echo "WEBHOOK_PUBLIC_URL=${WEBHOOK_URL:-SERVICE_NOT_FOUND}"
echo "Meta callback URL=${WEBHOOK_URL:-SERVICE_NOT_FOUND}/webhook"
echo "CRM connect endpoint=${WEBHOOK_URL:-SERVICE_NOT_FOUND}/connect/whatsapp"

echo
echo "Secret Manager names currently present (values hidden):"
gcloud secrets list --project="${PROJECT}" --format='value(name)' | sed 's/^/  - /' || true

if [[ -n "${WEBHOOK_URL}" ]]; then
  echo
  echo "Webhook health check:"
  curl -fsS "${WEBHOOK_URL}/healthz" || echo "Health request failed; inspect Cloud Run logs."
  echo
fi

if [[ "${APP_OK}" -eq 0 && "${WEBHOOK_OK}" -eq 0 ]]; then
  echo
  echo "Configuration names look complete. Reload the CRM and open WhatsApp connections."
  exit 0
fi

echo
echo "One or more required settings are missing. Follow docs/WHATSAPP_COEXISTENCE_SETUP.md."
exit 2
