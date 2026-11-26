"""Simple scenarios: round numbers and plain shapes in generated preferences (the default)."""

import random

import pytest

from hani2 import projects
from hani2 import scenario_store as store
from hani2.scenarios import registry, simple
from hani2.scenarios.story import derived_hints
from hani2.tools import ufun_views as uv


def _on_grid(x, step):
    return abs(x / step - round(x / step)) < 1e-6


@pytest.mark.parametrize("type_", sorted(registry.MAKERS))
def test_every_type_is_simple(type_):
    random.seed(3)
    s = store.make_scenario(type_, 0, simple_mode=True)
    assert simple.is_simple(s)
    for u in s.ufuns:
        ws = [float(w) for w in u.weights]
        assert abs(sum(ws) - 1) < 1e-9 and all(w > 0 for w in ws)
        assert all(_on_grid(w, simple.WEIGHT_STEP / (2 if len(ws) > 10 else 1)) for w in ws)
        assert _on_grid(u.reserved_value, simple.RESERVED_STEP)
        for issue, fn in zip(s.outcome_space.issues, u.values):
            vals = [float(fn(v)) for v in issue.all]
            assert all(_on_grid(v, simple.VALUE_STEP) for v in vals), (issue.name, vals)
            assert min(vals) == 0.0 and max(vals) == 1.0
    # the hints computed from the preferences agree with the simplified numbers
    for role, d in derived_hints(s).items():
        h = s.info["hints"].get(role) or {}
        for k, v in d.items():
            if k in h:
                assert h[k] == v


def test_simple_shapes_are_linear_and_symmetric():
    from hani2.scenarios.story import down, peak, up

    rng = random.Random(0)
    with simple.simple_mode():
        assert list(up(range(5), rng).values()) == [0.0, 0.25, 0.5, 0.75, 1.0]
        assert list(down(range(3), rng).values()) == [1.0, 0.5, 0.0]
        assert list(peak(range(5), 2, rng).values()) == [0.0, 0.5, 1.0, 0.5, 0.0]
    assert not simple.active()


def test_snap_weights_add_up():
    assert simple.snap_weights([0.523, 0.477]) == [0.5, 0.5]
    w = simple.snap_weights([1, 1, 1])
    assert abs(sum(w) - 1) < 1e-9 and all(_on_grid(x, 0.1) for x in w)
    w = simple.snap_weights([5] + [0.01] * 9)  # ten issues: each keeps at least 10%
    assert abs(sum(w) - 1) < 1e-9 and all(abs(x - 0.1) < 1e-9 for x in w)
    w = simple.snap_weights([1] * 12)  # more issues than 10% steps: 5% steps
    assert abs(sum(w) - 1) < 1e-9 and all(_on_grid(x, 0.05) for x in w)


def test_off_is_unchanged():
    random.seed(1)
    a = registry.MAKERS["Lease"](0)
    random.seed(1)
    b = store.make_scenario("Lease", 0, simple_mode=False)
    assert not simple.is_simple(b)
    assert [list(u.weights) for u in a.ufuns] == [list(u.weights) for u in b.ufuns]


def test_setting_precedence(hani2_home):
    assert store.simple_scenarios() is True  # on by default
    assert store.simple_scenarios(default=False) is False  # the global setting
    projects.create_project("P", defaults={"simple_scenarios": False})
    projects.create_study("P/a", type="online", overrides={"simple_scenarios": True})
    projects.create_study("P/b", type="online")
    with projects.use_study("P/a"):
        assert store.simple_scenarios(default=False) is True  # the study wins
    with projects.use_study("P/b"):
        assert store.simple_scenarios(default=True) is False  # then the project


@pytest.fixture
def pool(hani2_home, monkeypatch, tmp_path):
    base = tmp_path / "pool"
    monkeypatch.setenv("HANI2_SCENARIOS_BASE", str(base))
    return base


def test_pool_serves_only_simple_scenarios(pool):
    store.save_scenario(store.make_scenario("Lease", 0), pool / "Lease" / "0000Lease")
    _, info, _ = store.load_scenario("Lease", 0, simple_mode=True)
    assert info["generated"] and info.get("simple")  # the saved one is not simple
    _, info, _ = store.load_scenario("Lease", 0, simple_mode=False)
    assert not info["generated"]
    _, info, _ = store.load_scenario("Lease", 0, simple_mode=True, strict=True)  # strict: the saved set wins
    assert not info["generated"]
    store.save_scenario(store.make_scenario("Lease", 1, True), pool / "Lease" / "0001Lease")
    _, info, sdir = store.load_scenario("Lease", 0, simple_mode=True)
    assert not info["generated"] and sdir.endswith("0001Lease")


def test_issue_sentences():
    from negmas import make_issue
    from negmas.preferences.value_fun import TableFun

    i = make_issue([1, 2, 3, 4, 5], "Days")
    assert uv.describe_issue(i, TableFun({1: 0, 2: .25, 3: .5, 4: .75, 5: 1})) == \
        "The higher, the better (every step is worth the same)."
    assert uv.describe_issue(i, TableFun({1: 1, 2: .75, 3: .5, 4: .25, 5: 0})).startswith("The lower, the better")
    assert uv.describe_issue(i, TableFun({1: 0, 2: .5, 3: 1, 4: .5, 5: 0}), fmt="{} days") == \
        "Best at 3 days; the further away from it, the worse."
    c = make_issue(["red", "blue"], "Color")
    assert uv.describe_issue(c, TableFun({"red": 1, "blue": 0})) == "Best: red; worst: blue."
    assert "does not matter" in (uv.describe_issue(c, TableFun({"red": 1, "blue": 1})) or "")


def test_reserved_sentence():
    from negmas import LinearAdditiveUtilityFunction, make_issue, make_os

    os_ = make_os([make_issue(3, "x")])
    u = LinearAdditiveUtilityFunction([lambda x: x / 2], weights=[1.0], outcome_space=os_, reserved_value=0.1)
    assert uv.reserved_sentence(u) == "If you do not reach agreement you get 10% (your best option gives you 100%)."
    assert "do not know" in uv.reserved_sentence(u, hidden=True, hidden_hint="You do not know it; your Assistant does")
