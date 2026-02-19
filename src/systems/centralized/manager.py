"""Centralized manager agent that routes tasks to specialists."""

from __future__ import annotations

from typing import Any

from src.core.agent import AgentIdentity, BaseAgent
from src.core.llm_client import LLMClient
from src.domain.prompts import MANAGER_SYSTEM_PROMPT
from src.systems.centralized.routing import RoutingDecision, build_routing_context


class ManagerAgent:
    """The Study Manager that decides which specialist works next."""

    def __init__(self, llm: LLMClient) -> None:
        identity = AgentIdentity(
            name="Manager",
            role="Study Manager",
            goal="Coordinate specialists to produce a complete DTHH mission design",
            backstory="",
        )
        # Override system prompt with the manager-specific one
        self.agent = BaseAgent(identity=identity, llm=llm)
        self.agent.history = [
            {"role": "system", "content": MANAGER_SYSTEM_PROMPT}
        ]

    def decide_next(
        self,
        artifacts: dict[str, Any],
        completed_tasks: list[str],
        remaining_rounds: int,
    ) -> RoutingDecision:
        """Ask the manager who should work next."""
        context = build_routing_context(artifacts, completed_tasks, remaining_rounds)

        prompt = (
            f"Current state of the study:\n\n{context}\n\n"
            f"Decide which specialist should work next and what specific task "
            f"they should perform."
        )

        response, _record = self.agent.run(prompt)
        return RoutingDecision.parse(response)
