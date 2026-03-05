"""CLI entry point for running experiments."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.core.config import ExperimentConfig
from src.runner.experiment import ExperimentRunner


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a DiCWO experiment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config", "-c",
        required=True,
        help="Path to YAML config file",
    )
    parser.add_argument(
        "--results-dir", "-o",
        default="results",
        help="Directory for results (default: results/)",
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help="Skip LLM judge evaluation",
    )
    parser.add_argument(
        "--repeat", "-n",
        type=int,
        default=1,
        help="Run N times and compute averages (default: 1)",
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default=None,
        help="Override agent model (e.g. openai/gpt-5.2-chat)",
    )
    parser.add_argument(
        "--provider", "-p",
        type=str,
        default=None,
        help="Override provider (openai or openrouter). Auto-detected from model name if not set.",
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        default=None,
        help="Override judge model (default: same as --model if set)",
    )
    parser.add_argument(
        "--judge-provider",
        type=str,
        default=None,
        help="Override judge provider (default: same as --provider)",
    )
    args = parser.parse_args()

    # Auto-detect provider from model name
    if args.model and not args.provider:
        if "/" in args.model:
            args.provider = "openrouter"
        else:
            args.provider = "openai"

    # Load environment
    load_dotenv()
    api_keys: dict[str, str] = {}
    for provider, env_var in [("openai", "OPENAI_API_KEY"),
                               ("openrouter", "OPENROUTER_API_KEY")]:
        val = os.environ.get(env_var, "")
        if val:
            api_keys[provider] = val
    if not api_keys:
        print("Error: No API keys found. Set OPENAI_API_KEY and/or "
              "OPENROUTER_API_KEY in your .env file.")
        sys.exit(1)

    # Load config
    config = ExperimentConfig.from_yaml(args.config)

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

    print(f"Provider: {config.provider}, Model: {config.model}")
    if config.run_judge:
        print(f"Judge:    {config.effective_judge_model} ({config.effective_judge_provider})")

    # Run experiment
    runner = ExperimentRunner(
        config=config,
        api_keys=api_keys,
        results_dir=args.results_dir,
    )

    if args.repeat > 1:
        results = runner.run_repeated(n=args.repeat)
        avgs = results["averages"]
        print("\n" + "=" * 60)
        print(f"EXPERIMENT COMPLETE ({args.repeat} runs)")
        print("=" * 60)
        print(f"Results:  {results['run_dir']}")
        print(f"Calls:    {avgs.get('num_calls', 0):.1f} (avg)")
        print(f"Tokens:   {avgs.get('total_tokens', 0):,.0f} (avg)")
        print(f"Cost:     ${avgs.get('cost_usd', 0):.4f} (avg)")
        print(f"Latency:  {avgs.get('latency_s', 0):.1f}s (avg)")
        if "judge_mean_score" in avgs:
            print(f"Judge:    {avgs['judge_mean_score']:.2f} ± {avgs.get('judge_std', 0):.2f}")
    else:
        results = runner.run()
        print("\n" + "=" * 60)
        print("EXPERIMENT COMPLETE")
        print("=" * 60)
        print(f"Results: {results['run_dir']}")
        metrics = results["metrics"]["totals"]
        print(f"Calls:   {metrics['num_calls']}")
        print(f"Tokens:  {metrics['total_tokens']:,}")
        print(f"Cost:    ${metrics['cost_usd']:.4f}")
        print(f"Latency: {metrics['latency_s']:.1f}s")

        if "evaluation" in results and results["evaluation"]:
            eval_data = results["evaluation"]
            if "judge_scores" in eval_data:
                agg = eval_data["judge_scores"].get("_aggregate", {})
                if agg:
                    print(f"Judge:   {agg.get('mean_score', 'N/A')}/5")


if __name__ == "__main__":
    main()
