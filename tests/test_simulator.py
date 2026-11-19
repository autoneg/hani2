"""Simulated participants (hani2.simulator), their isolation from human results, the
simulation metric, the simulator source of error_review and the pre-questionnaire."""

import json

import pandas as pd
import pytest
from conftest import write_settings

from hani2.recording.format import Recording
from hani2.simulator import (Follower, LLMPersona, Skeptic, Stubborn, Suggestion, View, conformance, make_persona,
                             run_trials, simulate)
from hani2.support_agent.runtime import SupportAgent

AGENT = "test_simulator:FillAgent"


class FillAgent(SupportAgent):
    """Fills in the opponent's current offer as its suggestion on every turn (no LLM)."""

    def on_event(self, event_name: str, nmi=None) -> None:
        if event_name != "action_requested":
            return
        ctx = self.context()
        if ctx["partner_offer"]:
            self.session_state["actions"]["set_offer"](ctx["partner_offer"])

    def handle_user_message(self, text: str) -> None:
        self.post(f"Noted: {text}")


class SilentAgent(SupportAgent):
    def on_event(self, event_name: str, nmi=None) -> None:
        pass


def _view(**kw):
    base = dict(issues=[], partner_offer={"x": 1}, partner_offer_utility=0.5, partner_message=None, reserved_value=0.2,
                relative_time=0.5, step=5, n_steps=10, history=[], suggestion=None, assistant_messages=[],
                own_next={"x": 2}, own_next_utility=0.7, best=1.0)
    base.update(kw)
    return View(**base)


# --------------------------------------------------------------------------- #
# Personas                                                                     #
# --------------------------------------------------------------------------- #
def test_scripted_personas_decide_as_specified():
    good = Suggestion("counter", offer={"x": 3}, utility=0.8)
    bad = Suggestion("counter", offer={"x": 4}, utility=0.3)
    assert Follower().decide(_view(suggestion=bad)).offer == {"x": 4}
    assert Follower().decide(_view()).kind == "counter"  # 0.5 < own 0.7
    sk = Skeptic()
    assert sk.decide(_view(suggestion=good)).took_suggestion
    a = sk.decide(_view(suggestion=bad))
    assert not a.took_suggestion and a.offer == {"x": 2}
    assert not sk.decide(_view(suggestion=Suggestion("accept"))).took_suggestion  # 0.5 < own 0.7
    st = Stubborn(max_concession=0.1)  # floor 0.9
    assert not st.decide(_view(suggestion=good)).took_suggestion
    assert st.decide(_view(partner_offer_utility=0.95, own_next_utility=0.92)).kind == "accept"
    assert make_persona("stubborn:max_concession=0.3").max_concession == 0.3
    assert make_persona({"kind": "skeptic", "seed": 3}).seed == 3
    with pytest.raises(ValueError):
        make_persona("nobody")


def test_conformance_flags_broken_rules():
    turns = [dict(turn=1, action="counter", utility=0.5, suggestion={"kind": "counter", "utility": 0.5},
                  took_suggestion=False, own_next_utility=0.7)]
    assert conformance({"kind": "follower"}, turns)
    assert not conformance({"kind": "skeptic"}, turns)
    sim = {"kind": "stubborn", "params": {"max_concession": 0.2}, "best_utility": 1.0, "reservation": 0.1}
    assert conformance(sim, turns)  # 0.5 < floor 0.8
    assert not conformance(sim, [dict(turns[0], utility=0.85)])


# --------------------------------------------------------------------------- #
# The runner and the tagging                                                   #
# --------------------------------------------------------------------------- #
def test_follower_takes_the_assistants_filled_offer_and_is_tagged(hani2_home):
    write_settings(hani2_home, "questionnaires/per_negotiation.yaml",
                   "questions:\n  - id: q\n    text: How?\n    type: text\n    required: true\n")
    t = simulate("follower", agent_class=AGENT, seed=1)
    assert t.valid and t.status == "success" and t.turns >= 1
    assert t.suggestions_seen >= 1 and t.suggestions_taken == t.suggestions_seen
    assert t.goal_met == (t.human_utility >= t.reservation)
    rec = Recording.load(t.recording)
    assert rec.header["session"]["mode"] == "simulated" and rec.header["session"]["user"] == "sim_follower"
    assert rec.first("sim")["kind"] == "follower" and rec.of("sim_turn") and rec.last("sim_end")["valid"]
    assert rec.questionnaire is None  # simulated participants never get questionnaires

    from hani2.evaluation import evaluate_recording

    row = evaluate_recording(rec, ["simulation"])["row"]
    assert row["mode"] == "simulated" and row["participant_type"] == "simulated-easy" and row["persona"] == "follower"
    assert row["sim_valid"] == 1 and row["sim_take_rate"] == 1.0 and row["sim_violations"] == 0

    from hani2.results import read_user_results

    res = read_user_results("sim_follower").iloc[-1]
    assert res["mode"] == "simulated" and res["participant_type"] == "simulated-easy" and res["persona"] == "follower"


