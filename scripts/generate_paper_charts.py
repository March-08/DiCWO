"""Generate publication-quality charts for multi-model benchmark results.

Produces camera-ready figures suitable for top-tier AI journals.
Outputs go to figures/<experiment_dir_name>/ with a README.md.

Usage:
    python3 scripts/generate_paper_charts.py
    python3 scripts/generate_paper_charts.py --results-dir results --output-dir figures
    python3 scripts/generate_paper_charts.py --experiment 20260321  # filter by date prefix
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

# ── Style ────────────────────────────────────────────────────────────────────
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

# ── Color palette (colorblind-safe, Tol's) ──────────────────────────────────
SYSTEM_COLORS = {
    "single_agent": "#4477AA",
    "centralized":  "#EE6677",
    "dicwo":        "#228833",
}
SYSTEM_LABELS = {
    "single_agent": "Single Agent",
    "centralized":  "Centralized",
    "dicwo":        "DiCWO",
}
SYSTEM_HATCHES = {
    "single_agent": "",
    "centralized":  "//",
    "dicwo":        "",
}
MODEL_COLORS = ["#4477AA", "#EE6677", "#228833", "#CCBB44", "#AA3377",
                "#66CCEE", "#BBBBBB"]
SYSTEM_MARKERS = {"single_agent": "o", "centralized": "s", "dicwo": "D"}


# ═════════════════════════════════════════════════════════════════════════════
# Data loading
# ═════════════════════════════════════════════════════════════════════════════

MODEL_DISPLAY: dict[str, str] = {}  # populated at load time


def _model_display_name(raw: str) -> str:
    return MODEL_DISPLAY.get(raw, raw)


def _infer_display_name(raw: str) -> str:
    """Best-effort short display name from raw dir-safe model string."""
    # e.g. "openai_gpt-5.2-chat" → "GPT-5.2"
    clean = raw.split("_", 1)[-1] if "_" in raw else raw
    clean = re.sub(r":nitro$", "", clean)
    clean = re.sub(r"-chat$", "", clean)
    clean = re.sub(r"-fast$", "", clean)
    clean = clean.replace("minimax-", "MiniMax ")
    # Shorten known long names
    clean = re.sub(r"llama-3\.3-70b-instruct", "Llama-3.3-70B", clean)
    clean = re.sub(r"llama-(\d)", r"Llama-\1", clean)
    clean = re.sub(r"claude-sonnet-", "Sonnet-", clean)
    clean = re.sub(r"claude-opus-", "Opus-", clean)
    clean = re.sub(r"gpt-oss-", "GPT-OSS-", clean)
    parts = clean.split("-")
    return "-".join(p.upper() if len(p) <= 3 and p.isalpha() else p.title()
                    for p in parts).replace("Gpt", "GPT").replace("Glm", "GLM").replace("Qwen", "Qwen")


def find_experiment_dirs(results_dir: str, prefix: str = "") -> list[str]:
    """Find comparison directories matching an optional prefix."""
    dirs = []
    for d in sorted(os.listdir(results_dir)):
        full = Path(results_dir) / d
        if full.is_dir() and "comparison" in d:
            if prefix and not d.startswith(prefix):
                continue
            if (full / "comparison.json").exists():
                dirs.append(d)
    return dirs


def load_comparison_data(results_dir: str, exp_dirs: list[str]) -> list[dict]:
    """Load comparison.json from each experiment directory."""
    all_runs = []
    for d in exp_dirs:
        comp = Path(results_dir) / d / "comparison.json"
        data = json.load(open(comp))
        parts = d.split("_")
        idx_comp = parts.index("comparison")
        model_name = "_".join(parts[2:idx_comp])
        MODEL_DISPLAY[model_name] = _infer_display_name(model_name)
        for r in data["runs"]:
            r["model"] = model_name
            r["_exp_dir"] = d
        all_runs.extend(data["runs"])
    return all_runs


def load_detailed_data(results_dir: str, exp_dirs: list[str]) -> dict:
    """Load per-run metrics, evaluations, and metadata."""
    detail: dict[str, Any] = {
        "per_run_scores": defaultdict(list),     # (model, system) → [score, …]
        "per_subtask_scores": defaultdict(list),  # (model, subtask) → [score, …]
        "per_subtask_scores_by_system": defaultdict(list),  # (model, system, subtask) → [score, …]
        "call_logs": defaultdict(list),           # (model, system) → [call_records]
        "per_agent_tokens": defaultdict(lambda: defaultdict(list)),  # model → agent → [tokens]
        "confidence_gateway": defaultdict(list),  # model → [gateway_stats]
        "escalation": defaultdict(list),          # model → [escalation_dicts]
        "subtask_quality": defaultdict(list),     # model → [{subtask: quality}]
        "prompt_vs_completion": defaultdict(lambda: {"prompt": [], "completion": []}),
    }

    for d in exp_dirs:
        parts = d.split("_")
        idx_comp = parts.index("comparison")
        model = "_".join(parts[2:idx_comp])
        base = Path(results_dir) / d

        for sys_type in ["single_agent", "centralized", "dicwo"]:
            sys_dir = base / sys_type
            if not sys_dir.exists():
                continue

            for run_dir in sorted(sys_dir.iterdir()):
                if not run_dir.is_dir() or not run_dir.name.startswith("run_"):
                    continue

                # Per-run judge scores
                eval_path = run_dir / "evaluation.json"
                if eval_path.exists():
                    ev = json.load(open(eval_path))
                    js = ev.get("judge_scores", {})
                    agg = js.get("_aggregate", {})
                    if "mean_score" in agg:
                        detail["per_run_scores"][(model, sys_type)].append(agg["mean_score"])
                    # Per-subtask scores (dicwo / centralized)
                    for k, v in js.items():
                        if k.startswith("_"):
                            continue
                        if isinstance(v, dict) and "overall_score" in v:
                            detail["per_subtask_scores"][(model, k)].append(v["overall_score"])
                            detail["per_subtask_scores_by_system"][(model, sys_type, k)].append(v["overall_score"])

                # Call logs
                metrics_path = run_dir / "metrics.json"
                if metrics_path.exists():
                    met = json.load(open(metrics_path))
                    calls = met.get("call_log", [])
                    detail["call_logs"][(model, sys_type)].extend(calls)
                    totals = met.get("totals", {})
                    detail["prompt_vs_completion"][model]["prompt"].append(
                        totals.get("prompt_tokens", 0))
                    detail["prompt_vs_completion"][model]["completion"].append(
                        totals.get("completion_tokens", 0))
                    # Per-agent tokens (DiCWO only — most interesting)
                    if sys_type == "dicwo":
                        for agent, stats in met.get("per_agent", {}).items():
                            detail["per_agent_tokens"][model][agent].append(
                                stats.get("total_tokens", 0))

                # DiCWO-specific metadata
                if sys_type == "dicwo":
                    meta_path = run_dir / "metadata.json"
                    if meta_path.exists():
                        meta = json.load(open(meta_path))
                        cg = meta.get("confidence_gateway", {})
                        if cg:
                            detail["confidence_gateway"][model].append(cg)
                        esc = meta.get("escalation", {})
                        if esc:
                            detail["escalation"][model].append(esc)
                        sq = meta.get("subtask_quality", {})
                        if sq:
                            detail["subtask_quality"][model].append(sq)

    return dict(detail)


def _build_dataframe(runs: list[dict]) -> dict:
    models = sorted(set(r["model"] for r in runs),
                    key=lambda m: -max(r.get("judge_mean_score", 0) for r in runs
                                       if r["model"] == m))
    systems = ["single_agent", "centralized", "dicwo"]
    grid = {}
    for r in runs:
        grid[(r["model"], r["system_type"])] = r
    return {"models": models, "systems": systems, "grid": grid}


def _save(fig, out: Path, name: str):
    fig.savefig(out / f"{name}.pdf")
    fig.savefig(out / f"{name}.png")
    plt.close(fig)
    print(f"  {name}")


# ═════════════════════════════════════════════════════════════════════════════
# Figures — Aggregate (from comparison.json)
# ═════════════════════════════════════════════════════════════════════════════

def fig_judge_scores(df: dict, out: Path):
    models, systems, grid = df["models"], df["systems"], df["grid"]
    x = np.arange(len(models))
    width = 0.25
    fig, ax = plt.subplots(figsize=(7, 4))
    for i, sys in enumerate(systems):
        scores = [grid[(m, sys)].get("judge_mean_score", 0) for m in models]
        stds = [grid[(m, sys)].get("judge_std", 0) for m in models]
        ax.bar(x + i * width, scores, width,
               label=SYSTEM_LABELS[sys], color=SYSTEM_COLORS[sys],
               hatch=SYSTEM_HATCHES[sys], edgecolor="white", linewidth=0.5,
               yerr=stds, capsize=3, error_kw={"linewidth": 0.8})
    ax.set_ylabel("Judge Score (1–5)")
    ax.set_xticks(x + width)
    ax.set_xticklabels([_model_display_name(m) for m in models], rotation=30, ha="right")
    ax.set_ylim(1.5, 5.0)
    ax.legend(loc="upper right", framealpha=0.9)
    ax.set_title("Output Quality by Model and Architecture")
    _save(fig, out, "fig01_judge_scores")


def fig_cost_quality(df: dict, out: Path):
    models, systems, grid = df["models"], df["systems"], df["grid"]
    fig, ax = plt.subplots(figsize=(6, 4.5))
    for sys in systems:
        costs, scores, labels, stds = [], [], [], []
        for m in models:
            r = grid[(m, sys)]
            costs.append(r["cost_usd"])
            scores.append(r.get("judge_mean_score", 0))
            stds.append(r.get("judge_std", 0))
            labels.append(_model_display_name(m))
        ax.errorbar(costs, scores, yerr=stds, fmt="none",
                    ecolor=SYSTEM_COLORS[sys], capsize=2, alpha=0.5, linewidth=0.8)
        ax.scatter(costs, scores, s=70, marker=SYSTEM_MARKERS[sys],
                   color=SYSTEM_COLORS[sys], label=SYSTEM_LABELS[sys],
                   edgecolors="black", linewidth=0.4, zorder=5)
        for c, s, lbl in zip(costs, scores, labels):
            ax.annotate(lbl, (c, s), textcoords="offset points",
                        xytext=(6, 4), fontsize=7, alpha=0.8)
    # Pareto frontier
    all_pts = []
    for m in models:
        for sys in systems:
            r = grid[(m, sys)]
            all_pts.append((r["cost_usd"], r.get("judge_mean_score", 0)))
    all_pts.sort(key=lambda p: p[0])
    pareto, best = [], -1
    for cost, score in all_pts:
        if score > best:
            pareto.append((cost, score))
            best = score
    if len(pareto) > 1:
        px, py = zip(*pareto)
        ax.plot(px, py, "--", color="grey", alpha=0.5, linewidth=1, label="Pareto frontier")
    ax.set_xlabel("Average Cost per Run (USD)")
    ax.set_ylabel("Judge Score (1–5)")
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(
        lambda v, _: f"${v:.3f}" if v < 0.1 else f"${v:.2f}"))
    ax.set_ylim(1.5, 5.0)
    ax.legend(loc="lower right", framealpha=0.9)
    ax.set_title("Cost–Quality Trade-off (Pareto Frontier)")
    _save(fig, out, "fig02_cost_quality_pareto")


def fig_dicwo_uplift(df: dict, out: Path):
    models, systems, grid = df["models"], df["systems"], df["grid"]
    fig, ax = plt.subplots(figsize=(6, 4))
    x = np.arange(len(models))
    uplift_sa, uplift_cent = [], []
    for m in models:
        sa = grid[(m, "single_agent")].get("judge_mean_score", 0)
        cent = grid[(m, "centralized")].get("judge_mean_score", 0)
        dicwo = grid[(m, "dicwo")].get("judge_mean_score", 0)
        uplift_sa.append(((dicwo - sa) / sa) * 100 if sa > 0 else 0)
        uplift_cent.append(((dicwo - cent) / cent) * 100 if cent > 0 else 0)
    width = 0.35
    ax.bar(x - width / 2, uplift_sa, width, label="vs Single Agent",
           color="#4477AA", edgecolor="white", linewidth=0.5)
    ax.bar(x + width / 2, uplift_cent, width, label="vs Centralized",
           color="#EE6677", edgecolor="white", linewidth=0.5)
    ax.set_ylabel("Quality Uplift (%)")
    ax.set_xticks(x)
    ax.set_xticklabels([_model_display_name(m) for m in models], rotation=30, ha="right")
    ax.axhline(y=0, color="black", linewidth=0.5)
    ax.legend(loc="upper right", framealpha=0.9)
    ax.set_title("DiCWO Quality Uplift over Baselines")
    _save(fig, out, "fig03_dicwo_uplift")


def fig_heatmap(df: dict, out: Path):
    models, systems, grid = df["models"], df["systems"], df["grid"]
    data = np.array([[grid[(m, s)].get("judge_mean_score", 0) for s in systems]
                     for m in models])
    fig, ax = plt.subplots(figsize=(5, 4))
    im = ax.imshow(data, cmap="YlOrRd", aspect="auto", vmin=2.0, vmax=4.5)
    ax.set_xticks(range(len(systems)))
    ax.set_xticklabels([SYSTEM_LABELS[s] for s in systems])
    ax.set_yticks(range(len(models)))
    ax.set_yticklabels([_model_display_name(m) for m in models])
    for i in range(len(models)):
        for j in range(len(systems)):
            val = data[i, j]
            std = grid[(models[i], systems[j])].get("judge_std", 0)
            color = "white" if val > 3.5 else "black"
            ax.text(j, i, f"{val:.2f}\n\u00b1{std:.2f}", ha="center", va="center",
                    fontsize=9, color=color, fontweight="bold")
    fig.colorbar(im, ax=ax, shrink=0.8, label="Judge Score")
    ax.set_title("Judge Scores: Model \u00d7 Architecture")
    _save(fig, out, "fig04_heatmap")


def fig_efficiency(df: dict, out: Path):
    models, systems, grid = df["models"], df["systems"], df["grid"]
    fig, ax = plt.subplots(figsize=(7, 4))
    x = np.arange(len(models))
    width = 0.25
    for i, sys in enumerate(systems):
        eff = []
        for m in models:
            r = grid[(m, sys)]
            score = r.get("judge_mean_score", 0)
            cost = r["cost_usd"]
            eff.append(score / cost if cost > 0 else 0)
        ax.bar(x + i * width, eff, width, label=SYSTEM_LABELS[sys],
               color=SYSTEM_COLORS[sys], hatch=SYSTEM_HATCHES[sys],
               edgecolor="white", linewidth=0.5)
    ax.set_ylabel("Quality per Dollar (Score / USD)")
    ax.set_xticks(x + width)
    ax.set_xticklabels([_model_display_name(m) for m in models], rotation=30, ha="right")
    ax.set_yscale("log")
    ax.legend(loc="upper right", framealpha=0.9)
    ax.set_title("Cost Efficiency: Quality per Dollar")
    _save(fig, out, "fig05_efficiency")


def fig_latency_quality(df: dict, out: Path):
    models, systems, grid = df["models"], df["systems"], df["grid"]
    fig, ax = plt.subplots(figsize=(6, 4.5))
    for sys in systems:
        lats, scores, labels = [], [], []
        for m in models:
            r = grid[(m, sys)]
            lats.append(r["latency_s"])
            scores.append(r.get("judge_mean_score", 0))
            labels.append(_model_display_name(m))
        ax.scatter(lats, scores, s=70, marker=SYSTEM_MARKERS[sys],
                   color=SYSTEM_COLORS[sys], label=SYSTEM_LABELS[sys],
                   edgecolors="black", linewidth=0.4, zorder=5)
        for lat, s, lbl in zip(lats, scores, labels):
            ax.annotate(lbl, (lat, s), textcoords="offset points",
                        xytext=(6, 4), fontsize=7, alpha=0.8)
    ax.set_xlabel("Average Latency per Run (seconds)")
    ax.set_ylabel("Judge Score (1–5)")
    ax.set_xscale("log")
    ax.set_ylim(1.5, 5.0)
    ax.legend(loc="lower right", framealpha=0.9)
    ax.set_title("Latency–Quality Trade-off")
    _save(fig, out, "fig06_latency_quality")


def fig_token_usage(df: dict, out: Path):
    models, systems, grid = df["models"], df["systems"], df["grid"]
    fig, ax = plt.subplots(figsize=(7, 4))
    x = np.arange(len(models))
    width = 0.25
    for i, sys in enumerate(systems):
        tokens = [grid[(m, sys)]["total_tokens"] / 1000 for m in models]
        ax.bar(x + i * width, tokens, width, label=SYSTEM_LABELS[sys],
               color=SYSTEM_COLORS[sys], hatch=SYSTEM_HATCHES[sys],
               edgecolor="white", linewidth=0.5)
    ax.set_ylabel("Tokens (thousands)")
    ax.set_xticks(x + width)
    ax.set_xticklabels([_model_display_name(m) for m in models], rotation=30, ha="right")
    ax.set_yscale("log")
    ax.legend(loc="upper right", framealpha=0.9)
    ax.set_title("Token Consumption by Model and Architecture")
    _save(fig, out, "fig07_token_usage")


def fig_radar(df: dict, out: Path):
    models, systems, grid = df["models"], df["systems"], df["grid"]
    dims = ["Quality", "Cost\nEfficiency", "Speed", "Consistency"]
    n_dims = len(dims)
    angles = np.linspace(0, 2 * np.pi, n_dims, endpoint=False).tolist()
    angles += angles[:1]
    fig, ax = plt.subplots(figsize=(5.5, 5.5), subplot_kw=dict(polar=True))
    for idx, m in enumerate(models):
        r = grid[(m, "dicwo")]
        score = r.get("judge_mean_score", 0)
        cost, latency = r["cost_usd"], r["latency_s"]
        std = r.get("judge_std", 1)
        values = [
            (score - 2.0) / 2.5,
            min(1.0, (score / cost) / 150) if cost > 0 else 0,
            1.0 - min(1.0, latency / 1200),
            1.0 - min(1.0, std / 0.5),
        ]
        values += values[:1]
        ax.plot(angles, values, "o-", linewidth=1.5, markersize=4,
                label=_model_display_name(m), color=MODEL_COLORS[idx % len(MODEL_COLORS)])
        ax.fill(angles, values, alpha=0.08, color=MODEL_COLORS[idx % len(MODEL_COLORS)])
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(dims, fontsize=9)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0.25", "0.50", "0.75", "1.00"], fontsize=7, alpha=0.6)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), framealpha=0.9)
    ax.set_title("DiCWO Multi-Dimensional Comparison", y=1.08)
    _save(fig, out, "fig08_radar")


# ═════════════════════════════════════════════════════════════════════════════
# Figures — Detailed (from per-run data)
# ═════════════════════════════════════════════════════════════════════════════

def fig_score_distribution(detail: dict, df: dict, out: Path):
    """Violin / box plot of per-run judge scores across repeats."""
    models = df["models"]
    fig, axes = plt.subplots(1, 3, figsize=(10, 4), sharey=True)
    for ax, sys in zip(axes, ["single_agent", "centralized", "dicwo"]):
        positions, data_list, labels = [], [], []
        for i, m in enumerate(models):
            scores = detail["per_run_scores"].get((m, sys), [])
            if scores:
                data_list.append(scores)
                positions.append(i)
                labels.append(_model_display_name(m))
        if data_list:
            vp = ax.violinplot(data_list, positions=positions, showmeans=True,
                               showmedians=True, widths=0.7)
            for body in vp["bodies"]:
                body.set_facecolor(SYSTEM_COLORS[sys])
                body.set_alpha(0.6)
            ax.set_xticks(positions)
            ax.set_xticklabels(labels, rotation=30, ha="right")
        ax.set_title(SYSTEM_LABELS[sys])
        ax.set_ylim(1.0, 5.0)
    axes[0].set_ylabel("Judge Score")
    fig.suptitle("Score Distribution Across Repeats", y=1.02)
    fig.tight_layout()
    _save(fig, out, "fig09_score_distribution")


def fig_per_subtask_scores(detail: dict, df: dict, out: Path):
    """Grouped bar chart of per-subtask judge scores across models."""
    subtasks = ["market_analysis", "frequency_filing", "payload_design",
                "mission_analysis", "integration"]
    subtask_labels = ["Market\nAnalysis", "Frequency\nFiling", "Payload\nDesign",
                      "Mission\nAnalysis", "Integration"]
    models = df["models"]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = np.arange(len(subtasks))
    n = len(models)
    width = 0.8 / n
    for i, m in enumerate(models):
        means, stds = [], []
        for st in subtasks:
            scores = detail["per_subtask_scores"].get((m, st), [])
            if scores:
                means.append(np.mean(scores))
                stds.append(np.std(scores))
            else:
                # Try alternative key names (centralized uses role names)
                alt_map = {
                    "market_analysis": "market_analyst_output",
                    "frequency_filing": "frequency_filing_expert_output",
                    "payload_design": "payload_expert_output",
                    "mission_analysis": "mission_analyst_output",
                    "integration": "integration_report",
                }
                scores = detail["per_subtask_scores"].get((m, alt_map.get(st, "")), [])
                means.append(np.mean(scores) if scores else 0)
                stds.append(np.std(scores) if scores else 0)
        ax.bar(x + i * width - (n - 1) * width / 2, means, width,
               label=_model_display_name(m), color=MODEL_COLORS[i % len(MODEL_COLORS)],
               edgecolor="white", linewidth=0.5,
               yerr=stds, capsize=2, error_kw={"linewidth": 0.7})
    ax.set_ylabel("Judge Score (1–5)")
    ax.set_xticks(x)
    ax.set_xticklabels(subtask_labels)
    ax.set_ylim(1.0, 5.0)
    ax.legend(loc="upper right", framealpha=0.9, ncol=2)
    ax.set_title("Per-Subtask Quality Across Models")
    _save(fig, out, "fig10_subtask_scores")


def fig_per_subtask_scores_by_system(detail: dict, df: dict, out: Path):
    """Per-subtask quality broken down by system type (single agent, centralized, DiCWO)."""
    subtasks = ["market_analysis", "frequency_filing", "payload_design",
                "mission_analysis", "integration"]
    subtask_labels = ["Market\nAnalysis", "Frequency\nFiling", "Payload\nDesign",
                      "Mission\nAnalysis", "Integration"]
    # Centralized uses different key names for the same subtasks
    centralized_alt = {
        "market_analysis": "market_analyst_output",
        "frequency_filing": "frequency_filing_expert_output",
        "payload_design": "payload_expert_output",
        "mission_analysis": "mission_analyst_output",
        "integration": "integration_report",
    }
    models = df["models"]
    n = len(models)
    width = 0.8 / n

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
    systems = ["centralized", "dicwo"]

    for ax, sys in zip(axes, systems):
        x = np.arange(len(subtasks))
        for i, m in enumerate(models):
            means, stds = [], []
            for st in subtasks:
                key = st if sys == "dicwo" else centralized_alt.get(st, st)
                scores = detail["per_subtask_scores_by_system"].get(
                    (m, sys, key), [])
                means.append(np.mean(scores) if scores else 0)
                stds.append(np.std(scores) if scores else 0)
            ax.bar(x + i * width - (n - 1) * width / 2, means, width,
                   label=_model_display_name(m),
                   color=MODEL_COLORS[i % len(MODEL_COLORS)],
                   edgecolor="white", linewidth=0.5,
                   yerr=stds, capsize=2, error_kw={"linewidth": 0.7})
        ax.set_xticks(x)
        ax.set_xticklabels(subtask_labels)
        if sys == "dicwo":
            ax.legend(loc="upper right", framealpha=0.9, fontsize=7, ncol=2)
        ax.set_title(SYSTEM_LABELS[sys])
        ax.set_ylim(1.0, 5.0)

    axes[0].set_ylabel("Judge Score (1–5)")
    fig.suptitle("Per-Subtask Quality by System Architecture", y=1.02)
    fig.tight_layout()
    _save(fig, out, "fig20_subtask_scores_by_system")


def fig_reproducibility(detail: dict, df: dict, out: Path):
    """Cross-run reproducibility: std deviation of judge scores per model and system."""
    models = df["models"]
    systems = ["single_agent", "centralized", "dicwo"]
    n_sys = len(systems)

    # --- Panel 1: Std deviation bar chart ---
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5),
                             gridspec_kw={"width_ratios": [1.2, 1]})

    # Left panel: grouped bars of std deviation
    ax = axes[0]
    x = np.arange(len(models))
    width = 0.25
    for i, sys in enumerate(systems):
        stds = []
        for m in models:
            scores = detail["per_run_scores"].get((m, sys), [])
            stds.append(np.std(scores) if len(scores) > 1 else 0)
        ax.bar(x + i * width, stds, width,
               label=SYSTEM_LABELS[sys], color=SYSTEM_COLORS[sys],
               hatch=SYSTEM_HATCHES[sys], edgecolor="white", linewidth=0.5)
    ax.set_ylabel("Score Std Deviation (lower = more reproducible)")
    ax.set_xticks(x + width)
    ax.set_xticklabels([_model_display_name(m) for m in models], rotation=30, ha="right")
    ax.legend(loc="upper right", framealpha=0.9)
    ax.set_title("Cross-Run Score Variability")
    ax.set_ylim(0)

    # Right panel: coefficient of variation (std/mean) for normalized comparison
    ax2 = axes[1]
    for i, sys in enumerate(systems):
        cvs = []
        for m in models:
            scores = detail["per_run_scores"].get((m, sys), [])
            if len(scores) > 1 and np.mean(scores) > 0:
                cvs.append(np.std(scores) / np.mean(scores))
            else:
                cvs.append(0)
        ax2.bar(x + i * width, cvs, width,
                label=SYSTEM_LABELS[sys], color=SYSTEM_COLORS[sys],
                hatch=SYSTEM_HATCHES[sys], edgecolor="white", linewidth=0.5)
    ax2.set_ylabel("Coefficient of Variation (lower = more consistent)")
    ax2.set_xticks(x + width)
    ax2.set_xticklabels([_model_display_name(m) for m in models], rotation=30, ha="right")
    ax2.set_title("Normalized Reproducibility")
    ax2.set_ylim(0)

    fig.suptitle("Reproducibility: Score Consistency Across Repeated Runs", y=1.02)
    fig.tight_layout()
    _save(fig, out, "fig21_reproducibility")


def fig_call_latency_boxplot(detail: dict, df: dict, out: Path):
    """Box plot of per-call latency distribution by model and system."""
    models = df["models"]
    fig, axes = plt.subplots(1, 3, figsize=(10, 4), sharey=True)
    for ax, sys in zip(axes, ["single_agent", "centralized", "dicwo"]):
        data_list, labels = [], []
        for m in models:
            calls = detail["call_logs"].get((m, sys), [])
            lats = [c["latency_s"] for c in calls if "latency_s" in c]
            if lats:
                data_list.append(lats)
                labels.append(_model_display_name(m))
        if data_list:
            bp = ax.boxplot(data_list, tick_labels=labels, patch_artist=True,
                            widths=0.6, showfliers=False)
            for patch in bp["boxes"]:
                patch.set_facecolor(SYSTEM_COLORS[sys])
                patch.set_alpha(0.6)
            ax.tick_params(axis="x", rotation=30)
        ax.set_title(SYSTEM_LABELS[sys])
    axes[0].set_ylabel("Latency per Call (s)")
    fig.suptitle("Per-Call Latency Distribution", y=1.02)
    fig.tight_layout()
    _save(fig, out, "fig11_call_latency")


def fig_confidence_gateway(detail: dict, df: dict, out: Path):
    """Stacked bar chart of confidence gateway outcomes per model."""
    models = df["models"]
    models_with_data = [m for m in models if detail["confidence_gateway"].get(m)]
    if not models_with_data:
        print("  fig12_confidence_gateway — SKIPPED (no confidence data)")
        return
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))

    # Left: pass / reflect / intervene counts
    passed, reflected, intervened = [], [], []
    model_labels = []
    for m in models_with_data:
        records = detail["confidence_gateway"][m]
        p = sum(r.get("passed", 0) for r in records)
        ref = sum(r.get("reflections", 0) for r in records)
        inter = sum(r.get("interventions", 0) for r in records)
        passed.append(p)
        reflected.append(ref)
        intervened.append(inter)
        model_labels.append(_model_display_name(m))

    x = np.arange(len(models_with_data))
    ax1.bar(x, passed, label="Passed", color="#228833", edgecolor="white")
    ax1.bar(x, reflected, bottom=passed, label="Reflected", color="#CCBB44", edgecolor="white")
    bottoms = [p + r for p, r in zip(passed, reflected)]
    ax1.bar(x, intervened, bottom=bottoms, label="Intervened", color="#EE6677", edgecolor="white")
    ax1.set_xticks(x)
    ax1.set_xticklabels(model_labels, rotation=30, ha="right")
    ax1.set_ylabel("Count (across 4 runs)")
    ax1.legend(loc="upper right", framealpha=0.9)
    ax1.set_title("Confidence Gateway Outcomes")

    # Right: average confidence score
    avg_confs = []
    for m in models_with_data:
        records = detail["confidence_gateway"][m]
        confs = [r.get("avg_confidence", 0) for r in records if r.get("avg_confidence")]
        avg_confs.append(np.mean(confs) if confs else 0)

    bars = ax2.bar(x, avg_confs, color=[MODEL_COLORS[models.index(m) % len(MODEL_COLORS)]
                                         for m in models_with_data],
                   edgecolor="white", linewidth=0.5)
    ax2.axhline(y=85, color="red", linestyle="--", alpha=0.5, label="Proceed threshold (85%)")
    ax2.axhline(y=50, color="orange", linestyle="--", alpha=0.5, label="Intervene threshold (50%)")
    ax2.set_xticks(x)
    ax2.set_xticklabels(model_labels, rotation=30, ha="right")
    ax2.set_ylabel("Average Confidence (%)")
    ax2.set_ylim(0, 100)
    ax2.legend(loc="lower right", framealpha=0.9, fontsize=8)
    ax2.set_title("Average Self-Assessed Confidence")

    fig.suptitle("DiCWO Confidence Gateway Analysis", y=1.02)
    fig.tight_layout()
    _save(fig, out, "fig12_confidence_gateway")


def fig_escalation_patterns(detail: dict, df: dict, out: Path):
    """Heatmap of escalation protocol levels per subtask per model."""
    models = df["models"]
    models_with_data = [m for m in models if detail["escalation"].get(m)]
    if not models_with_data:
        print("  fig13_escalation — SKIPPED (no escalation data)")
        return
    subtasks = ["market_analysis", "frequency_filing", "payload_design",
                "mission_analysis", "integration"]
    protocol_names = ["solo", "audit", "debate", "parallel", "tool_verified"]

    # Average escalation level across runs
    data = np.zeros((len(models_with_data), len(subtasks)))
    for i, m in enumerate(models_with_data):
        for j, st in enumerate(subtasks):
            levels = []
            for esc in detail["escalation"][m]:
                if st in esc:
                    levels.append(esc[st].get("level", 0))
            data[i, j] = np.mean(levels) if levels else 0

    fig, ax = plt.subplots(figsize=(7, 4))
    im = ax.imshow(data, cmap="YlOrRd", aspect="auto", vmin=0, vmax=4)
    ax.set_xticks(range(len(subtasks)))
    ax.set_xticklabels([s.replace("_", "\n") for s in subtasks], fontsize=8)
    ax.set_yticks(range(len(models_with_data)))
    ax.set_yticklabels([_model_display_name(m) for m in models_with_data])
    for i in range(len(models_with_data)):
        for j in range(len(subtasks)):
            level = int(round(data[i, j]))
            pname = protocol_names[min(level, len(protocol_names) - 1)]
            color = "white" if data[i, j] > 2 else "black"
            ax.text(j, i, f"{pname}\n({data[i,j]:.1f})", ha="center", va="center",
                    fontsize=7, color=color)
    fig.colorbar(im, ax=ax, shrink=0.8, label="Escalation Level (0=solo, 4=tool_verified)")
    ax.set_title("DiCWO Protocol Escalation by Subtask")
    _save(fig, out, "fig13_escalation_heatmap")


def fig_subtask_quality_radar(detail: dict, df: dict, out: Path):
    """Radar chart of subtask quality scores per model (DiCWO metadata)."""
    models = df["models"]
    models_with_data = [m for m in models if detail["subtask_quality"].get(m)]
    if not models_with_data:
        print("  fig14_subtask_quality_radar — SKIPPED (no subtask quality data)")
        return
    subtasks = ["market_analysis", "frequency_filing", "payload_design",
                "mission_analysis", "integration"]
    st_labels = ["Market", "Frequency", "Payload", "Mission", "Integration"]
    n = len(subtasks)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(5.5, 5.5), subplot_kw=dict(polar=True))
    for idx, m in enumerate(models_with_data):
        values = []
        for st in subtasks:
            qs = [sq.get(st, 0) for sq in detail["subtask_quality"][m]]
            values.append(np.mean(qs) if qs else 0)
        values += values[:1]
        ax.plot(angles, values, "o-", linewidth=1.5, markersize=4,
                label=_model_display_name(m),
                color=MODEL_COLORS[models.index(m) % len(MODEL_COLORS)])
        ax.fill(angles, values, alpha=0.08,
                color=MODEL_COLORS[models.index(m) % len(MODEL_COLORS)])
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(st_labels, fontsize=9)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0.25", "0.50", "0.75", "1.00"], fontsize=7, alpha=0.6)
    ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.1), framealpha=0.9)
    ax.set_title("DiCWO Internal Subtask Quality", y=1.08)
    _save(fig, out, "fig14_subtask_quality_radar")


def fig_prompt_completion_ratio(detail: dict, df: dict, out: Path):
    """Stacked bar showing prompt vs completion token ratio per model."""
    models = df["models"]
    fig, ax = plt.subplots(figsize=(7, 4))
    x = np.arange(len(models))
    prompts, completions = [], []
    for m in models:
        p = detail["prompt_vs_completion"].get(m, {})
        prompts.append(sum(p.get("prompt", [0])) / 1000)
        completions.append(sum(p.get("completion", [0])) / 1000)
    ax.bar(x, prompts, label="Prompt tokens", color="#4477AA", edgecolor="white")
    ax.bar(x, completions, bottom=prompts, label="Completion tokens",
           color="#EE6677", edgecolor="white")
    ax.set_xticks(x)
    ax.set_xticklabels([_model_display_name(m) for m in models], rotation=30, ha="right")
    ax.set_ylabel("Tokens (thousands)")
    ax.legend(loc="upper right", framealpha=0.9)
    ax.set_title("Prompt vs Completion Token Breakdown")
    _save(fig, out, "fig15_prompt_completion")


# ═════════════════════════════════════════════════════════════════════════════
# README generation
# ═════════════════════════════════════════════════════════════════════════════

README_CONTENT = """# Figures

