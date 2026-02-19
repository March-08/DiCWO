"""LLM-as-a-Judge: score system outputs against rubrics using GPT-4o."""

from __future__ import annotations

import json
import re
from typing import Any

from src.core.llm_client import LLMClient
from src.evaluation.rubrics import Rubric, get_rubric_for_artifact

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

{output}

## Instructions

Score each criterion. Then provide an overall weighted score.

Respond with JSON:
{{
  "criteria_scores": {{
    "<criterion_name>": {{
      "score": <1-5>,
      "justification": "<brief explanation>"
    }}
  }},
  "overall_score": <weighted average, 1-5>,
  "summary": "<2-3 sentence overall assessment>"
}}
"""


class LLMJudge:
    """Evaluates system outputs using LLM-as-a-Judge."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def evaluate(self, artifacts: dict[str, Any]) -> dict[str, Any]:
        """Evaluate all artifacts against their rubrics."""
        results: dict[str, Any] = {}

        for key, value in artifacts.items():
            rubric = get_rubric_for_artifact(key)
            if rubric is None:
                continue

            output_text = str(value)[:6000]  # Truncate for context
            score = self._judge_artifact(rubric, output_text)
            results[key] = score

        # Compute aggregate
        if results:
            overall_scores = [
                r["overall_score"]
                for r in results.values()
                if isinstance(r, dict) and "overall_score" in r
            ]
            if overall_scores:
                results["_aggregate"] = {
                    "mean_score": round(sum(overall_scores) / len(overall_scores), 2),
                    "num_artifacts_judged": len(overall_scores),
                }

        return results

    def _judge_artifact(self, rubric: Rubric, output: str) -> dict[str, Any]:
        """Judge a single artifact against a rubric."""
        messages = [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": JUDGE_PROMPT.format(
                    rubric=rubric.to_prompt(),
                    output=output,
                ),
            },
        ]

        response, _record = self.llm.chat(
            messages=messages,
            agent_name="judge",
            temperature=0.3,  # Lower temp for consistent scoring
        )

        return self._parse_scores(response)

    def _parse_scores(self, raw: str) -> dict[str, Any]:
        """Parse judge response into structured scores."""
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        return {
            "parse_error": True,
            "raw_response": raw[:500],
            "overall_score": 0,
        }
