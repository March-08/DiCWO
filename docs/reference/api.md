# API Reference

Key classes and functions for programmatic use.

## Core

### `LLMClient`

:material-file-code: `src/core/llm_client.py`

```python
from src.core.llm_client import LLMClient

client = LLMClient(
    api_key="sk-...",
    model="meta-llama/llama-3.3-70b-instruct",
    provider="openrouter",       # "openai" | "openrouter"
    temperature=0.7,
)

response, record = client.chat(
    messages=[{"role": "user", "content": "Hello"}],
    agent_name="test",
)

print(record.total_tokens, record.cost_usd, record.latency_s)
```

### `BaseAgent`

:material-file-code: `src/core/agent.py`

```python
from src.core.agent import BaseAgent, AgentIdentity

identity = AgentIdentity(
    name="Payload Expert",
    role="RF Payload Engineer",
    goal="Design antenna systems",
    backstory="20 years of antenna design experience",
)

agent = BaseAgent(identity=identity, llm=client)
response, record = agent.run("Calculate link budget for 735 km at 2 GHz")
```

### `SharedState`

:material-file-code: `src/core/state.py`

```python
from src.core.state import SharedState

state = SharedState()
state.publish("market_analysis", "...", source="Market Analyst")
state.get("market_analysis")
state.get_context_summary()  # Markdown summary of all artifacts
```

### `ExperimentConfig`

:material-file-code: `src/core/config.py`

```python
from src.core.config import ExperimentConfig

config = ExperimentConfig.from_yaml("configs/dicwo.yaml")
config.model                     # "meta-llama/llama-3.3-70b-instruct"
config.effective_judge_model     # "openai/gpt-5.2-chat"
config.effective_judge_provider  # "openrouter"
```

## Runner

### `ExperimentRunner`

:material-file-code: `src/runner/experiment.py`

```python
from src.runner.experiment import ExperimentRunner

runner = ExperimentRunner(
    config=config,
    api_keys={"openrouter": "sk-or-..."},
)

# Single run
result = runner.run()
print(result["run_dir"], result["metrics"])

# Repeated runs
result = runner.run_repeated(n=3)
print(result["averages"])
```

### Comparison

:material-file-code: `src/runner/comparison.py`

```python
from src.runner.comparison import find_runs, compare_runs, compare_group, comparison_to_markdown

# Compare all runs in a directory
runs = find_runs("results")
comparison = compare_runs(runs)
print(comparison_to_markdown(comparison))

# Compare within a grouped experiment
comparison = compare_group("results/20260219_comparison")
```

## Evaluation

### `LLMJudge`

:material-file-code: `src/evaluation/llm_judge.py`

```python
from src.evaluation.llm_judge import LLMJudge

judge = LLMJudge(llm=judge_client)
scores = judge.evaluate(artifacts)
print(scores["_aggregate"]["mean_score"])
```

### Validators

:material-file-code: `src/evaluation/validators.py`

```python
from src.evaluation.validators import validate_artifacts, fspl_db, antenna_gain_db

# Run all checks on artifacts
results = validate_artifacts(artifacts)
print(results["verified_claims_ratio"])

# Individual physics functions
fspl_db(2e9, 735e3)        # Free-space path loss in dB
antenna_gain_db(9.0, 2e9)  # Antenna gain in dBi
```

### Scoresheet

:material-file-code: `src/evaluation/scoresheet.py`

```python
from src.evaluation.scoresheet import generate_scoresheet

md = generate_scoresheet(artifacts, system_type="dicwo", experiment_name="run_1")
```

## Analysis

### Plots

:material-file-code: `src/analysis/visualizations.py`

```python
from src.analysis.visualizations import plot_comparison

saved_paths = plot_comparison("results/20260219_comparison", "results/20260219_comparison")
```

### Reports

:material-file-code: `src/analysis/metrics_report.py`

```python
from src.analysis.metrics_report import generate_metrics_report, generate_csv

report = generate_metrics_report("results")
generate_csv("results", output_path="results/comparison.csv")
```