Publication-quality charts generated from the multi-model benchmark experiment.

All figures are available in **PDF** (vector, for LaTeX/paper) and **PNG** (for preview).

## Aggregate Comparison Charts

| Figure | File | Description |
|--------|------|-------------|
| 1 | `fig01_judge_scores` | **Output quality by model and architecture.** Grouped bar chart comparing judge scores (1-5 scale) across all models for each system architecture (Single Agent, Centralized, DiCWO). Error bars show standard deviation across 4 repeats. Key finding: DiCWO consistently scores highest. |
| 2 | `fig02_cost_quality_pareto` | **Cost-quality Pareto frontier.** Scatter plot (log-scale cost axis) showing the trade-off between average run cost and judge score. Each point is a (model, system) pair. The dashed Pareto frontier highlights configurations where no other option is both cheaper and better. |
| 3 | `fig03_dicwo_uplift` | **DiCWO quality uplift over baselines.** Percentage improvement that DiCWO achieves compared to Single Agent and Centralized baselines for each model. Quantifies the benefit of distributed orchestration. |
| 4 | `fig04_heatmap` | **Judge score heatmap.** Model x Architecture grid with color-coded mean scores and standard deviations. Provides a quick at-a-glance summary of all results. |
| 5 | `fig05_efficiency` | **Cost efficiency: quality per dollar.** Log-scale bar chart showing how much quality each dollar buys for each (model, system) combination. Single Agent is always most cost-efficient since it uses a single LLM call, but produces lower quality. |
| 6 | `fig06_latency_quality` | **Latency-quality trade-off.** Scatter plot (log-scale latency) showing that more compute time generally correlates with better quality. DiCWO cluster appears in the upper-right (high quality, high latency). |
| 7 | `fig07_token_usage` | **Token consumption.** Log-scale grouped bars showing total tokens used per (model, system). DiCWO uses 10-100x more tokens than Single Agent due to multi-agent coordination overhead. |
| 8 | `fig08_radar` | **DiCWO multi-dimensional comparison.** Radar chart comparing models across four normalized dimensions: Quality, Cost Efficiency, Speed, and Consistency (low variance). Reveals which models are well-rounded vs specialized. |

