"""Multi-system comparison: load results from multiple runs and generate tables."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.core.logging_utils import load_json, save_json


def load_run(run_dir: str | Path) -> dict[str, Any]:
    """Load all result files from a single run directory."""
    run_dir = Path(run_dir)
    result: dict[str, Any] = {}

    for filename in ["metadata.json", "metrics.json", "artifacts.json",
                     "evaluation.json", "conversation_log.json", "averages.json"]:
        path = run_dir / filename
        if path.exists():
            result[filename.replace(".json", "")] = load_json(path)

    for md_name in ["report.md", "mission_report.md", "summary.md",
                    "mission_report_best.md", "conversation_trace.md"]:
        path = run_dir / md_name
        if path.exists():
            result[md_name.replace(".md", "")] = path.read_text()

    return result


def find_runs(results_dir: str | Path = "results") -> list[Path]:
    """Find all run directories that contain a metadata.json (leaf runs)."""
    results_dir = Path(results_dir)
    if not results_dir.exists():
        return []
    runs = [d for d in results_dir.iterdir()
            if d.is_dir() and (d / "metadata.json").exists()]
    return sorted(runs)


def find_groups(results_dir: str | Path = "results") -> list[Path]:
    """Find experiment group directories (those with subdirectories containing metadata)."""
    results_dir = Path(results_dir)
    if not results_dir.exists():
        return []
    groups = []
    for d in sorted(results_dir.iterdir()):
        if not d.is_dir():
            continue
        # A group has subdirs with metadata, or has averages.json
        has_sub_runs = any(
            (sub / "metadata.json").exists()
            for sub in d.iterdir() if sub.is_dir()
        )
        if has_sub_runs or (d / "averages.json").exists():
            groups.append(d)
    return groups


def find_system_dirs(group_dir: str | Path) -> dict[str, Path]:
    """Within a group directory, find each system's result folder."""
    group_dir = Path(group_dir)
    systems = {}
    for d in sorted(group_dir.iterdir()):
        if not d.is_dir():
            continue
        # Check if it's a leaf run (has metadata.json directly)
        if (d / "metadata.json").exists():
            meta = load_json(d / "metadata.json")
            systems[meta.get("system_type", d.name)] = d
        # Or a repeated-run folder (has averages.json + sub-runs)
        elif (d / "averages.json").exists():
            # Infer system type from first sub-run
            for sub in sorted(d.iterdir()):
                if sub.is_dir() and (sub / "metadata.json").exists():
                    meta = load_json(sub / "metadata.json")
                    systems[meta.get("system_type", d.name)] = d
                    break
    return systems


def _extract_row(run_dir: Path) -> dict[str, Any]:
    """Extract a comparison row from a run directory (leaf or averaged)."""
    run_dir = Path(run_dir)
    data = load_run(run_dir)
    meta = data.get("metadata", {})
    averages = data.get("averages")

    # If this is a repeated-run folder, use averages
    if averages:
        return {
            "run_dir": str(run_dir),
            "system_type": meta.get("system_type", _infer_system_type(run_dir)),
            "model": meta.get("model", averages.get("model", "unknown")),
            "num_runs": averages.get("num_runs", 1),
            "num_calls": averages.get("num_calls", 0),
            "total_tokens": averages.get("total_tokens", 0),
            "cost_usd": averages.get("cost_usd", 0),
            "latency_s": averages.get("latency_s", 0),
            "judge_mean_score": averages.get("judge_mean_score"),
            "judge_std": averages.get("judge_std"),
        }

    # Single run
    metrics = data.get("metrics", {})
    evaluation = data.get("evaluation", {})
    totals = metrics.get("totals", {})
    judge_scores = evaluation.get("judge_scores", {})
    aggregate = judge_scores.get("_aggregate", {})

    return {
        "run_dir": str(run_dir),
        "system_type": meta.get("system_type", "unknown"),
        "model": meta.get("model", "unknown"),
        "num_runs": 1,
        "num_calls": totals.get("num_calls", 0),
        "total_tokens": totals.get("total_tokens", 0),
        "cost_usd": totals.get("cost_usd", 0),
        "latency_s": totals.get("latency_s", 0),
        "judge_mean_score": aggregate.get("mean_score"),
        "judge_std": None,
    }


def _infer_system_type(run_dir: Path) -> str:
    """Infer system type from sub-run metadata."""
    for sub in sorted(run_dir.iterdir()):
        if sub.is_dir() and (sub / "metadata.json").exists():
            meta = load_json(sub / "metadata.json")
            return meta.get("system_type", "unknown")
    return run_dir.name


def compare_runs(run_dirs: list[str | Path]) -> dict[str, Any]:
    """Compare multiple runs and produce a structured comparison."""
    rows = [_extract_row(Path(d)) for d in run_dirs]
    return {"runs": rows, "num_runs": len(rows)}


def compare_group(group_dir: str | Path) -> dict[str, Any]:
    """Compare all systems within an experiment group."""
    systems = find_system_dirs(group_dir)
    rows = [_extract_row(d) for d in systems.values()]
    return {"runs": rows, "num_runs": len(rows), "group_dir": str(group_dir)}


def comparison_to_markdown(comparison: dict[str, Any]) -> str:
    """Generate a Markdown comparison table."""
    runs = comparison["runs"]
    if not runs:
        return "No runs to compare."

    has_repeats = any(r.get("num_runs", 1) > 1 for r in runs)

    header = "| System | Model |"
    sep = "|--------|-------|"
    if has_repeats:
        header += " Runs |"
        sep += "------|"
    header += " Calls | Tokens | Cost ($) | Latency (s) | Judge Score |"
    sep += "-------|--------|----------|-------------|-------------|"

    lines = ["# System Comparison", "", header, sep]

    for r in runs:
        judge = "N/A"
        if r.get("judge_mean_score") is not None:
            judge = f"{r['judge_mean_score']:.2f}"
            if r.get("judge_std") is not None:
                judge += f" ± {r['judge_std']:.2f}"

        row = f"| {r['system_type']} | {r['model']} |"
        if has_repeats:
            row += f" {r.get('num_runs', 1)} |"
        row += (
            f" {r['num_calls']:.0f} | {r['total_tokens']:,.0f} | "
            f"{r['cost_usd']:.4f} | {r['latency_s']:.1f} | {judge} |"
        )
        lines.append(row)

    return "\n".join(lines)
