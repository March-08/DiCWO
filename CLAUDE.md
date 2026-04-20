# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Context

This is a **research codebase** implementing **DiCWO** (Distributed Calibration-Weighted Orchestration), a decentralized multi-agent protocol for LLM-based satellite constellation mission design. The repo compares three system architectures (single agent, centralized manager, DiCWO) on the same task and scores them with an LLM judge.

**End goal**: a paper for a Q1 journal, targeting **Expert Systems with Applications (ESWA)**. This shapes every decision in the repo:

- Experiments must be **reproducible and statistically defensible**: always prefer `--repeat ≥ 4`, report mean ± std, and run the full 8-model × 3-system benchmark (`scripts/run_multimodel.sh`) before claiming a result.
- Ablations matter: when changing a DiCWO component (bidding weights, confidence tiers, escalation ladder, spawning triggers), keep the baseline config runnable so the ablation can be shown side-by-side.
- Favor **explainable** outputs — `conversation_trace.md` and per-agent metrics are paper material, not just debug aids. Don't collapse or summarize them away.
- Figures live in `figures/` and are produced by `scripts/generate_paper_charts.py`, `scripts/generate_dicwo_diagram.py`, `scripts/generate_dimension_analysis.py`. These scripts are the canonical pipeline from `results/` → paper figure; changes to result schemas must keep these generators working.
- Terminology and claims need to match the paper. The README/docs use precise phrasing (e.g. "Distributed Calibration-Weighted Orchestration", "4-term bid", "tiered confidence gateway"). Don't casually rename concepts — it propagates into figures, docs, and eventually the manuscript.

There is no test suite — changes are validated by running experiments and inspecting the saved artifacts.

## Environment

- Python ≥ 3.11. Install with `pip install -e .` (sets up the `src/` package and the `run-experiment` entry point).
- Streamlit app has its own requirements: `pip install -r requirements-app.txt`.
- API keys live in `.env` (loaded via `python-dotenv`): at least one of `OPENAI_API_KEY` or `OPENROUTER_API_KEY` must be set. Provider is auto-detected from model names containing `/` → `openrouter`, else `openai`.

## Common Commands

```bash
# Run all 3 systems once, compare, save grouped results under results/
python3 scripts/run_all.py

# Statistical averaging (runs each system N times)
python3 scripts/run_all.py --repeat 4

# Override the model for all systems (provider auto-detected from the name)
python3 scripts/run_all.py --model openai/gpt-5.2-chat --repeat 4

# Run a single system from its YAML
python3 scripts/run_experiment.py --config configs/dicwo.yaml
python3 scripts/run_experiment.py --config configs/dicwo.yaml --no-judge --repeat 3

# Multi-model benchmark (8 models × 3 systems × N repeats, parallel)
bash scripts/run_multimodel.sh 4

# Streamlit UI
streamlit run app/app.py

# Docs site
pip install mkdocs-material
mkdocs serve        # local preview
mkdocs build        # static output in site/
```

CLI overrides available on both `run_all.py` and `run_experiment.py`: `--model`, `--provider`, `--judge-model`, `--judge-provider`, `--no-judge`, `--repeat`, `--results-dir`.

## Architecture

### The three systems share one runner, one config, one judge

`ExperimentRunner` (`src/runner/experiment.py`) is the single pipeline: `ExperimentConfig.from_yaml` → build LLM client(s) → instantiate the right `BaseSystem` subclass via `_build_system` → run → run judge → save artifacts. All three systems implement the `BaseSystem` interface (`src/systems/base_system.py`) returning a `SystemResult` with `artifacts`, `conversation_log`, and `metadata`. This is the contract to preserve when adding or modifying a system.

System selection is driven by `config.system_type` ∈ `{"single_agent", "centralized", "dicwo"}`. The string must match both the YAML field and the `src/systems/<name>/` folder.

### DiCWO iteration loop (`src/systems/dicwo/system.py`)

The distributed system is the research contribution. Its outer loop (up to `max_rounds` iterations) runs, in order:

1. **Beacon broadcasting** (`beacon.py`) — each agent emits capability beacons with calibration and evidence.
2. **Calibration-weighted bidding** (`bidding.py`) — 4-term score `α·fitness - β·calibration_cost - γ·cost + δ·diversity`; weights live in `system_params.bid_{alpha,beta,gamma,delta}`.
3. **Coalition proposals + joint consensus** (`consensus.py`) — selects `(agents, topology, protocol)` for each subtask.
4. **Execution under a protocol** — `solo | audit | debate | parallel | tool_verified` (see `PROTOCOL_DESCRIPTIONS` in `system.py`).
5. **Confidence gateway** (`confidence.py`) — tiered per-output self-assessment. **This design is load-bearing: do NOT replace with blind retry loops.** Tiers (thresholds in `system_params`):
   - score ≥ `confidence_threshold` (default 85) → `PROCEED`
   - `confidence_low_threshold` ≤ score < `confidence_threshold` → `REFLECT` (critique-then-retry, capped by `confidence_max_retries`)
   - score < `confidence_low_threshold` (default 50) → `INTERVENE` (report missing info, trigger escalation)
