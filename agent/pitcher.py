import os

from google import genai
from google.genai import types

from utils.rate_limiter import gemini_limiter


PITCH_PROMPT = """
You are a senior consultant at Focus Chain Labs, a digital transformation
consulting firm in Bangalore. You are writing the first line of a cold
outreach message to a decision maker at a potential client company.

Rules:
- Write exactly 1 to 2 sentences maximum
- Reference something SPECIFIC and RECENT about their company
- Do NOT use the words "digital transformation" — too generic
- Do NOT sound like a sales pitch or template
- Write peer-to-peer — you are a senior professional talking to another
- Make them curious enough to reply — do not ask for a meeting in this line
- Sound like a human who actually read about their company this morning

Contact: {contact_name}, {contact_title} at {company_name}
Primary signal: {primary_signal}
Pain point: {pain_point}
Recent news: {recent_news}
Our firm: Focus Chain Labs — we help mid-market companies modernise
operations using AI and cloud infrastructure

Return only the opening line. No quotes. No subject line. No explanation.
"""


def generate_pitch(lead: dict) -> str:
    gemini_limiter.wait()
    recent_news = " | ".join(
        n.get("title", "") for n in lead.get("recent_news", [])[:2]
    )

    prompt = PITCH_PROMPT.format(
        contact_name=lead.get("contact_name", "there"),
        contact_title=lead.get("contact_title", ""),
        company_name=lead.get("company_name", ""),
        primary_signal=lead.get("primary_signal", ""),
        pain_point=lead.get("pain_point", ""),
        recent_news=recent_news or lead.get("raw_snippet", "")
    )

    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                    thinking_level="medium"
                )
            )
        )
        return response.text.strip().strip('"')

    except Exception as e:
        print(f"  [ERROR] Pitch generation failed: {e}")
        return f"Reach out referencing their recent activity: {lead.get('primary_signal', '')}"
