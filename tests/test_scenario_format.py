"""The YAML scenario format: templates, lossless save/load, seeded pools and hand-made scenarios."""

import random
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from hani2 import scenario_store as store
from hani2.config import DEFAULT_SCENARIOS
from hani2.scenarios import registry
from hani2.scenarios.story import DERIVED_HINTS, Story, fill_hints, make_story_scenario

STORY_TYPES = [n for n in registry.names() if registry.get(n).story is not None]
ALL_TYPES = registry.names()


def _files(d: Path) -> dict[str, bytes]:
    return {str(p.relative_to(d)): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}


def _texts(s, n=30):
    disp = store.display_for(s)
    return [disp.str(o, s, False, True) for o in list(s.outcome_space.enumerate_or_sample(max_cardinality=n))[:n]]


@pytest.mark.parametrize("kind", STORY_TYPES)
def test_every_story_type_has_a_clean_template(kind):
    story = registry.get(kind).story
    assert story.folder == DEFAULT_SCENARIOS / kind and story.base_info
    s, errors, warnings = store.check_scenario(story.folder)
    assert not errors and not warnings, (errors, warnings)
    assert sorted(store.role_names(s)) == sorted(story.roles)


@pytest.mark.parametrize("kind", ALL_TYPES)
def test_save_and_load_lose_nothing(kind, tmp_path):
    random.seed(f"lossless:{kind}")
    made = registry.MAKERS[kind](0)
    store.save_scenario(made, tmp_path / "a")
    first = store._load_dir(tmp_path / "a")
    if registry.get(kind).story is not None:  # stories store their roles in the order negmas loads them
        assert not store.same_scenario(made, first)
        assert _texts(made) == _texts(first)
    store.save_scenario(first, tmp_path / "b")
    second = store._load_dir(tmp_path / "b")
    assert not store.same_scenario(first, second)
    assert _files(tmp_path / "a") == _files(tmp_path / "b")
    assert _texts(first) == _texts(second)
    assert [p.name for p in (tmp_path / "a").glob("_info*")] == ["_info.yml"]


def test_a_template_drives_every_generated_scenario(tmp_path):
    builtin = registry.get("License").story
    folder = tmp_path / "License"
    shutil.copytree(DEFAULT_SCENARIOS / "License", folder)
    info = yaml.safe_load((folder / "_info.yaml").read_text(encoding="utf-8"))
    info["title"] = "Licensing a Hearing Aid"
    info["issue_description"]["Royalty"] = "Per cent of every sale"
    info["hints"]["Inventor"]["Your role"] = "You invented the device."
    store.write_info(info, folder / "_info.yaml")
    story = Story.from_folder(folder, roles=builtin.roles, setup=builtin.setup)
    s = make_story_scenario(story, 0, random.Random(1))
    assert s.info["title"] == "Licensing a Hearing Aid"
    assert s.info["issue_description"]["Royalty"] == "Per cent of every sale"
    h = s.info["hints"]["Inventor"]
    assert h["Your role"] == "You invented the device."
    assert set(DERIVED_HINTS) <= set(h) and "Your estimate of approval" in h
    # the drawn hints follow the draw, not the template
    other = make_story_scenario(story, 0, random.Random(2))
    assert other.info["hints"]["Inventor"]["Your estimate of approval"] != h["Your estimate of approval"] or \
        other.info["hints"]["Firm"] != s.info["hints"]["Firm"]


def test_from_folder_reports_mismatches(tmp_path):
    builtin = registry.get("License").story
    with pytest.raises(ValueError, match="roles"):
        Story.from_folder("License", roles={"Firm": builtin.roles["Firm"]})
    folder = tmp_path / "License"
    shutil.copytree(DEFAULT_SCENARIOS / "License", folder)
    dom = yaml.safe_load((folder / "License.yml").read_text(encoding="utf-8"))
    dom["issues"][2]["values"].append(8)  # a royalty the role functions do not score
    (folder / "License.yml").write_text(yaml.safe_dump(dom, sort_keys=False), encoding="utf-8")
    story = Story.from_folder(folder, roles=builtin.roles, setup=builtin.setup)
    with pytest.raises(ValueError, match="no score for Royalty"):
        make_story_scenario(story, 0, random.Random(0))


def _gen(base, types, count, seed):
    from hani2.make_scenarios import generate

    generate(types=types, count=count, base=base, human_index=1, cache_inverter=False, rebuild_inverses_only=False,
             min_opposition=0.35, max_opposition=0.9, set_reservations=True, user_reserved_max=0.1,
             agent_reserved_max=0.2, max_tries=60, seed=seed, force=False)


def test_seeded_pools_are_reproducible(tmp_path):
    types = ["Trade", "Island", "Lease", "Estate"]
    _gen(tmp_path / "a", types, 3, seed=11)
    _gen(tmp_path / "b", types[::-1], 3, seed=11)  # another order
    _gen(tmp_path / "c", ["Lease"], 5, seed=11)  # a larger pool keeps the first slots
    _gen(tmp_path / "d", ["Lease"], 3, seed=12)
    assert _files(tmp_path / "a") == _files(tmp_path / "b")
    a, c = _files(tmp_path / "a" / "Lease"), _files(tmp_path / "c" / "Lease")
    assert a and all(c[k] == v for k, v in a.items())
    assert _files(tmp_path / "d" / "Lease") != a


