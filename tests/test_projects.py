"""Projects and studies: model, per-session resolution, routing, stamping, study types,
templates, consent per study, admin API and CLI."""

import csv
import json
import sqlite3
import time

import pytest
from conftest import write_settings
from fastapi.testclient import TestClient

from hani2 import projects
from hani2.projects import StudyRef
from hani2.testing import make_session


@pytest.fixture
def two_studies(hani2_home):
    projects.create_project("HI2027", full_name="Human-AI Interaction 2027", kind="assistant", year=2027,
                            organizer="The Lab", contact="lab@example.org", sponsor="ACME",
                            defaults={"n_required": 2})
    projects.create_study("HI2027/hi-01", type="prolific", title="January run", completion_code="CODE1",
                          start="2027-01-05", wave_no=1)
    projects.create_study("HAN2027/han-01", type="online", title="Online run",
                          completion_url="https://example.org/thanks?who={pid}&code={{completion_code}}",
                          completion_code="ONL")
    return hani2_home


@pytest.fixture
def client(hani2_home, monkeypatch):
    monkeypatch.setenv("HANI2_OPPONENTS", "BoulwareTBNegotiator")
    from hani2.server import app, hub

    hub.sessions.clear()
    with TestClient(app) as c:
        yield c
    hub.sessions.clear()


def recv_until(ws, pred, n=600):
    for _ in range(n):
        m = json.loads(ws.receive_text())
        if pred(m):
            return m
    raise AssertionError("message never arrived")


def files_under(path):
    return [p for p in path.rglob("*") if p.is_file()] if path.exists() else []


# --------------------------------------------------------------------------- #
# Model                                                                        #
# --------------------------------------------------------------------------- #
def test_model_and_layout(two_studies):
    home = two_studies
    assert (home / "projects" / "HI2027" / "project.yaml").exists()
    assert (home / "projects" / "HI2027" / "studies" / "hi-01" / "results").is_dir()
    pr = projects.load_project("HI2027")
    assert pr.kind == "assistant" and pr.year == 2027 and pr.defaults == {"n_required": 2}
    assert pr.extra == {"sponsor": "ACME"}
    st = projects.load_study("HI2027/hi-01")
    assert st.type == "prolific" and st.completion_code == "CODE1" and st.extra == {"wave_no": 1} and not st.legacy
    assert projects.list_projects()[0] == "default" and {"HI2027", "HAN2027"} <= set(projects.list_projects())
    assert projects.list_studies("HI2027") == ["hi-01"]


def test_old_experiment_is_a_study_of_the_default_project(hani2_home, monkeypatch):
    exp = hani2_home / "experiments" / "wave1"
    (exp / "results").mkdir(parents=True)
    ref = projects.parse_ref("wave1")
    assert ref == StudyRef("default", "wave1") and projects.study_dir(ref) == exp
    st = projects.load_study(ref)
    assert st.legacy and st.type == "prolific"
    assert "wave1" in projects.list_studies("default")
    monkeypatch.setenv("HANI2_EXPERIMENT", "wave1")
    assert projects.default_study() == ref
    monkeypatch.setenv("HANI2_STUDY", "HI2027/hi-01")
    assert projects.default_study() == StudyRef("HI2027", "hi-01")  # the new name wins


@pytest.mark.parametrize("bad", ["../x", "a/b/c", "", ".hidden", "a b", "x..y"])
def test_names_are_validated(bad):
    with pytest.raises(ValueError):
        projects.parse_ref(bad) if bad else projects.check_name(bad)


# --------------------------------------------------------------------------- #
# Per-session resolution                                                       #
# --------------------------------------------------------------------------- #
def test_settings_layers_study_project_settings_bundled(two_studies):
    from hani2.config import get_settings_file, load_env, read_settings_text, results_root

    home = two_studies
    write_settings(home, "consent.md", "settings consent")
    (home / "projects" / "HI2027" / "consent.md").write_text("project consent")
    (home / "projects" / "HI2027" / "env.json").write_text(json.dumps({"title": "Project title"}))
    (home / "projects" / "HI2027" / "studies" / "hi-01" / "env.json").write_text(json.dumps({"subtitle": "Study sub"}))
    assert read_settings_text("consent.md") == "settings consent"
    with projects.use_study("HI2027/hi-01"):
        assert read_settings_text("consent.md") == "project consent"
        env = load_env()
        assert env["title"] == "Project title" and env["subtitle"] == "Study sub"
        assert results_root() == home / "projects" / "HI2027" / "studies" / "hi-01" / "results"
        (home / "projects" / "HI2027" / "studies" / "hi-01" / "consent.md").write_text("study consent")
        assert read_settings_text("consent.md") == "study consent"
    with projects.use_study("HAN2027/han-01"):
        assert read_settings_text("consent.md") == "settings consent"
        assert get_settings_file("scenario_sets.yaml").parent.name == "default_settings"
    assert results_root() == home / "db"


