"""Hand-worked validation of system_use, engagement_flags, assistant_interaction, simulation, dual_control.

Every expected value is derived by hand from the metric's written definition (see the comments)."""

import pytest

from hani2.evaluation import evaluate_recording
from hani2.recording.format import Recording

HEADER = {"k": "header", "format": "hani2-recording", "version": 1, "id": "v", "t0": 0}
ISSUES = ["x", "y"]


def rec(*records, scenario=None):
    sc = {"t": 0, "k": "scenario", "name": "toy", "human_index": 0, "issue_names": ISSUES}
    if scenario:
        sc.update(scenario)
    return Recording.from_records([HEADER, sc, {"t": 0.5, "k": "start", "human_index": 0, "human_id": "H"},
                                   *records])


def run(r, metrics, **options):
    return evaluate_recording(r, metrics, options=options)["row"]


def draft(t, by, **values):
    return {"t": t, "k": "draft", "by": by, "values": values or None}


def act(t, actor, typ, offer=None):
    d = {"t": t, "k": "act", "actor": actor, "type": typ}
    if offer is not None:
        d["offer"] = offer
    return d


def chat(t, user, text="m"):
    return {"t": t, "k": "chat", "user": user, "text": text}


def check(row, expected):
    for k, v in expected.items():
        if v is None:
            assert row.get(k) is None, k
        else:
            assert row.get(k) == pytest.approx(v), k


# --------------------------------------------------------------------------- #
# system_use                                                                   #
# --------------------------------------------------------------------------- #
def test_system_use_documented_example():
    # Doc example: Assistant suggests X, Human sends X (adopted, 0 drafts before);
    # Assistant suggests Y, Human tries two offers, sends Z (ignored, 2 drafts before).
    # n_suggestions=2, adoption=1/2, ignored=1, explored=2, per_action=(0+2)/2=1.
    # No chat, no tools -> 0 counts; all seat actions by human -> shares 1, 0, 0.
    expected = {"n_user_messages": 0, "n_assistant_messages": 0, "n_suggestions": 2,
                "suggestion_adoption": 0.5, "suggestions_ignored": 1, "drafts_explored": 2,
                "drafts_per_action": 1.0, "n_tool_interactions": 0, "n_tools_used": 0, "n_tab_changes": 0,
                "actions_by_human": 1.0, "actions_by_agent": 0.0, "actions_by_autopilot": 0.0}
    r = rec(draft(1, "agent", x="A", y=1), act(2, "human", "offer", ["A", 1]),
            draft(3, "agent", x="B", y=2), draft(4, "human", x="B", y=3), draft(5, "human", x="C", y=3),
            act(6, "human", "offer", ["C", 3]))
    check(run(r, ["system_use"]), expected)


def test_system_use_mixed_actors_chat_and_tools():
    # chat: 1 by "You", 2 by "Assistant" -> n_user 1, n_assistant 2.
    # agent drafts: t4 (offer), t7 (offer), t8 (message-only, no values) -> n_suggestions 3
    #   (the doc: drafted messages count too).
    # The Assistant acts at t5 -> clears the pending suggestion; Human offer t6 follows none -> not counted.
    # Human text t9 does not clear the suggestion; autopilot t10 does. After_sugg = 0 -> adoption empty, ignored 0.
    # Human drafts: one (t10.5) before the Human's end (t11) -> explored 1.
    # per_action: human actions are t6 (0 drafts), t9 (0), t11 (1) -> mean 1/3.
    # Seat actions: agent, human, human(text), autopilot, human(end) = 5 -> human 3/5, agent 1/5, autopilot 1/5.
    # Tools: 3 interactions on components slider, slider, btn -> 3 interactions, 2 tools; 2 tab changes.
    expected = {"n_user_messages": 1, "n_assistant_messages": 2, "n_suggestions": 3,
                "suggestion_adoption": None, "suggestions_ignored": 0, "drafts_explored": 1,
                "drafts_per_action": 1 / 3, "n_tool_interactions": 3, "n_tools_used": 2, "n_tab_changes": 2,
                "actions_by_human": 0.6, "actions_by_agent": 0.2, "actions_by_autopilot": 0.2}
    r = rec(chat(1, "You"), chat(2, "Assistant"), chat(3, "Assistant"),
            draft(4, "agent", x="A", y=1), act(5, "agent", "offer", ["A", 1]),
            act(6, "human", "offer", ["B", 2]),
            draft(7, "agent", x="C", y=3), draft(8, "agent"),
            act(9, "human", "text"), act(10, "autopilot", "offer", ["C", 3]),
            draft(10.5, "human", x="D", y=4), act(11, "human", "end"),
            {"t": 12, "k": "ev", "type": "tool_interaction", "component": "slider"},
            {"t": 13, "k": "ev", "type": "tool_interaction", "component": "slider"},
            {"t": 14, "k": "ev", "type": "tool_interaction", "component": "btn"},
            {"t": 15, "k": "ev", "type": "tab_changed"}, {"t": 16, "k": "ev", "type": "tab_changed"})
    check(run(r, ["system_use"]), expected)


