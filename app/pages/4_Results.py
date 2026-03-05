"""Page 4: Results Dashboard — view, compare, and download experiment outputs."""

from __future__ import annotations

import io
import json
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from components.sidebar import render_sidebar
from utils.session import init_all_defaults, get

from src.runner.comparison import (
    load_run,
    find_groups,
    find_system_dirs,
    compare_group,
    comparison_to_markdown,
)

render_sidebar()
init_all_defaults()

st.title("Results Dashboard")
st.caption(
    "Explore experiment results: metrics, judge evaluations, mission reports, "
    "and cross-system comparisons with interactive charts."
)

RESULTS_DIR = _PROJECT_ROOT / "results"


# ── Discover all results ──────────────────────────────────────

def _find_all_leaf_runs(results_dir: Path) -> list[Path]:
    """Recursively find every directory that contains metadata.json."""
    if not results_dir.exists():
        return []
    leaves: list[Path] = []
    for meta in sorted(results_dir.rglob("metadata.json")):
        leaves.append(meta.parent)
    return leaves


def _run_label(run_dir: Path) -> str:
    """Human-readable label for a leaf run, showing its path relative to results/."""
    rel = run_dir.relative_to(RESULTS_DIR)
    parts = rel.parts
    # Load metadata for system type
    meta_path = run_dir / "metadata.json"
    system_type = "?"
    model = ""
    if meta_path.exists():
        try:
            with open(meta_path) as f:
                meta = json.load(f)
            system_type = meta.get("system_type", "?")
            model = meta.get("model", "")
        except Exception:
            pass
    # Short model name
    short_model = model.split("/")[-1] if "/" in model else model
    return f"{system_type} — {short_model}  ({'/'.join(parts)})"


leaf_runs = _find_all_leaf_runs(RESULTS_DIR)
groups = find_groups(RESULTS_DIR)

if not leaf_runs:
    st.info(
        "No experiment results found yet. Go to the **Run Experiment** page to start one!",
        icon="\U0001f4ad",
    )
    st.stop()

# ── Build selector ────────────────────────────────────────────

# Section 1: comparison groups (for cross-system view)
# Section 2: individual leaf runs
selectable_runs: dict[str, Path] = {}
for r in reversed(leaf_runs):
    selectable_runs[_run_label(r)] = r

selectable_groups: dict[str, Path] = {}
for g in reversed(groups):
    sys_dirs = find_system_dirs(g)
    if len(sys_dirs) >= 2:
        systems_str = ", ".join(sys_dirs.keys())
        selectable_groups[f"{g.name}  ({systems_str})"] = g

# Mode toggle — always show compare option if there are at least 2 runs
view_options = ["Single Run"]
if selectable_groups:
    view_options.append("Compare Systems (Group)")
if len(leaf_runs) >= 2:
    view_options.append("Compare Selected Runs")

if len(view_options) > 1:
    view_mode = st.radio(
        "View mode",
        view_options,
        horizontal=True,
        help=(
            "**Single Run**: detailed view of one run. "
            "**Compare Systems (Group)**: side-by-side charts for a pre-grouped experiment. "
            "**Compare Selected Runs**: pick any runs to compare."
        ),
        key="_view_mode",
    )
else:
    view_mode = "Single Run"


# ── Helper: render comparison charts ──────────────────────────

