"""The compact Preferences tool (the weights as one bar, the hints in the summary on top with an
arrow per issue), the simple view as the default with the tools on either side, and a project's
or study's forced value on disagreement."""

import json

from negmas import make_issue
from negmas.preferences.value_fun import TableFun

from hani2 import projects
from hani2 import scenario_store as store
from hani2.testing import make_session
from hani2.tools import ufun_views as uv


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _walk(comps):
    for c in comps or []:
        if isinstance(c, dict):
            yield c
            yield from _walk(c.get("children"))


def _prefs(s):
    t = next(t for t in s.tools if t.name == "Preferences")
    return s.render_tool(s.tool_state(t)["id"])["view"]


# --------------------------------------------------------------------------- #
# Issue directions                                                             #
# --------------------------------------------------------------------------- #
def test_issue_directions():
    i = make_issue([1, 2, 3, 4, 5], "Days")
    assert uv.explain_issue(i, TableFun({1: 0, 2: .25, 3: .5, 4: .75, 5: 1}))[1] == "up"
    assert uv.explain_issue(i, TableFun({1: 1, 2: .75, 3: .5, 4: .25, 5: 0}))[1] == "down"
    assert uv.explain_issue(i, TableFun({1: 0, 2: .5, 3: 1, 4: .5, 5: 0}))[1] == "target"
    c = make_issue(["red", "blue"], "Color")
    assert uv.explain_issue(c, TableFun({"red": 1, "blue": 0})) == ("Best: red; worst: blue.", None)
    # describe_issue still gives the sentence alone
    assert uv.describe_issue(i, TableFun({1: 0, 2: .5, 3: 1, 4: .5, 5: 0}), fmt="{} days") == \
        "Best at 3 days; the further away from it, the worse."


def test_kv_marks():
    from hani2.tools import ui

    assert "marks" not in ui.kv({"a": 1})
    assert ui.kv({"a": 1, "b": 2}, marks=["up", "sideways"])["marks"] == ["up", None]
    assert ui.kv([("a", 1), ("b", 2)], marks={"b": "target"})["marks"] == [None, "target"]


# --------------------------------------------------------------------------- #
# The Preferences tool                                                         #
# --------------------------------------------------------------------------- #
def test_summary_with_hints_is_on_top_and_collapsible():
    s = make_session()
    view = _prefs(s)
    top = view[0]
    assert top["type"] == "card" and top["title"] == "In short" and top["collapsible"]
    assert top.get("id") == "preferences-in-short"
    assert not any(c.get("title") == "Hints" and c["type"] == "card" for c in view)  # no card at the bottom
    want = next((c for c in _walk(top["children"]) if c.get("title") == "What you want on each issue"), None)
    if want is not None and "marks" in want:
        assert len(want["marks"]) == len(want["items"])
        assert set(want["marks"]) <= {"up", "down", "target", None}


def test_weights_chart_donut_or_bar(hani2_home):
    def pies_and_stacks(s):
        figs = [c["figure"] for c in _walk(_prefs(s)) if c.get("type") == "plot"]
        pies = sum(1 for f in figs for tr in f.get("data") or [] if tr.get("type") == "pie")
        stacks = sum(1 for f in figs if (f.get("layout") or {}).get("barmode") == "stack")
        return pies, stacks

    s = make_session()
    assert pies_and_stacks(s) == (0, 1)  # the bar by default
    assert not any(c.get("type") == "placed" for c in _walk(_prefs(s)))  # one chart: the window draws it alike
    projects.create_project("P")
    projects.create_study("P/donut")
    _write(projects.study_dir(projects.StudyRef("P", "donut")) / "env.json", {"tools": {"weights_chart": "donut"}})
    s = make_session(study="P/donut")
    assert pies_and_stacks(s) == (1, 0)


def test_weights_donut_in_the_window_only(hani2_home):
    projects.create_project("P")
    projects.create_study("P/win")
    _write(projects.study_dir(projects.StudyRef("P", "win")) / "env.json",
           {"tools": {"weights_chart_window": "donut"}})
    s = make_session(study="P/win")
    placed = [c for c in _walk(_prefs(s)) if c.get("type") == "placed"]
    assert len(placed) == 1 and placed[0]["places"] == ["pane", "window"]
    pane, window = placed[0]["children"]
    assert next(c for c in _walk([pane]) if c.get("type") == "plot")["figure"]["layout"]["barmode"] == "stack"
    assert window["figure"]["data"][0]["type"] == "pie"
    from hani2.tools.describe import describe_components

    assert describe_components([placed[0]]) == describe_components([pane])  # text: the pane's version


