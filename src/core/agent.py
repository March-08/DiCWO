"""BaseAgent: identity + LLM + conversation history."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.core.llm_client import LLMClient
from src.core.metrics import CallRecord


@dataclass
class AgentIdentity:
    """Static identity for an agent."""

    name: str
    role: str
    goal: str
    backstory: str

    def system_prompt(self) -> str:
        return (
            f"You are {self.name}, a {self.role}.\n\n"
            f"Goal: {self.goal}\n\n"
            f"Background: {self.backstory}\n\n"
            "Provide detailed, technically accurate responses. "
            "Use quantitative data when possible. "
            "Structure your output clearly with sections and tables where appropriate."
        )


@dataclass
class BaseAgent:
    """An agent with identity, LLM access, and conversation history.

    All orchestration logic lives in the system layer — the agent itself
    is intentionally simple.
    """

    identity: AgentIdentity
    llm: LLMClient
    history: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Seed history with system prompt
        if not self.history:
            self.history = [
                {"role": "system", "content": self.identity.system_prompt()}
            ]

    @property
    def name(self) -> str:
        return self.identity.name

    def run(
        self,
        prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, CallRecord]:
        """Send a user prompt, append to history, return (response, record)."""
        self.history.append({"role": "user", "content": prompt})

        response, record = self.llm.chat(
            messages=self.history,
            agent_name=self.name,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        self.history.append({"role": "assistant", "content": response})
        return response, record

    def inject_context(self, context: str, role: str = "system") -> None:
        """Inject additional context into the conversation history."""
        self.history.append({"role": role, "content": context})

    def reset(self) -> None:
        """Clear history back to just the system prompt."""
        self.history = [
            {"role": "system", "content": self.identity.system_prompt()}
        ]

    def get_history(self) -> list[dict[str, str]]:
        return list(self.history)
