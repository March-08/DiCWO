"""Communication graph management for DiCWO agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TopologyGraph:
    """Directed communication graph between agents.

    Edges represent allowed communication channels. The topology can be
    rewired by the policy engine based on checkpoint signals.
    """

    nodes: set[str] = field(default_factory=set)
    edges: dict[str, set[str]] = field(default_factory=dict)

    def add_node(self, name: str) -> None:
        self.nodes.add(name)
        self.edges.setdefault(name, set())

    def remove_node(self, name: str) -> None:
        self.nodes.discard(name)
        self.edges.pop(name, None)
        for neighbors in self.edges.values():
            neighbors.discard(name)

    def add_edge(self, source: str, target: str) -> None:
        self.edges.setdefault(source, set()).add(target)

    def remove_edge(self, source: str, target: str) -> None:
        if source in self.edges:
            self.edges[source].discard(target)

    def neighbors(self, name: str) -> set[str]:
        return self.edges.get(name, set())

    def set_fully_connected(self) -> None:
        """Make all nodes connected to all others."""
        for node in self.nodes:
            self.edges[node] = self.nodes - {node}

    def set_star(self, center: str) -> None:
        """Star topology: center connects to all, others only to center."""
        for node in self.nodes:
            if node == center:
                self.edges[node] = self.nodes - {node}
            else:
                self.edges[node] = {center}

    def set_ring(self, order: list[str] | None = None) -> None:
        """Ring topology: each node connects to next in order."""
        ordered = order or sorted(self.nodes)
        for i, node in enumerate(ordered):
            next_node = ordered[(i + 1) % len(ordered)]
            self.edges[node] = {next_node}

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": sorted(self.nodes),
            "edges": {k: sorted(v) for k, v in self.edges.items()},
        }

    @classmethod
    def from_agents(cls, agent_names: list[str], topology: str = "full") -> TopologyGraph:
        """Create a topology from a list of agent names."""
        graph = cls()
        for name in agent_names:
            graph.add_node(name)

        if topology == "full":
            graph.set_fully_connected()
        elif topology == "star":
            graph.set_star(agent_names[0])
        elif topology == "ring":
            graph.set_ring(agent_names)

        return graph
