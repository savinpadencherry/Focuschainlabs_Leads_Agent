"""
Streaming lead-generation pipeline.

Flow:
  user prompt + base ICP
    └─ planner       (Gemini turns prompt → search plan)
    └─ search        (Serper / Reddit / Tracxn / ProxyCurl / Naukri)
    └─ dedupe        (exclusion list + lowercase name set)
    └─ research      (homepage + news + reddit + linkedin per company)
    └─ score         (Gemini → 0-100 with sub-scores)
    └─ enrich        (Apollo → contact + contact's recent posts)
    └─ pitch         (Gemini → 1-line opening)
    └─ excel         (ranked, colour-coded, frozen header)

Two public functions:
  - run_pipeline_streaming(...) yields typed event dicts for live UIs
  - run_pipeline(...) is a sync wrapper that prints + returns the output path
"""

import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from agent.searcher import (
    search_serper, search_tracxn, search_proxycurl_jobs, search_naukri, search_reddit
)
from agent.researcher import research_company
from agent.scorer import score_company
from agent.enricher import enrich_contact
from agent.pitcher import generate_pitch_bundle
from agent.planner import plan_search
from utils.deduplicator import load_exclusion_list, deduplicate
from utils.excel_writer import write_leads_to_excel
from utils.exceptions import RateLimitError


def today() -> str:
    return datetime.today().strftime("%Y-%m-%d")


