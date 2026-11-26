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


def test_random_keeps_set_offer():
    s = _started(is_admin=True)
    r = _tool(s, RandomOutcomeTool)
    b = _button(r)
    assert b["label"] == "Set Offer" and b["action"] == "set_offer" and not b["disabled"]
    n = len(s.history)
    r.on_action("set_offer", {})
    assert len(s.history) == n
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
