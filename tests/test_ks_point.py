"""Edge cases of the Kalai–Smorodinsky point (``EvalContext.ks_point``)."""
from __future__ import annotations

import math

import pytest

from hani2.evaluation.base import EvalContext
from hani2.recording.format import Recording

INF, NAN = math.inf, math.nan


def _ctx(points, reserved=(0.2, 0.2)):
    """A one-issue scenario whose outcomes have the given (human, opponent) utilities."""
    names = [f"o{i}" for i in range(len(points))]
    sc = {"t": 0, "k": "scenario", "name": "s", "human_index": 0, "outcomes": [[n] for n in names],
          "utilities": [[p[0] for p in points], [p[1] for p in points]], "reserved": list(reserved),
          "issue_names": ["x"]}
    return EvalContext(Recording.from_records([
        {"k": "header", "format": "hani2-recording", "version": 1, "id": "ks", "t0": 0}, sc,
        {"t": 0, "k": "start", "human_index": 0},
    ]))


@pytest.mark.parametrize("points, reserved, expected", [
    pytest.param([(0.6, 0.7)], (0.2, 0.2), (0.6, 0.7), id="single-outcome"),
    pytest.param([(0.2, 0.2)], (0.2, 0.2), (0.2, 0.2), id="single-outcome-both-degenerate"),
    pytest.param([(0.2, 0.9), (0.2, 0.5)], (0.2, 0.2), (0.2, 0.9), id="human-degenerate"),
    pytest.param([(0.9, 0.2), (0.5, 0.2)], (0.2, 0.2), (0.9, 0.2), id="opponent-degenerate"),
    pytest.param([(0.2, 0.5), (0.1, 0.9)], (0.2, 0.2), (0.2, 0.5), id="degenerate-skips-unacceptable"),
    pytest.param([(1.0, 0.2), (0.6, 0.6), (0.2, 1.0)], (0.2, 0.2), (0.6, 0.6), id="balanced"),
    pytest.param([(1.0, 0.6), (0.6, 1.0)], (0.2, 0.2), (1.0, 0.6), id="tie-first"),
    pytest.param([(0.1, 0.1), (0.15, 0.05)], (0.2, 0.2), None, id="all-below-reservation"),
    pytest.param([(0.9, 0.1), (0.1, 0.9)], (0.2, 0.2), None, id="none-acceptable-to-both"),
    pytest.param([(NAN, 0.9), (0.6, 0.6)], (0.2, 0.2), (0.6, 0.6), id="nan-utility"),
    pytest.param([(INF, 0.5), (0.6, 0.6)], (0.2, 0.2), (0.6, 0.6), id="inf-utility"),
    # an infinite point that dominates the finite ones is the only Pareto point, and it does not count
    pytest.param([(INF, 0.9), (0.6, 0.6)], (0.2, 0.2), None, id="inf-dominates-finite"),
    pytest.param([(NAN, NAN)], (0.2, 0.2), None, id="only-nan"),
    pytest.param([(INF, INF)], (0.2, 0.2), None, id="only-inf"),
])
def test_ks_point_edge_cases(points, reserved, expected):
    ks = _ctx(points, reserved).ks_point
    if expected is None:
        assert ks is None
    else:
        assert ks is not None and tuple(ks) == pytest.approx(expected)


def test_optimality_degenerate_scenario_reports_kalai_distance():
    from hani2.evaluation import evaluate_recording
    ctx = _ctx([(0.2, 0.9), (0.2, 0.5)])
    out = evaluate_recording(ctx.rec, ["optimality"])
    assert not out["errors"]
    assert out["row"]["kalai_distance"] == pytest.approx(0.7)  # no deal (0.2, 0.2) vs KS point (0.2, 0.9)
