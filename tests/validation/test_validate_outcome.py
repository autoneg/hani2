"""Hand-worked validation of outcome, optimality, scenario_stats, factors, rule_checks, task_success, condition.

Every expected value is derived by hand from the metric's written definition (comments above each case),
never copied from the implementation's output.

Example scenario of docs/guide/metrics.md (single issue x = 0..7 standing for the outcomes A..H):
    A (1.00, 0.20)  B (0.80, 0.60)  C (0.62, 0.75)  D (0.35, 0.90)
    E (0.10, 1.00)  F (0.50, 0.45)  G (0.30, 0.35)  H (0.70, 0.30)      reservation (0.2, 0.2)
Pareto frontier: A, B, C, D, E (H is dominated by B, G by C, F by C).
"""

import pytest

from hani2.evaluation import evaluate_recording
from hani2.recording.format import Recording

H_U = [1.0, 0.8, 0.62, 0.35, 0.1, 0.5, 0.3, 0.7]
O_U = [0.2, 0.6, 0.75, 0.9, 1.0, 0.45, 0.35, 0.3]
IDX = dict(zip("ABCDEFGH", range(8)))


def _recording(*, scenario_extra=None, agreement=None, summary=None, trace=(), extra=(), start_extra=None,
               utilities=None, reserved=(0.2, 0.2), n_out=8):
    scenario = {"t": 0, "k": "scenario", "name": "toy", "human_index": 0,
                "outcomes": [[i] for i in range(n_out)],
                "utilities": utilities if utilities is not None else [H_U, O_U],
                "reserved": list(reserved), "issue_names": ["x"]}
    scenario.update(scenario_extra or {})
    recs = [{"k": "header", "format": "hani2-recording", "version": 1, "id": "s", "t0": 0}, scenario,
            {"t": 1, "k": "start", "human_index": 0, "human_id": "H", **(start_extra or {})}]
    recs += list(extra)
    if trace:
        recs.append({"t": 2, "k": "trace", "rows": list(trace)})
    recs.append({"t": 3, "k": "result", "summary": summary if summary is not None else {}, "row": {},
                 "agreement": agreement})
    return Recording.from_records(recs)


def _row(rec, metrics):
    return evaluate_recording(rec, metrics)["row"]


def _check(row, expected):
    for k, v in expected.items():
        if v is None:
            assert row.get(k) is None, (k, row.get(k))
        elif isinstance(v, str):
            assert row[k] == v, (k, row[k])
        else:
            assert row[k] == pytest.approx(v, abs=1e-6), (k, row[k], v)


def _agree(letter, ended_by="human", status="success", **kw):
    return _recording(agreement=[IDX[letter]], summary={"status": status, "ended_by": ended_by}, **kw)


def _no_deal(**kw):
    return _recording(agreement=None, summary={"status": "timedout", "ended_by": ""}, **kw)


# --------------------------------------------------------------------------- outcome
def test_outcome_docs_example_agreement_on_F():
    # F = (0.5, 0.45); d = (0.2, 0.2); best per side 1 (A for human, E for opponent).
    # human_advantage = (0.5-0.2)/(1-0.2) = 0.375 ; opponent_advantage = (0.45-0.2)/0.8 = 0.3125 ; welfare = 0.95
    expected = {"agreement": 1, "status": "success", "ended_by": "human", "human_utility": 0.5,
                "opponent_utility": 0.45, "human_advantage": 0.375, "opponent_advantage": 0.3125,
                "welfare": 0.95, "practice": 0}
    _check(_row(_agree("F"), ["outcome"]), expected)


def test_outcome_no_agreement_is_reservation_point():
    # No deal -> result is d = (0.2, 0.2): utilities 0.2/0.2, advantage (0.2-0.2)/0.8 = 0 on both sides,
    # welfare r_h + r_o = 0.4, agreement 0, ended_by empty (time limit), practice flag from start.
    expected = {"agreement": 0, "status": "timedout", "ended_by": None, "human_utility": 0.2,
                "opponent_utility": 0.2, "human_advantage": 0.0, "opponent_advantage": 0.0, "welfare": 0.4,
                "practice": 1}
    _check(_row(_no_deal(start_extra={"practice": True}), ["outcome"]), expected)


