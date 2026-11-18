"""Scheduling methods (opponents, Assistants, scenarios), their validation, the admin API,
results columns, the docs page, and refused confusing combinations of settings."""

import csv
import json
import os
import sqlite3
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from hani2 import assignment, conflicts, groups, projects, scheduling
from hani2 import scenario_store as store
from hani2.projects import StudyRef
from hani2.testing import make_session

HELLO = "level1_hello:HelloAgent"
RULES = "level2_rules:RulesAgent"
COACH = "level5_deal_coach:DealCoach"
POOL = ["BoulwareTBNegotiator", "ConcederTBNegotiator", "LinearTBNegotiator"]
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def study(hani2_home):
    projects.create_project("HI", kind="assistant")
    projects.create_study("HI/s1", type="prolific")
    return StudyRef("HI", "s1")


@pytest.fixture
def client(hani2_home, monkeypatch):
    monkeypatch.setenv("HANI2_OPPONENTS", "BoulwareTBNegotiator")
    from hani2.server import app, hub

    hub.sessions.clear()
    with TestClient(app) as c:
        yield c
    hub.sessions.clear()


def _set_study(ref, **data):
    f = projects.study_dir(ref) / projects.STUDY_FILE
    d = projects.read_yaml(f)
    d.update(data)
    projects.write_yaml(f, d)


def prolific(pid, ref, **kw):
    kw.setdefault("query", {"noautostart": "1"})
    return make_session(user=f"prolific_{pid}", mode="guest", partner=None, study=ref, **kw)


def _play(s):
    s.start()
    s.wait_for_turn()
    s.send_counter()
    s.wait_for_turn()
    s.end()
    s.wait_until_done()


def _flat(text):
    """CLI output without the box drawing and line wrapping of error panels."""
    return " ".join(text.replace("│", " ").split())


def _rows(s):
    return list(csv.DictReader(open(s.ss["user_path"] / "results.csv")))


# --------------------------------------------------------------------------- #
# The registry                                                                 #
# --------------------------------------------------------------------------- #
REQUIRED = {
    "opponents": {"latin_square", "random", "cyclic", "fixed_order", "external"},
    "assistants": {"balanced", "random_fixed", "random_each", "round_robin", "external"},
    "scenarios": {"by_participant", "set_order", "random", "latin_square", "external"},
}


def test_registry_has_every_method_with_details():
    for dim, keys in REQUIRED.items():
        assert keys <= set(scheduling.method_keys(dim))
        for m in scheduling.methods(dim):
            assert m.title and m.summary and "\n" not in m.summary
            d = m.details
            assert "**Advantages**" in d and "**Disadvantages**" in d and "$$" in d, (dim, m.key)
            assert "<<" not in d  # every example table was filled in
            if m.key != "external":
                assert "| Participant" in d, (dim, m.key)  # an example table
    assert scheduling.DEFAULTS == {"opponents": "latin_square", "assistants": "balanced", "scenarios": "by_participant"}


def test_validation_lists_the_valid_methods():
    with pytest.raises(ValueError, match="use one of latin_square, random, cyclic"):
        scheduling.check_method("opponents", "nope")
    with pytest.raises(ValueError, match="unknown dimension 'partners'"):
        scheduling.check_scheduling({"partners": "random"})
    with pytest.raises(ValueError, match="mapping"):
        scheduling.check_scheduling("random")
    assert scheduling.check_scheduling({"opponents": "random", "scenarios": None}) == {"opponents": "random"}


def test_docs_page_is_in_sync_with_the_registry():
    page = (ROOT / "docs" / "guide" / "scheduling.md").read_text()
    assert scheduling.docs_section(page) == scheduling.markdown_reference(), \
        "run: python -m hani2.scheduling docs/guide/scheduling.md"
    for dim in scheduling.DIMENSIONS:
        for m in scheduling.methods(dim):
            assert f"(`{m.key}`)" in page and m.details in page


