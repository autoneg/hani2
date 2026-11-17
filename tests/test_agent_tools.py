"""The support agent discovers, reads, uses and adds tools while the session runs."""

import pytest

from hani2.testing import make_session
from hani2.tools.base import Tool
from hani2.tools.describe import controls_of, describe_components
from hani2.tools import ui


def chat(s, text):
    s.user_chat(text)
    s.wait_agent_idle()


class Gadget(Tool):
    name = "Gadget"
    description = "A test gadget."
    agent_hint = "Press go."
    timing = "agent"
    pane = "lower"

    def init(self, session_state):
        self.events = ["init"]

    def scenario_loaded(self, session_state, scenario):
        self.events.append("scenario")

    def negotiation_started(self, session_state, nmi):
        self.events.append("started")

    def view(self):
        return [ui.stat("Presses", self.values.get("n", 0)), ui.slider("level", 0, 10, self.values.get("level", 3)),
                ui.button("Go", "go")]

    def on_action(self, action, payload):
        if action == "go":
            self.values["n"] = self.values.get("n", 0) + 1
            self.set_offer(self.scenario.outcome_space.random_outcome())


def test_describe_components_text_and_controls():
    comps = [ui.card(ui.stat("Utility", 0.5), ui.select("issue", ["a", "b"], "a", label="Issue"),
                     ui.table([{"x": 1}, {"x": 2}], on_select="pick"), ui.button("Go", "go"), title="Box")]
    text = describe_components(comps)
    assert "Utility: 0.5" in text and "Input 'issue'" in text and "options: a, b" in text
    assert "Table (2 rows)" in text and "action='pick'" in text and "Button 'Go'" in text
    c = controls_of(comps)
    assert set(c["inputs"]) == {"issue"} and set(c["actions"]) == {"go"} and set(c["tables"]) == {"pick"}
    assert len(describe_components([ui.markdown("x" * 10000)], max_chars=500)) <= 500


def test_level10_adds_its_tool_and_uses_the_selector():
    s = make_session(agent_class="level10_toolsmith:ToolsmithAgent")
    assert "Deal Compass" not in [t.name for t in s.tools]  # timing "agent": not added on its own
    s.start()
    s.wait_for_turn()
    s.wait_agent_idle()
    assert s.wait(lambda: any(t.name == "Deal Compass" for t in s.tools), 15)
    compass = next(t for t in s.tools if t.name == "Deal Compass")
    assert s.tool_state(compass)["added_by"] and s.snapshot()["tools"][-1]["added_by"]
    selector = next(t for t in s.tools if t.name == "Utility-based Selector")
    assert s.wait(lambda: selector.values.get("selected") == 0, 15)  # the agent reacts in the background
    assert s.draft and s.utility(s.draft_outcome()) is not None


def test_agent_reads_uses_adds_and_removes_tools(hani2_home):
    s = make_session(support_settings={"autonomy": "suggest"})
    sa = s.support_agent
    sa.tools = [Gadget]
    s.start()
    s.wait_for_turn()
    assert "Gadget" in [t["name"] for t in sa.available_tools()]
    assert sa.add_tool("Gadget", focus=True)["ok"]
    g = next(t for t in s.tools if t.name == "Gadget")
    assert g.events == ["init", "scenario", "started"]  # caught up with the round
    assert s.active_tabs["lower"] == "Gadget"
    read = sa.read_tool("Gadget")
    assert read["ok"] and "Press go." in read["text"] and "Input 'level'" in read["text"]
    res = sa.use_tool("Gadget", inputs={"level": 7}, action="go")
    assert res["ok"] and g.values["level"] == 7 and g.values["n"] == 1 and s.draft
    assert not sa.use_tool("Gadget", action="explode")["ok"]
    assert not sa.use_tool("Gadget", inputs={"nope": 1})["ok"]
    assert sa.add_tool("Gadget")["ok"]  # adding again just shows it
    assert len([t for t in s.tools if t.name == "Gadget"]) == 1
    assert not s.remove_tool("Preferences")["ok"]  # built-in tools can only be hidden
    assert sa.remove_tool("Gadget")["ok"] and "Gadget" not in [t.name for t in s.tools]
    s.end()


def test_agent_cannot_add_private_or_unknown_tools(hani2_home):
    s = make_session()
    sa = s.support_agent
    names = {t["name"] for t in sa.available_tools()}
    assert "Opponent Preferences" not in names and "Negotiation Plot" not in names  # admin-only
    assert not sa.add_tool("Opponent Preferences")["ok"]
    assert not sa.add_tool("os:system")["ok"]  # strings are names from the toolbox, never import paths


def test_tool_use_obeys_the_agents_capabilities(hani2_home):
    from hani2.support_agent.settings import DEFAULT_CAPABILITIES

    s = make_session(support_settings={"capabilities": {**DEFAULT_CAPABILITIES, "fill_offer": False}})
    sa = s.support_agent
    sa.tools = [Gadget]
    s.start()
    s.wait_for_turn()
    before = dict(s.draft)
    assert sa.add_tool("Gadget")["ok"]
    sa.use_tool("Gadget", action="go")
    assert s.draft == before  # the tool's set_offer was refused for the agent
    # the participant pressing the same button still works
    g = next(t for t in s.tools if t.name == "Gadget")
    g.on_action("go", {})
    assert s.draft != before
    s.end()


