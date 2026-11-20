import time

import pytest
from conftest import write_settings

from hani2.testing import make_session
from hani2.tools import Tool, ui
from hani2.tools.registry import tool_specs


def names(s):
    return [t.name for t in s.tools]


def test_tools_appear_by_timing_and_role():
    s = make_session()
    assert {"Preferences", "Scenario Info", "My Results"} <= set(names(s))
    assert "Trace" not in names(s)
    s.start()
    s.wait_for_turn()
    assert {"Utility Plot", "Outcome Plot", "Trace", "Value Histogram", "Utility-based Selector"} <= set(names(s))
    assert "LLM" not in names(s) and "Opponent Preferences" not in names(s)


def test_admin_query_flag_does_not_unlock_admin_tools():
    s = make_session(query={"admin": "1"})
    s.admin_mode = True
    s.start()
    s.wait_for_turn()
    assert "Opponent Preferences" not in names(s)
    trace = s.tool_controller.find("Trace")
    trace.values["show_agent"] = True
    view = trace.render()
    assert "Opponent utility" not in view[-1]["columns"]


def test_admin_gets_admin_tools():
    s = make_session(is_admin=True)
    s.start()
    s.wait_for_turn()
    assert {"LLM", "Random", "All Results", "Opponent Preferences"} <= set(names(s))


@pytest.mark.parametrize("phase", ["ready", "running", "ended"])
def test_every_builtin_tool_renders(phase):
    s = make_session(is_admin=True)
    if phase != "ready":
        s.start()
        s.wait_for_turn()
        s.play_counters(2)
    if phase == "ended":
        s.end()
        s.wait_until_done()
    for t in s.tools:
        if not s.tool_available(t):  # e.g. Past Negotiations: only with an information split
            assert s.render_tool(s.tool_state(t)["id"]) is None
            continue
        if not s.tool_state(t)["enabled"]:
            s.tool_controller.set_tool_enabled(t.name, True)
        view = s.render_tool(s.tool_state(t)["id"])["view"]
        assert isinstance(view, list) and view, t.name
        assert not any(c["type"] == "alert" and "failed to render" in c.get("text", "") for c in view), (t.name, view)


def test_utility_selector_row_sets_offer():
    s = make_session()
    s.start()
    s.wait_for_turn()
    sel = s.tool_controller.find("Utility-based Selector")
    sel.on_input("min_util", 0)
    sel.on_input("width", 100)
    table = next(c for c in sel.render() if c["type"] == "table")
    row = table["rows"][0]
    sel.on_action("pick", {"row": row, "index": 0})
    assert all(s.draft[k] == v for k, v in row.items() if k != "Utility")


def test_utility_selector_defaults_to_best_and_handles_unnormalized_ufuns():
    from types import SimpleNamespace

    from negmas import make_issue
    from negmas.outcomes import make_os
    from negmas.preferences import LinearAdditiveUtilityFunction
    from negmas.preferences.value_fun import AffineFun

    from hani2.tools.builtin import UtilitySelectorTool

    os = make_os([make_issue(10, "a"), make_issue(5, "b")])
    ufun = LinearAdditiveUtilityFunction(
        values=[AffineFun(3.0, 10), AffineFun(-2.0, 0)], weights=[2.0, 5.0], outcome_space=os
    )  # utilities span [-20, 74]
    sel = UtilitySelectorTool({"human_ufun": ufun, "scenario": SimpleNamespace(outcome_space=os)})
    assert sel.values["width"] == 100 and sel._range() == (0.7, 1.0)
    rows = next(c for c in sel.render() if c["type"] == "table")["rows"]
    utils = [r["Utility"] for r in rows]
    assert utils[0] == pytest.approx(1.0) and all(0.7 - 1e-9 <= u <= 1.0 + 1e-9 for u in utils)
    assert ufun(sel.get_outcome()) >= -20 + 0.7 * 94 - 1e-9
    sel.values["min_util"] = 100
    assert ufun(sel.get_outcome()) == pytest.approx(74.0)


