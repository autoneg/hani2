"""Generated scenarios are normalized by default; the setting ``normalized_scenarios`` off
generates them in points."""

import random

from hani2 import scenario_store as store


def _gen(normalized, simple=False, type_="Trade"):
    random.seed(7)
    return store.make_scenario(type_, 0, simple, normalized)


def test_default_is_normalized_and_unchanged():
    a, b = _gen(True), _gen(True)
    for u in a.ufuns:
        lo, hi = u.minmax()
        assert lo >= -1e-9 and abs(hi - 1) < 1e-9
    o = next(iter(a.outcome_space.enumerate()))
    assert [u(o) for u in a.ufuns] == [u(o) for u in b.ufuns]
    assert store.NORMALIZED_KEY not in (a.info or {})
    assert store.normalized_scenarios() is True


def test_not_normalized_is_in_points():
    for simple in (False, True):
        n, r = _gen(True, simple), _gen(False, simple)
        assert r.info[store.NORMALIZED_KEY] is False
        for un, ur in zip(n.ufuns, r.ufuns):
            assert ur.name == un.name and ur.id == un.id
            assert abs(ur.minmax()[1] - store.RAW_SCALE) < 1e-6
            assert abs(sum(ur.weights) - store.RAW_SCALE * sum(un.weights)) < 1e-6
            assert abs(ur.reserved_value - store.RAW_SCALE * un.reserved_value) < 1e-9
            for o in list(n.outcome_space.enumerate())[:20]:
                assert abs(ur(o) - store.RAW_SCALE * un(o)) < 1e-6


def test_normalize_scenario_scales_a_raw_one():
    r = _gen(False)
    n = store.normalize_scenario(r)
    for u in n.ufuns:
        lo, hi = u.minmax()
        assert abs(hi - 1) < 1e-6


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
        s = store.generate_scenario("Trade", 0, "simple")
        assert s.info[store.NORMALIZED_KEY] is False and abs(s.ufuns[0].minmax()[1] - store.RAW_SCALE) < 1e-6


def test_on_the_fly_load_follows_the_setting(hani2_home, monkeypatch, tmp_path):
    monkeypatch.setenv("HANI2_SCENARIOS_BASE", str(tmp_path / "empty"))
    s, info, _ = store.load_scenario("Trade", 0, load_existing=False, normalized=False)
    assert info[store.NORMALIZED_KEY] is False and abs(s.ufuns[0].minmax()[1] - store.RAW_SCALE) < 1e-6
    s, info, _ = store.load_scenario("Trade", 0, load_existing=False)
    assert store.NORMALIZED_KEY not in info and abs(s.ufuns[0].minmax()[1] - 1) < 1e-9
