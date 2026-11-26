"""The Utility Bar: the graphical utility inverter (click or drag on a 0-100% bar of the human's
utility and get offers from that part of it), the ``ui.range_bar`` component, the ``generator``
flag the page uses to list offer generators, and the ``popup`` render key."""

import json

import numpy as np

from hani2.testing import make_session
from hani2.tools import ui
from hani2.tools.builtin import UtilityBarTool
from hani2.tools.describe import describe_components


def _bar(s) -> UtilityBarTool:
    return next(t for t in s.tools if isinstance(t, UtilityBarTool))


def _started(**kw):
    s = make_session(**kw)
    s.start()
    s.wait_for_turn()
    return s


def _flipped_estimate(s) -> dict:
    values = {}
    for issue in s.scenario.outcome_space.issues:
        try:
            opts = list(issue.all)
        except Exception:  # noqa: BLE001 - continuous
            values[issue.name] = "increasing"
            continue
        values[issue.name] = {str(o): i / max(1, len(opts) - 1) for i, o in enumerate(opts)}
    return {"values": values, "reserved_value": 0.1}


def test_range_bar_component():
    c = ui.range_bar("area", [80, 20], density=[1, 2], marks=[{"value": 40, "label": "No deal", "kind": "bad"}])
    assert c["type"] == "range_bar" and c["value"] == [20.0, 80.0] and c["min"] == 0 and c["max"] == 100
    assert ui.range_bar("area", 42)["value"] == [42.0, 42.0]
    text = describe_components([c])
    assert "Input 'area'" in text and "[low, high]" in text


def test_it_is_the_first_generator_and_opens_the_side_pane():
    s = _started()
    side = sorted((t for t in s.tools if s.tool_state(t)["pane"] == "side"), key=lambda t: s.tool_state(t)["order"])
    assert side[0].name == "Utility Bar"
    assert s.active_tabs["side"] == "Utility Bar"
    tools = {t["name"]: t for t in s.snapshot()["tools"]}
    assert tools["Utility Bar"]["generator"] and tools["Utility-based Selector"]["generator"]
    assert not tools["Preferences"]["generator"]


def test_drag_modes():
    s = _started()
    b = _bar(s)
    _, mine = b._space()
    b.on_input("area", [40, 90])
    inside = {int(i) for i in np.flatnonzero((mine >= 0.4 - 1e-9) & (mine <= 0.9 + 1e-9))}
    assert inside, "the scenario has deals worth 40-90%"
    for mode in ("any", "some", "all"):
        b.on_input("mode", mode)
        res = b.results()
        assert res and set(res) <= inside, mode
    b.on_input("mode", "all")
    res = b.results()
    assert set(res) == inside and [mine[i] for i in res] == sorted((mine[i] for i in res), reverse=True)
    b.on_input("mode", "some")
    assert len(b.results()) == min(10, len(inside))
    # "Any offer" stays in the part (no fallback to a better deal) and "Another" draws again
    b.on_input("mode", "any")
    draws = set()
    for _ in range(12):
        draws.update(b.results())
        b.on_action("draw", {})
    assert draws <= inside and (len(draws) > 1 or len(inside) == 1)


def test_an_empty_part_says_so():
    import pytest

    s = _started()
    b = _bar(s)
    _, mine = b._space()
    u = sorted(set(float(x) * 100 for x in mine))
    gaps = [(a, c) for a, c in zip(u, u[1:]) if c - a > 2]
    if not gaps:
        pytest.skip("no gap between deals in this scenario")
    a, c = gaps[0]
    b.on_input("area", [a + 0.5, c - 0.5])
    assert not b.is_click() and b.results() == []
    assert "No deal is worth" in json.dumps(b.render())
    b.on_input("area", [a + 0.5, a + 0.5])  # a click there still finds the nearest deal
    assert b.results()


