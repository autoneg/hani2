"""The criteria catalogue and normalisation (``hani2.evaluation.criteria``): every numeric metric column
has a default normaliser, every normalised value is in [0, 1], questionnaire bounds and reversed items,
the participant-level rule, frozen references, ``GET /api/admin/criteria`` and ``hani2 scores``."""

import json
import math
from pathlib import Path

import pytest
import yaml

from hani2 import projects
from hani2.evaluation import REGISTRY
from hani2.evaluation import criteria as C
from hani2.evaluation.subjective import answer_values

ROOT = Path(__file__).resolve().parents[1]
VALUES = [None, "x", float("nan"), float("inf"), -1e9, -7, -1, -0.5, 0, 1e-9, 0.3, 0.5, 1, 2, 4, 7, 10, 1e3, 1e9]


# --------------------------------------------------------------------------- #
# Defaults                                                                     #
# --------------------------------------------------------------------------- #
def test_every_numeric_column_has_a_default_normaliser():
    missing = [f"{m.name}.{c.name} (range {c.range!r})" for m in REGISTRY.values() for c in m.columns
               if C.is_numeric(c) and C.default_normaliser(c) is None]
    assert missing == [], "give these columns a range that parses or a Column(normaliser=...): " + ", ".join(missing)
    # every default is valid, and the non-numeric columns are exactly the labels, categories and level names
    for m in REGISTRY.values():
        for c in m.columns:
            n = C.default_normaliser(c)
            if n is not None:
                assert C.check_normaliser(n) == n
            else:
                assert c.range.strip().lower() in C.NON_NUMERIC_RANGES
    nn = C.non_numeric_columns()
    assert {"status", "ended_by", "first_critical", "condition"} <= set(nn)
    assert not {c.id for c in C.metric_criteria()} & set(nn)


def test_defaults_follow_the_range_text_and_the_direction():
    by = C.by_id(C.metric_criteria())
    assert by["agreement"].normaliser == {"kind": "bounded", "lo": 0.0, "hi": 1.0}
    assert by["sim_goal_met"].normaliser == {"kind": "bounded", "lo": 0.0, "hi": 1.0}  # {0, 1}
    assert by["ja_overall"].normaliser == {"kind": "bounded", "lo": 1.0, "hi": 7.0}
    assert by["tom_other_trend"].normaliser == {"kind": "bounded", "lo": -1.0, "hi": 1.0}
    assert by["scale_tam_usefulness"].normaliser == {"kind": "bounded", "lo": 1.0, "hi": 7.0}
    assert by["human_advantage"].normaliser == {"kind": "advantage"}
    assert by["opponent_advantage"].normaliser == {"kind": "advantage"}
    assert by["welfare"].normaliser == {"kind": "bounded", "lo": 0, "hi": 2}
    # unbounded: reciprocal when lower is better, saturating otherwise (also without a direction)
    assert by["llm_tokens"].normaliser["kind"] == "reciprocal" and by["llm_tokens"].direction == "lower"
    assert by["assistant_errors"].normaliser["kind"] == "reciprocal"
    assert by["human_overrode_helpfully"].normaliser["kind"] == "saturating"
    assert by["n_offers"].normaliser == {"kind": "saturating", "scale": "reference_median"}
    assert by["n_offers"].direction == "none"


def test_levels_sources_and_costs():
    by = C.by_id(C.metric_criteria())
    assert {c.level for c in by.values()} == {"negotiation"}
    assert by["agreement"].source == "hard" and by["agreement"].cost == "live"
    assert by["ja_overall"].source == "soft" and by["ja_overall"].cost == "judge"
    assert by["scale_felt_heard"].source == "subjective" and by["scale_felt_heard"].cost == "questionnaire"
    assert by["hi_outcome"].source == "score" and by["hi_outcome"].cost == "live"
    assert by["han_interaction"].cost == "judge" and by["hi_interaction"].cost == "judge"  # scores of judged parts


