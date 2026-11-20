"""Per-scenario evaluation criteria (rule checks, judged criteria, task
success), the combined scores and the HAN / HI leaderboards."""

import json
import shutil

import pytest
import yaml
from fastapi.testclient import TestClient

from hani2.evaluation import evaluate_paths, evaluate_recording, leaderboard, leaderboards
from hani2.evaluation.scores import BY_NAME, score_row
from hani2.evaluation.tasks import check_target
from hani2.recording.format import Recording, iter_recordings


def _rec(points: dict, **kw):
    """A synthetic recording: one issue ``x`` whose values are the keys of ``points`` ((u_h, u_o) each)."""
    return Recording.from_records(_records(points, **kw))


def _records(points: dict, *, agreement=None, ended_by=None, extra=(), evaluation=None, status="success",
             reserved=(0.2, 0.2), header=None, start=None):
    names = list(points)
    sc = {"t": 0, "k": "scenario", "name": "s", "human_index": 0, "outcomes": [[k] for k in names],
          "utilities": [[points[k][0] for k in names], [points[k][1] for k in names]], "reserved": list(reserved),
          "issue_names": ["x"]}
    if evaluation is not None:
        sc["evaluation"] = evaluation
    return [
        {"k": "header", "format": "hani2-recording", "version": 1, "id": "ex", "t0": 0, **(header or {})},
        sc,
        {"t": 0, "k": "start", "human_index": 0, "human_id": "H", **(start or {})},
        *extra,
        {"t": 60, "k": "result", "summary": {"status": status, "ended_by": ended_by or ""}, "row": {},
         "agreement": [agreement] if agreement else None},
    ]


# --------------------------------------------------------------------------- #
# Targets, rule checks, task success                                           #
# --------------------------------------------------------------------------- #
def test_check_target():
    assert check_target(0.5, ">= 0.4") and not check_target(0.3, ">= 0.4")
    assert check_target(0.4, ">= 0.4") and check_target(0.4 - 1e-8, ">=0.4")  # rounding tolerance
    assert check_target(1, 1) and not check_target(0, 1) and check_target(1, True) and check_target(0, False)
    assert check_target(0.5, [0.4, 0.6]) and not check_target(0.7, [0.4, 0.6]) and check_target(0.9, [0.4, None])
    assert check_target("success", "== success") and check_target("broken", "!= success")
    assert check_target(0.1, "< 0.2") and not check_target(0.2, "< 0.2")
    assert check_target(None, ">= 0") is None and check_target(0.5, ">= abc") is None


def test_rule_checks_example():
    """The example of the rule_checks reference: suggestions worth 0.6, 0.15, 0.3; the Human accepts 0.18."""
    pts = dict(P=(0.6, 0.3), Q=(0.15, 0.9), R=(0.3, 0.5), S=(0.18, 0.95))
    drafts = [{"t": t, "k": "draft", "by": "agent", "values": {"x": v}} for t, v in ((1, "P"), (2, "Q"), (3, "R"))]
    acts = [{"t": 50, "k": "act", "actor": "human", "type": "accept", "offer": ["S"]}]
    row = evaluate_recording(_rec(pts, agreement="S", ended_by="human", extra=drafts + acts), ["rule_checks"])["row"]
    assert row["irrational_suggestions"] == 1 and row["irrational_accept"] == 1
    assert row["opponent_irrational_accept"] == 0 and row["opponent_failed"] == 0 and row["infrastructure_failure"] == 0
    # the Opponent accepting an offer worth less to it than its reservation value
    row = evaluate_recording(_rec(dict(A=(0.9, 0.1), B=(0.5, 0.5)), agreement="A", ended_by="agent"), ["rule_checks"])["row"]
    assert row["opponent_irrational_accept"] == 1 and row["irrational_accept"] == 0
    assert "irrational_suggestions" not in row  # no Assistant activity
    row = evaluate_recording(_rec(pts, status="agent_failed"), ["rule_checks"])["row"]
    assert row["opponent_failed"] == 1 and row["irrational_accept"] == 0


PTS = dict(A=(1.0, 0.2), B=(0.6, 0.6), C=(0.44, 0.8), D=(0.1, 1.0))  # advantages (r = 0.2): A 1, B 0.5, C 0.3, D < 0
CRIT = {"targets": {"agreement": 1, "human_advantage": ">= 0.4"}, "rules": ["irrational_accept"]}


