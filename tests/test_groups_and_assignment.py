"""Groups (opponent and Assistant pools), Assistant assignment, Latin squares,
failing loudly, attribution, CLI and admin API."""

import csv
import json
import sqlite3
import threading
from collections import Counter
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from hani2 import assignment, groups, projects
from hani2.projects import StudyRef
from hani2.testing import make_session

HELLO = "level1_hello:HelloAgent"
RULES = "level2_rules:RulesAgent"
COACH = "level5_deal_coach:DealCoach"


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


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


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


# --------------------------------------------------------------------------- #
# Group resolution                                                             #
# --------------------------------------------------------------------------- #
def test_group_resolution_order(study, hani2_home):
    sdir = projects.study_dir(study)
    layers = [
        (sdir / "results" / "groups", "LinearTBNegotiator", "results"),
        (sdir / "groups", "ConcederTBNegotiator", "study"),
        (projects.project_dir("HI") / "groups", "BoulwareTBNegotiator", "project"),
        (hani2_home / "settings" / "groups", "HybridNegotiator", "settings"),
    ]
    for d, member, _ in layers:
        _write(d / "pool.json", {"agents": [member]})
    _write(hani2_home / "settings" / "groups" / "llm.json", ["AspirationNegotiator"])  # shadows the built-in
    with projects.use_study(study):
        for d, member, source in layers:
            g = groups.resolve(groups.OPPONENT, ":pool")
            assert g.members == [member] and g.source == source
            (d / "pool.json").unlink()
        assert groups.resolve(groups.OPPONENT, "pool") is None
        assert groups.resolve(groups.OPPONENT, ":llm").members == ["AspirationNegotiator"]
        assert groups.resolve(groups.OPPONENT, ":notext").source == "builtin"
    # the same through ?group= and :token in a session
    _write(projects.project_dir("HI") / "groups" / "finalists.json", ["ConcederTBNegotiator"])
    s = make_session(user="t1", partner=None, study=study, query={"group": "finalists"}, load=False)
    assert [str(x) for x in s.opponent_pool()] == ["ConcederTBNegotiator"] and s.opponent_group == "finalists"
    s = make_session(user="t2", partner=None, study=study, query={"opponents": ":finalists"}, load=False)
    assert [str(x) for x in s.opponent_pool()] == ["ConcederTBNegotiator"] and s.opponent_group == "finalists"


def test_default_project_groups_live_in_the_settings_folder(hani2_home):
    assert groups.project_group_dir("default", "opponent") == hani2_home / "settings" / "groups"
    assert groups.project_group_dir("HI", "assistants") == hani2_home / "projects" / "HI" / "assistant_groups"


def test_relative_syspath_and_bad_keys(study, tmp_path):
    import sys

    pkg = projects.project_dir("HI") / "groups" / "code"
    pkg.mkdir(parents=True)
    _write(projects.project_dir("HI") / "groups" / "mine.json", {"syspath": ["code"], "agents": ["x.Y"]})
    with projects.use_study(study):
        g = groups.resolve(groups.OPPONENT, "mine")
    assert str(pkg.resolve()) in sys.path and g.syspath == [str(pkg.resolve())]
    for bad in ("../etc", "a/b", "a\\b", "..", ""):
        assert groups.find_file(groups.OPPONENT, bad) is None
    long_key = "test_hi_123_" + "a" * 60  # outside-system keys carry an hmac
    assert groups.valid_key(long_key)


def test_builtin_assistant_groups(hani2_home):
    assert groups.resolve(groups.ASSISTANT, ":default").members == [groups.DEFAULT_ASSISTANT_SPEC]
    tut = groups.resolve(groups.ASSISTANT, ":tutorial").members
    assert HELLO in tut and len(tut) == len(groups.TUTORIAL_ASSISTANTS)
    assert groups.expand_assistants(":tutorial,level1_hello:HelloAgent")[0] == HELLO
    _write(hani2_home / "settings" / "assistant_groups" / "duo.json", {"assistants": [HELLO, RULES]})
    _write(hani2_home / "settings" / "assistant_groups" / "old.json", {"agents": [COACH]})
    assert groups.expand_assistants([":duo", "old"]) == [HELLO, RULES, COACH]


