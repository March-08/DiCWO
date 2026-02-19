"""Progress bar and streaming log component for experiment runs."""

from __future__ import annotations

from typing import Any

import streamlit as st


def render_progress(events: list[tuple[str, dict[str, Any]]]) -> None:
    """Render a live progress display from accumulated events.

    Called on each rerun with the full list of events collected so far.
    """
    if not events:
        return

    # Aggregate metrics from events
    total_calls = 0
    total_tokens = 0
    total_cost = 0.0
    systems_started = 0
    systems_completed = 0
    judge_running = False
    is_complete = False
    has_error = False
    error_msg = ""
    log_lines: list[str] = []

    for event_type, data in events:
        if event_type == "llm_call":
            total_calls += 1
            total_tokens += data.get("tokens", 0)
            total_cost += data.get("cost", 0.0)
            agent = data.get("agent", "unknown")
            log_lines.append(
                f"**{agent}** \u2014 {data.get('tokens', 0):,} tokens, "
                f"${data.get('cost', 0):.4f}, {data.get('latency', 0):.1f}s"
            )
        elif event_type == "system_start":
            systems_started += 1
            sys_type = data.get("system_type", "?")
            model = data.get("model", "?")
            log_lines.append(f"Started **{sys_type}** with {model}")
        elif event_type == "system_complete":
            systems_completed += 1
            log_lines.append(
                f"System complete \u2014 {data.get('num_calls', 0)} calls, "
                f"${data.get('cost', 0):.4f}"
            )
        elif event_type == "judge_start":
            judge_running = True
            log_lines.append(f"Judge evaluation started ({data.get('model', '?')})")
        elif event_type == "complete":
            is_complete = True
            log_lines.append("Run complete!")
        elif event_type == "error":
            has_error = True
            error_msg = data.get("traceback", "Unknown error")
        elif event_type == "finished":
            is_complete = True

    # Metric cards
    col1, col2, col3 = st.columns(3)
    col1.metric("LLM Calls", total_calls)
    col2.metric("Total Tokens", f"{total_tokens:,}")
    col3.metric("Cost", f"${total_cost:.4f}")

    # Progress indication
    if has_error:
        st.error(f"Run failed:\n```\n{error_msg}\n```")
    elif is_complete:
        st.success("Experiment completed!")
    elif judge_running:
        st.info("Running judge evaluation...")
    elif systems_started > 0:
        st.info(f"Running system {systems_completed + 1} of {systems_started}...")

    # Activity log
    if log_lines:
        with st.expander("Activity Log", expanded=not is_complete):
            for line in reversed(log_lines[-50:]):
                st.markdown(f"- {line}")
