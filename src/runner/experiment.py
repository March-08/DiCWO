"""ExperimentRunner: config → run system → evaluate → save results."""

from __future__ import annotations

import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.config import ExperimentConfig
from src.core.llm_client import LLMClient
from src.core.logging_utils import save_json
from src.systems.base_system import BaseSystem, SystemResult


def _build_system(config: ExperimentConfig, llm: LLMClient) -> BaseSystem:
    """Factory: create the right system from config."""
    if config.system_type == "single_agent":
        from src.systems.single_agent.system import SingleAgentSystem
        return SingleAgentSystem(config, llm)
    elif config.system_type == "centralized":
        from src.systems.centralized.system import CentralizedSystem
        return CentralizedSystem(config, llm)
    elif config.system_type == "dicwo":
        from src.systems.dicwo.system import DiCWOSystem
        return DiCWOSystem(config, llm)
    else:
        raise ValueError(f"Unknown system type: {config.system_type}")


def _resolve_api_key(provider: str, api_keys: dict[str, str]) -> str:
    """Resolve the API key for a given provider."""
    import os
    # Check explicit keys dict first, then env vars
    key = api_keys.get(provider)
    if key:
        return key
    env_map = {
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    env_var = env_map.get(provider, f"{provider.upper()}_API_KEY")
    key = os.environ.get(env_var, "")
    if not key:
        raise ValueError(
            f"No API key for provider '{provider}'. "
            f"Set {env_var} in your .env file."
        )
    return key


class ExperimentRunner:
    """Runs an experiment end-to-end: system → judge → save."""

    def __init__(
        self,
        config: ExperimentConfig,
        api_key: str | None = None,
        api_keys: dict[str, str] | None = None,
        results_dir: str | Path = "results",
        group_dir: str | Path | None = None,
        run_label: str | None = None,
        progress_callback: Any | None = None,
    ) -> None:
        self.config = config
        self.progress_callback = progress_callback
        # api_keys: provider → key mapping. Legacy api_key arg maps to the config's provider.
        self.api_keys: dict[str, str] = dict(api_keys or {})
        if api_key:
            self.api_keys.setdefault(config.provider, api_key)
        self.results_dir = Path(results_dir)
        self.timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        # If group_dir is set, results go under that folder
        base = Path(group_dir) if group_dir else self.results_dir
        label = run_label or f"{self.timestamp}_{config.system_type}_{config.model}"
        self.run_dir = base / label

    def _emit(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        """Emit a progress event if a callback is registered."""
        if self.progress_callback is not None:
            self.progress_callback(event_type, data or {})

    def _make_llm(self) -> LLMClient:
        """Create a fresh LLMClient for the agent provider."""
        api_key = _resolve_api_key(self.config.provider, self.api_keys)
        return LLMClient(
            api_key=api_key,
            model=self.config.model,
            provider=self.config.provider,
            base_url=self.config.base_url or None,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            progress_callback=self.progress_callback,
        )

    def _make_judge_llm(self) -> LLMClient:
        """Create a separate LLMClient for the judge (may use a different provider/model)."""
        provider = self.config.effective_judge_provider
        api_key = _resolve_api_key(provider, self.api_keys)
        return LLMClient(
            api_key=api_key,
            model=self.config.effective_judge_model,
            provider=provider,
            base_url=self.config.effective_judge_base_url or None,
            temperature=0.3,
            max_tokens=self.config.max_tokens,
            progress_callback=self.progress_callback,
        )

    def run(self) -> dict[str, Any]:
        """Execute a single experiment run."""
        llm = self._make_llm()
        self._emit("system_start", {
            "system_type": self.config.system_type,
            "model": self.config.model,
        })
        print(f"[Experiment] Starting {self.config.system_type} with {self.config.model}")

        system = _build_system(self.config, llm)
        result = system.run()

        self._emit("system_complete", {
            "system_type": self.config.system_type,
            "num_calls": llm.metrics.num_calls,
            "total_tokens": llm.metrics.total_tokens,
            "cost": llm.metrics.total_cost,
        })
        print(f"[Experiment] System run complete. Saving results...")

        self._save_results(result, llm)
        self._save_mission_report(result)
        self._save_conversation_trace(result)

        evaluation = {}
        if self.config.run_judge:
            self._emit("judge_start", {"model": self.config.effective_judge_model})
            evaluation.update(self._run_judge(result, llm))
        if evaluation:
            save_json(evaluation, self.run_dir / "evaluation.json")

        self._generate_metrics_report(result, evaluation, llm)

        self._emit("complete", {
            "run_dir": str(self.run_dir),
            "metrics": llm.metrics.to_dict().get("totals", {}),
        })
        print(f"[Experiment] Results saved to {self.run_dir}")
        return {
            "run_dir": str(self.run_dir),
            "metrics": llm.metrics.to_dict(),
            "evaluation": evaluation,
        }

    def run_repeated(self, n: int = 3) -> dict[str, Any]:
        """Run the experiment N times, save each run, and compute averages.

        Results are saved as:
          <run_dir>/
            run_1/  run_2/  run_3/  ...
            averages.json
            mission_report_best.md   (from the run with highest judge score)
        """
        self.run_dir.mkdir(parents=True, exist_ok=True)

        all_results: list[dict[str, Any]] = []
        run_dirs: list[str] = []

        for i in range(1, n + 1):
            print(f"\n--- {self.config.system_type} run {i}/{n} ---")

            sub_runner = ExperimentRunner(
                config=self.config,
                api_keys=self.api_keys,
                group_dir=self.run_dir,
                run_label=f"run_{i}",
                progress_callback=self.progress_callback,
            )
            result = sub_runner.run()
            all_results.append(result)
            run_dirs.append(result["run_dir"])

        # Compute averages
        averages = self._compute_averages(all_results)
        save_json(averages, self.run_dir / "averages.json")

        # Copy best mission report to top level
        self._copy_best_mission_report(all_results)

        # Generate summary
        self._generate_repeat_summary(all_results, averages, n)

        print(f"\n[Experiment] {n} runs complete. Averages saved to {self.run_dir / 'averages.json'}")
        return {
            "run_dir": str(self.run_dir),
            "run_dirs": run_dirs,
            "averages": averages,
            "all_results": all_results,
        }

    # ------------------------------------------------------------------
    # Save helpers
    # ------------------------------------------------------------------

    def _save_results(self, result: SystemResult, llm: LLMClient) -> None:
        """Save all result files to the run directory."""
        self.run_dir.mkdir(parents=True, exist_ok=True)

        metadata = {
            "timestamp": self.timestamp,
            "config": self.config.to_dict(),
            "system_type": self.config.system_type,
            "model": self.config.model,
            "python_version": sys.version,
            "platform": platform.platform(),
            **result.metadata,
        }
        save_json(metadata, self.run_dir / "metadata.json")
        save_json(llm.metrics.to_dict(), self.run_dir / "metrics.json")
        save_json(result.artifacts, self.run_dir / "artifacts.json")
        save_json(result.conversation_log, self.run_dir / "conversation_log.json")

    def _save_mission_report(self, result: SystemResult) -> None:
        """Save the actual mission design output as a readable Markdown file."""
        lines = [
            f"# Mission Design Report",
            f"",
            f"**System**: {self.config.system_type}",
            f"**Model**: {self.config.model}",
            f"**Generated**: {self.timestamp}",
            f"",
            f"---",
            f"",
        ]

        # For single_agent: the whole output is the design
        if "complete_design" in result.artifacts:
            lines.append(result.artifacts["complete_design"])
        else:
            # Multi-agent: assemble from specialist outputs + integration
            artifact_order = [
                ("market_analysis", "Market Analysis"),
                ("market_analyst_output", "Market Analysis"),
                ("frequency_filing", "Frequency Filing"),
                ("frequency_filing_expert_output", "Frequency Filing"),
                ("payload_design", "Payload Design"),
                ("payload_expert_output", "Payload Design"),
                ("mission_analysis", "Mission Analysis"),
                ("mission_analyst_output", "Mission Analysis"),
                ("integration", "Integrated Mission Concept"),
                ("integration_report", "Integrated Mission Concept"),
            ]

            seen_sections: set[str] = set()
            for key, title in artifact_order:
                if key in result.artifacts and title not in seen_sections:
                    seen_sections.add(title)
                    lines.append(f"## {title}")
                    lines.append(f"")
                    lines.append(str(result.artifacts[key]))
                    lines.append(f"")
                    lines.append(f"---")
                    lines.append(f"")

            # Catch any remaining artifacts not in the order list
            for key, value in result.artifacts.items():
                matched = any(key == k for k, _ in artifact_order)
                if not matched:
                    lines.append(f"## {key}")
                    lines.append(f"")
                    lines.append(str(value))
                    lines.append(f"")

        report_path = self.run_dir / "mission_report.md"
        report_path.write_text("\n".join(lines))

    def _save_conversation_trace(self, result: SystemResult) -> None:
        """Render and save a human-readable conversation trace for expert review."""
        from src.core.logging_utils import ConversationLogger

        # Reconstruct logger from the conversation log entries
        logger = ConversationLogger(entries=list(result.conversation_log))
        trace_md = logger.render_conversation_trace(
            system_type=self.config.system_type,
        )
        trace_path = self.run_dir / "conversation_trace.md"
        trace_path.write_text(trace_md)

    def _run_judge(self, result: SystemResult, llm: LLMClient) -> dict[str, Any]:
        try:
            from src.evaluation.llm_judge import LLMJudge
            judge_llm = self._make_judge_llm()
            print(f"[Experiment] Running judge with {self.config.effective_judge_model} "
                  f"({self.config.effective_judge_provider})")
            judge = LLMJudge(judge_llm)
            scores = judge.evaluate(result.artifacts)
            return {"judge_scores": scores}
        except Exception as e:
            print(f"[Experiment] Judge evaluation failed: {e}")
            return {"judge_error": str(e)}

    def _generate_metrics_report(
        self, result: SystemResult, evaluation: dict[str, Any], llm: LLMClient,
    ) -> None:
        """Generate a metrics-only report (separate from mission report)."""
        metrics = llm.metrics
        lines = [
            f"# Metrics Report: {self.config.experiment_name}",
            f"",
            f"**System**: {self.config.system_type}",
            f"**Model**: {self.config.model}",
            f"**Timestamp**: {self.timestamp}",
            f"",
            f"## Metrics",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total LLM calls | {metrics.num_calls} |",
            f"| Total tokens | {metrics.total_tokens:,} |",
            f"| Prompt tokens | {metrics.total_prompt_tokens:,} |",
            f"| Completion tokens | {metrics.total_completion_tokens:,} |",
            f"| Total cost | ${metrics.total_cost:.4f} |",
            f"| Total latency | {metrics.total_latency:.1f}s |",
            f"",
        ]

        per_agent = metrics.per_agent_summary()
        if per_agent:
            lines.append("## Per-Agent Breakdown")
            lines.append("")
            lines.append("| Agent | Calls | Tokens | Cost |")
            lines.append("|-------|-------|--------|------|")
            for name, stats in per_agent.items():
                lines.append(
                    f"| {name} | {stats['num_calls']} | "
                    f"{stats['total_tokens']:,} | ${stats['cost_usd']:.4f} |"
                )
            lines.append("")

        if evaluation:
            lines.append("## Evaluation")
            lines.append("")
            if "judge_scores" in evaluation:
                lines.append("### LLM Judge Scores")
                lines.append("```json")
                lines.append(json.dumps(evaluation["judge_scores"], indent=2))
                lines.append("```")
                lines.append("")

        (self.run_dir / "report.md").write_text("\n".join(lines))

    # ------------------------------------------------------------------
    # Repeat / averaging helpers
    # ------------------------------------------------------------------

    def _compute_averages(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        """Compute average metrics across multiple runs."""
        n = len(results)
        if n == 0:
            return {}

        # Aggregate metric totals
        keys = ["num_calls", "total_tokens", "prompt_tokens",
                "completion_tokens", "cost_usd", "latency_s"]
        sums: dict[str, float] = {k: 0.0 for k in keys}

        judge_scores: list[float] = []

        for r in results:
            totals = r.get("metrics", {}).get("totals", {})
            for k in keys:
                sums[k] += totals.get(k, 0)

            ev = r.get("evaluation", {})
            js = ev.get("judge_scores", {}).get("_aggregate", {}).get("mean_score")
            if js is not None:
                judge_scores.append(js)

        averages = {k: round(v / n, 4) for k, v in sums.items()}

        if judge_scores:
            avg_judge = sum(judge_scores) / len(judge_scores)
            std_judge = (sum((s - avg_judge) ** 2 for s in judge_scores) / len(judge_scores)) ** 0.5
            averages["judge_mean_score"] = round(avg_judge, 4)
            averages["judge_std"] = round(std_judge, 4)
            averages["judge_all"] = judge_scores

        averages["num_runs"] = n
        return averages

    def _copy_best_mission_report(self, results: list[dict[str, Any]]) -> None:
        """Copy the mission report from the best-scoring run to the top level."""
        best_dir = None
        best_score = -1.0

        for r in results:
            score = (
                r.get("evaluation", {})
                .get("judge_scores", {})
                .get("_aggregate", {})
                .get("mean_score", 0)
            )
            if score > best_score:
                best_score = score
                best_dir = r["run_dir"]

        # Fallback: first run
        if best_dir is None and results:
            best_dir = results[0]["run_dir"]

        if best_dir:
            src = Path(best_dir) / "mission_report.md"
            if src.exists():
                dst = self.run_dir / "mission_report_best.md"
                dst.write_text(src.read_text())

    def _generate_repeat_summary(
        self, results: list[dict[str, Any]], averages: dict[str, Any], n: int,
    ) -> None:
        """Generate a summary markdown for repeated runs."""
        lines = [
            f"# Repeated Experiment Summary",
            f"",
            f"**System**: {self.config.system_type}",
            f"**Model**: {self.config.model}",
            f"**Runs**: {n}",
            f"",
            f"## Average Metrics",
            f"",
            f"| Metric | Average |",
            f"|--------|---------|",
            f"| LLM calls | {averages.get('num_calls', 0):.1f} |",
            f"| Tokens | {averages.get('total_tokens', 0):,.0f} |",
            f"| Cost | ${averages.get('cost_usd', 0):.4f} |",
            f"| Latency | {averages.get('latency_s', 0):.1f}s |",
        ]

        if "judge_mean_score" in averages:
            lines.append(
                f"| Judge score | {averages['judge_mean_score']:.2f} "
                f"± {averages.get('judge_std', 0):.2f} |"
            )
        lines.append("")
        lines.append("## Per-Run Results")
        lines.append("")
        lines.append("| Run | Tokens | Cost | Latency | Judge |")
        lines.append("|-----|--------|------|---------|-------|")

        for i, r in enumerate(results, 1):
            totals = r.get("metrics", {}).get("totals", {})
            ev = r.get("evaluation", {})
            js = ev.get("judge_scores", {}).get("_aggregate", {}).get("mean_score")
            lines.append(
                f"| {i} | {totals.get('total_tokens', 0):,} | "
                f"${totals.get('cost_usd', 0):.4f} | "
                f"{totals.get('latency_s', 0):.1f}s | "
                f"{f'{js:.2f}' if js is not None else 'N/A'} |"
            )

        (self.run_dir / "summary.md").write_text("\n".join(lines))
