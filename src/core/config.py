"""YAML configuration loading and ExperimentConfig dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ExperimentConfig:
    """Configuration for a single experiment run."""

    system_type: str  # "single_agent" | "centralized" | "dicwo"

    # LLM provider for agents
    provider: str = "openai"         # "openai" | "openrouter"
    model: str = "gpt-4o"
    base_url: str = ""               # Override provider default URL
    temperature: float = 0.7
    max_tokens: int = 16384
    seed: int | None = None

    # Separate judge LLM (defaults to same provider/model if not set)
    judge_provider: str = ""
    judge_model: str = ""
    judge_base_url: str = ""

    # System-specific parameters
    max_rounds: int = 10
    system_params: dict[str, Any] = field(default_factory=dict)

    # Domain config
    domain: dict[str, Any] = field(default_factory=dict)

    # Evaluation
    run_judge: bool = True
    run_validators: bool = True

    # Metadata
    experiment_name: str = ""
    description: str = ""

    @classmethod
    def from_yaml(cls, path: str | Path) -> ExperimentConfig:
        path = Path(path)
        with open(path) as f:
            data = yaml.safe_load(f)

        # Load domain config if referenced
        domain_path = data.pop("domain_config", None)
        if domain_path:
            domain_file = path.parent / domain_path
            if domain_file.exists():
                with open(domain_file) as f:
                    data["domain"] = yaml.safe_load(f)

        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @property
    def effective_judge_provider(self) -> str:
        return self.judge_provider or self.provider

    @property
    def effective_judge_model(self) -> str:
        return self.judge_model or self.model

    @property
    def effective_judge_base_url(self) -> str:
        return self.judge_base_url or self.base_url

    def to_dict(self) -> dict[str, Any]:
        return {
            "system_type": self.system_type,
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "seed": self.seed,
            "judge_provider": self.effective_judge_provider,
            "judge_model": self.effective_judge_model,
            "max_rounds": self.max_rounds,
            "system_params": self.system_params,
            "domain": self.domain,
            "run_judge": self.run_judge,
            "run_validators": self.run_validators,
            "experiment_name": self.experiment_name,
            "description": self.description,
        }
