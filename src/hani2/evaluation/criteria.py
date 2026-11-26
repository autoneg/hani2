"""Evaluation criteria: every number a score can be built from, and how each one
is mapped to ``[0, 1]`` (1 = best).

A **criterion** is a metric column (``hard``, ``soft``, ``subjective`` or ``score``)
or an answer to a questionnaire the project or study uses (``q_<id>``,
``scale_<name>``; post-session answers are ``post_q_<id>`` and
``post_scale_<name>``). :func:`catalogue` lists them with their level, direction,
default normaliser, cost and (optionally) coverage in some rows.

A **normaliser** is a small mapping, the same in Python, YAML and JSON::

    {"kind": "bounded", "lo": 1, "hi": 7}            # (x - lo) / (hi - lo), clipped
    {"kind": "advantage"}                             # clipped to [0, 1]
    {"kind": "reciprocal", "scale": "reference_median"}   # s / (s + x): lower is better
    {"kind": "saturating", "scale": "reference_median"}   # x / (x + s): higher is better
    {"kind": "percentile"}                            # share of reference games below x
    {"kind": "clip", "lo": 0, "hi": 10}               # your own bounds

With direction ``lower`` every rule is turned around (``1 - ·``); ``reciprocal``
and ``saturating`` are one rule seen from the two directions. The scale ``s`` of
the unbounded rules is the median in the project's **frozen reference**
(``projects/<p>/results/normalisation.json``, written by :func:`freeze` and
``hani2 scores freeze <project>``), so the median game scores 0.5 and adding
games never changes past scores. :func:`normalise` applies a normaliser to one
value; user-defined scores use it.

Run ``python -m hani2.evaluation.criteria docs/guide/criteria.md`` to regenerate
the reference page.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from hani2.evaluation.base import REGISTRY, Column, Metric, num

SOURCES = ("hard", "soft", "subjective", "questionnaire", "score")
LEVELS = ("negotiation", "participant")
DIRECTIONS = ("higher", "lower", "none")
COSTS = ("live", "questionnaire", "judge")  # in order of how much they need

#: the normaliser kinds: title, rule (LaTeX) and when it is the default
NORMALISER_KINDS: dict[str, tuple[str, str, str]] = {
    "bounded": ("Bounded", r"\frac{x - lo}{hi - lo}\ \text{clipped to } [0, 1]",
                "Columns with known bounds: `[0, 1]`, `0 or 1`, `1–7`, `[−1, 1]`, utilities, every questionnaire "
                "item and scale with its own bounds."),
    "advantage": ("Advantage", r"\min(1, \max(0, x))",
                  "The `*_advantage` columns: no better than no deal (or worse) is 0, the best outcome is 1."),
    "reciprocal": ("Reciprocal", r"\frac{s}{s + x}",
                   "Unbounded values where lower is better (counts, seconds, tokens, distances, US dollars)."),
    "saturating": ("Saturating", r"\frac{x}{x + s}",
                   "Unbounded values where higher is better, and unbounded values without a direction."),
    "percentile": ("Percentile", r"\frac{\#\{r < x\} + \tfrac12 \#\{r = x\}}{n}",
                   "Any criterion, on request: the share of the reference games with a lower value (ties count half)."),
    "clip": ("Clip", r"\frac{x - lo}{hi - lo}\ \text{clipped to } [0, 1]",
             "Any criterion, on request, with your own bounds."),
}
#: ``range`` texts of columns that are not numbers (they cannot be criteria)
NON_NUMERIC_RANGES = ("category", "level name", "a label", "a name")
_UNBOUNDED = ("count", "seconds", "tokens", "pixels", "us dollars", "≥ 0", ">= 0")
#: the scale of the unbounded rules unless a number is given
REFERENCE_MEDIAN = "reference_median"

REFERENCE_FILE = "normalisation.json"
REFERENCE_SCHEMA = "hani2.normalisation/1"
#: quantiles stored per criterion in a reference (0 %, 1 %, …, 100 %)
N_QUANTILES = 101
#: columns of evaluation rows that identify a game, not measure it
_ID_COLUMNS = frozenset(("key", "id", "user", "mode", "participant_type", "persona", "scenario", "opponent",
                         "support_agent", "support_model", "experiment", "started", "practice", "judge_model",
                         "assistant", "human_index"))

_NUM = r"[−-]?\d+(?:\.\d+)?"


# --------------------------------------------------------------------------- #
# Normalisers                                                                  #
# --------------------------------------------------------------------------- #
def _f(text: str) -> float:
    return float(text.replace("−", "-"))


def parse_range(text: str) -> dict | None:
    """The default normaliser that a ``Column.range`` text implies, or ``None``
    when the text does not say (``"utility difference"``) or the column is not a
    number (``"category"``)."""
    t = (text or "").strip().lower()
    if not t or t in NON_NUMERIC_RANGES:
        return None
    m = re.search(rf"[\[(]\s*({_NUM})\s*,\s*({_NUM})\s*[\])]", t)
    if m:
        return {"kind": "bounded", "lo": _f(m.group(1)), "hi": _f(m.group(2))}
    m = re.search(rf"\{{\s*({_NUM})\s*,\s*({_NUM})\s*\}}", t) or re.fullmatch(rf"({_NUM})\s+or\s+({_NUM})", t)
    if m:
        return {"kind": "bounded", "lo": _f(m.group(1)), "hi": _f(m.group(2))}
    m = re.search(rf"({_NUM})\s*[–-]\s*({_NUM})", t)
    if m:
        return {"kind": "bounded", "lo": _f(m.group(1)), "hi": _f(m.group(2))}
    if any(w in t for w in _UNBOUNDED):
        return {"kind": "saturating", "scale": REFERENCE_MEDIAN}
    return None


def check_normaliser(n: Any) -> dict:
    """A normaliser in its canonical form, or a ValueError saying what is wrong.
    A bare kind (``"percentile"``) is accepted."""
    if isinstance(n, str):
        n = {"kind": n}
    if not isinstance(n, dict):
        raise ValueError(f"a normaliser is a mapping with a 'kind', not {n!r}")
    kind = str(n.get("kind") or "")
    if kind not in NORMALISER_KINDS:
        raise ValueError(f"unknown normaliser kind {kind!r}; use one of {', '.join(NORMALISER_KINDS)}")
    out: dict[str, Any] = {"kind": kind}
    if kind in ("bounded", "clip"):
        lo, hi = num(n.get("lo")), num(n.get("hi"))
        if lo is None or hi is None:
            raise ValueError(f"a {kind} normaliser needs numbers 'lo' and 'hi'")
        if hi <= lo:
            raise ValueError(f"a {kind} normaliser needs lo < hi (got {lo:g} and {hi:g})")
        out.update(lo=lo, hi=hi)
    elif kind in ("reciprocal", "saturating"):
        s = n.get("scale", REFERENCE_MEDIAN)
        if s != REFERENCE_MEDIAN:
            v = num(s)
            if v is None or v <= 0:
                raise ValueError(f"the scale of a {kind} normaliser is a positive number or {REFERENCE_MEDIAN!r}")
            s = v
        out["scale"] = s
    return out


def describe_normaliser(n: dict | None, direction: str = "none") -> str:
    """A short text for a normaliser (``bounded [1, 7]``, ``reciprocal (s = reference median)``)."""
    if not n:
        return "none"
    kind = _oriented_kind(n["kind"], direction)
    if kind in ("bounded", "clip"):
        return f"{kind} [{n['lo']:g}, {n['hi']:g}]"
    if kind in ("reciprocal", "saturating"):
        s = n.get("scale", REFERENCE_MEDIAN)
        return f"{kind} (s = {'reference median' if s == REFERENCE_MEDIAN else f'{s:g}'})"
    return kind


def _oriented_kind(kind: str, direction: str) -> str:
    """``reciprocal`` and ``saturating`` are one rule; the direction picks the name."""
    if kind in ("reciprocal", "saturating"):
        return "reciprocal" if direction == "lower" else "saturating"
    return kind


def direction_of(col: Column) -> str:
    if col.higher_is_better is None:
        return "none"
    return "higher" if col.higher_is_better else "lower"


def is_numeric(col: Column) -> bool:
    """Whether a column holds numbers (labels, level names and categories do not)."""
    return (col.range or "").strip().lower() not in NON_NUMERIC_RANGES


def default_normaliser(col: Column) -> dict | None:
    """The column's default normaliser: its own ``normaliser``, else the one its
    ``range`` implies (``saturating`` turns into ``reciprocal`` for lower-is-better
    columns). ``None`` for columns that are not numbers."""
    if not is_numeric(col):
        return None
    n = check_normaliser(col.normaliser) if col.normaliser else parse_range(col.range)
    if n and n["kind"] in ("reciprocal", "saturating"):
        n = {**n, "kind": _oriented_kind(n["kind"], direction_of(col))}
    return n


# --------------------------------------------------------------------------- #
# The catalogue                                                                #
# --------------------------------------------------------------------------- #
@dataclass
class Criterion:
    """One number a score can use."""

    id: str
    title: str
    description: str = ""
    source: str = "hard"  #: hard | soft | subjective | questionnaire | score
    level: str = "negotiation"  #: negotiation (one value per game) | participant (one per person)
    direction: str = "none"  #: higher | lower | none
    normaliser: dict | None = None  #: the default mapping to [0, 1]
    cost: str = "live"  #: live | questionnaire | judge
    metric: str = ""  #: the metric that computes it (empty for questionnaire answers)
    range: str = ""
    #: the questionnaire form it comes from (per_negotiation, post_session), for questionnaire answers
    form: str = ""
    #: the share of the given rows that have a value (``None``: not computed)
    coverage: float | None = None
    #: whether HI scores may use it (``False`` for post-session answers of people who used several Assistants)
    hi_usable: bool = True
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["normaliser_text"] = describe_normaliser(self.normaliser, self.direction)
        return d


_KIND_SOURCE = {"hard": "hard", "soft": "soft", "subjective": "subjective", "score": "score"}
_KIND_COST = {"hard": "live", "soft": "judge", "subjective": "questionnaire"}


def _max_cost(costs: Iterable[str]) -> str:
    order = {c: i for i, c in enumerate(COSTS)}
    return max(costs, key=lambda c: order.get(c, 0), default="live")


def _metric_cost(m: Metric, seen: frozenset = frozenset()) -> str:
    """What a metric needs: ``judge`` for judged metrics, ``questionnaire`` for answers, else ``live``;
    a score needs the most of what it requires."""
    if m.kind != "score":
        return _KIND_COST.get(m.kind, "live")
    req = [REGISTRY[r] for r in m.requires if r in REGISTRY and r not in seen]
    return _max_cost(_metric_cost(r, seen | {m.name}) for r in req)


def _score_costs() -> dict[str, str]:
    """The cost of each built-in score: the most any of its components needs."""
    from hani2.evaluation import scores as _scores

    owner = {c.name: m for m in REGISTRY.values() for c in m.columns}
    out: dict[str, str] = {}
    for s in _scores.SCORES:  # in order, so a score of scores sees the earlier ones
        costs = []
        for comp in s.components:
            if comp.column in out:
                costs.append(out[comp.column])
            elif comp.column in owner:
                m = owner[comp.column]
                costs.append(_metric_cost(m) if m.kind == "score" else _KIND_COST.get(m.kind, "live"))
        out[s.name] = out[f"{s.name}_coverage"] = _max_cost(costs)
    return out


def metric_criteria() -> list[Criterion]:
    """A criterion for every numeric column of every registered metric (in registry order)."""
    score_cost = _score_costs()
    out, seen = [], set()
    for m in REGISTRY.values():
        for col in m.columns:
            if col.name in seen or not is_numeric(col):
                continue
            seen.add(col.name)
            cost = score_cost.get(col.name) or (_metric_cost(m) if m.kind == "score" else _KIND_COST.get(m.kind, "live"))
            out.append(Criterion(id=col.name, title=col.title, description=col.description,
                                 source=_KIND_SOURCE.get(m.kind, "hard"), direction=direction_of(col),
                                 normaliser=default_normaliser(col), cost=cost, metric=m.name, range=col.range))
    return out


def non_numeric_columns() -> list[str]:
    """The registered columns that are not numbers (they cannot be chosen)."""
    return [c.name for m in REGISTRY.values() for c in m.columns if not is_numeric(c)]


#: the prefix of the columns of each questionnaire form, and the level of its answers
FORM_PREFIX = {"per_negotiation": "", "post_session": "post_"}
FORM_LEVEL = {"per_negotiation": "negotiation", "post_session": "participant"}


def questionnaire_criteria(spec: dict | None, form: str = "per_negotiation") -> list[Criterion]:
    """A criterion for every numeric item (``q_<id>``) and every scale (``scale_<name>`` and
    ``scale_<name>_norm``) of one questionnaire form. Bounds come from the item types
    (``likert5``, ``likert7``, ``yes_no``, ``select``, ``min`` / ``max``); reversed items are
    already reversed, so their bounds are the same. A scale whose items have different ranges
    gets no default for its raw mean (use its ``_norm`` column)."""
    from hani2.evaluation.subjective import SCALES, item_bounds

    if not spec:
        return []
    prefix, level = FORM_PREFIX.get(form, ""), FORM_LEVEL.get(form, "negotiation")
    cost = "questionnaire"
    where = "after each negotiation" if level == "negotiation" else "once, after the last negotiation"
    items: list[Criterion] = []
    scales: dict[str, list[tuple[float, float]]] = {}
    for q in spec.get("questions") or []:
        qid, b = q.get("id"), item_bounds(q)
        if not qid or b is None or b[1] <= b[0]:
            continue
        scale = str(q["scale"]) if q.get("scale") else ""
        if scale:
            scales.setdefault(scale, []).append(b)
        d = str(q.get("direction") or ("higher" if scale else "none"))
        text = re.sub(r"[*_`]", "", str(q.get("text") or qid)).strip()
        rev = " (reversed)" if q.get("reverse") else ""
        items.append(Criterion(
            id=f"{prefix}q_{qid}", title=text if len(text) <= 80 else text[:77] + "…",
            description=f"Answer to “{text}”{rev}, asked {where}" + (f"; part of the scale {scale}" if scale else ""),
            source="questionnaire", level=level, direction=d if d in DIRECTIONS else "none",
            normaliser={"kind": "bounded", "lo": b[0], "hi": b[1]}, cost=cost, range=f"{b[0]:g}–{b[1]:g}",
            form=form))
    out: list[Criterion] = []
    for name, bounds in scales.items():
        lo, hi = {b[0] for b in bounds}, {b[1] for b in bounds}
        same = len(lo) == 1 and len(hi) == 1
        what = SCALES.get(name, name.replace("_", " "))
        out.append(Criterion(
            id=f"{prefix}scale_{name}", title=name.replace("_", " ").capitalize(),
            description=f"{what}: the mean of its {len(bounds)} item(s), asked {where}",
            source="questionnaire", level=level, direction="higher",
            normaliser={"kind": "bounded", "lo": min(lo), "hi": max(hi)} if same else None, cost=cost,
            range=f"{min(lo):g}–{max(hi):g}" if same else "mixed ranges", form=form))
        out.append(Criterion(
            id=f"{prefix}scale_{name}_norm", title=f"{name.replace('_', ' ').capitalize()} (0–1)",
            description=f"{what}, rescaled to 0–1 item by item, asked {where}",
            source="questionnaire", level=level, direction="higher",
            normaliser={"kind": "bounded", "lo": 0.0, "hi": 1.0}, cost=cost, range="[0, 1]", form=form))
    return out + items


def study_forms(project: str | None = None, study: str | None = None) -> dict[str, dict | None]:
    """The per-negotiation and post-session forms of a study, or the union over a project's studies
    (``None``: the current study). Pre-questionnaires describe people, not games, and are left out."""
    from hani2 import projects, questionnaires

    def forms() -> dict[str, dict | None]:
        return {f: questionnaires.resolve(f).spec for f in FORM_PREFIX}

    if project is None:
        return forms()
    refs = ([projects.StudyRef(project, study)] if study else
            [projects.StudyRef(project, s) for s in projects.list_studies(project)])
    if not refs:  # a project without studies: its own layer
        refs = [projects.StudyRef(project, "project-layer")]
    out: dict[str, dict | None] = {f: None for f in FORM_PREFIX}
    for ref in refs:
        with projects.use_study(ref):
            for f, spec in forms().items():
                if not spec:
                    continue
                acc = out[f] or {"questions": []}
                known = {q.get("id") for q in acc["questions"]}
                acc["questions"] += [q for q in spec.get("questions") or [] if q.get("id") not in known]
                out[f] = acc
    return out


def catalogue(project: str | None = None, study: str | None = None, rows: list[dict] | None = None,
              forms: dict[str, dict | None] | None = None) -> list[Criterion]:
    """Every criterion: metric columns, then the answers of the forms the project or study uses
    (``forms`` overrides them), with ``coverage`` and the participant-level rule filled in when
    ``rows`` (evaluation rows) are given."""
    out = metric_criteria()
    known = {c.id: c for c in out}
    forms = study_forms(project, study) if forms is None else forms
    for form, spec in forms.items():
        for c in questionnaire_criteria(spec, form):
            if c.id in known:  # a well-known scale: keep the metric's text, take the form's bounds
                k = known[c.id]
                if c.normaliser:
                    k.normaliser = c.normaliser
                k.range = c.range
                continue
            known[c.id] = c
            out.append(c)
    if rows is not None:
        apply_rows(out, rows)
    return out


def by_id(criteria: Iterable[Criterion]) -> dict[str, Criterion]:
    return {c.id: c for c in criteria}


# --------------------------------------------------------------------------- #
# Coverage and the participant-level rule                                      #
# --------------------------------------------------------------------------- #
def has_value(row: dict, cid: str) -> bool:
    return num(row.get(cid)) is not None


def coverage(rows: list[dict], cid: str) -> float | None:
    """The share of ``rows`` with a numeric value for ``cid`` (``None`` without rows)."""
    if not rows:
        return None
    return sum(has_value(r, cid) for r in rows) / len(rows)


def _assistant(row: dict) -> str:
    a = row.get("assistant_entrant") or row.get("assistant") or row.get("support_agent") or "none"
    return str(a)


def one_assistant_throughout(rows: list[dict]) -> bool:
    """Whether the games of one participant were all played with the same Assistant
    (or all without one). Only then can a post-session answer be credited to it."""
    return len({_assistant(r) for r in rows}) <= 1


def participant_key(row: dict) -> str:
    return str(row.get("participant") or row.get("user") or row.get("key") or "")


def attach_participant_answers(rows: list[dict], answers: dict[str, dict[str, Any]]) -> list[dict]:
    """Copy each participant's post-session values (``{participant: {post_q_x: 5, ...}}``, see
    :func:`post_session_values`) onto every game of theirs, **but only when they used one Assistant
    throughout**; otherwise the values are left out. Returns new rows."""
    by_person: dict[str, list[dict]] = {}
    for r in rows:
        by_person.setdefault(participant_key(r), []).append(r)
    ok = {p for p, rs in by_person.items() if one_assistant_throughout(rs)}
    out = []
    for r in rows:
        p = participant_key(r)
        vals = answers.get(p) if p in ok else None
        out.append({**r, **vals} if vals else dict(r))
    return out


def post_session_values(spec: dict | None, answers: dict | None) -> dict[str, float]:
    """The ``post_q_<id>`` / ``post_scale_<name>`` values of one participant's post-session answers."""
    from hani2.evaluation.subjective import answer_values

    if not spec or not answers:
        return {}
    return answer_values(spec, answers, prefix=FORM_PREFIX["post_session"])[0]


