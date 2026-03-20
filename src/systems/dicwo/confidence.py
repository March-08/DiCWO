"""Confidence Gateway — self-assessed quality gate for agent outputs.

After an agent produces output, the gateway asks the *same* agent (in the
same conversation) to rate its confidence.  The gateway uses **tiered
branching logic** based on the confidence score:

  - **>= high threshold** (default 85): Proceed — output is accepted.
  - **low–high range** (default 50–85): Reflective rerun — the agent
    critiques its own response, identifying contradictions and weak
    assumptions, then retries with the self-critique as context.
  - **< low threshold** (default 50): Intervention — the agent identifies
    what information is missing and returns a structured Request for
    Information instead of blindly retrying.

This avoids the "self-correction paradox": retrying without new data when
confidence is low due to *information gaps* (not reasoning errors) leads
to hallucination spirals, not improvement.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
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

REFLEXION_PROMPT = (
    "Your self-assessed confidence was {score}% (reason: {reason}), which "
    "is below the required {threshold}%.\n\n"
    "Before retrying, critically examine your previous response:\n"
    "1. Identify any logical contradictions, unsupported assumptions, or "
    "   weak reasoning steps.\n"
    "2. List specific areas where your response could be more precise or "
    "   better supported.\n"
    "3. Note any assumptions you made that should be stated explicitly.\n\n"
    "Reply with ONLY a JSON object (no markdown fences):\n"
    '{{"critique": "<your analysis>", "weak_points": ["<point1>", ...], '
    '"assumptions": ["<assumption1>", ...]}}'
)

REFLEXION_RETRY_PROMPT = (
    "Based on your self-critique:\n{critique}\n\n"
    "Now produce an improved response to the original task. Specifically:\n"
    "- Address each weak point you identified\n"
    "- Make your assumptions explicit rather than implicit\n"
    "- Be more conservative where you lack strong evidence\n"
    "- Do NOT fabricate data to fill gaps — state unknowns clearly"
)

INTERVENTION_PROMPT = (
    "Your self-assessed confidence was {score}% (reason: {reason}), which "
    "is critically low (below {low_threshold}%).\n\n"
    "This suggests you lack information needed to produce a reliable "
    "response. Do NOT attempt to guess or retry — instead, identify "
    "exactly what is missing.\n\n"
    "Reply with ONLY a JSON object (no markdown fences):\n"
    '{{"missing_info": ["<what specific data/input is needed>", ...], '
    '"blockers": ["<why you cannot proceed without this>", ...], '
    '"partial_result": "<what you CAN say with confidence>", '
    '"suggested_sources": ["<who or what could provide the missing info>", ...]}}'
)


# ------------------------------------------------------------------
# Enums and data classes
# ------------------------------------------------------------------


class ConfidenceAction(str, Enum):
    """Action taken by the gateway based on confidence tier."""

    PROCEED = "proceed"          # >= high threshold
    REFLECT = "reflect"          # low–high range: reflective rerun
    INTERVENE = "intervene"      # < low threshold: request for information


@dataclass
class ConfidenceRecord:
    """One confidence check (one attempt within a gated call)."""

    agent_name: str
    subtask: str
    attempt: int  # 1-based
    confidence: int  # 0-100
    passed: bool
    reason: str
    action: ConfidenceAction = ConfidenceAction.PROCEED


@dataclass
class InterventionRequest:
    """Structured request for information when confidence is critically low."""

    missing_info: list[str]
    blockers: list[str]
    partial_result: str
    suggested_sources: list[str]


@dataclass
class ConfidenceGatewayResult:
    """Aggregate result of a gated execution (possibly multiple attempts)."""

    final_response: str
    final_confidence: int
    records: list[ConfidenceRecord]
    passed: bool
    action_taken: ConfidenceAction = ConfidenceAction.PROCEED
    intervention: InterventionRequest | None = None


# ------------------------------------------------------------------
# Gateway
# ------------------------------------------------------------------


class ConfidenceGateway:
    """Tiered confidence gateway with reflexion and intervention."""

    def __init__(
        self,
        threshold: int = 85,
        low_threshold: int = 50,
        max_retries: int = 2,
    ) -> None:
        self.threshold = threshold
        self.low_threshold = low_threshold
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
        """Run *task_prompt* through *agent* with tiered confidence gating.

        Branching logic:
          - confidence >= threshold        → PROCEED (accept output)
          - low_threshold <= conf < thresh → REFLECT (critique + retry)
          - confidence < low_threshold     → INTERVENE (report missing info)

        Returns ``(response, last_call_record, gateway_result)``.
        """
        if context:
            agent.inject_context(context)

        records: list[ConfidenceRecord] = []
        attempt = 0
        response = ""
        record: CallRecord | None = None
        action_taken = ConfidenceAction.PROCEED
        intervention: InterventionRequest | None = None

        while attempt <= self.max_retries:
            attempt += 1

            # 1. Agent produces the response
            response, record = agent.run(task_prompt if attempt == 1 else
                                         self._build_retry_prompt(records))

            # 2. Same agent self-rates in the same conversation
            conf_response, _ = agent.run(CONFIDENCE_PROMPT)
            confidence, reason = self._parse_confidence(conf_response)

            passed = confidence >= self.threshold
            action = self._classify_action(confidence)

            cr = ConfidenceRecord(
                agent_name=agent.name,
                subtask=subtask,
                attempt=attempt,
                confidence=confidence,
                passed=passed,
                reason=reason,
                action=action,
            )
            records.append(cr)
            self.history.append(cr)

            if passed:
                action_taken = ConfidenceAction.PROCEED
                break

            if action == ConfidenceAction.INTERVENE:
                # Critically low confidence — request information, do not retry
                action_taken = ConfidenceAction.INTERVENE
                intervention = self._request_intervention(
                    agent, confidence, reason,
                )
                break

            # REFLECT tier: perform self-critique before next iteration
            action_taken = ConfidenceAction.REFLECT
            critique = self._perform_reflexion(agent, confidence, reason)
            # Store critique so the retry prompt can use it
            cr._critique = critique  # type: ignore[attr-defined]

        # Build result
        result = ConfidenceGatewayResult(
            final_response=response,
            final_confidence=records[-1].confidence,
            records=records,
            passed=records[-1].passed,
            action_taken=action_taken,
            intervention=intervention,
        )

        assert record is not None
        return response, record, result

    def to_dict(self) -> dict[str, Any]:
        """Summary stats + full records for metadata export."""
        total = len(self.history)
        passed = sum(1 for r in self.history if r.passed)
        retries = sum(1 for r in self.history if r.attempt > 1)
        reflections = sum(
            1 for r in self.history if r.action == ConfidenceAction.REFLECT
        )
        interventions = sum(
            1 for r in self.history if r.action == ConfidenceAction.INTERVENE
        )
        avg_conf = (
            sum(r.confidence for r in self.history) / total if total else 0
        )
        return {
            "threshold": self.threshold,
            "low_threshold": self.low_threshold,
            "max_retries": self.max_retries,
            "total_checks": total,
            "passed": passed,
            "failed": total - passed,
            "reflections": reflections,
            "interventions": interventions,
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
                    "action": r.action.value,
                }
                for r in self.history
            ],
        }

    # ----- helpers -----

    def _classify_action(self, confidence: int) -> ConfidenceAction:
        """Determine which tier a confidence score falls into."""
        if confidence >= self.threshold:
            return ConfidenceAction.PROCEED
        if confidence >= self.low_threshold:
            return ConfidenceAction.REFLECT
        return ConfidenceAction.INTERVENE

    def _perform_reflexion(
        self, agent: BaseAgent, confidence: int, reason: str,
    ) -> str:
        """Ask the agent to critique its own response before retrying."""
        prompt = REFLEXION_PROMPT.format(
            score=confidence,
            reason=reason,
            threshold=self.threshold,
        )
        critique_response, _ = agent.run(prompt)
        return critique_response

    def _build_retry_prompt(self, records: list[ConfidenceRecord]) -> str:
        """Build the retry prompt, using the critique if a reflexion was done."""
        last = records[-1]
        critique = getattr(last, "_critique", None)
        if critique:
            return REFLEXION_RETRY_PROMPT.format(critique=critique)
        # Fallback (shouldn't happen with tiered logic, but be safe)
        return REFLEXION_RETRY_PROMPT.format(
            critique=f"Confidence was {last.confidence}%: {last.reason}"
        )

    def _request_intervention(
        self, agent: BaseAgent, confidence: int, reason: str,
    ) -> InterventionRequest:
        """Ask the agent to identify missing information instead of retrying."""
        prompt = INTERVENTION_PROMPT.format(
            score=confidence,
            reason=reason,
            low_threshold=self.low_threshold,
        )
        intervention_response, _ = agent.run(prompt)
        return self._parse_intervention(intervention_response)

    @staticmethod
    def _parse_intervention(text: str) -> InterventionRequest:
        """Best-effort parse of the agent's intervention JSON."""
        try:
            cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`")
            data = json.loads(cleaned)
            return InterventionRequest(
                missing_info=data.get("missing_info", []),
                blockers=data.get("blockers", []),
                partial_result=data.get("partial_result", ""),
                suggested_sources=data.get("suggested_sources", []),
            )
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            return InterventionRequest(
                missing_info=[text[:500]],
                blockers=["Could not parse structured intervention response"],
                partial_result="",
                suggested_sources=[],
            )

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

        # Give up — treat as low confidence to trigger intervention
        return 0, f"Could not parse confidence from: {text[:120]}"