def test_click_finds_the_nearest():
    s = _started()
    b = _bar(s)
    _, mine = b._space()
    b.on_input("area", [37, 37])
    assert b.is_click()
    best = float(np.abs(mine - 0.37).min())
    for mode in ("any", "all"):
        b.on_input("mode", mode)
        res = b.results()
        assert res and all(abs(abs(mine[i] - 0.37) - best) < 1e-9 for i in res), mode
    b.on_input("mode", "some")
    res = b.results()
    nearest = sorted(np.abs(mine - 0.37))[: len(res)]
    assert len(res) == min(10, len(mine)) and sorted(abs(mine[i] - 0.37) for i in res) == nearest


def test_set_offer_and_pick_fill_the_draft():
    s = _started()
    b = _bar(s)
    b.on_input("area", [0, 100])
    b.on_input("mode", "some")
    b.on_action("set_offer", {})
    first = b._space()[0][b.results()[0]]
    assert tuple(s.draft[i.name] for i in s.scenario.outcome_space.issues) == tuple(first)
    table = next(c for c in b.render() if c["type"] == "table")
    row = table["rows"][-1]
    b.on_action("pick", {"row": row, "index": len(table["rows"]) - 1})
    assert all(s.draft[k] == v for k, v in row.items() if k != "Utility")


def test_opponent_modes_need_an_estimate_or_an_admin():
    # a participant without an estimate: no opponent modes, and asking for one gives "any"
    s = _started()
    b = _bar(s)
    assert b.opponent() == (None, None)
    b.on_input("mode", "opp_best")
    assert b.mode() == "any"
    sel = next(c for c in b.render() if c["type"] == "row")["children"][0]
    assert {o["value"] for o in sel["options"]} == {"any", "some", "all"}
    # with an estimate: the modes appear and rank by the estimate
    assert s.set_opponent_estimate(_flipped_estimate(s))["ok"]
    assert b.opponent()[1] == "estimate"
    b.on_input("area", [0, 100])
    b.on_input("mode", "opp_top")
    opp, _ = b._opp_utils()
    assert opp is not None
    res = b.results()
    assert b.mode() == "opp_top" and len(res) == 10
    assert [opp[i] for i in res] == sorted((opp[i] for i in res), reverse=True)
    assert float(opp[res[0]]) == float(opp.max())
    view = json.dumps(b.render())
    assert "Opponent (estimate)" in view and "estimate" in view
    # an admin sees the real preferences
    a = _started(is_admin=True)
    ab = _bar(a)
    assert ab.opponent()[1] == "real"
    ab.on_input("mode", "opp_best")
    assert ab.mode() == "opp_best" and len(ab.results()) == 1


def test_popup_key_is_rendered():
    s = _started()
    s.active_tabs["popup"] = "Preferences"
    assert "Preferences" in s.shown_tool_names()


def test_the_bar_shows_where_deals_are_and_the_marks():
    s = _started()
    b = _bar(s)
    bar = next(c for c in b.render() if c["type"] == "range_bar")
    assert sum(bar["density"]) == len(b._space()[0])
    assert any(m["label"] == "No deal" for m in bar.get("marks", []))


def test_the_assistant_sets_the_bar(hani2_home):
    s = _started(support_settings={"autonomy": "suggest"})
    sa = s.support_agent
    b = _bar(s)
    read = sa.read_tool("Utility Bar")
    assert read["ok"] and "Input 'area'" in read["text"] and "[low, high]" in read["text"]
    for given in ([40, 60], "40-60", "[40, 60]", {"low": 40, "high": 60}):
        res = sa.use_tool("Utility Bar", inputs={"area": given, "mode": "All offers"})
        assert res["ok"], res
        assert b.area() == (40.0, 60.0) and b.mode() == "all", given
    res = sa.use_tool("Utility Bar", inputs={"area": 55, "mode": "any"}, action="set_offer")
    assert res["ok"] and b.is_click() and s.draft