def test_system_use_text_does_not_clear_pending_suggestion():
    # Suggestion S1=[A,1]; Human text; Human offers [A,1] -> adopted (1 of 1).
    # Suggestion S2=[B,2]; Human offers [B,2] -> adopted. Suggestion S3; Human offers different -> ignored.
    # adopted 2, ignored 1 -> 2/3. n_suggestions 3.
    expected = {"n_suggestions": 3, "suggestion_adoption": 2 / 3, "suggestions_ignored": 1,
                "drafts_per_action": 0.0, "actions_by_human": 1.0}
    r = rec(draft(1, "agent", x="A", y=1), act(2, "human", "text"), act(3, "human", "offer", ["A", 1]),
            draft(4, "agent", x="B", y=2), act(5, "human", "offer", ["B", 2]),
            draft(6, "agent", x="C", y=3), act(7, "human", "offer", ["C", 9]))
    check(run(r, ["system_use"]), expected)


def test_system_use_no_seat_actions():
    # No seat actions: the shares are empty, no per-action mean.
    expected = {"actions_by_human": None, "actions_by_agent": None, "actions_by_autopilot": None,
                "drafts_per_action": None, "suggestion_adoption": None}
    check(run(rec(chat(1, "Assistant")), ["system_use"]), expected)


# --------------------------------------------------------------------------- #
# engagement_flags                                                             #
# --------------------------------------------------------------------------- #
def _turn(t):
    return {"t": t, "k": "turn"}


def test_engagement_flags_click_through():
    # turns at 10 and 20; Human offers at 11 (1 s) and 22 (2 s): median 1.5 s < 3 s, no human drafts -> click_through 1.
    # Human acted -> never_acted 0. No suggestions -> always_follows 0 (no adoption), never_follows 0 (<3 suggestions).
    expected = {"never_acted": 0, "click_through": 1, "always_follows": 0, "never_follows": 0}
    r = rec(_turn(10), act(11, "human", "offer", ["A", 1]), _turn(20), act(22, "human", "offer", ["B", 1]))
    check(run(r, ["engagement_flags"]), expected)
    # With threshold 1 s the median 1.5 is not below it -> click_through 0.
    assert run(r, ["engagement_flags"], click_through_seconds=1)["click_through"] == 0
    # Exploring one offer in the editor -> not click-through.
    r2 = rec(_turn(10), draft(10.5, "human", x="A", y=1), act(11, "human", "offer", ["A", 1]),
             _turn(20), act(22, "human", "offer", ["B", 1]))
    assert run(r2, ["engagement_flags"])["click_through"] == 0
    # Slow decisions (5 s and 6 s, median 5.5) -> 0.
    r3 = rec(_turn(10), act(15, "human", "offer", ["A", 1]), _turn(20), act(26, "human", "offer", ["B", 1]))
    assert run(r3, ["engagement_flags"])["click_through"] == 0


