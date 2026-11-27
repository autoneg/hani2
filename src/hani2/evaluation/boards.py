"""Leaderboards of projects and studies: one function for every view (pages, admin, the API).

A **project board** pools the project's chosen studies (and rows taken in from other projects, each
for one stratum); a **study board** shows one study. Both are configured by one ``leaderboard:``
block, set in ``project.yaml`` and overridden key by key in ``study.yaml`` for the study's board::

    leaderboard:
      track: hi                         # hi: entrants are Assistants; han: entrants are opponents
      source: game                      # game (default) | tournament (the simulated table)
      studies: [play, prolific-03]      # project board: which studies feed it (default: all)
      include:                          # rows from other projects, each with its stratum
        - {study: HI2027/play, stratum: vs_team}
      sort_options: [hi_score, utility, agreement]   # what end users may sort by
      default_sort: hi_score
      columns: [hi_score, utility, agreement, games, participants]
      user_options:                     # the switches end users get, with their allowed values
        games:   [all, people, ai]
        stratum: [combined, solo, paired]
        window:  [all, last_30_days]
      defaults: {games: all, stratum: combined, window: all}
      visibility: participants          # public | participants | admins
      rules: {min_games: 10, min_participants: 3, max_games_per_pair: 3,
              max_games_per_participant: 20, exclude_own: false, adjust: relative, ci: 0.95}

:func:`board` applies the rules of which games count (no practice, simulated participants, admin
or playground sessions, failures or abandoned matches; own-team games unless ``exclude_own``; caps
per participant and per pair of people, the latest games dropped first), computes every needed
score per game from the evaluation cache (:mod:`hani2.evaluation.eval_cache`), and ranks the
entrants with :func:`hani2.evaluation.tracks.leaderboard` (cells, adjustment, bootstrap) by the
chosen score or criterion. An entrant below ``min_games`` counted games or ``min_participants``
players who do not own it is listed as not ranked yet. The response is the schema
``hani2.leaderboard/2`` (:data:`SCHEMA`); no user name or participant index ever appears in it.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

SCHEMA = "hani2.leaderboard/2"
TRACKS = ("hi", "han")
SOURCES = ("game", "tournament")
VISIBILITY = ("public", "participants", "admins")
DEFAULT_VISIBILITY = "participants"
ADJUST = ("relative", "balanced")
SWITCHES = ("games", "stratum", "window")
GAMES = ("all", "people", "ai")
STRATA = {"hi": ("combined", "solo", "paired"), "han": ("alone", "vs_team", "both")}
WINDOW_ALL = "all"
_WINDOW = re.compile(r"^last_(\d{1,4})_days$")
#: columns that are counts, not scores or criteria
COUNT_COLUMNS = ("games", "participants", "guests", "abandon_rate", "cost_usd")
BLOCK_KEYS = ("track", "source", "studies", "include", "sort_options", "default_sort", "columns", "user_options",
              "defaults", "visibility", "rules")
RULE_DEFAULTS: dict[str, Any] = {"min_games": 10, "min_participants": 3, "max_games_per_pair": None,
                                 "max_games_per_participant": None, "exclude_own": False, "adjust": "relative",
                                 "ci": 0.95}
#: a score that needs the judge is provisional while fewer than this share of its games were judged
JUDGED_SHARE = 0.8


class BoardError(ValueError):
    """A request the board does not allow (a 400)."""


class BoardNotFound(LookupError):
    """No such project or study, or the project has no board (a 404)."""


# --------------------------------------------------------------------------- #
# The block: form, merging, checks                                             #
# --------------------------------------------------------------------------- #
def window_ok(v: Any) -> bool:
    return v == WINDOW_ALL or (isinstance(v, str) and bool(_WINDOW.match(v)) and int(_WINDOW.match(v).group(1)) > 0)


def _switch_ok(name: str, v: Any, track: str | None) -> bool:
    if name == "games":
        return v in GAMES
    if name == "stratum":
        return v in (STRATA[track] if track in STRATA else STRATA["hi"] + STRATA["han"])
    return window_ok(v)


def _switch_values(name: str, track: str | None) -> str:
    if name == "games":
        return ", ".join(GAMES)
    if name == "stratum":
        return ", ".join(STRATA[track] if track in STRATA else STRATA["hi"] + STRATA["han"])
    return "all, last_<n>_days (for example last_30_days)"


def _str_list(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) and x.strip() for x in v)


def _int(v: Any, lo: int) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= lo


def check_block(value: Any, where: str = "leaderboard", track: str | None = None) -> list[str]:
    """What is wrong with the form of one ``leaderboard:`` block as written in a file (``[]``: nothing).
    The checks against the scores and studies are :func:`save_problems`."""
    if value is None:
        return []
    if not isinstance(value, dict):
        return [f"'{where}' must be a mapping (track, sort_options, user_options, rules, …)"]
    out: list[str] = []
    unknown = sorted(set(value) - set(BLOCK_KEYS))
    if unknown:
        out.append(f"'{where}': unknown key(s) {', '.join(unknown)}; use {', '.join(BLOCK_KEYS)}")
    t = value.get("track")
    if t is not None and t not in TRACKS:
        out.append(f"'{where}.track' must be hi or han (got {t!r})")
    track = t if t in TRACKS else track
    if value.get("source") is not None and value["source"] not in SOURCES:
        out.append(f"'{where}.source' must be game or tournament (got {value['source']!r})")
    if value.get("visibility") is not None and value["visibility"] not in VISIBILITY:
        out.append(f"'{where}.visibility' must be one of {', '.join(VISIBILITY)} (got {value['visibility']!r})")
    st = value.get("studies")
    if st is not None:
        from hani2.projects import valid_name

        if not _str_list(st) or not all(valid_name(x) for x in st):
            out.append(f"'{where}.studies' must be a list of study names of this project")
    inc = value.get("include")
    if inc is not None:
        if not isinstance(inc, list):
            out.append(f"'{where}.include' must be a list like [{{study: HI2027/play, stratum: vs_team}}]")
        else:
            for i, e in enumerate(inc, 1):
                w = f"'{where}.include' entry {i}"
                if not isinstance(e, dict) or set(e) - {"study", "stratum"} or not isinstance(e.get("study"), str):
                    out.append(f"{w} must be {{study: <project>/<study>, stratum: <stratum>}}")
                    continue
                if e["study"].count("/") != 1:
                    out.append(f"{w}: study must be <project>/<study> (got {e['study']!r})")
                else:
                    from hani2.projects import valid_name

                    p, s = e["study"].split("/")
                    if not (valid_name(p) and valid_name(s)):
                        out.append(f"{w}: invalid study {e['study']!r}")
                if e.get("stratum") is not None and not _switch_ok("stratum", e["stratum"], track):
                    out.append(f"{w}: stratum must be one of {_switch_values('stratum', track)} (got {e['stratum']!r})")
    for k in ("sort_options", "columns"):
        if value.get(k) is not None and not _str_list(value[k]):
            out.append(f"'{where}.{k}' must be a list of score or criterion keys")
    if value.get("default_sort") is not None and not isinstance(value["default_sort"], str):
        out.append(f"'{where}.default_sort' must be a score or criterion key")
    uo = value.get("user_options")
    if uo is not None:
        if not isinstance(uo, dict):
            out.append(f"'{where}.user_options' must be a mapping like {{games: [all, people, ai]}}")
        else:
            for k, vals in uo.items():
                if k not in SWITCHES:
                    out.append(f"'{where}.user_options': unknown switch {k!r}; use {', '.join(SWITCHES)}")
                    continue
                if not isinstance(vals, list) or not vals:
                    out.append(f"'{where}.user_options.{k}' must be a non-empty list of values")
                    continue
                bad = [v for v in vals if not _switch_ok(k, v, track)]
                if bad:
                    out.append(f"'{where}.user_options.{k}': unknown value(s) {', '.join(map(repr, bad))}; "
                               f"use {_switch_values(k, track)}")
    df = value.get("defaults")
    if df is not None:
        if not isinstance(df, dict):
            out.append(f"'{where}.defaults' must be a mapping like {{games: all, window: all}}")
        else:
            for k, v in df.items():
                if k == "sort":
                    out.append(f"'{where}.defaults.sort': use default_sort")
                elif k not in SWITCHES:
                    out.append(f"'{where}.defaults': unknown switch {k!r}; use {', '.join(SWITCHES)}")
                elif not _switch_ok(k, v, track):
                    out.append(f"'{where}.defaults.{k}': unknown value {v!r}; use {_switch_values(k, track)}")
    rules = value.get("rules")
    if rules is not None:
        if not isinstance(rules, dict):
            out.append(f"'{where}.rules' must be a mapping (min_games, min_participants, …)")
        else:
            for k, v in rules.items():
                w = f"'{where}.rules.{k}'"
                if k not in RULE_DEFAULTS:
                    out.append(f"'{where}.rules': unknown rule {k!r}; use {', '.join(RULE_DEFAULTS)}")
                elif k in ("min_games", "min_participants") and not _int(v, 0):
                    out.append(f"{w} must be a whole number ≥ 0 (got {v!r})")
                elif k in ("max_games_per_pair", "max_games_per_participant") and v is not None and not _int(v, 1):
                    out.append(f"{w} must be a whole number ≥ 1, or null for no cap (got {v!r})")
                elif k == "exclude_own" and not isinstance(v, bool):
                    out.append(f"{w} must be true or false")
                elif k == "adjust" and v not in ADJUST:
                    out.append(f"{w} must be relative or balanced (got {v!r})")
                elif k == "ci" and (isinstance(v, bool) or not isinstance(v, (int, float)) or not 0.5 <= v < 1):
                    out.append(f"{w} must be a level from 0.5 to below 1, such as 0.95 (got {v!r})")
    return out


def file_problems(data: dict, nested: str) -> list[str]:
    """The form problems of the ``leaderboard`` blocks of a project.yaml or study.yaml mapping."""
    out: list[str] = []
    inner = data.get(nested) if isinstance(data.get(nested), dict) else {}
    for where, layer in (("leaderboard", data), (f"{nested}.leaderboard", inner)):
        out += check_block(layer.get("leaderboard"), where)
    return out


def _merge(base: dict, over: dict | None) -> dict:
    """``over`` on ``base``, key by key; ``rules``, ``user_options`` and ``defaults`` merge per key."""
    out = dict(base)
    for k, v in (over or {}).items():
        if k in ("rules", "user_options", "defaults") and isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


def _layer_block(layer: dict) -> dict | None:
    v = layer.get("leaderboard")
    return dict(v) if isinstance(v, dict) else None


@dataclass
class Settings:
    """The ``leaderboard`` block in effect for a project or study board."""

    project: str
    study: str | None
    track: str
    source: str
    studies: list[str]
    include: list[dict]
    sort_options: list[str]
    default_sort: str
    columns: list[str]
    user_options: dict[str, list[str]]
    defaults: dict[str, str]
    visibility: str
    rules: dict[str, Any]
    #: whether a block was written (the project's, or the study's)
    configured: bool
    #: what was given (merged), before the defaults
    given: dict[str, Any] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in ("track", "source", "studies", "include", "sort_options",
                                              "default_sort", "columns", "user_options", "defaults",
                                              "visibility", "rules")}


def _default_track(kind: str) -> str:
    return "han" if kind == "opponent" else "hi"


def _default_sort_options(track: str, ss: Any) -> list[str]:
    keys = [k for k in ss.enabled if ss.scores[k].track in (track, "any")]
    return keys or list(ss.enabled)


def settings(project: str, study: str | None = None, *, project_block: Any = ..., study_block: Any = ...,
             score_set: Any = None) -> Settings:
    """The block in effect: the defaults, the project's block, then (for a study board) the study's.
    ``project_block`` / ``study_block`` replace what the files say (to check a change before saving)."""
    from hani2 import projects
    from hani2.evaluation import scores as S

    pr = projects.load_project(project)
    pb = _layer_block(pr.defaults) if project_block is ... else (dict(project_block) if project_block else None)
    sb = None
    if study:
        st = projects.load_study(projects.StudyRef(project, study))
        sb = _layer_block(st.overrides) if study_block is ... else (dict(study_block) if study_block else None)
    given = _merge(pb or {}, sb)
    track: str = str(given["track"]) if given.get("track") in TRACKS else _default_track(pr.kind)
    ss = score_set if score_set is not None else S.resolve(project, study)
    so = given.get("sort_options")
    sort_options = [x for x in so if isinstance(x, str)] if isinstance(so, list) else []
    sort_options = sort_options or _default_sort_options(track, ss)
    ds = given.get("default_sort")
    default_sort = ds if isinstance(ds, str) and ds else (sort_options[0] if sort_options else "utility")
    co = given.get("columns")
    columns = [x for x in co if isinstance(x, str)] if isinstance(co, list) else []
    columns = columns or [*sort_options, "games", "participants"]
    problems = check_block(given, "leaderboard", track)
    # a hand-edited file is still served: what cannot be used falls back to the default
    rules = dict(RULE_DEFAULTS)
    for k, v in (given.get("rules") if isinstance(given.get("rules"), dict) else {}).items():
        if k in RULE_DEFAULTS and not check_block({"rules": {k: v}}, "leaderboard", track):
            rules[k] = v
    defaults = {"games": "all", "stratum": STRATA[track][0], "window": WINDOW_ALL}
    if isinstance(given.get("defaults"), dict):
        defaults.update({k: v for k, v in given["defaults"].items() if k in SWITCHES and _switch_ok(k, v, track)})
    uo = {}
    for k, v in (given.get("user_options") if isinstance(given.get("user_options"), dict) else {}).items():
        if k in SWITCHES and isinstance(v, list):
            vals = list(dict.fromkeys(x for x in v if _switch_ok(k, x, track)))
            if vals:
                uo[k] = vals
    studies = [x for x in given["studies"] if isinstance(x, str) and projects.valid_name(x)] \
        if isinstance(given.get("studies"), list) and given["studies"] else projects.list_studies(project)
    include = [dict(e) for e in (given.get("include") if isinstance(given.get("include"), list) else [])
               if isinstance(e, dict) and isinstance(e.get("study"), str)]
    if not isinstance(given.get("studies"), (list, type(None))):
        studies = projects.list_studies(project)
    return Settings(project=project, study=study, track=track, source=str(given.get("source") or "game"),
                    studies=studies, include=include, sort_options=sort_options, default_sort=default_sort,
                    columns=columns, user_options=uo, defaults=defaults,
                    visibility=str(given.get("visibility") or DEFAULT_VISIBILITY), rules=rules,
                    configured=bool(pb or sb), given=given, problems=problems)


def _criteria_index(project: str, study: str | None) -> dict[str, Any]:
    from hani2.evaluation import criteria as C

    return C.by_id(C.catalogue(project, study))


def _key_problem(key: str, ss: Any, crit: dict[str, Any], *, sort: bool) -> str | None:
    """Why ``key`` cannot be a sort option (``sort``) or a column here (``None``: it can)."""
    if key in COUNT_COLUMNS:
        return f"{key!r} is a count, not a score or criterion: it cannot be sorted by" if sort else None
    if key in ss.scores:
        return None if key in ss.enabled else f"score {key!r} is not enabled (scores_enabled)"
    c = crit.get(key)
    if c is None:
        return f"{key!r} is neither an enabled score nor a criterion"
    if c.source == "score":
        return f"score {key!r} is not enabled (scores_enabled)"
    if sort and c.direction not in ("higher", "lower"):
        return f"criterion {key!r} has no direction (higher or lower), so it cannot be sorted by"
    return None


def save_problems(data: dict, nested: str, *, ref: Any = None, project: str | None = None) -> list[str]:
    """What a saved project.yaml (``project``) or study.yaml (``ref``) would make wrong in a board: every
    key of ``sort_options`` and ``columns`` must be enabled in every study the board reads, and
    ``default_sort`` must be one of ``sort_options``; switch defaults must be allowed values."""
    from hani2 import projects
    from hani2.evaluation import scores as S

    inner = data.get(nested) if isinstance(data.get(nested), dict) else {}
    block = inner.get("leaderboard", data.get("leaderboard"))
    if block is not None and not isinstance(block, dict):
        return []
    sc = inner.get("scores", data.get("scores"))
    en = inner.get("scores_enabled", data.get("scores_enabled", ...))
    if ref is not None:
        ref = projects.parse_ref(ref)
        pname, sname = ref.project, ref.study
        if not projects.project_exists(pname):
            return []
        kw = {"study_block": block}
        skw = {"study_scores": sc if isinstance(sc, dict) else None, "study_enabled": en}
    else:
        pname, sname = project, None
        if not pname or not projects.project_exists(pname):
            return []
        kw = {"project_block": block}
        skw = {"project_scores": sc if isinstance(sc, dict) else None, "project_enabled": en}
    skw = {k: v for k, v in skw.items() if v is not ... and v is not None}
    if block is None and ref is None:
        return []
    try:
        ss = S.resolve(pname, sname, **skw)
        cfg = settings(pname, sname, score_set=ss, **kw)
    except Exception as e:  # noqa: BLE001 — a broken study file is reported elsewhere
        return [f"leaderboard: cannot be checked ({e})"]
    if not cfg.configured:
        return []
    out = list(cfg.problems)
    given = cfg.given
    if given.get("sort_options") is not None and not given["sort_options"]:
        out.append("leaderboard.sort_options must name at least one score or criterion")
    if cfg.default_sort not in cfg.sort_options:
        out.append(f"leaderboard.default_sort {cfg.default_sort!r} must be one of sort_options "
                   f"({', '.join(cfg.sort_options)})")
    for k, v in cfg.defaults.items():
        allowed = cfg.user_options.get(k)
        if allowed and v not in allowed:
            out.append(f"leaderboard.defaults.{k} {v!r} must be one of user_options.{k} ({', '.join(allowed)})")
    # every study the board reads: the study (a study board) or the project's chosen studies
    reads = [sname] if sname else [s for s in cfg.studies if projects.study_exists(projects.StudyRef(pname, s))]
    sets = [(sname or "(project)", ss)] if sname else [("(project)", ss)]
    for s in reads:
        if s != sname:
            try:
                sets.append((s, S.resolve(pname, s, **({k: v for k, v in skw.items() if k.startswith("project")}))))
            except Exception:  # noqa: BLE001
                continue
    crit = _criteria_index(pname, sname)
    for k in dict.fromkeys([*cfg.sort_options, *cfg.columns]):
        for where, sset in sets:
            p = _key_problem(k, sset, crit, sort=k in cfg.sort_options)
            if p:
                out.append(f"leaderboard: {p}" + ("" if where == "(project)" else f" in study {where!r}"))
                break
    return list(dict.fromkeys(out))


# --------------------------------------------------------------------------- #
# The options a viewer may use                                                 #
# --------------------------------------------------------------------------- #
def _option(key: str, ss: Any, crit: dict[str, Any]) -> dict[str, Any]:
    if key in ss.scores:
        s = ss.scores[key]
        d: dict[str, Any] = {"key": key, "title": s.title, "kind": "score"}
        if s.description:
            d["description"] = s.description
        return d
    c = crit.get(key)
    d = {"key": key, "title": c.title if c else key, "kind": "criterion",
         "direction": c.direction if c else "higher"}
    if c is not None and c.description:
        d["description"] = c.description
    return d


def admin_sort_keys(ss: Any, crit: dict[str, Any]) -> list[str]:
    """What an admin may sort by: every enabled score, and every criterion with a direction."""
    keys = list(ss.enabled)
    keys += [k for k, c in crit.items() if c.source != "score" and c.direction in ("higher", "lower")]
    return list(dict.fromkeys(keys))


def options(cfg: Settings, ss: Any, crit: dict[str, Any], *, admin: bool = False) -> dict[str, Any]:
    """The options of the response: the sort keys and the switch values the viewer may use, and the
    defaults. End users get ``sort_options`` and ``user_options``; a switch that is not listed is not
    offered. Admins get the sort options (every enabled score and criterion is accepted too) and every
    value."""
    keys = [k for k in cfg.sort_options if _key_problem(k, ss, crit, sort=True) is None]
    if admin:  # every enabled score too (any criterion with a direction is accepted as well)
        keys = list(dict.fromkeys([*keys, *ss.enabled]))
    out: dict[str, Any] = {"sort": [_option(k, ss, crit) for k in keys]}
    for sw in SWITCHES:
        if admin:
            out[sw] = list(GAMES) if sw == "games" else (list(STRATA[cfg.track]) if sw == "stratum"
                                                         else list(dict.fromkeys([WINDOW_ALL, "last_7_days",
                                                                                  "last_30_days", *cfg.user_options.get(sw, [])])))
        elif sw in cfg.user_options:
            out[sw] = list(cfg.user_options[sw])
    out["defaults"] = {"sort": default_sort(cfg, ss, crit) or cfg.default_sort, **cfg.defaults}
    return out


def default_sort(cfg: Settings, ss: Any, crit: dict[str, Any]) -> str | None:
    """The sort key of a request that names none: ``default_sort``, else the first usable sort option."""
    usable = [k for k in cfg.sort_options if _key_problem(k, ss, crit, sort=True) is None]
    if _key_problem(cfg.default_sort, ss, crit, sort=True) is None:
        return cfg.default_sort
    return usable[0] if usable else None


def parse_query(cfg: Settings, ss: Any, crit: dict[str, Any], query: dict | None, *, admin: bool = False) -> dict[str, str]:
    """The view asked for, checked against what the viewer may use (:class:`BoardError` otherwise)."""
    q = {k: v for k, v in (query or {}).items() if v not in (None, "")}
    unknown = sorted(set(q) - {"sort", *SWITCHES})
    if unknown:
        raise BoardError(f"unknown parameter(s) {', '.join(unknown)}; use sort, {', '.join(SWITCHES)}")
    out: dict[str, str] = {}
    allowed = [k for k in cfg.sort_options if _key_problem(k, ss, crit, sort=True) is None]
    if admin:
        allowed = list(dict.fromkeys([*allowed, *admin_sort_keys(ss, crit)]))
    if q.get("sort") is None:  # the default: when the file names one that cannot be used, the first that can
        sort = default_sort(cfg, ss, crit)
        if sort is None:
            raise BoardError("this board has no sort key that can be used (see its warnings)")
    else:
        sort = str(q["sort"])
    if sort not in allowed:
        raise BoardError(f"sort {sort!r} is not allowed here; use one of {', '.join(allowed) or '(none)'}")
    out["sort"] = sort
    for sw in SWITCHES:
        if sw not in q:  # the default always applies (an unusable one was replaced when the block was read)
            out[sw] = cfg.defaults[sw]
            continue
        v = str(q[sw])
        if admin:
            ok = _switch_ok(sw, v, cfg.track)
            values = _switch_values(sw, cfg.track)
        else:
            vals = cfg.user_options.get(sw)
            ok = v in vals if vals else v == cfg.defaults[sw]
            values = ", ".join(vals) if vals else f"{cfg.defaults[sw]} (this switch is fixed)"
        if not ok:
            raise BoardError(f"{sw} {v!r} is not allowed here; use {values}")
        out[sw] = v
    return out


# --------------------------------------------------------------------------- #
# Rows                                                                         #
# --------------------------------------------------------------------------- #
def _post_session(ref: Any, rows: list[dict]) -> list[dict]:
    """Each participant's post-session answers onto their games (only when they used one Assistant
    throughout), within one study."""
    from hani2 import projects, questionnaires
    from hani2.evaluation import criteria as C, eval_cache
    from hani2.study import read_post_session

    users = sorted({str(r.get("user")) for r in rows if r.get("user")})
    if not users:
        return rows
    try:
        with projects.use_study(ref):
            spec = questionnaires.spec("post_session")
    except Exception:  # noqa: BLE001
        spec = None
    if not spec:
        return rows
    root = eval_cache.results_dir(ref)
    answers = {}
    for u in users:
        try:
            a = read_post_session(root / u)
        except Exception:  # noqa: BLE001
            a = None
        vals = C.post_session_values(spec, (a or {}).get("answers", a) if isinstance(a, dict) else None)
        if vals:
            answers[u] = vals
    return C.attach_participant_answers(rows, answers) if answers else rows


def study_rows(ref: Any) -> tuple[list[dict], dict[str, Any]]:
    """The evaluation rows of one study's games (from the cache), with post-session answers joined."""
    from hani2.evaluation import eval_cache

    rows, info = eval_cache.rows(ref)
    rows = _post_session(ref, rows)
    for r in rows:
        r["_study"] = str(ref)
    return rows, info


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "1", "1.0", "yes")


