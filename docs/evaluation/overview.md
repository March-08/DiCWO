# Evaluation Overview

Outputs are assessed through two independent layers, providing both automated and human-verifiable quality signals.

```mermaid
graph TD
    S[System Output] --> J[Layer 1: LLM Judge]
    S --> H[Layer 2: Human Scoresheet]
    J --> E[evaluation.json]
    H --> SC[scoresheet.md]
```

## Layer Summary

| Layer | Method | Output | Cost |
|-------|--------|--------|------|
| [LLM Judge](judge.md) | GPT scores against rubrics | Scores 1-5 + justifications | ~1 LLM call per artifact |
| [Human Scoresheet](scoresheet.md) | Expert fills structured rubric | Comments + scores | Manual |

## When Each Runs

- **LLM Judge** — runs automatically after each system completes (disable with `--no-judge`)
- **Human Scoresheet** — generated on demand via Python API

## Aggregate Metrics

The comparison table shows the evaluation column:

| Metric | Source | Range |
|--------|--------|-------|
| **Judge Score** | Mean of LLM judge overall scores | 1.0 – 5.0 |
