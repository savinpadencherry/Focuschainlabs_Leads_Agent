import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from agent.searcher import (
    search_serper, search_tracxn, search_proxycurl_jobs, search_naukri
)
from agent.researcher import research_company
from agent.scorer import score_company
from agent.enricher import enrich_contact
from agent.pitcher import generate_pitch
from utils.deduplicator import load_exclusion_list, deduplicate
from utils.excel_writer import write_leads_to_excel


def today() -> str:
    return datetime.today().strftime("%Y-%m-%d")


def run_pipeline_streaming(
    icp_config_path: str,
    exclusion_list_path: str = None,
    max_leads: int = None,
    override_industries: list = None,
    custom_focus: str = None,
):
    """
    Generator pipeline — yields progress events so callers can render live UI.
    Each event is a dict with at minimum a "type" key.
    """
    max_leads = max_leads or int(os.getenv("MAX_LEADS_PER_RUN", 10))
    threshold = int(os.getenv("MIN_SCORE_THRESHOLD", 60))
    pilot = os.getenv("PILOT_MODE", "true").lower() == "true"

    # ── Load ICP ──────────────────────────────────────────────────────────────
    with open(icp_config_path) as f:
        icp = json.load(f)

    if override_industries:
        icp = {**icp, "target_industries": override_industries}
    if custom_focus and custom_focus.strip():
        icp = {**icp, "custom_focus": custom_focus.strip()}

    yield {"type": "config_loaded", "icp": icp, "pilot": pilot, "threshold": threshold}

    # ── Stage 1: Search ────────────────────────────────────────────────────────
    all_results = []

    yield {"type": "source_start", "source": "serper", "label": "Google Search (Serper)"}
    serper_results = []
    if os.getenv("SERPER_API_KEY"):
        keywords = icp["trigger_keywords"]
        if pilot:
            keywords = keywords[:20]
        for kw in keywords:
            serper_results.extend(search_serper(kw))
            time.sleep(0.3)
        for title in icp["target_titles"][:3]:
            serper_results.extend(
                search_serper(f'site:linkedin.com/jobs "{title}" "Bangalore" 2026')
            )
            time.sleep(0.3)
        all_results.extend(serper_results)
        yield {"type": "source_done", "source": "serper",
               "count": len(serper_results), "status": "done"}
    else:
        yield {"type": "source_done", "source": "serper",
               "count": 0, "status": "skip", "reason": "API key not configured"}

    yield {"type": "source_start", "source": "tracxn", "label": "Tracxn — Funded Startups"}
    if os.getenv("TRACXN_API_KEY"):
        t_results = search_tracxn(icp)
        all_results.extend(t_results)
        yield {"type": "source_done", "source": "tracxn",
               "count": len(t_results), "status": "done"}
    else:
        yield {"type": "source_done", "source": "tracxn",
               "count": 0, "status": "skip", "reason": "Optional — add key to enable"}

    yield {"type": "source_start", "source": "proxycurl", "label": "LinkedIn Jobs (ProxyCurl)"}
    if os.getenv("PROXYCURL_API_KEY"):
        pc_results = search_proxycurl_jobs(icp)
        all_results.extend(pc_results)
        yield {"type": "source_done", "source": "proxycurl",
               "count": len(pc_results), "status": "done"}
    else:
        yield {"type": "source_done", "source": "proxycurl",
               "count": 0, "status": "skip", "reason": "Optional — add key to enable"}

    yield {"type": "source_start", "source": "naukri", "label": "Naukri Job Board (scraper)"}
    naukri_results = search_naukri(icp)
    all_results.extend(naukri_results)
    if naukri_results:
        yield {"type": "source_done", "source": "naukri",
               "count": len(naukri_results), "status": "done"}
    else:
        yield {"type": "source_done", "source": "naukri",
               "count": 0, "status": "warn", "reason": "Site may block automated access"}

    # Dedup
    seen: set = set()
    unique = []
    for r in all_results:
        key = r["company_name"].lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(r)

    exclusion = load_exclusion_list(exclusion_list_path)
    companies = deduplicate(unique, exclusion)
    companies = companies[: max_leads * 3]

    yield {"type": "search_done",
           "raw": len(all_results), "unique": len(unique), "to_research": len(companies)}

    if not companies:
        yield {
            "type": "final", "leads": [], "output_path": None,
            "stats": {"total_leads": 0, "total_researched": 0,
                      "qualified_count": 0, "avg_score": 0,
                      "top_score": 0, "qualification_rate": "0%"},
            "error": "No companies found. Configure at least SERPER_API_KEY to start."
        }
        return

    # ── Stage 2: Research ──────────────────────────────────────────────────────
    yield {"type": "stage_start", "stage": "research", "total": len(companies)}

    researched = []
    for i, company in enumerate(companies):
        yield {"type": "research_progress",
               "idx": i + 1, "total": len(companies), "company": company["company_name"]}
        bundle = research_company(
            company["company_name"],
            company.get("website", ""),
            company.get("snippet", "")
        )
        researched.append({**company, **bundle})

    yield {"type": "stage_done", "stage": "research"}

    # ── Stage 3: Score ─────────────────────────────────────────────────────────
    yield {"type": "stage_start", "stage": "score", "total": len(researched)}

    scored = []
    for i, company in enumerate(researched):
        yield {"type": "score_progress",
               "idx": i + 1, "total": len(researched), "company": company["company_name"]}
        score_result = score_company(company, icp)
        merged = {**company, **score_result}
        scored.append(merged)
        yield {
            "type": "score_result",
            "company": company["company_name"],
            "score": score_result.get("total_score", 0),
            "qualify": score_result.get("qualify", False),
            "signal": score_result.get("primary_signal", ""),
        }

    qualified = [c for c in scored if c.get("qualify")]
    yield {"type": "stage_done", "stage": "score",
           "qualified": len(qualified), "total": len(scored)}

    # ── Stage 4: Enrich ────────────────────────────────────────────────────────
    enrich_cap = 5 if pilot else max_leads
    to_enrich = qualified[: min(max_leads, enrich_cap)]

    yield {"type": "stage_start", "stage": "enrich", "total": len(to_enrich)}

    enriched = []
    for i, company in enumerate(to_enrich):
        yield {"type": "enrich_progress",
               "idx": i + 1, "total": len(to_enrich), "company": company["company_name"]}
        contact = enrich_contact(
            company["company_name"], icp["target_titles"], icp["locations"][0]
        )
        enriched.append({**company, **contact, **icp})
        yield {"type": "enrich_result",
               "company": company["company_name"],
               "status": contact.get("enrichment_status", "not_found")}

    yield {"type": "stage_done", "stage": "enrich"}

    # ── Stage 5: Pitch ─────────────────────────────────────────────────────────
    yield {"type": "stage_start", "stage": "pitch", "total": len(enriched)}

    final_leads = []
    for i, lead in enumerate(enriched):
        yield {"type": "pitch_progress",
               "idx": i + 1, "total": len(enriched), "company": lead["company_name"]}
        lead["opening_line"] = generate_pitch(lead)
        final_leads.append(lead)

    yield {"type": "stage_done", "stage": "pitch"}

    # Fallback: write partial results if nothing cleared enrichment
    if not final_leads and scored:
        for company in scored[:max_leads]:
            company.update({
                "contact_name": "Manual lookup needed",
                "contact_title": "Manual lookup needed",
                "email": "Manual lookup needed",
                "linkedin_url": "Manual lookup needed",
                "opening_line": "",
                **icp,
            })
            final_leads.append(company)

    # ── Write Excel ────────────────────────────────────────────────────────────
    timestamp = datetime.today().strftime("%Y-%m-%d_%H%M")
    output_path = f"output/leads_{timestamp}.xlsx"
    write_leads_to_excel(final_leads, output_path)

    scores = [lead.get("total_score", 0) for lead in final_leads]
    avg_score = sum(scores) / max(len(scores), 1)

    yield {
        "type": "final",
        "leads": final_leads,
        "output_path": output_path,
        "stats": {
            "total_leads": len(final_leads),
            "total_researched": len(researched),
            "qualified_count": len(qualified),
            "avg_score": round(avg_score, 1),
            "top_score": max(scores) if scores else 0,
            "qualification_rate": f"{int(len(qualified) / max(len(researched), 1) * 100)}%",
        },
    }


