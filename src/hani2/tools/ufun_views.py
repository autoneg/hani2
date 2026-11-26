"""Showing preferences: one *view* per kind of utility function.

The Preferences and Opponent Preferences tools call :func:`render_ufun_view`.
It finds the view registered for the most specific class in the utility
function's MRO and calls it. A view is a plain function::

    from hani2.tools import ui
    from hani2.tools.ufun_views import register_ufun_view

    @register_ufun_view(MyUtilityFunction)
    def my_view(ctx):
        return [ui.card(ui.text_block("..."), title="My preferences")]

``ctx`` is a :class:`UfunViewContext`. Packages can also register views through
the ``hani2.ufun_views`` entry point group: the entry point must resolve to a
module (imported lazily, the module registers its views on import) or to a
callable that registers them.

Views must never raise: any failure falls back to the generic *ranking* view,
which works for any utility function (it samples outcomes when the space is
large).
"""

from __future__ import annotations

import math
import traceback
import warnings
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from typing import Any, Callable, Sequence

import numpy as np
import plotly.graph_objects as go

from hani2.tools import ui
from hani2.tools.plotting import HUMAN_COLOR, SEQUENCE, base_layout

__all__ = [
    "UfunViewContext",
    "register_ufun_view",
    "find_ufun_view",
    "render_ufun_view",
    "PREFERENCES_HELP_MD",
    "reserved_sentence",
    "describe_issue",
    "issue_explanations",
    "preference_summary",
    "MAX_DEPTH",
    "MAX_OUTCOMES",
]

#: Nested utility functions deeper than this are shown with the generic view.
MAX_DEPTH = 3
#: Spaces larger than this are sampled instead of enumerated.
MAX_OUTCOMES = 5000
ENTRY_POINT_GROUP = "hani2.ufun_views"

PREFERENCES_HELP_MD = """
Your **preferences** say how good each possible agreement is *for you*, on a
scale from **0% (worst) to 100% (best)**. Your AI opponent has its own
preferences, and you usually value things differently — that difference is
what makes a deal worth doing.

**How a deal's value is worked out**

An agreement fixes one option for every *issue* (for example a price, a
quantity or a delivery time). Each issue contributes in two steps:

- **Issue value** — within one issue, each option is worth a percentage to you
  (the bar chart). 100% is your favourite option for that issue, 0% your least
  favourite.
- **Issue weight** — issues are not equally important. The donut chart shows
  how much each issue *weighs*; the weights add up to 100%.

Your total score for a deal is the **weighted sum** of the issue values:

> total = weight₁ × value₁ + weight₂ × value₂ + …

The **value on disagreement** is what you get if the negotiation ends with
**no agreement**. A deal worth *more* than that beats walking away; a deal
worth *less* is worse than no deal at all.

**Worked example (Price and Delivery)**

Price weighs **70%** and Delivery **30%**; Price $10 → 100%, $20 → 50%;
Delivery Fast → 100%, Slow → 20%.

- Deal A — *$20, Fast*: 0.7 × 50% + 0.3 × 100% = **65%**
- Deal B — *$10, Slow*: 0.7 × 100% + 0.3 × 20% = **76%**

Deal B is better for you: a low price matters enough that you would accept
slow delivery to get it.
"""


# --------------------------------------------------------------------------- #
# Context and registry                                                         #
# --------------------------------------------------------------------------- #
@dataclass
class UfunViewContext:
    """Everything a view needs.

    ``key(name)`` gives a widget name that is unique among nested views; use it
    for any ``ui.select`` and read the value back with ``ctx.value(name)``.
    """

    tool: Any
    ufun: Any
    title_prefix: str = ""
    help_card: bool = True
    depth: int = 0
    path: str = ""
    names: list[str] = field(default_factory=list)
    rv_shown: bool = False
    #: the value on disagreement is not known to the viewer (see hani2.information); the hint says who knows it
    rv_hidden: bool = False
    rv_hidden_hint: str = "You do not know it"

    # -- widgets ---------------------------------------------------------- #
    def key(self, name: str) -> str:
        return f"{name}{'_' + self.path if self.path else ''}"

    def value(self, name: str, default: Any = None) -> Any:
        values = getattr(self.tool, "values", None) or {}
        return values.get(self.key(name), default)

    def choose(self, name: str, options: list[str], label: str) -> tuple[Any, ui.Component | None]:
        """A select over ``options`` and the currently selected option."""
        if not options:
            return None, None
        sel = self.value(name, options[0])
        if sel not in options:
            sel = options[0]
        return sel, ui.select(self.key(name), options, sel, label=label)

    @property
    def issues(self) -> list:
        os_ = getattr(self.ufun, "outcome_space", None)
        return list(getattr(os_, "issues", None) or [])

    @property
    def issue_names(self) -> list[str]:
        return [str(i.name) for i in self.issues]

    @property
    def nested(self) -> bool:
        return self.depth > 0

    # -- composition ------------------------------------------------------ #
    def child(self, ufun: Any, label: str) -> "UfunViewContext":
        return UfunViewContext(
            tool=self.tool, ufun=ufun, title_prefix="", help_card=False, depth=self.depth + 1,
            path=f"{self.path}_{label}" if self.path else label,
        )

    @property
    def opponent(self) -> bool:
        """The view shows someone else's preferences (the Opponent Preferences tool)."""
        return bool(self.title_prefix)

    def reserved_stat(self) -> ui.Component:
        """The value on disagreement, as one sentence."""
        self.rv_shown = True
        return ui.alert(reserved_sentence(self.ufun, hidden=self.rv_hidden, hidden_hint=self.rv_hidden_hint,
                                          opponent=self.opponent), "neutral")

    def layout(self, *left: ui.Component | None, right: ui.Component | None = None) -> ui.Component:
        """The standard two-column layout: summary on the left, details on the right.

        The value on disagreement goes under both columns (also when they stack
        on a narrow pane).
        """
        left_items = [c for c in left if c]
        if right is None:
            body = ui.column(*left_items) if left_items else None
        else:
            body = ui.grid(ui.column(*left_items), right, cols=2) if left_items else right
        if self.nested:
            return body or ui.column()
        return ui.column(body, self.reserved_stat())

    def explain(self, markdown: str) -> list[ui.Component]:
        if not self.help_card or self.nested:
            return []
        return [ui.card(ui.markdown(markdown, size="sm"), title="How your preferences work",
                        collapsible=True, collapsed=True)]


ViewFn = Callable[[UfunViewContext], "list[ui.Component]"]
_REGISTRY: dict[type, tuple[ViewFn, int]] = {}
_ep_loaded = False


