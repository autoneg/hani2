"""Questionnaires about the Assistant or the opponent: the ``tags`` of the predefined sets,
``{{agent}}`` filled in with the party a study evaluates (``questionnaire_agent``, else the
project's ``kind``), ``requires: agent``, the set checks and the admin API."""

import re

import pytest
import yaml
from fastapi.testclient import TestClient

from hani2 import projects, questionnaire_library, questionnaires
from hani2.projects import StudyRef
from hani2.templates import render_data, study_variables

BOTH = ("trust_in_automation", "ueq_eval", "ueq_s")


@pytest.fixture
def layers(hani2_home):
    projects.create_project("HI", kind="assistant")
    projects.create_study("HI/s1", type="prolific")
    projects.create_project("HAN", kind="opponent")
    projects.create_study("HAN/s1", type="prolific")
    projects.create_project("R", kind="none")
    projects.create_study("R/s1", type="lab")
    return {"HI": StudyRef("HI", "s1"), "HAN": StudyRef("HAN", "s1"), "R": StudyRef("R", "s1")}


def _as(role, data):
    return questionnaires.for_role(render_data(data, {"agent": role, "Agent": role.capitalize()}), role)


# --------------------------------------------------------------------------- #
# The tags of the bundled sets                                                 #
# --------------------------------------------------------------------------- #
def test_every_bundled_set_is_tagged_and_valid():
    raw = {}
    for p in questionnaires.library_dirs()[0].glob("*.yaml"):
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        assert "tags" in d, f"{p.name} has no tags"
        raw[d["id"]] = p.read_text(encoding="utf-8")
    lib = questionnaires.library()
    assert {k for k, s in lib.items() if set(s["tags"]) == {"assistant", "opponent"}} == set(BOTH)
    for sid in raw:
        assert questionnaire_library.check(raw[sid], sid, in_app=False) == [], sid


@pytest.mark.parametrize("sid", sorted(BOTH))
def test_a_both_party_set_names_no_party(sid):
    for q in questionnaires.library()[sid]["questions"]:
        assert "{{agent}}" in q["text"] and q["requires"] == "agent", q["id"]
        assert not re.search(r"\b(assistant|opponent)\b", q["text"], re.IGNORECASE), q["id"]


def test_as_an_assistant_study_the_sets_read_as_before():
    """Rendered for an Assistant study, every set reads "the assistant" and asks only when an
    Assistant took part (the wording the validated marks were checked on)."""
    lib = questionnaires.library()
    for sid, s in lib.items():
        out = _as("assistant", {"questions": s["questions"]})["questions"]
        for q in out:
            assert "{{" not in q["text"] and q.get("requires") in (None, "support_agent"), (sid, q["id"])
    tia = {q["id"]: q for q in _as("assistant", {"questions": lib["trust_in_automation"]["questions"]})["questions"]}
    assert tia["tia_reliable"]["text"] == "The assistant is reliable."
    assert tia["tia_suspicious"]["text"] == "I am suspicious of the assistant's intent, action, or output."
    assert tia["tia_reliable"]["requires"] == "support_agent"
    ueq = _as("assistant", {"questions": lib["ueq_eval"]["questions"]})["questions"]
    assert ueq[0]["text"] == "The assistant was …  (1 = not understandable, 7 = understandable)"


def test_as_an_opponent_study_the_both_party_sets_ask_about_the_opponent():
    lib = questionnaires.library()
    for sid in BOTH:
        for q in _as("opponent", {"questions": lib[sid]["questions"]})["questions"]:
            assert "{{" not in q["text"] and "requires" not in q, (sid, q["id"])
            assert re.search(r"\bopponent\b", q["text"]) and "assistant" not in q["text"], (sid, q["id"])
    tia = {q["id"]: q for q in _as("opponent", {"questions": lib["trust_in_automation"]["questions"]})["questions"]}
    assert tia["tia_trust"]["text"] == "I can trust the opponent."
    assert tia["tia_harmful"]["text"] == "The opponent's action will have a harmful or injurious outcome."


def test_ids_and_scales_do_not_change_with_the_party():
    qs = questionnaires.library()["ueq_s"]["questions"]
    a, o = _as("assistant", {"questions": qs})["questions"], _as("opponent", {"questions": qs})["questions"]
    assert [(q["id"], q.get("scale"), q.get("reverse")) for q in a] == [(q["id"], q.get("scale"), q.get("reverse")) for q in o]