def test_headless_session_in_a_study_writes_there(two_studies, monkeypatch):
    monkeypatch.setenv("HANI2_EXPERIMENT", "decoy")
    s = make_session(study="HI2027/hi-01")
    assert s.study_ref == StudyRef("HI2027", "hi-01")
    s.start()
    s.wait_for_turn()
    s.send_counter()
    s.wait_for_turn()
    s.end()
    s.wait_until_done()
    res = two_studies / "projects" / "HI2027" / "studies" / "hi-01" / "results" / "tester" / "results.csv"
    row = list(csv.DictReader(open(res)))[0]
    assert row["project"] == "HI2027" and row["study"] == "hi-01"
    assert not (two_studies / "experiments" / "decoy" / "results" / "tester").exists()


def test_project_defaults_and_env_wins(two_studies, monkeypatch):
    s = make_session(user="prolific_D1", mode="guest", partner=None, query={"noautostart": "1"}, study="HI2027/hi-01",
                     load=False)
    assert s.study.n_required == 2  # project.yaml default
    projects.create_study("HI2027/hi-01", n_required=3)
    s2 = make_session(user="prolific_D2", mode="guest", partner=None, query={"noautostart": "1"}, study="HI2027/hi-01",
                      load=False)
    assert s2.study.n_required == 3  # the study's override
    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "7")
    s3 = make_session(user="prolific_D3", mode="guest", partner=None, query={"noautostart": "1"}, study="HI2027/hi-01",
                      load=False)
    assert s3.study.n_required == 7  # an outside system's explicit input wins


# --------------------------------------------------------------------------- #
# Two studies in one server                                                    #
# --------------------------------------------------------------------------- #
def _play_prolific_round(client, prefix, pid):
    r = client.post(f"{prefix}/api/session", json={"mode": "guest", "query": {"PROLIFIC_PID": pid}})
    assert r.status_code == 200, r.text
    sid = r.json()["sid"]
    with client.websocket_connect(f"{prefix}/api/ws/{sid}") as ws:
        st = recv_until(ws, lambda m: m["type"] == "state")["state"]
        assert st["phase"] == "ready"
        # the auto-start timer (a separate thread) starts the negotiation
        recv_until(ws, lambda m: m["type"] == "state" and m["state"]["negotiation"]["is_my_turn"]
                   and not m["state"]["negotiation"]["thinking"])
        issue = st["scenario"]["issues"][0]
        value = issue["values"][0] if issue.get("values") else issue["min"]
        ws.send_text(json.dumps({"type": "send", "values": {issue["name"]: value}}))
        recv_until(ws, lambda m: m["type"] == "state" and m["state"]["negotiation"]["is_my_turn"]
                   and not m["state"]["negotiation"]["thinking"] or m["type"] == "state" and m["state"]["phase"] == "ended")
        ws.send_text(json.dumps({"type": "end"}))
        recv_until(ws, lambda m: m["type"] == "state" and m["state"]["phase"] in ("ended", "questionnaire", "finished"))
    return sid


