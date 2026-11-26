"""A study's mode (Solo, Paired, Mixed) and its ``pairing`` block.

``study_mode`` (``solo``, ``paired`` or ``mixed``) is a project default that a study may
override. It does not replace ``opponents``, which still decides who plays: it is a declared
intent that HANI2 checks against ``opponents``, the Assistant and the project's ``kind``.

* Unset, the mode is **derived** from ``opponents``: no human entry (``human`` /
  ``human+assistant``) is ``solo``, only human entries is ``paired``, both is ``mixed``.
* Set, it must agree with the pool (see :func:`check_settings`). A file in which they disagree
  is refused when it is saved. A hand-edited file that disagrees is reported (server log,
  ``hani2 study show``, the study's ``errors``) and **``opponents`` wins**: the derived mode is
  used.
* A ``paired`` study without ``opponents`` gets one filled in (``[human+assistant]`` in an
  HI project, ``[human]`` and ``assistants: [none]`` in a HAN project).

``pairing`` holds the options of studies where people meet (``scope``, ``assign``, ``slack``,
``cell_scenario``, ``allow_same_assistant``, ``fallback``, ``fallback_opponents``). The project's
block and the study's merge key by key. This module parses and validates it; ``scope`` decides
the lobby a session waits in (:func:`hani2.matches.match_key`).

The checks of the HAN agent years (``:han<year>-<set>`` entries) live here too, since they are
made at the same moments (on save, on load).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

MODES = ("solo", "paired", "mixed")
SOLO, PAIRED, MIXED = MODES
#: the keys of the ``pairing`` block and their allowed values (``None``: checked by type)
PAIRING_CHOICES: dict[str, tuple | None] = {
    "scope": ("study", "project", "code"),
    "assign": ("cells", "order", "random"),
    "slack": None,
    "cell_scenario": ("type", "name"),
    "allow_same_assistant": None,
    "fallback": ("ai", "wait", "end"),
    "fallback_opponents": None,
}
PAIRING_KEYS = tuple(PAIRING_CHOICES)
#: what each pairing key means when nobody sets it, per declared mode (``scope`` and ``assign``
#: keep today's behaviour unless the mode is declared ``paired``)
PAIRING_DEFAULTS: dict[str, Any] = {
    "scope": "project",
    "assign": "random",
    "slack": 1,
    "cell_scenario": "type",
    "allow_same_assistant": False,
    "fallback": "ai",
    "fallback_opponents": None,
}
PAIRED_DEFAULTS: dict[str, Any] = {"scope": "study", "assign": "cells"}
NO_ASSISTANT = "none"
_HAN_TOKEN = re.compile(r"^[:@]?han(\d{4})-(all|qualified|finalists|winners)$", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Small parsers                                                                #
# --------------------------------------------------------------------------- #
def items(value: Any) -> list[str]:
    """A pool setting as a list of non-empty strings (a comma-separated string is split)."""
    if value is None:
        return []
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    if isinstance(value, (list, tuple)):
        return [str(s).strip() for s in value if s is not None and str(s).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _is_human(spec: Any) -> bool:
    from hani2 import matches

    return matches.is_human(spec)


def _canonical(spec: Any) -> str:
    from hani2 import matches

    return matches.canonical(spec)


def derive(opponents: Any) -> str:
    """The mode a pool implies: no human entry → ``solo``, only human entries → ``paired``,
    both → ``mixed`` (a missing pool is the default pool: ``solo``)."""
    pool = items(opponents)
    humans = [x for x in pool if _is_human(x)]
    if not humans:
        return SOLO
    return PAIRED if len(humans) == len(pool) else MIXED


def check_mode(value: Any, where: str = "study_mode") -> str | None:
    """A ``study_mode`` value, cleaned (``None``: unset); a ValueError names the allowed values."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    v = str(value).strip().lower()
    if v not in MODES:
        raise ValueError(f"{where} must be one of {', '.join(MODES)} (got {value!r})")
    return v


