"""Harness connections: a model call through an installed agent harness instead of the API.

A *harness* connection (provider ``claude-code``, ``codex`` or ``pi``) appears in the model
chains like any other connection (``{connection, model, params}``), has a probe and falls back
the same way. Two levels of call:

1. **Plain completion** (system prompt + messages → text) for every purpose: text extraction and
   generation, :class:`~hani2.tools.llm_tool.LLMTool`, the judge and LLM opponents. Calls reach the
   harness through litellm's custom-provider hook (:data:`LITELLM_PROVIDER`), so code that calls
   ``litellm.completion`` itself (negmas-llm opponents) works unchanged.
2. **HANI2's functions for the Assistant** (where the harness supports them safely; see
   :data:`CAPABILITIES`). The harness runs the turn; each function it calls is executed by the
   Assistant's :class:`~hani2.support_agent.tools.ToolDispatcher`, so capabilities, events and
   recordings apply as for any other model. A harness without safe function calling is skipped
   for the ``assistant`` purpose (it resolves as unavailable there).

Usage rules (checked 2026-11-18; the sources are in each adapter and in the models guide): only
API keys are allowed, never a personal subscription sign-in, and every harness runs isolated
(see :mod:`hani2.harness.base`). A harness may also be limited to some purposes
(:func:`refused_for`): Claude Code and Codex serve only the judge and the console's Test, never
participants (see :mod:`hani2.harness.claude_code` and :mod:`hani2.harness.codex`).
"""

from __future__ import annotations

from typing import Any

from hani2.harness.base import (
    Execute,
    HarnessAdapter,
    HarnessError,
    HarnessReply,
    HarnessTimeout,
    HarnessUnavailable,
    Limits,
)

#: the litellm provider name that routes a call to a harness
LITELLM_PROVIDER = "hani2_harness"
#: ``api_base`` of a harness call: names the connection (no secret travels through litellm)
_BASE = "hani2-harness://"

__all__ = [
    "LITELLM_PROVIDER",
    "Execute",
    "HarnessAdapter",
    "HarnessError",
    "HarnessReply",
    "HarnessTimeout",
    "HarnessUnavailable",
    "Limits",
    "adapter",
    "complete",
    "run_tools",
    "supports_tools",
]

_ADAPTERS: dict[str, HarnessAdapter] = {}


def _load() -> dict[str, HarnessAdapter]:
    if not _ADAPTERS:
        from hani2.harness.claude_code import ClaudeCode
        from hani2.harness.codex import Codex
        from hani2.harness.pi import Pi

        for a in (ClaudeCode(), Codex(), Pi()):
            _ADAPTERS[a.id] = a
    return _ADAPTERS


def adapter(c_or_id: Any) -> HarnessAdapter:
    hid = c_or_id if isinstance(c_or_id, str) else c_or_id.preset.harness
    a = _load().get(hid)
    if a is None:
        raise HarnessUnavailable(f"unknown harness {hid!r}")
    return a


def capability_table() -> list[dict[str, Any]]:
    """Every harness: what it supports, which sign-in it allows and why (the console, the docs)."""
    out = []
    for a in _load().values():
        assistant = a.tools and (a.purposes is None or "assistant" in a.purposes)
        out.append({"id": a.id, "label": a.label, "completion": True, "assistant_tools": assistant,
                    "function_calling": a.tools,
                    "purposes": list(a.purposes) if a.purposes is not None else None,
                    "auth": ["api_key", "api_key_env"] + (["none"] if "ollama" in a.upstreams else []),
                    "auth_reason": a.auth_reason, "upstreams": {k: v[1] for k, v in a.upstreams.items()},
                    "default_upstream": a.default_upstream, "extra": a.extra, "sources": list(a.sources)})
    return out


def capabilities() -> dict[str, dict[str, Any]]:
    """``{harness: {completion, assistant_tools, purposes}}``, from the adapters."""
    return {a.id: {"completion": True, "function_calling": a.tools,
                   "assistant_tools": a.tools and (a.purposes is None or "assistant" in a.purposes),
                   "purposes": list(a.purposes) if a.purposes is not None else None} for a in _load().values()}


def supports_tools(c: Any) -> bool:
    return adapter(c).tools


def refused_for(c: Any, purpose: str) -> str:
    """Why ``c`` may not serve ``purpose`` (``""``: it may)."""
    a = adapter(c)
    if purpose == "assistant" and not a.tools:
        return f"{a.label} cannot call the Assistant's functions safely (completion only)"
    if a.purposes is not None and purpose not in a.purposes:
        return (f"{a.label} may serve only {', '.join(a.purposes)} here, not {purpose}: {a.auth_reason}")
    return ""


# --------------------------------------------------------------------------- #
# Connections                                                                  #
# --------------------------------------------------------------------------- #
def _err(msg: str) -> Exception:
    from hani2.connections import ConnectionError_

    return ConnectionError_(msg)


def upstream_of(c: Any) -> str:
    a = adapter(c)
    return c.upstream or a.default_upstream


