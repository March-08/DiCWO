"""System 3: DiCWO — Distributed Calibration-Weighted Orchestration.

Main orchestration loop matching the paper's pseudocode (Section 5.9):

  Initialize shared state S_0 from T
  for t = 0..T_max:
      broadcast S_t (compressed)
      for each agent: B_i(t) = EmitBeacon(S_t, P_i)
      Delta*(t) = ConsensusMerge({Decompose(S_t, P_i)})   # consensus decomposition
      for each subtask T_k in Delta*(t):
          bids = {bid_{i,k}(t)}
          (A, G, p) = ConsensusSelect(bids, coalitions)   # team, topology, protocol
          outputs_k = ExecuteProtocol(A, G, p, S_t)
          WriteArtifactsToMemory(outputs_k)
      Gamma_t = CheckpointSignals(S_t, new_artifacts)
      action = pi(Gamma_t, budgets)
      if action == HITL: ...
      if action == CREATE_AGENT: ...
      UpdateCalibrationReputationSynergy(S_t, outcomes)
      if AcceptanceCriteriaMet(S_t): break
"""

from __future__ import annotations

from typing import Any

from src.core.agent import AgentIdentity, BaseAgent
from src.core.config import ExperimentConfig
from src.core.llm_client import LLMClient
from src.domain.prompts import (
    CONTEXT_INJECTION,
    INTEGRATION_PROMPT,
    TASK_DESCRIPTIONS,
)
from src.domain.roles import SPECIALIST_ROLES, STUDY_MANAGER
from src.evaluation.validators import validate_artifacts
from src.systems.base_system import BaseSystem, SystemResult
from src.systems.dicwo.agent_factory import AgentFactory
from src.systems.dicwo.beacon import AGENT_CAPABILITIES, Beacon, BeaconRegistry
from src.systems.dicwo.bidding import BiddingEngine
from src.systems.dicwo.checkpoint import CheckpointEvaluator, CheckpointSignals
from src.systems.dicwo.consensus import ConsensusEngine
from src.systems.dicwo.hitl import HITLManager
from src.systems.dicwo.policy import PolicyAction, PolicyEngine
from src.systems.dicwo.topology import TopologyGraph


# Default subtask list (can be reordered by consensus decomposition)
DEFAULT_SUBTASKS = [
    "market_analysis",
    "frequency_filing",
    "payload_design",
    "mission_analysis",
    "integration",
]

# Subtask criticality (used in consensus protocol selection)
SUBTASK_CRITICALITY: dict[str, str] = {
    "market_analysis": "medium",
    "frequency_filing": "high",
    "payload_design": "high",
    "mission_analysis": "high",
    "integration": "critical",
}

# Execution protocols (paper Section 5.9)
PROTOCOL_DESCRIPTIONS = {
    "solo": "Single assigned agent executes alone",
    "audit": "Primary agent executes, secondary agent reviews",
    "debate": "Two agents debate, consensus selects best answer",
    "parallel": "Multiple agents execute in parallel, best output selected",
    "tool_verified": "Agent executes, then deterministic validators check claims",
}


