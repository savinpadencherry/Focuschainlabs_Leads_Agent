"""
Two Gemini-powered outputs per lead:
  1. opening_line    — 1-2 sentence peer-to-peer opener referencing real, recent activity.
  2. outreach_note   — Private 4-point call strategy note for the human rep.
"""

import os

from google import genai

from utils.rate_limiter import gemini_limiter


# ── Opening line ──────────────────────────────────────────────────────────────

PITCH_PROMPT = """
You are writing the first line of a cold outreach message to a decision
maker at a potential client company. You are NOT a salesperson — you are
a senior operator who actually read about their company this morning.

Rules:
- Exactly 1 to 2 sentences. No more.
- Reference something SPECIFIC and RECENT — a hire, a launch, a post,
  a funding round, a job opening, a quote.
- If they posted recently on LinkedIn, react to that post — not the company brochure.
- Do not say "digital transformation", "synergy", "leverage", or "circle back".
- Peer-to-peer tone. Do not ask for a meeting — make them curious enough to reply.

Contact:        {contact_name}, {contact_title} at {company_name}
Primary signal: {primary_signal}
Pain point:     {pain_point}
Recent news:    {recent_news}
Roles hiring:   {job_postings}
Their LinkedIn posts (most recent first):
{contact_posts}
Their company's LinkedIn chatter:
{linkedin_posts}
Their Reddit mentions:
{reddit_signals}
Our offering: {offering}

Return ONLY the opening line. No quotes. No subject line. No explanation.
"""


def generate_pitch(lead: dict) -> str:
    gemini_limiter.wait()

    def _join(items, n=2):
        return " | ".join(str(x) for x in items[:n] if x) or "(none)"

    prompt = PITCH_PROMPT.format(
        contact_name=lead.get("contact_name") or "there",
        contact_title=lead.get("contact_title", ""),
        company_name=lead.get("company_name", ""),
        primary_signal=lead.get("primary_signal", ""),
        pain_point=lead.get("pain_point", ""),
        recent_news=_join([n.get("title", "") for n in lead.get("recent_news", [])]),
        job_postings=_join([
            f"{j.get('role', '')}: {j.get('observation', '')}"
            for j in lead.get("job_postings", [])
        ]),
        contact_posts=_join(lead.get("contact_posts", [])),
        linkedin_posts=_join(lead.get("linkedin_posts", [])),
        reddit_signals=_join(lead.get("reddit_signals", [])),
        offering=lead.get("gap_hypothesis") or lead.get("custom_focus")
                  or lead.get("vertical", "B2B consulting"),
    )

    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt,
        )
        return response.text.strip().strip('"')

    except Exception as e:
        print(f"  [ERROR] Pitch generation failed: {e}")
        return f"Reach out referencing their recent activity: {lead.get('primary_signal', '')}"


# ── Outreach strategy note ────────────────────────────────────────────────────

OUTREACH_NOTE_PROMPT = """
You are briefing a human sales rep before their first call with a prospect.
This is a PRIVATE tactical note — not a pitch, not a message to send.

Write exactly 4 numbered points. Each point is 1-2 sentences max.

1. LEAD WITH: The single most specific insight or signal to open the conversation with.
   Cite what was actually found — a real ad, a real job post, a real news item.
   Do not be generic.

2. AVOID: One thing to NOT say or pitch first. Name the specific mistake
   a bad rep would make with this prospect.

3. ANGLE: The business pain angle most likely to make this person lean forward.
   Phrase it the way they would say it to themselves, not the way we would pitch it.

4. CONTACT NOTE: Nuance about who to call and why. If we have a named contact,
   comment on their role and likely priorities. If not, suggest who to ask for and why.

Company:        {company_name}
Contact:        {contact_name}, {contact_title}
Primary signal: {primary_signal}
Pain point:     {pain_point}
Ad activity:    {ad_activity}
Evidence:
{evidence_block}
Our offering:   {offering}
Score note:     {score_reasoning}

Return only the 4 numbered points. No headers. No preamble. No sign-off.
"""


def generate_outreach_note(lead: dict) -> str:
    gemini_limiter.wait()

    evidence = lead.get("evidence", [])
    evidence_block = "\n".join(
        f"  [{e['category'].upper()}] {e['observation'][:120]}"
        + (f" — {e['url']}" if e.get("url") else "")
        for e in evidence[:5]
    ) or "  (no evidence collected)"

    ad_signals = lead.get("ad_signals", [])
    ad_activity = " | ".join(ad_signals[:3]) if ad_signals else "None detected"

    prompt = OUTREACH_NOTE_PROMPT.format(
        company_name=lead.get("company_name", ""),
        contact_name=lead.get("contact_name") or "unknown",
        contact_title=lead.get("contact_title", ""),
        primary_signal=lead.get("primary_signal", ""),
        pain_point=lead.get("pain_point", ""),
        ad_activity=ad_activity,
        evidence_block=evidence_block,
        offering=lead.get("gap_hypothesis") or lead.get("custom_focus")
                  or lead.get("vertical", "B2B consulting"),
        score_reasoning=lead.get("score_reasoning", ""),
    )

    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt,
        )
        return response.text.strip()

    except Exception as e:
        print(f"  [ERROR] Outreach note generation failed: {e}")
        signal = lead.get("primary_signal", "recent company activity")
        pain   = lead.get("pain_point", "")
        return (
            f"1. LEAD WITH: Reference {signal}.\n"
            f"2. AVOID: Generic software pitch.\n"
            f"3. ANGLE: {pain or 'Explore their operational bottlenecks.'}\n"
            f"4. CONTACT NOTE: Ask for the decision maker by title if contact unknown."
        )
