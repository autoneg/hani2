"""Validation of the ``scores`` metric and of ``criteria.normalise`` against hand-worked examples.

Every expected value is derived by hand from the written definition (the module docs of
``hani2.evaluation.scores`` / ``criteria``, docs/guide/project-management.md#scores):

    S = sum(w_i * phi_i(x_i)) / sum(w_i)   over the components that have a value
    coverage = (weight with a value) / (total weight)

with phi = likert7: (x-1)/6, unit/advantage: clip(x, 0, 1), inverse: 1-clip(x), count: 1/(1+x).
"""

from types import SimpleNamespace

import pytest

from hani2.evaluation import scores as S
from hani2.evaluation.criteria import Criterion, normalise

A = dict(abs=1e-9)


def check(got: dict, expected: dict) -> None:
    for k, v in expected.items():
        if v is None:
            assert got[k] is None, k
        else:
            assert got[k] == pytest.approx(v, **A), k


def defined(key, data, **kw):
    ss = S.resolve(project_scores={key: data}, **kw)
    assert ss.problems == [], ss.problems
    return ss


# --------------------------------------------------------------------------- #
# Built-in scores                                                              #
# --------------------------------------------------------------------------- #
def test_scores_han_outcome():
    # opponent_advantage 0.7, advantage normaliser = clip(x) -> 0.7, weight 1 -> 0.7, coverage 1
    row = {"opponent_advantage": 0.7, "opponent_failed": 0}
    expected = {"han_outcome": 0.7, "han_outcome_coverage": 1.0}
    check(S.score_row(row), expected)
    # above 1 clips to 1, below 0 clips to 0
    assert S.score_row({"opponent_advantage": 1.4})["han_outcome"] == pytest.approx(1.0)
    assert S.score_row({"opponent_advantage": -0.2})["han_outcome"] == pytest.approx(0.0)


def test_scores_han_outcome_zero_if_failed():
    # zero_if opponent_failed == 1: score 0 with coverage 1, even with a large advantage
    row = {"opponent_advantage": 0.9, "opponent_failed": 1}
    expected = {"han_outcome": 0.0, "han_outcome_coverage": 1.0}
    check(S.score_row(row), expected)
    # no advantage at all and no failure: nothing present -> no score, coverage 0
    check(S.score_row({}), {"han_outcome": None, "han_outcome_coverage": 0.0})


def test_scores_han_interaction_full_row():
    # (value -> normalised, weight)
    # kindness .8 -> .8 (1); intelligence .6 -> .6 (1); humanlike .4 -> .4 (1); relationship 1 -> 1 (1)
    # satisfaction 0.5 -> 0.5 (0.5); jo_overall 7 -> 1 (1); jo_communication 4 -> .5 (.5)
    # jo_consistency 1 -> 0 (.5); jo_human_likeness 5 -> 4/6 (.5); opponent_failed 0 -> 1 (1)
    # opponent_irrational_accept 1 -> 0 (.5)
    # total weight = 1+1+1+1+.5+1+.5+.5+.5+1+.5 = 8.5
    # weighted sum = .8+.6+.4+1 + .25 + 1 + .25 + 0 + (.5*4/6) + 1 + 0
    row = {"scale_opponent_kindness_norm": 0.8, "scale_opponent_intelligence_norm": 0.6,
           "scale_opponent_humanlike_norm": 0.4, "scale_relationship_norm": 1.0, "scale_satisfaction_norm": 0.5,
           "jo_overall": 7, "jo_communication": 4, "jo_consistency": 1, "jo_human_likeness": 5,
           "opponent_failed": 0, "opponent_irrational_accept": 1}
    expected = {"han_interaction": (0.8 + 0.6 + 0.4 + 1 + 0.25 + 1 + 0.25 + 0 + 0.5 * 4 / 6 + 1 + 0) / 8.5,
                "han_interaction_coverage": 1.0}
    check(S.score_row(row), expected)


def test_scores_han_interaction_partial_row():
    # only jo_overall 4 -> .5 (w 1), jo_consistency 7 -> 1 (w .5), opponent_failed 1 -> 0 (w 1)
    # (no zero_if on han_interaction: a failure only costs its own component)
    # present weight 2.5, sum = .5 + .5 + 0 = 1.0 -> 0.4; coverage = 2.5 / 8.5
    row = {"jo_overall": 4, "jo_consistency": 7, "opponent_failed": 1}
    expected = {"han_interaction": 1.0 / 2.5, "han_interaction_coverage": 2.5 / 8.5}
    check(S.score_row(row), expected)


