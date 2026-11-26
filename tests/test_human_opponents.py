"""Two participants negotiating with each other (hani2.matches)."""

import csv
import time
import uuid

import pytest
from negmas import ResponseType, SAOResponse

from hani2 import matches
from hani2.testing import make_session


@pytest.fixture(autouse=True)
def _empty_lobby():
    matches.LOBBY.clear()
    yield
    matches.LOBBY.clear()


def rows(home, user):
    with open(home / "db" / user / "results.csv") as fh:
        return list(csv.DictReader(fh))


def own_rows(s):
    with open(s.ss["user_path"] / "results.csv") as fh:
        return list(csv.DictReader(fh))


def pair(code=None, **kw):
    """Two participants with an Assistant each, who asked for human+assistant opponents."""
    code = code or uuid.uuid4().hex[:6]
    kw.setdefault("n_steps", 10)
    a = make_session(user="alice", opponent="human+assistant", query={"match": code}, **kw)
    b = make_session(user="bob", opponent="human+assistant", query={"match": code}, **kw)
    return a, b


def test_pairing_shares_the_scenario_and_splits_the_sides(hani2_home):
    a, b = pair()
    assert a.match is not None and a.match is b.match
    assert a.scenario is b.scenario
    assert {a.human_index, b.human_index} == {0, 1}
    assert a.waiting_for_opponent and b.waiting_for_opponent
    assert a.snapshot()["opponent_kind"] == "human+assistant"


def test_different_codes_do_not_meet(hani2_home):
    a = make_session(user="alice", opponent="human+assistant", query={"match": "one"})
    b = make_session(user="bob", opponent="human+assistant", query={"match": "two"})
    assert a.match is not b.match
    assert matches.LOBBY.n_waiting() == 2


def test_negotiation_starts_when_both_are_ready_and_turns_alternate(hani2_home):
    a, b = pair()
    a.start()
    time.sleep(0.2)
    assert a.phase == "starting" and a.mechanism is None and a.waiting_for_opponent
    b.start()
    assert a.wait(lambda: a.phase == "running" and b.phase == "running")
    assert a.mechanism is b.mechanism
    first, second = (a, b) if a.wait_for_turn(2) and a.is_my_turn() else (b, a)
    assert first.wait_for_turn() and first.is_my_turn() and not second.is_my_turn()
    assert first.send_counter("an offer").get("ok", True)
    assert second.wait_for_turn() and second.is_my_turn()
    # the offer reached the other side's history, as the opponent's
    assert second.wait(lambda: any(h.get("by") == "agent" and h.get("text") == "an offer" for h in second.history))
    assert second.partner_offer() is not None
    assert second.accept()
    assert a.wait_until_done() and b.wait_until_done()
    assert a.result["status"] == "success" and b.result["status"] == "success"
    ra, rb = rows(hani2_home, "alice")[-1], rows(hani2_home, "bob")[-1]
    assert ra["match_id"] == rb["match_id"] != ""
    assert ra["mechanism_id"] == rb["mechanism_id"]
    assert ra["opponent_user"] == "bob" and rb["opponent_user"] == "alice"
    assert ra["agent_type"] == "human+assistant" and ra["opponent_kind"] == "human+assistant"
    assert float(ra["human_utility"]) == pytest.approx(float(rb["agent_utility"]))


def test_ending_reaches_both_sides(hani2_home):
    a, b = pair()
    a.start()
    b.start()
    assert a.wait(lambda: a.phase == "running" and b.phase == "running")
    first = a if a.wait_for_turn(2) and a.is_my_turn() else b
    other = b if first is a else a
    assert first.end()
    assert a.wait_until_done() and b.wait_until_done()
    assert first.result["ended_by"] == "human"
    assert other.result["ended_by"] == "agent"


def test_a_participant_leaving_ends_the_negotiation(hani2_home):
    a, b = pair()
    a.start()
    b.start()
    assert a.wait(lambda: a.phase == "running" and b.phase == "running")
    mover = a if a.wait_for_turn(2) and a.is_my_turn() else b
    stayer = b if mover is a else a
    mover.close()
    assert stayer.wait_until_done()
    assert stayer.result["status"] == "broken"