def test_two_studies_concurrently(two_studies, client, monkeypatch):
    home = two_studies
    monkeypatch.setenv("HANI2_EXPERIMENT", "decoy")
    monkeypatch.setenv("PROLIFIC_AUTO_START_SECONDS", "1")
    monkeypatch.setenv("PROLIFIC_PRACTICE_AGENTS", "BoulwareTBNegotiator")
    a = _play_prolific_round(client, "/s/HI2027/hi-01", "P1")
    b = _play_prolific_round(client, "/s/HAN2027/han-01", "P1")
    assert a != b and a.startswith("prolific:P1::") and b.startswith("prolific:P1::")
    for proj, study in (("HI2027", "hi-01"), ("HAN2027", "han-01")):
        root = home / "projects" / proj / "studies" / study / "results"
        rows = list(csv.DictReader(open(root / "prolific_P1" / "results.csv")))
        assert len(rows) == 1 and rows[0]["project"] == proj and rows[0]["study"] == study
        assert (root / "prolific_P1" / "prolific_session.json").exists()
        db = sqlite3.connect(root / "events.db")
        stamps = set(db.execute("SELECT DISTINCT project, study FROM events").fetchall())
        assert stamps == {(proj, study)}
        recs = list((root / "prolific_P1" / "recordings").glob("*"))
        assert recs
    hub_sessions = __import__("hani2.server", fromlist=["hub"]).hub.sessions
    for sid in list(hub_sessions):
        hub_sessions[sid].recorder and hub_sessions[sid].recorder.finalize()
    idx = next((home / "projects" / "HI2027" / "studies" / "hi-01" / "results" / "prolific_P1" / "recordings").glob("*.json"))
    info = json.loads(idx.read_text())
    assert info["project"] == "HI2027" and info["study"] == "hi-01"
    # nothing leaked into the process default study
    assert files_under(home / "experiments" / "decoy") == []


def test_default_urls_still_use_the_process_default(two_studies, client, monkeypatch):
    monkeypatch.setenv("HANI2_EXPERIMENT", "wave")
    r = client.post("/api/session", json={"mode": "guest", "query": {"PROLIFIC_PID": "Z", "noautostart": "1"}})
    assert r.json()["sid"] == "prolific:Z"
    assert (two_studies / "experiments" / "wave" / "results" / "prolific_Z").is_dir()
    # the same study named explicitly is the same session
    r = client.post("/s/default/wave/api/session", json={"mode": "guest", "query": {"PROLIFIC_PID": "Z"}})
    assert r.json()["sid"] == "prolific:Z"


def test_hani2_study_is_the_default_for_plain_urls(two_studies, client, monkeypatch):
    monkeypatch.setenv("HANI2_STUDY", "HI2027/hi-01")
    monkeypatch.setenv("HANI2_EXPERIMENT", "ignored")
    r = client.post("/api/session", json={"mode": "guest", "query": {"PROLIFIC_PID": "D", "noautostart": "1"}})
    assert r.json()["sid"] == "prolific:D"
    assert (two_studies / "projects" / "HI2027" / "studies" / "hi-01" / "results" / "prolific_D").is_dir()
    assert not (two_studies / "experiments" / "ignored" / "results" / "prolific_D").exists()


def test_routing_pages_redirects_and_unknown_studies(two_studies, client, monkeypatch):
    monkeypatch.setenv("HANI2_ROOT_PATH", "/root")
    html = client.get("/root/s/HI2027/hi-01/play?PROLIFIC_PID=x").text
    if "<head>" in html:
        assert 'name="hani2-base" content="/root/s/HI2027/hi-01"' in html
        assert '"/root/assets/' in html
    r = client.get("/root/play?study=HI2027/hi-01&PROLIFIC_PID=x", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/root/s/HI2027/hi-01/play?PROLIFIC_PID=x"
    assert client.get("/root/s/HI2027/nope/play").status_code == 404
    assert client.get("/s/..%2F..%2Fetc/x/play").status_code == 404
    assert client.get("/root/s/HI2027/hi-01/api/config").json()["study"]["name"] == "hi-01"
    assert client.get("/api/config?study=HI2027/hi-01").json()["study"]["project"] == "HI2027"
    assert client.get("/api/config?study=HI2027/missing").status_code == 404
    # the page's ?study= also reaches the session
    r = client.post("/api/session", json={"mode": "guest", "query": {"PROLIFIC_PID": "q", "study": "HI2027/hi-01",
                                                                      "noautostart": "1"}})
    assert r.json()["sid"] == "prolific:q::HI2027:hi-01"


# --------------------------------------------------------------------------- #
# Study types                                                                  #
# --------------------------------------------------------------------------- #
def test_online_participant_and_completion(two_studies, client, monkeypatch):
    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "1")
    r = client.post("/s/HAN2027/han-01/api/session", json={"mode": "guest", "query": {"pid": "u-7", "noautostart": "1"}})
    sid = r.json()["sid"]
    assert sid.startswith("participant:u-7::")
    from hani2.server import hub

    s = hub.get(sid)
    assert s.user == "participant_u-7" and s.study.KIND == "participant"
    assert s.ss["user_path"] == two_studies / "projects" / "HAN2027" / "studies" / "han-01" / "results" / "participant_u-7"
    assert s.study.completion_url() == "https://example.org/thanks?who=u-7&code=ONL"
    assert "ONL" in s.study.finish_text()
    # ?pid= means nothing in a Prolific study (the playground as before)
    r = client.post("/s/HI2027/hi-01/api/session", json={"mode": "guest", "query": {"pid": "u-7"}})
    assert r.json()["sid"].startswith("guest:")


