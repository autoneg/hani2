"""The questionnaire explorer of the admin console: every set with its origin and file, sourced sets
read-only (refused by the API too), editing a bundled set writes an override, editing your own
set rewrites its file, new sets and copies, the checks, path traversal, admin only; and the
parse / dump round trip of the Study forms item editor."""

import json

import pytest
import yaml
from fastapi.testclient import TestClient

from hani2 import questionnaire_library as ql
from hani2 import questionnaires

API = "/api/admin/questionnaire-library"
OWN = {"id": "my_set", "title": "Mine", "description": "D", "forms": ["post_session"],
       "questions": [{"id": "mine_1", "text": "Mine?", "type": "likert5", "required": True}]}


def _text(d):
    return yaml.safe_dump(d, sort_keys=False)


@pytest.fixture
def lib_dir(hani2_home):
    return hani2_home / "settings" / questionnaires.LIBRARY_DIR


@pytest.fixture
def admin(hani2_home):
    from hani2.server import app, hub

    hub.sessions.clear()
    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200
        yield c
    hub.sessions.clear()


def _set(admin, sid):
    return next(s for s in admin.get(API).json()["sets"] if s["id"] == sid)


def test_list_shows_origin_path_read_only_and_warnings(admin, lib_dir):
    lib_dir.mkdir(parents=True)
    (lib_dir / "my_set.yaml").write_text(_text(OWN), encoding="utf-8")
    (lib_dir / "demographics.yaml").write_text(_text({**OWN, "id": "demographics", "title": "My demographics"}),
                                               encoding="utf-8")
    (lib_dir / "broken.yaml").write_text("id: [", encoding="utf-8")
    r = admin.get(API).json()
    sets = {s["id"]: s for s in r["sets"]}
    assert r["own_dir"] == str(lib_dir) and r["broken"][0]["path"] == str(lib_dir / "broken.yaml")
    assert r["broken"][0]["command"].startswith("rm ")
    sus = sets["sus"]
    assert sus["origin"] == "bundled" and sus["read_only"] and sus["validated"] and "Brooke" in sus["source_citation"]
    assert sus["path"].endswith("default_settings/questionnaire_library/sus.yaml") and "delete" not in sus
    assert sus["scales"] == ["sus"] and sus["n_questions"] == 10
    assert sets["tam_ease"]["read_only"] and "Davis, 1989" in sets["tam_ease"]["warning"]
    assert sets["subjective_value"]["warning"] == ""
    mine = sets["my_set"]
    assert mine["origin"] == "own" and not mine["read_only"] and mine["path"] == str(lib_dir / "my_set.yaml")
    assert mine["delete"]["command"] == f"rm {lib_dir / 'my_set.yaml'}" and "disappears" in mine["delete"]["effect"]
    dem = sets["demographics"]
    assert dem["origin"] == "override" and not dem["read_only"] and dem["title"] == "My demographics"
    assert dem["bundled_path"].endswith("default_settings/questionnaire_library/demographics.yaml")
    assert "bundled version comes back" in dem["delete"]["effect"]
    # removing the files: the own set disappears, the override reverts to the bundled set
    (lib_dir / "my_set.yaml").unlink()
    (lib_dir / "demographics.yaml").unlink()
    sets = {s["id"]: s for s in admin.get(API).json()["sets"]}
    assert "my_set" not in sets and sets["demographics"]["origin"] == "bundled"


def test_get_returns_the_file_text(admin):
    r = admin.get(f"{API}/sus").json()
    assert r["id"] == "sus" and r["text"].startswith("id: sus")
    assert admin.get(f"{API}/nope").status_code == 404


def test_edit_a_bundled_set_writes_an_override(admin, lib_dir):
    before = (questionnaires.library_dirs()[0] / "demographics.yaml").read_text(encoding="utf-8")
    text = admin.get(f"{API}/demographics").json()["text"].replace("title:", "title: Edited\nold_title:", 1)
    r = admin.put(f"{API}/demographics", json={"text": text})
    assert r.status_code == 200, r.text
    assert r.json()["origin"] == "override" and r.json()["path"] == str(lib_dir / "demographics.yaml")
    assert (lib_dir / "demographics.yaml").read_text(encoding="utf-8") == text
    assert (questionnaires.library_dirs()[0] / "demographics.yaml").read_text(encoding="utf-8") == before
    s = _set(admin, "demographics")
    assert s["origin"] == "override" and s["title"] == "Edited"
    assert not list(lib_dir.glob(".*.tmp"))  # written atomically, nothing left behind


