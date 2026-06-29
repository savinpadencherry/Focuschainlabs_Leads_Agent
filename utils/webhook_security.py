"""Production switches for the public WhatsApp webhook."""

from __future__ import annotations

import os


def webhook_signature_required() -> bool:
    """Whether unsigned webhook traffic must be rejected fail-closed."""
    return (os.getenv("WEBHOOK_SIGNATURE_REQUIRED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def webhook_signature_configured() -> bool:
    """Whether the Meta app secret needed for signature verification is present."""
    return bool((os.getenv("META_APP_SECRET") or "").strip())
