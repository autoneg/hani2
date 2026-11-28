"""The interface's AI features (Write message, Offer from message, writing / reading them on send) go to
the Assistant first: the default one answers with the study's own prompts on its model, an Assistant
can answer them itself (tutorial level 12), and the interface's own model answers otherwise."""

import json
from types import SimpleNamespace

import pytest

import hani2.llm_service as llm
from hani2.hosting import make_app, registry, run_host
from hani2.support_agent.runtime import SupportAgent
from hani2.testing import make_session

TOKEN = "team-secret"


def _boom(*a, **kw):
    raise AssertionError("the interface's own model was asked")


def _first_offer(s):
    return {i.name: list(i.all)[0] for i in s.issues}


@pytest.fixture
def scripted_assistant(monkeypatch):
    """The default Assistant with a model that answers ``reply`` and records what it was sent."""

    def make(reply, **kw):
        monkeypatch.setattr(llm, "_call_llm", _boom)
        s = make_session(**kw)
        sa = s.support_agent
        sent: list[str] = []

        def complete(tools, force_action=False, no_tools=False):
            assert no_tools
            sent.append(sa.messages[-1]["content"])
            return {"role": "assistant", "content": reply(s) if callable(reply) else reply}

        monkeypatch.setattr(sa, "model", lambda: SimpleNamespace(ok=True, is_harness=False))
        monkeypatch.setattr(sa, "_complete", complete)
        return s, sent

    return make


def test_write_message_goes_to_the_default_assistant_with_the_default_prompt(scripted_assistant):
    s, sent = scripted_assistant('"Let us meet halfway."')
    s.set_draft(_first_offer(s))
    r = s.generate_text()
    assert r == {"ok": True, "text": "Let us meet halfway."}
    assert s.draft_text == "Let us meet halfway."
    assert len(sent) == 1 and "write the participant's message" in sent[0]
    # the study's generation prompt, filled in
    assert llm.build_generation_prompt(s.draft_outcome(), s.issues, s.llm_context("assistant")) in sent[0]
    # the JSON-free exchange is remembered as a short note, not the whole prompt
    assert "I wrote" in s.support_agent.messages[-1]["content"]


def test_offer_from_message_goes_to_the_default_assistant(scripted_assistant):
    reply = lambda s: json.dumps({"has_offer": True, "confidence": 0.9, "outcome": _first_offer(s)})  # noqa: E731
    s, sent = scripted_assistant(reply)
    s.draft_text = "how about the first of everything"
    assert s.extract_offer_from_text()["ok"]
    assert s.draft == _first_offer(s)
    assert "read the offer" in sent[0] and "how about the first of everything" in sent[0]


def test_auto_generate_on_send_uses_the_assistant(scripted_assistant):
    s, _ = scripted_assistant("Here is my offer.", n_steps=6)
    s.admin_prefs["auto_generate"] = True
    s.start()
    s.wait_for_turn()
    s.set_draft(_first_offer(s))
    assert s.send_counter(text="")["ok"]
    s.wait_for_turn()
    mine = [h for h in s.history if h["by"] == "human"]
    assert mine and mine[-1].get("text") == "Here is my offer."


def test_without_the_capability_the_interface_uses_its_own_model(monkeypatch):
    s = make_session()
    sa = s.support_agent
    monkeypatch.setattr(sa, "_complete", lambda *a, **kw: pytest.fail("the Assistant was asked"))
    sa.capabilities.admin_capabilities["llm_features"] = False
    assert s.llm_assistant("write_message") is None
    monkeypatch.setattr(llm, "_call_llm", lambda prompt, settings=None: "From the interface.")
    s.set_draft(_first_offer(s))
    assert s.generate_text()["text"] == "From the interface."


def test_fill_text_and_fill_offer_gate_each_feature():
    s = make_session()
    caps = s.support_agent.capabilities.admin_capabilities
    caps["fill_text"] = False
    assert s.llm_assistant("write_message") is None and s.llm_assistant("offer_from_message") is not None
    caps["fill_text"], caps["fill_offer"] = True, False
    assert s.llm_assistant("write_message") is not None and s.llm_assistant("offer_from_message") is None