@pytest.mark.parametrize("text,expected", [
    ("[0, 1]", {"kind": "bounded", "lo": 0, "hi": 1}),
    ("usually [0, 1]", {"kind": "bounded", "lo": 0, "hi": 1}),
    ("(0, 1]", {"kind": "bounded", "lo": 0, "hi": 1}),
    ("[−1, 1]", {"kind": "bounded", "lo": -1, "hi": 1}),
    ("0 or 1", {"kind": "bounded", "lo": 0, "hi": 1}),
    ("{0, 1}", {"kind": "bounded", "lo": 0, "hi": 1}),
    ("1–7", {"kind": "bounded", "lo": 1, "hi": 7}),
    ("the items' range (1–5)", {"kind": "bounded", "lo": 1, "hi": 5}),
    ("count", {"kind": "saturating", "scale": "reference_median"}),
    ("seconds", {"kind": "saturating", "scale": "reference_median"}),
    ("≥ 0 (0 = on the frontier)", {"kind": "saturating", "scale": "reference_median"}),
    ("utility difference", None), ("category", None), ("level name", None), ("", None),
])
def test_parse_range(text, expected):
    assert C.parse_range(text) == expected


def test_check_normaliser_refuses_bad_ones():
    assert C.check_normaliser("percentile") == {"kind": "percentile"}
    assert C.check_normaliser({"kind": "reciprocal", "scale": 3}) == {"kind": "reciprocal", "scale": 3.0}
    for bad in ({"kind": "nope"}, {"kind": "bounded", "lo": 1}, {"kind": "clip", "lo": 2, "hi": 1},
                {"kind": "saturating", "scale": 0}, {"kind": "saturating", "scale": "median"}, 3):
        with pytest.raises(ValueError):
            C.check_normaliser(bad)


# --------------------------------------------------------------------------- #
# Normalising                                                                  #
# --------------------------------------------------------------------------- #
def _references(cid):
    """No reference, a typical one, and the awkward ones (median 0, a constant, negatives)."""
    yield None
    yield C.build_reference([{cid: v} for v in (0, 1, 2, 3, 10)])
    yield C.build_reference([{cid: v} for v in (0, 0, 0, 0, 2)])  # median 0 -> the mean
    yield C.build_reference([{cid: 0} for _ in range(4)])  # median and mean 0 -> 1
    yield C.build_reference([{cid: v} for v in (-3, -2, -1)])


def test_every_normalised_value_is_in_the_unit_interval():
    crits = C.catalogue(forms={"per_negotiation": _form(), "post_session": _form()})
    for c in crits:
        for ref in _references(c.id):
            for d in (None, "higher", "lower", "none"):
                for x in VALUES:
                    v = C.normalise(x, c, direction=d, reference=ref)
                    assert v is None or (0.0 <= v <= 1.0 and math.isfinite(v)), (c.id, d, x, v)
    # and every normaliser kind on its own
    for n in ({"kind": "bounded", "lo": 0, "hi": 1}, {"kind": "advantage"}, {"kind": "reciprocal", "scale": 2},
              {"kind": "saturating"}, {"kind": "percentile"}, {"kind": "clip", "lo": -5, "hi": 5}):
        for ref in _references("n_offers"):
            for d in ("higher", "lower"):
                for x in VALUES:
                    v = C.normalise(x, "n_offers", direction=d, normaliser=n, reference=ref)
                    assert v is None or 0.0 <= v <= 1.0, (n, d, x, v)


