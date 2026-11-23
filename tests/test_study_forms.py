"""Study forms: the layered lookup of the pre / per-negotiation / post-session questionnaires
(switching a form off per study), consent for anonymous study participants, the post-session
questionnaire, the predefined question sets and the admin API."""

import json

import pytest
import yaml
from conftest import write_settings
from fastapi.testclient import TestClient

from hani2 import projects, questionnaires
from hani2.projects import StudyRef
from hani2.testing import make_session

FORM = {"title": "T", "questions": [{"id": "q1", "text": "Q?", "type": "likert5", "required": True}]}
POST = {"title": "Bye", "questions": [{"id": "overall", "text": "Overall?", "type": "likert7", "required": True}]}


@pytest.fixture
def study(hani2_home):
    projects.create_project("HI", kind="assistant")
    projects.create_study("HI/s1", type="prolific")
    return StudyRef("HI", "s1")


def _put(folder, form, data):
    p = folder / "questionnaires" / questionnaires.FORMS[form].file
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(data if isinstance(data, str) else yaml.safe_dump(data), encoding="utf-8")
    return p


def _set_study(ref, **data):
    f = projects.study_dir(ref) / projects.STUDY_FILE
    d = projects.read_yaml(f)
    d.update(data)
    projects.write_yaml(f, d)


def prolific(pid, ref=None, **kw):
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
# The lookup                                                                   #
# --------------------------------------------------------------------------- #
def test_study_switch_off_beats_the_project_form(study):
    _put(projects.project_dir("HI"), "post_session", POST)
    with projects.use_study(study):
        r = questionnaires.resolve("post_session")
        assert r.spec["title"] == "Bye" and r.source == "project:HI"
    _put(projects.study_dir(study), "post_session", "enabled: false\n")
    with projects.use_study(study):
        r = questionnaires.resolve("post_session")
        assert r.spec is None and r.disabled and r.source == "study:HI/s1"
    # another study of the project still gets the project's form
    projects.create_study("HI/s2", type="prolific")
    with projects.use_study(StudyRef("HI", "s2")):
        assert questionnaires.spec("post_session")["title"] == "Bye"


def test_environment_variables_win_and_are_named_as_the_source(study, hani2_home, monkeypatch, tmp_path):
    _put(projects.study_dir(study), "per_negotiation", FORM)
    f = tmp_path / "outside.yaml"
    f.write_text(yaml.safe_dump({"questions": [{"id": "x", "text": "X", "type": "text"}]}), encoding="utf-8")
    monkeypatch.setenv("PROLIFIC_PER_NEG_YAML", str(f))
    with projects.use_study(study):
        r = questionnaires.resolve("per_negotiation")
        assert r.source == "env:PROLIFIC_PER_NEG_YAML" and r.spec["questions"][0]["id"] == "x"


def test_validate_reports_problems():
    v = questionnaires.validate
    assert v("") == [] and v("enabled: false\n") == []
    assert v(yaml.safe_dump(FORM)) == []
    assert any("not valid YAML" in p for p in v("questions: [\n"))
    bad = {"questions": [{"id": "a", "text": "A", "type": "likert9"}, {"id": "a", "text": "B", "type": "select"}]}
    probs = v(yaml.safe_dump(bad))
    assert any("unknown type" in p for p in probs) and any("used twice" in p for p in probs)
    assert any("needs options" in p for p in probs)
    assert any("no questions" in p for p in v("title: x\n"))


# --------------------------------------------------------------------------- #
# The predefined question sets                                                 #
# --------------------------------------------------------------------------- #
def test_every_library_set_is_a_valid_form(hani2_home):
    lib = questionnaires.library()
    for key in ("ueq_eval", "ueq_s", "tam_usefulness_short", "tam_usefulness", "tam_ease", "subjective_value",
                "trust_in_automation", "nasa_tlx", "sus", "demographics", "negotiation_experience", "attention_check"):
        assert key in lib, key
    for sid, s in lib.items():
        assert s["title"] and s["description"] and s["forms"], sid
        assert set(s["forms"]) <= set(questionnaires.FORMS), sid
        assert questionnaires.validate(yaml.safe_dump({"questions": s["questions"]})) == [], sid
    assert len(lib["subjective_value"]["questions"]) == 16 and len(lib["sus"]["questions"]) == 10
    assert len(lib["ueq_eval"]["questions"]) == 8 and len(lib["trust_in_automation"]["questions"]) == 12


def test_compose_adds_sets_once_and_keeps_comments(hani2_home):
    text, added, skipped = questionnaires.compose("", ["ueq_eval", "tam_usefulness_short"], "per_negotiation")
    assert questionnaires.validate(text) == [] and len(added) == 10 and not skipped
    assert yaml.safe_load(text)["title"] == "After this negotiation"
    own = "# my form\ntitle: Mine\nquestions:\n  - {id: tam_useful, text: Mine, type: text}\n"
    text, added, skipped = questionnaires.compose(own, ["tam_usefulness_short"], "per_negotiation")
    assert text.startswith("# my form") and added == ["tam_effectiveness"] and skipped == ["tam_useful"]
    assert [q["id"] for q in yaml.safe_load(text)["questions"]] == ["tam_useful", "tam_effectiveness"]
    with pytest.raises(KeyError):
        questionnaires.compose("", ["nope"])
    # a switched-off form is switched back on by adding questions
    text, _, _ = questionnaires.compose("enabled: false\nquestions: []\n", ["sus"], "post_session")
    assert "enabled" not in yaml.safe_load(text)


