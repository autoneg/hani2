"""Settings of the Negotiation Support Agent (``settings/support_agent_settings.json``).

Who gets the assistant is resolved, highest precedence first, from the
``HANI2_SUPPORT_AGENT`` environment variable (set by ``hani2 --support-agent``),
then the ``mode`` setting: ``on`` (everyone), ``off`` (nobody) or ``auto``
(admins only).
"""

from __future__ import annotations

import os
from typing import Any

from hani2.config import load_json_settings, save_json_settings

__all__ = [
    "SUPPORT_AGENT_ENV_VAR",
    "DEFAULT_CAPABILITIES",
    "DEFAULT_SUPPORT_AGENT_SETTINGS",
    "load_support_agent_settings",
    "save_support_agent_settings",
    "support_agent_mode",
    "support_agent_enabled",
]

SUPPORT_AGENT_ENV_VAR = "HANI2_SUPPORT_AGENT"
FILENAME = "support_agent_settings.json"

try:
    from negmas_llm.common import DEFAULT_MODELS

    _default_model = DEFAULT_MODELS.get("ollama", "qwen3:4b-instruct")
except Exception:  # pragma: no cover
    _default_model = "qwen3:4b-instruct"

DEFAULT_CAPABILITIES: dict[str, bool] = {
    "chat": True,
    "toast": True,
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
}

DEFAULT_SYSTEM_PROMPT = """You are a Negotiation Support Agent embedded in a human-agent \
negotiation interface. You assist a single human negotiator during a live negotiation \
against a partner.

You can chat with the human, send notifications, show / hide / enable / rearrange their \
analysis tools, highlight parts of the interface, attach short notes to issues, change the \
layout, show small interactive panels, and help them act in the negotiation (fill the offer \
fields, write the message to the partner, and — depending on your granted autonomy — send a \
counter-offer, accept, or end the negotiation). Use the provided functions to take these \
actions; only the functions you are given are available in this session.

CRITICAL CONFIDENTIALITY RULE: any text you put in the message field is sent to the \
negotiation PARTNER. Never reveal the human's utility values, weights, exact reserved value, \
or that a utility function exists. Speak qualitatively. The utility information is for your \
reasoning only.

You are ALWAYS given the current negotiation state with each user message: the issues, the \
partner's current offer, the human's draft offer and message, the utilities and the recent \
history. Use it directly — NEVER ask the human for it. Call get_negotiation_state for a \
fresh snapshot mid-task.

You also have an always-visible status board; keep your current recommendation there with \
show_on_board. Be concise and helpful."""

DEFAULT_SUPPORT_AGENT_SETTINGS: dict[str, Any] = {
    "mode": "on",
    "agent_class": None,
    "provider": "ollama",
    "model": _default_model,
    "api_key_env": "OPENAI_API_KEY",
    "api_base": None,
    "temperature": 0.3,
    "max_tokens": 2000,
    "max_tool_iterations": 6,
    "autonomy": "full",
    "capabilities": dict(DEFAULT_CAPABILITIES),
    "proactive": {"on_negotiation_started": False, "on_action_requested": False, "on_negotiation_ended": False},
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
}


def load_support_agent_settings() -> dict:
    s = load_json_settings(FILENAME, DEFAULT_SUPPORT_AGENT_SETTINGS)
    caps = dict(DEFAULT_CAPABILITIES)
    caps.update(s.get("capabilities") or {})
    s["capabilities"] = caps
    if not s.get("system_prompt"):
        s["system_prompt"] = DEFAULT_SYSTEM_PROMPT
    return s


def save_support_agent_settings(settings: dict) -> None:
    save_json_settings(FILENAME, settings)


def support_agent_mode(settings: dict | None = None) -> str:
    env = os.getenv(SUPPORT_AGENT_ENV_VAR)
    if env is not None:
        v = env.strip().lower()
        if v in ("on", "1", "true", "yes", "enabled"):
            return "on"
        if v in ("off", "0", "false", "no", "disabled"):
            return "off"
        if v in ("auto", "admin", "admins"):
            return "auto"
    if settings is None:
        settings = load_support_agent_settings()
    mode = settings.get("mode")
    if isinstance(mode, str) and mode.strip().lower() in ("on", "off", "auto"):
        return mode.strip().lower()
    if settings.get("enabled") is not None:
        return "on" if settings.get("enabled") else "off"
    return "on"


def support_agent_enabled(settings: dict | None = None, is_admin: bool = False) -> bool:
    mode = support_agent_mode(settings)
    if mode == "on":
        return True
    if mode == "off":
        return False
    return bool(is_admin)
