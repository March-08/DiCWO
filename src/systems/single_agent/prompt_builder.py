"""Prompt builder for the single-agent system."""

from src.domain.prompts import SINGLE_AGENT_SYSTEM_PROMPT, SINGLE_AGENT_USER_PROMPT


def build_messages() -> list[dict[str, str]]:
    """Build the single-agent message list."""
    return [
        {"role": "system", "content": SINGLE_AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": SINGLE_AGENT_USER_PROMPT},
    ]