# --------------------------------------------------------------------------- #
# The group file's Assistant (outside system: HI test-your-agent)             #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("key", ["support_agent", "assistant"])
def test_group_file_names_the_assistant(study, key):
    g = projects.study_dir(study) / "results" / "groups"
    _write(g / "test_hi_7_abc.json", {"syspath": [], "agents": ["ConcederTBNegotiator"], key: COACH})
    s = make_session(user="guest_1", mode="guest", partner=None, study=study, query={"group": "test_hi_7_abc"})
    assert type(s.support_agent).__name__ == "DealCoach"
    assert s.support_agent.user_enabled  # starts switched on
    assert s.assistant_attribution()["assistant_group"] == "test_hi_7_abc"
    assert s.assistant_attribution()["assistant_source"] == "group"
    assert [str(x) for x in s.opponent_pool()] == ["ConcederTBNegotiator"]


def test_url_assistant_is_for_admins_only(study):
    s = make_session(user="admin", is_admin=True, partner=None, study=study, query={"assistant": COACH})
    assert type(s.support_agent).__name__ == "DealCoach"
    s = make_session(user="prolific_U", mode="guest", partner=None, study=study,
                     query={"assistant": COACH, "noautostart": "1"})
    assert type(s.support_agent).__name__ != "DealCoach"


# --------------------------------------------------------------------------- #
# Pools and assignment                                                         #
# --------------------------------------------------------------------------- #
def test_pool_levels(study, monkeypatch):
    _set_study(study, assistants=[HELLO, RULES])
    s = prolific("A", study)
    assert s.assistant_choice.source == "study" and s.assistant_choice.pool == [HELLO, RULES]
    monkeypatch.setenv("HANI2_ASSISTANT_CLASS", COACH)
    assert prolific("B", study).assistant_choice.source == "env"
    monkeypatch.setenv("HANI2_ASSISTANTS", RULES)
    s = prolific("C", study)
    assert s.assistant_choice.pool == [RULES] and type(s.support_agent).__name__ == "RulesAgent"
    monkeypatch.delenv("HANI2_ASSISTANTS")
    monkeypatch.delenv("HANI2_ASSISTANT_CLASS")
    _set_study(study, assistants=None)
    s = make_session(user="prolific_D", mode="guest", partner=None, study=study, agent_class=HELLO,
                     query={"noautostart": "1"})
    assert s.assistant_choice.source == "settings" and type(s.support_agent).__name__ == "HelloAgent"


def test_fixed_per_human_and_balanced(study):
    _set_study(study, assistants=":trio")
    _write(projects.project_dir("HI") / "assistant_groups" / "trio.json", {"assistants": [HELLO, RULES, COACH]})
    got = {}
    for i in range(7):
        s = prolific(f"P{i}", study)
        got[s.user] = s.assistant_choice.spec
        assert s.assistant_choice.group == "trio"
    assert list(got.values()) == [HELLO, RULES, COACH, HELLO, RULES, COACH, HELLO]  # ties: pool order
    # the same human keeps their Assistant (new session, next negotiation)
    s = prolific("P1", study)
    assert s.assistant_choice.spec == RULES
    s.load()
    assert s.assistant_choice.spec == RULES
    data = assignment.read_assignments(study)
    assert [data["humans"][f"prolific_P{i}"]["index"] for i in range(7)] == list(range(7))
    assert assignment.store_path(study) == projects.study_dir(study) / "results" / "assignments.json"


def test_admins_and_guests_are_not_counted(study):
    _set_study(study, assistants=[HELLO, RULES])
    for user, kw in (("admin", dict(is_admin=True)), ("guest_abc", dict(mode="guest"))):
        s = make_session(user=user, partner=None, study=study, **kw)
        assert s.support_agent is not None and s.assistant_choice.spec == HELLO
    assert assignment.read_assignments(study)["humans"] == {}
    assert prolific("P0", study).assistant_choice.spec == HELLO  # the first counted human
    assert prolific("P1", study).assistant_choice.spec == RULES