def test_normalise_values():
    assert C.normalise(4, "ja_overall") == pytest.approx(0.5)
    assert C.normalise(7, "ja_overall") == 1.0 and C.normalise(9, "ja_overall") == 1.0
    assert C.normalise(1, "irrational_accept") == 0.0  # lower is better: 1 - x
    assert C.normalise(-0.4, "human_advantage") == 0.0 and C.normalise(0.375, "human_advantage") == 0.375
    assert C.normalise(None, "agreement") is None and C.normalise(float("nan"), "agreement") is None
    ref = C.build_reference([{"n_offers": v, "assistant_errors": e} for v, e in ((2, 0), (4, 0), (6, 0), (8, 1))])
    # the median game scores 0.5, in either direction
    assert ref["criteria"]["n_offers"]["median"] == 5.0
    assert C.normalise(5, "n_offers", reference=ref) == pytest.approx(0.5)
    assert C.normalise(5, "n_offers", direction="lower", reference=ref) == pytest.approx(0.5)
    assert C.normalise(15, "n_offers", reference=ref) == pytest.approx(0.75)
    assert C.normalise(15, "n_offers", direction="lower", reference=ref) == pytest.approx(0.25)
    # median 0: the scale is the mean (0.25); no reference: scale 1
    assert ref["criteria"]["assistant_errors"]["scale"] == pytest.approx(0.25)
    assert C.normalise(0, "assistant_errors", reference=ref) == 1.0
    assert C.normalise(1, "assistant_errors", reference=ref) == pytest.approx(0.2)
    assert C.normalise(1, "assistant_errors") == pytest.approx(0.5)
    # a fixed scale, and your own bounds
    assert C.normalise(3, "n_offers", direction="lower", normaliser={"kind": "reciprocal", "scale": 1}) == 0.25
    assert C.normalise(3, "n_offers", normaliser={"kind": "reciprocal", "scale": 1}) == 0.25  # no direction: lower
    assert C.normalise(3, "n_offers", direction="lower", normaliser={"kind": "clip", "lo": 0, "hi": 10}) \
        == pytest.approx(0.7)
    # percentile: the share of reference games with a lower value, ties counting half
    assert C.normalise(5, "n_offers", normaliser="percentile", reference=ref) == pytest.approx(0.5)
    assert C.normalise(100, "n_offers", normaliser="percentile", reference=ref) == 1.0
    assert C.normalise(0, "n_offers", normaliser="percentile", reference=ref) == 0.0
    assert C.normalise(5, "n_offers", normaliser="percentile") is None  # no reference
    with pytest.raises(ValueError):
        C.normalise(1, "n_offers", direction="up")


def test_normalise_takes_a_column_or_a_criterion():
    col = REGISTRY["outcome"].column_info("agreement")
    assert C.normalise(1, col) == 1.0
    crit = C.Criterion("q_x", "x", direction="higher", normaliser={"kind": "bounded", "lo": 1, "hi": 5})
    assert C.normalise(2, crit) == pytest.approx(0.25)
    assert C.normalise(2, C.Criterion("y", "y")) is None  # no normaliser: cannot be mapped


# --------------------------------------------------------------------------- #
# Questionnaires                                                               #
# --------------------------------------------------------------------------- #
def _form():
    return {"questions": [
        {"id": "sat", "text": "How **satisfied** are you?", "type": "likert5"},
        {"id": "u1", "text": "Understandable", "type": "likert7", "scale": "ux"},
        {"id": "u2", "text": "Confusing", "type": "likert7", "scale": "ux", "reverse": True},
        {"id": "again", "text": "Again?", "type": "yes_no"},
        {"id": "coop", "text": "Cooperative?", "type": "select", "options": ["a", "b", "c", "d"]},
        {"id": "pct", "text": "How sure (0-100)?", "type": "likert7", "min": 0, "max": 100, "scale": "mixed"},
        {"id": "m2", "text": "Other", "type": "likert5", "scale": "mixed"},
        {"id": "note", "text": "Anything else?", "type": "text"},
    ]}