def test_engagement_flags_never_acted():
    # Only the Assistant and the autopilot act: the Human took no action -> never_acted 1;
    # click_through needs a human action -> 0.
    expected = {"never_acted": 1, "click_through": 0, "always_follows": 0, "never_follows": 0}
    r = rec(_turn(10), act(11, "agent", "offer", ["A", 1]), act(12, "autopilot", "offer", ["B", 1]))
    check(run(r, ["engagement_flags"]), expected)


def test_engagement_flags_always_follows():
    # Three suggestions each followed by an identical human offer: adoption 1, 3 human offers -> always_follows 1.
    # Adoption 1 means never_follows 0. Decisions are slow (turns far from actions) -> click_through 0.
    expected = {"never_acted": 0, "click_through": 0, "always_follows": 1, "never_follows": 0}
    seq = [draft(1, "agent", x="A", y=1), _turn(2), act(20, "human", "offer", ["A", 1]),
           draft(21, "agent", x="B", y=1), _turn(22), act(40, "human", "offer", ["B", 1]),
           draft(41, "agent", x="C", y=1), _turn(42), act(60, "human", "offer", ["C", 1])]
    check(run(rec(*seq), ["engagement_flags"]), expected)
    # Only two human offers -> below the minimum of 3 -> always_follows 0.
    assert run(rec(*seq[:6]), ["engagement_flags"])["always_follows"] == 0


def test_engagement_flags_never_follows():
    # Three suggestions, each followed by a different human offer: adoption 0, 3 suggestions -> never_follows 1.
    # always_follows 0 since adoption 0.
    expected = {"never_acted": 0, "click_through": 0, "always_follows": 0, "never_follows": 1}
    seq = [draft(1, "agent", x="A", y=1), _turn(2), act(20, "human", "offer", ["Z", 1]),
           draft(21, "agent", x="B", y=1), _turn(22), act(40, "human", "offer", ["Z", 2]),
           draft(41, "agent", x="C", y=1), _turn(42), act(60, "human", "offer", ["Z", 3])]
    check(run(rec(*seq), ["engagement_flags"]), expected)
    # Three suggestions but only two (message) drafts... no offer follows at all (adoption empty) -> still 1.
    r = rec(draft(1, "agent", x="A", y=1), draft(2, "agent"), draft(3, "agent"), _turn(4),
            act(30, "human", "text"))
    assert run(r, ["engagement_flags"])["never_follows"] == 1
    # Only two suggestions -> 0.
    r = rec(draft(1, "agent", x="A", y=1), draft(2, "agent"), _turn(4), act(30, "human", "text"))
    assert run(r, ["engagement_flags"])["never_follows"] == 0


# --------------------------------------------------------------------------- #
# assistant_interaction                                                        #
# --------------------------------------------------------------------------- #
def test_assistant_interaction_documented_example():
    # Doc: Human at 10 and 12, Assistant at 15 and 60.
    # 10 s message unanswered (12 replaced it); response 15-12 = 3 s; msg at 60 is proactive (48 s > 30).
    # Streak 2 (15 and 60 in a row). Functions: ok:true, ok:false, a text, an object without ok key
    # -> successes = 2 of 4 = 0.5.
    expected = {"assistant_response_seconds": 3.0, "unanswered_messages": 1, "unsolicited_messages": 1,
                "max_assistant_streak": 2, "fn_calls": 4, "fn_success_rate": 0.5}
    fns = [{"t": 20, "k": "fn", "name": "a", "args": {}, "result": {"ok": True}},
           {"t": 21, "k": "fn", "name": "a", "args": {}, "result": {"ok": False}},
           {"t": 22, "k": "fn", "name": "b", "args": {}, "result": "error text"},
           {"t": 23, "k": "fn", "name": "b", "args": {}, "result": {"data": 1}}]
    r = rec(chat(10, "You"), chat(12, "You"), chat(15, "Assistant"), *fns, chat(60, "Assistant"))
    out = evaluate_recording(r, ["assistant_interaction"])
    check(out["row"], expected)
    assert out["details"]["assistant_interaction"]["fn_by_name"] == {"a": 2, "b": 2}