def test_example_tables_follow_the_rules():
    d = scheduling.get_method("opponents", "latin_square").details
    assert "| 3 | C | B | A |" in d  # participant 3: the reversed first row (odd pool)
    assert "| 1 | B | C | A |" in scheduling.get_method("opponents", "cyclic").details
    assert "| 3 | A | B | C |" in scheduling.get_method("opponents", "fixed_order").details
    assert "| 4 | B |" in scheduling.get_method("assistants", "round_robin").details


# --------------------------------------------------------------------------- #
# The rules                                                                    #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("n", [2, 3, 4, 5])
def test_latin_square_opponents_are_order_and_carry_over_balanced(n):
    pool = [f"O{j}" for j in range(n)]
    R = n if n % 2 == 0 else 2 * n
    orders = [[scheduling.pick_opponent("latin_square", pool, i, k) for k in range(n)] for i in range(R)]
    for k in range(n):
        assert Counter(o[k] for o in orders) == Counter({p: R // n for p in pool})
    follows = Counter((o[k], o[k + 1]) for o in orders for k in range(n - 1))
    assert len(follows) == n * (n - 1) and len(set(follows.values())) == 1
    assert all(sorted(o) == sorted(pool) for o in orders)


def test_cyclic_fixed_and_random_opponents():
    assert [scheduling.pick_opponent("cyclic", POOL, 1, k) for k in range(3)] == [POOL[1], POOL[2], POOL[0]]
    assert [scheduling.pick_opponent("fixed_order", POOL, 7, k) for k in range(4)] == POOL + POOL[:1]
    a = [scheduling.pick_opponent("random", POOL, 0, k, seed="s|u") for k in range(30)]
    assert a == [scheduling.pick_opponent("random", POOL, 0, k, seed="s|u") for k in range(30)]  # reproducible
    assert set(a) == set(POOL)
    assert scheduling.pick_opponent("external", POOL, 0, 0) is None


def test_scenario_rules():
    T = ["X", "Y", "Z"]
    assert [scheduling.pick_scenario_type("by_participant", T, i, 5) for i in range(4)] == ["X", "Y", "Z", "X"]
    assert [scheduling.pick_scenario_type("set_order", T, 9, k, counter=k + 1) for k in range(3)] == ["Y", "Z", "X"]
    rows = [[scheduling.pick_scenario_type("latin_square", T, i, k) for k in range(3)] for i in range(6)]
    for k in range(3):
        assert Counter(r[k] for r in rows) == Counter({t: 2 for t in T})
    r = [scheduling.pick_scenario_type("random", T, 0, k, seed="x") for k in range(20)]
    assert r == [scheduling.pick_scenario_type("random", T, 0, k, seed="x") for k in range(20)]


def _human(study, i):
    return SimpleNamespace(user=f"prolific_H{i}", is_admin=False, study_ref=study)


def test_assistant_methods_fixed_per_human(study):
    pool = [HELLO, RULES, COACH]
    got = [assignment.assign_assistant(_human(study, i), pool, method="round_robin") for i in range(5)]
    assert got == [HELLO, RULES, COACH, HELLO, RULES]
    # kept per human even if the method changes later
    assert assignment.assign_assistant(_human(study, 1), pool, method="balanced") == RULES
    h = assignment.read_assignments(study)["humans"]["prolific_H1"]
    assert h["assistant_scheduling"] == "round_robin"
    other = StudyRef("HI", "s2")
    projects.create_study(other)
    rnd = [assignment.assign_assistant(SimpleNamespace(user=f"prolific_R{i}", is_admin=False, study_ref=other),
                                       pool, method="random_fixed") for i in range(30)]
    assert set(rnd) == set(pool)  # random, not in pool order
    again = [assignment.assign_assistant(SimpleNamespace(user=f"prolific_R{i}", is_admin=False, study_ref=other),
                                         pool, method="random_fixed") for i in range(30)]
    assert again == rnd


def test_random_each_assistant_changes_between_negotiations(study, monkeypatch):
    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "8")
    _set_study(study, assistants=[HELLO, RULES, COACH], scheduling={"assistants": "random_each"}, practice=False)
    s = prolific("E", study)
    seen = []
    for _ in range(8):
        spec = s.assistant_choice.spec
        assert s.assistant_choice.scheduling == "random_each"
        s.refresh_assistant(s.round_plan)  # a reconnect: same negotiation, same Assistant
        assert s.assistant_choice.spec == spec
        seen.append(spec)
        _play(s)
        s.load()
        if len(seen) == 3:  # a later visit (a new session) continues where the human left off
            s = prolific("E", study)
            assert s.assistant_choice.spec == scheduling.pick_assistant_each(
                [HELLO, RULES, COACH], 3, f"{study}|prolific_E")
    assert len(set(seen)) > 1
    assert "assistant" not in assignment.read_assignments(study)["humans"].get("prolific_E", {})
    assert {r["assistant_scheduling"] for r in _rows(s)} == {"random_each"}
    assert [r["assistant"] for r in _rows(s)] == seen


def test_external_with_a_practice_round(study, monkeypatch):
    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "1")
    _set_study(study, opponents=POOL, practice=True,
               scheduling={"opponents": "external", "assistants": "external", "scenarios": "external"})
    d = projects.study_dir(study) / "results" / "prolific_PR"
    d.mkdir(parents=True)
    (d / "schedule.json").write_text(json.dumps({"version": 2, "negotiations": [
        {"slot": 0, "agent_class_name": "LinearTBNegotiator", "scenario_type": "Trade", "assistant": RULES}]}))
    s = prolific("PR", study)
    assert s.round_plan["practice"] is True
    assert s.round_plan["opponent_scheduling"] == "practice" and s.round_plan["scenario_scheduling"] == "practice"
    assert type(s.support_agent).__name__ == "RulesAgent" and not s.assistant_error  # the first slot's Assistant
    db = sqlite3.connect(projects.study_dir(study) / "results" / "events.db")
    assert db.execute("SELECT COUNT(*) FROM events WHERE action='scheduling_missing'").fetchone()[0] == 0
    _play(s)
    s.load()
    assert s.round_plan["practice"] is False and s.round_plan["partner"] == "LinearTBNegotiator"
    assert s.round_plan["opponent_scheduling"] == "external" and s.round_plan["scenario_scheduling"] == "external"


