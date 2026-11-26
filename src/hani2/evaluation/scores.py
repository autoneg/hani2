"""Scores: weighted combinations of evaluation criteria, each in [0, 1] (1 = best).

**Built-in scores** summarise a session for the two competition tracks:

* **HAN** (Human-Agent Negotiation, no Assistant) ranks Opponent agents:
  ``han_outcome`` (what the agent obtained) and ``han_interaction`` (how well it
  behaved as an opponent: the participant's impressions, the judge, no failures).
* **HI** (Hybrid Intelligence, with an Assistant) ranks Assistants:
  ``hi_outcome`` (what the human–Assistant team obtained) and
  ``hi_interaction``, the mean of ``hi_assistant`` (how well it worked as an
  Assistant) and ``hi_team`` (how well the team worked: reliance, errors,
  efficiency).
* ``utility``: the Human side's advantage alone, for any session.

**Your scores** are defined in ``project.yaml`` (and ``study.yaml``, merged key by
key) under ``scores:``, in the same format as the built-ins (:func:`definition`)::

    scores:
      hi_score:
        title: HI-score
        track: hi                       # hi | han | any
        components:
          - {criterion: human_advantage, weight: 0.6}
          - {criterion: hi_team,         weight: 0.3}     # a score inside a score
          - {criterion: n_offers, weight: 0.1, direction: lower,
             normaliser: {kind: reciprocal, scale: reference_median}}
        missing: renormalise            # renormalise | zero | skip_game
        min_coverage: 0.5

Weights are ≥ 0 and sum to 1 (:func:`parse_definition` refuses anything else when
saving, and rescales a hand-edited file on load with a warning). Each component is
mapped to [0, 1] by :func:`hani2.evaluation.criteria.normalise`, with the
direction and normaliser of the criteria catalogue unless the component gives its
own. :func:`resolve` returns the scores of a project or study (built-ins, the
project's, the study's) with their problems, and ``scores_enabled`` picks the ones
that are shown. :func:`score_row` computes scores for one evaluation row and
:func:`active_components` drops, for everyone, a component that some entrant has
in fewer than ``min_coverage`` of its games.

The built-ins' weights can still be changed in ``env.json``::

    {"evaluation": {"scores": {"hi_assistant": {"weights": {"ja_overall": 2, "fn_success_rate": 0}}}}}

(a weight of 0 drops a component) or with the metric option ``scores``.
:func:`hani2.evaluation.leaderboard` ranks the entrants of a track.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from hani2.evaluation.base import Column, EvalContext, metric, num

log = logging.getLogger(__name__)

#: the built-ins' normalisers by their old names: raw value -> [0, 1] (higher is better)
NORMALISERS: dict[str, tuple[str, str, Any]] = {
    "unit": ("the value, clipped to [0, 1]", r"\min(1, \max(0, x))", lambda x: min(1.0, max(0.0, x))),
    "likert7": ("a 1–7 rating mapped to [0, 1]", r"(x - 1) / 6", lambda x: min(1.0, max(0.0, (x - 1) / 6))),
    "advantage": ("an advantage clipped to [0, 1] (no better than no deal = 0)", r"\min(1, \max(0, x))",
                  lambda x: min(1.0, max(0.0, x))),
    "inverse": ("one minus a [0, 1] value where lower is better (e.g. a 0/1 flag)", r"1 - \min(1, \max(0, x))",
                lambda x: 1.0 - min(1.0, max(0.0, x))),
    "count": ("a count where lower is better", r"1 / (1 + x)", lambda x: 1.0 / (1.0 + max(0.0, x))),
}
#: the same rules as definitions (a direction and a catalogue normaliser) that give the same values
LEGACY_RULES: dict[str, tuple[str, dict]] = {
    "unit": ("higher", {"kind": "bounded", "lo": 0.0, "hi": 1.0}),
    "likert7": ("higher", {"kind": "bounded", "lo": 1.0, "hi": 7.0}),
    "advantage": ("higher", {"kind": "advantage"}),
    "inverse": ("lower", {"kind": "bounded", "lo": 0.0, "hi": 1.0}),
    # 1 - x / (x + 1) = 1 / (1 + x); a fixed scale, so no reference can change it
    "count": ("lower", {"kind": "reciprocal", "scale": 1.0}),
}

TRACK_VALUES = ("hi", "han", "any")
MISSING_POLICIES = ("renormalise", "zero", "skip_game")
DEFAULT_MISSING = "renormalise"
DEFAULT_MIN_COVERAGE = 0.5
#: how far from 1 the weights of a score may sum
WEIGHT_TOLERANCE = 1e-6
SCORE_KEYS = ("title", "description", "track", "components", "missing", "min_coverage")
COMPONENT_KEYS = ("criterion", "weight", "direction", "normaliser", "label")
_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
#: prefixes of questionnaire columns (a score key must not look like one)
_RESERVED_PREFIXES = ("q_", "scale_", "post_q_", "post_scale_")


@dataclass
class Component:
    column: str
    weight: float
    #: the built-ins' rule name (see :data:`NORMALISERS`); empty for defined scores
    norm: str = "unit"
    label: str = ""
    #: ``higher`` or ``lower`` (filled in from :data:`LEGACY_RULES` or the catalogue)
    direction: str = ""
    #: the mapping to [0, 1] (a :mod:`~hani2.evaluation.criteria` normaliser)
    normaliser: dict | None = None

    def __post_init__(self) -> None:
        if self.norm and (not self.direction or self.normaliser is None):
            d, n = LEGACY_RULES[self.norm]
            self.direction = self.direction or d
            self.normaliser = dict(n) if self.normaliser is None else self.normaliser

    @property
    def criterion(self) -> str:
        return self.column


@dataclass
class Score:
    name: str
    title: str
    track: str  # "han", "hi" or "any"
    board: str  # "outcome" or "interaction" ("" for defined scores)
    description: str
    components: list[Component]
    details: str = ""
    #: columns that, when 1, force the score to 0 (e.g. the opponent failed)
    zero_if: list[str] = field(default_factory=list)
    #: only for sessions with an Assistant (empty otherwise)
    needs_assistant: bool = False
    missing: str = DEFAULT_MISSING
    min_coverage: float = DEFAULT_MIN_COVERAGE
    #: where it is defined: ``builtin``, ``project`` or ``study``
    origin: str = "builtin"

    @property
    def builtin(self) -> bool:
        return self.origin == "builtin"


def _c(col, w, norm="unit", label=""):
    return Component(col, w, norm, label)


SCORES: list[Score] = [
    Score("han_outcome", "HAN outcome", "han", "outcome",
          "What the Opponent agent obtained against the Human (Human-Agent Negotiation track)",
          [_c("opponent_advantage", 1, "advantage", "the Opponent's advantage")],
          zero_if=["opponent_failed"],
          details=r"""
