"""Strict scenarios: a project or study can require that only saved scenarios are served."""

import pytest

from hani2 import projects
from hani2 import scenario_store as store
from hani2.testing import make_session


def _gen(base, types, count=2, seed=0):
    from hani2.make_scenarios import generate

    generate(types=types, count=count, base=base, human_index=1, cache_inverter=False, rebuild_inverses_only=False,
             min_opposition=0.35, max_opposition=0.9, set_reservations=True, user_reserved_max=0.1,
             agent_reserved_max=0.2, max_tries=60, seed=seed, force=False)


@pytest.fixture
def pool(hani2_home, monkeypatch, tmp_path):
    base = tmp_path / "pool"
    monkeypatch.setenv("HANI2_SCENARIOS_BASE", str(base))
    return base


def test_strict_never_generates(pool):
    with pytest.raises(store.StrictScenarioError, match="no saved scenarios"):
        store.load_scenario("Lease", 0, strict=True)
    _, info, _ = store.load_scenario("Lease", 0)  # not strict: generated
    assert info["generated"]
    _gen(pool, ["Lease"])
    s, info, sdir = store.load_scenario("Lease", 3, load_existing=False, strict=True)  # strict always uses the pool
    assert not info["generated"] and info["load_index"] == 1 and sdir.endswith("0001Lease")
    with pytest.raises(store.StrictScenarioError, match="no saved scenario 'Nope'"):
        store.load_scenario("Lease", 0, name="Nope", strict=True)
    assert store.load_scenario("Lease", 0, name="0001Lease", strict=True)[1]["scenario_name"] == "0001Lease"


def test_strict_reports_a_broken_slot(pool):
    _gen(pool, ["Lease"])
    (pool / "Lease" / "0000Lease" / "Lease.yml").write_text("issues: [oops\n", encoding="utf-8")
    with pytest.raises(store.StrictScenarioError, match="cannot load"):
        store.load_scenario("Lease", 0, strict=True)
    _, info, _ = store.load_scenario("Lease", 0)  # not strict: replaced by a generated one
    assert info["generated"]
    assert "Lease" in store.pool_problems(["Lease"]) and "Trade" in store.pool_problems(["Trade"])


def test_strict_is_a_project_and_study_setting(hani2_home):
    projects.create_project("ANAC", defaults={"strict_scenarios": True})
    projects.create_study("ANAC/r1", type="online")
    projects.create_study("ANAC/practice", type="online", overrides={"strict_scenarios": False})
    projects.create_study("Pilot/s1", type="online")
    projects.create_study("Pilot/final", type="online", overrides={"strict_scenarios": True})
    for ref, want in (("ANAC/r1", True), ("ANAC/practice", False), ("Pilot/s1", False), ("Pilot/final", True)):
        with projects.use_study(ref):
            assert store.strict_scenarios() is want, ref
    with projects.use_study(None):
        assert store.strict_scenarios() is False  # off unless a project or study opts in


def test_a_strict_study_serves_only_its_saved_scenarios(hani2_home):
    projects.create_project("ANAC", defaults={"strict_scenarios": True})
    ref = projects.create_study("ANAC/r1", type="online")
    s = make_session(user="u1", partner=None, study="ANAC/r1", scenario_type="Lease", query={"noautostart": "1"})
    assert s.scenario is None and s.phase != "ready"
    assert any("strict scenarios" in m.get("message", "") for m in s.hub.of_type("toast"))

    _gen(projects.study_dir(projects.parse_ref("ANAC/r1")) / "scenarios", ["Lease"])
    s = make_session(user="u2", partner=None, study="ANAC/r1", scenario_type="Lease", query={"noautostart": "1"})
    s.admin_prefs["load_existing"] = False  # an admin cannot switch the pool off in a strict study
    s.load("Lease")
    assert s.scenario is not None and not s.ss["scenario_info"]["generated"]
    assert ref is not None
