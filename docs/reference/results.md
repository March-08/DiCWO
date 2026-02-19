# Results Format

## Folder Structures

=== "Single run"

    ```
    results/
      20260219_143000_single_agent_gpt-4o/
        mission_report.md         # Readable design output
        report.md                 # Metrics summary
        metadata.json             # Config snapshot
        metrics.json              # Tokens, costs, latencies
        artifacts.json            # Raw agent outputs
        conversation_log.json     # Full message trace
        evaluation.json           # Judge scores
    ```

=== "Grouped run (run_all)"

    ```
    results/
      20260219_143000_comparison/
        comparison.md             # Side-by-side table
        comparison.json           # Structured comparison data
        *.png                     # Plots
        single_agent/
          mission_report.md
          report.md
          metrics.json
          ...
        centralized/
          ...
        dicwo/
          ...
    ```

=== "Repeated run (--repeat N)"

    ```
    results/
      20260219_143000_comparison/
        comparison.md
        dicwo/
          averages.json           # Mean ± std
          summary.md              # Per-run table
          mission_report_best.md  # Best run promoted
          run_1/
            mission_report.md
            metrics.json
            ...
          run_2/
            ...
          run_3/
            ...
    ```

## File Reference

### `mission_report.md`

The primary output — a human-readable design document. For single-agent this is the full LLM response. For multi-agent systems it assembles specialist outputs into sections: Market Analysis, Frequency Filing, Payload Design, Mission Analysis, Integrated Mission Concept.

### `metadata.json`

```json
{
  "timestamp": "20260219_143000",
  "system_type": "dicwo",
  "model": "meta-llama/llama-3.3-70b-instruct",
  "config": { "..." },
  "python_version": "3.12.0",
  "platform": "macOS-15.0-arm64",
  "rounds_used": 8,
  "completed_subtasks": ["market_analysis", "frequency_filing", "..."]
}
```

### `metrics.json`

```json
{
  "totals": {
    "num_calls": 12,
    "total_tokens": 45230,
    "prompt_tokens": 28100,
    "completion_tokens": 17130,
    "cost_usd": 0.0234,
    "latency_s": 45.2
  },
  "per_agent": {
    "Market Analyst": { "num_calls": 2, "total_tokens": 8500, "..." },
    "Payload Expert": { "num_calls": 3, "total_tokens": 12400, "..." }
  },
  "call_log": ["..."]
}
```

### `artifacts.json`

Raw agent outputs keyed by artifact name (`market_analysis`, `payload_design`, etc.). Machine-readable version of the mission report.

### `conversation_log.json`

Full message trace with timestamps, agent names, roles, and per-call metadata (tokens, cost, latency). Useful for debugging orchestration.

### `evaluation.json`

Judge scores and evaluation results. See [LLM Judge](../evaluation/judge.md) for the schema.

### `averages.json`

Only present with `--repeat N`. Contains mean and standard deviation across runs:

```json
{
  "num_runs": 3,
  "total_tokens": 44500.0,
  "cost_usd": 0.0228,
  "latency_s": 43.8,
  "judge_mean_score": 3.72,
  "judge_std": 0.15,
  "judge_all": [3.6, 3.8, 3.75]
}
```
