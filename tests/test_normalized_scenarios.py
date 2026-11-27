"""Generated scenarios are normalized (as negmas normalizes) by default; the setting
``normalized_scenarios`` off keeps them as their makers draw them without normalizing."""

import random

from negmas import LinearAdditiveUtilityFunction as LAU
from negmas import make_issue
from negmas.outcomes import make_os
from negmas.preferences.value_fun import TableFun

from hani2 import scenario_store as store
from hani2.ufun_scale import is_normalized


def _gen(normalized, simple=False, type_="Trade"):
    random.seed(7)
    return store.make_scenario(type_, 0, simple, normalized)


def test_default_is_negmas_normalized():
    for t in ("Trade", "Grocery", "Island", "Lease"):
        for simple in (False, True):
            a = _gen(True, simple, t)
            assert all(is_normalized(u) for u in a.ufuns), (t, simple)
            assert store.NORMALIZED_KEY not in (a.info or {})
    a, b = _gen(True), _gen(True)
    o = next(iter(a.outcome_space.enumerate()))
    assert [u(o) for u in a.ufuns] == [u(o) for u in b.ufuns]
    assert store.normalized_scenarios() is True


def test_a_normalized_scenario_is_kept_as_it_is():
    a = _gen(True)
    before = list(a.ufuns)
    assert list(store.normalize_scenario(a).ufuns) == before  # the very same objects


def test_not_normalized_keeps_what_the_maker_draws():
    r = _gen(False, type_="Grocery")  # the items' points
    assert r.info[store.NORMALIZED_KEY] is False
    assert not all(is_normalized(u) for u in r.ufuns)
    for u in r.ufuns:
        lo, hi = u.minmax()
        assert lo <= u.reserved_value <= hi  # the drawn fraction, put on this scale
    n = store.normalize_scenario(r)
    assert all(is_normalized(u) for u in n.ufuns)
    # a maker that only draws normalized scenarios gives the same ones, marked not normalized
    t = _gen(False, type_="Lease")
    assert t.info[store.NORMALIZED_KEY] is False
    # simple scenarios stay normalized: their round numbers are percentages
    s = _gen(False, simple=True, type_="Grocery")
    assert all(is_normalized(u) for u in s.ufuns) and store.NORMALIZED_KEY not in (s.info or {})


def test_normalize_scenario_is_negmas_per_ufun():
    os_ = make_os([make_issue([1, 2, 3], "A"), make_issue(["x", "y"], "B")])
    u = LAU(values=[TableFun({1: -5, 2: 40, 3: 10}), TableFun({"x": 3, "y": -1})], weights=[2.5, -0.7],
            outcome_space=os_, reserved_value=0.0, name="u")
    v = LAU(values=[TableFun({1: 0, 2: 1, 3: 2}), TableFun({"x": 0, "y": 4})], weights=[1, 1],
            outcome_space=os_, reserved_value=3.0, name="v")
    from negmas.inout import Scenario

    s = store.normalize_scenario(Scenario(outcome_space=os_, ufuns=(u, v)))
    assert [x.name for x in s.ufuns] == ["u", "v"] and s.ufuns[0].id == u.id
    assert all(is_normalized(x) for x in s.ufuns)  # each on its own, not on a common range
    assert s.is_normalized(to=(0.0, 1.0), common_range=False)
    assert abs(s.ufuns[1].reserved_value - 0.5) < 1e-9  # 3 is half way from 0 to 6


def test_setting_precedence_and_generation(hani2_home):
    from hani2 import projects

    assert store.normalized_scenarios(default=False) is False  # the global setting
    projects.create_project("P", defaults={"normalized_scenarios": False})
    projects.create_study("P/a", type="online", overrides={"normalized_scenarios": True})
    projects.create_study("P/b", type="online")
    with projects.use_study("P/a"):
        assert store.normalized_scenarios(default=False) is True  # the study wins
    with projects.use_study("P/b"):
        assert store.normalized_scenarios(default=True) is False  # then the project
        random.seed(3)
        s = store.generate_scenario("Grocery", 0, "random")
        assert s.info[store.NORMALIZED_KEY] is False and not is_normalized(s.ufuns[0])


def test_on_the_fly_load_follows_the_setting(hani2_home, monkeypatch, tmp_path):
    monkeypatch.setenv("HANI2_SCENARIOS_BASE", str(tmp_path / "empty"))
    random.seed(1)
    s, info, _ = store.load_scenario("Grocery", 0, load_existing=False, normalized=False)
    assert info[store.NORMALIZED_KEY] is False and not all(is_normalized(u) for u in s.ufuns)
    s, info, _ = store.load_scenario("Grocery", 0, load_existing=False)
    assert store.NORMALIZED_KEY not in info and all(is_normalized(u) for u in s.ufuns)


def test_generate_one_not_normalized(hani2_home, tmp_path):
    from hani2 import make_scenarios as ms

    ok, msg = ms.generate_one("Grocery", 0, tmp_path / "Grocery", 1, True, False, random.Random(0), 0.0, 1.0,
                              True, 0.2, 0.2, 50, seed=0, normalized=False)
    assert ok and "(not normalized)" in msg
    s = store._load_dir(next((tmp_path / "Grocery").iterdir()))
    assert s.info.get(store.NORMALIZED_KEY) is False and not all(is_normalized(u) for u in s.ufuns)
    for u in s.ufuns:
        lo, hi = u.minmax()
        assert lo <= u.reserved_value <= lo + 0.2 * (hi - lo) + 1e-6
    ok, msg = ms.generate_one("Grocery", 1, tmp_path / "Grocery", 1, True, False, random.Random(0), 0.0, 1.0,
                              True, 0.2, 0.2, 50, seed=0)
    s = store._load_dir(tmp_path / "Grocery" / "0001Grocery")
    assert all(is_normalized(u) for u in s.ufuns) and "(not normalized)" not in msg