def apply_rows(criteria: list[Criterion], rows: list[dict], *, judged: bool | None = None) -> list[Criterion]:
    """Fill in ``coverage`` from ``rows`` and grey participant-level criteria out for HI scores when
    some participant used several Assistants. Coverage stays ``None`` (unknown) for criteria the rows
    could not contain: judged ones when the rows were evaluated without the judge (``judged`` false, or
    no row has a judge model) and post-session answers when no row carries any."""
    if judged is None:
        judged = any(r.get("judge_model") for r in rows)
    has_post = any(k.startswith("post_") for r in rows for k in r)
    by_person: dict[str, list[dict]] = {}
    for r in rows:
        by_person.setdefault(participant_key(r), []).append(r)
    mixed = sum(not one_assistant_throughout(rs) for rs in by_person.values())
    for c in criteria:
        unknown = (c.cost == "judge" and not judged) or (c.level == "participant" and not has_post)
        c.coverage = None if unknown else coverage(rows, c.id)
        if c.level == "participant" and mixed:
            c.hi_usable = False
            c.reason = (f"{mixed} participant(s) used more than one Assistant, so their post-session answers "
                        "cannot be credited to one Assistant")
    return criteria


# --------------------------------------------------------------------------- #
# References: the scale of the unbounded rules                                 #
# --------------------------------------------------------------------------- #
def stats(values: Iterable[Any]) -> dict[str, Any] | None:
    """The reference statistics of one criterion: ``n``, ``median``, ``mean``, ``min``, ``max``,
    ``quantiles`` (0 %, 1 %, …, 100 %) and ``scale``, the median, or the mean when the median is
    not positive (most games have none), or 1 when both are 0."""
    v = np.array([x for x in (num(x) for x in values) if x is not None], dtype=float)
    if v.size == 0:
        return None
    med, mu = float(np.median(v)), float(np.mean(v))
    scale = med if med > 0 else (mu if mu > 0 else 1.0)
    q = np.quantile(v, np.linspace(0, 1, N_QUANTILES))
    return {"n": int(v.size), "median": med, "mean": mu, "min": float(v.min()), "max": float(v.max()),
            "scale": scale, "quantiles": [round(float(x), 10) for x in q]}


