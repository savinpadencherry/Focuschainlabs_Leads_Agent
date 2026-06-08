"""
Prompt → Search Plan
The planner takes a free-form user prompt + base ICP, asks Gemini to
synthesise the actual search keywords, target titles, pain-point lens
and gap hypothesis the downstream pipeline will hunt for.

This is what turns "Find me Bangalore D2C brands hiring ecommerce ops"
into 12 specific Google queries + 5 LinkedIn job titles + a sharpened
ICP that scorer.py and researcher.py can act on.
"""

import os
import json
import re
from datetime import datetime

from utils.rate_limiter import gemini_limiter
from utils.exceptions import RateLimitError
from utils.gemini import generate_content_text


PLAN_PROMPT = """
You are a lead-generation strategist. The user has given you a
natural-language brief. Translate it into a concrete search plan that a
downstream web-scraping + LLM pipeline can execute today.

The user's brief is the source of truth — re-shape industries, titles
and keywords to match their intent, even if it diverges from the base ICP.
{vertical_context_block}
USER BRIEF:
{user_prompt}

BASE ICP (use as fallback for any field the brief does not constrain):
{base_icp}

CURRENT YEAR: {year}

Return ONLY valid JSON. No markdown. No prose. This exact shape:
{{
  "industries":        [<3 to 6 industry strings, narrowed to the brief>],
  "locations":         [<1 to 3 city strings>],
  "target_titles":     [<6 to 10 decision-maker titles who would own
                        the problem or budget, as defined by the vertical context above>],
  "trigger_keywords":  [<10 to 14 Google-ready queries as specified in the
                        vertical context above. Each one must be a real,
                        date-stamped search. Include the year. Prefer
                        individual person/org/news results; avoid listicles,
                        trend reports, "best providers", and generic guides.>],
  "linkedin_queries":  [<3 to 5 site:linkedin.com queries as specified in
                        the vertical context above>],
  "reddit_queries":    [<2 to 4 site:reddit.com queries that surface real
                        demand signals relevant to the vertical>],
  "yahoo_queries":     [<4 to 8 Yahoo-ready queries in the form
                        "linkedin [company or industry keyword] [role] [city]"
                        to surface real LinkedIn /in/ profile pages with names
                        and titles in snippets — no site: prefix>],
  "pain_hypothesis":   "<one sentence: the primary need or pain these targets
                       are most likely experiencing right now>",
  "gap_hypothesis":    "<one sentence: the specific gap the user's offering
                       closes for them>",
  "custom_focus":      "<one sentence summarising what the scorer should
                       weight most heavily when ranking these leads>"
}}
"""


_B2B_VERTICAL_CONTEXT = """
VERTICAL: Standard B2B lead-generation.
For trigger_keywords: mix hiring, expansion, operational pain, customer
experience, ecommerce, CRM, automation, booking, dispatch, inventory,
marketing, and process signals. Prefer individual company/job/news results.
Avoid CTO/CIO-led searches unless the user explicitly asks.
For linkedin_queries: use site:linkedin.com/jobs queries to surface active
hiring at target companies — infer role gaps and operational pains.
For yahoo_queries: use "linkedin [company or vertical] [decision-maker title]
[city]" strings (e.g. "linkedin Deloitte India analytics director Bengaluru")
to find real LinkedIn profile URLs and names via Yahoo Search.
"""

_BUYER_INTENT_VERTICAL_CONTEXT = """
VERTICAL: BUYER-INTENT / REFERRAL-CHANNEL — NOT B2B software or hiring.
This ICP sells directly to end-consumers OR sources leads through referral
organisations that have direct access to buyers. Ignore all hiring/CRM/ecommerce
framing below.

For trigger_keywords: generate BUYER DEMAND and REFERRAL CHANNEL signals.
  Good signal types:
    - People/families actively enquiring about the product (e.g. "retirement home
      Bangalore buy 2026", "NRI parents elder care Bangalore enquiry 2026")
    - Associations/communities whose members ARE the buyers (e.g. "senior citizens
      association Bangalore contact 2026", "retired bank employees Karnataka 2026")
    - Service providers with direct access to buyers (e.g. "geriatric care manager
      Bangalore contact 2026", "home healthcare Bangalore founder 2026")
    - Content revealing active demand (reviews, Reddit discussions, NRI forums)
  Do NOT generate job postings, Naukri/LinkedIn jobs, or CRM/software signals.

For linkedin_queries: use site:linkedin.com/in (profiles) NOT site:linkedin.com/jobs.
  Target individual advisors, care providers, association leaders, and community
  managers who are direct referral channels to buyers — NOT hiring posts.
"""


def _strip_fences(raw: str) -> str:
    return re.sub(r"```json|```", "", raw).strip()


