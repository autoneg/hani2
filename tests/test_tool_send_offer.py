"""Send offer in the offer generators where picking a deal already fills the counter-offer (the
Utility-based Selector and the Utility Bar): picking only fills the draft; the button sends the
picked deal with the typed message, like the Send offer button under the counter-offer, and is
disabled, with the reason as its tooltip, while the participant cannot send."""

import pytest

from hani2.testing import make_session
from hani2.tools.builtin import RandomOutcomeTool, UtilityBarTool, UtilitySelectorTool

TOOLS = [UtilitySelectorTool, UtilityBarTool]


def _tool(s, cls):
    return next(t for t in s.tools if isinstance(t, cls))


def _started(**kw):
    s = make_session(**kw)
    s.start()
    assert s.wait_for_turn()
    return s


def _button(t) -> dict:
    return next(c for c in t.render() if c["type"] == "button" and c["action"] in ("send_offer", "set_offer"))


def _table(t) -> dict:
    return next(c for c in t.render() if c["type"] == "table")


def _prepare(t):
    if isinstance(t, UtilityBarTool):
        t.on_input("area", [0, 100])
        t.on_input("mode", "some")
    else:
        t.on_input("min_util", 0)


def _pick(t, i: int = -1) -> dict:
    rows = _table(t)["rows"]
    i = i % len(rows)
    t.on_action("pick", {"row": rows[i], "index": i})
    return {k: v for k, v in rows[i].items() if k in {iss.name for iss in t.issues}}


def _human_offers(s) -> list:
    return [h for h in s.history if h.get("by") == "human" and h.get("kind") != "system"]


def _wait_sent(s, n: int) -> list:
    """The participant's offers once there are more than ``n`` (the move runs in the background)."""
    assert s.wait(lambda: len(_human_offers(s)) > n, 30)
    return _human_offers(s)


@pytest.mark.parametrize("cls", TOOLS)
def test_the_button_is_send_offer_and_needs_a_pick(cls):
    s = _started()
    t = _tool(s, cls)
    _prepare(t)
    b = _button(t)
    assert b["label"] == "Send offer" and b["action"] == "send_offer"
    assert b["disabled"] and b["tooltip"] == "Pick a deal first."
    assert "Set Offer" not in str(t.render())
    # pressing it anyway (WebMCP, a stale page) sends nothing
    n = len(s.history)
    assert not t.on_action("send_offer", {})["ok"]
    assert len(s.history) == n
    s.end()


@pytest.mark.parametrize("cls", TOOLS)
def test_picking_only_fills_the_draft_and_send_offer_sends_it_with_the_message(cls):
    s = _started()
    t = _tool(s, cls)
    _prepare(t)
    n = len(_human_offers(s))
    deal = _pick(t)
    assert all(s.draft[k] == v for k, v in deal.items())
    assert len(_human_offers(s)) == n  # picking sends nothing
    b = _button(t)
    assert not b["disabled"] and "Send" in b["tooltip"]
    s.set_draft_text("Here is my offer from the tool.")
    res = t.on_action("send_offer", {})
    assert res["ok"], res
    sent = _wait_sent(s, n)[n]
    assert all(sent["offer"][k] == v for k, v in deal.items())
    assert sent.get("text") == "Here is my offer from the tool."
    assert s.draft_text == ""  # the message is used up, as after the main Send offer button
    assert t.picked_outcome() is None and _button(t)["disabled"]
    s.end()


@pytest.mark.parametrize("cls", TOOLS)
def test_disabled_with_a_reason_when_the_participant_cannot_send(cls, monkeypatch):
    s = _started()  # the tools come with the start; after the end the reason is checked below
    t = _tool(s, cls)
    _prepare(t)
    _pick(t)
    assert not _button(t)["disabled"]
    # not the participant's turn
    monkeypatch.setattr(s, "is_my_turn", lambda: False)
    b = _button(t)
    assert b["disabled"] and b["tooltip"] == "Wait for your turn to send an offer."
    n = len(s.history)
    assert not t.on_action("send_offer", {})["ok"] and len(s.history) == n
    monkeypatch.undo()
    # the opponent is still thinking
    monkeypatch.setattr(s, "thinking", True)
    assert _button(t)["disabled"] and _button(t)["tooltip"] == "Wait for your turn to send an offer."
    monkeypatch.undo()
    # the autopilot negotiates
    monkeypatch.setattr(s, "autopilot_active", True)
    assert _button(t)["disabled"] and "autopilot" in _button(t)["tooltip"]
    assert not t.on_action("send_offer", {})["ok"] and len(s.history) == n
    monkeypatch.undo()
    # a study where offers are sent as messages only
    s.admin_prefs["text_only_mode"] = True
    assert _button(t)["disabled"] and "message" in _button(t)["tooltip"]
    s.admin_prefs["text_only_mode"] = False
    assert not _button(t)["disabled"]
    # once the negotiation is over
    s.end()
    assert s.wait(lambda: s.phase != "running", 10)
    b = _button(t)
    assert b["disabled"] and b["tooltip"] == "The negotiation is not running."


