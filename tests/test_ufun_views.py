"""Preference views for the many negmas utility-function types."""

import json

import pytest
from negmas import make_issue
from negmas.outcomes import make_os
from negmas.preferences import (
    AffineUtilityFunction,
    ComplexNonlinearUtilityFunction,
    ConstUtilityFunction,
    ExpDiscountedUFun,
    GLAUtilityFunction,
    GPAUtilityFunction,
    HyperRectangleUtilityFunction,
    IPUtilityFunction,
    LinDiscountedUFun,
    LinearAdditiveUtilityFunction,
    LinearUtilityFunction,
    MappingUtilityFunction,
    NonlinearHyperRectangleUtilityFunction,
    NonLinearAggregationUtilityFunction,
    PAUtilityFunction,
    ProbMappingUtilityFunction,
    RankOnlyUtilityFunction,
    WeightedUtilityFunction,
)
from negmas.preferences.value_fun import TableFun

from hani2.hub import jsonable
from hani2.testing import make_session
from hani2.tools import Tool, ui
from hani2.tools import ufun_views as uv
from hani2.tools.builtin import preference_view

OS = make_os([make_issue(["a", "b", "c"], "color"), make_issue(4, "size"), make_issue((0.0, 1.0), "price")])
OS2 = make_os([make_issue(["a", "b", "c"], "color"), make_issue(4, "size")])
OS1 = make_os([make_issue(["a", "b", "c"], "color")])
BIG = make_os([make_issue(100, f"i{i}") for i in range(4)])  # 10^8 outcomes
NUM = make_os([make_issue(5, "x"), make_issue(5, "y")])


def additive(os_=OS2, **kw):
    return LinearAdditiveUtilityFunction(
        values=[{"a": 1.0, "b": 0.5, "c": 0.0}, lambda x: x / 3][: len(os_.issues)],
        weights=[0.7, 0.3][: len(os_.issues)], outcome_space=os_, **kw)


def _a_in_range(o):
    return 1.0


def _with_os(u, os_):
    u.outcome_space = os_
    return u


def build():
    add = additive(bias=0.1, reserved_value=0.2)
    u = {
        "additive": add,
        "additive_big": LinearAdditiveUtilityFunction(
            values=[lambda x: x / 100] * 4, weights=[1, 2, 3, 4], outcome_space=BIG),
        "linear": LinearUtilityFunction(weights=[1.0, -2.0], outcome_space=NUM),
        "affine": AffineUtilityFunction(weights=[1.0, 2.0], bias=3.0, outcome_space=NUM),
        "gla": GLAUtilityFunction(
            factors=[((0,), {"a": 1.0, "b": 0.5, "c": 0.0}), ((0, 1), lambda t: (t[1] / 3) * (t[0] == "a"))],
            weights=[0.6, 0.4], bias=0.1, outcome_space=OS2),
        "gpa": GPAUtilityFunction(
            factors=[((0,), {"a": 1.0, "b": 0.5, "c": 0.0}), ((1,), lambda x: x / 3)],
            terms=[(0.5, (1, 0)), (0.3, (1, 1)), (0.2, (0, 2))], outcome_space=OS2),
        "pa": PAUtilityFunction(
            values=[{"a": 1.0, "b": 0.5, "c": 0.0}, lambda x: x / 3],
            terms=[(0.5, (1, 0)), (0.5, (1, 1))], outcome_space=OS2),
        "mapping": MappingUtilityFunction(mapping={("a",): 1.0, ("b",): 0.4, ("c",): 0.0}, outcome_space=OS1),
        "mapping_fn": MappingUtilityFunction(mapping=lambda o: (o[0] + o[1]) / 200, outcome_space=BIG),
        "nonlinear_agg": NonLinearAggregationUtilityFunction(
            values=[{"a": 1.0, "b": 0.5, "c": 0.0}, lambda x: x / 3], f=lambda v: v[0] * v[1], outcome_space=OS2),
        "rect": HyperRectangleUtilityFunction(
            outcome_ranges=[{0: ["a"], 1: (1, 3)}, {0: ["b", "c"]}], utilities=[3.0, 1.0],
            weights=[1.0, 2.0], bias=0.5, outcome_space=OS2),
        "rect_nl": _with_os(NonlinearHyperRectangleUtilityFunction(
            hypervolumes=[{0: ["a"]}], mappings=[2.0], f=lambda xs: sum(xs)), OS2),
        "weighted": WeightedUtilityFunction(ufuns=[add, additive()], weights=[0.5, 0.5], outcome_space=OS2),
        "complex": ComplexNonlinearUtilityFunction(
            ufuns=[add, additive()], combination_function=lambda xs: max(xs), outcome_space=OS2),
        "exp": ExpDiscountedUFun(add, discount=0.9),
        "lin": LinDiscountedUFun(add, cost=0.01),
        "const": ConstUtilityFunction(0.5, outcome_space=OS2),
        "rank": RankOnlyUtilityFunction(add),
        "prob_map": None,
        "ip": None,
    }
    return {k: v for k, v in u.items() if v is not None}


