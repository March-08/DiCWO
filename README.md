---
title: DiCWO Mission Design
emoji: "\U0001f6f0\ufe0f"
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

# DiCWO — Multi-Agent Satellite Mission Design

A research framework for comparing LLM multi-agent system architectures on a satellite constellation design task. Built from scratch with the OpenAI SDK.

The core contribution is **DiCWO** (Distributed Calibration-Weighted Orchestration), a fully decentralized multi-agent protocol where specialist agents self-organize through beacon broadcasting, calibration-weighted bidding, consensus-based coalition formation, and iterative checkpoint evaluation — with no central controller.

## System Architectures

| System | Architecture | Agents | Description |
|--------|-------------|--------|-------------|
| **Single Agent** | Monolithic | 1 LLM call | All roles combined in one prompt |
| **Centralized** | Hierarchical | Manager + 4 specialists | Manager routes subtasks to specialists |
| **DiCWO** | Distributed | Peer-to-peer specialists | Beacon-bid-consensus-checkpoint loop |

## DiCWO Pipeline

The DiCWO system implements a full iteration-level loop:

1. **Beacon Broadcasting** — Agents emit capability beacons with calibration scores and evidence
2. **Calibration-Weighted Bidding** — 4-term scoring: fitness, calibration, cost, diversity
3. **Coalition Formation** — Agents propose coalitions; joint consensus selects (team, topology, protocol)
4. **Confidence Gateway** — Tiered self-assessment before outputs reach checkpoint:
   - **>= 85%**: Proceed (output accepted)
   - **50-85%**: Reflective rerun (agent critiques its own response, then retries)
   - **< 50%**: Intervention (agent reports missing info; triggers protocol escalation)
5. **Checkpoint Evaluation** — 4-signal quality assessment (disagreement, uncertainty, verifiability, risk)
6. **Policy Engine** — Continue / Rewire / Stop decisions based on checkpoint signals
7. **Protocol Escalation** — Failed subtasks escalate: solo -> audit -> debate -> tool_verified
8. **Agent Spawning** — Dual trigger (coverage gaps + persistent failures) creates new specialists

## Quick Start

```bash
pip install -e .
cp .env.example .env              # add OPENAI_API_KEY and/or OPENROUTER_API_KEY
python3 scripts/run_all.py        # run all 3 systems, compare results
```

Run with repetitions for statistical averaging:

```bash
python3 scripts/run_all.py --repeat 3
```

Override models via CLI:

```bash
python3 scripts/run_all.py --model openai/gpt-4o --provider openrouter
```

## Output

Results are saved to `results/<timestamp>_comparison/` with:

- `mission_report.md` — the technical design output
- `conversation_trace.md` — human-readable transcript of all agent interactions, task delegation, and decision-making
- `metrics.json` — token usage, latency, cost, confidence gateway stats
- `evaluation.json` — judge scores across quality dimensions
- `comparison.csv` — side-by-side system comparison

## Configuration

Edit the YAML files in `configs/` to change models, providers, and system parameters:

```yaml
provider: openrouter
model: meta-llama/llama-3.3-70b-instruct
judge_provider: openrouter
judge_model: openai/gpt-5.2-chat

system_params:
  # Confidence gateway (tiered: proceed >= 85, reflect 50-85, intervene < 50)
  confidence_threshold: 85
  confidence_low_threshold: 50
  confidence_max_retries: 2
```

## Documentation

Full documentation: **[dicwo-docs.vercel.app](https://dicwo-docs.vercel.app)**

To serve locally:

```bash
pip install mkdocs-material
mkdocs serve
```

## Project Structure

```
src/
  core/           # Agent base class, LLM client, metrics
  domain/         # Mission-specific prompts, roles, validators
  systems/
    single/       # Single-agent baseline
    centralized/  # Hierarchical manager-worker system
    dicwo/        # Distributed system (the main contribution)
      beacon.py       # Capability broadcasting
      bidding.py      # Calibration-weighted bid computation
      consensus.py    # Joint consensus selection
      confidence.py   # Tiered confidence gateway (proceed/reflect/intervene)
      escalation.py   # Protocol escalation ladder
      checkpoint.py   # 4-signal quality evaluation
      policy.py       # Continue/Rewire/Stop decisions
      system.py       # Main orchestration loop
configs/          # YAML experiment configs
scripts/          # CLI entry points
app/              # Streamlit web interface
```