def test_weights_and_values_side_by_side_when_narrow():
    grids = [c for c in _walk(_prefs(make_session())) if c.get("type") == "grid"]
    assert grids and grids[0]["narrow_min"] == uv.NARROW_COLUMN


def test_weights_bar_shares():
    plot, key = uv._weights_bar(["Price", "Days"], [3.0, 1.0])["children"]
    assert [tr["x"][0] for tr in plot["figure"]["data"]] == [75.0, 25.0]
    assert [(i["label"], i["value"]) for i in key["items"]] == [("Price", "75%"), ("Days", "25%")]
    from hani2.tools.describe import describe_components

    assert "Key: Price 75%, Days 25%" in describe_components([key])


# --------------------------------------------------------------------------- #
# Views                                                                        #
# --------------------------------------------------------------------------- #
def test_simple_view_is_the_default_with_tools_on_the_right():
    s = make_session()
    assert s.layout["view"] == "simple"
    assert s.snapshot()["layout"]["tools_side"] == "right"
    assert s.ss["view_source"] == "default"
    assert make_session(query={"view": "full"}).layout["view"] == "full"


def test_tools_on_the_left_and_full_view_per_study(hani2_home):
    projects.create_project("P")
    projects.create_study("P/left")
    _write(projects.study_dir(projects.StudyRef("P", "left")) / "env.json",
           {"interface": {"simple_tools_side": "left", "view": "full"}})
    s = make_session(study="P/left")
    assert s.snapshot()["layout"]["tools_side"] == "left"
    assert s.layout["view"] == "full" and s.ss["view_source"] == "study"
    projects.create_study("P/odd")
    _write(projects.study_dir(projects.StudyRef("P", "odd")) / "env.json", {"interface": {"simple_tools_side": "up"}})
    assert make_session(study="P/odd").snapshot()["layout"]["tools_side"] == "right"


# --------------------------------------------------------------------------- #
# Forced value on disagreement                                                 #
# --------------------------------------------------------------------------- #
def test_forced_reserved_value_is_a_project_and_study_setting(hani2_home):
    projects.create_project("F", defaults={"force_reserved_value": 0.123})
    projects.create_study("F/a")
    projects.create_study("F/zero", overrides={"force_reserved_value": 0})
    projects.create_study("G/b")
    for ref, want in (("F/a", 0.123), ("F/zero", 0.0), ("G/b", None)):
        with projects.use_study(ref):
            assert store.forced_reserved_value() == want, ref
    for ref, want in (("F/a", 0.123), ("F/zero", 0.0)):
        s = make_session(study=ref)
        hi = s.ss["human_index"]
        assert float(s.scenario.ufuns[hi].reserved_value) == want, ref
        assert s.reserved_value() == want
        assert s.ss["scenario_info"]["forced_reserved_value"] == want
    # the human only: the opponent keeps the scenario's own value
    s = make_session(study="F/a")
    hi = s.ss["human_index"]
    opp = [float(u.reserved_value) for i, u in enumerate(s.scenario.ufuns) if i != hi]
    assert opp and all(v != 0.123 for v in opp)
    sc, _, _ = store.load_scenario("Trade", 0)
    before = [float(u.reserved_value) for u in sc.ufuns]
    assert store.force_reserved_value(sc, 0.5, indices=(1,))
    assert [float(u.reserved_value) for u in sc.ufuns] == [before[0], 0.5]
    assert not store.force_reserved_value(sc, None, indices=(0,))
    s = make_session(study="G/b")
    assert "forced_reserved_value" not in s.ss["scenario_info"]



# --------------------------------------------------------------------------- #
# The value on disagreement right under In short                               #
# --------------------------------------------------------------------------- #
LEAD = "If you do not reach agreement you get"


def _sentences(comps, needle):
    return [c["text"] for c in _walk(comps) if c.get("type") == "alert" and needle in str(c.get("text", ""))]


