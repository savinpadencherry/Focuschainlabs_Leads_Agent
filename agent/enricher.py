"""
Apollo-backed contact enrichment.

Three-stage fallback so free-tier accounts still return results:
  1. company + titles + location
  2. company + titles (drop location)
  3. company only (drop titles too)
"""

import os
import time
import requests

from utils.rate_limiter import apollo_limiter


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


def enrich_contact(company_name: str, target_titles: list, location: str) -> dict:
    if not os.getenv("APOLLO_API_KEY"):
        return _empty_result()

    apollo_limiter.wait()

    # Three progressively looser searches until we get a hit
    searches = [
        {"q_organization_name": company_name, "person_titles": target_titles,
         "organization_locations": [location], "per_page": 5},
        {"q_organization_name": company_name, "person_titles": target_titles,
         "per_page": 5},
        {"q_organization_name": company_name, "per_page": 5},
    ]

    for payload in searches:
        payload["api_key"] = os.getenv("APOLLO_API_KEY")
        try:
            response = requests.post(APOLLO_PEOPLE_SEARCH, json=payload, timeout=15)

            if response.status_code == 429:
                print("  [WARN] Apollo rate limited — waiting 60s")
                time.sleep(60)
                response = requests.post(APOLLO_PEOPLE_SEARCH, json=payload, timeout=15)

            if response.status_code != 200:
                print(f"  [WARN] Apollo returned {response.status_code}: {response.text[:120]}")
                continue

            people = response.json().get("people", [])
            if people:
                return _build_result(people)

        except Exception as e:
            print(f"  [ERROR] Apollo enrichment failed for {company_name}: {e}")
            break

    return _empty_result()


def _build_result(people: list) -> dict:
    best = _pick_most_senior(people)
    contact_name  = f"{best.get('first_name', '')} {best.get('last_name', '')}".strip()
    contact_title = best.get("title", "")
    email         = best.get("email", "") or ""
    phone         = _extract_phone(best)

    # Apollo free tier masks email as "email_unverified" — expose it anyway
    if not email:
        email = best.get("email_unverified", "") or ""

    return {
        "contact_name":      contact_name,
        "contact_title":     contact_title,
        "email":             email,
        "phone":             phone,
        "enrichment_status": "found",
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


def _empty_result() -> dict:
    return {
        "contact_name":      "",
        "contact_title":     "",
        "email":             "",
        "phone":             "",
        "enrichment_status": "not_found",
    }