def prob_ufuns():
    out = {}
    from negmas.helpers.prob import ScipyDistribution

    dists = [ScipyDistribution(type="uniform", loc=i / 10, scale=0.1) for i in range(3)]
    outs = [("a",), ("b",), ("c",)]
    out["ip"] = IPUtilityFunction(outcomes=outs, distributions=dists, outcome_space=OS1)
    out["prob_map"] = ProbMappingUtilityFunction(mapping=dict(zip(outs, dists)), outcome_space=OS1)
    return out


class _T:
    values: dict = {}


def render(u, **kw):
    comps = preference_view(_T(), u, **kw)
    assert comps
    assert isinstance(comps, list)
    json.dumps(jsonable(comps))  # JSON-able
    return comps


def texts(x):
    return json.dumps(jsonable(x))


@pytest.mark.parametrize("name", sorted(build()) + ["ip", "prob_map"])
def test_every_ufun_type_renders(name):
    u = build().get(name) or prob_ufuns().get(name)
    comps = render(u)
    t = texts(comps)
    assert "Value on disagreement" in t
    assert "failed" not in t and "cannot be shown" not in t


def test_dispatch_picks_most_specific_view():
    assert uv.find_ufun_view(build()["linear"]) is uv.linear_view
    assert uv.find_ufun_view(build()["additive"]) is uv.additive_view
    assert uv.find_ufun_view(build()["exp"]) is uv.discounted_view
    assert uv.find_ufun_view(object()) is uv.generic_view


def test_additive_keeps_help_card_and_opponent_hides_it():
    t = texts(render(build()["additive"]))
    assert "How your preferences work" in t and "Issue weights" in t
    t = texts(render(build()["additive"], title_prefix="Opponent ", help_card=False))
    assert "How your preferences work" not in t and "Opponent Issue weights" in t


def test_issue_selection_and_nested_views():
    tool = _T()
    tool.values = {"issue": "size"}
    json.dumps(jsonable(preference_view(tool, build()["weighted"])))
    comps = preference_view(tool, build()["weighted"])
    assert "Weights of the parts" in texts(comps)


def test_nesting_depth_limit():
    u = additive()
    for _ in range(uv.MAX_DEPTH + 2):
        u = WeightedUtilityFunction(ufuns=[u], weights=[1.0], outcome_space=OS2)
    render(u)


def test_large_spaces_are_sampled():
    outs, complete = uv.sample_outcomes(build()["mapping_fn"])
    assert not complete and 0 < len(outs) <= uv.MAX_OUTCOMES
    assert "estimated from a sample" in texts(render(build()["mapping_fn"]))


def test_failing_view_falls_back_to_generic():
    class Odd(MappingUtilityFunction):
        pass

    u = Odd(mapping={("a",): 1.0, ("b",): 0.4, ("c",): 0.0}, outcome_space=OS1)

    @uv.register_ufun_view(Odd)
    def boom(ctx):
        raise RuntimeError("nope")

    try:
        t = texts(render(u))
        assert "Best deals" in t
    finally:
        uv.unregister_ufun_view(Odd)


def test_custom_view_takes_precedence_and_priority():
    class Mine(MappingUtilityFunction):
        pass

    u = Mine(mapping={("a",): 1.0}, outcome_space=OS1)
    try:
        uv.register_ufun_view(Mine, lambda ctx: [ui.text_block("first")])
        assert "first" in texts(render(u))
        uv.register_ufun_view(Mine, lambda ctx: [ui.text_block("low")], priority=-1)
        assert "first" in texts(render(u))
        uv.register_ufun_view(Mine, lambda ctx: [ui.text_block("high")], priority=5)
        t = texts(render(u))
        assert "high" in t
        assert "Value on disagreement" in t  # always shown
    finally:
        uv.unregister_ufun_view(Mine)
    assert "Best deals" in texts(render(u))


def test_preference_tools_render_in_session():
    s = make_session(is_admin=True)
    s.start()
    s.wait_for_turn()
    for name in ("Preferences", "Opponent Preferences"):
        t = s.tool_controller.find(name)
        view = t.render()
        assert "Value on disagreement" in texts(view)
        assert isinstance(t, Tool)


def test_mapping_and_rank_views_list_best_deals():
    assert "Best deals" in texts(render(build()["mapping"]))
    assert "Deals from best to worst" in texts(render(build()["rank"]))
