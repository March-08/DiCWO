"""Page 1: Configure — system type, model, parameters."""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from components.sidebar import render_sidebar
from utils.defaults import (
    MODELS_BY_PROVIDER,
    PRICING,
    PROVIDERS,
    SYSTEM_CONFIGS,
    DICWO_PARAM_DEFAULTS,
    ALL_PROTOCOLS,
)
from utils.session import init_all_defaults, get, put

render_sidebar()
init_all_defaults()

st.title("Configure Experiment")
st.caption(
    "Set up the LLM models, system architecture, and parameters for your "
    "satellite constellation design experiment."
)

# ── System Type ───────────────────────────────────────────────

SYSTEM_TYPES = ["single_agent", "centralized", "dicwo"]
SYSTEM_LABELS = {
    "single_agent": "Single Agent",
    "centralized": "Centralized Manager",
    "dicwo": "DiCWO (Distributed)",
}
SYSTEM_DESCRIPTIONS = {
    "single_agent": (
        "A single LLM produces the entire Phase 0/A mission design in one response. "
        "Fastest and cheapest, but no specialist collaboration."
    ),
    "centralized": (
        "A manager agent coordinates specialist agents (Market Analyst, Frequency Expert, "
        "Payload Expert, Mission Analyst). The manager decides task order and routing."
    ),
    "dicwo": (
        "**Distributed Calibration-Weighted Orchestration** — agents autonomously bid for tasks "
        "based on capability scores, reach consensus via voting, and self-organize through "
        "checkpoints. The most advanced architecture with dynamic agent spawning and HITL support."
    ),
}

system_type = st.selectbox(
    "System Architecture",
    options=SYSTEM_TYPES,
    format_func=lambda x: SYSTEM_LABELS.get(x, x),
    index=SYSTEM_TYPES.index(get("system_type", "single_agent")),
    help="Choose how the LLM agents are organized to produce the mission design.",
    key="_system_type_select",
)
put("system_type", system_type)

st.info(SYSTEM_DESCRIPTIONS[system_type], icon="\u2139\ufe0f")

# Load YAML defaults for this system type
yaml_defaults = SYSTEM_CONFIGS.get(system_type, {})

# ── Agent LLM ─────────────────────────────────────────────────

st.divider()
st.subheader("Agent LLM")
st.caption(
    "The language model used by agents to generate mission design outputs. "
    "OpenRouter gives access to many models (Llama, Gemini, etc.) with a single API key."
)

col1, col2 = st.columns(2)

with col1:
    provider = st.selectbox(
        "Provider",
        options=PROVIDERS,
        index=PROVIDERS.index(yaml_defaults.get("provider", get("provider", "openrouter"))),
        help=(
            "**OpenAI**: Direct access to GPT models. Requires an OpenAI API key. "
            "**OpenRouter**: Gateway to 100+ models (Llama, Gemini, DeepSeek, etc.) with one key."
        ),
        key="_provider_select",
    )
    put("provider", provider)

with col2:
    models = MODELS_BY_PROVIDER.get(provider, [])
    default_model = yaml_defaults.get("model", get("model", ""))
    model_index = 0
    if default_model in models:
        model_index = models.index(default_model)

    def _format_model(m: str) -> str:
        """Show model name with price hint."""
        inp, out = PRICING.get(m, (0, 0))
        if inp == 0 and out == 0:
            return f"{m}  [FREE]"
        return f"{m}  [${inp:.2f}/${out:.2f} per 1M tok]"

    model = st.selectbox(
        "Model",
        options=models,
        index=model_index if models else 0,
        format_func=_format_model,
        help="Prices shown as input/output per 1M tokens. ':free' models have zero cost but may be rate-limited.",
        key="_model_select",
    )
    put("model", model)

col1, col2, col3 = st.columns(3)

with col1:
    temperature = st.slider(
        "Temperature",
        min_value=0.0,
        max_value=2.0,
        value=float(yaml_defaults.get("temperature", get("temperature", 0.7))),
        step=0.1,
        help=(
            "Controls randomness of LLM outputs. "
            "**0.0** = deterministic, always picks the most likely token. "
            "**0.7** = balanced creativity (recommended). "
            "**2.0** = highly creative/random."
        ),
        key="_temperature_slider",
    )
    put("temperature", temperature)

