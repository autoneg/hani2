"""Paired studies: match cells, the host's commit, the joiner's late binding, fallbacks (hani2.pairing)."""

import csv
import json
import sqlite3
import threading
import time
from types import SimpleNamespace

import pytest

from hani2 import assignment, matches, pairing, projects
from hani2.projects import StudyRef
from hani2.testing import make_session

HELLO = "level1_hello:HelloAgent"
RULES = "level2_rules:RulesAgent"
COACH = "level5_deal_coach:DealCoach"


@pytest.fixture(autouse=True)
def _empty_lobby():
    matches.LOBBY.clear()
    yield
    matches.LOBBY.clear()


def paired_study(name="HI/p", **fields):
    projects.create_project(name.split("/")[0], kind="assistant")
    fields.setdefault("type", "online")
    projects.create_study(name, study_mode="paired", **fields)
    return StudyRef(*name.split("/"))


def person(user, ref, load=True, **kw):
    kw.setdefault("n_steps", 10)
    return make_session(user=user, partner=None, study=ref, load=load, **kw)


def group(ref, key, data):
    d = projects.study_dir(ref) / "results" / "groups"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(json.dumps(data), encoding="utf-8")


def rows(s):
    with open(s.ss["user_path"] / "results.csv", newline="") as fh:
        return list(csv.DictReader(fh))


def spec(s):
    return s.assistant_choice.spec if s.assistant_choice is not None else None


def end_on_my_turn(s):
    """End an AI negotiation: ``end()`` is refused while it is not the human's turn (the opponent may
    move first), so wait for the turn and check that it was taken."""
    assert s.wait_for_turn() and s.end()


def play_out(a, b):
    """Both press Start, the first to move ends the negotiation (a completed match: no deal)."""
    a.start()
    b.start()
    assert a.wait(lambda: a.phase == "running" and b.phase == "running")
    first = a if a.wait_for_turn(2) and a.is_my_turn() else b
    assert first.end()
    assert a.wait_until_done() and b.wait_until_done()


# --------------------------------------------------------------------------- #
# The cell store                                                               #
# --------------------------------------------------------------------------- #
def test_cell_keys_are_canonical_by_side():
    k = assignment.cell_key("Trade", "a.b:A", "")
    assert k == "Trade|a.b:A@0|none@1"
    assert assignment.parse_cell(k) == ("Trade", "a.b:A", "none")


def test_only_completed_matches_fill_a_cell(hani2_home):
    ref = paired_study()
    key = assignment.cell_key("Trade", HELLO, RULES)
    with assignment.cell_store(ref) as d:
        assignment.reserve_cell(d, "m1", key, scenario_type="Trade", sides={0: (HELLO, 0), 1: (RULES, 2)})
        assignment.reserve_cell(d, "m2", key, scenario_type="Trade", sides={0: (HELLO, 1), 1: (RULES, 0)})
    d = assignment.read_cells(ref)
    assert assignment.cell_count(d, key) == 2 and not d["cells"]  # in flight: counted when choosing
    assert assignment.assistant_scenario_count(d, RULES, "Trade") == 2
    # m1: both rows clean -> completed once (a repeated report changes nothing)
    assert assignment.cell_row_written(ref, "m1", 0, True) == "waiting"
    assert assignment.cell_row_written(ref, "m1", 1, True) == "completed"
    assert assignment.cell_row_written(ref, "m1", 1, True) == ""
    # m2: one row abandoned -> released, fills nothing
    assert assignment.cell_row_written(ref, "m2", 0, False) == "released"
    assert assignment.cell_row_written(ref, "m2", 1, True) == ""
    d = assignment.read_cells(ref)
    assert d["cells"][key]["completed"] == 1 and d["cells"][key]["match_ids"] == ["m1"]
    assert d["inflight"] == {}
    assert d["positions"] == {HELLO: [1], RULES: [0, 0, 1]}
    assert json.loads(assignment.cells_path(ref).read_text())["version"] == 1