def test_own_library_sets_replace_bundled_ones(hani2_home):
    d = hani2_home / "settings" / questionnaires.LIBRARY_DIR
    d.mkdir(parents=True)
    (d / "sus.yaml").write_text(yaml.safe_dump({"id": "sus", "title": "My SUS", "questions": FORM["questions"]}),
                                encoding="utf-8")
    lib = questionnaires.library()
    assert lib["sus"]["title"] == "My SUS" and lib["sus"]["source"] == "settings"


# --------------------------------------------------------------------------- #
# Consent for anonymous participants                                           #
# --------------------------------------------------------------------------- #
def test_consent_is_off_by_default(study):
    s = prolific("C0", study)
    try:
        assert s.phase == "ready"
    finally:
        s.close()


def test_consent_agree_then_pre_questionnaire_and_only_once(study, hani2_home):
    write_settings(hani2_home, "env.json", {"auth": {"participant_consent": True}})
    _put(projects.study_dir(study), "pre_questionnaire", FORM)
    s = prolific("C1", study)
    try:
        assert s.phase == "questionnaire" and s.questionnaire["stage"] == "consent"
        assert s.questionnaire["body"].strip()
        s.start()
        assert s.phase == "questionnaire"  # nothing starts before consent
        assert not s.study.submit_questionnaire({})["ok"]
        assert s.study.submit_questionnaire({"consent": "agree"})["ok"]
        assert s.phase == "questionnaire" and s.questionnaire["stage"] == "pre"
        assert s.study.submit_questionnaire({"q1": 3})["ok"]
        assert s.phase == "ready"
        rec = json.loads((s.ss["user_path"] / "consent.json").read_text())
        assert rec["agreed"] is True and rec["study"] == "s1" and rec["hash"]
    finally:
        s.close()
    s = prolific("C1", study)
    try:
        assert s.phase == "ready"  # asked once
    finally:
        s.close()
    # a changed consent text asks again
    (projects.study_dir(study) / "consent.md").write_text("# New consent\nPlease agree.", encoding="utf-8")
    s = prolific("C1", study)
    try:
        assert s.questionnaire and s.questionnaire["stage"] == "consent" and "New consent" in s.questionnaire["body"]
    finally:
        s.close()


def test_consent_declined_ends_without_a_completion_link(study, hani2_home):
    write_settings(hani2_home, "env.json", {"auth": {"participant_consent": True}})
    s = prolific("C2", study)
    try:
        assert s.study.submit_questionnaire({"consent": "decline"})["ok"]
        assert s.phase == "finished" and s.finish_url is None and "return this study" in s.finish_text
        assert json.loads((s.ss["user_path"] / "consent.json").read_text())["agreed"] is False
    finally:
        s.close()


def test_consent_per_study_layer(study, hani2_home):
    (projects.study_dir(study) / "env.json").write_text(json.dumps({"auth": {"participant_consent": True}}),
                                                        encoding="utf-8")
    s = prolific("C3", study)
    try:
        assert s.questionnaire and s.questionnaire["stage"] == "consent"
    finally:
        s.close()
    projects.create_study("HI/s2", type="prolific")
    s = prolific("C3", StudyRef("HI", "s2"))
    try:
        assert s.phase == "ready"
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# The post-session questionnaire                                               #
# --------------------------------------------------------------------------- #
def test_post_session_before_the_completion_link_and_after_a_reconnect(study, monkeypatch):
    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "1")
    monkeypatch.setenv("PROLIFIC_COMPLETION_URL", "https://example.org/done?pid={pid}")
    _set_study(study, practice=False)
    _put(projects.study_dir(study), "per_negotiation", FORM)
    _put(projects.project_dir("HI"), "post_session", POST)
    s = prolific("P1", study)
    try:
        _play(s)
        assert s.phase == "questionnaire" and s.questionnaire.get("stage") is None  # per negotiation first
        assert s.study.submit_questionnaire({"q1": 4})["ok"]
        assert s.phase == "questionnaire" and s.questionnaire["stage"] == "post"
        assert s.finish_url is None
    finally:
        s.close()
    s = prolific("P1", study)  # a reconnect / later visit before answering: the form again
    try:
        assert s.phase == "questionnaire" and s.questionnaire["stage"] == "post"
        assert not s.study.submit_questionnaire({})["ok"]
        assert s.study.submit_questionnaire({"overall": 6})["ok"]
        assert s.phase == "finished" and s.finish_url == "https://example.org/done?pid=P1"
        rec = json.loads((s.ss["user_path"] / "post_session.json").read_text())
        assert rec["answers"] == {"overall": 6} and rec["project"] == "HI"
    finally:
        s.close()
    s = prolific("P1", study)
    try:
        assert s.phase == "finished"  # answered once
    finally:
        s.close()


