"""Compatibility suite: how an outside system (a competition website) drives HANI2.

It runs one HANI2 process per league with ``HANI2_EXPERIMENT=<wave>``, ``--root-path``,
``--support-agent on|off`` and ``--page play``; sends participants to
``<root>/play?PROLIFIC_PID=<pid>&group=<key>``; reads the results under
``$HANI2_EXPERIMENTS/<wave>/results/prolific_<PID>/``; writes ``schedule.json`` and
``groups/<key>.json`` there; and sets ``PROLIFIC_*`` / ``SCMLWEB_*`` variables.
None of this may change. These tests pin it.
"""

import csv
import json

import pytest
from fastapi.testclient import TestClient

from hani2.testing import make_session

#: columns the outside system reads from results.csv (existing columns are only ever added to)
RESULT_COLS = [
    "scenario", "human_id", "user", "agreement", "human_utility", "agent_utility", "welfare", "ended_at",
    "status", "ended_by", "mechanism_name", "mechanism_id", "n_human_actions", "load_at", "start_at",
    "load_to_start_seconds", "duration_seconds", "per_round_times", "broken", "timedout", "n_outcomes",
    "shared_time_limit", "shared_n_steps", "practice", "agent_type",
]
QUESTIONNAIRE_COLS = ["mechanism_id", "scenario", "agent_type", "practice", "shown_at", "submitted_at",
                      "duration_seconds"]

PER_NEG = """title: After
questions:
  - id: satisfaction_with_outcome
    text: Happy?
    type: likert5
    required: true
"""


@pytest.fixture
def wave(hani2_home, tmp_path, monkeypatch):
    """A league process: HANI2_EXPERIMENT=<wave>, experiments in $HANI2_EXPERIMENTS."""
    exps = tmp_path / "experiments"
    monkeypatch.setenv("HANI2_EXPERIMENTS", str(exps))
    monkeypatch.setenv("HANI2_EXPERIMENT", "hi-2026-11")
    monkeypatch.delenv("HANI2_STUDY", raising=False)
    return exps / "hi-2026-11" / "results"


@pytest.fixture
def client(hani2_home, monkeypatch):
    monkeypatch.setenv("HANI2_ROOT_PATH", "/hiplay2")
    monkeypatch.setenv("HANI2_OPPONENTS", "BoulwareTBNegotiator")
    from hani2.server import app, hub

    hub.sessions.clear()
    with TestClient(app) as c:
        yield c
    hub.sessions.clear()


def _play_one(s, act=True):
    s.start()
    s.wait_for_turn()
    if act:
        s.send_counter()
        s.wait_for_turn()
    s.end()
    s.wait_until_done()


def test_results_paths_and_files(wave, monkeypatch):
    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "1")
    monkeypatch.setenv("PROLIFIC_MAX_MINUTES", "60")
    monkeypatch.setenv("PROLIFIC_PRACTICE_AGENTS", "LinearTBNegotiator")
    s = make_session(user="prolific_P1", mode="guest", partner=None, query={"noautostart": "1"})
    user_dir = wave / "prolific_P1"
    assert s.ss["user_path"] == user_dir
    meta = json.loads((user_dir / "prolific_session.json").read_text())
    assert {"started_at", "scenario_type", "max_minutes", "max_negs"} <= set(meta)
    assert meta["max_minutes"] == 60 and meta["max_negs"] == 2
    _play_one(s)
    rows = list(csv.DictReader(open(user_dir / "results.csv")))
    assert len(rows) == 1 and rows[0]["user"] == "prolific_P1"
    missing = [c for c in RESULT_COLS if c not in rows[0]]
    assert not missing, missing
    assert (wave / "events.db").exists()


def test_no_experiment_writes_to_home_db(hani2_home):
    s = make_session(user="prolific_H1", mode="guest", partner=None, query={"noautostart": "1"})
    assert s.ss["user_path"] == hani2_home / "db" / "prolific_H1"


def test_per_negotiation_questionnaire_from_env(wave, tmp_path, monkeypatch):
    q = tmp_path / "per_negotiation.yaml"
    q.write_text(PER_NEG)
    monkeypatch.setenv("PROLIFIC_PER_NEG_YAML", str(q))
    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "2")
    s = make_session(user="prolific_Q1", mode="guest", partner=None, query={"noautostart": "1"})
    _play_one(s)
    assert s.phase == "questionnaire"
    assert s.study.submit_questionnaire({"satisfaction_with_outcome": 5})["ok"]
    rows = list(csv.DictReader(open(wave / "prolific_Q1" / "negotiation_questionnaires.csv")))
    assert rows[0]["satisfaction_with_outcome"] == "5"
    assert all(c in rows[0] for c in QUESTIONNAIRE_COLS)
    assert rows[0]["project"] == "default" and rows[0]["study"] == "hi-2026-11"  # added columns


