"""Normalized utility functions, as negmas (and negobench) define them.

A utility function is *normalized* when every deal is worth 0 to 1 (the worst deal 0,
the best 1). A linear-additive one is normalized in negmas's canonical form
("Normalization Method 3", see negmas's ``docs/normalization.rst``): the weights are
non-negative and add up to 1, there is no bias, and every issue's value function ranges
from 0 to 1. The value on disagreement goes through the same map as the deals, so it
keeps its place among them (it can fall below 0 if it was below the worst deal).

*Not normalized* means none of that: a deal can be worth anything, negative included,
value functions have any range and weights any size.

The work is negmas's (``ufun.normalize()``, ``Scenario.normalize`` and
``Scenario.is_normalized``); this module only adds the checks hani2 needs: a utility
function that is normalized already is returned as it is (so the built-in scenarios
never change), and one whose outcome space is too large to search is left alone.

Used by the Preferences tools (the normalized display) and by scenario generation (the
setting ``normalized_scenarios``).
"""

from __future__ import annotations

import math
from typing import Any

__all__ = ["is_normalized", "normalize", "normalize_scenario", "keep_names", "searchable", "on_range",
           "normalize_for_play", "raw_of", "RAW_ATTR"]

#: the attribute of a utility function normalized for a negotiation that holds the original
RAW_ATTR = "_hani2_raw"

#: spaces larger than this are not searched for their best and worst deals (unless the
#: utility function is linear-additive: negmas finds those issue by issue)
MAX_SEARCH = 5000
#: how far from 0 and 1 (and from 1 for the weights' sum) a normalized utility function may be:
#: saved scenarios round their numbers (a best deal of 0.9999 is normalized)
_TOL = 1e-3


def searchable(ufun: Any) -> bool:
    """Whether the best and worst deals can be found quickly: linear-additive (issue by
    issue) or a small outcome space."""
    from negmas.preferences import LinearAdditiveUtilityFunction

    if isinstance(ufun, LinearAdditiveUtilityFunction):
        return True
    try:
        os_ = ufun.outcome_space
        return bool(os_.is_finite() and os_.cardinality <= MAX_SEARCH)
    except Exception:  # noqa: BLE001
        return False


def _close(a: float, b: float) -> bool:
    return math.isfinite(a) and abs(a - b) < _TOL


def is_normalized(ufun: Any) -> bool:
    """Whether ``ufun`` is normalized (see the module): its deals range from 0 to 1 and, if
    it is linear-additive, its weights add up to 1 and every value function ranges from 0
    to 1. ``False`` when that cannot be told quickly."""
    from negmas.preferences import LinearAdditiveUtilityFunction

    if ufun is None or not searchable(ufun):
        return False
    try:
        lo, hi = (float(x) for x in ufun.minmax())
        if not (_close(lo, 0.0) and _close(hi, 1.0)):
            return False
        if isinstance(ufun, LinearAdditiveUtilityFunction):
            if abs(float(getattr(ufun, "_bias", 0.0) or 0.0)) > _TOL:
                return False
            ws = [float(w) for w in ufun.weights]
            if any(w < -_TOL for w in ws) or not _close(sum(ws), 1.0):
                return False
            for fn, issue in zip(ufun.values, ufun.outcome_space.issues):
                a, b = (float(x) for x in fn.minmax(issue))
                if a < -_TOL or b > 1 + _TOL:
                    return False
        return True
    except Exception:  # noqa: BLE001
        return False


def on_range(ufun: Any, r: float) -> float:
    """The value ``r`` of the way from ``ufun``'s worst deal to its best: ``r`` itself for a
    normalized utility function (or one too large to search), the same place on the scale
    of one that is not."""
    if not searchable(ufun) or is_normalized(ufun):
        return r
    try:
        lo, hi = (float(x) for x in ufun.minmax())
    except Exception:  # noqa: BLE001
        return r
    return round(lo + r * (hi - lo), 4) if math.isfinite(lo) and math.isfinite(hi) else r


def keep_names(new: Any, old: Any) -> Any:
    """``new`` with ``old``'s name and id (negmas gives a normalized copy a fresh id)."""
    for attr in ("name", "id"):
        try:
            if getattr(new, attr, None) != getattr(old, attr, None):
                setattr(new, attr, getattr(old, attr))
        except Exception:  # noqa: BLE001
            pass
    return new


def normalize(ufun: Any) -> Any:
    """``ufun`` normalized by negmas (``ufun.normalize()``: deals from 0 to 1, the canonical
    form for a linear-additive one). Returned as it is when it is normalized already,
    when its outcome space is too large to search, or when negmas cannot normalize it."""
    if ufun is None or not searchable(ufun) or is_normalized(ufun):
        return ufun
    try:
        return keep_names(ufun.normalize(), ufun)
    except Exception:  # noqa: BLE001
        return ufun


def normalize_scenario(scenario: Any) -> Any:
    """``scenario`` with every utility function normalized on its own (negmas's
    ``Scenario.normalize`` with ``common_range=False``, both ends guaranteed). A scenario
    normalized already is returned as it is, so the built-in generators' scenarios do not
    change."""
    ufuns = list(scenario.ufuns)
    if all(is_normalized(u) for u in ufuns) or not all(searchable(u) for u in ufuns):
        return scenario
    try:
        scenario.normalize(to=(0.0, 1.0), common_range=False, guarantee_min=True, guarantee_max=True)
    except Exception:  # noqa: BLE001 - one by one, leaving any negmas cannot normalize
        scenario.ufuns = tuple(normalize(u) for u in ufuns)
        return scenario
    scenario.ufuns = tuple(keep_names(n, o) for n, o in zip(scenario.ufuns, ufuns))
    return scenario


def normalize_for_play(scenario: Any) -> Any:
    """The scenario a negotiation is played on: ``scenario`` itself when it is normalized
    already, else a copy with every utility function normalized (:func:`normalize_scenario`),
    so the offer buttons, the gauges, the history, the scores, the opponent and the Assistant
    all work on 0..1. Each normalized utility function keeps a copy of the original (see
    :func:`raw_of`), which the Preferences tools show when they show raw numbers. The
    scenario passed in is never changed (saved scenarios may be cached)."""
    import copy

    ufuns = list(scenario.ufuns)
    if all(is_normalized(u) for u in ufuns) or not all(searchable(u) for u in ufuns):
        return scenario
    raws = [copy.deepcopy(u) for u in ufuns]
    play = copy.copy(scenario)
    play.ufuns = tuple(ufuns)
    play.stats = None
    normalize_scenario(play)
    for n, r in zip(play.ufuns, raws):
        try:
            setattr(n, RAW_ATTR, r)
        except Exception:  # noqa: BLE001
            pass
    return play


def raw_of(ufun: Any) -> Any:
    """The original of a utility function normalized for a negotiation
    (:func:`normalize_for_play`), with its value on disagreement at the place the normalized
    one has (so a forced value on disagreement shows in the original's numbers too); any
    other utility function as it is."""
    raw = getattr(ufun, RAW_ATTR, None)
    if raw is None:
        return ufun
    try:
        raw.reserved_value = on_range(raw, float(ufun.reserved_value))
    except Exception:  # noqa: BLE001
        pass
    return raw
