"""The metric reference: every metric and column is described, the formulas
render, the docs page is in sync, the API and the CLI serve it, and the worked
examples in the texts match the implementation."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hani2.evaluation import REGISTRY, compare_rows, evaluate_recording
from hani2.evaluation.reference import AGGREGATES, FIGURES, NOTATION, details_markdown, figure_svg, reference_markdown
from hani2.recording.format import Recording

ROOT = Path(__file__).resolve().parents[1]

# the inline-math rule of the docs (arithmatex "smart dollar") and of the replay tool
INLINE = re.compile(r"(?<![\\$])\$(?![\s$])((?:\\.|[^\\$])+?)(?<![\s\\])\$(?![\d$])")
DISPLAY = re.compile(r"\$\$(.+?)\$\$", re.S)


def _columns():
    for m in REGISTRY.values():
        for c in m.columns + m.patterns:
            yield m, c


def _texts():
    yield "notation", NOTATION
    for m in REGISTRY.values():
        yield m.name, m.details
    for m, c in _columns():
        yield f"{m.name}.{c.name}", c.details
    for c in AGGREGATES:
        yield c.name, c.details


def _all_tex() -> list[tuple[str, str, bool]]:
    out = []
    for m in REGISTRY.values():
        out.append((m.name, m.formula, True))
    for m, c in _columns():
        out.append((f"{m.name}.{c.name}", c.formula, True))
    out += [(c.name, c.formula, True) for c in AGGREGATES]
    for where, text in _texts():
        out += [(where, t.strip(), True) for t in DISPLAY.findall(text)]
        out += [(where, t, False) for t in INLINE.findall(DISPLAY.sub("", text))]
    return out


def test_every_metric_and_column_is_described():
    assert len(REGISTRY) >= 17
    for m in REGISTRY.values():
        assert m.description and m.formula and m.details, m.name
        assert all(f in FIGURES for f in m.figures), m.name
    n = 0
    for m, c in _columns():
        n += 1
        assert c.description and c.formula and c.details and c.range, (m.name, c.name)
    assert n > 140
    for c in AGGREGATES:
        assert c.description and c.formula and c.details, c.name


def test_texts_have_no_escape_accidents():
    """LaTeX in non-raw strings loses ``\\t``, ``\\f``, ``\\b``… to control characters."""
    for m in REGISTRY.values():
        assert "$" not in m.formula
    for m, c in _columns():
        assert "$" not in c.formula, c.name
    for where, tex, _ in _all_tex():
        assert not re.search(r"[\x00-\x08\x0b-\x1f]", tex), where
    for where, text in _texts():
        assert not re.search(r"[\x00-\x08\x0b-\x1f]", text), where
        # every dollar is math (or escaped): an odd one would show up as text in the docs
        rest = INLINE.sub("", DISPLAY.sub("", text)).replace(r"\$", "")
        assert "$" not in rest, (where, rest[rest.find("$") - 40: rest.find("$") + 40])


@pytest.mark.skipif(not shutil.which("node") or not (ROOT / "frontend/node_modules/katex").is_dir(),
                    reason="needs node and the frontend's node_modules (npm install)")
def test_every_formula_renders_with_katex(tmp_path):
    items = [{"where": w, "tex": t, "display": d} for w, t, d in _all_tex()]
    (tmp_path / "tex.json").write_text(json.dumps(items), encoding="utf-8")
    script = tmp_path / "check.cjs"
    script.write_text(
        "const katex = require(process.argv[2]);\n"
        "const items = require(process.argv[3]);\n"
        "const bad = [];\n"
        "for (const it of items) { try { katex.renderToString(it.tex, {displayMode: it.display, throwOnError: true, strict: 'ignore'}); }"
        " catch (e) { bad.push(it.where + ': ' + e.message); } }\n"
        "console.log(JSON.stringify({n: items.length, bad}));\n", encoding="utf-8")
    res = subprocess.run(["node", str(script), str(ROOT / "frontend/node_modules/katex"), str(tmp_path / "tex.json")],
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert out["n"] > 300 and out["bad"] == []


def test_docs_page_is_in_sync():
    page = ROOT / "docs/guide/metrics.md"
    assert page.read_text(encoding="utf-8") == reference_markdown(), \
        "docs/guide/metrics.md is out of date: run .venv/bin/python scripts/make_metric_reference.py"
    text = page.read_text(encoding="utf-8")
    for m, c in _columns():
        assert f"`{c.name}`" in text
    assert "HANI " not in text and "HANI." not in text
    for name in FIGURES:
        assert figure_svg(name).startswith("<svg") and "\n\n" not in figure_svg(name)


@pytest.mark.skipif(not shutil.which("node") or not (ROOT / "frontend/node_modules").is_dir(),
                    reason="needs node (22.6+, which runs TypeScript) and npm install")
def test_frontend_math_rule():
    """The `$` rule of the replay tool's Markdown (frontend/tests/mathText.test.ts)."""
    res = subprocess.run(["node", "--test", "tests/"], cwd=ROOT / "frontend", capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stdout + res.stderr


def test_api_and_cli(hani2_home, monkeypatch):
    from typer.testing import CliRunner

    from hani2.cli import app as cli
    from hani2.server import app

    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200
        ref = c.get("/api/replay/metric-reference").json()
        assert ref["notation"] and set(ref["figures"]) == set(FIGURES)
        assert ref["figures"]["outcome_space"]["svg"].startswith("<svg")
        opt = next(m for m in ref["metrics"] if m["name"] == "optimality")
        col = next(x for x in opt["columns"] if x["name"] == "nash_distance")
        assert col["formula"] and col["details"] and opt["figures"] == ["outcome_space"]
        assert any(p["name"] == "q_<id>" for m in ref["metrics"] for p in m["patterns"])
        assert {a["name"] for a in ref["aggregates"]} >= {"mean", "std", "balanced", "pass_hat_k"}
        # the light listing stays light
        lite = c.get("/api/replay/metrics").json()["metrics"]
        assert "details" not in lite[0] and "formula" not in lite[0]["columns"][0]
        c.post("/api/auth/logout")
        c.post("/api/auth/register", json={"username": "bob", "password": "secret", "confirm": "secret", "consent": True})
        assert c.get("/api/replay/metric-reference").status_code == 403
    r = CliRunner().invoke(cli, ["replay", "metrics", "--details", "kalai_distance"])
    assert r.exit_code == 0 and "Kalai" in r.output and r"\kappa" in r.output
    r = CliRunner().invoke(cli, ["replay", "metrics", "scale_mine_norm"])
    assert r.exit_code == 0 and "rescaled" in r.output
    assert "Notation" in details_markdown() and "pass^k" in details_markdown("pass_hat_k")
    assert CliRunner().invoke(cli, ["replay", "metrics", "--details", "nope"]).exit_code == 1


# --------------------------------------------------------------------------- #
# The worked examples in the texts                                             #
# --------------------------------------------------------------------------- #
#: the example scenario of the figure: (u_h, u_o) of A–H, r = (0.2, 0.2)
EXAMPLE = dict(A=(1.0, .2), B=(.8, .6), C=(.62, .75), D=(.35, .9), E=(.1, 1.0), F=(.5, .45), G=(.3, .35), H=(.7, .3))


def _example(human_offers=("F",), agreement="F", extra=()):
    names = list(EXAMPLE)
    U = [[EXAMPLE[k][0] for k in names], [EXAMPLE[k][1] for k in names]]
    trace = [{"t": 0.1 * i, "negotiator": "H", "offer": [k]} for i, k in enumerate(human_offers)]
    return Recording.from_records([
        {"k": "header", "format": "hani2-recording", "version": 1, "id": "ex", "t0": 0},
        {"t": 0, "k": "scenario", "name": "example", "human_index": 0, "outcomes": [[k] for k in names],
         "utilities": U, "reserved": [0.2, 0.2], "issue_names": ["x"]},
        {"t": 0, "k": "start", "human_index": 0, "human_id": "H"},
        {"t": 59, "k": "trace", "rows": trace},
        *extra,
        {"t": 60, "k": "result", "summary": {"status": "success"}, "row": {},
         "agreement": [agreement] if agreement else None},
    ])


def test_outcome_and_optimality_examples():
    row = evaluate_recording(_example(), ["outcome", "optimality", "scenario_stats"])["row"]
    assert row["human_utility"] == 0.5 and row["opponent_utility"] == 0.45
    assert row["human_advantage"] == pytest.approx(0.375) and row["opponent_advantage"] == pytest.approx(0.3125)
    assert row["welfare"] == pytest.approx(0.95)
    assert row["pareto_distance"] == pytest.approx(0.3231, abs=1e-4)
    assert row["nash_distance"] == pytest.approx(0.3354, abs=1e-4)
    assert row["kalai_distance"] == pytest.approx(0.3231, abs=1e-4)
    assert row["welfare_optimality"] == pytest.approx(0.95 / 1.4)
    assert row["nash_product_ratio"] == pytest.approx(0.3125)
    assert row["fairness_gap"] == pytest.approx(0.0625)
    assert row["n_outcomes"] == 8 and row["pareto_size"] == 5 and row["zopa_fraction"] == pytest.approx(0.875)
    assert row["opposition"] == pytest.approx(0.4472, abs=1e-4)
    # no deal: the reservation point
    nd = evaluate_recording(_example(agreement=None), ["outcome", "optimality"])["row"]
    assert nd["agreement"] == 0 and nd["human_utility"] == 0.2 and nd["human_advantage"] == 0
    assert nd["nash_product_ratio"] == 0 and nd["fairness_gap"] == 0


def test_dynamics_example():
    row = evaluate_recording(_example(human_offers=("A", "B", "B", "C"), agreement="C"), ["dynamics"])["row"]
    assert row["human_move_concession"] == pytest.approx(2 / 3) and row["human_move_silent"] == pytest.approx(1 / 3)
    assert row["human_concession"] == pytest.approx(0.38) and row["tom_reflect_index"] == pytest.approx(1 / 3)


def test_activity_and_assistant_examples():
    tel = {"t": 0, "k": "tel", "sent": 0, "ev": [[0, "mm", 1, 1]]}
    tels = [dict(tel, t=t, ev=[[0, "mm", 1, 1]]) for t in (2, 3, 20, 24, 58)]
    chat = [{"t": 10, "k": "chat", "user": "You", "text": "a"}, {"t": 12, "k": "chat", "user": "You", "text": "b"},
            {"t": 15, "k": "chat", "user": "Assistant", "text": "c"}, {"t": 60, "k": "chat", "user": "Assistant", "text": "d"}]
    row = evaluate_recording(_example(extra=tels + chat), ["activity", "assistant_interaction"])["row"]
    assert row["idle_fraction"] == pytest.approx(51 / 60)
    assert row["unanswered_messages"] == 1 and row["assistant_response_seconds"] == pytest.approx(3)
    assert row["unsolicited_messages"] == 1 and row["max_assistant_streak"] == 2


def test_compare_examples():
    rows = [dict(opponent="A", scenario="s1", x=v) for v in (0.2, 0.4, 0.6)] + [dict(opponent="A", scenario="s2", x=1.0)]
    g = compare_rows(rows, by="opponent", columns=[{"name": "x"}])["groups"][0]
    assert g["mean"]["x"] == pytest.approx(0.55) and g["balanced"]["x"] == pytest.approx(0.7)
    rows = [dict(opponent="A", scenario="s", agreement=a) for a in (1, 1, 0, 0)]
    rel = {r["k"]: r["pass_hat_k"] for r in compare_rows(rows, by="opponent")["reliability"]}
    assert rel[1] == pytest.approx(0.5) and rel[2] == pytest.approx(1 / 6) and rel[3] == 0


def test_dynamic_columns_get_descriptions():
    from hani2.evaluation import evaluate_many

    rec = _example(extra=[{"t": 61, "k": "questionnaire", "spec": {"questions": [
        {"id": "mine", "type": "likert7", "scale": "custom"}, {"id": "solo", "type": "likert5"}]},
        "answers": {"mine": 5, "solo": 4}}])
    cols = {c["name"]: c for c in evaluate_many([("k", rec)], ["questionnaire"])["columns"]}
    assert cols["scale_custom_norm"]["description"] and cols["q_solo"]["description"]
    assert cols["scale_custom"]["description"] != cols["scale_custom_norm"]["description"]


def test_timing_examples():
    state = {"phase": "running", "negotiation": {"is_my_turn": True, "thinking": False}}
    acts = [{"t": 12, "k": "act", "actor": "human", "type": "text", "text": "hi"},
            {"t": 14.5, "k": "act", "actor": "human", "type": "offer", "offer": ["B"]}]
    rec = _example(extra=[{"t": 10, "k": "out", "m": "state", "seq": 1, "full": state}, *acts])
    assert evaluate_recording(rec, ["timing"])["details"]["timing"]["decision_times"] == [2, 4.5]
    # without a browser: the session's turn events (a message does not start a new turn)
    acts = [{"t": t, "k": "act", "actor": "human", "type": "offer", "offer": ["B"]} for t in (5, 9, 14)]
    turns = [{"t": t, "k": "turn"} for t in (1, 7, 12)]
    msg = [{"t": 8, "k": "act", "actor": "human", "type": "text", "text": "hi"}]
    rec = _example(extra=sorted(acts + turns + msg, key=lambda e: e["t"]))
    assert evaluate_recording(rec, ["timing"])["details"]["timing"]["decision_times"] == [4, 1, 2, 2]
    # older recordings with neither: from the start or the previous move, never 0 by construction
    rec = _example(extra=sorted(acts + msg, key=lambda e: e["t"]))
    assert evaluate_recording(rec, ["timing"])["details"]["timing"]["decision_times"] == [5, 3, 4, 5]


def test_headless_sessions_record_turns(hani2_home):
    import time

    from hani2.testing import make_session

    s = make_session(assistant_settings={"mode": "off"})
    s.start()
    for _ in range(2):
        s.wait_for_turn()
        time.sleep(0.3)
        s.send_counter()
    s.wait_for_turn()
    time.sleep(0.3)
    s.end()
    assert s.wait(lambda: Recording.load(s.recorder.path).of("trace"), 10)
    times = evaluate_recording(Recording.load(s.recorder.path), ["timing"])["details"]["timing"]["decision_times"]
    assert len(times) == 3 and all(0.25 < t < 2 for t in times), times


def test_system_use_example():
    ev = [{"t": 1, "k": "draft", "by": "agent", "values": {"x": "B"}},
          {"t": 2, "k": "act", "actor": "human", "type": "offer", "offer": ["B"]},
          {"t": 3, "k": "draft", "by": "agent", "values": {"x": "C"}},
          {"t": 4, "k": "draft", "by": "human", "values": {"x": "D"}},
          {"t": 5, "k": "draft", "by": "human", "values": {"x": "E"}},
          {"t": 6, "k": "act", "actor": "human", "type": "offer", "offer": ["F"]}]
    row = evaluate_recording(_example(extra=ev), ["system_use"])["row"]
    assert row["n_suggestions"] == 2 and row["suggestion_adoption"] == 0.5 and row["suggestions_ignored"] == 1
    assert row["drafts_explored"] == 2 and row["drafts_per_action"] == 1


def test_questionnaire_example():
    items = [("u", 6, False), ("s", 5, False), ("e", 6, False), ("f", 5, False), ("c", 2, True), ("p", 5, False)]
    spec = {"questions": [{"id": i, "type": "likert7", "scale": "ueq_pragmatic", "reverse": r} for i, _, r in items]}
    q = {"t": 61, "k": "questionnaire", "spec": spec, "answers": {i: v for i, v, _ in items}}
    row = evaluate_recording(_example(extra=[q]), ["questionnaire"])["row"]
    assert row["scale_ueq_pragmatic"] == pytest.approx(5.5) and row["scale_ueq_pragmatic_norm"] == pytest.approx(0.75)


def test_llm_judge_examples(hani2_home, monkeypatch):
    from hani2.evaluation import llm_judge

    answers = {
        "EXPECTED": {"results": [{"met": v} for v in (True, True, True, True, False, None, None)]},
        "ERRORS": {"errors": [{"source": "assistant", "time": "01:10", "severity": "minor"},
                              {"source": "human", "time": "02:30", "severity": "critical"},
                              {"source": "assistant", "time": "03:05", "severity": "critical"}],
                   "overrides_helped": 1, "overrides_hurt": 0},
    }
    monkeypatch.setattr(llm_judge, "CALL", lambda prompt, s: json.dumps(next(v for k, v in answers.items() if k in prompt)))
    acts = [{"t": 5, "k": "act", "actor": "human", "type": "offer", "offer": ["B"]}]
    row = evaluate_recording(_example(extra=acts), ["nl_assertions", "error_review"], use_llm=True,
                             options={"assertions": [f"a{i}" for i in range(7)]})["row"]
    assert row["assertions_met"] == pytest.approx(0.8) and row["assertions_total"] == 5
    assert row["assistant_errors"] == 2 and row["assistant_critical_errors"] == 1
    assert row["human_errors"] == 1 and row["human_critical_errors"] == 1 and row["first_critical"] == "human"
