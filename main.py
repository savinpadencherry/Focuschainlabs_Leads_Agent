import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from agent.searcher import search_all_sources
from agent.researcher import research_company
from agent.scorer import score_company
from agent.enricher import enrich_contact
from agent.pitcher import generate_pitch
from utils.deduplicator import load_exclusion_list, deduplicate
from utils.excel_writer import write_leads_to_excel


def today() -> str:
    return datetime.today().strftime("%Y-%m-%d")


def run_pipeline(
    icp_config_path: str,
    exclusion_list_path: str = None,
    max_leads: int = None
) -> str:
    max_leads = max_leads or int(os.getenv("MAX_LEADS_PER_RUN", 10))
    threshold = int(os.getenv("MIN_SCORE_THRESHOLD", 60))
    pilot = os.getenv("PILOT_MODE", "true").lower() == "true"

    if pilot:
        print("=" * 50)
        print("  PILOT MODE — costs capped to free tiers")
        print("=" * 50)

    print(f"\n[1/7] Loading ICP config: {icp_config_path}")
    with open(icp_config_path) as f:
        icp = json.load(f)
    print(f"      Vertical: {icp['vertical']} | Client: {icp['client']}")

    print(f"\n[2/7] Searching for signal companies across 4 sources...")
    raw = search_all_sources(icp)
    print(f"      Raw results: {len(raw)} companies")

    print(f"\n[3/7] Deduplicating...")
    exclusion = load_exclusion_list(exclusion_list_path)
    companies = deduplicate(raw, exclusion)
    print(f"      After dedup: {len(companies)} companies")

    # Cap research candidates at 3x max leads to control API costs
    research_cap = max_leads * 3
    companies = companies[:research_cap]
    print(f"      Researching top {len(companies)} candidates")

    print(f"\n[4/7] Researching companies...")
    researched = []
    for i, company in enumerate(companies, 1):
        print(f"      [{i}/{len(companies)}] {company['company_name']}")
        bundle = research_company(
            company["company_name"],
            company.get("website", ""),
            company.get("snippet", "")
        )
        researched.append({**company, **bundle})

    print(f"\n[5/7] Scoring with Gemini 3.5 Flash (thinking: low)...")
    scored = []
    for i, company in enumerate(researched, 1):
        print(f"      [{i}/{len(researched)}] {company['company_name']}")
        score = score_company(company, icp)
        scored.append({**company, **score})

    qualified = [c for c in scored if c.get("qualify") is True]
    print(f"      Qualified (score >= {threshold}): {len(qualified)}")

    # In pilot mode, cap Apollo enrichments to 5 calls
    enrich_cap = 5 if pilot else max_leads
    to_enrich = qualified[:min(max_leads, enrich_cap)]

    print(f"\n[6/7] Enriching contacts via Apollo.io...")
    enriched = []
    for i, company in enumerate(to_enrich, 1):
        print(f"      [{i}/{len(to_enrich)}] {company['company_name']}")
        contact = enrich_contact(
            company["company_name"],
            icp["target_titles"],
            icp["locations"][0]
        )
        enriched.append({**company, **contact, **icp})

    print(f"\n[7/7] Generating opening lines with Gemini 3.5 Flash (thinking: medium)...")
    final_leads = []
    for i, lead in enumerate(enriched, 1):
        print(f"      [{i}/{len(enriched)}] {lead['company_name']}")
        lead["opening_line"] = generate_pitch(lead)
        final_leads.append(lead)

    # Write partial results even if pipeline had some errors
    if not final_leads and scored:
        print("  [WARN] No leads cleared enrichment — writing scored results as partial output")
        for company in scored[:max_leads]:
            company.update({
                "contact_name": "Manual lookup needed",
                "contact_title": "Manual lookup needed",
                "email": "Manual lookup needed",
                "linkedin_url": "Manual lookup needed",
                "opening_line": "",
                **icp
            })
            final_leads.append(company)

    timestamp = datetime.today().strftime("%Y-%m-%d_%H%M")
    output_path = f"output/leads_{timestamp}.xlsx"
    write_leads_to_excel(final_leads, output_path)

    total_researched = len(researched)
    qualified_count = len(qualified)
    print(f"\n{'=' * 50}")
    print(f"  DONE")
    print(f"  Leads found:     {len(final_leads)}")
    print(f"  Qualified rate:  {qualified_count}/{total_researched} "
          f"({int(qualified_count / max(total_researched, 1) * 100)}%)")
    print(f"  Output:          {output_path}")
    print(f"{'=' * 50}\n")

    return output_path


if __name__ == "__main__":
    run_pipeline(
        icp_config_path="config/icp_digital_transformation.json",
        exclusion_list_path=None
    )
