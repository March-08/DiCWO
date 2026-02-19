"""Shared sidebar: API keys and status indicators."""

from __future__ import annotations

import streamlit as st

from utils.session import init_all_defaults, has_api_key_for, get


def render_sidebar() -> None:
    """Render the shared sidebar on every page."""
    init_all_defaults()

    with st.sidebar:
        st.title("DiCWO Mission Design")
        st.caption("Satellite constellation design with multi-agent systems")

        st.divider()

        # API Keys
        st.subheader("API Keys")
        st.caption("Keys are stored in session memory only — never persisted.")

        st.session_state["openai_api_key"] = st.text_input(
            "OpenAI API Key",
            value=get("openai_api_key", ""),
            type="password",
            key="_openai_key_input",
        )
        st.session_state["openrouter_api_key"] = st.text_input(
            "OpenRouter API Key",
            value=get("openrouter_api_key", ""),
            type="password",
            key="_openrouter_key_input",
        )

        # Status indicators
        st.divider()
        st.subheader("Status")

        provider = get("provider", "openrouter")
        judge_provider = get("judge_provider", "openrouter")

        col1, col2 = st.columns(2)
        with col1:
            if has_api_key_for(provider):
                st.success(f"Agent: {provider}", icon="\u2705")
            else:
                st.warning(f"Agent: {provider}", icon="\u26a0\ufe0f")
        with col2:
            if has_api_key_for(judge_provider):
                st.success(f"Judge: {judge_provider}", icon="\u2705")
            else:
                st.warning(f"Judge: {judge_provider}", icon="\u26a0\ufe0f")

        # Run status
        if get("running", False):
            st.info("Experiment running...", icon="\u23f3")
        elif get("run_error"):
            st.error("Last run failed", icon="\u274c")
        elif get("run_results"):
            st.success(f"{len(get('run_results', []))} run(s) complete", icon="\u2705")
