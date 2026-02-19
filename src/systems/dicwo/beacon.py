"""Capability beacons: agents advertise what they can do each round.

Paper reference (Section 5.9): Each agent emits a beacon containing
can_do, need, estimate, calibrated_confidence_interval,
suggested_collaborators, and evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Beacon:
    """A capability advertisement from an agent.

    Matches the paper's beacon specification:
      - can_do (capabilities): what the agent can handle
      - need: what the agent needs from others to proceed
      - estimate (estimated_cost): estimated token/cost budget for tasks
      - calibrated_confidence_interval: confidence adjusted by history
      - suggested_collaborators: agents this agent prefers to work with
      - evidence: past results supporting advertised capabilities
    """

    agent_name: str
    capabilities: list[str]
    confidence: float  # 0-1, self-assessed raw confidence
    calibration_score: float = 1.0  # Updated based on outcome history
    load: float = 0.0  # Current workload (0 = idle, 1 = fully loaded)
    round_num: int = 0

    # Paper-required fields
    needs: list[str] = field(default_factory=list)  # Capabilities needed from others
    estimated_cost: float = 0.0  # Estimated token cost for claimed tasks
    suggested_collaborators: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)  # References to past outputs

    # Anti-gaming: beacons with no evidence get down-weighted
    evidence_weight: float = 1.0  # 0-1, reduced if claims are unsupported

    @property
    def calibrated_confidence(self) -> float:
        """Confidence adjusted by calibration history and evidence weight."""
        return self.confidence * self.calibration_score * self.evidence_weight

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "capabilities": self.capabilities,
            "confidence": self.confidence,
            "calibration_score": round(self.calibration_score, 4),
            "calibrated_confidence": round(self.calibrated_confidence, 4),
            "load": self.load,
            "round_num": self.round_num,
            "needs": self.needs,
            "estimated_cost": round(self.estimated_cost, 4),
            "suggested_collaborators": self.suggested_collaborators,
            "evidence": self.evidence[-3:],  # Last 3 for brevity
            "evidence_weight": round(self.evidence_weight, 4),
        }


# Capability definitions per agent role
AGENT_CAPABILITIES: dict[str, list[str]] = {
    "Market Analyst": [
        "market_analysis",
        "demand_estimation",
        "region_assessment",
        "throughput_derivation",
    ],
    "Frequency Filing Expert": [
        "frequency_filing",
        "itu_compliance",
        "spectrum_analysis",
        "rf_parameters",
    ],
    "Payload Expert": [
        "payload_design",
        "link_budget",
        "antenna_sizing",
        "rf_engineering",
    ],
    "Mission Analyst": [
        "mission_analysis",
        "constellation_design",
        "cost_estimation",
        "orbit_selection",
    ],
    "Study Manager": [
        "integration",
        "consistency_check",
        "trade_study",
        "review",
    ],
}

# Estimated cost per subtask (relative units, used in bidding cost term)
SUBTASK_COST_ESTIMATES: dict[str, float] = {
    "market_analysis": 0.3,
    "frequency_filing": 0.4,
    "payload_design": 0.5,
    "mission_analysis": 0.4,
    "integration": 0.6,
}


@dataclass
class BeaconRegistry:
    """Collects and queries beacons from all agents."""

    beacons: dict[str, Beacon] = field(default_factory=dict)

    def register(self, beacon: Beacon) -> None:
        self.beacons[beacon.agent_name] = beacon

    def get_capable_agents(self, capability: str) -> list[Beacon]:
        """Return beacons of agents that advertise a given capability."""
        return [
            b for b in self.beacons.values()
            if capability in b.capabilities
        ]

    def get_best_for(self, capability: str) -> Beacon | None:
        """Return the best agent for a capability (by calibrated confidence)."""
        candidates = self.get_capable_agents(capability)
        if not candidates:
            return None
        return max(candidates, key=lambda b: b.calibrated_confidence)

    def all_beacons(self) -> list[Beacon]:
        return list(self.beacons.values())

    def downweight_unsupported(self) -> None:
        """Anti-gaming: reduce evidence_weight for beacons lacking evidence."""
        for beacon in self.beacons.values():
            if not beacon.evidence:
                beacon.evidence_weight = max(0.5, beacon.evidence_weight * 0.9)
            else:
                beacon.evidence_weight = min(1.0, beacon.evidence_weight * 1.05)

    def to_dict(self) -> dict[str, Any]:
        return {name: b.to_dict() for name, b in self.beacons.items()}