def test_capabilities_switch_off_tool_functions(hani2_home):
    s = make_session(support_settings={"capabilities": {"tool_add": False, "tool_use": False}})
    sa = s.support_agent
    assert not sa.read_tool("Preferences")["ok"]
    assert not sa.add_tool("Trace")["ok"]
    names = [f["function"]["name"] for f in sa.dispatcher.schemas()] if hasattr(sa.dispatcher, "schemas") else []
    assert "use_tool" not in names and "add_tool" not in names


def test_llm_agent_discovers_and_uses_tools(scripted, hani2_home):
    s = make_session(support_settings={"autonomy": "suggest"})
    s.support_agent.tools = [Gadget]
    s.start()
    s.wait_for_turn()
    llm = scripted(
        ("list_tools", {}),
        ("add_tool", {"name": "Gadget"}),
        ("read_tool", {"name": "Gadget"}),
        ("use_tool", {"name": "Gadget", "inputs": {"level": 9}, "action": "go"}),
        "I used the Gadget.",
    )
    chat(s, "use your tools")
    for fn in ("list_tools", "read_tool", "use_tool", "add_tool"):
        assert fn in llm.calls[0]["tools"]
    g = next(t for t in s.tools if t.name == "Gadget")
    assert g.values["level"] == 9 and g.values["n"] == 1
    tool_msgs = [m for m in s.support_agent.messages if m.get("role") == "tool"]
    assert any("can_add" in m["content"] and "Gadget" in m["content"] for m in tool_msgs)
    assert any("Press go." in m["content"] for m in tool_msgs)
    assert s.chat[-1]["text"] == "I used the Gadget."
    s.end()


def test_cli_tools_option_registers_agent_only_tools(hani2_home, tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from hani2 import cli

    f = tmp_path / "team_tools.py"
    f.write_text(
        "from hani2.tools.base import Tool\n"
        "from hani2.tools import ui\n"
        "class TeamTool(Tool):\n"
        "    name = 'Team Tool'\n"
        "    timing = 'agent'\n"
        "    def view(self):\n"
        "        return [ui.markdown('hello')]\n"
    )
    monkeypatch.setattr(cli, "_serve", lambda *a, **k: None)
    r = CliRunner().invoke(cli.app, ["--tools", f"{f}:TeamTool", "--no-browser"])
    assert r.exit_code == 0, r.output
    s = make_session()
    s.start()
    assert "Team Tool" not in [t.name for t in s.tools]
    assert "Team Tool" in [t["name"] for t in s.support_agent.available_tools()]
    assert s.support_agent.add_tool("Team Tool")["ok"]
    assert "hello" in s.support_agent.read_tool("Team Tool")["text"]
    s.end()
    r = CliRunner().invoke(cli.app, ["--tools", "nope.module:Missing", "--no-browser"])
    assert r.exit_code != 0
    import os

    os.environ.pop("HANI2_TOOLS", None)


@pytest.mark.parametrize("cap", ["tool_add", "tool_use"])
def test_new_capabilities_are_described(cap):
    from hani2.support_agent.capabilities import CAPABILITY_INFO, Capability
    from hani2.support_agent.settings import DEFAULT_CAPABILITIES

    assert Capability(cap) and cap in CAPABILITY_INFO and DEFAULT_CAPABILITIES[cap] is True


def test_tools_are_not_added_twice(hani2_home):
    s = make_session()
    sa = s.support_agent
    assert "Trace" not in [t.name for t in s.tools]  # appears at start
    assert sa.add_tool("Trace")["ok"]
    s.start()
    s.wait_for_turn()
    assert [t.name for t in s.tools].count("Trace") == 1
    s.end()


def test_list_tools_with_only_tool_use(hani2_home):
    caps = {k: False for k in ("tool_enable", "tool_visibility", "tool_order", "tool_add")}
    from hani2.support_agent.settings import DEFAULT_CAPABILITIES

    s = make_session(support_settings={"capabilities": {**DEFAULT_CAPABILITIES, **caps}})
    names = [f["function"]["name"] for f in s.support_agent.dispatcher.schemas()]
    assert "list_tools" in names and "read_tool" in names and "add_tool" not in names


class Revealer(Tool):
    name = "Revealer"
    timing = "agent"

    def view(self):
        if not self.values.get("show"):
            return [ui.checkbox("show", False, label="Show options")]
        return [ui.checkbox("show", True), ui.table([{"x": 1}, {"x": 2}], on_select="pick")]

    def on_action(self, action, payload):
        self.values["picked"] = payload["index"]


def test_use_tool_checks_actions_after_applying_inputs(hani2_home):
    s = make_session()
    sa = s.support_agent
    sa.tools = [Revealer]
    assert sa.add_tool("Revealer")["ok"]
    res = sa.use_tool("Revealer", inputs={"show": "true"}, action="pick", row=1)
    assert res["ok"], res
    assert next(t for t in s.tools if t.name == "Revealer").values["picked"] == 1