def register_ufun_view(cls: type, fn: ViewFn | None = None, *, priority: int = 0):
    """Register ``fn`` as the view of ``cls`` (and its subclasses).

    Usable as ``register_ufun_view(Cls, fn)`` or as a decorator
    ``@register_ufun_view(Cls)``. The most specific registered class in the
    MRO wins; if one class is registered twice, the higher ``priority`` wins
    (later registrations win ties).
    """
    def _register(f: ViewFn) -> ViewFn:
        old = _REGISTRY.get(cls)
        if old is None or priority >= old[1]:
            _REGISTRY[cls] = (f, priority)
        return f

    return _register if fn is None else _register(fn)


def unregister_ufun_view(cls: type) -> None:
    _REGISTRY.pop(cls, None)


def _load_entry_points() -> None:
    global _ep_loaded
    if _ep_loaded:
        return
    _ep_loaded = True
    try:
        eps = list(entry_points(group=ENTRY_POINT_GROUP))
    except Exception:  # pragma: no cover
        return
    for ep in eps:
        try:
            obj = ep.load()
            if callable(obj) and not isinstance(obj, type):
                obj()  # a registration function; modules register on import
        except Exception as e:  # noqa: BLE001
            warnings.warn(f"hani2: could not load ufun view {ep.name!r}: {e}", stacklevel=2)


def find_ufun_view(ufun: Any) -> ViewFn:
    """The view for ``ufun``: the most specific registered class wins."""
    _load_entry_points()
    for cls in type(ufun).__mro__:
        hit = _REGISTRY.get(cls)
        if hit is not None:
            return hit[0]
    return generic_view


def render_ufun_view(tool: Any, ufun: Any, *, title_prefix: str = "", help_card: bool = True,
                     ctx: UfunViewContext | None = None, reserved_hint: str | None = None) -> list[ui.Component]:
    """Render ``ufun`` with the best view; never raises. ``reserved_hint``: the
    value on disagreement is hidden and this hint is shown instead."""
    if ufun is None:
        return [ui.text_block("No preferences loaded yet.", muted=True)]
    if ctx is None:
        ctx = UfunViewContext(tool=tool, ufun=ufun, title_prefix=title_prefix, help_card=help_card,
                              rv_hidden=reserved_hint is not None, rv_hidden_hint=reserved_hint or "")
    view = generic_view if ctx.depth >= MAX_DEPTH else find_ufun_view(ufun)
    try:
        comps = list(view(ctx))
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        ctx.rv_shown = False
        try:
            comps = list(generic_view(ctx))
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            comps = [ui.alert("These preferences cannot be shown.", "neutral")]
    if not ctx.nested and not ctx.rv_shown:
        comps.append(ctx.reserved_stat())
    return comps


