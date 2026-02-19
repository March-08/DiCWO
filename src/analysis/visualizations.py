"""Matplotlib plots for experiment result visualization."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

from src.runner.comparison import compare_runs, find_runs


def plot_comparison(
    results_dir: str | Path = "results",
    output_dir: str | Path | None = None,
) -> list[str]:
    """Generate comparison plots across all runs.

    Returns list of saved file paths.
    """
    runs = find_runs(results_dir)
    if not runs:
        print("No runs found.")
        return []

    comparison = compare_runs(runs)
    data = comparison["runs"]
    if not data:
        return []

    saved = []
    output_dir = Path(output_dir) if output_dir else Path(results_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Cost comparison bar chart
    fig, ax = plt.subplots(figsize=(8, 5))
    systems = [r["system_type"] for r in data]
    costs = [r["cost_usd"] for r in data]
    ax.bar(systems, costs, color=["#4C78A8", "#F58518", "#54A24B"][:len(systems)])
    ax.set_ylabel("Cost (USD)")
    ax.set_title("LLM Cost per System")
    ax.grid(axis="y", alpha=0.3)
    path = output_dir / "cost_comparison.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    saved.append(str(path))

    # 2. Token usage comparison
    fig, ax = plt.subplots(figsize=(8, 5))
    tokens = [r["total_tokens"] for r in data]
    ax.bar(systems, tokens, color=["#4C78A8", "#F58518", "#54A24B"][:len(systems)])
    ax.set_ylabel("Total Tokens")
    ax.set_title("Token Usage per System")
    ax.grid(axis="y", alpha=0.3)
    path = output_dir / "token_comparison.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    saved.append(str(path))

    # 3. Quality vs Cost scatter
    judge_scores = [r.get("judge_mean_score") for r in data]
    if any(s is not None for s in judge_scores):
        fig, ax = plt.subplots(figsize=(8, 5))
        for i, r in enumerate(data):
            if r.get("judge_mean_score") is not None:
                ax.scatter(
                    r["cost_usd"],
                    r["judge_mean_score"],
                    s=100,
                    label=r["system_type"],
                    zorder=5,
                )
                ax.annotate(
                    r["system_type"],
                    (r["cost_usd"], r["judge_mean_score"]),
                    textcoords="offset points",
                    xytext=(10, 5),
                )
        ax.set_xlabel("Cost (USD)")
        ax.set_ylabel("Judge Score (1-5)")
        ax.set_title("Quality vs Cost")
        ax.grid(alpha=0.3)
        ax.legend()
        path = output_dir / "quality_vs_cost.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        saved.append(str(path))

    # 4. Latency comparison
    fig, ax = plt.subplots(figsize=(8, 5))
    latencies = [r["latency_s"] for r in data]
    ax.bar(systems, latencies, color=["#4C78A8", "#F58518", "#54A24B"][:len(systems)])
    ax.set_ylabel("Latency (seconds)")
    ax.set_title("Total Latency per System")
    ax.grid(axis="y", alpha=0.3)
    path = output_dir / "latency_comparison.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    saved.append(str(path))

    print(f"Saved {len(saved)} plots to {output_dir}")
    return saved