with col2:
    max_rounds = st.number_input(
        "Max Rounds",
        min_value=1,
        max_value=50,
        value=int(yaml_defaults.get("max_rounds", get("max_rounds", 10))),
        step=1,
        help=(
            "Maximum number of agent interaction rounds before the system stops. "
            "Single Agent uses 1 round. Centralized typically needs 5-10. "
            "DiCWO may need 10-15 for complex designs. Higher = more thorough but more expensive."
        ),
        key="_max_rounds_input",
    )
    put("max_rounds", max_rounds)

with col3:
    max_tokens = st.number_input(
        "Max Tokens per Response",
        min_value=256,
        max_value=131072,
        value=int(yaml_defaults.get("max_tokens", get("max_tokens", 16384))),
        step=1024,
        help=(
            "Maximum number of tokens (words) each LLM response can contain. "
            "16384 is a good default. Increase if agent responses are getting cut off. "
            "1 token ~ 0.75 words."
        ),
        key="_max_tokens_input",
    )
    put("max_tokens", max_tokens)

# ── Judge LLM ─────────────────────────────────────────────────

st.divider()
st.subheader("Judge LLM")
st.caption(
    "A separate LLM evaluates the quality of the mission design after it's generated. "
    "Using a stronger/different model as judge gives a more objective assessment. "
    "The judge scores each section (market analysis, payload design, etc.) on a rubric."
)

col1, col2 = st.columns(2)

with col1:
    judge_provider = st.selectbox(
        "Judge Provider",
        options=PROVIDERS,
        index=PROVIDERS.index(yaml_defaults.get("judge_provider", get("judge_provider", "openrouter"))),
        help="The API provider for the judge model. Can differ from the agent provider.",
        key="_judge_provider_select",
    )
    put("judge_provider", judge_provider)

with col2:
    judge_models = MODELS_BY_PROVIDER.get(judge_provider, [])
    default_judge = yaml_defaults.get("judge_model", get("judge_model", ""))
    judge_model_index = 0
    if default_judge in judge_models:
        judge_model_index = judge_models.index(default_judge)
    judge_model = st.selectbox(
        "Judge Model",
        options=judge_models,
        index=judge_model_index if judge_models else 0,
        format_func=_format_model,
        help="Tip: use a stronger model than the agents (e.g., GPT-4.1 judging Llama outputs) for reliable scoring.",
        key="_judge_model_select",
    )
    put("judge_model", judge_model)

# ── Evaluation ────────────────────────────────────────────────

st.divider()
st.subheader("Evaluation")
st.caption("Choose whether to run a judge evaluation after the design is generated.")

run_judge = st.checkbox(
    "Run LLM Judge",
    value=yaml_defaults.get("run_judge", get("run_judge", True)),
    help=(
        "Uses a separate LLM to score each section of the mission design on "
        "technical accuracy, completeness, and consistency. Adds cost and time, "
        "but gives a quality score for comparison."
    ),
    key="_run_judge_check",
)
put("run_judge", run_judge)

# ── DiCWO Parameters ──────────────────────────────────────────