def _blank(v: Any) -> bool:
    from hani2.evaluation.tracks import _blank as b

    return b(v)


def _entrant(r: dict, track: str) -> str:
    if track == "han":
        return str(r.get("opponent") or "?")
    for k in ("assistant_entrant", "assistant", "support_agent"):
        if not _blank(r.get(k)) and str(r.get(k)) != "none":
            return str(r[k])
    return "none"


def _spec(r: dict, track: str) -> str:
    if track == "han":
        return str(r.get("opponent") or "")
    for k in ("assistant", "support_agent"):
        if not _blank(r.get(k)) and str(r.get(k)) != "none":
            return str(r[k])
    return ""


def label_of(spec: str) -> str:
    """A short name for a spec: its class name (``pkg.mod:Helper`` → ``Helper``)."""
    s = str(spec or "").strip()
    if not s:
        return ""
    s = s.split(":")[-1] if ":" in s else s
    return s.split(".")[-1] or s


def _started(r: dict) -> datetime | None:
    v = r.get("started")
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _clean_number(v: Any) -> Any:
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


# --------------------------------------------------------------------------- #
# The board                                                                    #
# --------------------------------------------------------------------------- #
def _resolve(project: str, study: str | None):
    from hani2 import projects

    if not projects.valid_name(project) or not projects.project_exists(project):
        raise BoardNotFound(f"unknown project {project!r}")
    if study is not None and (not projects.valid_name(study) or not projects.study_exists(projects.StudyRef(project, study))):
        raise BoardNotFound(f"unknown study {project}/{study}")


