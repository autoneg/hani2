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

import contextlib
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
                   where: str = "", env_opponents: Any = None) -> ModeInfo:
    """Check merged study settings (``study_mode``, ``opponents``, ``assistants``, ``pairing``)
    against each other and the project's ``kind``. ``explicit_fallback`` is
    ``human_opponent_fallback`` when an env.json sets it (``None``: not set anywhere).
    ``env_opponents`` is the pool env.json gives (study folder, project folder, settings folder):
    a session plays it when the files name no ``opponents``, so it is checked the same way. A
    Paired study is the exception: the pool it fills in wins over env.json, as in a session."""
    pre = f"{where}: " if where else ""
    info = ModeInfo()
    try:
        info.declared = check_mode(settings.get("study_mode"))
    except ValueError as e:
        info.errors.append(pre + str(e))
    opp_raw = settings.get("opponents")
    opponents = items(opp_raw)
    if not opponents and info.declared != PAIRED:
        opponents = items(env_opponents)
    assistants = items(settings.get("assistants"))
    info.derived = derive(opponents)
    info.mode = info.derived
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


@contextlib.contextmanager
def _layer(ref: Any = None, project: str | None = None):
    """Read env.json (``han.current_year``, …) as a session of study ``ref`` would, or, for a
    project file, from that project's folder and the settings folder."""
    from hani2 import config, projects

    if ref is not None:
        with projects.use_study(ref):
            yield
    else:
        with projects.use_study(None), config.layer_view(project):
            yield


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


def _env_opponents(dirs: list) -> tuple[list[str], str]:
    """The opponent pool env.json gives in the current layer view (``opponents``, old name
    ``agents``) and where it comes from: the first of ``dirs`` (study folder, project folder) or the
    settings folder whose own env.json names it, else ``hani2 --settings``."""
    from hani2.config import get_env, read_json_own_file, settings_dir

    pool = items(get_env("opponents", []) or get_env("agents", []) or [])
    if not pool:
        return [], ""
    names = ["study env.json", "project env.json", "settings env.json"]
    for name, d in zip(names, [*dirs[:2], settings_dir()]):
        if d is None:
            continue
        own = read_json_own_file(d / "env.json")
        if items(own.get("opponents")) or items(own.get("agents")):
            return pool, name
    return pool, "hani2 --settings"


def _settings_assistant() -> tuple[str, str]:
    """The Assistant of assistant_settings.json in the current layer view (``agent_class``, else
    the built-in one) and the file it comes from."""
    from hani2 import config, groups
    from hani2.support_agent.settings import FILENAME, load_assistant_settings

    spec = groups.default_assistant_spec(load_assistant_settings())
    study, proj = config.experiment_dir(), config.project_dir()
    for d in [*config.settings_layers(), config.settings_dir()]:
        if str(config.read_json_own_file(d / FILENAME).get("agent_class") or "").strip():
            where = "study" if d == study else "project" if d == proj else "settings"
            return spec, f"{where} {FILENAME}"
    return spec, "built-in"