def test_stale_in_flight_matches_are_dropped(hani2_home):
    ref = paired_study()
    with assignment.cell_store(ref) as d:
        assignment.reserve_cell(d, "old", "Trade|a@0|b@1", ttl=1)
        d["inflight"]["old"]["expires"] = time.time() - 1
        assignment.reserve_cell(d, "new", "Trade|a@0|b@1", ttl=60)
    assert set(assignment.read_cells(ref)["inflight"]) == {"new"}
    assert assignment.release_cell(ref, "new") and not assignment.read_cells(ref)["inflight"]


# --------------------------------------------------------------------------- #
# The joiner's choice (unit)                                                   #
# --------------------------------------------------------------------------- #
def _host(assistant, remaining=None, scenario="Trade", index=0, ref=None, counted=False, same_ok=False):
    h = SimpleNamespace(_pair_ctx={"assistant": assistant, "remaining": remaining or [assistant],
                                   "scenario": scenario, "scenario_type": scenario, "ref": ref,
                                   "counted": counted, "position": 0, "same_ok": same_ok},
                        assistant_choice=None)
    return matches.Match("k", h, index, None, {"scenario_type": scenario}, None, None, True, True)


def _ctx(remaining, **kw):
    return {"assign": "cells", "slack": 0, "same_ok": False, "remaining": remaining, "ref": None,
            "counted": False, "position": 0, "by_type": False, "own_type": "Trade", "code": False, **kw}


def test_the_joiner_never_takes_the_hosts_assistant():
    m = _host(HELLO)
    assert pairing.selector(_ctx([HELLO]))([m]) is None  # only the host's Assistant left: no fit
    got = pairing.selector(_ctx([HELLO, RULES]))([m])
    assert got is m and m.ctx[1]["assistant"] == RULES
    assert m.cell == assignment.cell_key("Trade", HELLO, RULES)
    assert pairing.selector(_ctx([HELLO], same_ok=True))([_host(HELLO, same_ok=True)]) is not None


def test_the_joiner_prefers_the_most_constrained_host():
    wide, narrow = _host(HELLO, [HELLO, COACH, RULES]), _host(HELLO, [HELLO])
    for _ in range(10):
        assert pairing.selector(_ctx([RULES]))([wide, narrow]) is narrow


def test_order_takes_only_the_next_planned_assistant():
    m = _host(RULES)
    assert pairing.selector(_ctx([RULES, COACH], assign="order"))([m]) is None
    assert pairing.selector(_ctx([COACH, RULES], assign="order"))([m]) is m


def test_by_participant_joiners_fit_hosts_of_their_own_type():
    m = _host(HELLO, scenario="Island")
    assert pairing.selector(_ctx([RULES], by_type=True, own_type="Trade"))([m]) is None
    assert pairing.selector(_ctx([RULES], by_type=True, own_type="Island"))([m]) is m


def test_cell_counts_and_slack_decide(hani2_home):
    ref = paired_study()
    full = assignment.cell_key("Trade", HELLO, RULES)
    with assignment.cell_store(ref) as d:
        d["cells"][full] = {"completed": 1, "match_ids": ["x"], "type": "Trade"}
    for _ in range(10):  # strict: the empty cell (HELLO against COACH)
        m = _host(HELLO, ref=ref)
        pairing.selector(_ctx([RULES, COACH], ref=ref))([m])
        assert m.ctx[1]["assistant"] == COACH
    picks = set()
    for _ in range(40):  # slack 1: both tied on the count; the position counts are equal: chance
        m = _host(HELLO, ref=ref)
        pairing.selector(_ctx([RULES, COACH], ref=ref, slack=1))([m])
        picks.add(m.ctx[1]["assistant"])
    assert picks == {RULES, COACH}


