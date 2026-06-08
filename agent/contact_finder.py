"""
Multi-source contact discovery for B2B leads.

Supporting utilities for the enrichment cascade:

  1. Direct website/contact-page scrape for public email + phone
  2. LinkedIn-via-Serper — find profile from job title + company
  3. Hunter.io Email Finder — email from (domain, first, last)
  4. Pattern guess — generate likely emails as last resort

Every contact carries `email_confidence`:
  verified — returned by Hunter with confidence >= 70
  likely   — Hunter confidence 40-69 OR pattern guess validated by Hunter
  guess    — pure pattern guess, not validated
"""

import os
import re
import time
import requests
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from agent.searcher import search_serper, search_yahoo_linkedin_profiles
from utils import budget


HUNTER_FIND     = "https://api.hunter.io/v2/email-finder"
HUNTER_VERIFY   = "https://api.hunter.io/v2/email-verifier"

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(
    r"(?:\+91[\s-]?)?(?:0[\s-]?)?[6-9]\d{2}[\s-]?\d{3}[\s-]?\d{4}"
)

_NON_COMPANY_CONTACT_DOMAINS = (
    "linkedin.com", "naukri.com", "indeed.com", "glassdoor.", "bebee.com",
    "foundit.in", "monsterindia.com", "timesjobs.com", "shine.com",
    "ambitionbox.com", "reddit.com", "quora.com",
)


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

    # Cap the title fan-out to 3 — each is a Serper call and the first few
    # decision-maker titles carry almost all of the hit rate.
    for title in target_titles[:3]:
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


def find_decision_maker_via_yahoo(company_name: str, target_titles: list, city: str = "Bengaluru") -> dict:
    """
    Use Yahoo Search (not Google — Yahoo doesn't block automated fetches)
    to find real LinkedIn profiles matching a decision-maker title at the
    company. Yahoo returns actual LinkedIn profile pages in search results
    with names, titles, and locations displayed in snippets.

    Returns {name, title, linkedin_url} or {} if nothing credible found.
    """
    if not company_name:
        return {}

    for title in target_titles[:3]:
        profiles = search_yahoo_linkedin_profiles(company_name, title, city)
        for p in profiles:
            name = p.get("name", "")
            linkedin_url = p.get("linkedin_url", "")
            snippet = p.get("snippet", "")
            if name and linkedin_url:
                if company_name.lower() in (snippet + " " + linkedin_url).lower():
                    return {
                        "contact_name":  name,
                        "contact_title": title,
                        "linkedin_url":  linkedin_url,
                        "source":        "yahoo_linkedin",
                    }
    return {}


# ── Direct website / contact-page scrape ─────────────────────────────────────

def find_public_contact_info(company_name: str, website: str = "") -> dict:
    """
    Best-effort public contact scrape without paid contact databases.
    Returns generic or named contact details if the company publishes them.
    """
    urls = _candidate_contact_urls(company_name, website)
    for url in urls:
        hit = _scrape_contact_url(url)
        if hit.get("email") or hit.get("phone"):
            hit["contact_source"] = "public_website"
            hit.setdefault("email_confidence", "likely" if hit.get("email") else "unknown")
            return hit
    return {}


def _candidate_contact_urls(company_name: str, website: str) -> list:
    urls = []
    if website and website.startswith("http") and not _is_non_company_domain(website):
        root = website.split("?")[0].rstrip("/")
        if "/" in root.replace("https://", "").replace("http://", ""):
            root = f"{root.split('://')[0]}://{root.split('://', 1)[1].split('/')[0]}"
        urls.extend([
            root,
            urljoin(root + "/", "contact"),
            urljoin(root + "/", "contact-us"),
            urljoin(root + "/", "about"),
            urljoin(root + "/", "team"),
            urljoin(root + "/", "leadership"),
        ])

    if company_name and os.getenv("SERPER_API_KEY"):
        try:
            for result in search_serper(f'"{company_name}" contact email phone', num=5):
                url = result.get("website", "")
                if url and url.startswith("http"):
                    urls.append(url)
        except Exception:
            pass

    deduped = []
    seen = set()
    for url in urls:
        key = url.rstrip("/").lower()
        if key not in seen:
            seen.add(key)
            deduped.append(url)
    return deduped[:8]


def _is_non_company_domain(url: str) -> bool:
    domain = url.replace("https://", "").replace("http://", "").split("/")[0].lower()
    return any(blocked in domain for blocked in _NON_COMPANY_CONTACT_DOMAINS)


def _scrape_contact_url(url: str) -> dict:
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8,
        )
        if resp.status_code >= 400:
            return {}
    except Exception:
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    mailto_emails = [
        a.get("href", "").replace("mailto:", "").split("?")[0].strip()
        for a in soup.select("a[href^='mailto:']")
    ]
    emails = _clean_emails(mailto_emails + EMAIL_RE.findall(resp.text + " " + text))
    phones = _clean_phones(PHONE_RE.findall(text))

    return {
        "contact_name": "",
        "contact_title": "Public contact",
        "email": emails[0] if emails else "",
        "phone": phones[0] if phones else "",
        "linkedin_url": "",
    }


def _clean_emails(values: list) -> list:
    out, seen = [], set()
    junk = ("example.", "domain.", "email.com", "sentry.", "wixpress", "schema.org")
    for value in values:
        email = str(value).strip().strip(".,;:()[]{}<>").lower()
        if not email or "@" not in email or any(j in email for j in junk):
            continue
        if email.startswith(("noreply@", "no-reply@", "donotreply@")):
            continue
        if email not in seen:
            seen.add(email)
            out.append(email)
    return out


def _clean_phones(values: list) -> list:
    out, seen = [], set()
    for value in values:
        phone = re.sub(r"\s+", " ", str(value)).strip()
        digits = re.sub(r"\D", "", phone)
        if len(digits) < 10:
            continue
        if phone not in seen:
            seen.add(phone)
            out.append(phone)
    return out


# ── Hunter.io Email Finder ────────────────────────────────────────────────────

def hunter_find_email(domain: str, first_name: str, last_name: str) -> dict:
    """Returns {email, confidence:int 0-100} or {} on miss."""
    api_key = os.getenv("HUNTER_API_KEY")
    if not (api_key and domain and first_name and last_name):
        return {}
    if not budget.allow("hunter"):
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
    if not budget.allow("hunter"):
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