def test_leaving_before_the_start_puts_the_other_back_in_the_lobby(hani2_home):
    code = uuid.uuid4().hex[:6]
    a, b = pair(code)
    b.close()
    assert a.match is not None and not a.match.paired
    c = make_session(user="carol", opponent="human+assistant", query={"match": code})
    assert c.match is a.match and a.match.paired


def test_no_partner_falls_back_to_an_ai_opponent(hani2_home):
    a = make_session(user="alice", opponent="human,BoulwareTBNegotiator", query={"match": "lonely"}, load=False)
    a.admin_prefs["human_opponent_wait"] = 0.3
    a.admin_prefs["n_steps"] = 6
    a.load()
    # the pool has both: retry until this round drew the human entry
    tries = 0
    while a.match is None and tries < 30:
        matches.LOBBY.clear()
        a.phase = "ended"
        a.load()
        tries += 1
    assert a.match is not None
    a.start()
    assert a.wait(lambda: a.phase == "running", 10)
    assert a.match is None
    assert a.ss["last_partner_type"] == "BoulwareTBNegotiator"
    assert a.wait_for_turn()
    a.act(SAOResponse(ResponseType.END_NEGOTIATION, None))
    assert a.wait_until_done()
    assert rows(hani2_home, "alice")[-1]["opponent_kind"] == "agent"


def test_pools_without_human_are_unchanged(hani2_home):
    s = make_session(user="dave")
    assert s.match is None and not s.waiting_for_opponent
    assert s.snapshot()["opponent_kind"] == "agent"


def test_a_team_with_an_assistant_against_a_participant_alone(hani2_home):
    code = uuid.uuid4().hex[:6]
    # alice's study: an Assistant, human opponents alone; bob's: no Assistant, human+assistant opponents
    a = make_session(user="alice", opponent="human", query={"match": code}, n_steps=10)
    b = make_session(user="bob", opponent="human+assistant", query={"match": code}, n_steps=10,
                     assistant_settings={"mode": "off"})
    assert a.support_agent is not None and b.support_agent is None
    assert a.match is not None and a.match is b.match
    assert a.snapshot()["opponent_kind"] == "human" and b.snapshot()["opponent_kind"] == "human+assistant"
    a.start()
    b.start()
    assert a.wait(lambda: a.phase == "running" and b.phase == "running")
    first = a if a.wait_for_turn(2) and a.is_my_turn() else b
    other = b if first is a else a
    first.send_counter("hello")
    assert other.wait_for_turn() and other.is_my_turn()
    assert other.accept()
    assert a.wait_until_done() and b.wait_until_done()
    assert rows(hani2_home, "alice")[-1]["agent_type"] == "human"
    assert rows(hani2_home, "bob")[-1]["agent_type"] == "human+assistant"


def test_sides_that_do_not_fit_are_not_paired(hani2_home):
    code = uuid.uuid4().hex[:6]
    # both have an Assistant but want an opponent without one
    a = make_session(user="alice", opponent="human", query={"match": code})
    b = make_session(user="bob", opponent="human", query={"match": code})
    assert a.match is not b.match
    # a participant alone who wants a participant alone fits neither
    c = make_session(user="carol", opponent="human", query={"match": code}, assistant_settings={"mode": "off"})
    assert c.match not in (a.match, b.match)
    # a participant alone who wants a team fits alice or bob (who want someone alone): one at random
    d = make_session(user="dan", opponent="human+assistant", query={"match": code}, assistant_settings={"mode": "off"})
    assert d.match in (a.match, b.match) and d.match.paired


def test_human_opponents_pair_across_studies_of_a_project(hani2_home):
    from hani2 import matches as mm

    class S:
        def __init__(self, study):
            self.query = {}
            self.study_ref = type("R", (), {"project": "hi", "study": study})()

    assert mm.match_key(S("team")) == mm.match_key(S("solo")) == "project:hi"
    assert mm.is_human("Human + Assistant") and mm.wants_assistant("human_assistant") and not mm.wants_assistant("human")