def test_external_assistant_without_schedule_fails_loudly(study):
    _set_study(study, assistants=[HELLO], scheduling={"assistants": "external"})
    s = prolific("X", study)
    assert s.support_agent is None and "external" in s.assistant_error
    assert s.snapshot()["assistant_error"] == s.assistant_error
    d = s.ss["user_path"]
    (d / "schedule.json").write_text(json.dumps({"version": 2, "assistant": RULES, "negotiations": []}))
    s2 = prolific("X", study)
    assert type(s2.support_agent).__name__ == "RulesAgent" and s2.assistant_choice.scheduling == "external"


# --------------------------------------------------------------------------- #
# Studies: methods in use, merging, recording                                  #
# --------------------------------------------------------------------------- #
def test_methods_merge_per_dimension(study):
    projects.create_project("HI", scheduling={"opponents": "random", "scenarios": "set_order"})
    _set_study(study, scheduling={"scenarios": "latin_square"})
    eff, explicit, errors = scheduling.resolve(study)
    assert eff == {"opponents": "random", "assistants": "balanced", "scenarios": "latin_square"}
    assert explicit == {"opponents": "random", "scenarios": "latin_square"} and errors == []
    assert scheduling.methods_for(None) == scheduling.DEFAULTS
    # a hand-edited bad name: reported, the default used
    _set_study(study, scheduling={"opponents": "zigzag"})
    eff, _, errors = scheduling.resolve(study)
    assert eff["opponents"] == "random" and "zigzag" in errors[0] and "latin_square" in errors[0]


def test_create_study_merges_and_validates_scheduling(study):
    projects.create_study(study, scheduling={"opponents": "cyclic"})
    projects.create_study(study, scheduling={"assistants": "round_robin"})
    assert projects.load_study(study).overrides["scheduling"] == {"opponents": "cyclic", "assistants": "round_robin"}
    with pytest.raises(ValueError, match="use one of"):
        projects.create_study(study, scheduling={"scenarios": "nope"})


