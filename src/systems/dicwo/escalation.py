"""Protocol escalation ladder for subtasks.

When a subtask fails checkpoint quality checks and the policy decides to
REWIRE, the subtask's execution protocol is escalated through increasingly
rigorous modes:

  Level 0: solo           -- single agent drafts
  Level 1: audit          -- draft + independent critic/verifier
  Level 2: debate         -- proposer-critic-judge (3-way)
  Level 3: tool_verified  -- forced calculations/self-review

This converts REWIRE decisions into concrete corrective behaviour rather
than topology changes that re-select solo and waste tokens.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Ordered from least to most rigorous
ESCALATION_LADDER: list[str] = ["solo", "audit", "debate", "tool_verified"]


@dataclass
class EscalationState:
    """Per-subtask escalation tracking."""

    level: int = 0
    attempts: int = 0

    @property
    def protocol(self) -> str:
        """Current minimum protocol for this subtask."""
        return ESCALATION_LADDER[min(self.level, len(ESCALATION_LADDER) - 1)]

    @property
    def at_max(self) -> bool:
        return self.level >= len(ESCALATION_LADDER) - 1


class EscalationLadder:
    """Tracks and manages protocol escalation per subtask.

    The ladder acts as a *floor*: consensus may still select a higher
    protocol, but never a lower one than the current escalation level.
    """

    def __init__(self) -> None:
        self._state: dict[str, EscalationState] = {}

    def get_protocol(self, subtask: str) -> str:
        """Return the current minimum protocol for *subtask*."""
        state = self._state.get(subtask)
        if state is None:
            return ESCALATION_LADDER[0]
        return state.protocol

    def get_level(self, subtask: str) -> int:
        state = self._state.get(subtask)
        return state.level if state else 0

    def escalate(self, subtask: str) -> str:
        """Bump *subtask* to the next protocol level. Returns the new protocol."""
        if subtask not in self._state:
            self._state[subtask] = EscalationState(level=0, attempts=1)

        state = self._state[subtask]
        if not state.at_max:
            state.level += 1
        state.attempts += 1
        return state.protocol

    def record_attempt(self, subtask: str) -> None:
        """Record an execution attempt without escalation."""
        if subtask not in self._state:
            self._state[subtask] = EscalationState()
        self._state[subtask].attempts += 1

    def is_escalated(self, subtask: str) -> bool:
        """True if *subtask* has been escalated beyond initial solo."""
        state = self._state.get(subtask)
        return state is not None and state.level > 0

    def at_max(self, subtask: str) -> bool:
        """True if *subtask* has reached the top of the ladder."""
        state = self._state.get(subtask)
        return state is not None and state.at_max

    def to_dict(self) -> dict[str, dict]:
        return {
            subtask: {
                "level": s.level,
                "protocol": s.protocol,
                "attempts": s.attempts,
            }
            for subtask, s in self._state.items()
        }

    @staticmethod
    def enforce_floor(consensus_protocol: str, subtask: str, ladder: "EscalationLadder") -> str:
        """Return the higher of *consensus_protocol* and the escalation floor."""
        floor = ladder.get_protocol(subtask)
        floor_idx = ESCALATION_LADDER.index(floor)
        cons_idx = (
            ESCALATION_LADDER.index(consensus_protocol)
            if consensus_protocol in ESCALATION_LADDER
            else 0
        )
        return ESCALATION_LADDER[max(floor_idx, cons_idx)]