def test_simulated_sessions_do_not_count_as_humans(hani2_home):
    from hani2 import assignment
    from hani2.testing import make_session

    s = make_session(user="sim_x", mode="simulated", agent_class=AGENT)
    try:
        assert not assignment.counts_as_human(s)
    finally:
        s.close()


def test_run_trials_reports_pass_hat_k(hani2_home):
    res = run_trials(["follower", "stubborn:max_concession=0.0"], k=2, agent_class=AGENT, n_steps=6)
    assert len(res["trials"]) == 4 and res["success"] == "goal_met"
    groups = {g["group"] for g in res["groups"]}
    assert groups == {"follower (easy) [simulated]", "stubborn (hard) [simulated]"}
    assert {r["k"] for r in res["reliability"]} == {1, 2}


def test_stubborn_never_goes_below_its_floor(hani2_home):
    t = simulate("stubborn:max_concession=0.15", agent_class=AGENT, seed=2, n_steps=8)
    sim = Recording.load(t.recording)
    floor = max(t.reservation, sim.first("sim")["best_utility"] - 0.15)
    assert all(e["utility"] is None or e["utility"] >= floor - 1e-6 for e in t.log)
    if t.agreement is not None:
        assert t.human_utility >= floor - 1e-6


# --------------------------------------------------------------------------- #
# Leaderboards                                                                 #
# --------------------------------------------------------------------------- #
def test_leaderboards_never_rank_simulated_with_humans_and_stratify_by_type():
    from hani2.results import is_simulated, leaderboard, leaderboard_by_type, simulated_leaderboard

    def rows(user, mode, ptype, utils, **kw):
        return [dict(user=user, mode=mode, participant_type=ptype, scenario="s", human_utility=u, **kw) for u in utils]

    df = pd.DataFrame(rows("alice", "main", "expert", [0.9, 0.8, 0.7]) + rows("bob", "main", "novice", [0.5, 0.4])
                      + rows("sim_follower", "simulated", "simulated-easy", [1.0, 1.0], persona="follower",
                             assistant="A", goal_met=True)
                      + rows("sim_stubborn", "simulated", "simulated-hard", [0.1, 0.9], persona="stubborn",
                             assistant="A", goal_met=[False, True][0]))
    lb = leaderboard(df)
    assert [r["user"] for r in lb] == ["alice", "bob"] and lb[0]["participant_type"] == "expert"
    strata = leaderboard_by_type(df)
    assert set(strata) == {"expert", "novice"} and [r["user"] for r in strata["novice"]] == ["bob"]
    sim = simulated_leaderboard(df)
    assert {r["persona"] for r in sim} == {"follower", "stubborn"}
    f = next(r for r in sim if r["persona"] == "follower")
    assert f["goal_rate"] == 1.0 and f["pass^2"] == 1.0 and f["participant_type"] == "simulated-easy"
    # rows written before the mode column existed count as human; sim_ users never do
    old = pd.DataFrame([dict(user="carol", scenario="s", human_utility=0.5), dict(user="sim_x", scenario="s", human_utility=1)])
    assert list(is_simulated(old)) == [False, True]
    assert [r["user"] for r in leaderboard(old)] == ["carol"]


def test_results_csv_gains_the_new_columns_after_old_rows(hani2_home):
    from hani2.config import results_root
    from hani2.results import read_user_results

    d = results_root() / "sim_follower"
    d.mkdir(parents=True)
    pd.DataFrame([dict(scenario="old", user="sim_follower", human_utility=0.1)]).to_csv(d / "results.csv", index=False)
    simulate("follower", agent_class=AGENT, n_steps=4)
    df = read_user_results("sim_follower")
    assert len(df) == 2 and df.iloc[-1]["mode"] == "simulated"


def test_compare_rows_keeps_simulated_groups_apart():
    from hani2.evaluation import compare_rows

    rows = [dict(support_agent="A", mode="main", scenario="s", agreement=1),
            dict(support_agent="A", mode="simulated", scenario="s", agreement=0)]
    out = compare_rows(rows, by="support_agent")
    assert {g["group"] for g in out["groups"]} == {"A", "A [simulated]"}
    assert {g["group"] for g in compare_rows(rows, by="mode")["groups"]} == {"main", "simulated"}