def test_scores_hi_outcome_and_utility():
    # human_advantage .375 -> .375 for both; they need no Assistant
    row = {"human_advantage": 0.375}
    expected = {"hi_outcome": 0.375, "hi_outcome_coverage": 1.0, "utility": 0.375, "utility_coverage": 1.0}
    check(S.score_row(row), expected)
    # a negative advantage (worse than no deal) is 0; a missing one is no score with coverage 0
    check(S.score_row({"human_advantage": -0.3, "support_agent": "x"}), {"hi_outcome": 0.0, "utility": 0.0})
    check(S.score_row({}), {"hi_outcome": None, "hi_outcome_coverage": 0.0, "utility": None,
                            "utility_coverage": 0.0})


HI_ROW = {
    "support_agent": "bot",
    # hi_assistant components
    "ja_overall": 4, "ja_helpfulness": 7, "ja_autonomy_respect": 1, "assertions_met": 0.5,
    "task_communicated": 1.0, "assistant_critical_errors": 3, "assistant_errors": 1,
    "irrational_suggestions": 0, "fn_success_rate": 0.8, "unanswered_messages": 1,
    "scale_ueq_pragmatic_norm": 0.6, "scale_tam_usefulness_norm": 0.2, "scale_felt_heard_norm": 1.0,
    "scale_intention_to_use_norm": 0.0,
    # hi_team components
    "human_overrode_harmfully": 0, "human_critical_errors": 1, "jh_use_of_assistant": 7, "jh_engagement": 4,
    "always_follows": 1, "click_through": 0, "irrational_accept": 0, "welfare_optimality": 0.6,
}


def test_scores_hi_assistant_full_row():
    # (normalised, weight): ja_overall 4 -> .5 (1); ja_helpfulness 7 -> 1 (.5); ja_autonomy 1 -> 0 (.5)
    # assertions_met .5 (1); task_communicated 1 (1); critical errors 3 -> 1/4 (1); errors 1 -> 1/2 (.5)
    # irrational_suggestions 0 -> 1 (1); fn_success .8 (.5); unanswered 1 -> 1/2 (.5)
    # ueq .6 (.5); tam .2 (.5); felt_heard 1 (.5); intention 0 (.5)
    # total weight 9.5; sum = .5 + .5 + 0 + .5 + 1 + .25 + .25 + 1 + .4 + .25 + .3 + .1 + .5 + 0 = 5.55
    expected = {"hi_assistant": 5.55 / 9.5, "hi_assistant_coverage": 1.0}
    check(S.score_row(HI_ROW), expected)


def test_scores_hi_assistant_partial_row_docs_example():
    # the documented example: ja_overall 6 -> 5/6 (w 1), one critical error -> 1/2 (w 1), nothing else
    # S = (5/6 + 1/2) / 2 = 2/3; coverage = 2 / 9.5
    row = {"support_agent": "bot", "ja_overall": 6, "assistant_critical_errors": 1}
    expected = {"hi_assistant": (5 / 6 + 1 / 2) / 2, "hi_assistant_coverage": 2 / 9.5}
    check(S.score_row(row), expected)


def test_scores_hi_team_full_row():
    # overrode_harmfully 0 -> 1 (1); critical_errors 1 -> 1/2 (1); jh_use 7 -> 1 (1); engagement 4 -> .5 (.5)
    # always_follows 1 -> 0 (.5); click_through 0 -> 1 (.5); irrational_accept 0 -> 1 (1); welfare .6 (.5)
    # total weight 6; sum = 1 + .5 + 1 + .25 + 0 + .5 + 1 + .3 = 4.55
    expected = {"hi_team": 4.55 / 6, "hi_team_coverage": 1.0}
    check(S.score_row(HI_ROW), expected)


