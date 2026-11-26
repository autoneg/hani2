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


def test_prolific_auto_timers_do_nothing_after_close(hani2_home, monkeypatch):
    import time

    monkeypatch.setenv("PROLIFIC_AUTO_START_SECONDS", "1")
    s = make_session(user="prolific_C1", mode="guest", partner=None)
    assert s.study.auto_kind == "start" and s.phase == "ready"
    s.close()
    time.sleep(1.5)
    assert s.phase == "ready" and s.mechanism is None  # the auto-start never fired


def test_prolific_schedule(hani2_home, monkeypatch):
    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "2")
    d = hani2_home / "db" / "prolific_S1"
    d.mkdir(parents=True)
    (d / "prolific_session.json").write_text(json.dumps({"started_at": "2000-01-01T00:00:00", "scenario_type": "Trade"}), encoding="utf-8")
    (d / "results.csv").write_text("ended_at,practice,n_human_actions,status\n1999-01-01T00:00:00,False,3,success\n", encoding="utf-8")
    (d / "schedule.json").write_text(json.dumps({"negotiations": [{"slot": 0, "agent_class_name": "ConcederTBNegotiator", "scenario_type": "Island", "scenario_index": 0}]}), encoding="utf-8")
    s = make_session(user="prolific_S1", mode="guest", partner=None, query={"noautostart": "1"})
    assert not s.ss["is_practice_round"]  # returning participant
    assert s._scenario_name().startswith("Island")
    s.start()
    s.wait_for_turn()
    assert s.ss["last_partner_type"] == "ConcederTBNegotiator"


def test_questionnaire_only_when_one_is_open():
    from hani2.testing import make_session

    s = make_session()
    s.start()
    s.wait_for_turn()
    r = s.study.submit_questionnaire({"x": 1})
    assert r["ok"] is False and s.phase == "running"


def test_questionnaire_answers_cannot_overwrite_row_metadata(tmp_path):
    import csv

    from hani2.study import save_questionnaire

    save_questionnaire(tmp_path, {"mechanism_id": "m", "agent_type": "Real", "practice": False}, {"q1": 3})
    save_questionnaire(tmp_path, {"mechanism_id": "m2", "agent_type": "Real", "practice": False},
                       {"q1": 4, "agent_type": "forged"})
    rows = list(csv.DictReader((tmp_path / "negotiation_questionnaires.csv").open()))
    assert [r["agent_type"] for r in rows] == ["Real", "Real"]


# --------------------------------------------------------------------------- #
# Prolific: hani2 owns the plan for slots schedule.json leaves open            #
# --------------------------------------------------------------------------- #
OPP3 = ["BoulwareTBNegotiator", "ConcederTBNegotiator", "LinearTBNegotiator"]
ASS3 = ["level1_hello:HelloAgent", "level2_rules:RulesAgent", "level5_deal_coach:DealCoach"]


def _prolific_study(hani2_home, monkeypatch, **overrides):
    from hani2 import projects
    from hani2.projects import StudyRef

    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "3")
    projects.create_project("HI", kind="assistant")
    projects.create_study("HI/s1", type="prolific", opponents=OPP3, assistants=ASS3, practice=False, n_required=3,
                          scheduling={"assistants": "latin_square", "opponents": "latin_square"}, **overrides)
    return StudyRef("HI", "s1")


def _write_schedule(ref, pid, slots):
    from hani2 import projects

    d = projects.study_dir(ref) / "results" / f"prolific_{pid}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "schedule.json").write_text(json.dumps({"version": 2, "negotiations": slots}), encoding="utf-8")
    return d


def _play_round(s):
    s.start()
    s.wait_for_turn()
    s.send_counter()
    s.wait_for_turn()
    s.end()
    s.wait_until_done()
    s.load()


def test_open_slots_use_the_study_plan_and_its_crossing(hani2_home, monkeypatch):
    """scmlweb's schedule fixes only the scenario type: the opponent and the Assistant come from
    the study's methods, crossed, and the old rotation is not started (D14)."""
    from hani2 import assignment, scheduling

    ref = _prolific_study(hani2_home, monkeypatch)
    path = assignment.store_path(ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "humans": {}, "next_index": 6}), encoding="utf-8")  # block 1
    d = _write_schedule(ref, "OPEN", [{"slot": k, "scenario_type": "Trade"} for k in range(3)])
    s = make_session(user="prolific_OPEN", mode="guest", partner=None, study=ref, query={"noautostart": "1"})
    got = []
    for k in range(3):
        assert s.round_plan["opponent_scheduling"] == "latin_square" and s.round_plan["scenario_scheduling"] == "external"
        assert s.assistant_choice.scheduling == "latin_square"
        got.append((s.assistant_choice.spec, s.round_plan["partner"]))
        _play_round(s)
    seed = f"{ref}|prolific_OPEN"
    want = [(scheduling.pick_assistant_slot("latin_square", ASS3, 6, k),
             scheduling.pick_opponent("latin_square", OPP3, 6, k, seed, offset=1)) for k in range(3)]
    assert got == want
    assert not (d / "fallback_rotation.txt").exists()


def test_participants_on_the_old_rotation_keep_it(hani2_home, monkeypatch):
    ref = _prolific_study(hani2_home, monkeypatch)
    d = _write_schedule(ref, "OLD", [{"slot": 0, "scenario_type": "Trade"}])
    (d / "fallback_rotation.txt").write_text("1", encoding="utf-8")
    s = make_session(user="prolific_OLD", mode="guest", partner=None, study=ref, query={"noautostart": "1"})
    assert s.round_plan["partner"] == OPP3[1] and s.round_plan["opponent_scheduling"] == "cyclic"
    assert s.study.planned_opponents(3) is None


def test_a_slot_naming_an_opponent_still_wins(hani2_home, monkeypatch):
    ref = _prolific_study(hani2_home, monkeypatch)
    _write_schedule(ref, "NAMED", [{"slot": 0, "agent_class_name": "LinearTBNegotiator"}, {"slot": 1}])
    s = make_session(user="prolific_NAMED", mode="guest", partner=None, study=ref, query={"noautostart": "1"})
    assert s.round_plan["partner"] == "LinearTBNegotiator" and s.round_plan["opponent_scheduling"] == "external"
    plan = s.study.planned_opponents(3)
    assert plan[0] == "LinearTBNegotiator" and plan[1] in OPP3
    _play_round(s)
    assert s.round_plan["opponent_scheduling"] == "latin_square" and s.round_plan["partner"] == plan[1]
