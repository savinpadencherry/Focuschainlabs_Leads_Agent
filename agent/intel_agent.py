"""
Intel Agent — pipeline company news & signal monitor.

Cost per 10-company run:
  • 1 Serper /news call per company  (free 100/day quota)
  • 1 Gemini Flash call per company  (~$0.0004 total for 10)
  • Freshness cache skips companies checked within FRESH_HOURS
  • Hard cap: MAX_PER_RUN companies per run

Yields event dicts for streaming to the Intel UI.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Generator

import requests

from utils.llm import generate_content_text
from utils.rate_limiter import serper_limiter


_NEWS_URL   = "https://google.serper.dev/news"
FRESH_HOURS = 12
MAX_PER_RUN = 15


SIGNAL_META: dict[str, dict] = {
    "funding":     {"icon": "💰", "label": "Funding",     "color": "#1a6b3c", "bg": "rgba(26,107,60,.13)"},
    "expansion":   {"icon": "📈", "label": "Expansion",   "color": "#1a3a6b", "bg": "rgba(26,58,107,.13)"},
    "leadership":  {"icon": "👤", "label": "Leadership",  "color": "#5a2d82", "bg": "rgba(90,45,130,.13)"},
    "product":     {"icon": "🚀", "label": "Product",     "color": "#B7791F", "bg": "rgba(183,121,31,.13)"},
    "partnership": {"icon": "🤝", "label": "Partnership", "color": "#1a6b6b", "bg": "rgba(26,107,107,.13)"},
    "award":       {"icon": "🏆", "label": "Award",       "color": "#8b7a00", "bg": "rgba(139,122,0,.13)"},
    "pain":        {"icon": "⚠️",  "label": "Pain Signal", "color": "#A93D3D", "bg": "rgba(169,61,61,.13)"},
    "other":       {"icon": "📰", "label": "News",        "color": "#6B7F85", "bg": "rgba(107,127,133,.13)"},
}

TIMING_META: dict[str, dict] = {
    "immediate": {"label": "Reach out now",  "color": "#1a6b3c", "bg": "rgba(26,107,60,.12)"},
    "good":      {"label": "Good timing",    "color": "#B7791F", "bg": "rgba(183,121,31,.12)"},
    "wait":      {"label": "Wait & monitor", "color": "#6B7F85", "bg": "rgba(107,127,133,.12)"},
    "skip":      {"label": "Skip for now",   "color": "#A93D3D", "bg": "rgba(169,61,61,.12)"},
}


_ANALYZE_PROMPT = """\
You are a B2B sales intelligence analyst. Analyze recent news about "{company}" and extract signals useful for sales outreach.

SEARCH RESULTS:
{results_text}

CONTACT: {contact_name} ({contact_title}) — {industry}
OUR OFFERING: {offering}

Identify every significant signal. Signal types:
  funding     — raised capital, new investors, IPO, valuation news
  expansion   — new markets, locations, headcount growth, new offices
  leadership  — new C-suite, key hire, departure, restructure
  product     — new product, feature launch, rebranding
  partnership — joint venture, integration, deal signed
  award       — industry recognition, ranking, certification
  pain        — layoffs, restructuring, challenges, complaints, negative press
  other       — any other significant news

Return ONLY valid JSON, no markdown fences, no explanation:
{{
  "signals": [
    {{
      "type": "funding|expansion|leadership|product|partnership|award|pain|other",
      "headline": "One-sentence description of what happened",
      "detail": "1-2 sentences of context",
      "relevance": "Why this matters for our outreach specifically",
      "url": "source URL or empty string"
    }}
  ],
  "summary": "2-sentence overview of company's current business situation and momentum",
  "opener": "Specific 1-sentence opening line for cold outreach referencing a real signal (avoid clichés like 'I noticed...' or 'Congrats on...')",
  "outreach_timing": "immediate|good|wait|skip",
  "timing_reason": "One sentence explaining the timing recommendation"
}}

