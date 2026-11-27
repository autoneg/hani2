"""A negotiation always runs on a normalized scenario: one that is not normalized is
normalized when it starts (a normalized one is used as it is, and ``assume_normalized``
skips the check); the Preferences tools in raw numbers show the original numbers."""

import json
import random

from hani2 import scenario_store as store
from hani2.testing import make_session
from hani2.tools import ufun_views as uv
from hani2.ufun_scale import RAW_ATTR, is_normalized, raw_of


def _env(home, negotiation, tools=None):
    from hani2.config import settings_dir

    settings_dir().mkdir(parents=True, exist_ok=True)
    (settings_dir() / "env.json").write_text(json.dumps({"negotiation": negotiation, "tools": tools or {}}))


RAW = {"simple_scenarios": False, "normalized_scenarios": False}


def _session(**kw):
    random.seed(2)
    return make_session(scenario_type="Grocery", n_steps=6, **kw)


def test_a_raw_scenario_is_normalized_for_the_negotiation(hani2_home, monkeypatch, tmp_path):
    monkeypatch.setenv("HANI2_SCENARIOS_BASE", str(tmp_path / "empty"))
    _env(hani2_home, RAW)
    s = _session()
    assert s.ss["scenario_info"].get(store.NORMALIZED_KEY) is False  # generated in points
    assert all(is_normalized(u) for u in s.scenario.ufuns)  # played on 0..1
    h = s.human_ufun
    raw = raw_of(h)
    assert raw is not h and not is_normalized(raw)
    lo, hi = raw.minmax()
    assert abs(raw.reserved_value - (lo + h.reserved_value * (hi - lo))) < 1e-3
    assert 0 <= s.snapshot()["reserved_value"] <= 1


def test_preferences_show_the_original_numbers_in_raw_mode(hani2_home, monkeypatch, tmp_path):
    monkeypatch.setenv("HANI2_SCENARIOS_BASE", str(tmp_path / "empty"))
    _env(hani2_home, RAW, {"preferences_scale": "raw"})
    s = _session()
    raw = raw_of(s.human_ufun)
    summary = uv.preference_summary(s.human_ufun)
    assert "%" not in summary
    texts = json.dumps(uv.render_ufun_view(type("T", (), {"values": {}})(), s.human_ufun))
    assert f"{raw.minmax()[1]:.3g}" in texts  # what the best deal is worth, in points


def test_a_normalized_scenario_is_used_as_it_is(hani2_home):
    random.seed(2)
    sc, _, _ = store.load_scenario("Trade", 0, load_existing=False)
    sc = store.normalize_scenario(sc)
    assert store.normalize_for_play(sc) is sc
    s = make_session(n_steps=6)
    assert not any(hasattr(u, RAW_ATTR) for u in s.scenario.ufuns)


def test_assume_normalized_skips_it(hani2_home, monkeypatch, tmp_path):
    from hani2 import projects

    monkeypatch.setenv("HANI2_SCENARIOS_BASE", str(tmp_path / "empty"))
    projects.create_project("P", defaults={"assume_normalized": True, **RAW})
    projects.create_study("P/a", type="online")
    with projects.use_study("P/a"):
        assert store.assume_normalized() is True
        random.seed(2)
        sc, _, _ = store.load_scenario("Grocery", 0, load_existing=False, simple_mode=False, normalized=False)
        assert store.normalize_for_play(sc) is sc and not all(is_normalized(u) for u in sc.ufuns)
    assert store.assume_normalized() is False


def test_raw_of_follows_negmas_range_with_a_one_option_issue():
    from negmas import LinearAdditiveUtilityFunction as LAU
    from negmas import make_issue
    from negmas.inout import Scenario
    from negmas.outcomes import make_os
    from negmas.preferences.value_fun import TableFun

    from hani2.ufun_scale import normalize_for_play

    os_ = make_os([make_issue(["a", "b", "c"], "x"), make_issue(["only"], "y")])
    u = LAU(values=[TableFun({"a": 1, "b": 5, "c": 3}), TableFun({"only": 2})], weights=[1, 1], outcome_space=os_,
            reserved_value=4.0, name="u")
    play = normalize_for_play(Scenario(outcome_space=os_, ufuns=(u, u.normalize())))
    n = play.ufuns[0]
    assert raw_of(n).reserved_value == 4.0  # untouched: the original
    lo, hi = n.minmax()
    n.reserved_value = lo + 0.5 * (hi - lo)  # forced half way
    assert abs(raw_of(n).reserved_value - 5.0) < 1e-9  # half way from 3 to 7


def test_weighted_preferences_in_raw_numbers(hani2_home):
    from negmas import LinearAdditiveUtilityFunction as LAU
    from negmas import make_issue
    from negmas.outcomes import make_os
    from negmas.preferences import WeightedUtilityFunction
    from negmas.preferences.value_fun import TableFun

    _env(hani2_home, {}, {"preferences_scale": "raw"})
    os_ = make_os([make_issue(["a", "b"], "x")])
    parts = [LAU(values=[TableFun({"a": 1, "b": 0})], outcome_space=os_), LAU(values=[TableFun({"a": 0, "b": 2})],
                                                                                 outcome_space=os_)]
    w = WeightedUtilityFunction(ufuns=parts, weights=[2, 3], outcome_space=os_)
    texts = json.dumps(uv.render_ufun_view(type("T", (), {"values": {}})(), w))
    assert "Weights of the parts" in texts and "(its weight)" in texts
