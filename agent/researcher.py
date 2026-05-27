"""
Per-company research bundle.

For each company we:
  1. Fetch homepage (meta description + first paragraphs).
  2. Pull recent news via Serper (with source URLs).
  3. Pull tech/hiring signals via Serper.
  4. Pull Reddit chatter (pain-signal radar).
  5. Pull LinkedIn-indexed posts.
  6. Detect ad activity — Google Ads brand search + tracking pixels on homepage.
  7. Build a structured evidence list: category, observation, url, strength.

Every step is wrapped — one failed source never breaks the bundle.
"""

import os
import requests
from datetime import datetime
from bs4 import BeautifulSoup

from agent.searcher import search_serper, search_reddit, search_serper_raw


def today() -> str:
    return datetime.today().strftime("%Y-%m-%d")


# Ad/analytics trackers we look for on the homepage HTML
_AD_TRACKERS = {
    "Google Ads":       ["googleadservices.com", "google_ad_client", "gtag('config'", "adwords"],
    "Facebook/Meta":    ["fbq(", "connect.facebook.net", "facebook.com/tr"],
    "LinkedIn Ads":     ["snap.licdn.com", "linkedin.com/insight"],
    "Hotjar/Clarity":   ["hotjar.com/c/hotjar", "clarity.ms"],
    "Google Analytics": ["googletagmanager.com", "google-analytics.com"],
}


def _detect_ad_activity(company_name: str, website: str) -> dict:
    """
    Two-pass ad detection:
      1. Brand-name Google search → inspect the Serper 'ads' array.
      2. Homepage HTML scan for known ad/analytics tracking pixels.
    Returns {running_ads: bool, ad_signals: [str]}.
    """
    signals = []

    # Pass 1 — Google Ads (brand search via Serper)
    if os.getenv("SERPER_API_KEY"):
        try:
            data = search_serper_raw(f'"{company_name}"', num=5)
            domain = ""
            if website:
                domain = website.replace("https://", "").replace("http://", "").split("/")[0]
            for ad in data.get("ads", []):
                title = ad.get("title", "")
                link  = ad.get("link", "")
                if company_name.lower() in title.lower() or (domain and domain in link):
                    signals.append(f"Running own Google Ads — '{title}'")
                else:
                    signals.append(f"Competitor ads on brand search — '{title}'")
        except Exception:
            pass

    # Pass 2 — Tracking pixels on homepage
    if website and website.startswith("http"):
        try:
            resp = requests.get(website, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
            html = resp.text.lower()
            for platform, keywords in _AD_TRACKERS.items():
                if any(k.lower() in html for k in keywords):
                    signals.append(f"Ad/tracking pixel present: {platform}")
        except Exception:
            pass

    return {"running_ads": bool(signals), "ad_signals": signals[:5]}


def _collect_evidence(bundle: dict, website: str) -> list:
    """
    Aggregate all research signals into a structured list:
      [{"category", "observation", "url", "strength"}, ...]

    Strength tiers:
      high   — paid ads, active hiring, funding news
      medium — news mention, LinkedIn post, Reddit chatter
    """
    items = []

    # Paid-ad signals (highest priority)
    for ad in bundle.get("ad_signals", []):
        items.append({
            "category":    "paid_ads",
            "observation": ad,
            "url":         website or "",
            "strength":    "high",
        })

    # Hiring signals
    for snippet in bundle.get("tech_hiring", []):
        if snippet:
            items.append({
                "category":    "hiring",
                "observation": snippet[:200],
                "url":         "",
                "strength":    "high",
            })

    # Recent news (with source URL)
    for news in bundle.get("recent_news", []):
        obs = (news.get("title") or news.get("snippet", "")).strip()
        if obs:
            items.append({
                "category":    "news",
                "observation": obs[:200],
                "url":         news.get("url", ""),
                "strength":    "medium",
            })

    # LinkedIn posts
    for post in bundle.get("linkedin_posts", []):
        if post:
            items.append({
                "category":    "linkedin",
                "observation": post[:200],
                "url":         "",
                "strength":    "medium",
            })

    # Reddit / community
    for signal in bundle.get("reddit_signals", []):
        if signal:
            items.append({
                "category":    "community",
                "observation": signal[:200],
                "url":         "",
                "strength":    "medium",
            })

    # High-strength items first, cap at 8
    items.sort(key=lambda x: 0 if x["strength"] == "high" else 1)
    return items[:8]


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
        "running_ads":      False,
        "ad_signals":       [],
        "evidence":         [],
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

    # ── Recent news (store URL alongside snippet) ──────────────────────────
    for query in [
        f"{company_name} news {year}",
        f"{company_name} funding OR CTO OR expansion OR launch {year}",
    ]:
        try:
            for r in search_serper(query)[:2]:
                bundle["recent_news"].append({
                    "title": r.get("snippet", "")[:200],
                    "url":   r.get("website", ""),
                    "date":  r.get("date_found", ""),
                })
        except Exception:
            pass

    # ── Tech / hiring signals ──────────────────────────────────────────────
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

    # ── Ad activity detection ──────────────────────────────────────────────
    try:
        ad = _detect_ad_activity(company_name, website)
        bundle["running_ads"] = ad["running_ads"]
        bundle["ad_signals"]  = ad["ad_signals"]
    except Exception:
        pass

    # ── Structured evidence ────────────────────────────────────────────────
    bundle["evidence"] = _collect_evidence(bundle, website)

    return bundle
