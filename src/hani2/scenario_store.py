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


#: Key order of a written info file (the texts first, the hints last); other keys follow in their own order.
INFO_KEY_ORDER = ("Name", "title", "short_description", "long_description", "human_role", "role_descriptions",
                  "n_issue_columns", "issue_description", "issue_format", "split", "story", "hints")


def write_info(info: dict, path: Path | str) -> Path:
    """Write a scenario info dict as YAML that is easy to edit by hand:
    multi-line texts as ``|`` blocks, texts first and hints last. Reading it
    back gives the same dict."""
    import yaml

    class _Dumper(yaml.SafeDumper):
        pass

    def _str(dumper, s):
        return dumper.represent_scalar("tag:yaml.org,2002:str", s, style="|" if "\n" in s else None)

    _Dumper.add_representer(str, _str)
    ordered = {k: info[k] for k in INFO_KEY_ORDER if k in info}
    ordered.update({k: v for k, v in info.items() if k not in ordered})
    path = Path(path)
    path.write_text(yaml.dump(ordered, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=110),
                    encoding="utf-8")
    return path


def save_scenario(scenario: Scenario, folder: Path | str, info_name: str | None = None) -> Path:
    """Write ``scenario`` to ``folder`` in the on-disk format (``<Type>.yml``, one
    file per role, one info file) so that :func:`load_scenario` gives it back
    unchanged. Info files under the other accepted names are removed, so a stale
    copy can never shadow the new one. ``info_name`` keeps the folder's current
    info file name by default (``_info.yml`` for a new folder)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if info_name is None:
        info_name = next((n for n in INFO_FILES if (folder / n).exists()), "_info.yml")
    # negmas records where a scenario was loaded from; that is not part of the scenario
    os_ = scenario.outcome_space
    old_path = getattr(os_, "path", None)
    if old_path is not None:
        object.__setattr__(os_, "path", None)  # the outcome space is a frozen attrs class
    try:
        return _save(scenario, folder, info_name)
    finally:
        if old_path is not None:
            object.__setattr__(os_, "path", old_path)


def _save(scenario: Scenario, folder: Path, info_name: str) -> Path:
    # role files of a previous scenario with other role names would load as extra negotiators
    ser = scenario.serialize()
    keep = {f"{ser['domain']['name']}.yml"} | {f"{u['name']}.yml" for u in ser["ufuns"]}
    for f in folder.iterdir():
        if f.is_file() and f.suffix in (".yml", ".yaml") and not f.name.startswith("_") and f.name not in keep:
            f.unlink()
    scenario.dumpas(folder, save_info=False)
    if scenario.info:
        write_info(scenario.info, folder / info_name)
    for n in INFO_FILES:
        if (n != info_name or not scenario.info) and (folder / n).exists():
            (folder / n).unlink()
    return folder


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


# --------------------------------------------------------------------------- #
# Writing scenarios by hand                                                   #
# --------------------------------------------------------------------------- #
def scenario_folders(path: Path | str) -> list[Path]:
    """The scenario folders under ``path``: ``path`` itself when it is one, else
    its scenario subfolders (a category), else those of its categories."""
    p = Path(path).expanduser()
    if not p.is_dir():
        return []
    if _is_scenario_dir(p):
        return [p]
    out: list[Path] = []
    for d in sorted(x for x in p.iterdir() if x.is_dir() and not x.name.startswith((".", "_"))):
        out += [d] if _is_scenario_dir(d) else scenario_folders(d)
    return out


def same_scenario(a: Scenario, b: Scenario, tol: float = 1e-9) -> list[str]:
    """How two scenarios differ (empty when they are the same): issues and their
    options (with types), roles and their order, every utility of every outcome,
    reservation values and info."""
    diffs: list[str] = []
    ia, ib = a.outcome_space.issues, b.outcome_space.issues
    if [i.name for i in ia] != [i.name for i in ib]:
        return [f"issues {[i.name for i in ia]} != {[i.name for i in ib]}"]
    for x, y in zip(ia, ib):
        vx, vy = list(x.all), list(y.all)
        if vx != vy or [type(v) for v in vx] != [type(v) for v in vy]:
            diffs.append(f"options of {x.name}: {vx} != {vy}")
    if role_names(a) != role_names(b):
        diffs.append(f"roles {role_names(a)} != {role_names(b)}")
        return diffs
    outcomes = list(a.outcome_space.enumerate_or_sample(max_cardinality=200_000))
    for ua, ub in zip(a.ufuns, b.ufuns):
        if ua.reserved_value != ub.reserved_value:
            diffs.append(f"{ua.name}: reserved value {ua.reserved_value} != {ub.reserved_value}")
        bad = next((o for o in outcomes if abs(float(ua(o)) - float(ub(o))) > tol), None)
        if bad is not None:
            diffs.append(f"{ua.name}: utility of {bad} {float(ua(bad))} != {float(ub(bad))}")
    if (a.info or {}) != (b.info or {}):
        ia_, ib_ = a.info or {}, b.info or {}
        keys = sorted(k for k in set(ia_) | set(ib_) if ia_.get(k) != ib_.get(k))
        diffs.append(f"info differs in {keys}")
    return diffs


#: Info keys every scenario should have (the participant reads them).
REQUIRED_INFO = ("title", "short_description", "long_description")


def check_scenario(path: Path | str) -> tuple[Scenario | None, list[str], list[str]]:
    """Check a scenario folder written by hand or by a generator. Returns
    ``(scenario, errors, warnings)``: errors stop it from being served (or from
    loading back unchanged), warnings are texts or hints a participant would miss."""
    import tempfile

    p = Path(path).expanduser()
    errors: list[str] = []
    warnings: list[str] = []
    if not p.is_dir() or not _is_scenario_dir(p):
        return None, [f"{p} is not a scenario folder (no <Type>.yml)"], []
    s = _load_dir(p)
    if s is None:
        return None, [f"{p} cannot be loaded (see the message above)"], []
    names = [n for n in INFO_FILES if (p / n).exists()]
    if len(names) > 1:
        errors.append(f"more than one info file ({', '.join(names)}); only {names[0]} is read")
    if len(s.ufuns) < 2:
        errors.append(f"needs a utility function per role, found {len(s.ufuns)}")
    for u in s.ufuns:
        if u.outcome_space is None:
            errors.append(f"{u.name}: no outcome space")
    info = s.info or {}
    if not names:
        warnings.append("no _info.yaml: the participant sees no title, descriptions or hints")
    for k in REQUIRED_INFO:
        if names and not str(info.get(k) or "").strip():
            warnings.append(f"_info.yaml has no {k}")
    descs = info.get("issue_description") or {}
    for i in s.outcome_space.issues:
        if names and not descs.get(i.name):
            warnings.append(f"issue {i.name!r} has no issue_description")
    hints = info.get("hints") or {}
    for r in role_names(s):
        if names and not hints.get(r):
            warnings.append(f"role {r!r} has no hints (hani2 scenario check --fill-hints adds the computed ones)")
    for key in ("issue_description", "issue_format"):
        extra = sorted(set(info.get(key) or {}) - {i.name for i in s.outcome_space.issues})
        if extra:
            warnings.append(f"{key} names unknown issues {extra}")
    extra = sorted(set(hints) - set(role_names(s)))
    if extra:
        warnings.append(f"hints name unknown roles {extra}")
    if info.get("human_role") and str(info["human_role"]).lower() not in [r.lower() for r in role_names(s)]:
        errors.append(f"human_role {info['human_role']!r} is not one of the roles {role_names(s)}")
    for u in s.ufuns:
        try:
            lo, hi = u.minmax()
            if hi > 1 + 1e-6 or lo < -1e-6:
                warnings.append(f"{u.name}: utilities range over [{lo:.4g}, {hi:.4g}], not [0, 1]")
        except Exception:  # noqa: BLE001 - only a hint
            pass
    if not errors:
        with tempfile.TemporaryDirectory() as tmp:
            save_scenario(s, Path(tmp) / p.name)
            back = _load_dir(Path(tmp) / p.name)
            if back is None:
                errors.append("cannot be loaded after saving it again")
            else:
                errors += [f"changes when saved and loaded again: {d}" for d in same_scenario(s, back)]
        try:
            o = next(iter(s.outcome_space.enumerate_or_sample(max_cardinality=10)))
            display_for(s, str(p)).str(o, s, False, True)
        except Exception as e:  # noqa: BLE001
            errors.append(f"an offer cannot be shown: {e!r}")
    return s, errors, warnings
