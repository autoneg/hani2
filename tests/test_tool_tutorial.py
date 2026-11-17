"""Tool help, easy registration, LLM tools and the support agent's access to tools."""

import time
from pathlib import Path

import pytest
from conftest import write_settings

from hani2.testing import make_session
from hani2.tools import LLMTool, Tool, register_tool, ui
from hani2.tools import registry


def _fake_llm(monkeypatch, reply="- **Price** is still open"):
    calls = []

    def complete(prompt, *, system=None, **kw):
        calls.append({"prompt": prompt, "system": system})
        return reply

    monkeypatch.setattr("hani2.llm_service.complete", complete)
    return calls


def _wait(cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


# -- help ------------------------------------------------------------------
def test_every_builtin_and_example_tool_has_help():
    import ask_ai
    import concession_tracker
    import negotiation_summary
    import offer_counter
    import what_if

    classes = registry.builtin_tool_classes() + [
        offer_counter.OfferCounter, what_if.WhatIf, concession_tracker.ConcessionTracker,
        negotiation_summary.NegotiationSummary, ask_ai.AskAI,
    ]
    for cls in classes:
        assert cls.description, cls
        assert len(cls.help.strip()) > len(cls.description), f"{cls.name} needs a help text"
        assert not cls.help_text().startswith(" "), "help_text() is dedented"


def test_help_falls_back_to_description_and_reaches_the_browser():
    class Plain(Tool):
        name = "Plain"
        description = "Only a description."

    assert Plain.help_text() == "Only a description."
    s = make_session()
    prefs = next(t for t in s.snapshot()["tools"] if t["name"] == "Preferences")
    assert "weighted sum" in prefs["help"]


# -- registration ----------------------------------------------------------
HELLO = '''
from hani2.tools import Tool, ui

class _Helper(Tool):
    pass

class Base(Tool):
    abstract = True

class Hello(Tool):
    name = "Hello"
    description = "Says hello."
    help = "Shows a greeting."
    pane = "side"
    timing = "load"
    def view(self):
        return [ui.markdown("Hello VERSION")]
'''


def test_tools_folder_is_loaded_and_reloaded(hani2_home):
    folder = hani2_home / "tools"
    folder.mkdir(parents=True)
    f = folder / "hello.py"
    f.write_text(HELLO.replace("VERSION", "one"))
    s = make_session()
    tool = s.tool_controller.find("Hello")
    assert tool is not None and s.tool_state(tool)["pane"] == "side"
    assert "Base" not in [t.name for t in s.tools] and "_Helper" not in [t.name for t in s.tools]
    assert tool.render()[0]["text"] == "Hello one"
    assert registry.SOURCES[type(tool)] == str(f)
    # an edited file is picked up by the next session, without a restart
    f.write_text(HELLO.replace("VERSION", "two"))
    import os
    os.utime(f, (time.time() + 5, time.time() + 5))
    s2 = make_session()
    assert s2.tool_controller.find("Hello").render()[0]["text"] == "Hello two"


def test_tools_env_var_paths_and_file_specs(hani2_home, tmp_path, monkeypatch):
    other = tmp_path / "mine"
    other.mkdir()
    (other / "hello.py").write_text(HELLO.replace("VERSION", "env"))
    # --tools / HANI2_TOOLS mixes folders and classes, separated by commas
    monkeypatch.setenv("HANI2_TOOLS", f"{other},{Path(__file__).parents[1] / 'examples/tools/offer_counter.py'}:OfferCounter")
    assert registry.tool_paths()[-1] == other
    s = make_session()
    assert s.tool_controller.find("Hello") is not None
    assert "Offer Counter" in {c.name for c in registry.discover_tool_classes()}
    monkeypatch.delenv("HANI2_TOOLS")
    assert registry.import_tool(f"{other / 'hello.py'}:Hello").name == "Hello"
    # a folder in tools.extra (what `experiment create --tools DIR` writes) works too
    write_settings(hani2_home, "env.json", {"tools": {"extra": [str(other)]}})
    assert other in registry.tool_paths()
    assert make_session().tool_controller.find("Hello") is not None


def test_broken_tool_file_does_not_break_sessions(hani2_home, capsys):
    folder = hani2_home / "tools"
    folder.mkdir(parents=True)
    (folder / "broken.py").write_text("raise RuntimeError('boom')\n")
    s = make_session()
    assert s.tool_controller.find("Preferences") is not None
    assert "could not load tools from" in capsys.readouterr().out


def test_register_tool_decorator(monkeypatch):
    monkeypatch.setattr(registry, "_REGISTERED", [])

    @register_tool
    class Decorated(Tool):
        name = "Decorated"
        timing = "load"

    s = make_session()
    assert s.tool_controller.find("Decorated") is not None
    with pytest.raises(TypeError):
        register_tool(object)


def test_cli_tools_new_creates_a_loadable_tool(hani2_home):
    from typer.testing import CliRunner

    from hani2.cli import app

    r = CliRunner().invoke(app, ["tools", "new", "Deal Summary", "--llm"])
    assert r.exit_code == 0, r.output
    path = hani2_home / "tools" / "deal_summary.py"
    assert path.exists()
    (cls,) = registry.load_tool_file(path)
    assert issubclass(cls, LLMTool) and cls.name == "Deal Summary" and cls.help
    r = CliRunner().invoke(app, ["tools", "list"])
    assert "Deal Summary" in r.output and str(path) in r.output


# -- LLM tools -------------------------------------------------------------
def test_negotiation_summary_asks_the_llm(monkeypatch):
    from negotiation_summary import NegotiationSummary

    calls = _fake_llm(monkeypatch)
    s = make_session()
    s.start()
    s.wait_for_turn()
    tool = NegotiationSummary(s.ss)
    tool.on_action("ask", {})
    assert _wait(lambda: not tool.busy)
    assert tool.answer == "- **Price** is still open"
    prompt = calls[0]["prompt"]
    assert "Summarise the negotiation" in prompt and "Partner:" in prompt and s.issues[0].name in prompt
    assert any(c.get("type") == "card" for c in tool.render())


def test_llm_errors_are_shown(monkeypatch):
    from negotiation_summary import NegotiationSummary

    def boom(prompt, **kw):
        raise RuntimeError("no model")

    monkeypatch.setattr("hani2.llm_service.complete", boom)
    s = make_session()
    s.start()
    s.wait_for_turn()
    tool = NegotiationSummary(s.ss)
    tool.run()
    assert _wait(lambda: not tool.busy)
    assert "no model" in tool.error
    assert any(c["type"] == "alert" and "no model" in c["text"] for c in tool.render())


def test_ask_ai_needs_a_question(monkeypatch):
    from ask_ai import AskAI

    calls = _fake_llm(monkeypatch, "Price matters most.")
    s = make_session()
    s.start()
    s.wait_for_turn()
    tool = AskAI(s.ss)
    tool.on_action("ask", {"question": "  "})
    assert tool.error == "Type a question first." and not calls
    tool.on_action("ask", {"question": "What matters most?"})
    assert _wait(lambda: tool.answer == "Price matters most.")
    assert "What matters most?" in calls[0]["prompt"] and "preferences" in calls[0]["prompt"]


# -- the support agent -----------------------------------------------------
def _session_with_summary(monkeypatch, **kw):
    import negotiation_summary

    monkeypatch.setattr(registry, "_REGISTERED", [negotiation_summary.NegotiationSummary])
    s = make_session(**kw)
    s.start()
    s.wait_for_turn()
    # scenarios are random: make sure the selector lists outcomes
    s.tool_controller.find("Utility-based Selector").values.update(min_util=0, width=100)
    return s


def test_agent_reads_tool_help(monkeypatch):
    s = _session_with_summary(monkeypatch)
    agent = s.support_agent
    read = agent.dispatcher.execute("read_tool", {"name": "Summary"})
    assert read["ok"] and "language model" in read["text"]  # the help text heads what the agent reads
    sel = agent.read_tool("Utility-based Selector")["text"]
    assert "Utility-based Selector" in sel and "min_util" in sel
    # a switched-off tool cannot be read, but the agent still gets its help
    s.tool_controller.set_tool_enabled("Summary", False)
    off = agent.read_tool("Summary")
    assert not off["ok"] and "language model" in off["help"]


def test_agent_uses_an_llm_tool(monkeypatch, scripted):
    _fake_llm(monkeypatch, "Both sides are far apart.")
    s = _session_with_summary(monkeypatch)
    s.play_counters(1)
    s.wait_for_turn()
    res = s.support_agent.use_tool("Summary", action="ask")
    # use_tool waits for the background call, so the agent reads the answer, not "Thinking..."
    assert res["ok"] and "Both sides are far apart." in res["text"]
    summary = s.tool_controller.find("Summary")
    summary.answer = None
    # and through the LLM function
    llm = scripted(("use_tool", {"name": "Summary", "action": "ask"}), "done")
    s.user_chat("summarise the negotiation")
    assert _wait(lambda: summary.answer == "Both sides are far apart.")
    assert "use_tool" in llm.calls[0]["tools"]
