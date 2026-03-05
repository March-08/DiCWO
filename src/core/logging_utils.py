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


    def render_conversation_trace(self, system_type: str = "unknown") -> str:
        """Render the conversation log as a human-readable Markdown transcript.

        The output is designed for expert reviewers to assess orchestration
        quality: task delegation, decision-making, agent interactions, and
        chain-of-thought reasoning.
        """
        lines: list[str] = [
            "# Conversation Trace",
            "",
            f"**System**: {system_type}",
            f"**Entries**: {len(self.entries)}",
            "",
            "---",
            "",
        ]

        if system_type == "single_agent":
            lines.extend(self._render_single_agent_trace())
        elif system_type == "centralized":
            lines.extend(self._render_centralized_trace())
        elif system_type == "dicwo":
            lines.extend(self._render_dicwo_trace())
        else:
            lines.extend(self._render_generic_trace())

        return "\n".join(lines)

    def _render_single_agent_trace(self) -> list[str]:
        lines: list[str] = []
        for entry in self.entries:
            role = entry.get("role", "")
            content = entry.get("content", "")
            meta = entry.get("metadata", {})

            if role == "system":
                lines.append("## System Prompt")
                lines.append("")
                lines.append(content)
                lines.append("")
            elif role == "user":
                lines.append("## User Task")
                lines.append("")
                lines.append(content)
                lines.append("")
            elif role == "assistant":
                lines.append("## Agent Response")
                lines.append("")
                if meta:
                    tokens = meta.get("total_tokens", "")
                    cost = meta.get("cost_usd", "")
                    latency = meta.get("latency_s", "")
                    if tokens or cost:
                        lines.append(
                            f"*Tokens: {tokens:,} | "
                            f"Cost: ${cost:.4f} | "
                            f"Latency: {latency:.1f}s*"
                            if isinstance(tokens, (int, float))
                            else f"*{meta}*"
                        )
                        lines.append("")
                lines.append(content)
                lines.append("")
        return lines

    def _render_centralized_trace(self) -> list[str]:
        lines: list[str] = []
        current_round = 0

        for entry in self.entries:
            agent = entry.get("agent", "")
            role = entry.get("role", "")
            content = entry.get("content", "")
            meta = entry.get("metadata", {})

            if role == "decision":
                round_num = meta.get("round", current_round + 1)
                if round_num != current_round:
                    current_round = round_num
                    lines.append(f"## Round {current_round}")
                    lines.append("")

                lines.append(f"### Manager Decision")
                lines.append("")
                lines.append(f"**{agent}**: {content}")
                lines.append("")
                reasoning = meta.get("reasoning", "")
                if reasoning:
                    lines.append(f"> **Reasoning**: {reasoning}")
                    lines.append("")

            elif role == "assistant":
                lines.append(f"### {agent} Response")
                lines.append("")
                # Show execution metadata
                tokens = meta.get("total_tokens")
                cost = meta.get("cost_usd")
                latency = meta.get("latency_s")
                phase = meta.get("phase", "")
                if phase:
                    lines.append(f"*Phase: {phase}*")
                    lines.append("")
                if tokens is not None:
                    lines.append(
                        f"*Tokens: {tokens:,} | "
                        f"Cost: ${cost:.4f} | "
                        f"Latency: {latency:.1f}s*"
                    )
                    lines.append("")
                lines.append(content)
                lines.append("")
                lines.append("---")
                lines.append("")

        return lines

    def _render_dicwo_trace(self) -> list[str]:
        lines: list[str] = []
        current_round = 0

        for entry in self.entries:
            agent = entry.get("agent", "")
            role = entry.get("role", "")
            content = entry.get("content", "")
            meta = entry.get("metadata", {})

            round_num = meta.get("round", 0)
            subtask = meta.get("subtask", "")

            # New iteration header
            if round_num > current_round and round_num > 0:
                current_round = round_num
                lines.append(f"## Iteration {current_round}")
                lines.append("")

            if role == "bidding":
                lines.append(f"### Bidding & Coalitions")
                lines.append("")
                lines.append(f"**{agent}**: {content}")
                lines.append("")

            elif role == "consensus":
                lines.append(f"### Consensus Selection")
                if subtask:
                    lines[-1] = f"### Consensus Selection — `{subtask}`"
                lines.append("")
                lines.append(f"**{agent}**: {content}")
                lines.append("")

            elif role == "assistant":
                protocol = meta.get("protocol", "")
                phase = meta.get("phase", "")
                header = f"### {agent}"
                if protocol:
                    header += f" (protocol: {protocol})"
                if phase:
                    header += f" [{phase}]"
                lines.append(header)
                lines.append("")
                tokens = meta.get("total_tokens")
                cost = meta.get("cost_usd")
                latency = meta.get("latency_s")
                if tokens is not None:
                    lines.append(
                        f"*Tokens: {tokens:,} | "
                        f"Cost: ${cost:.4f} | "
                        f"Latency: {latency:.1f}s*"
                    )
                    lines.append("")
                lines.append(content)
                lines.append("")
                lines.append("---")
                lines.append("")

            elif role == "checkpoint":
                lines.append(f"### Checkpoint Evaluation")
                if subtask:
                    lines[-1] = f"### Checkpoint Evaluation — `{subtask}`"
                lines.append("")
                lines.append(f"**{agent}**: {content}")
                lines.append("")

            elif role == "policy":
                lines.append(f"### Policy Decision")
                lines.append("")
                lines.append(f"**{agent}**: {content}")
                lines.append("")

            elif role == "rewire":
                lines.append(f"### Topology Rewire")
                lines.append("")
                lines.append(f"**{agent}**: {content}")
                lines.append("")

            elif role == "factory":
                lines.append(f"### Agent Spawned")
                lines.append("")
                lines.append(f"**{agent}**: {content}")
                lines.append("")

            else:
                # Catch-all for unexpected roles
                lines.append(f"### {agent} ({role})")
                lines.append("")
                lines.append(content)
                lines.append("")

        return lines

    def _render_generic_trace(self) -> list[str]:
        lines: list[str] = []
        for entry in self.entries:
            agent = entry.get("agent", "unknown")
            role = entry.get("role", "")
            content = entry.get("content", "")
            lines.append(f"### {agent} ({role})")
            lines.append("")
            lines.append(content)
            lines.append("")
            lines.append("---")
            lines.append("")
        return lines


def save_json(data: Any, path: Path) -> None:
    """Write any serializable data to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def load_json(path: Path) -> Any:
    """Read a JSON file."""
    with open(path) as f:
        return json.load(f)