def test_questionnaire_items_and_scales_with_their_bounds():
    by = C.by_id(C.questionnaire_criteria(_form(), "per_negotiation"))
    assert "q_note" not in by  # free text cannot be a criterion
    assert by["q_sat"].normaliser == {"kind": "bounded", "lo": 1.0, "hi": 5.0} and by["q_sat"].direction == "none"
    assert by["q_u2"].normaliser == {"kind": "bounded", "lo": 1.0, "hi": 7.0} and by["q_u2"].direction == "higher"
    assert "(reversed)" in by["q_u2"].description
    assert by["q_again"].normaliser == {"kind": "bounded", "lo": 0.0, "hi": 1.0}
    assert by["q_coop"].normaliser == {"kind": "bounded", "lo": 1.0, "hi": 4.0}
    assert by["q_pct"].normaliser == {"kind": "bounded", "lo": 0.0, "hi": 100.0}
    assert by["scale_ux"].normaliser == {"kind": "bounded", "lo": 1.0, "hi": 7.0}
    # a scale whose items have different ranges has no bounds for its raw mean: use its _norm column
    assert by["scale_mixed"].normaliser is None and by["scale_mixed_norm"].normaliser["hi"] == 1.0
    assert all(c.source == "questionnaire" and c.level == "negotiation" and c.cost == "questionnaire"
               for c in by.values())


def test_reversed_items_are_already_reversed():
    vals, texts = answer_values(_form(), {"u1": 6, "u2": 2, "sat": 4, "again": "yes", "coop": "c", "note": "hi"})
    assert vals["q_u2"] == 6  # 1 + 7 - 2
    assert vals["scale_ux"] == 6 and vals["scale_ux_norm"] == pytest.approx(5 / 6)
    assert vals["q_again"] == 1 and vals["q_coop"] == 3 and texts == {"note": "hi"}
    crit = C.by_id(C.questionnaire_criteria(_form()))
    # so the normalised reversed item is high when the answer was low
    assert C.normalise(vals["q_u2"], crit["q_u2"]) == pytest.approx(5 / 6)
    assert C.normalise(vals["q_sat"], crit["q_sat"]) == pytest.approx(0.75)


def test_the_questionnaire_metric_gives_every_item():
    from hani2.evaluation import evaluate_recording
    from hani2.recording.format import Recording

    q = {"t": 61, "k": "questionnaire", "spec": _form(), "answers": {"u1": 6, "u2": 2, "sat": 4}}
    rec = Recording.from_records([{"k": "header", "format": "hani2-recording", "version": 1, "id": "x", "t0": 0},
                                  {"t": 0, "k": "start", "human_index": 0}, q])
    row = evaluate_recording(rec, ["questionnaire"])["row"]
    assert row["q_u1"] == 6 and row["q_u2"] == 6 and row["q_sat"] == 4 and row["scale_ux"] == 6


def test_post_session_answers_are_participant_level():
    crit = C.by_id(C.questionnaire_criteria(_form(), "post_session"))
    assert set(crit) >= {"post_q_sat", "post_scale_ux", "post_scale_ux_norm"}
    assert all(c.level == "participant" for c in crit.values())
    assert C.post_session_values(_form(), {"u1": 7, "u2": 1}) == {
        "post_q_u1": 7, "post_q_u2": 7, "post_scale_ux": 7, "post_scale_ux_norm": 1.0}


