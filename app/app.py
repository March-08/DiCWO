"""DiCWO Mission Design — Streamlit web app entry point."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path for imports
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from components.sidebar import render_sidebar

st.set_page_config(
    page_title="DiCWO Mission Design",
    page_icon="\U0001f6f0\ufe0f",
    layout="wide",
    initial_sidebar_state="expanded",
)

render_sidebar()

# ── Landing Page ──────────────────────────────────────────────

st.title("\U0001f6f0\ufe0f DiCWO Mission Design Studio")
st.markdown(
    """
    Welcome to the **DiCWO Mission Design Studio** — a web interface for running
    multi-agent satellite constellation design experiments.

    ### How to use

    1. **Enter API keys** in the sidebar (OpenAI and/or OpenRouter)
    2. **Configure** your experiment on the Configure page
    3. **Edit prompts** if you want to customize agent behaviour
    4. **Run** the experiment and watch live progress
    5. **View results** in the dashboard, compare systems, and download outputs

    ---

    ### Systems available

    | System | Description |
    |--------|-------------|
    | **Single Agent** | One LLM produces the entire mission design in a single response |
    | **Centralized** | A manager agent routes tasks to specialist agents |
    | **DiCWO** | Distributed Calibration-Weighted Orchestration — agents bid for tasks, reach consensus, and self-organize |

    ---

    Use the **sidebar navigation** to get started.
    """
)
