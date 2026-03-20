"""Confidence Gateway — self-assessed quality gate for agent outputs.

After an agent produces output, the gateway asks the *same* agent (in the
same conversation) to rate its confidence.  If below threshold the agent
retries immediately, creating a fast inner loop that catches low-quality
outputs before they reach the heavier checkpoint / escalation machinery.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from src.core.agent import BaseAgent
from src.core.metrics import CallRecord

# ------------------------------------------------------------------
# Prompts
# ------------------------------------------------------------------

CONFIDENCE_PROMPT = (
    "Rate your confidence in the response you just provided on a scale "
    "from 0 to 100.  Consider accuracy, completeness, and specificity.\n\n"
    "Reply with ONLY a JSON object (no markdown fences):\n"
    '{"confidence": <int 0-100>, "reason": "<one sentence>"}'
)

RETRY_PROMPT = (
    "Your self-assessed confidence was {score}%, which is below the "
    "required threshold of {threshold}%.  Reason: {reason}\n\n"
    "Please produce an improved, higher-quality response to the original "
    "task.  Address the weaknesses you identified."
)

# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------


@dataclass
class ConfidenceRecord:
    """One confidence check (one attempt within a gated call)."""

    agent_name: str
    subtask: str
    attempt: int  # 1-based
    confidence: int  # 0-100
    passed: bool
    reason: str


@dataclass
class ConfidenceGatewayResult:
    """Aggregate result of a gated execution (possibly multiple attempts)."""

    final_response: str
    final_confidence: int
    records: list[ConfidenceRecord]
    passed: bool


# ------------------------------------------------------------------
# Gateway
# ------------------------------------------------------------------


class ConfidenceGateway:
    """Ask the producing agent to self-rate; retry if below threshold."""

    def __init__(self, threshold: int = 85, max_retries: int = 2) -> None:
        self.threshold = threshold
        self.max_retries = max_retries
        self.history: list[ConfidenceRecord] = []

    # ----- public API -----

    def gate(
        self,
        agent: BaseAgent,
        subtask: str,
        task_prompt: str,
        context: str = "",
    ) -> tuple[str, CallRecord, ConfidenceGatewayResult]:
        """Run *task_prompt* through *agent* with confidence gating.

        Returns ``(response, last_call_record, gateway_result)``.
        """
        if context:
            agent.inject_context(context)

        records: list[ConfidenceRecord] = []
        attempt = 0
        response = ""
        record: CallRecord | None = None

        while attempt <= self.max_retries:
            attempt += 1

            # 1. Agent produces (or re-produces) the response
            response, record = agent.run(task_prompt if attempt == 1 else
                                         RETRY_PROMPT.format(
                                             score=records[-1].confidence,
                                             threshold=self.threshold,
                                             reason=records[-1].reason,
                                         ))

            # 2. Same agent self-rates in the same conversation
            conf_response, _ = agent.run(CONFIDENCE_PROMPT)
            confidence, reason = self._parse_confidence(conf_response)

            passed = confidence >= self.threshold
            cr = ConfidenceRecord(
                agent_name=agent.name,
                subtask=subtask,
                attempt=attempt,
                confidence=confidence,
                passed=passed,
                reason=reason,
            )
            records.append(cr)
            self.history.append(cr)

            if passed:
                break

        # Build result
        result = ConfidenceGatewayResult(
            final_response=response,
            final_confidence=records[-1].confidence,
            records=records,
            passed=records[-1].passed,
        )

        assert record is not None
        return response, record, result

    def to_dict(self) -> dict[str, Any]:
        """Summary stats + full records for metadata export."""
        total = len(self.history)
        passed = sum(1 for r in self.history if r.passed)
        retries = sum(1 for r in self.history if r.attempt > 1)
        avg_conf = (
            sum(r.confidence for r in self.history) / total if total else 0
        )
        return {
            "threshold": self.threshold,
            "max_retries": self.max_retries,
            "total_checks": total,
            "passed": passed,
            "failed": total - passed,
            "retries": retries,
            "avg_confidence": round(avg_conf, 1),
            "records": [
                {
                    "agent": r.agent_name,
                    "subtask": r.subtask,
                    "attempt": r.attempt,
                    "confidence": r.confidence,
                    "passed": r.passed,
                    "reason": r.reason,
                }
                for r in self.history
            ],
        }

    # ----- helpers -----

    @staticmethod
    def _parse_confidence(text: str) -> tuple[int, str]:
        """Best-effort parse of the agent's confidence JSON."""
        # Try JSON parse first
        try:
            # Strip markdown fences if present
            cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`")
            data = json.loads(cleaned)
            return int(data["confidence"]), str(data.get("reason", ""))
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            pass

        # Fallback: look for a bare number
        match = re.search(r"\b(\d{1,3})\b", text)
        if match:
            return min(int(match.group(1)), 100), text[:120]

        # Give up — treat as low confidence to trigger retry
        return 0, f"Could not parse confidence from: {text[:120]}"