def build_reference(rows: list[dict], *, provisional: bool = False, **meta: Any) -> dict:
    """A reference from evaluation rows: the statistics of every numeric column."""
    cols = sorted({k for r in rows for k, v in r.items() if k not in _ID_COLUMNS and num(v) is not None
                   and not isinstance(v, bool)})
    crit = {}
    for k in cols:
        s = stats([r.get(k) for r in rows])
        if s is not None:
            crit[k] = s
    return {"schema": REFERENCE_SCHEMA, "provisional": provisional, "games": len(rows), **meta, "criteria": crit}


def reference_path(project: str) -> Path:
    from hani2 import projects

    return projects.project_dir(project) / "results" / REFERENCE_FILE


def load_reference(project: str) -> dict | None:
    """The project's frozen reference, or ``None`` when none is frozen (or the file is broken)."""
    p = reference_path(project)
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("criteria"), dict) else None


def reference_setting(project: str) -> dict[str, Any]:
    """The project's ``normalisation.reference`` (``{"studies": [...], "end": "YYYY-MM-DD"}``), from
    ``project.yaml`` at the top level or under ``defaults:``. Empty when unset."""
    from hani2 import projects

    pr = projects.load_project(project)
    norm = pr.defaults.get("normalisation")
    if norm is None:
        norm = pr.extra.get("normalisation")
    ref = (norm or {}).get("reference") if isinstance(norm, dict) else None
    if not isinstance(ref, dict):
        return {}
    out: dict[str, Any] = {}
    if ref.get("studies"):
        st = ref["studies"]
        out["studies"] = [str(s) for s in ([st] if isinstance(st, str) else st)]
    if ref.get("end"):
        out["end"] = str(ref["end"])
    return out