def _section(fn: Callable[[], ui.Component | list | None], what: str = "") -> list[ui.Component]:
    """Run one section of a view; a failing section is skipped, not fatal."""
    try:
        out = fn()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return []
    if out is None:
        return []
    return list(out) if isinstance(out, (list, tuple)) else [out]


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _finite(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except Exception:  # noqa: BLE001
        return False


def _reserved(ufun: Any) -> float | None:
    rv = getattr(ufun, "reserved_value", None)
    if isinstance(rv, (int, float, np.floating)) and _finite(rv):
        return float(rv)
    try:  # distributions
        m = float(rv.mean())  # type: ignore[union-attr]
        return m if _finite(m) else None
    except Exception:  # noqa: BLE001
        return None


def _fmt_value(v: float | None) -> str:
    if v is None:
        return "Not set"
    if -1e-9 <= v <= 1 + 1e-9:
        return _pct(v)
    return f"{v:.3g}"


def _pct(v: float) -> str:
    """A share as a percentage: ``10%``, ``12.5%`` (no trailing ``.0``)."""
    p = round(100 * float(v), 1)
    return f"{p:.0f}%" if abs(p - round(p)) < 1e-9 else f"{p:.1f}%"


def reserved_sentence(ufun: Any, *, hidden: bool = False, hidden_hint: str = "", opponent: bool = False) -> str:
    """The value on disagreement in one sentence: "If you do not reach agreement you
    get 10% (your best option gives you 100%)." ``hidden``: the viewer does not know it."""
    who, gets, its = ("the opponent", "gets", "its best option gives it") if opponent else \
        ("you", "get", "your best option gives you")
    if hidden:
        rest = hidden_hint.split(";", 1)[1].strip() if ";" in hidden_hint else ""
        out = f"You do not know what {who} {gets} if no agreement is reached."
        return out + (f" {rest[:1].upper()}{rest[1:]}." if rest else "")
    rv = _reserved(ufun)
    lead = "If you do not reach agreement you" if not opponent else "If no agreement is reached the opponent"
    if rv is None:
        return f"{lead} {gets} nothing set by these preferences."
    if _unit_scale(ufun) and -1e-9 <= rv <= 1 + 1e-9:
        return f"{lead} {gets} {_pct(rv)} ({its} 100%)."
    return f"{lead} {gets} {rv:.3g}."


def _unit_scale(ufun: Any) -> bool:
    """Whether the best deal is worth exactly 1 (100%), so percentages read naturally."""
    try:
        _, hi = ufun.minmax()
        return abs(float(hi) - 1.0) < 1e-6
    except Exception:  # noqa: BLE001
        return False


def _num(x: Any) -> float:
    """A float from a number or a distribution (its mean); nan on failure."""
    try:
        return float(x)
    except Exception:  # noqa: BLE001
        pass
    for attr in ("mean", "expectation"):
        try:
            return float(getattr(x, attr)())
        except Exception:  # noqa: BLE001
            continue
    return float("nan")


def _utility(ufun: Any, outcome: Any) -> float:
    try:
        return _num(ufun(outcome))
    except Exception:  # noqa: BLE001
        return float("nan")


def _apply(fn: Any, x: Any) -> float:
    """Evaluate a value function that may be callable, a dict or a list."""
    try:
        if isinstance(fn, dict):
            return _num(fn[x])
        if callable(fn):
            return _num(fn(x))
        return _num(fn[x])
    except Exception:  # noqa: BLE001
        return float("nan")


def _unit(vals: list[float]) -> bool:
    fin = [v for v in vals if _finite(v)]
    return bool(fin) and min(fin) >= -1e-9 and max(fin) <= 1 + 1e-9


def _issue_labels(issue: Any, n_cont: int = 20) -> list:
    if issue.is_continuous():
        return [float(v) for v in np.linspace(issue.min_value, issue.max_value, num=n_cont, endpoint=True)]
    return list(issue.all)


def _label(v: Any) -> str:
    return f"{v:.4g}" if isinstance(v, (float, np.floating)) else str(v)


#: axis labels longer than this are shortened in the middle (start and end stay visible)
MAX_AXIS_LABEL = 28


def _short_labels(labels: list[str], limit: int = MAX_AXIS_LABEL) -> list[str]:
    """Axis labels that fit: a long one keeps its start and end around "…"; every
    label stays distinct (a category axis merges equal ones)."""
    out: list[str] = []
    for full in labels:
        lab = full if len(full) <= limit else f"{full[:(limit - 1) // 2 + (limit - 1) % 2].rstrip()}…" \
                                              f"{full[-((limit - 1) // 2):].lstrip()}"
        base, k = lab, 2
        while lab in out:
            lab = f"{base} ({k})"
            k += 1
        out.append(lab)
    return out


def _bars(labels: list, vals: list[float], *, color: str = HUMAN_COLOR) -> ui.Component:
    """Horizontal bars; percentages when every value is within 0..1. The labels
    are shown in full (the margin grows to fit them) unless excessively long."""
    pct = _unit(vals)
    xs = [100 * v if pct else v for v in vals]
    full = [_label(v) for v in labels]
    fig = go.Figure(data=[go.Bar(
        y=_short_labels(full), x=xs, orientation="h", marker_color=color, customdata=full,
        hovertemplate="%{customdata}: %{x:.3g}" + ("%" if pct else "") + "<extra></extra>")])
    xaxis: dict[str, Any] = dict(range=[0, 100], ticksuffix="%") if pct else dict(zeroline=True)
    fig.update_layout(**base_layout(max(160, 26 * len(labels) + 40), legend=False, xaxis=xaxis,
                                    yaxis=dict(type="category", autorange="reversed", automargin=True),
                                    margin=dict(l=8, r=16, t=12, b=40)))
    return ui.plot(fig)


def _line(xs: list, ys: list[float]) -> ui.Component:
    pct = _unit(ys)
    fig = go.Figure(data=[go.Scatter(x=xs, y=[100 * y if pct else y for y in ys], mode="lines",
                                     line=dict(color=HUMAN_COLOR))])
    fig.update_layout(**base_layout(220, legend=False, yaxis=dict(ticksuffix="%" if pct else "")))
    return ui.plot(fig)


def _fun_plot(issue: Any, fn: Any) -> ui.Component:
    labels = _issue_labels(issue)
    vals = [_apply(fn, v) for v in labels]
    if issue.is_continuous():
        return _line(labels, vals)
    return _bars(labels, vals)


def _weights_plot(names: list[str], weights: list[float]) -> ui.Component:
    """A donut when all weights are non-negative, signed bars otherwise."""
    if all(w >= 0 for w in weights) and sum(weights) > 0:
        fig = go.Figure(
            data=[go.Pie(labels=names, values=weights, hole=0.55, textinfo="label+percent",
                         # labels sit outside the ring and the margins grow to fit
                         # them, so none is cut off by the card title or edges
                         textposition="outside", automargin=True,
                         hovertemplate="%{label}: %{percent}<extra></extra>",
                         marker=dict(colors=SEQUENCE * 4), sort=False)]
        )
        fig.update_layout(**base_layout(260 + 6 * max(0, len(names) - 6), legend=False,
                                        margin=dict(l=24, r=24, t=28, b=28)))
        return ui.plot(fig)
    colors = [HUMAN_COLOR if w >= 0 else "#ef4444" for w in weights]
    fig = go.Figure(data=[go.Bar(y=_short_labels([str(n) for n in names]), x=weights, orientation="h",
                                 marker_color=colors, customdata=[str(n) for n in names],
                                 hovertemplate="%{customdata}: %{x:.3g}<extra></extra>")])
    fig.update_layout(**base_layout(max(160, 26 * len(names) + 40), legend=False,
                                    xaxis=dict(zeroline=True),
                                    yaxis=dict(type="category", autorange="reversed", automargin=True),
                                    margin=dict(l=8, r=16, t=12, b=40)))
    return ui.plot(fig)


def _bias_stat(ufun: Any) -> ui.Component | None:
    try:
        b = float(getattr(ufun, "bias", getattr(ufun, "_bias", 0.0)) or 0.0)
    except Exception:  # noqa: BLE001
        return None
    if b == 0 or not _finite(b):
        return None
    return ui.stat("Starting amount", f"{b:+.3g}", hint="Added to the total of every deal")


#: the short texts under the chart titles (``(you, opponent)``)
WEIGHTS_CAPTION = ("How much each issue counts in your total for a deal: a bigger slice is a more important "
                   "issue. The slices add up to 100%.",
                   "How much each issue counts in the opponent's total for a deal: a bigger slice is a more "
                   "important issue. The slices add up to 100%.")
SIGNED_WEIGHTS_CAPTION = ("How much your total changes for every extra unit of each issue (red: it goes down).",
                          "How much the opponent's total changes for every extra unit of each issue (red: it "
                          "goes down).")
PARTS_CAPTION = ("How much each set of preferences counts in your total. The slices add up to 100%.",
                 "How much each set of preferences counts in the opponent's total. The slices add up to 100%.")
VALUES_CAPTION = ("Pick an issue to see what each of its options is worth to you: 100% is your favourite option "
                  "of that issue, 0% your least favourite.",
                  "Pick an issue to see what each of its options is worth to the opponent: 100% is its "
                  "favourite option of that issue, 0% its least favourite.")


def _caption(ctx: UfunViewContext, texts: tuple[str, str]) -> ui.Component:
    return ui.text_block(texts[1] if ctx.opponent else texts[0], muted=True)


def _per_issue_card(ctx: UfunViewContext, funs: list, *, title: str | None = None) -> ui.Component | None:
    """A select over issues and the chart of the selected issue's value function."""
    names = ctx.issue_names
    if not names or not funs:
        return None
    selected, select = ctx.choose("issue", names, "Issue")
    children = [_caption(ctx, VALUES_CAPTION), select]
    idx = names.index(selected)
    if idx < len(funs):
        children += _section(lambda: _fun_plot(ctx.issues[idx], funs[idx]))
    return ui.card(*children, title=title or f"{ctx.title_prefix}Value of each option")


def _weights_card(ctx: UfunViewContext, names: list[str], weights: list[float],
                  title: str = "Issue weights", caption: tuple[str, str] | None = None) -> ui.Component:
    if caption is None:
        signed = not (all(w >= 0 for w in weights) and sum(weights) > 0)
        caption = SIGNED_WEIGHTS_CAPTION if signed else WEIGHTS_CAPTION
    return ui.card(_caption(ctx, caption), _weights_plot(names, weights), title=f"{ctx.title_prefix}{title}")


def _plain(ctx: UfunViewContext, text: str) -> ui.Component | None:
    return ui.text_block(text, muted=True) if not ctx.nested else None


# --------------------------------------------------------------------------- #
# Generic view: ranking table and histogram, for any utility function          #
# --------------------------------------------------------------------------- #
def sample_outcomes(ufun: Any, limit: int = MAX_OUTCOMES) -> tuple[list, bool]:
    """Outcomes of the ufun's space (all of them, or a sample) and whether it is the complete set."""
    os_ = getattr(ufun, "outcome_space", None)
    if os_ is None:
        return [], False
    try:
        if os_.is_finite() and os_.cardinality <= limit:
            return list(os_.enumerate()), True
    except Exception:  # noqa: BLE001
        pass
    try:  # never enumerate a big space: ``enumerate_or_sample`` would walk all of it
        return list(os_.sample(limit, with_replacement=False, fail_if_not_enough=False)), False
    except Exception:  # noqa: BLE001
        pass
    try:
        return list(os_.sample(limit)), False
    except Exception:  # noqa: BLE001
        return [], False


def _outcome_row(ctx_issues: list[str], outcome: Any) -> dict[str, Any]:
    try:
        vals = list(outcome)
    except Exception:  # noqa: BLE001
        vals = [outcome]
    if len(ctx_issues) == len(vals):
        return {n: _label(v) for n, v in zip(ctx_issues, vals)}
    return {f"Issue {i + 1}": _label(v) for i, v in enumerate(vals)}


def ranking_components(ctx: UfunViewContext, ufun: Any | None = None, *, top: int = 10) -> list[ui.Component]:
    """Best outcomes by (expected) value plus a histogram of all values."""
    ufun = ctx.ufun if ufun is None else ufun
    outcomes, complete = sample_outcomes(ufun)
    if not outcomes:
        return [ui.alert("The possible deals cannot be listed for these preferences.", "neutral")]
    scored = [(o, _utility(ufun, o)) for o in outcomes]
    scored = [(o, u) for o, u in scored if _finite(u)]
    if not scored:
        return [ui.alert("These preferences gave no values for the possible deals.", "neutral")]
    scored.sort(key=lambda t: -t[1])
    names = [str(i.name) for i in getattr(getattr(ufun, "outcome_space", None), "issues", None) or []]
    vals = [u for _, u in scored]
    pct = _unit(vals)
    rows = [{"Rank": i + 1, **_outcome_row(names, o), "Value": u} for i, (o, u) in enumerate(scored[:top])]
    note = ("" if complete else f" (estimated from a sample of {len(scored)} possible deals)")
    comps: list[ui.Component] = [
        ui.card(ui.table(rows, formats={"Value": "percent" if pct else "float"}, sortable=False, page_size=top),
                title=f"{ctx.title_prefix}Best deals{note}")
    ]
    fig = go.Figure(data=[go.Histogram(x=[100 * v if pct else v for v in vals], nbinsx=20,
                                       marker_color=HUMAN_COLOR)])
    fig.update_layout(**base_layout(220, legend=False, bargap=0.05,
                                    xaxis=dict(title="Value of a deal" + (" (%)" if pct else "")),
                                    yaxis=dict(title="Number of deals")))
    comps.append(ui.card(ui.plot(fig), title=f"{ctx.title_prefix}How deals are spread{note}"))
    return comps


GENERIC_HELP_MD = """
Each possible agreement has a **value** for you. The table lists the deals you
like most, and the chart shows how many deals fall at each level of value.

The **value on disagreement** is what you get if the negotiation ends with
**no agreement**. A deal worth *more* than that beats walking away.
"""


def generic_view(ctx: UfunViewContext) -> list[ui.Component]:
    out: list[ui.Component] = list(ranking_components(ctx))
    if not ctx.nested:
        out.append(ctx.reserved_stat())
    out += ctx.explain(GENERIC_HELP_MD)
    return out


# --------------------------------------------------------------------------- #
# Additive utility functions                                                   #
# --------------------------------------------------------------------------- #
def additive_view(ctx: UfunViewContext) -> list[ui.Component]:
    u = ctx.ufun
    names = ctx.issue_names
    weights = [float(w) for w in u.weights]
    left = [*_section(lambda: _weights_card(ctx, names, weights)), *_section(lambda: _bias_stat(u))]
    comps = [ctx.layout(*left, right=_per_issue_card(ctx, list(u.values)))]
    return comps + ctx.explain(PREFERENCES_HELP_MD)


# --------------------------------------------------------------------------- #
# Linear / affine                                                              #
# --------------------------------------------------------------------------- #
LINEAR_HELP_MD = """
Your total for a deal is worked out directly from the **numbers** in it. Each
issue has a **weight**: how much your total goes up (or down, when the weight
is negative) for every extra unit of that issue.

> total = weight₁ × issue₁ + weight₂ × issue₂ + … + starting amount

The **value on disagreement** is what you get if the negotiation ends with
**no agreement**.
"""


def linear_view(ctx: UfunViewContext) -> list[ui.Component]:
    u = ctx.ufun
    names = ctx.issue_names
    weights = [float(w) for w in u.weights]
    terms = " + ".join(f"{w:.3g} × {n}" for w, n in zip(weights, names))
    bias = _bias_stat(u)
    if bias is not None:
        terms += f" {float(u.bias):+.3g}"
    right = ui.card(ui.text_block(f"Total = {terms}"), ui.table(
        [{"Issue": n, "Weight": w} for n, w in zip(names, weights)], formats={"Weight": "float"}, sortable=False),
        title=f"{ctx.title_prefix}How the total is worked out")
    left = [_weights_card(ctx, names, weights), bias]
    comps = [ctx.layout(*left, right=right)]
    comps += _section(lambda: ranking_components(ctx, top=5))
    return comps + ctx.explain(LINEAR_HELP_MD)


# --------------------------------------------------------------------------- #
# Generalised factor-based ufuns (GLA, GPA, PA)                                #
# --------------------------------------------------------------------------- #
def _factor_label(ctx: UfunViewContext, indices: tuple, k: int | None = None) -> str:
    names = ctx.issue_names
    parts = [names[i] if 0 <= i < len(names) else f"Issue {i + 1}" for i in indices]
    return " & ".join(parts) or (f"Factor {k + 1}" if k is not None else "Factor")


def _factor_labels(ctx: UfunViewContext, factors: list) -> list[str]:
    labels = [_factor_label(ctx, tuple(ix), k) for k, (ix, _) in enumerate(factors)]
    seen: dict[str, int] = {}
    out = []
    for lab in labels:  # keep select options unique
        seen[lab] = seen.get(lab, 0) + 1
        out.append(lab if seen[lab] == 1 else f"{lab} ({seen[lab]})")
    return out


def _heatmap(ctx: UfunViewContext, indices: tuple, fn: Any) -> ui.Component | None:
    issues = ctx.issues
    a, b = (issues[i] for i in indices)
    if a.is_continuous() or b.is_continuous() or a.cardinality * b.cardinality > 400:
        return None
    av, bv = list(a.all), list(b.all)
    z = [[_apply(fn, (x, y)) for x in av] for y in bv]
    pct = _unit([v for r in z for v in r])
    fig = go.Figure(data=[go.Heatmap(z=[[100 * v if pct else v for v in r] for r in z],
                                     x=[_label(v) for v in av], y=[_label(v) for v in bv],
                                     colorscale="Blues", colorbar=dict(ticksuffix="%" if pct else ""))])
    fig.update_layout(**base_layout(max(220, 22 * len(bv) + 80), legend=False,
                                    xaxis=dict(title=str(a.name), type="category"),
                                    yaxis=dict(title=str(b.name), type="category", autorange="reversed")))
    return ui.plot(fig)


def _factor_card(ctx: UfunViewContext, factors: list, title: str) -> ui.Component | None:
    if not factors:
        return None
    labels = _factor_labels(ctx, factors)
    selected, select = ctx.choose("factor", labels, "Factor")
    k = labels.index(selected)
    indices, fn = factors[k]
    indices = tuple(indices)
    children: list[ui.Component | None] = [select]
    issues = ctx.issues
    if len(indices) == 1 and 0 <= indices[0] < len(issues):
        children += _section(lambda: _fun_plot(issues[indices[0]], fn))
    elif len(indices) == 2 and all(0 <= i < len(issues) for i in indices):
        hm = _section(lambda: _heatmap(ctx, indices, fn))
        children += hm or [ui.text_block("This factor depends on several issues together.", muted=True)]
    else:
        children.append(ui.text_block("This factor depends on several issues together.", muted=True))
    return ui.card(*children, title=title)


GLA_HELP_MD = """
Your total for a deal is a **weighted sum of factors**. A factor looks at one
issue, or at a few issues *together* (so the same option can be worth more or
less depending on the others). Each factor has a **weight**.

> total = weight₁ × factor₁ + weight₂ × factor₂ + … + starting amount

The **value on disagreement** is what you get if the negotiation ends with
**no agreement**.
"""


def gla_view(ctx: UfunViewContext) -> list[ui.Component]:
    u = ctx.ufun
    factors = list(u.factors)
    labels = _factor_labels(ctx, factors)
    weights = [float(w) for w in u.weights]
    left = [*_section(lambda: _weights_card(ctx, labels, weights, "Factor weights")),
            *_section(lambda: _bias_stat(u))]
    right = _factor_card(ctx, factors, f"{ctx.title_prefix}Value of each option")
    return [ctx.layout(*left, right=right)] + ctx.explain(GLA_HELP_MD)


def _term_text(labels: list[str], powers: tuple[int, ...]) -> str:
    sup = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")
    parts = []
    for lab, p in zip(labels, powers):
        if p == 0:
            continue
        parts.append(f"({lab})" + ("" if p == 1 else str(int(p)).translate(sup)))
    return " × ".join(parts) or "(constant)"


POLY_HELP_MD = """
Your total for a deal is a **sum of terms**. Each term multiplies a
**coefficient** by the values of one or more factors (a factor can be
multiplied by itself, which makes it count more strongly).

> total = coefficient₁ × term₁ + coefficient₂ × term₂ + … + starting amount

The **value on disagreement** is what you get if the negotiation ends with
**no agreement**.
"""


def _poly_view(ctx: UfunViewContext, factors: list) -> list[ui.Component]:
    u = ctx.ufun
    labels = _factor_labels(ctx, factors)
    terms = list(u.terms)
    rows = [{"Term": _term_text(labels, tuple(p)), "Coefficient": float(c)} for c, p in terms]
    left = [ui.card(ui.table(rows, formats={"Coefficient": "float"}, sortable=False),
                    title=f"{ctx.title_prefix}Terms"), _bias_stat(u)]
    right = _factor_card(ctx, factors, f"{ctx.title_prefix}Value of each option")
    return [ctx.layout(*left, right=right)] + ctx.explain(POLY_HELP_MD)


def pa_view(ctx: UfunViewContext) -> list[ui.Component]:
    factors = [((i,), f) for i, f in enumerate(ctx.ufun.values)]
    return _poly_view(ctx, factors)


def gpa_view(ctx: UfunViewContext) -> list[ui.Component]:
    return _poly_view(ctx, list(ctx.ufun.factors))


# --------------------------------------------------------------------------- #
# Non-linear aggregation of per-issue values                                   #
# --------------------------------------------------------------------------- #
NONLINEAR_HELP_MD = """
Each issue first gets a **value** (the bar chart). The values are then
combined by a **custom rule** that is not a simple weighted sum, so the best
deal is not always the one with the best option on every issue. The table of
best deals shows what this rule produces.

The **value on disagreement** is what you get if the negotiation ends with
**no agreement**.
"""


def nonlinear_agg_view(ctx: UfunViewContext) -> list[ui.Component]:
    u = ctx.ufun
    funs = list(u.values) if isinstance(u.values, (list, tuple)) else []
    card = _per_issue_card(ctx, funs, title=f"{ctx.title_prefix}Value of each option")
    comps = [ctx.layout(_plain(ctx, "The value of each issue is combined by a custom rule."), right=card)]
    comps += _section(lambda: ranking_components(ctx, top=5))
    return comps + ctx.explain(NONLINEAR_HELP_MD)


# --------------------------------------------------------------------------- #
# Hyper-rectangles                                                             #
# --------------------------------------------------------------------------- #
def _range_text(ctx: UfunViewContext, key: Any, rng: Any) -> str:
    names = ctx.issue_names
    name = names[key] if isinstance(key, int) and 0 <= key < len(names) else str(key)
    if isinstance(rng, tuple) and len(rng) == 2:
        return f"{name}: {_label(rng[0])} to {_label(rng[1])}"
    if isinstance(rng, (list, set, frozenset)):
        return f"{name}: " + ", ".join(_label(v) for v in rng)
    return f"{name}: {_label(rng)}"


def _rect_text(ctx: UfunViewContext, rect: Any) -> str:
    try:
        if isinstance(rect, dict):
            return "; ".join(_range_text(ctx, k, v) for k, v in rect.items()) or "All deals"
        return str(rect)
    except Exception:  # noqa: BLE001
        return str(rect)


RECT_HELP_MD = """
Your preferences are described by **regions** of deals, for example "price
between 10 and 20 and delivery is Fast". A deal that falls inside a region
earns that region's value; a deal can fall inside several regions, and then
the values are combined.

The **value on disagreement** is what you get if the negotiation ends with
**no agreement**.
"""


def hyperrect_view(ctx: UfunViewContext) -> list[ui.Component]:
    u = ctx.ufun
    ranges = list(getattr(u, "outcome_ranges", None) or getattr(u, "hypervolumes", None) or [])
    mappings = list(getattr(u, "mappings", []) or [])
    weights = list(getattr(u, "weights", None) or [])
    rows = []
    for i, rect in enumerate(ranges):
        m = mappings[i] if i < len(mappings) else None
        row: dict[str, Any] = {"Region": i + 1, "Deals in the region": _rect_text(ctx, rect),
                               "Value": float(m) if isinstance(m, (int, float)) else "Depends on the deal"}
        if weights:
            row["Weight"] = float(weights[i]) if i < len(weights) else 1.0
        rows.append(row)
    cols = ["Region", "Deals in the region", "Value"] + (["Weight"] if weights else [])
    card = ui.card(ui.table(rows, columns=cols, formats={"Value": "float", "Weight": "float"}, sortable=False),
                   title=f"{ctx.title_prefix}Regions")
    left = [_plain(ctx, "A deal earns the value of every region it falls in."), _bias_stat(u)]
    comps = [ctx.layout(*left, right=card)]
    comps += _section(lambda: ranking_components(ctx, top=5))
    return comps + ctx.explain(RECT_HELP_MD)


# --------------------------------------------------------------------------- #
# Combinations and wrappers                                                    #
# --------------------------------------------------------------------------- #
def _component_name(u: Any, i: int) -> str:
    name = str(getattr(u, "name", "") or "")
    return f"{i + 1}. {name}" if name else f"Part {i + 1}"


def _nested_cards(ctx: UfunViewContext, parts: list) -> list[ui.Component]:
    cards = []
    for i, p in enumerate(parts):
        label = _component_name(p, i)
        sub = render_ufun_view(ctx.tool, p, ctx=ctx.child(p, f"p{i + 1}"))
        cards.append(ui.card(*sub, title=label, collapsible=True, collapsed=True))
    return cards


WEIGHTED_HELP_MD = """
Your total for a deal combines **several sets of preferences**. Each part
gives the deal its own value, and each part has a **weight** (the donut chart)
saying how much it counts.

> total = weight₁ × part₁ + weight₂ × part₂ + …

Open a part below to see how it values things.
"""


def weighted_view(ctx: UfunViewContext) -> list[ui.Component]:
    u = ctx.ufun
    parts = list(u.values)
    names = [_component_name(p, i) for i, p in enumerate(parts)]
    weights = [float(w) for w in u.weights]
    comps = [ctx.layout(*_section(lambda: _weights_card(ctx, names, weights, "Weights of the parts",
                                                         caption=PARTS_CAPTION)))]
    comps += _nested_cards(ctx, parts)
    comps += _section(lambda: ranking_components(ctx, top=5))
    return comps + ctx.explain(WEIGHTED_HELP_MD)


COMPLEX_HELP_MD = """
Your total for a deal combines **several sets of preferences** with a
**custom rule** (not a simple weighted sum). Open a part below to see how it
values things; the table of best deals shows what the rule produces overall.
"""


def complex_view(ctx: UfunViewContext) -> list[ui.Component]:
    parts = list(ctx.ufun.ufuns)
    comps = [ctx.layout(_plain(ctx, f"{len(parts)} sets of preferences are combined by a custom rule."))]
    comps += _nested_cards(ctx, parts)
    comps += _section(lambda: ranking_components(ctx, top=5))
    return comps + ctx.explain(COMPLEX_HELP_MD)


def _discount_text(u: Any) -> tuple[str, list[tuple[str, Any]]]:
    name = type(u).__name__
    factor = getattr(u, "factor", None)
    what = factor if isinstance(factor, str) else "elapsed time"
    what = {"step": "round", "current_step": "round", "relative_time": "share of the time used",
            "time": "time"}.get(what, what)
    dyn = bool(getattr(u, "dynamic_reservation", False))
    if name == "ExpDiscountedUFun":
        d = getattr(u, "discount", None)
        text = (f"The value of every deal shrinks by a fixed share as the negotiation goes on: "
                f"it is multiplied by {d if d is not None else 1:.3g} for every unit of {what}.")
        params = [("Discount", d), ("Counted in", what)]
    else:
        cost, power = getattr(u, "cost", None), getattr(u, "power", 1.0)
        text = (f"A cost is subtracted from the value of every deal as the negotiation goes on: "
                f"{cost if cost is not None else 0:.3g} for every unit of {what}"
                + ("." if power in (1, 1.0, None) else f", raised to the power {power:.3g}."))
        params = [("Cost per unit", cost), ("Power", power), ("Counted in", what)]
    params.append(("Also applies to the value on disagreement", "Yes" if dyn else "No"))
    return text, params


def discounted_view(ctx: UfunViewContext) -> list[ui.Component]:
    u = ctx.ufun
    text, params = _discount_text(u)
    inner = u.ufun
    head = ui.card(ui.text_block(text), ui.kv([(k, "—" if v is None else v) for k, v in params]),
                   title=f"{ctx.title_prefix}Time pressure")
    sub = render_ufun_view(ctx.tool, inner, ctx=ctx.child(inner, "inner"))
    comps = [ctx.layout(head), ui.card(*sub, title="Preferences before time pressure")]
    return comps + ctx.explain(
        "Your total for a deal is its normal value, **reduced the longer the negotiation lasts**. "
        "Reaching a deal sooner is worth more.\n\nThe **value on disagreement** is what you get "
        "if the negotiation ends with **no agreement**.")


def rank_only_view(ctx: UfunViewContext) -> list[ui.Component]:
    outcomes, complete = sample_outcomes(ctx.ufun)
    scored = [(o, _utility(ctx.ufun, o)) for o in outcomes]
    scored = sorted([(o, u) for o, u in scored if _finite(u)], key=lambda t: -t[1])
    names = ctx.issue_names
    rows = [{"Rank": i + 1, **_outcome_row(names, o)} for i, (o, _) in enumerate(scored)]
    comps: list[ui.Component] = [ui.card(ui.table(rows, sortable=False, page_size=15, max_height=360),
                                         title=f"{ctx.title_prefix}Deals from best to worst"
                                               + ("" if complete else f" (a sample of {len(rows)})"))]
    if not ctx.nested:
        comps.append(ctx.reserved_stat())
    return comps + ctx.explain(
        "Only the **order** of deals is known: the table lists them from the one you like most to the "
        "one you like least. How much better one deal is than another is not recorded.")


def const_view(ctx: UfunViewContext) -> list[ui.Component]:
    v = _num(getattr(ctx.ufun, "value", float("nan")))
    comps = [ctx.layout(ui.stat("Value of every deal", _fmt_value(v if _finite(v) else None),
                                hint="All deals are equally good"))]
    return comps + ctx.explain("Every possible deal has the **same value** for you, so no deal is better "
                               "than another.")


PROB_HELP_MD = """
For each deal the value is **uncertain**: it can turn out higher or lower. The
table ranks deals by their **expected value**, the average you would get if
the same deal were repeated many times.

The **value on disagreement** is what you get if the negotiation ends with
**no agreement**.
"""


def prob_view(ctx: UfunViewContext) -> list[ui.Component]:
    out = [ui.text_block("The value of a deal is uncertain; deals are ranked by their expected value.",
                         muted=True)]
    out += ranking_components(ctx)
    if not ctx.nested:
        out.append(ctx.reserved_stat())
    return out + ctx.explain(PROB_HELP_MD)


def _register_builtin_views() -> None:
    import negmas.preferences as p

    def reg(name: str, fn: ViewFn) -> None:
        cls = getattr(p, name, None)
        if cls is not None:
            register_ufun_view(cls, fn)

    reg("BaseUtilityFunction", generic_view)
    reg("LinearAdditiveUtilityFunction", additive_view)  # also LinearUtilityAggregationFunction
    reg("AffineUtilityFunction", linear_view)  # also LinearUtilityFunction
    reg("GLAUtilityFunction", gla_view)
    reg("GPAUtilityFunction", gpa_view)
    reg("PAUtilityFunction", pa_view)
    reg("NonLinearAggregationUtilityFunction", nonlinear_agg_view)
    reg("HyperRectangleUtilityFunction", hyperrect_view)
    reg("NonlinearHyperRectangleUtilityFunction", hyperrect_view)
    reg("WeightedUtilityFunction", weighted_view)
    reg("ComplexNonlinearUtilityFunction", complex_view)
    reg("DiscountedUtilityFunction", discounted_view)
    reg("RankOnlyUtilityFunction", rank_only_view)
    reg("ConstUtilityFunction", const_view)
    reg("ProbUtilityFunction", prob_view)


_register_builtin_views()


# --------------------------------------------------------------------------- #
# Part of the preferences (an information split, see hani2.information)        #
# --------------------------------------------------------------------------- #
PARTIAL_HELP_MD = """
Your preferences come in two parts. Each **issue** has a **weight** (how much it
matters to you; the weights add up to 100%), and each **option** of an issue has
a **value** (100% for your favourite option of that issue, 0% for your least
favourite). A deal is worth the weighted sum: weight₁ × value₁ + weight₂ × value₂ + …

In this negotiation you know only one of the two parts. Your Assistant knows the
other one, so work it out together.
"""


def partial_preference_view(tool: Any, ufun: Any, part: str, *, reserved_hint: str | None = None,
                            other_holder: str = "your Assistant") -> list[ui.Component]:
    """The part ``part`` (``weights`` / ``values`` / ``none``) of an additive
    utility function, with a note on who knows the rest. Never raises."""
    if ufun is None:
        return [ui.text_block("No preferences loaded yet.", muted=True)]
    ctx = UfunViewContext(tool=tool, ufun=ufun, rv_hidden=reserved_hint is not None, rv_hidden_hint=reserved_hint or "")
    try:
        names = ctx.issue_names
        if part == "weights":
            note = f"How much each option of an issue is worth to you is known to {other_holder}."
            body = ctx.layout(_weights_card(ctx, names, [float(w) for w in ufun.weights]))
        elif part == "values":
            note = f"How important each issue is to you (its weight) is known to {other_holder}."
            body = ctx.layout(right=_per_issue_card(ctx, list(ufun.values)))
        else:
            note = f"Your preferences are known to {other_holder}. Ask it what each deal is worth to you."
            body = ctx.layout()
        return [ui.alert(note, "info", title="You know part of your preferences"), body,
                *ctx.explain(PARTIAL_HELP_MD)]
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return [ui.alert("These preferences cannot be shown.", "neutral")]


# --------------------------------------------------------------------------- #
# Preferences in words: a short summary and one line per issue                 #
# --------------------------------------------------------------------------- #
def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool)