def test_scores_hi_team_partial_row():
    # only irrational_accept 1 -> 0 (w 1) and jh_engagement 7 -> 1 (w .5): sum .5 over .. present 1.5 -> 1/3
    # coverage = 1.5 / 6
    row = {"support_agent": "bot", "irrational_accept": 1, "jh_engagement": 7}
    expected = {"hi_team": 0.5 / 1.5, "hi_team_coverage": 1.5 / 6}
    check(S.score_row(row), expected)


def test_scores_hi_interaction_full_row():
    # hi_interaction = (1 * hi_assistant + 1 * hi_team) / 2, with the two scores computed first
    # hi_assistant = 5.55 / 9.5, hi_team = 4.55 / 6, both components present -> coverage 1
    expected = {"hi_interaction": (5.55 / 9.5 + 4.55 / 6) / 2, "hi_interaction_coverage": 1.0}
    check(S.score_row(HI_ROW), expected)


def test_scores_hi_interaction_from_given_scores():
    # fed with its two components directly: (0.4 + 0.8) / 2 = 0.6, coverage 1
    row = {"support_agent": "bot", "hi_assistant": 0.4, "hi_team": 0.8}
    v, cov = S.compute(S.BY_NAME["hi_interaction"], row)
    expected = {"hi_interaction": 0.6, "hi_interaction_coverage": 1.0}
    check({"hi_interaction": v, "hi_interaction_coverage": cov}, expected)
    # one missing: the other alone (renormalise), coverage 1/2
    v, cov = S.compute(S.BY_NAME["hi_interaction"], {"support_agent": "bot", "hi_team": 0.8})
    check({"hi_interaction": v, "hi_interaction_coverage": cov}, {"hi_interaction": 0.8, "hi_interaction_coverage": 0.5})


def test_scores_hi_interaction_when_assistant_part_is_empty():
    # a row with only hi_team inputs: hi_assistant has no value (None, coverage 0), so
    # hi_interaction = hi_team = 1 (irrational_accept 0 -> 1, the only input, weight 1) with coverage 1/2
    row = {"support_agent": "bot", "irrational_accept": 0}
    expected = {"hi_assistant": None, "hi_assistant_coverage": 0.0, "hi_team": 1.0,
                "hi_team_coverage": 1.0 / 6, "hi_interaction": 1.0, "hi_interaction_coverage": 0.5}
    check(S.score_row(row), expected)


@pytest.mark.parametrize("support", [None, "none", ""])
def test_scores_hi_needs_assistant_without_one(support):
    # needs_assistant: no Assistant (key absent, "none" or empty) -> hi_assistant, hi_team, hi_interaction
    # have neither a value nor a coverage; the outcome scores do not need an Assistant
    row = dict(HI_ROW)
    row["human_advantage"] = 0.5
    if support is None:
        del row["support_agent"]
    else:
        row["support_agent"] = support
    expected = {"hi_assistant": None, "hi_assistant_coverage": None, "hi_team": None, "hi_team_coverage": None,
                "hi_interaction": None, "hi_interaction_coverage": None, "hi_outcome": 0.5,
                "hi_outcome_coverage": 1.0, "utility": 0.5, "utility_coverage": 1.0}
    check(S.score_row(row), expected)


def test_scores_weight_override_option():
    # options {"scores": {"hi_assistant": {"weights": {"ja_overall": 0}}}} drops ja_overall.
    # Row: ja_overall 7 -> 1, assistant_errors 1 -> 1/2 (w .5).
    # default: (1*1 + .5*.5) / 1.5 = 5/6, coverage 1.5/9.5
    # dropped: total weight 9.5 - 1 = 8.5, present weight .5 (assistant_errors .5 -> .25 / .5 = .5)
    # coverage = .5 / 8.5
    row = {"support_agent": "bot", "ja_overall": 7, "assistant_errors": 1}
    check(S.score_row(row), {"hi_assistant": 1.25 / 1.5, "hi_assistant_coverage": 1.5 / 9.5})
    opts = {"scores": {"hi_assistant": {"weights": {"ja_overall": 0}}}}
    check(S.score_row(row, opts), {"hi_assistant": 0.5, "hi_assistant_coverage": 0.5 / 8.5})


def test_scores_metric_function_returns_every_column():
    # the registered metric adds exactly the score and coverage columns of score_row
    ctx = SimpleNamespace(row={"human_advantage": 0.25})
    out = S.scores(ctx, {})
    names = ("han_outcome", "han_interaction", "hi_outcome", "hi_assistant", "hi_team", "hi_interaction", "utility")
    assert set(out) == {n for n in names} | {f"{n}_coverage" for n in names}
    check(out, {"hi_outcome": 0.25, "utility": 0.25})