def test_plus_in_a_url_decodes_to_a_space_and_still_means_human_assistant():
    from urllib.parse import parse_qs

    v = parse_qs("opponents=human+assistant")["opponents"][0]
    assert v == "human assistant"
    assert matches.is_human(v) and matches.wants_assistant(v)
    assert not matches.is_human("humanoid") and not matches.wants_assistant("human")


def test_a_host_answering_its_pre_questionnaire_can_still_be_joined(hani2_home):
    code = uuid.uuid4().hex[:6]
    a = make_session(user="alice", opponent="human+assistant", query={"match": code})
    a.phase = "questionnaire"
    b = make_session(user="bob", opponent="human+assistant", query={"match": code})
    assert b.match is a.match and a.match.paired


def test_a_partner_who_never_starts_is_replaced(hani2_home):
    a, b = pair()
    a.admin_prefs["human_opponent_wait"] = 0.2
    old = a.match
    a.start()
    # bob never presses Start: after the wait alice is back in the lobby, bob gets a match of his own
    assert a.wait(lambda: b.match is not old and b.match is not None, 10)
    assert a.match is old and not old.paired and b.match.paired is False
    assert b.phase == "ready" and a.phase == "starting"
    c = make_session(user="carol", opponent="human+assistant", query={"match": a.query["match"]})
    assert c.match in (old, b.match)


def test_a_page_closed_for_good_ends_the_negotiation(hani2_home):
    a, b = pair()
    for s in (a, b):
        s.admin_prefs["human_opponent_absent"] = 0.2
    a.start()
    b.start()
    assert a.wait(lambda: a.phase == "running" and b.phase == "running")
    b.hub.n_connections = lambda sid: 0  # bob's tab is gone (his session stays, as in the server)
    a.hub.n_connections = lambda sid: 1
    assert a.wait_until_done(15) and b.wait_until_done(15)
    assert a.result["status"] == "broken"
    ra, rb = rows(hani2_home, "alice")[-1], rows(hani2_home, "bob")[-1]
    assert ra["abandoned"] == "opponent" and rb["abandoned"] == "self"


def test_studies_of_one_project_pair_a_team_with_a_participant_alone(hani2_home):
    from hani2 import projects

    projects.create_project("HH")
    projects.create_study("HH/team", opponents=["human"])
    projects.create_study("HH/solo", opponents=["human+assistant"])
    a = make_session(user="alice", partner=None, study="HH/team", n_steps=10)
    b = make_session(user="bob", partner=None, study="HH/solo", n_steps=10, assistant_settings={"mode": "off"})
    assert a.support_agent is not None and b.support_agent is None
    assert a.match is not None and a.match is b.match
    a.start()
    b.start()
    assert a.wait(lambda: a.phase == "running" and b.phase == "running")
    first = a if a.wait_for_turn(2) and a.is_my_turn() else b
    first.end()
    assert a.wait_until_done() and b.wait_until_done()
    assert own_rows(a)[-1]["opponent_kind"] == "human"
    assert own_rows(b)[-1]["opponent_kind"] == "human+assistant"


def test_one_study_whose_participants_cannot_fit_each_other_is_never_paired(hani2_home):
    from hani2 import projects

    projects.create_project("HX")
    projects.create_study("HX/s", opponents=["human"])  # with an Assistant, wanting opponents without one
    a = make_session(user="alice", partner=None, study="HX/s")
    b = make_session(user="bob", partner=None, study="HX/s")
    assert a.match is not None and b.match is not None and a.match is not b.match


def test_the_opponent_picker_never_offers_human_entries(hani2_home):
    from hani2 import choices

    s = make_session(user="erin", opponent="human+assistant,BoulwareTBNegotiator", load=False)
    opts = choices.opponent_options(s, True)
    assert [choices.spec_key(o) for o in opts] == ["BoulwareTBNegotiator"]


def test_a_late_joiner_gets_the_full_wait_to_press_start(hani2_home):
    code = uuid.uuid4().hex[:6]
    a = make_session(user="alice", opponent="human+assistant", query={"match": code}, load=False)
    a.admin_prefs["human_opponent_wait"] = 1.5
    a.load()
    a.start()  # alice presses Start alone and waits
    time.sleep(1.2)
    b = make_session(user="bob", opponent="human+assistant", query={"match": code})
    assert b.match is a.match
    time.sleep(0.8)  # alice has waited longer than the wait, but bob just arrived
    assert b.match is a.match and a.match.paired
    b.start()
    assert a.wait(lambda: a.phase == "running" and b.phase == "running")