@dataclass
class Pools:
    """The pools a session of a study (or of a project's studies) would play, resolved from the
    files without starting one. Process settings (``hani2 --assistants`` / ``HANI2_ASSISTANTS``,
    ``hani2 --opponents``) and per-session choices (URLs, group files, ``schedule.json``) are
    left out: see :func:`process_warnings`."""

    #: the Assistant entries as written (study.yaml, project.yaml, the mode, assistant_settings.json)
    assistant_entries: list[str] = field(default_factory=list)
    #: the Assistants after groups are expanded (N of the K ≤ N check)
    assistants: list[str] = field(default_factory=list)
    assistants_source: str = ""
    #: the opponent entries (study.yaml, project.yaml, the mode, env.json, the built-in pool)
    opponents: list[str] = field(default_factory=list)
    opponents_source: str = ""
    #: K: counted negotiations per person and where it comes from
    n_required: int = 5
    n_required_source: str = "default"
    #: the merged ``scheduling`` block (project, then study)
    scheduling: dict[str, Any] = field(default_factory=dict)
    mode: ModeInfo = field(default_factory=ModeInfo)
    errors: list[str] = field(default_factory=list)
    #: the pool env.json gives under the files (whether or not it is used)
    env_opponents: list[str] = field(default_factory=list)

    @property
    def assistant_method(self) -> str:
        from hani2 import scheduling

        return str(self.scheduling.get("assistants") or scheduling.DEFAULTS["assistants"])

    def options(self) -> dict[str, Any]:
        """``cross`` / ``assistant_repeats`` as set in the files (a bad value: ValueError)."""
        from hani2 import scheduling

        return {k: scheduling.check_option(k, self.scheduling[k]) for k in scheduling.OPTIONS if k in self.scheduling}

    def repeat_problems(self) -> list[str]:
        """K > N for a method that uses each Assistant at most once (``[]`` when the pool is only
        ``none``: a study without Assistants)."""
        from hani2 import scheduling

        if self.assistants and all(a.lower() == NO_ASSISTANT for a in self.assistants):
            return []
        try:
            opts = self.options()
        except ValueError:
            return []  # reported by check_scheduling
        out = scheduling.repeat_problems(self.assistant_method, self.n_required, self.assistants, opts)
        if self.assistants_source not in ("study.yaml", "project.yaml"):
            out = [f"{p} (the Assistants come from {self.assistants_source})" for p in out]
        return out

    def editor_pools(self, env_pool: list[str]) -> dict[str, Any]:
        """The editor's ``pools`` block: the pools in effect as saved, their source (``study``,
        ``project``, ``study_mode``, ``env``: an env.json layer, ``settings``: assistant_settings.json,
        ``default``: built in), the env.json pool under the files (``env``: what an unsaved layer with
        no pool falls back to) and the mode the pool implies."""
        def short(src: str) -> str:
            return {"study.yaml": "study", "project.yaml": "project", "built-in": "default"}.get(
                src, "env" if src.endswith("env.json") else "settings" if "assistant_settings" in src else src)

        return {"opponents": {"effective": list(self.opponents), "source": short(self.opponents_source),
                              "env": list(env_pool)},
                "assistants": {"effective": list(self.assistant_entries), "source": short(self.assistants_source)},
                "derived_mode": self.mode.derived}

    def to_dict(self) -> dict[str, Any]:
        from hani2 import scheduling

        try:
            repeats = scheduling.repeats_allowed(self.assistant_method, self.options())
        except ValueError:
            repeats = None
        return {"assistants": {"entries": list(self.assistant_entries), "pool": list(self.assistants),
                               "n": len(self.assistants), "source": self.assistants_source},
                "opponents": {"entries": list(self.opponents), "source": self.opponents_source},
                "n_required": {"value": self.n_required, "source": self.n_required_source},
                "assistant_method": self.assistant_method, "assistant_repeats": repeats,
                "mode": self.mode.mode, "declared": self.mode.declared, "derived": self.mode.derived,
                "mode_error": self.mode.mode_error,
                "repeat_problems": self.repeat_problems(),
                "process_overrides": process_overrides(),
                "errors": list(self.errors)}


def process_overrides() -> dict[str, str]:
    """The process settings that replace a study's pools for every session of this server
    (``hani2 --assistants`` / ``--assistant``, ``hani2 --opponents``, ``PROLIFIC_N_REQUIRED``)."""
    import os

    from hani2.support_agent.settings import ASSISTANT_CLASS_ENV_VAR, SUPPORT_AGENT_CLASS_ENV_VAR, assistant_env

    out: dict[str, str] = {}
    a = (os.environ.get("HANI2_ASSISTANTS") or "").strip() or (
        assistant_env(ASSISTANT_CLASS_ENV_VAR, SUPPORT_AGENT_CLASS_ENV_VAR) or "").strip()
    if a:
        out["assistants"] = a
    o = (os.environ.get("HANI2_OPPONENTS") or os.environ.get("HANI2_AGENTS") or "").strip()
    if o:
        out["opponents"] = o
    k = (os.environ.get("PROLIFIC_N_REQUIRED") or "").strip()
    if k:
        out["n_required"] = k
    return out


