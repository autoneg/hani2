"""Which tools a session gets.

Tools come from three places, in this order:

1. the built-in tools (:mod:`hani2.tools.builtin`);
2. packages exposing an entry point in the ``hani2.tools`` group
   (``my_tool = "my_package.tools:MyTool"``);
3. ``settings/env.json`` → ``"tools": {"extra": ["module:Class", ...]}``.

``"tools": {"disabled": ["Trace", ...]}`` removes tools by name and
``"tools": {"overrides": {"Trace": {"pane": "side", "enabled": true}}}``
changes the defaults (``pane``, ``timing``, ``enabled``, ``admin_only``,
``guest``, ``order``) of any tool.
"""

from __future__ import annotations

import importlib
import traceback
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import TYPE_CHECKING, Any

from hani2.config import get_env
from hani2.tools.base import Tool

if TYPE_CHECKING:  # pragma: no cover
    from hani2.session import NegotiationSession


@dataclass
class ToolSpec:
    cls: type[Tool]
    name: str
    pane: str
    timing: str
    enabled: bool
    admin_only: bool
    guest: bool
    order: int
    at_front: bool = False


def builtin_tool_classes() -> list[type[Tool]]:
    from hani2.tools import builtin as b

    return [
        b.PreferencesTool,
        b.ScenarioInfoTool,
        b.UserResultsTool,
        b.ValueHistogramTool,
        b.UtilityPlotTool,
        b.OutcomePlotTool,
        b.TraceTool,
        b.UtilitySelectorTool,
        b.ResponseGeneratorTool,
        b.RandomOutcomeTool,
        b.AllResultsTool,
        b.AgentPreferencesTool,
    ]


def import_tool(spec: str) -> type[Tool]:
    if ":" in spec:
        mod, _, attr = spec.partition(":")
    else:
        mod, _, attr = spec.rpartition(".")
    obj = getattr(importlib.import_module(mod), attr)
    if not (isinstance(obj, type) and issubclass(obj, Tool)):
        raise TypeError(f"{spec} is not a hani2 Tool subclass")
    return obj


def discover_tool_classes() -> list[type[Tool]]:
    classes = list(builtin_tool_classes())
    try:
        for ep in entry_points(group="hani2.tools"):
            try:
                obj = ep.load()
                if isinstance(obj, type) and issubclass(obj, Tool) and obj not in classes:
                    classes.append(obj)
            except Exception:
                traceback.print_exc()
    except Exception:  # pragma: no cover
        pass
    cfg = get_env("tools", {}) or {}
    for spec in cfg.get("extra", []) or []:
        try:
            obj = import_tool(str(spec))
            if obj not in classes:
                classes.append(obj)
        except Exception as e:  # noqa: BLE001
            print(f"[hani2] could not load tool {spec!r}: {e}")
    return classes


def tool_specs() -> list[ToolSpec]:
    cfg = get_env("tools", {}) or {}
    disabled = {str(x).lower() for x in cfg.get("disabled", []) or []}
    overrides: dict[str, dict[str, Any]] = cfg.get("overrides", {}) or {}
    specs = []
    for cls in discover_tool_classes():
        name = cls.name or cls.__name__
        if name.lower() in disabled:
            continue
        o = overrides.get(name, {})
        specs.append(
            ToolSpec(
                cls=cls,
                name=name,
                pane=o.get("pane", cls.pane),
                timing=o.get("timing", cls.timing),
                enabled=bool(o.get("enabled", cls.enabled)),
                admin_only=bool(o.get("admin_only", cls.admin_only)),
                guest=bool(o.get("guest", cls.guest)),
                order=int(o.get("order", cls.order)),
                at_front=bool(o.get("at_front", cls.order <= 1)),
            )
        )
    return specs


def build_tools(session: "NegotiationSession", timing: str) -> list[tuple[ToolSpec, Tool]]:
    out = []
    for spec in tool_specs():
        if spec.timing != timing:
            continue
        if spec.admin_only and not session.is_admin:
            continue
        if not spec.guest and session.mode == "guest":
            continue
        try:
            tool = spec.cls(session.ss, enabled=spec.enabled)
            tool.name = spec.name
        except Exception:
            traceback.print_exc()
            continue
        out.append((spec, tool))
    return out