def test_edit_your_own_set_rewrites_its_file(admin, lib_dir):
    lib_dir.mkdir(parents=True)
    f = lib_dir / "differently_named.yaml"  # the file name need not be the id
    f.write_text(_text(OWN), encoding="utf-8")
    new = _text({**OWN, "title": "Renamed"})
    assert admin.put(f"{API}/my_set", json={"text": new}).status_code == 200
    assert f.read_text(encoding="utf-8") == new and not (lib_dir / "my_set.yaml").exists()
    # the id stays
    r = admin.put(f"{API}/my_set", json={"text": _text({**OWN, "id": "other"})})
    assert r.status_code == 422 and "Copy as new" in r.json()["detail"]


def test_sourced_sets_are_read_only_in_the_api(admin, lib_dir):
    text = admin.get(f"{API}/sus").json()["text"]
    r = admin.put(f"{API}/sus", json={"text": text})
    assert r.status_code == 403 and "read-only" in r.json()["detail"]
    assert not (lib_dir / "sus.yaml").exists()
    # an own override of a sourced set (written by hand) stays read-only, as does an own set with a url
    lib_dir.mkdir(parents=True)
    (lib_dir / "sus.yaml").write_text(_text({**OWN, "id": "sus"}), encoding="utf-8")
    (lib_dir / "linked.yaml").write_text(_text({**OWN, "id": "linked", "url": "https://example.org/x"}), encoding="utf-8")
    assert admin.put(f"{API}/sus", json={"text": _text({**OWN, "id": "sus"})}).status_code == 403
    assert admin.put(f"{API}/linked", json={"text": _text({**OWN, "id": "linked"})}).status_code == 403
    # creating never overrides a set
    r = admin.post(API, json={"text": _text({**OWN, "id": "tam_ease"})})
    assert r.status_code == 422 and "already used" in r.json()["detail"]
    # a set saved in the app cannot make itself read-only
    r = admin.post(API, json={"text": _text({**OWN, "url": "https://example.org"})})
    assert r.status_code == 422 and "based_on" in r.json()["detail"]


def test_add_a_new_set(admin, lib_dir):
    blank = admin.get(API).json()["blank"]
    assert admin.post(f"{API}/check", json={"text": blank}).json()["problems"] == []
    r = admin.post(API, json={"text": _text({**OWN, "id": "HAN2027-PreSession"})})
    assert r.status_code == 200, r.text
    assert (lib_dir / "HAN2027-PreSession.yaml").exists()
    s = _set(admin, "HAN2027-PreSession")
    assert s["origin"] == "own" and not s["read_only"]
    assert admin.post(API, json={"text": _text({**OWN, "id": "HAN2027-PreSession"})}).status_code == 422
    # it is offered by the Study forms picker
    assert "HAN2027-PreSession" in {x["id"] for x in admin.get("/api/admin/questionnaires/library").json()["sets"]}


def test_copy_as_new_from_a_sourced_set(admin, lib_dir):
    text = admin.get(f"{API}/tam_ease/copy").json()["text"]
    data = yaml.safe_load(text)
    assert data["id"] == "tam_ease_copy" and "reference" not in data and "Davis (1989)" in data["based_on"]
    assert data["copied_from"] == "tam_ease" and len(data["questions"]) == 6
    assert admin.post(API, json={"text": text}).status_code == 200
    s = _set(admin, "tam_ease_copy")
    assert not s["read_only"] and s["based_on"] == data["based_on"] and not s["validated"]
    assert "Davis, 1989" in s["warning"]  # the warning follows the copy
    # the copy can be edited; a copy of the copy keeps the original warning
    edited = text.replace("(copy)", "(mine)")
    assert admin.put(f"{API}/tam_ease_copy", json={"text": edited}).status_code == 200
    again = yaml.safe_load(admin.get(f"{API}/tam_ease_copy/copy?new_id=tam2").json()["text"])
    assert again["id"] == "tam2" and again["copied_from"] == "tam_ease"