def test_outcome_multilateral_below_reservation():
    # 3 parties, human seat 0. U_h=[.9,.5,.1], U_o1=[.1,.4,.6], U_o2=[0,.3,.5] -> opponent side sums [.1,.7,1.1].
    # r = (0.3, 0.1, 0.2) -> d = (0.3, 0.3). Agreement = outcome 2: (0.1, 1.1).
    # human_advantage = (0.1-0.3)/(0.9-0.3) = -1/3 (deal worse than no deal), opponent: (1.1-0.3)/(1.1-0.3) = 1,
    # welfare = 1.2.
    expected = {"human_utility": 0.1, "opponent_utility": 1.1, "human_advantage": -1 / 3,
                "opponent_advantage": 1.0, "welfare": 1.2, "agreement": 1}
    rec = _recording(utilities=_U3, reserved=(0.3, 0.1, 0.2), n_out=3, agreement=[2],
                     summary={"status": "success", "ended_by": "human"})
    _check(_row(rec, ["outcome"]), expected)


_U3 = [[0.9, 0.5, 0.1], [0.1, 0.4, 0.6], [0.0, 0.3, 0.5]]


def test_outcome_no_utility_table_uses_summary():
    # Without a utility table the utilities and human advantage come from the session summary and the
    # opponent advantage is empty (docs caveat). welfare = 0.6 + 0.3 = 0.9.
    rec = _recording(scenario_extra={"outcomes": [], "utilities": []}, agreement=None,
                     summary={"status": "success", "human_utility": 0.6, "agent_utility": 0.3,
                              "human_advantage": 0.5})
    expected = {"human_utility": 0.6, "opponent_utility": 0.3, "human_advantage": 0.5,
                "opponent_advantage": None, "welfare": 0.9}
    _check(_row(rec, ["outcome"]), expected)


# --------------------------------------------------------------------------- optimality
def test_optimality_docs_example_agreement_on_F():
    # Frontier A,B,C,D,E. Distances from F=(.5,.45): to C (.12,.30) -> sqrt(.0144+.09)=sqrt(.1044)=0.323110;
    #   to B (.3,.15) 0.3354, to D (.15,.45) 0.474 -> pareto_distance = 0.323110, not optimal.
    # Nash products on frontier: A 0, B .6*.4=.24, C .42*.55=.231, D .15*.7=.105, E 0 -> B (.8,.6);
    #   nash_distance = sqrt(.3^2+.15^2) = sqrt(.1125) = 0.335410.
    # Kalai: gains normalised by (1-.2)=.8: A (1,0)->0, B (.75,.5)->.5, C (.525,.6875)->.525, D .1875, E not
    #   individually rational (.1<.2) -> C (.62,.75); kalai_distance = 0.323110.
    # welfare sums A1.2 B1.4 C1.37 D1.25 E1.1 F.95 G.65 H1.0 -> max 1.4; .95/1.4 = 0.678571.
    # nash_product_ratio = (.3*.25)/.24 = 0.3125 ; fairness_gap = |.375-.3125| = 0.0625.
    expected = {"pareto_distance": 0.1044 ** 0.5, "pareto_optimal": 0, "nash_distance": 0.1125 ** 0.5,
                "kalai_distance": 0.1044 ** 0.5, "welfare_optimality": 0.95 / 1.4,
                "nash_product_ratio": 0.3125, "fairness_gap": 0.0625}
    _check(_row(_agree("F"), ["outcome", "optimality"]), expected)


def test_optimality_agreement_on_nash_point():
    # Agreeing on B = (.8,.6): on the frontier -> pareto_distance 0, pareto_optimal 1; B is the Nash point
    # -> nash_distance 0, nash_product_ratio .24/.24 = 1; Kalai point is C: (.18,-.15) -> sqrt(.0324+.0225)
    # = sqrt(.0549) = 0.234307; welfare 1.4/1.4 = 1; advantages (.8-.2)/.8 = .75 and (.6-.2)/.8 = .5 -> gap .25.
    expected = {"pareto_distance": 0.0, "pareto_optimal": 1, "nash_distance": 0.0, "kalai_distance": 0.0549 ** 0.5,
                "welfare_optimality": 1.0, "nash_product_ratio": 1.0, "fairness_gap": 0.25}
    _check(_row(_agree("B"), ["outcome", "optimality"]), expected)


