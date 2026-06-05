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

from utils.rate_limiter import gemini_limiter
from utils.exceptions import RateLimitError
from utils.gemini import generate_content_text


SCORING_PROMPT = """
You are a lead qualification engine.
Score this lead and return ONLY valid JSON.
No markdown. No prose. No code fences. Just the JSON object.
{scoring_guidance_block}
SCORING DIMENSIONS:

1. fit_score (max 25)
   25 = perfect industry + size + location match for the user's brief
   10-24 = partial match
   0-9 = wrong vertical or location

2. trigger_score (max 35)
   30-35 = multiple current buying signals: relevant hiring + expansion/news + clear operational pain
   25-30 = actively hiring 2+ relevant roles tied to operations, CRM, ecommerce, automation, support, booking, logistics, marketing, or process improvement
   20-25 = recent expansion, new branch/product/service launch, growth push, or public process/customer pain
   15-20 = job post or news item implies manual workflow, software, fulfilment, lead-flow, reporting, or customer support gap
   5-14 = generic digital/software mention only
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
  "responsible_owner":   "<senior role/person most likely accountable for solving this pain, based on hiring/news/management evidence>",
  "one_line_reasoning":  "<one crisp SDR-facing sentence explaining why this lead belongs in the sheet>",
  "score_reasoning":     "Fit X/25 because <basis>. Trigger X/35 because <basis>. Reachability X/20 because <basis>. Recency X/20 because <basis>. Total X/100 because <short conclusion>.",
  "qualify":             <true if total_score >= threshold else false>,
  "disqualified_reason": "<only populate if qualify is false>"
}}
"""


def score_company(research_bundle: dict, icp_config: dict) -> dict:
    threshold = int(icp_config.get("min_score_threshold") or os.getenv("MIN_SCORE_THRESHOLD", 60))
    gemini_limiter.wait()

    custom_focus     = icp_config.get("custom_focus", "")
    pain_hypothesis  = icp_config.get("pain_hypothesis", "")
    gap_hypothesis   = icp_config.get("gap_hypothesis", "")
    scoring_guidance = icp_config.get("scoring_guidance", "")

    if scoring_guidance:
        scoring_guidance_block = (
            "\nVERTICAL CONTEXT — READ FIRST (overrides the generic assumptions below):\n"
            f"{scoring_guidance}\n"
            "If this vertical is NOT about B2B hiring/operations (e.g. real-estate buyers, "
            "consumer demand, or referral channels that reach buyers), then reinterpret "
            "trigger_score as the strength of BUYING INTENT or ACCESS TO QUALIFIED BUYERS "
            "described above (not hiring activity), and reinterpret pain_point as the buyer "
            "need the offering solves. Be generous: surface plausible leads even at low "
            "confidence, and explain the uncertainty in score_reasoning.\n"
        )
    else:
        scoring_guidance_block = ""

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
        if k not in ("custom_focus", "pain_hypothesis", "gap_hypothesis", "scoring_guidance")
    }

    prompt = SCORING_PROMPT.format(
        scoring_guidance_block=scoring_guidance_block,
        hypotheses_block=hypotheses_block,
        custom_focus_section=custom_focus_section,
        icp_config=json.dumps(icp_clean, indent=2, default=str),
        research_bundle=json.dumps(research_bundle, indent=2, default=str),
    )

    for attempt in range(2):
        try:
            raw = re.sub(r"```json|```", "", generate_content_text(prompt).strip()).strip()
            result = json.loads(raw)
            return _normalise_result(result, threshold)

        except json.JSONDecodeError:
            if attempt == 0:
                print(f"  [RETRY] JSON parse failed for {research_bundle.get('company_name', '')}")
                continue
            print(f"  [SKIP] Scoring failed after retry: {research_bundle.get('company_name', '')}")
            return {
                "total_score": 0, "qualify": False, "error": "scoring_failed",
                "primary_signal": "", "pain_point": "", "responsible_owner": "",
                "one_line_reasoning": "", "score_reasoning": "Scoring failed.",
            }
        except Exception as e:
            _raise_if_rate_limit("gemini", e)
            print(f"  [ERROR] Gemini call failed: {e}")
            return {
                "total_score": 0, "qualify": False, "error": str(e),
                "primary_signal": "", "pain_point": "", "responsible_owner": "",
                "one_line_reasoning": "", "score_reasoning": "",
            }


def _normalise_result(result: dict, threshold: int) -> dict:
    for key in ("fit_score", "trigger_score", "reachability_score", "intent_recency_score"):
        try:
            result[key] = int(result.get(key, 0) or 0)
        except Exception:
            result[key] = 0

    if not result.get("total_score"):
        result["total_score"] = (
            result["fit_score"]
            + result["trigger_score"]
            + result["reachability_score"]
            + result["intent_recency_score"]
        )
    result["qualify"] = int(result.get("total_score", 0) or 0) >= threshold
    result.setdefault("responsible_owner", "")
    result.setdefault("one_line_reasoning", "")

    reasoning = str(result.get("score_reasoning", "") or "").strip()
    if "Fit" not in reasoning or "Trigger" not in reasoning:
        reasoning = (
            f"Fit {result['fit_score']}/25 based on industry, size and location match. "
            f"Trigger {result['trigger_score']}/35 based on the strongest hiring/news/pain signal found. "
            f"Reachability {result['reachability_score']}/20 based on available company/contact evidence. "
            f"Recency {result['intent_recency_score']}/20 based on how recent the signal appears. "
            f"Total {result.get('total_score', 0)}/100."
        )
    result["score_reasoning"] = reasoning
    return result


def _raise_if_rate_limit(service: str, exc: Exception) -> None:
    msg = str(exc).lower()
    if any(k in msg for k in ("429", "resource_exhausted", "quota", "rate limit", "ratelimit")):
        raise RateLimitError(service, str(exc))