def test_post_session_switched_off_for_one_study(study, monkeypatch):
    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "1")
    _set_study(study, practice=False)
    _put(projects.project_dir("HI"), "post_session", POST)
    _put(projects.study_dir(study), "post_session", "enabled: false\n")
    s = prolific("P2", study)
    try:
        _play(s)
        assert s.phase == "finished"
    finally:
        s.close()


def test_outside_system_flow_shows_no_new_forms(hani2_home, monkeypatch, tmp_path):
    """An outside system (its own consent, pre and post pages) sends participants to /play
    with only PROLIFIC_PER_NEG_YAML set: HANI2 adds no consent and no post-session form."""
    f = tmp_path / "per_neg.yaml"
    f.write_text(yaml.safe_dump(FORM), encoding="utf-8")
    monkeypatch.setenv("PROLIFIC_PER_NEG_YAML", str(f))
    monkeypatch.setenv("PROLIFIC_N_REQUIRED", "1")
    s = prolific("O1")
    try:
        assert s.phase == "ready"
        practice = bool(s.ss.get("is_practice_round"))
        _play(s)
        assert s.questionnaire.get("stage") is None
        assert s.study.submit_questionnaire({"q1": 2})["ok"]
        if practice:
            s.load()
            _play(s)
            assert s.study.submit_questionnaire({"q1": 2})["ok"]
        assert s.phase == "finished"
    finally:
        s.study._cancel()
        s.close()


# --------------------------------------------------------------------------- #
# Admin API                                                                    #
# --------------------------------------------------------------------------- #
@pytest.fixture
def admin(study, monkeypatch):
    from hani2.server import app, hub

    hub.sessions.clear()
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"username": "admin", "password": "adminpass"})
        assert r.status_code == 200, r.text
        yield c
    hub.sessions.clear()


def test_admin_edits_forms_per_layer(admin, study):
    _put(projects.project_dir("HI"), "post_session", POST)
    r = admin.get("/api/admin/settings/post_session?layer=study:HI/s1").json()
    assert r["exists"] is False and r["source"] == "project:HI" and r["active"] and "Bye" in r["effective"]
    bad = admin.put("/api/admin/settings/post_session?layer=study:HI/s1", json={"text": "questions: [{id: a}]"})
    assert bad.status_code == 422
    ok = admin.put("/api/admin/settings/post_session?layer=study:HI/s1", json={"text": "enabled: false\n"})
    assert ok.status_code == 200
    r = admin.get("/api/admin/settings/post_session?layer=study:HI/s1").json()
    assert r["exists"] and r["disabled"] and not r["active"] and r["source"] == "study:HI/s1"
    assert admin.delete("/api/admin/settings/post_session?layer=study:HI/s1").status_code == 200
    assert admin.get("/api/admin/settings/post_session?layer=study:HI/s1").json()["active"]


def test_admin_library_compose_and_check(admin):
    lib = admin.get("/api/admin/questionnaires/library").json()
    assert {s["id"] for s in lib["sets"]} >= {"ueq_eval", "subjective_value"}
    assert [f["key"] for f in lib["forms"]] == ["pre_questionnaire", "per_negotiation", "post_session"]
    r = admin.post("/api/admin/questionnaires/compose", json={"text": "", "sets": ["sus"], "form": "post_session"}).json()
    assert r["problems"] == [] and len(r["added"]) == 10
    c = admin.post("/api/admin/questionnaires/check", json={"text": r["text"]}).json()
    assert c["problems"] == [] and len(c["form"]["questions"]) == 10
    assert admin.post("/api/admin/questionnaires/compose", json={"sets": ["nope"]}).status_code == 404


def test_cli_list_compose_and_check(hani2_home, tmp_path):
    from typer.testing import CliRunner

    from hani2.cli import app

    run = CliRunner()
    r = run.invoke(app, ["questionnaire", "list", "--form", "post_session"])
    assert r.exit_code == 0 and "sus" in r.output and "negotiation_experience" not in r.output
    out = tmp_path / "post_session.yaml"
    r = run.invoke(app, ["questionnaire", "compose", "sus", "session_feedback", "--form", "post_session", "-o", str(out)])
    assert r.exit_code == 0, r.output
    assert len(yaml.safe_load(out.read_text())["questions"]) == 15
    assert run.invoke(app, ["questionnaire", "check", str(out)]).exit_code == 0
    bad = tmp_path / "bad.yaml"
    bad.write_text("questions: [{id: a, text: A, type: nope}]\n")
    r = run.invoke(app, ["questionnaire", "check", str(bad)])
    assert r.exit_code == 1 and "unknown type" in r.output
    assert run.invoke(app, ["questionnaire", "compose", "nope"]).exit_code != 0


def test_docs_list_every_library_set(hani2_home):
    from pathlib import Path

    page = (Path(__file__).resolve().parents[1] / "docs" / "guide" / "study-forms.md").read_text(encoding="utf-8")
    for sid, s in questionnaires.library().items():
        assert f"| `{sid}` | {len(s['questions'])} |" in page, sid