def check_connection(c: Any) -> None:
    """Refuse a harness connection whose sign-in or upstream provider is not allowed."""
    a = adapter(c)
    up = upstream_of(c)
    if up not in a.upstreams:
        raise _err(f"{a.label} cannot call {up!r} here; allowed: {', '.join(a.upstreams)} "
                   f"(API keys or a local server only: {a.auth_reason})")
    local = up == "ollama"
    if c.auth == "subscription":
        raise _err(f"{a.label}: subscription sign-in is not allowed. {a.auth_reason}")
    if local and c.auth != "none":
        raise _err(f"{a.label} with a local Ollama server needs no key (auth none)")
    if not local and c.auth not in ("api_key", "api_key_env"):
        raise _err(f"{a.label} signs in with an API key only (auth api_key or api_key_env). {a.auth_reason}")
    if not c.upstream:
        c.upstream = up
    if c.auth == "api_key_env" and not c.api_key_env:
        c.api_key_env = a.upstreams[up][0]
    if c.base_url and not local:
        raise _err(f"{a.label}: a base URL is allowed only for a local Ollama server")


def api_key_env(c: Any) -> str:
    """The variable the harness reads its key from (the upstream's usual one)."""
    return adapter(c).upstreams[upstream_of(c)][0]


def has_credentials(c: Any) -> tuple[bool, str]:
    """Whether the harness is installed and the connection has its key (no network)."""
    from hani2 import connections as conns

    a = adapter(c)
    st = a.status()
    if not st.get("found"):
        return False, f"{a.label}: {st.get('error') or 'not installed'}"
    if upstream_of(c) == "ollama":
        return True, ""
    if not conns.api_key(c):
        if c.auth == "api_key_env":
            return False, f"the environment variable {c.api_key_env} is not set"
        return False, "no API key stored"
    return True, ""


def probe(c: Any, model: str) -> Any:
    """Installed, a key and an allowed model; nothing is sent (a call costs money and time)."""
    from hani2 import connections as conns

    ok, why = has_credentials(c)
    if not ok:
        return conns.Probe(False, why)
    if model:
        bad = adapter(c).check_model(c, model)
        if bad:
            return conns.Probe(False, bad)
    return conns.Probe(True, verified=False)


def default_model(c: Any) -> str:
    """The model the console's Test uses for ``c`` (by its upstream provider)."""
    a = adapter(c)
    return a.default_models.get(upstream_of(c)) or (c.preset.examples[0] if c.preset.examples else "")


def public_info(c: Any) -> dict[str, Any]:
    a = adapter(c)
    return {"id": a.id, "status": a.status(), "assistant_tools": not refused_for(c, "assistant"),
            "purposes": list(a.purposes) if a.purposes is not None else None, "upstream": upstream_of(c),
            "default_model": default_model(c), "auth_reason": a.auth_reason}


def api_base_for(c: Any) -> str:
    return f"{_BASE}{c.name}"


def connection_from_base(api_base: str | None) -> Any:
    from hani2 import connections as conns

    if not api_base or not str(api_base).startswith(_BASE):
        raise HarnessUnavailable("a harness call without its connection")
    name = str(api_base)[len(_BASE):]
    c = conns.get(name)
    if c is None or not c.preset.harness:
        raise HarnessUnavailable(f"no harness connection named {name!r}")
    if c.disabled:
        raise HarnessUnavailable(c.disabled)
    return c


def secret_for(c: Any) -> str | None:
    """The key the child gets (``None`` for a local server)."""
    from hani2 import connections as conns

    if upstream_of(c) == "ollama":
        return None
    key = conns.api_key(c)
    if not key:
        raise HarnessUnavailable(f"{c.name}: no API key (a harness signs in with an API key only)")
    return key


def home_of(c: Any) -> Any:
    """The connection's isolated folder (``settings/secrets/<name>/harness``, 0700)."""
    from hani2 import connections as conns
    from hani2.harness.base import private_dir

    return private_dir(conns.token_dir(c.name) / "harness")


# --------------------------------------------------------------------------- #
# Calls                                                                        #
# --------------------------------------------------------------------------- #
def complete(c: Any, model: str, messages: list[dict], params: dict[str, Any] | None = None) -> HarnessReply:
    a = adapter(c)
    bad = a.check_model(c, model)
    if bad:
        raise HarnessUnavailable(bad)
    return a.complete(c, model, messages, dict(params or {}))


def run_tools(c: Any, model: str, messages: list[dict], tools: list[dict], execute: Execute,
              params: dict[str, Any] | None = None) -> HarnessReply:
    a = adapter(c)
    if not a.tools:
        raise HarnessUnavailable(f"{a.label} does not call HANI2's functions (completion only)")
    bad = a.check_model(c, model)
    if bad:
        raise HarnessUnavailable(bad)
    return a.run_tools(c, model, messages, tools, execute, dict(params or {}))


# --------------------------------------------------------------------------- #
# litellm: route ``hani2_harness/<model>`` calls to the harness                #
# --------------------------------------------------------------------------- #
_INSTALLED = False


def install_litellm_provider() -> None:
    """Register :data:`LITELLM_PROVIDER` with litellm (once)."""
    global _INSTALLED
    if _INSTALLED:
        return
    import litellm

    from hani2.harness.litellm_provider import HarnessLLM

    if not any(item.get("provider") == LITELLM_PROVIDER for item in litellm.custom_provider_map):
        litellm.custom_provider_map = [*litellm.custom_provider_map,
                                       {"provider": LITELLM_PROVIDER, "custom_handler": HarnessLLM()}]
    _INSTALLED = True
