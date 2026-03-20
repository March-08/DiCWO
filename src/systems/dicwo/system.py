"""System 3: DiCWO — Distributed Calibration-Weighted Orchestration.

Main orchestration loop matching Figure 1 of the paper:

  Initialize shared state S_0 from T
  for t = 0..T_max:
      compressed = compress_state(S_t)
      broadcast beacons (compressed S_t)
      optional re-decomposition
      for each pending subtask T_k:
          bids = compute_bids(T_k)
          coalitions = propose_coalitions(T_k)
          (A, G, p) = joint_consensus_select(coalitions)
          outputs_k = execute(T_k, A[0], p, A)
      signals_map = checkpoint_iteration(outputs)
      decision = apply_policy_iteration(signals_map)
      handle_policy_v2(decision)
      maybe_spawn_agents()
      update calibration, reputation, synergy
      if acceptance_met(): break
"""

from __future__ import annotations

from typing import Any

from src.core.agent import BaseAgent
from src.core.config import ExperimentConfig
from src.core.llm_client import LLMClient
from src.domain.prompts import (
    CONTEXT_INJECTION,
    INTEGRATION_PROMPT,
    TASK_DESCRIPTIONS,
)
from src.domain.roles import SPECIALIST_ROLES, STUDY_MANAGER

from src.systems.base_system import BaseSystem, SystemResult
from src.systems.dicwo.agent_factory import AgentFactory
from src.systems.dicwo.beacon import AGENT_CAPABILITIES, Beacon, BeaconRegistry
from src.systems.dicwo.bidding import BiddingEngine
from src.systems.dicwo.checkpoint import CheckpointEvaluator, CheckpointSignals
from src.systems.dicwo.confidence import ConfidenceAction, ConfidenceGateway
from src.systems.dicwo.consensus import ConsensusEngine
from src.systems.dicwo.escalation import EscalationLadder, ESCALATION_LADDER
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
    "tool_verified": "Agent executes with extra self-review step",
}


