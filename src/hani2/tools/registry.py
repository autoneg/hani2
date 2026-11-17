"""Which tools a session gets.

Tools come from these places, in this order:

1. the built-in tools (:mod:`hani2.tools.builtin`);
2. packages exposing an entry point in the ``hani2.tools`` group
   (``my_tool = "my_package.tools:MyTool"``);
3. classes decorated with :func:`register_tool` (or passed to it);
4. the **tools folders**: every ``*.py`` file in ``$HANI2_HOME/tools``, in the
   folders listed in ``env.json`` → ``"tools": {"paths": [...]}`` and in the
   folders and ``.py`` files given to ``hani2 --tools`` (``HANI2_TOOLS``) or
   listed in ``tools.extra``. Each file contributes the :class:`Tool`
   subclasses it defines (or those listed in its ``TOOLS`` variable), except
   classes whose name starts with ``_`` or that set ``abstract = True``
   (helper base classes). Files are re-read when they change, so a new
   session picks up an edited tool without restarting the server;
5. ``settings/env.json`` → ``"tools": {"extra": ["module:Class", ...]}`` and
   the classes given to ``hani2 --tools`` (``HANI2_TOOLS``);
   ``path/to/file.py:Class`` works too.

A tool whose ``timing`` is ``"agent"`` never appears on its own; a support
agent adds it when it chooses (see :func:`addable_tool_specs`).

``"tools": {"disabled": ["Trace", ...]}`` removes tools by name and
``"tools": {"overrides": {"Trace": {"pane": "side", "enabled": true}}}``
changes the defaults (``pane``, ``timing``, ``enabled``, ``admin_only``,
``guest``, ``order``, ``at_front``) of any tool. Names are case-insensitive.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import os
import sys
import threading
import traceback
from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hani2.config import get_env, home
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
        b.NegotiationPlotTool,
        b.OutcomePlotTool,
        b.TraceTool,
        b.UtilitySelectorTool,
        b.ResponseGeneratorTool,
        b.RandomOutcomeTool,
        b.AllResultsTool,
        b.OpponentPreferencesTool,
    ]


_REGISTERED: list[type[Tool]] = []
_FILE_CACHE: dict[str, tuple[float, list[type[Tool]]]] = {}
_FILE_LOCK = threading.Lock()
#: Where each discovered tool class came from (``"built-in"``, a file path ...).
SOURCES: dict[type[Tool], str] = {}


def register_tool(cls: type[Tool]) -> type[Tool]:
    """Make a tool class available to every new session. Usable as a decorator::

        from hani2.tools import Tool, register_tool, ui

        @register_tool
        class Hello(Tool):
            def view(self):
                return [ui.markdown("Hello!")]

    The module that defines the class must be imported before sessions start
    (for example from your own launcher script, or because it is in a tools
    folder, where decorating is optional).
    """
    if not (isinstance(cls, type) and issubclass(cls, Tool)):
        raise TypeError(f"{cls!r} is not a hani2 Tool subclass")
    if cls not in _REGISTERED:
        _REGISTERED.append(cls)
    return cls


def tools_dir() -> Path:
    """The default tools folder: ``$HANI2_HOME/tools``."""
    return home() / "tools"


def is_tool_path(entry: str) -> bool:
    """Whether a ``--tools`` / ``tools.extra`` entry names a folder or a whole
    ``.py`` file (every tool in it) rather than one class."""
    e = str(entry).strip()
    if not e or ".py:" in e:
        return False
    return e.endswith(".py") or Path(e).expanduser().is_dir()


def _extra_entries() -> list[str]:
    cfg = get_env("tools", {}) or {}
    cmdline = [x.strip() for x in (os.environ.get("HANI2_TOOLS") or "").split(",") if x.strip()]
    return [str(x).strip() for x in list(cfg.get("extra", []) or []) + cmdline if str(x).strip()]


def tool_paths() -> list[Path]:
    """Every folder or file searched for tools (existing or not)."""
    paths = [tools_dir()]
    cfg = get_env("tools", {}) or {}
    paths += [Path(str(p)).expanduser() for p in (cfg.get("paths", []) or [])]
    paths += [Path(e).expanduser() for e in _extra_entries() if is_tool_path(e)]
    out: list[Path] = []
    for p in paths:
        if p not in out:
            out.append(p)
    return out


def _tool_files(path: Path) -> list[Path]:
    if path.is_file() and path.suffix == ".py":
        return [path]
    if path.is_dir():
        return sorted(f for f in path.glob("*.py") if not f.name.startswith(("_", ".")) and not f.name.startswith("test_"))
    return []


def _classes_in(module) -> list[type[Tool]]:
    listed = getattr(module, "TOOLS", None)
    if listed is not None:
        return [c for c in listed if isinstance(c, type) and issubclass(c, Tool)]
    return [
        c for _, c in inspect.getmembers(module, inspect.isclass)
        if issubclass(c, Tool) and c.__module__ == module.__name__ and not c.__name__.startswith("_")
        and not c.__dict__.get("abstract", False)
    ]


def load_tool_file(path: str | Path) -> list[type[Tool]]:
    """Import a Python file and return the tool classes it defines.

    The result is cached until the file changes; a changed file is imported
    again, so new sessions get the new version.
    """
    p = Path(path).expanduser().resolve()
    mtime = p.stat().st_mtime
    with _FILE_LOCK:
        hit = _FILE_CACHE.get(str(p))
        if hit and hit[0] == mtime:
            return hit[1]
        name = f"hani2_user_tools.{p.stem}_{abs(hash(str(p))) % 10**8}"
        spec = importlib.util.spec_from_file_location(name, p)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot import {p}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        folder = str(p.parent)
        added = folder not in sys.path
        if added:  # let the file import its neighbours
            sys.path.insert(0, folder)
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
        finally:
            if added:
                try:
                    sys.path.remove(folder)
                except ValueError:
                    pass
        classes = _classes_in(module)
        _FILE_CACHE[str(p)] = (mtime, classes)
        return classes


def import_tool(spec: str) -> type[Tool]:
    """Load a tool class from ``module:Class``, ``module.Class`` or
    ``path/to/file.py:Class`` (a file is re-read when it changes)."""
    spec = str(spec).strip()
    if ".py:" in spec:
        path, _, attr = spec.rpartition(":")
        for c in load_tool_file(path):
            if c.__name__ == attr:
                return c
        raise AttributeError(f"{path} has no tool class {attr!r}")
    from hani2.support_agent.runtime import load_class

    obj = load_class(spec)
    if not (isinstance(obj, type) and issubclass(obj, Tool)):
        raise TypeError(f"{spec} is not a hani2 Tool subclass")
    return obj


_REPORTED: set[str] = set()


def _report(key: str, msg: str) -> None:
    if key not in _REPORTED:  # discovery runs per session: say it once
        _REPORTED.add(key)
        print(msg)


def discover_tool_classes() -> list[type[Tool]]:
    classes: list[type[Tool]] = []
    names: dict[str, type[Tool]] = {}

    def add(obj: type[Tool], source: str) -> None:
        if obj in classes:
            return
        name = (obj.name or obj.__name__).lower()
        if name in names:
            _report(f"dup:{name}:{source}", f"[hani2] tool {obj.name or obj.__name__!r} from {source} ignored: "
                    f"a tool with that name already comes from {SOURCES.get(names[name], '?')}")
            return
        classes.append(obj)
        names[name] = obj
        SOURCES[obj] = source

    for c in builtin_tool_classes():
        add(c, "built-in")
    try:
        for ep in entry_points(group="hani2.tools"):
            try:
                obj = ep.load()
                if isinstance(obj, type) and issubclass(obj, Tool):
                    add(obj, f"entry point {ep.name}")
            except Exception:
                traceback.print_exc()
    except Exception:  # pragma: no cover
        pass
    for c in list(_REGISTERED):
        add(c, f"register_tool ({c.__module__})")
    for path in tool_paths():
        for f in _tool_files(path):
            try:
                for c in load_tool_file(f):
                    add(c, str(f))
            except Exception as e:  # noqa: BLE001 - a broken file must not break the server
                _report(f"file:{f}:{f.stat().st_mtime}", f"[hani2] could not load tools from {f}: {e}")
    for spec in _extra_entries():
        if is_tool_path(spec):
            continue  # loaded with the tool folders above
        try:
            add(import_tool(spec), f"tools.extra / --tools ({spec})")
        except Exception as e:  # noqa: BLE001
            _report(f"extra:{spec}", f"[hani2] could not load tool {spec!r}: {e}")
    return classes


def tool_specs() -> list[ToolSpec]:
    cfg = get_env("tools", {}) or {}
    disabled = {str(x).lower() for x in cfg.get("disabled", []) or []}
    overrides: dict[str, dict[str, Any]] = {str(k).lower(): v for k, v in (cfg.get("overrides", {}) or {}).items()}
    specs = []
    for cls in discover_tool_classes():
        name = cls.name or cls.__name__
        if name.lower() in disabled:
            continue
        o = overrides.get(name.lower(), {})
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


def addable_tool_specs(session: "NegotiationSession") -> list[ToolSpec]:
    """Registered tools a support agent may add to ``session`` now: tools not
    already present that this participant is allowed to have (admin-only and
    guest rules and ``tools.disabled`` still apply)."""
    present = {t.name.lower() for t in session.tools}
    out = []
    for spec in tool_specs():
        if spec.name.lower() in present:
            continue
        if spec.admin_only and not session.is_admin:
            continue
        if not spec.guest and session.mode == "guest":
            continue
        out.append(spec)
    return out