def visibility(project: str, study: str | None = None) -> str:
    """Who may see the board: ``public``, ``participants`` (signed-in users) or ``admins``."""
    _resolve(project, study)
    v = settings(project, study).visibility
    return v if v in VISIBILITY else DEFAULT_VISIBILITY


def has_board(project: str) -> bool:
    """Whether the project has a ``leaderboard`` block (``GET /api/v1/leaderboards`` lists it)."""
    from hani2 import projects

    try:
        return _layer_block(projects.load_project(project).defaults) is not None
    except Exception:  # noqa: BLE001
        return False


def list_boards() -> list[dict[str, Any]]:
    """Every project that has a board: its track, year, visibility and studies."""
    from hani2 import projects

    out = []
    for p in projects.list_projects():
        if not has_board(p):
            continue
        try:
            pr = projects.load_project(p)
            cfg = settings(p)
        except Exception:  # noqa: BLE001
            continue
        out.append({"project": p, "title": pr.full_name or p, "track": cfg.track, "source": cfg.source,
                    "year": pr.year, "visibility": cfg.visibility,
                    "studies": [{"study": s, "visibility": _safe_vis(p, s)} for s in projects.list_studies(p)]})
    return out


def _safe_vis(p: str, s: str) -> str:
    try:
        return visibility(p, s)
    except Exception:  # noqa: BLE001
        return DEFAULT_VISIBILITY