def _end_ok(started: Any, end: str | None) -> bool:
    if not end:
        return True
    if not started:
        return False
    s = str(started)
    # an end date includes the whole day
    return s[: len(end)] <= end if len(end) <= 10 else s <= end


def reference_rows(project: str, studies: list[str] | None = None, end: str | None = None, *,
                   use_llm: bool = False, include_simulated: bool = False) -> tuple[list[dict], list[str]]:
    """The evaluation rows of the reference games: the finished, counted games (no practice, no admin
    sessions, no simulated participants) of the given studies (default: every study of the project),
    started on or before ``end``. Returns the rows and the studies read."""
    from hani2 import projects
    from hani2.evaluation import evaluate_many, load_paths

    names = list(studies or projects.list_studies(project))
    unknown = [s for s in names if not projects.study_exists(projects.StudyRef(project, s))]
    if unknown:
        raise ValueError(f"unknown study/studies in project {project!r}: {', '.join(unknown)}")
    rows: list[dict] = []
    for s in names:
        res = projects.study_dir(projects.StudyRef(project, s)) / "results"
        if not res.is_dir():
            continue
        recs = [(k, rec) for k, rec in load_paths([res])
                if rec.result is not None and not (rec.header.get("session") or {}).get("is_admin")]
        with projects.use_study(projects.StudyRef(project, s)):
            ev = evaluate_many(recs, use_llm=use_llm)
        for r in ev["rows"]:
            if r.get("practice") or (r.get("mode") == "simulated" and not include_simulated):
                continue
            if not _end_ok(r.get("started"), end):
                continue
            rows.append({**r, "study": s})
    return rows, names


