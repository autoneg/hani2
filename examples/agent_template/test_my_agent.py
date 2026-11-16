"""Offline smoke test: the agent loads and its tool works without an LLM."""

from hani2.testing import make_session

from my_agent import MyAgent


def test_assess_runs_on_a_live_negotiation():
    session = make_session(agent_class="my_agent:MyAgent", partner="BoulwareTBNegotiator")
    session.start()
    session.wait_for_turn()
    agent = session.support_agent
    assert isinstance(agent, MyAgent)
    result = agent.dispatcher.execute("assess_partner_offer", {})
    assert result["ok"] and result["verdict"] in {"accept", "counter", "end_or_counter"}