def test_schedule_json_version_2_is_honoured(wave, monkeypatch):
    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "2")
    d = wave / "prolific_S1"
    d.mkdir(parents=True)
    (d / "prolific_session.json").write_text(json.dumps({"started_at": "2000-01-01T00:00:00", "scenario_type": "Trade"}))
    (d / "results.csv").write_text("ended_at,practice,n_human_actions,status\n1999-01-01T00:00:00,False,3,success\n")
    (d / "schedule.json").write_text(json.dumps({"version": 2, "pid": "S1", "negotiations": [
        {"slot": 0, "agent_class_name": "ConcederTBNegotiator", "scenario_type": "Island", "scenario_index": 0,
         "time_limit": 77}]}))
    s = make_session(user="prolific_S1", mode="guest", partner=None, query={"noautostart": "1"})
    assert not s.ss["is_practice_round"]
    assert s._scenario_name().startswith("Island")
    assert s.round_plan["time_limit"] == 77
    s.start()
    s.wait_for_turn()
    assert s.ss["last_partner_type"] == "ConcederTBNegotiator"
    s.end()
    s.wait_until_done()
    # the file written before keeps its rows and columns; new columns are only added
    rows = list(csv.DictReader(open(d / "results.csv")))
    assert len(rows) == 2 and rows[0]["ended_at"] == "1999-01-01T00:00:00" and rows[0]["status"] == "success"
    assert {"ended_at", "practice", "n_human_actions", "status", "project", "study"} <= set(rows[0])
    assert rows[1]["study"] == "hi-2026-11"


def test_group_file_in_results(wave):
    g = wave / "groups"
    g.mkdir(parents=True)
    (g / "finalists.json").write_text(json.dumps({"syspath": [], "agents": ["ConcederTBNegotiator"]}))
    (g / "plain.json").write_text(json.dumps(["LinearTBNegotiator"]))
    s = make_session(user="tester", partner=None, query={"group": "finalists"})
    assert [str(x) for x in s.opponent_pool()] == ["ConcederTBNegotiator"]
    s2 = make_session(user="tester2", partner=None, query={"group": "plain"})
    assert [str(x) for x in s2.opponent_pool()] == ["LinearTBNegotiator"]


def test_completion_urls(wave, monkeypatch):
    monkeypatch.delenv("PROLIFIC_COMPLETION_URL", raising=False)
    monkeypatch.delenv("SCMLWEB_BASE_URL", raising=False)
    monkeypatch.delenv("SCMLWEB_PROLIFIC_PATH", raising=False)
    s = make_session(user="prolific_C1", mode="guest", partner=None, query={"noautostart": "1"}, load=False)
    assert s.study.completion_url() == "https://anac.cs.brown.edu/prolific/done?PROLIFIC_PID=C1"
    monkeypatch.setenv("SCMLWEB_PROLIFIC_PATH", "/prolific/hi")
    monkeypatch.setenv("SCMLWEB_BASE_URL", "https://example.org/")
    assert s.study.completion_url() == "https://example.org/prolific/hi/done?PROLIFIC_PID=C1"
    monkeypatch.setenv("PROLIFIC_COMPLETION_URL", "https://x.org/done?p={pid}")
    assert s.study.completion_url() == "https://x.org/done?p=C1"


def test_prolific_scenarios_base(wave, tmp_path, monkeypatch):
    from hani2 import scenario_store as store

    base = tmp_path / "han_prolific_scenarios"
    base.mkdir()
    monkeypatch.setenv("HANI_PROLIFIC_SCENARIOS_BASE", str(base))
    assert store.base_dir() == base
    (wave.parent / "scenarios").mkdir(parents=True)
    assert store.base_dir() == wave.parent / "scenarios"  # the experiment's own scenarios come first (as before)


def test_play_url_under_root_path(wave, client):
    html = client.get("/hiplay2/play?PROLIFIC_PID=abc&group=finalists").text
    if "hani2-base" in html:  # the web app is built
        assert 'name="hani2-base" content="/hiplay2"' in html
    r = client.post("/hiplay2/api/session",
                    json={"mode": "guest", "query": {"PROLIFIC_PID": "abc", "group": "finalists", "noautostart": "1"}})
    assert r.status_code == 200 and r.json()["sid"] == "prolific:abc"
    assert (wave / "prolific_abc" / "prolific_session.json").exists()
    with client.websocket_connect("/hiplay2/api/ws/prolific:abc") as ws:
        for _ in range(50):
            m = json.loads(ws.receive_text())
            if m["type"] == "state":
                assert m["state"]["study"]["kind"] == "prolific"
                break


def test_cli_options_used_by_the_outside_system(hani2_home, monkeypatch):
    from typer.testing import CliRunner

    from hani2 import cli

    seen = {}
    monkeypatch.setattr(cli, "_serve", lambda host, port, open_path, reload=False, log_level="info":
                        seen.update(host=host, port=port, open_path=open_path))
    for v in ("HANI2_ROOT_PATH", "HANI2_EXPERIMENT", "HANI2_ASSISTANT"):
        monkeypatch.delenv(v, raising=False)
    r = CliRunner().invoke(cli.app, ["--host", "127.0.0.1", "--port", "5019", "--root-path", "/hiplay2",
                                     "--support-agent", "on", "--no-browser", "--page", "play",
                                     "--experiment", "hi-2026-11"])
    assert r.exit_code == 0, r.output
    import os

    assert os.environ["HANI2_ROOT_PATH"] == "/hiplay2" and os.environ["HANI2_EXPERIMENT"] == "hi-2026-11"
    assert os.environ["HANI2_ASSISTANT"] == "on"
    assert seen["port"] == 5019 and seen["open_path"] is None
    for v in ("HANI2_ROOT_PATH", "HANI2_EXPERIMENT", "HANI2_ASSISTANT", "HANI2_SUPPORT_AGENT"):
        os.environ.pop(v, None)