def test_utility_selector_follows_a_new_ufun_before_the_negotiation_starts():
    """The next scenario's ufun replaces the old one before start: the selector must not reuse the old inverter."""
    from types import SimpleNamespace

    from negmas import make_issue
    from negmas.outcomes import make_os
    from negmas.preferences import LinearAdditiveUtilityFunction
    from negmas.preferences.value_fun import AffineFun, TableFun

    from hani2.tools.builtin import UtilitySelectorTool

    os1 = make_os([make_issue(10, "a")])
    u1 = LinearAdditiveUtilityFunction(values=[AffineFun(1.0, 0)], outcome_space=os1)
    state = {"human_ufun": u1, "scenario": SimpleNamespace(outcome_space=os1)}
    sel = UtilitySelectorTool(state)
    assert next(c for c in sel.render() if c["type"] == "table")["rows"]
    os2 = make_os([make_issue(["x", "y"], "b")])
    u2 = LinearAdditiveUtilityFunction(values=[TableFun({"x": 0.0, "y": 1.0})], outcome_space=os2)
    state.update(human_ufun=u2, scenario=SimpleNamespace(outcome_space=os2))
    view = sel.render()
    assert not any(c["type"] == "alert" for c in view), view
    rows = next(c for c in view if c["type"] == "table")["rows"]
    assert [r["b"] for r in rows] == ["y"]


def test_tool_controller_move_hide_focus():
    s = make_session()
    c = s.tool_controller
    assert c.move_tool("Scenario Info", pane="side")["ok"]
    assert s.tool_state(c.find("Scenario Info"))["pane"] == "side"
    assert not c.set_tool_visible("Preferences", False)["ok"]  # permanent
    s.start()
    s.wait_for_turn()
    assert c.set_tool_visible("Trace", False)["ok"]
    assert c.focus_tool("Trace")["ok"]
    st = s.tool_state(c.find("Trace"))
    assert st["visible"] and st["enabled"] and s.active_tabs[st["pane"]] == "Trace"


class Counter(Tool):
    name = "Counter"
    pane = "side"
    timing = "load"

    def view(self):
        return [ui.stat("clicks", self.values.get("n", 0)), ui.button("+1", "inc")]

    def on_action(self, action, payload):
        self.values["n"] = self.values.get("n", 0) + 1


def test_extra_tools_from_settings(hani2_home):
    write_settings(hani2_home, "env.json", {"tools": {"extra": ["test_tools:Counter", "what_if:WhatIf", "offer_counter:OfferCounter",
                                                                 "concession_tracker:ConcessionTracker"],
                                                       "disabled": ["Trace"], "overrides": {"Value Histogram": {"pane": "side"}}}})
    specs = {s.name: s for s in tool_specs()}
    assert "Trace" not in specs and specs["Value Histogram"].pane == "side"
    s = make_session()
    t = s.tool_controller.find("Counter")
    tid = s.tool_state(t)["id"]
    s.tool_action(tid, "inc", {})
    assert s.render_tool(tid)["view"][0]["value"] == 1
    s.start()
    s.wait_for_turn()
    s.play_counters(2)
    for name in ("What If", "Offer Counter", "Concession Tracker"):
        view = s.tool_controller.find(name).render()
        assert view and view[0]["type"] != "alert", name
    wi = s.tool_controller.find("What If")
    first = s.issues[0]
    wi.on_input(first.name, list(first.all)[-1])
    wi.on_action("use", {})
    assert s.draft[first.name] == list(first.all)[-1]


def test_broken_tool_shows_an_error_instead_of_crashing():
    class Broken(Tool):
        def view(self):
            raise RuntimeError("boom")

    s = make_session()
    v = Broken(s.ss).render()
    assert v[0]["type"] == "alert" and "boom" in v[0]["text"]