def test_optimality_no_agreement_uses_reservation_point():
    # No deal -> point d=(.2,.2). Distances to frontier points: A (.8,0)=.8, B (.6,.4)=.721110,
    # C (.42,.55)=sqrt(.1764+.3025)=sqrt(.4789)=.692026, D (.15,.7)=.715891, E (-.1,.8)=.806 -> min C .692026.
    # Nash B: .721110 ; Kalai C: .692026 ; welfare opt = (.2+.2)/1.4 = .285714 ; Nash product (0*0) = 0 ;
    # fairness gap |0-0| = 0 ; d is not on the frontier.
    expected = {"pareto_distance": 0.4789 ** 0.5, "pareto_optimal": 0, "nash_distance": 0.52 ** 0.5,
                "kalai_distance": 0.4789 ** 0.5, "welfare_optimality": 0.4 / 1.4, "nash_product_ratio": 0.0,
                "fairness_gap": 0.0}
    _check(_row(_no_deal(), ["outcome", "optimality"]), expected)


def test_optimality_multilateral_reservation_above_utility():
    # Same 3-party scenario as above; points (summed opponents): A (.9,.1), B (.5,.7), C (.1,1.1); d=(.3,.3).
    # All three are Pareto optimal. Agreement C=(.1,1.1) -> pareto_distance 0, optimal 1.
    # Nash products (gains clipped at 0): A 0.6*0=0, B .2*.4=.08, C 0*.8=0 -> B (.5,.7):
    #   nash_distance = sqrt(.4^2+.4^2)=sqrt(.32)=.565685.
    # Kalai: only B is >= d on both sides -> B; kalai_distance = .565685.
    # welfare sums 1.0, 1.2, 1.2 -> max 1.2 ; C: 1.2/1.2 = 1.
    # nash_product_ratio: human gain clipped to 0 -> 0/.08 = 0.
    # fairness: A_h = (.1-.3)/(.9-.3) = -1/3, A_o = (1.1-.3)/(1.1-.3) = 1 -> |-1/3-1| = 4/3.
    expected = {"pareto_distance": 0.0, "pareto_optimal": 1, "nash_distance": 0.32 ** 0.5,
                "kalai_distance": 0.32 ** 0.5, "welfare_optimality": 1.0, "nash_product_ratio": 0.0,
                "fairness_gap": 4 / 3}
    rec = _recording(utilities=_U3, reserved=(0.3, 0.1, 0.2), n_out=3, agreement=[2],
                     summary={"status": "success", "ended_by": "human"})
    _check(_row(rec, ["outcome", "optimality"]), expected)


def test_optimality_no_gain_for_both_leaves_nash_empty():
    # Two outcomes (.9,.1) and (.1,.9) with d = (.95,.95): nobody gains
    # anywhere, so Nash and Kalai points are undefined (their distances empty) and the Nash ratio is empty.
    # Agreement on outcome 0 = (.9,.1): both on frontier -> pareto_distance 0.
    # welfare: sums 1.0, 1.0 -> 1.0/1.0 = 1.
    expected = {"pareto_distance": 0.0, "pareto_optimal": 1, "nash_distance": None, "kalai_distance": None,
                "welfare_optimality": 1.0, "nash_product_ratio": None}
    rec = _recording(utilities=[[0.9, 0.1], [0.1, 0.9]], reserved=(0.95, 0.95), n_out=2, agreement=[0],
                     summary={"status": "success", "ended_by": "human"})
    _check(_row(rec, ["outcome", "optimality"]), expected)


# --------------------------------------------------------------------------- scenario_stats
def test_scenario_stats_docs_example():
    # 8 outcomes; acceptable to both (>= .2 each): all but E (human .1) -> 7/8 = .875; frontier size 5;
    # ideal point (1,1): to A (0,.8)=.8, B (.2,.4)=sqrt(.2)=.447214, C (.38,.25)=.4549, D (.65,.1), E (.9,0)
    # -> min = B = 0.447214.
    expected = {"n_outcomes": 8, "zopa_fraction": 0.875, "pareto_size": 5, "opposition": 0.2 ** 0.5}
    _check(_row(_no_deal(), ["scenario_stats"]), expected)


