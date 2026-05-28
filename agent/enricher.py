"""
Multi-source decision-maker enrichment.

Cascade per company:
  1. Apollo people search (3 progressively-looser queries)
  2. LinkedIn-via-Serper fallback if Apollo missed
  3. Email recovery for any contact missing an email:
       a. Hunter.io Email Finder (if HUNTER_API_KEY set)
       b. Pattern guess + Hunter verifier ranking
       c. Pure pattern guess (lowest tier)

Always returns a dict with:
  contact_name, contact_title, email, phone, linkedin_url,
  email_confidence (verified/likely/guess/unknown),
  contact_source (apollo/linkedin/empty),
  enrichment_status (found/partial/not_found).
"""

import os
import time
import requests

from utils.rate_limiter import apollo_limiter
from agent.contact_finder import (
    find_decision_maker_via_linkedin,
    hunter_find_email,
    best_guess_email,
    extract_domain,
    split_name,
)


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

    # ── Step 2: LinkedIn-via-Serper fallback ──────────────────────────────────
    if not contact.get("contact_name"):
        linkedin_hit = find_decision_maker_via_linkedin(company_name, target_titles)
        if linkedin_hit:
            contact.update(linkedin_hit)
            contact["contact_source"] = "linkedin"

    # ── Step 3: Email recovery ────────────────────────────────────────────────
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
    best = _pick_most_senior(people)
    name = f"{best.get('first_name', '')} {best.get('last_name', '')}".strip()
    email = best.get("email", "") or best.get("email_unverified", "") or ""
    return {
        "contact_name":     name,
        "contact_title":    best.get("title", ""),
        "email":            email,
        "phone":            _extract_phone(best),
        "linkedin_url":     best.get("linkedin_url", "") or "",
        "email_confidence": "verified" if best.get("email") else ("likely" if email else "unknown"),
        "contact_source":   "apollo",
    }


def _pick_most_senior(people: list) -> dict:
    for priority_title in TITLE_PRIORITY:
        for person in people:
            if priority_title.lower() in (person.get("title") or "").lower():
                return person
    return people[0]


def _extract_phone(person: dict) -> str:
    for key in ("phone_number", "sanitized_phone", "mobile_phone", "direct_phone"):
        if person.get(key):
            return str(person[key])
    for phone in person.get("phone_numbers", []) or []:
        if isinstance(phone, dict):
            value = (
                phone.get("sanitized_number")
                or phone.get("raw_number")
                or phone.get("number")
            )
            if value:
                return str(value)
        elif phone:
            return str(phone)
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
