"""Distributed vote/debate aggregation for team/topology/protocol selection.

Paper reference (Section 5.9):
  - ConsensusMerge({Decompose(S_t, P_i)}): agents propose task decompositions,
    consensus merges them into agreed subtask ordering
  - ConsensusSelect(bids, coalitions, constraints): distributed consensus on
    team composition, communication topology, and execution protocol
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from src.core.agent import BaseAgent


@dataclass
class Vote:
    """A single agent's vote on a proposal."""

    agent_name: str
    choice: str
    confidence: float
    reasoning: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "choice": self.choice,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }


@dataclass
class ConsensusResult:
    """Outcome of a consensus round."""

    proposal: str
    votes: list[Vote]
    winner: str
    agreement_ratio: float
    debate_log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal": self.proposal,
            "votes": [v.to_dict() for v in self.votes],
            "winner": self.winner,
            "agreement_ratio": round(self.agreement_ratio, 4),
            "debate_log": self.debate_log,
        }


VOTE_PROMPT = """\
You are participating in a distributed decision about the following proposal:

{proposal}

Options: {options}

Current context:
{context}

Vote for one option. Respond with JSON:
{{
  "choice": "<your choice>",
  "confidence": <0.0-1.0>,
  "reasoning": "<brief justification>"
}}
"""

DEBATE_PROMPT = """\
You are debating the following proposal:

{proposal}

Previous arguments:
{previous_arguments}

Your position: {position}

Provide a concise argument (2-3 sentences) for or against. Focus on \
technical merit, not just preferences.
"""

DECOMPOSITION_PROMPT = """\
You are a satellite mission design specialist. Given the current mission state, \
propose an ordering of the remaining subtasks.

Available subtasks: {subtasks}
Completed so far: {completed}

Current mission context:
{context}

Propose an ordering of the remaining subtasks as a JSON list, with brief reasoning:
{{
  "ordering": ["subtask1", "subtask2", ...],
  "reasoning": "<why this ordering is optimal>"
}}
"""

PROTOCOL_SELECTION_PROMPT = """\
For the subtask "{subtask}", choose the best execution protocol.

Available protocols:
- solo: Single agent executes alone (fastest, cheapest)
- audit: Primary agent executes, a reviewer checks the output (good for critical tasks)
- debate: Two agents produce competing outputs, best is selected (resolves disagreements)
- parallel: Multiple agents execute independently, outputs are merged (max diversity)
- tool_verified: Agent executes, then deterministic validators check claims (for verifiable tasks)

The assigned primary agent is: {primary_agent}
Subtask criticality: {criticality}
Current disagreement level: {disagreement:.2f}

Current context:
{context}

Vote for one protocol. Respond with JSON:
{{
  "choice": "<protocol name>",
  "confidence": <0.0-1.0>,
  "reasoning": "<brief justification>"
}}
"""


