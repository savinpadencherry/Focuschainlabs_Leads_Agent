"""
Multi-source contact discovery for B2B leads.

Cascade strategy (each step runs only if the previous one didn't yield
a usable contact / email):

  1. Apollo /v1/mixed_people_search — primary
  2. LinkedIn-via-Serper — find profile from job title + company
  3. Hunter.io Email Finder — email from (domain, first, last)
  4. Pattern guess — generate likely emails as last resort

Every contact carries `email_confidence`:
  verified — returned by Apollo or Hunter with confidence >= 70
  likely   — Hunter confidence 40-69 OR pattern guess validated by Hunter
  guess    — pure pattern guess, not validated
"""

import os
import re
import time
import requests

from agent.searcher import search_serper


HUNTER_FIND     = "https://api.hunter.io/v2/email-finder"
HUNTER_VERIFY   = "https://api.hunter.io/v2/email-verifier"


# ── LinkedIn search via Serper ────────────────────────────────────────────────

_NAME_REGEX = re.compile(r"^([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)\b")


def find_decision_maker_via_linkedin(company_name: str, target_titles: list) -> dict:
    """
    Query Serper for LinkedIn profiles matching a decision-maker title
    at the company. Returns {name, title, linkedin_url} or {} if nothing
    looked credible.
    """
    if not company_name or not os.getenv("SERPER_API_KEY"):
        return {}

    for title in target_titles[:5]:
        query = f'site:linkedin.com/in "{title}" "{company_name}"'
        try:
            results = search_serper(query, num=5)
        except Exception:
            continue

        for r in results:
            url     = r.get("website", "") or r.get("link", "")
            snippet = r.get("snippet", "")
            title_s = r.get("title", "") or snippet

            if "linkedin.com/in/" not in url:
                continue

            # LinkedIn titles look like "Priya Sharma - VP HR - Cadabams ..."
            name_match = _NAME_REGEX.match(title_s.strip())
            if not name_match:
                continue
            name = name_match.group(1).strip()

            # Verify the company name appears in the result (avoids cross-company false hits)
            if company_name.lower() not in (title_s + " " + snippet).lower():
                continue

            return {
                "contact_name":  name,
                "contact_title": title,
                "linkedin_url":  url.split("?")[0],
                "source":        "linkedin_search",
            }

    return {}


# ── Hunter.io Email Finder ────────────────────────────────────────────────────

def hunter_find_email(domain: str, first_name: str, last_name: str) -> dict:
    """Returns {email, confidence:int 0-100} or {} on miss."""
    api_key = os.getenv("HUNTER_API_KEY")
    if not (api_key and domain and first_name and last_name):
        return {}

    try:
        resp = requests.get(
            HUNTER_FIND,
            params={
                "domain":     domain,
                "first_name": first_name,
                "last_name":  last_name,
                "api_key":    api_key,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return {}
        data = (resp.json() or {}).get("data", {}) or {}
        email = data.get("email")
        if not email:
            return {}
        return {
            "email":      email,
            "confidence": int(data.get("score") or 0),
        }
    except Exception as e:
        print(f"  [WARN] Hunter find_email failed: {e}")
        return {}


def hunter_verify_email(email: str) -> int:
    """Returns 0-100 confidence score, or -1 if Hunter not configured."""
    api_key = os.getenv("HUNTER_API_KEY")
    if not (api_key and email):
        return -1
    try:
        resp = requests.get(
            HUNTER_VERIFY,
            params={"email": email, "api_key": api_key},
            timeout=10,
        )
        if resp.status_code != 200:
            return -1
        data = (resp.json() or {}).get("data", {}) or {}
        return int(data.get("score") or 0)
    except Exception:
        return -1


# ── Pattern-based email guess ─────────────────────────────────────────────────

def generate_email_candidates(domain: str, first_name: str, last_name: str) -> list:
    """
    Return likely email patterns (ranked) for India / global B2B.
    Caller is responsible for verifying.
    """
    if not (domain and first_name and last_name):
        return []
    f = first_name.lower().strip()
    l = last_name.lower().strip()
    return [
        f"{f}.{l}@{domain}",
        f"{f}@{domain}",
        f"{f}{l}@{domain}",
        f"{f[0]}{l}@{domain}",
        f"{f}_{l}@{domain}",
        f"{l}.{f}@{domain}",
    ]


def best_guess_email(domain: str, first_name: str, last_name: str) -> dict:
    """
    Use Hunter verifier if available to pick the best candidate.
    Returns {email, confidence:int, confidence_tier:str}.
    """
    candidates = generate_email_candidates(domain, first_name, last_name)
    if not candidates:
        return {}

    best_email = candidates[0]
    best_score = -1

    for candidate in candidates:
        score = hunter_verify_email(candidate)
        if score > best_score:
            best_email, best_score = candidate, score
        if score >= 80:
            break  # good enough

    tier = "guess"
    if best_score >= 70:
        tier = "verified"
    elif best_score >= 40:
        tier = "likely"

    return {
        "email":           best_email,
        "confidence":      max(best_score, 0),
        "confidence_tier": tier,
    }


# ── Domain helpers ────────────────────────────────────────────────────────────

def extract_domain(website: str) -> str:
    if not website:
        return ""
    domain = website.replace("https://", "").replace("http://", "")
    domain = domain.split("/")[0].split("?")[0].strip().lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def split_name(full_name: str) -> tuple:
    """('Priya Sharma',) → ('Priya', 'Sharma')"""
    if not full_name:
        return ("", "")
    parts = full_name.strip().split()
    if len(parts) == 1:
        return (parts[0], "")
    return (parts[0], " ".join(parts[1:]))
