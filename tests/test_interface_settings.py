"""What participants may adjust, per layer; start-time overrides; pinned messages; notifications;
how the Assistant appears."""

import json

import pytest
from typer.testing import CliRunner

from hani2 import projects
from hani2.config import OVERRIDES_ENV_VAR, get_env, load_env, read_overrides_file
from hani2.server import _dispatch
from hani2.testing import make_session


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def layered(hani2_home, tmp_path, monkeypatch):
    """time_limit set at every level: settings 100 < overrides 200 < project 300 < study 400."""
    _write(hani2_home / "settings" / "env.json", {"negotiation": {"time_limit": 100, "n_steps": 11, "step_time_limit": 10}})
    ov = tmp_path / "overrides.yaml"
    ov.write_text("negotiation:\n  time_limit: 200\n  n_steps: 22\n  step_time_limit: 20\nassistant:\n  autonomy: semi\n", encoding="utf-8")
    monkeypatch.setenv(OVERRIDES_ENV_VAR, str(ov))
    projects.create_project("P")
    projects.create_study("P/s1")
    projects.create_study("P/s2")
    _write(projects.project_dir("P") / "env.json", {"negotiation": {"time_limit": 300, "step_time_limit": 30}})
    _write(projects.study_dir(projects.StudyRef("P", "s1")) / "env.json", {"negotiation": {"time_limit": 400, "step_time_limit": 40}})
    return ov


