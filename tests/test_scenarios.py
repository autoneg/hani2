import pytest

from hani2 import scenario_store as store
from hani2.display import DefaultOutcomeDisplay


@pytest.mark.parametrize("kind", ["Trade", "Island", "Grocery"])
def test_generate_each_type(kind):
    s, info, sdir = store.load_scenario(kind, 3, load_existing=False)
    assert info["generated"] and sdir is None
    assert len(s.ufuns) == 2
    disp = store.display_for(s)
    o = next(iter(s.outcome_space.enumerate_or_sample(max_cardinality=5)))
    assert isinstance(disp.str(o, s, False, True), str)


def test_setup_copies_samples_and_they_load(hani2_home):
    from hani2.setup import run_setup

    run_setup(quiet=True)
    assert (hani2_home / "settings" / "env.json").exists()
    assert set(store.list_scenarios("Trade")) == {"Trade"}
    s, info, sdir = store.load_scenario("Trade", 7)
    assert not info["generated"] and sdir and sdir.endswith("Trade")
    assert s.info.get("title")


def test_pool_wraps_around(hani2_home):
    from hani2.make_scenarios import generate

    generate(types=["Trade"], count=2, base=None, human_index=1, cache_inverter=True, rebuild_inverses_only=False,
             min_opposition=0.0, max_opposition=1.0, set_reservations=True, user_reserved_max=0.1,
             agent_reserved_max=0.2, max_tries=5, seed=0, force=False)
    names = store.list_scenarios("Trade")
    assert names == ["0000Trade", "0001Trade"]
    _, info, _ = store.load_scenario("Trade", 5)
    assert info["load_index"] == 1


def test_next_index_persists(tmp_path):
    assert store.next_index(tmp_path) == 0
    assert store.next_index(tmp_path) == 1
    assert store.next_index(tmp_path, advance=False) == 2


def test_scenario_order_and_pid_type():
    assert store.scenario_order() == ["Trade", "Island", "Grocery"]
    assert store.pid_type("abc") == store.pid_type("abc")


def test_default_display():
    s, _, _ = store.load_scenario("Trade", 0, load_existing=False)
    assert DefaultOutcomeDisplay().str(None, s, False, False) == "❓"