def test_balanced_under_concurrency(study):
    pool = [HELLO, RULES, COACH]
    n = 30
    barrier = threading.Barrier(n)
    out = {}

    def run(i):
        sess = SimpleNamespace(user=f"prolific_T{i}", is_admin=False, study_ref=study)
        barrier.wait()
        out[i] = assignment.assign_assistant(sess, pool)
        out[i] = (out[i], assignment.participant_index(sess))

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    counts = Counter(a for a, _ in out.values())
    assert sum(counts.values()) == n and max(counts.values()) - min(counts.values()) <= 1
    assert sorted(i for _, i in out.values()) == list(range(n))  # unique indices
    data = assignment.read_assignments(study)
    assert len(data["humans"]) == n and data["next_index"] == n


def test_reassigned_when_the_assistant_leaves_the_pool(study):
    sess = SimpleNamespace(user="prolific_R", is_admin=False, study_ref=study)
    assert assignment.assign_assistant(sess, [HELLO, RULES]) == HELLO
    assert assignment.assign_assistant(sess, [RULES, COACH]) == RULES
    h = assignment.read_assignments(study)["humans"]["prolific_R"]
    assert h["assistant"] == RULES and h["previous_assistants"] == [HELLO]


def test_assistant_off_takes_no_slot(study, monkeypatch):
    _set_study(study, assistants=[HELLO, RULES])
    s = make_session(user="prolific_O", mode="guest", partner=None, study=study, query={"noautostart": "1"},
                     assistant_settings={"mode": "off"})
    assert s.support_agent is None and not s.assistant_error
    assert "assistant" not in assignment.read_assignments(study)["humans"].get("prolific_O", {})


def test_schedule_assistant_wins(study, monkeypatch):
    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "2")
    _set_study(study, assistants=[HELLO])
    d = projects.study_dir(study) / "results" / "prolific_S"
    d.mkdir(parents=True)
    (d / "prolific_session.json").write_text(json.dumps({"started_at": "2000-01-01T00:00:00", "scenario_type": "Trade"}))
    (d / "results.csv").write_text("ended_at,practice,n_human_actions,status\n1999-01-01T00:00:00,False,3,success\n")
    (d / "schedule.json").write_text(json.dumps({"version": 2, "assistant": RULES, "negotiations": [
        {"slot": 0, "agent_class_name": "ConcederTBNegotiator", "scenario_type": "Trade", "scenario_index": 0,
         "time_limit": 60, "assistant": COACH},
        {"slot": 1, "agent_class_name": "LinearTBNegotiator", "scenario_type": "Trade", "scenario_index": 1,
         "time_limit": 60}]}))
    s = prolific("S", study)
    assert s.round_plan["assistant"] == COACH and type(s.support_agent).__name__ == "DealCoach"
    assert s.assistant_choice.source == "schedule"
    _play(s)
    s.load()
    assert s.round_plan["assistant"] == RULES and type(s.support_agent).__name__ == "RulesAgent"


