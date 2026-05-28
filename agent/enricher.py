"""
Multi-source decision-maker enrichment.

Cascade per company:
  1. Apollo people search (3 progressively-looser queries)
  2. Apify (3-actor cascade)
       a. dominic-quaiser/decision-maker-name-email-extractor  (website NER)
       b. harvestapi/linkedin-company-employees                (no cookies)
       c. vdrmota/contact-info-scraper                        (public emails)
  3. LinkedIn-via-Serper fallback (Google-indexed profiles)
  4. Email recovery for any contact missing an email:
       a. Hunter.io Email Finder
       b. Pattern guess + Hunter verifier ranking

Always returns a dict with:
  contact_name, contact_title, email, phone, linkedin_url,
  email_confidence (verified/likely/guess/unknown),
  contact_source (apollo/apify_*/linkedin/empty),
  enrichment_status (found/partial/not_found).
"""

import os
import time
import requests

from utils.rate_limiter import apollo_limiter
from utils.exceptions import RateLimitError
from agent.contact_finder import (
    find_decision_maker_via_linkedin,
    hunter_find_email,
    best_guess_email,
    extract_domain,
    split_name,
)
from agent.apify_enricher import find_contact_via_apify


APOLLO_PEOPLE_SEARCH = "https://api.apollo.io/v1/mixed_people_search"

TITLE_PRIORITY = [
    "CTO", "Chief Technology Officer",
    "CIO", "Chief Information Officer",
    "CDO", "Chief Digital Officer",
    "VP Technology", "VP IT", "VP Engineering",
    "Head of IT", "Head of Engineering", "Director Technology",
    "VP Digital Transformation",
    "COO", "VP Operations",
    "CPO", "Chief People Officer", "HR Director", "Head of HR",
]


def enrich_contact(
    company_name: str,
    target_titles: list,
    location: str,
    website: str = "",
) -> dict:
    """Full multi-source enrichment for one company."""

    # ── Step 1: Apollo ────────────────────────────────────────────────────────
    contact = _apollo_search(company_name, target_titles, location)

    # ── Step 2: Apify cascade (decision-maker → LinkedIn → website) ───────────
    if not (contact.get("contact_name") and contact.get("email")):
        try:
            apify_hit = find_contact_via_apify(company_name, website, target_titles)
        except RateLimitError:
            apify_hit = {}
        if apify_hit:
            # Merge: Apify fills whatever Apollo missed
            if not contact.get("contact_name"):
                contact.update(apify_hit)
            else:
                # Apollo gave us a name but no email — borrow email/phone from Apify
                contact["email"]       = contact.get("email") or apify_hit.get("email", "")
                contact["phone"]       = contact.get("phone") or apify_hit.get("phone", "")
                contact["linkedin_url"]= contact.get("linkedin_url") or apify_hit.get("linkedin_url", "")

    # ── Step 3: LinkedIn-via-Serper fallback ──────────────────────────────────
    if not contact.get("contact_name"):
        linkedin_hit = find_decision_maker_via_linkedin(company_name, target_titles)
        if linkedin_hit:
            contact.update(linkedin_hit)
            contact["contact_source"] = "linkedin"

    # ── Step 4: Email recovery ────────────────────────────────────────────────
    if contact.get("contact_name") and not contact.get("email"):
        domain = extract_domain(website)
        first, last = split_name(contact["contact_name"])

        # 3a. Hunter Email Finder (high-precision)
        hunter_hit = hunter_find_email(domain, first, last)
        if hunter_hit.get("email"):
            contact["email"]            = hunter_hit["email"]
            contact["email_confidence"] = _tier_from_score(hunter_hit["confidence"])

        # 3b. Pattern guess + verifier ranking
        elif domain and first and last:
            guess = best_guess_email(domain, first, last)
            if guess.get("email"):
                contact["email"]            = guess["email"]
                contact["email_confidence"] = guess["confidence_tier"]

    contact.setdefault("email_confidence",
                       "verified" if contact.get("email") else "unknown")
    contact.setdefault("contact_source",  "apollo" if contact.get("email") else "")
    contact["enrichment_status"] = _status(contact)

    # Normalise — always return same keys
    return {
        "contact_name":      contact.get("contact_name", ""),
        "contact_title":     contact.get("contact_title", ""),
        "email":             contact.get("email", ""),
        "phone":             contact.get("phone", ""),
        "linkedin_url":      contact.get("linkedin_url", ""),
        "email_confidence":  contact.get("email_confidence", "unknown"),
        "contact_source":    contact.get("contact_source", ""),
        "enrichment_status": contact["enrichment_status"],
    }


# ── Apollo (3-stage fallback) ─────────────────────────────────────────────────