if system_type == "dicwo":
    st.divider()
    st.subheader("DiCWO Advanced Parameters")
    st.caption(
        "These control the DiCWO orchestration algorithm. Default values work well for most cases. "
        "Only change these if you understand the bidding/consensus mechanism."
    )

    SECTION_DESCRIPTIONS = {
        "Bid Weights": (
            "Controls how agents bid for tasks. The bid formula is: "
            "`bid = alpha * fit - beta * calibration_penalty - gamma * cost + delta * diversity`. "
            "Higher alpha favours capable agents; higher gamma penalises expensive ones."
        ),
        "Consensus": (
            "When multiple agents produce outputs, consensus voting determines which is best. "
            "The threshold sets how much agreement is needed before accepting a result."
        ),
        "Checkpoint Thresholds": (
            "After each task, a checkpoint evaluates the output quality. "
            "If disagreement or uncertainty is too high, the system rewires (reassigns) or escalates."
        ),
        "HITL Budget": (
            "Human-in-the-Loop: if the system is highly uncertain about a result, it can request "
            "human review. EVoI (Expected Value of Information) measures how much a human review would help."
        ),
        "Policy": (
            "Controls when the system stops retrying and what quality threshold triggers early completion."
        ),
        "Agent Factory": (
            "DiCWO can dynamically spawn new specialist agents during a run if needed. "
            "These settings control how many can be spawned and how long they live."
        ),
    }

    yaml_sys_params = yaml_defaults.get("system_params", {})
    sys_params = dict(get("system_params", {}))

    for section_name, params in DICWO_PARAM_DEFAULTS.items():
        with st.expander(section_name, expanded=False):
            st.markdown(f"*{SECTION_DESCRIPTIONS.get(section_name, '')}*")
            for param_key, meta in params.items():
                default_val = yaml_sys_params.get(param_key, meta["default"])
                if isinstance(meta["default"], int):
                    val = st.number_input(
                        param_key.replace("_", " ").title(),
                        min_value=meta["min"],
                        max_value=meta["max"],
                        value=int(default_val),
                        step=meta["step"],
                        help=meta["help"],
                        key=f"_dicwo_{param_key}",
                    )
                else:
                    val = st.slider(
                        param_key.replace("_", " ").title(),
                        min_value=float(meta["min"]),
                        max_value=float(meta["max"]),
                        value=float(default_val),
                        step=float(meta["step"]),
                        help=meta["help"],
                        key=f"_dicwo_{param_key}",
                    )
                sys_params[param_key] = val

    PROTOCOL_DESCRIPTIONS = {
        "solo": "Single agent executes the task alone",
        "audit": "One agent executes, a second agent reviews the output",
        "debate": "Two agents debate, consensus selects the best answer",
        "parallel": "Multiple agents execute in parallel, best output selected",
        "tool_verified": "Agent executes, then a second pass verifies the result",
    }

    with st.expander("Execution Protocols", expanded=False):
        st.markdown(
            "*Protocols define how tasks are executed. Each subtask is assigned a protocol "
            "based on its complexity and risk.*"
        )
        yaml_protocols = yaml_sys_params.get("protocols", ALL_PROTOCOLS)
        selected = st.multiselect(
            "Enabled Protocols",
            options=ALL_PROTOCOLS,
            default=yaml_protocols,
            help="Select which execution strategies are available to the orchestrator.",
            key="_dicwo_protocols",
        )
        for p in ALL_PROTOCOLS:
            st.caption(f"**{p}**: {PROTOCOL_DESCRIPTIONS.get(p, '')}")
        sys_params["protocols"] = selected

    put("system_params", sys_params)

# ── Summary ───────────────────────────────────────────────────

st.divider()
st.subheader("Configuration Summary")

inp_price, out_price = PRICING.get(model, (0, 0))
j_inp, j_out = PRICING.get(judge_model, (0, 0))

col1, col2 = st.columns(2)
with col1:
    st.markdown("**Agent Setup**")
    st.markdown(f"- Architecture: **{SYSTEM_LABELS.get(system_type, system_type)}**")
    st.markdown(f"- Model: `{model}`")
    st.markdown(f"- Provider: {provider}")
    st.markdown(f"- Temperature: {temperature} | Max rounds: {max_rounds}")
    st.markdown(f"- Price: ${inp_price:.2f} in / ${out_price:.2f} out per 1M tokens")

with col2:
    st.markdown("**Evaluation Setup**")
    st.markdown(f"- Judge model: `{judge_model}`")
    st.markdown(f"- Judge price: ${j_inp:.2f} in / ${j_out:.2f} out per 1M tokens")
    st.markdown(f"- LLM Judge: {'Enabled' if run_judge else 'Disabled'}")

st.success("Configuration saved. Go to **Run Experiment** to start.", icon="\u2705")