# --------------------------------------------------------------------------- #
# Latin squares and scenarios                                                  #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("n", [2, 3, 4, 5, 6])
def test_latin_square_is_balanced(n):
    rows = assignment.latin_square(n)
    assert len(rows) == (n if n % 2 == 0 else 2 * n)
    for row in rows:
        assert sorted(row) == list(range(n))
    for col in range(n):
        assert Counter(r[col] for r in rows) == Counter({i: len(rows) // n for i in range(n)})
    follows = Counter((r[i], r[i + 1]) for r in rows for i in range(n - 1))
    assert len(set(follows.values())) == 1 and len(follows) == n * (n - 1)  # every ordered pair equally often


def test_opponents_follow_the_latin_square_in_a_study(study, monkeypatch):
    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "4")
    pool = ["BoulwareTBNegotiator", "ConcederTBNegotiator", "LinearTBNegotiator", "HybridNegotiator"]
    _set_study(study, opponents=pool, practice=False)
    orders = []
    for i in range(4):
        s = prolific(f"L{i}", study)
        order = [s.study.plan_round(None, None)["partner"]]
        for slot in range(1, 4):
            order.append(s.study.latin_square_partner(slot))
        orders.append(order)
    expected = [[pool[j] for j in row] for row in assignment.latin_square(4)]
    assert orders == expected
    types = [prolific(f"L{i}", study).study.meta["scenario_type"] for i in range(4)]
    from hani2 import scenario_store as store

    order = store.scenario_order()
    assert types == [order[i % len(order)] for i in range(4)]


def test_no_study_keeps_the_old_rotation(hani2_home, monkeypatch):
    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "2")
    monkeypatch.setenv("PROLIFIC_FINALISTS", "BoulwareTBNegotiator,ConcederTBNegotiator,LinearTBNegotiator")
    s = make_session(user="prolific_N", mode="guest", partner=None, query={"noautostart": "1"}, load=False)
    s.study.has_practice = False
    assert s.study.latin_square_partner(0) is None
    assert s.study.plan_round(None, None)["partner"] == "BoulwareTBNegotiator"
    assert (hani2_home / "db" / "prolific_N" / "fallback_rotation.txt").exists()


def test_rotation_offsets_unique_under_concurrency(tmp_path):
    from hani2.study import ProlificStudy

    n = 40
    barrier = threading.Barrier(n)
    out: dict[int, int] = {}
    again: dict[int, int] = {}

    def run(i):
        st = SimpleNamespace(user_path=tmp_path / f"prolific_C{i}")
        st.user_path.mkdir()
        barrier.wait()
        out[i] = ProlificStudy._rotation_offset(st)
        again[i] = ProlificStudy._rotation_offset(st)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(out.values()) == list(range(n))  # unique and contiguous
    assert again == out  # kept per participant
    assert (tmp_path / "_prolific_fallback_counter.txt").read_text() == str(n)


# --------------------------------------------------------------------------- #
# Failing loudly                                                               #
# --------------------------------------------------------------------------- #
def _events(ref, action):
    db = sqlite3.connect(projects.study_dir(ref) / "results" / "events.db")
    return db.execute("SELECT value FROM events WHERE action=?", (action,)).fetchall()


def test_failing_group_assistant_is_visible(study):
    _write(projects.study_dir(study) / "results" / "groups" / "broken.json",
           {"agents": ["ConcederTBNegotiator"], "support_agent": "nope.module.Missing"})
    s = make_session(user="guest_b", mode="guest", partner=None, study=study, query={"group": "broken"})
    assert s.support_agent is None
    assert "nope.module.Missing" in s.assistant_error
    snap = s.snapshot()
    assert snap["assistant_error"] == s.assistant_error and snap["support"] is None
    assert any(m.get("type") == "toast" and m.get("level") == "error" for m in s.hub.messages)
    assert _events(study, "assistant_failed")
    _play(s)
    row = next(csv.DictReader(open(s.ss["user_path"] / "results.csv")))
    assert row["assistant"] == "nope.module.Missing" and "nope.module.Missing" in row["assistant_error"]


def test_failing_constructor_and_not_an_assistant(study):
    _set_study(study, assistants=["hani2.groups:Group"])
    s = prolific("F1", study)
    assert s.support_agent is None and "not an Assistant" in s.assistant_error
    _set_study(study, assistants=[HELLO])
    from hani2.support_agent import runtime

    class Boom(runtime.SupportAgent):
        def __init__(self, *a, **k):
            raise RuntimeError("kaputt")

    import sys

    sys.modules[__name__].Boom = Boom
    _set_study(study, assistants=[f"{__name__}:Boom"])
    s = prolific("F2", study)
    assert s.support_agent is None and "kaputt" in s.assistant_error


def test_unknown_assistant_group_fails(study):
    _set_study(study, assistants=":missing")
    s = prolific("F3", study)
    assert s.support_agent is None and "names no Assistant" in s.assistant_error