def test_the_host_commits_the_emptiest_assistant_and_type(hani2_home):
    ref = paired_study()
    with assignment.cell_store(ref) as d:
        d["cells"][assignment.cell_key("Trade", HELLO, RULES)] = {"completed": 2, "match_ids": [], "type": "Trade"}
        d["cells"][assignment.cell_key("Island", COACH, HELLO)] = {"completed": 1, "match_ids": [], "type": "Island"}
    ctx = {"remaining": [HELLO, COACH], "ref": ref, "position": 0, "assign": "cells"}
    assert pairing.commit(ctx, ["Trade"], "Trade") == (COACH, "Trade")
    assert pairing.commit(ctx, ["Trade", "Island"], "Trade") == (COACH, "Trade")
    assert pairing.commit({**ctx, "remaining": [HELLO]}, ["Trade", "Island"], "Trade") == (HELLO, "Island")
    assert pairing.commit({**ctx, "assign": "order"}, ["Trade"], "Trade")[0] == HELLO


# --------------------------------------------------------------------------- #
# In a study                                                                    #
# --------------------------------------------------------------------------- #
def test_a_paired_match_fills_one_cell_and_records_both_sides(hani2_home):
    ref = paired_study(assistants=[HELLO, RULES, COACH], scheduling={"assistants": "latin_square"},
                       n_required=3)
    a = person("alice", ref)
    assert a.match is not None and not a.match.paired
    host_a = spec(a)
    assert host_a in (HELLO, RULES, COACH) and a.support_agent is not None  # live while waiting
    b = person("bob", ref)
    assert b.match is a.match and a.match.paired
    assert spec(b) != host_a  # chosen at pairing, never the host's
    key = a.match.cell
    assert assignment.parse_cell(key)[0] == a.ss["scenario_type"]
    assert set(assignment.read_cells(ref)["inflight"]) == {a.match.id}
    assert b.round_plan["scenario_scheduling"] == "host"
    play_out(a, b)
    d = assignment.read_cells(ref)
    assert d["inflight"] == {} and d["cells"][key]["completed"] == 1
    used = assignment.read_assignments(ref)["humans"]
    assert used["alice"]["used_assistants"] == [[host_a, a.match.id]]
    assert used["bob"]["used_assistants"] == [[spec(b), a.match.id]]
    ra, rb = rows(a)[-1], rows(b)[-1]
    for r in (ra, rb):
        assert r["study_mode"] == "paired" and r["pairing"] == "cells" and r["match_cell"] == key
        assert r["assistant_position"] == "0" and r["plan_size"] == "3" and r["cross_study"] == "False"
    assert {ra["side"], rb["side"]} == {"0", "1"} and ra["side"] == ra["human_index"]
    assert ra["opponent_assistant"] == spec(b) and rb["opponent_assistant"] == host_a
    assert ra["opponent_participant"] == "1" and rb["opponent_participant"] == "0"
    sides = {int(ra["side"]): host_a, int(rb["side"]): spec(b)}
    assert key == assignment.cell_key(ra["scenario_type"], sides[0], sides[1])
    # the next match: neither uses an Assistant again (at most once per person)
    a.load()
    b.load()
    assert b.match is a.match
    assert spec(a) != host_a and spec(b) not in (used["bob"]["used_assistants"][0][0], spec(a))
    assert rows(a)[-1]["assistant_position"] == "0"
    assert a.ss["assistant_position"] == 1 and b.ss["assistant_position"] == 1


def test_same_assistant_matches_are_not_formed_unless_allowed(hani2_home):
    for allow, name in ((False, "HI/no"), (True, "HI/yes")):
        ref = paired_study(name, assistants=[HELLO, RULES], scheduling={"assistants": "round_robin"},
                           pairing={"allow_same_assistant": allow})
        group(ref, "hello", {"agents": ["human+assistant"], "assistant": HELLO})
        a = person("alice", ref, query={"group": "hello"})
        c = person("carol", ref, query={"group": "hello"})
        assert spec(a) == spec(c) == HELLO
        assert (c.match is a.match) is allow
        matches.LOBBY.clear()