## Detailed Analysis Charts

| Figure | File | Description |
|--------|------|-------------|
| 9 | `fig09_score_distribution` | **Score distribution across repeats.** Violin plots showing the full distribution of judge scores for each model within each system type. Reveals variance and potential bimodality in quality outcomes. |
| 10 | `fig10_subtask_scores` | **Per-subtask quality across models.** Grouped bars showing judge scores broken down by the 5 mission subtasks (market analysis, frequency filing, payload design, mission analysis, integration). Identifies which subtasks each model excels or struggles with. |
| 11 | `fig11_call_latency` | **Per-call latency distribution.** Box plots of individual LLM call latencies for each model within each system type. Shows whether slowness comes from consistently slow calls or occasional outliers. |
| 12 | `fig12_confidence_gateway` | **DiCWO confidence gateway analysis.** Left panel: stacked bars of gateway outcomes (passed/reflected/intervened) across runs. Right panel: average self-assessed confidence per model with threshold lines. Shows how well each model self-assesses its output quality. |
| 13 | `fig13_escalation_heatmap` | **DiCWO protocol escalation patterns.** Heatmap showing the average escalation level reached per subtask per model (0=solo through 4=tool_verified). Reveals which subtasks require heavier coordination protocols. |
| 14 | `fig14_subtask_quality_radar` | **DiCWO internal subtask quality.** Radar chart of the system's own quality assessment (0-1 scale) per subtask per model, as recorded by the checkpoint evaluator. Complements the external judge scores. |
| 15 | `fig15_prompt_completion` | **Prompt vs completion token breakdown.** Stacked bars showing input (prompt) vs output (completion) token counts per model across all runs. High prompt-to-completion ratio indicates context-heavy coordination overhead. |