def board(project: str, study: str | None = None, query: dict | None = None, *, admin: bool = False,
          n_boot: int = 1000, seed: int = 0, now: datetime | None = None) -> dict[str, Any]:
    """The board of a project (``study=None``) or of one study, for ``query`` (``sort``, ``games``,
    ``stratum``, ``window``), as the schema ``hani2.leaderboard/2``. Values the viewer may not use raise
    :class:`BoardError`; ``admin`` allows every enabled score and criterion and every switch value."""
    from hani2 import projects
    from hani2.evaluation import scores as S

    _resolve(project, study)
    ss = S.resolve(project, study)
    cfg = settings(project, study, score_set=ss)
    crit = _criteria_index(project, study)
    q = parse_query(cfg, ss, crit, query, admin=admin)
    now = now or datetime.now(timezone.utc)
    warnings: list[str] = [f"leaderboard settings: {p}" for p in cfg.problems]
    if ss.problems:
        warnings.append(f"{len(ss.problems)} score definition problem(s): see `hani2 scores check`")
    # the rows: the study, or the project's chosen studies and the rows taken in from other projects
    refs = [projects.StudyRef(project, study)] if study else []
    if not study:
        for s in cfg.studies:
            r = projects.StudyRef(project, s)
            if projects.study_exists(r):
                refs.append(r)
            else:
                warnings.append(f"study {s!r} of leaderboard.studies does not exist (yet)")
    rows: list[dict] = []
    stale = 0
    for r in refs:
        rs, info = study_rows(r)
        rows += rs
        stale += info.get("failed", 0)
    if not study:
        for inc in cfg.include:
            try:
                r = projects.parse_ref(inc["study"])
            except ValueError:
                continue
            if not projects.study_exists(r):
                warnings.append(f"included study {inc['study']!r} does not exist (yet)")
                continue
            rs, info = study_rows(r)
            for x in rs:
                x["_only_stratum"] = inc.get("stratum") or None
            rows += rs
    if stale:
        warnings.append(f"{stale} recording(s) could not be evaluated and are left out")
    value_keys = [k for k in dict.fromkeys([q["sort"], *cfg.columns]) if k not in COUNT_COLUMNS
                  and _key_problem(k, ss, crit, sort=False) is None]
    dropped_cols = [k for k in cfg.columns if k not in COUNT_COLUMNS and k not in value_keys]
    if dropped_cols:
        warnings.append(f"column(s) {', '.join(dropped_cols)} are not enabled here and are not shown")
    if _key_problem(cfg.default_sort, ss, crit, sort=True) is not None:
        warnings.append(f"default_sort {cfg.default_sort!r} cannot be used here; the board uses {q['sort']!r}")
    if cfg.source == "tournament":
        return _tournament(cfg, q, refs, ss, crit, admin, now, warnings)
    out = _game_board(cfg, q, rows, ss, crit, value_keys, project, study, now, n_boot, seed, warnings)
    out["options"] = options(cfg, ss, crit, admin=admin)
    out.pop("_reference")
    out["data_version"] = data_version(out)
    return _order(out)


