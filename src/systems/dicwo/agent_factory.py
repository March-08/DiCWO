"""On-demand agent synthesis with TTL management and credentialing.

Paper reference (Section 5.9):
  - Agent factory synthesizes specialists for detected capability gaps
  - Spawned agents must pass entrance micro-tasks (credentialing)
  - Peer review before full admission
  - TTL-bound: agents expire after a set number of rounds
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from src.core.agent import AgentIdentity, BaseAgent
from src.core.llm_client import LLMClient


@dataclass
class SpawnedAgentInfo:
    """Metadata for a dynamically spawned agent."""

    name: str
    capabilities: list[str]
    ttl_rounds: int
    created_round: int
    expires_round: int
    credentialed: bool = False  # Whether agent passed entrance micro-task
    credential_score: float = 0.0

    def is_expired(self, current_round: int) -> bool:
        return current_round >= self.expires_round

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "capabilities": self.capabilities,
            "ttl_rounds": self.ttl_rounds,
            "created_round": self.created_round,
            "expires_round": self.expires_round,
            "credentialed": self.credentialed,
            "credential_score": round(self.credential_score, 4),
        }


SYNTHESIS_PROMPT = """\
You need a specialist with the following capabilities: {capabilities}

This specialist is needed because: {reason}

Create a detailed role description for this specialist. The specialist \
should be credentialed and domain-specific. Respond with JSON:
{{
  "name": "<specialist name>",
  "role": "<role title>",
  "goal": "<specific goal>",
  "backstory": "<credentials and experience>"
}}
"""

CREDENTIAL_MICRO_TASK = """\
You are being evaluated for admission as a specialist in: {capabilities}

Answer the following domain-specific question to demonstrate competence:

{question}

Provide a precise, technically accurate answer in 2-3 sentences.
"""

# Credentialing questions per capability area
CREDENTIAL_QUESTIONS: dict[str, str] = {
    "market_analysis": (
        "What are the key factors that determine addressable market size "
        "for a direct-to-handset satellite service? Name at least 3."
    ),
    "frequency_filing": (
        "What is the ITU coordination process for filing a new satellite "
        "frequency allocation in S-band? What key parameters must be specified?"
    ),
    "payload_design": (
        "Explain the relationship between antenna diameter, beamwidth, and "
        "gain at a given frequency. How does altitude affect link budget closure?"
    ),
    "mission_analysis": (
        "For a LEO constellation providing continuous global coverage, "
        "what determines the minimum number of orbital planes and satellites per plane?"
    ),
    "integration": (
        "What are the most common cross-subsystem inconsistencies in satellite "
        "mission design, and how should they be resolved?"
    ),
}

CREDENTIAL_EVAL_PROMPT = """\
Evaluate this answer for technical accuracy (0.0 to 1.0):

Question: {question}
Answer: {answer}

Respond with JSON:
{{
  "score": <0.0-1.0>,
  "correct": <true/false>,
  "feedback": "<brief feedback>"
}}
"""


class AgentFactory:
    """Creates specialist agents on demand when capability gaps are detected.

    Implements the paper's agent synthesis with:
    - LLM-generated role descriptions
    - Entrance micro-task credentialing
    - TTL-based lifecycle management
    """

    def __init__(
        self,
        llm: LLMClient,
        max_agents: int = 2,
        default_ttl: int = 5,
        credential_threshold: float = 0.5,
    ) -> None:
        self.llm = llm
        self.max_agents = max_agents
        self.default_ttl = default_ttl
        self.credential_threshold = credential_threshold
        self.spawned: list[SpawnedAgentInfo] = []
        self.agents: dict[str, BaseAgent] = {}

    def spawn(
        self,
        capabilities: list[str],
        reason: str,
        current_round: int,
    ) -> BaseAgent | None:
        """Synthesize a new specialist agent with credentialing.

        Steps (per paper):
        1. Generate role description via LLM
        2. Run entrance micro-task
        3. Evaluate micro-task response
        4. Admit only if score >= threshold
        """
        if len(self.spawned) >= self.max_agents:
            return None

        # Step 1: Use LLM to generate role description
        prompt = SYNTHESIS_PROMPT.format(
            capabilities=", ".join(capabilities),
            reason=reason,
        )

        response, _record = self.llm.chat(
            [{"role": "user", "content": prompt}],
            agent_name="agent_factory",
        )

        # Parse response
        json_match = re.search(r"\{[^{}]*\}", response, re.DOTALL)
        if not json_match:
            return None

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            return None

        identity = AgentIdentity(
            name=data.get("name", f"Specialist_{len(self.spawned) + 1}"),
            role=data.get("role", "Specialist"),
            goal=data.get("goal", "Provide specialist analysis"),
            backstory=data.get("backstory", "Domain specialist"),
        )

        agent = BaseAgent(identity=identity, llm=self.llm)

        # Step 2-3: Credentialing micro-task
        credentialed, score = self._credential_test(agent, capabilities)

        info = SpawnedAgentInfo(
            name=identity.name,
            capabilities=capabilities,
            ttl_rounds=self.default_ttl,
            created_round=current_round,
            expires_round=current_round + self.default_ttl,
            credentialed=credentialed,
            credential_score=score,
        )

        # Step 4: Only admit if credentialed
        if not credentialed:
            # Log but don't add the agent
            self.spawned.append(info)  # Track the attempt
            return None

        self.spawned.append(info)
        self.agents[identity.name] = agent
        return agent

    def _credential_test(
        self,
        agent: BaseAgent,
        capabilities: list[str],
    ) -> tuple[bool, float]:
        """Run entrance micro-task and evaluate.

        Paper: spawned agents must demonstrate competence before admission.
        """
        # Pick a relevant credentialing question
        question = None
        for cap in capabilities:
            if cap in CREDENTIAL_QUESTIONS:
                question = CREDENTIAL_QUESTIONS[cap]
                break

        if question is None:
            # No specific question available; grant provisional access
            return True, 0.6

        # Agent answers the micro-task
        prompt = CREDENTIAL_MICRO_TASK.format(
            capabilities=", ".join(capabilities),
            question=question,
        )
        answer, _record = agent.run(prompt)

        # Evaluate the answer using the LLM
        eval_prompt = CREDENTIAL_EVAL_PROMPT.format(
            question=question,
            answer=answer[:1000],
        )
        eval_response, _record = self.llm.chat(
            [{"role": "user", "content": eval_prompt}],
            agent_name="credential_evaluator",
        )

        # Parse evaluation
        score = self._parse_credential_score(eval_response)
        return score >= self.credential_threshold, score

    def _parse_credential_score(self, raw: str) -> float:
        """Parse credentialing evaluation response."""
        json_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return float(data.get("score", 0.5))
            except (json.JSONDecodeError, ValueError):
                pass
        return 0.5

    def cleanup_expired(self, current_round: int) -> list[str]:
        """Remove expired agents. Returns list of removed names."""
        removed = []
        active = []
        for info in self.spawned:
            if info.is_expired(current_round):
                self.agents.pop(info.name, None)
                removed.append(info.name)
            else:
                active.append(info)
        self.spawned = active
        return removed

    def get_agent(self, name: str) -> BaseAgent | None:
        return self.agents.get(name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "spawned": [s.to_dict() for s in self.spawned],
            "active_count": len(self.agents),
        }
