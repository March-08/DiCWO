"""Checkpoint signals: disagreement, uncertainty, verifiability, risk."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from src.core.agent import BaseAgent


@dataclass
class CheckpointSignals:
    """Signals computed after a subtask execution round."""

    disagreement: float  # 0-1: how much agents disagree
    uncertainty: float   # 0-1: average self-reported uncertainty
    verifiability: float # 0-1: fraction of claims that can be checked
    risk: float          # 0-1: combined risk score

    @property
    def needs_intervention(self) -> bool:
        return self.risk > 0.6 or self.disagreement > 0.3

    def to_dict(self) -> dict[str, Any]:
        return {
            "disagreement": round(self.disagreement, 4),
            "uncertainty": round(self.uncertainty, 4),
            "verifiability": round(self.verifiability, 4),
            "risk": round(self.risk, 4),
            "needs_intervention": self.needs_intervention,
        }


CHECKPOINT_PROMPT = """\
You are evaluating the quality and reliability of the following output \
from a satellite mission design study.

Subtask: {subtask}
Output:
{output}

Rate the following on a scale of 0.0 to 1.0:
1. uncertainty: How uncertain are the claims? (0 = very certain, 1 = very uncertain)
2. verifiability: What fraction of claims can be checked against physics/data? (0 = none, 1 = all)

Respond with JSON:
{{
  "uncertainty": <float>,
  "verifiability": <float>,
  "concerns": "<brief list of concerns, if any>"
}}
"""


class CheckpointEvaluator:
    """Evaluates outputs and computes checkpoint signals."""

    def __init__(
        self,
        disagreement_threshold: float = 0.3,
        uncertainty_threshold: float = 0.5,
        risk_threshold: float = 0.6,
    ) -> None:
        self.disagreement_threshold = disagreement_threshold
        self.uncertainty_threshold = uncertainty_threshold
        self.risk_threshold = risk_threshold

    def evaluate(
        self,
        subtask: str,
        outputs: dict[str, str],
        reviewer: BaseAgent,
    ) -> CheckpointSignals:
        """Compute checkpoint signals for a set of outputs.

        Args:
            subtask: The subtask that was executed
            outputs: agent_name → output mapping
            reviewer: An agent to use for evaluation
        """
        uncertainties = []
        verifiabilities = []

        for agent_name, output in outputs.items():
            prompt = CHECKPOINT_PROMPT.format(subtask=subtask, output=output[:2000])
            response, _record = reviewer.run(prompt)
            parsed = self._parse_checkpoint(response)
            uncertainties.append(parsed.get("uncertainty", 0.5))
            verifiabilities.append(parsed.get("verifiability", 0.5))

        # Disagreement: variance-based if multiple outputs
        disagreement = 0.0
        if len(outputs) > 1:
            # Use LLM to assess disagreement between outputs
            disagreement = self._assess_disagreement(outputs, reviewer)

        avg_uncertainty = sum(uncertainties) / len(uncertainties) if uncertainties else 0.5
        avg_verifiability = sum(verifiabilities) / len(verifiabilities) if verifiabilities else 0.5

        # Risk = weighted combination
        risk = 0.4 * disagreement + 0.3 * avg_uncertainty + 0.3 * (1 - avg_verifiability)

        return CheckpointSignals(
            disagreement=disagreement,
            uncertainty=avg_uncertainty,
            verifiability=avg_verifiability,
            risk=risk,
        )

    def _assess_disagreement(
        self,
        outputs: dict[str, str],
        reviewer: BaseAgent,
    ) -> float:
        """Use LLM to assess disagreement between multiple outputs."""
        summaries = []
        for name, output in outputs.items():
            summaries.append(f"[{name}]: {output[:500]}")

        prompt = (
            "Compare the following outputs from different agents on the same task. "
            "Rate their disagreement on a scale of 0.0 (fully agree) to 1.0 "
            "(completely contradict). Respond with just a number.\n\n"
            + "\n\n".join(summaries)
        )

        response, _record = reviewer.run(prompt)
        try:
            return max(0.0, min(1.0, float(response.strip())))
        except ValueError:
            return 0.3  # Default moderate disagreement

    def _parse_checkpoint(self, raw: str) -> dict[str, Any]:
        """Parse checkpoint evaluation response."""
        json_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        return {"uncertainty": 0.5, "verifiability": 0.5}
