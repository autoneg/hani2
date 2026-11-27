"""The save checks see the pools a session would play (env.json, assistant_settings.json, the mode),
and a project save re-checks the project's studies."""

import json
import os

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from hani2 import assignment, projects, scheduling, study_modes
from hani2.projects import StudyRef

HELLO = "level1_hello:HelloAgent"
RULES = "level2_rules:RulesAgent"
COACH = "level5_deal_coach:DealCoach"


@pytest.fixture
def study(hani2_home):
    projects.create_project("HI", kind="assistant")
    projects.create_study("HI/s1", type="prolific")
    return StudyRef("HI", "s1")


@pytest.fixture
def client(hani2_home):
    from hani2.server import app, hub

    hub.sessions.clear()
    with TestClient(app) as c:
        c.post("/api/auth/login", json={"username": "admin", "password": "adminpass"})
        yield c
    hub.sessions.clear()


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
    return _run


def _write_json(folder, name, data):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(json.dumps(data), encoding="utf-8")


def _write_study_yaml(ref, data):
    projects.write_yaml(projects.study_dir(ref) / projects.STUDY_FILE, data)


def _flat(text):
    return " ".join(text.replace("│", " ").split())


# --------------------------------------------------------------------------- #
# K ≤ N with the Assistant pool that is not in a YAML file                      #
# --------------------------------------------------------------------------- #
def test_k_above_n_with_the_pool_of_the_study_folders_assistant_settings_is_refused(study):
    _write_json(projects.study_dir(study), "assistant_settings.json", {"agent_class": HELLO})
    with pytest.raises(ValueError, match=r"n_required = 3 negotiations but only 1 Assistant \(level1_hello"):
        projects.create_study(study, n_required=3, scheduling={"assistants": "latin_square"})
    projects.create_study(study, n_required=3, scheduling={"assistants": "latin_square", "assistant_repeats": True})
    pools = study_modes.study_pools(study)
    assert pools.assistants == [HELLO] and pools.assistants_source == "study assistant_settings.json"


def test_k_above_n_with_the_project_folders_assistant_settings_is_refused(study):
    _write_json(projects.project_dir("HI"), "assistant_settings.json", {"agent_class": RULES})
    with pytest.raises(ValueError, match="but only 1 Assistant"):
        projects.create_project("HI", kind="assistant", n_required=2, scheduling={"assistants": "cyclic"})
    pools = study_modes.project_pools("HI")
    assert pools.assistants == [RULES] and pools.assistants_source == "project assistant_settings.json"
    # the built-in Assistant (no agent_class anywhere) is a pool of one as well
    (projects.project_dir("HI") / "assistant_settings.json").unlink()
    with pytest.raises(ValueError, match="but only 1 Assistant"):
        projects.create_study(study, n_required=2, scheduling={"assistants": "balanced_subset"})


def test_a_paired_han_study_without_assistants_is_not_a_repeat(hani2_home):
    projects.create_project("HAN", kind="opponent")
    projects.create_study("HAN/p", study_mode="paired", n_required=4, scheduling={"assistants": "latin_square"})
    pools = study_modes.study_pools("HAN/p")
    assert pools.assistants == ["none"] and pools.assistants_source == "study_mode"


def test_the_process_assistants_warn_in_study_show_but_do_not_refuse(study, monkeypatch, run):
    projects.create_study(study, assistants=[HELLO, RULES, COACH], n_required=3,
                          scheduling={"assistants": "latin_square"})
    monkeypatch.setenv("HANI2_ASSISTANTS", f"{HELLO},{RULES}")
    projects.create_study(study, title="still saved")  # the files' pool (3) is what is checked
    r = run("study", "show", str(study))
    out = _flat(r.output)
    assert "WARNING: scheduling.assistants is 'latin_square' with n_required = 3 negotiations but only 2" in out
    assert "hani2 --assistants" in out
    assert "assistants: level1_hello:HelloAgent, level2_rules:RulesAgent, level5_deal_coach:DealCoach (study.yaml)" in out


