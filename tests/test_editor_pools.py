"""The ``editor`` block of the project and study GET payloads names the pools in effect, where they come
from (including an env.json layer, which the editor's live mode check could not see from the files) and
the mode they imply."""

import json

from fastapi.testclient import TestClient

from hani2 import projects
from hani2.projects import StudyRef


def _client():
    from hani2.server import app

    return TestClient(app)


def _login(c):
    assert c.post("/api/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200


def test_an_env_json_pool_reaches_the_editor(hani2_home):
    projects.create_project("HI", kind="assistant", year=2027)
    projects.create_study("HI/play", type="online")
    ref = StudyRef("HI", "play")
    (projects.study_dir(ref) / "env.json").write_text(json.dumps({"opponents": ["human+assistant"]}), encoding="utf-8")
    with _client() as c:
        _login(c)
        ed = c.get("/api/admin/projects/HI/studies/play").json()["editor"]
        assert ed["pools"]["opponents"] == {"effective": ["human+assistant"], "source": "env",
                                            "env": ["human+assistant"]}
        assert ed["pools"]["derived_mode"] == "paired"
        # the project layer does not see the study's env.json
        ped = c.get("/api/admin/projects/HI").json()["editor"]
        assert ped["pools"]["opponents"]["env"] == [] and ped["pools"]["derived_mode"] == "solo"


def test_the_files_win_over_env_json_and_assistants_are_inherited(hani2_home):
    projects.create_project("HI", kind="assistant", year=2027)
    f = projects.project_dir("HI") / projects.PROJECT_FILE
    d = projects.read_yaml(f)
    d.setdefault("defaults", {}).update({"opponents": [":pan"], "assistants": ["x.A", "x.B"]})
    projects.write_yaml(f, d)
    projects.create_study("HI/play", type="online")
    (projects.project_dir("HI") / "env.json").write_text(json.dumps({"opponents": ["human"]}), encoding="utf-8")
    with _client() as c:
        _login(c)
        ed = c.get("/api/admin/projects/HI/studies/play").json()["editor"]
        assert ed["pools"]["opponents"]["effective"] == [":pan"] and ed["pools"]["opponents"]["source"] == "project"
        assert ed["pools"]["opponents"]["env"] == ["human"]
        assert ed["pools"]["assistants"] == {"effective": ["x.A", "x.B"], "source": "project"}
        assert ed["inherited"]["assistants"] == ["x.A", "x.B"]
        assert ed["pools"]["derived_mode"] == "solo"
