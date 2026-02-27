# Configuration

Experiments are driven by YAML files in `configs/`. Each file specifies the system type, model, provider, and evaluation settings.

## YAML Reference

```yaml title="configs/single_agent.yaml"
# ── Required ──
system_type: single_agent        # single_agent | centralized | dicwo

# ── LLM for agents ──
provider: openrouter             # openai | openrouter
model: meta-llama/llama-3.3-70b-instruct
temperature: 0.7

# ── LLM for judge (defaults to same as agents if omitted) ──
judge_provider: openrouter
judge_model: openai/gpt-5.2-chat

# ── Experiment ──
experiment_name: my_experiment
description: "Free-text description"
max_rounds: 10                   # max orchestration rounds (multi-agent only)

# ── Evaluation ──
run_judge: true

# ── Domain ──
domain_config: domain/dthh_mission.yaml
```

## Providers

| Provider | Base URL | Env Var |
|----------|----------|---------|
| `openai` | `https://api.openai.com/v1` | `OPENAI_API_KEY` |
| `openrouter` | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |

For custom providers, set `base_url` explicitly in the YAML and create a matching env var.

## Model Selection

Agents and judge can use different providers and models:

=== "Cheap agents + strong judge"

    ```yaml
    provider: openrouter
    model: meta-llama/llama-3.3-70b-instruct
    judge_provider: openrouter
    judge_model: openai/gpt-5.2-chat
    ```

=== "All OpenAI"

    ```yaml
    provider: openai
    model: gpt-4o-mini
    judge_provider: openai
    judge_model: gpt-4o
    ```

=== "Free testing"

    ```yaml
    provider: openrouter
    model: meta-llama/llama-3.3-70b-instruct:free
    judge_provider: openrouter
    judge_model: meta-llama/llama-3.3-70b-instruct:free
    ```

### Recommended Models

| Use case | Model | Cost (per 1M tokens) |
|----------|-------|------|
| Free testing | `meta-llama/llama-3.3-70b-instruct:free` | Free |
| Cheap agents | `deepseek/deepseek-chat-v3-0324` | $0.14 / $0.28 |
| Cheap agents | `qwen/qwen3-30b-a3b` | $0.05 / $0.15 |
| Strong judge | `openai/gpt-5.2-chat` | via OpenRouter |
| Strong judge | `anthropic/claude-sonnet-4` | $3.00 / $15.00 |

## DiCWO Parameters

The DiCWO system accepts additional parameters under `system_params`:

```yaml title="configs/dicwo.yaml"
system_params:
  calibration_decay: 0.9       # Score multiplier on failure
  diversity_bonus: 0.1         # Weight for less-used agents
  consensus_threshold: 0.7     # Agreement ratio for consensus
  min_voters: 3                # Minimum agents in votes
  disagreement_threshold: 0.3  # Triggers topology rewire
  uncertainty_threshold: 0.5   # Triggers topology rewire
  risk_threshold: 0.6          # Combined risk threshold
  acceptance_quality: 0.7      # Min quality for early stop
  max_spawned_agents: 2        # Max dynamically created agents
  agent_ttl_rounds: 5          # Spawned agents expire after N rounds
  protocols:                   # Available execution protocols
    - solo
    - audit
    - debate
    - parallel
```

| Parameter | Default | Effect |
|-----------|---------|--------|
| `calibration_decay` | 0.9 | Lower = harsher penalty for failed tasks |
| `diversity_bonus` | 0.1 | Higher = more rotation across agents |
| `consensus_threshold` | 0.7 | Lower = easier agreement |
| `disagreement_threshold` | 0.3 | Higher = less frequent topology rewires |
| `uncertainty_threshold` | 0.5 | Higher = less frequent topology rewires |
| `risk_threshold` | 0.6 | Lower = more frequent interventions |
| `acceptance_quality` | 0.7 | Higher = stricter early-stop criterion |
