"""Cross-cutting quality dimension analysis from existing per-criterion judge scores.

Re-aggregates the 20 per-criterion scores (already in evaluation.json) into
4 cross-cutting quality dimensions that span multiple artifacts.  This adds
depth to the evaluation without any new LLM calls.

Produces:
  - consolidated_dimensions.json  (all data)
  - fig_dimensions_gpt52.pdf/png  (GPT-5.2 primary: grouped bars by dimension)
  - fig_dimensions_heatmap.pdf/png (all models × dimensions heatmap for DiCWO)
  - fig_dimensions_radar.pdf/png  (radar chart: 3 systems on GPT-5.2)
  - fig_dimensions_delta.pdf/png  (DiCWO uplift over centralized per dimension)

Usage:
    python3 scripts/generate_dimension_analysis.py
    python3 scripts/generate_dimension_analysis.py --results-dir results --output-dir figures/dimensions
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

# ── Style (matches generate_paper_charts.py) ─────────────────────────────────
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif", "serif"],
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.labelsize": 11,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": "--",
})

# Colorblind-safe palette (Tol's)
SYSTEM_COLORS = {
    "single_agent": "#EE7733",
    "centralized": "#0077BB",
    "dicwo": "#009988",
}
SYSTEM_LABELS = {
    "single_agent": "Single Agent",
    "centralized": "Centralized",
    "dicwo": "DiCWO",
}

# ── Dimension Definitions ─────────────────────────────────────────────────────
#
# Each criterion maps to exactly one dimension.  The artifact key is matched
# via substring (same logic as rubrics.py) to handle naming differences
# between systems (e.g. "market_analyst_output" vs "market_analysis").
#
# Mapping format: (artifact_substring, criterion_name)

DIMENSIONS: dict[str, dict[str, list[tuple[str, str]]]] = {
    "Technical Accuracy": {
        "weight": 0.35,
        "description": "Physics correctness, numerical accuracy, RF parameter validity",
        "criteria": [
            ("payload", "link_budget_closure"),
            ("payload", "physics_consistency"),
            ("frequency", "gt_eirp_values"),
            ("market", "throughput_derivation"),
            ("mission", "constellation_sizing"),
        ],
    },
    "Engineering Completeness": {
        "weight": 0.20,
        "description": "Coverage of required elements, presentation quality",
        "criteria": [
            ("market", "completeness"),
            ("integration", "completeness"),
            ("payload", "table_format"),
            ("frequency", "bandwidth_justification"),
        ],
    },
    "Cross-System Consistency": {
        "weight": 0.25,
        "description": "Internal consistency, reference alignment, contradiction absence",
        "criteria": [
            ("integration", "cross_consistency"),
            ("frequency", "reference_comparison"),
            ("mission", "reference_comparison"),
            ("payload", "antenna_sizing"),
            ("frequency", "itu_compliance"),
        ],
    },
    "Design Justification": {
        "weight": 0.20,
        "description": "Trade-off reasoning, cost realism, decision documentation",
        "criteria": [
            ("market", "demand_grounding"),
            ("market", "region_justification"),
            ("mission", "trade_offs"),
            ("mission", "cost_estimates"),
            ("integration", "trade_documentation"),
            ("integration", "technical_soundness"),
        ],
    },
}

# For single-agent: if evaluation_per_subtask.json exists (from rejudge),
# all 5 subtask rubrics are available and all dimensions can be computed.
# Otherwise falls back to integration rubric only (Technical Accuracy = NaN).


# ── Data extraction ───────────────────────────────────────────────────────────

def _match_artifact(artifact_key: str, substring: str) -> bool:
    """Check if an artifact key matches a substring pattern.

    Special case: "integration" also matches "complete_design" (single-agent)
    and "integration_report" (centralized).
    """
    key = artifact_key.lower()
    if substring == "integration":
        return ("integration" in key or "complete_design" in key)
    return substring in key


def extract_criteria_scores(eval_data: dict) -> dict[str, dict[str, float]]:
    """Extract {artifact_key: {criterion: score}} from evaluation.json data."""
    js = eval_data.get("judge_scores", {})
    result = {}
    for artifact_key, artifact_data in js.items():
        if artifact_key == "_aggregate":
            continue
        criteria = artifact_data.get("criteria_scores", {})
        result[artifact_key] = {
            crit: info["score"] for crit, info in criteria.items()
            if isinstance(info, dict) and "score" in info
        }
    return result


def compute_dimension_scores(
    criteria_scores: dict[str, dict[str, float]],
) -> dict[str, float | None]:
    """Compute cross-cutting dimension scores from per-criterion data.

    Returns {dimension_name: mean_score} where score is the arithmetic mean
    of all matched criteria for that dimension, or None if no criteria matched.
    """
    dim_scores = {}
    for dim_name, dim_def in DIMENSIONS.items():
        matched_scores = []
        for artifact_sub, crit_name in dim_def["criteria"]:
            # Find the matching artifact
            for artifact_key, crits in criteria_scores.items():
                if _match_artifact(artifact_key, artifact_sub):
                    if crit_name in crits:
                        matched_scores.append(crits[crit_name])
                    break
        if matched_scores:
            dim_scores[dim_name] = sum(matched_scores) / len(matched_scores)
        else:
            dim_scores[dim_name] = None
    return dim_scores


def load_all_runs(results_dir: Path) -> list[dict[str, Any]]:
    """Load dimension scores from all 20260323 experiment runs."""
    records = []
    for exp_dir in sorted(results_dir.iterdir()):
        if not exp_dir.is_dir() or not exp_dir.name.startswith("20260323_172838_"):
            continue
        # Extract model name from directory
        model = exp_dir.name.replace("20260323_172838_", "").replace("_comparison", "")

        for sys_dir in sorted(exp_dir.iterdir()):
            if not sys_dir.is_dir():
                continue
            sys_type = sys_dir.name
            if sys_type not in ("single_agent", "centralized", "dicwo"):
                continue

            for run_dir in sorted(sys_dir.iterdir()):
                if not run_dir.is_dir() or not run_dir.name.startswith("run_"):
                    continue
                eval_path = run_dir / "evaluation.json"
                if not eval_path.exists():
                    continue

                eval_data = json.loads(eval_path.read_text())
                criteria = extract_criteria_scores(eval_data)

                # For single_agent: merge per-subtask re-judge data if available
                if sys_type == "single_agent":
                    per_st_path = run_dir / "evaluation_per_subtask.json"
                    if per_st_path.exists():
                        per_st = json.loads(per_st_path.read_text())
                        for k, v in per_st.items():
                            if k.startswith("_"):
                                continue
                            if isinstance(v, dict) and "criteria_scores" in v:
                                cs = {
                                    crit: info["score"]
                                    for crit, info in v["criteria_scores"].items()
                                    if isinstance(info, dict) and "score" in info
                                }
                                # Use subtask key directly (e.g. "market_analysis")
                                criteria[k] = cs
                dims = compute_dimension_scores(criteria)

                # Also extract the original aggregate
                agg = eval_data.get("judge_scores", {}).get("_aggregate", {})

                records.append({
                    "model": model,
                    "system_type": sys_type,
                    "run": run_dir.name,
                    "dimensions": dims,
                    "original_mean_score": agg.get("mean_score"),
                    "num_artifacts": agg.get("num_artifacts_judged", 0),
                    "raw_criteria": criteria,
                })

    return records


def aggregate_records(records: list[dict]) -> dict[str, Any]:
    """Aggregate per-run records into per-(model, system) statistics."""
    grouped = defaultdict(list)
    for r in records:
        key = (r["model"], r["system_type"])
        grouped[key].append(r)

    result = {}
    for (model, sys_type), runs in grouped.items():
        dim_values = defaultdict(list)
        orig_scores = []
        for run in runs:
            for dim_name, score in run["dimensions"].items():
                if score is not None:
                    dim_values[dim_name].append(score)
            if run["original_mean_score"] is not None:
                orig_scores.append(run["original_mean_score"])

        dim_stats = {}
        for dim_name in DIMENSIONS:
            vals = dim_values.get(dim_name, [])
            if vals:
                dim_stats[dim_name] = {
                    "mean": round(np.mean(vals), 4),
                    "std": round(np.std(vals), 4),
                    "n": len(vals),
                    "values": [round(v, 4) for v in vals],
                }
            else:
                dim_stats[dim_name] = {"mean": None, "std": None, "n": 0, "values": []}

        result[(model, sys_type)] = {
            "model": model,
            "system_type": sys_type,
            "num_runs": len(runs),
            "dimensions": dim_stats,
            "original_mean": round(np.mean(orig_scores), 4) if orig_scores else None,
            "original_std": round(np.std(orig_scores), 4) if orig_scores else None,
        }

    return result


# ── Pretty model names ────────────────────────────────────────────────────────

MODEL_DISPLAY = {
    "openai_gpt-5.2-chat": "GPT-5.2",
    "anthropic_claude-sonnet-4.6": "Claude Sonnet 4.6",
    "x-ai_grok-4.1-fast": "Grok 4.1 Fast",
    "z-ai_glm-4.7:nitro": "GLM-4.7",
    "minimax_minimax-m2.5:nitro": "Minimax M2.5",
    "qwen_qwen3-32b:nitro": "Qwen3-32B",
    "openai_gpt-oss-120b:nitro": "GPT-OSS-120B",
    "meta-llama_llama-3.3-70b-instruct:nitro": "Llama 3.3 70B",
}

def _model_label(m: str) -> str:
    return MODEL_DISPLAY.get(m, m)


# ── Chart helpers ─────────────────────────────────────────────────────────────

def _save(fig, out_dir: Path, name: str):
    for ext in ("pdf", "png"):
        fig.savefig(out_dir / f"{name}.{ext}")
    plt.close(fig)
    print(f"  Saved {name}")


DIM_SHORT = {
    "Technical Accuracy": "Technical\nAccuracy",
    "Engineering Completeness": "Engineering\nCompleteness",
    "Cross-System Consistency": "Cross-System\nConsistency",
    "Design Justification": "Design\nJustification",
}

DIM_ORDER = list(DIMENSIONS.keys())


# ── Fig 1: GPT-5.2 grouped bars by dimension ─────────────────────────────────

def fig_dimensions_primary(agg: dict, out: Path):
    """Grouped bar chart: 3 systems × 4 dimensions for GPT-5.2."""
    model = "openai_gpt-5.2-chat"
    systems = ["single_agent", "centralized", "dicwo"]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = np.arange(len(DIM_ORDER))
    width = 0.22
    offsets = [-width, 0, width]

    for i, sys_type in enumerate(systems):
        key = (model, sys_type)
        data = agg.get(key, {}).get("dimensions", {})
        means = []
        stds = []
        for dim in DIM_ORDER:
            d = data.get(dim, {})
            m = d.get("mean")
            s = d.get("std", 0)
            means.append(m if m is not None else 0)
            stds.append(s if s is not None else 0)

        bars = ax.bar(
            x + offsets[i], means, width,
            yerr=stds, capsize=3,
            label=SYSTEM_LABELS[sys_type],
            color=SYSTEM_COLORS[sys_type],
            edgecolor="white", linewidth=0.5,
            zorder=3,
        )

        # Value labels
        for bar, m, s in zip(bars, means, stds):
            if m > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2, bar.get_height() + s + 0.08,
                    f"{m:.2f}", ha="center", va="bottom", fontsize=7.5,
                )

    ax.set_xticks(x)
    ax.set_xticklabels([DIM_SHORT[d] for d in DIM_ORDER], fontsize=9)
    ax.set_ylabel("Score (1–5)")
    ax.set_ylim(0, 5.5)
    ax.set_title("Quality Dimensions — GPT-5.2 (4 runs, mean ± std)", fontsize=12)
    ax.legend(loc="upper right", framealpha=0.9)
    ax.yaxis.set_major_locator(mticker.MultipleLocator(1))

    fig.tight_layout()
    _save(fig, out, "fig_dimensions_gpt52")


# ── Fig 2: Heatmap — all models × dimensions for DiCWO ───────────────────────

def fig_dimensions_heatmap(agg: dict, out: Path):
    """Heatmap: models (rows) × dimensions (cols) for DiCWO system."""
    models_ordered = [
        "openai_gpt-5.2-chat",
        "anthropic_claude-sonnet-4.6",
        "x-ai_grok-4.1-fast",
        "z-ai_glm-4.7:nitro",
        "minimax_minimax-m2.5:nitro",
        "qwen_qwen3-32b:nitro",
        "openai_gpt-oss-120b:nitro",
        "meta-llama_llama-3.3-70b-instruct:nitro",
    ]

    # Filter to models that exist in the data
    models = [m for m in models_ordered if (m, "dicwo") in agg]

    matrix = np.zeros((len(models), len(DIM_ORDER)))
    for i, model in enumerate(models):
        data = agg.get((model, "dicwo"), {}).get("dimensions", {})
        for j, dim in enumerate(DIM_ORDER):
            d = data.get(dim, {})
            matrix[i, j] = d.get("mean", 0) if d.get("mean") is not None else 0

    fig, ax = plt.subplots(figsize=(7, 5))
    im = ax.imshow(matrix, cmap="YlOrRd", aspect="auto", vmin=1.5, vmax=5.0)

    ax.set_xticks(range(len(DIM_ORDER)))
    ax.set_xticklabels([DIM_SHORT[d] for d in DIM_ORDER], fontsize=9)
    ax.set_yticks(range(len(models)))
    ax.set_yticklabels([_model_label(m) for m in models], fontsize=9)

    # Annotate cells
    for i in range(len(models)):
        for j in range(len(DIM_ORDER)):
            val = matrix[i, j]
            color = "white" if val > 3.8 else "black"
            ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                    fontsize=8.5, color=color, fontweight="bold")

    ax.set_title("DiCWO Quality Dimensions by Model (mean of 4 runs)", fontsize=12)
    cbar = fig.colorbar(im, ax=ax, shrink=0.8, label="Score (1–5)")
    fig.tight_layout()
    _save(fig, out, "fig_dimensions_heatmap")


# ── Fig 3: Radar chart — 3 systems on GPT-5.2 ────────────────────────────────

def fig_dimensions_radar(agg: dict, out: Path):
    """Radar chart: 3 systems × 4 dimensions for GPT-5.2."""
    model = "openai_gpt-5.2-chat"
    systems = ["single_agent", "centralized", "dicwo"]

    angles = np.linspace(0, 2 * np.pi, len(DIM_ORDER), endpoint=False).tolist()
    angles += angles[:1]  # close the polygon

    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))

    for sys_type in systems:
        key = (model, sys_type)
        data = agg.get(key, {}).get("dimensions", {})
        values = []
        for dim in DIM_ORDER:
            d = data.get(dim, {})
            m = d.get("mean")
            values.append(m if m is not None else 0)
        values += values[:1]  # close

        ax.plot(angles, values, "o-", linewidth=2, markersize=5,
                label=SYSTEM_LABELS[sys_type], color=SYSTEM_COLORS[sys_type])
        ax.fill(angles, values, alpha=0.1, color=SYSTEM_COLORS[sys_type])

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([DIM_SHORT[d] for d in DIM_ORDER], fontsize=9)
    ax.set_ylim(0, 5.2)
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.set_yticklabels(["1", "2", "3", "4", "5"], fontsize=8)
    ax.set_title("Quality Profile — GPT-5.2", fontsize=12, pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), framealpha=0.9)

    fig.tight_layout()
    _save(fig, out, "fig_dimensions_radar")


# ── Fig 4: DiCWO uplift over centralized per dimension ────────────────────────

def fig_dimensions_delta(agg: dict, out: Path):
    """Bar chart: DiCWO minus Centralized score per dimension, all models."""
    models_ordered = [
        "openai_gpt-5.2-chat",
        "anthropic_claude-sonnet-4.6",
        "x-ai_grok-4.1-fast",
        "z-ai_glm-4.7:nitro",
        "minimax_minimax-m2.5:nitro",
        "qwen_qwen3-32b:nitro",
        "openai_gpt-oss-120b:nitro",
        "meta-llama_llama-3.3-70b-instruct:nitro",
    ]
    models = [m for m in models_ordered if (m, "dicwo") in agg and (m, "centralized") in agg]

    fig, axes = plt.subplots(1, len(DIM_ORDER), figsize=(14, 4.5), sharey=True)

    for j, dim in enumerate(DIM_ORDER):
        ax = axes[j]
        deltas = []
        labels = []
        for model in models:
            d_dicwo = agg.get((model, "dicwo"), {}).get("dimensions", {}).get(dim, {})
            d_cent = agg.get((model, "centralized"), {}).get("dimensions", {}).get(dim, {})
            m_d = d_dicwo.get("mean")
            m_c = d_cent.get("mean")
            if m_d is not None and m_c is not None:
                deltas.append(m_d - m_c)
                labels.append(_model_label(model))

        colors = ["#009988" if d >= 0 else "#CC3311" for d in deltas]
        y = np.arange(len(labels))
        ax.barh(y, deltas, color=colors, edgecolor="white", linewidth=0.5, height=0.6)
        ax.set_yticks(y)
        if j == 0:
            ax.set_yticklabels(labels, fontsize=8)
        else:
            ax.set_yticklabels([])
        ax.axvline(0, color="black", linewidth=0.8, zorder=5)
        ax.set_title(DIM_SHORT[dim], fontsize=10)
        ax.set_xlim(-1.5, 1.5)

        # Value labels
        for yi, d in zip(y, deltas):
            ha = "left" if d >= 0 else "right"
            offset = 0.05 if d >= 0 else -0.05
            ax.text(d + offset, yi, f"{d:+.2f}", va="center", ha=ha, fontsize=7)

    axes[0].set_ylabel("Model")
    fig.suptitle("DiCWO Uplift over Centralized by Quality Dimension", fontsize=12, y=1.02)
    fig.tight_layout()
    _save(fig, out, "fig_dimensions_delta")


# ── Fig 5: All 20 criteria detail (appendix) ─────────────────────────────────

def fig_criteria_detail(agg: dict, out: Path):
    """Horizontal bar chart: all 20 individual criteria for GPT-5.2, by system."""
    model = "openai_gpt-5.2-chat"
    systems = ["single_agent", "centralized", "dicwo"]

    # Build criteria list grouped by dimension
    criteria_labels = []
    criteria_keys = []
    dim_boundaries = []
    for dim_name in DIM_ORDER:
        dim_boundaries.append(len(criteria_labels))
        for artifact_sub, crit_name in DIMENSIONS[dim_name]["criteria"]:
            label = f"{crit_name.replace('_', ' ').title()}"
            criteria_labels.append(label)
            criteria_keys.append((artifact_sub, crit_name))
    dim_boundaries.append(len(criteria_labels))

    fig, ax = plt.subplots(figsize=(9, 8))
    y = np.arange(len(criteria_labels))
    height = 0.25

    # Load raw records for GPT-5.2
    records_path = Path("results")
    exp_dir = records_path / "20260323_172838_openai_gpt-5.2-chat_comparison"

    offsets = [-height, 0, height]
    for si, sys_type in enumerate(systems):
        means = []
        stds = []
        for artifact_sub, crit_name in criteria_keys:
            vals = []
            sys_dir = exp_dir / sys_type
            for run_dir in sorted(sys_dir.iterdir()):
                if not run_dir.is_dir() or not run_dir.name.startswith("run_"):
                    continue
                # Load evaluation data; for single_agent merge per-subtask rejudge
                eval_path = run_dir / "evaluation.json"
                if not eval_path.exists():
                    continue
                eval_data = json.loads(eval_path.read_text())
                criteria = extract_criteria_scores(eval_data)
                if sys_type == "single_agent":
                    per_st_path = run_dir / "evaluation_per_subtask.json"
                    if per_st_path.exists():
                        per_st = json.loads(per_st_path.read_text())
                        for k, v in per_st.items():
                            if k.startswith("_"):
                                continue
                            if isinstance(v, dict) and "criteria_scores" in v:
                                cs = {
                                    c: info["score"]
                                    for c, info in v["criteria_scores"].items()
                                    if isinstance(info, dict) and "score" in info
                                }
                                criteria[k] = cs
                for ak, crits in criteria.items():
                    if _match_artifact(ak, artifact_sub) and crit_name in crits:
                        vals.append(crits[crit_name])
                        break
            means.append(np.mean(vals) if vals else 0)
            stds.append(np.std(vals) if vals else 0)

        ax.barh(
            y + offsets[si], means, height,
            xerr=stds, capsize=2,
            label=SYSTEM_LABELS[sys_type],
            color=SYSTEM_COLORS[sys_type],
            edgecolor="white", linewidth=0.5,
        )

    # Dimension group labels
    for i, dim_name in enumerate(DIM_ORDER):
        start = dim_boundaries[i]
        end = dim_boundaries[i + 1]
        mid = (start + end - 1) / 2
        ax.axhspan(start - 0.5, end - 0.5, alpha=0.06,
                    color=["#DDDDDD", "#EEEEEE"][i % 2])
        ax.text(-0.15, mid, dim_name, transform=ax.get_yaxis_transform(),
                ha="right", va="center", fontsize=8, fontstyle="italic",
                color="#555555")

    ax.set_yticks(y)
    ax.set_yticklabels(criteria_labels, fontsize=8)
    ax.set_xlabel("Score (1–5)")
    ax.set_xlim(0, 5.5)
    ax.set_ylim(-0.5, len(criteria_labels) - 0.5)
    ax.invert_yaxis()
    ax.legend(loc="lower right", framealpha=0.9)
    ax.set_title("Per-Criterion Scores — GPT-5.2 (All Architectures)", fontsize=12)

    fig.tight_layout()
    _save(fig, out, "fig_criteria_detail")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Cross-cutting dimension analysis")
    parser.add_argument("--results-dir", default="results", help="Results directory")
    parser.add_argument("--output-dir", default="figures/dimensions", help="Output directory")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Loading evaluation data from all runs...")
    records = load_all_runs(results_dir)
    print(f"  Loaded {len(records)} run records")

    print("Aggregating dimension scores...")
    agg = aggregate_records(records)

    # Print summary table
    print("\n  GPT-5.2 Dimension Summary:")
    print(f"  {'Dimension':<30} {'Single':>10} {'Central':>10} {'DiCWO':>10}")
    print(f"  {'-'*30} {'-'*10} {'-'*10} {'-'*10}")
    for dim in DIM_ORDER:
        row = f"  {dim:<30}"
        for sys in ["single_agent", "centralized", "dicwo"]:
            key = ("openai_gpt-5.2-chat", sys)
            d = agg.get(key, {}).get("dimensions", {}).get(dim, {})
            m = d.get("mean")
            s = d.get("std")
            if m is not None:
                row += f" {m:.2f}±{s:.2f}"
            else:
                row += f"      N/A "
        print(row)

    # Save consolidated JSON
    serializable = {}
    for (model, sys_type), data in agg.items():
        serializable[f"{model}__{sys_type}"] = data
    out_json = out_dir / "consolidated_dimensions.json"
    with open(out_json, "w") as f:
        json.dump(serializable, f, indent=2, default=str)
    print(f"\n  Saved {out_json}")

    # Also save a paper-ready table as Markdown
    _save_markdown_table(agg, out_dir)

    # Generate charts
    print("\nGenerating charts...")
    fig_dimensions_primary(agg, out_dir)
    fig_dimensions_heatmap(agg, out_dir)
    fig_dimensions_radar(agg, out_dir)
    fig_dimensions_delta(agg, out_dir)
    fig_criteria_detail(agg, out_dir)

    print(f"\nAll outputs saved to {out_dir}/")


def _save_markdown_table(agg: dict, out_dir: Path):
    """Generate a paper-ready Markdown table."""
    lines = [
        "# Cross-Cutting Quality Dimensions",
        "",
        "## GPT-5.2 Primary Results (4 runs, mean ± std)",
        "",
        "| Dimension | Weight | Single Agent | Centralized | DiCWO |",
        "|-----------|--------|-------------|-------------|-------|",
    ]
    for dim in DIM_ORDER:
        w = DIMENSIONS[dim]["weight"]
        row = f"| {dim} | {w:.0%} |"
        for sys in ["single_agent", "centralized", "dicwo"]:
            key = ("openai_gpt-5.2-chat", sys)
            d = agg.get(key, {}).get("dimensions", {}).get(dim, {})
            m = d.get("mean")
            s = d.get("std")
            if m is not None:
                row += f" {m:.2f} ± {s:.2f} |"
            else:
                row += " N/A |"
        lines.append(row)

    # Weighted composite
    lines.append("")
    lines.append("## Weighted Composite Score")
    lines.append("")
    lines.append("| System | Composite | Original Aggregate |")
    lines.append("|--------|-----------|-------------------|")
    for sys in ["single_agent", "centralized", "dicwo"]:
        key = ("openai_gpt-5.2-chat", sys)
        data = agg.get(key, {})
        dims = data.get("dimensions", {})
        weighted = 0
        total_w = 0
        for dim_name, dim_def in DIMENSIONS.items():
            d = dims.get(dim_name, {})
            m = d.get("mean")
            if m is not None:
                weighted += dim_def["weight"] * m
                total_w += dim_def["weight"]
        composite = weighted / total_w if total_w > 0 else None
        orig = data.get("original_mean")
        c_str = f"{composite:.2f}" if composite is not None else "N/A"
        o_str = f"{orig:.2f}" if orig is not None else "N/A"
        lines.append(f"| {SYSTEM_LABELS[sys]} | {c_str} | {o_str} |")

    # Multi-model DiCWO table
    lines.append("")
    lines.append("## DiCWO Dimensions Across Models")
    lines.append("")
    header = "| Model |"
    sep = "|-------|"
    for dim in DIM_ORDER:
        short = dim.split()[0]
        header += f" {short} |"
        sep += "------|"
    header += " Overall |"
    sep += "---------|"
    lines.append(header)
    lines.append(sep)

    models_ordered = [
        "openai_gpt-5.2-chat",
        "anthropic_claude-sonnet-4.6",
        "x-ai_grok-4.1-fast",
        "z-ai_glm-4.7:nitro",
        "minimax_minimax-m2.5:nitro",
        "qwen_qwen3-32b:nitro",
        "openai_gpt-oss-120b:nitro",
        "meta-llama_llama-3.3-70b-instruct:nitro",
    ]
    for model in models_ordered:
        key = (model, "dicwo")
        data = agg.get(key, {})
        if not data:
            continue
        row = f"| {_model_label(model)} |"
        for dim in DIM_ORDER:
            d = data.get("dimensions", {}).get(dim, {})
            m = d.get("mean")
            row += f" {m:.2f} |" if m is not None else " N/A |"
        orig = data.get("original_mean")
        row += f" {orig:.2f} |" if orig is not None else " N/A |"
        lines.append(row)

    md_path = out_dir / "dimension_tables.md"
    md_path.write_text("\n".join(lines))
    print(f"  Saved {md_path}")


if __name__ == "__main__":
    main()
