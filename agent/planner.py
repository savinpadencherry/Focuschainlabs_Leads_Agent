"""
Prompt → Search Plan
The planner takes a free-form user prompt + base ICP, asks Gemini to
synthesise the actual search keywords, target titles, pain-point lens
and gap hypothesis the downstream pipeline will hunt for.

This is what turns "Find me Bangalore D2C brands that just hired a CTO"
into 12 specific Google queries + 5 LinkedIn job titles + a sharpened
ICP that scorer.py and researcher.py can act on.
"""

import os
import json
import re
from datetime import datetime

from google import genai

from utils.rate_limiter import gemini_limiter
from utils.exceptions import RateLimitError


PLAN_PROMPT = """
You are a B2B lead-generation strategist. The user has given you a
natural-language brief. Translate it into a concrete search plan that a
downstream web-scraping + LLM pipeline can execute today.

The user's brief is the source of truth — re-shape industries, titles
and keywords to match their intent, even if it diverges from the base ICP.

USER BRIEF:
{user_prompt}

BASE ICP (use as fallback for any field the brief does not constrain):
{base_icp}

CURRENT YEAR: {year}

Return ONLY valid JSON. No markdown. No prose. This exact shape:
{{
  "industries":        [<3 to 6 industry strings, narrowed to the brief>],
  "locations":         [<1 to 3 city strings>],
  "target_titles":     [<6 to 10 senior decision-maker titles who would own
                        the problem or budget, not junior implementers>],
  "trigger_keywords":  [<10 to 14 Google-ready queries — each one a real,
                        date-stamped search a SDR would run, not a topic.
                        Include the year. Mix funding, hiring, leadership
                        moves, job posts, management appointments, product
                        launches, expansion, and tech-stack/problem signals.>],
  "linkedin_queries":  [<3 to 5 site:linkedin.com/jobs queries that surface
                        active hiring at target companies. These should help
                        infer what role gaps or operational pains they are
                        trying to solve.>],
  "reddit_queries":    [<2 to 4 site:reddit.com queries that surface
                        practitioners complaining about the pain the user
                        sells into — these reveal real demand signals>],
  "pain_hypothesis":   "<one sentence: the operational pain these targets
                       are most likely feeling right now>",
  "gap_hypothesis":    "<one sentence: the specific capability gap the
                       user's offering closes for them>",
  "custom_focus":      "<one sentence summarising what the scorer should
                       weight most heavily when ranking these companies>"
}}
"""


def _strip_fences(raw: str) -> str:
    return re.sub(r"```json|```", "", raw).strip()


def plan_search(user_prompt: str, base_icp: dict) -> dict:
    """Return a fully-formed search plan derived from the user's prompt."""

    if not user_prompt or not user_prompt.strip():
        return _fallback_plan(base_icp)

    if not os.getenv("GEMINI_API_KEY"):
        return _fallback_plan(base_icp, user_prompt)

    gemini_limiter.wait()

    icp_slim = {
        "vertical":         base_icp.get("vertical"),
        "client":           base_icp.get("client"),
        "target_industries": base_icp.get("target_industries", []),
        "locations":        base_icp.get("locations", ["Bangalore"]),
        "target_titles":    base_icp.get("target_titles", []),
        "trigger_keywords": base_icp.get("trigger_keywords", [])[:6],
    }

    prompt = PLAN_PROMPT.format(
        user_prompt=user_prompt.strip(),
        base_icp=json.dumps(icp_slim, indent=2),
        year=datetime.today().year,
    )

    for attempt in range(2):
        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            resp = client.models.generate_content(
                model="gemini-3.5-flash",
                contents=prompt,
            )
            plan = json.loads(_strip_fences(resp.text))
            return _normalise(plan, base_icp, user_prompt)

        except json.JSONDecodeError:
            if attempt == 0:
                continue
            print("  [SKIP] Planner JSON parse failed — using fallback")
            return _fallback_plan(base_icp, user_prompt)
        except Exception as e:
            _raise_if_rate_limit("gemini", e)
            print(f"  [ERROR] Planner call failed: {e}")
            return _fallback_plan(base_icp, user_prompt)


def _normalise(plan: dict, base_icp: dict, user_prompt: str) -> dict:
    """Guarantee every field exists and is the right type."""
    return {
        "industries":        _as_list(plan.get("industries"))
                              or base_icp.get("target_industries", []),
        "locations":         _as_list(plan.get("locations"))
                              or base_icp.get("locations", ["Bangalore"]),
        "target_titles":     _as_list(plan.get("target_titles"))
                              or base_icp.get("target_titles", []),
        "trigger_keywords":  _as_list(plan.get("trigger_keywords"))
                              or base_icp.get("trigger_keywords", []),
        "linkedin_queries":  _as_list(plan.get("linkedin_queries")),
        "reddit_queries":    _as_list(plan.get("reddit_queries")),
        "pain_hypothesis":   plan.get("pain_hypothesis", "") or "",
        "gap_hypothesis":    plan.get("gap_hypothesis", "") or "",
        "custom_focus":      plan.get("custom_focus", user_prompt[:300]),
    }


def _raise_if_rate_limit(service: str, exc: Exception) -> None:
    """Re-raise as RateLimitError if the exception looks like a quota error."""
    msg = str(exc).lower()
    if any(k in msg for k in ("429", "resource_exhausted", "quota", "rate limit", "ratelimit")):
        raise RateLimitError(service, str(exc))


def _as_list(value) -> list:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _fallback_plan(base_icp: dict, user_prompt: str = "") -> dict:
    """Used when the LLM is unavailable or returns garbage."""
    year = datetime.today().year
    titles = base_icp.get("target_titles", [])[:3]
    city = (base_icp.get("locations") or ["Bangalore"])[0]
    return {
        "industries":       base_icp.get("target_industries", []),
        "locations":        base_icp.get("locations", ["Bangalore"]),
        "target_titles":    base_icp.get("target_titles", []),
        "trigger_keywords": base_icp.get("trigger_keywords", []),
        "linkedin_queries": [
            f'site:linkedin.com/jobs "{t}" "{city}" {year}' for t in titles
        ],
        "reddit_queries": [
            f'site:reddit.com {base_icp.get("vertical", "B2B")} {city} pain',
        ],
        "pain_hypothesis": "",
        "gap_hypothesis":  "",
        "custom_focus":    user_prompt.strip()[:300],
    }