def test_task_success_example():
    """The example of the task_success reference."""
    ok = evaluate_recording(_rec(PTS, agreement="B", ended_by="agent", evaluation=CRIT), ["task_success"])["row"]
    assert ok["human_advantage"] == pytest.approx(0.5)
    assert ok["task_targets_met"] == 1 and ok["task_rules_ok"] == 1 and ok["task_success"] == 1
    assert ok["task_components"] == 2
    bad = evaluate_recording(_rec(PTS, agreement="C", ended_by="agent", evaluation=CRIT), ["task_success"])["row"]
    assert bad["human_advantage"] == pytest.approx(0.3)
    assert bad["task_targets_met"] == pytest.approx(0.5) and bad["task_success"] == 0
    # accepting below the reservation value breaks the rule
    acts = [{"t": 50, "k": "act", "actor": "agent", "type": "accept", "offer": ["D"]}]
    crit = dict(CRIT, targets={"agreement": 1})
    r = evaluate_recording(_rec(PTS, agreement="D", ended_by="human", extra=acts, evaluation=crit), ["task_success"])["row"]
    assert r["irrational_accept"] == 1 and r["task_rules_ok"] == 0 and r["task_success"] == 0
    # no criteria: nothing
    assert "task_success" not in evaluate_recording(_rec(PTS, agreement="B"), ["task_success"])["row"]
    # criteria from the options (for scenarios without their own); the scenario's own win
    r = evaluate_recording(_rec(PTS, agreement="C"), ["task_success"], options={"criteria": CRIT})["row"]
    assert r["task_success"] == 0
    r = evaluate_recording(_rec(PTS, agreement="C", evaluation={"targets": {"agreement": 1}}), ["task_success"],
                           options={"criteria": CRIT})["row"]
    assert r["task_success"] == 1


def test_task_success_basis():
    crit = dict(CRIT, communicate=["Price matters most"])
    # without the judge the default basis uses what was evaluated
    r = evaluate_recording(_rec(PTS, agreement="B", evaluation=crit), ["task_success"])["row"]
    assert r["task_success"] == 1 and r["task_components"] == 2
    # an explicit basis is strict: an unevaluated component leaves the result empty
    r = evaluate_recording(_rec(PTS, agreement="B", evaluation=dict(crit, basis=["targets", "communicate"])),
                           ["task_success"])["row"]
    assert r["task_success"] is None and r["task_components"] == 2
    r = evaluate_recording(_rec(PTS, agreement="C", evaluation=dict(crit, basis=["rules"])), ["task_success"])["row"]
    assert r["task_success"] == 1 and r["task_components"] == 1
    with pytest.raises(Exception):
        from hani2.evaluation.base import EvalContext
        from hani2.evaluation.tasks import task_success

        ctx = EvalContext(_rec(PTS, agreement="B", evaluation=dict(CRIT, basis=["nope"])))
        task_success(ctx, {})


def test_task_judge(hani2_home, monkeypatch):
    from hani2.evaluation import llm_judge

    prompts = []

    def fake(prompt, s):
        prompts.append(prompt)
        return json.dumps({"facts": [{"conveyed": True}, {"conveyed": True}, {"conveyed": False}],
                           "assertions": [{"met": True}, {"met": None}]})

    monkeypatch.setattr(llm_judge, "CALL", fake)
    crit = dict(CRIT, communicate=["f1", "f2", "f3"], assertions=["a1", "a2"])
    chat = [{"t": 5, "k": "chat", "user": "Assistant", "text": "Price matters most to you."}]
    rec = _rec(PTS, agreement="B", extra=chat, evaluation=crit)
    out = evaluate_recording(rec, ["task_judge", "task_success"], use_llm=True)
    row = out["row"]
    assert row["task_communicated"] == pytest.approx(2 / 3) and row["task_assertions_met"] == 1
    assert row["task_components"] == 4 and row["task_success"] == 0  # one fact was not conveyed
    assert [f["conveyed"] for f in out["details"]["task_judge"]["facts"]] == [True, True, False]
    assert "f3" in prompts[0] and "a2" in prompts[0]
    # the cache key depends on the criteria
    from hani2.evaluation.base import EvalContext
    from hani2.evaluation.tasks import _judge_cache

    other = _rec(PTS, agreement="B", evaluation=dict(crit, communicate=["g"]))
    assert _judge_cache(EvalContext(rec), {}) != _judge_cache(EvalContext(other), {})
    # without facts or assertions the judge is not asked
    n = len(prompts)
    assert "task_communicated" not in evaluate_recording(_rec(PTS, agreement="B", evaluation=CRIT), ["task_judge"],
                                                         use_llm=True)["row"]
    assert len(prompts) == n


