"""SharedState: artifact store, requirements log, and event tracking."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class SharedState:
    """Shared state accessible by all agents in a system.

    Stores artifacts (agent outputs), requirements, and an event log.
    Serializes cleanly to JSON.
    """

    artifacts: dict[str, Any] = field(default_factory=dict)
    requirements: dict[str, Any] = field(default_factory=dict)
    event_log: list[dict[str, Any]] = field(default_factory=list)

    def publish(self, key: str, value: Any, *, source: str = "unknown") -> None:
        """Publish an artifact."""
        self.artifacts[key] = value
        self._log_event("publish", source=source, key=key)

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve an artifact."""
        return self.artifacts.get(key, default)

    def set_requirement(self, key: str, value: Any) -> None:
        self.requirements[key] = value

    def get_requirement(self, key: str, default: Any = None) -> Any:
        return self.requirements.get(key, default)

    def get_context_summary(self, keys: list[str] | None = None) -> str:
        """Return a text summary of selected (or all) artifacts for injection."""
        target = keys or list(self.artifacts.keys())
        parts = []
        for k in target:
            v = self.artifacts.get(k)
            if v is not None:
                if isinstance(v, str):
                    parts.append(f"## {k}\n{v}")
                else:
                    parts.append(f"## {k}\n{json.dumps(v, indent=2, default=str)}")
        return "\n\n".join(parts)

    def _log_event(self, event_type: str, **kwargs: Any) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            **kwargs,
        }
        self.event_log.append(entry)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifacts": self.artifacts,
            "requirements": self.requirements,
            "event_log": self.event_log,
        }

    def reset(self) -> None:
        self.artifacts.clear()
        self.requirements.clear()
        self.event_log.clear()
