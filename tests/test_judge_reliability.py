"""Judge reliability of the soft score components: two judge models, inter-judge agreement,
judge–questionnaire correlation, the scores and leaderboards under each judge, and the gate that
keeps unreliable components out of a ranking."""

import gzip
import json
import random
import re
from types import SimpleNamespace

import pytest
from conftest import write_settings

from hani2.recording.format import Recording


def _records(i: int, kindness: int, assistant: bool = False) -> list[dict]:
    """A small session (the human says "session-<i>") against opponent ``opp<i % 3>``, whose
    participant rated the opponent's kindness ``kindness`` (1–7)."""
    q = {"t": 61, "k": "questionnaire",
         "spec": {"questions": [{"id": "k", "type": "likert7", "scale": "opponent_kindness"}]},
         "answers": {"k": kindness}}
    start = {"t": 0, "k": "start", "human_index": 0, "human_id": "H", "opponent": f"opp{i % 3}"}
    if assistant:
        start["support_agent"] = {"enabled": True, "name": f"asst{i % 3}"}
    rows = [
        {"k": "header", "format": "hani2-recording", "version": 1, "id": f"r{i}", "t0": 0,
         "session": {"user": f"u{i}"}},
        {"t": 0, "k": "scenario", "name": "example", "human_index": 0, "outcomes": [["A"], ["B"]],
         "utilities": [[1.0, 0.0], [0.0, 1.0]], "reserved": [0.2, 0.2], "issue_names": ["x"]},
        start,
        {"t": 1, "k": "act", "actor": "human", "type": "text", "text": f"session-{i}"},
    ]
    if assistant:
        rows += [{"t": 2, "k": "chat", "user": "Assistant", "text": "I can suggest offers."},
                 {"t": 3, "k": "act", "actor": "human", "type": "offer", "offer": ["A"]}]
    rows += [{"t": 59, "k": "trace", "rows": [{"t": 0.1, "negotiator": "O", "offer": ["B"]}]}, q,
             {"t": 60, "k": "result", "summary": {"status": "success"}, "row": {}, "agreement": ["B"]}]
    return rows


def _rec(i: int, kindness: int, assistant: bool = False) -> Recording:
    return Recording.from_records(_records(i, kindness, assistant))


def _answer(model: str, i: int) -> dict:
    """What a fake judge says about session ``i``."""
    rnd = random.Random(f"{model}-{i}")
    return {"overall": i % 7 + 1,                       # both judges agree and follow the participant
            "communication": rnd.randint(1, 7),         # the judges disagree
            "human_likeness": 7,                        # constant: alpha undefined
            "consistency": None,                        # never judged
            "helpfulness": i % 5 + 2, "engagement": 3 + i % 4, "use_of_assistant": 1 + i % 7,
            "autonomy_respect": rnd.randint(1, 7), "justification": "x"}


def _session(prompt: str) -> int:
    return int(re.search(r"session-(\d+)", prompt).group(1))


def _fake(prompt: str, settings: dict) -> str:
    i, model = _session(prompt), settings["model"]
    if "EXPECTED OUTCOMES" in prompt:
        n = len(re.findall(r"^\d+\. ", prompt.split("EXPECTED OUTCOMES:")[1].split("RECORD:")[0], re.M))
        return json.dumps({"results": [{"met": (i + j) % 2 == 0} for j in range(n)]})
    if "List the ERRORS" in prompt:
        sev = "critical" if i % 3 == 0 else "minor"
        return json.dumps({"errors": [{"source": "human" if i % 2 else "assistant", "time": "00:01",
                                       "severity": sev}] * (1 + i % 3),
                           "overrides_helped": i % 2, "overrides_hurt": i % 2})
    return json.dumps(_answer(model, i))


JUDGES = ["ollama:judge-a", "ollama:judge-b"]


# --------------------------------------------------------------------------- #
# Statistics                                                                   #
# --------------------------------------------------------------------------- #
def test_krippendorff_alpha_textbook_values():
    """Krippendorff (2011), *Computing Krippendorff's alpha-reliability*: 4 coders, 12 units."""
    from hani2.evaluation.reliability import krippendorff_alpha

    N = None
    A = [1, 2, 3, 3, 2, 1, 4, 1, 2, N, N, N]
    B = [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, N, 3]
    C = [N, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, N]
    D = [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, N]
    units = list(zip(A, B, C, D))
    assert krippendorff_alpha(units, "nominal") == pytest.approx(0.743, abs=1e-3)
    assert krippendorff_alpha(units, "ordinal") == pytest.approx(0.815, abs=1e-3)
    assert krippendorff_alpha(units, "interval") == pytest.approx(0.849, abs=1e-3)
    assert krippendorff_alpha([[7, 7], [7, 7], [7, 7]], "ordinal") is None  # no variance
    assert krippendorff_alpha([[1, 1], [2, 2], [3, 3]], "ordinal") == pytest.approx(1.0)