@pytest.mark.parametrize("method", ["fixed_order", "cyclic", "random", "latin_square"])
def test_opponent_methods_in_a_prolific_study(study, monkeypatch, method):
    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "3")
    _set_study(study, opponents=POOL, practice=False, scheduling={"opponents": method})
    for i in range(3):
        s = prolific(f"O{i}", study)
        order = []
        for k in range(3):
            assert s.round_plan["opponent_scheduling"] == method
            order.append(s.round_plan["partner"])
            assert s.round_plan["partner"] == scheduling.pick_opponent(method, POOL, i, k, f"{study}|{s.user}")
            _play(s)
            s.load()
        assert [r["agent_type"] for r in _rows(s)] == order
        assert {r["opponent_scheduling"] for r in _rows(s)} == {method}
        if method == "fixed_order":
            assert order == POOL


def test_scenario_methods_in_a_prolific_study(study, monkeypatch):
    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "3")
    _set_study(study, opponents=POOL, practice=False, scheduling={"scenarios": "latin_square"})
    types = store.scenario_order()
    s = prolific("S0", study)
    got = []
    for k in range(3):
        got.append(s.round_plan["type"])
        _play(s)
        s.load()
    assert got == [scheduling.pick_scenario_type("latin_square", types, 0, k) for k in range(3)]
    assert {r["scenario_scheduling"] for r in _rows(s)} == {"latin_square"}


def test_defaults_are_recorded(study, monkeypatch):
    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "1")
    _set_study(study, opponents=POOL, assistants=[HELLO, RULES], practice=False)
    s = prolific("D", study)
    _play(s)
    row = _rows(s)[0]
    assert (row["opponent_scheduling"], row["assistant_scheduling"], row["scenario_scheduling"]) == \
        ("latin_square", "balanced", "by_participant")


def test_outside_a_study_nothing_is_scheduled(hani2_home):
    s = make_session(partner=None, query={"opponents": ",".join(POOL)})
    _play(s)
    row = _rows(s)[0]
    assert row["opponent_scheduling"] == "" and row["scenario_scheduling"] == ""


def test_schedule_json_wins_and_external_missing_is_visible(study, monkeypatch):
    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "2")
    _set_study(study, opponents=POOL, practice=False, scheduling={"opponents": "external", "scenarios": "external"})
    s = prolific("M", study)  # no schedule.json
    assert s.round_plan["opponent_scheduling"] == "external:missing"
    assert s.round_plan["scenario_scheduling"] == "external:missing"
    _play(s)
    assert _rows(s)[0]["opponent_scheduling"] == "external:missing"
    db = sqlite3.connect(projects.study_dir(study) / "results" / "events.db")
    assert db.execute("SELECT COUNT(*) FROM events WHERE action='scheduling_missing'").fetchone()[0] >= 2
    d = projects.study_dir(study) / "results" / "prolific_W"
    d.mkdir(parents=True)
    (d / "schedule.json").write_text(json.dumps({"version": 2, "negotiations": [
        {"slot": 0, "agent_class_name": "LinearTBNegotiator", "scenario_type": "Trade", "scenario_index": 0}]}))
    _set_study(study, scheduling={"opponents": "random"})
    s = prolific("W", study)
    assert s.round_plan["partner"] == "LinearTBNegotiator" and s.round_plan["opponent_scheduling"] == "external"
    assert s.round_plan["scenario_scheduling"] == "external"


def test_plain_study_sessions(study):
    _set_study(study, opponents=POOL, scheduling={"opponents": "fixed_order", "scenarios": "latin_square"})
    s = make_session(user="user_a", partner=None, study=study, scenario_type=None)
    assert s.round_plan["partner"] == POOL[0] and s.round_plan["opponent_scheduling"] == "fixed_order"
    assert s.round_plan["scenario_scheduling"] == "latin_square"
    _set_study(study, scheduling={})
    s = make_session(user="user_b", partner=None, study=study, scenario_type=None)
    assert s.round_plan["scenario_scheduling"] == "set_order"  # unchanged unless chosen explicitly