If no meaningful signals found: {{"signals":[],"summary":"No recent news found.","opener":"","outreach_timing":"wait","timing_reason":"No fresh signals to anchor outreach."}}
"""


def run_intel(
    companies: list[dict],
    *,
    existing_briefings: list[dict] | None = None,
    freshness_hours: int = FRESH_HOURS,
    offering: str = "",
) -> Generator[dict[str, Any], None, None]:
    """
    Monitor companies for news signals. Yields event dicts for streaming to UI.

    Each company dict must include: name, website (optional), industry (optional),
    contact_id (optional), contact_name (optional), contact_title (optional).
    """
    companies = companies[:MAX_PER_RUN]
    total      = len(companies)
    existing   = existing_briefings or []
    new_briefs: list[dict] = []
    total_sigs  = 0
    serper_used = 0

    yield {"type": "start", "total": total, "companies": [c.get("name", "") for c in companies]}

    for idx, co in enumerate(companies, 1):
        name = (co.get("name") or "").strip()
        if not name:
            continue

        yield {"type": "checking", "company": name, "idx": idx, "total": total}

        # ── Freshness check — skip if recently fetched ────────────────────────
        cached = _find_cached(name, existing, freshness_hours)
        if cached:
            age = _age_hours(cached.get("ran_at", ""))
            yield {"type": "cached", "company": name, "briefing": cached,
                   "age_hrs": round(age, 1)}
            new_briefs.append(cached)
            total_sigs += len(cached.get("signals", []))
            continue

        if not os.getenv("SERPER_API_KEY"):
            yield {"type": "error", "company": name,
                   "error": "SERPER_API_KEY not configured in secrets"}
            continue

        # ── Serper news search — 1 call per company ───────────────────────────
        yield {"type": "searching", "company": name}
        try:
            serper_limiter.wait()
            news = _search_news(name)
            serper_used += 1
        except Exception as exc:
            msg = str(exc)
            if "429" in msg or "quota" in msg.lower():
                yield {"type": "rate_limit", "company": name,
                       "error": "Serper daily quota reached — run paused"}
                break
            yield {"type": "error", "company": name, "error": f"Search error: {msg[:120]}"}
            continue

        if not news:
            yield {"type": "no_news", "company": name}
            empty = _make_briefing(co, [], "No recent news found.", "",
                                   "wait", "No signals to anchor outreach.", [])
            new_briefs.append(empty)
            continue

        yield {
            "type":      "found",
            "company":   name,
            "count":     len(news),
            "headlines": [n.get("title", "")[:90] for n in news[:3]],
        }

        from utils.llm import llm_configured
        if not llm_configured():
            yield {"type": "error", "company": name,
                   "error": "No LLM key configured in secrets (DEEPSEEK_API_KEY or GEMINI_API_KEY)"}
            continue

        # ── Gemini Flash analysis — 1 call per company ───────────────────────
        yield {"type": "analyzing", "company": name}
        try:
            analysis = _analyze(co, news, offering=offering)
        except Exception as exc:
            yield {"type": "error", "company": name, "error": f"Analysis error: {str(exc)[:120]}"}
            continue

        signals = analysis.get("signals") or []
        total_sigs += len(signals)

        briefing = _make_briefing(
            co, signals,
            analysis.get("summary", ""),
            analysis.get("opener", ""),
            analysis.get("outreach_timing", "wait"),
            analysis.get("timing_reason", ""),
            [n.get("link", "") for n in news[:5]],
        )
        new_briefs.append(briefing)

        yield {
            "type":         "briefing",
            "company":      name,
            "briefing":     briefing,
            "signal_count": len(signals),
        }

    yield {
        "type":             "done",
        "total_companies":  total,
        "total_signals":    total_sigs,
        "serper_calls":     serper_used,
        "briefings":        new_briefs,
    }


# ── Search ────────────────────────────────────────────────────────────────────

def _search_news(company: str, num: int = 8) -> list[dict]:
    """One Serper /news call. Returns normalised news items."""
    api_key = os.getenv("SERPER_API_KEY", "")
    # Broad signal query — catches most interesting events in one call
    query = (
        f'"{company}" '
        f'(funding OR raised OR expansion OR "new office" OR partnership '
        f'OR leadership OR appointed OR award OR "product launch" OR layoffs)'
    )
    resp = requests.post(
        _NEWS_URL,
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json={"q": query, "num": num, "gl": "in", "hl": "en"},
        timeout=12,
    )
    if resp.status_code == 429:
        raise Exception("429 — Serper news quota reached")
    resp.raise_for_status()

    return [
        {
            "title":   r.get("title", ""),
            "snippet": r.get("snippet", ""),
            "link":    r.get("link", ""),
            "date":    r.get("date", ""),
            "source":  r.get("source", ""),
        }
        for r in (resp.json() or {}).get("news", [])
        if r.get("title")
    ]


# ── Analysis ──────────────────────────────────────────────────────────────────

def _analyze(co: dict, news: list[dict], offering: str = "") -> dict:
    results_text = "\n\n".join(
        f"[{i+1}] {n.get('source','')} ({n.get('date','')})\n"
        f"Title:   {n.get('title','')}\n"
        f"Snippet: {n.get('snippet','')}\n"
        f"URL:     {n.get('link','')}"
        for i, n in enumerate(news[:6])
    )
    prompt = _ANALYZE_PROMPT.format(
        company       = co.get("name", "the company"),
        results_text  = results_text,
        contact_name  = co.get("contact_name", "the decision maker"),
        contact_title = co.get("contact_title", ""),
        industry      = co.get("industry", ""),
        offering      = offering or "B2B automation and AI agent services",
    )
    raw = generate_content_text(prompt)
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    raw = re.sub(r"\s*```\s*$", "", raw.strip(), flags=re.MULTILINE)
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        return _parse_fallback(raw)


def _parse_fallback(raw: str) -> dict:
    result: dict[str, Any] = {"signals": []}
    for key in ("summary", "opener", "outreach_timing", "timing_reason"):
        m = re.search(rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"', raw, re.DOTALL)
        if m:
            result[key] = m.group(1).replace("\\n", "\n").replace('\\"', '"')
    return result


# ── Storage helpers ───────────────────────────────────────────────────────────

def _make_briefing(
    co: dict,
    signals: list,
    summary: str,
    opener: str,
    timing: str,
    timing_reason: str,
    sources: list,
) -> dict[str, Any]:
    return {
        "id":              str(uuid.uuid4()),
        "company":         co.get("name", ""),
        "contact_id":      co.get("contact_id", ""),
        "contact_name":    co.get("contact_name", ""),
        "contact_title":   co.get("contact_title", ""),
        "industry":        co.get("industry", ""),
        "ran_at":          _utc_now(),
        "signals":         signals,
        "summary":         summary,
        "opener":          opener,
        "outreach_timing": timing if timing in TIMING_META else "wait",
        "timing_reason":   timing_reason,
        "sources":         [u for u in sources if u],
        "pushed_to_crm":   False,
    }


def _find_cached(name: str, existing: list[dict], max_age_hrs: int) -> dict | None:
    matches = [b for b in existing if (b.get("company") or "").lower() == name.lower()]
    if not matches:
        return None
    latest = max(matches, key=lambda b: b.get("ran_at", ""))
    return latest if _age_hours(latest.get("ran_at", "")) < max_age_hrs else None


def _age_hours(ts: str) -> float:
    if not ts:
        return 9999.0
    try:
        dt  = datetime.fromisoformat(ts)
        now = datetime.now(timezone.utc)
        dt  = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        return (now - dt).total_seconds() / 3600
    except Exception:
        return 9999.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