def test_a_single_assistant_pool_pairs_anyway(hani2_home):
    ref = paired_study()  # no assistants: one (the configured) Assistant for everybody
    a = person("alice", ref)
    b = person("bob", ref)
    assert b.match is a.match and spec(a) == spec(b)


def test_two_joiners_arriving_together_take_different_cells(hani2_home, monkeypatch):
    from hani2 import scenario_store as store

    ref = paired_study(assistants=[HELLO, RULES, COACH], scheduling={"assistants": "random_each"},
                       pairing={"slack": 0}, scenario_set=None)
    group(ref, "hello", {"agents": ["human+assistant"], "assistant": HELLO})
    h1 = person("h1", ref, query={"group": "hello"})
    h2 = person("h2", ref, query={"group": "hello"})
    assert h1.match is not h2.match and h1.human_index == h2.human_index
    j1, j2 = person("j1", ref, load=False), person("j2", ref, load=False)
    real = store.load_scenario

    def slow(*args, **kw):
        time.sleep(0.2)
        return real(*args, **kw)

    monkeypatch.setattr(store, "load_scenario", slow)
    ts = [threading.Thread(target=s.load) for s in (j1, j2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert {id(j1.match), id(j2.match)} == {id(h1.match), id(h2.match)}  # each host got one joiner
    assert HELLO not in (spec(j1), spec(j2))
    inflight = assignment.read_cells(ref)["inflight"]
    assert set(inflight) == {h1.match.id, h2.match.id}  # one reservation per match
    assert h1.match.cell != h2.match.cell  # the second saw the first's cell in flight
    assert {e["cell"] for e in inflight.values()} == {h1.match.cell, h2.match.cell}


def test_one_host_and_two_joiners_together(hani2_home):
    ref = paired_study(assistants=[HELLO, RULES, COACH], scheduling={"assistants": "random_each"})
    h = person("h", ref)
    j1, j2 = person("j1", ref, load=False), person("j2", ref, load=False)
    ts = [threading.Thread(target=s.load) for s in (j1, j2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    joined = [j for j in (j1, j2) if j.match is h.match]
    assert len(joined) == 1 and h.match.paired
    other = j2 if joined[0] is j1 else j1
    assert other.match is not None and not other.match.paired  # waits as a host
    assert set(assignment.read_cells(ref)["inflight"]) == {h.match.id}


def test_abandoned_and_separated_matches_release_their_cells(hani2_home):
    ref = paired_study(assistants=[HELLO, RULES, COACH], scheduling={"assistants": "latin_square"},
                       n_required=3)
    # separated before the start: released
    a, b = person("alice", ref), person("bob", ref)
    assert b.match is a.match and a.match.cell_ref is not None
    b.close()
    assert assignment.read_cells(ref)["inflight"] == {} and a.match.cell is None
    assert "used_assistants" not in assignment.read_assignments(ref)["humans"]["bob"]
    # abandoned after the start: released, nothing filled, both Assistants used
    c = person("carol", ref)
    assert c.match is a.match
    a.start()
    c.start()
    assert a.wait(lambda: a.phase == "running" and c.phase == "running")
    mover = a if a.wait_for_turn(2) and a.is_my_turn() else c
    stayer = c if mover is a else a
    mid = a.match.id
    mover.close()
    assert stayer.wait_until_done()
    assert rows(stayer)[-1]["abandoned"] == "opponent"
    d = assignment.read_cells(ref)
    assert d["inflight"] == {} and d["cells"] == {}
    humans = assignment.read_assignments(ref)["humans"]
    assert [m for _a, m in humans["alice"]["used_assistants"]] == [mid]
    assert [m for _a, m in humans["carol"]["used_assistants"]] == [mid]


def test_nobody_fits_ai_fallback(hani2_home):
    ref = paired_study(assistants=[HELLO, RULES], scheduling={"assistants": "latin_square"}, n_required=2,
                       pairing={"fallback": "ai", "fallback_opponents": ["BoulwareTBNegotiator"]})
    a = person("alice", ref, load=False)
    a.admin_prefs["human_opponent_wait"] = 0.3
    a.load()
    first = spec(a)
    with a.lock:  # the fallback sets both under the lock: it waited, or the timer fired already
        assert a.ss.get("match_id") or a.ss["pairing"] == "fallback"
    a.start()
    assert a.wait(lambda: a.phase == "running", 10)
    assert a.match is None and a.ss["last_partner_type"] == "BoulwareTBNegotiator"
    assert spec(a) == first  # the committed Assistant plays the AI
    end_on_my_turn(a)
    assert a.wait_until_done()
    r = rows(a)[-1]
    assert (r["study_mode"], r["opponent_kind"], r["pairing"], r["match_cell"]) == ("paired", "agent", "fallback", "")
    assert [x for x, _m in assignment.read_assignments(ref)["humans"]["alice"]["used_assistants"]] == [first]
    assert assignment.read_cells(ref) == {"version": 1, "cells": {}, "inflight": {}, "positions": {}}
    a.load()
    assert spec(a) != first  # used: the next one


def test_nobody_fits_wait_keeps_waiting(hani2_home):
    ref = paired_study(pairing={"fallback": "wait"})
    a = person("alice", ref, load=False)
    a.admin_prefs["human_opponent_wait"] = 0.2
    a.load()
    m = a.match
    assert not a._can_play_ai_instead()
    assert not a.choose_opponent_kind("ai")["ok"]
    time.sleep(0.8)
    assert a.match is m and matches.LOBBY.n_waiting() == 1
    b = person("bob", ref)
    assert b.match is m


def test_nobody_fits_end_skips_to_the_next_assistant_then_finishes(hani2_home):
    ref = paired_study(assistants=[HELLO, RULES], scheduling={"assistants": "latin_square"}, n_required=2,
                       pairing={"fallback": "end"})
    a = person("alice", ref, load=False)
    a.admin_prefs["human_opponent_wait"] = 0.3
    a.load()
    first = spec(a)
    assert a.wait(lambda: a.match is not None and spec(a) != first, 10)  # skipped, the next one waits
    assert a.wait(lambda: a.phase == "finished", 10)  # nothing left: the study ends early
    h = assignment.read_assignments(ref)["humans"]["alice"]
    assert sorted(h["skipped_assistants"]) == sorted([HELLO, RULES]) and "used_assistants" not in h
    assert matches.LOBBY.n_waiting() == 0


def test_by_participant_people_meet_only_their_own_scenario_type(hani2_home):
    from hani2 import scenario_store as store

    ref = paired_study(scheduling={"scenarios": "by_participant"})
    n_types = len(store.scenario_order(None))
    people = [person(f"p{i}", ref, load=False) for i in range(n_types + 1)]
    for s in people:
        assignment.participant_index(s)  # 0, 1, …: the first and the last share the first type
    for s in people:
        s.load()
    first, last = people[0], people[-1]
    assert first.ss["scenario_type"] == last.ss["scenario_type"]
    assert last.match is first.match and last.round_plan["scenario_scheduling"] == "host"
    for s in people[1:-1]:  # every other type waits alone
        assert s.match is not None and not s.match.paired and s.ss["scenario_type"] != first.ss["scenario_type"]


def test_paired_rows_in_the_scenario_started_event_and_evaluation_fields(hani2_home):
    from hani2.evaluation import ID_FIELDS, PAIRED_FIELDS
    from hani2.results import PAIRED_COLUMNS

    assert set(PAIRED_COLUMNS) <= set(PAIRED_FIELDS) <= set(ID_FIELDS)
    ref = paired_study()
    a, b = person("alice", ref), person("bob", ref)
    play_out(a, b)
    assert set(PAIRED_COLUMNS) <= set(a._paired_columns())
    assert a._paired_columns()["match_cell"] == a.match.cell


def test_solo_rows_carry_position_and_plan_size(hani2_home):
    projects.create_project("HS", kind="assistant")
    projects.create_study("HS/s", type="online", study_mode="solo", opponents=["BoulwareTBNegotiator"],
                          n_required=4)
    s = make_session(user="sam", partner=None, study="HS/s", n_steps=4)
    s.start()
    end_on_my_turn(s)
    assert s.wait_until_done()
    r = rows(s)[-1]
    assert (r["study_mode"], r["pairing"], r["assistant_position"], r["plan_size"]) == ("solo", "", "0", "4")
    assert r["match_cell"] == "" and r["opponent_assistant"] == ""
    out = make_session(user="nobody", n_steps=4)  # outside a study: empty
    out.start()
    end_on_my_turn(out)
    assert out.wait_until_done()
    r = rows(out)[-1]
    assert (r["study_mode"], r["assistant_position"], r["plan_size"]) == ("", "", "")


def test_mixed_studies_keep_the_random_lobby(hani2_home):
    projects.create_project("HM", kind="assistant")
    projects.create_study("HM/g", type="online", study_mode="mixed",
                          opponents=["human+assistant", "BoulwareTBNegotiator"])
    a = make_session(user="alice", partner=None, study="HM/g", n_steps=10, load=False)
    b = make_session(user="bob", partner=None, study="HM/g", n_steps=10, load=False)
    for s in (a, b):
        s.admin_prefs["human_opponents_first"] = True
        s.load()
    assert pairing.settings(a) is None and a._pair_ctx is None
    assert b.match is a.match and a.match.cell is None
    assert not assignment.cells_path(StudyRef("HM", "g")).exists()


def test_balance_report_has_a_paired_part(hani2_home):
    from typer.testing import CliRunner

    from hani2 import balance
    from hani2.cli import app

    ref = paired_study(assistants=[HELLO, RULES, COACH], scheduling={"assistants": "latin_square"},
                       n_required=3)
    a, b = person("alice", ref), person("bob", ref)
    play_out(a, b)
    rep = balance.study_balance(ref)
    p = rep["paired"]
    assert p["mode"] == "paired" and p["matches"] == 1 and p["inflight"] == 0
    assert p["cells"][a.match.cell] == 1 and sum(p["cells"].values()) == 1
    assert p["expected_cells"] == 3 * 3 * 2 and p["empty_cells"] == 17  # S·N(N−1)
    assert sum(p["totals"].values()) == 2 and p["same_assistant_matches"] == 0
    assert sorted(p["incomplete"]) == ["alice", "bob"]  # 1 of 3
    assert sum(x["n"] for x in p["pairs"]) == 0  # each used one Assistant so far
    text = balance.render(rep)
    assert "Paired balance" in text and "Match cells" in text
    out = CliRunner().invoke(app, ["study", "balance", str(ref)])
    assert out.exit_code == 0, out.output
    assert "Paired balance" in out.output
    projects.create_study("HI/solo", type="online", study_mode="solo", opponents=["BoulwareTBNegotiator"])
    assert balance.study_balance(StudyRef("HI", "solo"))["paired"] is None


def test_an_assistant_error_is_shown_not_taken_for_a_finished_study(hani2_home):
    ref = paired_study(assistants=["no_such_module:Nothing"], scheduling={"assistants": "latin_square"},
                       n_required=1)
    a = person("alice", ref)
    assert a.phase != "finished" and not a.__dict__.get("_paired_exhausted")
    assert a.assistant_error or (a.assistant_choice is not None and a.assistant_choice.error)
    # a pool that names no Assistant at all (the error comes from the pool itself)
    ctx = pairing.context(a, {}, "Trade", {**pairing.settings(a)})
    assert ctx["late"] or ctx["method"] != "error"
    orig = assignment.assistant_pool
    try:
        assignment.assistant_pool = lambda *x, **k: assignment.AssistantChoice(spec=None, error="broken")
        ctx = pairing.context(a, {}, "Trade", {**pairing.settings(a)})
        assert ctx["method"] == "error" and not ctx["late"]  # built before pairing: the error shows
    finally:
        assignment.assistant_pool = orig


def test_the_two_people_left_with_the_same_assistant_both_fall_back(hani2_home):
    ref = paired_study(assistants=[HELLO, RULES], scheduling={"assistants": "round_robin"},
                       pairing={"fallback": "ai", "fallback_opponents": ["BoulwareTBNegotiator"]})
    group(ref, "hello", {"agents": ["human+assistant"], "assistant": HELLO})
    people = [person(u, ref, load=False, query={"group": "hello"}) for u in ("alice", "carol")]
    for s in people:
        s.admin_prefs["human_opponent_wait"] = 0.3
        s.load()
    a, c = people
    assert a.match is not None and c.match is not None and a.match is not c.match  # nobody fits
    for s in people:
        s.start()
    assert a.wait(lambda: a.phase == "running" and c.phase == "running", 10)
    assert a.match is None and c.match is None
    for s in people:
        end_on_my_turn(s)
        assert s.wait_until_done()
        assert rows(s)[-1]["pairing"] == "fallback"
    d = assignment.read_cells(ref)
    assert d["cells"] == {} and d["inflight"] == {}


def test_a_host_leaving_before_the_start_leaves_the_joiner_hosting_the_real_scenario(hani2_home):
    ref = paired_study(assistants=[HELLO, RULES, COACH], scheduling={"assistants": "latin_square"},
                       n_required=3)
    a, b = person("alice", ref), person("bob", ref)
    assert b.match is a.match
    played = b.ss["scenario_type"]
    a.close()
    assert b.match is not None and not b.match.paired
    assert b.match.scenario_type == played
    assert b.match.ctx[b.match.host_index()]["assistant"] == spec(b)
    c = person("carol", ref)
    assert c.match is b.match and spec(c) != spec(b)
    assert assignment.parse_cell(b.match.cell)[0] == played == c.ss["scenario_type"]
    assert set(assignment.read_cells(ref)["inflight"]) == {b.match.id}


def test_a_mixed_game_with_cells_balances_and_may_share_an_assistant(hani2_home):
    projects.create_project("HG", kind="assistant")
    projects.create_study("HG/play", type="online", study_mode="mixed",
                          opponents=["human+assistant", "BoulwareTBNegotiator"],
                          assistants=[HELLO, RULES], scheduling={"assistants": "balanced"},
                          pairing={"assign": "cells", "allow_same_assistant": True})
    ref = StudyRef("HG", "play")
    group(ref, "team", {"agents": ["human+assistant", "BoulwareTBNegotiator"], "assistant": HELLO})
    a = make_session(user="inviter", partner=None, study=ref, n_steps=10, load=False, query={"group": "team"})
    g = make_session(user="guest1", partner=None, study=ref, n_steps=10, load=False, query={"group": "team"})
    for s in (a, g):
        s.admin_prefs["human_opponents_first"] = True
        s.load()
    assert pairing.settings(a) is not None and not a._pair_ctx["late"]
    assert g.match is a.match and spec(a) == spec(g) == HELLO
    assert a.match.cell == assignment.cell_key(a.ss["scenario_type"], HELLO, HELLO)
    play_out(a, g)
    assert rows(a)[-1]["pairing"] == rows(g)[-1]["pairing"] == "cells"
    assert assignment.read_cells(ref)["cells"][a.match.cell]["completed"] == 1


def test_same_assistant_filter_holds_when_assistants_come_from_group_files_only(hani2_home):
    ref = paired_study()  # no assistants key: the Assistants come from the group files
    group(ref, "hello", {"agents": ["human+assistant"], "assistant": HELLO})
    a = person("alice", ref, query={"group": "hello"})
    c = person("carol", ref, query={"group": "hello"})
    assert spec(a) == spec(c) == HELLO and c.match is not a.match


def test_evaluation_rows_from_recordings_carry_the_paired_fields(hani2_home):
    """The rows built from a Paired match's recordings carry its ID fields (not only the CSV)."""
    from hani2.evaluation import evaluate_paths, leaderboard

    ref = paired_study()
    a, b = person("alice", ref), person("bob", ref)
    play_out(a, b)
    ev = evaluate_paths([projects.study_dir(ref)], ["outcome"])
    got = sorted((r for r in ev["rows"] if r.get("match_id")), key=lambda r: r["side"])
    assert len(got) == 2, ev["errors"]
    for r in got:
        assert r["study_mode"] == "paired" and r["pairing"] == "cells" and r["match_id"] == a.match.id
        assert r["match_cell"] == a.match.cell and r["opponent_kind"] == "human+assistant"
        assert r["plan_size"] is not None and r["assistant_position"] is not None
    assert [r["side"] for r in got] == [0, 1]
    assert got[0]["opponent_participant"] is not None and got[0]["opponent_assistant"]
    lb = leaderboard(ev["rows"], "hi", "outcome", n_boot=0)
    assert lb["strata"] == {"solo": 0, "paired": 2} and lb["totals"]["sessions"] == 1
    assert lb["totals"]["matches"] == 1 and lb["cells"][-2:] == ["side", "opponent_assistant"]


# --------------------------------------------------------------------------- #
# A shrunk pool never gives a person an Assistant they used                     #
# --------------------------------------------------------------------------- #
def _set_pool(ref, assistants, **scheduling):
    f = projects.study_dir(ref) / projects.STUDY_FILE
    data = projects.read_yaml(f)
    data["assistants"] = assistants
    if scheduling:
        data["scheduling"] = {**(data.get("scheduling") or {}), **scheduling}
    projects.write_yaml(f, data)


@pytest.mark.parametrize("method", ["latin_square", "balanced_subset"])
def test_paired_shrunk_pool_does_not_repeat_and_finishes_early(hani2_home, method):
    ref = paired_study(assistants=[HELLO, RULES], scheduling={"assistants": method}, n_required=2)
    a = person("alice", ref, load=False)
    rest, _m = assignment.remaining_assistants(a, a.assistant_settings, {})
    assert sorted(rest) == sorted([HELLO, RULES])
    assignment.mark_used(a, rest[0], "m1")
    _set_pool(ref, [rest[0]])  # the Assistant alice has not used left the pool
    assert assignment.remaining_assistants(a, a.assistant_settings, {})[0] == []  # not the used one again
    a.load()
    assert a.phase == "finished" and matches.LOBBY.n_waiting() == 0
    db = sqlite3.connect(projects.study_dir(ref) / "results" / "events.db")
    assert db.execute("SELECT COUNT(*) FROM events WHERE action='finished_early'").fetchone()[0] == 1
    _set_pool(ref, [rest[0]], assistant_repeats=True)
    assert assignment.remaining_assistants(a, a.assistant_settings, {})[0] == [rest[0]]  # repeats: wraps


def test_paired_replan_fills_open_slots_from_unused(hani2_home):
    ref = paired_study(assistants=[HELLO, RULES, COACH], scheduling={"assistants": "balanced_subset"},
                       n_required=2)
    a = person("bob", ref, load=False)
    rest, _m = assignment.remaining_assistants(a, a.assistant_settings, {})
    assignment.mark_used(a, rest[0], "m1")
    _set_pool(ref, [x for x in (HELLO, RULES, COACH) if x != rest[1]])
    new, _m = assignment.remaining_assistants(a, a.assistant_settings, {})
    assert new == [x for x in (HELLO, RULES, COACH) if x not in rest[:2]]
    assert assignment.read_assignments(ref)["humans"]["bob"]["assistant_plan"][0] == rest[0]
