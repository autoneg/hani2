"""Tool groups, the tools a study offers, and where tools go in each view.

Configured in ``tools.yaml``, read from the settings folder, then the project
folder, then the study folder (a later layer wins)::

    groups:                          # named groups of tools (and of other groups)
      core: ["@information", "Utility-based Selector"]
      plots: [visualization, Trace]  # a bare word: a group when one has that name, else a tool
    offer: ["@core", "@plots"]       # the tools sessions get (default: every tool)
    placement:                       # per tool: all views, or per view
      Trace: {pane: side}
      Value Histogram:
        full: {pane: lower}
        simple: {visible: false}

Group entries follow :mod:`hani2.composition`: ``@name`` / ``:name`` is a group,
a bare word is a group when one has that name, else a tool name (names are
case-insensitive). The built-in groups come from the tools themselves:
every tool's ``groups`` attribute, plus ``admin`` (admin-only tools),
``assistant`` (timing ``"agent"``: added by the Assistant) and ``all``.

Layers: ``groups`` merge by name (a later layer replaces a group of the same
name), ``offer`` comes from the most specific layer that sets it, and
``placement`` merges per tool, per view and per key.

Placement of a tool in view ``v`` (``full``, ``simple``, ``focus``) is, later
wins: its ``pane`` and ``order`` and visible, the class's ``placement[v]``,
env.json ``tools.overrides`` (``pane``, ``order``, ``placement``), then the
``tools.yaml`` placement of the layers.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

import yaml

from hani2 import composition

__all__ = ["FILE", "VIEWS", "PANES", "BUILTIN_GROUPS", "layer_files", "read_file", "load_config", "tool_groups_of",
           "builtin_groups", "all_groups", "expand", "offered", "resolve_placement", "check_placement",
           "write_group", "delete_group", "write_placement", "write_offer"]

FILE = "tools.yaml"
VIEWS = ("full", "simple", "focus")
PANES = ("upper", "lower", "side")
PLACEMENT_KEYS = ("pane", "visible", "order")

BUILTIN_GROUPS = {
    "all": "Every registered tool",
    "admin": "Tools only logged-in administrators get",
    "information": "What the participant knows: preferences, scenario information, offers so far, results",
    "visualization": "Plots and charts",
    "recommendation": "Tools that suggest offers (Utility-based Selector, LLM, Random, outcome selectors)",
    "assistant": "Tools the Assistant adds when it chooses (timing 'agent')",
}


# --------------------------------------------------------------------------- #
# Files                                                                        #
# --------------------------------------------------------------------------- #
def layer_files() -> list[Path]:
    """The ``tools.yaml`` files that apply now, least specific first (existing or not)."""
    from hani2.config import settings_dir, settings_layers

    out: list[Path] = []
    for p in [settings_dir() / FILE] + [d / FILE for d in reversed(settings_layers())]:
        if p not in out:
            out.append(p)
    return out


def read_file(path: Path) -> dict[str, Any]:
    """One ``tools.yaml`` as ``{groups, offer, placement}`` (empty when missing or broken)."""
    out: dict[str, Any] = {"groups": {}, "offer": None, "placement": {}}
    if not Path(path).is_file():
        return out
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError("expected a mapping with groups, offer and placement")
        groups = data.get("groups") or {}
        if not isinstance(groups, dict):
            raise ValueError("`groups` must map group names to lists of tools")
        for k, v in groups.items():
            if isinstance(v, str):
                v = [x.strip() for x in v.split(",")]
            out["groups"][str(k)] = [str(x).strip() for x in (v or []) if str(x).strip()]
        offer = data.get("offer")
        if isinstance(offer, str):
            offer = [x.strip() for x in offer.split(",") if x.strip()]
        if offer is not None:
            out["offer"] = [str(x).strip() for x in offer if str(x).strip()]
        pl = data.get("placement") or {}
        if not isinstance(pl, dict):
            raise ValueError("`placement` must map tool names to placements")
        out["placement"] = {str(k): check_placement(v) for k, v in pl.items()}
    except Exception as e:  # noqa: BLE001 - a broken edit must not break the server
        print(f"[hani2] ignoring {path}: {e}")
        return {"groups": {}, "offer": None, "placement": {}}
    return out


def _merge_placement(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for k, v in (extra or {}).items():
        if k in VIEWS:
            out.setdefault(k, {}).update(v or {})
        else:
            out[k] = v
    return out


def load_config(files: Iterable[Path] | None = None) -> dict[str, Any]:
    """``tools.yaml`` merged over the layers: ``{groups, offer, placement}``
    (``placement`` keyed by lower-case tool name)."""
    groups: dict[str, list[str]] = {}
    offer: list[str] | None = None
    placement: dict[str, dict[str, Any]] = {}
    for f in (layer_files() if files is None else files):
        data = read_file(f)
        for name, entries in data["groups"].items():
            for old in [k for k in groups if k.lower() == name.lower()]:
                del groups[old]
            groups[name] = entries
        if data["offer"] is not None:
            offer = data["offer"]
        for tool, pl in data["placement"].items():
            placement[tool.lower()] = _merge_placement(placement.get(tool.lower(), {}), pl)
    return {"groups": groups, "offer": offer, "placement": placement}


def _rw(layer_dir: Path) -> tuple[Path, dict[str, Any]]:
    f = Path(layer_dir) / FILE
    raw: dict[str, Any] = {}
    if f.is_file():
        try:
            raw = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"cannot read {f}: {e}") from None
        if not isinstance(raw, dict):
            raise ValueError(f"{f} is not a mapping")
    return f, raw


def _save(f: Path, raw: dict[str, Any]) -> Path:
    f.parent.mkdir(parents=True, exist_ok=True)
    # an empty ``offer`` is kept: it means "no tool", while no ``offer`` means "every tool"
    clean = {k: v for k, v in raw.items() if v not in (None, {}, []) or (k == "offer" and v == [])}
    tmp = f.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(clean, sort_keys=False, allow_unicode=True), encoding="utf-8")
    tmp.replace(f)
    return f


def write_group(layer_dir: Path, name: str, entries: list[str]) -> Path:
    f, raw = _rw(layer_dir)
    g = dict(raw.get("groups") or {})
    for old in [k for k in g if str(k).lower() == name.lower()]:
        del g[old]
    g[name] = [str(x).strip() for x in entries if str(x).strip()]
    raw["groups"] = g
    return _save(f, raw)


def delete_group(layer_dir: Path, name: str) -> bool:
    f, raw = _rw(layer_dir)
    g = dict(raw.get("groups") or {})
    keys = [k for k in g if str(k).lower() == name.lower()]
    if not keys:
        return False
    for k in keys:
        del g[k]
    raw["groups"] = g
    _save(f, raw)
    return True


def write_offer(layer_dir: Path, entries: list[str] | None) -> Path:
    """Set (or with ``None`` clear) the tools offered at this layer."""
    f, raw = _rw(layer_dir)
    raw["offer"] = None if entries is None else [str(x).strip() for x in entries if str(x).strip()]
    if entries is None:
        raw.pop("offer", None)
    return _save(f, raw)


def write_placement(layer_dir: Path, placement: dict[str, Any], replace: bool = False) -> Path:
    """Merge (or with ``replace`` set) per-tool placements at this layer; a tool
    mapped to ``None`` loses its placement here."""
    f, raw = _rw(layer_dir)
    cur = {} if replace else dict(raw.get("placement") or {})
    for tool, pl in (placement or {}).items():
        for old in [k for k in cur if str(k).lower() == str(tool).lower()]:
            del cur[old]
        if pl is not None:
            cur[str(tool)] = check_placement(pl)
    raw["placement"] = cur
    return _save(f, raw)


# --------------------------------------------------------------------------- #
# Placement                                                                    #
# --------------------------------------------------------------------------- #
def _check_one(v: Any, where: str) -> dict[str, Any]:
    if not isinstance(v, dict):
        raise ValueError(f"{where}: expected a mapping with pane, visible and order")
    out: dict[str, Any] = {}
    for k, x in v.items():
        if k == "pane":
            if x not in PANES:
                raise ValueError(f"{where}: pane must be one of {', '.join(PANES)}")
            out[k] = x
        elif k == "visible":
            if not isinstance(x, bool):
                raise ValueError(f"{where}: visible must be true or false")
            out[k] = x
        elif k == "order":
            if isinstance(x, bool) or not isinstance(x, (int, float)):
                raise ValueError(f"{where}: order must be a number")
            out[k] = int(x)
        else:
            raise ValueError(f"{where}: unknown key {k!r} (use pane, visible, order or a view: {', '.join(VIEWS)})")
    return out


def check_placement(pl: Any) -> dict[str, Any]:
    """Validate a placement: keys ``pane``/``visible``/``order`` (every view) and
    views (``full``, ``simple``, ``focus``) mapping to those keys."""
    if not isinstance(pl, dict):
        raise ValueError("a placement is a mapping")
    out: dict[str, Any] = {}
    flat = {k: v for k, v in pl.items() if k not in VIEWS}
    if flat:
        out.update(_check_one(flat, "placement"))
    for view in VIEWS:
        if view in pl and pl[view] is not None:
            out[view] = _check_one(pl[view], f"placement.{view}")
    return out


def resolve_placement(cls: type, pane: str, order: int, *, override: dict[str, Any] | None = None,
                      layers: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """The placement of a tool in every view: ``{view: {pane, visible, order}}``.
    ``pane``/``order`` are the tool's defaults after env.json overrides; ``override``
    is env.json ``tools.overrides[name].placement``; ``layers`` the merged
    ``tools.yaml`` placement of the tool."""
    own = getattr(cls, "placement", None) or {}
    out: dict[str, dict[str, Any]] = {}
    for view in VIEWS:
        p = {"pane": pane, "visible": True, "order": int(order)}
        try:
            p.update(_check_one(own.get(view) or {}, f"{getattr(cls, '__name__', cls)}.placement.{view}"))
        except ValueError as e:
            print(f"[hani2] {e}; ignored")
        for extra in (override, layers):
            if not extra:
                continue
            p.update({k: v for k, v in extra.items() if k in PLACEMENT_KEYS})
            p.update((extra.get(view) or {}))
        out[view] = p
    return out


# --------------------------------------------------------------------------- #
# Groups                                                                       #
# --------------------------------------------------------------------------- #
def tool_groups_of(cls: type, *, admin_only: bool | None = None, timing: str | None = None) -> list[str]:
    """The built-in groups of a tool: its ``groups`` plus ``admin`` / ``assistant``."""
    gs = [str(g).strip().lower() for g in (getattr(cls, "groups", ()) or ()) if str(g).strip()]
    if isinstance(getattr(cls, "groups", None), str):
        gs = [cls.groups.strip().lower()]  # type: ignore[union-attr]
    if (getattr(cls, "admin_only", False) if admin_only is None else admin_only) and "admin" not in gs:
        gs.append("admin")
    if (getattr(cls, "timing", "") if timing is None else timing) == "agent" and "assistant" not in gs:
        gs.append("assistant")
    return gs


def builtin_groups(specs: Iterable[Any]) -> dict[str, list[str]]:
    """``{group: [tool names]}`` derived from tool specs (or anything with
    ``name`` and ``groups``): the standard groups always exist (maybe empty)."""
    out: dict[str, list[str]] = {k: [] for k in BUILTIN_GROUPS}
    for s in specs:
        out["all"].append(s.name)
        for g in s.groups:
            out.setdefault(g, [])
            if s.name not in out[g]:
                out[g].append(s.name)
    return out


def all_groups(specs: Iterable[Any], config: dict[str, Any] | None = None) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """``(user_groups_raw, builtin_groups)``."""
    cfg = load_config() if config is None else config
    return dict(cfg["groups"]), builtin_groups(specs)


def _lookup(user: dict[str, list[str]], builtin: dict[str, list[str]]):
    u = composition.dict_lookup(user)
    b = composition.dict_lookup(builtin)

    def lookup(name: str, explicit: bool):
        hit = u(name, explicit)
        if hit is not None:
            return hit
        hit = b(name, explicit)
        return None if hit is None else (hit[0], hit[1], True)

    return lookup


def expand(entries: Iterable[str], specs: Iterable[Any], config: dict[str, Any] | None = None,
           name: str | None = None) -> list[str]:
    """Expand tool-group entries into tool names (canonical case; unknown names dropped)."""
    specs = list(specs)
    user, builtin = all_groups(specs, config)
    names = {s.name.lower(): s.name for s in specs}
    out = composition.expand_entries(list(entries), _lookup(user, builtin), name=name, label="tool group")
    result: list[str] = []
    for x in out:
        n = names.get(str(x).lower())
        if n is not None and n not in result:
            result.append(n)
    return result


def expanded_groups(specs: Iterable[Any], config: dict[str, Any] | None = None) -> dict[str, list[str]]:
    """Every group (user groups first, then built-ins) with its tools."""
    specs = list(specs)
    cfg = load_config() if config is None else config
    user, builtin = all_groups(specs, cfg)
    lk = _lookup(user, builtin)
    names = {s.name.lower(): s.name for s in specs}
    out: dict[str, list[str]] = {}
    for g, entries in user.items():
        items = composition.expand_entries(entries, lk, name=g, label="tool group")
        out[g] = [names[str(x).lower()] for x in items if str(x).lower() in names]
    for g, members in builtin.items():
        if not any(k.lower() == g for k in out):
            out[g] = list(members)
    return out


def offered(specs: Iterable[Any], config: dict[str, Any] | None = None) -> set[str] | None:
    """Lower-case names of the tools offered (``None``: every tool, the default)."""
    cfg = load_config() if config is None else config
    if cfg.get("offer") is None:
        return None
    return {n.lower() for n in expand(cfg["offer"], specs, cfg)}