def freeze(project: str, studies: list[str] | None = None, end: str | None = None, *, use_llm: bool = False,
           include_simulated: bool = False, rows: list[dict] | None = None) -> dict:
    """Compute the reference of a project and write it to ``projects/<p>/results/normalisation.json``.
    ``studies`` and ``end`` default to the project's ``normalisation.reference``. Judged criteria are
    only included with ``use_llm`` (which may call the judge for games not judged yet)."""
    setting = reference_setting(project)
    studies = studies or setting.get("studies")
    end = end or setting.get("end")
    if rows is None:
        rows, names = reference_rows(project, studies, end, use_llm=use_llm, include_simulated=include_simulated)
    else:
        names = list(studies or [])
    if not rows:
        raise ValueError(f"project {project!r} has no counted games to freeze a reference from")
    ref = build_reference(rows, project=project, studies=names, end=end, llm=use_llm,
                          frozen_at=_dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat())
    p = reference_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ref, indent=1, allow_nan=False), encoding="utf-8")
    tmp.replace(p)
    return ref


def reference_summary(ref: dict | None) -> dict[str, Any]:
    """What a board shows about its reference (without the per-criterion statistics)."""
    if not ref:
        return {"frozen": False, "provisional": True}
    return {"frozen": not ref.get("provisional"), "provisional": bool(ref.get("provisional")),
            **{k: ref.get(k) for k in ("project", "studies", "end", "games", "frozen_at", "llm") if k in ref},
            "criteria": len(ref.get("criteria") or {})}


