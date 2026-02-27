"""Calibration-weighted bidding for task assignment.

Paper reference (Section 5.9):
  bid_{i,k}(t) = alpha * fit(P_i, T_k, S_t)
               - beta  * cal_penalty(P_i)
               - gamma * cost(P_i, T_k)
               + delta * divgain(P_i, A_cand_k)

Where:
  - fit: how well the agent's capabilities match the subtask
  - cal_penalty: 1 - calibration_score (penalizes poorly calibrated agents)
  - cost: agent's estimated cost for the subtask
  - divgain: diversity gain from adding this agent to the candidate set
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.systems.dicwo.beacon import Beacon, BeaconRegistry, SUBTASK_COST_ESTIMATES


@dataclass
class Bid:
    """A bid from an agent for a subtask."""

    agent_name: str
    subtask: str
    score: float  # Final combined bid score
    fit: float  # Capability match score
    cal_penalty: float  # Calibration penalty (1 - cal_score)
    cost: float  # Estimated cost
    diversity_bonus: float  # Diversity gain
    reputation: float  # Agent reputation score

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "subtask": self.subtask,
            "score": round(self.score, 4),
            "fit": round(self.fit, 4),
            "cal_penalty": round(self.cal_penalty, 4),
            "cost": round(self.cost, 4),
            "diversity_bonus": round(self.diversity_bonus, 4),
            "reputation": round(self.reputation, 4),
        }


@dataclass
class CoalitionProposal:
    """A candidate micro-coalition for a subtask."""

    subtask: str
    members: list[str]
    coalition_type: str  # proposer_critic / solver_verifier / parallel_independent
    synergy_score: float
    combined_fit: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "subtask": self.subtask,
            "members": self.members,
            "coalition_type": self.coalition_type,
            "synergy_score": round(self.synergy_score, 4),
            "combined_fit": round(self.combined_fit, 4),
        }


@dataclass
class BiddingEngine:
    """Computes calibration-weighted bids for subtask assignment.

    Implements the paper's 4-term bidding formula with configurable weights.
    Also tracks reputation and synergy across agents.
    """

    # Paper's bid formula weights
    alpha: float = 1.0   # Weight for capability fit
    beta: float = 0.5    # Weight for calibration penalty
    gamma: float = 0.3   # Weight for cost
    delta: float = 0.2   # Weight for diversity gain

    calibration_decay: float = 0.9
    # Track how many times each agent has been assigned (for diversity)
    assignment_counts: dict[str, int] = field(default_factory=dict)
    # Reputation: running average of outcome quality per agent
    reputation: dict[str, float] = field(default_factory=dict)
    # Synergy: tracks how well pairs of agents work together
    synergy: dict[str, dict[str, float]] = field(default_factory=dict)

    def compute_bids(
        self,
        subtask: str,
        registry: BeaconRegistry,
    ) -> list[Bid]:
        """Compute bids for all capable agents on a subtask.

        Implements: bid = alpha*fit - beta*cal_penalty - gamma*cost + delta*divgain
        """
        candidates = registry.get_capable_agents(subtask)
        if not candidates:
            # Fall back to all agents
            candidates = registry.all_beacons()

        bids = []
        total_assignments = sum(self.assignment_counts.values()) or 1

        for beacon in candidates:
            # fit: how well capabilities match (1.0 = primary capability, partial otherwise)
            fit = self._compute_fit(beacon, subtask)

            # cal_penalty: penalize agents with poor calibration history
            cal_penalty = 1.0 - beacon.calibration_score

            # cost: normalized estimated cost for this subtask
            base_cost = SUBTASK_COST_ESTIMATES.get(subtask, 0.3)
            cost = base_cost * (1 + beacon.load)  # Higher load = higher effective cost

            # divgain: bonus for less-used agents (promotes diversity)
            agent_assignments = self.assignment_counts.get(beacon.agent_name, 0)
            diversity_bonus = 1.0 - (agent_assignments / total_assignments)

            # Apply evidence weight (anti-gaming)
            fit *= beacon.evidence_weight

            # Paper formula: alpha*fit - beta*cal_penalty - gamma*cost + delta*divgain
            score = (
                self.alpha * fit
                - self.beta * cal_penalty
                - self.gamma * cost
                + self.delta * diversity_bonus
            )

            # Reputation bonus (paper's reputation tracking)
            rep = self.reputation.get(beacon.agent_name, 0.5)
            score += 0.1 * rep  # Small reputation factor

            bids.append(Bid(
                agent_name=beacon.agent_name,
                subtask=subtask,
                score=score,
                fit=fit,
                cal_penalty=cal_penalty,
                cost=cost,
                diversity_bonus=diversity_bonus,
                reputation=rep,
            ))

        # Sort by score descending
        bids.sort(key=lambda b: b.score, reverse=True)
        return bids

    def assign(self, subtask: str, registry: BeaconRegistry) -> str | None:
        """Assign subtask to the highest-bidding agent."""
        bids = self.compute_bids(subtask, registry)
        if not bids:
            return None
        winner = bids[0].agent_name
        self.assignment_counts[winner] = self.assignment_counts.get(winner, 0) + 1
        return winner

    def get_top_k(
        self,
        subtask: str,
        registry: BeaconRegistry,
        k: int = 2,
    ) -> list[str]:
        """Return top-k agents for a subtask (for coalition formation)."""
        bids = self.compute_bids(subtask, registry)
        return [b.agent_name for b in bids[:k]]

    def propose_coalitions(
        self,
        subtask: str,
        registry: BeaconRegistry,
    ) -> list[CoalitionProposal]:
        """Generate candidate micro-coalitions from top bidders.

        Produces solo (top-1) and pair coalitions from top 3-4 bidders,
        scored by combined fit + synergy. Coalition type is determined by
        the relative strength gap between members.
        """
        bids = self.compute_bids(subtask, registry)
        if not bids:
            return []

        proposals: list[CoalitionProposal] = []

        # Solo proposal: top-1 bidder
        top = bids[0]
        proposals.append(CoalitionProposal(
            subtask=subtask,
            members=[top.agent_name],
            coalition_type="parallel_independent",
            synergy_score=0.0,
            combined_fit=top.fit,
        ))

        # Pair proposals from top 3-4 bidders
        top_bids = bids[:min(4, len(bids))]
        for i in range(len(top_bids)):
            for j in range(i + 1, len(top_bids)):
                a, b = top_bids[i], top_bids[j]
                synergy = self.get_synergy(a.agent_name, b.agent_name)
                combined_fit = (a.fit + b.fit) / 2.0

                # Determine coalition type by relative strength gap
                gap = abs(a.score - b.score)
                if gap > 0.3:
                    # Large gap: stronger agent leads, weaker verifies
                    ctype = "proposer_critic"
                elif gap > 0.1:
                    ctype = "solver_verifier"
                else:
                    ctype = "parallel_independent"

                proposals.append(CoalitionProposal(
                    subtask=subtask,
                    members=[a.agent_name, b.agent_name],
                    coalition_type=ctype,
                    synergy_score=synergy,
                    combined_fit=combined_fit + 0.2 * synergy,
                ))

        # Sort by combined_fit descending
        proposals.sort(key=lambda p: p.combined_fit, reverse=True)
        return proposals

    def update_calibration(
        self,
        agent_name: str,
        registry: BeaconRegistry,
        success: bool,
    ) -> None:
        """Update calibration score based on outcome."""
        beacon = registry.beacons.get(agent_name)
        if beacon is None:
            return
        if success:
            beacon.calibration_score = min(
                1.0,
                beacon.calibration_score * (1 / self.calibration_decay),
            )
        else:
            beacon.calibration_score *= self.calibration_decay

    def update_reputation(
        self,
        agent_name: str,
        quality_score: float,
        decay: float = 0.8,
    ) -> None:
        """Update reputation with exponential moving average.

        Paper: UpdateCalibrationReputationSynergy includes reputation tracking.
        """
        old = self.reputation.get(agent_name, 0.5)
        self.reputation[agent_name] = decay * old + (1 - decay) * quality_score

    def update_synergy(
        self,
        agent_a: str,
        agent_b: str,
        quality_score: float,
        decay: float = 0.8,
    ) -> None:
        """Track how well a pair of agents worked together.

        Paper: synergy is part of UpdateCalibrationReputationSynergy.
        """
        if agent_a not in self.synergy:
            self.synergy[agent_a] = {}
        old = self.synergy[agent_a].get(agent_b, 0.5)
        self.synergy[agent_a][agent_b] = decay * old + (1 - decay) * quality_score

    def get_synergy(self, agent_a: str, agent_b: str) -> float:
        """Get synergy score between two agents."""
        return self.synergy.get(agent_a, {}).get(agent_b, 0.5)

    def _compute_fit(self, beacon: Beacon, subtask: str) -> float:
        """Compute capability fit between an agent and a subtask."""
        if subtask in beacon.capabilities:
            return 1.0
        # Partial match for related capabilities
        related = {
            "market_analysis": {"demand_estimation", "region_assessment", "throughput_derivation"},
            "frequency_filing": {"itu_compliance", "spectrum_analysis", "rf_parameters"},
            "payload_design": {"link_budget", "antenna_sizing", "rf_engineering"},
            "mission_analysis": {"constellation_design", "cost_estimation", "orbit_selection"},
            "integration": {"consistency_check", "trade_study", "review"},
        }
        related_caps = related.get(subtask, set())
        overlap = len(set(beacon.capabilities) & related_caps)
        if overlap > 0:
            return 0.5 + 0.5 * (overlap / max(len(related_caps), 1))
        return 0.1  # Minimal fit for completely unrelated agent
