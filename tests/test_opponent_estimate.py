"""An estimate of the opponent's utility function (negmas' ``Negotiator.opponent_ufun``): set by the
Assistant or anyone, it unlocks the Negotiation Plot (marked as an estimate) and the Utility-based
Selector's opponent options."""

import json

from hani2.testing import make_session
from hani2.tools.builtin import OPP_COLUMN, NegotiationPlotTool, UtilitySelectorTool


def _tool(s, cls):
    return next((t for t in s.tools if isinstance(t, cls)), None)


def _text(view) -> str:
    return json.dumps(view, default=str)


def _flipped_spec(s) -> dict:
    """An estimate that differs from the opponent's real preferences: every option of every
    discrete issue valued the other way round from the human's."""
    values = {}
    for issue in s.scenario.outcome_space.issues:
        try:
            opts = list(issue.all)
        except Exception:  # noqa: BLE001 - continuous
            values[issue.name] = "increasing"
            continue
        if all(isinstance(o, (int, float)) for o in opts) and len(opts) > 20:
            values[issue.name] = "decreasing"
            continue
        values[issue.name] = {str(o): i / max(1, len(opts) - 1) for i, o in enumerate(opts)}
    return {"values": values, "reserved_value": 0.1}


def _plot_points(plot):
    return plot._space()["points"]


def test_no_estimate_no_extras():
    s = make_session()
    assert s.opponent_ufun_estimate is None
    assert _tool(s, NegotiationPlotTool) is None  # admin-only without an estimate
    s.start()
    s.wait_for_turn()
    sel = _tool(s, UtilitySelectorTool)
    assert OPP_COLUMN not in _text(sel.render()) and "estimate" not in _text(sel.render()).lower()


def test_assistant_estimate_unlocks_the_plot_with_the_estimate_only():
    s = make_session()
    res = s.support_agent.set_opponent_estimate(_flipped_spec(s))
    assert res["ok"], res
    plot = _tool(s, NegotiationPlotTool)
    assert plot is not None and plot.estimate_only
    assert s.tool_state(plot)["added_by"] == "assistant"
    view = _text(plot.render())
    assert "Estimate" in view and "Opponent utility (estimate)" in view
    assert "Real preferences" not in view and '"name": "opponent"' not in view  # no switch to the real ones
    # the points use the estimate (scaled to 0..1), not the opponent's real utility function
    est, real = s.opponent_ufun_estimate, s.opponent_ufun
    assert est is not None and real is not None
    outcomes = plot._space()["outcomes"]
    ys = [p[1] for p in _plot_points(plot)]
    assert ys != [float(real(o)) for o in outcomes]
    raw = [float(est(o)) for o in outcomes]
    lo, hi = min(raw), max(raw)
    assert max(abs(y - (r - lo) / (hi - lo)) for y, r in zip(ys, raw)) < 1e-9
    # a participant's copy never switches to the real preferences
    plot.on_input("opponent", "real")
    assert plot.opponent()[1] == "estimate"


def test_updating_and_clearing_the_estimate():
    s = make_session()
    agent = s.support_agent
    agent.set_opponent_estimate(_flipped_spec(s))
    plot = _tool(s, NegotiationPlotTool)
    first = _plot_points(plot)
    spec = _flipped_spec(s)
    spec["weights"] = {s.scenario.outcome_space.issues[0].name: 5}
    agent.set_opponent_estimate(spec)
    assert _plot_points(plot) != first
    assert agent.set_opponent_estimate(None)["ok"]
    assert s.opponent_ufun_estimate is None and _tool(s, NegotiationPlotTool) is None


def test_estimate_set_before_start_reaches_the_negotiator_and_is_dropped_by_the_next_scenario():
    s = make_session()
    s.support_agent.set_opponent_estimate(_flipped_spec(s))
    est = s.opponent_ufun_estimate
    s.start()
    s.wait_for_turn()
    neg = s._human_negotiator()
    assert neg.opponent_ufun is est
    s.end()
    s.wait_until_done()
    s.load()
    assert s.opponent_ufun_estimate is None and _tool(s, NegotiationPlotTool) is None


def test_estimate_set_straight_on_the_negotiator_is_picked_up():
    s = make_session()
    s.start()
    s.wait_for_turn()
    u = s.opponent_estimate_from_spec(_flipped_spec(s))
    s._human_negotiator().private_info["opponent_ufun"] = u
    s._tools_hook("action_requested")
    assert s.opponent_ufun_estimate is u and _tool(s, NegotiationPlotTool) is not None


def test_selector_shows_and_ranks_by_the_estimate_and_picks_only_issues():
    s = make_session()
    s.start()
    s.wait_for_turn()
    s.support_agent.set_opponent_estimate(_flipped_spec(s))
    sel = _tool(s, UtilitySelectorTool)
    sel.values.update(min_util=0, width=100)
    view = _text(sel.render())
    assert OPP_COLUMN in view and "estimate" in view
    sel.on_input("rank_by", "opponent")
    rows = next(c for c in sel.selector_view() if c.get("type") == "table")["rows"]
    assert rows[0][OPP_COLUMN] >= rows[-1][OPP_COLUMN] and "Utility" in rows[0]
    sel.on_action("pick", {"row": rows[0], "index": 0})
    issues = {i.name for i in s.scenario.outcome_space.issues}
    assert set(s.draft) <= issues and s.draft
    # without the estimate the options go and the sliders are the human's again
    s.support_agent.set_opponent_estimate(None)
    assert not sel._by_opponent() and OPP_COLUMN not in _text(sel.render())


def test_admin_plot_says_real_and_can_switch_between_estimate_and_real():
    s = make_session(is_admin=True)
    plot = _tool(s, NegotiationPlotTool)
    assert plot is not None and not plot.estimate_only
    assert "Real preferences" in _text(plot.render())
    s.support_agent.set_opponent_estimate(_flipped_spec(s))
    assert _tool(s, NegotiationPlotTool) is plot  # no second copy
    assert plot.opponent()[1] == "estimate" and "Estimate" in _text(plot.render())
    plot.on_input("opponent", "real")
    assert plot.opponent()[1] == "real" and plot.opponent()[0] is s.opponent_ufun


def test_capability_and_bad_estimates():
    s = make_session(assistant_settings={"capabilities": {"opponent_model": False}})
    assert not s.support_agent.set_opponent_estimate(_flipped_spec(s))["ok"]
    assert "set_opponent_estimate" not in {f["function"]["name"] for f in s.support_agent.dispatcher.schemas()}
    s = make_session()
    d = s.support_agent.dispatcher
    assert not d.execute("set_opponent_estimate", {"weights": {"No such issue": 1}})["ok"]
    issue = s.scenario.outcome_space.issues[0]
    bad = d.execute("set_opponent_estimate", {"values": {issue.name: {"not an option": 1}}})
    assert not bad["ok"] and "not an option" in bad["error"]
    assert not d.execute("set_opponent_estimate", {})["ok"]
    ok = d.execute("set_opponent_estimate", _flipped_spec(s))
    assert ok["ok"] and ok["estimate"]["by"] == "assistant"
    assert d.execute("set_opponent_estimate", {"clear": True})["ok"] and s.opponent_ufun_estimate is None


def test_disabled_plot_is_not_added(hani2_home):
    (hani2_home / "settings").mkdir(parents=True, exist_ok=True)
    (hani2_home / "settings" / "env.json").write_text(json.dumps({"tools": {"disabled": ["Negotiation Plot"]}}))
    s = make_session()
    assert s.support_agent.set_opponent_estimate(_flipped_spec(s))["ok"]
    assert _tool(s, NegotiationPlotTool) is None
