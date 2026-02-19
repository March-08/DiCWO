"""Policy engine: decide next action based on checkpoint signals.

Paper reference (Section 5.9):
  action = pi(Gamma_t, budgets)
  Actions: continue, rewire, verify, expand diversity, request HITL,
           create new agent, or stop

Also enforces HITL budget (max N calls per session) and acceptance criteria.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.systems.dicwo.checkpoint import CheckpointSignals


class PolicyAction(str, Enum):
    CONTINUE = "continue"
    REWIRE = "rewire"
    VERIFY = "verify"          # Re-run with deterministic validators
    HITL = "hitl"
    SPAWN = "spawn"
    ESCALATE = "escalate"
    STOP = "stop"              # Acceptance criteria met


@dataclass
class PolicyDecision:
    """A policy decision with action and metadata."""

    action: PolicyAction
    reason: str
    params: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "params": self.params,
        }


class PolicyEngine:
    """Decides what to do based on checkpoint signals.

    Implements the paper's policy function pi(Gamma_t, budgets) with:
    - HITL budget enforcement
    - Acceptance criteria checking
    - All 7 actions from the paper
    """

    def __init__(
        self,
        hitl_evoi_threshold: float = 0.7,
        max_spawned_agents: int = 2,
        max_hitl_calls: int = 3,  # Paper: "max N HITL calls per session"
        disagreement_threshold: float = 0.3,
        uncertainty_threshold: float = 0.5,
        risk_threshold: float = 0.6,
        acceptance_quality: float = 0.7,  # Min quality to accept and stop
    ) -> None:
        self.hitl_evoi_threshold = hitl_evoi_threshold
        self.max_spawned_agents = max_spawned_agents
        self.max_hitl_calls = max_hitl_calls
        self.disagreement_threshold = disagreement_threshold
        self.uncertainty_threshold = uncertainty_threshold
        self.risk_threshold = risk_threshold
        self.acceptance_quality = acceptance_quality
        self.spawned_count = 0
        self.hitl_count = 0
        # Track quality of completed subtasks for acceptance criteria
        self.subtask_quality: dict[str, float] = {}

    def decide(
        self,
        signals: CheckpointSignals,
        round_num: int,
        max_rounds: int,
        available_capabilities: set[str],
        needed_capabilities: set[str],
        subtask: str = "",
    ) -> PolicyDecision:
        """Evaluate signals and return a policy decision.

        Decision priority (paper Section 5.9):
        1. Acceptance criteria met → STOP
        2. High risk + disagreement → HITL (if budget allows)
        3. Low verifiability → VERIFY
        4. Capability gap → SPAWN
        5. High disagreement → REWIRE
        6. High uncertainty → ESCALATE
        7. Otherwise → CONTINUE
        """

        # Track quality for this subtask
        quality = 1.0 - signals.risk
        if subtask:
            self.subtask_quality[subtask] = quality

        # 1. Check acceptance criteria (paper's AcceptanceCriteriaMet)
        if self._acceptance_criteria_met():
            return PolicyDecision(
                action=PolicyAction.STOP,
                reason="Acceptance criteria met: all subtasks above quality threshold",
                params={"quality_scores": dict(self.subtask_quality)},
            )

        # 2. High risk + high disagreement → HITL (with budget check)
        if (
            signals.risk > self.risk_threshold
            and signals.disagreement > self.disagreement_threshold
        ):
            evoi = self._estimate_evoi(signals)
            if evoi > self.hitl_evoi_threshold and self.hitl_count < self.max_hitl_calls:
                return PolicyDecision(
                    action=PolicyAction.HITL,
                    reason=(
                        f"High risk ({signals.risk:.2f}) with disagreement "
                        f"({signals.disagreement:.2f}). EVoI={evoi:.2f}. "
                        f"HITL budget: {self.hitl_count}/{self.max_hitl_calls}"
                    ),
                    params={"evoi": evoi},
                )

        # 3. Low verifiability → VERIFY (use deterministic validators)
        if signals.verifiability < 0.4 and signals.uncertainty > 0.4:
            return PolicyDecision(
                action=PolicyAction.VERIFY,
                reason=(
                    f"Low verifiability ({signals.verifiability:.2f}) with "
                    f"uncertainty ({signals.uncertainty:.2f}). "
                    f"Running deterministic validators."
                ),
                params={"subtask": subtask},
            )

        # 4. Capability gap → spawn
        missing = needed_capabilities - available_capabilities
        if missing and self.spawned_count < self.max_spawned_agents:
            return PolicyDecision(
                action=PolicyAction.SPAWN,
                reason=f"Missing capabilities: {missing}",
                params={"missing_capabilities": list(missing)},
            )

        # 5. High disagreement alone → rewire topology
        if signals.disagreement > self.disagreement_threshold:
            return PolicyDecision(
                action=PolicyAction.REWIRE,
                reason=f"Disagreement ({signals.disagreement:.2f}) exceeds threshold",
                params={"target_topology": "full"},
            )

        # 6. High uncertainty → escalate for review
        if signals.uncertainty > self.uncertainty_threshold:
            return PolicyDecision(
                action=PolicyAction.ESCALATE,
                reason=f"Uncertainty ({signals.uncertainty:.2f}) exceeds threshold",
                params={},
            )

        # 7. All good → continue
        return PolicyDecision(
            action=PolicyAction.CONTINUE,
            reason="Signals within acceptable bounds",
            params={},
        )

    def _acceptance_criteria_met(self) -> bool:
        """Paper's AcceptanceCriteriaMet(S_t).

        Returns True if all tracked subtasks are above the quality threshold.
        Requires at least 3 subtasks to be completed.
        """
        if len(self.subtask_quality) < 3:
            return False
        return all(q >= self.acceptance_quality for q in self.subtask_quality.values())

    def _estimate_evoi(self, signals: CheckpointSignals) -> float:
        """Estimate Expected Value of Information for HITL.

        Higher when uncertainty is high and the decision is important (high risk).
        """
        return signals.uncertainty * signals.risk * (1 + signals.disagreement)

    def record_spawn(self) -> None:
        self.spawned_count += 1

    def record_hitl(self) -> None:
        """Track HITL budget usage."""
        self.hitl_count += 1

    @property
    def hitl_budget_remaining(self) -> int:
        return max(0, self.max_hitl_calls - self.hitl_count)
