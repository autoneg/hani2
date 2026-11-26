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
    assert pies_and_stacks(s) == (1, 0)  # the donut by default
    projects.create_project("P")
    projects.create_study("P/bar")
    _write(projects.study_dir(projects.StudyRef("P", "bar")) / "env.json", {"tools": {"weights_chart": "bar"}})
    s = make_session(study="P/bar")
    assert pies_and_stacks(s) == (0, 1)


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
    projects.create_project("F", defaults={"force_reserved_value": 0.2})
    projects.create_study("F/a")
    projects.create_study("F/zero", overrides={"force_reserved_value": 0})
    projects.create_study("G/b")
    for ref, want in (("F/a", 0.2), ("F/zero", 0.0), ("G/b", None)):
        with projects.use_study(ref):
            assert store.forced_reserved_value() == want, ref
    for ref, want in (("F/a", 0.2), ("F/zero", 0.0)):
        s = make_session(study=ref)
        assert all(float(u.reserved_value) == want for u in s.scenario.ufuns), ref
        assert s.reserved_value() == want
        assert s.ss["scenario_info"]["forced_reserved_value"] == want
    s = make_session(study="G/b")
    assert "forced_reserved_value" not in s.ss["scenario_info"]