def _vertical_context_block(base_icp: dict) -> str:
    """Return the vertical context block for PLAN_PROMPT based on the ICP's search_type."""
    if base_icp.get("search_type") == "buyer_intent" or base_icp.get("scoring_guidance"):
        return _BUYER_INTENT_VERTICAL_CONTEXT
    return _B2B_VERTICAL_CONTEXT


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
        vertical_context_block=_vertical_context_block(base_icp),
        user_prompt=user_prompt.strip(),
        base_icp=json.dumps(icp_slim, indent=2),
        year=datetime.today().year,
    )

    for attempt in range(2):
        try:
            plan = json.loads(_strip_fences(generate_content_text(prompt)))
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
    titles = _filter_titles(
        _as_list(plan.get("target_titles")) or base_icp.get("target_titles", []),
        user_prompt,
    )
    return {
        "industries":        _as_list(plan.get("industries"))
                              or base_icp.get("target_industries", []),
        "locations":         _as_list(plan.get("locations"))
                              or base_icp.get("locations", ["Bangalore"]),
        "target_titles":     titles,
        "trigger_keywords":  _as_list(plan.get("trigger_keywords"))
                              or base_icp.get("trigger_keywords", []),
        "linkedin_queries":  _as_list(plan.get("linkedin_queries")),
        "reddit_queries":    _as_list(plan.get("reddit_queries")),
        "yahoo_queries":     _as_list(plan.get("yahoo_queries")),
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


def _filter_titles(titles: list, user_prompt: str = "") -> list:
    prompt = (user_prompt or "").lower()
    allow_tech = any(token in prompt for token in ("cto", "cio", "chief technology", "chief information"))
    if allow_tech:
        return titles
    blocked = ("cto", "cio", "chief technology officer", "chief information officer")
    return [t for t in titles if not any(b in str(t).lower() for b in blocked)]


def _fallback_plan(base_icp: dict, user_prompt: str = "") -> dict:
    """Used when the LLM is unavailable or returns garbage."""
    year = datetime.today().year
    titles = _filter_titles(base_icp.get("target_titles", []), user_prompt)
    city = (base_icp.get("locations") or ["Bangalore"])[0]
    industries = base_icp.get("target_industries", [])
    brief = re.sub(r"\s+", " ", (user_prompt or "").strip())[:140]

    is_buyer_intent = (
        base_icp.get("search_type") == "buyer_intent"
        or bool(base_icp.get("scoring_guidance"))
    )

    if is_buyer_intent:
        # For consumer/referral verticals: generate demand-signal keywords, not job signals
        trigger_keywords = (
            base_icp.get("trigger_keywords")
            or [
                f'retirement homes {city} buy {year}',
                f'senior living apartments {city} enquiry {year}',
                f'NRI parents elder care {city} {year}',
                f'geriatric care manager {city} contact {year}',
                f'senior citizens association {city} {year}',
                f'home healthcare {city} founder {year}',
                f'assisted living {city} {year}',
                f'estate planning advisor {city} senior {year}',
            ]
        )
        linkedin_queries = [
            f'site:linkedin.com/in "{t}" "{city}"' for t in titles[:5]
        ]
        yahoo_queries = [
            f"linkedin {t} {city}" for t in titles[:4]
        ]
        reddit_queries = [
            f'site:reddit.com {city} senior living parents care',
            f'site:reddit.com NRI parents India elder care',
        ]
    elif brief:
        trigger_keywords = [
            f'{brief} company hiring operations manager {year}',
            f'{brief} site:linkedin.com/jobs {year}',
            f'{brief} "we are hiring" operations {year}',
            f'{city} {industries[0] if industries else "SMB"} company operations automation hiring {year}',
            f'{city} logistics dispatch warehouse management automation hiring {year}',
            f'{city} SME customer support CRM automation hiring {year}',
        ]
        linkedin_queries = [
            f'site:linkedin.com/jobs "{t}" "{city}" {year}' for t in titles
        ][:5]
        yahoo_queries = [
            f"linkedin {industries[0] if industries else brief} {t} {city}"
            for t in titles[:4]
        ]
        reddit_queries = [f'site:reddit.com {brief or base_icp.get("vertical", "B2B")} pain']
    else:
        trigger_keywords = base_icp.get("trigger_keywords", [])
        linkedin_queries = [
            f'site:linkedin.com/jobs "{t}" "{city}" {year}' for t in titles
        ][:5]
        yahoo_queries = [
            f"linkedin {t} {city}" for t in titles[:4]
        ]
        reddit_queries = [f'site:reddit.com {base_icp.get("vertical", "B2B")} pain']

    return {
        "industries":       base_icp.get("target_industries", []),
        "locations":        base_icp.get("locations", ["Bangalore"]),
        "target_titles":    titles,
        "trigger_keywords": trigger_keywords,
        "linkedin_queries": linkedin_queries,
        "yahoo_queries":    yahoo_queries,
        "reddit_queries":   reddit_queries,
        "pain_hypothesis":  "",
        "gap_hypothesis":   "",
        "custom_focus":     user_prompt.strip()[:300],
    }
