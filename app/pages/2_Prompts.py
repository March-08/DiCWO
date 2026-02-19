"""Page 2: Prompts — edit system prompts, task descriptions, and agent roles."""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from components.sidebar import render_sidebar
from utils.session import init_all_defaults, get, put

# Import the actual prompt/role modules so we can read defaults
from src.domain import prompts as prompts_module
from src.domain import roles as roles_module
from src.core.agent import AgentIdentity

render_sidebar()
init_all_defaults()

st.title("Edit Prompts & Roles")
st.caption("Customize the prompts and agent identities used in each run. Changes apply to the next run only.")

# ── Helpers ───────────────────────────────────────────────────

def _get_custom(key: str, default: str) -> str:
    """Get a custom prompt value, falling back to default."""
    customs = get("custom_prompts", {})
    return customs.get(key, default)


def _set_custom(key: str, value: str, default: str) -> None:
    """Set a custom prompt (or remove if it matches default)."""
    customs = dict(get("custom_prompts", {}))
    if value.strip() == default.strip():
        customs.pop(key, None)
    else:
        customs[key] = value
    put("custom_prompts", customs)


def _get_custom_role(name: str) -> dict | None:
    """Get a custom role dict, or None for default."""
    return get("custom_roles", {}).get(name)


def _set_custom_role(name: str, role_dict: dict | None) -> None:
    customs = dict(get("custom_roles", {}))
    if role_dict is None:
        customs.pop(name, None)
    else:
        customs[name] = role_dict
    put("custom_roles", customs)


# ── Tabs ──────────────────────────────────────────────────────

tab_sys, tab_tasks, tab_roles = st.tabs(["System Prompts", "Task Descriptions", "Agent Roles"])

# ── System Prompts ────────────────────────────────────────────

with tab_sys:
    st.subheader("System Prompts")

    prompt_defs = [
        ("SINGLE_AGENT_SYSTEM_PROMPT", "Single Agent System Prompt"),
        ("SINGLE_AGENT_USER_PROMPT", "Single Agent User Prompt"),
        ("MANAGER_SYSTEM_PROMPT", "Manager System Prompt"),
        ("MANAGER_ROUTING_PROMPT", "Manager Routing Prompt"),
        ("INTEGRATION_PROMPT", "Integration Prompt"),
        ("CONTEXT_INJECTION", "Context Injection Template"),
    ]

    for attr_name, label in prompt_defs:
        default_val = getattr(prompts_module, attr_name, "")
        current_val = _get_custom(attr_name, default_val)
        is_modified = current_val.strip() != default_val.strip()

        header_col, reset_col = st.columns([5, 1])
        with header_col:
            st.markdown(f"**{label}**" + (" (modified)" if is_modified else ""))
        with reset_col:
            if is_modified and st.button("Reset", key=f"_reset_{attr_name}"):
                _set_custom(attr_name, default_val, default_val)
                st.rerun()

        new_val = st.text_area(
            label,
            value=current_val,
            height=200,
            key=f"_prompt_{attr_name}",
            label_visibility="collapsed",
        )
        _set_custom(attr_name, new_val, default_val)

# ── Task Descriptions ─────────────────────────────────────────

with tab_tasks:
    st.subheader("Task Descriptions")
    st.caption("These are the task prompts given to specialist agents.")

    for task_key, default_desc in prompts_module.TASK_DESCRIPTIONS.items():
        agent = prompts_module.TASK_AGENT_MAP.get(task_key, "")
        store_key = f"TASK_{task_key}"
        current_val = _get_custom(store_key, default_desc)
        is_modified = current_val.strip() != default_desc.strip()

        header_col, reset_col = st.columns([5, 1])
        with header_col:
            st.markdown(f"**{task_key}** ({agent})" + (" (modified)" if is_modified else ""))
        with reset_col:
            if is_modified and st.button("Reset", key=f"_reset_{store_key}"):
                _set_custom(store_key, default_desc, default_desc)
                st.rerun()

        new_val = st.text_area(
            task_key,
            value=current_val,
            height=120,
            key=f"_task_{task_key}",
            label_visibility="collapsed",
        )
        _set_custom(store_key, new_val, default_desc)

# ── Agent Roles ───────────────────────────────────────────────

with tab_roles:
    st.subheader("Agent Roles")
    st.caption("Edit agent identities — name, role, goal, and backstory.")

    for identity in roles_module.ALL_ROLES:
        custom = _get_custom_role(identity.name)
        is_modified = custom is not None

        with st.expander(
            f"{identity.name}" + (" (modified)" if is_modified else ""),
            expanded=False,
        ):
            reset_col1, reset_col2 = st.columns([5, 1])
            with reset_col2:
                if is_modified and st.button("Reset", key=f"_reset_role_{identity.name}"):
                    _set_custom_role(identity.name, None)
                    st.rerun()

            current = custom or {
                "name": identity.name,
                "role": identity.role,
                "goal": identity.goal,
                "backstory": identity.backstory,
            }

            name_val = st.text_input(
                "Name", value=current["name"],
                key=f"_role_name_{identity.name}",
            )
            role_val = st.text_input(
                "Role", value=current["role"],
                key=f"_role_role_{identity.name}",
            )
            goal_val = st.text_area(
                "Goal", value=current["goal"], height=100,
                key=f"_role_goal_{identity.name}",
            )
            backstory_val = st.text_area(
                "Backstory", value=current["backstory"], height=100,
                key=f"_role_backstory_{identity.name}",
            )

            new_role = {
                "name": name_val,
                "role": role_val,
                "goal": goal_val,
                "backstory": backstory_val,
            }

            # Check if anything changed from default
            default_dict = {
                "name": identity.name,
                "role": identity.role,
                "goal": identity.goal,
                "backstory": identity.backstory,
            }
            if new_role != default_dict:
                _set_custom_role(identity.name, new_role)
            else:
                _set_custom_role(identity.name, None)

# ── Reset All ─────────────────────────────────────────────────

st.divider()
if st.button("Reset All to Defaults", type="secondary"):
    put("custom_prompts", {})
    put("custom_roles", {})
    st.rerun()

# Show modification count
n_prompts = len(get("custom_prompts", {}))
n_roles = len(get("custom_roles", {}))
if n_prompts or n_roles:
    st.info(f"{n_prompts} prompt(s) and {n_roles} role(s) modified from defaults.")
else:
    st.success("All prompts and roles are at their defaults.")