def test_assistant_interaction_proactive_and_boundaries():
    # A@1: before any Human message -> proactive (1). streak 1.
    # H@5, A@7 answers (2 s); A@35 is exactly 30 s after... last human 5 -> 30 s, not > 30 -> not proactive.
    # Streak A@7, A@35 = 2.
    # H@40, H@50 (40 unanswered), A@53 answers 50 (3 s); H@70 unanswered at session end.
    # unanswered = 2; response mean = (2+3)/2 = 2.5; proactive 1; streak 2; no fn calls -> rate empty.
    expected = {"assistant_response_seconds": 2.5, "unanswered_messages": 2, "unsolicited_messages": 1,
                "max_assistant_streak": 2, "fn_calls": 0, "fn_success_rate": None}
    r = rec(chat(1, "Assistant"), chat(5, "You"), chat(7, "Assistant"), chat(35, "Assistant"),
            chat(40, "You"), chat(50, "You"), chat(53, "Assistant"), chat(70, "You"))
    check(run(r, ["assistant_interaction"]), expected)


def test_assistant_interaction_just_over_thirty_seconds_is_proactive():
    # H@0, A@2 (answer), A@33: 33 s after the Human's last message (> 30) -> proactive 1. Response 2 s.
    expected = {"assistant_response_seconds": 2.0, "unanswered_messages": 0, "unsolicited_messages": 1,
                "max_assistant_streak": 2}
    r = rec(chat(0, "You"), chat(2, "Assistant"), chat(33, "Assistant"))
    check(run(r, ["assistant_interaction"]), expected)


# --------------------------------------------------------------------------- #
# simulation                                                                   #
# --------------------------------------------------------------------------- #
def _sturn(n, sug=None, took=False, action="counter", u=None):
    d = {"t": 10 + n, "k": "sim_turn", "turn": n, "action": action, "took_suggestion": took}
    if sug is not None:
        d["suggestion"] = {"kind": "counter", "utility": sug}
    if u is not None:
        d["utility"] = u
    return d


def test_simulation_stubborn_documented_example():
    # Stubborn persona, reservation 0.4, best utility 0.9, max_concession default 0.2 -> floor = max(0.4, 0.7) = 0.7.
    # 6 turns; turns 1-4 have a suggestion, only turn 2 took it -> take_rate 1/4.
    # Turn 5: counter worth 0.65 < 0.7 -> one violation. Turn 6: accept worth 0.7 (== floor) -> fine.
    # goal_met 1, valid 1 (default), stopped 0, turns 6, violations 1.
    expected = {"sim_goal_met": 1, "sim_valid": 1, "sim_turns": 6, "sim_take_rate": 0.25,
                "sim_violations": 1, "sim_stopped": 0}
    turns = [_sturn(1, sug=0.9, u=0.9), _sturn(2, sug=0.85, took=True, u=0.85), _sturn(3, sug=0.75, u=0.8),
             _sturn(4, sug=0.72, u=0.75), _sturn(5, u=0.65), _sturn(6, action="accept", u=0.7)]
    r = rec({"t": 9, "k": "sim", "kind": "stubborn", "reservation": 0.4, "best_utility": 0.9, "params": {}},
            *turns, {"t": 30, "k": "sim_end", "goal_met": True})
    check(run(r, ["simulation"]), expected)


def test_simulation_llm_persona_stopped_and_invalid():
    # LLM persona: conformance is not computed -> violations empty.
    # 2 turns, none with a suggestion -> take_rate empty. sim_end: goal not met, invalid, stopped.
    expected = {"sim_goal_met": 0, "sim_valid": 0, "sim_turns": 2, "sim_take_rate": None,
                "sim_violations": None, "sim_stopped": 1}
    r = rec({"t": 9, "k": "sim", "kind": "llm"}, _sturn(1), _sturn(2),
            {"t": 30, "k": "sim_end", "goal_met": False, "valid": False, "stopped": True,
             "invalid_reason": "timeout"})
    out = evaluate_recording(r, ["simulation"])
    check(out["row"], expected)
    assert out["details"]["simulation"]["invalid_reason"] == "timeout"