def run_pipeline_streaming(
    icp_config_path: str,
    exclusion_list_path: str = None,
    max_leads: int = None,
    override_industries: list = None,
    override_locations: list = None,
    override_titles: list = None,
    custom_focus: str = None,
    user_prompt: str = None,
):
    """Generator pipeline — yields typed events for live UIs."""

    max_leads = max_leads or int(os.getenv("MAX_LEADS_PER_RUN", 30))
    threshold = int(os.getenv("MIN_SCORE_THRESHOLD", 60))
    pilot     = os.getenv("PILOT_MODE", "true").lower() == "true"

    # ── Load base ICP ──────────────────────────────────────────────────────
    with open(icp_config_path) as f:
        icp = json.load(f)

    if override_industries:
        icp["target_industries"] = override_industries
    if override_locations:
        icp["locations"] = override_locations
    if override_titles:
        icp["target_titles"] = override_titles
    if custom_focus and custom_focus.strip():
        icp["custom_focus"] = custom_focus.strip()

    yield {"type": "config_loaded", "icp": icp, "pilot": pilot, "threshold": threshold}

    # ── Stage 0: Plan ──────────────────────────────────────────────────────
    yield {"type": "stage_start", "stage": "plan", "total": 1}

    plan = plan_search(user_prompt or custom_focus or "", icp)
    icp.update({
        "target_industries":  plan.get("industries")    or icp.get("target_industries"),
        "locations":          plan.get("locations")     or icp.get("locations"),
        "target_titles":      plan.get("target_titles") or icp.get("target_titles"),
        "trigger_keywords":   plan.get("trigger_keywords") or icp.get("trigger_keywords"),
        "pain_hypothesis":    plan.get("pain_hypothesis", ""),
        "gap_hypothesis":     plan.get("gap_hypothesis", ""),
        "custom_focus":       plan.get("custom_focus")  or icp.get("custom_focus", ""),
    })
    yield {"type": "plan_ready", "plan": plan}
    yield {"type": "stage_done", "stage": "plan"}

    # ── Stage 1: Search ────────────────────────────────────────────────────
    all_results = []

    # Serper — main keyword sweep
    yield {"type": "source_start", "source": "serper", "label": "Google Search (Serper)"}
    serper_results = []
    if os.getenv("SERPER_API_KEY"):
        kws = icp["trigger_keywords"]
        if pilot:
            kws = kws[:20]
        for kw in kws:
            yield {"type": "keyword_searching", "keyword": kw[:80], "source": "serper"}
            try:
                kw_results = search_serper(kw)
            except RateLimitError as e:
                yield {"type": "rate_limit", "service": e.service, "message": str(e), "stage": "search"}
                yield {"type": "source_done", "source": "serper", "count": len(serper_results), "status": "rate_limited"}
                kw_results = []
                break
            serper_results.extend(kw_results)
            yield {"type": "keyword_done", "keyword": kw[:80], "count": len(kw_results), "source": "serper"}
            time.sleep(0.25)
        for q in plan.get("linkedin_queries", [])[:3]:
            yield {"type": "keyword_searching", "keyword": q[:80], "source": "linkedin"}
            try:
                q_results = search_serper(q)
            except RateLimitError as e:
                yield {"type": "rate_limit", "service": e.service, "message": str(e), "stage": "search"}
                q_results = []
                break
            serper_results.extend(q_results)
            yield {"type": "keyword_done", "keyword": q[:80], "count": len(q_results), "source": "linkedin"}
            time.sleep(0.25)
        all_results.extend(serper_results)
        yield {"type": "source_done", "source": "serper",
               "count": len(serper_results), "status": "done"}
    else:
        yield {"type": "source_done", "source": "serper",
               "count": 0, "status": "skip", "reason": "API key not configured"}

    # Reddit — pain-signal sweep
    yield {"type": "source_start", "source": "reddit",
           "label": "Reddit (pain signals via Google)"}
    reddit_results = []
    if os.getenv("SERPER_API_KEY"):
        for q in plan.get("reddit_queries", [])[:3]:
            yield {"type": "keyword_searching", "keyword": q[:80], "source": "reddit"}
            q_results = search_reddit(q)
            reddit_results.extend(q_results)
            yield {"type": "keyword_done", "keyword": q[:80], "count": len(q_results), "source": "reddit"}
            time.sleep(0.25)
        all_results.extend(reddit_results)
        yield {"type": "source_done", "source": "reddit",
               "count": len(reddit_results), "status": "done"}
    else:
        yield {"type": "source_done", "source": "reddit",
               "count": 0, "status": "skip", "reason": "Needs Serper key"}

    # Tracxn
    yield {"type": "source_start", "source": "tracxn", "label": "Tracxn — Funded Startups"}
    if os.getenv("TRACXN_API_KEY"):
        t = search_tracxn(icp)
        all_results.extend(t)
        yield {"type": "source_done", "source": "tracxn", "count": len(t), "status": "done"}
    else:
        yield {"type": "source_done", "source": "tracxn",
               "count": 0, "status": "skip", "reason": "Optional — add key to enable"}

    # ProxyCurl — sunset May 2026, always skip
    yield {"type": "source_done", "source": "proxycurl",
           "count": 0, "status": "skip", "reason": "Sunset — replaced by Naukri + Serper"}

    # Naukri
    yield {"type": "source_start", "source": "naukri", "label": "Naukri Job Board (scraper)"}
    yield {"type": "keyword_searching", "keyword": "Naukri job board scrape", "source": "naukri"}
    nk = search_naukri(icp)
    all_results.extend(nk)
    yield {
        "type": "source_done", "source": "naukri", "count": len(nk),
        "status": "done" if nk else "warn",
        "reason": None if nk else "Site may block automated access",
    }

    # ── Dedupe ─────────────────────────────────────────────────────────────
    seen, unique = set(), []
    for r in all_results:
        key = (r.get("company_name") or "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(r)

    exclusion = load_exclusion_list(exclusion_list_path)
    companies = deduplicate(unique, exclusion)
    companies = companies[: max_leads * 4]

    yield {"type": "search_done",
           "raw": len(all_results), "unique": len(unique),
           "to_research": len(companies)}

    if not companies:
        yield {
            "type": "final", "leads": [], "output_path": None,
            "plan": plan,
            "stats": {"total_leads": 0, "total_researched": 0,
                      "qualified_count": 0, "avg_score": 0,
                      "top_score": 0, "qualification_rate": "0%"},
            "error": "No companies found. At minimum, set SERPER_API_KEY.",
        }
        return

    # ── Stage 2: Research ──────────────────────────────────────────────────
    yield {"type": "stage_start", "stage": "research", "total": len(companies)}
    researched = []
    for i, company in enumerate(companies):
        yield {"type": "research_progress",
               "idx": i + 1, "total": len(companies),
               "company": company["company_name"]}
        bundle = research_company(
            company["company_name"],
            company.get("website", ""),
            company.get("snippet", ""),
            icp.get("target_titles", []),
        )
        researched.append({**company, **bundle})
        yield {"type": "company_researched",
               "company": company["company_name"],
               "website": company.get("website", ""),
               "ad_detected": bundle.get("running_ads", False),
               "evidence_count": len(bundle.get("evidence", []))}
    yield {"type": "stage_done", "stage": "research"}

    # ── Stage 3: Score ─────────────────────────────────────────────────────
    yield {"type": "stage_start", "stage": "score", "total": len(researched)}
    scored = []
    for i, company in enumerate(researched):
        yield {"type": "score_progress",
               "idx": i + 1, "total": len(researched),
               "company": company["company_name"]}
        try:
            result = score_company(company, icp)
        except RateLimitError as e:
            yield {"type": "rate_limit", "service": e.service, "message": str(e), "stage": "score"}
            result = {"total_score": 0, "qualify": False, "primary_signal": "", "error": "rate_limited"}
        merged = {**company, **result}
        scored.append(merged)
        yield {
            "type": "score_result",
            "company": company["company_name"],
            "score":   result.get("total_score", 0),
            "qualify": result.get("qualify", False),
            "signal":  result.get("primary_signal", ""),
        }

    scored_sorted = sorted(scored, key=lambda x: x.get("total_score", 0), reverse=True)
    qualified = [c for c in scored_sorted if c.get("qualify")]
    yield {"type": "stage_done", "stage": "score",
           "qualified": len(qualified), "total": len(scored)}

    selected_for_output = qualified[:max_leads]
    if len(selected_for_output) < max_leads:
        selected_names = {
            (c.get("company_name") or "").lower().strip()
            for c in selected_for_output
        }
        for company in scored_sorted:
            key = (company.get("company_name") or "").lower().strip()
            if key not in selected_names:
                selected_for_output.append(company)
                selected_names.add(key)
            if len(selected_for_output) >= max_leads:
                break

    # ── Stage 4: Enrich ────────────────────────────────────────────────────
    enrich_cap = min(max_leads, int(os.getenv("APOLLO_ENRICH_CAP", max_leads)))
    to_enrich = selected_for_output[: min(max_leads, enrich_cap)]
    yield {"type": "stage_start", "stage": "enrich", "total": len(to_enrich)}

    enriched = []
    enriched_names = set()
    for i, company in enumerate(to_enrich):
        yield {"type": "enrich_progress",
               "idx": i + 1, "total": len(to_enrich),
               "company": company["company_name"]}
        contact = enrich_contact(
            company["company_name"],
            icp["target_titles"],
            icp["locations"][0],
            website=company.get("website", ""),
        )
        enriched.append({**company, **contact, **icp})
        enriched_names.add((company.get("company_name") or "").lower().strip())
        yield {"type": "enrich_result",
               "company": company["company_name"],
               "status":  contact.get("enrichment_status", "not_found")}
    yield {"type": "stage_done", "stage": "enrich"}

    for company in selected_for_output:
        key = (company.get("company_name") or "").lower().strip()
        if key in enriched_names:
            continue
        company.update({
            "contact_name":      "",
            "contact_title":     company.get("responsible_owner", ""),
            "email":             "",
            "phone":             "",
            "enrichment_status": "not_found",
            **icp,
        })
        enriched.append(company)

    # ── Stage 5: Pitch ─────────────────────────────────────────────────────
    yield {"type": "stage_start", "stage": "pitch", "total": len(enriched)}
    final_leads = []
    for i, lead in enumerate(enriched):
        yield {"type": "pitch_progress",
               "idx": i + 1, "total": len(enriched),
               "company": lead["company_name"]}
        try:
            bundle = generate_pitch_bundle(lead)
        except RateLimitError as e:
            yield {"type": "rate_limit", "service": e.service,
                   "message": str(e), "stage": "pitch"}
            bundle = {"opening_line": "", "outreach_note": "", "reason_to_reach": ""}
        lead["opening_line"]    = bundle["opening_line"]
        lead["outreach_note"]   = bundle["outreach_note"]
        lead["reason_to_reach"] = bundle["reason_to_reach"]
        final_leads.append(lead)
    yield {"type": "stage_done", "stage": "pitch"}

    # ── Write Excel ────────────────────────────────────────────────────────
    timestamp   = datetime.today().strftime("%Y-%m-%d_%H%M")
    output_path = f"output/leads_{timestamp}.xlsx"
    write_leads_to_excel(final_leads, output_path)

    scores    = [lead.get("total_score", 0) for lead in final_leads]
    avg_score = sum(scores) / max(len(scores), 1)

    yield {
        "type": "final",
        "leads": final_leads,
        "output_path": output_path,
        "plan": plan,
        "stats": {
            "total_leads":        len(final_leads),
            "total_researched":   len(researched),
            "qualified_count":    len(qualified),
            "avg_score":          round(avg_score, 1),
            "top_score":          max(scores) if scores else 0,
            "qualification_rate": f"{int(len(qualified) / max(len(researched), 1) * 100)}%",
        },
    }


def run_pipeline(
    icp_config_path: str,
    exclusion_list_path: str = None,
    max_leads: int = None,
    user_prompt: str = None,
) -> str:
    """Synchronous wrapper for CLI usage. Returns the output path."""
    output_path = None
    pilot = os.getenv("PILOT_MODE", "true").lower() == "true"

    if pilot:
        print("=" * 50)
        print("  PILOT MODE — costs capped to free tiers")
        print("=" * 50)

    for ev in run_pipeline_streaming(
        icp_config_path, exclusion_list_path, max_leads, user_prompt=user_prompt
    ):
        t = ev.get("type", "")
        if t == "config_loaded":
            icp = ev["icp"]
            print(f"\n[ICP] {icp.get('vertical')} | {icp.get('client')}")
        elif t == "plan_ready":
            p = ev["plan"]
            print(f"[PLAN] industries={p.get('industries')}  "
                  f"keywords={len(p.get('trigger_keywords', []))}")
        elif t == "source_done":
            print(f"  [{ev['source']}] {ev['status']} — {ev.get('count', 0)} results")
        elif t == "search_done":
            print(f"\n[SEARCH] {ev['to_research']} companies to research")
        elif t == "stage_start":
            print(f"\n[STAGE] {ev['stage'].upper()} — {ev.get('total', 0)} items")
        elif t == "score_result":
            q = "QF" if ev["qualify"] else "NQ"
            print(f"  {q} {ev['company']} — {ev['score']}/100")
        elif t == "stage_done" and ev.get("stage") == "score":
            print(f"\n  Qualified: {ev.get('qualified', 0)}/{ev.get('total', 0)}")
        elif t == "final":
            output_path = ev.get("output_path")
            stats = ev.get("stats", {})
            print(f"\n{'=' * 50}")
            print(f"  DONE  |  Leads: {stats.get('total_leads')}  |  "
                  f"Avg: {stats.get('avg_score')}  |  Out: {output_path}")
            print(f"{'=' * 50}\n")

    return output_path


if __name__ == "__main__":
    run_pipeline(
        icp_config_path="config/icp_digital_transformation.json",
        exclusion_list_path=None,
        user_prompt="Find Bangalore mid-market manufacturers who have hired a "
                    "CTO in the last 90 days and are migrating off legacy ERP.",
    )
