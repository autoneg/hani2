"""Support agents: the tutorial agents (no LLM) and the built-in LLM agent with a scripted model."""

import threading
import time

from hani2.support_agent import Autonomy, Capability, CapabilityState, SupportAgent
from hani2.testing import make_session


def chat(s, text):
    s.user_chat(text)


def test_level1_echo():
    s = make_session(agent_class="level1_hello:HelloAgent")
    chat(s, "hi there")
    assert s.chat[-1]["text"] == "Hello! You said: hi there"


def test_level2_reads_state():
    s = make_session(agent_class="level2_rules:RulesAgent")
    s.start()
    s.wait_for_turn()
    chat(s, "what now?")
    assert "Opponent offer:" in s.chat[-1]["text"]


def test_bad_agent_class_fails_loudly():
    s = make_session(agent_class="nope.nothing:Missing")
    assert s.support_agent is None and "nope.nothing:Missing" in s.assistant_error


def test_default_agent_class_is_the_built_in_assistant():
    s = make_session(agent_class="")
    assert type(s.support_agent) is SupportAgent and not s.assistant_error


def test_level6_hides_and_reveals_tools():
    s = make_session(agent_class="level6_guided:GuidedAgent")
    s.start()
    s.wait_for_turn()
    s.wait_agent_idle()
    vis = {t.name: s.tool_state(t)["visible"] for t in s.tools}
    assert vis["Utility Plot"] is False and vis["Trace"] is False
    for _ in range(2):
        s.send_counter()
        s.wait_for_turn()
        s.wait_agent_idle()
    vis = {t.name: s.tool_state(t)["visible"] for t in s.tools}
    assert vis["Utility Plot"] is True


def test_level7_ask_user_and_answer():
    s = make_session(agent_class="level7_asking:AskingCoach")
    t = threading.Thread(target=s.support_agent.on_event, args=("negotiation_started",))
    t.start()
    assert s.wait(lambda: s.pending_question is not None, 5)
    assert s.pending_question["options"] == ["Cautious", "Balanced", "Aggressive"]
    s.support_agent._answer_question("Aggressive", echo=True)
    t.join(5)
    assert s.support_agent.style == "Aggressive"
    assert "Aggressive" in s.chat[-1]["text"]


def test_level8_highlight_and_annotate():
    s = make_session(agent_class="level8_spotlight:SpotlightAgent")
    s.start()
    s.wait_for_turn()
    s.wait_agent_idle()
    assert s.highlights and s.highlights[-1]["target"] in ("reject", "accept", "partner_offer")
    s.send_counter()
    s.wait_for_turn()
    s.wait_agent_idle()
    snap = s.snapshot()
    assert isinstance(snap["annotations"], dict)


def test_level9_layout_and_panels():
    s = make_session(agent_class="level9_panels:PanelAgent")
    s.start()
    s.wait_for_turn()
    s.wait_agent_idle()
    assert s.layout["view"] == "focus"
    ids = {p["id"] for p in s.agent_panels}
    assert "welcome" in ids and "best" in ids
    s.support_agent.on_panel_action("welcome", "full", {})
    assert s.layout["view"] == "full" and "welcome" not in {p["id"] for p in s.agent_panels}
    best = next(p for p in s.agent_panels if p["id"] == "best")
    offer = next(c for c in best["components"] if c["type"] == "outcome")["values"]
    s.support_agent.on_panel_action("best", "use", {"offer": offer})
    assert s.draft == offer and s.highlights[-1]["target"] == "send"


def test_capability_lattice():
    c = CapabilityState({"chat": True, "accept": True, "end": False}, "semi")
    assert c.has(Capability.CHAT) and not c.has("end")
    c.set_user_capability("chat", False)
    assert not c.has("chat")
    c.set_user_capability("end", True)
    assert not c.has("end")  # users cannot widen
    c.set_user_autonomy("full")
    assert c.autonomy == Autonomy.SEMI
    assert c.autonomy_allows_execute(Capability.SUBMIT_COUNTER)
    assert not c.autonomy_allows_execute(Capability.ACCEPT) and c.autonomy_allows_confirm(Capability.ACCEPT)