# --------------------------------------------------------------------------- #
# The settings-file Assistant fails loudly                                     #
# --------------------------------------------------------------------------- #
def test_settings_assistant_fails_loudly(study):
    s = prolific("B", study, agent_class="nope.nothing:Missing")
    assert s.support_agent is None and "assistant_settings.json" in s.assistant_error
    db = sqlite3.connect(projects.study_dir(study) / "results" / "events.db")
    assert db.execute("SELECT COUNT(*) FROM events WHERE action='assistant_failed'").fetchone()[0] >= 1
    _play(s)
    assert "nope.nothing:Missing" in _rows(s)[0]["assistant_error"]


# --------------------------------------------------------------------------- #
# Admin API                                                                    #
# --------------------------------------------------------------------------- #
def test_scheduling_methods_endpoint(client):
    assert client.get("/api/admin/scheduling-methods").status_code == 401
    client.post("/api/auth/login", json={"username": "admin", "password": "adminpass"})
    data = client.get("/api/admin/scheduling-methods").json()
    assert set(data) == {"dimensions", "defaults"}
    assert set(data["dimensions"]) == {"opponents", "assistants", "scenarios"}
    for dim, items in data["dimensions"].items():
        assert REQUIRED[dim] <= {m["key"] for m in items}
        for m in items:
            assert set(m) == {"key", "title", "summary", "details"}
    assert data["defaults"] == scheduling.DEFAULTS


def test_study_endpoints_round_trip_scheduling(study, client):
    client.post("/api/auth/login", json={"username": "admin", "password": "adminpass"})
    url = "/api/admin/projects/HI/studies/s1"
    body = {"data": {"type": "online", "scheduling": {"opponents": "random", "assistants": "round_robin"}}}
    assert client.put(url, json=body).json()["ok"]
    got = client.get(url).json()
    assert got["scheduling"] == {"opponents": "random", "assistants": "round_robin"}
    assert got["scheduling_effective"] == {"opponents": "random", "assistants": "round_robin",
                                           "scenarios": "by_participant"}
    assert got["errors"] == []
    # what a client read, edited and sent back: the top-level scheduling wins, read-only keys dropped
    got["scheduling"] = {"opponents": "cyclic"}
    assert client.put(url, json={"data": got}).json()["ok"]
    again = client.get(url).json()
    assert again["scheduling"] == {"opponents": "cyclic"} and again["scheduling_effective"]["assistants"] == "balanced"
    raw = projects.read_yaml(projects.study_dir(study) / projects.STUDY_FILE)
    assert "links" not in raw and "scheduling_effective" not in raw and "errors" not in raw
    r = client.put(url, json={"data": {"scheduling": {"opponents": "sideways"}}})
    assert r.status_code == 400 and "latin_square" in r.json()["detail"]
    r = client.put(url, json={"yaml": "n_required: 3\noverrides:\n  n_required: 5\n"})
    assert r.status_code == 400 and "n_required" in r.json()["detail"]
    assert client.put("/api/admin/projects/HI", json={"data": {"kind": "assistant",
                                                               "scheduling": {"scenarios": "random"}}}).json()["ok"]
    p = client.get("/api/admin/projects/HI").json()
    assert p["scheduling"] == {"scenarios": "random"}
    p["scheduling"] = {"scenarios": "set_order"}
    assert client.put("/api/admin/projects/HI", json={"data": p}).json()["ok"]
    assert client.get("/api/admin/projects/HI").json()["scheduling"] == {"scenarios": "set_order"}
    assert client.get(url).json()["scheduling_effective"]["scenarios"] == "set_order"
    assert client.put("/api/admin/projects/HI", json={"data": {"scheduling": {"scenarios": "x"}}}).status_code == 400


# --------------------------------------------------------------------------- #
# Confusing combinations                                                       #
# --------------------------------------------------------------------------- #
@pytest.fixture
def run(monkeypatch):
    from hani2 import cli

    monkeypatch.setattr(cli, "_serve", lambda *a, **k: None)
    saved = dict(os.environ)

    def _run(*args):
        r = CliRunner().invoke(cli.app, ["--no-browser", *args])
        for k in set(os.environ) - set(saved):
            os.environ.pop(k)
        return r

    yield _run
    os.environ.clear()
    os.environ.update(saved)