def data_version(out: dict) -> str:
    """A hash of everything a board shows except when it was made: the same data give the same version,
    and any change of a value, an entrant, an option or a note gives another."""
    body = {k: v for k, v in out.items() if k not in ("generated_at", "data_version")}
    return "sha1:" + hashlib.sha1(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


_TOP = ("schema", "project", "study", "track", "source", "generated_at", "data_version", "query", "options", "columns",
        "scores", "rules", "entries", "unranked", "excluded", "warnings")


def _order(out: dict) -> dict:
    return {**{k: out[k] for k in _TOP if k in out}, **{k: v for k, v in out.items() if k not in _TOP}}


def _game_board(cfg: Settings, q: dict, rows: list[dict], ss: Any, crit: dict, value_keys: list[str],
                project: str, study: str | None, now: datetime, n_boot: int, seed: int,
                warnings: list[str]) -> dict[str, Any]:
    from hani2.evaluation import criteria as C, scores as S, tracks as T

    track = cfg.track
    rules = cfg.rules
    in_track = [r for r in rows if T._in_track(r, track)]
    for r in in_track:
        r["_entrant"] = _entrant(r, track)
        if not _truthy(r.get("counted", True)):
            r["_exclude"] = "admin or test session"
        elif rules.get("exclude_own") and _truthy(r.get("own_assistant")):
            r["_exclude"] = "own team"
    # partners among every row (a left-out partner still names the opponent)
    partners = T._partners(in_track)
    same = {id(r) for r in in_track if track == "hi" and T._match_of(r) and T._same_assistant(r, partners.get(id(r)))}
    # scores per game: only the components every entrant has often enough
    base, _, _ = T._filter(in_track, track, False, False, None)
    names = [k for k in value_keys if k in ss.scores]
    needed = ss.needed(names)
    ref = C.reference_for(project, base)
    active = S.active_components(base, needed, lambda r: r["_entrant"]) if needed else {}
    for r in in_track:
        r.update(S.score_row(r, None, active, scores=needed, reference=ref))
        if id(r) in same:  # same-Assistant games: out of utility and of scores that say skip
            for k in names:
                if k == "utility" or getattr(ss.scores[k], "same_assistant", "once") == "skip":
                    r[k] = None
    # caps (the latest games over a cap are dropped), on the games that count
    caps = {"max_games_per_participant": lambda r: (r["_entrant"], str(r.get("user"))),
            "max_games_per_pair": lambda r: ((r["_entrant"], *sorted([str(r.get("user")), str(r.get("opponent_user"))]))
                                             if T.is_paired(r) and not _blank(r.get("opponent_user")) else None)}
    ordered = sorted(base, key=lambda r: (str(r.get("started") or ""), str(r.get("id") or "")))
    for rule, keyf in caps.items():
        cap = rules.get(rule)
        if not cap:
            continue
        seen: dict[Any, int] = {}
        for r in ordered:
            if r.get("_exclude"):
                continue
            k = keyf(r)
            if k is None:
                continue
            seen[k] = seen.get(k, 0) + 1
            if seen[k] > cap:
                r["_exclude"] = "cap"
    counted = [r for r in base if not r.get("_exclude")]
    # minimums, on every counted game (whatever the switches show)
    per: dict[str, dict[str, Any]] = {}
    for r in counted:
        e = per.setdefault(r["_entrant"], {"games": 0, "players": set(), "spec": _spec(r, track)})
        e["games"] += 1
        if not _truthy(r.get("own_assistant")):
            e["players"].add(str(r.get("user")))
    # the view: games and window switches (the stratum is the tracks' own)
    cutoff = None
    if q["window"] != WINDOW_ALL:
        cutoff = now - timedelta(days=int(_WINDOW.match(q["window"]).group(1)))
    for r in in_track:
        hide = (q["games"] == "people" and not T.is_paired(r)) or (q["games"] == "ai" and T.is_paired(r))
        if cutoff is not None:
            d = _started(r)
            hide = hide or d is None or d < cutoff
        if hide:
            r["_hidden"] = True
    directions = {k: (crit[k].direction if k in crit and k not in ss.scores else "higher") for k in value_keys}
    lb = T.leaderboard(in_track, track, T.GAME_BOARD, rank_by=q["sort"], values=value_keys, directions=directions,
                       relative=rules.get("adjust", "relative") == "relative", stratum=q["stratum"],
                       n_boot=n_boot, seed=seed, ci=float(rules.get("ci") or 0.95), min_coverage=0.0)
    # games per entrant in the view, whatever the games switch
    view_games: dict[str, dict[str, int]] = {}
    guests: dict[str, set] = {}
    for r in counted:
        if cutoff is not None and ((_started(r) or cutoff) < cutoff or _started(r) is None):
            continue
        if q["stratum"] not in ("combined", "both") and not _in_stratum(r, track, q["stratum"]):
            continue
        g = view_games.setdefault(r["_entrant"], {"all": 0, "people": 0, "ai": 0})
        g["all"] += 1
        g["people" if T.is_paired(r) else "ai"] += 1
        if not _blank(r.get("invited_by")):
            guests.setdefault(r["_entrant"], set()).add(str(r.get("user")))
    # abandon rate per entrant: abandoned games among the counted and abandoned ones
    gone = {T._match_of(r) for r in in_track if T._abandoned(r) and T._match_of(r)}
    ab: dict[str, list[int]] = {}
    counted_ids = {id(r) for r in counted}
    for r in in_track:
        if r.get("practice") or r.get("mode") == "simulated" or not _truthy(r.get("counted", True)):
            continue
        a = T._abandoned(r) or (T._match_of(r) in gone and T._match_of(r) is not None)
        if a or id(r) in counted_ids:
            x = ab.setdefault(r["_entrant"], [0, 0])
            x[0] += int(a)
            x[1] += 1
    minimum_g, minimum_p = int(rules.get("min_games") or 0), int(rules.get("min_participants") or 0)
    entries, unranked = [], []
    main = q["sort"]
    sign = -1.0 if directions.get(main) == "lower" else 1.0
    for e in lb["entries"]:
        name = e["entrant"]
        info = per.get(name, {"games": 0, "players": set(), "spec": ""})
        vg = view_games.get(name, {"all": 0, "people": 0, "ai": 0})
        reason = None
        if info["games"] < minimum_g:
            reason = "min_games"
        elif len(info["players"]) < minimum_p:
            reason = "min_participants"
        elif e["scores"][main]["mean"] is None:
            reason = "no_value"
        if reason:
            unranked.append({"entrant": name, "label": label_of(info["spec"] or name), "games": {"all": info["games"]},
                             "reason": reason})
            continue
        vals = {k: {"mean": _clean_number(e["scores"][k]["mean"]),
                    "ci": [_clean_number(e["scores"][k]["lo"]), _clean_number(e["scores"][k]["hi"])]}
                for k in value_keys}
        ar = ab.get(name)
        entries.append({"rank": None, "tied_with_leader": False, "entrant": name, "assistant": info["spec"] or name,
                        "label": label_of(info["spec"] or name), "values": vals, "games": vg,
                        "participants": e["participants"], "guests": len(guests.get(name, set())),
                        "ci_unit": e["scores"][main]["ci_unit"],
                        "abandon_rate": (ar[0] / ar[1]) if ar and ar[1] else 0.0,
                        "cost_usd": _clean_number(e["cost_usd"])})
        if track == "han":
            entries[-1]["opponent"] = entries[-1].pop("assistant")
    # ranks among the ranked entrants (equal means share a rank; ties with the leader by the CI)
    entries.sort(key=lambda x: (-sign * x["values"][main]["mean"], x["entrant"]))
    rank, prev = 0, None
    lead = entries[0]["values"][main] if entries else None
    for i, x in enumerate(entries):
        m = x["values"][main]["mean"]
        if prev is None or not math.isclose(m, prev, abs_tol=1e-12):
            rank = i + 1
        x["rank"], prev = rank, m
        lo, hi = x["values"][main]["ci"]
        if i and lead is not None:
            if sign > 0:
                x["tied_with_leader"] = bool(lead["ci"][0] is not None and hi is not None and hi >= lead["ci"][0])
            else:
                x["tied_with_leader"] = bool(lead["ci"][1] is not None and lo is not None and lo <= lead["ci"][1])
    # the scores: weights in effect, dropped parts, provisional
    view = [r for r in in_track if not r.get("_hidden") and not r.get("_exclude")]
    judged = sum(1 for r in view if r.get("judge_model")) / len(view) if view else 0.0
    cat_cost = {k: c.cost for k, c in crit.items()}
    score_info = {}
    notes = list(lb.get("notes") or [])
    for k in value_keys:
        if k not in ss.scores:
            continue
        sc = ss.scores[k]
        kept = active.get(k)
        flat = S.flattened(k, ss.scores)
        needs_judge = any(cat_cost.get(c) == "judge" for c, w in flat.items() if w > 0)
        uses_ref = any((c.normaliser or {}).get("scale") == C.REFERENCE_MEDIAN
                       or (c.normaliser or {}).get("kind") == "percentile" for c in sc.components)
        prov = (needs_judge and judged < JUDGED_SHARE) or (uses_ref and bool((ref or {}).get("provisional", ref is None)))
        score_info[k] = {"weights_in_effect": {c: round(w, 6) for c, w in S.weights_in_effect(sc, kept).items()},
                         "dropped": sorted({c.column for c in sc.components} - (kept or set())),
                         "provisional": bool(prov), "title": sc.title}
        if needs_judge and judged < JUDGED_SHARE:
            notes.append(f"{sc.title} is provisional: {judged:.0%} of its games were judged (it needs "
                         f"{JUDGED_SHARE:.0%}; run `hani2 leaderboard judge`)")
        if score_info[k]["dropped"]:
            warnings.append(f"{sc.title}: component(s) {', '.join(score_info[k]['dropped'])} were measured for too "
                            "few games of some entrant and are left out for everyone")
    rsum = C.reference_summary(ref if ref and not ref.get("provisional") else None)
    if rsum["frozen"]:
        notes.append(f"normalisation: the frozen reference of {', '.join(map(str, rsum.get('studies') or [])) or 'the project'}"
                     + (f" (games until {rsum['end']})" if rsum.get("end") else "")
                     + (f", frozen at {rsum['frozen_at']}" if rsum.get("frozen_at") else ""))
    else:
        notes.append("normalisation: no frozen reference yet; unbounded criteria are scaled on the current games, "
                     "so the values are provisional (`hani2 scores freeze`)")
    if rules.get("adjust", "relative") == "relative":
        notes.append("means are cell-adjusted (each game against the mean of its cell), shown on the values' scale")
    else:
        notes.append("means are cell-balanced (the mean of the cell means)")
    warnings += [w for w in lb.get("warnings") or [] if w not in warnings]
    excluded = dict(lb["excluded"])
    return {
        "schema": SCHEMA, "project": project, "study": study, "track": track, "source": cfg.source,
        "generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "query": dict(q), "columns": list(cfg.columns), "scores": score_info,
        "rules": dict(rules), "entries": entries, "unranked": unranked, "excluded": excluded,
        "warnings": list(dict.fromkeys(warnings)), "notes": notes, "visibility": cfg.visibility,
        "stratum_title": lb.get("stratum_title"), "cells": lb.get("cells"),
        "totals": {k: lb["totals"].get(k) for k in ("sessions", "matches", "agreement_rate", "welfare")},
        "reference": rsum, "_reference": ref,
    }


def _in_stratum(r: dict, track: str, stratum: str) -> bool:
    from hani2.evaluation import tracks as T

    st = T.study_stratum(r) if track == "hi" else T.han_stratum(r)
    return st == stratum


def _tournament(cfg: Settings, q: dict, refs: list, ss: Any, crit: dict, admin: bool, now: datetime,
                warnings: list[str]) -> dict[str, Any]:
    """The simulated table (``source: tournament``): per Assistant, the goal rate of its valid simulated
    trials, averaged over personas."""
    import pandas as pd

    from hani2.evaluation import eval_cache
    from hani2.results import simulated_leaderboard

    frames = []
    for r in refs:
        for f in sorted(eval_cache.results_dir(r).glob("*/results.csv")):
            try:
                frames.append(pd.read_csv(f, index_col=None))
            except Exception:  # noqa: BLE001
                continue
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    table = simulated_leaderboard(df)
    by: dict[str, list[dict]] = {}
    for row in table:
        by.setdefault(row["assistant"], []).append(row)
    entries = []
    for a, rs in by.items():
        trials = sum(r["trials"] for r in rs)
        rate = sum(r["goal_rate"] * r["trials"] for r in rs) / trials if trials else None
        util = sum(r["mean_utility"] * r["trials"] for r in rs) / trials if trials else None
        entries.append({"rank": None, "tied_with_leader": False, "entrant": a, "assistant": a, "label": label_of(a),
                        "values": {"goal_rate": {"mean": rate, "ci": [None, None]},
                                   "mean_utility": {"mean": util, "ci": [None, None]}},
                        "games": {"all": trials}, "personas": len(rs)})
    entries.sort(key=lambda e: (-(e["values"]["goal_rate"]["mean"] or 0), e["entrant"]))
    for i, e in enumerate(entries):
        e["rank"] = i + 1
    out = {"schema": SCHEMA, "project": cfg.project, "study": cfg.study, "track": cfg.track, "source": "tournament",
           "generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
           "query": dict(q), "options": options(cfg, ss, crit, admin=admin), "columns": ["goal_rate", "mean_utility", "games"],
           "scores": {}, "rules": dict(cfg.rules), "entries": entries, "unranked": [], "excluded": {},
           "warnings": warnings + ["the simulated table: the sort and switches do not apply to it"],
           "notes": ["simulated participants against each Assistant; goal rate = deals worth at least the persona's "
                     "reservation value"], "visibility": cfg.visibility}
    out["data_version"] = data_version(out)
    return _order(out)


def query_key(q: dict, admin: bool) -> str:
    """A short key of a view (for an ETag)."""
    return hashlib.sha1(json.dumps([q, admin], sort_keys=True).encode()).hexdigest()[:12]


def paths_of(project: str, study: str | None = None) -> Iterable[str]:
    """The studies a board reads (``P/S``), for the command line."""
    from hani2 import projects

    if study:
        return [f"{project}/{study}"]
    cfg = settings(project)
    return [f"{project}/{s}" for s in cfg.studies if projects.study_exists(projects.StudyRef(project, s))] + \
        [e["study"] for e in cfg.include if isinstance(e.get("study"), str)]
