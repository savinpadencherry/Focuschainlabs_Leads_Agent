"""Production entrypoint for the WhatsApp webhook Cloud Run service.

The underlying FastAPI app already verifies X-Hub-Signature-256 whenever
META_APP_SECRET is present. This wrapper adds the fail-closed production switch:
when WEBHOOK_SIGNATURE_REQUIRED=true, a missing app secret locks POST /webhook
instead of allowing unsigned traffic through.
"""

from __future__ import annotations

from fastapi import Request, Response

from utils.webhook_security import (
    webhook_signature_configured,
    webhook_signature_required,
)
from whatsapp_webhook import app


@app.middleware("http")
async def enforce_webhook_signature_configuration(request: Request, call_next):
    if (
        request.method.upper() == "POST"
        and request.url.path == "/webhook"
        and webhook_signature_required()
        and not webhook_signature_configured()
    ):
        return Response(
            status_code=503,
            content='{"error":"webhook signature verification is required but not configured"}',
            media_type="application/json",
        )
    return await call_next(request)