# --------------------------------------------------------------------------- #
# Combined scores                                                              #
# --------------------------------------------------------------------------- #
def test_scores_example():
    """The example of the scores reference."""
    out = score_row({"support_agent": "A", "human_advantage": 0.375, "ja_overall": 6, "assistant_critical_errors": 1})
    assert out["hi_outcome"] == pytest.approx(0.375)
    assert out["hi_assistant"] == pytest.approx((5 / 6 + 1 / 2) / 2, abs=1e-3)
    assert out["hi_assistant_coverage"] == pytest.approx(2 / 9.5)
    assert sum(c.weight for c in BY_NAME["hi_assistant"].components) == pytest.approx(9.5)
    # hi_interaction is the mean of the Assistant and team scores
    out = score_row({"support_agent": "A", "ja_overall": 7, "irrational_accept": 1})
    assert out["hi_assistant"] == 1 and out["hi_team"] == 0 and out["hi_interaction"] == pytest.approx(0.5)
    # no Assistant: no HI Assistant / team scores
    out = score_row({"support_agent": "none", "unanswered_messages": 0, "human_advantage": 0.5})
    assert out["hi_assistant"] is None and out["hi_team"] is None and out["hi_interaction"] is None
    # a failing opponent gets 0 for its outcome
    assert score_row({"opponent_advantage": 0.9, "opponent_failed": 1})["han_outcome"] == 0
    # weights from env.json and the options (0 drops a component)
    w = {"scores": {"hi_assistant": {"weights": {"assistant_critical_errors": 0}}}}
    out = score_row({"support_agent": "A", "ja_overall": 6, "assistant_critical_errors": 1}, w)
    assert out["hi_assistant"] == pytest.approx(5 / 6)


def test_scores_are_columns_of_every_evaluation():
    r = evaluate_recording(_rec(PTS, agreement="B"))["row"]
    assert r["han_outcome"] == pytest.approx((0.6 - 0.2) / 0.8) and r["hi_outcome"] == pytest.approx(0.5)
    r = evaluate_recording(_rec(PTS, agreement="B"), ["scores"])["row"]  # its requirements are added
    assert r["hi_outcome"] == pytest.approx(0.5) and "agreement" in r


# --------------------------------------------------------------------------- #
# Leaderboards                                                                 #
# --------------------------------------------------------------------------- #
def _row(agent, user, scenario, opponent, adv, **kw):
    return {**dict(support_agent=agent, support_model=None, user=user, scenario=scenario, opponent=opponent,
                   status="success", agreement=1, practice=0, human_advantage=adv), **kw}