# --------------------------------------------------------------------------- #
# Defined scores                                                               #
# --------------------------------------------------------------------------- #
def test_defined_score_three_components_catalogue_defaults():
    # human_advantage .8 -> .8 (w .5, advantage); ja_overall 5 -> 4/6 (w .3, catalogue bounded [1, 7]);
    # n_offers 12 (w .2, direction lower, reciprocal scale 4): 4 / (4 + 12) = .25
    # S = .4 + .2 + .05 = .65, coverage 1
    ss = defined("mix", {"components": [
        {"criterion": "human_advantage", "weight": 0.5},
        {"criterion": "ja_overall", "weight": 0.3},
        {"criterion": "n_offers", "weight": 0.2, "direction": "lower",
         "normaliser": {"kind": "reciprocal", "scale": 4}}]})
    row = {"human_advantage": 0.8, "ja_overall": 5, "n_offers": 12}
    v, cov = S.compute(ss.scores["mix"], row)
    check({"mix": v, "mix_coverage": cov}, {"mix": 0.65, "mix_coverage": 1.0})


def test_defined_score_direction_override():
    # ja_overall 5 -> 4/6 with the default direction (higher); direction lower flips it: 1 - 2/3 = 1/3
    # human_advantage .2 -> .2.   S = .5 * 1/3 + .5 * .2 = 1/6 + .1
    ss = defined("flip", {"components": [{"criterion": "ja_overall", "weight": 0.5, "direction": "lower"},
                                         {"criterion": "human_advantage", "weight": 0.5}]})
    v, cov = S.compute(ss.scores["flip"], {"ja_overall": 5, "human_advantage": 0.2})
    check({"flip": v, "flip_coverage": cov}, {"flip": 1 / 6 + 0.1, "flip_coverage": 1.0})


def test_defined_score_catalogue_direction_lower():
    # irrational_accept is a 0/1 flag where lower is better (catalogue): 1 -> 0, 0 -> 1
    # S = .5 * 0 + .5 * .6 = .3 for (1, .6)
    ss = defined("flag", {"components": [{"criterion": "irrational_accept", "weight": 0.5},
                                         {"criterion": "welfare_optimality", "weight": 0.5}]})
    v, _ = S.compute(ss.scores["flag"], {"irrational_accept": 1, "welfare_optimality": 0.6})
    assert v == pytest.approx(0.3, **A)
    v, _ = S.compute(ss.scores["flag"], {"irrational_accept": 0, "welfare_optimality": 0.6})
    assert v == pytest.approx(0.8, **A)


def test_defined_score_clip_normaliser():
    # clip lo 2, hi 10: x = 6 -> (6 - 2) / 8 = .5; x = 20 -> 1 (clipped); x = 0 -> 0
    # direction lower: x = 6 -> .5, x = 2 -> 1
    up = defined("c_up", {"components": [{"criterion": "n_offers", "weight": 1, "direction": "higher",
                                          "normaliser": {"kind": "clip", "lo": 2, "hi": 10}}]}).scores["c_up"]
    down = defined("c_dn", {"components": [{"criterion": "n_offers", "weight": 1, "direction": "lower",
                                            "normaliser": {"kind": "clip", "lo": 2, "hi": 10}}]}).scores["c_dn"]
    for x, e_up, e_down in [(6, 0.5, 0.5), (20, 1.0, 0.0), (0, 0.0, 1.0), (2, 0.0, 1.0)]:
        expected = {"c_up": e_up, "c_dn": e_down}
        got = {"c_up": S.compute(up, {"n_offers": x})[0], "c_dn": S.compute(down, {"n_offers": x})[0]}
        check(got, expected)