def _render_comparison_charts(comp_runs: list[dict[str, Any]]) -> None:
    """Render comparison table and charts from a list of comparison row dicts."""

    comp_rows = []
    for r in comp_runs:
        comp_rows.append({
            "System": r.get("system_type", "?"),
            "Model": r.get("model", "?"),
            "Runs": r.get("num_runs", 1),
            "Calls": r.get("num_calls", 0),
            "Tokens": r.get("total_tokens", 0),
            "Cost ($)": r.get("cost_usd", 0),
            "Latency (s)": r.get("latency_s", 0),
            "Judge Score": r.get("judge_mean_score"),
        })

    df_comp = pd.DataFrame(comp_rows)
    st.dataframe(
        df_comp.style.format({
            "Cost ($)": "${:.4f}",
            "Latency (s)": "{:.1f}",
            "Tokens": "{:,.0f}",
            "Calls": "{:.0f}",
            "Judge Score": lambda x: f"{x:.2f}" if x is not None else "N/A",
        }),
        use_container_width=True,
        hide_index=True,
    )

    systems = df_comp["System"].tolist()
    palette = ["#4da6ff", "#ff6b6b", "#51cf66", "#ffa94d", "#cc5de8"]
    colors = palette[: len(systems)]

    fig, axes = plt.subplots(1, 3, figsize=(14, 4))

    axes[0].bar(systems, df_comp["Tokens"], color=colors)
    axes[0].set_title("Total Tokens")
    axes[0].set_ylabel("Tokens")
    for i, v in enumerate(df_comp["Tokens"]):
        axes[0].text(i, v, f"{v:,.0f}", ha="center", va="bottom", fontsize=8)

    axes[1].bar(systems, df_comp["Cost ($)"], color=colors)
    axes[1].set_title("Total Cost ($)")
    axes[1].set_ylabel("USD")
    for i, v in enumerate(df_comp["Cost ($)"]):
        axes[1].text(i, v, f"${v:.4f}", ha="center", va="bottom", fontsize=8)

    judge_vals = [s if s is not None else 0 for s in df_comp["Judge Score"]]
    has_judge = any(s is not None for s in df_comp["Judge Score"].tolist())
    if has_judge:
        axes[2].bar(systems, judge_vals, color=colors)
        axes[2].set_title("Judge Score")
        axes[2].set_ylabel("Score")
        for i, v in enumerate(judge_vals):
            if df_comp["Judge Score"].iloc[i] is not None:
                axes[2].text(i, v, f"{v:.2f}", ha="center", va="bottom", fontsize=8)
    else:
        axes[2].text(0.5, 0.5, "No judge scores", ha="center", va="center",
                     transform=axes[2].transAxes, fontsize=12, color="gray")
        axes[2].set_title("Judge Score")

    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, max(2, len(systems) * 0.8)))
    ax.barh(systems, df_comp["Latency (s)"], color=colors)
    ax.set_xlabel("Seconds")
    ax.set_title("Total Latency Comparison")
    for i, v in enumerate(df_comp["Latency (s)"]):
        ax.text(v, i, f" {v:.1f}s", va="center", fontsize=9)
    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


# ── SINGLE RUN VIEW ──────────────────────────────────────────