def test_scenario_stats_multilateral_zopa_checks_each_party():
    # 3 outcomes, parties h,o1,o2 with r = (.3,.1,.2). ZOPA is checked per party (not summed opponents):
    #   outcome0 (.9,.1,0): o2 0 < .2 -> out ; outcome1 (.5,.4,.3): all ok -> in ; outcome2 (.1,.6,.5): h<.3 -> out
    #   -> 1/3. Pareto points (.9,.1),(.5,.7),(.1,1.1): all 3. Ideal (.9,1.1): A (0,1.0)=1, B (.4,.4)=.565685,
    #   C (.8,0)=.8 -> .565685.
    expected = {"n_outcomes": 3, "zopa_fraction": 1 / 3, "pareto_size": 3, "opposition": 0.32 ** 0.5}
    rec = _recording(utilities=_U3, reserved=(0.3, 0.1, 0.2), n_out=3, agreement=None,
                     summary={"status": "timedout"})
    _check(_row(rec, ["scenario_stats"]), expected)


def test_scenario_stats_no_conflict_has_zero_opposition():
    # One outcome (1,1) is best for both: frontier = {it}, ideal point = it -> opposition 0, pareto_size 1.
    # Outcomes (1,1),(.5,.5),(.2,.2) with r=(.5,.5): ZOPA = outcomes >= .5 on both -> 2/3.
    expected = {"n_outcomes": 3, "zopa_fraction": 2 / 3, "pareto_size": 1, "opposition": 0.0}
    rec = _recording(utilities=[[1.0, 0.5, 0.2], [1.0, 0.5, 0.2]], reserved=(0.5, 0.5), n_out=3,
                     agreement=None, summary={"status": "timedout"})
    _check(_row(rec, ["scenario_stats"]), expected)


# --------------------------------------------------------------------------- rule_checks
def test_rule_checks_human_accepts_below_reservation():
    # Human seat accepts E = (.1, 1.0): u_h .1 < r_h .2 -> irrational_accept 1; the opponent did not accept
    # (ended_by human) -> opponent_irrational_accept 0; status success -> failure flags 0.
    expected = {"irrational_accept": 1, "opponent_irrational_accept": 0, "opponent_failed": 0,
                "infrastructure_failure": 0}
    _check(_row(_agree("E", ended_by="human"), ["rule_checks"]), expected)


def test_rule_checks_acceptance_above_reservation_is_fine():
    # F = (.5,.45) accepted by the human: .5 >= .2 -> 0 ; the opponent flag 0.
    expected = {"irrational_accept": 0, "opponent_irrational_accept": 0}
    _check(_row(_agree("F", ended_by="human"), ["rule_checks"]), expected)


def test_rule_checks_opponent_accepts_below_reservation():
    # Opponent accepts outcome 0 = (.9,.1) in 3-party scenario: u_o sum .1 < r_o = .1+.2 = .3 -> opponent flag 1,
    # human flag 0 (human did not accept).
    expected = {"irrational_accept": 0, "opponent_irrational_accept": 1}
    rec = _recording(utilities=_U3, reserved=(0.3, 0.1, 0.2), n_out=3, agreement=[0],
                     summary={"status": "success", "ended_by": "agent"})
    _check(_row(rec, ["rule_checks"]), expected)


def test_rule_checks_acceptor_inferred_from_acts_when_ended_by_missing():
    # No ended_by: a human-seat accept act means the human accepted. E is below r_h -> irrational_accept 1.
    rec = _recording(agreement=[IDX["E"]], summary={"status": "success"},
                     extra=[{"t": 2, "k": "act", "actor": "autopilot", "type": "accept", "offer": [4]}])
    _check(_row(rec, ["rule_checks"]), {"irrational_accept": 1, "opponent_irrational_accept": 0})


def test_rule_checks_no_agreement_flags_zero():
    expected = {"irrational_accept": 0, "opponent_irrational_accept": 0, "opponent_failed": 0,
                "infrastructure_failure": 0}
    _check(_row(_no_deal(), ["rule_checks"]), expected)


def test_rule_checks_failure_statuses():
    # status agent_failed -> opponent_failed 1, infrastructure_failure 0; erred -> the reverse.
    for status, exp in (("agent_failed", (1, 0)), ("erred", (0, 1))):
        rec = _recording(agreement=None, summary={"status": status})
        expected = {"opponent_failed": exp[0], "infrastructure_failure": exp[1]}
        _check(_row(rec, ["rule_checks"]), expected)