@pytest.mark.parametrize("text,needle", [
    ("id: [", "not valid YAML"),
    ("- a\n- b\n", "must be a mapping"),
    (_text({**OWN, "forms": ["lunch"]}), "unknown form"),
    (_text({**OWN, "title": ""}), "no title"),
    (_text({**OWN, "id": "a b"}), "invalid id"),
    (_text({**OWN, "questions": []}), "no questions"),
    (_text({**OWN, "questions": OWN["questions"] * 2}), "used twice"),
    (_text({**OWN, "questions": [{"id": "q", "text": "Q", "type": "nope"}]}), "unknown type"),
    (_text({**OWN, "questions": [{"id": "q", "text": "Q", "type": "select"}]}), "needs options"),
])
def test_invalid_sets_are_refused(admin, lib_dir, text, needle):
    problems = admin.post(f"{API}/check", json={"text": text}).json()["problems"]
    assert any(needle in p for p in problems), problems
    r = admin.post(API, json={"text": text})
    assert r.status_code == 422 and needle in r.json()["detail"]
    assert not lib_dir.exists() or not list(lib_dir.iterdir())


@pytest.mark.parametrize("sid", ["..", "..%2F..%2Fetc", "a.b", "%2Fetc%2Fpasswd", "x" * 81])
def test_path_traversal_is_refused(admin, lib_dir, sid):
    for r in (admin.get(f"{API}/{sid}"), admin.put(f"{API}/{sid}", json={"text": _text(OWN)}),
              admin.get(f"{API}/{sid}/copy")):
        assert r.status_code in (400, 404, 405), (sid, r.status_code)
    assert admin.get(f"{API}/sus/copy?new_id=..%2Fx").status_code == 400
    # the id in the body is the one that names the file
    for bad in ("../evil", "/tmp/evil", "a/b", ".hidden"):
        r = admin.post(API, json={"text": _text({**OWN, "id": bad})})
        assert r.status_code == 422 and "invalid id" in r.json()["detail"], bad
    assert not (lib_dir.parent / "evil.yaml").exists() and not lib_dir.exists()
    with pytest.raises(ql.LibraryError):
        ql.check_id("../x")


def test_admin_only(hani2_home):
    from hani2.server import app

    with TestClient(app) as c:
        for r in (c.get(API), c.get(f"{API}/sus"), c.get(f"{API}/sus/copy"), c.post(API, json={"text": ""}),
                  c.put(f"{API}/demographics", json={"text": ""}), c.post(f"{API}/check", json={"text": ""}),
                  c.post("/api/admin/questionnaires/parse", json={"text": ""}),
                  c.post("/api/admin/questionnaires/dump", json={"data": {}})):
            assert r.status_code == 401
        c.post("/api/auth/register", json={"username": "bob", "password": "bobpass1"})
        c.post("/api/auth/login", json={"username": "bob", "password": "bobpass1"})
        assert c.get(API).status_code == 403
        assert c.post(API, json={"text": _text(OWN)}).status_code == 403


def test_form_parse_and_dump_round_trip_every_set(admin):
    for sid, s in questionnaires.library().items():
        data = {"version": "1", "title": "T", "intro": "I", "questions": s["questions"], "extra": {"keep": 1}}
        text = yaml.safe_dump(data, sort_keys=False)
        parsed = admin.post("/api/admin/questionnaires/parse", json={"text": text}).json()["data"]
        out = admin.post("/api/admin/questionnaires/dump", json={"data": json.loads(json.dumps(parsed))}).json()
        assert out["problems"] == [] and yaml.safe_load(out["text"]) == data, sid  # labels keep their int keys
    assert admin.post("/api/admin/questionnaires/parse", json={"text": "a: ["}).status_code == 422
    assert admin.post("/api/admin/questionnaires/parse", json={"text": ""}).json()["data"] == {}
    off = admin.post("/api/admin/questionnaires/dump", json={"data": {"enabled": False}}).json()
    assert yaml.safe_load(off["text"]) == {"enabled": False} and off["problems"] == []


def test_cli_check_set_uses_the_same_rules(hani2_home, tmp_path):
    from typer.testing import CliRunner

    from hani2.cli import app

    run = CliRunner()
    for f in questionnaires.library_dirs()[0].glob("*.yaml"):  # every bundled set passes, as a file in the library
        r = run.invoke(app, ["questionnaire", "check", str(f)])
        assert r.exit_code == 0, r.output
    bad = tmp_path / "bad.yaml"
    bad.write_text(_text({**OWN, "forms": ["lunch"]}))
    assert run.invoke(app, ["questionnaire", "check", str(bad)]).exit_code == 0  # as a form it is fine
    r = run.invoke(app, ["questionnaire", "check", "--set", str(bad)])
    assert r.exit_code == 1 and "unknown form" in r.output
