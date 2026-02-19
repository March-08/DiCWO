"""JSON-lines structured logging and conversation trace."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ConversationLogger:
    """Records the full message trace of a system run as JSON-lines."""

    entries: list[dict[str, Any]] = field(default_factory=list)

    def log(
        self,
        agent: str,
        role: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": agent,
            "role": role,
            "content": content,
        }
        if metadata:
            entry["metadata"] = metadata
        self.entries.append(entry)

    def to_list(self) -> list[dict[str, Any]]:
        return list(self.entries)

    def save(self, path: Path) -> None:
        with open(path, "w") as f:
            json.dump(self.entries, f, indent=2, default=str)

    def save_jsonl(self, path: Path) -> None:
        with open(path, "w") as f:
            for entry in self.entries:
                f.write(json.dumps(entry, default=str) + "\n")


def save_json(data: Any, path: Path) -> None:
    """Write any serializable data to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def load_json(path: Path) -> Any:
    """Read a JSON file."""
    with open(path) as f:
        return json.load(f)
