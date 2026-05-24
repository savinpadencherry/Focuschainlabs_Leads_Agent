"""
Gemini-driven lead scorer.

Returns a dict with total_score (0-100), four sub-scores, primary_signal,
pain_point, score_reasoning, qualify, disqualified_reason.

Accepts an optional `custom_focus`, `pain_hypothesis`, and `gap_hypothesis`
on the icp dict — these are injected into the prompt so the model weights
them when ranking.
"""

import os
import json
import re

from google import genai
from google.genai import types

from utils.rate_limiter import gemini_limiter


SCORING_PROMPT = """
You are a B2B lead qualification engine.
Score this company and return ONLY valid JSON.
No markdown. No prose. No code fences. Just the JSON object.

SCORING DIMENSIONS:

1. fit_score (max 25)
   25 = perfect industry + size + location match for the user's brief
   10-24 = partial match
   0-9 = wrong vertical or location

2. trigger_score (max 35)
   30-35 = new CTO/CIO/CDO hired in last 90 days
   25-30 = funding round in last 6 months
   20-25 = actively hiring 3+ relevant roles right now
   15-20 = migration / launch / expansion mentioned
   5-14 = generic technology mention only
   0-4 = no signal found

3. reachability_score (max 20)
   18-20 = named decision maker found in research
   10-17 = company LinkedIn page exists with employee count
   3-9 = generic contact page only
   0-2 = no contact information found

4. intent_recency_score (max 20)
   18-20 = signal in last 30 days
   12-17 = signal in last 31-90 days
   6-11 = signal in last 91-180 days
   0-5 = older than 180 days or undated

WEIGHT THESE PAIN / GAP HYPOTHESES HEAVILY when set:
{hypotheses_block}{custom_focus_section}
ICP:
{icp_config}

COMPANY RESEARCH:
{research_bundle}

Return exactly this JSON and nothing else:
{{
  "total_score":         <integer 0-100>,
  "fit_score":           <integer 0-25>,
  "trigger_score":       <integer 0-35>,
  "reachability_score":  <integer 0-20>,
  "intent_recency_score":<integer 0-20>,
  "primary_signal":      "<the single most compelling reason to reach out NOW — specific, not generic>",
  "pain_point":          "<their most likely operational pain that the user's offering solves>",
  "score_reasoning":     "<exactly 2 sentences explaining the total score>",
  "qualify":             <true if total_score >= threshold else false>,
  "disqualified_reason": "<only populate if qualify is false>"
}}
"""


def score_company(research_bundle: dict, icp_config: dict) -> dict:
    threshold = int(os.getenv("MIN_SCORE_THRESHOLD", 60))
    gemini_limiter.wait()

    custom_focus     = icp_config.get("custom_focus", "")
    pain_hypothesis  = icp_config.get("pain_hypothesis", "")
    gap_hypothesis   = icp_config.get("gap_hypothesis", "")

    if pain_hypothesis or gap_hypothesis:
        hypotheses_block = (
            f"\n- Pain hypothesis: {pain_hypothesis}"
            f"\n- Gap hypothesis: {gap_hypothesis}\n"
        )
    else:
        hypotheses_block = "\n(none provided)\n"

    custom_focus_section = (
        f"\nADDITIONAL TARGETING CONTEXT (user-specified, weigh heavily):\n{custom_focus}\n"
        if custom_focus else ""
    )

    icp_clean = {
        k: v for k, v in icp_config.items()
        if k not in ("custom_focus", "pain_hypothesis", "gap_hypothesis")
    }

    prompt = SCORING_PROMPT.format(
        hypotheses_block=hypotheses_block,
        custom_focus_section=custom_focus_section,
        icp_config=json.dumps(icp_clean, indent=2, default=str),
        research_bundle=json.dumps(research_bundle, indent=2, default=str),
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
            raw = re.sub(r"```json|```", "", response.text.strip()).strip()
            result = json.loads(raw)
            result["qualify"] = result.get("total_score", 0) >= threshold
            return result

        except json.JSONDecodeError:
            if attempt == 0:
                print(f"  [RETRY] JSON parse failed for {research_bundle.get('company_name', '')}")
                continue
            print(f"  [SKIP] Scoring failed after retry: {research_bundle.get('company_name', '')}")
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