class ConsensusEngine:
    """Runs distributed voting, debate, and consensus among agents."""

    def __init__(
        self,
        threshold: float = 0.7,
        min_voters: int = 3,
    ) -> None:
        self.threshold = threshold
        self.min_voters = min_voters

    def vote(
        self,
        proposal: str,
        options: list[str],
        agents: dict[str, BaseAgent],
        context: str = "",
    ) -> ConsensusResult:
        """Run a vote across agents."""
        votes: list[Vote] = []

        for name, agent in agents.items():
            prompt = VOTE_PROMPT.format(
                proposal=proposal,
                options=", ".join(options),
                context=context,
            )

            response, _record = agent.run(prompt)
            vote = self._parse_vote(name, response)
            votes.append(vote)

        # Tally weighted by confidence
        tallies: dict[str, float] = {}
        for v in votes:
            tallies[v.choice] = tallies.get(v.choice, 0) + v.confidence

        total_weight = sum(tallies.values()) or 1
        winner = max(tallies, key=lambda k: tallies[k])
        agreement = tallies[winner] / total_weight

        return ConsensusResult(
            proposal=proposal,
            votes=votes,
            winner=winner,
            agreement_ratio=agreement,
        )

    def debate_then_vote(
        self,
        proposal: str,
        options: list[str],
        agents: dict[str, BaseAgent],
        context: str = "",
        debate_rounds: int = 1,
    ) -> ConsensusResult:
        """Run debate rounds followed by a final vote."""
        debate_log: list[str] = []

        # Debate rounds
        for r in range(debate_rounds):
            for name, agent in agents.items():
                prompt = DEBATE_PROMPT.format(
                    proposal=proposal,
                    previous_arguments="\n".join(debate_log[-6:]),  # Last 6 args
                    position=f"Round {r + 1}",
                )
                response, _record = agent.run(prompt)
                debate_log.append(f"[{name}] {response}")

        # Final vote
        result = self.vote(proposal, options, agents, context)
        result.debate_log = debate_log
        return result

    def decompose_and_merge(
        self,
        available_subtasks: list[str],
        completed_subtasks: list[str],
        agents: dict[str, BaseAgent],
        context: str = "",
    ) -> list[str]:
        """Consensus-based task decomposition (paper's ConsensusMerge).

        Each agent proposes a subtask ordering, then we merge via ranked voting.
        """
        if len(available_subtasks) <= 1:
            return available_subtasks

        proposals: list[list[str]] = []

        for name, agent in agents.items():
            prompt = DECOMPOSITION_PROMPT.format(
                subtasks=", ".join(available_subtasks),
                completed=", ".join(completed_subtasks) or "none",
                context=context[:2000],
            )
            response, _record = agent.run(prompt)
            ordering = self._parse_ordering(response, available_subtasks)
            proposals.append(ordering)

        # Merge via Borda count (ranked voting)
        return self._borda_merge(proposals, available_subtasks)

    def consensus_select_protocol(
        self,
        subtask: str,
        primary_agent: str,
        agents: dict[str, BaseAgent],
        context: str = "",
        criticality: str = "medium",
        disagreement: float = 0.0,
    ) -> str:
        """ConsensusSelect for execution protocol (paper Section 5.9).

        Agents vote on the best protocol for the given subtask.
        """
        protocols = ["solo", "audit", "debate", "parallel", "tool_verified"]
        votes: list[Vote] = []

        for name, agent in agents.items():
            prompt = PROTOCOL_SELECTION_PROMPT.format(
                subtask=subtask,
                primary_agent=primary_agent,
                criticality=criticality,
                disagreement=disagreement,
                context=context[:1500],
            )
            response, _record = agent.run(prompt)
            vote = self._parse_vote(name, response)
            # Validate choice is a real protocol
            if vote.choice not in protocols:
                vote.choice = "solo"  # Default fallback
            votes.append(vote)

        # Tally weighted by confidence
        tallies: dict[str, float] = {}
        for v in votes:
            tallies[v.choice] = tallies.get(v.choice, 0) + v.confidence

        if not tallies:
            return "solo"

        return max(tallies, key=lambda k: tallies[k])

    def _parse_vote(self, agent_name: str, raw: str) -> Vote:
        """Parse a vote response from an agent."""
        json_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return Vote(
                    agent_name=agent_name,
                    choice=data.get("choice", "abstain"),
                    confidence=float(data.get("confidence", 0.5)),
                    reasoning=data.get("reasoning", ""),
                )
            except (json.JSONDecodeError, ValueError):
                pass

        # Fallback
        return Vote(
            agent_name=agent_name,
            choice="abstain",
            confidence=0.5,
            reasoning=raw[:200],
        )

    def _parse_ordering(self, raw: str, valid_subtasks: list[str]) -> list[str]:
        """Parse an ordering proposal from an agent."""
        json_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                ordering = data.get("ordering", [])
                # Filter to only valid subtasks
                valid = [s for s in ordering if s in valid_subtasks]
                # Add any missing subtasks at the end
                for s in valid_subtasks:
                    if s not in valid:
                        valid.append(s)
                return valid
            except (json.JSONDecodeError, ValueError):
                pass
        return list(valid_subtasks)

    def _borda_merge(
        self,
        proposals: list[list[str]],
        candidates: list[str],
    ) -> list[str]:
        """Merge multiple ranked orderings via Borda count."""
        n = len(candidates)
        scores: dict[str, float] = {c: 0.0 for c in candidates}

        for ordering in proposals:
            for rank, item in enumerate(ordering):
                if item in scores:
                    scores[item] += n - rank  # Higher rank = more points

        # Sort by score descending
        return sorted(candidates, key=lambda c: scores.get(c, 0), reverse=True)
