import random

import pytest
from negmas import Scenario

from hani2 import scenario_sets
from hani2 import scenario_store as store
from hani2.scenarios import registry
from hani2.scenarios.story import _opposition

STORY_TYPES = [n for n in registry.names() if registry.get(n).story is not None]


@pytest.mark.parametrize("kind", registry.names())
def test_every_type_saves_and_loads(kind, tmp_path):
    random.seed(7)
    s = store.MAKER_MAP[kind](0)
    d = tmp_path / kind
    s.dumpas(d)
    r = Scenario.load(d)
    assert r is not None and len(r.ufuns) == 2
    r.info = store._read_info(d)
    names = [u.name for u in r.ufuns]
    assert names == sorted(names)  # Scenario.load sorts the roles by name
    if registry.get(kind).story is not None:
        # stories build their roles in that order, so nothing moves on reload
        assert [u.name for u in s.ufuns] == names
        for o in list(r.outcome_space.enumerate_or_sample(max_cardinality=20)):
            for a, b in zip(s.ufuns, r.ufuns):
                assert abs(float(a(o)) - float(b(o))) < 1e-6
        assert set(r.info["hints"]) == set(names)
        assert r.info["short_description"] and "**The Domain**" in r.info["long_description"]
    disp = store.display_for(r, str(d))
    o = next(iter(r.outcome_space.enumerate_or_sample(max_cardinality=3)))
    assert isinstance(disp.str(o, r, False, True), str)


@pytest.mark.parametrize("kind", STORY_TYPES)
def test_stories_keep_the_story_and_vary_the_utilities(kind):
    story = registry.get(kind).story
    draws = [store.MAKER_MAP[kind](i) for i in range(8)]
    texts = {(d.info["title"], d.info["short_description"], d.info["long_description"]) for d in draws}
    assert len(texts) == 1
    assert len({tuple(round(w, 4) for w in d.ufuns[0].weights) for d in draws}) > 1
    lo, hi = story.band
    in_band = [lo <= _opposition(d.outcome_space, list(d.ufuns)) <= hi for d in draws]
    assert sum(in_band) >= 7


def test_type_names_are_not_prefixes_of_each_other():
    names = registry.names()
    for a in names:
        for b in names:
            assert a == b or not b.startswith(a), (a, b)


def test_default_set_is_han2026_and_sets_are_case_insensitive(monkeypatch):
    assert scenario_sets.active_set() == "HAN2026"
    assert store.scenario_order() == ["Trade", "Island", "Grocery"]
    assert scenario_sets.resolve("anac2027") == "ANAC2027"
    assert store.scenario_order("anac2027")[0] == "Lease"
    monkeypatch.setenv("HANI2_SCENARIO_SET", "mit2025")
    assert store.scenario_order() == ["Furniture", "Lease", "Consulting"]
    assert store.scenario_order("IAGO") == ["Resources", "Estate", "Grocery"]


def test_every_bundled_set_only_lists_known_types():
    sets, default = scenario_sets.load_sets()
    assert default in sets
    for name, types in sets.items():
        for t in types:
            assert t in store.MAKER_MAP, (name, t)


def test_user_sets_and_a_changed_order_file(hani2_home):
    (hani2_home / "settings").mkdir(parents=True)
    (hani2_home / "settings" / "scenario_sets.yaml").write_text("sets:\n  Mine: [Lease, Trade]\n")
    assert scenario_sets.resolve("mine") == "Mine" and "HAN2026" in scenario_sets.set_names()
    (hani2_home / "settings" / "scenario_order.txt").write_text("Trade\nIsland\nGrocery\n")
    assert scenario_sets.active_set() == "HAN2026"  # an unchanged copy (as `hani2 setup` writes) is not custom
    (hani2_home / "settings" / "scenario_order.txt").write_text("Island\n")
    assert scenario_sets.active_set() == "Custom" and store.scenario_order() == ["Island"]
    assert store.scenario_order("Mine") == ["Lease", "Trade"]
    (hani2_home / "settings" / "scenario_sets.yaml").write_text("sets: [broken")
    assert "HAN2026" in scenario_sets.set_names()  # a broken file is ignored


