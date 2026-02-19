"""Progress bar and streaming log component for experiment runs."""

from __future__ import annotations

from typing import Any

import streamlit as st


def render_progress(
    events: list[tuple[str, dict[str, Any]]],
    total_systems: int = 1,
    all_done: bool = False,
) -> None:
    """Render a live progress display from accumulated events.

    Called on each rerun with the full list of events collected so far.

    Args:
        events: All progress events accumulated across all threads.
        total_systems: Total number of system runs expected.
        all_done: Whether all threads have finished (set by the caller).
    """
    if not events:
        return

    # Aggregate metrics from events
    total_calls = 0
    total_tokens = 0
    total_cost = 0.0
    systems_started = 0
    systems_completed = 0
    runs_finished = 0
    judge_running = False
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
            runs_finished += 1
            log_lines.append("Run complete!")
        elif event_type == "error":
            has_error = True
            error_msg = data.get("traceback", "Unknown error")
        elif event_type == "finished":
            runs_finished += 1

    # Metric cards
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("LLM Calls", total_calls)
    col2.metric("Total Tokens", f"{total_tokens:,}")
    col3.metric("Cost", f"${total_cost:.4f}")
    col4.metric("Progress", f"{min(runs_finished, total_systems)}/{total_systems}")

    # Progress bar
    progress_frac = min(runs_finished, total_systems) / max(total_systems, 1)
    if not all_done:
        # Show partial progress between finished runs
        partial = 0.5 / max(total_systems, 1)  # half-step for in-progress run
        progress_frac = min(progress_frac + partial, 0.99)
    st.progress(min(progress_frac, 1.0))

    # Progress indication
    if has_error:
        st.error(f"Run failed:\n```\n{error_msg}\n```")
    elif all_done:
        st.success(f"All {total_systems} experiment(s) completed!")
    elif runs_finished > 0 and runs_finished < total_systems:
        st.info(f"Completed {runs_finished}/{total_systems} runs. Next run in progress...")
    elif judge_running:
        st.info("Running judge evaluation...")
    elif systems_started > 0:
        st.info(f"Running system {systems_completed + 1}...")

    # Activity log
    if log_lines:
        with st.expander("Activity Log", expanded=not all_done):
            for line in reversed(log_lines[-50:]):
                st.markdown(f"- {line}")
