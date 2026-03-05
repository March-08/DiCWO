"""Run all 3 systems and generate a grouped comparison report.

Usage:
    python3 scripts/run_all.py                                    # 1 run each (YAML defaults)
    python3 scripts/run_all.py --repeat 4                          # 4 runs each, averaged
    python3 scripts/run_all.py --model openai/gpt-5.2-chat         # override agent model (OpenRouter)
    python3 scripts/run_all.py --model gpt-4o --provider openai    # use OpenAI directly
    python3 scripts/run_all.py --model openai/gpt-5.2-chat --repeat 4 --judge-model openai/gpt-5.2-chat
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.core.config import ExperimentConfig
from src.core.logging_utils import save_json
from src.runner.comparison import compare_group, comparison_to_markdown
from src.runner.experiment import ExperimentRunner
from src.analysis.visualizations import plot_comparison


CONFIGS = [
    "configs/single_agent.yaml",
    "configs/centralized_manager.yaml",
    "configs/dicwo.yaml",
]


def _collect_api_keys() -> dict[str, str]:
    """Collect all available API keys from environment."""
    keys: dict[str, str] = {}
    for provider, env_var in [("openai", "OPENAI_API_KEY"),
                               ("openrouter", "OPENROUTER_API_KEY")]:
        val = os.environ.get(env_var, "")
        if val:
            keys[provider] = val
    return keys


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all 3 systems and compare")
    parser.add_argument("--repeat", "-n", type=int, default=1,
                        help="Number of runs per system (default: 1)")
    parser.add_argument("--model", "-m", type=str, default=None,
                        help="Override agent model for all systems (e.g. openai/gpt-5.2-chat)")
    parser.add_argument("--provider", "-p", type=str, default=None,
                        help="Override provider (openai or openrouter). "
                             "Auto-detected from model name if not set.")
    parser.add_argument("--judge-model", type=str, default=None,
                        help="Override judge model (default: same as --model if set)")
    parser.add_argument("--judge-provider", type=str, default=None,
                        help="Override judge provider (default: same as --provider)")
    parser.add_argument("--no-judge", action="store_true",
                        help="Skip LLM judge evaluation")
    parser.add_argument("--results-dir", default="results",
                        help="Base results directory (default: results/)")
    args = parser.parse_args()

    # Auto-detect provider from model name if not explicitly set
    if args.model and not args.provider:
        if "/" in args.model:
            args.provider = "openrouter"
        else:
            args.provider = "openai"

    load_dotenv()
    api_keys = _collect_api_keys()
    if not api_keys:
        print("Error: No API keys found. Set OPENAI_API_KEY and/or "
              "OPENROUTER_API_KEY in your .env file.")
        sys.exit(1)

    # Create a group directory for this experiment batch
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    group_dir = Path(args.results_dir) / f"{timestamp}_comparison"
    group_dir.mkdir(parents=True, exist_ok=True)

    print(f"Experiment group: {group_dir}")
    print(f"Runs per system:  {args.repeat}")
    print(f"API keys loaded:  {', '.join(api_keys.keys())}")
    print()

    system_dirs: list[str] = []

    for config_path in CONFIGS:
        config = ExperimentConfig.from_yaml(config_path)

        # Apply CLI overrides
        if args.model:
            config.model = args.model
        if args.provider:
            config.provider = args.provider
        if args.judge_model:
            config.judge_model = args.judge_model
        elif args.model:
            config.judge_model = args.model
        if args.judge_provider:
            config.judge_provider = args.judge_provider
        elif args.provider:
            config.judge_provider = args.provider
        if args.no_judge:
            config.run_judge = False

        print(f"\n{'='*60}")
        print(f"  System: {config.system_type}")
        print(f"  Model:  {config.model} ({config.provider})")
        if config.run_judge:
            print(f"  Judge:  {config.effective_judge_model} ({config.effective_judge_provider})")
        print(f"{'='*60}")

        runner = ExperimentRunner(
            config=config,
            api_keys=api_keys,
            group_dir=group_dir,
            run_label=config.system_type,
        )

        if args.repeat > 1:
            result = runner.run_repeated(n=args.repeat)
            avgs = result["averages"]
            print(f"\n  Averages ({args.repeat} runs):")
            print(f"    Tokens:  {avgs.get('total_tokens', 0):,.0f}")
            print(f"    Cost:    ${avgs.get('cost_usd', 0):.4f}")
            print(f"    Latency: {avgs.get('latency_s', 0):.1f}s")
            if "judge_mean_score" in avgs:
                print(f"    Judge:   {avgs['judge_mean_score']:.2f} ± {avgs.get('judge_std', 0):.2f}")
        else:
            result = runner.run()
            metrics = result["metrics"]["totals"]
            print(f"\n  Tokens:  {metrics['total_tokens']:,}")
            print(f"  Cost:    ${metrics['cost_usd']:.4f}")
            print(f"  Latency: {metrics['latency_s']:.1f}s")

        system_dirs.append(result["run_dir"])

    # Generate comparison
    print(f"\n{'='*60}")
    print("  COMPARISON")
    print(f"{'='*60}\n")

    comparison = compare_group(group_dir)
    md = comparison_to_markdown(comparison)
    print(md)

    # Save comparison files to the group folder
    (group_dir / "comparison.md").write_text(md)
    save_json(comparison, group_dir / "comparison.json")

    # Generate plots
    try:
        saved = plot_comparison(group_dir, group_dir)
        if saved:
            print(f"\nPlots saved to {group_dir}")
    except Exception as e:
        print(f"\nPlot generation skipped: {e}")

    print(f"\nAll results in: {group_dir}")
    print(f"  comparison.md    — side-by-side table")
    print(f"  comparison.json  — structured data")
    for d in system_dirs:
        name = Path(d).name
        has_best = (Path(d) / "mission_report_best.md").exists()
        has_mission = (Path(d) / "mission_report.md").exists()
        report_label = "mission_report_best.md" if has_best else ("mission_report.md" if has_mission else "")
        has_trace = (Path(d) / "conversation_trace.md").exists()
        trace_label = " + conversation_trace.md" if has_trace else ""
        print(f"  {name}/  {report_label}{trace_label}")


if __name__ == "__main__":
    main()