def test_a_hand_made_scenario_is_served(hani2_home, monkeypatch, tmp_path):
    base = tmp_path / "scenarios"
    monkeypatch.setenv("HANI2_SCENARIOS_BASE", str(base))
    folder = base / "MyCase"
    shutil.copytree(DEFAULT_SCENARIOS / "Estate", folder)
    info = yaml.safe_load((folder / "_info.yaml").read_text(encoding="utf-8"))
    for h in info["hints"].values():
        for k in DERIVED_HINTS:
            h.pop(k, None)
    store.write_info(info, folder / "_info.yaml")
    assert "MyCase" in store.available_types()
    s, binfo, sdir = store.load_scenario("MyCase", 4)
    assert not binfo["generated"] and Path(sdir) == folder
    assert "You get" in store.display_for(s, sdir).str((1, 0, 2, 3), s, False, True)
    fill_hints(s)
    assert s.info["hints"]["human"]["Most important issue"] in [i.name for i in s.outcome_space.issues]


def test_save_scenario_removes_stale_files(tmp_path):
    folder = tmp_path / "x"
    shutil.copytree(DEFAULT_SCENARIOS / "Trade", folder)
    (folder / "_info.yml").write_text("title: stale\n", encoding="utf-8")
    (folder / "Old.yml").write_text("name: Old\n", encoding="utf-8")
    s = store._load_dir(folder)
    store.save_scenario(s, folder)
    names = sorted(p.name for p in folder.iterdir())
    assert "Old.yml" not in names and "_info.yml" in names and "_info.yaml" not in names


def test_cli_scenario_new_and_check(tmp_path):
    from hani2.cli import app

    r = CliRunner()
    res = r.invoke(app, ["scenario", "new", "CityTrip", str(tmp_path / "Trip")])
    assert res.exit_code == 0, res.output
    assert _files(tmp_path / "Trip") == _files(DEFAULT_SCENARIOS / "CityTrip")
    res = r.invoke(app, ["scenario", "new", "Lease", str(tmp_path / "L"), "--generate", "--seed", "4"])
    assert res.exit_code == 0, res.output
    res = r.invoke(app, ["scenario", "check", str(tmp_path)])
    assert res.exit_code == 0, res.output
    assert "2 scenario(s), 0 with errors" in res.output
    (tmp_path / "L" / "_info.yaml").write_text("human_role: Nobody\n", encoding="utf-8")
    res = r.invoke(app, ["scenario", "check", str(tmp_path / "L")])
    assert res.exit_code == 1 and "human_role" in res.output


@pytest.mark.parametrize("kind", STORY_TYPES)
def test_template_hints_match_its_utility_functions(kind):
    from hani2.scenarios.story import derived_hints

    s = store._load_dir(DEFAULT_SCENARIOS / kind)
    for role, computed in derived_hints(s).items():
        written = s.info["hints"][role]
        assert {k: written.get(k) for k in computed} == computed, role


def test_bare_names_are_bundled_templates_whatever_the_cwd(tmp_path, monkeypatch):
    _gen(tmp_path, ["Lease"], 1, seed=0)  # a pool folder with a Lease category
    monkeypatch.chdir(tmp_path)
    story = Story.from_folder("Lease", roles=registry.get("Lease").story.roles)
    assert story.folder == DEFAULT_SCENARIOS / "Lease"


def test_issue_types_in_the_template_are_kept(tmp_path):
    builtin = registry.get("Estate").story
    folder = tmp_path / "Estate"
    shutil.copytree(DEFAULT_SCENARIOS / "Estate", folder)
    dom = yaml.safe_load((folder / "Estate.yml").read_text(encoding="utf-8"))
    dom["issues"][0] = {"name": dom["issues"][0]["name"], "type": "DiscreteOrdinalIssue",
                        "values": list(range(7))}
    (folder / "Estate.yml").write_text(yaml.safe_dump(dom, sort_keys=False), encoding="utf-8")
    story = Story.from_folder(folder, roles=builtin.roles, setup=builtin.setup)
    s = make_story_scenario(story, 0, random.Random(0))
    assert type(s.outcome_space.issues[0]).__name__ == "DiscreteOrdinalIssue"
    assert s.outcome_space.name == "Estate"


def test_the_results_keep_the_exact_scenario_played(hani2_home):
    from hani2.testing import make_session

    _gen(None, ["Lease"], 1, seed=3)
    slot = store.base_dir() / "Lease" / "0000Lease"
    s = make_session(scenario_type="Lease", n_steps=4)
    s.start()
    assert s.wait_for_turn()
    s.play_counters(6)
    assert s.wait_until_done()
    saved = list((hani2_home / "db" / "tester" / "scenarios").iterdir())
    assert len(saved) == 1
    assert _files(saved[0]) == {k: v for k, v in _files(slot).items() if not k.endswith(".pkl")}
    assert any((hani2_home / "db" / "tester" / "mechanisms").iterdir())  # written after the scenario copy
