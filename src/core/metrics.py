"""Per-call and aggregate metrics collection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CallRecord:
    """Record for a single LLM call."""

    agent_name: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    latency_s: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "latency_s": round(self.latency_s, 3),
        }


@dataclass
class MetricsCollector:
    """Collects per-call records and computes aggregates."""

    calls: list[CallRecord] = field(default_factory=list)

    def record_call(self, record: CallRecord) -> None:
        self.calls.append(record)

    @property
    def total_tokens(self) -> int:
        return sum(c.total_tokens for c in self.calls)

    @property
    def total_prompt_tokens(self) -> int:
        return sum(c.prompt_tokens for c in self.calls)

    @property
    def total_completion_tokens(self) -> int:
        return sum(c.completion_tokens for c in self.calls)

    @property
    def total_cost(self) -> float:
        return sum(c.cost_usd for c in self.calls)

    @property
    def total_latency(self) -> float:
        return sum(c.latency_s for c in self.calls)

    @property
    def num_calls(self) -> int:
        return len(self.calls)

    def per_agent_summary(self) -> dict[str, dict[str, Any]]:
        agents: dict[str, list[CallRecord]] = {}
        for c in self.calls:
            agents.setdefault(c.agent_name, []).append(c)

        summary = {}
        for name, records in agents.items():
            summary[name] = {
                "num_calls": len(records),
                "total_tokens": sum(r.total_tokens for r in records),
                "prompt_tokens": sum(r.prompt_tokens for r in records),
                "completion_tokens": sum(r.completion_tokens for r in records),
                "cost_usd": round(sum(r.cost_usd for r in records), 6),
                "latency_s": round(sum(r.latency_s for r in records), 3),
            }
        return summary

    def to_dict(self) -> dict[str, Any]:
        return {
            "totals": {
                "num_calls": self.num_calls,
                "total_tokens": self.total_tokens,
                "prompt_tokens": self.total_prompt_tokens,
                "completion_tokens": self.total_completion_tokens,
                "cost_usd": round(self.total_cost, 6),
                "latency_s": round(self.total_latency, 3),
            },
            "per_agent": self.per_agent_summary(),
            "call_log": [c.to_dict() for c in self.calls],
        }

    def reset(self) -> None:
        self.calls.clear()