The outcome board of the Human-Agent Negotiation track ranks Opponent agents by the share of their
largest possible gain over no deal that they obtained against human participants. No deal scores 0,
and so does a session that the agent ended by failing.
"""),
    Score("han_interaction", "HAN interaction", "han", "interaction",
          "How well the Opponent agent behaved as an opponent (Human-Agent Negotiation track)",
          [_c("scale_opponent_kindness_norm", 1, label="questionnaire: kindness"),
           _c("scale_opponent_intelligence_norm", 1, label="questionnaire: intelligence"),
           _c("scale_opponent_humanlike_norm", 1, label="questionnaire: human-likeness"),
           _c("scale_relationship_norm", 1, label="questionnaire: wanting to negotiate again"),
           _c("scale_satisfaction_norm", 0.5, label="questionnaire: the participant's satisfaction"),
           _c("jo_overall", 1, "likert7", "judge: overall"),
           _c("jo_communication", 0.5, "likert7", "judge: communication"),
           _c("jo_consistency", 0.5, "likert7", "judge: consistency"),
           _c("jo_human_likeness", 0.5, "likert7", "judge: human-likeness"),
           _c("opponent_failed", 1, "inverse", "did not fail"),
           _c("opponent_irrational_accept", 0.5, "inverse", "did not accept below its reservation value")],
          details=r"""
The interaction board of the Human-Agent Negotiation track: how the participants experienced the
agent (questionnaire), how a language-model judge rates its behaviour and messages, and whether it
negotiated soundly (no failure, no deal accepted below its own reservation value).
"""),
    Score("hi_outcome", "HI outcome", "hi", "outcome",
          "What the human–Assistant team obtained (Hybrid Intelligence track)",
          [_c("human_advantage", 1, "advantage", "the Human side's advantage")],
          details=r"""
The outcome board of the Hybrid Intelligence track ranks Assistants by the share of the largest
possible gain over no deal that the team (the Human with the Assistant) obtained. No deal scores 0.
"""),
    Score("hi_assistant", "HI Assistant", "hi", "interaction",
          "How well the Assistant worked as an Assistant (Hybrid Intelligence track)",
          [_c("ja_overall", 1, "likert7", "judge: overall"),
           _c("ja_helpfulness", 0.5, "likert7", "judge: helpfulness"),
           _c("ja_autonomy_respect", 0.5, "likert7", "judge: left the Human in control"),
           _c("assertions_met", 1, label="judge: assertions met"),
           _c("task_communicated", 1, label="judge: scenario facts conveyed"),
           _c("assistant_critical_errors", 1, "count", "judge: critical errors"),
           _c("assistant_errors", 0.5, "count", "judge: errors"),
           _c("irrational_suggestions", 1, "count", "suggestions below the reservation value"),
           _c("fn_success_rate", 0.5, label="function calls that worked"),
           _c("unanswered_messages", 0.5, "count", "unanswered messages"),
           _c("scale_ueq_pragmatic_norm", 0.5, label="questionnaire: UEQ pragmatic quality"),
           _c("scale_tam_usefulness_norm", 0.5, label="questionnaire: usefulness"),
           _c("scale_felt_heard_norm", 0.5, label="questionnaire: felt heard"),
           _c("scale_intention_to_use_norm", 0.5, label="questionnaire: would use it again")],
          needs_assistant=True,
          details=r"""
