import csv
import time

from negmas import ResponseType, SAOResponse

from hani2.testing import make_session


def rows(home, user="tester"):
    with open(home / "db" / user / "results.csv") as fh:
        return list(csv.DictReader(fh))


def test_counter_offers_until_the_end(hani2_home):
    s = make_session(n_steps=6)
    assert s.phase == "ready" and s.scenario is not None
    s.start()
    assert s.wait_for_turn()
    assert s.partner_offer() is not None
    s.play_counters(10, text="my offer")
    assert s.wait_until_done()
    assert s.result["status"] in ("timedout", "success", "broken")
    r = rows(hani2_home)
    assert len(r) == 1 and r[0]["agent_type"] == "BoulwareTBNegotiator"
    assert int(r[0]["n_human_actions"]) >= 1
    assert (hani2_home / "db" / "tester" / "logs").is_dir()
    texts = [h.get("text") for h in s.history if h.get("by") == "human"]
    assert "my offer" in texts


def test_accept_reaches_agreement(hani2_home):
    s = make_session()
    s.start()
    s.wait_for_turn()
    assert s.accept()
    assert s.wait_until_done()
    assert s.result["status"] == "success" and s.result["ended_by"] == "human"
    assert rows(hani2_home)[0]["status"] == "success"


def test_end_by_human(hani2_home):
    s = make_session()
    s.start()
    s.wait_for_turn()
    s.end()
    s.wait_until_done()
    assert s.result["status"] == "broken" and s.result["ended_by"] == "human"


def test_draft_validation_and_utility():
    s = make_session()
    s.start()
    s.wait_for_turn()
    issue = s.issues[0]
    good = list(issue.all)[0]
    r = s.set_draft({issue.name.lower(): good})  # case-insensitive issue names
    assert r["ok"] and s.draft[issue.name] == good
    bad = s.set_draft({issue.name: "not-a-value"})
    assert not bad["ok"]
    assert s.set_draft({"nonsense": 1})["unrecognised"] == ["nonsense"]
    assert 0 <= s.utility(s.draft_outcome()) <= 1


def test_text_only_requires_message():
    s = make_session(is_admin=True)
    s.start()
    s.wait_for_turn()
    assert not s.send_counter(text="", text_only=True)["ok"]
    assert s.send_counter(text="just talking", text_only=True)["ok"]
    s.wait_for_turn()
    mine = [h for h in s.history if h.get("by") == "human"]
    assert mine[-1]["text"] == "just talking" and mine[-1]["offer"] is None


def test_timeout_sends_reject_and_finishes():
    s = make_session(n_steps=None, time_limit=2)
    s.start()
    assert s.wait_until_done(timeout=20)
    assert s.result["status"] in ("timedout", "broken")


def test_load_is_refused_while_running():
    s = make_session()
    s.start()
    s.wait_for_turn()
    name = s._scenario_name()
    s.load("Island")
    assert s._scenario_name() == name and s.phase == "running"


def test_next_negotiation_after_end():
    s = make_session()
    s.start()
    s.wait_for_turn()
    s.end()
    s.wait_until_done()
    s.load("Grocery")
    assert s.phase == "ready" and s._scenario_name().startswith("Grocery")
    assert s.history == []


def test_snapshot_is_json_safe():
    import json

    from hani2.hub import _dumps

    s = make_session()
    s.start()
    s.wait_for_turn()
    json.loads(_dumps({"type": "state", "state": s.snapshot()}))


def test_human_placeholder_runs_tool_hooks():
    s = make_session()
    seen = []
    s.start()
    s.wait_for_turn()
    s.tools[0].action_to_execute = lambda ss, nmi, a: seen.append(a.response)
    s.send_counter()
    s.wait_for_turn()
    assert seen and seen[0] == ResponseType.REJECT_OFFER


def test_new_scenario_resets_the_last_offer():
    s = make_session(scenario_type="Island")
    s.start()
    s.wait_for_turn()
    s.send_counter()
    s.wait_for_turn()
    s.end()
    s.wait_until_done()
    s.load("Grocery")
    s.start()
    s.wait_for_turn()
    assert s.scenario.outcome_space.is_valid(s.draft_outcome())
    assert s.send_counter()["ok"]
    s.wait_for_turn()
    assert s.phase == "running"


def test_invalid_offer_is_refused():
    s = make_session()
    s.start()
    s.wait_for_turn()
    s.draft[s.issues[0].name] = "nonsense"
    r = s.send_counter()
    assert not r["ok"] and s.is_my_turn()
