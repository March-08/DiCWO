"""Human-in-the-loop question selection based on Expected Value of Information.

Paper reference (Section 5.9):
  - HITL is triggered when EVoI exceeds a threshold
  - Budget: max N HITL calls per task/session
  - Questions are selected to maximize information gain
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.systems.dicwo.checkpoint import CheckpointSignals


@dataclass
class HITLQuestion:
    """A question selected for human review."""

    question: str
    subtask: str
    evoi: float
    context: str
    options: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "subtask": self.subtask,
            "evoi": round(self.evoi, 4),
            "context": self.context[:500],
            "options": self.options,
        }


@dataclass
class HITLResponse:
    """Human response to a HITL question."""

    question_id: int
    answer: str
    confidence: float = 1.0


class HITLManager:
    """Manages human-in-the-loop interactions based on EVoI.

    Enforces a session-level budget (paper: "max N HITL calls per task/session").
    """

    def __init__(
        self,
        evoi_threshold: float = 0.7,
        max_calls: int = 3,
    ) -> None:
        self.evoi_threshold = evoi_threshold
        self.max_calls = max_calls
        self.questions: list[HITLQuestion] = []
        self.responses: list[HITLResponse] = []

    @property
    def budget_remaining(self) -> int:
        return max(0, self.max_calls - len(self.questions))

    @property
    def budget_exhausted(self) -> bool:
        return self.budget_remaining <= 0

    def should_ask_human(self, signals: CheckpointSignals) -> bool:
        """Check if HITL is warranted based on signals and budget."""
        if self.budget_exhausted:
            return False
        evoi = signals.uncertainty * signals.risk * (1 + signals.disagreement)
        return evoi > self.evoi_threshold

    def generate_question(
        self,
        subtask: str,
        signals: CheckpointSignals,
        context: str,
    ) -> HITLQuestion:
        """Generate a question for human review (consumes budget)."""
        evoi = signals.uncertainty * signals.risk * (1 + signals.disagreement)

        if signals.disagreement > 0.5:
            question = (
                f"Agents disagree on '{subtask}'. The key disagreement "
                f"involves the following area. Which approach do you prefer?"
            )
        elif signals.uncertainty > 0.7:
            question = (
                f"High uncertainty in '{subtask}'. Could you provide guidance "
                f"on the expected values or constraints?"
            )
        else:
            question = (
                f"Risk threshold exceeded for '{subtask}'. "
                f"Please review the current outputs and confirm direction."
            )

        q = HITLQuestion(
            question=question,
            subtask=subtask,
            evoi=evoi,
            context=context,
        )
        self.questions.append(q)
        return q

    def record_response(self, question_idx: int, answer: str) -> None:
        """Record a human response."""
        self.responses.append(HITLResponse(
            question_id=question_idx,
            answer=answer,
        ))

    def get_pending_questions(self) -> list[HITLQuestion]:
        """Return questions that haven't been answered."""
        answered_ids = {r.question_id for r in self.responses}
        return [
            q for i, q in enumerate(self.questions)
            if i not in answered_ids
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "questions": [q.to_dict() for q in self.questions],
            "responses": [
                {"question_id": r.question_id, "answer": r.answer}
                for r in self.responses
            ],
            "budget_remaining": self.budget_remaining,
            "max_calls": self.max_calls,
        }