def test_spearman_ties_and_constant():
    from hani2.evaluation.reliability import spearman

    rho, p = spearman([1, 2, 2, 3, 4], [10, 20, 20, 30, 40])
    assert rho == pytest.approx(1.0) and p == 0.0
    assert spearman([1, 1, 1], [1, 2, 3]) == (None, None)


def test_the_components_are_the_soft_components_of_the_scores():
    from hani2.evaluation.reliability import score_components, soft_columns
    from hani2.evaluation.scores import SCORES

    comps = {c["name"]: c for c in score_components()}
    used = {c.column for s in SCORES for c in s.components}
    assert set(comps) == used & soft_columns()
    assert comps["jo_overall"]["scores"] == [{"score": "han_interaction", "track": "han", "weight": 1.0}]
    assert comps["assistant_critical_errors"]["level"] == "interval" and comps["assistant_critical_errors"]["norm"] == "count"
    assert "jo_kindness" not in comps and "jo_kindness" in {c["name"] for c in score_components(all_soft=True)}
    # a weight of 0 takes a component out of the scores
    assert "jo_overall" not in {c["name"] for c in score_components(
        options={"scores": {"han_interaction": {"weights": {"jo_overall": 0}}}})}


# --------------------------------------------------------------------------- #
# The report                                                                   #
# --------------------------------------------------------------------------- #
def test_reliability_report(hani2_home, monkeypatch):
    from hani2.evaluation import judge_reliability, llm_judge
    from hani2.evaluation.reliability import reliability_markdown

    monkeypatch.setattr(llm_judge, "CALL", _fake)
    recs = [(f"r{i}", _rec(i, i % 7 + 1)) for i in range(15)]  # HAN: no Assistant
    rep = judge_reliability(judges=JUDGES, recordings=recs)
    comp = {c["name"]: c for c in rep["components"]}
    assert set(comp) == {"jo_overall", "jo_communication", "jo_human_likeness"}  # consistency never judged
    ov = comp["jo_overall"]
    assert ov["n"] == 15 and ov["alpha"] == pytest.approx(1.0) and ov["exact"] == 1.0 and ov["ready"]
    q = {x["questionnaire"]: x for x in ov["questionnaire"]}["scale_opponent_kindness_norm"]
    assert q["n"] == 15 and q["rho"] == pytest.approx(1.0)
    assert not comp["jo_communication"]["ready"] and "disagree" in comp["jo_communication"]["verdict"]
    hl = comp["jo_human_likeness"]
    assert hl["alpha"] is None and "no variance" in hl["verdict"] and not hl["ready"]
    assert rep["ready"] == ["jo_overall"] and set(rep["not_ready"]) == {"jo_communication", "jo_human_likeness"}
    # the score under each judge: only the disagreeing component differs
    han = {s["name"]: s for s in rep["scores"]}["han_interaction"]
    assert han["n"] == 15 and han["alpha"] is not None and han["alpha"] < 1
    # the HAN interaction board under each judge (three opponents)
    board = {b["track"]: b for b in rep["boards"]}["han"]
    assert board["entrants"] == 3 and {o["entrant"] for o in board["order"]} == {"opp0", "opp1", "opp2"}
    md = reliability_markdown(rep)
    assert "`jo_overall`" in md and "han_interaction ×1" in md and "Leaderboards under each judge" in md
    # too few sessions
    few = judge_reliability(judges=JUDGES, recordings=recs[:5], boards=False)
    assert not any(c["ready"] for c in few["components"]) and few["boards"] == []


def test_judges_must_differ(hani2_home):
    from hani2.evaluation import judge_reliability

    with pytest.raises(ValueError, match="at least two"):
        judge_reliability(judges=["ollama:a"], recordings=[])
    with pytest.raises(ValueError, match="same model"):
        judge_reliability(judges=["ollama:a", "ollama:a"], recordings=[])


