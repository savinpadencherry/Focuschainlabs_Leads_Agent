"""
Sources — Serper (Google), Tracxn, ProxyCurl, Naukri, Reddit.

Each function returns a list of normalised dicts the pipeline can merge:
  { company_name, website, snippet, signal_keyword, source, date_found }

Optional sources skip silently when their API key is missing.
"""

import os
import time
import requests
import re
from datetime import datetime
from bs4 import BeautifulSoup

from utils.rate_limiter import serper_limiter
from utils.exceptions import RateLimitError
from utils import budget


SERPER_URL = "https://google.serper.dev/search"


def today() -> str:
    return datetime.today().strftime("%Y-%m-%d")


def extract_company_name(title: str) -> str:
    """Best-effort extraction of a company name from a search result title."""
    raw = (title or "").strip()
    if not raw:
        return ""

    # Job result titles often read "Role at Company - LinkedIn".
    at_match = re.search(r"\bat\s+([^|–—·-]{2,80})", raw, flags=re.I)
    if at_match:
        candidate = at_match.group(1).strip(" :,-")
        if _looks_like_company(candidate):
            return candidate

    hiring_match = re.search(r"^(.{2,80}?)\s+hiring\b", raw, flags=re.I)
    if hiring_match:
        candidate = hiring_match.group(1).strip(" :,-")
        if _looks_like_company(candidate):
            return candidate

    title = raw
    for sep in [" - ", " | ", " – ", " · ", " — "]:
        if sep in title:
            title = title.split(sep)[0]
    return title.strip()


def _looks_like_company(value: str) -> bool:
    v = (value or "").strip().lower()
    if not v:
        return False
    if re.match(r"^\d+(\s|$)", v):
        return False
    if re.search(r"\b20\d{2}\b", v):
        return False
    bad = (
        "job", "jobs", "career", "careers", "vacancy", "vacancies",
        "hiring", "opening", "openings", "recruitment", "naukri",
        "linkedin", "indeed", "glassdoor",
    )
    article_markers = (
        "best ", "top ", "how to", "what is", "guide", "trends",
        "technology trends", "service providers", "solution providers",
        "companies in ", "list of", "market size", "report", "blog",
        "jobs in", " jobs", "expo", "exhibition", "conference",
        "biggest", "transforming", " sector", "course", "training",
    )
    role_markers = (
        "executive", "executives", "manager", "assistant", "associate",
        "officer", "intern", "engineer", "developer", "specialist",
        "coordinator", "consultant", "analyst",
    )
    if any(marker in v for marker in article_markers):
        return False
    if any(marker in v.split() for marker in role_markers):
        return False
    if len(v.split()) > 9:
        return False
    return not any(v == b or v.startswith(f"{b} ") for b in bad)


# ─── Serper (Google) ─────────────────────────────────────────────────────────
def search_serper_raw(keyword: str, num: int = 5) -> dict:
    """Returns the full Serper response including ads, knowledgeGraph, etc."""
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        return {}
    if not budget.allow("serper"):
        return {}
    serper_limiter.wait()
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    body = {"q": keyword, "gl": "in", "hl": "en", "num": num}
    try:
        response = requests.post(SERPER_URL, headers=headers, json=body, timeout=10)
        if response.status_code == 429:
            raise RateLimitError("serper", "Serper search quota reached")
        response.raise_for_status()
        return response.json()
    except RateLimitError:
        raise
    except Exception as e:
        print(f"  [WARN] Serper raw failed for '{keyword[:60]}': {e}")
        return {}