def test_lab_session_code(two_studies, client):
    projects.create_study("HAN2027/lab-kyoto", type="lab", end_text="Thanks! Please tell {{organizer}}.")
    projects.create_project("HAN2027", organizer="Kyoto team")
    r = client.post("/s/HAN2027/lab-kyoto/api/session", json={"mode": "guest", "query": {"code": "A1", "noautostart": "1"}})
    from hani2.server import hub

    s = hub.get(r.json()["sid"])
    assert s.user == "participant_A1" and s.study.completion_url() is None
    assert s.study.finish_text() == "Thanks! Please tell Kyoto team."


def test_prolific_completion_order(two_studies, monkeypatch):
    s = make_session(user="prolific_C", mode="guest", partner=None, query={"noautostart": "1"}, study="HI2027/hi-01",
                     load=False)
    assert s.study.completion_url() == "https://app.prolific.com/submissions/complete?cc=CODE1"
    projects.create_study("HI2027/hi-01", completion_url="https://done.example/{pid}")
    assert s.study.completion_url() == "https://done.example/C"
    monkeypatch.setenv("SCMLWEB_PROLIFIC_PATH", "/prolific/hi")
    assert s.study.completion_url() == "https://anac.cs.brown.edu/prolific/hi/done?PROLIFIC_PID=C"
    monkeypatch.setenv("PROLIFIC_COMPLETION_URL", "https://env.example/{pid}")
    assert s.study.completion_url() == "https://env.example/C"


# --------------------------------------------------------------------------- #
# Templates                                                                    #
# --------------------------------------------------------------------------- #
def test_templates(two_studies, monkeypatch):
    from hani2.templates import render, render_report, study_variables

    v = study_variables(StudyRef("HI2027", "hi-01"))
    assert v["project_full_name"] == "Human-AI Interaction 2027" and v["study_title"] == "January run"
    assert v["study_year"] == "2027" and v["n_required"] == "2" and v["completion_code"] == "CODE1"
    assert v["organizer"] == "The Lab" and v["project_sponsor"] == "ACME" and v["study_wave_no"] == "1"
    text = "{{ project_full_name }} / {{study_type}} / {{nope}} / {{%PROLIFIC_PID%}}"
    out, unknown = render_report(text, v)
    assert out == "Human-AI Interaction 2027 / prolific / {{nope}} / {{%PROLIFIC_PID%}}" and unknown == ["nope"]
    with projects.use_study("HI2027/hi-01"):
        assert render("{{minutes}} min") == "45 min"
        monkeypatch.setenv("PROLIFIC_MAX_MINUTES", "60")
        assert render("{{minutes}} min") == "60 min"
    assert study_variables(None)["project_name"] == "default"


def test_texts_rendered_for_participants_raw_for_admins(two_studies, client):
    home = two_studies
    (home / "projects" / "HI2027" / "consent.md").write_text("# {{project_full_name}} ({{study_title}})")
    (home / "projects" / "HI2027" / "announcements.md").write_text("Run {{study_name}}")
    (home / "projects" / "HI2027" / "questionnaires").mkdir()
    (home / "projects" / "HI2027" / "questionnaires" / "per_negotiation.yaml").write_text(
        "questions:\n  - id: q\n    text: How was {{project_name}}?\n    type: text\n")
    assert client.get("/s/HI2027/hi-01/api/consent").json()["markdown"] == "# Human-AI Interaction 2027 (January run)"
    assert client.get("/s/HI2027/hi-01/api/announcements").json()["markdown"] == "Run hi-01"
    from hani2.study import questionnaire_spec

    with projects.use_study("HI2027/hi-01"):
        assert questionnaire_spec()["questions"][0]["text"] == "How was HI2027?"
    client.post("/api/auth/login", json={"username": "admin", "password": "adminpass"})
    raw = client.get("/api/admin/settings/consent?project=HI2027").json()
    assert raw["text"] == "# {{project_full_name}} ({{study_title}})" and raw["exists"]
    pv = client.post("/api/admin/templates/preview", json={"kind": "consent", "study": "HI2027/hi-01"}).json()
    assert pv["rendered"].startswith("# Human-AI") and pv["unknown"] == []
    pv = client.post("/api/admin/templates/preview", json={"text": "{{x}} {{contact}}", "study": "HI2027/hi-01"}).json()
    assert pv["rendered"] == "{{x}} lab@example.org" and pv["unknown"] == ["x"] and "minutes" in pv["descriptions"]