# --------------------------------------------------------------------------- #
# Language-model persona                                                       #
# --------------------------------------------------------------------------- #
def test_llm_persona_chats_discloses_follows_and_stops(hani2_home, monkeypatch):
    from hani2 import simulator

    prompts = []

    def fake(prompt, persona):
        prompts.append(prompt)
        n = len(prompts)
        if n == 1:
            return json.dumps({"say_to_assistant": "I mostly care about getting a fair deal.", "action": None})
        if n == 2:
            return json.dumps({"action": "follow", "message": "Let's settle."})
        return json.dumps({"say_to_assistant": "Thanks, I'm done. " + simulator.STOP, "action": None})

    monkeypatch.setattr(simulator, "CALL", fake)
    p = LLMPersona(goal="A fair deal.", reservation=0.0, max_chat_per_turn=1)
    t = simulate(p, agent_class=AGENT, n_steps=10)
    assert t.valid and t.turns >= 1
    assert "PRIVATE RESERVATION VALUE: 0.00" in prompts[0] and "A fair deal." in prompts[0]
    assert "Noted: I mostly care about getting a fair deal." in prompts[1]  # the Assistant's reply is shown
    rec = Recording.load(t.recording)
    chats = [c.get("text") for c in rec.of("chat")]
    assert "I mostly care about getting a fair deal." in chats
    assert not any(simulator.STOP in (c or "") for c in chats)  # the stop token never reaches the Assistant
    assert rec.first("sim")["kind"] == "llm" and rec.first("sim")["difficulty"] == "hard"


def test_llm_persona_model_failure_makes_the_trial_invalid(hani2_home, monkeypatch):
    from hani2 import simulator

    def broken(prompt, persona):
        raise RuntimeError("no model")

    monkeypatch.setattr(simulator, "CALL", broken)
    t = simulate(LLMPersona(), agent_class=AGENT, n_steps=6)
    assert not t.valid and t.invalid_reason == "simulator model failed"


# --------------------------------------------------------------------------- #
# error_review with a simulator source                                         #
# --------------------------------------------------------------------------- #
def test_error_review_has_a_simulator_source(hani2_home, monkeypatch):
    from hani2.evaluation import evaluate_recording, llm_judge

    t = simulate("skeptic", agent_class=AGENT, n_steps=6)
    rec = Recording.load(t.recording)
    seen = []

    def fake(prompt, settings):
        seen.append(prompt)
        return json.dumps({"errors": [{"source": "simulator", "time": "00:01", "severity": "critical"},
                                      {"source": "persona", "time": "00:02", "severity": "minor"},
                                      {"source": "assistant", "time": "00:03", "severity": "minor"}],
                           "overrides_helped": 0, "overrides_hurt": 0})

    monkeypatch.setattr(llm_judge, "CALL", fake)
    row = evaluate_recording(rec, ["error_review"], use_llm=True)["row"]
    assert "SIMULATED participant" in seen[0] and "skeptic" in seen[0]
    assert row["simulator_errors"] == 2 and row["simulator_critical_errors"] == 1
    assert row["assistant_errors"] == 1 and row["human_errors"] == 0 and row["first_critical"] == "simulator"


def test_error_review_of_human_sessions_is_unchanged(monkeypatch):
    from hani2.evaluation.llm_judge import _error_source

    assert _error_source("simulator", simulated=False) == "human"
    assert _error_source("the assistant", simulated=True) == "assistant"


# --------------------------------------------------------------------------- #
# Pre-questionnaire and participant type                                       #
# --------------------------------------------------------------------------- #
def test_pre_questionnaire_sets_the_participant_type_once(hani2_home):
    from hani2.testing import make_session

    write_settings(hani2_home, "env.json", {"pre_questionnaire": "expertise"})
    s = make_session(user="alice", agent_class="test_simulator:SilentAgent")
    try:
        assert s.phase == "questionnaire" and s.questionnaire["stage"] == "pre"
        s.start()
        assert s.phase == "questionnaire"  # nothing starts before it is answered
        assert not s.study.submit_questionnaire({})["ok"]
        assert s.study.submit_questionnaire({"expertise": "It is part of my job"})["ok"]
        assert s.phase == "ready" and s.ss["participant_type"] == "expert"
        s.start()
        s.wait_for_turn()
        s.end()
        s.wait_until_done()
        from hani2.results import read_user_results

        assert read_user_results("alice").iloc[-1]["participant_type"] == "expert"
    finally:
        s.close()
    s2 = make_session(user="alice", agent_class="test_simulator:SilentAgent")
    try:
        assert s2.phase == "ready" and s2.ss["participant_type"] == "expert"  # asked only once
    finally:
        s2.close()


def test_pre_questionnaire_is_opt_in_and_skips_simulated_and_admins(hani2_home):
    from hani2.testing import make_session

    s = make_session(user="bob", agent_class="test_simulator:SilentAgent")
    assert s.phase == "ready"
    s.close()
    write_settings(hani2_home, "env.json", {"pre_questionnaire": "expertise"})
    for kw in (dict(user="admin", is_admin=True), dict(user="sim_x", mode="simulated")):
        s = make_session(agent_class="test_simulator:SilentAgent", **kw)
        assert s.phase == "ready", kw
        s.close()


def test_participant_type_mapping():
    from hani2.study import participant_type_of

    spec = {"participant_type": {"question": "exp", "map": {"1": "novice", "5": "expert"}}}
    assert participant_type_of(spec, {"exp": 5}) == "expert"
    assert participant_type_of(spec, {"exp": 3}) == "3"
    assert participant_type_of(spec, {}) == ""
    assert participant_type_of({}, {"expertise": "Pro"}) == "Pro"