def reference_for(project: str, rows: list[dict] | None = None) -> dict | None:
    """The project's frozen reference, else a provisional one from ``rows`` (``None`` without either)."""
    ref = load_reference(project)
    if ref is not None:
        return ref
    return build_reference(rows, provisional=True, project=project) if rows else None


# --------------------------------------------------------------------------- #
# Normalising a value                                                          #
# --------------------------------------------------------------------------- #
_INDEX: dict[str, Criterion] = {}


def _metric_index() -> dict[str, Criterion]:
    """The metric criteria by id (rebuilt when metrics are registered after the first call)."""
    global _INDEX
    if not _INDEX or len(_INDEX) != sum(1 for m in REGISTRY.values() for c in m.columns if is_numeric(c)):
        _INDEX = by_id(metric_criteria())
    return _INDEX


def _entry(reference: dict | None, cid: str) -> dict | None:
    e = ((reference or {}).get("criteria") or {}).get(cid)
    return e if isinstance(e, dict) else None


def _clip01(x: float) -> float:
    return min(1.0, max(0.0, x))


def normalise(value: Any, criterion: "Criterion | Column | str | None" = None, *, direction: str | None = None,
              normaliser: Any = None, reference: dict | None = None) -> float | None:
    """``value`` mapped to ``[0, 1]`` (1 = best), or ``None`` when it is missing or cannot be mapped.

    ``criterion`` gives the defaults (a :class:`Criterion`, a metric ``Column`` or a column id);
    ``direction`` and ``normaliser`` override them. ``reference`` (a frozen or provisional
    reference, see :func:`reference_for`) supplies the scale of ``reciprocal`` / ``saturating``
    (scale 1 without one) and the quantiles of ``percentile`` (``None`` without one)."""
    x = num(value)
    if x is None:
        return None
    if isinstance(criterion, str):
        crit = _metric_index().get(criterion)
        if crit is None:
            raise ValueError(f"unknown criterion {criterion!r}: pass questionnaire answers as a Criterion "
                             "(from catalogue())")
        cid = criterion
    elif isinstance(criterion, Column):
        crit = Criterion(id=criterion.name, title=criterion.title, direction=direction_of(criterion),
                         normaliser=default_normaliser(criterion))
        cid = criterion.name
    else:
        crit = criterion
        cid = crit.id if crit else ""
    d = direction or (crit.direction if crit else "none")
    if d not in DIRECTIONS:
        raise ValueError(f"unknown direction {d!r}; use higher, lower or none")
    n = check_normaliser(normaliser) if normaliser is not None else (crit.normaliser if crit else None)
    if not n:
        return None
    kind = n["kind"]
    if kind in ("bounded", "clip"):
        v = _clip01((x - n["lo"]) / (n["hi"] - n["lo"]))
    elif kind == "advantage":
        v = _clip01(x)
    elif kind in ("reciprocal", "saturating"):
        s = n.get("scale", REFERENCE_MEDIAN)
        if s == REFERENCE_MEDIAN:
            e = _entry(reference, cid)
            s = num(e.get("scale")) if e else None
            s = s if s and s > 0 else 1.0
        x = max(0.0, x)
        v = x / (x + s)
        if kind == "reciprocal" and d == "none":
            d = "lower"  # reciprocal says lower is better by itself
    elif kind == "percentile":
        e = _entry(reference, cid)
        q = np.asarray((e or {}).get("quantiles") or [], dtype=float)
        if q.size == 0:
            return None
        lower = np.searchsorted(q, x, side="left")
        upto = np.searchsorted(q, x, side="right")
        v = (lower + 0.5 * (upto - lower)) / q.size
    else:  # pragma: no cover - check_normaliser refuses it
        return None
    v = 1.0 - v if d == "lower" else v
    return float(v) if math.isfinite(v) else None


