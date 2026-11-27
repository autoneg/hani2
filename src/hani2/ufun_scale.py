"""Utility functions scaled so that the best deal is worth 1 (100%).

Normalized here means *scaled*, never shifted: the best deal is worth 1, a deal worth 0
stays at 0 and the value on disagreement keeps its sign. An additive utility function
keeps its shape: each issue's values are divided by that issue's best value (so its
favourite option is worth 1) and the weights take the difference (so they add up to 1).
Utility functions whose best deal is worth 1 already are returned as they are, so the
scenarios the built-in generators make are never changed.

Used by the Preferences tools (the normalized display) and by scenario generation (the
setting ``normalized_scenarios``).
"""

from __future__ import annotations

import math
from typing import Any

__all__ = ["best_value", "is_scaled", "scale_to_best", "scale_by", "keep_names"]

#: spaces larger than this are not searched for their best deal (unless the ufun is additive)
MAX_SEARCH = 5000
_TOL = 1e-6


def _additive(ufun: Any) -> bool:
    from negmas.preferences import LinearAdditiveUtilityFunction

    return type(ufun) is LinearAdditiveUtilityFunction


def _cheap(ufun: Any) -> bool:
    """Whether the best deal can be found quickly: additive (issue by issue) or a small space."""
    from negmas.preferences import LinearAdditiveUtilityFunction

    if isinstance(ufun, LinearAdditiveUtilityFunction):
        return True
    try:
        os_ = ufun.outcome_space
        return bool(os_.is_finite() and os_.cardinality <= MAX_SEARCH)
    except Exception:  # noqa: BLE001
        return False


def best_value(ufun: Any) -> float | None:
    """The value of the best deal; ``None`` when it cannot be found (quickly)."""
    if ufun is None or not _cheap(ufun):
        return None
    try:
        hi = float(ufun.minmax()[1])
    except Exception:  # noqa: BLE001
        return None
    return hi if math.isfinite(hi) else None


def is_scaled(ufun: Any) -> bool:
    """Whether the best deal is worth 1 (or that cannot be told, or scaling cannot help)."""
    hi = best_value(ufun)
    return hi is None or hi <= 0 or abs(hi - 1.0) < _TOL


def keep_names(new: Any, old: Any) -> Any:
    """``new`` with ``old``'s name and id (negmas gives a scaled copy a fresh id)."""
    for attr in ("name", "id"):
        try:
            if getattr(new, attr, None) != getattr(old, attr, None):
                setattr(new, attr, getattr(old, attr))
        except Exception:  # noqa: BLE001
            pass
    return new


def _scaled_rv(rv: Any, k: float) -> Any:
    try:
        return float(rv) * k if rv is not None and math.isfinite(float(rv)) else rv
    except Exception:  # noqa: BLE001
        return rv


def scale_by(ufun: Any, k: float, *, weights: bool = True) -> Any:
    """``ufun`` multiplied by ``k`` (the value on disagreement too). An additive utility
    function scales its weights (``weights``) and keeps its option values."""
    from negmas.preferences import LinearAdditiveUtilityFunction as LAU

    if weights and _additive(ufun):
        bias = float(getattr(ufun, "_bias", 0.0) or 0.0)
        return keep_names(LAU(values=ufun.values, weights=[float(w) * k for w in ufun.weights], bias=bias * k,
                              outcome_space=ufun.outcome_space, name=ufun.name,
                              reserved_value=_scaled_rv(ufun.reserved_value, k)), ufun)
    return keep_names(ufun.scale_by(k), ufun)


def _additive_to_best(ufun: Any, hi: float) -> Any | None:
    """An additive ``ufun`` with every issue's best option worth 1 and weights adding up to
    1 (``None`` when that does not give the same preferences, e.g. with a bias)."""
    from negmas.preferences import LinearAdditiveUtilityFunction as LAU

    if float(getattr(ufun, "_bias", 0.0) or 0.0) != 0.0:
        return None
    issues = list(ufun.outcome_space.issues)
    values, weights = [], []
    for fn, w, issue in zip(ufun.values, ufun.weights, issues):
        m = float(fn.minmax(issue)[1])
        if not math.isfinite(m) or m <= 0 or float(w) < 0:
            return None
        values.append(fn.scale_by(1.0 / m) if abs(m - 1.0) > _TOL else fn)
        weights.append(float(w) * m / hi)
    if abs(sum(weights) - 1.0) > 1e-6:  # the issues' best options are not reached together
        return None
    return keep_names(LAU(values=values, weights=weights, outcome_space=ufun.outcome_space, name=ufun.name,
                          reserved_value=_scaled_rv(ufun.reserved_value, 1.0 / hi)), ufun)


def scale_to_best(ufun: Any) -> Any:
    """``ufun`` scaled so that its best deal is worth 1 (see the module). Returned as it is
    when that is so already, or when it cannot be scaled."""
    if is_scaled(ufun):
        return ufun
    hi = best_value(ufun)
    assert hi is not None
    try:
        if _additive(ufun):
            out = _additive_to_best(ufun, hi)
            if out is not None:
                return out
        return scale_by(ufun, 1.0 / hi, weights=False)
    except Exception:  # noqa: BLE001
        return ufun