def test_configured_agent_class_fails_loudly(hani2_home):
    """agent_class in assistant_settings.json (also written by ``hani2 experiment create
    --assistant <class>``) fails like an assigned Assistant: no silent fallback."""
    s = make_session(agent_class="nope.nothing:Missing")
    assert s.support_agent is None
    assert "nope.nothing:Missing" in s.assistant_error and "assistant_settings.json" in s.assistant_error
    assert s.snapshot()["assistant_error"] == s.assistant_error
    assert any(m.get("type") == "toast" and m.get("level") == "error" for m in s.hub.messages)


# --------------------------------------------------------------------------- #
# Attribution                                                                  #
# --------------------------------------------------------------------------- #
def test_attribution_in_results_events_and_recordings(study):
    _write(projects.project_dir("HI") / "assistant_groups" / "duo.json", {"assistants": [HELLO, RULES]})
    _set_study(study, assistants=":duo", practice=False)
    _write(projects.project_dir("HI") / "groups" / "fin.json", ["ConcederTBNegotiator"])
    s = prolific("AT", study, query={"noautostart": "1", "group": "fin"})
    _play(s)
    row = next(csv.DictReader(open(s.ss["user_path"] / "results.csv")))
    assert row["assistant"] == HELLO and row["assistant_group"] == "duo"
    assert row["assistant_class"].endswith("HelloAgent") and row["assistant_error"] == ""
    assert row["opponent_group"] == "fin" and row["agent_type"] == "ConcederTBNegotiator"
    assert row["support_agent"] in ("True", "False")  # the old column stays
    vals = [json.loads(v) for (v,) in sqlite3.connect(projects.study_dir(study) / "results" / "events.db").execute(
        "SELECT value FROM events WHERE event_type='scenario_started'").fetchall()]
    assert vals and vals[-1]["assistant"] == HELLO and vals[-1]["opponent_group"] == "fin"
    if s.recorder is not None:
        s.recorder.finalize()
        info = json.loads(next((s.ss["user_path"] / "recordings").glob("*.json")).read_text())
        assert info["assistant"] == HELLO and info["assistant_group"] == "duo" and info["opponent_group"] == "fin"


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def test_cli_assistants_and_groups_list(hani2_home, monkeypatch):
    import os

    from typer.testing import CliRunner

    from hani2 import cli

    monkeypatch.setattr(cli, "_serve", lambda *a, **k: None)
    try:
        r = CliRunner().invoke(cli.app, ["--no-browser", "--assistants", f"{HELLO},:tutorial"])
        assert r.exit_code == 0, r.output
        assert os.environ["HANI2_ASSISTANTS"] == f"{HELLO},:tutorial"
        os.environ.pop("HANI2_ASSISTANTS")
        r = CliRunner().invoke(cli.app, ["--no-browser", "--assistants", "nope.mod:Missing"])
        assert r.exit_code != 0 and "cannot import" in r.output
        r = CliRunner().invoke(cli.app, ["--no-browser", "--assistants", ":missing"])
        assert r.exit_code != 0
    finally:
        os.environ.pop("HANI2_ASSISTANTS", None)
    projects.create_project("HAN")
    _write(projects.project_dir("HAN") / "groups" / "finalists.json",
           {"description": "The finalists", "agents": ["ConcederTBNegotiator"], "assistant": HELLO})
    _write(projects.project_dir("HAN") / "assistant_groups" / "pair.json", {"assistants": [HELLO, RULES]})
    r = CliRunner().invoke(cli.app, ["groups", "list", "--project", "HAN", "--no-builtin"])
    assert r.exit_code == 0, r.output
    assert ":finalists" in r.output and "The finalists" in r.output and "assistant: " + HELLO in r.output
    assert ":pair" in r.output and RULES in r.output
    r = CliRunner().invoke(cli.app, ["groups", "list", "--kind", "assistant"])
    assert ":default" in r.output and ":tutorial" in r.output


