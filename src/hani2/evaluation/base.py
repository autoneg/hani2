"""Metric registry and the per-recording evaluation context.

A metric is a function ``fn(ctx: EvalContext, options: dict) -> dict`` that
returns column values (and optionally ``"_details"``). Register one with
:func:`metric`::

    from hani2.evaluation import metric, Column

    @metric("my_metric", kind="hard", title="My metric",
            columns=[Column("my_value", "My value", "What it measures", higher_is_better=True)])
    def my_metric(ctx, options):
        return {"my_value": len(ctx.human_offers)}

``kind`` is ``hard`` (computed from the log), ``soft`` (judged by a language
model; ``needs_llm=True``) or ``subjective`` (from the participant's
questionnaire answers).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, Callable

import numpy as np

from hani2.recording.format import Recording


@dataclass
class Column:
    """One output column of a metric.

    ``description`` is a one-line summary (table headers, CLI listing).
    The reference fields explain the column fully and are shared by the CLI
    (``hani2 replay metrics --details``), the API, the replay tool and the docs:

    * ``formula`` — its exact definition in LaTeX (no ``$`` delimiters);
    * ``details`` — Markdown: what it measures, why it matters, how to read it,
      a worked example and caveats (inline math ``$...$``, display ``$$...$$``);
    * ``range`` — the possible values (e.g. ``[0, 1]``, ``count``, ``seconds``).

    A ``name`` with ``<...>`` (e.g. ``q_<id>``) describes a family of dynamic
    columns (see :meth:`Metric.column_info`).
    """

    name: str
    title: str
    description: str = ""
    higher_is_better: bool | None = None
    formula: str = ""
    details: str = ""
    range: str = ""

    def info(self) -> dict:
        return dict(name=self.name, title=self.title, description=self.description,
                    higher_is_better=self.higher_is_better, formula=self.formula, details=self.details,
                    range=self.range)

    def matches(self, name: str) -> bool:
        if "<" not in self.name:
            return name == self.name
        rx = re.escape(self.name)
        rx = re.sub(r"<[^>]*>", ".+", rx.replace(r"\<", "<").replace(r"\>", ">"))
        return re.fullmatch(rx, name) is not None


@dataclass
class Metric:
    """A registered metric. ``details`` (Markdown) and ``formula`` (LaTeX)
    explain it as a whole; ``patterns`` describe dynamic columns (``q_<id>``);
    ``figures`` name figures of :data:`FIGURES` that illustrate it."""

    name: str
    kind: str
    title: str
    description: str
    columns: list[Column]
    fn: Callable[["EvalContext", dict], dict]
    needs_llm: bool = False
    default: bool = True
    version: str = "1"
    formula: str = ""
    details: str = ""
    patterns: list[Column] = field(default_factory=list)
    figures: list[str] = field(default_factory=list)
    options: dict[str, str] = field(default_factory=dict)

    def info(self, full: bool = False) -> dict:
        """The metric's description; ``full`` adds the reference texts
        (formulas, details, dynamic-column patterns and figures)."""
        cols = [c.info() for c in self.columns]
        if not full:
            cols = [{k: c[k] for k in ("name", "title", "description", "higher_is_better")} for c in cols]
        out = dict(name=self.name, kind=self.kind, title=self.title, description=self.description,
                   needs_llm=self.needs_llm, default=self.default, version=self.version, columns=cols)
        if full:
            out.update(formula=self.formula, details=self.details, patterns=[c.info() for c in self.patterns],
                       figures=list(self.figures), options=dict(self.options))
        return out

    def column_info(self, name: str) -> Column | None:
        """The declared column ``name``, else the first pattern that matches it."""
        for c in self.columns:
            if c.name == name:
                return c
        for c in self.patterns:
            if c.matches(name):
                return c
        return None


REGISTRY: dict[str, Metric] = {}


def metric(name: str, *, kind: str, title: str, columns: list[Column], description: str = "",
           needs_llm: bool = False, default: bool = True, version: str = "1", formula: str = "",
           details: str = "", patterns: list[Column] | None = None, figures: list[str] | None = None,
           options: dict[str, str] | None = None):
    """Register a metric (decorator). ``description`` defaults to the first
    paragraph of the function's docstring."""
    if kind not in ("hard", "soft", "subjective"):
        raise ValueError(f"unknown metric kind {kind!r}")

    def deco(fn):
        REGISTRY[name] = Metric(name, kind, title, description or (fn.__doc__ or "").strip(), columns, fn,
                                needs_llm=needs_llm, default=default, version=version, formula=formula,
                                details=details.strip(), patterns=list(patterns or []),
                                figures=list(figures or []), options=dict(options or {}))
        return fn

    return deco


