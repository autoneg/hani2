"""The predefined questionnaires of human-agent negotiation competitions (HAN 2026, HAN 2025).

They must repeat the competition's questions exactly as asked. The sources are kept in ``tests/data``:
the HAN 2026 form files (scmlweb ``resources/questionnaires/*.yaml`` at the commit used for the
competition) and the items of the HAN 2025 Google Forms (read from each form's page data).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from hani2 import questionnaires
from hani2.evaluation import catalog as C

DATA = Path(__file__).parent / "data"
SCMLWEB = Path.home() / "code" / "sites" / "scmlweb"
HAN2026_COMMIT = "571df34e010b65ff3779c68362f198e771a34d76"  #: the last change before HAN 2026 ran (2026-06-10)

HAN2026 = {"HAN2026-PreSession": ("pre_session", "pre_questionnaire"),
           "HAN2026-PostNegotiation": ("per_negotiation", "per_negotiation"),
           "HAN2026-PostSession": ("post_session", "post_session")}
HAN2025 = {"HAN2025-PreStudy": ("pre_study", "pre_questionnaire"),
           "HAN2025-PostSession": ("post_session", "post_session"),
           "HAN2025-PostStudy": ("post_study", "post_session")}
#: the likeability items as printed in the results papers (IVA 2018 for ANAC 2017, ACII 2019 for ANAC 2018)
HAL_ITEMS = ["How satisfied were you with the final agreement?", "How much do you like your opponent?",
             "Would you negotiate with this opponent again?"]
HAL = {"ANAC-HAL2017-PostNegotiation": (None, "per_negotiation"), "ANAC-HAL2018-PostNegotiation": (None, "per_negotiation")}
ALL = {**HAN2026, **HAN2025, **HAL}


@pytest.fixture
def lib(hani2_home):
    return questionnaires.library()


@pytest.fixture
def client(hani2_home):
    from fastapi.testclient import TestClient

    from hani2.server import app

    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200
        yield c


@pytest.mark.parametrize("sid", sorted(ALL))
def test_competition_set_loads_and_passes_the_form_checker(lib, sid):
    s = lib[sid]
    assert s["source"] == "bundled" and s["id"] == sid and s["title"] == sid
    assert s["forms"] == [ALL[sid][1]] and s["description"] and s["reference"]
    assert questionnaires.validate(yaml.safe_dump({"questions": s["questions"]})) == []
    text, added, skipped = questionnaires.compose("", [sid], ALL[sid][1])
    assert questionnaires.validate(text) == [] and len(added) == len(s["questions"]) and not skipped
    info = C.questionnaire_info(sid)
    assert info and info.competition and not info.validated_by, "competition sets are not validated instruments"
    # the organisers' own sets cite nothing (editable in the app); sets taken from a paper cite it (read-only)
    if sid in HAL:
        assert info.citation and info.url.startswith("https://doi.org/")
    else:
        assert not info.citation and not info.url and "url" not in yaml.safe_load(
            (questionnaires.library_dirs()[0] / f"{sid}.yaml").read_text(encoding="utf-8"))


def test_hyphenated_capitalised_ids_are_valid_set_ids(lib, client):
    """Set ids such as ``HAN2026-PreSession`` load, compose and reach the admin console unchanged."""
    assert set(ALL) <= set(lib)
    sets = {s["id"]: s for s in client.get("/api/admin/questionnaires/library").json()["sets"]}
    assert set(ALL) <= set(sets) and sets["HAN2026-PreSession"]["validated"] is False
    r = client.post("/api/admin/questionnaires/compose",
                    json={"text": "", "sets": ["HAN2026-PreSession"], "form": "pre_questionnaire"})
    assert r.status_code == 200 and r.json()["added"][0] == "experience_negotiation"


@pytest.mark.parametrize("sid", sorted(HAN2026))
def test_han2026_sets_match_the_competition_forms(lib, sid):
    src = yaml.safe_load((DATA / "han2026" / f"{HAN2026[sid][0]}.yaml").read_text(encoding="utf-8"))
    assert lib[sid]["questions"] == src["questions"]  # ids, texts, types, labels, options, required: verbatim


@pytest.mark.skipif(not (SCMLWEB / ".git").exists(), reason="the scmlweb repository is not here")
@pytest.mark.parametrize("name", ["pre_session", "per_negotiation", "post_session"])
def test_han2026_test_data_is_the_competition_version(name):
    r = subprocess.run(["git", "-C", str(SCMLWEB), "show", f"{HAN2026_COMMIT}:resources/questionnaires/{name}.yaml"],
                       capture_output=True, text=True)
    if r.returncode:
        pytest.skip(r.stderr.strip())
    assert (DATA / "han2026" / f"{name}.yaml").read_text(encoding="utf-8") == r.stdout


#: the HAN 2025 identification items HANI2 records itself
_ID_ITEMS = {"Registered user-name:", "Session-ID:", "Date and Time:", "Number of negotiations:"}


@pytest.mark.parametrize("sid", sorted(HAN2025))
def test_han2025_sets_match_the_google_forms(lib, sid):
    """Every other item of the form, once, in order: the text as written (hard line breaks as spaces), a
    1–5 linear scale as likert5, a multiple choice as select with its options, short answer and paragraph
    as text, the grid as one select per row; and nothing else."""
    form = json.loads((DATA / "han2025" / f"{HAN2025[sid][0]}.json").read_text(encoding="utf-8"))
    expected: list[dict] = []
    seen: set[str] = set()
    for it in form["items"]:
        text = it["title"].replace("\n", " ")
        if text in _ID_ITEMS or text in seen:
            continue
        seen.add(text)
        if it["type"] == "grid":
            expected += [{"text": f"{text} — {row.rstrip(':')}", "type": "select", "options": it["columns"],
                          "required": it["required"]} for row in it["rows"]]
            continue
        e = {"text": text, "required": it["required"],
             "type": {"short_answer": "text", "paragraph": "text", "multiple_choice": "select",
                      "linear_scale": "likert5"}[it["type"]]}
        if it["type"] == "linear_scale":
            assert it["options"] == ["1", "2", "3", "4", "5"] and not any(it["endpoint_labels"])
        if it["type"] == "multiple_choice":
            e["options"] = it["options"]
        expected.append(e)
    got = [{k: v for k, v in q.items() if k != "id"} for q in lib[sid]["questions"]]
    assert got == expected
    assert all(q["id"].startswith("han2025_") for q in lib[sid]["questions"])
    assert form["url"] in lib[sid]["description"]


@pytest.mark.parametrize("sid", sorted(HAL))
def test_anac_hal_sets_match_the_results_papers(lib, sid):
    qs = lib[sid]["questions"]
    assert [q["text"] for q in qs] == HAL_ITEMS
    assert all(q["type"] == "likert7" and q["scale"] == "hal_likeability" and "labels" not in q for q in qs)
    assert "https://doi.org/" in lib[sid]["reference"]


def test_han2025_ids_are_shared_by_the_same_question_across_sets(lib):
    by_text: dict[str, set[str]] = {}
    for sid in HAN2025:
        for q in lib[sid]["questions"]:
            by_text.setdefault(q["text"], set()).add(q["id"])
    assert all(len(ids) == 1 for ids in by_text.values())


def test_cli_lists_the_competition_sets(hani2_home):
    from typer.testing import CliRunner

    from hani2.cli import app

    r = CliRunner().invoke(app, ["questionnaire", "list", "--form", "pre_questionnaire"])
    assert r.exit_code == 0 and "HAN2026-PreSession" in r.output and "HAN2025-PreStudy" in r.output
    assert "HAN2026-PostSession" not in r.output


def test_questionnaires_page_has_a_competition_section():
    from hani2.evaluation import catalog_docs

    md = catalog_docs.questionnaires_markdown()
    sec = md.split("## Questionnaires of negotiation competitions", 1)[1].split("\n## ", 1)[0]
    for sid in ALL:
        assert f"{{#{sid}}}" in sec
    assert sec.index("HAN2026-PreSession") < sec.index("HAN2026-PostNegotiation") < sec.index("HAN2025-PreStudy") \
        < sec.index("ANAC-HAL2018-PostNegotiation") < sec.index("ANAC-HAL2017-PostNegotiation")
