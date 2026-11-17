"""Finding, loading and generating negotiation scenarios.

Scenario types are the registered generators (see
:mod:`hani2.scenarios.registry`) plus any category folder found in the
scenarios directory. A category folder holds either a *pool* of numbered
scenarios (``0000Trade/``, ``0001Trade/``, …, as written by ``hani2
generate``) or plain named negmas scenario folders. Which types are used, and
in which order, comes from the active scenario set
(:mod:`hani2.scenario_sets`). Which side the participant plays is decided by
a role-assignment rule (:func:`assign_human`).
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import random
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from negmas import Scenario
from negmas.helpers.inout import load

from hani2 import scenario_sets
from hani2.config import DEFAULT_SCENARIOS, scenarios_dir
from hani2.display import DefaultOutcomeDisplay
from hani2.scenarios import registry

#: ``{type: maker}`` / ``{type: display}`` of the registered generators (live views of the registry).
MAKER_MAP: dict[str, Callable[[int], Scenario]] = registry.MAKERS
DISPLAY_MAP: dict[str, Any] = registry.DISPLAYS

#: Role-assignment rules (admin setting ``role_rule``).
ROLE_RULES = {
    "auto": "A role named human, else the scenario's suggested role, else the participant's index",
    "index": "The participant's index (admin setting)",
    "roles": "The first role listed in the preferred roles, else auto",
    "alternate": "Alternate between the roles from one negotiation to the next",
    "random": "A random role",
}
INFO_FILES = ("_info.yml", "_info.yaml", "_info.yaml.yml")
LAST_SCENARIO_FILE = "last_scenario.txt"


def base_dir() -> Path:
    """Scenario pool root: experiment → ``HANI_PROLIFIC_SCENARIOS_BASE`` → settings."""
    from hani2.config import experiment_dir

    exp = experiment_dir()
    if exp is not None and (exp / "scenarios").is_dir():
        return exp / "scenarios"
    env = (os.environ.get("HANI2_SCENARIOS_BASE") or os.environ.get("HANI_PROLIFIC_SCENARIOS_BASE") or "").strip()
    if env:
        return Path(env).expanduser()
    return scenarios_dir()


def scenario_order(scenario_set: str | None = None) -> list[str]:
    """Scenario types of the active set (or of ``scenario_set``), in order."""
    registry.load_plugins()
    types = scenario_sets.set_types(scenario_set)
    return types or ["Trade", "Island", "Grocery"]


def available_types(scenario_set: str | None = None) -> list[str]:
    """Every type HANI2 can serve: the active set's first, then the other
    registered generators, then any other category folder."""
    types = list(scenario_order(scenario_set))
    for t in MAKER_MAP:
        if t not in types:
            types.append(t)
    b = base_dir()
    if b.is_dir():
        for d in sorted(b.iterdir()):
            if d.is_dir() and not d.name.startswith((".", "_")) and d.name not in types:
                types.append(d.name)
    return types


def _is_scenario_dir(d: Path) -> bool:
    return any(f.suffix in (".yml", ".yaml") and not f.name.startswith("_") for f in d.iterdir() if f.is_file())


def _pool(type_: str) -> list[Path]:
    """Scenario folders of a category: numbered pool slots or named scenarios.
    A category folder that is itself a scenario counts as a one-scenario pool."""
    d = base_dir() / type_
    if not d.is_dir():
        return []
    subs = sorted(p for p in d.iterdir() if p.is_dir() and not p.name.startswith((".", "_")) and _is_scenario_dir(p))
    if subs:
        return subs
    return [d] if _is_scenario_dir(d) else []


def list_scenarios(type_: str) -> list[str]:
    return [p.name for p in _pool(type_)]


def _read_info(path: Path) -> dict:
    for name in INFO_FILES:
        f = path / name
        if f.exists():
            try:
                return load(f) or {}
            except Exception:
                return {}
    return {}


def _load_dir(path: Path) -> Scenario | None:
    try:
        s = Scenario.load(path)
    except Exception as e:  # pragma: no cover - defensive
        print(f"[hani2] cannot load scenario {path}: {e}")
        return None
    if s is None:
        return None
    s.info = _read_info(path) or (s.info or {})
    return s


def load_scenario(
    type_: str,
    index: int,
    load_existing: bool = True,
    generate_on_failure: bool = True,
    name: str | None = None,
) -> tuple[Scenario, dict[str, Any], str | None]:
    """Return ``(scenario, basic_info, scenario_dir)`` for slot ``index`` of ``type_``.

    With ``load_existing`` the pool is used (index wraps around); otherwise —
    or when the pool is empty — a scenario is generated on the fly.
    """
    pool = _pool(type_) if load_existing else []
    if name:
        named = [p for p in pool if p.name == name]
        pool = named or pool
    if pool:
        path = pool[0] if name and pool[0].name == name else pool[index % len(pool)]
        s = _load_dir(path)
        if s is not None:
            return s, dict(index=index, load_index=index % len(pool), load_path=str(path),
                           scenario_name=path.name, generated=False, scenario_type=type_), str(path)
        if not generate_on_failure or type_ not in MAKER_MAP:
            raise ValueError(f"Cannot load scenario from {path}")
    registry.load_plugins()
    if type_ not in MAKER_MAP:
        # Try the bundled sample scenario of that name.
        sample = DEFAULT_SCENARIOS / type_
        if sample.is_dir():
            s = _load_dir(sample)
            if s is not None:
                return s, dict(index=index, load_index=None, load_path=str(sample),
                               scenario_name=type_, generated=False, scenario_type=type_), None
        raise ValueError(f"Unknown scenario type {type_!r}")
    s = MAKER_MAP[type_](index)
    info = dict(index=index, load_index=None, load_path=None,
                scenario_name=s.outcome_space.name, generated=True, scenario_type=type_)
    return s, info, None


def display_for(scenario: Scenario, scenario_dir: str | None = None):
    """The OutcomeDisplay for a scenario: its own ``display.py`` first, then the
    built-in display matching the outcome-space name, else the default."""
    if scenario_dir:
        f = Path(scenario_dir) / "display.py"
        if f.exists():
            try:
                spec = importlib.util.spec_from_file_location(f"hani2_display_{abs(hash(str(f)))}", f)
                mod = importlib.util.module_from_spec(spec)  # type: ignore
                spec.loader.exec_module(mod)  # type: ignore
                for v in vars(mod).values():
                    if isinstance(v, type) and issubclass(v, DefaultOutcomeDisplay) and v is not DefaultOutcomeDisplay:
                        return v()
            except Exception as e:  # pragma: no cover
                print(f"[hani2] could not load {f}: {e}")
    name = str(getattr(scenario.outcome_space, "name", "") or "")
    base = name.split("/")[-1]
    if name in DISPLAY_MAP or base in DISPLAY_MAP:
        return DISPLAY_MAP.get(name) or DISPLAY_MAP[base]
    # the longest registered name the outcome-space name starts with
    for key in sorted(DISPLAY_MAP, key=len, reverse=True):
        if name.startswith(key) or base.startswith(key):
            return DISPLAY_MAP[key]
    if (scenario.info or {}).get("story") or (scenario.info or {}).get("issue_format"):
        from hani2.scenarios.story import StoryOutcomeDisplay

        return StoryOutcomeDisplay()
    return DefaultOutcomeDisplay()


def next_index(user_path: Path, advance: bool = True) -> int:
    f = user_path / LAST_SCENARIO_FILE
    try:
        idx = int(f.read_text().strip()) + 1 if f.exists() else 0
    except ValueError:
        idx = 0
    if advance:
        user_path.mkdir(parents=True, exist_ok=True)
        f.write_text(str(idx))
    return idx


def pid_type(pid: str, types: list[str] | None = None) -> str:
    types = types or scenario_order()
    h = int(hashlib.sha1(pid.encode()).hexdigest(), 16)
    return types[h % len(types)]


def pick_type(index: int, predefined_order: bool, scenario_set: str | None = None) -> str:
    order = scenario_order(scenario_set)
    if predefined_order:
        return order[index % len(order)]
    return random.choice(order)


def role_names(scenario: Scenario) -> list[str]:
    return [str(getattr(u, "name", "") or "") for u in scenario.ufuns]


def assign_human(
    scenario: Scenario,
    rule: str = "auto",
    human_index: int = 1,
    preferred_roles: list[str] | tuple[str, ...] = (),
    counter: int = 0,
) -> int:
    """The index of the negotiator the participant plays in ``scenario``.

    A role named ``human`` always goes to the participant: such scenarios are
    written from the participant's point of view (issue values like
    ``human``/``agent`` and "you get" texts refer to it). For the other
    scenarios ``rule`` decides (see :data:`ROLE_RULES`): ``auto`` (the
    scenario's suggested role, ``info["human_role"]``, else ``human_index``),
    ``index``, ``roles``
    (the first of ``preferred_roles`` the scenario has), ``alternate``
    (``counter`` modulo the number of roles) and ``random``."""
    names = role_names(scenario)
    n = len(names) or 1
    lowered = [x.lower() for x in names]
    rule = (rule or "auto").lower()
    if "human" in lowered:
        return lowered.index("human")
    suggested = str((scenario.info or {}).get("human_role") or "").lower()
    if rule == "index":
        return int(human_index) % n
    if rule == "random":
        return random.randrange(n)
    if rule == "alternate":
        return int(counter) % n
    if rule == "roles":
        for r in preferred_roles or ():
            if str(r).strip().lower() in lowered:
                return lowered.index(str(r).strip().lower())
    if suggested in lowered:
        return lowered.index(suggested)
    return int(human_index) % n


def copy_info(s: Scenario) -> dict:
    return deepcopy(s.info or {})
