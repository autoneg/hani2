"""How the Preferences tools show numbers: normalized percentages (the default) or the
utility function's own numbers, and a line instead of bars for issues with many options."""

import json

from negmas import LinearAdditiveUtilityFunction as LAU
from negmas import make_issue
from negmas.outcomes import make_os
from negmas.preferences.value_fun import AffineFun, TableFun

from hani2.tools import ufun_views as uv


class _Tool:
    values: dict = {}


def _walk(comps):
    for c in comps or []:
        if isinstance(c, dict):
            yield c
            yield from _walk(c.get("children"))


def _raw_ufun():
    os_ = make_os([make_issue([1, 2, 3], "Days"), make_issue(["x", "y"], "Color")])
    return LAU(values=[AffineFun(2, 0), TableFun({"x": 5, "y": 1})], weights=[3, 1], outcome_space=os_,
               reserved_value=11, name="human")


def _env(hani2_home, tools):
    from hani2.config import settings_dir

    settings_dir().mkdir(parents=True, exist_ok=True)
    (settings_dir() / "env.json").write_text(json.dumps({"tools": tools}), encoding="utf-8")


def _texts(comps):
    out = []
    for c in _walk(comps):
        out += [str(c.get(k)) for k in ("text", "value") if c.get(k) is not None]
        out += [str(i.get("value")) for i in c.get("items") or [] if isinstance(i, dict)]
    return out


def test_normalized_by_default_is_negmas_normalization(hani2_home):
    u = _raw_ufun()  # deals worth 7..23, value on disagreement 11
    shown = uv.display_ufun(u)
    assert shown is not u and shown.name == "human" and shown.id == u.id
    # negmas: deals from 0 to 1, every value function from 0 to 1, weights adding up to 1
    assert tuple(round(x, 6) for x in shown.minmax()) == (0.0, 1.0)
    assert [round(w, 4) for w in shown.weights] == [0.75, 0.25]
    issues = list(u.outcome_space.issues)
    assert [[round(f(v), 4) for v in i.all] for f, i in zip(shown.values, issues)] == [[0.0, 0.5, 1.0], [1.0, 0.0]]
    assert abs(shown.reserved_value - (11 - 7) / 16) < 1e-9  # the same map as the deals
    o = (2, "y")
    assert abs(shown(o) - (u(o) - 7) / 16) < 1e-9
    comps = uv.render_ufun_view(_Tool(), u)
    texts = " ".join(_texts(comps))
    assert "25%" in texts and "(your best option gives you 100%)" in texts
    legend = next(c for c in _walk(comps) if c.get("type") == "legend")
    assert [i["value"] for i in legend["items"]] == ["75%", "25%"]


def _unconstrained():
    os_ = make_os([make_issue([1, 2, 3, 4, 5], "A"), make_issue(["p", "q", "r"], "B"), make_issue((0.0, 10.0), "C")])
    return LAU(values=[TableFun({1: -5, 2: 40, 3: 10, 4: 0, 5: -2}), TableFun({"p": 3, "q": -1, "r": 7}),
                       AffineFun(-2, 3)], weights=[2.5, -0.7, 1.3], outcome_space=os_, reserved_value=-4, name="w")


def test_a_ufun_without_constraints_is_shown_both_ways(hani2_home):
    u = _unconstrained()  # a negative weight, values below 0, weights not adding up to 1
    shown = uv.display_ufun(u)
    assert tuple(round(x, 6) for x in shown.minmax()) == (0.0, 1.0)
    assert all(w >= 0 for w in shown.weights) and abs(sum(shown.weights) - 1) < 1e-9
    texts = " ".join(_texts(uv.render_ufun_view(_Tool(), u)))
    assert "your best option gives you 100%" in texts
    _env(hani2_home, {"preferences_scale": "raw"})
    comps = uv.render_ufun_view(_Tool(), u)
    texts = " ".join(_texts(comps))
    assert "you get -4 (your best option gives you 105)" in texts and "%" not in texts.replace("100%", "")
    weights = next(c for c in _walk(comps) if c.get("type") == "plot")
    assert weights["figure"]["data"][0]["x"] == [2.5, -0.7, 1.3]
    assert any("negative weight" in t for t in _texts(comps))
    assert "%" not in uv.preference_summary(u)


def test_a_normalized_ufun_is_shown_as_it_is():
    os_ = make_os([make_issue([1, 2], "A")])
    u = LAU(values=[TableFun({1: 0.0, 2: 1.0})], weights=[1.0], outcome_space=os_, reserved_value=0.1)
    assert uv.display_ufun(u) is u


def test_raw_shows_the_numbers(hani2_home):
    _env(hani2_home, {"preferences_scale": "raw"})
    u = _raw_ufun()
    comps = uv.render_ufun_view(_Tool(), u)
    texts = " ".join(_texts(comps))
    assert "If you do not reach agreement you get 11 (your best option gives you 23)." in texts
    legend = next(c for c in _walk(comps) if c.get("type") == "legend")
    assert [i["value"] for i in legend["items"]] == ["3", "1"]
    bars = next(c for c in _walk(comps) if c.get("type") == "plot" and c["figure"]["data"][0].get("orientation") == "h"
                and c["figure"]["layout"].get("barmode") != "stack")
    assert bars["figure"]["data"][0]["x"] == [2.0, 4.0, 6.0]  # Days' own values, not percentages
    assert "ticksuffix" not in (bars["figure"]["layout"].get("xaxis") or {})
    help_ = next(c for c in comps if c.get("title") == "How your preferences work")
    assert "%" not in help_["children"][0]["text"]
    summary = uv.preference_summary(u)
    assert "**Days** (3)" in summary and "%" not in summary


def test_many_options_draw_a_line_the_same_way_round(hani2_home):
    issue = make_issue(list(range(30)), "Units")
    plot = uv._fun_plot(issue, TableFun({v: v / 29 for v in range(30)}))
    tr = plot["figure"]["data"][0]
    assert tr["type"] == "scatter" and tr["y"][:3] == [0.0, 1.0, 2.0]  # the options down the side
    assert plot["figure"]["layout"]["yaxis"]["autorange"] == "reversed"
    assert plot["figure"]["layout"]["xaxis"]["ticksuffix"] == "%"
    few = uv._fun_plot(make_issue([1, 2, 3], "Few"), TableFun({1: 0, 2: .5, 3: 1}))
    assert few["figure"]["data"][0]["type"] == "bar"
    _env(hani2_home, {"values_line_above": 2})
    assert uv._fun_plot(make_issue([1, 2, 3], "Few"), TableFun({1: 0, 2: .5, 3: 1}))["figure"]["data"][0]["type"] \
        == "scatter"


def test_continuous_issue_is_a_line_with_values_across():
    issue = make_issue((0.0, 10.0), "Price")
    tr = uv._fun_plot(issue, AffineFun(0.1, 0))["figure"]["data"][0]
    assert tr["type"] == "scatter" and len(tr["y"]) == uv.LINE_POINTS and tr["y"][0] == 0.0
    assert max(tr["x"]) == 100.0  # the value across, in percent
