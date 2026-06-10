"""
Per-run API budget guard — a hard ceiling on outbound paid API calls.

RateLimiter (utils/rate_limiter.py) throttles *how fast* we call an API.
This module caps *how many* calls a single run may make, so a run can never
blow through a free-tier quota or run up a surprise bill — even if a loop
misbehaves or an LLM prompt fans out unexpectedly.

Design
------
  • Process-global counters, guarded by a lock (safe across Streamlit reruns).
  • Caps are env-overridable: SERPER_BUDGET, LLM_BUDGET, HUNTER_BUDGET, …
  • reset() is called at the start of every agent run.
  • allow(service) reserves one unit and returns False once the cap is hit.
    Callers degrade gracefully (return empty / fall back) rather than
    overspending — the run still finishes with whatever it gathered.

Defaults are tuned so a full, high-quality Scout run stays inside Serper's
free credits. Because enrichment runs last in the pipeline, it is the first
thing to degrade when the ceiling is reached — research and scoring signal
(the parts that matter most) are protected.
"""

from __future__ import annotations

import os
import threading

_LOCK = threading.Lock()


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _read_caps() -> dict[str, int]:
    # A full-quality Scout run uses ~160 Serper calls (discovery + research +
    # enrichment). The 200 ceiling lets that complete while making a runaway
    # (loop / unexpected fan-out) impossible. Lower SERPER_BUDGET to force a
    # tighter, cheaper run — enrichment degrades first, research is protected.
    return {
        "serper": _env_int("SERPER_BUDGET", 200),
        # "llm" covers every FocusChain LLM call regardless of engine.
        # LLM_BUDGET wins; GEMINI_BUDGET is honoured for older deployments.
        "llm": _env_int("LLM_BUDGET", _env_int("GEMINI_BUDGET", 80)),
        "hunter": _env_int("HUNTER_BUDGET", 20),
        "apollo": _env_int("APOLLO_BUDGET", 40),
        "apify":  _env_int("APIFY_BUDGET", 25),
    }


_FALLBACK_CAP = 10_000
_counts: dict[str, int] = {}
_caps: dict[str, int] = _read_caps()


def reset() -> None:
    """Zero all counters and re-read caps from env. Call once per run."""
    global _caps
    with _LOCK:
        _counts.clear()
        _caps = _read_caps()


def cap(service: str) -> int:
    with _LOCK:
        return _caps.get(service, _FALLBACK_CAP)


def allow(service: str, n: int = 1) -> bool:
    """
    Reserve `n` calls for `service`. Returns True (and increments the counter)
    when within budget, or False when the per-run ceiling would be exceeded.
    A False return means: do NOT make the call.
    """
    with _LOCK:
        limit = _caps.get(service, _FALLBACK_CAP)
        current = _counts.get(service, 0)
        if current + n > limit:
            return False
        _counts[service] = current + n
        return True


def used(service: str | None = None):
    """Calls consumed so far — a single int, or the whole dict if no service."""
    with _LOCK:
        if service is None:
            return dict(_counts)
        return _counts.get(service, 0)


def remaining(service: str) -> int:
    with _LOCK:
        return max(0, _caps.get(service, _FALLBACK_CAP) - _counts.get(service, 0))


def snapshot() -> dict[str, dict[str, int]]:
    """Full usage + caps for UI display: {service: {used, cap, remaining}}."""
    with _LOCK:
        return {
            svc: {
                "used": _counts.get(svc, 0),
                "cap": limit,
                "remaining": max(0, limit - _counts.get(svc, 0)),
            }
            for svc, limit in _caps.items()
        }
