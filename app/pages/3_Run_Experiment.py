"""Page 3: Run Experiment — execute with live progress."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from components.sidebar import render_sidebar
from components.progress import render_progress
from utils.session import init_all_defaults, get, put, get_api_keys, has_api_key_for
from utils.runner_thread import ExperimentThread

from src.core.config import ExperimentConfig
from src.runner.experiment import ExperimentRunner
from src.domain import prompts as prompts_module
from src.domain import roles as roles_module
from src.core.agent import AgentIdentity

render_sidebar()
init_all_defaults()

st.title("Run Experiment")
st.caption(
    "Launch one or more system architectures and watch progress in real time. "
    "Results are saved automatically and can be viewed on the Results page."
)

SYSTEM_LABELS = {
    "single_agent": "Single Agent",
    "centralized": "Centralized Manager",
    "dicwo": "DiCWO (Distributed)",
}
ALL_SYSTEM_TYPES = ["single_agent", "centralized", "dicwo"]


# ── Helpers ───────────────────────────────────────────────────

def _apply_custom_prompts() -> None:
    """Monkey-patch prompt module constants with any custom values."""
    customs = get("custom_prompts", {})
    for key, value in customs.items():
        if key.startswith("TASK_"):
            task_key = key[5:]
            if task_key in prompts_module.TASK_DESCRIPTIONS:
                prompts_module.TASK_DESCRIPTIONS[task_key] = value
        elif hasattr(prompts_module, key):
            setattr(prompts_module, key, value)


def _apply_custom_roles() -> None:
    """Monkey-patch role module with any custom identities."""
    customs = get("custom_roles", {})
    for name, role_dict in customs.items():
        identity = AgentIdentity(**role_dict)
        if hasattr(roles_module, "ROLE_MAP"):
            roles_module.ROLE_MAP[name] = identity
        for i, r in enumerate(roles_module.ALL_ROLES):
            if r.name == name:
                roles_module.ALL_ROLES[i] = identity
        for i, r in enumerate(roles_module.SPECIALIST_ROLES):
            if r.name == name:
                roles_module.SPECIALIST_ROLES[i] = identity
        var_map = {
            "Study Manager": "STUDY_MANAGER",
            "Market Analyst": "MARKET_ANALYST",
            "Frequency Filing Expert": "FREQUENCY_EXPERT",
            "Payload Expert": "PAYLOAD_EXPERT",
            "Mission Analyst": "MISSION_ANALYST",
        }
        if name in var_map:
            setattr(roles_module, var_map[name], identity)


def _build_config(system_type: str) -> ExperimentConfig:
    """Build an ExperimentConfig from session state."""
    system_params = get("system_params", {}) if system_type == "dicwo" else {}

    return ExperimentConfig(
        system_type=system_type,
        provider=get("provider", "openrouter"),
        model=get("model", "meta-llama/llama-3.3-70b-instruct"),
        temperature=get("temperature", 0.7),
        max_tokens=get("max_tokens", 16384),
        max_rounds=get("max_rounds", 10),
        judge_provider=get("judge_provider", "openrouter"),
        judge_model=get("judge_model", "openai/gpt-4.1"),
        run_judge=get("run_judge", True),
        system_params=system_params,
        experiment_name=f"webapp_{system_type}",
    )


def _make_runner_factory(config: ExperimentConfig, results_dir: Path):
    """Return a factory that creates an ExperimentRunner with callback."""
    api_keys = get_api_keys()

    def factory(progress_callback):
        return ExperimentRunner(
            config=config,
            api_keys=api_keys,
            results_dir=str(results_dir),
            progress_callback=progress_callback,
        )
    return factory


def _start_run(system_types: list[str], repeat: int) -> None:
    """Start experiment run(s) in background threads."""
    put("running", True)
    put("run_error", None)
    put("progress_events", [])
    put("run_results", [])

    results_dir = _PROJECT_ROOT / "results"

    threads: list[ExperimentThread] = []
    for sys_type in system_types:
        config = _build_config(sys_type)
        factory = _make_runner_factory(config, results_dir)
        thread = ExperimentThread()
        thread.start(factory, repeat=repeat)
        threads.append(thread)

    put("run_threads", threads)
    put("run_system_types", system_types)


# ── Pre-flight checks ────────────────────────────────────────

provider = get("provider", "openrouter")
has_key = has_api_key_for(provider)

if not has_key:
    st.warning(
        f"No API key set for **{provider}**. "
        "Enter it in the sidebar (left panel) before running.",
        icon="\u26a0\ufe0f",
    )

# ── System Selection ──────────────────────────────────────────

st.subheader("Select Systems to Run")
st.caption(
    "Choose which system architectures to run. Selecting multiple runs them sequentially "
    "so you can compare results on the Results page."
)

# Current system from Configure page
configured_system = get("system_type", "single_agent")

col1, col2, col3 = st.columns(3)

with col1:
    run_single = st.checkbox(
        "Single Agent",
        value=(configured_system == "single_agent"),
        help="One LLM generates the full design in a single pass. Fast and cheap.",
        key="_run_single_agent",
    )
with col2:
    run_centralized = st.checkbox(
        "Centralized Manager",
        value=(configured_system == "centralized"),
        help="A manager routes tasks to 4 specialist agents. Medium cost.",
        key="_run_centralized",
    )
with col3:
    run_dicwo = st.checkbox(
        "DiCWO (Distributed)",
        value=(configured_system == "dicwo"),
        help="Agents bid, vote, and self-organize. Most thorough but most expensive.",
        key="_run_dicwo",
    )

selected_systems: list[str] = []
if run_single:
    selected_systems.append("single_agent")
if run_centralized:
    selected_systems.append("centralized")
if run_dicwo:
    selected_systems.append("dicwo")

if not selected_systems:
    st.warning("Select at least one system to run.", icon="\u261d\ufe0f")

# ── Run Parameters ────────────────────────────────────────────

st.divider()
st.subheader("Run Parameters")

col1, col2 = st.columns(2)
with col1:
    repeat_count = st.number_input(
        "Repeat Count",
        min_value=1,
        max_value=10,
        value=1,
        step=1,
        help=(
            "Run each selected system N times and compute averages. "
            "Useful for measuring consistency and getting statistically meaningful results. "
            "Cost multiplies by N."
        ),
        key="_repeat_count",
    )
with col2:
    st.markdown("**Current Config**")
    st.markdown(f"- Model: `{get('model', '?')}`")
    st.markdown(f"- Provider: {get('provider', '?')}")
    st.markdown(f"- Temperature: {get('temperature', 0.7)}")

# Show what will run
n_runs = len(selected_systems) * repeat_count
if selected_systems:
    labels = [SYSTEM_LABELS.get(s, s) for s in selected_systems]
    st.info(
        f"Will run **{', '.join(labels)}** "
        f"{'(' + str(repeat_count) + 'x each) ' if repeat_count > 1 else ''}"
        f"= **{n_runs} total run(s)**",
        icon="\U0001f680",
    )

# ── Run Button ────────────────────────────────────────────────

st.divider()

is_running = get("running", False)

if st.button(
    f"Run {n_runs} Experiment{'s' if n_runs != 1 else ''}",
    type="primary",
    disabled=is_running or not has_key or not selected_systems,
    use_container_width=True,
):
    _apply_custom_prompts()
    _apply_custom_roles()
    _start_run(selected_systems, repeat_count)
    st.rerun()

# ── Live Progress (auto-refreshing fragment — no full-page rerun) ─

if is_running:
    st.divider()

    @st.fragment(run_every=3)
    def _live_progress():
        """Fragment that polls threads every 3s without re-rendering the rest of the page."""
        threads: list[ExperimentThread] = get("run_threads", [])
        if not threads:
            return

        all_events: list[tuple[str, dict[str, Any]]] = list(get("progress_events", []))
        all_done = True
        results = list(get("run_results", []))

        for thread in threads:
            new_events = thread.drain_events()
            all_events.extend(new_events)

            if thread.is_running:
                all_done = False
            elif thread.done.is_set():
                if thread.result and thread.result not in results:
                    results.append(thread.result)
                if thread.error:
                    put("run_error", thread.error)

        put("progress_events", all_events)
        put("run_results", results)

        n_total = len(threads)
        render_progress(all_events, total_systems=n_total, all_done=all_done)

        if all_done:
            put("running", False)
            if get("run_error"):
                st.error("One or more runs failed. Check the activity log above for details.")
            else:
                st.balloons()
                st.info("Head to the **Results** page to view the full dashboard with charts and comparisons.")
            # One final full-page rerun to re-enable the Run button
            st.rerun(scope="app")

    _live_progress()

# ── Show last results summary ─────────────────────────────────

elif get("run_results"):
    st.divider()
    results = get("run_results", [])
    st.subheader(f"Last Run: {len(results)} Result(s)")

    for i, r in enumerate(results):
        run_dir = r.get("run_dir", "?")
        metrics = r.get("metrics", {}).get("totals", {})
        evaluation = r.get("evaluation", {})
        judge_score = evaluation.get("judge_scores", {}).get("_aggregate", {}).get("mean_score")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Run", Path(run_dir).name[:30])
        col2.metric("Tokens", f"{metrics.get('total_tokens', 0):,}")
        col3.metric("Cost", f"${metrics.get('cost_usd', 0):.4f}")
        col4.metric("Judge", f"{judge_score:.2f}" if judge_score else "N/A")

    st.info("Go to the **Results** page for detailed charts, comparisons, and downloads.")
