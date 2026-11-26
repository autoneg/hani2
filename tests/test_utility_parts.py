"""The colour-coded utility bars: the human's utility issue by issue, most important first."""

import math

from hani2.testing import make_session


def session_with(information=None, scenario="Trade"):
    s = make_session(load=False)
    if information is not None:
        s.admin_prefs["information"] = information
    s.load(scenario)
    return s


def test_parts_sum_to_the_utility_in_weight_order():
    s = session_with(scenario="Grocery")
    u = s.human_ufun
    order = s.utility_issue_order()
    names = [i.name for i in u.outcome_space.issues]
    weights = dict(zip(names, u.weights))
    assert sorted(order) == sorted(names)
    assert [weights[n] for n in order] == sorted(weights.values(), reverse=True)
    for o in u.outcome_space.sample(20):
        parts = s.utility_parts(o)
        assert len(parts) == len(names) and min(parts) >= 0
        assert math.isclose(sum(parts), u(o), abs_tol=1e-5)
        by_name = dict(zip(order, parts))
        for x, n, w, fn in zip(o, names, u.weights, u.values):
            assert math.isclose(by_name[n], w * fn(x), abs_tol=1e-5)


def test_snapshot_history_and_result_carry_the_parts():
    s = session_with()
    snap = s.snapshot()
    assert snap["utility_issues"] == s.utility_issue_order()
    assert snap["prefs"]["color_utility_by_issue"] is False  # off by default
    assert s.set_pref("color_utility_by_issue", True)
    s.start()
    s.play_counters(2)
    s.wait_for_turn()
    snap = s.snapshot()
    assert len(snap["draft"]["utility_parts"]) == len(snap["utility_issues"])
    offers = [h for h in snap["history"] if h.get("kind") == "offer" and h.get("offer")]
    assert offers and all(math.isclose(sum(h["utility_parts"]), h["utility"], abs_tol=1e-5) for h in offers)
    if snap["partner_offer"] is not None:
        assert math.isclose(sum(snap["partner_offer"]["utility_parts"]), snap["partner_offer"]["utility"], abs_tol=1e-5)
    s.end()


def test_hidden_when_the_participant_does_not_know_their_weights():
    s = session_with({"preferences": {"human": "values", "assistant": "full", "show_totals_to_partial": True}})
    assert s.sees_totals("human") and not s.shows_utility_parts()
    snap = s.snapshot()
    assert snap["utility_issues"] is None and snap["draft"]["utility_parts"] is None
    s.start()
    s.play_counters(1)
    s.wait_for_turn()
    hist = [h for h in s.snapshot()["history"] if h.get("kind") == "offer"]
    assert hist and all("utility_parts" not in h for h in hist)
    assert all("utility" in h for h in hist)  # the totals stay


def test_not_additive_gives_no_parts():
    from negmas.preferences import MappingUtilityFunction

    s = session_with()
    os_ = s.human_ufun.outcome_space
    s.ss["human_ufun"] = MappingUtilityFunction(lambda o: 0.5, outcome_space=os_)
    assert s.utility_issue_order() is None
    assert s.utility_parts(next(iter(os_.sample(1)))) is None
