"""Settings of the Assistant (``settings/assistant_settings.json``).

The old file name ``support_agent_settings.json`` is still read: in the
settings folder and in an experiment folder, ``assistant_settings.json`` is
merged over ``support_agent_settings.json`` when both exist.

Who gets the Assistant is resolved, highest precedence first, from the
``HANI2_ASSISTANT`` environment variable (set by ``hani2 --assistant``; the old
name ``HANI2_SUPPORT_AGENT`` is still read), then the ``mode`` setting: ``on``
(everyone), ``off`` (nobody) or ``auto`` (admins only). ``HANI2_ASSISTANT_CLASS``
(set by ``hani2 --assistant <class>``; old name ``HANI2_SUPPORT_AGENT_CLASS``)
overrides the ``agent_class`` setting.

The functions and constants with ``support_agent`` in their names are the old
names of the ``assistant`` ones and stay available.
"""

from __future__ import annotations

import os
from typing import Any

from hani2.config import load_json_settings, save_json_settings

__all__ = [
    "ASSISTANT_ENV_VAR",
    "ASSISTANT_CLASS_ENV_VAR",
    "parse_assistant_choice",
    "DEFAULT_CAPABILITIES",
    "DEFAULT_ASSISTANT_SETTINGS",
    "load_assistant_settings",
    "save_assistant_settings",
    "assistant_mode",
    "assistant_enabled",
    "assistant_env",
    # old names
    "SUPPORT_AGENT_ENV_VAR",
    "SUPPORT_AGENT_CLASS_ENV_VAR",
    "parse_support_agent_choice",
    "DEFAULT_SUPPORT_AGENT_SETTINGS",
    "load_support_agent_settings",
    "save_support_agent_settings",
    "support_agent_mode",
    "support_agent_enabled",
]

ASSISTANT_ENV_VAR = "HANI2_ASSISTANT"
ASSISTANT_CLASS_ENV_VAR = "HANI2_ASSISTANT_CLASS"
#: old names of the environment variables, still read (the new ones win)
SUPPORT_AGENT_ENV_VAR = "HANI2_SUPPORT_AGENT"
SUPPORT_AGENT_CLASS_ENV_VAR = "HANI2_SUPPORT_AGENT_CLASS"
FILENAME = "assistant_settings.json"
#: old name of the settings file, still read under ``assistant_settings.json``
OLD_FILENAME = "support_agent_settings.json"


def assistant_env(new: str, old: str) -> str | None:
    """The value of the environment variable ``new``, else of its old name ``old``."""
    v = os.getenv(new)
    if v is not None and v.strip():
        return v
    return os.getenv(old)


try:
    from negmas_llm.common import DEFAULT_MODELS

    _default_model = DEFAULT_MODELS.get("ollama", "qwen3:4b-instruct")
except Exception:  # pragma: no cover
    _default_model = "qwen3:4b-instruct"

DEFAULT_CAPABILITIES: dict[str, bool] = {
    "chat": True,
    "toast": True,
    "pin": True,
    "tool_enable": True,
    "tool_visibility": True,
    "tool_order": True,
    "fill_offer": True,
    "fill_text": True,
    "submit_counter": True,
    "accept": True,
    "end": True,
    "highlight": True,
    "annotate": True,
    "layout": True,
    "panels": True,
    "tool_add": True,
    "tool_use": True,
    "private_info": True,
}

DEFAULT_SYSTEM_PROMPT = """You are the Assistant, a negotiation assistant embedded in a human-agent \
negotiation interface. You assist a single human negotiator during a live negotiation \
against an opponent.

You can chat with the human, send notifications, show / hide / enable / rearrange their \
analysis tools, highlight parts of the interface, attach short notes to issues, change the \
layout, show small interactive panels, and help them act in the negotiation (fill the offer \
fields, write the message to the opponent, and — depending on your granted autonomy — send a \
counter-offer, accept, or end the negotiation). Use the provided functions to take these \
actions; only the functions you are given are available in this session.

CRITICAL CONFIDENTIALITY RULE: any text you put in the message field is sent to the \
negotiation OPPONENT. Never reveal the human's utility values, weights, exact reserved value, \
or that a utility function exists. Speak qualitatively. The utility information is for your \
reasoning only.

You are ALWAYS given the current negotiation state with each user message: the issues, the \
opponent's current offer, the human's draft offer and message, the utilities and the recent \
history. Use it directly — NEVER ask the human for it. Call get_negotiation_state for a \
fresh snapshot mid-task. In the state, the partner_* fields and history entries \
by "partner" are the opponent's (wire names); call the other side "the opponent" with the human.

The participant's tools are part of your toolkit: list_tools shows them with a description, \
read_tool gives a tool's help text (what it does and how it works), what it currently shows \
and which inputs and buttons it has, and use_tool operates it (for example to find good offers or check how an offer scores). Prefer \
reading a relevant tool over guessing, and tell the participant which tool you used. With \
add_tool you can put a new tool on their screen (choose from list_tools → can_add) when it \
would help them right now.

You also have an always-visible status board; keep your current recommendation there with \
show_on_board. With pin_message you can pin a short message above or below the negotiation \
(the screen makes room for it) and remove it again with unpin_message.

In some negotiations you and the participant know different things: the state then has an \
"information" section saying who holds what. Utilities or the reserved value are missing from \
the state when you may not know them. Call get_private_information for what only you know \
(part of the participant's preferences, past negotiations in this scenario, market research) \
and use it to guide the participant; ask them about what only they know. Be concise and helpful."""