def test_defined_score_percentile_with_reference():
    # reference quantiles [1, 2, 2, 5] (n = 4); percentile = (#{r < x} + .5 #{r = x}) / 4
    # x = 5: (3 + .5) / 4 = .875; with human_advantage .5 -> .5 at equal weights: S = (.875 + .5) / 2 = .6875
    ref = {"criteria": {"n_offers": {"quantiles": [1, 2, 2, 5]}}}
    ss = defined("pct", {"components": [
        {"criterion": "n_offers", "weight": 0.5, "direction": "higher", "normaliser": {"kind": "percentile"}},
        {"criterion": "human_advantage", "weight": 0.5}]})
    v, cov = S.compute(ss.scores["pct"], {"n_offers": 5, "human_advantage": 0.5}, reference=ref)
    check({"pct": v, "pct_coverage": cov}, {"pct": 0.6875, "pct_coverage": 1.0})
    # without a reference the percentile has no value: the component counts as missing -> coverage .5, S = .5
    v, cov = S.compute(ss.scores["pct"], {"n_offers": 5, "human_advantage": 0.5})
    check({"pct": v, "pct_coverage": cov}, {"pct": 0.5, "pct_coverage": 0.5})


def test_defined_score_reference_median_scale():
    # reference scale 3 for n_offers, reciprocal + lower: x = 9 -> 3 / (3 + 9) = .25
    # without a reference the scale is 1: 1 / (1 + 9) = .1
    ss = defined("rm", {"components": [{"criterion": "n_offers", "weight": 1, "direction": "lower",
                                        "normaliser": {"kind": "reciprocal", "scale": "reference_median"}}]})
    ref = {"criteria": {"n_offers": {"scale": 3}}}
    assert S.compute(ss.scores["rm"], {"n_offers": 9}, reference=ref)[0] == pytest.approx(0.25, **A)
    assert S.compute(ss.scores["rm"], {"n_offers": 9})[0] == pytest.approx(0.1, **A)


def _half_missing(policy):
    return defined("m_" + policy, {"missing": policy, "components": [
        {"criterion": "human_advantage", "weight": 0.5}, {"criterion": "ja_overall", "weight": 0.5}]}).scores["m_" + policy]


@pytest.mark.parametrize("policy, value", [("renormalise", 0.6), ("zero", 0.3), ("skip_game", None)])
def test_defined_score_missing_policy(policy, value):
    # human_advantage .6 (w .5), ja_overall missing (w .5)
    # renormalise: .6 * .5 / .5 = .6;  zero: .6 * .5 / 1 = .3;  skip_game: no value.  coverage .5 for all
    v, cov = S.compute(_half_missing(policy), {"human_advantage": 0.6})
    expected = {"score": value, "coverage": 0.5}
    check({"score": v, "coverage": cov}, expected)


@pytest.mark.parametrize("policy", ["renormalise", "zero", "skip_game"])
def test_defined_score_nothing_present(policy):
    # no component has a value: renormalise -> none, coverage 0; zero -> 0, coverage 0; skip_game -> none, 0
    v, cov = S.compute(_half_missing(policy), {})
    assert cov == 0.0
    assert v == (0.0 if policy == "zero" else None)


def test_defined_score_zero_weight_component_is_not_counted():
    # weights .6 / .4 / 0: the 0-weight component is neither in the sum nor in the coverage
    # human_advantage .5 (.6) and ja_overall 7 -> 1 (.4): S = .3 + .4 = .7; coverage 1 though the third is absent
    ss = defined("z", {"components": [{"criterion": "human_advantage", "weight": 0.6},
                                      {"criterion": "ja_overall", "weight": 0.4},
                                      {"criterion": "welfare_optimality", "weight": 0}]})
    v, cov = S.compute(ss.scores["z"], {"human_advantage": 0.5, "ja_overall": 7})
    check({"z": v, "z_coverage": cov}, {"z": 0.7, "z_coverage": 1.0})


def test_defined_score_weights_rescaled_when_loaded():
    # weights 1 and 3 (hand-edited file): non-strict loading rescales to .25 / .75 with a warning
    # human_advantage .4, ja_overall 7 -> 1: S = .25 * .4 + .75 * 1 = .85.  strict refuses them
    data = {"components": [{"criterion": "human_advantage", "weight": 1}, {"criterion": "ja_overall", "weight": 3}]}
    ss = S.resolve(project_scores={"rs": data})
    assert ss.warnings and not ss.problems
    v, _ = S.compute(ss.scores["rs"], {"human_advantage": 0.4, "ja_overall": 7})
    assert v == pytest.approx(0.85, **A)
    assert any("sum" in p for p in S.resolve(project_scores={"rs": data}, strict=True).problems)