The Assistant itself: how a language-model judge rates its help, whether it conveyed what the
scenario requires and met the assertions, its errors, unsound suggestions, technical reliability and
responsiveness, and how the participant experienced it.
"""),
    Score("hi_team", "HI team", "hi", "interaction",
          "How well the human–Assistant team worked together (Hybrid Intelligence track)",
          [_c("human_overrode_harmfully", 1, "count", "judge: harmful overrides of the Assistant"),
           _c("human_critical_errors", 1, "count", "judge: the Human's critical errors"),
           _c("jh_use_of_assistant", 1, "likert7", "judge: use of the Assistant"),
           _c("jh_engagement", 0.5, "likert7", "judge: engagement"),
           _c("always_follows", 0.5, "inverse", "did not blindly follow every suggestion"),
           _c("click_through", 0.5, "inverse", "did not click through"),
           _c("irrational_accept", 1, "inverse", "did not accept below the reservation value"),
           _c("welfare_optimality", 0.5, label="efficiency of the result")],
          needs_assistant=True,
          details=r"""
The team: appropriate reliance on the Assistant (neither ignoring it harmfully nor following it
blindly), the Human's engagement and critical errors, a sound final decision and an efficient result.
"""),
    Score("hi_interaction", "HI interaction", "hi", "interaction",
          "The Assistant and the team together: the ranked score of the HI interaction board",
          [_c("hi_assistant", 1, label="the HI Assistant score"), _c("hi_team", 1, label="the HI team score")],
          needs_assistant=True,
          details=r"""
The interaction board of the Hybrid Intelligence track ranks Assistants by the mean of how well they
worked as an Assistant (`hi_assistant`) and how well their teams worked (`hi_team`).
"""),
    Score("utility", "Utility", "any", "outcome",
          "The Human side's advantage alone, for any session",
          [_c("human_advantage", 1, "advantage", "the Human side's advantage")],
          details=r"""