def _apollo_search(company_name: str, target_titles: list, location: str) -> dict:
    if not os.getenv("APOLLO_API_KEY"):
        return {}

    apollo_limiter.wait()

    searches = [
        {"q_organization_name": company_name, "person_titles": target_titles,
         "organization_locations": [location], "per_page": 5},
        {"q_organization_name": company_name, "person_titles": target_titles,
         "per_page": 5},
        {"q_organization_name": company_name, "per_page": 10},
    ]

    for payload in searches:
        payload["api_key"] = os.getenv("APOLLO_API_KEY")
        try:
            response = requests.post(APOLLO_PEOPLE_SEARCH, json=payload, timeout=15)

            if response.status_code == 429:
                print("  [WARN] Apollo rate-limited — waiting 60s")
                time.sleep(60)
                response = requests.post(APOLLO_PEOPLE_SEARCH, json=payload, timeout=15)

            if response.status_code != 200:
                print(f"  [WARN] Apollo {response.status_code}: {response.text[:120]}")
                continue

            people = (response.json() or {}).get("people", [])
            if people:
                return _build_apollo_record(people)

        except Exception as e:
            print(f"  [ERROR] Apollo failed for {company_name}: {e}")
            break

    return {}


def _build_apollo_record(people: list) -> dict:
    best  = _pick_most_senior(people)
    name  = f"{best.get('first_name', '')} {best.get('last_name', '')}".strip()
    email = _extract_email(best)
    return {
        "contact_name":     name,
        "contact_title":    best.get("title", ""),
        "email":            email,
        "phone":            _extract_phone(best),
        "linkedin_url":     best.get("linkedin_url", "") or "",
        "email_confidence": _apollo_email_confidence(best, email),
        "contact_source":   "apollo",
    }


# Apollo returns this placeholder when the email is gated behind credits
_APOLLO_PLACEHOLDER_PATTERNS = ("email_not_unlocked", "domain.com")


def _is_real_email(value) -> bool:
    if not value or not isinstance(value, str):
        return False
    v = value.lower().strip()
    if "@" not in v or "." not in v.split("@")[-1]:
        return False
    for p in _APOLLO_PLACEHOLDER_PATTERNS:
        if p in v:
            return False
    return True


def _extract_email(person: dict) -> str:
    """Try every email field Apollo exposes, in order of trust."""
    candidates = [
        person.get("email"),
        person.get("email_unverified"),
        person.get("work_email"),
        person.get("primary_email"),
    ]
    candidates += person.get("personal_emails") or []
    contact = person.get("contact") or {}
    candidates += [
        contact.get("email"),
        contact.get("email_unverified"),
        contact.get("work_email"),
    ]
    for c in candidates:
        if _is_real_email(c):
            return c.strip()
    return ""


def _apollo_email_confidence(person: dict, email: str) -> str:
    """
    Map Apollo's email_status to our tier.
    'verified' → verified, 'guessed' / 'unverified' → likely, else unknown.
    """
    if not email:
        return "unknown"
    status = (person.get("email_status") or "").lower()
    if "verified" in status and "un" not in status:
        return "verified"
    if status in ("likely", "guessed", "extrapolated", "unverified"):
        return "likely"
    # No status field but we have an email — call it likely (Apollo's bar isn't high)
    return "likely"


def _pick_most_senior(people: list) -> dict:
    for priority_title in TITLE_PRIORITY:
        for person in people:
            if priority_title.lower() in (person.get("title") or "").lower():
                return person
    return people[0]


def _extract_phone(person: dict) -> str:
    """Take any phone Apollo gives us — direct fields, arrays, nested contact."""
    # Direct scalar fields
    for key in (
        "phone_number", "sanitized_phone", "mobile_phone", "direct_phone",
        "primary_phone", "work_phone", "corporate_phone", "home_phone",
    ):
        value = person.get(key)
        if value:
            return str(value).strip()

    # Phone arrays
    for arr_key in ("phone_numbers", "personal_phones"):
        for phone in person.get(arr_key, []) or []:
            if isinstance(phone, dict):
                value = (
                    phone.get("sanitized_number")
                    or phone.get("raw_number")
                    or phone.get("number")
                    or phone.get("phone")
                )
                if value:
                    return str(value).strip()
            elif phone:
                return str(phone).strip()

    # Nested contact object (Apollo sometimes nests phones here)
    contact = person.get("contact") or {}
    for key in ("phone_number", "sanitized_phone", "mobile_phone", "direct_phone"):
        if contact.get(key):
            return str(contact[key]).strip()
    for phone in contact.get("phone_numbers", []) or []:
        if isinstance(phone, dict):
            value = (
                phone.get("sanitized_number")
                or phone.get("raw_number")
                or phone.get("number")
            )
            if value:
                return str(value).strip()

    return ""


def _tier_from_score(score: int) -> str:
    if score >= 70:
        return "verified"
    if score >= 40:
        return "likely"
    return "guess"


def _status(contact: dict) -> str:
    if contact.get("email") and contact.get("contact_name"):
        return "found"
    if contact.get("contact_name"):
        return "partial"  # have name + LinkedIn but no email
    return "not_found"