def test_defined_score_contains_a_score():
    # defined = .5 * hi_team + .5 * human_advantage; hi_team = 4.55 / 6 (HI_ROW); human_advantage .4
    # S = .5 * 4.55/6 + .5 * .4 (a score has direction higher and bounded [0, 1]: the identity)
    ss = defined("mixed", {"track": "hi", "components": [{"criterion": "hi_team", "weight": 0.5},
                                                          {"criterion": "human_advantage", "weight": 0.5}]})
    row = dict(HI_ROW, human_advantage=0.4)
    out = S.score_row(row, scores=ss.scores.values())
    check(out, {"mixed": 0.5 * 4.55 / 6 + 0.2, "mixed_coverage": 1.0, "hi_team": 4.55 / 6})
    # without an Assistant hi_team has no value: renormalise -> human_advantage alone = .4, coverage .5
    out = S.score_row({"human_advantage": 0.4}, scores=ss.scores.values())
    check(out, {"mixed": 0.4, "mixed_coverage": 0.5, "hi_team": None})


def test_defined_score_has_no_zero_if():
    # zero_if is a built-in feature only: the definition format (SCORE_KEYS) refuses it
    sc, problems, _ = S.parse_definition("zz", {"zero_if": ["opponent_failed"],
                                                "components": [{"criterion": "human_advantage", "weight": 1}]})
    assert sc is None and any("zero_if" in p for p in problems)


# --------------------------------------------------------------------------- #
# criteria.normalise                                                           #
# --------------------------------------------------------------------------- #
def crit(direction="higher", normaliser=None, cid="x"):
    return Criterion(id=cid, title=cid, direction=direction, normaliser=normaliser)


def test_normalise_bounded():
    # (x - 1) / 6 clipped to [0, 1]: 4 -> .5; 7 -> 1; 1 -> 0; 10 -> 1 (clipped); -3 -> 0
    n = {"kind": "bounded", "lo": 1, "hi": 7}
    for x, e in [(4, 0.5), (7, 1.0), (1, 0.0), (10, 1.0), (-3, 0.0), (2, 1 / 6)]:
        assert normalise(x, crit(normaliser=n)) == pytest.approx(e, **A)
    # lower flips it: 1 - (x - 1) / 6
    assert normalise(2, crit("lower", n)) == pytest.approx(5 / 6, **A)
    # negative bounds [-1, 1]: x = .5 -> 1.5 / 2 = .75
    assert normalise(0.5, crit(normaliser={"kind": "bounded", "lo": -1, "hi": 1})) == pytest.approx(0.75, **A)


def test_normalise_clip():
    # clip lo 0 hi 10: 2.5 -> .25; 15 -> 1; -5 -> 0; lower: 2.5 -> .75
    n = {"kind": "clip", "lo": 0, "hi": 10}
    for x, e in [(2.5, 0.25), (15, 1.0), (-5, 0.0)]:
        assert normalise(x, crit(normaliser=n)) == pytest.approx(e, **A)
    assert normalise(2.5, crit("lower", n)) == pytest.approx(0.75, **A)


def test_normalise_advantage():
    # clip(x, 0, 1): .3 -> .3; 1.7 -> 1; -.4 -> 0; lower: .3 -> .7
    n = {"kind": "advantage"}
    for x, e in [(0.3, 0.3), (1.7, 1.0), (-0.4, 0.0)]:
        assert normalise(x, crit(normaliser=n)) == pytest.approx(e, **A)
    assert normalise(0.3, crit("lower", n)) == pytest.approx(0.7, **A)


def test_normalise_reciprocal():
    # s / (s + x) for lower-is-better; s = 2, x = 6: 2 / 8 = .25
    n = {"kind": "reciprocal", "scale": 2}
    assert normalise(6, crit("lower", n)) == pytest.approx(0.25, **A)
    # the same rule seen from the other direction (higher): 1 - .25 = .75
    assert normalise(6, crit("higher", n)) == pytest.approx(0.75, **A)
    # no direction: reciprocal says lower is better by itself
    assert normalise(6, crit("none", n)) == pytest.approx(0.25, **A)
    # x = 0 -> best (1); a negative value is treated as 0
    assert normalise(0, crit("lower", n)) == pytest.approx(1.0, **A)
    assert normalise(-5, crit("lower", n)) == pytest.approx(1.0, **A)