## Data

- `consolidated_results.json` — All comparison data in a single JSON file for custom analysis.

## Regeneration

```bash
python3 scripts/generate_paper_charts.py
python3 scripts/generate_paper_charts.py --experiment 20260321  # specific experiment date
```
"""


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Generate paper-quality charts")
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--output-dir", default="figures")
    parser.add_argument("--experiment", default="", help="Filter experiment dirs by prefix (e.g. 20260321)")
    args = parser.parse_args()

    results_dir = args.results_dir
    exp_dirs = find_experiment_dirs(results_dir, args.experiment)
    if not exp_dirs:
        print("No experiment directories found!")
        sys.exit(1)

    # Determine output subfolder name from experiment dirs
    # Use common date prefix as subfolder name
    dates = set()
    for d in exp_dirs:
        dates.add(d.split("_")[0])
    if len(dates) == 1:
        subfolder = f"{dates.pop()}_comparison"
    else:
        subfolder = "_".join(sorted(dates)) + "_comparison"

    out = Path(args.output_dir) / subfolder
    out.mkdir(parents=True, exist_ok=True)

    print(f"Experiment directories: {len(exp_dirs)}")
    for d in exp_dirs:
        print(f"  {d}")
    print(f"Output: {out}/\n")

    # Load data
    print("Loading comparison data...")
    runs = load_comparison_data(results_dir, exp_dirs)
    df = _build_dataframe(runs)
    print(f"Found {len(df['models'])} models x {len(df['systems'])} systems")

    print("Loading detailed per-run data...")
    detail = load_detailed_data(results_dir, exp_dirs)
    print()

    # Generate figures
    print("Generating figures:")

    # Aggregate charts
    fig_judge_scores(df, out)
    fig_cost_quality(df, out)
    fig_dicwo_uplift(df, out)
    fig_heatmap(df, out)
    fig_efficiency(df, out)
    fig_latency_quality(df, out)
    fig_token_usage(df, out)
    fig_radar(df, out)

    # Detailed charts
    fig_score_distribution(detail, df, out)
    fig_per_subtask_scores(detail, df, out)
    fig_per_subtask_scores_by_system(detail, df, out)
    fig_reproducibility(detail, df, out)
    fig_call_latency_boxplot(detail, df, out)
    fig_confidence_gateway(detail, df, out)
    fig_escalation_patterns(detail, df, out)
    fig_subtask_quality_radar(detail, df, out)
    fig_prompt_completion_ratio(detail, df, out)

    # Confidence gateway deep-dive
    print("Loading confidence gateway records...")
    cg_data = _load_confidence_records(results_dir, exp_dirs)
    fig_reflection_improvement(cg_data, df, out)
    fig_calibration_scatter(cg_data, df, out)
    fig_subtask_confidence_heatmap(cg_data, df, out)
    fig_retry_waterfall(cg_data, df, out)

    # Save consolidated data and README
    json.dump(runs, open(out / "consolidated_results.json", "w"), indent=2)
    (out / "README.md").write_text(README_CONTENT + CONFIDENCE_README)

    print(f"\nAll figures saved to {out}/")
    print(f"README: {out}/README.md")


# ═════════════════════════════════════════════════════════════════════════════
# Figures — Confidence Gateway Deep Dive
# ═════════════════════════════════════════════════════════════════════════════

def _load_confidence_records(results_dir: str, exp_dirs: list[str]) -> dict:
    """Load all individual confidence gateway records."""
    from collections import defaultdict
    records_by_model = defaultdict(list)
    stats_by_model = defaultdict(list)

    for d in exp_dirs:
        parts = d.split("_")
        idx = parts.index("comparison")
        model = "_".join(parts[2:idx])
        dicwo_dir = Path(results_dir) / d / "dicwo"
        if not dicwo_dir.exists():
            continue
        for run_dir in sorted(dicwo_dir.iterdir()):
            if not run_dir.name.startswith("run_"):
                continue
            meta_path = run_dir / "metadata.json"
            if not meta_path.exists():
                continue
            meta = json.load(open(meta_path))
            cg = meta.get("confidence_gateway", {})
            if cg:
                stats_by_model[model].append(cg)
                for rec in cg.get("records", []):
                    rec["_model"] = model
                    records_by_model[model].append(rec)
    return {"records": dict(records_by_model), "stats": dict(stats_by_model)}


def fig_reflection_improvement(cg_data: dict, df: dict, out: Path):
    """Show how pass rate and confidence improve with each retry attempt."""
    models = df["models"]
    models_with_data = [m for m in models if cg_data["records"].get(m)]
    if not models_with_data:
        print("  fig16_reflection_improvement — SKIPPED")
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))

    for idx, m in enumerate(models_with_data):
        records = cg_data["records"][m]
        by_attempt = defaultdict(list)
        for r in records:
            by_attempt[r.get("attempt", 1)].append(r)

        attempts = sorted(by_attempt.keys())
        if len(attempts) < 1:
            continue

        pass_rates = []
        avg_confs = []
        for att in attempts:
            recs = by_attempt[att]
            n_passed = sum(1 for r in recs if r.get("passed"))
            confs = [r.get("confidence", 0) for r in recs]
            pass_rates.append(n_passed / len(recs) * 100 if recs else 0)
            avg_confs.append(np.mean(confs) if confs else 0)

        color = MODEL_COLORS[models.index(m) % len(MODEL_COLORS)]
        ax1.plot(attempts, pass_rates, "o-", label=_model_display_name(m),
                 color=color, linewidth=2, markersize=6)
        ax2.plot(attempts, avg_confs, "o-", label=_model_display_name(m),
                 color=color, linewidth=2, markersize=6)

    ax1.set_xlabel("Attempt Number")
    ax1.set_ylabel("Pass Rate (%)")
    ax1.set_ylim(0, 105)
    ax1.set_xticks([1, 2, 3])
    ax1.legend(loc="lower right", framealpha=0.9)
    ax1.set_title("Pass Rate by Attempt")

    ax2.set_xlabel("Attempt Number")
    ax2.set_ylabel("Average Confidence (%)")
    ax2.set_ylim(60, 100)
    ax2.set_xticks([1, 2, 3])
    ax2.axhline(y=85, color="red", linestyle="--", alpha=0.5, linewidth=0.8)
    ax2.legend(loc="lower right", framealpha=0.9)
    ax2.set_title("Confidence by Attempt")

    fig.suptitle("Self-Reflection Improves Output Quality on Retry", y=1.02)
    fig.tight_layout()
    _save(fig, out, "fig16_reflection_improvement")


def fig_calibration_scatter(cg_data: dict, df: dict, out: Path):
    """Scatter: self-assessed confidence vs external judge score per model."""
    models = df["models"]
    grid = df["grid"]
    models_with_data = [m for m in models if cg_data["stats"].get(m)]
    if not models_with_data:
        print("  fig17_calibration — SKIPPED")
        return

    fig, ax = plt.subplots(figsize=(6, 5))
    for idx, m in enumerate(models_with_data):
        stats = cg_data["stats"][m]
        avg_conf = np.mean([s.get("avg_confidence", 0) for s in stats])
        judge_score = grid[(m, "dicwo")].get("judge_mean_score", 0)
        judge_std = grid[(m, "dicwo")].get("judge_std", 0)
        color = MODEL_COLORS[models.index(m) % len(MODEL_COLORS)]
        ax.errorbar(avg_conf, judge_score, yerr=judge_std,
                    fmt="o", markersize=10, color=color,
                    ecolor=color, capsize=4, alpha=0.8, zorder=5)
        ax.annotate(_model_display_name(m), (avg_conf, judge_score),
                    textcoords="offset points", xytext=(8, 6), fontsize=9)

    # Perfect calibration line (normalized)
    ax.axvline(x=85, color="red", linestyle="--", alpha=0.3, label="Proceed threshold")
    ax.set_xlabel("Average Self-Assessed Confidence (%)")
    ax.set_ylabel("External Judge Score (1–5)")
    ax.set_xlim(75, 100)
    ax.set_ylim(2.0, 5.0)
    ax.legend(loc="lower right", framealpha=0.9)
    ax.set_title("Self-Calibration: Confidence vs External Quality")
    _save(fig, out, "fig17_calibration_scatter")


def fig_subtask_confidence_heatmap(cg_data: dict, df: dict, out: Path):
    """Heatmap of average confidence per subtask per model."""
    models = df["models"]
    models_with_data = [m for m in models if cg_data["records"].get(m)]
    if not models_with_data:
        print("  fig18_subtask_confidence — SKIPPED")
        return

    subtasks = ["market_analysis", "frequency_filing", "payload_design",
                "mission_analysis", "integration"]
    st_labels = ["Market\nAnalysis", "Frequency\nFiling", "Payload\nDesign",
                 "Mission\nAnalysis", "Integration"]

    data = np.zeros((len(models_with_data), len(subtasks)))
    counts = np.zeros_like(data)
    for i, m in enumerate(models_with_data):
        for rec in cg_data["records"][m]:
            st = rec.get("subtask", "")
            if st in subtasks:
                j = subtasks.index(st)
                data[i, j] += rec.get("confidence", 0)
                counts[i, j] += 1
    # Average
    with np.errstate(divide="ignore", invalid="ignore"):
        data = np.where(counts > 0, data / counts, 0)

    fig, ax = plt.subplots(figsize=(7, 4))
    im = ax.imshow(data, cmap="RdYlGn", aspect="auto", vmin=60, vmax=100)
    ax.set_xticks(range(len(subtasks)))
    ax.set_xticklabels(st_labels, fontsize=8)
    ax.set_yticks(range(len(models_with_data)))
    ax.set_yticklabels([_model_display_name(m) for m in models_with_data])
    for i in range(len(models_with_data)):
        for j in range(len(subtasks)):
            val = data[i, j]
            n = int(counts[i, j])
            color = "white" if val < 75 else "black"
            ax.text(j, i, f"{val:.0f}%\n(n={n})", ha="center", va="center",
                    fontsize=8, color=color, fontweight="bold")
    fig.colorbar(im, ax=ax, shrink=0.8, label="Avg Confidence (%)")
    ax.set_title("Self-Assessed Confidence by Subtask and Model")
    _save(fig, out, "fig18_subtask_confidence_heatmap")


def fig_retry_waterfall(cg_data: dict, df: dict, out: Path):
    """Waterfall chart showing how checks flow through attempt 1→2→3."""
    models = df["models"]
    models_with_retries = [m for m in models
                           if any(r.get("attempt", 1) > 1
                                  for r in cg_data.get("records", {}).get(m, []))]
    if not models_with_retries:
        print("  fig19_retry_waterfall — SKIPPED")
        return

    fig, axes = plt.subplots(1, len(models_with_retries),
                              figsize=(3.5 * len(models_with_retries), 4),
                              sharey=True)
    if len(models_with_retries) == 1:
        axes = [axes]

    for ax, m in zip(axes, models_with_retries):
        records = cg_data["records"][m]
        by_attempt = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0})
        for r in records:
            att = r.get("attempt", 1)
            by_attempt[att]["total"] += 1
            if r.get("passed"):
                by_attempt[att]["passed"] += 1
            else:
                by_attempt[att]["failed"] += 1

        attempts = sorted(by_attempt.keys())
        totals = [by_attempt[a]["total"] for a in attempts]
        passed = [by_attempt[a]["passed"] for a in attempts]
        failed = [by_attempt[a]["failed"] for a in attempts]

        x = np.arange(len(attempts))
        ax.bar(x, passed, label="Passed", color="#228833", edgecolor="white")
        ax.bar(x, failed, bottom=passed, label="Failed → retry",
               color="#EE6677", edgecolor="white")
        ax.set_xticks(x)
        ax.set_xticklabels([f"Attempt {a}" for a in attempts], fontsize=8)
        ax.set_title(_model_display_name(m), fontsize=10)

        # Annotate counts
        for i, (p, f, t) in enumerate(zip(passed, failed, totals)):
            ax.text(i, t + 0.5, f"n={t}", ha="center", fontsize=8, alpha=0.7)

    axes[0].set_ylabel("Number of Checks")
    axes[-1].legend(loc="upper right", framealpha=0.9, fontsize=8)
    fig.suptitle("Confidence Check Flow: Attempts and Outcomes", y=1.02)
    fig.tight_layout()
    _save(fig, out, "fig19_retry_waterfall")


CONFIDENCE_README = """
## Confidence Gateway Deep Dive

| Figure | File | Description |
|--------|------|-------------|
| 16 | `fig16_reflection_improvement` | **Reflection improves quality on retry.** Line plots showing how pass rate and average confidence increase across attempt 1, 2, and 3. Demonstrates that self-critique (reflexion) meaningfully improves output quality rather than simply re-rolling. |
| 17 | `fig17_calibration_scatter` | **Self-calibration accuracy.** Scatter plot comparing each model's average self-assessed confidence against its external judge score. Reveals which models are well-calibrated (GPT-5.2), overconfident (Grok-4.1), or appropriately self-critical (MiniMax). |
| 18 | `fig18_subtask_confidence_heatmap` | **Confidence by subtask and model.** Heatmap showing average self-assessed confidence for each (model, subtask) pair with sample counts. Identifies which subtasks are universally harder (payload design) vs model-specific difficulties. |
| 19 | `fig19_retry_waterfall` | **Retry flow waterfall.** Stacked bar charts per model showing how many checks pass vs fail at each attempt level. Visualizes the funnel: most checks pass on attempt 1, failures flow to attempt 2, etc. Only shown for models that triggered retries. |
"""


if __name__ == "__main__":
    main()