# --------------------------------------------------------------------------- #
# Admin API                                                                    #
# --------------------------------------------------------------------------- #
def test_admin_group_endpoints(study, client):
    assert client.get("/api/admin/groups").status_code == 401
    client.post("/api/auth/login", json={"username": "admin", "password": "adminpass"})
    base = "/api/admin/projects/HI/groups"
    assert client.put(f"{base}/opponents/finalists", json={"description": "F", "agents": ["ConcederTBNegotiator"],
                                                          "assistant": HELLO}).json()["ok"]
    assert client.put(f"{base}/assistant/pair", json=[HELLO, RULES]).json()["ok"]
    g = client.get(f"{base}/opponent/finalists").json()
    assert g["members"] == ["ConcederTBNegotiator"] and g["assistant"] == HELLO and g["description"] == "F"
    assert json.loads((projects.project_dir("HI") / "assistant_groups" / "pair.json").read_text()) == \
        {"assistants": [HELLO, RULES]}
    lst = client.get("/api/admin/groups?project=HI").json()
    keys = {(g["key"], g["source"]) for g in lst["opponent"]}
    assert ("finalists", "project") in keys and ("llm", "builtin") in keys
    assert {g["key"] for g in lst["assistant"]} >= {"pair", "default", "tutorial"}
    by_study = client.get("/api/admin/groups?study=HI/s1").json()
    assert any(g["key"] == "pair" and g["active"] for g in by_study["assistant"])
    assert client.put(f"{base}/opponent/..x", json=["A"]).status_code in (400, 404)
    assert client.put(f"{base}/opponent/ok", json={"agents": "notalist"}).status_code == 400
    assert client.put(f"{base}/bogus/ok", json=["A"]).status_code == 400
    assert client.put("/api/admin/projects/NOPE/groups/opponent/x", json=["A"]).status_code == 404
    assert client.delete(f"{base}/assistant/pair").json()["ok"]
    assert client.get(f"{base}/assistant/pair").status_code == 404
    a = client.get("/api/admin/projects/HI/studies/s1/assignments").json()
    assert a["humans"] == {}


def test_admin_sessions_show_the_assistant(study, client):
    _write(projects.study_dir(study) / "results" / "groups" / "broken.json",
           {"agents": ["BoulwareTBNegotiator"], "assistant": "nope.Missing"})
    r = client.post("/api/session", json={"mode": "guest", "query": {"study": "HI/s1", "group": "broken"}})
    assert r.status_code == 200, r.text
    client.post("/api/auth/login", json={"username": "admin", "password": "adminpass"})
    rows = client.get("/api/admin/sessions").json()
    row = next(x for x in rows if x["study"] == "HI/s1")
    assert row["assistant"] == "nope.Missing" and "nope.Missing" in row["assistant_error"]


def test_test_links_are_not_balanced_or_recorded(study):
    _set_study(study, opponents=["BoulwareTBNegotiator", "ConcederTBNegotiator"])
    _write(projects.project_dir("HI") / "groups" / "try.json",
           {"agents": ["BoulwareTBNegotiator", "ConcederTBNegotiator"], "assistant": COACH})
    s = make_session(user="user_abc", partner=None, study=study, query={"group": "try"})
    assert type(s.support_agent).__name__ == "DealCoach"
    assert "partner" not in s.round_plan  # random opponent from the group, as before
    assert assignment.read_assignments(study)["humans"] == {}
    # a logged-in user of the study without a URL pool follows the Latin square
    s = make_session(user="user_def", partner=None, study=study)
    assert s.round_plan["partner"] == "BoulwareTBNegotiator"
    assert assignment.read_assignments(study)["humans"]["user_def"]["index"] == 0


def test_admin_mode_keeps_the_random_choice(study):
    _set_study(study, opponents=["BoulwareTBNegotiator", "ConcederTBNegotiator"])
    s = make_session(user="user_x", partner=None, study=study, load=False)
    assert s.study.plan_round(None, None)["partner"] == "BoulwareTBNegotiator"
    s.admin_mode = True  # ?admin=1 (the opponent picker)
    assert "partner" not in s.study.plan_round(None, None)