def test_participant_answers_are_credited_only_with_one_assistant_throughout():
    rows = [{"user": "ann", "assistant": "A", "key": "1"}, {"user": "ann", "assistant": "A", "key": "2"},
            {"user": "bob", "assistant": "A", "key": "3"}, {"user": "bob", "assistant": "B", "key": "4"},
            {"user": "cy", "support_agent": "none", "key": "5"}]
    answers = {"ann": {"post_q_sat": 4}, "bob": {"post_q_sat": 2}, "cy": {"post_q_sat": 5}}
    out = C.attach_participant_answers(rows, answers)
    assert [r.get("post_q_sat") for r in out] == [4, 4, None, None, 5]
    assert "post_q_sat" not in rows[0]  # the input rows are not changed
    assert C.one_assistant_throughout(rows[:2]) and not C.one_assistant_throughout(rows[2:4])
    # the catalogue greys participant-level criteria out for HI scores, and says why
    crits = C.catalogue(rows=out, forms={"per_negotiation": None, "post_session": _form()})
    sat = C.by_id(crits)["post_q_sat"]
    assert not sat.hi_usable and "more than one Assistant" in sat.reason
    assert sat.coverage == pytest.approx(3 / 5)
    assert C.by_id(crits)["agreement"].hi_usable and C.by_id(crits)["agreement"].coverage == 0.0
    ok = C.catalogue(rows=out[:2], forms={"per_negotiation": None, "post_session": _form()})
    assert C.by_id(ok)["post_q_sat"].hi_usable


# --------------------------------------------------------------------------- #
# A project with a study, forms and recordings                                 #
# --------------------------------------------------------------------------- #
EXAMPLE = {"A": (1.0, 0.2), "B": (0.8, 0.4), "C": (0.6, 0.6), "D": (0.4, 0.8)}


def _write_recording(folder: Path, rid: str, *, n_offers: int, started: str, practice=False, answers=None):
    names = list(EXAMPLE)
    trace = [{"t": 0.1 * i, "negotiator": "H" if i % 2 == 0 else "O", "offer": [names[i % 4]]} for i in range(n_offers)]
    recs = [{"k": "header", "format": "hani2-recording", "version": 1, "id": rid, "t0": 0, "created": started,
             "session": {"user": rid}},
            {"t": 0, "k": "scenario", "name": "ex", "human_index": 0, "outcomes": [[k] for k in names],
             "utilities": [[EXAMPLE[k][0] for k in names], [EXAMPLE[k][1] for k in names]], "reserved": [0.1, 0.1],
             "issue_names": ["x"]},
            {"t": 0, "k": "start", "human_index": 0, "human_id": "H", "practice": practice},
            {"t": 59, "k": "trace", "rows": trace}]
    if answers:
        recs.append({"t": 60, "k": "questionnaire", "spec": _form(), "answers": answers})
    recs.append({"t": 61, "k": "result", "summary": {"status": "success"}, "row": {}, "agreement": ["C"]})
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{rid}.hrec").write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")


@pytest.fixture
def project(hani2_home):
    projects.create_project("HI2027", kind="assistant")
    projects.create_study("HI2027/play", type="online")
    projects.create_study("HI2027/late", type="online")
    sdir = projects.study_dir(projects.StudyRef("HI2027", "play"))
    (sdir / "questionnaires").mkdir(parents=True, exist_ok=True)
    (sdir / "questionnaires" / "per_negotiation.yaml").write_text(yaml.safe_dump(_form()), encoding="utf-8")
    (sdir / "questionnaires" / "post_session.yaml").write_text(yaml.safe_dump(
        {"questions": [{"id": "overall", "text": "Overall?", "type": "likert7"}]}), encoding="utf-8")
    for i, n in enumerate((2, 4, 6)):
        _write_recording(sdir / "results" / f"p{i}", f"r{i}", n_offers=n, started=f"2027-01-0{i + 1}T10:00:00",
                         answers={"sat": 3 + i})
    _write_recording(sdir / "results" / "p9", "practice", n_offers=40, started="2027-01-01T09:00:00", practice=True)
    late = projects.study_dir(projects.StudyRef("HI2027", "late")) / "results" / "q"
    _write_recording(late, "late", n_offers=40, started="2027-06-01T10:00:00")
    return "HI2027"


