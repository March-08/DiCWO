# Human Expert Scoresheet

Auto-generated Markdown scoresheets for manual review by a domain expert. The scoresheet mirrors the LLM judge rubrics but provides space for human scores and free-text comments.

## Generating a Scoresheet

```python
from src.evaluation.scoresheet import generate_scoresheet
from src.core.logging_utils import load_json

artifacts = load_json("results/.../artifacts.json")
sheet = generate_scoresheet(
    artifacts,
    system_type="dicwo",
    experiment_name="experiment_1"
)

with open("scoresheet.md", "w") as f:
    f.write(sheet)
```

## Scoresheet Structure

The generated Markdown contains:

1. **Header** — experiment name, system type, evaluator name/date fields
2. **Per-artifact rubric tables** — one section per subtask with:
    - Criterion name
    - Score column (1–5, blank for the human to fill)
    - Weight
    - Comments column
    - Subsection overall score
3. **Workflow rubric** (multi-agent systems only) — agent selection, information sharing, convergence
4. **Overall assessment** — overall score, "would you use this as a Phase 0/A starting point?", strengths, weaknesses, comments

## Example Output

```markdown
# Expert Evaluation Scoresheet

**Experiment**: dicwo_run_1
**Evaluator**: _________________________
**Date**: _________________________

---

## Payload Design

| Criterion | Score (1-5) | Weight | Comments |
|-----------|-------------|--------|----------|
| Link budget closure | _____ | 2.0 | |
| Antenna sizing | _____ | 1.5 | |
| Table format | _____ | 1.0 | |
| Physics consistency | _____ | 1.5 | |

**Subsection overall**: _____ / 5
```

## Implementation

:material-file-code: `src/evaluation/scoresheet.py`
