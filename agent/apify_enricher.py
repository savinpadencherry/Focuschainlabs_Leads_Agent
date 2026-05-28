"""
Apify-backed contact discovery.

Three actors tried in cascade per company:

  1. dominic-quaiser/decision-maker-name-email-extractor
     Scrapes the company website, uses NER to find named decision-makers
     with job titles and emails. Best when the company publishes a team/
     leadership page.

  2. harvestapi/linkedin-company-employees
     Searches LinkedIn for employees of the company filtered by title.
     No cookies required. Returns name, title, LinkedIn URL.
     Typically no email in short mode — we hand off to Hunter/guess.

  3. vdrmota/contact-info-scraper
     Last resort: extracts every email + phone publicly listed on the
     company homepage. Usually returns info@/hr@/careers@ style addresses
     — still useful as outreach starting point.

All actors use the Apify /run-sync-get-dataset-items endpoint (up to 90s).
If APIFY_API_KEY is not set every function returns {} silently.
"""

import os
import time
import requests

from utils.exceptions import RateLimitError


APIFY_BASE = "https://api.apify.com/v2"

# Stable actor IDs
ACTOR_DECISION_MAKER = "dominic-quaiser/decision-maker-name-email-extractor"
ACTOR_LINKEDIN_EMP   = "harvestapi/linkedin-company-employees"
ACTOR_CONTACT_INFO   = "vdrmota/contact-info-scraper"

# Title priority list (shared with enricher)
TITLE_PRIORITY = [
    "Founder", "Co-Founder", "Owner", "Managing Director", "CEO",
    "COO", "General Manager", "Business Head",
    "Head of Operations", "Operations Manager", "VP Operations",
    "Growth Head", "Marketing Head", "Digital Marketing Head",
    "Ecommerce Head", "Head of IT", "IT Manager", "Automation Head",
    "Plant Head", "Factory Manager", "Procurement Head",
    "CHRO", "CPO", "Chief People Officer",
    "HR Director", "Head of HR", "VP Human Resources",
]


# ── Core runner ───────────────────────────────────────────────────────────────

def _apify_run(actor_id: str, input_data: dict, timeout: int = 90) -> list:
    """
    POST to Apify run-sync-get-dataset-items.
    Returns list of result items, or [] on any failure.
    Raises RateLimitError on HTTP 429.
    """
    api_key = os.getenv("APIFY_API_KEY")
    if not api_key:
        return []

    actor_path = actor_id.replace("/", "~")
    url = f"{APIFY_BASE}/acts/{actor_path}/run-sync-get-dataset-items"

    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
            },
            json=input_data,
            timeout=timeout + 15,          # requests timeout > actor timeout
            params={"timeout": timeout, "memory": 512},
        )

        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, list) else []

        if resp.status_code == 429:
            raise RateLimitError("apify", "Apify rate limit or insufficient credits")

        # 400 often means bad input schema — log and continue
        print(f"  [WARN] Apify {actor_id}: HTTP {resp.status_code} — {resp.text[:120]}")
        return []

    except RateLimitError:
        raise
    except requests.exceptions.Timeout:
        print(f"  [WARN] Apify {actor_id}: actor timed out after {timeout}s")
        return []
    except Exception as e:
        print(f"  [WARN] Apify {actor_id}: {e}")
        return []


# ── Actor 1 — Decision-maker name + email extractor ───────────────────────────

def _find_via_decision_maker_actor(website: str, target_titles: list) -> dict:
    """
    Scrapes company website with NER to identify named decision-makers.
    Returns contact dict if a matching title is found, else {}.
    """
    if not website or not website.startswith("http"):
        return {}

    items = _apify_run(ACTOR_DECISION_MAKER, {
        "startUrls": [{"url": website}],
    }, timeout=90)

    # Try title-priority match first
    for priority_title in TITLE_PRIORITY:
        for item in items:
            raw_title = (
                item.get("jobTitle") or item.get("title") or
                item.get("role")    or item.get("position") or ""
            ).lower()
            if priority_title.lower() in raw_title:
                return _dm_item_to_contact(item, priority_title)

    # Any result is better than nothing
    if items:
        return _dm_item_to_contact(items[0])

    return {}


def _dm_item_to_contact(item: dict, title_hint: str = "") -> dict:
    name = (
        item.get("name") or item.get("fullName") or
        item.get("personName") or item.get("contactName") or ""
    ).strip()
    if not name:
        return {}
    return {
        "contact_name":  name,
        "contact_title": (
            item.get("jobTitle") or item.get("title") or
            item.get("role")    or item.get("position") or title_hint
        ),
        "email": (
            item.get("email") or item.get("emailAddress") or
            item.get("workEmail") or ""
        ),
        "phone": (
            item.get("phone") or item.get("phoneNumber") or
            item.get("mobilePhone") or ""
        ),
        "linkedin_url":   item.get("linkedinUrl") or item.get("linkedin") or "",
        "contact_source": "apify_decision_maker",
    }