def test_each_judge_reaches_its_own_model(hani2_home, monkeypatch):
    """Through the real call path: the pinned judge is the model litellm is asked for (no chain
    fallback), and each judge's judgements are cached under its own key."""
    import litellm

    from hani2.evaluation import evaluate_recording, llm_judge

    seen = []

    def fake(**kw):
        seen.append(kw["model"])
        msg = SimpleNamespace(content=json.dumps(_answer(kw["model"], _session(kw["messages"][0]["content"]))),
                              tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None)

    monkeypatch.setattr(litellm, "completion", fake)
    monkeypatch.setattr(llm_judge, "CALL", None)
    rec = _rec(3, 4)
    a = evaluate_recording(rec, ["judge_opponent"], use_llm=True, judge="ollama:judge-a")["row"]
    b = evaluate_recording(rec, ["judge_opponent"], use_llm=True, judge="ollama:judge-b")["row"]
    assert seen == ["ollama_chat/judge-a", "ollama_chat/judge-b"]
    assert a["jo_overall"] == b["jo_overall"] == 4
    with llm_judge.use_judge("ollama:judge-a"):
        ka = llm_judge.cache_key("judge_opponent", "1", {})
    with llm_judge.use_judge("ollama:judge-b"):
        kb = llm_judge.cache_key("judge_opponent", "1", {})
    assert ka != kb and "judge-a" in ka and "judge-b" in kb
    assert llm_judge._PINNED.get() is None  # the pin ends with the block


# --------------------------------------------------------------------------- #
# The gate                                                                     #
# --------------------------------------------------------------------------- #
def test_leaderboard_leaves_out_components_that_are_not_ready(hani2_home, monkeypatch):
    from hani2.evaluation import evaluate_many, judge_reliability, leaderboard, llm_judge
    from hani2.evaluation.reliability import soft_columns

    monkeypatch.setattr(llm_judge, "CALL", _fake)
    recs = [(f"r{i}", _rec(i, i % 7 + 1)) for i in range(15)]
    rep = judge_reliability(judges=JUDGES, recordings=recs, boards=False)
    with llm_judge.use_judge(JUDGES[0]):
        rows = evaluate_many(recs, None, use_llm=True)["rows"]
    free = leaderboard(rows, "han", "interaction", n_boot=0)
    assert {"jo_overall", "jo_communication", "jo_human_likeness"} <= set(free["components"]["han_interaction"])
    gated = leaderboard(rows, "han", "interaction", n_boot=0, reliability=rep)
    comps = set(gated["components"]["han_interaction"])
    assert "jo_overall" in comps and not comps & {"jo_communication", "jo_human_likeness", "jo_consistency"}
    assert "scale_opponent_kindness_norm" in comps  # questionnaire and log components stay
    assert set(gated["reliability"]["left_out"]["han_interaction"]) == {"jo_communication", "jo_human_likeness",
                                                                         "jo_consistency"}
    assert gated["reliability"]["judges"] == rep["judges"]
    assert {r["judge_model"] for r in rows} == {rep["judges"][0]}
    assert not any("judged by" in w for w in gated["warnings"])
    assert leaderboard(rows, "han", "interaction", n_boot=0, reliability=rep, official=True)["components"] \
        == gated["components"]
    # sessions judged by a model the report did not check
    with llm_judge.use_judge("ollama:judge-c"):
        rows_c = evaluate_many(recs, None, use_llm=True)["rows"]
    other = leaderboard(rows_c, "han", "interaction", n_boot=0, reliability=rep)
    assert "jo_overall" in other["components"]["han_interaction"]
    assert any("did not check" not in w and "judge-c" in w for w in other["warnings"])
    off_c = leaderboard(rows_c, "han", "interaction", n_boot=0, reliability=rep, official=True)
    assert not set(off_c["components"]["han_interaction"]) & soft_columns()
    assert any("did not check" in w for w in off_c["warnings"])
    # official without a report: no soft component at all
    off = leaderboard(rows, "han", "interaction", n_boot=0, official=True)
    assert not set(off["components"]["han_interaction"]) & {"jo_overall", "jo_communication"}
    assert any("without a judge reliability report" in w for w in off["warnings"])
    # official with the report named in env.json (relative: the settings folder)
    (hani2_home / "settings").mkdir(parents=True, exist_ok=True)
    (hani2_home / "settings" / "rel.json").write_text(json.dumps(rep))
    write_settings(hani2_home, "env.json", {"evaluation": {"reliability": {"report": "rel.json"}}})
    env = leaderboard(rows, "han", "interaction", n_boot=0, official=True)
    assert env["components"] == gated["components"] and env["reliability"]["report"].endswith("rel.json")
    with pytest.raises(ValueError, match="not a judge reliability report"):
        leaderboard(rows, "han", "interaction", n_boot=0, reliability={"x": 1})