# --------------------------------------------------------------------------- #
# Consent per study                                                            #
# --------------------------------------------------------------------------- #
def test_consent_per_study_and_reask_on_change(two_studies, client):
    home = two_studies
    write_settings(home, "env.json", {"auth": {"enforce_consent": True}})
    write_settings(home, "consent.md", "Default consent")
    assert client.post("/api/auth/register", json={"username": "eve", "password": "secret", "confirm": "secret",
                                                    "consent": True}).status_code == 200
    # the default study: consented at registration
    assert client.post("/api/session", json={"mode": "main"}).status_code == 200
    assert not client.get("/api/auth/me").json()["needs_consent"]
    # a new study asks again
    assert client.get("/s/HI2027/hi-01/api/auth/me").json()["needs_consent"]
    r = client.post("/s/HI2027/hi-01/api/session", json={"mode": "main"})
    assert r.status_code == 403 and r.json()["detail"] == "consent_required"
    c = client.get("/s/HI2027/hi-01/api/consent").json()
    assert client.post("/s/HI2027/hi-01/api/consent", json={"agree": True, "full_name": "Eve E", "hash": "stale"}).status_code == 409
    assert client.post("/s/HI2027/hi-01/api/consent", json={"agree": True, "full_name": "Eve E", "hash": c["hash"]}).status_code == 200
    r = client.post("/s/HI2027/hi-01/api/session", json={"mode": "main"})
    assert r.status_code == 200 and r.json()["sid"] == "main:eve::HI2027:hi-01"
    from hani2 import auth

    rec = auth.get_meta("eve")["consents"]["HI2027/hi-01"]
    assert rec["hash"] == c["hash"] and rec["study"] == "hi-01" and rec["date"]
    # a changed text asks again
    (home / "projects" / "HI2027" / "studies" / "hi-01" / "consent.md").write_text("New consent")
    assert client.get("/s/HI2027/hi-01/api/auth/me").json()["needs_consent"]
    assert client.post("/s/HI2027/hi-01/api/session", json={"mode": "main"}).status_code == 403


def test_old_consent_flag_still_counts_for_the_default_study(hani2_home, monkeypatch):
    from hani2 import auth

    auth.create_user("old", "pw12", consented=True, consent_date="2025-01-01")
    assert auth.has_study_consent("old", None, "any text")
    monkeypatch.setenv("HANI2_EXPERIMENT", "wave")
    assert auth.has_study_consent("old", StudyRef("default", "wave"), "any text")
    assert not auth.has_study_consent("old", StudyRef("HI2027", "hi-01"), "any text")


# --------------------------------------------------------------------------- #
# Stamping                                                                     #
# --------------------------------------------------------------------------- #
def test_old_events_database_gets_the_new_columns(hani2_home):
    from hani2 import events as ev

    db = hani2_home / "db"
    db.mkdir(parents=True)
    c = sqlite3.connect(db / "events.db")
    c.executescript("""CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, user TEXT,
        experiment TEXT, event_type TEXT NOT NULL, timestamp TEXT NOT NULL, component TEXT, action TEXT, value TEXT,
        scenario_id TEXT, round_number INTEGER, utility_value REAL, duration_ms REAL);
        CREATE TABLE sessions (id TEXT PRIMARY KEY, user TEXT, experiment TEXT, mode TEXT, start_time TEXT,
        end_time TEXT, ip TEXT, user_agent TEXT);""")
    c.execute("INSERT INTO events (session_id,user,event_type,timestamp) VALUES ('s','u','login','2020')")
    c.commit()
    c.close()
    ev._CONN.clear()
    ev.log_event(None, ev.EventType.LOGIN, user="u2")
    rows = ev.query_events()
    assert len(rows) == 2 and rows[0]["project"] == "default" and rows[0]["study"] == ""


