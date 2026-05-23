import requests
from datetime import datetime
from bs4 import BeautifulSoup

from agent.searcher import search_serper


def today() -> str:
    return datetime.today().strftime("%Y-%m-%d")


def research_company(company_name: str, website: str, snippet: str) -> dict:
    """Build a research bundle for one company."""

    bundle = {
        "company_name": company_name,
        "website": website,
        "about": "",
        "homepage_text": "",
        "recent_news": [],
        "tech_hiring": [],
        "raw_snippet": snippet,
        "limited_research": False,
        "research_date": today()
    }

    # Step 1: Fetch homepage
    if website and website.startswith("http"):
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(website, headers=headers, timeout=8)
            soup = BeautifulSoup(resp.text, "html.parser")

            # Meta description
            meta = soup.find("meta", {"name": "description"})
            bundle["about"] = meta["content"][:300] if meta else ""

            # First meaningful paragraph
            paragraphs = soup.find_all("p")
            body_text = " ".join(
                p.get_text(strip=True) for p in paragraphs[:5]
                if len(p.get_text(strip=True)) > 40
            )
            bundle["homepage_text"] = body_text[:500]

        except Exception:
            bundle["limited_research"] = True

    # Step 2: Recent news via Serper
    for query in [
        f"{company_name} news 2026",
        f"{company_name} funding OR CTO OR expansion OR technology 2026"
    ]:
        try:
            results = search_serper(query)
            for r in results[:2]:
                bundle["recent_news"].append({
                    "title": r.get("snippet", "")[:200],
                    "date": r.get("date_found", "")
                })
        except Exception:
            pass

    # Step 3: Tech hiring signals via Serper
    try:
        jobs = search_serper(
            f"{company_name} hiring technology cloud data IT 2026"
        )
        bundle["tech_hiring"] = [
            j.get("snippet", "")[:100] for j in jobs[:3]
        ]
    except Exception:
        pass

    return bundle