def test_hi_leaderboard():
    rows = [
        _row("A", "u1", "s1", "o1", 0.2), _row("A", "u2", "s1", "o1", 0.4), _row("A", "u3", "s2", "o1", 1.0),
        _row("B", "u1", "s1", "o1", 0.1), _row("B", "u2", "s2", "o1", 0.3), _row("B", "u3", "s2", "o2", 0.5),
        _row("B", "u4", "s1", "o1", 0.9, practice=1),  # practice: left out
        _row("B", "u4", "s1", "o1", 0.0, status="agent_failed", agreement=0),  # opponent failure: not B's fault
        _row("A", "u5", "s1", "o1", None, status=None, agreement=None),  # abandoned
        dict(_row("none", "u1", "s1", "o1", 0.9)),  # HAN session: not in HI
    ]
    lb = leaderboard(rows, "hi", "outcome", n_boot=200)
    assert lb["excluded"] == {"practice": 1, "opponent failure": 1, "abandoned": 1}
    a, b = lb["entries"]
    assert a["entrant"] == "A" and a["rank"] == 1 and b["rank"] == 2
    # cell-balanced: A = mean(mean(0.2, 0.4), 1.0) = 0.65; B = mean(0.1, 0.3, 0.5) = 0.3
    assert a["scores"]["hi_outcome"]["mean"] == pytest.approx(0.65)
    assert b["scores"]["hi_outcome"]["mean"] == pytest.approx(0.3)
    assert a["n"] == 3 and a["cells"] == 2 and a["participants"] == 3 and b["cells"] == 3
    s = a["scores"]["hi_outcome"]
    assert s["ci_unit"] == "participant" and s["lo"] <= s["mean"] <= s["hi"]
    assert lb["success"] == "agreement" and a["pass_hat_k"] == {1: 1.0}
    # relative to the cell means: s1/o1 mean over all = (0.2+0.4+0.1)/3
    rel = leaderboard(rows, "hi", "outcome", relative=True, n_boot=0)
    ra = rel["entries"][0]["scores"]["hi_outcome"]
    assert ra["mean"] == pytest.approx(((0.2 + 0.4) / 2 - 0.7 / 3 + 1.0 - 0.65) / 2)


def test_leaderboards_use_the_same_components_for_everyone():
    rows = [_row("A", "u1", "s", "o", 0.5, ja_overall=7, irrational_accept=0),
            _row("A", "u2", "s", "o", 0.5, ja_overall=7, irrational_accept=0),
            _row("B", "u1", "s", "o", 0.5, irrational_accept=1),  # B was never judged
            _row("B", "u2", "s", "o", 0.5, irrational_accept=1)]
    lb = leaderboards(rows, "hi", n_boot=0)["interaction"]
    assert lb["components"]["hi_assistant"] == [] and "ja_overall" in lb["dropped_components"]["hi_assistant"]
    assert lb["components"]["hi_team"] == ["irrational_accept"]
    a = next(e for e in lb["entries"] if e["entrant"] == "A")
    assert a["scores"]["hi_interaction"]["mean"] == pytest.approx(1.0)  # only the team score, not A's ja_overall
    assert lb["entries"][0]["entrant"] == "A"


def test_han_leaderboard():
    def r(opp, user, adv, **kw):
        return {**dict(support_agent="none", user=user, scenario="s", opponent=opp, status="success", agreement=1,
                       opponent_advantage=adv), **kw}

    rows = [r("X", "u1", 0.8), r("X", "u2", 0.6), r("Y", "u1", 0.9), r("Y", "u2", 0.9, status="agent_failed", opponent_failed=1),
            r("Z", "u1", 0.5, status="erred"), dict(r("X", "u3", 0.1), support_agent="A")]
    lb = leaderboard(rows, "han", "outcome", n_boot=0)
    assert lb["excluded"] == {"system failure": 1}
    got = {e["entrant"]: e["scores"]["han_outcome"]["mean"] for e in lb["entries"]}
    # Y's failed session scores 0 (its own fault): (0.9 + 0) / 2
    assert got == {"X": pytest.approx(0.7), "Y": pytest.approx(0.45)}
    assert lb["success"] == "agreement" and lb["cells"] == ["scenario"]
    with pytest.raises(ValueError):
        leaderboard(rows, "nope")