@pytest.mark.parametrize("cls", TOOLS)
def test_changing_the_draft_or_the_inputs_drops_the_pick(cls):
    s = _started()
    t = _tool(s, cls)
    _prepare(t)
    deal = _pick(t)
    assert t.picked_outcome() is not None
    # the participant edits the deal in the counter-offer: Send offer would no longer send what they see
    issue = s.issues[0]
    other = next(v for v in issue.all if v != deal[issue.name])
    s.set_draft({issue.name: other})
    assert t.picked_outcome() is None and _button(t)["disabled"]
    _pick(t)
    _prepare(t)  # new inputs: a new list
    assert t.picked_outcome() is None
    s.end()


def test_the_set_offer_action_still_fills_the_draft():
    s = _started()
    b = _tool(s, UtilityBarTool)
    _prepare(b)
    n = len(s.history)
    b.on_action("set_offer", {})
    first = b._space()[0][b.results()[0]]
    assert tuple(s.draft[i.name] for i in s.scenario.outcome_space.issues) == tuple(first)
    assert len(s.history) == n
    s.end()


def test_random_generates_into_the_draft_and_send_offer_sends_it():
    s = _started(is_admin=True)
    r = _tool(s, RandomOutcomeTool)
    b = _button(r)
    assert b["label"] == "Send offer" and b["disabled"] and b["tooltip"] == "Generate a deal first."
    assert "Set Offer" not in str(r.render())
    n = len(_human_offers(s))
    assert r.on_action("generate", {})["ok"]
    deal = r.picked_outcome()
    assert deal and all(s.draft[k] == v for k, v in deal.items())
    assert len(_human_offers(s)) == n  # generating sends nothing
    assert any(c["type"] == "outcome" for c in r.render())
    assert not _button(r)["disabled"]
    s.set_draft_text("A random one.")
    assert r.on_action("send_offer", {})["ok"]
    sent = _wait_sent(s, n)[n]
    assert all(sent["offer"][k] == v for k, v in deal.items()) and sent.get("text") == "A random one."
    assert r.picked_outcome() is None and _button(r)["disabled"]
    s.end()


def _llm(s, monkeypatch, reply: dict):
    import json

    import hani2.llm_service as llm

    monkeypatch.setattr(llm, "is_llm_configured", lambda: True)
    monkeypatch.setattr(llm, "_call_llm", lambda prompt, settings=None: json.dumps(reply))
    if s.support_agent is not None:
        s.support_agent.user_enabled = False  # the tool's own prompt (the Assistant path is tested below)
    tool = s.tool_controller.find("LLM")
    tool.on_action("generate", {"instruction": "be fair"})
    assert s.wait(lambda: not tool.busy, 10)
    assert tool.generated, tool.status
    return tool


def _llm_buttons(tool) -> dict:
    row = next(c for c in tool.render() if c["type"] == "row")
    return {c["label"]: c for c in row["children"] if c["type"] == "button"}


