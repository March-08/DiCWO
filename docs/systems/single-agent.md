# System 1: Single Agent

The simplest baseline — one LLM call with a monolithic prompt.

## How It Works

A single prompt combines all five specialist perspectives (market analysis, frequency planning, payload design, mission analysis, integration). The model must produce a complete mission design in one shot.

```mermaid
graph LR
    P[Monolithic prompt] --> LLM --> R[Complete design]
```

- **1 LLM call**, **1 artifact** (`complete_design`)
- No iteration, no specialization, no quality control
- Cheapest and fastest baseline
- Expected to produce lower quality due to lack of focused expertise

## Prompt Design

The system prompt instructs the LLM to cover all five areas with quantitative data, tables, and structured sections. The user prompt describes the specific mission (LEO DTHH constellation for unmodified smartphones).

See `src/domain/prompts.py` for the full prompt text (`SINGLE_AGENT_SYSTEM_PROMPT`, `SINGLE_AGENT_USER_PROMPT`).

## Implementation

:material-file-code: `src/systems/single_agent/system.py`

```python
class SingleAgentSystem(BaseSystem):
    def run(self) -> SystemResult:
        messages = build_messages()  # system + user prompt
        response, record = self.llm.chat(messages, agent_name="single_agent")
        self.state.publish("complete_design", response)
        return SystemResult(artifacts=self.state.artifacts, ...)
```

## When to Use

- As a **lower-bound baseline** for comparison
- To establish the minimum cost/latency for a given model
- To test that the evaluation pipeline works before running multi-agent systems