def run_pipeline(
    icp_config_path: str,
    exclusion_list_path: str = None,
    max_leads: int = None,
) -> str:
    """Synchronous wrapper — collects streaming events and returns the output path."""
    output_path = None
    pilot = os.getenv("PILOT_MODE", "true").lower() == "true"

    if pilot:
        print("=" * 50)
        print("  PILOT MODE — costs capped to free tiers")
        print("=" * 50)

    for event in run_pipeline_streaming(icp_config_path, exclusion_list_path, max_leads):
        t = event.get("type", "")
        if t == "config_loaded":
            icp = event["icp"]
            print(f"\n[ICP] {icp.get('vertical')} | {icp.get('client')}")
        elif t == "source_done":
            print(f"  [{event['source']}] {event['status']} — {event.get('count', 0)} results")
        elif t == "search_done":
            print(f"\n[SEARCH] {event['to_research']} companies to research")
        elif t == "stage_start":
            print(f"\n[STAGE] {event['stage'].upper()} — {event.get('total', 0)} items")
        elif t == "score_result":
            q = "✓" if event["qualify"] else "✗"
            print(f"  {q} {event['company']} — {event['score']}/100")
        elif t == "stage_done" and event.get("stage") == "score":
            print(f"\n  Qualified: {event.get('qualified', 0)}/{event.get('total', 0)}")
        elif t == "final":
            output_path = event.get("output_path")
            stats = event.get("stats", {})
            print(f"\n{'=' * 50}")
            print(f"  DONE  |  Leads: {stats.get('total_leads')}  |  "
                  f"Avg score: {stats.get('avg_score')}  |  Output: {output_path}")
            print(f"{'=' * 50}\n")

    return output_path


if __name__ == "__main__":
    run_pipeline(
        icp_config_path="config/icp_digital_transformation.json",
        exclusion_list_path=None,
    )