if view_mode == "Single Run":
    selected_label = st.selectbox(
        "Select a run",
        options=list(selectable_runs.keys()),
        index=0,
        key="_run_selector",
    )
    if not selected_label:
        st.stop()

    selected_path = selectable_runs[selected_label]
    data = load_run(selected_path)

    if not data:
        st.error(f"Could not load data from `{selected_path}`")
        st.stop()

    # ── Overview Metrics ──────────────────────────────────────

    st.divider()
    st.subheader("Overview Metrics")

    metrics_data: dict[str, Any] = data.get("metrics", {})
    totals = metrics_data.get("totals", {})
    averages = data.get("averages", {})

    # For averaged runs, totals live directly in averages
    if not totals and averages:
        totals = averages

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "LLM Calls",
        f"{totals.get('num_calls', 0):.0f}",
        help="Total number of LLM API calls made during this run.",
    )
    col2.metric(
        "Total Tokens",
        f"{totals.get('total_tokens', 0):,.0f}",
        help="Total input + output tokens consumed. 1 token ~ 0.75 words.",
    )
    col3.metric(
        "Cost",
        f"${totals.get('cost_usd', 0):.4f}",
        help="Estimated cost based on model pricing.",
    )
    col4.metric(
        "Latency",
        f"{totals.get('latency_s', 0):.1f}s",
        help="Total wall-clock time spent on LLM calls (excludes local processing).",
    )

    # ── Per-Agent Breakdown with Charts ───────────────────────

    per_agent = metrics_data.get("per_agent", {})
    if per_agent:
        st.divider()
        st.subheader("Per-Agent Breakdown")
        st.caption("How work was distributed across agents in this run.")

        rows = []
        for agent_name, stats in per_agent.items():
            rows.append({
                "Agent": agent_name,
                "Calls": stats.get("num_calls", 0),
                "Tokens": stats.get("total_tokens", 0),
                "Cost ($)": stats.get("cost_usd", 0),
                "Latency (s)": stats.get("latency_s", 0),
            })

        if rows:
            df_agents = pd.DataFrame(rows)
            st.dataframe(
                df_agents.style.format({
                    "Cost ($)": "${:.4f}",
                    "Latency (s)": "{:.1f}",
                    "Tokens": "{:,.0f}",
                }),
                use_container_width=True,
                hide_index=True,
            )

            col1, col2 = st.columns(2)
            with col1:
                fig, ax = plt.subplots(figsize=(5, 3))
                ax.barh(df_agents["Agent"], df_agents["Tokens"], color="#4da6ff")
                ax.set_xlabel("Tokens")
                ax.set_title("Token Usage by Agent")
                plt.tight_layout()
                st.pyplot(fig)
                plt.close(fig)

            with col2:
                fig, ax = plt.subplots(figsize=(5, 3))
                costs = df_agents["Cost ($)"]
                if costs.sum() > 0:
                    colors = plt.cm.Set2(range(len(df_agents)))
                    ax.pie(costs, labels=df_agents["Agent"], autopct="%1.1f%%", colors=colors)
                    ax.set_title("Cost Distribution")
                else:
                    ax.text(0.5, 0.5, "All free models", ha="center", va="center",
                            transform=ax.transAxes, fontsize=12, color="gray")
                    ax.set_title("Cost Distribution")
                plt.tight_layout()
                st.pyplot(fig)
                plt.close(fig)

    # ── Judge Evaluation ──────────────────────────────────────

    evaluation = data.get("evaluation", {})
    judge_scores = evaluation.get("judge_scores", {})

    if judge_scores or averages.get("judge_mean_score"):
        st.divider()
        st.subheader("Judge Evaluation")
        st.caption("Quality scores assigned by the LLM judge on a per-section rubric.")

        if averages.get("judge_mean_score") is not None:
            col1, col2 = st.columns(2)
            col1.metric(
                "Mean Judge Score (averaged runs)",
                f"{averages['judge_mean_score']:.2f}"
                + (f" \u00b1 {averages.get('judge_std', 0):.2f}" if averages.get("judge_std") else ""),
            )
            if averages.get("judge_all"):
                col2.metric("Scores per run", str(averages["judge_all"]))

        if judge_scores:
            aggregate = judge_scores.get("_aggregate", {})
            if aggregate and not averages.get("judge_mean_score"):
                st.metric("Aggregate Score", f"{aggregate.get('mean_score', 0):.2f}")

            artifact_scores = {
                k: v for k, v in judge_scores.items()
                if k != "_aggregate" and isinstance(v, dict)
            }
            if artifact_scores:
                score_names = []
                score_vals = []
                for name, sdata in artifact_scores.items():
                    s = sdata.get("score", sdata.get("overall_score"))
                    if s is not None:
                        try:
                            score_names.append(name.replace("_", " ").title())
                            score_vals.append(float(s))
                        except (ValueError, TypeError):
                            pass

                if score_names:
                    fig, ax = plt.subplots(figsize=(8, max(2, len(score_names) * 0.6)))
                    bars = ax.barh(score_names, score_vals, color="#4da6ff")
                    ax.set_xlim(0, max(10, max(score_vals) * 1.15))
                    ax.set_xlabel("Score")
                    ax.set_title("Judge Scores by Section")
                    for bar, val in zip(bars, score_vals):
                        ax.text(bar.get_width() + 0.15, bar.get_y() + bar.get_height() / 2,
                                f"{val:.1f}", va="center", fontsize=9)
                    plt.tight_layout()
                    st.pyplot(fig)
                    plt.close(fig)

                for artifact_name, score_data in artifact_scores.items():
                    score_val = score_data.get("score", score_data.get("overall_score", "N/A"))
                    with st.expander(f"{artifact_name.replace('_', ' ').title()} — Score: {score_val}"):
                        for k, v in score_data.items():
                            if isinstance(v, str) and len(v) > 200:
                                st.markdown(f"**{k}**:")
                                st.markdown(v)
                            else:
                                st.markdown(f"**{k}**: {v}")

    # ── Mission Report ────────────────────────────────────────

    report_key = "mission_report_best" if "mission_report_best" in data else "mission_report"
    report_text = data.get(report_key, "")

    if report_text:
        st.divider()
        st.subheader("Mission Design Report")
        st.caption("The full mission design output rendered as formatted Markdown.")
        with st.expander("View Full Report", expanded=False):
            st.markdown(report_text)

    # ── Conversation Trace ────────────────────────────────────

    trace_text = data.get("conversation_trace", "")
    if trace_text:
        st.divider()
        st.subheader("Conversation Trace")
        st.caption(
            "Full chain-of-thought transcript showing agent interactions, "
            "task delegation, and decision-making — used for orchestration "
            "quality evaluation."
        )
        with st.expander("View Full Conversation Trace", expanded=False):
            st.markdown(trace_text)

    # ── Metrics Report ────────────────────────────────────────

    metrics_report_text = data.get("report", "")
    if metrics_report_text:
        st.divider()
        with st.expander("Metrics Report (Technical)", expanded=False):
            st.markdown(metrics_report_text)

    # ── Downloads ─────────────────────────────────────────────

    st.divider()
    st.subheader("Downloads")
    st.caption("Export results for offline analysis or sharing.")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if report_text:
            st.download_button(
                "\U0001f4c4 Mission Report (.md)",
                data=report_text,
                file_name="mission_report.md",
                mime="text/markdown",
                use_container_width=True,
            )
        else:
            st.button("\U0001f4c4 No report", disabled=True, use_container_width=True)

    with col2:
        if trace_text:
            st.download_button(
                "\U0001f4ac Conversation Trace (.md)",
                data=trace_text,
                file_name="conversation_trace.md",
                mime="text/markdown",
                use_container_width=True,
            )
        else:
            st.button("\U0001f4ac No trace", disabled=True, use_container_width=True)

    with col3:
        metrics_json = json.dumps(metrics_data, indent=2, default=str)
        st.download_button(
            "\U0001f4ca Metrics (.json)",
            data=metrics_json,
            file_name="metrics.json",
            mime="application/json",
            use_container_width=True,
        )

    with col4:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            if selected_path.is_dir():
                for fp in sorted(selected_path.rglob("*")):
                    if fp.is_file():
                        zf.write(fp, fp.relative_to(selected_path))
        zip_buffer.seek(0)
        st.download_button(
            "\U0001f4e6 Full Run (.zip)",
            data=zip_buffer,
            file_name=f"{selected_path.name}.zip",
            mime="application/zip",
            use_container_width=True,
        )

    # ── Raw JSON viewer ───────────────────────────────────────

    with st.expander("Raw Data (JSON)", expanded=False):
        tab_meta, tab_metrics, tab_eval = st.tabs(["Metadata", "Metrics", "Evaluation"])
        with tab_meta:
            meta = data.get("metadata", {})
            st.json(meta) if meta else st.caption("No metadata available.")
        with tab_metrics:
            st.json(metrics_data) if metrics_data else st.caption("No metrics available.")
        with tab_eval:
            st.json(evaluation) if evaluation else st.caption("No evaluation data available.")

    # ── Delete run ─────────────────────────────────────────────

    st.divider()
    # Find the top-level result folder (parent of the leaf run if nested)
    _delete_target = selected_path
    while _delete_target.parent != RESULTS_DIR and _delete_target.parent.parent.exists():
        _delete_target = _delete_target.parent
        if _delete_target == RESULTS_DIR:
            _delete_target = selected_path
            break

    _del_key = f"_confirm_del_{_delete_target.name}"
    with st.expander("Danger Zone", expanded=False):
        st.warning(
            f"This will permanently delete **{_delete_target.name}** and all its contents.",
            icon="\u26a0\ufe0f",
        )
        confirm = st.checkbox("I understand, delete this result", key=_del_key)
        if st.button(
            "Delete Result",
            type="primary",
            disabled=not confirm,
            key=f"_btn_del_{_delete_target.name}",
        ):
            shutil.rmtree(_delete_target)
            st.success("Deleted! Refreshing...")
            st.rerun()