def test_value_on_disagreement_is_right_under_in_short():
    view = _prefs(make_session())
    assert view[0]["title"] == "In short"
    under = view[1]
    assert under["type"] == "alert" and under["text"].startswith(LEAD) and "(your best option gives you 100%)" in under["text"]
    assert under.get("id") == "preferences-reserved"
    assert len(_sentences(view, LEAD)) == 1  # not repeated below the charts
    assert not _sentences(view[0].get("children"), LEAD)  # outside the card: seen also when it is folded


def test_value_on_disagreement_under_in_short_in_raw_numbers(hani2_home):
    from hani2.config import settings_dir

    _write(settings_dir() / "env.json", {"tools": {"preferences_scale": "raw"}})
    view = _prefs(make_session())
    assert view[0]["title"] == "In short" and view[1]["text"].startswith(LEAD)
    assert "%" not in view[1]["text"] and len(_sentences(view, LEAD)) == 1


def test_value_on_disagreement_hidden_is_said_under_in_short():
    s = make_session(load=False)
    s.admin_prefs["information"] = {"preferences": {"reserved_value": "assistant"}}
    s.load("Trade")
    view = _prefs(s)
    assert view[0]["title"] == "In short"
    assert view[1]["text"].startswith("You do not know what you get if no agreement is reached")
    assert not _sentences(view, LEAD)


def test_reserved_out_takes_the_sentence_of_any_view():
    from negmas import make_issue
    from negmas.outcomes import make_os
    from negmas.preferences import MappingUtilityFunction

    class _Tool:
        values: dict = {}

    os_ = make_os([make_issue([1, 2, 3], "A")])
    u = MappingUtilityFunction({(1,): 0.0, (2,): 0.5, (3,): 1.0}, outcome_space=os_, reserved_value=0.25)
    out: list = []
    comps = uv.render_ufun_view(_Tool(), u, reserved_out=out)
    assert len(out) == 1 and out[0]["text"].startswith(LEAD) and not _sentences(comps, LEAD)
    assert len(_sentences(uv.render_ufun_view(_Tool(), u), LEAD)) == 1  # without it: in the view, as before


def test_reserved_out_without_a_value_on_disagreement_keeps_the_fallback():
    from negmas import LinearAdditiveUtilityFunction as LAU
    from negmas import make_issue
    from negmas.outcomes import make_os

    class _Tool:
        values: dict = {}

    os_ = make_os([make_issue([1, 2], "A")])
    u = LAU(values=[TableFun({1: 0.0, 2: 1.0})], weights=[1.0], outcome_space=os_, reserved_value=float("-inf"))
    out: list = []
    comps = uv.render_ufun_view(_Tool(), u, reserved_out=out)
    assert len(out) == 1 and out[0]["text"] == f"{LEAD} nothing set by these preferences."
    assert None not in comps


def test_a_plugin_view_appending_reserved_stat_with_a_sink_leaves_no_gap():
    from negmas import make_issue
    from negmas.outcomes import make_os
    from negmas.preferences import MappingUtilityFunction

    class _Tool:
        values: dict = {}

    class _U(MappingUtilityFunction):
        pass

    uv.register_ufun_view(_U, lambda ctx: [ui_text("x"), ctx.reserved_stat()])
    try:
        u = _U({(1,): 0.0, (2,): 1.0}, outcome_space=make_os([make_issue([1, 2], "A")]), reserved_value=0.5)
        out: list = []
        comps = uv.render_ufun_view(_Tool(), u, reserved_out=out)
        assert None not in comps and len(out) == 1
    finally:
        uv.unregister_ufun_view(_U)


def ui_text(t):
    from hani2.tools import ui

    return ui.text_block(t)


def test_partial_preferences_put_the_value_on_disagreement_on_top():
    for part in ("weights", "values", "none"):
        s = make_session(load=False)
        s.admin_prefs["information"] = {"preferences": {"human": part, "assistant": "full"}}
        s.load("Trade")
        view = _prefs(s)
        assert not any(c.get("title") == "In short" for c in _walk(view)), part
        assert view[0]["type"] == "alert" and view[0]["text"].startswith(LEAD), part
        assert view[0].get("id") == "preferences-reserved"
        assert view[1].get("title") == "You know part of your preferences", part
        assert len(_sentences(view, LEAD)) == 1, part  # not repeated under the charts


