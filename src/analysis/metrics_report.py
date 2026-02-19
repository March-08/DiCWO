"""Generate Markdown/CSV comparison tables from experiment results."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from src.runner.comparison import compare_runs, comparison_to_markdown, find_runs


def generate_metrics_report(
    results_dir: str | Path = "results",
    output_path: str | Path | None = None,
) -> str:
    """Generate a comprehensive metrics report across all runs."""
    runs = find_runs(results_dir)
    if not runs:
        return "No experiment runs found."

    comparison = compare_runs(runs)
    md = comparison_to_markdown(comparison)

    # Add per-system details
    lines = [md, "", "---", ""]

    for run_data in comparison["runs"]:
        run_dir = Path(run_data["run_dir"])
        report_path = run_dir / "report.md"
        if report_path.exists():
            lines.append(f"## Details: {run_data['system_type']}")
            lines.append("")
            lines.append(report_path.read_text())
            lines.append("")

    report = "\n".join(lines)

    if output_path:
        Path(output_path).write_text(report)

    return report


def generate_csv(
    results_dir: str | Path = "results",
    output_path: str | Path | None = None,
) -> str:
    """Generate a CSV comparison table."""
    runs = find_runs(results_dir)
    comparison = compare_runs(runs)

    output = io.StringIO()
    if comparison["runs"]:
        writer = csv.DictWriter(output, fieldnames=comparison["runs"][0].keys())
        writer.writeheader()
        writer.writerows(comparison["runs"])

    csv_text = output.getvalue()

    if output_path:
        Path(output_path).write_text(csv_text)

    return csv_text