def _project_from(name: str, data: dict | None):
    """Project ``name`` as on disk, or as the project.yaml mapping ``data`` about to be saved."""
    from hani2 import projects

    if data is not None:
        _, defaults, _ = projects._split(data, projects.PROJECT_FIELDS, "defaults")
        kind = str(data.get("kind") or "none").lower()
        return projects.Project(name=name, kind=kind if kind in projects.KINDS else "none", defaults=defaults)
    try:
        return projects.load_project(name)
    except ValueError:
        return projects.Project(name=name)


def effective_pools(project: Any, overrides: dict | None = None, ref: Any = None, *, where: str = "") -> Pools:
    """The pools, K and the mode of study ``ref`` (``overrides``: its study.yaml settings) in
    ``project`` (a :class:`hani2.projects.Project`, possibly one about to be saved), or of the
    project's own defaults (``ref`` ``None``), resolved the way a session resolves them:

    * Assistants: study.yaml, else project.yaml ``assistants``, else what the mode fills in (a
      Paired HAN study: ``none``), else ``agent_class`` of assistant_settings.json (study folder,
      project folder, settings folder), else the built-in Assistant;
    * opponents: study.yaml, else project.yaml ``opponents``, else what a Paired study fills in,
      else env.json (study folder, project folder, settings folder), else the built-in pool;
    * K: ``PROLIFIC_N_REQUIRED``, else ``n_required`` of the files, else 5.
    """
    import os

    from hani2 import groups, projects

    r = projects.parse_ref(ref) if ref is not None else None
    pname = project.name
    merged = _layer_settings(project, overrides)
    ov = overrides or {}
    dirs = [projects.study_dir(r), projects.project_layer_dir(pname)] if r is not None \
        else [None, projects.project_layer_dir(pname)]
    out = Pools()
    with _layer(r, None if r is not None else pname):
        env_pool, env_source = _env_opponents(dirs)
        out.env_opponents = list(env_pool)
        info = check_settings(merged, project.kind, explicit_fallback=_explicit_fallback([d for d in dirs if d]),
                              where=where, env_opponents=env_pool)
        out.mode = info

        def source(key: str) -> str:
            return "study.yaml" if ov.get(key) is not None else "project.yaml"

        if items(merged.get("opponents")):
            out.opponents, out.opponents_source = items(merged["opponents"]), source("opponents")
        elif info.filled.get("opponents"):
            out.opponents, out.opponents_source = list(info.filled["opponents"]), "study_mode"
        elif env_pool:
            out.opponents, out.opponents_source = env_pool, env_source
            # say where a pool no file names comes from, so the fix goes to the right file
            info.errors = [f"{e} (the opponents come from {env_source})"
                           if "study_mode" in e or "opponents:" in e else e for e in info.errors]
        else:
            from hani2.agents import DEFAULT_POOL

            out.opponents, out.opponents_source = [str(x) for x in DEFAULT_POOL], "built-in"
        raw = items(merged.get("assistants"))
        if raw:
            out.assistants_source = source("assistants")
        elif info.filled.get("assistants"):
            raw, out.assistants_source = list(info.filled["assistants"]), "study_mode"
        if raw:
            out.assistant_entries = raw
            problems: list[str] = []
            try:
                out.assistants = groups.expand_assistants(raw, r, errors=problems)
            except Exception as e:  # noqa: BLE001 - a broken group is reported by the group checks
                problems.append(str(e))
            out.errors += problems
        else:
            spec, out.assistants_source = _settings_assistant()
            out.assistant_entries = out.assistants = [spec]
    from hani2 import scheduling

    out.scheduling = scheduling._merged_scheduling(project.defaults.get("scheduling"), ov.get("scheduling"))
    env_k = (os.environ.get("PROLIFIC_N_REQUIRED") or "").strip()
    try:
        if env_k:
            out.n_required, out.n_required_source = int(env_k), "PROLIFIC_N_REQUIRED"
        elif merged.get("n_required") is not None:
            out.n_required, out.n_required_source = int(merged["n_required"]), source("n_required")
    except (TypeError, ValueError):
        out.n_required_source = "invalid"
    return out