def search_serper(keyword: str, num: int = 10) -> list:
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        return []
    if not budget.allow("serper"):
        return []
    serper_limiter.wait()

    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    body = {"q": keyword, "gl": "in", "hl": "en", "num": num}

    try:
        response = requests.post(SERPER_URL, headers=headers, json=body, timeout=10)
        if response.status_code == 429:
            raise RateLimitError("serper", "Serper search quota reached")
        response.raise_for_status()
        results = response.json().get("organic", [])
        normalised = [
            {
                "company_name":   extract_company_name(r.get("title", "")),
                "website":        r.get("link", ""),
                "result_title":   r.get("title", ""),
                "snippet":        r.get("snippet", ""),
                "signal_keyword": keyword,
                "source":         "serper",
                "date_found":     today(),
            }
            for r in results if r.get("title")
        ]
        return [r for r in normalised if _looks_like_company(r.get("company_name", ""))]
    except RateLimitError:
        raise
    except Exception as e:
        print(f"  [WARN] Serper failed for '{keyword[:60]}': {e}")
        return []


# ─── Reddit (via Serper site:reddit.com) ─────────────────────────────────────
def search_reddit(query: str) -> list:
    """Reddit returns operator-rich pain-point posts when queried via Google."""
    if not os.getenv("SERPER_API_KEY"):
        return []

    q = query if "site:reddit.com" in query else f"site:reddit.com {query}"
    results = search_serper(q, num=6)
    for r in results:
        r["source"] = "reddit"
        r["signal_keyword"] = f"reddit:{query[:60]}"
    return results


# ─── Tracxn ─────────────────────────────────────────────────────────────────
def search_tracxn(icp: dict) -> list:
    if not os.getenv("TRACXN_API_KEY"):
        return []
    TRACXN_URL = "https://platform.tracxn.com/api/2.2/company/search"
    headers = {
        "accessToken": os.getenv("TRACXN_API_KEY"),
        "Content-Type": "application/json",
    }
    body = {
        "filters": {
            "location": icp.get("locations", ["Bangalore"]),
            "stage":    ["Series A", "Series B", "Series C", "Series D"],
            "sector":   icp.get("target_industries", []),
        },
        "pagination": {"start": 0, "rows": 25},
    }
    try:
        response = requests.post(TRACXN_URL, headers=headers, json=body, timeout=15)
        response.raise_for_status()
        companies = response.json().get("companies", [])
        return [
            {
                "company_name":   c.get("name", ""),
                "website":        c.get("website", ""),
                "snippet":        f"Funded — {c.get('stage', '')} — {c.get('sector', '')}",
                "signal_keyword": "funded_startup",
                "source":         "tracxn",
                "date_found":     today(),
            }
            for c in companies if c.get("name")
        ]
    except Exception as e:
        print(f"  [WARN] Tracxn failed: {e}")
        return []


# ─── ProxyCurl — SUNSET (May 2026) ───────────────────────────────────────────
# ProxyCurl has been discontinued. The team moved to NinjaPear (competitive
# intelligence), which does not offer a LinkedIn jobs endpoint. LinkedIn job
# signals are now sourced via Serper (site:linkedin.com/jobs queries) and
# Naukri. This stub exists so imports don't break; it always returns [].
def search_proxycurl_jobs(icp: dict) -> list:  # noqa: ARG001
    return []


# ─── Naukri (HTML scrape) ────────────────────────────────────────────────────
def search_naukri(icp: dict) -> list:
    results = []
    city = (icp.get("locations") or ["Bangalore"])[0].lower()
    titles = icp.get("target_titles", [])[:3] or ["Founder", "Head of Operations"]
    queries = ["+".join(t.split()) for t in titles]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }
    for query in queries:
        try:
            url = f"https://www.naukri.com/jobs-in-{city}?keyWord={query}"
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")
            company_tags = soup.select("a.comp-name") or soup.select("[class*='comp']")
            for tag in company_tags[:10]:
                name = tag.get_text(strip=True)
                if name and len(name) > 2:
                    results.append({
                        "company_name":   name,
                        "website":        "",
                        "snippet":        f"Hiring on Naukri: {query.replace('+', ' ')}",
                        "signal_keyword": f"naukri:{query[:30]}",
                        "source":         "naukri",
                        "date_found":     today(),
                    })
            time.sleep(2)
        except Exception as e:
            print(f"  [WARN] Naukri failed for '{query}': {e}")
            continue
    return results
