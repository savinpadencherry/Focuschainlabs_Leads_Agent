"""
Per-company research bundle.

For each company we:
  1. Fetch the homepage (meta description + first paragraphs).
  2. Pull recent news via Serper.
  3. Pull tech-hiring signals via Serper.
  4. Pull Reddit chatter mentioning the company (pain-signal radar).
  5. Pull LinkedIn-indexed posts mentioning the company.

Every step is wrapped — one failed source never breaks the bundle.
"""

import requests
from datetime import datetime
from bs4 import BeautifulSoup

from agent.searcher import search_serper, search_reddit


def today() -> str:
    return datetime.today().strftime("%Y-%m-%d")


def research_company(company_name: str, website: str, snippet: str) -> dict:
    bundle = {
        "company_name":     company_name,
        "website":          website,
        "about":            "",
        "homepage_text":    "",
        "recent_news":      [],
        "tech_hiring":      [],
        "reddit_signals":   [],
        "linkedin_posts":   [],
        "raw_snippet":      snippet,
        "limited_research": False,
        "research_date":    today(),
    }

    # ── Homepage ───────────────────────────────────────────────────────────
    if website and website.startswith("http"):
        try:
            resp = requests.get(
                website,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=8,
            )
            soup = BeautifulSoup(resp.text, "html.parser")

            meta = soup.find("meta", {"name": "description"})
            bundle["about"] = (meta["content"][:300] if meta and meta.get("content") else "")

            paragraphs = soup.find_all("p")
            body = " ".join(
                p.get_text(strip=True) for p in paragraphs[:5]
                if len(p.get_text(strip=True)) > 40
            )
            bundle["homepage_text"] = body[:500]
        except Exception:
            bundle["limited_research"] = True

    year = datetime.today().year

    # ── Recent news ────────────────────────────────────────────────────────
    for query in [
        f"{company_name} news {year}",
        f"{company_name} funding OR CTO OR expansion OR launch {year}",
    ]:
        try:
            for r in search_serper(query)[:2]:
                bundle["recent_news"].append({
                    "title": r.get("snippet", "")[:200],
                    "date":  r.get("date_found", ""),
                })
        except Exception:
            pass

    # ── Tech hiring ────────────────────────────────────────────────────────
    try:
        jobs = search_serper(f"{company_name} hiring technology cloud data IT {year}")
        bundle["tech_hiring"] = [j.get("snippet", "")[:120] for j in jobs[:3]]
    except Exception:
        pass

    # ── Reddit chatter ─────────────────────────────────────────────────────
    try:
        for r in search_reddit(f'"{company_name}"')[:3]:
            bundle["reddit_signals"].append(r.get("snippet", "")[:200])
    except Exception:
        pass

    # ── LinkedIn-indexed posts ─────────────────────────────────────────────
    try:
        for r in search_serper(f'site:linkedin.com/posts "{company_name}"')[:3]:
            bundle["linkedin_posts"].append(r.get("snippet", "")[:200])
    except Exception:
        pass

    return bundle