# --------------------------------------------------------------------------- #
# The generated docs page                                                      #
# --------------------------------------------------------------------------- #
DOCS_START = "<!-- criteria-reference:start (generated by `python -m hani2.evaluation.criteria docs/guide/criteria.md`) -->"
DOCS_END = "<!-- criteria-reference:end -->"
_SOURCE_TITLE = {"hard": "Measured from the log (hard)", "soft": "Judged by a language model (soft)",
                 "subjective": "Questionnaire scales (subjective)", "score": "Scores"}


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _bundled_form() -> dict | None:
    """The bundled evaluation questionnaire (the docs show its items as an example)."""
    import yaml

    from hani2.config import DEFAULT_SETTINGS_DIR

    p = DEFAULT_SETTINGS_DIR / "questionnaires" / "evaluation.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.is_file() else None


def markdown_reference() -> str:
    """The generated part of ``docs/guide/criteria.md`` (from the registry and the bundled files only)."""
    out = ["## Normalisers\n",
           "| Normaliser | Rule | Default for |\n| --- | --- | --- |"]
    for k, (title, rule, default) in NORMALISER_KINDS.items():
        out.append(f"| `{k}` | ${rule}$ | {_cell(default)} |")
    out.append("\nWith direction `lower`, every rule is turned around ($1 - \\cdot$). `reciprocal` and `saturating` "
               "are the same rule seen from the two directions; $s$ is the median of the project's frozen reference "
               "(the mean when the median is 0, and 1 when there is no reference yet).\n")
    crits = metric_criteria()
    counts = {s: sum(c.source == s for c in crits) for s in _SOURCE_TITLE}
    n_dir = sum(c.direction != "none" for c in crits)
    out.append("## Metric columns\n")
    out.append(f"{len(crits)} numeric columns of {len(REGISTRY)} metrics: "
               + ", ".join(f"{counts[s]} {s}" for s in _SOURCE_TITLE)
               + f". {n_dir} have a direction; the other {len(crits) - n_dir} are descriptive, so a score that "
               "uses one of them must state its direction. Every one is a game-level criterion.\n")
    for s, title in _SOURCE_TITLE.items():
        out.append(f"### {title} {{#source-{s}}}\n")
        out.append("| Criterion | Title | Direction | Default normaliser | Cost | Metric |\n"
                   "| --- | --- | --- | --- | --- | --- |")
        for c in crits:
            if c.source == s:
                out.append(f"| `{c.id}` | {_cell(c.title)} | {c.direction} | "
                           f"{describe_normaliser(c.normaliser, c.direction)} | {c.cost} | "
                           f"[`{c.metric}`](metrics.md) |")
        out.append("")
    nn = non_numeric_columns()
    out.append(f"These {len(nn)} columns are not numbers and cannot be chosen: "
               + ", ".join(f"`{c}`" for c in nn) + ".\n")
    out.append("## Questionnaire answers (the bundled evaluation questionnaire)\n")
    out.append("Each project or study lists the items and scales of its own forms. As an example, these are the "
               "criteria of the bundled `evaluation` questionnaire used after each negotiation:\n")
    out.append("| Criterion | Direction | Default normaliser | Level |\n| --- | --- | --- | --- |")
    for c in questionnaire_criteria(_bundled_form(), "per_negotiation"):
        out.append(f"| `{c.id}` | {c.direction} | {describe_normaliser(c.normaliser, c.direction)} | {c.level} |")
    return "\n".join(out).rstrip() + "\n"


