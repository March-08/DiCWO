# Quick Start

## Run all three systems

```bash
python3 scripts/run_all.py
```

This runs Single Agent → Centralized → DiCWO sequentially, evaluates each, and produces a comparison table. Results are grouped under `results/<timestamp>_comparison/`.

## Run with repetitions

```bash
python3 scripts/run_all.py --repeat 3
```

Each system runs 3 times. Averages and standard deviations are computed automatically.

## Run a single system

```bash
python3 scripts/run_experiment.py -c configs/single_agent.yaml
python3 scripts/run_experiment.py -c configs/centralized_manager.yaml
python3 scripts/run_experiment.py -c configs/dicwo.yaml
```

## Skip evaluation (faster)

```bash
python3 scripts/run_all.py --no-judge              # skip LLM judge
```

## Check results

After a run completes, open the results folder:

```
results/<timestamp>_comparison/
  comparison.md               ← side-by-side table
  single_agent/
    mission_report.md         ← the actual design output
  centralized/
    mission_report.md
  dicwo/
    mission_report.md
```

!!! info "Mission reports"
    `mission_report.md` is the readable design document produced by each system. For multi-agent systems it assembles all specialist outputs into structured sections.

## CLI Reference

### `run_all.py`

| Flag | Description |
|------|-------------|
| `--repeat N`, `-n N` | Run each system N times, compute averages |
| `--no-judge` | Skip LLM-as-a-Judge evaluation |
| `--results-dir DIR` | Output directory (default: `results/`) |

### `run_experiment.py`

| Flag | Description |
|------|-------------|
| `--config PATH`, `-c` | Path to YAML config (required) |
| `--repeat N`, `-n N` | Run N times, compute averages |
| `--no-judge` | Skip LLM judge |
| `--results-dir DIR`, `-o` | Output directory |

## Jupyter Notebooks

Three notebooks in `notebooks/`:

| Notebook | Purpose |
|----------|---------|
| `01_run_experiments.ipynb` | Run each system interactively |
| `02_analyze_results.ipynb` | Inspect individual run results |
| `03_compare_systems.ipynb` | Comparison tables and plots |