def test_autopilot_survives_an_assistant_swap(study, monkeypatch):
    s = make_session(user="admin", is_admin=True, partner=None, study=study, query={"assistant": HELLO})
    s.autopilot_active = True
    s.support_agent.set_autopilot(True)
    s.query["assistant"] = RULES
    s.load()
    assert type(s.support_agent).__name__ == "RulesAgent" and s.support_agent.autopilot


def test_schedule_opponent_outside_the_pool_has_no_group(study, monkeypatch):
    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "1")
    _write(projects.project_dir("HI") / "groups" / "fin.json", ["ConcederTBNegotiator"])
    d = projects.study_dir(study) / "results" / "prolific_G"
    d.mkdir(parents=True)
    (d / "prolific_session.json").write_text(json.dumps({"started_at": "2000-01-01T00:00:00", "scenario_type": "Trade"}))
    (d / "results.csv").write_text("ended_at,practice,n_human_actions,status\n1999-01-01T00:00:00,False,3,success\n")
    (d / "schedule.json").write_text(json.dumps([{"agent_class_name": "LinearTBNegotiator"}]))
    s = prolific("G", study, query={"noautostart": "1", "group": "fin"})
    assert s.round_plan["partner"] == "LinearTBNegotiator" and s.round_plan["opponent_group"] == ""


def _participant_package(root: Path, pkg: str) -> None:
    """A submitted agent unpacked as scmlweb does: <root>/<pkg>/coach.py, imported as pkg.coach.Class."""
    (root / pkg).mkdir(parents=True)
    (root / pkg / "__init__.py").write_text("")
    (root / pkg / "coach.py").write_text(
        "from level5_deal_coach import DealCoach\n\n\nclass MyCoach(DealCoach):\n    pass\n")


def test_scmlweb_hi_test_group_for_a_signed_in_participant(study, tmp_path):
    """HI 'test my agent': the participant's own Assistant, a signed-in (not guest) user, dotted specs."""
    _participant_package(tmp_path / "agents", "a789")
    g = projects.study_dir(study) / "results" / "groups"
    _write(g / "test_hi_789_tok.json", {"syspath": [str(tmp_path / "agents")], "agents": ["ConcederTBNegotiator"],
                                        "support_agent": "a789.coach.MyCoach"})
    s = make_session(user="anac_789", mode="main", partner=None, study=study, query={"group": "test_hi_789_tok"})
    assert type(s.support_agent).__name__ == "MyCoach" and s.support_agent.user_enabled
    assert [str(x) for x in s.opponent_pool()] == ["ConcederTBNegotiator"]
    s.start()
    s.wait_for_turn()
    assert s.phase == "running"


def test_scmlweb_han_test_group_plays_the_participants_agent(study, tmp_path):
    root = tmp_path / "agents" / "a456"
    root.mkdir(parents=True)
    (root / "__init__.py").write_text("")
    (root / "neg.py").write_text("from negmas.sao import BoulwareTBNegotiator\n\n\nclass Mine(BoulwareTBNegotiator):\n    pass\n")
    g = projects.study_dir(study) / "results" / "groups"
    _write(g / "test_han_456_tok.json", {"syspath": [str(tmp_path / "agents")], "agents": ["a456.neg.Mine"]})
    s = make_session(user="anac_456", mode="main", partner=None, study=study, query={"group": "test_han_456_tok"})
    s.start()
    s.wait_for_turn()
    assert "Mine" in str(s.ss.get("last_partner_type"))


def test_a_broken_test_agent_falls_back_without_crashing(study):
    g = projects.study_dir(study) / "results" / "groups"
    _write(g / "test_hi_1_bad.json", {"syspath": [], "agents": ["ConcederTBNegotiator"], "support_agent": "nope.missing.Class"})
    s = make_session(user="anac_1", mode="main", partner=None, study=study, query={"group": "test_hi_1_bad"})
    assert s.assistant_error  # shown to the participant, not raised
    s.start()
    s.wait_for_turn()
    assert s.phase == "running"
