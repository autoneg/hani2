from conftest import write_settings

from hani2.testing import make_session


def test_negotiator_driver_plays_to_the_end(hani2_home):
    write_settings(hani2_home, "autopilot_settings.json", {"allowed": True, "driver": "ConcederTBNegotiator", "step_delay": 0})
    s = make_session(n_steps=8)
    s.start()
    s.wait_for_turn()
    assert s.snapshot()["autopilot"]["available"]
    r = s.set_autopilot(True)
    assert r["ok"], r
    assert s.wait_until_done(timeout=30)
    assert s.ss.get("autopilot_used")


def test_not_allowed_by_default(hani2_home):
    s = make_session()
    s.start()
    s.wait_for_turn()
    assert not s.set_autopilot(True)["ok"]
    assert not s.autopilot_active


def test_support_agent_driver_acts_each_turn(hani2_home, scripted):
    write_settings(hani2_home, "autopilot_settings.json", {"allowed": True, "driver": "Support Agent", "step_delay": 0})
    s = make_session(n_steps=4, support_settings={"autonomy": "suggest"})
    llm = scripted(*([("submit_counter_offer", {"message": "auto"})] * 10))
    s.start()
    s.wait_for_turn()
    assert s.set_autopilot(True)["ok"]
    assert s.wait_until_done(timeout=30)
    assert any(c["force"] for c in llm.calls)
    # autonomy is restored when autopilot is switched off
    s.set_autopilot(False)
    assert s.support_agent.capabilities.autonomy.value == "suggest"


def test_stall_net_disengages(hani2_home, scripted):
    write_settings(hani2_home, "autopilot_settings.json", {"allowed": True, "driver": "Support Agent", "step_delay": 0})
    s = make_session(n_steps=30)
    scripted(*(["I am just chatting"] * 50))
    s.start()
    s.wait_for_turn()
    s.set_autopilot(True)
    assert s.wait(lambda: not s.autopilot_active or s.phase != "running", 30)
    assert any(m.get("type") == "toast" and "disengaged" in m["message"] for m in s.hub.messages) or s.phase != "running"