def test_rule_checks_irrational_suggestions_counts_assistant_drafts():
    # Assistant (by="agent") drafts worth to the human: x=1 -> .8, x=4 -> .1 (<.2), x=6 -> .3,
    # x=4 again -> .1 (<.2) => 2. A human-made draft x=7 (.7) and one at x=4 by the human are not counted.
    drafts = [{"t": 2 + i * .01, "k": "draft", "by": by, "values": {"x": x}}
              for i, (by, x) in enumerate([("agent", 1), ("agent", 4), ("human", 4), ("agent", 6), ("agent", 4)])]
    expected = {"irrational_suggestions": 2}
    _check(_row(_agree("F", extra=drafts), ["rule_checks"]), expected)


def test_rule_checks_irrational_suggestions_zero_with_assistant_activity():
    # Only good suggestions (x=1 -> .8, x=5 -> .5) -> count 0 (present, not empty).
    drafts = [{"t": 2, "k": "draft", "by": "agent", "values": {"x": 1}},
              {"t": 2.1, "k": "draft", "by": "agent", "values": {"x": 5}}]
    _check(_row(_agree("F", extra=drafts), ["rule_checks"]), {"irrational_suggestions": 0})


def test_rule_checks_irrational_suggestions_empty_without_assistant():
    _check(_row(_agree("F"), ["rule_checks"]), {"irrational_suggestions": None})


# --------------------------------------------------------------------------- factors
def _composed(cell_extra=None, constraint=None, target_hu=0.6):
    comp = {"cell": {"issues": "4", "opposition": "high", "zopa": "narrow", "constraint": "hidden",
                     "deception": "honest", "time_pressure": "relaxed", **(cell_extra or {})},
            "target": {"human_utility": target_hu}}
    if constraint:
        comp["constraint"] = constraint
    return {"info": {"composition": comp}}


def test_factors_target_attainment_below_target_and_constraint_hit():
    # r_h = .2, target human utility .6, deal F gives .5: attainment (.5-.2)/(.6-.2) = .75 ;
    # .5 < .6 -> reached_target 0 ; forbidden option is x=5 and the agreement is x=5 (F) -> violated 1.
    expected = {"target_attainment": 0.75, "reached_target": 0, "constraint_violated": 1,
                "factor_issues": "4", "factor_opposition": "high", "factor_zopa": "narrow",
                "factor_constraint": "hidden", "factor_deception": "honest", "factor_time_pressure": "relaxed"}
    rec = _agree("F", scenario_extra=_composed(constraint={"issue": "x", "value": "5"}))
    _check(_row(rec, ["outcome", "factors"]), expected)


def test_factors_target_exceeded_and_constraint_avoided():
    # Deal B gives .8: attainment (.8-.2)/.4 = 1.5 ; .8 >= .6 -> reached 1 ; x=1 != forbidden 5 -> 0.
    expected = {"target_attainment": 1.5, "reached_target": 1, "constraint_violated": 0}
    rec = _agree("B", scenario_extra=_composed(constraint={"issue": "x", "value": "5"}))
    _check(_row(rec, ["outcome", "factors"]), expected)


def test_factors_deal_below_reservation_gives_negative_attainment():
    # E gives .1: (.1-.2)/(.6-.2) = -0.25 ; not reached.
    expected = {"target_attainment": -0.25, "reached_target": 0, "constraint_violated": None}
    _check(_row(_agree("E", scenario_extra=_composed()), ["outcome", "factors"]), expected)


def test_factors_no_agreement():
    # No deal -> the human gets r_h = .2: attainment 0, reached 0, constraint not violated (0).
    expected = {"target_attainment": 0.0, "reached_target": 0, "constraint_violated": 0}
    rec = _no_deal(scenario_extra=_composed(constraint={"issue": "x", "value": "5"}))
    _check(_row(rec, ["outcome", "factors"]), expected)


def test_factors_target_equal_to_reservation_is_undefined():
    # target gain 0 -> division undefined -> attainment and reached_target empty.
    expected = {"target_attainment": None, "reached_target": None}
    _check(_row(_agree("F", scenario_extra=_composed(target_hu=0.2)), ["factors"]), expected)


def test_factors_episode_levels_come_from_what_was_played():
    # Opponent played the deceptive negotiator and 8 steps (tight): levels read from the start record,
    # not from the cell (which says honest/relaxed). 13 steps matches no level -> "steps=13".
    rec = _agree("F", scenario_extra=_composed(),
                 start_extra={"opponent": "helpers.DeceptiveTBNegotiator", "n_steps": 8})
    _check(_row(rec, ["factors"]), {"factor_deception": "deceptive", "factor_time_pressure": "tight"})
    rec = _agree("F", scenario_extra=_composed(), start_extra={"opponent": "helpers.HonestTBNegotiator", "n_steps": 13})
    _check(_row(rec, ["factors"]), {"factor_deception": "honest", "factor_time_pressure": "steps=13"})