# ── COMPARE SYSTEMS (GROUP) VIEW ─────────────────────────────

elif view_mode == "Compare Systems (Group)":
    selected_group_label = st.selectbox(
        "Select experiment group",
        options=list(selectable_groups.keys()),
        index=0,
        key="_group_selector",
    )
    if not selected_group_label:
        st.stop()

    group_path = selectable_groups[selected_group_label]

    st.divider()
    st.subheader("Cross-System Comparison")
    st.caption("Side-by-side comparison of all system architectures in this experiment group.")

    comparison = compare_group(group_path)
    comp_runs = comparison.get("runs", [])

    if not comp_runs:
        st.warning("No comparable runs found in this group.")
        st.stop()

    _render_comparison_charts(comp_runs)

    # ── Per-system details ────────────────────────────────────

    st.divider()
    st.subheader("Per-System Details")

    sys_dirs = find_system_dirs(group_path)
    tabs = st.tabs([name.replace("_", " ").title() for name in sys_dirs.keys()])

    for tab, (sys_name, sys_path) in zip(tabs, sys_dirs.items()):
        with tab:
            sys_data = load_run(sys_path)
            if not sys_data:
                st.warning(f"No data found for {sys_name}")
                continue

            # Metrics
            sys_metrics = sys_data.get("metrics", {})
            sys_totals = sys_metrics.get("totals", {})
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Calls", f"{sys_totals.get('num_calls', 0):.0f}")
            c2.metric("Tokens", f"{sys_totals.get('total_tokens', 0):,.0f}")
            c3.metric("Cost", f"${sys_totals.get('cost_usd', 0):.4f}")
            c4.metric("Latency", f"{sys_totals.get('latency_s', 0):.1f}s")

            # Judge
            sys_eval = sys_data.get("evaluation", {})
            sys_judge = sys_eval.get("judge_scores", {})
            agg = sys_judge.get("_aggregate", {})
            if agg:
                st.metric("Judge Score", f"{agg.get('mean_score', 0):.2f}")

            # Mission report
            rk = "mission_report_best" if "mission_report_best" in sys_data else "mission_report"
            report = sys_data.get(rk, "")
            if report:
                with st.expander("Mission Report", expanded=False):
                    st.markdown(report)

            # Conversation trace
            sys_trace = sys_data.get("conversation_trace", "")
            if sys_trace:
                with st.expander("Conversation Trace", expanded=False):
                    st.markdown(sys_trace)

    # ── Markdown comparison ───────────────────────────────────

    with st.expander("Raw Comparison (Markdown)"):
        st.code(comparison_to_markdown(comparison), language="markdown")

    # ── Group download ────────────────────────────────────────

    st.divider()
    st.subheader("Downloads")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in sorted(group_path.rglob("*")):
            if fp.is_file():
                zf.write(fp, fp.relative_to(group_path))
    zip_buffer.seek(0)
    st.download_button(
        "\U0001f4e6 Download Full Group (.zip)",
        data=zip_buffer,
        file_name=f"{group_path.name}.zip",
        mime="application/zip",
        use_container_width=True,
    )

    # ── Delete group ──────────────────────────────────────────

    st.divider()
    _gdel_key = f"_confirm_gdel_{group_path.name}"
    with st.expander("Danger Zone", expanded=False):
        st.warning(
            f"This will permanently delete **{group_path.name}** and all its contents "
            f"({len(sys_dirs)} system runs).",
            icon="\u26a0\ufe0f",
        )
        gconfirm = st.checkbox("I understand, delete this experiment group", key=_gdel_key)
        if st.button(
            "Delete Experiment Group",
            type="primary",
            disabled=not gconfirm,
            key=f"_btn_gdel_{group_path.name}",
        ):
            shutil.rmtree(group_path)
            st.success("Deleted! Refreshing...")
            st.rerun()