class DiCWOSystem(BaseSystem):
    """Full DiCWO distributed orchestration system (Figure 1).

    Iteration-level processing with:
    - Consensus-based task decomposition (with re-decomposition)
    - 4-term calibration-weighted bidding + coalition proposals
    - Joint ConsensusSelect for (team, topology, protocol)
    - Checkpoint signals with 4 dimensions
    - Simplified 3-action policy (Continue / Rewire / Stop)
    - Spawn via dual trigger (coverage gap + persistent failure)
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
        self.topology = TopologyGraph.from_agents(
            list(self.agents.keys()), topology="full"
        )

        # Confidence gateway (tiered: proceed / reflect / intervene)
        self.confidence_gateway = ConfidenceGateway(
            threshold=params.get("confidence_threshold", 85),
            low_threshold=params.get("confidence_low_threshold", 50),
            max_retries=params.get("confidence_max_retries", 2),
        )

        # Protocol escalation ladder
        self.escalation = EscalationLadder()

        # Failure tracking for spawn trigger
        self.failure_tracker: dict[str, int] = {}  # subtask → consecutive failures
        self.coverage_gap_log: list[str] = []  # subtasks with no capable agents

        # Max retries for a failed subtask before moving on
        self.max_retries = params.get("max_subtask_retries", 1)

    def run(self) -> SystemResult:
        """Main DiCWO iteration-level loop (Figure 1)."""
        max_rounds = self.config.max_rounds
        completed_subtasks: list[str] = []
        round_num = 0
        early_stop = False
        last_rewire_round = 0

        # Phase 0: Consensus-based task decomposition
        subtask_queue = self._consensus_decomposition(completed_subtasks)
        print(f"  [DiCWO] Consensus subtask order: {subtask_queue}")

        while round_num < max_rounds:
            round_num += 1
            pending = [s for s in subtask_queue if s not in completed_subtasks]
            if not pending:
                break

            print(f"  [DiCWO] Iteration {round_num}/{max_rounds} — pending: {pending}")

            # Step 1: Compress state to bound context growth
            compressed = self._compress_state()

            # Step 2: Broadcast beacons with compressed state
            self._broadcast_beacons(round_num, compressed)
            self.registry.downweight_unsupported()

            # Step 3: Optional re-decomposition
            if self._should_redecompose(round_num, last_rewire_round):
                subtask_queue = self._consensus_decomposition(completed_subtasks)
                pending = [s for s in subtask_queue if s not in completed_subtasks]
                print(f"  [DiCWO] Re-decomposed subtask order: {subtask_queue}")

            # Step 4: Process each pending subtask
            iteration_outputs: dict[str, dict[str, str]] = {}
            iteration_teams: dict[str, list[str]] = {}

            for subtask in pending:
                # 4a. Compute bids
                bids = self.bidding.compute_bids(subtask, self.registry)
                if not bids:
                    self.coverage_gap_log.append(subtask)
                    print(f"  [DiCWO] No bids for {subtask}, logging coverage gap")
                    continue

                # 4b. Propose coalitions
                coalitions = self.bidding.propose_coalitions(subtask, self.registry)

                self.logger.log(
                    agent="DiCWO",
                    role="bidding",
                    content=(
                        f"Bids for '{subtask}': {[b.to_dict() for b in bids[:3]]}; "
                        f"Coalitions: {[c.to_dict() for c in coalitions[:3]]}"
                    ),
                    metadata={"round": round_num},
                )

                # 4c. Joint consensus select (team, topology, protocol)
                coalition_options = [
                    {"label": f"coalition_{i}", "members": c.members}
                    for i, c in enumerate(coalitions)
                ]
                team, topo, protocol = self._joint_consensus_select(
                    subtask, coalition_options, round_num
                )

                # Enforce escalation floor: consensus can go higher, never lower
                raw_protocol = protocol
                protocol = EscalationLadder.enforce_floor(protocol, subtask, self.escalation)

                escalation_info = ""
                if protocol != raw_protocol:
                    escalation_info = (
                        f" (escalated from {raw_protocol}, "
                        f"level {self.escalation.get_level(subtask)})"
                    )

                self.logger.log(
                    agent="DiCWO",
                    role="consensus",
                    content=(
                        f"Joint select: team={team}, topology={topo}, "
                        f"protocol={protocol}{escalation_info}"
                    ),
                    metadata={"round": round_num, "subtask": subtask},
                )

                # Apply topology
                if topo == "full":
                    self.topology.set_fully_connected()
                elif topo == "star":
                    self.topology.set_star(STUDY_MANAGER.name)

                # 4d. Execute
                primary = team[0] if team else bids[0].agent_name
                self.escalation.record_attempt(subtask)
                outputs = self._execute(subtask, primary, protocol, team)
                iteration_outputs[subtask] = outputs
                iteration_teams[subtask] = team

            # Step 5: Checkpoint all subtask outputs
            signals_map = self._checkpoint_iteration(iteration_outputs, round_num)

            # Step 6: Aggregate signals → policy decision
            decision = self._apply_policy_iteration(signals_map, round_num, max_rounds)

            self.logger.log(
                agent="DiCWO",
                role="policy",
                content=f"Iteration decision: {decision.to_dict()}",
                metadata={"round": round_num},
            )

            # Step 7: Handle policy + escalation
            #   On REWIRE: identify subtasks with bad signals and escalate them.
            #   Escalated subtasks are NOT marked completed — they re-enter pending
            #   on the next iteration with a higher protocol floor.
            self._handle_policy_v2(decision)
            escalated_this_round: set[str] = set()

            if decision.action == PolicyAction.REWIRE:
                last_rewire_round = round_num
                for subtask, signals in signals_map.items():
                    is_bad = (
                        signals.disagreement > self.policy.disagreement_threshold
                        or signals.uncertainty > self.policy.uncertainty_threshold
                    )
                    if is_bad and not self.escalation.at_max(subtask):
                        old_proto = self.escalation.get_protocol(subtask)
                        new_proto = self.escalation.escalate(subtask)
                        escalated_this_round.add(subtask)
                        print(
                            f"  [DiCWO] Escalated '{subtask}': "
                            f"{old_proto} -> {new_proto}"
                        )
                        self.logger.log(
                            agent="DiCWO",
                            role="escalation",
                            content=(
                                f"Escalated '{subtask}': {old_proto} -> {new_proto} "
                                f"(disagreement={signals.disagreement:.2f}, "
                                f"uncertainty={signals.uncertainty:.2f})"
                            ),
                            metadata={"round": round_num, "subtask": subtask},
                        )

            # Step 8: Maybe spawn agents (dual trigger)
            self._maybe_spawn_agents(round_num)

            # Step 9: Store outputs, update trust
            #   Skip escalated subtasks — they will be retried next iteration.
            for subtask, outputs in iteration_outputs.items():
                signals = signals_map.get(subtask)
                team = iteration_teams.get(subtask, [])
                primary = team[0] if team else next(iter(outputs), "unknown")

                if subtask in escalated_this_round:
                    # Don't store or mark complete; will retry with escalated protocol
                    if signals:
                        self.failure_tracker[subtask] = (
                            self.failure_tracker.get(subtask, 0) + 1
                        )
                    continue

                self._store_output(subtask, outputs, primary)
                completed_subtasks.append(subtask)

                # Add evidence to primary's beacon
                beacon = self.registry.beacons.get(primary)
                if beacon:
                    beacon.evidence.append(f"completed:{subtask}:round{round_num}")

                # Update calibration, reputation, synergy
                if signals:
                    success = signals.risk < 0.5
                    quality = 1.0 - signals.risk
                    self.bidding.update_calibration(primary, self.registry, success)
                    self.bidding.update_reputation(primary, quality)
                    if len(team) >= 2:
                        self.bidding.update_synergy(team[0], team[1], quality)

                    # Track failures for spawn trigger
                    if signals.risk >= 0.5:
                        self.failure_tracker[subtask] = self.failure_tracker.get(subtask, 0) + 1
                    else:
                        self.failure_tracker[subtask] = 0

            # Cleanup expired spawned agents
            removed = self.factory.cleanup_expired(round_num)
            for name in removed:
                self.agents.pop(name, None)
                self.topology.remove_node(name)

            # Step 10: Check acceptance
            if decision.action == PolicyAction.STOP or self._acceptance_met():
                early_stop = True
                print("  [DiCWO] Acceptance criteria met — early stop")
                break

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
                "spawned_agents": self.factory.to_dict(),
                "topology": self.topology.to_dict(),
                "reputation": dict(self.bidding.reputation),
                "synergy": {
                    k: dict(v) for k, v in self.bidding.synergy.items()
                },
                "subtask_quality": dict(self.policy.subtask_quality),
                "confidence_gateway": self.confidence_gateway.to_dict(),
                "escalation": self.escalation.to_dict(),
                "coverage_gaps": self.coverage_gap_log,
                "failure_tracker": dict(self.failure_tracker),
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

    def _broadcast_beacons(self, round_num: int, compressed: str = "") -> None:
        """All agents broadcast their capabilities (paper: EmitBeacon).

        Agents receive compressed S_t as part of beacon context.
        """
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
                estimated_cost=0.3,
            )
            self.registry.register(beacon)

        # Inject compressed state into agents if available
        if compressed:
            for agent in self.agents.values():
                agent.inject_context(compressed)

    def _compress_state(self) -> str:
        """Truncate artifacts to bound context growth (3000 chars total)."""
        if not self.state.artifacts:
            return ""

        summary = self.state.get_context_summary()
        if len(summary) <= 3000:
            return summary
        return summary[:3000] + "\n... [truncated]"

    def _joint_consensus_select(
        self,
        subtask: str,
        coalition_options: list[dict[str, Any]],
        round_num: int,
    ) -> tuple[list[str], str, str]:
        """Dispatch to consensus engine for joint (team, topology, protocol) selection."""
        context = self.state.get_context_summary() if self.state.artifacts else ""

        return self.consensus.joint_consensus_select(
            subtask=subtask,
            coalitions=coalition_options,
            agents=self.agents,
            context=context,
        )

    def _checkpoint_iteration(
        self,
        iteration_outputs: dict[str, dict[str, str]],
        round_num: int,
    ) -> dict[str, CheckpointSignals]:
        """Run checkpoint over all subtask outputs for this iteration."""
        reviewer = self.agents.get(STUDY_MANAGER.name)
        if reviewer is None:
            reviewer = BaseAgent(identity=STUDY_MANAGER, llm=self.llm)

        signals_map: dict[str, CheckpointSignals] = {}
        for subtask, outputs in iteration_outputs.items():
            signals = self.checkpoint_eval.evaluate(subtask, outputs, reviewer)
            signals_map[subtask] = signals

            self.logger.log(
                agent="DiCWO",
                role="checkpoint",
                content=f"Checkpoint [{subtask}]: {signals.to_dict()}",
                metadata={"round": round_num, "subtask": subtask},
            )

        return signals_map

    def _apply_policy_iteration(
        self,
        signals_map: dict[str, CheckpointSignals],
        round_num: int,
        max_rounds: int,
    ) -> Any:
        """Aggregate signals (worst-case) then call policy.

        Takes the worst signal across all subtasks in this iteration.
        """
        if not signals_map:
            return self.policy.decide(
                signals=CheckpointSignals(
                    disagreement=0.0, uncertainty=0.5,
                    verifiability=0.5, risk=0.3,
                ),
                round_num=round_num,
                max_rounds=max_rounds,
            )

        # Worst-case aggregation across subtasks
        worst = CheckpointSignals(
            disagreement=max(s.disagreement for s in signals_map.values()),
            uncertainty=max(s.uncertainty for s in signals_map.values()),
            verifiability=min(s.verifiability for s in signals_map.values()),
            risk=max(s.risk for s in signals_map.values()),
        )

        # Track per-subtask quality in policy engine
        for subtask, signals in signals_map.items():
            quality = 1.0 - signals.risk
            self.policy.subtask_quality[subtask] = quality

        return self.policy.decide(
            signals=worst,
            round_num=round_num,
            max_rounds=max_rounds,
        )

    def _handle_policy_v2(self, decision: Any) -> None:
        """Simplified policy handler: Continue (noop), Rewire, Stop."""
        if decision.action == PolicyAction.REWIRE:
            target = decision.params.get("target_topology", "full")
            if target == "full":
                self.topology.set_fully_connected()
            elif target == "star":
                self.topology.set_star(STUDY_MANAGER.name)
            self.logger.log(
                agent="DiCWO",
                role="rewire",
                content=f"Topology rewired to {target}",
                metadata={},
            )
        # CONTINUE and STOP are no-ops here (STOP handled in caller)

    def _maybe_spawn_agents(self, round_num: int) -> None:
        """Dual trigger spawn: coverage gaps + persistent failures (>=2 consecutive).

        Coverage gap: subtask had no capable agents during bidding.
        Persistent failure: subtask failed checkpoint >= 2 consecutive times.
        """
        spawn_reasons: list[tuple[list[str], str]] = []

        # Trigger 1: Coverage gaps from bidding
        if self.coverage_gap_log:
            # Deduplicate
            unique_gaps = list(dict.fromkeys(self.coverage_gap_log))
            for gap in unique_gaps:
                spawn_reasons.append(
                    ([gap], f"Coverage gap: no capable agents for '{gap}'")
                )
            self.coverage_gap_log.clear()

        # Trigger 2: Persistent failures (>= 2 consecutive)
        for subtask, count in self.failure_tracker.items():
            if count >= 2:
                spawn_reasons.append(
                    ([subtask], f"Persistent failure: '{subtask}' failed {count} times")
                )

        for capabilities, reason in spawn_reasons:
            agent = self.factory.spawn(capabilities, reason, round_num)
            if agent:
                self.agents[agent.name] = agent
                self.topology.add_node(agent.name)
                self.topology.set_fully_connected()
                self.registry.register(Beacon(
                    agent_name=agent.name,
                    capabilities=capabilities,
                    confidence=0.7,
                    round_num=round_num,
                ))
                self.policy.record_spawn()
                self.logger.log(
                    agent="DiCWO",
                    role="factory",
                    content=f"Spawned agent: {agent.name} for {reason}",
                    metadata={"round": round_num},
                )

    def _should_redecompose(self, round_num: int, last_rewire_round: int) -> bool:
        """Heuristic: re-decompose every 3 rounds or right after a rewire."""
        if round_num > 1 and round_num == last_rewire_round + 1:
            return True
        if round_num > 1 and round_num % 3 == 0:
            return True
        return False

    def _acceptance_met(self) -> bool:
        """Check quality across completed subtasks.

        Delegates to policy engine's acceptance criteria.
        """
        return self.policy._acceptance_criteria_met()

    # ------------------------------------------------------------------
    # Execution and storage (unchanged)
    # ------------------------------------------------------------------

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
            response, record, gw_result = self.confidence_gateway.gate(
                agent, subtask, task_desc, context=context,
            )
            outputs[primary_agent] = response

            self._log_confidence(primary_agent, subtask, gw_result)
            self._handle_intervention(primary_agent, subtask, gw_result)
            self.logger.log(
                agent=primary_agent,
                role="assistant",
                content=response,
                metadata={**record.to_dict(), "protocol": "solo"},
            )

        elif protocol == "audit":
            # Primary executes with confidence gating, then another agent reviews
            agent = self.agents[primary_agent]
            response, record, gw_result = self.confidence_gateway.gate(
                agent, subtask, task_desc, context=context,
            )
            outputs[primary_agent] = response

            self._log_confidence(primary_agent, subtask, gw_result)
            self._handle_intervention(primary_agent, subtask, gw_result)
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
            # Two agents from coalition produce outputs with confidence gating
            debate_agents = []
            if coalition and len(coalition) >= 2:
                debate_agents = [self.agents[n] for n in coalition[:2] if n in self.agents]
            if len(debate_agents) < 2:
                debate_agents = [
                    a for name, a in self.agents.items()
                    if name != STUDY_MANAGER.name
                ][:2]

            for agent in debate_agents:
                response, record, gw_result = self.confidence_gateway.gate(
                    agent, subtask, task_desc, context=context,
                )
                outputs[agent.name] = response

                self._log_confidence(agent.name, subtask, gw_result)
                self._handle_intervention(agent.name, subtask, gw_result)
                self.logger.log(
                    agent=agent.name,
                    role="assistant",
                    content=response,
                    metadata={**record.to_dict(), "protocol": "debate"},
                )

        elif protocol == "parallel":
            # All capable agents execute with confidence gating
            capable = self.registry.get_capable_agents(subtask)
            agent_names = [b.agent_name for b in capable] or [primary_agent]

            for name in agent_names[:3]:  # Cap at 3
                agent = self.agents.get(name)
                if not agent:
                    continue
                response, record, gw_result = self.confidence_gateway.gate(
                    agent, subtask, task_desc, context=context,
                )
                outputs[name] = response

                self._log_confidence(name, subtask, gw_result)
                self._handle_intervention(name, subtask, gw_result)
                self.logger.log(
                    agent=name,
                    role="assistant",
                    content=response,
                    metadata={**record.to_dict(), "protocol": "parallel"},
                )

        elif protocol == "tool_verified":
            # Fallback: execute like solo with confidence gating
            agent = self.agents[primary_agent]
            response, record, gw_result = self.confidence_gateway.gate(
                agent, subtask, task_desc, context=context,
            )
            outputs[primary_agent] = response

            self._log_confidence(primary_agent, subtask, gw_result)
            self._handle_intervention(primary_agent, subtask, gw_result)
            self.logger.log(
                agent=primary_agent,
                role="assistant",
                content=response,
                metadata={**record.to_dict(), "protocol": "tool_verified"},
            )

        return outputs

    def _handle_intervention(
        self,
        agent_name: str,
        subtask: str,
        gw_result: Any,
    ) -> None:
        """Handle confidence gateway interventions.

        When an agent's confidence is critically low (<50%), the gateway
        returns an InterventionRequest instead of blindly retrying.  This
        method escalates the subtask through the protocol ladder and logs
        the missing information so the next iteration can address it.
        """
        if gw_result.action_taken != ConfidenceAction.INTERVENE:
            return

        intervention = gw_result.intervention
        if intervention is None:
            return

        # Escalate the subtask protocol for the next iteration
        if not self.escalation.at_max(subtask):
            old_proto = self.escalation.get_protocol(subtask)
            new_proto = self.escalation.escalate(subtask)
            print(
                f"  [DiCWO] Confidence intervention for '{subtask}': "
                f"escalated {old_proto} -> {new_proto}"
            )
        else:
            print(
                f"  [DiCWO] Confidence intervention for '{subtask}': "
                f"already at max escalation"
            )

        # Track as failure so spawn trigger can fire
        self.failure_tracker[subtask] = (
            self.failure_tracker.get(subtask, 0) + 1
        )

        # Log the structured intervention for traceability
        self.logger.log(
            agent=agent_name,
            role="confidence_intervention",
            content=(
                f"Agent '{agent_name}' requested intervention for '{subtask}'.\n"
                f"Missing info: {intervention.missing_info}\n"
                f"Blockers: {intervention.blockers}\n"
                f"Partial result: {intervention.partial_result[:300]}\n"
                f"Suggested sources: {intervention.suggested_sources}"
            ),
            metadata={
                "subtask": subtask,
                "confidence": gw_result.final_confidence,
                "missing_info": intervention.missing_info,
                "blockers": intervention.blockers,
                "suggested_sources": intervention.suggested_sources,
            },
        )

    def _log_confidence(
        self,
        agent_name: str,
        subtask: str,
        gw_result: Any,
    ) -> None:
        """Log confidence gateway results."""
        last = gw_result.records[-1] if gw_result.records else None
        attempts = len(gw_result.records)
        self.logger.log(
            agent=agent_name,
            role="confidence_gateway",
            content=(
                f"Confidence gate [{subtask}]: "
                f"score={gw_result.final_confidence}%, "
                f"passed={gw_result.passed}, "
                f"attempts={attempts}"
                + (f", reason={last.reason}" if last else "")
            ),
            metadata={
                "subtask": subtask,
                "confidence": gw_result.final_confidence,
                "passed": gw_result.passed,
                "attempts": attempts,
            },
        )

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