# --------------------------------------------------------------------------- #
# study_mode against an opponent pool from env.json                             #
# --------------------------------------------------------------------------- #
def test_solo_against_a_human_pool_from_the_project_env_json_is_refused(study):
    _write_json(projects.project_dir("HI"), "env.json", {"opponents": ["human+assistant"]})
    with pytest.raises(ValueError, match=r"study_mode is 'solo' but opponents \[human\+assistant\]"):
        projects.create_study(study, study_mode="solo")
    with pytest.raises(ValueError, match="study_mode is 'solo'"):
        projects.create_project("HI", kind="assistant", study_mode="solo")
    pools = study_modes.study_pools(study)
    assert pools.opponents == ["human+assistant"] and pools.opponents_source == "project env.json"
    assert pools.mode.derived == "paired"


def test_solo_against_a_human_pool_from_the_study_env_json_is_refused(study):
    _write_json(projects.study_dir(study), "env.json", {"opponents": ["human", ":pan"]})
    with pytest.raises(ValueError, match="study_mode is 'solo'"):
        projects.create_study(study, study_mode="solo")
    assert study_modes.study_pools(study).opponents_source == "study env.json"


def test_mixed_with_a_mixed_env_json_pool_is_accepted(study):
    _write_json(projects.project_dir("HI"), "env.json", {"opponents": ["human+assistant", ":pan"]})
    st = projects.create_study(study, study_mode="mixed")
    assert st.overrides["study_mode"] == "mixed"
    assert study_modes.resolve(study).mode == "mixed"


def test_paired_fills_its_pool_over_an_ai_env_json_pool_as_a_session_does(study):
    _write_json(projects.project_dir("HI"), "env.json", {"opponents": [":pan"]})
    projects.create_study(study, study_mode="paired")
    pools = study_modes.study_pools(study)
    assert pools.opponents == ["human+assistant"] and pools.opponents_source == "study_mode"
    from hani2.testing import make_session

    s = make_session(user="prolific_P1", mode="guest", partner=None, study=study, query={"noautostart": "1"})
    assert s.admin_prefs["opponent_types"] == ["human+assistant"]


def test_the_resolver_matches_a_session(study):
    from hani2.agents import expand_agents
    from hani2.support_agent.settings import load_assistant_settings
    from hani2.testing import make_session

    _write_json(projects.project_dir("HI"), "env.json", {"opponents": ["BoulwareTBNegotiator"]})
    _write_json(projects.study_dir(study), "assistant_settings.json", {"agent_class": RULES})
    s = make_session(user="prolific_P2", mode="guest", partner=None, study=study, query={"noautostart": "1"})
    pools = study_modes.study_pools(study)
    with projects.use_study(study):
        settings = load_assistant_settings()
    assert assignment.assistant_pool(s, settings).pool == pools.assistants == [RULES]
    with projects.use_study(study):
        assert [str(x) for x in s._base_pool()] == [str(x) for x in expand_agents(pools.opponents)]
    projects.create_study(study, assistants=[HELLO, COACH], opponents=["ConcederTBNegotiator"])
    s = make_session(user="prolific_P3", mode="guest", partner=None, study=study, query={"noautostart": "1"})
    pools = study_modes.study_pools(study)
    assert assignment.assistant_pool(s, settings).pool == pools.assistants == [HELLO, COACH]
    with projects.use_study(study):
        assert [str(x) for x in s._base_pool()] == [str(x) for x in expand_agents(pools.opponents)]


