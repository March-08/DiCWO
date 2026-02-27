"""Load YAML defaults, model lists, and pricing info for the Streamlit app."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is importable
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import yaml

from src.core.llm_client import _PRICING, PROVIDER_URLS

# ---------------------------------------------------------------------------
# YAML config loading
# ---------------------------------------------------------------------------

CONFIGS_DIR = _PROJECT_ROOT / "configs"

SYSTEM_CONFIGS: dict[str, dict] = {}
for yaml_file in ["single_agent.yaml", "centralized_manager.yaml", "dicwo.yaml"]:
    path = CONFIGS_DIR / yaml_file
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        SYSTEM_CONFIGS[data.get("system_type", yaml_file.replace(".yaml", ""))] = data

# Domain config
DOMAIN_CONFIG_PATH = CONFIGS_DIR / "domain" / "dthh_mission.yaml"
DOMAIN_CONFIG: dict = {}
if DOMAIN_CONFIG_PATH.exists():
    with open(DOMAIN_CONFIG_PATH) as f:
        DOMAIN_CONFIG = yaml.safe_load(f) or {}


# ---------------------------------------------------------------------------
# Model lists by provider
# ---------------------------------------------------------------------------

def get_models_by_provider() -> dict[str, list[str]]:
    """Return {provider: [model_names]} from the _PRICING dict."""
    openai_models: list[str] = []
    openrouter_models: list[str] = []

    for model in _PRICING:
        if "/" in model:
            openrouter_models.append(model)
        else:
            openai_models.append(model)

    return {
        "openai": sorted(set(openai_models)),
        "openrouter": sorted(set(openrouter_models)),
    }


MODELS_BY_PROVIDER = get_models_by_provider()
PRICING = _PRICING
PROVIDERS = list(PROVIDER_URLS.keys())

# ---------------------------------------------------------------------------
# DiCWO-specific parameter defaults
# ---------------------------------------------------------------------------

DICWO_PARAM_DEFAULTS: dict[str, dict] = {
    "Bid Weights": {
        "bid_alpha": {"default": 1.0, "min": 0.0, "max": 5.0, "step": 0.1, "help": "Weight for capability fit"},
        "bid_beta": {"default": 0.5, "min": 0.0, "max": 5.0, "step": 0.1, "help": "Weight for calibration penalty"},
        "bid_gamma": {"default": 0.3, "min": 0.0, "max": 5.0, "step": 0.1, "help": "Weight for cost"},
        "bid_delta": {"default": 0.2, "min": 0.0, "max": 5.0, "step": 0.1, "help": "Weight for diversity gain"},
        "calibration_decay": {"default": 0.9, "min": 0.0, "max": 1.0, "step": 0.05, "help": "Decay factor for calibration updates"},
    },
    "Consensus": {
        "consensus_threshold": {"default": 0.7, "min": 0.0, "max": 1.0, "step": 0.05, "help": "Agreement ratio for consensus"},
        "min_voters": {"default": 3, "min": 1, "max": 5, "step": 1, "help": "Minimum voters for consensus"},
    },
    "Checkpoint Thresholds": {
        "disagreement_threshold": {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.05, "help": "Triggers rewire if exceeded"},
        "uncertainty_threshold": {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05, "help": "Triggers escalate if exceeded"},
        "risk_threshold": {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.05, "help": "Combined risk threshold"},
    },
    "Legacy Thresholds": {
        "hitl_evoi_threshold": {"default": 0.7, "min": 0.0, "max": 1.0, "step": 0.05, "help": "EVoI threshold (legacy, kept for backward compatibility)"},
        "max_hitl_calls": {"default": 3, "min": 0, "max": 10, "step": 1, "help": "Max HITL calls (legacy, kept for backward compatibility)"},
    },
    "Policy": {
        "acceptance_quality": {"default": 0.7, "min": 0.0, "max": 1.0, "step": 0.05, "help": "Min quality to trigger early stop"},
        "max_subtask_retries": {"default": 1, "min": 0, "max": 5, "step": 1, "help": "Max retry attempts for failed subtasks"},
    },
    "Agent Factory": {
        "max_spawned_agents": {"default": 2, "min": 0, "max": 10, "step": 1, "help": "Max dynamically created agents"},
        "agent_ttl_rounds": {"default": 5, "min": 1, "max": 20, "step": 1, "help": "Time-to-live rounds for spawned agents"},
        "credential_threshold": {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05, "help": "Min score to pass entrance task"},
    },
}

ALL_PROTOCOLS = ["solo", "audit", "debate", "parallel", "tool_verified"]