# ── Actor 2 — LinkedIn company employees (no cookies) ────────────────────────

def _find_via_linkedin_employees(company_name: str, target_titles: list) -> dict:
    """
    Searches LinkedIn for employees of the company. No cookies required.
    Returns best title match with name + LinkedIn URL (no email in short mode).
    """
    items = _apify_run(ACTOR_LINKEDIN_EMP, {
        "company":    company_name,
        "searchMode": "short",
        "maxProfiles": 20,
        "location":   "India",
    }, timeout=80)

    for priority_title in TITLE_PRIORITY:
        for item in items:
            headline = (
                item.get("headline") or item.get("jobTitle") or
                item.get("title")    or item.get("occupation") or ""
            ).lower()
            if priority_title.lower() in headline:
                return _li_item_to_contact(item, priority_title)

    # Return first employee if no title match but target_titles has a match
    for item in items:
        headline = (
            item.get("headline") or item.get("jobTitle") or item.get("title") or ""
        ).lower()
        for t in (target_titles or []):
            if t.lower() in headline:
                return _li_item_to_contact(item, t)

    return {}


def _li_item_to_contact(item: dict, title_hint: str = "") -> dict:
    name = (
        item.get("fullName") or item.get("name") or
        item.get("firstName", "") + " " + item.get("lastName", "")
    ).strip()
    if not name:
        return {}
    return {
        "contact_name":  name,
        "contact_title": (
            item.get("headline") or item.get("jobTitle") or
            item.get("title")    or title_hint
        ),
        "email":          "",               # short mode doesn't include email
        "phone":          "",
        "linkedin_url":   (
            item.get("profileUrl") or item.get("url") or
            item.get("linkedinUrl") or ""
        ),
        "contact_source": "apify_linkedin",
    }


# ── Actor 3 — Website contact info scraper ────────────────────────────────────

def _find_via_contact_scraper(website: str) -> dict:
    """
    Scrapes all emails + phones publicly listed on the company homepage.
    Returns first usable email/phone even if generic (info@, hr@, etc.).
    """
    if not website or not website.startswith("http"):
        return {}

    items = _apify_run(ACTOR_CONTACT_INFO, {
        "startUrls": [{"url": website}],
    }, timeout=60)

    for item in items:
        # Actor may return emails as a list or a single string
        raw_emails = item.get("emails") or item.get("email") or []
        if isinstance(raw_emails, str):
            raw_emails = [raw_emails]

        raw_phones = (
            item.get("phones") or item.get("phoneNumbers") or
            item.get("phone")  or []
        )
        if isinstance(raw_phones, str):
            raw_phones = [raw_phones]

        # Filter junk
        emails = [
            e.strip() for e in raw_emails
            if isinstance(e, str) and "@" in e and "example" not in e.lower()
        ]
        phones = [
            p.strip() for p in raw_phones
            if isinstance(p, str) and len(p.strip()) >= 7
        ]

        if emails or phones:
            return {
                "contact_name":   "",
                "contact_title":  "",
                "email":          emails[0] if emails else "",
                "phone":          phones[0] if phones else "",
                "linkedin_url":   "",
                "contact_source": "apify_website",
            }

    return {}


# ── Main entry point ──────────────────────────────────────────────────────────

def find_contact_via_apify(
    company_name: str,
    website: str,
    target_titles: list,
) -> dict:
    """
    Orchestrate the three Apify actors in order of contact quality.
    Returns a contact dict (may be partial) or {} if APIFY_API_KEY not set.

    The caller (enricher.py) is responsible for merging with existing
    partial data and running email recovery (Hunter / pattern guess).
    """
    if not os.getenv("APIFY_API_KEY"):
        return {}

    # 1. Decision-maker extractor — best chance of name + email in one shot
    result = _find_via_decision_maker_actor(website, target_titles)
    if result.get("contact_name") and result.get("email"):
        print(f"  [Apify] decision-maker actor hit: {result['contact_name']}")
        return result

    # 2. LinkedIn employees — name + title + LinkedIn URL, usually no email
    li_result = _find_via_linkedin_employees(company_name, target_titles)
    if li_result.get("contact_name"):
        print(f"  [Apify] LinkedIn employees hit: {li_result['contact_name']}")
        # Merge: keep any email from step 1 if we already had partial data
        if result.get("contact_name"):
            result["linkedin_url"] = li_result.get("linkedin_url") or result.get("linkedin_url", "")
        else:
            result = li_result

    # 3. Website contact scraper — fills phone/email even if generic
    if not result.get("email") and not result.get("phone"):
        ws_result = _find_via_contact_scraper(website)
        if ws_result.get("email") or ws_result.get("phone"):
            print(f"  [Apify] website scraper hit: {ws_result.get('email') or ws_result.get('phone')}")
            result["email"] = result.get("email") or ws_result.get("email", "")
            result["phone"] = result.get("phone") or ws_result.get("phone", "")
            if not result.get("contact_source"):
                result["contact_source"] = "apify_website"

    return result
