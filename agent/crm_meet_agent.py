"""Conversational Google Meet prep — short chat openers from CRM context."""

from __future__ import annotations

import os

from utils.gemini import generate_json


def build_google_calendar_url(
    *,
    title: str,
    start_date: str,
    start_time: str,
    duration_minutes: int = 30,
    details: str = "",
    meet_link: str = "",
) -> str:
    """Return a Google Calendar event template URL (no OAuth required)."""
    from urllib.parse import quote

    date_part = start_date.replace("-", "")
    time_part = start_time.replace(":", "")[:4].ljust(4, "0")
    start = f"{date_part}T{time_part}00"
    end_h = int(time_part[:2])
    end_m = int(time_part[2:4]) + duration_minutes
    end_h += end_m // 60
    end_m = end_m % 60
    end = f"{date_part}T{end_h:02d}{end_m:02d}00"

    body = details.strip()
    if meet_link:
        body = f"{body}\n\nJoin Google Meet: {meet_link}".strip()

    params = {
        "action": "TEMPLATE",
        "text": title or "CRM meeting",
        "dates": f"{start}/{end}",
        "details": body,
    }
    if meet_link:
        params["location"] = meet_link
    query = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    return f"https://calendar.google.com/calendar/render?{query}"


def generate_meet_chat_prompts(
    contact: dict,
    *,
    meeting_subject: str = "",
    meeting_notes: str = "",
) -> dict:
    """
    Generate conversational Google Meet chat messages from CRM + meeting context.
    Returns {opener, visit_questions[], follow_up, calendar_summary}.
    """
    name = (contact.get("name") or "").strip()
    company = (contact.get("company") or "").strip()
    stage = (contact.get("status") or "new").strip()
    notes = (contact.get("notes") or "").strip()[:400]
    subject = (meeting_subject or "").strip()
    meet_notes = (meeting_notes or "").strip()[:400]

    fallback = {
        "opener": (
            f"Hi{' ' + name.split()[0] if name else ''} — thanks for joining. "
            "I'd love to hear how things are going on your side before we dive in."
        ),
        "visit_questions": [
            "What prompted you to take this call today?",
            "Who else is involved in evaluating this on your team?",
            "What would a successful outcome look like for you in the next 30 days?",
        ],
        "follow_up": "I'll share a short recap here after we wrap — anything you'd like me to include?",
        "calendar_summary": subject or f"Follow-up with {name or company or 'lead'}",
    }

    if not os.getenv("GEMINI_API_KEY"):
        return fallback

    prompt = f"""You help a sales team open Google Meet chats in a warm, conversational tone.
Return ONLY valid JSON (no markdown):
{{
  "opener": "<1-2 sentence friendly Meet chat opener>",
  "visit_questions": ["<question 1>", "<question 2>", "<question 3>"],
  "follow_up": "<1 sentence closing / recap offer for the chat>",
  "calendar_summary": "<short calendar event title, max 12 words>"
}}

Contact: {name or "Unknown"} at {company or "Unknown company"}
Pipeline stage: {stage}
CRM notes: {notes or "None"}
Meeting title: {subject or "General follow-up"}
Prep notes: {meet_notes or "None"}

Keep questions natural — like you'd ask in chat after joining, not a formal survey."""

    try:
        data = generate_json(prompt)
        if not data.get("opener"):
            return fallback
        questions = data.get("visit_questions") or fallback["visit_questions"]
        if isinstance(questions, str):
            questions = [questions]
        return {
            "opener": str(data.get("opener") or fallback["opener"]).strip(),
            "visit_questions": [str(q).strip() for q in questions[:4] if str(q).strip()],
            "follow_up": str(data.get("follow_up") or fallback["follow_up"]).strip(),
            "calendar_summary": str(data.get("calendar_summary") or fallback["calendar_summary"]).strip(),
        }
    except Exception:
        return fallback


def format_meet_chat_script(payload: dict) -> str:
    """Plain-text script to paste into Google Meet chat."""
    lines = [payload.get("opener", "")]
    for q in payload.get("visit_questions") or []:
        lines.append(f"• {q}")
    if payload.get("follow_up"):
        lines.append(payload["follow_up"])
    return "\n\n".join(line for line in lines if line.strip())
