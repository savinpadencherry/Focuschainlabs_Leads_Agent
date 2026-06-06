"""
Gemini pitch bundle — ONE call per lead, three outputs:
  opening_line     — 1-2 sentence peer-to-peer opener.
  outreach_note    — Private 4-point call strategy for the human rep.
  reason_to_reach  — Single sentence: why THIS person, THIS week.

Single-call design keeps Gemini usage to 1 call/lead instead of 3,
cutting daily quota consumption by ~60%.
"""

import os
import json
import re

from utils.rate_limiter import gemini_limiter
from utils.exceptions import RateLimitError
from utils.gemini import generate_content_text


PITCH_BUNDLE_PROMPT = """
You are briefing a human sales rep. Return ONLY valid JSON — no markdown, no prose.

Generate three outputs for this lead:

1. opening_line
   - Exactly 1-2 sentences. Peer-to-peer tone.
   - Reference something SPECIFIC and RECENT about the company or contact.
   - Do NOT use "digital transformation", "synergy", "leverage", "circle back".
   - Do NOT ask for a meeting — make them curious enough to reply.

2. outreach_note  (PRIVATE — not sent to prospect)
   - Exactly 4 numbered points, each 1-2 sentences:
     1. LEAD WITH: Most specific insight to open the conversation. Cite a real signal.
     2. AVOID: One thing NOT to say or pitch first. Name the specific mistake.
     3. ANGLE: The business pain phrased the way THEY would say it to themselves.
     4. CONTACT NOTE: Who to call, why this person, what their likely priorities are.

3. reason_to_reach  (one sentence, max 30 words)
   - Why message THIS specific contact THIS week.
   - Anchor to: their name + title + the trigger event + why it's urgent now.
   - Example: "Reach Priya Sharma (CHRO) this week — Cadabams just announced
     a 200-bed expansion and her HR ops will need elder-care benefits before
     the onboarding wave hits."

---
Contact:        {contact_name}, {contact_title} at {company_name}
Primary signal: {primary_signal}
Pain point:     {pain_point}
Score note:     {score_reasoning}
Trigger timing: {trigger_recency}
Ad activity:    {ad_activity}
Evidence:
{evidence_block}
Our offering:   {offering}

Return ONLY this JSON and nothing else:
{{
  "opening_line":    "<1-2 sentences>",
  "outreach_note":   "1. LEAD WITH: ...\\n2. AVOID: ...\\n3. ANGLE: ...\\n4. CONTACT NOTE: ...",
  "reason_to_reach": "<one sentence>"
}}
"""


def generate_pitch_bundle(lead: dict) -> dict:
    """
    Single Gemini call that returns opening_line, outreach_note, reason_to_reach.
    Falls back to safe defaults on any error.
    """
    gemini_limiter.wait()

    recency_score = lead.get("intent_recency_score", 0) or 0
    recency_label = (
        "within last 30 days"  if recency_score >= 18 else
        "within last 90 days"  if recency_score >= 12 else
        "within last 6 months" if recency_score >= 6  else
        "older signal"
    )

    evidence = lead.get("evidence", [])
    evidence_block = "\n".join(
        f"  [{e['category'].upper()}] {e['observation'][:120]}"
        + (f" — {e['url']}" if e.get("url") else "")
        for e in evidence[:5]
    ) or "  (no evidence collected)"

    ad_signals  = lead.get("ad_signals", []) or []
    ad_activity = " | ".join(ad_signals[:3]) if ad_signals else "None detected"

    contact_name = lead.get("contact_name") or "the decision maker"
    contact_title = lead.get("contact_title", "")

    prompt = PITCH_BUNDLE_PROMPT.format(
        contact_name   = contact_name,
        contact_title  = contact_title,
        company_name   = lead.get("company_name", ""),
        primary_signal = lead.get("primary_signal", ""),
        pain_point     = lead.get("pain_point", ""),
        score_reasoning= lead.get("score_reasoning", ""),
        trigger_recency= recency_label,
        ad_activity    = ad_activity,
        evidence_block = evidence_block,
        offering       = (lead.get("offering") or lead.get("gap_hypothesis")
                          or lead.get("custom_focus") or lead.get("vertical", "")),
    )

    try:
        raw  = re.sub(r"```json|```", "", generate_content_text(prompt).strip()).strip()
        data = json.loads(raw)
        return {
            "opening_line":    str(data.get("opening_line",    "")).strip().strip('"'),
            "outreach_note":   str(data.get("outreach_note",   "")).strip(),
            "reason_to_reach": str(data.get("reason_to_reach", "")).strip().strip('"'),
        }

    except json.JSONDecodeError:
        # Gemini returned text but not valid JSON — extract what we can
        return _fallback_bundle(lead)

    except Exception as e:
        _raise_if_rate_limit("gemini", e)
        print(f"  [ERROR] Pitch bundle failed for {lead.get('company_name', '')}: {e}")
        return _fallback_bundle(lead)


def _fallback_bundle(lead: dict, hint: str = "") -> dict:
    signal  = lead.get("primary_signal", "their recent activity")
    pain    = lead.get("pain_point", "operational bottlenecks")
    name    = lead.get("contact_name") or "the decision maker"
    title   = lead.get("contact_title", "")
    company = lead.get("company_name", "")

    opening = f"Saw {company}'s recent activity around {signal} — wanted to reach out directly."
    note    = (
        f"1. LEAD WITH: Reference {signal}.\n"
        f"2. AVOID: Generic or irrelevant pitch not tied to their specific context.\n"
        f"3. ANGLE: {pain}\n"
        f"4. CONTACT NOTE: Ask for {title or 'the decision maker'} if contact unclear."
    )
    reason = f"Reach {name}{' (' + title + ')' if title else ''} — {signal}."

    return {
        "opening_line":    opening,
        "outreach_note":   note,
        "reason_to_reach": reason,
    }


# Keep legacy function names so nothing else breaks
def generate_pitch(lead: dict) -> str:
    return generate_pitch_bundle(lead).get("opening_line", "")


def generate_outreach_note(lead: dict) -> str:
    return generate_pitch_bundle(lead).get("outreach_note", "")


def generate_reason_to_reach(lead: dict) -> str:
    return generate_pitch_bundle(lead).get("reason_to_reach", "")


def _raise_if_rate_limit(service: str, exc: Exception) -> None:
    msg = str(exc).lower()
    if any(k in msg for k in ("429", "resource_exhausted", "quota", "rate limit", "ratelimit")):
        raise RateLimitError(service, str(exc))
