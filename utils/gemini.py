"""Small Gemini wrapper with model fallback for transient capacity spikes."""

from __future__ import annotations

import os
from google import genai

from utils import budget


def _models() -> list[str]:
    primary = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    fallbacks = ["gemini-2.0-flash", "gemini-1.5-flash"]
    ordered = [primary] + fallbacks
    return list(dict.fromkeys(m for m in ordered if m))


def generate_content_text(prompt: str) -> str:
    """Return Gemini text, trying lower-demand flash models if primary is busy."""
    if not budget.allow("gemini"):
        raise RuntimeError(
            "Per-run AI call budget reached (GEMINI_BUDGET). "
            "Start a new run or raise the GEMINI_BUDGET cap to continue."
        )
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    last_exc = None
    for model in _models():
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            return response.text or ""
        except Exception as exc:
            last_exc = exc
            msg = str(exc).lower()
            retryable = any(
                token in msg
                for token in ("503", "unavailable", "overloaded", "high demand", "temporarily")
            )
            if retryable:
                continue
            raise
    if last_exc:
        raise last_exc
    return ""