def test_the_assistant_is_not_asked_for_its_own_or_the_autopilots_requests():
    """The Assistant sending a counter-offer (or the autopilot) would wait on itself: the interface's
    own model answers then."""
    s = make_session()
    with s.acting_for_agent(set()):
        assert s._actor() == "agent"
        assert s.llm_assistant("write_message") is None
    s.support_agent.autopilot = True
    assert s.llm_assistant("write_message") is None
    s.support_agent.autopilot = False
    seen = []
    s.support_agent.dispatcher.register("probe", lambda args: seen.append(s.llm_assistant("write_message")) or {"ok": True},
                                        lambda: {})
    s.support_agent.dispatcher.execute("probe", {})  # the Assistant's own function (submit_counter_offer …)
    assert seen == [None] and s.llm_assistant("write_message") is not None


def test_an_assistant_that_returns_none_falls_back(monkeypatch):
    s = make_session()
    monkeypatch.setattr(s.support_agent, "write_message", lambda offer, wait=15.0: None)
    monkeypatch.setattr(llm, "_call_llm", lambda prompt, settings=None: "Fallback.")
    s.set_draft(_first_offer(s))
    assert s.generate_text()["text"] == "Fallback."


def test_tutorial_level12_answers_without_a_model(monkeypatch):
    monkeypatch.setattr(llm, "_call_llm", _boom)
    s = make_session(agent_class="level12_ghostwriter:GhostwriterAgent")
    offer = _first_offer(s)
    s.set_draft(offer)
    r = s.generate_text()
    assert r["ok"] and r["text"].startswith("Hello! To get us started, I propose")
    s.draft_text = "; ".join(f"{k}: {v}" for k, v in offer.items())
    s.set_draft({k: list(i.all)[-1] for k, i in zip(offer, s.issues)})
    assert s.extract_offer_from_text()["ok"]
    assert s.draft == offer


def test_tutorial_level12_passes_other_messages_to_the_default(monkeypatch):
    s = make_session(agent_class="level12_ghostwriter:GhostwriterAgent")
    asked = []
    monkeypatch.setattr(SupportAgent, "offer_from_message",
                        lambda self, text, wait=15.0: asked.append(text) or {"outcome": None, "error": None})
    s.draft_text = "something vague"
    assert not s.extract_offer_from_text()["ok"]
    assert asked == ["something vague"]


class Writer(SupportAgent):
    def write_message(self, offer, wait=15.0):
        return {"text": f"hosted: {sorted(offer)}", "error": None}

    def offer_from_message(self, text, wait=15.0):
        return {"outcome": {i.name: list(i.all)[0] for i in self.session.issues}, "error": None}


def test_a_hosted_assistant_answers_the_ai_features(monkeypatch):
    monkeypatch.setattr(llm, "_call_llm", _boom)
    app = make_app("assistant", Writer, token=TOKEN)
    with run_host(app) as url:
        registry.add("default", "writer", "assistant", url, token=TOKEN)
        s = make_session(agent_class="remote:writer")
        s.start()
        s.wait_for_turn()
        s.wait_agent_idle()
        offer = _first_offer(s)
        s.set_draft(offer)
        assert s.generate_text()["text"] == f"hosted: {sorted(offer)}"
        s.set_draft({k: list(i.all)[-1] for k, i in zip(offer, s.issues)})
        s.draft_text = "anything"
        assert s.extract_offer_from_text()["ok"] and s.draft == offer


def test_a_remote_assistant_that_did_not_ask_for_the_events_falls_back(monkeypatch):
    app = make_app("assistant", Writer, token=TOKEN)
    with run_host(app) as url:
        registry.add("default", "writer2", "assistant", url, token=TOKEN)
        s = make_session(agent_class="remote:writer2")
        s.start()
        s.wait_for_turn()
        s.wait_agent_idle()
        s.support_agent._wants.discard("write_message")  # an older host: it does not know the event
        monkeypatch.setattr(llm, "_call_llm", lambda prompt, settings=None: "From the interface.")
        s.set_draft(_first_offer(s))
        assert s.generate_text()["text"] == "From the interface."


def test_a_failing_assistant_model_falls_back_to_the_interface(monkeypatch):
    s = make_session()
    sa = s.support_agent

    def broken(*a, **kw):
        raise RuntimeError("the Assistant's model is down")

    monkeypatch.setattr(sa, "model", lambda: SimpleNamespace(ok=True, is_harness=False))
    monkeypatch.setattr(sa, "_complete", broken)
    monkeypatch.setattr(llm, "_call_llm", lambda prompt, settings=None: "From the interface.")
    s.set_draft(_first_offer(s))
    assert s.generate_text()["text"] == "From the interface."
    assert not sa._busy.locked()