@pytest.mark.parametrize("args, says", [
    (["--assistant", HELLO, "--assistants", RULES], "--assistants alone"),
    (["--assistant", "off", "--assistants", RULES], "switched off"),
    (["--no-assistant", "--assistants", RULES], "switched off"),
    (["--no-assistant", "--assistant", "on"], "--no-assistant"),
    (["--support-agent", "on", "--assistant", "on"], "old name of --assistant"),
    (["--study", "P/s", "--experiment", "e"], "old name of --study"),
    (["--opponents", "BoulwareTBNegotiator", "--agents", "ConcederTBNegotiator"], "old name of --opponents"),
    (["--scenario-set", "HAN2026", "--set", "HAN2026"], "old name of --scenario-set"),
])
def test_cli_refuses_confusing_options(run, args, says):
    r = run(*args)
    assert r.exit_code != 0 and says in _flat(r.output), r.output
    assert "HANI2_ASSISTANTS" not in os.environ and "HANI2_STUDY" not in os.environ  # nothing was set


@pytest.mark.parametrize("args", [
    ["--assistant", "on", "--assistants", RULES],
    ["--assistant", "auto", "--assistants", RULES],
    ["--agents", "BoulwareTBNegotiator"],
    ["--experiment", "e1"],
    ["--support-agent", "off"],
    ["--no-support-agent"],
    ["--set", "HAN2026"],
    ["--scenario-set", "HAN2026"],
])
def test_cli_old_names_alone_still_work(run, args):
    r = run(*args)
    assert r.exit_code == 0, r.output


def test_cli_refuses_option_against_environment(run, monkeypatch):
    monkeypatch.setenv("HANI2_ASSISTANTS", RULES)
    r = run("--assistant", HELLO)
    assert r.exit_code != 0 and "HANI2_ASSISTANTS" in _flat(r.output)
    monkeypatch.setenv("HANI2_ASSISTANT_CLASS", HELLO)
    assert run("info").exit_code == 0  # subcommands still work; the server refuses to start


def test_experiment_create_refuses_confusing_options(run, hani2_home):
    r = run("experiment", "create", "e1", "--assistant", HELLO, "--assistants", RULES)
    assert r.exit_code != 0 and "--assistants alone" in _flat(r.output)
    from hani2.config import experiments_root

    assert not (experiments_root() / "e1").exists()
    r = run("experiment", "create", "e2", "--assistants", f"{HELLO},{RULES}")
    assert r.exit_code == 0, r.output
    assert projects.load_study("default/e2").overrides["assistants"] == [HELLO, RULES]


@pytest.mark.parametrize("env, says", [
    ({"HANI2_ASSISTANT_CLASS": HELLO, "HANI2_ASSISTANTS": RULES}, "HANI2_ASSISTANTS alone"),
    ({"HANI2_SUPPORT_AGENT_CLASS": HELLO, "HANI2_ASSISTANTS": RULES}, "HANI2_ASSISTANTS alone"),
    ({"HANI2_ASSISTANT": "off", "HANI2_ASSISTANTS": RULES}, "switches the Assistant off"),
    ({"HANI2_ASSISTANT": "on", "HANI2_SUPPORT_AGENT": "off"}, "set only HANI2_ASSISTANT"),
    ({"HANI2_ASSISTANT_CLASS": HELLO, "HANI2_SUPPORT_AGENT_CLASS": RULES}, "set only HANI2_ASSISTANT_CLASS"),
    ({"HANI2_STUDY": "P/s", "HANI2_EXPERIMENT": "e"}, "set only HANI2_STUDY"),
    ({"HANI2_OPPONENTS": "A", "HANI2_AGENTS": "B"}, "set only HANI2_OPPONENTS"),
    ({"PROLIFIC_PRACTICE_OPPONENTS": "A", "PROLIFIC_PRACTICE_AGENTS": "B"}, "PROLIFIC_PRACTICE_OPPONENTS"),
    ({"HANI2_PER_NEG_YAML": "a.yaml", "PROLIFIC_PER_NEG_YAML": "b.yaml"}, "HANI2_PER_NEG_YAML"),
])
def test_environment_conflicts_stop_the_server(hani2_home, monkeypatch, env, says):
    assert any(says in p for p in conflicts.env_problems(env)), conflicts.env_problems(env)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from hani2.server import app

    with pytest.raises(conflicts.ConflictError, match="confusing settings"):
        with TestClient(app):
            pass