# --------------------------------------------------------------------------- #
# A project save re-checks its studies                                          #
# --------------------------------------------------------------------------- #
def test_a_project_change_that_breaks_a_paired_study_is_refused(study, client):
    projects.create_study(study, study_mode="paired")
    with pytest.raises(ValueError, match=r"study HI/s1: study_mode is 'paired' but opponents is \[:pan\]"):
        projects.create_project("HI", opponents=[":pan"])
    r = client.put("/api/admin/projects/HI", json={"data": {"kind": "assistant", "opponents": [":pan"]}})
    assert r.status_code == 400
    assert "study HI/s1: study_mode is 'paired'" in r.json()["detail"]
    assert "opponents" not in projects.load_project("HI").defaults  # nothing written
    # a kind change counts too: a Paired HAN study plays without Assistants
    projects.create_study(study, assistants=[HELLO])
    r = client.put("/api/admin/projects/HI", json={"data": {"kind": "opponent"}})
    assert r.status_code == 400 and "study HI/s1" in r.json()["detail"]


def test_a_project_change_that_makes_k_above_n_in_a_study_is_refused(study, client):
    projects.create_project("HI", kind="assistant", assistants=[HELLO, RULES, COACH])
    projects.create_study(study, n_required=3, scheduling={"assistants": "latin_square"})
    with pytest.raises(ValueError, match="study HI/s1: scheduling.assistants is 'latin_square' with n_required = 3"):
        projects.create_project("HI", assistants=[HELLO, RULES])
    r = client.put("/api/admin/projects/HI", json={"data": {"kind": "assistant", "assistants": [HELLO]}})
    assert r.status_code == 400 and "study HI/s1: " in r.json()["detail"]
    # an env.json pool counts for the studies too: a Solo study that would inherit a human pool
    projects.create_study("HI/s2", study_mode="solo")
    r = client.put("/api/admin/projects/HI", json={"data": {"kind": "assistant", "assistants": [HELLO, RULES, COACH],
                                                             "opponents": ["human+assistant"]}})
    assert r.status_code == 400 and "study HI/s2: study_mode is 'solo'" in r.json()["detail"]


def test_a_study_already_broken_does_not_block_an_unrelated_project_edit(study, client):
    _write_study_yaml(study, {"type": "prolific", "study_mode": "solo", "opponents": ["human"]})  # hand-edited
    _write_study_yaml(StudyRef("HI", "s2"), {"type": "prolific", "assistants": [HELLO], "n_required": 4,
                                             "scheduling": {"assistants": "cyclic"}})
    assert study_modes.study_pools(study).mode.mode_error
    assert scheduling.study_repeat_problems("HI/s2")
    projects.create_project("HI", full_name="Human-Assistant study")
    r = client.put("/api/admin/projects/HI", json={"data": {"kind": "assistant", "full_name": "Renamed"}})
    assert r.status_code == 200, r.text


# --------------------------------------------------------------------------- #
# The editor block                                                              #
# --------------------------------------------------------------------------- #
def test_the_get_payloads_carry_the_effective_pools_and_the_mode(study, client):
    _write_json(projects.project_dir("HI"), "env.json", {"opponents": ["human+assistant", ":pan"]})
    _write_json(projects.project_dir("HI"), "assistant_settings.json", {"agent_class": HELLO})
    projects.create_study(study, n_required=2, scheduling={"assistants": "latin_square", "assistant_repeats": True})
    eff = client.get("/api/admin/projects/HI").json()["editor"]["effective"]
    assert eff["assistants"] == {"entries": [HELLO], "pool": [HELLO], "n": 1,
                                 "source": "project assistant_settings.json"}
    assert eff["opponents"] == {"entries": ["human+assistant", ":pan"], "source": "project env.json"}
    assert eff["mode"] == eff["derived"] == "mixed" and eff["declared"] is None and not eff["mode_error"]
    assert eff["n_required"] == {"value": 5, "source": "default"} and eff["assistant_method"] == "balanced"
    eff = client.get("/api/admin/projects/HI/studies/s1").json()["editor"]["effective"]
    assert eff["n_required"] == {"value": 2, "source": "study.yaml"}
    assert eff["assistant_method"] == "latin_square" and eff["assistant_repeats"] is True
    assert eff["repeat_problems"] == [] and eff["process_overrides"] == {}