def test_simulation_follower_violations_and_unfinished():
    # Follower must take every suggestion. 3 turns with suggestions, took on turn 1 only ->
    # take_rate 1/3, violations 2 (turns 2 and 3). Without a sim_end: goal_met empty, valid 0, stopped 0.
    expected = {"sim_goal_met": None, "sim_valid": 0, "sim_turns": 3, "sim_take_rate": 1 / 3,
                "sim_violations": 2, "sim_stopped": 0}
    r = rec({"t": 9, "k": "sim", "kind": "follower"}, _sturn(1, sug=0.5, took=True), _sturn(2, sug=0.5),
            _sturn(3, sug=0.5))
    check(run(r, ["simulation"]), expected)


def test_simulation_goal_not_met():
    # sim_end goal_met False, valid True (explicit) -> goal 0, valid 1; zero turns; no suggestions.
    expected = {"sim_goal_met": 0, "sim_valid": 1, "sim_turns": 0, "sim_take_rate": None,
                "sim_violations": 0, "sim_stopped": 0}
    r = rec({"t": 9, "k": "sim", "kind": "follower"}, {"t": 30, "k": "sim_end", "goal_met": False, "valid": True})
    check(run(r, ["simulation"]), expected)


# --------------------------------------------------------------------------- #
# dual_control                                                                 #
# --------------------------------------------------------------------------- #
CONS = [{"issue": "rent", "max": 3200}, {"issue": "pets", "allowed": ["yes"]}]


def _dc(agreement, info=None, split=True):
    info = {"split": split, "constraints": CONS} if info is None else info
    return rec({"t": 20, "k": "result", "summary": {}, "row": {}, "agreement": agreement},
               scenario={"issue_names": ["rent", "pets"], "information": info})


def test_dual_control_both_broken():
    # Agreement rent=3500 (> max 3200: broken), pets=no (not in allowed [yes]: broken).
    # split flag true -> 1; constraints_met 0; 2 violations.
    expected = {"information_split": 1, "constraints_met": 0, "n_constraint_violations": 2}
    check(run(_dc([3500, "no"]), ["dual_control"]), expected)


def test_dual_control_one_broken():
    # rent=3200 equals the maximum -> OK; pets=no broken -> 1 violation, met 0.
    expected = {"information_split": 1, "constraints_met": 0, "n_constraint_violations": 1}
    check(run(_dc([3200, "no"]), ["dual_control"]), expected)


def test_dual_control_all_met():
    # rent=3000 <= 3200, pets=yes allowed -> met 1, 0 violations.
    expected = {"information_split": 1, "constraints_met": 1, "n_constraint_violations": 0}
    check(run(_dc([3000, "yes"]), ["dual_control"]), expected)


def test_dual_control_no_agreement_and_no_split():
    # No agreement: constraints_met and violations empty, split still 1.
    expected = {"information_split": 1, "constraints_met": None, "n_constraint_violations": None}
    check(run(_dc(None), ["dual_control"]), expected)
    # Information present but split false, constraints kept: split 0, met 1, 0 violations.
    expected = {"information_split": 0, "constraints_met": 1, "n_constraint_violations": 0}
    check(run(_dc([3000, "yes"], split=False), ["dual_control"]), expected)


def test_dual_control_without_information():
    # No information block at all: split 0, the rest empty. ("Empty for negotiations without a split.")
    expected = {"information_split": 0, "constraints_met": None, "n_constraint_violations": None}
    r = rec({"t": 20, "k": "result", "summary": {}, "row": {}, "agreement": [3000, "yes"]})
    check(run(r, ["dual_control"]), expected)