# --------------------------------------------------------------------------- #
# End to end: the criteria stay hidden, are recorded and evaluated             #
# --------------------------------------------------------------------------- #
@pytest.fixture
def scenario_with_criteria(hani2_home, monkeypatch):
    from hani2.scenario_store import DEFAULT_SCENARIOS

    base = hani2_home / "pool"
    dst = base / "Acq" / "Acquisition"
    shutil.copytree(DEFAULT_SCENARIOS / "Acquisition", dst)
    info = yaml.safe_load((dst / "_info.yaml").read_text(encoding="utf-8"))
    info["evaluation"] = {"targets": {"agreement": 1}, "rules": ["irrational_accept"],
                          "communicate": ["SECRET-FACT Price is your most important issue"]}
    (dst / "_info.yaml").write_text(yaml.safe_dump(info, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("HANI2_SCENARIOS_BASE", str(base))
    return "Acq"


def _play(stype, assistant=True, user="tester"):
    from hani2.testing import make_session

    s = make_session(user=user, scenario_type=stype, n_steps=8, assistant_settings={"mode": "on" if assistant else "off"})
    assert "evaluation" not in (s.scenario.info or {})
    assert "SECRET-FACT" not in json.dumps(s.snapshot(), default=str)
    s.start()
    s.wait_for_turn()
    s.accept()
    s.wait_until_done()
    return s, s.recorder.finalize()


def test_criteria_are_hidden_recorded_and_evaluated(hani2_home, scenario_with_criteria):
    s, path = _play(scenario_with_criteria)
    rec = Recording.load(path)
    assert rec.scenario["evaluation"]["rules"] == ["irrational_accept"]
    row = evaluate_recording(rec)["row"]
    assert row["task_success"] in (0, 1) and row["task_components"] == 2
    assert row["hi_outcome"] is not None
    # the participant's copy of the scenario keeps the criteria
    copies = list((hani2_home).rglob("db/*/scenarios/*/_info.y*ml"))
    assert copies and all("evaluation" in yaml.safe_load(c.read_text(encoding="utf-8")) for c in copies)


def test_scenario_check_reads_the_criteria():
    from hani2.scenario_store import evaluation_warnings

    assert evaluation_warnings(CRIT) == []
    w = evaluation_warnings({"targets": {"x": ">= abc"}, "rules": ["nope"], "basis": ["dbhash"], "extra": 1})
    assert len(w) == 5 and any("nope" in x for x in w) and any("dbhash" in x for x in w)
    assert evaluation_warnings([1]) and evaluation_warnings({"targets": [1]})


def test_cli_and_api(hani2_home, scenario_with_criteria, tmp_path):
    from typer.testing import CliRunner

    from hani2.cli import app as cli
    from hani2.server import app

    _play(scenario_with_criteria, True, "u1")
    _play(scenario_with_criteria, False, "u2")
    res = evaluate_paths([hani2_home])
    assert len(res["rows"]) == 2 and not res["errors"]
    r = CliRunner().invoke(cli, ["replay", "leaderboard", str(hani2_home), "--track", "hi"])
    assert r.exit_code == 0, r.output
    assert "outcome board" in r.output and "interaction board" in r.output and "hi_outcome" in r.output
    out = tmp_path / "lb.json"
    r = CliRunner().invoke(cli, ["replay", "leaderboard", str(hani2_home), "-t", "han", "-b", "outcome", "-o", str(out)])
    assert r.exit_code == 0, r.output
    lb = json.loads(out.read_text(encoding="utf-8"))
    assert lb["track"] == "han" and len(lb["entries"]) == 1 and lb["entries"][0]["n"] == 1
    assert CliRunner().invoke(cli, ["replay", "leaderboard", "--track", "x"]).exit_code == 1
    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200
        keys = [x["key"] for x in c.get("/api/replay/recordings").json()["recordings"]]
        got = c.post("/api/replay/leaderboard", json={"keys": keys, "track": "hi"}).json()
        assert set(got["boards"]) == {"outcome", "interaction"}
        e = got["boards"]["outcome"]["entries"][0]
        assert e["n"] == 1 and e["rank"] == 1
        assert c.post("/api/replay/leaderboard", json={"keys": keys, "track": "x"}).status_code == 400
        assert c.post("/api/replay/leaderboard", json={"keys": []}).status_code == 400
    assert any(f.name.endswith(".hrec") for f in iter_recordings(hani2_home))


def test_targets_that_cannot_be_checked_never_pass():
    crit = {"targets": {"agreement": 1, "no_such_column": ">= 0.5"}, "rules": ["irrational_accept"]}
    # no deal: the agreement target fails, so the session fails although the other target cannot be checked
    r = evaluate_recording(_rec(PTS, agreement=None, evaluation=crit), ["task_success"])["row"]
    assert r["task_success"] == 0 and "task_targets_met" not in r
    # a deal: the unknown target leaves the result empty instead of passing
    r = evaluate_recording(_rec(PTS, agreement="B", evaluation=crit), ["task_success"])["row"]
    assert r["task_success"] is None
    from hani2.scenario_store import evaluation_warnings

    assert any("no_such_column" in w for w in evaluation_warnings(crit))
    assert evaluation_warnings({"targets": {"scale_satisfaction_norm": ">= 0.5", "human_advantage": ">= 0"}}) == []


def test_board_weight_share_and_warnings():
    rows = [_row("A", "u1", "s", "o", 0.5, irrational_accept=0), _row("B", "u2", "s", "o", 0.5, irrational_accept=0)]
    lb = leaderboard(rows, "hi", "interaction", n_boot=0)
    # only irrational_accept (weight 1 of 6) of hi_team is measured, nothing of hi_assistant
    assert lb["weight_share"]["hi_team"] == pytest.approx(1 / 6)
    assert lb["weight_share"]["hi_assistant"] == 0
    assert lb["weight_share"]["hi_interaction"] == pytest.approx((1 / 6) / 2)
    assert any("of its weight" in w for w in lb["warnings"]) and any("same hi_interaction" in w for w in lb["warnings"])
    assert leaderboard(rows, "hi", "outcome", n_boot=0)["weight_share"]["hi_outcome"] == 1


def test_judged_scores_end_to_end(hani2_home, monkeypatch):
    """File-backed recordings, a stubbed judge (cached on the second run) and the HI interaction board."""
    from hani2.evaluation import llm_judge

    calls = []

    def fake(prompt, s):
        calls.append(prompt)
        if "Grade each expected outcome" in prompt:
            return json.dumps({"results": [{"met": True}] * 10})
        if "List the ERRORS" in prompt:
            return json.dumps({"errors": [], "overrides_helped": 0, "overrides_hurt": 0})
        return json.dumps({**{c: 6 for c in llm_judge.ASSISTANT_CRITERIA}, "overall": 6, "justification": "ok"})

    monkeypatch.setattr(llm_judge, "CALL", fake)
    folder = hani2_home / "recs"
    folder.mkdir(parents=True)
    chat = [{"t": 5, "k": "chat", "user": "Assistant", "text": "Take B."}]
    acts = [{"t": 6, "k": "act", "actor": "human", "type": "offer", "offer": ["B"]}]
    from hani2.recording.format import dumps_line

    for i, agent in enumerate(("A", "A", "B", "B")):
        recs = _records(PTS, agreement="B", ended_by="agent", extra=chat + acts, header={"id": f"r{i}", "session": {"user": f"u{i}"}},
                        start={"support_agent": {"enabled": True, "name": agent}})
        (folder / f"r{i}.hrec").write_text("".join(dumps_line(r) + "\n" for r in recs), encoding="utf-8")
    first = evaluate_paths([folder], use_llm=True)
    assert not first["errors"], first["errors"]
    n = len(calls)
    assert n > 0 and all(r["ja_overall"] == 6 for r in first["rows"])
    second = evaluate_paths([folder], use_llm=True)
    assert len(calls) == n  # every judgement came from the .eval.json cache
    lb = leaderboards(second["rows"], "hi", n_boot=0)["interaction"]
    assert "ja_overall" in lb["components"]["hi_assistant"] and lb["weight_share"]["hi_assistant"] > 0.3
    a = lb["entries"][0]["scores"]["hi_assistant"]["mean"]
    assert a is not None and 0 < a <= 1


def test_simulated_sessions_are_not_ranked_with_humans():
    rows = [dict(key=f"k{i}", user=f"u{i}", scenario="s", opponent="o", support_agent="A", status="success",
                 agreement=1, human_advantage=0.5, mode="simulated" if i % 2 else "normal") for i in range(6)]
    lb = leaderboard(rows, "hi", "outcome", n_boot=0)
    assert lb["sessions"] == 3 and lb["excluded"] == {"simulated participant": 3}
    assert leaderboard(rows, "hi", "outcome", n_boot=0, include_simulated=True)["sessions"] == 6


def test_pass_hat_k_is_per_scenario_and_opponent():
    from hani2.evaluation import compare_rows

    rows = [dict(group="g", scenario="s", opponent="A", agreement=1.0) for _ in range(4)]
    rows += [dict(group="g", scenario="s", opponent="B", agreement=0.0) for _ in range(4)]
    rel = {r["k"]: r["pass_hat_k"] for r in compare_rows(rows, by="group", max_k=4)["reliability"]}
    assert rel[4] == pytest.approx(0.5)
