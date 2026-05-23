import os
import time
import requests
from datetime import datetime
from bs4 import BeautifulSoup

from utils.rate_limiter import serper_limiter

SERPER_URL = "https://google.serper.dev/search"


def today() -> str:
    return datetime.today().strftime("%Y-%m-%d")


def extract_company_name(title: str) -> str:
    """Best-effort extraction of a company name from a search result title."""
    # Strip common suffixes like " - LinkedIn", " | Crunchbase", etc.
    for sep in [" - ", " | ", " – ", " · "]:
        if sep in title:
            title = title.split(sep)[0]
    return title.strip()


def search_serper(keyword: str) -> list:
    serper_limiter.wait()
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        print("  [SKIP] Serper API key not set")
        return []
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json"
    }
    body = {"q": keyword, "gl": "in", "hl": "en", "num": 10}
    try:
        response = requests.post(SERPER_URL, headers=headers, json=body, timeout=10)
        response.raise_for_status()
        results = response.json().get("organic", [])
        return [
            {
                "company_name": extract_company_name(r.get("title", "")),
                "website": r.get("link", ""),
                "snippet": r.get("snippet", ""),
                "signal_keyword": keyword,
                "source": "serper",
                "date_found": today()
            }
            for r in results if r.get("title")
        ]
    except Exception as e:
        print(f"  [WARN] Serper search failed for '{keyword}': {e}")
        return []


def search_tracxn(icp: dict) -> list:
    if not os.getenv("TRACXN_API_KEY"):
        print("  [SKIP] Tracxn API key not set")
        return []
    TRACXN_URL = "https://platform.tracxn.com/api/2.2/company/search"
    headers = {
        "accessToken": os.getenv("TRACXN_API_KEY"),
        "Content-Type": "application/json"
    }
    body = {
        "filters": {
            "location": icp["locations"],
            "stage": ["Series A", "Series B", "Series C", "Series D"],
            "sector": icp["target_industries"]
        },
        "pagination": {"start": 0, "rows": 25}
    }
    try:
        response = requests.post(TRACXN_URL, headers=headers, json=body, timeout=15)
        response.raise_for_status()
        companies = response.json().get("companies", [])
        return [
            {
                "company_name": c.get("name", ""),
                "website": c.get("website", ""),
                "snippet": f"Funded startup — {c.get('stage', '')} — {c.get('sector', '')}",
                "signal_keyword": "funded_startup",
                "source": "tracxn",
                "date_found": today()
            }
            for c in companies if c.get("name")
        ]
    except Exception as e:
        print(f"  [WARN] Tracxn search failed: {e}")
        return []


def search_proxycurl_jobs(icp: dict) -> list:
    if not os.getenv("PROXYCURL_API_KEY"):
        print("  [SKIP] ProxyCurl API key not set")
        return []
    PROXYCURL_JOBS_URL = "https://nubela.co/proxycurl/api/v2/linkedin/company/job"
    headers = {"Authorization": f"Bearer {os.getenv('PROXYCURL_API_KEY')}"}
    results = []
    for title in icp["target_titles"][:3]:
        try:
            params = {
                "keyword": f"{title} digital transformation",
                "location": "Bangalore, Karnataka, India",
                "job_type": "full-time"
            }
            response = requests.get(
                PROXYCURL_JOBS_URL, headers=headers, params=params, timeout=15
            )
            response.raise_for_status()
            for job in response.json().get("job", []):
                results.append({
                    "company_name": job.get("company", {}).get("name", ""),
                    "website": job.get("company", {}).get("url", ""),
                    "snippet": f"Actively hiring: {job.get('title', '')}",
                    "signal_keyword": f"linkedin_job_{title}",
                    "source": "proxycurl",
                    "date_found": today()
                })
        except Exception as e:
            print(f"  [WARN] ProxyCurl search failed for title '{title}': {e}")
            continue
    return results


def search_naukri(icp: dict) -> list:
    results = []
    queries = [
        "digital+transformation+head+of+IT+Bangalore",
        "CTO+CIO+Bangalore+technology",
        "cloud+architect+data+engineering+Bangalore"
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36"
    }
    for query in queries:
        try:
            url = f"https://www.naukri.com/jobs-in-bangalore?keyWord={query}"
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")
            company_tags = soup.select("a.comp-name") or soup.select("[class*='comp']")
            for tag in company_tags[:10]:
                name = tag.get_text(strip=True)
                if name and len(name) > 2:
                    results.append({
                        "company_name": name,
                        "website": "",
                        "snippet": f"Hiring on Naukri: {query.replace('+', ' ')}",
                        "signal_keyword": f"naukri_{query[:30]}",
                        "source": "naukri",
                        "date_found": today()
                    })
            time.sleep(2)  # polite delay
        except Exception as e:
            print(f"  [WARN] Naukri scrape failed for {query}: {e}")
            continue
    return results


def search_all_sources(icp: dict) -> list:
    all_results = []
    pilot = os.getenv("PILOT_MODE", "true").lower() == "true"

    print("  Searching Serper (Google)...")
    keywords = icp["trigger_keywords"]
    if pilot:
        keywords = keywords[:20]  # cap to free tier limit in pilot mode
    for keyword in keywords:
        all_results.extend(search_serper(keyword))
        time.sleep(0.5)

    # Also search job listings for target titles
    for title in icp["target_titles"][:3]:
        query = f'site:linkedin.com/jobs "{title}" "Bangalore" 2026'
        all_results.extend(search_serper(query))
        time.sleep(0.5)

    print("  Searching Tracxn (funded startups)...")
    all_results.extend(search_tracxn(icp))

    print("  Searching ProxyCurl (LinkedIn jobs)...")
    all_results.extend(search_proxycurl_jobs(icp))

    print("  Searching Naukri (Indian job boards)...")
    all_results.extend(search_naukri(icp))

    # Deduplicate by company_name (case-insensitive)
    seen = set()
    unique = []
    for r in all_results:
        key = r["company_name"].lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(r)

    print(f"  Total unique companies found: {len(unique)}")
    return unique