def test_llm_has_set_offer_and_send_offer(monkeypatch):
    s = _started(is_admin=True)
    tool = s.tool_controller.find("LLM")
    assert not any(c["type"] == "row" for c in tool.render())  # no buttons before a suggestion
    outcome = {i.name: list(i.all)[-1] for i in s.issues}
    tool = _llm(s, monkeypatch, {"text": "Meet me here.", "outcome": outcome, "reasoning": "fair"})
    buttons = _llm_buttons(tool)
    assert set(buttons) == {"Set offer", "Send offer"} and not buttons["Send offer"]["disabled"]
    n = len(_human_offers(s))
    # Set offer copies the suggestion, sends nothing
    tool.on_action("apply", {})
    assert s.draft == outcome and s.draft_text == "Meet me here." and len(_human_offers(s)) == n
    # Send offer sends the suggestion with its message, even after the participant changed the draft
    issue = s.issues[0]
    s.set_draft({issue.name: next(v for v in issue.all if v != outcome[issue.name])})
    assert tool.on_action("send_offer", {})["ok"]
    sent = _wait_sent(s, n)[n]
    assert sent["offer"] == outcome and sent.get("text") == "Meet me here."
    assert tool.generated is None and s.draft_text == ""
    s.end()


def test_llm_send_offer_is_disabled_with_a_reason(monkeypatch):
    s = _started(is_admin=True)
    outcome = {i.name: list(i.all)[0] for i in s.issues}
    tool = _llm(s, monkeypatch, {"text": "Hi.", "outcome": outcome, "reasoning": "x"})
    monkeypatch.setattr(s, "is_my_turn", lambda: False)
    send = _llm_buttons(tool)["Send offer"]
    assert send["disabled"] and send["tooltip"] == "Wait for your turn to send an offer."
    n = len(s.history)
    assert not tool.on_action("send_offer", {})["ok"] and len(s.history) == n
    assert not _llm_buttons(tool)["Set offer"].get("disabled")  # copying is always possible
    s.end()


def test_the_assistant_picks_and_sends_through_the_tool(hani2_home):
    s = _started(assistant_settings={"autonomy": "full"})
    sa = s.support_agent
    n = len(_human_offers(s))
    res = sa.use_tool("Utility-based Selector", inputs={"min_util": 0}, action="pick", row=0)
    assert res["ok"], res
    picked = _tool(s, UtilitySelectorTool).picked_outcome()
    assert picked and all(s.draft[k] == v for k, v in picked.items())
    assert len(_human_offers(s)) == n
    assert sa.use_tool("Utility-based Selector", action="send_offer")["ok"]
    assert len(_wait_sent(s, n)) == n + 1
    s.end()


def test_an_assistant_that_may_not_send_cannot_send_through_the_tool(hani2_home):
    from hani2.support_agent.settings import DEFAULT_CAPABILITIES

    s = _started(assistant_settings={"capabilities": {**DEFAULT_CAPABILITIES, "submit_counter": False}})
    sa = s.support_agent
    t = _tool(s, UtilitySelectorTool)
    assert sa.use_tool("Utility-based Selector", inputs={"min_util": 0}, action="pick", row=0)["ok"]
    assert t.picked_outcome()
    n = len(_human_offers(s))
    sa.use_tool("Utility-based Selector", action="send_offer")
    assert not s.wait(lambda: len(_human_offers(s)) > n, 1)
    # the participant pressing the same button still sends
    assert t.on_action("send_offer", {})["ok"]
    assert len(_wait_sent(s, n)) == n + 1
    s.end()


# --------------------------------------------------------------------------- #
# The LLM tool asks the Assistant when there is one; an empty instruction asks  #
# for a recommendation                                                         #
# --------------------------------------------------------------------------- #
def _stub_assistant(s, monkeypatch, reply: dict, seen: list):
    import json
    from types import SimpleNamespace

    import hani2.llm_service as llm

    sa = s.support_agent
    monkeypatch.setattr(sa, "model", lambda: SimpleNamespace(ok=True, is_harness=False))

    def complete(tools, force_action=False, no_tools=False):
        seen.append({"messages": list(sa.messages), "no_tools": no_tools})
        return {"role": "assistant", "content": json.dumps(reply)}

    monkeypatch.setattr(sa, "_complete", complete)

    def no_tool_prompt(*a, **k):
        raise AssertionError("the tool's own prompt was used")

    monkeypatch.setattr(llm, "_call_llm", no_tool_prompt)
    return sa


def _generate(s, tool, **payload):
    tool.on_action("generate", payload)
    assert s.wait(lambda: not tool.busy, 10)
    return tool.generated