def test_overrides_file_maps_kinds_and_env_keys(tmp_path):
    f = tmp_path / "o.yaml"
    f.write_text("interface:\n  notifications: {toast_seconds: 2}\nassistant: {autonomy: suggest}\nmodels: {default: ['ollama:x']}\n", encoding="utf-8")
    out = read_overrides_file(f)
    assert out["env.json"] == {"interface": {"notifications": {"toast_seconds": 2}}}
    assert out["assistant_settings.json"] == {"autonomy": "suggest"}
    assert out["models.json"] == {"default": ["ollama:x"]}
    f.write_text("- not a mapping\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_overrides_file(f)


def test_precedence_settings_overrides_project_study(layered):
    from hani2.support_agent.settings import load_assistant_settings

    with projects.use_study(None):
        assert get_env("negotiation.time_limit") == 200  # the overrides beat the settings folder
        assert load_assistant_settings()["autonomy"] == "semi"
    with projects.use_study("P/s2"):
        assert get_env("negotiation.time_limit") == 300  # the project beats the overrides
        assert get_env("negotiation.n_steps") == 22  # … which still beat the settings folder
    with projects.use_study("P/s1"):
        assert get_env("negotiation.time_limit") == 400  # the study beats its project


def test_sessions_see_their_layer(layered):
    # (make_session fixes time_limit and n_steps itself, so look at another setting)
    assert make_session(mode="guest", load=False).admin_prefs["step_time_limit"] == 20
    assert make_session(load=False).admin_prefs["step_time_limit"] == 20
    assert make_session(study="P/s2", load=False).admin_prefs["step_time_limit"] == 30
    assert make_session(study="P/s1", load=False).admin_prefs["step_time_limit"] == 40


def test_bundled_defaults_view_skips_overrides(layered):
    from hani2.config import layer_view

    with projects.use_study(None), layer_view(None, skip_settings=True):
        assert load_env()["negotiation"]["time_limit"] == 300  # the bundled default, nothing else


def test_cli_rejects_a_bad_settings_file(tmp_path, monkeypatch):
    from hani2.cli import app

    bad = tmp_path / "bad.yaml"
    bad.write_text("- 1\n", encoding="utf-8")
    r = CliRunner().invoke(app, ["--settings", str(bad), "--no-browser", "info"])
    assert r.exit_code != 0 and "mapping" in r.output


def test_participant_settings_gate_prefs_layout_and_assistant(hani2_home):
    projects.create_project("P")
    projects.create_study("P/locked")
    _write(projects.study_dir(projects.StudyRef("P", "locked")) / "env.json", {"interface": {
        "participant_settings": {"show_history": False, "layout_view": False, "assistant_autonomy": False},
        "prefs": {"offer_display": "table"}}})
    s = make_session(study="P/locked")
    assert s.prefs["offer_display"] == "table"  # the layer's default
    ui = s.snapshot()["interface"]
    assert ui["participant_settings"]["show_history"] is False and ui["participant_settings"]["font_scale"] is True
    assert not s.set_pref("show_history", False) and s.prefs["show_history"] is True
    assert s.set_pref("font_scale", 1.2)
    view = s.layout["view"]
    _dispatch(s, {"type": "layout", "view": "focus"})
    assert s.layout["view"] == view
    before = s.support_agent.capabilities.user_autonomy
    _dispatch(s, {"type": "support", "op": "autonomy", "value": "suggest"})
    assert s.support_agent.capabilities.user_autonomy == before
    # the same study, an administrator: everything, with the hidden ones listed
    a = make_session(study="P/locked", is_admin=True)
    assert all(a.snapshot()["interface"]["participant_settings"].values())
    assert "show_history" in a.snapshot()["interface"]["hidden_from_participants"]
    assert a.set_pref("show_history", False)
    # another study of the project is not affected
    projects.create_study("P/open")
    assert make_session(study="P/open").set_pref("show_history", False)


def test_moving_tools_can_be_switched_off_per_study(hani2_home):
    projects.create_project("P")
    projects.create_study("P/fixed")
    _write(projects.study_dir(projects.StudyRef("P", "fixed")) / "env.json", {"negotiation": {"allow_moving_tools": False}})
    s = make_session(study="P/fixed")
    t = s.tools[0]
    pane = s.tool_state(t)["pane"]
    other = next(p for p in ("upper", "lower", "side") if p != pane)
    assert s.snapshot()["interface"]["move_tools"] is False
    _dispatch(s, {"type": "tool_layout", "op": "move", "name": t.name, "pane": other})
    assert s.tool_state(t)["pane"] == pane
    s2 = make_session()
    t2 = s2.tools[0]
    pane2 = s2.tool_state(t2)["pane"]
    other2 = next(p for p in ("upper", "lower", "side") if p != pane2)
    _dispatch(s2, {"type": "tool_layout", "op": "move", "name": t2.name, "pane": other2})
    assert s2.tool_state(t2)["pane"] == other2


def test_assistant_pins_messages_and_the_human_dismisses_them():
    s = make_session()
    d = s.support_agent.dispatcher
    assert {"pin_message", "unpin_message"} <= {sc["function"]["name"] for sc in d.schemas()}
    r = d.execute("pin_message", {"text": "**Deadline** in 2 minutes", "position": "top", "id": "deadline"})
    assert r["ok"] and r["id"] == "deadline"
    d.execute("pin_message", {"text": "Keep this", "position": "bottom", "id": "keep", "dismissible": False})
    d.execute("pin_message", {"text": "Deadline in 1 minute", "position": "top", "id": "deadline"})  # replaces
    pins = s.snapshot()["pins"]
    assert [(p["id"], p["position"]) for p in pins] == [("deadline", "top"), ("keep", "bottom")]
    assert pins[0]["text"] == "Deadline in 1 minute"
    assert not d.execute("pin_message", {"text": "x", "position": "left"})["ok"]
    _dispatch(s, {"type": "unpin", "id": "keep"})  # not dismissible
    _dispatch(s, {"type": "unpin", "id": "deadline"})
    assert [p["id"] for p in s.pins] == ["keep"]
    assert d.execute("unpin_message", {})["ok"] and s.pins == []
    s.support_agent.capabilities.set_user_capability("pin", False)
    assert "pin_message" not in {sc["function"]["name"] for sc in d.schemas()}
    assert not s.support_agent.pin_message("x")["ok"]


def test_pins_are_cleared_with_a_new_scenario():
    s = make_session()
    s.pin("hello")
    s.load()
    assert s.pins == []


def test_notifications_are_kept_for_the_notification_list():
    s = make_session()
    s.support_agent.toast("Watch the price", "warning")
    s.toast("Saved")
    notes = s.snapshot()["notifications"]
    assert [(n["message"], n["source"], n["level"]) for n in notes[-2:]] == [
        ("Watch the price", "assistant", "warning"), ("Saved", "system", "info")]
    toasts = s.hub.of_type("toast")
    assert toasts[-2]["source"] == "assistant" and toasts[-1]["id"] == notes[-1]["id"]
    _dispatch(s, {"type": "clear_notifications"})
    assert s.snapshot()["notifications"] == []


def test_toast_duration_comes_from_the_layer(hani2_home):
    _write(hani2_home / "settings" / "env.json", {"interface": {"notifications": {"toast_seconds": 2.5, "center": False}}})
    ui = make_session().snapshot()["interface"]
    assert ui["toast_ms"] == 2500 and ui["notification_center"] is False


def test_assistant_presentation_panel_persona_or_choice():
    s = make_session()
    assert s.snapshot()["interface"]["assistant"] == {"style": "panel", "choice": False, "movable": True}
    assert not s.set_pref("assistant_presentation", "persona")  # the admin did not offer a choice
    p = make_session(assistant_settings={"presentation": {"style": "persona", "persona_movable": False}})
    assert p.snapshot()["interface"]["assistant"] == {"style": "persona", "choice": False, "movable": False}
    c = make_session(assistant_settings={"presentation": {"style": "choice", "choice_default": "both"}})
    assert c.snapshot()["interface"]["assistant"]["style"] == "both"
    assert c.set_pref("assistant_presentation", "persona")
    assert c.snapshot()["interface"]["assistant"] == {"style": "persona", "choice": True, "movable": True}
    assert not c.set_pref("assistant_presentation", "sideways")


def test_admin_console_shows_interface_defaults_and_the_overrides_file(layered):
    from fastapi.testclient import TestClient

    from hani2.server import app

    with TestClient(app) as c:
        _admin_checks(c, layered)


def _admin_checks(c, layered):
    assert c.post("/api/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200
    env = c.get("/api/admin/settings/env?layer=settings").json()["effective"]
    assert env["interface"]["participant_settings"]["show_history"] is True
    assert env["negotiation"]["allow_moving_tools"] is True and env["negotiation"]["time_limit"] == 200
    info = c.get("/api/admin/layers").json()
    assert info["overrides"]["path"] == str(layered) and "env.json" in info["overrides"]["files"]
    meta = c.get("/api/admin/meta").json()
    assert "layout_view" in meta["participant_settings"] and "pin" in meta["capabilities"]


def test_a_study_env_json_beats_its_project_yaml(hani2_home):
    projects.create_project("Q", time_limit=111, role_rule="random")
    projects.create_study("Q/a")
    projects.create_study("Q/b", time_limit=333)
    _write(projects.study_dir(projects.StudyRef("Q", "a")) / "env.json", {"negotiation": {"role_rule": "index"}})
    a = make_session(study="Q/a", load=False)
    assert a.admin_prefs["role_rule"] == "index"  # the study's env.json beats project.yaml
    b = make_session(study="Q/b", load=False)
    assert b.admin_prefs["role_rule"] == "random"  # project.yaml beats the settings' defaults