def test_catalogue_of_a_study_lists_its_forms(project):
    by = C.by_id(C.catalogue("HI2027", "play"))
    assert by["q_sat"].level == "negotiation" and by["q_sat"].normaliser["hi"] == 5.0
    assert by["post_q_overall"].level == "participant" and by["post_q_overall"].source == "questionnaire"
    assert "agreement" in by and "hi_team" in by
    # the other study has no forms of its own (the bundled per-negotiation form applies)
    late = C.by_id(C.catalogue("HI2027", "late"))
    assert "q_sat" not in late or late["q_sat"].normaliser["hi"] == 5.0
    assert "post_q_overall" not in late
    # the project: every study's forms
    assert "post_q_overall" in C.by_id(C.catalogue("HI2027"))


def test_freeze_writes_the_reference(project):
    ref = C.freeze("HI2027", ["play"])
    p = projects.project_dir("HI2027") / "results" / "normalisation.json"
    assert p.is_file() and json.loads(p.read_text())["criteria"]["n_offers"]["median"] == 4.0
    assert ref["schema"] == C.REFERENCE_SCHEMA and ref["games"] == 3  # practice left out
    assert ref["studies"] == ["play"] and not ref["provisional"] and ref["llm"] is False
    st = ref["criteria"]["n_offers"]
    assert st["n"] == 3 and st["min"] == 2 and st["max"] == 6 and len(st["quantiles"]) == C.N_QUANTILES
    assert "ja_overall" not in ref["criteria"]  # judged criteria need --llm
    assert C.load_reference("HI2027")["frozen_at"] == ref["frozen_at"]
    # the frozen median is the scale: adding games later does not change it
    assert C.normalise(4, "n_offers", reference=C.reference_for("HI2027")) == pytest.approx(0.5)
    _write_recording(projects.study_dir(projects.StudyRef("HI2027", "play")) / "results" / "p5", "r5", n_offers=30,
                     started="2027-01-05T10:00:00")
    assert C.normalise(4, "n_offers", reference=C.reference_for("HI2027")) == pytest.approx(0.5)
    assert C.reference_summary(C.load_reference("HI2027"))["frozen"] is True