def write_docs(path: str | Path) -> bool:
    """Rewrite the generated part of the docs page; ``True`` when it changed."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    a, b = text.index(DOCS_START), text.index(DOCS_END)
    new = text[: a + len(DOCS_START)] + "\n\n" + markdown_reference() + "\n" + text[b:]
    if new != text:
        p.write_text(new, encoding="utf-8")
        return True
    return False


def docs_section(text: str) -> str:
    a, b = text.index(DOCS_START), text.index(DOCS_END)
    return text[a + len(DOCS_START): b].strip() + "\n"


def api_payload(project: str | None = None, study: str | None = None, rows: list[dict] | None = None) -> dict:
    """What ``GET /api/admin/criteria`` returns."""
    crits = catalogue(project, study, rows)
    ref = load_reference(project) if project else None
    return {"criteria": [c.to_dict() for c in crits],
            "normalisers": [{"kind": k, "title": t, "rule": r, "default_for": d}
                            for k, (t, r, d) in NORMALISER_KINDS.items()],
            "sources": list(SOURCES), "levels": list(LEVELS), "directions": list(DIRECTIONS), "costs": list(COSTS),
            "not_numeric": non_numeric_columns(),
            "reference": reference_summary(ref), "games": None if rows is None else len(rows)}


if __name__ == "__main__":  # pragma: no cover
    import sys

    import hani2.evaluation  # noqa: F401  (registers the metrics)

    for f in sys.argv[1:] or ["docs/guide/criteria.md"]:
        print(f"{f}: {'updated' if write_docs(f) else 'up to date'}")
