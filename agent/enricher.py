import os
import time
import requests

from utils.rate_limiter import apollo_limiter


APOLLO_PEOPLE_SEARCH = "https://api.apollo.io/v1/mixed_people_search"

TITLE_PRIORITY = [
    "CTO", "Chief Technology Officer",
    "CIO", "Chief Information Officer",
    "VP Technology", "VP IT",
    "Head of IT", "Director Technology",
    "VP Digital Transformation",
    "COO", "VP Operations"
]


def enrich_contact(company_name: str, target_titles: list, location: str) -> dict:
    apollo_limiter.wait()

    if not os.getenv("APOLLO_API_KEY"):
        return _manual_lookup_result()

    payload = {
        "api_key": os.getenv("APOLLO_API_KEY"),
        "q_organization_name": company_name,
        "person_titles": target_titles,
        "organization_locations": [location],
        "contact_email_status": ["verified", "likely to engage"],
        "per_page": 5
    }

    try:
        response = requests.post(
            APOLLO_PEOPLE_SEARCH,
            json=payload,
            timeout=15
        )

        if response.status_code == 429:
            print("  [WARN] Apollo rate limited — waiting 60s")
            time.sleep(60)
            response = requests.post(
                APOLLO_PEOPLE_SEARCH, json=payload, timeout=15
            )

        response.raise_for_status()
        people = response.json().get("people", [])
        if not people:
            return _manual_lookup_result()

        best = _pick_most_senior(people)

        return {
            "contact_name": f"{best.get('first_name', '')} {best.get('last_name', '')}".strip(),
            "contact_title": best.get("title", ""),
            "email": best.get("email", ""),
            "linkedin_url": best.get("linkedin_url", ""),
            "enrichment_status": "found"
        }

    except Exception as e:
        print(f"  [ERROR] Apollo enrichment failed for {company_name}: {e}")
        return _manual_lookup_result()


def _pick_most_senior(people: list) -> dict:
    for priority_title in TITLE_PRIORITY:
        for person in people:
            title = person.get("title", "").lower()
            if priority_title.lower() in title:
                return person
    return people[0]


def _manual_lookup_result() -> dict:
    return {
        "contact_name": "Manual lookup needed",
        "contact_title": "Manual lookup needed",
        "email": "Manual lookup needed",
        "linkedin_url": "Manual lookup needed",
        "enrichment_status": "not_found"
    }