# --------------------------------------------------------------------------- #
# Admin API                                                                    #
# --------------------------------------------------------------------------- #
def test_admin_projects_api(two_studies, client):
    assert client.get("/api/admin/projects").status_code == 401
    client.post("/api/auth/login", json={"username": "admin", "password": "adminpass"})
    ps = client.get("/api/admin/projects").json()["projects"]
    assert {"default", "HI2027", "HAN2027"} <= {p["name"] for p in ps}
    assert client.put("/api/admin/projects/NEW", json={"yaml": "full_name: New one\nkind: opponent\n"}).json()["ok"]
    assert client.get("/api/admin/projects/NEW").json()["full_name"] == "New one"
    r = client.put("/api/admin/projects/NEW/studies/s1", json={"data": {"type": "online", "title": "S1"}}).json()
    assert r["links"]["participant"].endswith("/s/NEW/s1/play?pid=<PARTICIPANT_ID>")
    st = client.get("/api/admin/projects/NEW/studies/s1").json()
    assert st["title"] == "S1" and "type: online" in st["yaml"]
    assert client.put("/api/admin/projects/NEW/studies/s2", json={"data": {"type": "bogus"}}).status_code == 400
    assert client.put("/api/admin/projects/..bad/studies/s2", json={"data": {}}).status_code in (400, 404)
    assert client.get("/api/admin/projects/NEW/studies/missing").status_code == 404
    # settings layers
    assert client.put("/api/admin/settings/consent?study=NEW/s1", json={"text": "study text"}).json()["ok"]
    assert (two_studies / "projects" / "NEW" / "studies" / "s1" / "consent.md").read_text() == "study text"
    assert client.put("/api/admin/settings/assistant?project=NEW", json={"mode": "off"}).json()["ok"]
    assert client.get("/api/admin/settings/assistant?project=NEW").json() == {"mode": "off"}
    assert client.get("/api/admin/settings/assistant?study=NEW/s1").json() == {}
    got = client.get("/api/admin/settings/consent?study=NEW/s1").json()
    assert got["text"] == "study text" and got["effective"] == "study text"
    assert client.get("/api/admin/settings/consent?study=../../x").status_code in (400, 404)
    assert client.get("/api/admin/settings/consent?project=../x").status_code == 400
    assert not (two_studies / "settings" / "consent.md").exists()


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def test_cli_projects_and_studies(hani2_home, monkeypatch):
    from typer.testing import CliRunner

    from hani2 import cli

    run = CliRunner()
    r = run.invoke(cli.app, ["project", "create", "HI2027", "--kind", "assistant", "--full-name", "HI 2027"])
    assert r.exit_code == 0, r.output
    r = run.invoke(cli.app, ["study", "create", "HI2027/hi-01", "--type", "prolific", "--title", "Jan",
                             "--completion-code", "XYZ", "--prolific-study-id", "abc123",
                             "--base-url", "https://hani.example/root"])
    assert r.exit_code == 0, r.output
    assert ("https://hani.example/root/s/HI2027/hi-01/play?PROLIFIC_PID={{%PROLIFIC_PID%}}"
            "&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}") in r.output
    st = projects.load_study("HI2027/hi-01")
    assert st.prolific_study_id == "abc123" and st.completion_code == "XYZ"
    assert run.invoke(cli.app, ["study", "create", "X/y", "--type", "nope"]).exit_code != 0
    # updating keeps what is not given
    assert run.invoke(cli.app, ["study", "create", "HI2027/on", "--type", "online"]).exit_code == 0
    assert run.invoke(cli.app, ["study", "create", "HI2027/on", "--title", "Later"]).exit_code == 0
    assert projects.load_study("HI2027/on").type == "online" and projects.load_study("HI2027/on").title == "Later"
    assert run.invoke(cli.app, ["project", "create", "HI2027", "--year", "2028"]).exit_code == 0
    assert projects.load_project("HI2027").kind == "assistant"
    assert run.invoke(cli.app, ["experiment", "create", "wave1"]).exit_code == 0
    out = run.invoke(cli.app, ["study", "list"]).output
    assert "HI2027/hi-01" in out and "default/wave1" in out
    assert "HI 2027" in run.invoke(cli.app, ["project", "list"]).output
    assert "XYZ" in run.invoke(cli.app, ["study", "show", "HI2027/hi-01"]).output
    monkeypatch.setattr(cli, "_serve", lambda *a, **k: None)
    r = run.invoke(cli.app, ["--study", "HI2027/hi-01", "--no-browser"])
    assert r.exit_code == 0, r.output
    import os

    assert os.environ.pop("HANI2_STUDY") == "HI2027/hi-01"
    assert run.invoke(cli.app, ["--study", "../x", "--no-browser"]).exit_code != 0