def file_pools(data: dict, nested: str, *, ref: Any = None, project: str | None = None,
               project_data: dict | None = None) -> Pools:
    """:func:`effective_pools` of a project.yaml (``nested="defaults"``) or study.yaml
    (``nested="overrides"``) mapping about to be saved. ``project_data`` is a project.yaml about
    to be saved that a study's settings are merged with (default: the project as on disk)."""
    from hani2 import projects

    _, settings, _ = projects._split(data, (), nested)
    if nested == "overrides":
        r = projects.parse_ref(ref) if ref is not None else None
        pname = r.project if r is not None else (project or projects.DEFAULT_PROJECT)
        return effective_pools(_project_from(pname, project_data), settings, r)
    return effective_pools(_project_from(project or projects.DEFAULT_PROJECT, data), None, None)


def save_problems(data: dict, nested: str, *, ref: Any = None, project: str | None = None,
                  project_data: dict | None = None) -> list[str]:
    """What the mode checks refuse in a project.yaml (``nested="defaults"``) or study.yaml
    (``nested="overrides"``) about to be saved: the file's settings merged with its project's
    (``project_data``: a project.yaml about to be saved), against the opponent pool a session would
    play (the files, else env.json)."""
    return file_pools(data, nested, ref=ref, project=project, project_data=project_data).mode.errors


_REPORTED: set[str] = set()


def study_pools(ref: Any) -> Pools | None:
    """:func:`effective_pools` of study ``ref`` as it is on disk."""
    from hani2 import projects

    r = projects.parse_ref(ref) if isinstance(ref, str) else ref
    if r is None:
        return None
    st = projects.get_study(r)
    return effective_pools(projects.get_project(r), st.overrides if st is not None else {}, r, where=f"study {r}")


def resolve(ref: Any) -> ModeInfo:
    """The mode of study ``ref`` (``None``: outside a study, the derived mode of no pool). Problems
    are printed once to the server log; when the declared mode disagrees with the pool, the derived
    one is used."""
    if ref is None:
        return ModeInfo()
    pools = study_pools(ref)
    if pools is None:
        return ModeInfo()
    info = pools.mode
    for e in info.errors:
        if e not in _REPORTED:
            _REPORTED.add(e)
            tail = " (opponents wins: the derived mode is used)" if info.mode_error and "study_mode" in e else ""
            print(f"[hani2] ERROR: {e}{tail}")
    return info


def project_pools(name: str) -> Pools:
    """:func:`effective_pools` of a project's own defaults."""
    from hani2 import projects

    return effective_pools(projects.load_project(name), None, None, where=f"project {name}")


def resolve_project(name: str) -> ModeInfo:
    """The mode a project gives its studies (its defaults alone), with what is wrong with it."""
    return project_pools(name).mode


def process_warnings(ref: Any) -> list[str]:
    """What the process settings of this server (``hani2 --assistants`` / ``HANI2_ASSISTANTS``,
    ``hani2 --opponents`` / ``HANI2_OPPONENTS``) break in study ``ref``: they replace the study's
    pools for every session, so they are warnings (``hani2 study show``), never a refusal."""
    from hani2 import groups, scheduling

    pools = study_pools(ref)
    if pools is None:
        return []
    over = process_overrides()
    out: list[str] = []
    if "assistants" in over:
        pool = groups.expand_assistants(items(over["assistants"]), pools_ref(ref))
        try:
            opts = pools.options()
        except ValueError:
            opts = {}
        for p in scheduling.repeat_problems(pools.assistant_method, pools.n_required, pool, opts):
            out.append(f"{p} (the Assistants come from hani2 --assistants / HANI2_ASSISTANTS on this server)")
    if "opponents" in over and pools.mode.declared is not None:
        from hani2 import projects

        r = pools_ref(ref)
        merged = _layer_settings(projects.get_project(r), {**(getattr(projects.get_study(r), "overrides", {}) or {}),
                                                           "opponents": items(over["opponents"])})
        info = check_settings(merged, projects.get_project(r).kind)
        for e in info.errors:
            if "study_mode" in e:
                out.append(f"{e} (the opponents come from hani2 --opponents / HANI2_OPPONENTS on this server)")
    return out


def pools_ref(ref: Any) -> Any:
    from hani2 import projects

    return projects.parse_ref(ref) if isinstance(ref, str) else ref


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