The simplest score: the share of the largest possible gain over no deal that the Human side obtained,
with or without an Assistant. No deal scores 0. Every project and study has it.
"""),
]
BY_NAME = {s.name: s for s in SCORES}


def _weights(score: Score, options: dict | None) -> dict[str, float]:
    """The components' weights; a built-in's after the overrides of ``env.json`` and ``options``
    (a defined score's weights are its own: they sum to 1)."""
    w = {c.column: float(c.weight) for c in score.components}
    if not score.builtin:
        return w
    from hani2.config import get_env

    for src in (get_env("evaluation.scores", None), (options or {}).get("scores")):
        if isinstance(src, dict) and isinstance(src.get(score.name), dict):
            for k, v in (src[score.name].get("weights") or {}).items():
                if k in w and num(v) is not None:
                    w[k] = float(v)
    return w


def component_value(c: Component, row: dict, reference: dict | None = None) -> float | None:
    """The component's value in ``row`` mapped to [0, 1] (``None`` when missing)."""
    from hani2.evaluation.criteria import Criterion, normalise

    x = num(row.get(c.column))
    if x is None:
        return None
    return normalise(x, Criterion(id=c.column, title=c.column, direction=c.direction or "higher",
                                  normaliser=c.normaliser), reference=reference)


def compute(score: Score, row: dict, *, options: dict | None = None, only: set[str] | None = None,
            reference: dict | None = None) -> tuple[float | None, float | None]:
    """``(score, coverage)`` of one row; ``only`` restricts the components. Coverage is the share
    of the weight whose components had a value. A missing value is left out and the others
    rescaled (``renormalise``), counts as 0 (``zero``) or leaves the game without a score
    (``skip_game``)."""
    w = _weights(score, options)
    if score.needs_assistant and str(row.get("support_agent") or "none") == "none":
        return None, None
    if any(num(row.get(z)) == 1 for z in score.zero_if):
        return 0.0, 1.0
    total = got = acc = 0.0
    for c in score.components:
        wt = w.get(c.column, 0.0)
        if wt <= 0 or (only is not None and c.column not in only):
            continue
        total += wt
        v = component_value(c, row, reference)
        if v is None:
            continue
        acc += wt * float(v)
        got += wt
    if total <= 0:
        return None, None
    cov = got / total
    if score.missing == "zero":
        v = acc / total
    elif score.missing == "skip_game" and got < total * (1 - 1e-12):
        return None, cov
    elif got <= 0:
        return None, 0.0
    else:
        v = acc / got
    return (v if math.isfinite(v) else None), cov


def score_row(row: dict, options: dict | None = None, only: dict[str, set[str]] | None = None, *,
              scores: Iterable[Score] | None = None, reference: dict | None = None) -> dict:
    """Every score (and its coverage) of a row, in order (scores of scores see
    the earlier ones). ``only`` restricts the components per score; ``scores``
    (default: the built-ins) must be in dependency order, as :func:`resolve` gives them."""
    r = dict(row)
    out: dict[str, Any] = {}
    for s in (SCORES if scores is None else scores):
        v, cov = compute(s, r, options=options, only=(only or {}).get(s.name), reference=reference)
        r[s.name] = v
        out[s.name], out[f"{s.name}_coverage"] = v, cov
    return out


def active_components(rows: list[dict], scores: Iterable[Score], group: Callable[[dict], Any], *,
                      min_coverage: float | None = None, blocked: set[str] | None = None) -> dict[str, set[str]]:
    """Per score, the components present in at least ``min_coverage`` (default: each score's own) of
    the games of **every** entrant (``group(row)`` names a row's entrant), so every entrant is scored
    on the same parts; the others are dropped for everyone. A score inside a score is kept when that
    score kept any component. ``blocked`` columns are never used. ``scores`` must be in dependency
    order."""
    groups: dict[Any, list[dict]] = {}
    for r in rows:
        groups.setdefault(group(r), []).append(r)
    out: dict[str, set[str]] = {}
    names = set()
    for s in scores:
        names.add(s.name)
        mc = s.min_coverage if min_coverage is None else min_coverage
        keep = set()
        for c in s.components:
            if c.column in names or c.column in BY_NAME:
                if out.get(c.column):
                    keep.add(c.column)
                continue
            if blocked and c.column in blocked:
                continue
            if groups and all(sum(1 for r in rs if num(r.get(c.column)) is not None) / len(rs) >= mc
                              for rs in groups.values()):
                keep.add(c.column)
        out[s.name] = keep
    return out


def weights_in_effect(score: Score, active: set[str] | None = None, options: dict | None = None) -> dict[str, float]:
    """The weights a score uses, rescaled to sum to 1 (only the ``active`` components when given)."""
    w = {k: v for k, v in _weights(score, options).items() if v > 0 and (active is None or k in active)}
    total = sum(w.values())
    return {k: v / total for k, v in w.items()} if total > 0 else {}


def flattened(name: str, scores: dict[str, Score], options: dict | None = None) -> dict[str, float]:
    """A score's weights flattened down to criteria (a score inside a score shares out its weight)."""
    out: dict[str, float] = {}

    def walk(n: str, share: float, seen: frozenset) -> None:
        for k, v in weights_in_effect(scores[n], options=options).items():
            if k in scores and k not in seen:
                walk(k, share * v, seen | {k})
            else:
                out[k] = out.get(k, 0.0) + share * v

    walk(name, 1.0, frozenset({name}))
    return out


# --------------------------------------------------------------------------- #
# Definitions: the format of project.yaml and study.yaml                       #
# --------------------------------------------------------------------------- #
def definition(score: Score, options: dict | None = None) -> dict[str, Any]:
    """A score in the format of ``scores:`` (the built-ins' weights rescaled to sum to 1)."""
    w = weights_in_effect(score, options=options)
    comps = []
    for c in score.components:
        d: dict[str, Any] = {"criterion": c.column, "weight": round(w.get(c.column, 0.0), 12)}
        if c.direction:
            d["direction"] = c.direction
        if c.normaliser:
            d["normaliser"] = dict(c.normaliser)
        if c.label:
            d["label"] = c.label
        comps.append(d)
    out: dict[str, Any] = {"title": score.title, "description": score.description, "track": score.track,
                           "components": comps, "missing": score.missing, "min_coverage": score.min_coverage}
    if score.builtin:
        out["builtin"] = True
        if score.board:
            out["board"] = score.board
        if score.zero_if:
            out["zero_if"] = list(score.zero_if)
        if score.needs_assistant:
            out["needs_assistant"] = True
    return out


def metric_column_names() -> set[str]:
    """Every column of every registered metric (a score key must not be one)."""
    from hani2.evaluation.base import REGISTRY

    return {c.name for m in REGISTRY.values() for c in m.columns}


def check_key(key: Any) -> list[str]:
    """What is wrong with a score key: its form, and clashes with columns and built-ins."""
    if not isinstance(key, str) or not _KEY.match(key):
        return [f"score key {key!r}: use a letter, then letters, digits and '_' (at most 64)"]
    if key in BY_NAME:
        return [f"score {key!r} is built in and read-only: duplicate it under another key to change it"]
    cols = metric_column_names()
    if key in cols or f"{key}_coverage" in cols or key.endswith("_coverage"):
        return [f"score key {key!r} is the name of a column: choose another"]
    if key.startswith(_RESERVED_PREFIXES):
        return [f"score key {key!r} looks like a questionnaire answer (q_, scale_, post_…): choose another"]
    return []


def _is_weight(v: Any) -> bool:
    return not isinstance(v, bool) and num(v) is not None


def parse_definition(key: str, data: Any, *, strict: bool = True,
                     origin: str = "project") -> tuple[Score | None, list[str], list[str]]:
    """A defined score from its ``scores:`` entry: ``(score, problems, warnings)``. The score is
    ``None`` when there is a problem. Weights must be ≥ 0 and sum to 1 (within
    :data:`WEIGHT_TOLERANCE`); with ``strict`` false (a hand-edited file being loaded) other sums
    are rescaled with a warning instead. Directions and normalisers that the catalogue supplies
    are filled in by :func:`resolve`."""
    from hani2.evaluation.criteria import DIRECTIONS, check_normaliser

    where = f"score {key!r}"
    problems = check_key(key)
    warnings: list[str] = []
    if not isinstance(data, dict):
        return None, problems + [f"{where} must be a mapping (title, track, components, …)"], warnings
    unknown = sorted(set(data) - set(SCORE_KEYS))
    if unknown:
        problems.append(f"{where}: unknown key(s) {', '.join(unknown)}; use {', '.join(SCORE_KEYS)}")
    track = str(data.get("track") or "any")
    if track not in TRACK_VALUES:
        problems.append(f"{where}: track must be one of {', '.join(TRACK_VALUES)} (got {track!r})")
    missing = str(data.get("missing") or DEFAULT_MISSING)
    if missing not in MISSING_POLICIES:
        problems.append(f"{where}: missing must be one of {', '.join(MISSING_POLICIES)} (got {missing!r})")
    mc = data.get("min_coverage", DEFAULT_MIN_COVERAGE)
    if mc is None:
        mc = DEFAULT_MIN_COVERAGE
    if not _is_weight(mc) or not 0 <= float(mc) <= 1:
        problems.append(f"{where}: min_coverage must be a number from 0 to 1 (got {mc!r})")
        mc = DEFAULT_MIN_COVERAGE
    for k in ("title", "description"):
        if data.get(k) is not None and not isinstance(data.get(k), str):
            problems.append(f"{where}: {k} must be text")
    raw = data.get("components")
    comps: list[Component] = []
    if not isinstance(raw, list) or not raw:
        problems.append(f"{where}: components must be a non-empty list of {{criterion, weight}}")
        raw = []
    seen: set[str] = set()
    for i, c in enumerate(raw, 1):
        cw = f"{where}, component {i}"
        if not isinstance(c, dict):
            problems.append(f"{cw} must be a mapping with a criterion and a weight")
            continue
        bad = sorted(set(c) - set(COMPONENT_KEYS))
        if bad:
            problems.append(f"{cw}: unknown key(s) {', '.join(bad)}; use {', '.join(COMPONENT_KEYS)}")
        crit = c.get("criterion")
        if not isinstance(crit, str) or not crit:
            problems.append(f"{cw}: criterion is missing")
            continue
        cw = f"{where}, component {crit!r}"
        if crit in seen:
            problems.append(f"{cw} is given twice")
            continue
        seen.add(crit)
        if crit == key:
            problems.append(f"{where} contains itself")
        wt = c.get("weight")
        if not _is_weight(wt) or float(wt) < 0:
            problems.append(f"{cw}: weight must be a number ≥ 0 (got {wt!r})")
            continue
        d = c.get("direction")
        if d is not None and (d not in DIRECTIONS):
            problems.append(f"{cw}: direction must be higher or lower (got {d!r})")
            d = None
        n = c.get("normaliser")
        if n is not None:
            try:
                n = check_normaliser(n)
            except ValueError as e:
                problems.append(f"{cw}: {e}")
                n = None
        comps.append(Component(crit, float(wt), norm="", label=str(c.get("label") or ""),
                               direction="" if d in (None, "none") else str(d), normaliser=n))
    total = sum(c.weight for c in comps)
    if comps and total <= 0:
        problems.append(f"{where}: the weights sum to 0; give at least one component a weight above 0")
    elif comps and abs(total - 1) > WEIGHT_TOLERANCE:
        msg = f"{where}: the weights sum to {total:.6g} ({100 * total:.4g} %), not 1 (100 %)"
        if strict:
            problems.append(msg + "; rescale them (Normalise) before saving")
        else:
            warnings.append(msg + "; rescaled to sum to 1")
            for c in comps:
                c.weight = c.weight / total
    if problems:
        return None, problems, warnings
    return Score(name=key, title=str(data.get("title") or key), track=track, board="",
                 description=str(data.get("description") or ""), components=comps, missing=missing,
                 min_coverage=float(mc), origin=origin), problems, warnings


def file_problems(value: Any, where: str = "scores", *, strict: bool = True) -> tuple[list[str], list[str]]:
    """``(problems, warnings)`` of a ``scores:`` mapping as written in one file: each definition's
    form, weights and keys, and cycles among its own scores. Criteria are checked by :func:`resolve`,
    which knows the catalogue."""
    if value is None:
        return [], []
    if not isinstance(value, dict):
        return [f"'{where}' must be a mapping of score keys to definitions"], []
    problems: list[str] = []
    warnings: list[str] = []
    parsed: dict[str, Score] = {}
    for k, d in value.items():
        if d is None:  # a study's ``key: null`` removes the project's score
            continue
        sc, p, w = parse_definition(k, d, strict=strict)
        problems += [f"{where}: {x}" for x in p]
        warnings += [f"{where}: {x}" for x in w]
        if sc is not None:
            parsed[k] = sc
    for cyc in _cycles(parsed):
        problems.append(f"{where}: scores contain each other in a cycle: {' → '.join(cyc + [cyc[0]])}")
    return problems, warnings


def enabled_problems(value: Any, where: str = "scores_enabled") -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
        return [f"'{where}' must be a list of score keys"]
    return []


def _deps(s: Score, known: Iterable[str]) -> list[str]:
    k = set(known)
    return [c.column for c in s.components if c.column in k]


def _cycles(scores: dict[str, Score]) -> list[list[str]]:
    """The cycles among ``scores`` (each once, as a list of keys)."""
    out: list[list[str]] = []
    state: dict[str, int] = {}
    stack: list[str] = []
    found: set[frozenset] = set()

    def visit(n: str) -> None:
        state[n] = 1
        stack.append(n)
        for d in _deps(scores[n], scores):
            if state.get(d) == 1:
                cyc = stack[stack.index(d):]
                if frozenset(cyc) not in found:
                    found.add(frozenset(cyc))
                    out.append(list(cyc))
            elif d not in state:
                visit(d)
        stack.pop()
        state[n] = 2

    for n in scores:
        if n not in state:
            visit(n)
    return out


def _order(scores: dict[str, Score]) -> list[str]:
    """``scores`` in dependency order (a score after the scores it contains); no cycles."""
    out: list[str] = []
    done: set[str] = set()

    def visit(n: str) -> None:
        if n in done:
            return
        done.add(n)
        for d in _deps(scores[n], scores):
            visit(d)
        out.append(n)

    for n in scores:
        visit(n)
    return out


# --------------------------------------------------------------------------- #
# The scores of a project or study                                             #
# --------------------------------------------------------------------------- #
@dataclass
class ScoreSet:
    """The scores of a project or study."""

    #: every usable score (built-ins first), in dependency order
    scores: dict[str, Score]
    #: the scores shown in boards, results views and exports (``scores_enabled``)
    enabled: list[str]
    #: what is wrong (a score with a problem is left out)
    problems: list[str] = field(default_factory=list)
    #: what was fixed on load (weights rescaled)
    warnings: list[str] = field(default_factory=list)
    #: the definitions as written, by key (``project`` and ``study``)
    defined: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: whether ``scores_enabled`` was set (else the default: every score)
    enabled_set_by: str = "default"

    def needed(self, names: Iterable[str] | None = None) -> list[Score]:
        """The scores to compute for ``names`` (default: the enabled ones), with the scores inside
        them, in dependency order."""
        want: set[str] = set()

        def add(n: str) -> None:
            if n in want or n not in self.scores:
                return
            want.add(n)
            for d in _deps(self.scores[n], self.scores):
                add(d)

        for n in (self.enabled if names is None else names):
            add(n)
        return [s for k, s in self.scores.items() if k in want]

    def to_dict(self, options: dict | None = None) -> dict[str, Any]:
        return {"scores": [{"key": k, "origin": s.origin, "enabled": k in self.enabled,
                            **definition(s, options), "flattened": flattened(k, self.scores, options)}
                           for k, s in self.scores.items()],
                "enabled": list(self.enabled), "enabled_set_by": self.enabled_set_by,
                "problems": list(self.problems), "warnings": list(self.warnings)}


def _file_scores(layer: dict, key: str = "scores") -> dict:
    v = layer.get(key)
    return dict(v) if isinstance(v, dict) else {}


def resolve(project: str | None = None, study: str | None = None, *, strict: bool = False,
            project_scores: dict | None = None, study_scores: dict | None = None,
            project_enabled: Any = ..., study_enabled: Any = ..., rows: list[dict] | None = None,
            criteria: list | None = None) -> ScoreSet:
    """The scores of a project (or of a study: the project's, then the study's, merged key by key):
    the built-ins, then the defined ones in dependency order, each component with its direction and
    normaliser from the catalogue unless it gives its own. A score with a problem (unknown
    criterion, no direction or normaliser, a cycle, a score inside it that has a problem, the
    participant-level rule) is left out and named in ``problems``.

    ``project_scores``, ``study_scores``, ``project_enabled`` and ``study_enabled`` replace what the
    files say (to check a change before saving it); ``strict`` refuses weights that do not sum to 1
    instead of rescaling them. ``rows`` (evaluation rows) apply the participant-level rule: a ``hi``
    score may not use a post-session answer when some participant used more than one Assistant."""
    from hani2 import projects
    from hani2.evaluation import criteria as C

    pdefs: dict = {}
    sdefs: dict = {}
    pen: Any = None
    sen: Any = None
    if project:
        pr = projects.load_project(project)
        pdefs, pen = _file_scores(pr.defaults), pr.defaults.get("scores_enabled")
        if study:
            st = projects.load_study(projects.StudyRef(project, study))
            sdefs, sen = _file_scores(st.overrides), st.overrides.get("scores_enabled")
    pdefs = pdefs if project_scores is None else dict(project_scores)
    sdefs = sdefs if study_scores is None else dict(study_scores)
    pen = pen if project_enabled is ... else project_enabled
    sen = sen if study_enabled is ... else study_enabled
    merged: dict[str, tuple[str, Any]] = {k: ("project", v) for k, v in pdefs.items()}
    merged.update({k: ("study", v) for k, v in sdefs.items() if v is not None})
    for k, v in sdefs.items():  # ``key: null`` in a study removes the project's score
        if v is None:
            merged.pop(k, None)
    problems: list[str] = []
    warnings: list[str] = []
    parsed: dict[str, Score] = {}
    for k, (origin, d) in merged.items():
        sc, p, w = parse_definition(k, d, strict=strict, origin=origin)
        problems += [f"{origin}: {x}" for x in p]
        warnings += [f"{origin}: {x}" for x in w]
        if sc is not None:
            parsed[k] = sc
    for cyc in _cycles(parsed):
        problems.append(f"scores contain each other in a cycle: {' → '.join(cyc + [cyc[0]])}")
        for k in cyc:
            parsed.pop(k, None)
    cat = criteria if criteria is not None else C.catalogue(project, study, rows)
    if rows is not None and criteria is not None:
        C.apply_rows(cat, rows)
    # defined scores come from ``merged`` (which may be a change not saved yet), not from the files
    by = {k: v for k, v in C.by_id(cat).items() if not (v.source == "score" and not v.metric)}
    bad: set[str] = set()
    for k, s in parsed.items():
        for c in s.components:
            where = f"score {k!r}, component {c.column!r}"
            if c.column in merged or c.column in BY_NAME:  # a score inside a score
                c.direction = c.direction or "higher"
                c.normaliser = c.normaliser or {"kind": "bounded", "lo": 0.0, "hi": 1.0}
                continue
            crit = by.get(c.column)
            if crit is None:
                problems.append(f"{where}: unknown criterion (not a metric column, a questionnaire answer of "
                                "this project or study, or a score)")
                bad.add(k)
                continue
            if not c.direction:
                if crit.direction == "none":
                    problems.append(f"{where}: the criterion has no direction; give direction: higher or lower")
                    bad.add(k)
                    continue
                c.direction = crit.direction
            if c.normaliser is None:
                if not crit.normaliser:
                    problems.append(f"{where}: the criterion has no default normaliser; give one "
                                    "(for example {kind: bounded, lo: 0, hi: 10})")
                    bad.add(k)
                    continue
                c.normaliser = dict(crit.normaliser)
            if s.track == "hi" and crit.level == "participant" and not crit.hi_usable:
                problems.append(f"{where}: a post-session answer cannot be used in an HI score here: {crit.reason}")
                bad.add(k)
    # a score that contains a score with a problem has one too
    changed = True
    while changed:
        changed = False
        for k, s in parsed.items():
            if k in bad:
                continue
            gone = [c.column for c in s.components if c.column in merged and (c.column in bad or c.column not in parsed)]
            if gone:
                problems.append(f"score {k!r} contains {', '.join(map(repr, gone))}, which has a problem")
                bad.add(k)
                changed = True
    for k in bad:
        parsed.pop(k, None)
    scores: dict[str, Score] = dict(BY_NAME)
    for k in _order(parsed):
        scores[k] = parsed[k]
    enabled_src, by_src = (sen, "study") if sen is not None else ((pen, "project") if pen is not None else (None, "default"))
    for where, v in (("project", pen), ("study", sen)):
        problems += [f"{where}: {x}" for x in enabled_problems(v)]
    if isinstance(enabled_src, list):
        unknown = [x for x in enabled_src if isinstance(x, str) and x not in scores and x not in merged]
        if unknown:
            problems.append(f"scores_enabled ({by_src}): unknown score(s) {', '.join(unknown)}")
        enabled = list(dict.fromkeys(x for x in enabled_src if isinstance(x, str) and x in scores))
    else:
        enabled, by_src = list(scores), "default"
    for w in warnings:
        log.warning("[hani2] %s%s: %s", project or "", f"/{study}" if study else "", w)
    return ScoreSet(scores=scores, enabled=enabled, problems=list(dict.fromkeys(problems)), warnings=warnings,
                    defined={k: d for k, (_, d) in merged.items()}, enabled_set_by=by_src)


def check(project: str | None = None, study: str | None = None, **kw: Any) -> list[str]:
    """Every problem of the scores of a project or study (empty: they can be saved). Weight sums
    that are not 1 are problems here."""
    return resolve(project, study, strict=True, **kw).problems


def score_rows(rows: list[dict], scores: ScoreSet | Iterable[Score], *, names: Iterable[str] | None = None,
               group: Callable[[dict], Any] | None = None, reference: dict | None = None,
               options: dict | None = None) -> list[dict]:
    """``rows`` with the scores ``names`` (default: the enabled ones) and their coverage added.
    With ``group`` (a row's entrant) a component that some entrant has in fewer than the score's
    ``min_coverage`` of its games is dropped for everyone (:func:`active_components`)."""
    lst = scores.needed(names) if isinstance(scores, ScoreSet) else list(scores)
    only = active_components(rows, lst, group) if group is not None else None
    return [{**r, **score_row(r, options, only, scores=lst, reference=reference)} for r in rows]


# --------------------------------------------------------------------------- #
# The metric (and its reference texts, generated from the definitions)         #
# --------------------------------------------------------------------------- #
def _score_details(s: Score) -> str:
    rows = "\n".join(f"| `{c.column}` | {c.label} | {c.weight:g} | {NORMALISERS[c.norm][0]}: ${NORMALISERS[c.norm][1]}$ |"
                     for c in s.components)
    zero = (f"\n\nThe score is 0 when {', '.join(f'`{z}`' for z in s.zero_if)} is 1." if s.zero_if else "")
    if s.needs_assistant:
        zero += "\n\nEmpty for sessions without an Assistant."
    return (s.details.strip() + "\n\n| Component | What | Weight | Normalised as |\n| --- | --- | --- | --- |\n" + rows
            + zero + "\n\nComponents without a value are left out (see `" + s.name + "_coverage`).")


def _columns() -> list[Column]:
    out = []
    for s in SCORES:
        out.append(Column(s.name, s.title, s.description, True,
                          formula=r"S = \frac{\sum_{i \in P} w_i\, \phi_i(x_i)}{\sum_{i \in P} w_i}", range="[0, 1]",
                          details=_score_details(s)))
        out.append(Column(f"{s.name}_coverage", f"{s.title} coverage", f"Share of the weight of {s.name} that had a value",
                          True, formula=r"\frac{\sum_{i \in P} w_i}{\sum_{i} w_i}", range="[0, 1]",
                          details=f"""
The share of the total weight of `{s.name}` whose components had a value in this session: 1 when
every component was measured, lower when (for example) there was no questionnaire or no judge.
Compare scores only between sessions with similar coverage; the leaderboards use the same
components for every entrant.
"""))
    return out


@metric("scores", kind="score", title="Combined scores (HAN and HI tracks)", stage=2,
        requires=["outcome", "optimality", "rule_checks", "system_use", "engagement_flags", "assistant_interaction",
                  "task_success"],
        options={"scores": "Weight overrides: {score: {weights: {column: weight}}} (0 drops a component)."},
        formula=r"S = \frac{\sum_{i \in P} w_i\, \phi_i(x_i)}{\sum_{i \in P} w_i}, \qquad P = \{i : x_i \text{ has a value}\}",
        details=r"""
A few numbers in $[0, 1]$ (higher is better) that summarise a session for the two competition tracks.
Each is a weighted mean of components $x_i$ taken from the other metrics, each normalised to $[0, 1]$
by $\phi_i$ (ratings of 1–7 become $(x - 1)/6$, error counts $1/(1 + x)$, flags $1 - x$). Components
without a value (no questionnaire, no language-model judge) are left out, and the coverage column tells
how much of the weight was present.

* **Human-Agent Negotiation** (no Assistant; the entrants are Opponent agents): `han_outcome` (what the
  agent obtained) and `han_interaction` (how well it behaved as an opponent).
* **Hybrid Intelligence** (with an Assistant; the entrants are Assistants): `hi_outcome` (what the team
  obtained) and `hi_interaction`, the mean of `hi_assistant` (how well it worked as an Assistant) and
  `hi_team` (how well the team worked).

Change the weights with `env.json` `evaluation.scores` or the option `scores`. The
[leaderboards](evaluation.md#tracks-and-leaderboards) rank entrants by these scores.

**Example.** `hi_outcome` of a session with `human_advantage` $= 0.375$ is $0.375$. A session with
`ja_overall` $= 6$ (normalised $5/6$) and one critical Assistant error (normalised $1/2$), and no other
component of `hi_assistant`, has `hi_assistant` $= (1 \cdot 5/6 + 1 \cdot 1/2)/2 = 0.667$ and a coverage
of $2/9.5 = 0.21$.
""", columns=_columns())
def scores(ctx: EvalContext, options: dict) -> dict:
    """The combined scores of the HAN and HI tracks, from the other metrics."""
    return score_row(ctx.row, options)