def test_two_participants_loading_together_are_paired(hani2_home, monkeypatch):
    import threading

    from hani2 import scenario_store as store

    code = uuid.uuid4().hex[:6]
    a = make_session(user="alice", opponent="human+assistant", query={"match": code}, load=False)
    b = make_session(user="bob", opponent="human+assistant", query={"match": code}, load=False)
    real = store.load_scenario

    def slow(*args, **kw):
        time.sleep(0.3)
        return real(*args, **kw)

    monkeypatch.setattr(store, "load_scenario", slow)
    ts = [threading.Thread(target=s.load) for s in (a, b)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert a.match is not None and a.match is b.match


def test_a_time_limit_ends_a_negotiation_nobody_acts_in(hani2_home):
    a, b = pair(time_limit=3)
    a.start()
    b.start()
    assert a.wait(lambda: a.phase == "running" and b.phase == "running")
    assert a.wait_until_done(20) and b.wait_until_done(20)
    assert a.result["status"] == "timedout" and b.result["status"] == "timedout"


def test_a_time_limit_ends_a_negotiation_after_one_offer(hani2_home):
    a, b = pair(time_limit=3)
    a.start()
    b.start()
    assert a.wait(lambda: a.phase == "running" and b.phase == "running")
    first = a if a.wait_for_turn(2) and a.is_my_turn() else b
    first.send_counter("one offer")
    assert a.wait_until_done(20) and b.wait_until_done(20)
    assert a.result["status"] == "timedout" and b.result["status"] == "timedout"


def test_prolific_participants_scheduled_against_human_assistant(hani2_home, monkeypatch):
    import json

    from hani2 import projects

    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "1")
    projects.create_project("HP")
    projects.create_study("HP/s1", type="prolific", practice=False)
    ref = projects.StudyRef("HP", "s1")
    for pid in ("PA", "PB"):
        d = projects.study_dir(ref) / "results" / f"prolific_{pid}"
        d.mkdir(parents=True)
        (d / "schedule.json").write_text(json.dumps({"version": 2, "negotiations": [
            {"slot": 0, "agent_class_name": "human+assistant", "scenario_type": "Trade"}]}), encoding="utf-8")
    a = make_session(user="prolific_PA", mode="guest", partner=None, study=ref, query={"noautostart": "1"})
    b = make_session(user="prolific_PB", mode="guest", partner=None, study=ref, query={"noautostart": "1"})
    assert a.round_plan["partner"] == "human+assistant"
    assert a.match is not None and a.match is b.match


# --------------------------------------------------------------------------- #
# study_mode: where people meet and the per-session checks                     #
# --------------------------------------------------------------------------- #
def _group(ref, key, data):
    import json

    from hani2 import projects

    d = projects.study_dir(ref) / "results" / "groups"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(json.dumps(data), encoding="utf-8")


def test_the_lobby_follows_pairing_scope(hani2_home):
    from hani2 import projects

    projects.create_project("HI", kind="assistant")
    projects.create_study("HI/paired", study_mode="paired")  # declared paired: the study alone
    projects.create_study("HI/wide", study_mode="paired", pairing={"scope": "project"})
    projects.create_study("HI/old", opponents=["human+assistant"])  # not declared: as before
    projects.create_study("HI/codes", study_mode="paired", pairing={"scope": "code"})

    def key(study, query=None):
        s = make_session(user=f"u{uuid.uuid4().hex[:6]}", partner=None, study=f"HI/{study}", load=False,
                         query=query or {})
        return s, matches.match_key(s)

    assert key("paired")[1] == "study:HI/paired"
    assert key("wide")[1] == key("old")[1] == "project:HI"
    s, k = key("codes")
    assert k == f"nocode:{s.sid}"  # without a code, nobody to meet
    assert key("codes", {"match": "abc"})[1] == key("paired", {"match": "abc"})[1] == "code:abc"