def test_ui_jsonable_handles_numpy_and_nan():
    import math

    import numpy as np

    assert ui.jsonable({"a": np.float64(1.5), "b": float("nan"), "c": (np.int64(2),)}) == {"a": 1.5, "b": None, "c": [2]}
    assert ui.table([{"x": math.inf}])["rows"][0]["x"] == "inf"


def test_llm_tool_generates_and_applies(monkeypatch):
    import json as _json

    import hani2.llm_service as llm

    s = make_session(is_admin=True)
    s.start()
    s.wait_for_turn()
    outcome = {i.name: list(i.all)[0] for i in s.issues}
    monkeypatch.setattr(llm, "is_llm_configured", lambda: True)
    monkeypatch.setattr(llm, "_call_llm", lambda prompt, settings=None: _json.dumps(
        {"text": "How about this?", "outcome": outcome, "reasoning": "fair"}))
    tool = s.tool_controller.find("LLM")
    tool.on_action("generate", {"instruction": "be fair"})
    assert s.wait(lambda: not tool.busy, 10)
    assert tool.generated and tool.generated["text"] == "How about this?", tool.status
    tool.on_action("apply", {})
    assert s.draft == outcome and s.draft_text == "How about this?"
    assert "instruction_prompt" in __import__("hani2.config", fromlist=["x"]).load_llm_settings()


def test_negotiation_plot_for_admins():
    s = make_session(is_admin=True)
    assert "Negotiation Plot" in names(s)
    s.start()
    s.wait_for_turn()
    s.play_counters(2)
    plot = next(c for c in s.tool_controller.find("Negotiation Plot").render() if c["type"] == "plot")
    traces = {t.get("name") for t in plot["figure"]["data"]}
    assert {"Outcomes", "Pareto frontier", "Nash", "Your offers", "Opponent offers"} <= traces
    assert "Negotiation Plot" not in names(make_session())


def test_admin_can_open_admin_only_tools_to_everyone(hani2_home):
    write_settings(hani2_home, "env.json", {"tools": {"overrides": {"negotiation plot": {"admin_only": False},
                                                                     "Opponent Preferences": {"admin_only": False}},
                                                       "show_opponent_utility": True}})
    s = make_session()
    assert {"Negotiation Plot", "Opponent Preferences"} <= set(names(s))
    s.start()
    s.wait_for_turn()
    trace = s.tool_controller.find("Trace")
    trace.values["show_agent"] = True
    assert "Opponent utility" in trace.render()[-1]["columns"]


def test_practice_rounds_never_count_in_scores_or_leaderboard():
    import pandas as pd

    from hani2.results import leaderboard
    from hani2.tools.builtin import _results_view

    # practice is read back from results.csv as a bool (or a string in mixed/old files)
    rows = [dict(user="alice", scenario="s", human_utility=u, practice=p, status="success")
            for u, p in [(0.5, False), (0.5, False), (1.0, True), (1.0, "True")]]
    rows += [dict(user="bob", scenario="s", human_utility=u, practice=False) for u in (0.6, 0.6)]
    df = pd.DataFrame(rows)
    lb = leaderboard(df)
    assert [r["user"] for r in lb] == ["bob", "alice"]
    assert lb[1]["negotiations"] == 2 and lb[1]["mean_utility"] == pytest.approx(0.5)

    class _T:
        values: dict = {}

    comps = _results_view(_T(), df[df["user"] == "alice"], leaderboard=False)
    stats = {c["label"]: c["value"] for c in comps[0]["children"]}
    assert stats == {"Score": "50.0", "Negotiations": 2, "Agreements": 2}
    assert len(comps[-1]["rows"]) == 4  # the table still lists the practice rounds
    # right after the practice round: nothing counts yet, but the round is listed
    comps = _results_view(_T(), df.iloc[2:4], leaderboard=False)
    assert {c["label"]: c["value"] for c in comps[0]["children"]} == {"Score": "0.0", "Negotiations": 0, "Agreements": 0}
    assert len(comps[-1]["rows"]) == 2