6. **Checkpoint evaluation** (`checkpoint.py`) — 4 signals: disagreement, uncertainty, verifiability, risk.
7. **Policy engine** (`policy.py`) — emits `continue | rewire | stop` based on checkpoint signals and `acceptance_quality`.
8. **Protocol escalation** (`escalation.py`) — ladder `solo → audit → debate → tool_verified` for failed subtasks.
9. **Agent spawning** (`agent_factory.py`) — dual trigger (coverage gap + persistent failure) to create new specialists; capped by `max_spawned_agents` with `agent_ttl_rounds`.

Default subtask list and criticality map are at the top of `system.py` (`DEFAULT_SUBTASKS`, `SUBTASK_CRITICALITY`). Agent identities are in `src/domain/roles.py`; prompts in `src/domain/prompts.py`.

### Config layering

- `configs/*.yaml` — per-system config, parsed into `ExperimentConfig` (`src/core/config.py`). Unknown keys are silently dropped by the dataclass filter in `from_yaml`.
- `domain_config:` points to a file under `configs/domain/` (e.g. `dthh_mission.yaml`) which is loaded into `config.domain`.
- `system_params:` is a free-form dict the system reads directly — DiCWO-specific tuning lives here.
- `judge_provider` / `judge_model` default to the agent's provider/model via `effective_judge_*` properties.

### LLM client, pricing, metrics

`src/core/llm_client.py` wraps the OpenAI SDK for both OpenAI and OpenRouter (any OpenAI-compatible provider works via `base_url`). Cost estimation uses the `_PRICING` table (per 1M input/output tokens) — when adding a model, add an entry there or cost will be reported as zero. OpenRouter returns actual cost via the `x-openrouter-cost` header and is preferred when present. All calls are recorded in `MetricsCollector` (`src/core/metrics.py`) and summarized into `metrics.json`.

### Results layout

A run produces a group directory `results/<timestamp>_<modeltag>_comparison/` with:

- `comparison.md` / `comparison.json` / `comparison.csv` — side-by-side table from `src/runner/comparison.py`
- Per-system subfolder `<system>/`:
  - `averages.json` + `summary.md` — aggregated stats across repeats
  - `mission_report_best.md` — pick of the best run (when reflection selected one)
  - `run_N/` for each repeat, containing: `mission_report.md`, `report.md`, `conversation_trace.md` (human-readable transcript), `conversation_log.json` (structured turns), `metrics.json` (tokens/cost/latency, per-agent breakdown, full `call_log`), `evaluation.json` (judge scores per rubric dimension), `artifacts.json`, `metadata.json`

The comparison step also calls `src/analysis/visualizations.plot_comparison` to emit PNG charts; failure there is caught and does not fail the run.

**Known data quirk**: `comparison.md` / `comparison.json` shows `model: "unknown"` for every row. The per-run `metrics.json` and `metadata.json` have the real model name — `comparison.py` just isn't reading it. Don't "fix" it blindly by inventing a source; check where the field is populated first.

### Canonical benchmark

The project's headline evaluation is the 8-model × 3-system × 4-repeat suite in `scripts/run_multimodel.sh` (`REPEAT=4`, judge = `openai/gpt-5.2-chat`). Latest group (2026-03-23) is under `results/20260323_172838_*_comparison/`. Reference points from that run:

- DiCWO produced the top judge score across all 8 models, but the lift over single_agent ranges from **+0.39** (claude-sonnet-4.6) to **+1.41** (z-ai/glm-4.7).
- Best absolute: gpt-5.2-chat DiCWO = **4.28 ± 0.04** (std also ~10× lower than its single_agent baseline).
- **Cost envelope matters**: DiCWO uses 100–1000× more tokens than single_agent. Per-run cost spans $0.06 (llama-3.3-70b) → $23 (claude-sonnet-4.6). Latency spans 166 s → 6288 s. Any DiCWO change that multiplies LLM calls needs to be justified against this existing overhead — strong base models already show diminishing returns.
- Token distribution skews heavily to **Study Manager** and **Market Analyst** (often >50% of spend) because they drive coordination. Profiling a DiCWO change should inspect `metrics.json.per_agent`, not just the `totals`.

## Working With This Codebase

- When adding a new model, update `_PRICING` in `src/core/llm_client.py` so cost tracking works.
- When changing DiCWO behavior, thread new parameters through `system_params` rather than adding constructor args — that keeps configs as the single source of truth.
- The three systems run **in parallel** in `run_all.py` (`ThreadPoolExecutor`, one worker per system), and repeats within a system can also run in parallel inside `ExperimentRunner.run_repeated`. Avoid shared mutable state in any system implementation.
- The `scripts/` folder contains run entry points AND ad-hoc figure/analysis generators (`generate_paper_charts.py`, `generate_dicwo_diagram.py`, `generate_dimension_analysis.py`, `rejudge_single_agent.py`). These read from `results/` — keep them as read-only consumers.
- Notebooks under `notebooks/` are for result analysis, not the main workflow.
- `main-crewAI-ollama-CDF-CXS-5_RAG.py` at repo root is legacy CrewAI code kept for reference; the current system does not depend on CrewAI.

## Reference

Full docs: https://dicwo-docs.vercel.app (source under `docs/`, config in `mkdocs.yml`). `docs/systems/dicwo.md` is the canonical description of the DiCWO pipeline — consult it before restructuring the loop.
