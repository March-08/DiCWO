# LLM-as-a-Judge

A separate LLM (the judge) scores each system output against predefined rubrics. The judge is configured independently from the agents — it can be a stronger, more expensive model.

## How It Works

1. For each artifact, the matching rubric is loaded
2. The judge receives: rubric + artifact text + scoring instructions
3. It returns JSON with per-criterion scores (1–5), justifications, and a weighted overall score
4. Scores are aggregated across all artifacts into a `mean_score`

The judge runs at `temperature=0.3` for scoring consistency.

## Rubrics

### Market Analysis

| Criterion | Weight | Checks |
|-----------|--------|--------|
| Demand grounding | 1.5x | Is demand backed by data (population, connectivity gaps)? |
| Region justification | 1.0x | Are target regions justified geographically and economically? |
| Throughput derivation | 1.5x | Is total throughput derived correctly from user counts and rates? |
| Completeness | 1.0x | Are all required elements present? |

### Frequency Filing

| Criterion | Weight | Checks |
|-----------|--------|--------|
| ITU compliance | 1.5x | Are selected bands appropriate for MSS/DTHH? |
| G/T and EIRP values | 1.5x | Are smartphone RF parameters correct and referenced? |
| Bandwidth justification | 1.0x | Does bandwidth match throughput requirements? |
| Reference comparison | 1.0x | Comparison with AST SpaceMobile and others? |

### Payload Design

| Criterion | Weight | Checks |
|-----------|--------|--------|
| Link budget closure | 2.0x | Positive margin at each altitude? |
| Antenna sizing | 1.5x | Consistent with altitude, frequency, and references? |
| Table format | 1.0x | Clear tables with all parameters? |
| Physics consistency | 1.5x | FSPL, gain, beamwidth calculations correct? |

### Mission Analysis

| Criterion | Weight | Checks |
|-----------|--------|--------|
| Constellation sizing | 1.5x | Realistic satellite count per altitude? |
| Cost estimates | 1.5x | Within $100M–$10B with Falcon 9 pricing? |
| Trade-offs | 1.0x | Altitude/cost/coverage trade-offs justified? |
| Reference comparison | 1.0x | Compared with AST SpaceMobile? |

### Integration

| Criterion | Weight | Checks |
|-----------|--------|--------|
| Cross-consistency | 2.0x | No contradictions between subsystems? |
| Completeness | 1.5x | Covers orbit, constellation, budget, cost? |
| Technical soundness | 1.5x | Engineering choices realistic? |
| Trade documentation | 1.0x | Key trade-offs and risks documented? |

### Workflow (multi-agent only)

| Criterion | Checks |
|-----------|--------|
| Agent selection | Were the right agents consulted at the right time? |
| Information sharing | Was information passed effectively between specialists? |
| Convergence | Were iterations productive (not circular)? |

## Output Format

```json title="evaluation.json (excerpt)"
{
  "judge_scores": {
    "market_analysis": {
      "criteria_scores": {
        "demand_grounding": {
          "score": 4,
          "justification": "References ITU data and World Bank statistics..."
        }
      },
      "overall_score": 3.8,
      "summary": "Solid market analysis with quantitative demand estimates..."
    },
    "_aggregate": {
      "mean_score": 3.65,
      "num_artifacts_judged": 5
    }
  }
}
```

## Implementation

:material-file-code: `src/evaluation/llm_judge.py` — Judge logic and prompts
:material-file-code: `src/evaluation/rubrics.py` — Rubric definitions as dataclasses