def test_role_assignment_rules():
    lease = store.MAKER_MAP["Lease"](0)  # roles Landlord, Tenant; suggested Tenant
    assert store.assign_human(lease) == 1
    assert store.assign_human(lease, "index", human_index=0) == 0
    assert store.assign_human(lease, "roles", preferred_roles=["landlord"]) == 0
    assert [store.assign_human(lease, "alternate", counter=c) for c in range(3)] == [0, 1, 0]
    assert store.assign_human(lease, "random") in (0, 1)
    island = store.MAKER_MAP["Island"](0)  # roles agent, human
    for rule in ("auto", "index", "roles", "alternate", "random"):
        assert island.ufuns[store.assign_human(island, rule, human_index=0, counter=0)].name == "human"


def test_session_uses_the_set_and_the_role_rule(hani2_home):
    from hani2.testing import make_session

    s = make_session(scenario_type=None, load=False)
    s.admin_prefs["scenario_set"] = "ANAC2027"
    s.admin_prefs["allow_scenario_selection"] = False
    s.load()
    assert s.ss["scenario_info"]["scenario_type"] in scenario_sets.set_types("ANAC2027")
    s2 = make_session(scenario_type="Lease", load=False)
    s2.admin_prefs["role_rule"] = "roles"
    s2.admin_prefs["human_roles"] = ["Landlord"]
    s2.load("Lease")
    assert s2.ss["human_id"] == "Landlord (You)"


STORY_FILE = '''
from hani2.scenarios.story import Issue, Side, Story, down, up

def _buyer(rng, ctx):
    return Side(values={"Price": down([1, 2, 3], rng), "Size": up(["S", "M", "L"], rng)},
                weights={"Price": rng.uniform(1, 2), "Size": rng.uniform(0.5, 1.5)})

def _seller(rng, ctx):
    return Side(values={"Price": up([1, 2, 3], rng), "Size": down(["S", "M", "L"], rng)},
                weights={"Price": rng.uniform(1, 2), "Size": rng.uniform(0.5, 1.5)})

STORIES = [Story(
    type="TestShirt", title="Shirt", short_description="A shirt is sold.",
    long_description="**The Domain** Price and size.",
    roles={"Buyer": _buyer, "Seller": _seller},
    role_descriptions={"Buyer": "the buyer", "Seller": "the seller"},
    issues=[Issue("Price", [1, 2, 3], fmt="${}"), Issue("Size", ["S", "M", "L"])],
    band=(0.0, 1.0),
)]
'''


def test_scenario_types_from_a_file(tmp_path, monkeypatch, hani2_home):
    f = tmp_path / "shirt.py"
    f.write_text(STORY_FILE)
    monkeypatch.setenv("HANI2_SCENARIO_TYPES", str(f))
    assert "TestShirt" in registry.load_plugins()
    s, info, _ = store.load_scenario("TestShirt", 0)
    assert info["generated"] and s.outcome_space.name == "TestShirt"
    try:
        assert store.display_for(s).str((2, "M"), s, False, True) == "Price: $2, Size: M"
    finally:
        registry.unregister("TestShirt")


def test_catalog_page_lists_every_type_and_set():
    from pathlib import Path

    page = (Path(__file__).resolve().parents[1] / "docs" / "guide" / "scenario-sets.md").read_text()
    sets, _ = scenario_sets.load_sets()
    for name in sets:
        assert name == "Custom" or f"## {name}\n" in page, name
    for t in registry.names():
        assert f"### {t}\n" in page, t
        story = registry.get(t).story
        if story is not None:
            assert story.short_description in page, t


def test_sets_made_of_sets(hani2_home):
    sets, _ = scenario_sets.load_sets()
    assert sets["HI2027"] == sets["HAN2027"] == sets["ANAC2027"]
    assert len(sets["ANAC2027"]) == len(set(sets["ANAC2027"])) == 8
    (hani2_home / "settings").mkdir(parents=True)
    (hani2_home / "settings" / "scenario_sets.yaml").write_text(
        "sets:\n"
        "  A: [Lease, Trade]\n"
        "  B: [Trade, Island, '@A']\n"
        "  C: [a, b, Grocery, Lease]\n"  # bare set names (any case), duplicates dropped
        "  Loop1: [Loop2, Energy]\n"
        "  Loop2: [Loop1, Chores]\n"
    )
    sets, _ = scenario_sets.load_sets()
    assert sets["B"] == ["Trade", "Island", "Lease"]
    assert sets["C"] == ["Lease", "Trade", "Island", "Grocery"]
    assert set(sets["Loop1"]) == {"Energy", "Chores"} and set(sets["Loop2"]) == {"Energy", "Chores"}
    assert store.scenario_order("c") == ["Lease", "Trade", "Island", "Grocery"]