def _flag(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("1", "true", "yes", "on"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("0", "false", "no", "off"):
        return False
    return None


def check_pairing(value: Any, where: str = "pairing") -> tuple[dict[str, Any], list[str]]:
    """``(clean, problems)`` for a ``pairing`` block: the valid keys, cleaned, and what is wrong
    with the others (unknown keys, values not allowed)."""
    if value is None:
        return {}, []
    if not isinstance(value, dict):
        return {}, [f"{where} must be a mapping of {', '.join(PAIRING_KEYS)}"]
    out: dict[str, Any] = {}
    problems: list[str] = []
    for k, v in value.items():
        if k not in PAIRING_CHOICES:
            problems.append(f"{where}: unknown key {k!r}; use {', '.join(PAIRING_KEYS)}")
            continue
        if v is None:
            continue
        allowed = PAIRING_CHOICES[k]
        if allowed is not None:
            s = str(v).strip().lower()
            if s not in allowed:
                problems.append(f"{where}.{k} must be one of {', '.join(allowed)} (got {v!r})")
                continue
            out[k] = s
        elif k == "slack":
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                problems.append(f"{where}.slack must be a whole number ≥ 0 (got {v!r})")
                continue
            out[k] = v
        elif k == "allow_same_assistant":
            f = _flag(v)
            if f is None:
                problems.append(f"{where}.allow_same_assistant must be true or false (got {v!r})")
                continue
            out[k] = f
        elif k == "fallback_opponents":
            pool = items(v)
            humans = [x for x in pool if _is_human(x)]
            if humans:
                problems.append(f"{where}.fallback_opponents is the AI pool of the fallback: remove "
                                f"{', '.join(humans)}")
                continue
            out[k] = pool or None
    return out, problems


def merge_pairing(*layers: Any) -> dict[str, Any]:
    """The ``pairing`` blocks of several layers (project first, study last), merged key by key."""
    out: dict[str, Any] = {}
    for layer in layers:
        if isinstance(layer, dict):
            out.update({k: v for k, v in layer.items() if v is not None})
    return out


def han_token(token: Any) -> tuple[int, str] | None:
    """``(year, set)`` of a ``:han<year>-<set>`` pool entry (``None``: not one)."""
    m = _HAN_TOKEN.match(str(token or "").strip())
    return (int(m.group(1)), m.group(2).lower()) if m else None


def han_year_problems(pool: Any, where: str = "opponents") -> list[str]:
    """``:han<year>-<set>`` entries whose year no source covers (neither the installed
    ``han-agents`` package nor the submissions of ``han.current_year``)."""
    out: list[str] = []
    for tok in items(pool):
        ht = han_token(tok)
        if ht is None:
            continue
        from hani2 import han_submissions

        if not han_submissions.year_covered(ht[0]):
            out.append(f"{where}: {tok}: no agents for {ht[0]} ({han_submissions.coverage_text()})")
    return out


# --------------------------------------------------------------------------- #
# The mode against the pool                                                    #
# --------------------------------------------------------------------------- #
@dataclass
class ModeInfo:
    """What a study's mode is and what follows from it."""

    #: the mode in use: the declared one when it agrees with the pool, else the derived one
    mode: str = SOLO
    #: ``study_mode`` as set in study.yaml / project.yaml (``None``: unset)
    declared: str | None = None
    #: the mode ``opponents`` implies
    derived: str = SOLO
    #: the declared mode disagrees with the pool (``opponents`` wins)
    mode_error: bool = False
    #: the pairing keys set in the files (project, then study, merged)
    pairing: dict[str, Any] = field(default_factory=dict)
    #: settings HANI2 fills in because the mode needs them (``opponents``, ``assistants``)
    filled: dict[str, list[str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def explicit(self) -> bool:
        """``study_mode`` is set and agrees with the pool: the per-session checks apply."""
        return self.declared is not None and not self.mode_error

    @property
    def pairing_effective(self) -> dict[str, Any]:
        """Every pairing key: the files' value, else the mode's default."""
        out = dict(PAIRING_DEFAULTS)
        if self.explicit and self.mode == PAIRED:
            out.update(PAIRED_DEFAULTS)
        out.update(self.pairing)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "declared": self.declared, "derived": self.derived,
                "mode_error": self.mode_error, "pairing": dict(self.pairing),
                "pairing_effective": self.pairing_effective, "filled": dict(self.filled),
                "errors": list(self.errors)}


def _fmt(pool: list[str]) -> str:
    return "[" + ", ".join(pool) + "]"


def check_settings(settings: dict[str, Any], kind: str = "none", *, explicit_fallback: bool | None = None,
                   where: str = "") -> ModeInfo:
    """Check merged study settings (``study_mode``, ``opponents``, ``assistants``, ``pairing``)
    against each other and the project's ``kind``. ``explicit_fallback`` is
    ``human_opponent_fallback`` when an env.json sets it (``None``: not set anywhere)."""
    pre = f"{where}: " if where else ""
    info = ModeInfo()
    opp_raw = settings.get("opponents")
    opponents = items(opp_raw)
    assistants = items(settings.get("assistants"))
    info.derived = derive(opponents)
    info.mode = info.derived
    try:
        info.declared = check_mode(settings.get("study_mode"))
    except ValueError as e:
        info.errors.append(pre + str(e))
    pairing, problems = check_pairing(settings.get("pairing"))
    info.pairing = pairing
    info.errors += [pre + p for p in problems]
    fb = pairing.get("fallback")
    if fb is not None and explicit_fallback is not None and (fb == "wait") != (explicit_fallback is False):
        info.errors.append(f"{pre}pairing.fallback is {fb!r} but human_opponent_fallback is "
                           f"{str(explicit_fallback).lower()} (fallback: wait is human_opponent_fallback: "
                           f"false); keep one")
    info.errors += [pre + p for p in han_year_problems(opponents)]
    info.errors += [pre + p for p in han_year_problems(pairing.get("fallback_opponents"), "pairing.fallback_opponents")]
    mode = info.declared
    if mode is None:
        return info
    humans = [x for x in opponents if _is_human(x)]
    ai = [x for x in opponents if not _is_human(x)]
    no_assistant = bool(assistants) and all(a.lower() == NO_ASSISTANT for a in assistants)
    bad: list[str] = []
    kind = kind if kind in ("assistant", "opponent", "none") else "none"
    if mode == SOLO:
        if humans:
            bad.append(f"study_mode is 'solo' but opponents {_fmt(opponents)} lists "
                       f"{', '.join(humans)}; a Solo study plays AI opponents only (remove the human "
                       f"entries, or use study_mode: paired or mixed)")
        if kind == "assistant" and no_assistant:
            bad.append("study_mode is 'solo' in an HI project (kind: assistant) but assistants is "
                       "[none]; name the Assistants")
    elif mode == PAIRED:
        want = {"assistant": ["human+assistant"], "opponent": ["human"]}.get(kind)
        if not opponents:
            if want is None:
                want = ["human"] if no_assistant else ["human+assistant"]
            info.filled["opponents"] = list(want)
        elif want is not None and (ai or {_canonical(x) for x in humans} != set(want)):
            bad.append(f"study_mode is 'paired' but opponents is {_fmt(opponents)}; a Paired "
                       f"{'HI' if kind == 'assistant' else 'HAN'} study (kind: {kind}) needs opponents: "
                       f"{_fmt(want)}")
        elif want is None and ai:
            bad.append(f"study_mode is 'paired' but opponents {_fmt(opponents)} lists AI entries "
                       f"({', '.join(ai)}); a Paired study lists human entries only (human, "
                       f"human+assistant), or use study_mode: mixed")
        if kind == "assistant" and no_assistant:
            bad.append("study_mode is 'paired' in an HI project (kind: assistant) but assistants is "
                       "[none]; each side needs an Assistant")
        if kind == "opponent":
            if not assistants:
                info.filled["assistants"] = [NO_ASSISTANT]
            elif not no_assistant:
                bad.append(f"study_mode is 'paired' in a HAN project (kind: opponent) but assistants is "
                           f"{_fmt(assistants)}; people play without an Assistant (assistants: [none])")
    elif mode == MIXED:
        if not opponents:
            bad.append("study_mode is 'mixed' but no opponents are given; name the pool, with a person "
                       "and an AI, e.g. opponents: [human+assistant, \":pan\"]")
        elif not humans or not ai:
            bad.append(f"study_mode is 'mixed' but opponents {_fmt(opponents)} has "
                       f"{'no human entry' if not humans else 'no AI entry'}; a Mixed pool lists at least "
                       f"one person (human, human+assistant) and one AI opponent")
    if bad:
        info.errors += [pre + b for b in bad]
        info.mode_error = True
        info.filled = {}
        info.mode = info.derived
    else:
        info.mode = mode
    if info.filled.get("opponents"):
        info.derived = derive(info.filled["opponents"])
    return info


# --------------------------------------------------------------------------- #
# Reading a study's files                                                      #
# --------------------------------------------------------------------------- #
def _explicit_fallback(dirs: list) -> bool | None:
    """``negotiation.human_opponent_fallback`` from the first env.json (study, project, settings
    folder) that sets it; ``None`` when none does (the built-in default does not count)."""
    from hani2.config import read_json_own_file, settings_dir

    for d in [*dirs, settings_dir()]:
        if d is None:
            continue
        try:
            neg = (read_json_own_file(d / "env.json").get("negotiation") or {})
        except Exception:  # noqa: BLE001
            continue
        if isinstance(neg, dict) and "human_opponent_fallback" in neg:
            f = _flag(neg["human_opponent_fallback"])
            return True if f is None else f
    return None


def _layer_settings(project: Any, overrides: dict | None) -> dict[str, Any]:
    """The project's defaults with a study's overrides on top (``None`` values inherit;
    ``pairing`` merges key by key)."""
    from hani2 import projects

    base = dict(project.defaults) if project is not None else {}
    out = {k: v for k, v in base.items() if k in projects.DEFAULT_KEYS}
    for k, v in (overrides or {}).items():
        if k in projects.DEFAULT_KEYS and v is not None:
            out[k] = v
    if isinstance(base.get("pairing"), dict) or isinstance((overrides or {}).get("pairing"), dict):
        out["pairing"] = merge_pairing(base.get("pairing"), (overrides or {}).get("pairing"))
    return out


def save_problems(data: dict, nested: str, *, ref: Any = None, project: str | None = None) -> list[str]:
    """What the mode checks refuse in a project.yaml (``nested="defaults"``) or study.yaml
    (``nested="overrides"``) about to be saved: the file's settings merged with its project's."""
    from hani2 import projects

    _, settings, _ = projects._split(data, (), nested)
    settings = {k: v for k, v in settings.items() if k in projects.DEFAULT_KEYS}
    if nested == "overrides":
        r = projects.parse_ref(ref) if ref is not None else None
        pname = r.project if r is not None else (project or projects.DEFAULT_PROJECT)
        try:
            pr = projects.load_project(pname)
        except ValueError:
            pr = projects.Project(name=pname)
        merged = _layer_settings(pr, settings)
        kind = pr.kind
        dirs = [projects.study_dir(r) if r is not None else None, projects.project_layer_dir(pname)]
    else:
        merged = _layer_settings(None, settings)
        kind = str(data.get("kind") or "none").lower()
        dirs = [projects.project_layer_dir(project) if project else None]
    info = check_settings(merged, kind, explicit_fallback=_explicit_fallback(dirs))
    return info.errors


_REPORTED: set[str] = set()


def resolve(ref: Any) -> ModeInfo:
    """The mode of study ``ref`` (``None``: outside a study, the derived mode of no pool). Problems
    are printed once to the server log; when the declared mode disagrees with the pool, the derived
    one is used."""
    from hani2 import projects

    if ref is None:
        return ModeInfo()
    r = projects.parse_ref(ref) if isinstance(ref, str) else ref
    if r is None:
        return ModeInfo()
    pr = projects.get_project(r)
    st = projects.get_study(r)
    merged = _layer_settings(pr, st.overrides if st is not None else {})
    dirs = [projects.study_dir(r), projects.project_layer_dir(r.project)]
    info = check_settings(merged, pr.kind, explicit_fallback=_explicit_fallback(dirs), where=f"study {r}")
    if not merged.get("opponents") and info.declared is None:
        # no opponents in the files: the derived mode comes from the pool env.json gives
        try:
            from hani2.config import get_env

            with projects.use_study(r):
                env_pool = get_env("opponents", []) or get_env("agents", []) or []
            info.derived = info.mode = derive(env_pool)
        except Exception:  # noqa: BLE001
            pass
    for e in info.errors:
        if e not in _REPORTED:
            _REPORTED.add(e)
            tail = " (opponents wins: the derived mode is used)" if info.mode_error and "study_mode" in e else ""
            print(f"[hani2] ERROR: {e}{tail}")
    return info


def resolve_project(name: str) -> ModeInfo:
    """The mode a project gives its studies (its defaults alone), with what is wrong with it."""
    from hani2 import projects

    pr = projects.load_project(name)
    merged = _layer_settings(pr, {})
    return check_settings(merged, pr.kind, explicit_fallback=_explicit_fallback([projects.project_layer_dir(name)]),
                          where=f"project {name}")


# --------------------------------------------------------------------------- #
# Per-session checks (group files, schedule slots)                             #
# --------------------------------------------------------------------------- #
def filter_group_pool(mode: str, pool: list) -> tuple[list | None, str]:
    """A group file's opponent pool checked against the study's declared mode:
    ``(pool to use, warning)``. ``None`` means the group's pool is refused and the study's own
    pool is used. ``paired``: the AI entries are dropped (all of them AI: refused); ``solo``: a
    pool with a human entry is refused; ``mixed``: used as it is."""
    humans = [x for x in pool if _is_human(x)]
    ai = [x for x in pool if not _is_human(x)]
    if mode == PAIRED and ai:
        if not humans:
            return None, (f"the page's group file lists only AI opponents ({', '.join(map(str, ai))}) but the "
                          f"study is Paired: the study's own pool is used")
        return humans, (f"the page's group file lists AI opponents ({', '.join(map(str, ai))}) but the study "
                        f"is Paired: they are dropped (people only)")
    if mode == SOLO and humans:
        return None, (f"the page's group file lists {', '.join(map(str, humans))} but the study is Solo "
                      f"(AI opponents only): the study's own pool is used")
    return pool, ""


def slot_allowed(mode: str, spec: Any) -> bool:
    """Whether a ``schedule.json`` slot's ``agent_class_name`` fits the study's declared mode."""
    if mode == SOLO:
        return not _is_human(spec)
    if mode == PAIRED:
        return _is_human(spec)
    return True
