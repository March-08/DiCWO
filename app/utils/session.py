"""Session state helpers for the Streamlit app."""

from __future__ import annotations

from typing import Any

import streamlit as st


def init_state(key: str, default: Any) -> None:
    """Set a session state key if it doesn't exist yet."""
    if key not in st.session_state:
        st.session_state[key] = default


def get(key: str, default: Any = None) -> Any:
    """Get a session state value with a default."""
    return st.session_state.get(key, default)


def put(key: str, value: Any) -> None:
    """Set a session state value."""
    st.session_state[key] = value


def init_all_defaults() -> None:
    """Initialize all session state defaults for the app."""
    # API keys
    init_state("openai_api_key", "")
    init_state("openrouter_api_key", "")

    # Configuration
    init_state("system_type", "single_agent")
    init_state("provider", "openrouter")
    init_state("model", "meta-llama/llama-3.3-70b-instruct")
    init_state("temperature", 0.7)
    init_state("max_rounds", 10)
    init_state("max_tokens", 16384)
    init_state("judge_provider", "openrouter")
    init_state("judge_model", "openai/gpt-4.1")
    init_state("run_judge", True)
    # DiCWO params
    init_state("system_params", {})

    # Prompts (None means "use defaults")
    init_state("custom_prompts", {})
    init_state("custom_roles", {})

    # Run state
    init_state("running", False)
    init_state("run_results", [])
    init_state("run_error", None)
    init_state("progress_events", [])
    init_state("run_thread", None)


def get_api_keys() -> dict[str, str]:
    """Return the provider -> API key mapping from session state."""
    keys: dict[str, str] = {}
    if st.session_state.get("openai_api_key"):
        keys["openai"] = st.session_state["openai_api_key"]
    if st.session_state.get("openrouter_api_key"):
        keys["openrouter"] = st.session_state["openrouter_api_key"]
    return keys


def has_api_key_for(provider: str) -> bool:
    """Check if we have an API key for the given provider."""
    keys = get_api_keys()
    return bool(keys.get(provider))
