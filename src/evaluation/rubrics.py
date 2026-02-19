"""Rubric definitions for LLM-as-a-Judge evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RubricCriterion:
    """A single scoring criterion within a rubric."""

    name: str
    description: str
    weight: float = 1.0

    def to_prompt(self) -> str:
        return f"- **{self.name}** (weight {self.weight}): {self.description}"


@dataclass
class Rubric:
    """A complete rubric for evaluating one artifact."""

    name: str
    description: str
    criteria: list[RubricCriterion] = field(default_factory=list)

    def to_prompt(self) -> str:
        criteria_text = "\n".join(c.to_prompt() for c in self.criteria)
        return (
            f"## Rubric: {self.name}\n"
            f"{self.description}\n\n"
            f"Score each criterion from 1 (poor) to 5 (excellent):\n"
            f"{criteria_text}"
        )


# ---------------------------------------------------------------------------
# Artifact-level rubrics
# ---------------------------------------------------------------------------

MARKET_ANALYSIS_RUBRIC = Rubric(
    name="Market Analysis",
    description="Evaluate the market analysis output for the DTHH constellation.",
    criteria=[
        RubricCriterion(
            "demand_grounding",
            "Is demand grounded in data (population stats, connectivity gaps, references)?",
            weight=1.5,
        ),
        RubricCriterion(
            "region_justification",
            "Are target regions justified with geographic and economic reasoning?",
        ),
        RubricCriterion(
            "throughput_derivation",
            "Is the total throughput requirement derived correctly from user counts and data rates?",
            weight=1.5,
        ),
        RubricCriterion(
            "completeness",
            "Does the analysis cover all required elements (regions, users, rates, total throughput)?",
        ),
    ],
)

FREQUENCY_FILING_RUBRIC = Rubric(
    name="Frequency Filing",
    description="Evaluate the frequency/spectrum plan for DTHH.",
    criteria=[
        RubricCriterion(
            "itu_compliance",
            "Are selected bands ITU-compliant and appropriate for MSS/DTHH?",
            weight=1.5,
        ),
        RubricCriterion(
            "gt_eirp_values",
            "Are G/T and EIRP values correct and referenced for standard smartphones?",
            weight=1.5,
        ),
        RubricCriterion(
            "bandwidth_justification",
            "Is the selected bandwidth justified against throughput requirements?",
        ),
        RubricCriterion(
            "reference_comparison",
            "Is there comparison with existing DTHH operators (AST SpaceMobile, etc.)?",
        ),
    ],
)

PAYLOAD_DESIGN_RUBRIC = Rubric(
    name="Payload Design",
    description="Evaluate link budgets and antenna sizing.",
    criteria=[
        RubricCriterion(
            "link_budget_closure",
            "Do link budgets close for each altitude (positive margin)?",
            weight=2.0,
        ),
        RubricCriterion(
            "antenna_sizing",
            "Are antenna sizes consistent with altitude and frequency? Match AST SpaceMobile?",
            weight=1.5,
        ),
        RubricCriterion(
            "table_format",
            "Are link budgets presented in clear table format with all parameters?",
        ),
        RubricCriterion(
            "physics_consistency",
            "Are FSPL, gain, beamwidth calculations physically consistent?",
            weight=1.5,
        ),
    ],
)

MISSION_ANALYSIS_RUBRIC = Rubric(
    name="Mission Analysis",
    description="Evaluate constellation sizing and cost analysis.",
    criteria=[
        RubricCriterion(
            "constellation_sizing",
            "Is constellation size realistic for each altitude given beamwidth?",
            weight=1.5,
        ),
        RubricCriterion(
            "cost_estimates",
            "Are cost estimates reasonable ($100M-$10B) with Falcon 9 pricing?",
            weight=1.5,
        ),
        RubricCriterion(
            "trade_offs",
            "Are altitude/cost/coverage trade-offs clearly justified?",
        ),
        RubricCriterion(
            "reference_comparison",
            "Is the result compared with existing systems like AST SpaceMobile?",
        ),
    ],
)

INTEGRATION_RUBRIC = Rubric(
    name="Integration",
    description="Evaluate the final integrated mission concept.",
    criteria=[
        RubricCriterion(
            "cross_consistency",
            "Are all subsystem outputs consistent with each other (no contradictions)?",
            weight=2.0,
        ),
        RubricCriterion(
            "completeness",
            "Is the final design complete (orbit, constellation, link budget, cost)?",
            weight=1.5,
        ),
        RubricCriterion(
            "technical_soundness",
            "Are the engineering choices technically sound and realistic?",
            weight=1.5,
        ),
        RubricCriterion(
            "trade_documentation",
            "Are key trade-offs and risks documented?",
        ),
    ],
)

# Mapping from artifact key patterns to rubrics
ARTIFACT_RUBRICS: dict[str, Rubric] = {
    "market": MARKET_ANALYSIS_RUBRIC,
    "frequency": FREQUENCY_FILING_RUBRIC,
    "payload": PAYLOAD_DESIGN_RUBRIC,
    "mission": MISSION_ANALYSIS_RUBRIC,
    "integration": INTEGRATION_RUBRIC,
    "complete_design": INTEGRATION_RUBRIC,  # Single-agent output
}


# ---------------------------------------------------------------------------
# Workflow-level rubric (multi-agent only)
# ---------------------------------------------------------------------------

WORKFLOW_RUBRIC = Rubric(
    name="Workflow Quality",
    description="Evaluate the multi-agent coordination process.",
    criteria=[
        RubricCriterion(
            "agent_selection",
            "Were the right agents consulted at the right time?",
        ),
        RubricCriterion(
            "information_sharing",
            "Was information shared effectively between specialists?",
        ),
        RubricCriterion(
            "convergence",
            "Were iterations productive (convergence, not circular)?",
        ),
    ],
)


def get_rubric_for_artifact(key: str) -> Rubric | None:
    """Find the matching rubric for an artifact key."""
    key_lower = key.lower()
    for pattern, rubric in ARTIFACT_RUBRICS.items():
        if pattern in key_lower:
            return rubric
    return None