def test_paired_studies_scoped_to_the_study_do_not_meet_each_other(hani2_home):
    from hani2 import projects

    projects.create_project("HI", kind="assistant")
    projects.create_study("HI/a", study_mode="paired")
    projects.create_study("HI/b", study_mode="paired")
    a = make_session(user="alice", partner=None, study="HI/a", n_steps=10)
    b = make_session(user="bob", partner=None, study="HI/b", n_steps=10)
    assert a.match is not None and b.match is not None and a.match is not b.match
    c = make_session(user="carol", partner=None, study="HI/a", n_steps=10)
    assert c.match is a.match and a.match.paired


def test_a_paired_han_study_without_opponents_pairs_people_without_assistants(hani2_home):
    from hani2 import projects

    projects.create_project("HAN", kind="opponent")
    projects.create_study("HAN/p", study_mode="paired")
    a = make_session(user="alice", partner=None, study="HAN/p", n_steps=10)
    b = make_session(user="bob", partner=None, study="HAN/p", n_steps=10)
    assert a.opponent_pool() == ["human"]
    assert a.support_agent is None and b.support_agent is None
    assert a.match is not None and a.match is b.match


def test_group_files_are_checked_against_a_declared_mode(hani2_home):
    from hani2 import projects

    projects.create_project("HI", kind="assistant")
    projects.create_study("HI/p", study_mode="paired")
    projects.create_study("HI/s", study_mode="solo", opponents=["BoulwareTBNegotiator"])
    projects.create_study("HI/old", opponents=["BoulwareTBNegotiator"])
    for st in ("p", "s", "old"):
        ref = projects.StudyRef("HI", st)
        _group(ref, "mix", {"agents": ["human+assistant", "LinearTBNegotiator"]})
        _group(ref, "ai", {"agents": ["LinearTBNegotiator"]})
    # Paired: the group's AI entries are dropped; a group of AI only is refused (the study's pool)
    p = make_session(user="alice", partner=None, study="HI/p", query={"group": "mix"}, load=False)
    assert p.opponent_pool() == ["human+assistant"]
    p2 = make_session(user="bob", partner=None, study="HI/p", query={"group": "ai"}, load=False)
    assert p2.opponent_pool() == ["human+assistant"]
    # Solo: a group with a human entry is refused, and the study's pool is used
    s = make_session(user="carol", partner=None, study="HI/s", query={"group": "mix"}, load=False)
    assert s.opponent_pool() == ["BoulwareTBNegotiator"]
    s2 = make_session(user="dan", partner=None, study="HI/s", query={"group": "ai"}, load=False)
    assert s2.opponent_pool() == ["LinearTBNegotiator"]
    # no declared mode: the group file is used as it is (as before)
    o = make_session(user="erin", partner=None, study="HI/old", query={"group": "mix"}, load=False)
    assert o.opponent_pool() == ["human+assistant", "LinearTBNegotiator"]
    # an admin's ?opponents= is a test link: never checked
    adm = make_session(user="admin", partner=None, study="HI/s", is_admin=True, load=False,
                       query={"opponents": "human+assistant,LinearTBNegotiator"})
    assert adm.opponent_pool() == ["human+assistant", "LinearTBNegotiator"]


def test_a_schedule_slot_is_checked_against_a_declared_mode(hani2_home, monkeypatch):
    import json

    from hani2 import projects

    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "1")
    projects.create_project("HS", kind="assistant")
    projects.create_study("HS/s", type="prolific", practice=False, study_mode="solo", opponents=["BoulwareTBNegotiator"])
    ref = projects.StudyRef("HS", "s")
    d = projects.study_dir(ref) / "results" / "prolific_PA"
    d.mkdir(parents=True)
    (d / "schedule.json").write_text(json.dumps({"version": 2, "negotiations": [
        {"slot": 0, "agent_class_name": "human+assistant", "scenario_type": "Trade"}]}), encoding="utf-8")
    a = make_session(user="prolific_PA", mode="guest", partner=None, study=ref, query={"noautostart": "1"})
    assert a.round_plan["partner"] == "BoulwareTBNegotiator" and a.match is None