class DiCWOSystem(BaseSystem):
    """Full DiCWO distributed orchestration system.

    Matches the paper's main loop with all mechanisms:
    - Consensus-based task decomposition
    - 4-term calibration-weighted bidding
    - ConsensusSelect for protocol
    - Checkpoint signals with 4 dimensions
    - Policy engine with 7 actions
    - HITL with EVoI and budget
    - Agent factory with credentialing
    - Subtask revisiting on failure
    - Acceptance criteria for early exit
    - Reputation and synergy tracking
    """

    def __init__(self, config: ExperimentConfig, llm: LLMClient) -> None:
        super().__init__(config, llm)
        params = config.system_params

        # Create specialist agents
        self.agents: dict[str, BaseAgent] = {}
        for role in SPECIALIST_ROLES:
            self.agents[role.name] = BaseAgent(identity=role, llm=llm)
        self.agents[STUDY_MANAGER.name] = BaseAgent(identity=STUDY_MANAGER, llm=llm)

        # DiCWO components
        self.registry = BeaconRegistry()
        self.bidding = BiddingEngine(
            alpha=params.get("bid_alpha", 1.0),
            beta=params.get("bid_beta", 0.5),
            gamma=params.get("bid_gamma", 0.3),
            delta=params.get("bid_delta", 0.2),
            calibration_decay=params.get("calibration_decay", 0.9),
        )
        self.consensus = ConsensusEngine(
            threshold=params.get("consensus_threshold", 0.7),
            min_voters=params.get("min_voters", 3),
        )
        self.checkpoint_eval = CheckpointEvaluator(
            disagreement_threshold=params.get("disagreement_threshold", 0.3),
            uncertainty_threshold=params.get("uncertainty_threshold", 0.5),
            risk_threshold=params.get("risk_threshold", 0.6),
        )
        self.policy = PolicyEngine(
            hitl_evoi_threshold=params.get("hitl_evoi_threshold", 0.7),
            max_spawned_agents=params.get("max_spawned_agents", 2),
            max_hitl_calls=params.get("max_hitl_calls", 3),
            disagreement_threshold=params.get("disagreement_threshold", 0.3),
            uncertainty_threshold=params.get("uncertainty_threshold", 0.5),
            risk_threshold=params.get("risk_threshold", 0.6),
            acceptance_quality=params.get("acceptance_quality", 0.7),
        )
        self.factory = AgentFactory(
            llm=llm,
            max_agents=params.get("max_spawned_agents", 2),
            default_ttl=params.get("agent_ttl_rounds", 5),
            credential_threshold=params.get("credential_threshold", 0.5),
        )
        self.hitl = HITLManager(
            evoi_threshold=params.get("hitl_evoi_threshold", 0.7),
            max_calls=params.get("max_hitl_calls", 3),
        )
        self.topology = TopologyGraph.from_agents(
            list(self.agents.keys()), topology="full"
        )

        # Max retries for a failed subtask before moving on
        self.max_retries = params.get("max_subtask_retries", 1)

    def run(self) -> SystemResult:
        """Main DiCWO orchestration loop (paper Section 5.9 pseudocode)."""
        max_rounds = self.config.max_rounds
        completed_subtasks: list[str] = []
        retry_counts: dict[str, int] = {}
        round_num = 0
        early_stop = False

        # Phase 0: Consensus-based task decomposition
        subtask_queue = self._consensus_decomposition(completed_subtasks)
        print(f"  [DiCWO] Consensus subtask order: {subtask_queue}")

        while subtask_queue and round_num < max_rounds:
            subtask = subtask_queue[0]
            round_num += 1
            print(f"  [DiCWO] Round {round_num}/{max_rounds} — subtask: {subtask}")

            # Phase 1: Broadcast beacons (paper: EmitBeacon)
            self._broadcast_beacons(round_num)

            # Anti-gaming: down-weight unsupported beacons
            self.registry.downweight_unsupported()

            # Phase 2: Bidding (paper: bid_{i,k}(t) = alpha*fit - beta*cal - gamma*cost + delta*div)
            bids = self.bidding.compute_bids(subtask, self.registry)
            winner_name = self.bidding.assign(subtask, self.registry)
            if winner_name is None:
                print(f"  [DiCWO] No agent available for {subtask}, skipping")
                subtask_queue.pop(0)
                continue

            # Get coalition (top-2 agents for the subtask)
            coalition = self.bidding.get_top_k(subtask, self.registry, k=2)

            self.logger.log(
                agent="DiCWO",
                role="bidding",
                content=(
                    f"Assigned '{subtask}' to {winner_name} "
                    f"(coalition: {coalition}, bids: {[b.to_dict() for b in bids[:3]]})"
                ),
                metadata={"round": round_num},
            )

            # Phase 3: ConsensusSelect for protocol (paper: distributed consensus on protocol)
            protocol = self._consensus_select_protocol(subtask, winner_name, round_num)

            self.logger.log(
                agent="DiCWO",
                role="consensus",
                content=f"Protocol: {protocol}",
                metadata={"round": round_num},
            )

            # Phase 4: Execute protocol
            outputs = self._execute(subtask, winner_name, protocol, coalition)

            # Phase 5: Checkpoint signals
            signals = self._checkpoint(subtask, outputs, round_num)

            self.logger.log(
                agent="DiCWO",
                role="checkpoint",
                content=f"Signals: {signals.to_dict()}",
                metadata={"round": round_num},
            )

            # Phase 6: Policy decision
            decision = self._apply_policy(signals, subtask, round_num, max_rounds)

            self.logger.log(
                agent="DiCWO",
                role="policy",
                content=f"Decision: {decision.to_dict()}",
                metadata={"round": round_num},
            )

            # Handle policy actions
            should_advance = self._handle_policy(
                decision, signals, subtask, round_num, outputs, winner_name
            )

            if decision.action == PolicyAction.STOP:
                early_stop = True
                # Still store the output before stopping
                self._store_output(subtask, outputs, winner_name)
                completed_subtasks.append(subtask)
                subtask_queue.pop(0)
                print("  [DiCWO] Acceptance criteria met — early stop")
                break

            if should_advance:
                # Store output and advance to next subtask
                self._store_output(subtask, outputs, winner_name)
                completed_subtasks.append(subtask)
                subtask_queue.pop(0)

                # Add evidence to winner's beacon (for anti-gaming)
                beacon = self.registry.beacons.get(winner_name)
                if beacon:
                    beacon.evidence.append(f"completed:{subtask}:round{round_num}")
            else:
                # Subtask failed checkpoint — retry or skip
                retry_counts[subtask] = retry_counts.get(subtask, 0) + 1
                if retry_counts[subtask] > self.max_retries:
                    print(f"  [DiCWO] Max retries for {subtask}, accepting current output")
                    self._store_output(subtask, outputs, winner_name)
                    completed_subtasks.append(subtask)
                    subtask_queue.pop(0)
                else:
                    print(f"  [DiCWO] Retrying {subtask} (attempt {retry_counts[subtask]})")

            # UpdateCalibrationReputationSynergy (paper Section 5.9)
            success = signals.risk < 0.5
            quality = 1.0 - signals.risk
            self.bidding.update_calibration(winner_name, self.registry, success)
            self.bidding.update_reputation(winner_name, quality)
            if len(coalition) >= 2:
                self.bidding.update_synergy(coalition[0], coalition[1], quality)

            # Cleanup expired spawned agents
            removed = self.factory.cleanup_expired(round_num)
            for name in removed:
                self.agents.pop(name, None)
                self.topology.remove_node(name)

        # Final integration if not already done
        if "integration" not in completed_subtasks and not early_stop:
            self._run_integration()
            completed_subtasks.append("integration")

        return SystemResult(
            artifacts=self.state.artifacts,
            conversation_log=self.logger.to_list(),
            metadata={
                "system_type": "dicwo",
                "rounds_used": round_num,
                "completed_subtasks": completed_subtasks,
                "early_stop": early_stop,
                "hitl": self.hitl.to_dict(),
                "spawned_agents": self.factory.to_dict(),
                "topology": self.topology.to_dict(),
                "reputation": dict(self.bidding.reputation),
                "synergy": {
                    k: dict(v) for k, v in self.bidding.synergy.items()
                },
                "subtask_quality": dict(self.policy.subtask_quality),
            },
        )

    # ------------------------------------------------------------------
    # Internal phases
    # ------------------------------------------------------------------

    def _consensus_decomposition(self, completed: list[str]) -> list[str]:
        """Paper: ConsensusMerge({Decompose(S_t, P_i)}).

        Agents propose subtask orderings, merged via Borda count.
        """
        remaining = [s for s in DEFAULT_SUBTASKS if s not in completed]
        if len(remaining) <= 1:
            return remaining

        context = self.state.get_context_summary() if self.state.artifacts else ""
        return self.consensus.decompose_and_merge(
            available_subtasks=remaining,
            completed_subtasks=completed,
            agents=self.agents,
            context=context,
        )

    def _broadcast_beacons(self, round_num: int) -> None:
        """All agents broadcast their capabilities (paper: EmitBeacon)."""
        for name, agent in self.agents.items():
            caps = AGENT_CAPABILITIES.get(name, [])
            # Check spawned agents
            if not caps:
                for info in self.factory.spawned:
                    if info.name == name:
                        caps = info.capabilities
                        break

            # Preserve existing beacon state (calibration, evidence)
            existing = self.registry.beacons.get(name)

            beacon = Beacon(
                agent_name=name,
                capabilities=caps,
                confidence=0.8,
                calibration_score=(
                    existing.calibration_score if existing else 1.0
                ),
                round_num=round_num,
                evidence=existing.evidence if existing else [],
                evidence_weight=existing.evidence_weight if existing else 1.0,
                needs=self._infer_needs(name),
                estimated_cost=0.3,  # Default; could be dynamic
            )
            self.registry.register(beacon)

    def _consensus_select_protocol(
        self,
        subtask: str,
        primary_agent: str,
        round_num: int,
    ) -> str:
        """Paper: ConsensusSelect — distributed consensus on execution protocol.

        Uses lightweight consensus (3 voters) to select protocol.
        For round 1, use heuristic to avoid costly consensus on first pass.
        """
        if round_num <= 1 and subtask in ("market_analysis",):
            # First subtask is low-risk, skip consensus overhead
            return "solo"

        # Get recent disagreement level
        prev_disagreement = 0.0
        if self.policy.subtask_quality:
            last_quality = list(self.policy.subtask_quality.values())[-1]
            prev_disagreement = 1.0 - last_quality

        context = self.state.get_context_summary() if self.state.artifacts else ""
        criticality = SUBTASK_CRITICALITY.get(subtask, "medium")

        # Use a subset of agents for efficiency (paper allows any subset)
        voter_names = list(self.agents.keys())[:3]
        voters = {n: self.agents[n] for n in voter_names if n in self.agents}

        return self.consensus.consensus_select_protocol(
            subtask=subtask,
            primary_agent=primary_agent,
            agents=voters,
            context=context,
            criticality=criticality,
            disagreement=prev_disagreement,
        )

    def _execute(
        self,
        subtask: str,
        primary_agent: str,
        protocol: str,
        coalition: list[str] | None = None,
    ) -> dict[str, str]:
        """Execute a subtask using the selected protocol."""
        task_desc = TASK_DESCRIPTIONS.get(subtask, subtask)
        outputs: dict[str, str] = {}

        # Inject context from previous artifacts
        context = ""
        if self.state.artifacts:
            context = CONTEXT_INJECTION.format(
                context=self.state.get_context_summary()
            )

        if protocol == "solo":
            agent = self.agents[primary_agent]
            if context:
                agent.inject_context(context)
            response, record = agent.run(task_desc)
            outputs[primary_agent] = response

            self.logger.log(
                agent=primary_agent,
                role="assistant",
                content=response,
                metadata={**record.to_dict(), "protocol": "solo"},
            )

        elif protocol == "audit":
            # Primary executes, then another agent reviews
            agent = self.agents[primary_agent]
            if context:
                agent.inject_context(context)
            response, record = agent.run(task_desc)
            outputs[primary_agent] = response

            self.logger.log(
                agent=primary_agent,
                role="assistant",
                content=response,
                metadata={**record.to_dict(), "protocol": "audit", "phase": "execute"},
            )

            # Find reviewer (from coalition or Study Manager)
            reviewer_name = STUDY_MANAGER.name
            if coalition and len(coalition) >= 2:
                reviewer_name = coalition[1] if coalition[0] == primary_agent else coalition[0]
            if reviewer_name == primary_agent:
                for name in self.agents:
                    if name != primary_agent:
                        reviewer_name = name
                        break

            reviewer = self.agents.get(reviewer_name)
            if reviewer:
                review_prompt = (
                    f"Review the following output for '{subtask}':\n\n"
                    f"{response[:3000]}\n\n"
                    f"Identify any errors, inconsistencies, or missing elements. "
                    f"If the output is correct, confirm it. If not, provide corrections."
                )
                review, r_record = reviewer.run(review_prompt)
                outputs[reviewer_name] = review

                self.logger.log(
                    agent=reviewer_name,
                    role="assistant",
                    content=review,
                    metadata={**r_record.to_dict(), "protocol": "audit", "phase": "review"},
                )

        elif protocol == "debate":
            # Two agents from coalition produce outputs, then debate
            debate_agents = []
            if coalition and len(coalition) >= 2:
                debate_agents = [self.agents[n] for n in coalition[:2] if n in self.agents]
            if len(debate_agents) < 2:
                debate_agents = [
                    a for name, a in self.agents.items()
                    if name != STUDY_MANAGER.name
                ][:2]

            for agent in debate_agents:
                if context:
                    agent.inject_context(context)
                response, record = agent.run(task_desc)
                outputs[agent.name] = response

                self.logger.log(
                    agent=agent.name,
                    role="assistant",
                    content=response,
                    metadata={**record.to_dict(), "protocol": "debate"},
                )

        elif protocol == "parallel":
            # All capable agents execute in parallel (sequential in practice)
            capable = self.registry.get_capable_agents(subtask)
            agent_names = [b.agent_name for b in capable] or [primary_agent]

            for name in agent_names[:3]:  # Cap at 3
                agent = self.agents.get(name)
                if not agent:
                    continue
                if context:
                    agent.inject_context(context)
                response, record = agent.run(task_desc)
                outputs[name] = response

                self.logger.log(
                    agent=name,
                    role="assistant",
                    content=response,
                    metadata={**record.to_dict(), "protocol": "parallel"},
                )

        elif protocol == "tool_verified":
            # Agent executes, then deterministic validators check claims
            agent = self.agents[primary_agent]
            if context:
                agent.inject_context(context)
            response, record = agent.run(task_desc)
            outputs[primary_agent] = response

            self.logger.log(
                agent=primary_agent,
                role="assistant",
                content=response,
                metadata={**record.to_dict(), "protocol": "tool_verified", "phase": "execute"},
            )

            # Run deterministic validators on the output
            validation = validate_artifacts({subtask: response})
            validator_summary = (
                f"Validator results for '{subtask}': "
                f"{validation['passed']}/{validation['total_checks']} checks passed. "
            )
            for check in validation["checks"]:
                if not check.get("pass", True):
                    validator_summary += f"FAILED: {check['check']} — {check}. "

            self.logger.log(
                agent="tool_validator",
                role="system",
                content=validator_summary,
                metadata={"protocol": "tool_verified", "phase": "validate", "validation": validation},
            )

            # If validators found issues, ask agent to self-correct
            if validation["verified_claims_ratio"] < 1.0:
                correction_prompt = (
                    f"The following validator checks found issues in your output:\n\n"
                    f"{validator_summary}\n\n"
                    f"Please revise your output to address these issues. "
                    f"Original output:\n{response[:2000]}"
                )
                corrected, c_record = agent.run(correction_prompt)
                outputs[primary_agent] = corrected  # Replace with corrected version

                self.logger.log(
                    agent=primary_agent,
                    role="assistant",
                    content=corrected,
                    metadata={**c_record.to_dict(), "protocol": "tool_verified", "phase": "correct"},
                )

        return outputs

    def _checkpoint(
        self,
        subtask: str,
        outputs: dict[str, str],
        round_num: int,
    ) -> CheckpointSignals:
        """Evaluate outputs and compute checkpoint signals."""
        reviewer = self.agents.get(STUDY_MANAGER.name)
        if reviewer is None:
            reviewer = BaseAgent(identity=STUDY_MANAGER, llm=self.llm)

        return self.checkpoint_eval.evaluate(subtask, outputs, reviewer)

    def _apply_policy(
        self,
        signals: CheckpointSignals,
        subtask: str,
        round_num: int,
        max_rounds: int,
    ) -> Any:
        """Apply policy engine to decide next action."""
        available_caps = set()
        for beacon in self.registry.all_beacons():
            available_caps.update(beacon.capabilities)

        needed_caps = set(TASK_DESCRIPTIONS.keys())

        return self.policy.decide(
            signals=signals,
            round_num=round_num,
            max_rounds=max_rounds,
            available_capabilities=available_caps,
            needed_capabilities=needed_caps,
            subtask=subtask,
        )

    def _handle_policy(
        self,
        decision: Any,
        signals: CheckpointSignals,
        subtask: str,
        round_num: int,
        outputs: dict[str, str],
        winner_name: str,
    ) -> bool:
        """Handle a policy decision. Returns True if subtask should advance."""

        if decision.action == PolicyAction.HITL:
            # Record HITL budget usage
            self.policy.record_hitl()
            q = self.hitl.generate_question(
                subtask, signals, self.state.get_context_summary()
            )
            self.logger.log(
                agent="DiCWO",
                role="hitl",
                content=f"HITL question: {q.question}",
                metadata={"round": round_num, "evoi": q.evoi, "budget_remaining": self.hitl.budget_remaining},
            )
            # Auto-respond in experiment mode (no real human)
            self.hitl.record_response(len(self.hitl.questions) - 1, "continue")
            return True  # Advance despite HITL (in automated mode)

        elif decision.action == PolicyAction.SPAWN:
            missing = decision.params.get("missing_capabilities", [])
            agent = self.factory.spawn(missing, decision.reason, round_num)
            if agent:
                self.agents[agent.name] = agent
                self.topology.add_node(agent.name)
                self.topology.set_fully_connected()
                self.registry.register(Beacon(
                    agent_name=agent.name,
                    capabilities=missing,
                    confidence=0.7,
                    round_num=round_num,
                ))
                self.policy.record_spawn()
                self.logger.log(
                    agent="DiCWO",
                    role="factory",
                    content=f"Spawned agent: {agent.name} (credentialed)",
                    metadata={"round": round_num},
                )
            return True

        elif decision.action == PolicyAction.REWIRE:
            target = decision.params.get("target_topology", "full")
            if target == "full":
                self.topology.set_fully_connected()
            elif target == "star":
                self.topology.set_star(STUDY_MANAGER.name)
            return True

        elif decision.action == PolicyAction.VERIFY:
            # Run deterministic validators on the output
            validation = validate_artifacts({subtask: outputs.get(winner_name, "")})
            self.logger.log(
                agent="tool_validator",
                role="system",
                content=f"Verification: {validation['passed']}/{validation['total_checks']} passed",
                metadata={"round": round_num, "validation": validation},
            )
            # If validation failed significantly, retry the subtask
            if validation["verified_claims_ratio"] < 0.5:
                return False  # Don't advance; retry
            return True

        elif decision.action == PolicyAction.ESCALATE:
            # Log escalation; in experiment mode, continue anyway
            return True

        elif decision.action == PolicyAction.STOP:
            return True  # Handled in caller

        # CONTINUE
        return True

    def _store_output(
        self,
        subtask: str,
        outputs: dict[str, str],
        winner_name: str,
    ) -> None:
        """Store the primary output in shared state."""
        primary_output = outputs.get(winner_name, list(outputs.values())[0] if outputs else "")
        self.state.publish(subtask, primary_output, source=winner_name)

    def _infer_needs(self, agent_name: str) -> list[str]:
        """Infer what an agent needs from others based on current state."""
        caps = AGENT_CAPABILITIES.get(agent_name, [])
        all_subtasks = set(DEFAULT_SUBTASKS)
        own_subtasks = set(caps) & all_subtasks
        return list(all_subtasks - own_subtasks)

    def _run_integration(self) -> None:
        """Final integration pass by Study Manager."""
        all_outputs = self.state.get_context_summary()
        prompt = INTEGRATION_PROMPT.format(all_outputs=all_outputs)

        integrator = self.agents.get(STUDY_MANAGER.name)
        if integrator is None:
            integrator = BaseAgent(identity=STUDY_MANAGER, llm=self.llm)

        response, record = integrator.run(prompt)

        self.logger.log(
            agent="Study Manager",
            role="assistant",
            content=response,
            metadata={**record.to_dict(), "phase": "integration"},
        )

        self.state.publish("integration", response, source="Study Manager")