def test_partial_preferences_hidden_value_on_top():
    s = make_session(load=False)
    s.admin_prefs["information"] = {"preferences": {"human": "weights", "assistant": "full",
                                                    "reserved_value": "assistant"}}
    s.load("Trade")
    view = _prefs(s)
    assert view[0]["text"].startswith("You do not know what you get if no agreement is reached")


def test_opponent_preferences_keep_the_value_under_the_charts():
    s = make_session(is_admin=True)
    view = s.tool_controller.find("Opponent Preferences").view()
    lead = "If no agreement is reached the opponent"
    assert lead not in json.dumps(view[:1])  # not on top (the admin warning is)
    alerts = [c for c in _walk(view) if c.get("type") == "alert" and lead in str(c.get("text"))]
    assert len(alerts) == 1
    body = next(c for c in view if c.get("type") == "column" and alerts[0] in c["children"])
    assert body["children"][-1] is alerts[0] and len(body["children"]) > 1  # under the charts, as before


# --------------------------------------------------------------------------- #
# The human may switch the weights between the bar and the donut               #
# --------------------------------------------------------------------------- #
def _switches(s):
    return [c for c in _walk(_prefs(s)) if c.get("type") == "radio" and c.get("name") == uv.WEIGHTS_CHART_INPUT]


def test_weights_chart_switch_is_off_by_default():
    from hani2.config import DEFAULT_ENV, get_env

    assert DEFAULT_ENV["tools"]["weights_chart_switch"] is False
    assert get_env("tools.weights_chart_switch") is False and not uv.weights_chart_switch()
    assert _switches(make_session()) == []


def test_weights_chart_switch_inherits_and_studies_override(hani2_home):
    projects.create_project("P")
    _write(projects.project_dir("P") / "env.json", {"tools": {"weights_chart_switch": True, "weights_chart": "donut"}})
    projects.create_study("P/on")
    projects.create_study("P/off")
    _write(projects.study_dir(projects.StudyRef("P", "off")) / "env.json", {"tools": {"weights_chart_switch": False}})
    sw = _switches(make_session(study="P/on"))
    assert len(sw) == 1 and sw[0]["value"] == "donut"  # starts at the configured chart
    assert [o["value"] for o in sw[0]["options"]] == ["bar", "donut"]
    assert _switches(make_session(study="P/off")) == []


def test_weights_chart_switch_changes_the_chart_and_is_remembered(hani2_home, monkeypatch):
    from hani2 import events as ev

    projects.create_project("P")
    projects.create_study("P/sw")
    _write(projects.study_dir(projects.StudyRef("P", "sw")) / "env.json",
           {"tools": {"weights_chart_switch": True, "weights_chart_window": "donut"}})
    s = make_session(study="P/sw")
    placed = [c for c in _walk(_prefs(s)) if c.get("type") == "placed"]
    assert len(placed) == 1  # each place starts at its own configured chart, with its own toggle
    assert [next(c for c in _walk([p]) if c.get("type") == "radio")["value"] for p in placed[0]["children"]] == \
        ["bar", "donut"]
    logged = []
    monkeypatch.setattr(ev, "log_event", lambda *a, **k: logged.append((a, k)))
    t = next(t for t in s.tools if t.name == "Preferences")
    s.tool_input(s.tool_state(t)["id"], uv.WEIGHTS_CHART_INPUT, "donut")
    assert logged and logged[-1][1]["action"] == "input:weights_chart" and logged[-1][1]["value"] == "donut"
    view = _prefs(s)  # rendered again: the choice holds in the pane and the window alike
    assert not any(c.get("type") == "placed" for c in _walk(view))
    assert [c["value"] for c in _switches(s)] == ["donut"]
    figs = [c["figure"] for c in _walk(view) if c.get("type") == "plot"]
    assert any(tr.get("type") == "pie" for f in figs for tr in f.get("data") or [])
    assert not any((f.get("layout") or {}).get("barmode") == "stack" for f in figs)
    s.tool_input(s.tool_state(t)["id"], uv.WEIGHTS_CHART_INPUT, "bar")
    assert [c["value"] for c in _switches(s)] == ["bar"]
