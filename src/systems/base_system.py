"""Abstract base class for all multi-agent systems."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from src.core.config import ExperimentConfig
from src.core.llm_client import LLMClient
from src.core.logging_utils import ConversationLogger
from src.core.state import SharedState


@dataclass
class SystemResult:
    """Result of a system run."""

    artifacts: dict[str, Any]
    conversation_log: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseSystem(ABC):
    """Abstract interface for experiment systems."""

    def __init__(self, config: ExperimentConfig, llm: LLMClient) -> None:
        self.config = config
        self.llm = llm
        self.state = SharedState()
        self.logger = ConversationLogger()

    @abstractmethod
    def run(self) -> SystemResult:
        """Execute the system and return results."""
        ...

    @property
    def system_type(self) -> str:
        return self.config.system_type