def test_schemas_follow_capabilities():
    s = make_session()
    names = lambda: {sc["function"]["name"] for sc in s.support_agent.dispatcher.schemas()}
    assert {"highlight", "annotate", "set_layout", "show_panel", "accept_offer"} <= names()
    s.support_agent.capabilities.set_user_capability("highlight", False)
    assert "highlight" not in names()
    assert not s.support_agent.dispatcher.execute("highlight", {"target": "accept"})["ok"]


def test_llm_agent_tool_calls(scripted):
    s = make_session(support_settings={"autonomy": "suggest"})
    s.start()
    s.wait_for_turn()
    issue = s.issues[0]
    v = list(issue.all)[-1]
    llm = scripted(
        ("set_offer", {"outcome": {issue.name: v}}),
        ("highlight", {"target": f"issue:{issue.name}", "message": "Look here"}),
        ("set_layout", {"view": "simple"}),
        ("show_panel", {"panel_id": "p", "title": "Plan", "markdown": "**Hold firm**", "buttons": [{"label": "OK", "action": "ok"}]}),
        ("submit_counter_offer", {"message": "fair?"}),
        "Prepared your counter-offer.",
    )
    chat(s, "help me")
    assert s.draft[issue.name] == v
    assert any(h["target"] == f"issue:{issue.name}" for h in s.highlights)
    assert s.layout["view"] == "simple"
    assert s.agent_panels[0]["id"] == "p"
    assert s.is_my_turn()  # suggest mode: nothing sent
    assert any(h["target"] == "reject" for h in s.highlights)
    assert s.chat[-1]["text"] == "Prepared your counter-offer."
    assert "accept_offer" in llm.calls[0]["tools"]


def test_llm_agent_full_autonomy_sends(scripted):
    s = make_session(support_settings={"autonomy": "full"})
    s.start()
    s.wait_for_turn()
    n = len(s.history)
    scripted(("submit_counter_offer", {"message": "here"}), "sent")
    chat(s, "send something")
    s.wait_for_turn()
    assert len(s.history) > n


def test_semi_autonomy_accept_asks_for_confirmation(scripted):
    s = make_session(support_settings={"autonomy": "semi"})
    s.start()
    s.wait_for_turn()
    scripted(("accept_offer", {}), "asked")
    chat(s, "accept it")
    assert any(m.get("type") == "confirm" and m["kind"] == "accept" for m in s.hub.messages)
    assert s.phase == "running"


def test_draft_below_reserved_warning():
    s = make_session()
    s.start()
    s.wait_for_turn()
    worst = s.human_ufun.worst()
    s.set_draft(s.outcome_to_dict(worst))
    if s.utility(worst) < s.reserved_value():
        assert any(m.get("type") == "toast" and m["level"] == "warning" for m in s.hub.messages)
        assert "offer" in s.annotations


def test_turned_off_agent_does_not_answer():
    s = make_session(agent_class="level1_hello:HelloAgent")
    s.support_agent.set_user_enabled(False)
    s.user_chat("hello")
    assert "turned off" in s.chat[-1]["text"]


def test_python_helpers_respect_capabilities():
    s = make_session(agent_class="level8_spotlight:SpotlightAgent")
    caps = s.support_agent.capabilities
    for cap in ("highlight", "annotate", "layout", "panels", "tool_visibility"):
        caps.set_user_capability(cap, False)
    s.start()
    s.wait_for_turn()
    s.wait_agent_idle()
    assert s.highlights == [] and s.annotations == {}
    sa = s.support_agent
    assert not sa.set_layout(view="focus")["ok"] and s.layout["view"] == "full"
    assert not sa.show_panel("p", "t", [])["ok"] and s.agent_panels == []
    assert not sa.focus_tool("Trace")["ok"]


def test_text_tool_calls_are_recovered():
    from hani2.support_agent.runtime import parse_text_tool_calls

    calls = parse_text_tool_calls('[tool call: set_message_text({"text": "hi (there)"})] and [tool call: list_tools({})]')
    assert [c["function"]["name"] for c in calls] == ["set_message_text", "list_tools"]
    assert parse_text_tool_calls("no calls here") == []
