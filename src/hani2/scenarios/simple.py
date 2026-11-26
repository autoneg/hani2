"""Simple scenarios: generated preferences that are as easy to read as possible.

In *simple* mode (the ``simple_scenarios`` setting, see
:func:`hani2.scenario_store.simple_scenarios`) every generated scenario uses
round numbers and plain shapes:

- every option's value is a multiple of 5% (0% and 100% are kept), so no
  option is worth 34.6% (5%, not 10%, so that a linear issue with five options
  reads 0%, 25%, 50%, 75%, 100% and a symmetric triangle stays symmetric);
- issue weights are multiples of 10% that add up to 100% (5% when there are
  more than ten issues), none of them zero;
- the value on disagreement is a multiple of 5%;
- "more is better" and "less is better" issues are linear (every step is worth
  the same), and an issue with a best option in the middle falls off at the
  same rate on both sides (a symmetric triangle);
- drawn noise is switched off.

Because option values are multiples of 5% and weights multiples of 10%, the
value of every deal is a multiple of 0.5%.

Generators ask :func:`active` and draw simpler preferences; any scenario can
also be simplified after the fact with :func:`simplify_scenario` (used for
generators that know nothing about the mode). Use :func:`simple_mode` to turn
the mode on for a block of code::

    with simple_mode():
        scenario = registry.MAKERS["Lease"](0)
"""

from __future__ import annotations

import contextlib
import contextvars
import math
from typing import Any, Iterator, Sequence

__all__ = [
    "VALUE_STEP", "WEIGHT_STEP", "RESERVED_STEP", "SIMPLE_KEY", "active", "simple_mode", "snap", "snap_values",
    "snap_weights", "snap_reserved", "simplify_ufun", "simplify_scenario", "is_simple",
]

#: option values are multiples of this
VALUE_STEP = 0.05
#: issue weights are multiples of this (``WEIGHT_STEP / 2`` with more than 1 / WEIGHT_STEP issues)
WEIGHT_STEP = 0.1
#: the value on disagreement is a multiple of this
RESERVED_STEP = 0.05
#: the key in a scenario's info that marks it as generated in simple mode
SIMPLE_KEY = "simple"

_ACTIVE: contextvars.ContextVar[bool] = contextvars.ContextVar("hani2_simple_scenarios", default=False)


def active() -> bool:
    """Whether scenarios are being generated in simple mode."""
    return _ACTIVE.get()


@contextlib.contextmanager
def simple_mode(on: bool = True) -> Iterator[None]:
    """Generate simple scenarios inside the block (``on=False`` turns the mode off)."""
    token = _ACTIVE.set(bool(on))
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def snap(x: float, step: float) -> float:
    """``x`` rounded to the nearest multiple of ``step``, halves up (as a clean float)."""
    digits = max(0, -int(math.floor(math.log10(step))) + 1)
    return round(math.floor(float(x) / step + 0.5 + 1e-9) * step, digits)


def snap_values(d: dict[Any, float], step: float = VALUE_STEP) -> dict[Any, float]:
    """Rescale option values to [0, 1] (worst 0, best 1) and round them to ``step``.
    Rounding keeps the order of the options (ties may appear) and both ends."""
    if not d:
        return {}
    lo, hi = min(d.values()), max(d.values())
    if hi - lo < 1e-9:
        return {k: 1.0 for k in d}
    return {k: snap((v - lo) / (hi - lo), step) for k, v in d.items()}


def snap_weights(ws: Sequence[float], step: float | None = None) -> list[float]:
    """Weights as multiples of ``step`` that add up to 1, each at least one step
    (largest-remainder rounding). The default step is :data:`WEIGHT_STEP`, halved
    while there are more issues than steps."""
    n = len(ws)
    if n == 0:
        return []
    if step is None:
        step = WEIGHT_STEP
        while n * step > 1 + 1e-9:
            step /= 2
    units = int(round(1 / step))
    ws = [max(0.0, float(w)) for w in ws]
    total = sum(ws) or 1.0
    ws = [w / total if sum(ws) else 1.0 / n for w in ws]
    # every issue gets one unit; the rest is shared out by largest remainder
    spare = units - n
    raw = [max(0.0, w * units - 1) for w in ws]
    raw_total = sum(raw)
    raw = [r * spare / raw_total for r in raw] if raw_total > 0 else [spare / n] * n
    base = [int(math.floor(r)) for r in raw]
    left = spare - sum(base)
    order = sorted(range(n), key=lambda i: (-(raw[i] - base[i]), -ws[i], i))
    for i in order[:left]:
        base[i] += 1
    return [snap((b + 1) * step, step / 10) for b in base]


def snap_reserved(r: float, step: float = RESERVED_STEP) -> float:
    """The value on disagreement rounded to ``step`` (kept within [0, 1])."""
    return min(1.0, max(0.0, snap(r, step)))


def is_simple(scenario: Any) -> bool:
    """Whether a scenario was generated in simple mode (marked in its info)."""
    return bool((getattr(scenario, "info", None) or {}).get(SIMPLE_KEY))


def simplify_ufun(ufun: Any) -> Any:
    """A simplified copy of a linear-additive utility function over discrete
    issues: option values rescaled to [0, 1] and rounded, weights rounded, the
    value on disagreement rounded. Other utility functions are returned as they are."""
    from negmas import LinearAdditiveUtilityFunction
    from negmas.preferences.value_fun import TableFun

    if not isinstance(ufun, LinearAdditiveUtilityFunction):
        return ufun
    os_ = ufun.outcome_space
    issues = list(getattr(os_, "issues", None) or [])
    if not issues or any(i.is_continuous() for i in issues):
        return ufun
    tables = []
    for issue, fn in zip(issues, ufun.values):
        vals = {}
        for v in issue.all:
            try:
                vals[v] = float(fn(v))
            except Exception:  # noqa: BLE001
                return ufun
        tables.append(TableFun(snap_values(vals)))
    rv = ufun.reserved_value
    rv = snap_reserved(rv) if isinstance(rv, (int, float)) and math.isfinite(rv) else rv
    return LinearAdditiveUtilityFunction(tuple(tables), weights=tuple(snap_weights(list(ufun.weights))),
                                         reserved_value=rv, name=ufun.name, id=ufun.id, outcome_space=os_)


def simplify_scenario(scenario: Any) -> Any:
    """Simplify every utility function of ``scenario`` (see :func:`simplify_ufun`),
    recompute the hints derived from them and mark the scenario as simple. Safe to
    call on a scenario that is simple already (nothing changes)."""
    from negmas import Scenario

    from copy import deepcopy

    from .story import derived_hints

    ufuns = tuple(simplify_ufun(u) for u in scenario.ufuns)
    out = Scenario(outcome_space=scenario.outcome_space, ufuns=ufuns, info=deepcopy(dict(scenario.info or {})))
    out.info[SIMPLE_KEY] = True
    # the hints computed from the preferences (most important issue, ideal deal) follow the new numbers
    hints = out.info.get("hints") or {}
    for role, d in derived_hints(out).items():
        h = hints.get(role)
        if isinstance(h, dict):
            h.update({k: v for k, v in d.items() if k in h})
    return out
