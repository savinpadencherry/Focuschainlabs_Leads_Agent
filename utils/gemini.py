"""Small Gemini wrapper with model fallback for transient capacity spikes.

Everything funnels through here so the per-run budget guard (utils.budget) and
the model cascade are enforced in exactly one place. Supports plain text,
strict-JSON, and multimodal (audio) prompts — all on the same free Flash tier.
"""

from __future__ import annotations

import json
import os
import re

from google import genai

from utils import budget


def _models() -> list[str]:
    primary = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    fallbacks = ["gemini-2.0-flash", "gemini-1.5-flash"]
    ordered = [primary] + fallbacks
    return list(dict.fromkeys(m for m in ordered if m))


def _client() -> genai.Client:
    return genai.Client(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in ("503", "unavailable", "overloaded", "high demand", "temporarily")
    )


def _generate(contents) -> str:
    """Core call: budget-guarded, with model cascade on transient overload."""
    if not budget.allow("gemini"):
        raise RuntimeError("Gemini budget for this run is exhausted.")
    client = _client()
    last_exc: Exception | None = None
    for model in _models():
        try:
            response = client.models.generate_content(model=model, contents=contents)
            return response.text or ""
        except Exception as exc:  # noqa: BLE001 - we re-raise after the cascade
            last_exc = exc
            if _is_retryable(exc):
                continue
            raise
    if last_exc:
        raise last_exc
    return ""


def generate_content_text(prompt: str) -> str:
    """Return Gemini text, trying lower-demand flash models if primary is busy."""
    return _generate(prompt)


def generate_content_multimodal(prompt: str, audio_bytes: bytes, mime_type: str = "audio/wav") -> str:
    """Send a prompt plus an audio clip (e.g. a spoken CRM record) to Gemini.

    Uses the same free Flash tier and budget guard as text. Gemini transcribes
    and reasons over the audio in a single call — no separate STT service.
    """
    from google.genai import types

    audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
    return _generate([prompt, audio_part])


def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/wav") -> str:
    """Speech-to-text only — verbatim words, nothing structured or interpreted.

    Kept deliberately separate from generate_json()'s field-extraction prompt:
    the caller shows this plain transcript to the user for editing *before*
    any "agent" reasoning runs over it (one short, budget-guarded call).
    """
    prompt = (
        "Transcribe the spoken audio verbatim, word for word. "
        "Return ONLY the transcribed text — no labels, quotes, or commentary."
    )
    return generate_content_multimodal(prompt, audio_bytes, mime_type=mime_type).strip()


def _extract_json(raw: str) -> str:
    """Pull a JSON object out of a model reply that may be fenced or chatty."""
    text = (raw or "").strip()
    # Strip ```json ... ``` or ``` ... ``` fences.
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    # Fall back to the first {...} span if there's leading/trailing prose.
    if not text.startswith("{"):
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            text = brace.group(0)
    return text


def generate_json(prompt: str, audio_bytes: bytes | None = None, mime_type: str = "audio/wav") -> dict:
    """Return a parsed JSON object from Gemini, with audio optional.

    Returns {} if the model produces nothing parseable, so callers can degrade
    gracefully rather than crash.
    """
    if audio_bytes is not None:
        raw = generate_content_multimodal(prompt, audio_bytes, mime_type=mime_type)
    else:
        raw = generate_content_text(prompt)
    if not raw:
        return {}
    try:
        return json.loads(_extract_json(raw))
    except (json.JSONDecodeError, ValueError):
        return {}
