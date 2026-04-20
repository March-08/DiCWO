"""Re-judge single agent outputs against ALL 5 subtask rubrics.

The original evaluation only scored `complete_design` against the integration
rubric. This script scores the same monolithic output against all 5 rubrics
(market analysis, frequency filing, payload design, mission analysis,
integration) to enable apples-to-apples comparison with centralized and DiCWO.

Results are saved alongside the original evaluation.json as
evaluation_per_subtask.json.

Usage:
    python3 scripts/rejudge_single_agent.py
    python3 scripts/rejudge_single_agent.py --experiment 20260323
    python3 scripts/rejudge_single_agent.py --experiment 20260323 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.core.llm_client import LLMClient
from src.evaluation.rubrics import (
    MARKET_ANALYSIS_RUBRIC,
    FREQUENCY_FILING_RUBRIC,
    PAYLOAD_DESIGN_RUBRIC,
    MISSION_ANALYSIS_RUBRIC,
    INTEGRATION_RUBRIC,
)

RUBRICS = {
    "market_analysis": MARKET_ANALYSIS_RUBRIC,
    "frequency_filing": FREQUENCY_FILING_RUBRIC,
    "payload_design": PAYLOAD_DESIGN_RUBRIC,
    "mission_analysis": MISSION_ANALYSIS_RUBRIC,
    "integration": INTEGRATION_RUBRIC,
}

JUDGE_SYSTEM_PROMPT = """\
You are an expert evaluator for satellite mission design studies. You score \
outputs against rubrics on a 1-5 scale.

Scoring guide:
1 = Poor: Missing, incorrect, or fundamentally flawed
2 = Below Average: Present but with significant errors or gaps
3 = Average: Adequate but lacking depth or precision
4 = Good: Solid work with minor issues
5 = Excellent: Comprehensive, accurate, well-structured

For each criterion, provide:
- A score (1-5)
- A brief justification (1-2 sentences)
"""

JUDGE_PROMPT = """\
{rubric}

## Output to Evaluate

The following is a COMPLETE satellite mission design report produced by a \
single agent. You must evaluate ONLY the portion relevant to "{subtask_name}" \
— ignore all other sections when scoring.

{output}

## Instructions

Score each criterion as it applies to the {subtask_name} content in this \
report. If the report lacks a dedicated section for {subtask_name}, score \
based on whatever relevant information is present (or score low if absent).

Respond with JSON:
{{
  "criteria_scores": {{
    "<criterion_name>": {{
      "score": <1-5>,
      "justification": "<brief explanation>"
    }}
  }},
  "overall_score": <weighted average, 1-5>,
  "summary": "<2-3 sentence assessment of the {subtask_name} quality>"
}}
"""

SUBTASK_DISPLAY = {
    "market_analysis": "Market Analysis",
    "frequency_filing": "Frequency Filing",
    "payload_design": "Payload Design",
    "mission_analysis": "Mission Analysis",
    "integration": "Integration",
}


def find_single_agent_runs(results_dir: str, prefix: str = "") -> list[Path]:
    """Find all single_agent run directories in comparison experiments."""
    runs = []
    results = Path(results_dir)
    for d in sorted(results.iterdir()):
        if not d.is_dir() or "comparison" not in d.name:
            continue
        if prefix and not d.name.startswith(prefix):
            continue
        sa_dir = d / "single_agent"
        if not sa_dir.exists():
            continue
        for run_dir in sorted(sa_dir.iterdir()):
            if run_dir.is_dir() and run_dir.name.startswith("run_"):
                artifacts_path = run_dir / "artifacts.json"
                if artifacts_path.exists():
                    runs.append(run_dir)
    return runs


def judge_against_rubric(
    llm: LLMClient,
    output_text: str,
    subtask: str,
) -> dict:
    """Judge an output against a specific subtask rubric."""
    rubric = RUBRICS[subtask]
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": JUDGE_PROMPT.format(
                rubric=rubric.to_prompt(),
                output=output_text[:6000],
                subtask_name=SUBTASK_DISPLAY[subtask],
            ),
        },
    ]

    response, _record = llm.chat(
        messages=messages,
        agent_name="judge",
        temperature=0.3,
    )

    import re
    json_match = re.search(r"\{[\s\S]*\}", response)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    return {"parse_error": True, "raw_response": response[:500], "overall_score": 0}


def main():
    parser = argparse.ArgumentParser(
        description="Re-judge single agent outputs against all 5 subtask rubrics"
    )
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--experiment", default="",
                        help="Filter by experiment prefix (e.g. 20260323)")
    parser.add_argument("--judge-model", default="openai/gpt-5.2-chat")
    parser.add_argument("--judge-provider", default="openrouter")
    parser.add_argument("--dry-run", action="store_true",
                        help="List runs without judging")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key and not args.dry_run:
        print("Error: No API key found.")
        sys.exit(1)

    runs = find_single_agent_runs(args.results_dir, args.experiment)
    print(f"Found {len(runs)} single_agent runs to re-judge")

    if args.dry_run:
        for r in runs:
            existing = (r / "evaluation_per_subtask.json").exists()
            print(f"  {r}  {'[DONE]' if existing else ''}")
        return

    llm = LLMClient(
        api_key=api_key,
        model=args.judge_model,
        provider=args.judge_provider,
        temperature=0.3,
    )

    for run_dir in runs:
        out_path = run_dir / "evaluation_per_subtask.json"
        if out_path.exists():
            print(f"  SKIP {run_dir} (already judged)")
            continue

        artifacts = json.load(open(run_dir / "artifacts.json"))
        output = artifacts.get("complete_design", "")
        if not output:
            print(f"  SKIP {run_dir} (no complete_design artifact)")
            continue

        model_name = str(run_dir).split("_comparison")[0].split("_172838_")[-1]
        run_name = run_dir.name
        print(f"  Judging {model_name} / {run_name} against 5 rubrics...")

        results = {}
        for subtask in RUBRICS:
            print(f"    {subtask}...", end=" ", flush=True)
            score = judge_against_rubric(llm, output, subtask)
            results[subtask] = score
            overall = score.get("overall_score", "?")
            print(f"score={overall}")

        # Compute aggregate
        overall_scores = [
            r["overall_score"]
            for r in results.values()
            if isinstance(r, dict) and "overall_score" in r
            and isinstance(r["overall_score"], (int, float))
        ]
        if overall_scores:
            results["_aggregate"] = {
                "mean_score": round(sum(overall_scores) / len(overall_scores), 2),
                "num_subtasks_judged": len(overall_scores),
            }

        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"    -> saved to {out_path}")

    print("\nDone!")


if __name__ == "__main__":
    main()
