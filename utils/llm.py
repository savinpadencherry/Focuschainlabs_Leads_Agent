"""FocusChain LLM — the single language-model layer for every agent.

All agents call this module; none of them know (or show) which provider is
underneath. The provider chain is:

  1. Primary engine — DeepSeek's OpenAI-compatible API (deepseek-chat), used
     whenever DEEPSEEK_API_KEY is set. Strong reasoning at very low cost.
  2. Fallback engine — Gemini Flash (existing GEMINI_API_KEY), used when the
     primary key is absent or a call fails. Keeps the app alive on the free
     tier with zero behaviour change.

Everything funnels through _generate() so the per-run budget guard
(utils.budget, service "llm") is enforced in exactly one place. Speech-to-text
is handled by the device keyboard/OS dictation, never the LLM.
"""

from __future__ import annotations

import json
import os
import re

import requests

from utils import budget

_DEEPSEEK_URL = (os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/") + "/chat/completions"


def _deepseek_key() -> str:
    # FOCUSCHAIN_LLM_KEY is the white-label alias used in client-facing docs.
    return (os.getenv("DEEPSEEK_API_KEY") or os.getenv("FOCUSCHAIN_LLM_KEY") or "").strip()


def _deepseek_model() -> str:
    return (os.getenv("DEEPSEEK_MODEL") or "deepseek-chat").strip()


def _gemini_key() -> str:
    return (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()


def engine_label() -> str:
    """White-label engine name for UI display."""
    return "FocusChain LLM"


def llm_configured() -> bool:
    """True when at least one engine has a key."""
    return bool(_deepseek_key() or _gemini_key())


def _call_deepseek(prompt: str) -> str:
    resp = requests.post(
        _DEEPSEEK_URL,
        headers={
            "Authorization": f"Bearer {_deepseek_key()}",
            "Content-Type": "application/json",
        },
        json={
            "model": _deepseek_model(),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": float(os.getenv("LLM_TEMPERATURE", "0.4")),
            "stream": False,
        },
        timeout=90,
    )
    resp.raise_for_status()
    body = resp.json()
    return ((body.get("choices") or [{}])[0].get("message") or {}).get("content") or ""


# Supported Gemini models only — legacy names (2.0-flash, 1.5-flash…) remap.
_GEMINI_SUPPORTED = ("gemini-2.5-flash", "gemini-2.5-flash-lite")
_GEMINI_LEGACY = {
    "gemini-2.0-flash": "gemini-2.5-flash",
    "gemini-2.0-flash-exp": "gemini-2.5-flash",
    "gemini-1.5-flash": "gemini-2.5-flash",
    "gemini-1.5-flash-latest": "gemini-2.5-flash",
    "gemini-1.5-pro": "gemini-2.5-flash",
    "gemini-pro": "gemini-2.5-flash",
}


def _normalize_gemini_model(name: str) -> str:
    cleaned = (name or "").strip().lower()
    if cleaned in _GEMINI_LEGACY:
        return _GEMINI_LEGACY[cleaned]
    if cleaned in _GEMINI_SUPPORTED:
        return cleaned
    # Unknown/empty model id — default to current flash rather than failing.
    return "gemini-2.5-flash"


def _gemini_models() -> list[str]:
    primary = _normalize_gemini_model(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    ordered = [primary] + [m for m in _GEMINI_SUPPORTED if m != primary]
    return list(dict.fromkeys(ordered))


def _gemini_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in ("503", "unavailable", "overloaded", "high demand", "temporarily")
    )


def _call_gemini(prompt: str) -> str:
    from google import genai

    client = genai.Client(api_key=_gemini_key())
    last_exc: Exception | None = None
    for model in _gemini_models():
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            return response.text or ""
        except Exception as exc:  # noqa: BLE001 - cascade, then re-raise
            last_exc = exc
            if _gemini_retryable(exc):
                continue
            raise
    if last_exc:
        raise last_exc
    return ""


def _generate(prompt: str) -> str:
    """Core call: budget-guarded, primary engine with automatic fallback."""
    if not budget.allow("llm"):
        raise RuntimeError("FocusChain LLM budget for this run is exhausted.")

    primary_exc: Exception | None = None
    if _deepseek_key():
        try:
            return _call_deepseek(prompt)
        except Exception as exc:  # noqa: BLE001 - fall back to the second engine
            primary_exc = exc

    if _gemini_key():
        try:
            return _call_gemini(prompt)
        except Exception as exc:  # noqa: BLE001
            raise primary_exc or exc

    if primary_exc:
        raise primary_exc
    raise RuntimeError(
        "No LLM configured — set DEEPSEEK_API_KEY (or GEMINI_API_KEY as fallback) in secrets."
    )


def generate_content_text(prompt: str) -> str:
    """Return LLM text for a prompt — the one entry point every agent uses."""
    return _generate(prompt)


def _extract_json(raw: str) -> str:
    """Pull a JSON object out of a model reply that may be fenced or chatty."""
    text = (raw or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    if not text.startswith("{"):
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            text = brace.group(0)
    return text


def generate_json(prompt: str) -> dict:
    """Return a parsed JSON object from the LLM.

    Returns {} if the model produces nothing parseable, so callers can degrade
    gracefully rather than crash.
    """
    raw = generate_content_text(prompt)
    if not raw:
        return {}
    try:
        return json.loads(_extract_json(raw))
    except (json.JSONDecodeError, ValueError):
        return {}