def test_normalise_saturating():
    # x / (x + s) for higher-is-better; s = 2, x = 6: 6 / 8 = .75
    n = {"kind": "saturating", "scale": 2}
    assert normalise(6, crit("higher", n)) == pytest.approx(0.75, **A)
    assert normalise(6, crit("lower", n)) == pytest.approx(0.25, **A)
    assert normalise(6, crit("none", n)) == pytest.approx(0.75, **A)
    assert normalise(0, crit("higher", n)) == pytest.approx(0.0, **A)


def test_normalise_reference_median_scale():
    # scale reference_median = the reference's "scale" for that criterion id: s = 5, x = 15 -> 5/20 = .25
    n = {"kind": "reciprocal", "scale": "reference_median"}
    ref = {"criteria": {"x": {"scale": 5.0}, "other": {"scale": 100.0}}}
    assert normalise(15, crit("lower", n), reference=ref) == pytest.approx(0.25, **A)
    # saturating at the median game: x = s -> .5
    assert normalise(5, crit("higher", {"kind": "saturating", "scale": "reference_median"}),
                     reference=ref) == pytest.approx(0.5, **A)
    # no reference (or no entry for the id): s = 1 -> 1 / (1 + 15) = .0625
    assert normalise(15, crit("lower", n)) == pytest.approx(0.0625, **A)
    assert normalise(15, crit("lower", n), reference={"criteria": {}}) == pytest.approx(0.0625, **A)


def test_normalise_percentile():
    # quantiles [1, 2, 2, 5] (n = 4): (#{r < x} + .5 #{r = x}) / 4
    # x = 0: 0; x = 1: (0 + .5) / 4 = .125; x = 2: (1 + 1) / 4 = .5; x = 3: 3 / 4; x = 5: 3.5 / 4; x = 9: 1
    ref = {"criteria": {"x": {"quantiles": [1, 2, 2, 5]}}}
    n = {"kind": "percentile"}
    for x, e in [(0, 0.0), (1, 0.125), (2, 0.5), (3, 0.75), (5, 0.875), (9, 1.0)]:
        assert normalise(x, crit("higher", n), reference=ref) == pytest.approx(e, **A), x
    # lower: x = 5 -> 1 - .875 = .125
    assert normalise(5, crit("lower", n), reference=ref) == pytest.approx(0.125, **A)
    # no reference -> no value
    assert normalise(5, crit("higher", n)) is None


def test_normalise_overrides_and_missing_values():
    # keyword direction / normaliser override the criterion's: bounded [0, 10] x = 4 lower -> .6
    c = crit("higher", {"kind": "advantage"})
    assert normalise(4, c, direction="lower", normaliser={"kind": "bounded", "lo": 0, "hi": 10}) == pytest.approx(0.6, **A)
    # a bare kind name is accepted
    assert normalise(0.3, c, normaliser="advantage") == pytest.approx(0.3, **A)
    # missing / non-numeric / non-finite values and no normaliser: None
    for bad in (None, "abc", float("nan"), float("inf")):
        assert normalise(bad, c) is None
    assert normalise(0.5, crit("higher", None)) is None
    # numeric strings are numbers
    assert normalise("0.25", c) == pytest.approx(0.25, **A)
    # invalid kind / direction are refused
    with pytest.raises(ValueError):
        normalise(1, c, normaliser={"kind": "nope"})
    with pytest.raises(ValueError):
        normalise(1, c, direction="sideways")
    with pytest.raises(ValueError):
        normalise(1, c, normaliser={"kind": "bounded", "lo": 3, "hi": 3})


def test_normalise_metric_column_defaults():
    # a metric column id takes its catalogue defaults: ja_overall is a 1-7 rating (higher better):
    # 5 -> 4/6; irrational_accept is a 0/1 flag, lower better: 1 -> 0
    assert normalise(5, "ja_overall") == pytest.approx(4 / 6, **A)
    assert normalise(1, "irrational_accept") == pytest.approx(0.0, **A)
    assert normalise(0, "irrational_accept") == pytest.approx(1.0, **A)
