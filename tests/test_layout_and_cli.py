"""Divider sizes, revealing the participant's preferences, and choosing the support agent from the CLI."""

import pytest
from typer.testing import CliRunner

from hani2.support_agent.settings import parse_support_agent_choice
from hani2.testing import make_session


def test_sizes_are_sanitised(hani2_home):
    s = make_session()
    res = s.set_layout(sizes={"tools": 0.4, "dock": "0.5", "bad": "x", "huge": 3, "nan": float("nan")})
    assert res["ok"]
    assert s.layout["sizes"] == {"tools": 0.4, "dock": 0.5}
    assert not s.set_layout(sizes=[1, 2])["ok"]


def test_own_preferences_are_revealed_on_start(hani2_home):
    s = make_session()
    prefs = next(t for t in s.tools if t.name == "Preferences")
    st = s.tool_state(prefs)
    st["visible"] = False
    others = [t.name for t in s.tools if s.tool_state(t)["pane"] == st["pane"] and t.name != "Preferences"]
    if others:
        s.active_tabs[st["pane"]] = others[0]
    s.set_layout(view="focus", collapsed=["tools"])
    s.start()
    assert st["visible"]
    assert s.active_tabs[st["pane"]] == "Preferences" and s.active_tabs["all"] == "Preferences"
    assert s.layout["view"] == "full" and "tools" not in s.layout["collapsed"]
    snap = s.snapshot()
    assert snap["reveal"]["tool"] == "Preferences"
    s.end()


@pytest.mark.parametrize(
    "value,expected",
    [("on", ("on", None)), ("OFF", ("off", None)), ("admins", ("auto", None)),
     ("mypkg.agents:Mine", ("on", "mypkg.agents:Mine")), ("agents/mine.py:Mine", ("on", "agents/mine.py:Mine"))],
)
def test_parse_support_agent_choice(value, expected):
    assert parse_support_agent_choice(value) == expected


def test_parse_support_agent_choice_rejects_junk():
    with pytest.raises(ValueError):
        parse_support_agent_choice("maybe")


AGENT_FILE = '''
from hani2.support_agent import SupportAgent

class Mine(SupportAgent):
    pass
'''


def test_support_agent_class_from_file(hani2_home, tmp_path, monkeypatch):
    f = tmp_path / "mine.py"
    f.write_text(AGENT_FILE)
    monkeypatch.setenv("HANI2_SUPPORT_AGENT", "on")
    monkeypatch.setenv("HANI2_SUPPORT_AGENT_CLASS", f"{f}:Mine")
    s = make_session()
    assert type(s.support_agent).__name__ == "Mine"


def test_experiment_create_with_support_agent_class(hani2_home, tmp_path, monkeypatch):
    import json

    from hani2.cli import app

    f = tmp_path / "mine.py"
    f.write_text(AGENT_FILE)
    monkeypatch.setenv("HANI2_EXPERIMENTS", str(tmp_path / "exps"))
    r = CliRunner().invoke(app, ["experiment", "create", "hi", "--support-agent", f"{f}:Mine"])
    assert r.exit_code == 0, r.output
    sa = json.loads((tmp_path / "exps" / "hi" / "support_agent_settings.json").read_text())
    assert sa == {"mode": "on", "agent_class": f"{f.resolve()}:Mine"}
    r = CliRunner().invoke(app, ["experiment", "create", "han", "--no-support-agent"])
    assert r.exit_code == 0, r.output
    assert json.loads((tmp_path / "exps" / "han" / "support_agent_settings.json").read_text()) == {"mode": "off"}
    r = CliRunner().invoke(app, ["experiment", "create", "bad", "--support-agent", "nope.module:Missing"])
    assert r.exit_code != 0


def test_no_support_agent_driver_without_an_agent(hani2_home):
    from hani2.support_agent.autopilot import SUPPORT_AGENT_DRIVER, driver_options, resolve_driver

    s = make_session(support_settings={"mode": "off"})
    assert s.support_agent is None
    settings = {"allowed": True, "driver": SUPPORT_AGENT_DRIVER, "allowed_drivers": None}
    assert SUPPORT_AGENT_DRIVER not in driver_options(settings, s)
    assert resolve_driver(s, settings) != SUPPORT_AGENT_DRIVER
    only_sa = {"allowed": True, "driver": SUPPORT_AGENT_DRIVER, "allowed_drivers": [SUPPORT_AGENT_DRIVER]}
    assert resolve_driver(s, only_sa) is None
