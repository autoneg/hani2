"""Everything an admin can set by editing a settings file has a control in the admin console, or is
listed in :data:`FILE_ONLY` with the reason it is edited only in the file (each settings page and the
project and study views also have an editor for the whole file).

The keys come from the code's own registries: the defaults of env.json, the Assistant, autopilot and
language-model settings, the project and study keys (:data:`hani2.projects.DEFAULT_KEYS` and the
fields), the ``information`` block, the ``pairing`` block, and the keys of questionnaire forms and
library sets. :data:`EXTRA_ENV` adds the env.json keys that are read without a default (and so are in
no registry). A new key fails here until it gets a control or a line in :data:`FILE_ONLY`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hani2 import config, information, projects, study_modes
from hani2.support_agent import autopilot
from hani2.support_agent import settings as assistant_settings

ROOT = Path(__file__).resolve().parents[1]
ADMIN = ROOT / "frontend" / "src" / "admin"

#: env.json keys read with ``get_env`` but without a default in :data:`hani2.config.DEFAULT_ENV`
EXTRA_ENV = [
    "auth.default_password_login", "auth.sso", "auth.participant_consent", "docs_url", "public_url", "recording.enabled",
    "playground.choices", "tools.show_opponent_utility",
    "names.apply", "names.self", "names.opponent",
    "webmcp.enabled", "webmcp.actions", "webmcp.studies",
    "han.current_year", "han.import_dir", "han.submissions",
    "questionnaires", "pre_questionnaire", "questionnaire", "post_questionnaire",
    "interface.prefs.font_scale", "interface.vary_appearance.assistant", "interface.vary_appearance.opponent",
    "tools.paths", "tools.extra", "tools.disabled",
    "negotiation.information",
    "evaluation.llm", "evaluation.criteria", "evaluation.scores", "evaluation.assertions",
    "evaluation.reliability.pairs", "evaluation.reliability.report", "evaluation.cache.live",
]

#: keys edited only in the file (the raw editor of the page), with the reason
FILE_ONLY: dict[str, str] = {
    "auth.cookie_secret": "generated once and kept in .cookie_secret; changing it signs everyone out",
    "admin.password": "the first password of the default admin account; the Users page sets passwords",
    "evaluation.llm": "old single-model judge settings; the Models page sets the judge chain",
    "evaluation.criteria": "server-wide criteria for power users; projects and studies have score builders",
    "evaluation.scores": "server-wide scores for power users; projects and studies have score builders",
    "evaluation.assertions": "LLM-judge assertions, a list of rules best written in the file",
    "evaluation.reliability.pairs": "judge reliability runs, set up from the command line",
    "evaluation.reliability.report": "judge reliability runs, set up from the command line",
    "evaluation.cache.live": "a cache switch for debugging the evaluation",
    "assistant.enabled": "the old on/off switch, replaced by mode (Who gets the Assistant)",
}

#: prefixes whose keys the console lists from the server's registries (``/api/admin/meta``)
GENERATED = ("capabilities.", "interface.participant_settings.", "tools.overrides.")

#: per-question keys of a form file, and set keys of the questionnaire library
QUESTION_KEYS = ["id", "text", "type", "required", "labels", "options", "scale", "reverse", "direction", "requires",
                 "min", "max"]
FORM_KEYS = ["title", "intro", "questions", "enabled", "participant_type"]
SET_KEYS = ["id", "title", "description", "reference", "forms", "tags", "based_on", "questions"]


def _src() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in ADMIN.rglob("*.ts*"))


SRC = _src()


def _leaves(d: dict, pre: str = "") -> list[str]:
    out = []
    for k, v in d.items():
        p = f"{pre}{k}"
        out += _leaves(v, p + ".") if isinstance(v, dict) and v else [p]
    return out


def _has(path: str) -> bool:
    """The key occurs as a quoted path, a template path (``.${…}.key``) or a bare quoted key."""
    q = re.escape(path)
    # "a.b" / `a.b` / .a.b" (a template's tail), `a.b.${…}` (a template prefix) and key=a.b (a reset URL)
    return bool(re.search(rf'["`]{q}["`]|["`.]{q}["`]|`{q}\.\$\{{|key={q}\b', SRC))


def _cases() -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []
    cases += [("env", p) for p in _leaves(config.DEFAULT_ENV) + EXTRA_ENV]
    cases += [("assistant", p) for p in _leaves(assistant_settings.DEFAULT_ASSISTANT_SETTINGS)]
    cases += [("autopilot", p) for p in _leaves(autopilot.DEFAULT_AUTOPILOT_SETTINGS)]
    cases += [("llm", p) for p in _leaves(config.DEFAULT_LLM_SETTINGS)]
    cases += [("project", k) for k in (*projects.DEFAULT_KEYS, *projects.PROJECT_FIELDS, *projects.STUDY_FIELDS)]
    cases += [("information", "information." + p) for p in _leaves(information.DEFAULTS)]
    cases += [("pairing", k) for k in study_modes.PAIRING_KEYS]
    cases += [("question", k) for k in QUESTION_KEYS + FORM_KEYS + SET_KEYS]
    return list(dict.fromkeys(cases))


@pytest.mark.parametrize("where,key", _cases(), ids=lambda x: str(x))
def test_every_setting_has_a_control(where, key):
    full = f"{where}.{key}" if where in ("assistant", "autopilot", "llm") else key
    if full in FILE_ONLY or key in FILE_ONLY or key.startswith(GENERATED):
        return
    if where == "pairing" and _has(f"pairing.{key}"):
        return
    if where == "question":  # keys of forms and sets: written by the item editor and the set editor
        assert re.search(rf'["\s.]{re.escape(key)}\b', (ADMIN / "pages" / "FormItemsEditor.tsx").read_text()
                         + (ADMIN / "pages" / "QuestionnaireLibrary.tsx").read_text()), key
        return
    leaf = key.split(".")[-1]
    assert _has(key) or (where == "information" and _has(leaf)), (
        f"{where}: {key} has no control in frontend/src/admin; add one, or list it in FILE_ONLY with the reason")


def test_file_only_reasons_are_given():
    assert all(FILE_ONLY.values())


def test_every_env_key_the_code_reads_is_registered():
    """A literal ``get_env("a.b")`` in the package is a default or in EXTRA_ENV (else this test could miss it)."""
    known = set(_leaves(config.DEFAULT_ENV)) | set(EXTRA_ENV)
    prefixes = {".".join(k.split(".")[:i]) for k in known for i in range(1, k.count(".") + 1)}
    read = set()
    for f in (ROOT / "src" / "hani2").rglob("*.py"):
        read |= set(re.findall(r'get_env\(\s*"([A-Za-z_.]+)"', f.read_text(encoding="utf-8")))
    missing = sorted(k for k in read if k not in known and k not in prefixes and k not in ("agents",))
    assert not missing, f"register these env.json keys in DEFAULT_ENV or EXTRA_ENV: {missing}"


def test_every_json_page_and_yaml_view_has_a_whole_file_editor():
    page = (ADMIN / "SettingsPage.tsx").read_text(encoding="utf-8")
    for f in ("env.json", "llm_settings.json", "assistant_settings.json", "autopilot_settings.json"):
        assert f in page, f
    views = (ADMIN / "pages" / "Projects.tsx").read_text(encoding="utf-8")
    assert 'file="project.yaml"' in views and 'file="study.yaml"' in views


# --------------------------------------------------------------------------- #
# The endpoints the new controls use                                           #
# --------------------------------------------------------------------------- #
@pytest.fixture
def admin(hani2_home):
    from fastapi.testclient import TestClient

    from hani2.server import app, hub

    projects.create_project("HI", kind="assistant")
    projects.create_study("HI/s1", type="prolific")
    hub.sessions.clear()
    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200
        yield c
    hub.sessions.clear()


def test_meta_lists_the_setting_names_and_tool_fronts(admin):
    m = admin.get("/api/admin/meta").json()
    keys = m["setting_keys"]
    assert {"assistant_starts_on", "questionnaires", "questionnaire_agent", "information", "kind"} <= set(keys["project"])
    assert "title" not in keys["project"] and "title" in keys["study"]  # a project may use {{project_title}}
    assert all("at_front" in t for t in m["tools"])


def test_library_lists_the_named_forms(admin):
    names = admin.get("/api/admin/questionnaires/library").json()["named_forms"]
    assert {"evaluation", "expertise"} <= set(names)


def test_study_yaml_saved_whole_and_refused_with_the_reason(admin):
    url = "/api/admin/projects/HI/studies/s1"
    text = "type: prolific\ntitle: Run 1\noverrides:\n  assistant_starts_on: true\n  questionnaires: false\n"
    assert admin.put(url, json={"yaml": text}).json()["ok"]
    assert "assistant_starts_on: true" in admin.get(url).json()["yaml"]
    st = projects.get_study(projects.StudyRef("HI", "s1"))
    assert st.overrides["assistant_starts_on"] is True and st.overrides["questionnaires"] is False
    bad = admin.put(url, json={"yaml": "overrides:\n  questionnaire_agent: partner\n"})
    assert bad.status_code == 400 and "questionnaire_agent" in bad.json()["detail"]


def test_a_settings_file_saved_whole_replaces_the_layer_file(admin):
    url = "/api/admin/settings/env?layer=project:HI"
    assert admin.put(url, json={"names": {"apply": "always"}, "webmcp": {"studies": True}}).json()["ok"]
    own = admin.get(url).json()["own"]
    assert own == {"names": {"apply": "always"}, "webmcp": {"studies": True}}
    assert admin.put(url, json={}).json()["ok"]
    assert admin.get(url).json()["own"] == {}