def num(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def mean(xs: list) -> float | None:
    v = [x for x in (num(x) for x in xs) if x is not None]
    return float(np.mean(v)) if v else None


def median(xs: list) -> float | None:
    v = [x for x in (num(x) for x in xs) if x is not None]
    return float(np.median(v)) if v else None


class EvalContext:
    """Everything metrics need, derived once from a :class:`Recording`."""

    def __init__(self, rec: Recording):
        self.rec = rec

    # -- scenario -------------------------------------------------------------------
    @cached_property
    def scenario(self) -> dict:
        return self.rec.scenario or {}

    @property
    def has_scenario(self) -> bool:
        return bool(self.scenario.get("outcomes")) and bool(self.scenario.get("utilities"))

    @cached_property
    def hi(self) -> int:
        st = self.rec.start or {}
        return int(st.get("human_index", self.scenario.get("human_index", 1)) or 0)

    @cached_property
    def oi(self) -> list[int]:
        n = len(self.scenario.get("utilities") or [[], []])
        return [i for i in range(n) if i != self.hi]

    @cached_property
    def U(self) -> np.ndarray:
        """``(n_parties, n_outcomes)`` utilities (NaN where unknown)."""
        u = self.scenario.get("utilities") or []
        return np.array([[np.nan if v is None else float(v) for v in row] for row in u], dtype=float)

    @cached_property
    def outcome_index(self) -> dict[tuple, int]:
        return {_key(o): i for i, o in enumerate(self.scenario.get("outcomes") or [])}

    @cached_property
    def reserved(self) -> np.ndarray:
        r = self.scenario.get("reserved") or []
        return np.array([0.0 if v is None else float(v) for v in r], dtype=float)

    def utils_of(self, offer: Any) -> np.ndarray | None:
        """Every party's utility for an outcome (``None`` if not in the table)."""
        if offer is None or not self.has_scenario:
            return None
        i = self.outcome_index.get(_key(offer))
        if i is None:
            return None
        return self.U[:, i]

    def hu(self, offer: Any) -> float | None:
        u = self.utils_of(offer)
        return None if u is None else num(u[self.hi])

    def ou(self, offer: Any) -> float | None:
        u = self.utils_of(offer)
        return None if u is None else num(sum(u[i] for i in self.oi))

    @cached_property
    def two_party(self) -> np.ndarray:
        """``(2, n_outcomes)``: human, opponent(s) summed."""
        U = self.U
        if U.size == 0:
            return np.zeros((2, 0))
        return np.vstack([U[self.hi], U[self.oi].sum(axis=0)])

    @cached_property
    def pareto(self) -> np.ndarray:
        """Indices of Pareto-optimal outcomes (human vs opponent utility)."""
        P = self.two_party
        if P.shape[1] == 0:
            return np.array([], dtype=int)
        pts = P.T
        order = np.lexsort((-pts[:, 1], -pts[:, 0]))
        front, best_o = [], -np.inf
        for i in order:
            if pts[i, 1] > best_o + 1e-12:
                front.append(i)
                best_o = pts[i, 1]
        return np.array(front, dtype=int)

    @cached_property
    def disagreement(self) -> np.ndarray:
        r = self.reserved
        if r.size == 0:
            return np.zeros(2)
        return np.array([r[self.hi], sum(r[i] for i in self.oi)])

    @cached_property
    def nash_point(self) -> np.ndarray | None:
        P = self.two_party[:, self.pareto] if self.pareto.size else None
        if P is None:
            return None
        d = self.disagreement
        gain = np.clip(P[0] - d[0], 0, None) * np.clip(P[1] - d[1], 0, None)
        if not np.any(gain > 0):
            return None
        return P[:, int(np.argmax(gain))]

    @cached_property
    def ks_point(self) -> np.ndarray | None:
        """Kalai–Smorodinsky: the Pareto point that best equalises normalised gains."""
        P = self.two_party[:, self.pareto] if self.pareto.size else None
        if P is None:
            return None
        d = self.disagreement
        best = P.max(axis=1)
        rng = np.where(best - d > 1e-12, best - d, np.nan)
        g = (P - d[:, None]) / rng[:, None]
        valid = np.all(P >= d[:, None] - 1e-12, axis=0)
        if not np.any(valid):
            return None
        score = np.where(valid, np.minimum(g[0], g[1]), -np.inf)
        return P[:, int(np.nanargmax(score))]

    @cached_property
    def max_welfare(self) -> float | None:
        P = self.two_party
        return float(P.sum(axis=0).max()) if P.shape[1] else None

    def dist_to_pareto(self, point: np.ndarray) -> float | None:
        if not self.pareto.size:
            return None
        P = self.two_party[:, self.pareto]
        return float(np.min(np.linalg.norm(P - point[:, None], axis=0)))

    def point_of(self, offer: Any) -> np.ndarray | None:
        if offer is None:
            return self.disagreement
        h, o = self.hu(offer), self.ou(offer)
        if h is None or o is None:
            return None
        return np.array([h, o])

    # -- the negotiation -------------------------------------------------------------
    @cached_property
    def offers(self) -> list[dict]:
        out = []
        for o in self.rec.offers():
            o = dict(o)
            o["hu"], o["ou"] = self.hu(o["offer"]), self.ou(o["offer"])
            out.append(o)
        return out

    @cached_property
    def human_offers(self) -> list[dict]:
        return [o for o in self.offers if o["by"] == "human"]

    @cached_property
    def opponent_offers(self) -> list[dict]:
        return [o for o in self.offers if o["by"] == "agent"]

    @cached_property
    def acts(self) -> list[dict]:
        return self.rec.of("act")

    @cached_property
    def agreement(self) -> list | None:
        r = self.rec.last("result")
        return r.get("agreement") if r else None

    @cached_property
    def summary(self) -> dict:
        return self.rec.summary or {}

    @cached_property
    def started_at(self) -> float | None:
        s = self.rec.first("start")
        return float(s["t"]) if s else None

    @cached_property
    def ended_at(self) -> float | None:
        r = self.rec.first("result")
        return float(r["t"]) if r else None

    @cached_property
    def telemetry(self) -> list[tuple[float, str, list]]:
        return self.rec.telemetry()

    @cached_property
    def chat(self) -> list[dict]:
        return self.rec.of("chat")

    @cached_property
    def human_name(self) -> str:
        return "You"

    def is_human_chat(self, c: dict) -> bool:
        return str(c.get("user")) == "You"

    @cached_property
    def llm_calls(self) -> list[dict]:
        return self.rec.of("llm")

    @cached_property
    def fn_calls(self) -> list[dict]:
        return self.rec.of("fn")

    @cached_property
    def drafts(self) -> list[dict]:
        return self.rec.of("draft")

    @cached_property
    def turn_starts(self) -> list[float]:
        """Times the participant's turn began (from the screen states when a
        browser was connected, else the opponent's offers)."""
        out, prev = [], False
        for t, _, st in self.rec.states():
            neg = (st or {}).get("negotiation") or {}
            mine = bool(neg.get("is_my_turn")) and not neg.get("thinking") and st.get("phase") == "running"
            if mine and not prev:
                out.append(t)
            prev = mine
        return out


def _key(o: Any) -> tuple:
    if isinstance(o, dict):
        o = list(o.values())
    try:
        return tuple(_norm(v) for v in o)
    except TypeError:
        return (_norm(o),)


def _norm(v: Any) -> Any:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        f = float(v)
        return int(f) if f.is_integer() else round(f, 9)
    return str(v)


@dataclass
class EvalResult:
    key: str
    values: dict[str, Any] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
