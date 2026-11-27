"""The metric catalogue: every metric column has a group, the generated pages are current, every
validated entry names a real validation test that names it, and the API sends the groups."""

import ast
from pathlib import Path

import pytest

import hani2.evaluation  # noqa: F401  (registers the metrics)
from hani2.evaluation import catalog as C
from hani2.evaluation import catalog_docs
from hani2.evaluation.base import REGISTRY

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(hani2_home):
    from fastapi.testclient import TestClient

    from hani2.server import app

    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200
        yield c


def test_every_metric_column_has_a_group():
    assert C.ungrouped_columns() == [], "add the metric to METRIC_GROUP (or the column to COLUMN_GROUP) in catalog.py"
    assert set(C.METRIC_GROUP.values()) | set(C.COLUMN_GROUP.values()) <= set(C.GROUP_IDS)
    assert set(C.METRIC_GROUP) <= set(REGISTRY), "METRIC_GROUP names a metric that does not exist"
    known = {c.name for m in REGISTRY.values() for c in m.columns}
    assert set(C.COLUMN_GROUP) <= known, "COLUMN_GROUP names a column that does not exist"


def test_every_group_is_used_and_ids_have_rules():
    from hani2.evaluation.criteria import metric_criteria

    used = {c.group for c in metric_criteria()}
    assert used == set(C.GROUP_IDS)
    assert C.group_of("q_fun") == C.group_of("post_scale_workload_norm") == "subjective"
    assert C.group_of("my_score", source="score") == "scores"


@pytest.mark.parametrize("rel", list(catalog_docs.PAGES.values()))
def test_generated_pages_are_current(rel):
    text = catalog_docs.pages()[rel]
    assert (ROOT / rel).read_text(encoding="utf-8") == text, \
        f"{rel} is out of date: run .venv/bin/python scripts/make_metric_catalog.py"


def test_pages_are_in_the_nav():
    nav = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    for rel in catalog_docs.PAGES.values():
        assert rel.removeprefix("docs/") in nav


def _functions(path: Path) -> dict[str, tuple[str, set[str]]]:
    """Each test's source and the keys of its ``expected = {...}`` dicts that have a value (not ``None``)."""
    src = path.read_text(encoding="utf-8")
    out = {}
    for n in ast.parse(src).body:
        if not (isinstance(n, ast.FunctionDef) and n.name.startswith("test_")):
            continue
        keys = set()
        for a in ast.walk(n):
            if (isinstance(a, ast.Assign) and isinstance(a.value, ast.Dict)
                    and any(isinstance(t, ast.Name) and t.id == "expected" for t in a.targets)):
                keys |= {k.value for k, v in zip(a.value.keys, a.value.values)
                         if isinstance(k, ast.Constant) and isinstance(k.value, str)
                         and not (isinstance(v, ast.Constant) and v.value is None)}
        out[n.name] = (ast.get_source_segment(src, n) or "", keys)
    return out


def test_validated_entries_name_existing_tests_that_name_them():
    seen: dict[str, dict[str, str]] = {}
    entries = list(C.validation_entries())
    assert entries
    for entry, test in entries:
        file, _, func = test.partition("::")
        assert file.startswith("tests/validation/") and func, f"{entry}: {test!r} is not tests/validation/<file>::<test>"
        p = ROOT / file
        assert p.is_file(), f"{entry}: {file} does not exist"
        funcs = seen.setdefault(file, _functions(p))
        assert func in funcs, f"{entry}: {file} has no test {func}"
        src, expected = funcs[func]
        if entry in C.QUESTIONNAIRES:  # a questionnaire test reads the set by its id
            assert f'"{entry}"' in src, f"{test} does not use the questionnaire {entry}"
        elif "<" in entry:  # a pattern (q_<id>, scale_<name>): the test expects values of such columns
            assert any(k.startswith(entry.split("<")[0]) for k in expected), f"{test} expects no {entry} value"
        else:  # a column: the test compares it with a hand-derived value (an `expected` key that is not None)
            assert entry in expected, f"{test} has no hand-derived expected value for {entry}"


def test_not_validated_metrics_say_why():
    from hani2.evaluation.criteria import metric_criteria

    for c in metric_criteria():
        if not c.validated:
            assert C.not_validated_reason(c.id, c.metric), f"{c.id} is neither validated nor explained"
    for k, q in C.QUESTIONNAIRES.items():
        assert q.note, f"questionnaire {k} has no validation note"


def test_every_bundled_questionnaire_is_catalogued():
    from hani2 import questionnaires

    bundled = {k for k, s in questionnaires.library().items() if s["source"] == "bundled"}
    assert bundled <= set(C.QUESTIONNAIRES), f"add {sorted(bundled - set(C.QUESTIONNAIRES))} to catalog.QUESTIONNAIRES"


def test_criteria_api_sends_groups_and_marks(client):
    d = client.get("/api/admin/criteria").json()
    assert [g["id"] for g in d["groups"]] == list(C.GROUP_IDS)
    by = {c["id"]: c for c in d["criteria"]}
    assert by["human_advantage"]["group"] == "outcome" and by["human_advantage"]["validated"] is True
    assert by["fairness_gap"]["group"] == "fairness"
    assert by["ja_overall"]["group"] == "judge" and by["ja_overall"]["validated"] is False
    assert all(c["group"] in C.GROUP_IDS for c in d["criteria"])


def test_questionnaire_library_api_sends_marks_and_sources(client):
    sets = {s["id"]: s for s in client.get("/api/admin/questionnaires/library").json()["sets"]}
    assert sets["sus"]["validated"] is True and sets["subjective_value"]["url"].startswith("https://")
    assert sets["tam_ease"]["validated"] is False and sets["tam_ease"]["validation_note"]
    assert sets["demographics"]["validated"] is False


def test_scores_api_marks_validated_built_ins_only(client):
    """The built-in scores are checked on hand-worked examples; a project's own score (or a copy of a
    built-in) is not, whatever its key."""
    name = "CatalogScores"
    assert client.put(f"/api/admin/projects/{name}", json={"data": {"kind": "assistant", "year": 2027}}).status_code == 200
    assert client.post(f"/api/admin/projects/{name}/scores/my_team/duplicate", json={"from": "hi_team"}).status_code == 200
    d = client.get(f"/api/admin/scores?project={name}").json()
    by = {s["key"]: s for s in d["scores"]}
    assert by["hi_team"]["validated"] is True and by["han_outcome"]["validated"] is True
    assert by["my_team"]["validated"] is False
    assert d["validated_tooltip"] == C.VALIDATED_TOOLTIP


def test_tam_measures_carry_a_source_warning():
    """No readable copy of Davis's item sheet: every TAM set and TAM scale says so in a warning box."""
    tam_sets = {k for k in C.QUESTIONNAIRES if k.startswith("tam_")}
    assert tam_sets and tam_sets <= set(C.QUESTIONNAIRE_WARNINGS)
    tam_cols = {c.name for m in REGISTRY.values() for c in m.columns if "tam_" in c.name}
    assert tam_cols and tam_cols <= set(C.SOURCE_WARNINGS)
    for md in catalog_docs.pages().values():
        assert '!!! warning "Items not checked against the source"' in md