def test_factors_empty_for_non_composed_scenario():
    expected = {"target_attainment": None, "reached_target": None, "constraint_violated": None,
                "factor_issues": None}
    _check(_row(_agree("F"), ["factors"]), expected)


# --------------------------------------------------------------------------- task_success
_STAGE = ["outcome", "optimality", "rule_checks", "task_success"]


def _crit(**c):
    return {"evaluation": c}


def test_task_success_all_components_hold():
    # F: agreement 1, human_advantage .375 >= .3, pareto_distance .3231 <= .33 -> 3/3 targets;
    # rule irrational_accept = 0 (human accepted .5 >= .2) -> rules_ok 1; 2 components both hold -> success 1.
    expected = {"task_success": 1, "task_targets_met": 1.0, "task_rules_ok": 1, "task_components": 2}
    crit = _crit(targets={"agreement": 1, "human_advantage": ">= 0.3", "pareto_distance": "<= 0.33"},
                 rules=["irrational_accept"])
    _check(_row(_agree("F", scenario_extra=crit), _STAGE), expected)


def test_task_success_failed_targets():
    # human_advantage .375 < .4 fails and pareto_distance .3231 > .3 fails; agreement 1 holds -> 1/3.
    # Rules fine -> rules_ok 1; targets False -> success 0 (components counted: targets, rules = 2).
    expected = {"task_success": 0, "task_targets_met": 1 / 3, "task_rules_ok": 1, "task_components": 2}
    crit = _crit(targets={"agreement": 1, "human_advantage": ">= 0.4", "pareto_distance": "<= 0.3"},
                 rules=["irrational_accept"])
    _check(_row(_agree("F", scenario_extra=crit), _STAGE), expected)


def test_task_success_rule_violation():
    # Human accepts E (.1 < r_h .2) -> irrational_accept 1 -> rules_ok 0 ; targets: agreement 1 holds -> 1.0.
    # Product 1*0 -> success 0.
    expected = {"task_success": 0, "task_targets_met": 1.0, "task_rules_ok": 0, "task_components": 2}
    crit = _crit(targets={"agreement": 1}, rules=["irrational_accept"])
    _check(_row(_agree("E", scenario_extra=crit), _STAGE), expected)


def test_task_success_no_agreement_fails_agreement_target():
    # agreement 0 != 1 -> targets 0/1 = 0 ; success 0 ; a no-deal never trips irrational_accept -> rules_ok 1.
    expected = {"task_success": 0, "task_targets_met": 0.0, "task_rules_ok": 1, "task_components": 2}
    crit = _crit(targets={"agreement": 1}, rules=["irrational_accept"])
    _check(_row(_no_deal(scenario_extra=crit), _STAGE), expected)


def test_task_success_range_and_string_targets():
    # [lo, hi] range on welfare .95 in [.9, 1.0] holds; status "== success" holds; nash_distance .3354 within
    # "< 0.34" holds -> 3/3, success 1, a single component (targets).
    expected = {"task_success": 1, "task_targets_met": 1.0, "task_components": 1}
    crit = _crit(targets={"welfare": [0.9, 1.0], "status": "== success", "nash_distance": "< 0.34"})
    _check(_row(_agree("F", scenario_extra=crit), _STAGE), expected)


def test_task_success_explicit_basis_with_unevaluated_judge_component_is_empty():
    # basis [targets, communicate]; communicate needs the LLM judge (not run) -> not evaluated -> success
    # empty (not a pass); components counted = basis length 2; targets_met still 1.0.
    expected = {"task_success": None, "task_targets_met": 1.0, "task_components": 2}
    crit = _crit(targets={"agreement": 1}, communicate=["Price matters most"], basis=["targets", "communicate"])
    _check(_row(_agree("F", scenario_extra=crit), _STAGE), expected)


def test_task_success_explicit_basis_limits_components():
    # Failed rule is ignored when the basis is only targets (agreement holds) -> success 1, components 1.
    expected = {"task_success": 1, "task_targets_met": 1.0, "task_rules_ok": 0, "task_components": 1}
    crit = _crit(targets={"agreement": 1}, rules=["irrational_accept"], basis=["targets"])
    _check(_row(_agree("E", scenario_extra=crit), _STAGE), expected)