def _fmt_option(v: Any, fmt: str = "{}") -> str:
    try:
        return fmt.format(v)
    except (ValueError, TypeError, IndexError, KeyError):
        return _label(v)


def _shape(vals: list[float], eps: float = 1e-9) -> tuple[str, int]:
    """``(kind, index)`` of a value curve over ordered options: ``flat``, ``up``,
    ``down``, ``peak`` / ``valley`` (index of the best / worst option) or ``mixed``."""
    if max(vals) - min(vals) < eps:
        return "flat", 0
    d = [b - a for a, b in zip(vals, vals[1:])]
    if all(x >= -eps for x in d):
        return "up", len(vals) - 1
    if all(x <= eps for x in d):
        return "down", 0
    top = int(np.argmax(vals))
    if all(x >= -eps for x in d[:top]) and all(x <= eps for x in d[top:]):
        return "peak", top
    low = int(np.argmin(vals))
    if all(x <= eps for x in d[:low]) and all(x >= -eps for x in d[low:]):
        return "valley", low
    return "mixed", top


def _pace(vals: list[float], eps: float = 1e-6) -> str:
    """How a monotone curve rises: evenly, mostly at first or mostly at the end."""
    d = [abs(b - a) for a, b in zip(vals, vals[1:])]
    # rounding to a 5% grid makes an even curve a little uneven: allow for it
    if len(d) < 2 or max(d) - min(d) < max(eps, 0.06 * (max(vals) - min(vals))):
        return "even"
    half = len(d) // 2
    first, last = sum(d[:half]) / max(1, half), sum(d[-half:]) / max(1, half)
    return "early" if first > last else "late"