DEFAULT_ASSISTANT_SETTINGS: dict[str, Any] = {
    "mode": "on",
    "agent_class": None,
    "provider": "ollama",
    "model": _default_model,
    "api_key_env": "OPENAI_API_KEY",
    "api_base": None,
    "temperature": 0.3,
    "max_tokens": 2000,
    "max_tool_iterations": 10,
    "autonomy": "full",
    "capabilities": dict(DEFAULT_CAPABILITIES),
    "proactive": {"on_negotiation_started": False, "on_action_requested": False, "on_negotiation_ended": False},
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
    # tool classes (module:Class or path/to/file.py:Class) the agent may add
    "toolbox": [],
    # how the Assistant appears: style panel (opened from the header), persona (a movable
    # character in the corner that notifications come out of), both, or choice (the
    # participant picks; choice_default first)
    "presentation": {"style": "panel", "choice_default": "panel", "persona_movable": True},
}


def load_assistant_settings() -> dict:
    s = load_json_settings(FILENAME, DEFAULT_ASSISTANT_SETTINGS, old_names=(OLD_FILENAME,))
    caps = dict(DEFAULT_CAPABILITIES)
    caps.update(s.get("capabilities") or {})
    s["capabilities"] = caps
    if not s.get("system_prompt"):
        s["system_prompt"] = DEFAULT_SYSTEM_PROMPT
    klass = assistant_env(ASSISTANT_CLASS_ENV_VAR, SUPPORT_AGENT_CLASS_ENV_VAR)
    if klass and klass.strip():
        s["agent_class"] = klass.strip()
    return s


_MODES = {
    "on": "on", "1": "on", "true": "on", "yes": "on", "enabled": "on",
    "off": "off", "0": "off", "false": "off", "no": "off", "disabled": "off", "none": "off",
    "auto": "auto", "admin": "auto", "admins": "auto",
}


def parse_assistant_choice(value: str) -> tuple[str, str | None]:
    """Interpret an ``--assistant`` value: a mode (``on``, ``off``, ``auto``)
    or an Assistant class (``package.module:Class``, ``package.module.Class``
    or ``path/to/file.py:Class``), which means ``on`` with that class.
    Returns ``(mode, agent_class)``; raises ``ValueError`` for anything else."""
    v = (value or "").strip()
    if v.lower() in _MODES:
        return _MODES[v.lower()], None
    if ":" in v or "." in v:
        return "on", v
    raise ValueError(
        f"{value!r} is not an Assistant choice: use on, off, auto or a class such as mypkg.agents:MyAgent"
    )


def save_assistant_settings(settings: dict) -> None:
    save_json_settings(FILENAME, settings)


def assistant_mode(settings: dict | None = None) -> str:
    env = assistant_env(ASSISTANT_ENV_VAR, SUPPORT_AGENT_ENV_VAR)
    if env is not None and env.strip().lower() in _MODES:
        return _MODES[env.strip().lower()]
    if settings is None:
        settings = load_assistant_settings()
    mode = settings.get("mode")
    if isinstance(mode, str) and mode.strip().lower() in ("on", "off", "auto"):
        return mode.strip().lower()
    if settings.get("enabled") is not None:
        return "on" if settings.get("enabled") else "off"
    return "on"


def assistant_enabled(settings: dict | None = None, is_admin: bool = False) -> bool:
    mode = assistant_mode(settings)
    if mode == "on":
        return True
    if mode == "off":
        return False
    return bool(is_admin)


# old names
DEFAULT_SUPPORT_AGENT_SETTINGS = DEFAULT_ASSISTANT_SETTINGS
load_support_agent_settings = load_assistant_settings
save_support_agent_settings = save_assistant_settings
parse_support_agent_choice = parse_assistant_choice
support_agent_mode = assistant_mode
support_agent_enabled = assistant_enabled
