# DiCWO

**Distributed Calibration-Weighted Orchestration for Satellite Mission Design**

A framework for comparing three LLM multi-agent architectures on a real-world engineering task: designing a LEO satellite constellation for direct-to-handheld (DTHH) communications.

---

## What is this?

This project implements and benchmarks three system designs of increasing complexity:

<div class="grid cards" markdown>

-   :material-robot-outline:{ .lg .middle } **Single Agent**

    ---

    One LLM call with a monolithic prompt combining all specialist roles. The lower-bound baseline.

-   :material-sitemap:{ .lg .middle } **Centralized Manager**

    ---

    A Study Manager routes tasks to 4 domain specialists, collects outputs, and integrates. Mirrors traditional hierarchical MAS.

-   :material-graph-outline:{ .lg .middle } **DiCWO**

    ---

    Agents self-organize through beacons, calibration-weighted bidding, distributed consensus, and adaptive policy decisions.

</div>

## Key Features

- **No frameworks** — built from scratch with the `openai` SDK for full transparency and control.
- **Provider-agnostic** — works with OpenAI, OpenRouter, or any OpenAI-compatible API. Agents and judge can use different models.
- **Two-layer evaluation** — LLM-as-a-Judge with rubrics and auto-generated human scoresheets.
- **Statistical runs** — repeat experiments N times and get mean ± std for all metrics.
- **Organized results** — every run produces mission reports, metrics, conversation logs, and evaluation scores in a structured folder.

## Quick Start

```bash
pip install -e .
cp .env.example .env              # add your API key(s)
python3 scripts/run_all.py        # run all 3 systems, compare
```

See the [Installation](getting-started/installation.md) and [Quick Start](getting-started/quickstart.md) guides for details.

## Project Structure

```
src/
  core/           # LLM client, agent, shared state, metrics, config
  domain/         # Satellite mission roles, prompts, reference data
  systems/
    single_agent/ # System 1
    centralized/  # System 2
    dicwo/        # System 3
  evaluation/     # Judge, rubrics, scoresheets
  runner/         # Experiment runner, comparison
  analysis/       # Reports, plots
configs/          # YAML experiment configs
scripts/          # CLI entry points
notebooks/        # Jupyter notebooks for interactive analysis
```