def describe_issue(issue: Any, fn: Any, *, fmt: str = "{}", unit: tuple[str, str] | None = None,
                   own: Callable[[Any], Any] | None = None, opponent: bool = False) -> str | None:
    """One plain sentence on what the owner of value function ``fn`` wants on
    ``issue``: "The lower, the better (every step is worth the same).", "Best at
    5 days; the further away from it, the worse.", "Best: Red, then Blue; worst:
    Green." ``unit`` (an item split): the issue counts items, ``own`` maps an
    issue value to how many items the owner gets. ``None`` when nothing can be said."""
    try:
        labels = _issue_labels(issue, n_cont=21)
        vals = [_apply(fn, v) for v in labels]
    except Exception:  # noqa: BLE001
        return None
    if not labels or not all(_finite(v) for v in vals):
        return None
    you = "the opponent" if opponent else "you"
    kind, at = _shape(vals)
    if kind == "flat":
        return f"It does not matter to {you}: every option is worth the same."
    numeric = all(_is_number(v) for v in labels)
    if unit is not None and numeric:
        many = unit[1] if len(unit) > 1 else str(issue.name)
        mine = [own(v) if own else v for v in labels]
        pairs = sorted(zip(mine, vals), key=lambda t: t[0])
        k, _ = _shape([v for _, v in pairs])
        who = "the opponent gets" if opponent else "you get"
        if k == "up":
            return f"The more {many} {who}, the better."
        if k == "down":
            return f"The fewer {many} {who}, the better."
    if numeric and len(labels) > 2:
        # how the value grows on the way from the worst option to the best one
        pace = _pace(vals if kind == "up" else vals[::-1]) if kind in ("up", "down") else ""
        how = {"even": " (every step is worth the same)",
               "early": " (the first steps away from the worst option matter most)",
               "late": " (only the steps close to the best option really count)"}.get(pace, "")
        if kind == "up":
            return f"The higher, the better{how}."
        if kind == "down":
            return f"The lower, the better{how}."
        best = _fmt_option(labels[at], fmt)
        if kind == "peak":
            return f"Best at {best}; the further away from it, the worse."
        if kind == "valley":
            return f"Worst at {_fmt_option(labels[at], fmt)}; the further away from it, the better."
    order = sorted(range(len(labels)), key=lambda i: -vals[i])
    names = [_fmt_option(labels[i], fmt) for i in order]
    if len(names) == 2:
        return f"Best: {names[0]}; worst: {names[1]}."
    if len(names) <= 5:
        return f"From best to worst: {', '.join(names)}."
    return f"Best: {names[0]}, then {names[1]}; worst: {names[-1]}."


