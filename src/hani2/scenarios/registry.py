"""The registry of scenario types that HANI2 can generate.

A scenario type has a *maker* (``maker(index) -> negmas.Scenario``, called for
every fresh scenario) and an optional *display* (how an offer is written as
text). The built-in types are registered here; your own types are registered
from Python files:

* every ``*.py`` file in ``<settings>/scenario_types/`` (and
  ``<experiment>/scenario_types/`` when an experiment is active), and
* the files or modules listed in ``HANI2_SCENARIO_TYPES`` (comma-separated;
  ``hani2 run --scenario-types`` sets it).

Such a file registers its types in one of three ways: a module-level
``STORIES`` list of :class:`~hani2.scenarios.story.Story` objects, a
``SCENARIO_TYPES`` dict ``{name: maker}``, or calls to :func:`register` /
:func:`register_story`.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Callable

from negmas import Scenario

from .story import Story, StoryOutcomeDisplay, make_story_scenario

__all__ = ["ScenarioType", "register", "register_story", "unregister", "get", "names", "MAKERS", "DISPLAYS", "load_plugins"]


@dataclass
class ScenarioType:
    name: str
    maker: Callable[[int], Scenario]
    display: Any = None
    story: Story | None = None
    builtin: bool = False


_TYPES: dict[str, ScenarioType] = {}
#: ``{type: maker}`` and ``{type: display}`` views, kept in step with the registry
#: (``hani2.scenario_store.MAKER_MAP`` / ``DISPLAY_MAP`` are these dicts).
MAKERS: dict[str, Callable[[int], Scenario]] = {}
DISPLAYS: dict[str, Any] = {}


def register(name: str, maker: Callable[[int], Scenario], display: Any = None, *, replace: bool = True,
             story: Story | None = None, builtin: bool = False) -> ScenarioType:
    """Register (or replace) a scenario type. ``name`` is also the folder name
    of its pool in the scenarios directory, and should be the outcome-space
    name of the scenarios it makes (that is how a saved scenario finds its
    display again)."""
    if name in _TYPES and not replace:
        raise ValueError(f"scenario type {name!r} is already registered")
    t = ScenarioType(name, maker, display, story, builtin)
    _TYPES[name] = t
    MAKERS[name] = maker
    if display is not None:
        DISPLAYS[name] = display
    else:
        DISPLAYS.pop(name, None)
    return t


def register_story(story: Story, *, replace: bool = True, builtin: bool = False) -> ScenarioType:
    """Register a :class:`Story` as a scenario type."""
    return register(story.type, partial(make_story_scenario, story), StoryOutcomeDisplay(), replace=replace,
                    story=story, builtin=builtin)


def unregister(name: str) -> None:
    """Remove a scenario type (no error if it is not registered)."""
    _TYPES.pop(name, None)
    MAKERS.pop(name, None)
    DISPLAYS.pop(name, None)


def get(name: str) -> ScenarioType | None:
    return _TYPES.get(name)


def names() -> list[str]:
    return list(_TYPES)


def _register_builtins() -> None:
    from . import anl, iago, mit, pie
    from .grocery import GroceryOutcomeDisplay, make_grocery_scenario
    from .island import IslandOutcomeDisplay, make_island_scenario
    from .trade import TradeOutcomeDisplay, make_trade_scenario

    register("Trade", make_trade_scenario, TradeOutcomeDisplay(), builtin=True)
    register("Island", make_island_scenario, IslandOutcomeDisplay(), builtin=True)
    register("Grocery", make_grocery_scenario, GroceryOutcomeDisplay(), builtin=True)
    for mod in (mit, pie, anl, iago):
        for story in mod.STORIES:
            register_story(story, builtin=True)


# --------------------------------------------------------------------------- #
# Plugins                                                                     #
# --------------------------------------------------------------------------- #
_LOADED: set[str] = set()


def _import(spec: str):
    p = Path(spec).expanduser()
    if p.suffix == ".py" or p.exists():
        name = f"hani2_scenario_types_{abs(hash(str(p.resolve())))}"
        s = importlib.util.spec_from_file_location(name, p)
        if s is None or s.loader is None:
            raise ImportError(f"cannot import {p}")
        mod = importlib.util.module_from_spec(s)
        s.loader.exec_module(mod)
        return mod
    return importlib.import_module(spec)


def _plugin_specs() -> list[str]:
    from hani2.config import experiment_dir, settings_dir

    specs: list[str] = []
    dirs = [settings_dir() / "scenario_types"]
    exp = experiment_dir()
    if exp is not None:
        dirs.append(exp / "scenario_types")
    for d in dirs:
        if d.is_dir():
            specs += [str(f) for f in sorted(d.glob("*.py")) if not f.name.startswith("_")]
    specs += [s.strip() for s in (os.environ.get("HANI2_SCENARIO_TYPES") or "").split(",") if s.strip()]
    return specs


def load_plugins(force: bool = False) -> list[str]:
    """Import the user's scenario-type files (once each). Returns the type
    names they registered. A broken file is reported and skipped."""
    added: list[str] = []
    for spec in _plugin_specs():
        if spec in _LOADED and not force:
            continue
        _LOADED.add(spec)
        before = set(_TYPES)
        try:
            mod = _import(spec)
            for story in getattr(mod, "STORIES", []) or []:
                register_story(story)
            for name, maker in (getattr(mod, "SCENARIO_TYPES", {}) or {}).items():
                register(name, maker)
        except Exception as e:  # noqa: BLE001 - a bad plugin must not stop the server
            print(f"[hani2] could not load scenario types from {spec}: {e!r}")
            continue
        added += [n for n in _TYPES if n not in before]
    return added


_register_builtins()