def test_env_json_opponents_and_agents(hani2_home, run):
    from conftest import write_settings

    write_settings(hani2_home, "env.json", {"opponents": ["BoulwareTBNegotiator"], "agents": ["ConcederTBNegotiator"]})
    assert "keep only 'opponents'" in conflicts.settings_problems()[0]
    r = run()
    assert r.exit_code != 0 and "keep only 'opponents'" in _flat(r.output)


def test_environment_without_conflicts():
    ok = [{"HANI2_ASSISTANT": "on", "HANI2_SUPPORT_AGENT": "on", "HANI2_ASSISTANTS": RULES},
          {"HANI2_STUDY": "default/e", "HANI2_EXPERIMENT": "e"},
          {"HANI2_EXPERIMENT": "e", "HANI2_SUPPORT_AGENT": "on"},
          {"HANI2_ASSISTANT_CLASS": HELLO, "HANI2_SUPPORT_AGENT_CLASS": HELLO}]
    for env in ok:
        assert conflicts.env_problems(env) == []


def test_files_with_conflicting_keys(study):
    with pytest.raises(ValueError, match="'assistant'.*'support_agent'"):
        groups.validate_data(groups.OPPONENT, {"agents": ["A"], "assistant": HELLO, "support_agent": RULES})
    with pytest.raises(ValueError, match="keep only 'assistants'"):
        groups.validate_data(groups.ASSISTANT, {"assistants": [HELLO], "agents": [RULES]})
    groups.validate_data(groups.OPPONENT, {"agents": ["A"], "assistant": HELLO, "support_agent": HELLO})  # same: fine
    f = projects.study_dir(study) / "results" / "groups" / "both.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"agents": ["ConcederTBNegotiator"], "assistant": HELLO, "support_agent": RULES}))
    s = make_session(user="guest_c", mode="guest", partner=None, study=study, query={"group": "both"})
    assert s.support_agent is None and "support_agent" in s.assistant_error
    a = projects.project_dir("HI") / "assistant_groups" / "mixed.json"
    a.parent.mkdir(parents=True)
    a.write_text(json.dumps({"assistants": [HELLO], "agents": [RULES]}))
    _set_study(study, assistants=":mixed")
    s = prolific("C", study)
    assert s.support_agent is None and "keep only 'assistants'" in s.assistant_error
    # study.yaml: the same setting at the top level and under overrides
    _set_study(study, assistants=None, n_required=3, overrides={"n_required": 5})
    st = projects.load_study(study)
    assert any("n_required" in e for e in st.errors)
    with pytest.raises(ValueError, match="n_required"):
        projects.check_file_data({"n_required": 3, "overrides": {"n_required": 5}}, "overrides")


def test_cli_study_create_and_scheduling_list(run, hani2_home):
    r = run("study", "create", "P/s1", "--opponent-scheduling", "random", "--scenario-scheduling", "set_order")
    assert r.exit_code == 0, r.output
    r = run("study", "create", "P/s1", "--assistant-scheduling", "round_robin")
    assert r.exit_code == 0, r.output
    assert projects.load_study("P/s1").overrides["scheduling"] == {
        "opponents": "random", "scenarios": "set_order", "assistants": "round_robin"}
    r = run("study", "create", "P/s1", "--opponent-scheduling", "sideways")
    assert r.exit_code != 0 and "latin_square" in _flat(r.output)
    r = run("study", "show", "P/s1")
    assert "opponents: random" in r.output and "scenarios: set_order" in r.output
    r = run("scheduling", "list")
    assert r.exit_code == 0 and all(k in r.output for ks in REQUIRED.values() for k in ks)
    r = run("scheduling", "list", "--details", "--dimension", "assistants")
    assert "**Advantages**" in r.output and "latin_square" not in r.output
