"""Scenario sets: named, ordered lists of scenario types.

Sets are defined in ``scenario_sets.yaml`` (bundled default, then
``<settings>/scenario_sets.yaml``, then ``<experiment>/scenario_sets.yaml``;
later files add sets or replace sets of the same name). A set lists scenario
types and other sets (``@Name`` or just the set's name); composed sets expand
in order without duplicates. ``Custom`` is always available: it is the list in
``scenario_order.txt``.

The active set is, first hit wins: an explicit name (the admin's session
setting), ``HANI2_SCENARIO_SET``, a changed ``scenario_order.txt`` (``Custom``)
and the file's ``default`` (``HAN2026``).
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from hani2.config import DEFAULT_SETTINGS_DIR, get_settings_file, settings_dir, settings_layers

__all__ = ["CUSTOM", "DEFAULT_SET", "load_sets", "raw_sets", "expand", "set_names", "resolve", "set_types", "active_set", "custom_order"]

FILE = "scenario_sets.yaml"
ORDER_FILE = "scenario_order.txt"
CUSTOM = "Custom"
DEFAULT_SET = "HAN2026"


def _read(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text()) or {}
        if not isinstance(data, dict):
            raise ValueError("expected a mapping with `sets` and `default`")
        sets = data.get("sets") or {}
        if not isinstance(sets, dict):
            raise ValueError("`sets` must map set names to lists of scenario types")
        return data
    except Exception as e:  # noqa: BLE001 - a broken edit must not break the server
        print(f"[hani2] ignoring {path}: {e}")
        return {}


def _layers() -> list[Path]:
    out = [DEFAULT_SETTINGS_DIR / FILE, settings_dir() / FILE]
    out += [d / FILE for d in reversed(settings_layers())]
    return [p for p in out if p.exists()]


def load_sets() -> tuple[dict[str, list[str]], str]:
    """``({name: [types]}, default_name)`` merged over all layers, with sets
    made of other sets expanded (see :func:`expand`)."""
    raw, default = raw_sets()
    return expand(raw), default


def raw_sets() -> tuple[dict[str, list[str]], str]:
    """Like :func:`load_sets`, but with the entries as written (sets not expanded)."""
    sets: dict[str, list[str]] = {}
    default = DEFAULT_SET
    for path in _layers():
        data = _read(path)
        for name, types in (data.get("sets") or {}).items():
            if isinstance(types, str):
                types = [t.strip() for t in types.split(",")]
            # replace a set of the same name regardless of case
            for old in [k for k in sets if k.lower() == str(name).lower()]:
                del sets[old]
            sets[str(name)] = [str(t).strip() for t in (types or []) if str(t).strip()]
        if data.get("default"):
            default = str(data["default"])
    sets[CUSTOM] = custom_order() or list(sets.get(default) or sets.get(DEFAULT_SET) or [])
    return sets, default


def expand(raw: dict[str, list[str]]) -> dict[str, list[str]]:
    """Resolve sets made of other sets (see :mod:`hani2.composition`, shared by
    every kind of group).

    An entry ``@Name`` (or ``:Name``) is always the set ``Name``; a bare entry
    that names a set (case-insensitively) is that set too, otherwise it is a
    scenario type. Sets expand recursively in place, duplicates are dropped (the
    first occurrence keeps its position), and a cycle is reported and broken."""
    from hani2.composition import expand_groups

    return expand_groups(raw, label="scenario set")


def _order_lines(text: str) -> list[str]:
    return [t.strip() for t in text.splitlines() if t.strip() and not t.strip().startswith("#")]


def custom_order() -> list[str]:
    """The types in ``scenario_order.txt`` (the settings or experiment copy, or the bundled one)."""
    p = get_settings_file(ORDER_FILE)
    return _order_lines(p.read_text()) if p.exists() else []


def custom_order_changed() -> bool:
    """Whether ``scenario_order.txt`` was changed from the bundled default."""
    p = get_settings_file(ORDER_FILE)
    bundled = DEFAULT_SETTINGS_DIR / ORDER_FILE
    if not p.exists() or p.resolve() == bundled.resolve():
        return False
    return _order_lines(p.read_text()) != (_order_lines(bundled.read_text()) if bundled.exists() else [])


def set_names() -> list[str]:
    return list(load_sets()[0])


def resolve(name: str | None) -> str | None:
    """The canonical name of set ``name`` (case-insensitive), or ``None``."""
    if not name:
        return None
    for k in load_sets()[0]:
        if k.lower() == str(name).strip().lower():
            return k
    return None


def active_set(explicit: str | None = None) -> str:
    """The name of the set in use (see the module docstring for the order)."""
    for candidate in (explicit, os.environ.get("HANI2_SCENARIO_SET")):
        if candidate:
            found = resolve(candidate)
            if found:
                return found
            print(f"[hani2] unknown scenario set {candidate!r}; using the default")
    if custom_order_changed():
        return CUSTOM
    sets, default = load_sets()
    return resolve(default) or DEFAULT_SET


def set_types(name: str | None = None) -> list[str]:
    """The scenario types of set ``name`` (default: the active set)."""
    sets, _ = load_sets()
    return list(sets.get(active_set(name), []) or sets.get(DEFAULT_SET, []))