def _issue_funs(ufun: Any) -> list | None:
    """One value function per issue, for utility functions built that way."""
    funs = getattr(ufun, "values", None)
    issues = list(getattr(getattr(ufun, "outcome_space", None), "issues", None) or [])
    try:
        funs = list(funs) if funs is not None and not callable(funs) else None
    except TypeError:
        return None
    return funs if funs and len(funs) == len(issues) else None


def issue_explanations(ufun: Any, info: dict | None = None, *, roles: Sequence[str] = (),
                       opponent: bool = False) -> list[tuple[str, str]]:
    """``[(issue, sentence)]``: what the owner of ``ufun`` wants on every issue
    (see :func:`describe_issue`), using the formats and item units of the
    scenario ``info``. ``roles`` are the scenario's role names (in an item split
    the issues count the items of the role ``human``). Empty for utility
    functions without one value function per issue."""
    funs = _issue_funs(ufun)
    if not funs:
        return []
    info = info or {}
    fmts = info.get("issue_format") or {}
    split = info.get("split") or {}
    units, totals = split.get("units") or {}, split.get("totals") or {}
    lower = {str(r).lower() for r in roles}
    flipped = bool(split) and "human" in lower and str(getattr(ufun, "name", "")).lower() != "human"
    out = []
    for issue, fn in zip(ufun.outcome_space.issues, funs):
        name = str(issue.name)
        unit = tuple(units[name]) if name in units else None
        own = None
        if unit is not None and flipped:
            total = totals.get(name, issue.max_value)
            own = (lambda v, t=total: t - v)
        text = describe_issue(issue, fn, fmt=fmts.get(name, "{}"), unit=unit, own=own,  # type: ignore[arg-type]
                              opponent=opponent)
        if text:
            out.append((name, text))
    return out


