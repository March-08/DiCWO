---
title: DiCWO Mission Design
emoji: "\U0001f6f0\ufe0f"
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

# DiCWO — Multi-Agent Satellite Mission Design

A framework for comparing three LLM system architectures on a satellite constellation design task. Built from scratch with the OpenAI SDK.

| System | Architecture | Agents |
|--------|-------------|--------|
| **Single Agent** | Monolithic | 1 LLM call, all roles combined |
| **Centralized** | Hierarchical | Manager routes to 4 specialists |
| **DiCWO** | Distributed | Beacon-bid-consensus-checkpoint loop |

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

Results are saved to `results/<timestamp>_comparison/` with mission reports, metrics, evaluation scores, and comparison tables.

## Configuration

Edit the YAML files in `configs/` to change models and providers:

```yaml
provider: openrouter
model: meta-llama/llama-3.3-70b-instruct
judge_provider: openrouter
judge_model: openai/gpt-5.2-chat
```

## Documentation

Full documentation: **[dicwo-docs.vercel.app](https://dicwo-docs.vercel.app)**

To serve locally:

```bash
pip install mkdocs-material
mkdocs serve
```