def _write_hrec(folder, i: int) -> None:
    rows = _records(i, i % 7 + 1, assistant=True)
    (folder / f"r{i}.hrec").write_bytes(gzip.compress("\n".join(json.dumps(r) for r in rows).encode()))


def test_cli_report_and_gated_leaderboard(hani2_home, monkeypatch, tmp_path):
    """The commands as users run them: every soft score component of the HI track, JSON output,
    both judges cached on disk, and the report gating `leaderboard`."""
    from typer.testing import CliRunner

    from hani2.cli import app
    from hani2.evaluation import llm_judge

    calls = []

    def fake(prompt, settings):
        calls.append(settings["model"])
        return _fake(prompt, settings)

    monkeypatch.setattr(llm_judge, "CALL", fake)
    folder = tmp_path / "recs"
    folder.mkdir()
    for i in range(12):
        _write_hrec(folder, i)
    out = tmp_path / "rep.json"
    args = ["replay", "judge-reliability", str(folder), "-j", JUDGES[0], "-j", JUDGES[1], "-o", str(out)]
    r = CliRunner().invoke(app, args)
    assert r.exit_code == 0, r.output
    rep = json.loads(out.read_text())
    comp = {c["name"]: c for c in rep["components"]}
    assert rep["recordings"] == 12 and not rep["errors"]
    assert {"ja_helpfulness", "ja_overall", "jh_engagement", "jh_use_of_assistant", "assertions_met",
            "assistant_errors", "assistant_critical_errors", "human_critical_errors",
            "human_overrode_harmfully"} <= set(comp)
    assert comp["assistant_errors"]["level"] == "interval" and comp["assistant_errors"]["ready"]
    assert comp["jh_engagement"]["ready"] and "agreement only" in comp["jh_engagement"]["verdict"]
    assert not comp["ja_autonomy_respect"]["ready"]
    assert {s["name"] for s in rep["scores"]} >= {"hi_assistant", "hi_team", "hi_interaction"}
    assert {b["track"] for b in rep["boards"]} == {"hi"}
    assert "Judge reliability" in r.output
    assert len(list(folder.glob("*.eval.json"))) == 12
    n = len(calls)
    assert {"judge-a", "judge-b"} <= set(calls)
    assert CliRunner().invoke(app, args).exit_code == 0 and len(calls) == n  # from the cache
    # --all-soft adds the columns no score uses (first_critical is nominal)
    r2 = CliRunner().invoke(app, args[:-2] + ["--all-soft", "-o", str(tmp_path / "all.json")])
    allc = {c["name"]: c for c in json.loads((tmp_path / "all.json").read_text())["components"]}
    assert r2.exit_code == 0 and allc["first_critical"]["level"] == "nominal" and not allc["first_critical"]["in_score"]
    # the leaderboard reads the report
    n = len(calls)
    lb = CliRunner().invoke(app, ["replay", "leaderboard", str(folder), "-t", "hi", "-b", "interaction",
                                  "--judge", JUDGES[0], "--reliability", str(out), "--official"])
    assert lb.exit_code == 0, lb.output
    assert "left out (judge reliability not shown)" in lb.output and "ja_autonomy_respect" in lb.output
    assert "judged by" not in lb.output and len(calls) == n  # the checked judge, from the cache
    bad = CliRunner().invoke(app, ["replay", "judge-reliability", str(folder), "-j", JUDGES[0]])
    assert bad.exit_code == 1 and "at least two" in bad.output
    empty = tmp_path / "empty"
    empty.mkdir()
    r3 = CliRunner().invoke(app, ["replay", "judge-reliability", str(empty), "-j", "ollama:a", "-j", "ollama:b"])
    assert r3.exit_code == 0 and "0 recordings" in r3.output


def test_api_takes_the_report_not_a_path(hani2_home):
    from fastapi.testclient import TestClient

    from hani2.server import app

    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200
        r = c.post("/api/replay/leaderboard", json={"keys": ["x"], "track": "hi", "reliability": "/etc/passwd"})
        assert r.status_code == 400 and "not a path" in r.json()["detail"]