def test_the_llm_tool_asks_the_assistant(monkeypatch):
    s = _started(is_admin=True)
    outcome = {i.name: list(i.all)[-1] for i in s.issues}
    seen: list = []
    sa = _stub_assistant(s, monkeypatch, {"text": "From your Assistant.", "outcome": outcome, "reasoning": "x"}, seen)
    before = len(sa.messages)
    tool = s.tool_controller.find("LLM")
    assert "Your Assistant writes the suggestions." in str(tool.render())
    g = _generate(s, tool, instruction="hold firm on the first issue")
    assert g and g["outcome"] == outcome and g["text"] == "From your Assistant.", tool.status
    # the Assistant got the participant's words, with its own system prompt and conversation, and called no function
    sent = seen[0]
    assert sent["no_tools"] and sent["messages"][0]["role"] == "system"
    assert "hold firm on the first issue" in sent["messages"][-1]["content"]
    # the conversation remembers the request in plain words (not the JSON exchange)
    added = sa.messages[before:]
    assert len(added) == 2 and "hold firm on the first issue" in added[0]["content"]
    assert "{" not in added[0]["content"]
    # and Send offer sends the Assistant's suggestion
    n = len(_human_offers(s))
    assert tool.on_action("send_offer", {})["ok"]
    assert _wait_sent(s, n)[n]["offer"] == outcome
    s.end()


def test_an_empty_instruction_asks_for_a_recommendation(monkeypatch):
    s = _started(is_admin=True)
    outcome = {i.name: list(i.all)[0] for i in s.issues}
    seen: list = []
    _stub_assistant(s, monkeypatch, {"text": "Here.", "outcome": outcome, "reasoning": "x"}, seen)
    tool = s.tool_controller.find("LLM")
    gen = next(c for c in tool.render() if c["type"] == "button" and c["action"] == "generate")
    assert gen["label"] == "Generate" and gen["empty_label"] == "Recommend an offer" and gen["empty_input"] == "instruction"
    assert not gen["disabled"]
    assert _generate(s, tool, instruction="")["outcome"] == outcome
    assert "Recommend an offer" in seen[-1]["messages"][-1]["content"]
    # Text only: the empty button writes a message
    tool.on_input("mode", "text_only")
    gen = next(c for c in tool.render() if c["type"] == "button" and c["action"] == "generate")
    assert gen["empty_label"] == "Write a message"
    assert tool.instruction().startswith("Write a message")
    s.end()


def test_without_the_assistant_the_tool_uses_its_own_prompt(monkeypatch):
    import json

    import hani2.llm_service as llm

    s = _started(is_admin=True)
    outcome = {i.name: list(i.all)[0] for i in s.issues}
    prompts: list = []
    monkeypatch.setattr(llm, "is_llm_configured", lambda: True)
    monkeypatch.setattr(llm, "_call_llm", lambda prompt, settings=None: prompts.append(prompt) or json.dumps(
        {"text": "Tool.", "outcome": outcome, "reasoning": "x"}))
    sa = s.support_agent
    sa.user_enabled = False  # switched off by the participant
    tool = s.tool_controller.find("LLM")
    assert "Your Assistant" not in str(tool.render())
    assert _generate(s, tool, instruction="")["text"] == "Tool."
    assert "Recommend an offer" in prompts[-1]  # an empty instruction is a recommendation here too
    # an Assistant that may not fill the offer leaves it to the tool too
    sa.user_enabled = True
    sa.capabilities.admin_capabilities["fill_offer"] = False
    assert sa.suggest_offer("anything", "both") is None
    s.end()


def test_the_assistant_pressing_generate_uses_the_tools_prompt(monkeypatch):
    """The Assistant waits on the tool while it presses Generate: asking it again would wait on itself."""
    import json

    import hani2.llm_service as llm

    s = _started(is_admin=True, assistant_settings={"autonomy": "full"})
    outcome = {i.name: list(i.all)[0] for i in s.issues}
    monkeypatch.setattr(llm, "is_llm_configured", lambda: True)
    monkeypatch.setattr(llm, "_call_llm", lambda prompt, settings=None: json.dumps(
        {"text": "Tool.", "outcome": outcome, "reasoning": "x"}))
    sa = s.support_agent
    monkeypatch.setattr(sa, "suggest_offer", lambda *a, **k: (_ for _ in ()).throw(AssertionError("asked itself")))
    res = sa.use_tool("LLM", inputs={"instruction": "be fair"}, action="generate")
    assert res["ok"], res
    tool = s.tool_controller.find("LLM")
    assert tool.generated and tool.generated["text"] == "Tool.", tool.status
    s.end()