def test_freeze_reads_the_project_setting(project):
    pdir = projects.project_dir("HI2027")
    data = yaml.safe_load((pdir / "project.yaml").read_text())
    data["defaults"] = {**(data.get("defaults") or {}), "normalisation": {"reference": {"studies": ["play", "late"],
                                                                                         "end": "2027-01-02"}}}
    (pdir / "project.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    assert C.reference_setting("HI2027") == {"studies": ["play", "late"], "end": "2027-01-02"}
    ref = C.freeze("HI2027")
    assert ref["games"] == 2 and ref["end"] == "2027-01-02" and ref["studies"] == ["play", "late"]
    # the top level of project.yaml works too
    data.pop("defaults")
    data["normalisation"] = {"reference": {"studies": "late"}}
    (pdir / "project.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    assert C.reference_setting("HI2027") == {"studies": ["late"]}
    assert C.freeze("HI2027")["games"] == 1
    with pytest.raises(ValueError, match="unknown study"):
        C.freeze("HI2027", ["nope"])
    with pytest.raises(ValueError, match="no counted games"):
        C.freeze("HI2027", ["late"], "2026-01-01")


def test_without_a_frozen_reference_the_reference_is_provisional(project):
    assert C.load_reference("HI2027") is None
    assert C.reference_summary(None) == {"frozen": False, "provisional": True}
    rows, _ = C.reference_rows("HI2027", ["play"])
    ref = C.reference_for("HI2027", rows)
    assert ref["provisional"] and C.reference_summary(ref)["frozen"] is False
    (projects.project_dir("HI2027") / "results").mkdir(exist_ok=True)
    C.reference_path("HI2027").write_text("{broken", encoding="utf-8")
    assert C.load_reference("HI2027") is None


# --------------------------------------------------------------------------- #
# API and command line                                                         #
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(hani2_home):
    from fastapi.testclient import TestClient

    from hani2.server import app

    with TestClient(app) as c:
        yield c


def test_admin_criteria_endpoint(client, project):
    assert client.get("/api/admin/criteria").status_code in (401, 403)
    assert client.post("/api/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200
    r = client.get("/api/admin/criteria")
    assert r.status_code == 200
    body = r.json()
    ids = {c["id"]: c for c in body["criteria"]}
    assert ids["human_advantage"]["normaliser"] == {"kind": "advantage"}
    assert ids["n_offers"]["normaliser_text"] == "saturating (s = reference median)"
    assert set(ids["agreement"]) >= {"id", "title", "description", "source", "level", "direction", "normaliser",
                                     "cost", "coverage"}
    assert {n["kind"] for n in body["normalisers"]} == set(C.NORMALISER_KINDS)
    assert body["reference"] == {"frozen": False, "provisional": True} and body["games"] is None
    r = client.get("/api/admin/criteria", params={"study": "HI2027/play"})
    assert r.status_code == 200, r.text
    ids = {c["id"]: c for c in r.json()["criteria"]}
    assert ids["post_q_overall"]["level"] == "participant" and ids["agreement"]["coverage"] is None
    r = client.get("/api/admin/criteria", params={"study": "HI2027/play", "coverage": "true"})
    body = r.json()
    ids = {c["id"]: c for c in body["criteria"]}
    assert body["games"] == 3 and ids["agreement"]["coverage"] == 1.0 and ids["q_sat"]["coverage"] == 1.0
    assert ids["ja_overall"]["coverage"] == 0.0
    C.freeze("HI2027", ["play"])
    ref = client.get("/api/admin/criteria", params={"project": "HI2027"}).json()["reference"]
    assert ref["frozen"] and ref["games"] == 3 and ref["studies"] == ["play"]
    assert client.get("/api/admin/criteria", params={"project": "nope"}).status_code == 404
    assert client.get("/api/admin/criteria", params={"study": "HI2027/nope"}).status_code == 404
    assert client.get("/api/admin/criteria", params={"project": "../x"}).status_code == 400
    assert client.get("/api/admin/criteria", params={"project": "other", "study": "HI2027/play"}).status_code == 400
    assert client.get("/api/admin/criteria", params={"coverage": "true"}).status_code == 400


def test_scores_cli(project, tmp_path):
    from typer.testing import CliRunner

    from hani2 import cli

    r = CliRunner().invoke(cli.app, ["scores", "freeze", "HI2027", "--studies", "play"])
    assert r.exit_code == 0, r.output
    assert "3 games" in r.output and C.load_reference("HI2027")["studies"] == ["play"]
    r = CliRunner().invoke(cli.app, ["scores", "freeze", "nope"])
    assert r.exit_code == 1 and "no project" in r.output
    r = CliRunner().invoke(cli.app, ["scores", "freeze", "HI2027", "--studies", "late", "--end", "2020-01-01"])
    assert r.exit_code == 1 and "no counted games" in r.output
    r = CliRunner().invoke(cli.app, ["scores", "criteria", "HI2027/play"])
    assert r.exit_code == 0 and "post_q_overall" in r.output and "reference: frozen" in r.output
    out = tmp_path / "c.json"
    r = CliRunner().invoke(cli.app, ["scores", "criteria", "HI2027/play", "--coverage", "-o", str(out)])
    assert r.exit_code == 0, r.output
    assert json.loads(out.read_text())["games"] == 3


# --------------------------------------------------------------------------- #
# The generated docs page                                                      #
# --------------------------------------------------------------------------- #
def test_docs_page_is_in_sync():
    page = ROOT / "docs/guide/criteria.md"
    text = page.read_text(encoding="utf-8")
    assert C.docs_section(text) == C.markdown_reference().strip() + "\n", \
        "docs/guide/criteria.md is out of date: run .venv/bin/python -m hani2.evaluation.criteria docs/guide/criteria.md"
    for c in C.metric_criteria():
        assert f"`{c.id}`" in text
    assert "HANI " not in text and "HANI." not in text
