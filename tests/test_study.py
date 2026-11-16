import csv
import json

from conftest import write_settings

from hani2.testing import make_session

Q = """title: After
questions:
  - id: sat
    text: Happy?
    type: likert5
    required: true
"""


def test_no_questionnaire_by_default():
    s = make_session()
    s.start()
    s.wait_for_turn()
    s.end()
    s.wait_until_done()
    assert s.phase == "ended" and s.questionnaire is None


def test_questionnaire_flow(hani2_home):
    write_settings(hani2_home, "questionnaires/per_negotiation.yaml", Q)
    s = make_session()
    s.start()
    s.wait_for_turn()
    s.send_counter()
    s.wait_for_turn()
    s.end()
    s.wait_until_done()
    assert s.phase == "questionnaire"
    s.load("Trade")
    assert s.phase == "questionnaire"  # cannot skip it
    assert not s.study.submit_questionnaire({})["ok"]
    assert s.study.submit_questionnaire({"sat": 4})["ok"]
    assert s.phase == "ended"
    rows = list(csv.DictReader(open(hani2_home / "db" / "tester" / "negotiation_questionnaires.csv")))
    assert rows[0]["sat"] == "4" and rows[0]["agent_type"] == "BoulwareTBNegotiator"


def test_prolific_practice_counted_and_finish(hani2_home, monkeypatch):
    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "1")
    monkeypatch.setenv("PROLIFIC_PRACTICE_AGENTS", "LinearTBNegotiator")
    monkeypatch.setenv("PROLIFIC_FINALISTS", "BoulwareTBNegotiator")
    monkeypatch.setenv("PROLIFIC_COMPLETION_URL", "https://example.org/done?pid={pid}")
    s = make_session(user="prolific_P1", mode="guest", partner=None, query={"noautostart": "1"})
    assert s.ss["is_practice_round"] and s.support_agent and not s.support_agent.user_enabled
    s.start()
    s.wait_for_turn()
    assert s.ss["last_partner_type"] == "LinearTBNegotiator"
    s.send_counter()
    s.wait_for_turn()
    s.end()
    s.wait_until_done()
    assert "Practice complete" in s.notice["text"]
    # zero-action counted round does not count
    s.load()
    assert not s.ss["is_practice_round"]
    s.start()
    s.wait_for_turn()
    assert s.ss["last_partner_type"] == "BoulwareTBNegotiator"
    s.end()  # ending without an offer = no action
    s.wait_until_done()
    assert "NOT count" in s.notice["text"] and s.study.counted() == 0
    s.load()
    s.start()
    s.wait_for_turn()
    s.send_counter()
    s.wait_for_turn()
    s.end()
    s.wait_until_done()
    assert s.phase == "finished" and s.finish_url == "https://example.org/done?pid=P1"
    # a reload of a finished participant still gets the link
    s.phase = "ended"
    s.finish_url = None
    s.load()
    assert s.phase == "finished" and s.finish_url


def test_prolific_schedule(hani2_home, monkeypatch):
    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "2")
    d = hani2_home / "db" / "prolific_S1"
    d.mkdir(parents=True)
    (d / "prolific_session.json").write_text(json.dumps({"started_at": "2000-01-01T00:00:00", "scenario_type": "Trade"}))
    (d / "results.csv").write_text("ended_at,practice,n_human_actions,status\n1999-01-01T00:00:00,False,3,success\n")
    (d / "schedule.json").write_text(json.dumps({"negotiations": [{"slot": 0, "agent_class_name": "ConcederTBNegotiator", "scenario_type": "Island", "scenario_index": 0}]}))
    s = make_session(user="prolific_S1", mode="guest", partner=None, query={"noautostart": "1"})
    assert not s.ss["is_practice_round"]  # returning participant
    assert s._scenario_name().startswith("Island")
    s.start()
    s.wait_for_turn()
    assert s.ss["last_partner_type"] == "ConcederTBNegotiator"
