"""System 2: Centralized Manager — manager routes to specialist agents."""

from __future__ import annotations

from src.core.agent import BaseAgent
from src.core.config import ExperimentConfig
from src.core.llm_client import LLMClient
from src.domain.prompts import CONTEXT_INJECTION, INTEGRATION_PROMPT
from src.domain.roles import ROLE_MAP, SPECIALIST_ROLES, STUDY_MANAGER
from src.systems.base_system import BaseSystem, SystemResult
from src.systems.centralized.manager import ManagerAgent


class CentralizedSystem(BaseSystem):
    """Manager-driven hierarchical system mirroring the CrewAI process."""

    def __init__(self, config: ExperimentConfig, llm: LLMClient) -> None:
        super().__init__(config, llm)
        self.manager = ManagerAgent(llm)
        # Create specialist agents
        self.specialists: dict[str, BaseAgent] = {}
        for role in SPECIALIST_ROLES:
            self.specialists[role.name] = BaseAgent(identity=role, llm=llm)

    def run(self) -> SystemResult:
        max_rounds = self.config.max_rounds
        completed_tasks: list[str] = []

        for round_num in range(max_rounds):
            remaining = max_rounds - round_num
            print(f"  [Centralized] Round {round_num + 1}/{max_rounds}")

            # Manager decides next action
            decision = self.manager.decide_next(
                self.state.artifacts, completed_tasks, remaining
            )

            self.logger.log(
                agent="Manager",
                role="decision",
                content=f"Next: {decision.next_agent} | Task: {decision.task}",
                metadata={"reasoning": decision.reasoning, "round": round_num + 1},
            )

            if decision.is_done:
                print("  [Centralized] Manager signaled DONE — running integration")
                break

            # Route to specialist
            agent = self._resolve_agent(decision.next_agent)
            if agent is None:
                print(f"  [Centralized] Unknown agent: {decision.next_agent}, skipping")
                continue

            # Inject context from previous artifacts
            if self.state.artifacts:
                context_text = CONTEXT_INJECTION.format(
                    context=self.state.get_context_summary()
                )
                agent.inject_context(context_text)

            # Specialist executes task
            response, record = agent.run(decision.task)

            self.logger.log(
                agent=agent.name,
                role="assistant",
                content=response,
                metadata=record.to_dict(),
            )

            # Publish artifact
            artifact_key = f"{agent.name.lower().replace(' ', '_')}_output"
            self.state.publish(artifact_key, response, source=agent.name)
            completed_tasks.append(f"{agent.name}: {decision.task[:80]}")

        # Integration pass
        self._run_integration()

        return SystemResult(
            artifacts=self.state.artifacts,
            conversation_log=self.logger.to_list(),
            metadata={
                "system_type": "centralized",
                "rounds_used": min(round_num + 1, max_rounds),
                "completed_tasks": completed_tasks,
            },
        )

    def _resolve_agent(self, name: str) -> BaseAgent | None:
        """Find a specialist agent by name (fuzzy match)."""
        # Exact match
        if name in self.specialists:
            return self.specialists[name]
        # Fuzzy: check if any key contains the name
        name_lower = name.lower()
        for key, agent in self.specialists.items():
            if name_lower in key.lower() or key.lower() in name_lower:
                return agent
        return None

    def _run_integration(self) -> None:
        """Final integration pass by the Study Manager."""
        all_outputs = self.state.get_context_summary()
        prompt = INTEGRATION_PROMPT.format(all_outputs=all_outputs)

        integrator = BaseAgent(identity=STUDY_MANAGER, llm=self.llm)
        response, record = integrator.run(prompt)

        self.logger.log(
            agent="Study Manager",
            role="assistant",
            content=response,
            metadata={**record.to_dict(), "phase": "integration"},
        )

        self.state.publish("integration_report", response, source="Study Manager")