# --------------------------------------------------------------------------- #
# The party of a study                                                         #
# --------------------------------------------------------------------------- #
def test_the_party_follows_the_kind_and_the_setting(layers):
    assert questionnaires.agent_role(layers["HI"]) == "assistant"
    assert questionnaires.agent_role(layers["HAN"]) == "opponent"
    assert questionnaires.agent_role(layers["R"]) == "assistant"
    assert questionnaires.agent_role(StudyRef("HAN", "")) == "opponent"  # the project without a study
    projects.create_project("R", defaults={"questionnaire_agent": "opponent"})
    assert questionnaires.agent_role(layers["R"]) == "opponent"
    projects.create_study("R/s1", overrides={"questionnaire_agent": "assistant"})
    assert questionnaires.agent_role(layers["R"]) == "assistant"  # the study wins over its project
    with pytest.raises(ValueError, match="questionnaire_agent"):
        projects.create_study("R/s1", overrides={"questionnaire_agent": "nonsense"})
    assert study_variables(layers["HAN"])["agent"] == "opponent"
    assert study_variables(layers["HAN"])["Agent"] == "Opponent"
    with projects.use_study(layers["HAN"]):
        assert questionnaires.agent_role() == "opponent"


def _spec(form):
    out = questionnaires.spec(form)
    assert out is not None
    return out


def test_one_form_file_reads_per_study(layers):
    text, _, _ = questionnaires.compose("", ["trust_in_automation"], "per_negotiation")
    for ref in (layers["HI"], layers["HAN"]):
        p = projects.study_dir(ref) / "questionnaires" / "per_negotiation.yaml"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    with projects.use_study(layers["HI"]):
        hi = {q["id"]: q for q in _spec("per_negotiation")["questions"]}
    with projects.use_study(layers["HAN"]):
        han = {q["id"]: q for q in _spec("per_negotiation")["questions"]}
    assert hi["tia_trust"]["text"] == "I can trust the assistant." and hi["tia_trust"]["requires"] == "support_agent"
    assert han["tia_trust"]["text"] == "I can trust the opponent." and "requires" not in han["tia_trust"]


def test_criteria_titles_are_rendered(layers):
    from hani2.evaluation import criteria

    text, _, _ = questionnaires.compose("", ["trust_in_automation"], "per_negotiation")
    p = projects.study_dir(layers["HAN"]) / "questionnaires" / "per_negotiation.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    spec = criteria.study_forms("HAN", "s1")["per_negotiation"]
    assert spec is not None
    assert all("{{" not in q["text"] for q in spec["questions"])
    assert any(q["text"] == "I can trust the opponent." for q in spec["questions"])


# --------------------------------------------------------------------------- #
# The set checks                                                               #
# --------------------------------------------------------------------------- #
SET = """id: mine
title: Mine
forms: [per_negotiation]
tags: {tags}
questions:
  - {{id: m1, text: "{text}", type: likert7, requires: {requires}}}
"""


def test_set_checks_on_tags(hani2_home):
    ok = SET.format(tags="[assistant, opponent]", text="The {{agent}} helped.", requires="agent")
    assert questionnaire_library.check(ok) == []
    assert questionnaire_library.check(SET.format(tags="[assistant]", text="The assistant helped.", requires="support_agent")) == []
    bad = questionnaire_library.check(SET.format(tags="[partner]", text="x", requires="agent"))
    assert any("unknown tag" in e for e in bad)
    named = questionnaire_library.check(SET.format(tags="[assistant, opponent]", text="The assistant helped.", requires="agent"))
    assert any("{{agent}}" in e for e in named)
    req = questionnaire_library.check(SET.format(tags="[assistant, opponent]", text="The {{agent}} helped.", requires="support_agent"))
    assert any("requires: agent" in e for e in req)


# --------------------------------------------------------------------------- #
# Admin API                                                                    #
# --------------------------------------------------------------------------- #
@pytest.fixture
def admin(layers):
    from hani2.server import app, hub

    hub.sessions.clear()
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"username": "admin", "password": "adminpass"})
        assert r.status_code == 200, r.text
        yield c
    hub.sessions.clear()


def test_admin_library_and_preview_use_the_layer(admin):
    r = admin.get("/api/admin/questionnaires/library?layer=study:HAN/s1").json()
    assert r["agent"] == "opponent"
    assert {s["id"]: s["tags"] for s in r["sets"]}["ueq_s"] == ["assistant", "opponent"]
    assert admin.get("/api/admin/questionnaires/library?layer=project:HI").json()["agent"] == "assistant"
    text, _, _ = questionnaires.compose("", ["ueq_s"], "per_negotiation")
    han = admin.post("/api/admin/questionnaires/check?layer=project:HAN", json={"text": text}).json()
    hi = admin.post("/api/admin/questionnaires/check?layer=study:HI/s1", json={"text": text}).json()
    assert han["form"]["questions"][0]["text"] == "The opponent was …"
    assert hi["form"]["questions"][0]["text"] == "The assistant was …"
