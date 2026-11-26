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
    s = make_session(query={"view": "full"})
    prefs = next(t for t in s.tools if t.name == "Preferences")
    st = s.tool_state(prefs)
    st["visible"] = False
    others = [t.name for t in s.tools if s.tool_state(t)["pane"] == st["pane"] and t.name != "Preferences"]
    if others:
        s.active_tabs[st["pane"]] = others[0]
    s.set_layout(collapsed=["tools"])
    s.start()
    assert st["visible"]
    assert s.active_tabs[st["pane"]] == "Preferences" and s.active_tabs["all"] == "Preferences"
    assert s.layout["view"] == "full" and "tools" not in s.layout["collapsed"]
    snap = s.snapshot()
    assert snap["reveal"]["tool"] == "Preferences" and not snap["reveal"]["popup"]
    s.end()


def test_focus_view_reveals_the_preferences_in_the_popup(hani2_home):
    s = make_session()
    s.set_layout(view="focus")
    s.start()
    assert s.layout["view"] == "focus"  # the view is kept
    assert s.active_tabs["popup"] == "Preferences" and "Preferences" in s.shown_tool_names()
    reveal = s.snapshot()["reveal"]
    assert reveal["tool"] == "Preferences" and reveal["popup"]
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
    f.write_text(AGENT_FILE, encoding="utf-8")
    monkeypatch.setenv("HANI2_SUPPORT_AGENT", "on")
    monkeypatch.setenv("HANI2_SUPPORT_AGENT_CLASS", f"{f}:Mine")
    s = make_session()
    assert type(s.support_agent).__name__ == "Mine"


def test_experiment_create_with_support_agent_class(hani2_home, tmp_path, monkeypatch):
    import json

    from hani2.cli import app

    f = tmp_path / "mine.py"
    f.write_text(AGENT_FILE, encoding="utf-8")
    monkeypatch.setenv("HANI2_EXPERIMENTS", str(tmp_path / "exps"))
    r = CliRunner().invoke(app, ["experiment", "create", "hi", "--assistant", f"{f}:Mine"])
    assert r.exit_code == 0, r.output
    sa = json.loads((tmp_path / "exps" / "hi" / "assistant_settings.json").read_text(encoding="utf-8"))
    assert sa == {"mode": "on", "agent_class": f"{f.resolve()}:Mine"}
    r = CliRunner().invoke(app, ["experiment", "create", "han", "--no-assistant"])
    assert r.exit_code == 0, r.output
    assert json.loads((tmp_path / "exps" / "han" / "assistant_settings.json").read_text(encoding="utf-8")) == {"mode": "off"}
    r = CliRunner().invoke(app, ["experiment", "create", "bad", "--assistant", "nope.module:Missing"])
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


def test_opponents_from_the_command_line_and_old_names(hani2_home, monkeypatch):
    from hani2.session import NegotiationSession

    monkeypatch.setenv("HANI2_OPPONENTS", "ConcederTBNegotiator")
    s = NegotiationSession("o1", "alice")
    assert [str(x).split(".")[-1] for x in s.opponent_pool()] == ["ConcederTBNegotiator"]
    monkeypatch.delenv("HANI2_OPPONENTS")
    monkeypatch.setenv("HANI2_AGENTS", "BoulwareTBNegotiator")  # old name still works
    assert [str(x).split(".")[-1] for x in NegotiationSession("o2", "alice").opponent_pool()] == ["BoulwareTBNegotiator"]
    s = NegotiationSession("o3", "alice", is_admin=True, query={"opponents": "AspirationNegotiator"})
    assert [str(x).split(".")[-1] for x in s.opponent_pool()] == ["AspirationNegotiator"]
    # a non-admin's ?opponents= is ignored; ?group= still works
    s = NegotiationSession("o4", "alice", query={"opponents": "AspirationNegotiator"})
    assert "AspirationNegotiator" not in [str(x).split(".")[-1] for x in s.opponent_pool()]
    s = NegotiationSession("o5", "alice", query={"group": ":template"})
    assert s.opponent_pool() and s.opponent_group == "template"


def test_old_admin_pref_names_map_to_opponent_names(hani2_home):
    s = make_session(is_admin=True)
    assert s.set_pref("partner_types", ["BoulwareTBNegotiator"])
    assert s.admin_prefs["opponent_types"] == ["BoulwareTBNegotiator"]
    assert s.set_pref("show_opponent_type", True)


def test_cli_opponents_option(hani2_home, tmp_path, monkeypatch):
    import json

    from hani2 import cli

    served = {}
    monkeypatch.setattr(cli, "_serve", lambda *a, **k: served.setdefault("ok", True))
    r = CliRunner().invoke(cli.app, ["--opponents", "BoulwareTBNegotiator,:template", "--no-browser"])
    assert r.exit_code == 0, r.output
    import os

    assert os.environ["HANI2_OPPONENTS"] == "BoulwareTBNegotiator,:template" and served
    r = CliRunner().invoke(cli.app, ["--agents", "ConcederTBNegotiator", "--no-browser"])
    assert r.exit_code == 0 and os.environ["HANI2_OPPONENTS"] == "ConcederTBNegotiator"
    monkeypatch.setenv("HANI2_EXPERIMENTS", str(tmp_path / "exps"))
    r = CliRunner().invoke(cli.app, ["experiment", "create", "han", "--no-support-agent", "--opponents", "BoulwareTBNegotiator"])
    assert r.exit_code == 0, r.output
    env = json.loads((tmp_path / "exps" / "han" / "env.json").read_text(encoding="utf-8"))
    assert env["opponents"] == ["BoulwareTBNegotiator"]
    os.environ.pop("HANI2_OPPONENTS", None)


def test_only_shown_tools_are_rendered(hani2_home):
    from hani2.hub import Hub

    s = make_session()
    shown = s.shown_tool_names()
    assert shown
    front = next(t for t in s.tools if t.name in shown)
    hidden = [t for t in s.tools if t.name not in shown]
    assert hidden, "expected some tools behind inactive tabs"
    hub = Hub()  # no event loop: tool_changed only records what it would render
    hub.sessions[s.sid] = s
    hid = s.tool_state(hidden[0])["id"]
    hub.tool_changed(s.sid, hid)
    assert hid not in hub._tools_pending.get(s.sid, set())
    pid = s.tool_state(front)["id"]
    hub.tool_changed(s.sid, pid)
    assert pid in hub._tools_pending[s.sid]
    # opening the hidden tool's tab makes it renderable
    s.active_tabs[s.tool_state(hidden[0])["pane"]] = hidden[0].name
    hub.tool_changed(s.sid, hid)
    assert hid in hub._tools_pending[s.sid]
    # a tool being rendered is queued for one more render, not rendered twice at once
    s.active_tabs["max"] = front.name  # keep the first tool on screen (enlarged)
    hub._tools_pending[s.sid].discard(pid)
    hub._tools_rendering.add((s.sid, pid))
    hub.tool_changed(s.sid, pid)
    assert (s.sid, pid) in hub._tools_again and pid not in hub._tools_pending[s.sid]


def test_write_table_to_stdout_keeps_stdout_open(capsys):
    import sys
    from pathlib import Path

    from hani2.cli import _write_table

    _write_table([{"a": 1}], ["a"], Path("-"))
    print("still open")
    assert not sys.stdout.closed
    assert "still open" in capsys.readouterr().out


def test_python_m_cli_has_every_command():
    import subprocess
    import sys

    r = subprocess.run([sys.executable, "-m", "hani2.cli", "scheduling", "--help"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
