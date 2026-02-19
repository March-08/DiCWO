"""Routing logic: parse manager decisions and map to agents."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class RoutingDecision:
    """Parsed routing decision from the manager."""

    next_agent: str
    task: str
    context: str = ""
    reasoning: str = ""
    is_done: bool = False

    @classmethod
    def parse(cls, raw: str) -> RoutingDecision:
        """Parse the manager's JSON response into a RoutingDecision."""
        # Try to extract JSON from the response
        json_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
        if not json_match:
            # Fallback: treat as free text, try to infer intent
            if "DONE" in raw.upper():
                return cls(
                    next_agent="DONE",
                    task="integration",
                    reasoning=raw,
                    is_done=True,
                )
            raise ValueError(f"Could not parse routing decision from: {raw[:200]}")

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON in routing decision: {json_match.group()[:200]}")

        next_agent = data.get("next_agent", "")
        is_done = next_agent.upper() == "DONE"

        return cls(
            next_agent=next_agent,
            task=data.get("task", ""),
            context=data.get("context", ""),
            reasoning=data.get("reasoning", ""),
            is_done=is_done,
        )


def build_routing_context(
    artifacts: dict[str, Any],
    completed_tasks: list[str],
    remaining_rounds: int,
) -> str:
    """Build the context string for the manager's routing prompt."""
    parts = []

    if artifacts:
        parts.append("=== Current Artifacts ===")
        for key, value in artifacts.items():
            preview = str(value)[:500] + "..." if len(str(value)) > 500 else str(value)
            parts.append(f"\n### {key}\n{preview}")

    completed_str = ", ".join(completed_tasks) if completed_tasks else "None"

    context = "\n".join(parts) if parts else "No artifacts produced yet."
    return (
        f"Current state of the study:\n\n{context}\n\n"
        f"Completed tasks: {completed_str}\n"
        f"Remaining budget: {remaining_rounds} rounds"
    )
