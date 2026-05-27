"""
Personalised opening-line generator.
Threads company signal + contact's own recent posts into a peer-to-peer line.
"""

import os

from google import genai

from utils.rate_limiter import gemini_limiter


PITCH_PROMPT = """
You are writing the first line of a cold outreach message to a decision
maker at a potential client company. You are NOT a salesperson — you are
a senior operator who actually read about their company this morning.

Rules:
- Exactly 1 to 2 sentences. No more.
- Reference something SPECIFIC and RECENT — a hire, a launch, a post,
  a funding round, a job opening, a quote.
- If they posted recently on LinkedIn, react to that post — not the
  company brochure.
- Do not say "digital transformation", "synergy", "leverage", or "circle back".
- Peer-to-peer tone. Do not ask for a meeting in this line — make them
  curious enough to reply.

Contact:        {contact_name}, {contact_title} at {company_name}
Primary signal: {primary_signal}
Pain point:     {pain_point}
Recent news:    {recent_news}
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
        contact_posts=_join(lead.get("contact_posts", [])),
        linkedin_posts=_join(lead.get("linkedin_posts", [])),
        reddit_signals=_join(lead.get("reddit_signals", [])),
        offering=lead.get("gap_hypothesis") or lead.get("custom_focus")
                  or lead.get("vertical", "B2B consulting"),
    )

    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        return response.text.strip().strip('"')

    except Exception as e:
        print(f"  [ERROR] Pitch generation failed: {e}")
        return f"Reach out referencing their recent activity: {lead.get('primary_signal', '')}"
