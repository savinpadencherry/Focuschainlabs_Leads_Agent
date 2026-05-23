import os
import json
import re

from google import genai
from google.genai import types

from utils.rate_limiter import gemini_limiter


SCORING_PROMPT = """
You are a B2B lead qualification engine for a digital transformation
consulting firm in Bangalore, India.

Score this company and return ONLY valid JSON.
No markdown. No explanation. No code blocks. Just the JSON object.

SCORING DIMENSIONS:

1. fit_score (max 25 points)
   Does this company match the ICP?
   25 = perfect industry + size + location match
   10-24 = partial match
   0-9 = wrong vertical or location

2. trigger_score (max 35 points)
   Is there an active signal they need transformation NOW?
   30-35 = new CTO/CIO/CDO hired in last 90 days
   25-30 = funding round in last 6 months
   20-25 = actively hiring 3+ cloud/data/IT roles right now
   15-20 = ERP or legacy system migration mentioned
   5-14 = general technology mention only
   0-4 = no signal found

3. reachability_score (max 20 points)
   Can we reach a named decision maker?
   18-20 = named CTO/CIO/VP IT found in research
   10-17 = company LinkedIn page exists with employee count
   3-9 = generic contact page only
   0-2 = no contact information found at all

4. intent_recency_score (max 20 points)
   How recent is the primary signal?
   18-20 = signal in last 30 days
   12-17 = signal in last 31 to 90 days
   6-11 = signal in last 91 to 180 days
   0-5 = signal older than 180 days or undated
{custom_focus_section}
ICP:
{icp_config}

COMPANY RESEARCH:
{research_bundle}

Return this exact JSON and nothing else:
{{
  "total_score": <integer 0-100>,
  "fit_score": <integer 0-25>,
  "trigger_score": <integer 0-35>,
  "reachability_score": <integer 0-20>,
  "intent_recency_score": <integer 0-20>,
  "primary_signal": "<the single most compelling reason to reach out NOW — specific, not generic>",
  "pain_point": "<their most likely operational pain that digital transformation consulting solves>",
  "score_reasoning": "<exactly 2 sentences explaining the total score>",
  "qualify": <true if total_score >= threshold else false>,
  "disqualified_reason": "<only populate if qualify is false>"
}}
"""


def score_company(research_bundle: dict, icp_config: dict) -> dict:
    threshold = int(os.getenv("MIN_SCORE_THRESHOLD", 60))
    gemini_limiter.wait()

    custom_focus = icp_config.get("custom_focus", "")
    custom_focus_section = (
        f"\nADDITIONAL TARGETING CONTEXT (user-specified, weigh heavily):\n{custom_focus}\n"
        if custom_focus else ""
    )

    # Remove internal fields before serializing ICP for the prompt
    icp_clean = {k: v for k, v in icp_config.items() if k not in ("custom_focus",)}

    prompt = SCORING_PROMPT.format(
        custom_focus_section=custom_focus_section,
        icp_config=json.dumps(icp_clean, indent=2),
        research_bundle=json.dumps(research_bundle, indent=2),
    )

    for attempt in range(2):
        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            response = client.models.generate_content(
                model="gemini-3.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_level="low")
                ),
            )
            raw = response.text.strip()
            raw = re.sub(r"```json|```", "", raw).strip()
            result = json.loads(raw)
            result["qualify"] = result.get("total_score", 0) >= threshold
            return result

        except json.JSONDecodeError:
            if attempt == 0:
                print(f"  [RETRY] JSON parse failed for {research_bundle['company_name']}")
                continue
            print(f"  [SKIP] Scoring failed after retry: {research_bundle['company_name']}")
            return {
                "total_score": 0, "qualify": False, "error": "scoring_failed",
                "primary_signal": "", "pain_point": "", "score_reasoning": "Scoring failed.",
            }
        except Exception as e:
            print(f"  [ERROR] Gemini call failed: {e}")
            return {
                "total_score": 0, "qualify": False, "error": str(e),
                "primary_signal": "", "pain_point": "", "score_reasoning": "",
            }