# ── COMPARE SELECTED RUNS VIEW ───────────────────────────────

elif view_mode == "Compare Selected Runs":
    from src.runner.comparison import compare_runs

    st.caption("Pick any 2 or more runs to compare side by side.")

    selected_labels = st.multiselect(
        "Select runs to compare",
        options=list(selectable_runs.keys()),
        default=list(selectable_runs.keys())[:min(3, len(selectable_runs))],
        key="_compare_multi_selector",
    )

    if len(selected_labels) < 2:
        st.warning("Select at least 2 runs to compare.", icon="\u261d\ufe0f")
        st.stop()

    selected_paths = [selectable_runs[label] for label in selected_labels]

    st.divider()
    st.subheader("Run Comparison")

    comparison = compare_runs(selected_paths)
    comp_runs = comparison.get("runs", [])

    if not comp_runs:
        st.warning("Could not load data from the selected runs.")
        st.stop()

    # Use labels that distinguish runs (system_type + short path)
    for r in comp_runs:
        run_path = Path(r["run_dir"])
        rel = run_path.relative_to(RESULTS_DIR)
        r["system_type"] = f"{r['system_type']} ({rel.parts[0][:20]})"

    _render_comparison_charts(comp_runs)

    # ── Per-run details in tabs ───────────────────────────────

    st.divider()
    st.subheader("Per-Run Details")

    tab_labels = [f"{Path(r['run_dir']).relative_to(RESULTS_DIR).parts[0][:25]}" for r in comp_runs]
    tabs = st.tabs(tab_labels)

    for tab, r in zip(tabs, comp_runs):
        with tab:
            run_path = Path(r["run_dir"])
            run_data = load_run(run_path)
            if not run_data:
                st.warning(f"No data found for {run_path.name}")
                continue

            sys_metrics = run_data.get("metrics", {})
            sys_totals = sys_metrics.get("totals", {})
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Calls", f"{sys_totals.get('num_calls', 0):.0f}")
            c2.metric("Tokens", f"{sys_totals.get('total_tokens', 0):,.0f}")
            c3.metric("Cost", f"${sys_totals.get('cost_usd', 0):.4f}")
            c4.metric("Latency", f"{sys_totals.get('latency_s', 0):.1f}s")

            sys_eval = run_data.get("evaluation", {})
            sys_judge = sys_eval.get("judge_scores", {})
            agg = sys_judge.get("_aggregate", {})
            if agg:
                st.metric("Judge Score", f"{agg.get('mean_score', 0):.2f}")

            rk = "mission_report_best" if "mission_report_best" in run_data else "mission_report"
            report = run_data.get(rk, "")
            if report:
                with st.expander("Mission Report", expanded=False):
                    st.markdown(report)

            run_trace = run_data.get("conversation_trace", "")
            if run_trace:
                with st.expander("Conversation Trace", expanded=False):
                    st.markdown(run_trace)
