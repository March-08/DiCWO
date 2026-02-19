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
        "--no-validators",
        action="store_true",
        help="Skip domain validators",
    )
    parser.add_argument(
        "--repeat", "-n",
        type=int,
        default=1,
        help="Run N times and compute averages (default: 1)",
    )
    args = parser.parse_args()

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

    if args.no_judge:
        config.run_judge = False
    if args.no_validators:
        config.run_validators = False

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
        if "verified_claims_ratio" in avgs:
            print(f"Valid:    {avgs['verified_claims_ratio']:.0%}")
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
            if "validator_results" in eval_data:
                ratio = eval_data["validator_results"].get("verified_claims_ratio")
                if ratio is not None:
                    print(f"Valid:   {ratio:.0%}")


if __name__ == "__main__":
    main()
