"""System 1: Single-Agent baseline — one LLM call with monolithic prompt."""

from __future__ import annotations

from src.core.config import ExperimentConfig
from src.core.llm_client import LLMClient
from src.systems.base_system import BaseSystem, SystemResult
from src.systems.single_agent.prompt_builder import build_messages


class SingleAgentSystem(BaseSystem):
    """Lower-bound baseline: one LLM call combining all 5 roles."""

    def __init__(self, config: ExperimentConfig, llm: LLMClient) -> None:
        super().__init__(config, llm)

    def run(self) -> SystemResult:
        messages = build_messages()

        # Log the prompt
        self.logger.log(
            agent="single_agent",
            role="system",
            content=messages[0]["content"],
        )
        self.logger.log(
            agent="single_agent",
            role="user",
            content=messages[1]["content"],
        )

        # Single LLM call
        response, record = self.llm.chat(
            messages=messages,
            agent_name="single_agent",
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

        self.logger.log(
            agent="single_agent",
            role="assistant",
            content=response,
            metadata=record.to_dict(),
        )

        # Store as artifact
        self.state.publish("complete_design", response, source="single_agent")

        return SystemResult(
            artifacts=self.state.artifacts,
            conversation_log=self.logger.to_list(),
            metadata={"system_type": "single_agent", "num_calls": 1},
        )