def test_task_success_empty_without_criteria():
    expected = {"task_success": None, "task_targets_met": None, "task_rules_ok": None, "task_components": None}
    _check(_row(_agree("F"), _STAGE), expected)


# --------------------------------------------------------------------------- condition
def _acts(*actors, kind="offer"):
    return [{"t": 2 + i * .01, "k": "act", "actor": a, "type": kind, "offer": [i]} for i, a in enumerate(actors)]


def _cond(assistant="on", oracle=False, info=False, driver=None):
    c = {"assistant": assistant, "oracle": oracle, "opponent_info_tools": info}
    if driver:
        c["autopilot_driver"] = driver
    return {"condition": c}


def test_condition_team_human_acts_only():
    # Assistant on, no oracle, all 3 seat actions by the human -> share 0/3 = 0 -> label team.
    expected = {"condition": "team", "assistant_condition": "on", "oracle": 0, "opponent_info_tools": 0,
                "autopilot_share": 0.0, "autopilot_driver": ""}
    rec = _agree("F", start_extra=_cond(), extra=_acts("human", "human", "human"))
    _check(_row(rec, ["condition"]), expected)


def test_condition_oracle_team_with_opponent_info():
    expected = {"condition": "oracle_team", "oracle": 1, "opponent_info_tools": 1, "autopilot_share": 0.0}
    rec = _agree("F", start_extra=_cond(oracle=True, info=True), extra=_acts("human", "human"))
    _check(_row(rec, ["condition"]), expected)


def test_condition_human_alone():
    expected = {"condition": "human_alone", "assistant_condition": "none", "oracle": 0, "autopilot_share": 0.0}
    rec = _agree("F", start_extra=_cond(assistant="none"), extra=_acts("human", "human"))
    _check(_row(rec, ["condition"]), expected)


def test_condition_full_autopilot_by_assistant_with_oracle():
    # 4 seat actions, all autopilot -> share 1 ; driver event "Assistant" ; oracle -> oracle_no_human.
    expected = {"condition": "oracle_no_human", "oracle": 1, "autopilot_share": 1.0, "autopilot_driver": "Assistant"}
    ev = [{"t": 1.5, "k": "ev", "type": "autopilot", "active": True, "driver": "Assistant"}]
    rec = _agree("F", start_extra=_cond(oracle=True), extra=ev + _acts("autopilot", "autopilot", "autopilot", "autopilot"))
    _check(_row(rec, ["condition"]), expected)


def test_condition_full_autopilot_by_negotiator():
    expected = {"condition": "negotiator_autopilot", "autopilot_share": 1.0, "autopilot_driver": "BoulwareAgent"}
    ev = [{"t": 1.5, "k": "ev", "type": "autopilot", "active": True, "driver": "BoulwareAgent"}]
    rec = _agree("F", start_extra=_cond(), extra=ev + _acts("autopilot", "autopilot"))
    _check(_row(rec, ["condition"]), expected)


def test_condition_mixed_share_counts_only_seat_actions():
    # Seat actions: offer, offer, accept, text (4; one autopilot) -> share 1/4. A "view" act is not a
    # seat action and must not enter the denominator.
    expected = {"condition": "mixed", "autopilot_share": 0.25}
    acts = [{"t": 2, "k": "act", "actor": "autopilot", "type": "offer", "offer": [1]},
            {"t": 2.1, "k": "act", "actor": "human", "type": "offer", "offer": [2]},
            {"t": 2.2, "k": "act", "actor": "human", "type": "accept"},
            {"t": 2.3, "k": "act", "actor": "human", "type": "text"},
            {"t": 2.4, "k": "act", "actor": "autopilot", "type": "view"}]
    rec = _agree("F", start_extra=_cond(driver="Assistant"), extra=acts)
    _check(_row(rec, ["condition"]), expected)


def test_condition_unknown_without_recorded_condition():
    # One human seat action -> autopilot share 0/1 = 0 (defined whenever the seat acted); with no seat
    # action at all the share is empty.
    expected = {"condition": "unknown", "oracle": None, "opponent_info_tools": None, "autopilot_share": 0.0}
    _check(_row(_agree("F", extra=_acts("human")), ["condition"]), expected)
    _check(_row(_agree("F"), ["condition"]), {"condition": "unknown", "autopilot_share": None})