def preference_summary(ufun: Any, *, opponent: bool = False) -> str:
    """A short, always-visible summary of ``ufun`` in plain words (markdown)."""
    you, your = ("the opponent", "its") if opponent else ("you", "your")
    if ufun is None:
        return ""
    unit = _unit_scale(ufun)
    scale = (f"Every possible deal is worth between 0% and 100% to {you}: 100% is {your} best deal."
             if unit else f"Every possible deal has a value for {you}; higher is better.")
    ws = getattr(ufun, "weights", None)
    names = [str(i.name) for i in getattr(getattr(ufun, "outcome_space", None), "issues", None) or []]
    funs = _issue_funs(ufun)
    try:
        ws = [float(w) for w in ws] if ws is not None and funs else None
    except Exception:  # noqa: BLE001
        ws = None
    if ws and len(ws) == len(names) and all(w >= 0 for w in ws) and sum(ws) > 0:
        tot = sum(ws)
        ranked = sorted(zip(names, [w / tot for w in ws]), key=lambda t: -t[1])
        if len(ranked) == 1:
            imp = f"Only **{ranked[0][0]}** is negotiated."
        else:
            imp = f"What matters most: {', then '.join(f'**{n}** ({_pct(w)})' for n, w in ranked[:2])}"
            imp += (f"; least: **{ranked[-1][0]}** ({_pct(ranked[-1][1])})." if len(ranked) > 2 else ".")
        how = (f"A deal is worth the weighted sum of the values of its options, so give way on the issues "
               f"that matter little to {you} to win the ones that matter most.")
        return f"{scale} {imp} {how}"
    if funs:
        return f"{scale} Each issue adds its own part to the total; the charts show what each option is worth."
    return f"{scale} The table shows the deals {you} like{'s' if opponent else ''} most."
