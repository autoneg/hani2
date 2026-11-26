"""The Assistant's control of the interface: the bare (no tools) view and a study's fixed view,
how offers read (display overrides), and the participant's display settings and style sheet."""

import json

from hani2 import projects
from hani2.server import _dispatch
from hani2.testing import make_session


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _names(s):
    return {f["function"]["name"] for f in s.support_agent.dispatcher.schemas()}


# --------------------------------------------------------------------------- #
# Views                                                                        #
# --------------------------------------------------------------------------- #
def test_assistant_switches_between_simple_full_and_bare():
    s = make_session()
    d = s.support_agent.dispatcher
    for view in ("simple", "full", "focus", "bare", "full"):
        assert d.execute("set_layout", {"view": view})["ok"]
        assert s.layout["view"] == view and s.snapshot()["layout"]["view"] == view
    assert not d.execute("set_layout", {"view": "sideways"})["ok"]
    assert "bare" in json.dumps(next(f for f in d.schemas() if f["function"]["name"] == "set_layout"))


def test_bare_view_from_the_url_and_tools_note():
    s = make_session(query={"view": "bare"})
    assert s.layout["view"] == "bare"
    t = s.tools[0]
    res = s.tool_controller.focus_tool(t.name)
    assert res["ok"] and "bare view shows no tools" in res["note"]
    # revealing the participant's preferences never leaves the bare view
    s.start()
    s.wait_for_turn()
    assert s.layout["view"] == "bare"


def test_study_sets_and_locks_the_view(hani2_home):
    projects.create_project("P")
    projects.create_study("P/notools")
    _write(projects.study_dir(projects.StudyRef("P", "notools")) / "env.json",
           {"interface": {"view": "bare", "view_locked": True}})
    s = make_session(study="P/notools")
    assert s.layout["view"] == "bare"
    snap = s.snapshot()
    assert snap["layout"].get("locked") is True
    assert snap["interface"]["participant_settings"]["layout_view"] is False
    # neither the participant nor the Assistant can leave it
    _dispatch(s, {"type": "layout", "view": "full"})
    assert s.layout["view"] == "bare"
    res = s.support_agent.dispatcher.execute("set_layout", {"view": "full"})
    assert not res["ok"] and "fixes the view" in res["error"]
    assert s.layout["view"] == "bare"
    # an administrator can
    a = make_session(study="P/notools", is_admin=True)
    assert a.set_layout(view="full")["ok"] and a.layout["view"] == "full"
    # a study that only sets the start view leaves it switchable
    projects.create_study("P/startbare")
    _write(projects.study_dir(projects.StudyRef("P", "startbare")) / "env.json", {"interface": {"view": "bare"}})
    o = make_session(study="P/startbare")
    assert o.layout["view"] == "bare" and o.set_layout(view="simple")["ok"]


# --------------------------------------------------------------------------- #
# How offers read                                                              #
# --------------------------------------------------------------------------- #
def _offer_then_override(s):
    s.start()
    s.wait_for_turn()
    names = [i.name for i in s.issues]
    return names


def test_offer_display_overrides_rewrite_the_history_and_reset():
    s = make_session()
    names = _offer_then_override(s)
    d = s.support_agent.dispatcher
    tpl = " / ".join("<{%s}>" % n for n in names)
    res = d.execute("set_offer_display", {"offer_template": tpl, "offer_display": "text"})
    assert res["ok"], res
    offers = [h for h in s.history if h.get("kind") == "offer"]
    assert offers and all(h["offer_str"].startswith("<") for h in offers)
    assert s.prefs["offer_display"] == "text"
    snap = s.snapshot()
    assert snap["display_overrides"]["offer_template"] == tpl
    # value labels reach the editor's labels (issues_spec)
    first = s.issues[0]
    v = list(first.all)[0] if hasattr(first, "all") else first.min_value
    assert d.execute("set_offer_display", {"value_labels": {first.name: {str(v): "VERY FIRST"}}})["ok"]
    spec = next(i for i in s.issues_spec() if i["name"] == first.name)
    assert "VERY FIRST" in json.dumps(spec)
    # reset brings the scenario's own presentation back
    assert d.execute("set_offer_display", {"reset": True})["ok"]
    assert s.display_overrides == {}
    assert not any(h["offer_str"].startswith("<") for h in s.history if h.get("kind") == "offer")


def test_offer_display_validates_its_input():
    s = make_session()
    names = _offer_then_override(s)
    d = s.support_agent.dispatcher
    assert not d.execute("set_offer_display", {"offer_template": "{NoSuchIssue} at {%s}" % names[0]})["ok"]
    assert not d.execute("set_offer_display", {"issue_format": {"NoSuchIssue": "{}"}})["ok"]
    assert not d.execute("set_offer_display", {"issue_format": {names[0]: "{0} {1}"}})["ok"]
    assert not d.execute("set_offer_display", {"issue_widget": {names[0]: "dial"}})["ok"]
    assert not d.execute("set_offer_display", {"offer_display": "cards"})["ok"]
    assert s.display_overrides == {}
    assert d.execute("set_offer_display", {"issue_widget": {names[0]: "select"}})["ok"]
    assert s.issue_widget(names[0]) == "select"


def test_offer_display_and_interface_need_their_capabilities():
    s = make_session(assistant_settings={"capabilities": {"offer_display": False, "interface": False}})
    assert "set_offer_display" not in _names(s) and "set_interface" not in _names(s)
    assert not s.support_agent.set_offer_display(offer_template="x")["ok"]
    assert not s.support_agent.set_interface(prefs={"font_scale": 1.2})["ok"]
    t = make_session()
    assert {"set_offer_display", "set_interface"} <= _names(t)


# --------------------------------------------------------------------------- #
# Display settings and the style sheet                                          #
# --------------------------------------------------------------------------- #
def test_set_interface_changes_prefs_and_css():
    s = make_session()
    d = s.support_agent.dispatcher
    res = d.execute("set_interface", {"prefs": {"font_scale": 1.3, "last_offer_on_top": True, "nonsense": 1},
                                      "custom_css": ":root{--you: 200 40 40}"})
    assert res["ok"] and s.prefs["font_scale"] == 1.3 and s.prefs["last_offer_on_top"] is True
    assert "nonsense" in res["refused"]
    assert s.snapshot()["custom_css"] == ":root{--you: 200 40 40}"
    for bad in ("body{background:url(http://x)}", "@import 'x.css';", "a{color:red !important}",
                "x" * 9000, "</style><script>"):
        r = s.set_interface(custom_css=bad)
        assert "custom_css" in r["refused"]
    assert s.custom_css == ":root{--you: 200 40 40}"
    assert s.set_interface(custom_css="")["ok"] and s.snapshot()["custom_css"] is None
    assert "font_scale" in s.set_interface(prefs={"font_scale": 9})["refused"]


def test_set_interface_respects_what_the_study_fixes(hani2_home):
    projects.create_project("P")
    projects.create_study("P/fixed")
    _write(projects.study_dir(projects.StudyRef("P", "fixed")) / "env.json",
           {"interface": {"participant_settings": {"show_history": False}}})
    s = make_session(study="P/fixed")
    res = s.support_agent.set_interface(prefs={"show_history": False, "font_scale": 1.1})
    assert "show_history" in res["refused"] and s.prefs["show_history"] is True
    assert s.prefs["font_scale"] == 1.1
