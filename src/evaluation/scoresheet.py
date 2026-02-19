"""Generate human evaluation scoresheets as Markdown."""

from __future__ import annotations

from typing import Any

from src.evaluation.rubrics import (
    ARTIFACT_RUBRICS,
    WORKFLOW_RUBRIC,
    Rubric,
    get_rubric_for_artifact,
)


def generate_scoresheet(
    artifacts: dict[str, Any],
    system_type: str,
    experiment_name: str = "",
) -> str:
    """Generate a Markdown scoresheet for human expert review."""
    lines = [
        f"# Expert Evaluation Scoresheet",
        f"",
        f"**Experiment**: {experiment_name}",
        f"**System**: {system_type}",
        f"**Evaluator**: _________________________",
        f"**Date**: _________________________",
        f"",
        f"---",
        f"",
        f"## Instructions",
        f"",
        f"Score each criterion from 1 (poor) to 5 (excellent). "
        f"Add comments where appropriate.",
        f"",
    ]

    # Artifact-level scoring
    for key, value in artifacts.items():
        rubric = get_rubric_for_artifact(key)
        if rubric is None:
            continue

        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## {rubric.name}")
        lines.append(f"")
        lines.append(f"*{rubric.description}*")
        lines.append(f"")
        lines.append(f"| Criterion | Score (1-5) | Weight | Comments |")
        lines.append(f"|-----------|-------------|--------|----------|")

        for criterion in rubric.criteria:
            lines.append(
                f"| {criterion.name} | _____ | {criterion.weight} | |"
            )

        lines.append(f"")
        lines.append(f"**Subsection overall**: _____ / 5")
        lines.append(f"")
        lines.append(f"**Expert comments**:")
        lines.append(f"")
        lines.append(f"")

    # Workflow rubric (multi-agent only)
    if system_type != "single_agent":
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## {WORKFLOW_RUBRIC.name}")
        lines.append(f"")
        lines.append(f"*{WORKFLOW_RUBRIC.description}*")
        lines.append(f"")
        lines.append(f"| Criterion | Score (1-5) | Weight | Comments |")
        lines.append(f"|-----------|-------------|--------|----------|")

        for criterion in WORKFLOW_RUBRIC.criteria:
            lines.append(
                f"| {criterion.name} | _____ | {criterion.weight} | |"
            )

        lines.append(f"")
        lines.append(f"**Workflow overall**: _____ / 5")
        lines.append(f"")

    # Overall assessment
    lines.extend([
        f"---",
        f"",
        f"## Overall Assessment",
        f"",
        f"**Overall score**: _____ / 5",
        f"",
        f"**Would you use this design as a Phase 0/A starting point?** Yes / No",
        f"",
        f"**Key strengths**:",
        f"",
        f"",
        f"**Key weaknesses**:",
        f"",
        f"",
        f"**Additional comments**:",
        f"",
        f"",
    ])

    return "\n".join(lines)
