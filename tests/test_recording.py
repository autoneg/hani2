"""Recording, replay reconstruction and evaluation."""

import json
import random
import time

import pytest
from conftest import write_settings
from fastapi.testclient import TestClient

from hani2.recording.format import Recording, diff, iter_recordings, patch


# --------------------------------------------------------------------------- #
# Format                                                                       #
# --------------------------------------------------------------------------- #
def _rand(depth=0):
    r = random.random()
    if depth > 2 or r < 0.3:
        return random.choice([1, 2.5, "a", "b", None, True, [1, 2], []])
    if r < 0.6:
        return [_rand(depth + 1) for _ in range(random.randint(0, 3))]
    return {random.choice("abcdef"): _rand(depth + 1) for _ in range(random.randint(0, 4))}


def test_diff_patch_roundtrip():
    random.seed(3)
    for _ in range(500):
        a = {k: _rand() for k in "xyz" if random.random() < 0.8}
        b = {k: _rand() for k in "xyzw" if random.random() < 0.8}
        if random.random() < 0.3 and isinstance(a.get("x"), list):
            b["x"] = a["x"] + [1, 2]
        assert patch(a, diff(a, b)) == b
        assert diff(a, a) is None


def test_truncated_file_still_loads(tmp_path):
    p = tmp_path / "x.hrec.jsonl"
    p.write_text(json.dumps({"k": "header", "format": "hani2-recording", "version": 1, "id": "x", "t0": 0}) + "\n"
                 + json.dumps({"t": 1, "k": "ev", "type": "a"}) + "\n" + '{"t": 2, "k": "e')
    r = Recording.load(p)
    assert r.id == "x" and len(r.events) == 1 and not r.complete


# --------------------------------------------------------------------------- #
# Through the real server                                                      #
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(hani2_home, monkeypatch):
    monkeypatch.setenv("HANI2_OPPONENTS", "BoulwareTBNegotiator")
    monkeypatch.setenv("HANI2_SUPPORT_AGENT", "off")
    from hani2.server import app, hub

    hub.sessions.clear()
    with TestClient(app) as c:
        yield c


def login(c, u="admin", p="adminpass"):
    assert c.post("/api/auth/login", json={"username": u, "password": p}).status_code == 200


def recv_until(ws, pred, got, n=600):
    for _ in range(n):
        m = json.loads(ws.receive_text())
        got.append(m)
        if pred(m):
            return m
    raise AssertionError("message never arrived")


def _play_round(client):
    login(client)
    sid = client.post("/api/session", json={"mode": "main", "query": {}}).json()["sid"]
    got: list[dict] = []
    with client.websocket_connect(f"/api/ws/{sid}") as ws:
        st = recv_until(ws, lambda m: m["type"] == "state", got)["state"]
        ws.send_text(json.dumps({"type": "telemetry", "sent": int(time.time() * 1000),
                                 "events": [[int(time.time() * 1000), "vp", 1280, 800, 2, "desktop", True, "light"],
                                            [int(time.time() * 1000), "mm", 10, 20],
                                            [int(time.time() * 1000), "click", 10, 20, 0, {"sel": "#start"}]]}))
        ws.send_text(json.dumps({"type": "start"}))
        recv_until(ws, lambda m: m["type"] == "state" and m["state"]["negotiation"]["is_my_turn"]
                   and not m["state"]["negotiation"]["thinking"], got)
        issue = st["scenario"]["issues"][0]
        value = issue["values"][-1] if issue.get("values") else issue["max"]
        ws.send_text(json.dumps({"type": "draft", "values": {issue["name"]: value}}))
        recv_until(ws, lambda m: m["type"] == "draft", got)
        ws.send_text(json.dumps({"type": "send", "text": "hello"}))
        recv_until(ws, lambda m: m["type"] == "state" and m["state"]["negotiation"]["is_my_turn"]
                   and not m["state"]["negotiation"]["thinking"] and len(m["state"]["history"]) >= 3, got)
        ws.send_text(json.dumps({"type": "end"}))
        recv_until(ws, lambda m: m["type"] == "state" and m["state"]["phase"] in ("ended", "questionnaire"), got)
        time.sleep(0.2)
    from hani2.server import hub

    hub.remove(sid)  # closes the session → finalises the recording
    return sid, got


def test_recording_reconstructs_every_screen(client, hani2_home):
    sid, got = _play_round(client)
    files = [f for f in iter_recordings(hani2_home) if f.name.endswith(".hrec")]
    assert files, "no recording written"
    rec = Recording.load(files[0])
    assert rec.complete
    kinds = {e["k"] for e in rec.events}
    assert {"scenario", "start", "act", "in", "tel", "out", "trace", "result", "draft"} <= kinds
    # every state the browser received is reconstructed exactly from the file
    states = {seq: st for _, seq, st in rec.states()}
    sent = [m for m in got if m["type"] == "state" and "_seq" in m]
    assert sent
    for m in sent:
        if m["_seq"] in states:
            assert states[m["_seq"]] == json.loads(json.dumps(m["state"])), m["_seq"]
    # most of them are in this recording (the very first one may precede it)
    assert sum(1 for m in sent if m["_seq"] in states) >= len(sent) - 2
    acts = rec.of("act")
    assert acts[0]["actor"] == "human" and acts[0]["type"] == "offer" and acts[0]["text"] == "hello"
    assert acts[-1]["type"] == "end"
    assert [e for e in rec.of("draft") if e["by"] == "human"]
    tel = rec.telemetry()
    assert [t for t in tel if t[1] == "click"] and [t for t in tel if t[1] == "vp"]
    assert rec.summary["status"] == "broken" and rec.summary["ended_by"] == "human"


def test_replay_api(client, hani2_home):
    _play_round(client)
    lst = client.get("/api/replay/recordings").json()["recordings"]
    assert len(lst) == 1 and lst[0]["status"] == "broken"
    key = lst[0]["key"]
    data = client.get("/api/replay/recording", params={"key": key}).json()
    assert data["header"]["format"] == "hani2-recording" and data["events"]
    ev = client.post("/api/replay/evaluate", json={"keys": [key]}).json()
    row = ev["rows"][0]
    assert row["agreement"] == 0 and row["n_human_offers"] >= 1 and row["has_telemetry"] == 1
    assert any(c["name"] == "pareto_distance" for c in ev["columns"])
    cmp = client.post("/api/replay/compare", json={"keys": [key], "by": "opponent"}).json()
    assert cmp["groups"][0]["n"] == 1
    metrics = client.get("/api/replay/metrics").json()["metrics"]
    assert {"hard", "soft", "subjective"} <= {m["kind"] for m in metrics}
    # keys never escape their folder
    for bad in ("0:../../etc/passwd", "0:/etc/passwd", "9:x", "nonsense"):
        assert client.get("/api/replay/recording", params={"key": bad}).status_code == 404
    # upload a copy
    raw = client.get("/api/replay/download", params={"key": key}).content
    up = client.post("/api/replay/upload", params={"name": "copy.hrec"}, content=raw)
    assert up.status_code == 200
    assert client.post("/api/replay/upload", params={"name": "x.hrec"}, content=b"junk").status_code == 400
    # admin only
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"username": "bob", "password": "secret", "confirm": "secret", "consent": True})
    assert client.get("/api/replay/recordings").status_code == 403
    assert client.get("/api/replay/recording", params={"key": key}).status_code == 403


# --------------------------------------------------------------------------- #
# Headless: attribution, LLM calls, questionnaire                              #
# --------------------------------------------------------------------------- #
def _headless(**kw):
    from hani2.testing import make_session

    return make_session(partner="BoulwareTBNegotiator", n_steps=12, **kw)


def test_actor_attribution_and_llm_calls():
    from hani2.recording import recorder as rec

    s = _headless()
    s.start()
    s.wait_for_turn()
    with rec.acting("agent"):
        s.set_draft({s.issues[0].name: list(s.issues[0].all)[0]}, by_agent=True)  # assistant suggestion
    s.ss["actions"]["set_offer"]({s.issues[0].name: list(s.issues[0].all)[-1]})  # the human using a tool

    class _U:
        prompt_tokens, completion_tokens, total_tokens = 10, 5, 15

    class _Resp:
        usage = _U()

        class choices:  # noqa: N801
            pass

    msg = type("M", (), {"content": "hi", "tool_calls": None})()
    _Resp.choices = [type("C", (), {"message": msg})()]
    with rec.bind(s.sid, "support"):
        rec.record_llm_call({"model": "m", "messages": [{"role": "user", "content": "a"}]}, _Resp(), 0.5)
        rec.record_llm_call({"model": "m", "messages": [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]}, _Resp(), 0.5)
    with rec.acting("agent"):
        s.send_counter()
    s.wait_for_turn()
    s.end()
    s.wait_until_done()
    path = s.recorder.finalize()
    r = Recording.load(path)
    acts = r.of("act")
    assert acts[0]["actor"] == "agent" and acts[-1]["actor"] == "human"
    drafts = r.of("draft")
    assert drafts[0]["by"] == "agent" and drafts[1]["by"] == "human" and drafts[1]["via"] == "tool"
    calls = r.of("llm")
    assert len(calls) == 2 and calls[1]["prefix"] == 1 and calls[1]["usage"]["total_tokens"] == 15

    from hani2.evaluation import evaluate_recording

    row = evaluate_recording(r, ["llm_usage", "system_use"])["row"]
    assert row["llm_calls"] == 2 and row["llm_tokens"] == 30 and row["support_llm_calls"] == 2
    assert row["actions_by_agent"] == 0.5 and row["n_suggestions"] == 1


def test_questionnaire_scales(hani2_home, monkeypatch):
    monkeypatch.setenv("HANI2_PER_NEG_YAML", "evaluation")
    from hani2 import study

    s = _headless()
    spec = study.questionnaire_spec()
    assert spec and any(q.get("scale") == "ueq_pragmatic" for q in spec["questions"])
    shown = study.questionnaire_for(s, spec)
    assert any(q.get("requires") == "support_agent" for q in shown["questions"])  # the test session has one
    s.support_agent.user_enabled = False
    assert not any(q.get("requires") == "support_agent" for q in study.questionnaire_for(s, spec)["questions"])
    s.support_agent.user_enabled = True
    s.start()
    s.play_counters(1)
    s.wait_for_turn()
    s.end()
    s.wait_until_done()
    assert s.phase == "questionnaire"
    answers = {q["id"]: 7 for q in s.questionnaire["questions"] if q["type"].startswith("likert")}
    assert s.study.submit_questionnaire(answers)["ok"]
    r = Recording.load(s.recorder.finalize())
    from hani2.evaluation import evaluate_recording

    row = evaluate_recording(r, ["questionnaire"])["row"]
    # "clear–confusing" is reverse-scored: 7 → 1, the five others 7 → mean (5*7+1)/6
    assert row["scale_ueq_pragmatic"] == pytest.approx((5 * 7 + 1) / 6)
    assert row["scale_ueq_hedonic"] == pytest.approx(1.0)  # valuable–inferior and good–bad are reversed: 7 → 1
    assert row["scale_tam_usefulness"] == 7 and row["questionnaire_answered"] == 1


def test_optimality_on_known_scenario():
    from hani2.evaluation import evaluate_recording

    outcomes = [[0], [1], [2], [3]]
    U = [[1.0, 0.7, 0.4, 0.0], [0.0, 0.6, 0.8, 1.0]]  # human, opponent
    recs = [
        {"k": "header", "format": "hani2-recording", "version": 1, "id": "s", "t0": 0},
        {"t": 0, "k": "scenario", "name": "toy", "human_index": 0, "outcomes": outcomes, "utilities": U,
         "reserved": [0.0, 0.0], "issue_names": ["x"]},
        {"t": 1, "k": "start", "human_index": 0, "human_id": "H"},
        {"t": 2, "k": "trace", "rows": [{"t": 0.1, "negotiator": "O", "offer": [3]},
                                         {"t": 0.2, "negotiator": "H", "offer": [0]},
                                         {"t": 0.3, "negotiator": "O", "offer": [2]},
                                         {"t": 0.4, "negotiator": "H", "offer": [1]}]},
        {"t": 3, "k": "result", "summary": {"status": "success"}, "row": {}, "agreement": [1]},
    ]
    row = evaluate_recording(Recording.from_records(recs), ["outcome", "optimality", "dynamics"])["row"]
    assert row["agreement"] == 1 and row["human_utility"] == 0.7 and row["opponent_utility"] == 0.6
    assert row["pareto_optimal"] == 1 and row["nash_distance"] == pytest.approx(0.0)  # 0.7*0.6 is the largest product
    assert row["welfare_optimality"] == pytest.approx(1.3 / 1.3)
    assert row["human_move_concession"] == 1.0 and row["opponent_move_concession"] == 1.0


def test_llm_judge_is_cached(monkeypatch):
    from hani2.evaluation import evaluate_recording, llm_judge

    s = _headless()
    s.start()
    s.wait_for_turn()
    s.add_chat("Assistant", "I can suggest offers.")
    s.end()
    s.wait_until_done()
    r = Recording.load(s.recorder.finalize())
    calls = []

    def fake(prompt, settings):
        calls.append(prompt)
        return '```json\n{"results": [{"met": true}, {"met": null}], "helpfulness": 6, "overall": 5, "justification": "x"}\n```'

    monkeypatch.setattr(llm_judge, "CALL", fake)
    out = evaluate_recording(r, ["nl_assertions", "judge_assistant"], use_llm=True,
                             options={"assertions": ["It explained itself.", "It asked about goals."]})
    assert out["row"]["assertions_met"] == 1.0 and out["row"]["assertions_total"] == 1
    assert out["row"]["ja_helpfulness"] == 6 and "I can suggest offers." in calls[0]
    n = len(calls)
    evaluate_recording(r, ["nl_assertions", "judge_assistant"], use_llm=True,
                       options={"assertions": ["It explained itself.", "It asked about goals."]})
    assert len(calls) == n  # cached
    assert not evaluate_recording(r, ["nl_assertions"])["row"].get("assertions_met")  # LLM metrics need use_llm


def test_pass_hat_k_and_compare():
    from hani2.evaluation import compare_rows, pass_hat_k

    assert pass_hat_k(4, 2, 1) == 0.5 and pass_hat_k(4, 2, 2) == pytest.approx(1 / 6)
    rows = [dict(opponent="A", scenario="s1", agreement=1, human_utility=0.5),
            dict(opponent="A", scenario="s1", agreement=0, human_utility=0.1),
            dict(opponent="B", scenario="s1", agreement=1, human_utility=0.9)]
    out = compare_rows(rows, by="opponent")
    a = next(g for g in out["groups"] if g["group"] == "A")
    assert a["n"] == 2 and a["mean"]["human_utility"] == pytest.approx(0.3)
    assert {(r["group"], r["k"]): r["pass_hat_k"] for r in out["reliability"]}[("A", 2)] == 0.0


def test_recording_can_be_disabled(monkeypatch, hani2_home):
    monkeypatch.setenv("HANI2_RECORD", "0")
    s = _headless()
    assert s.recorder is None
    write_settings(hani2_home, "env.json", {"recording": {"enabled": False}})
    monkeypatch.setenv("HANI2_RECORD", "1")
    assert _headless().recorder is None


def test_cli_evaluate(hani2_home, tmp_path):
    from typer.testing import CliRunner

    from hani2.cli import app

    s = _headless()
    s.start()
    s.wait_for_turn()
    s.end()
    s.wait_until_done()
    s.recorder.finalize()
    out = tmp_path / "m.csv"
    res = CliRunner().invoke(app, ["replay", "evaluate", str(hani2_home), "-m", "outcome,length", "--out", str(out)])
    assert res.exit_code == 0, res.output
    text = out.read_text()
    assert "human_utility" in text and "n_offers" in text
    res = CliRunner().invoke(app, ["replay", "compare", str(hani2_home), "--by", "scenario"])
    assert res.exit_code == 0 and "pass^k" in res.output


def test_support_agent_round_over_websocket(hani2_home, monkeypatch, scripted):
    """The assistant chats, fills in an offer (a function call) and the human sends it."""
    monkeypatch.setenv("HANI2_OPPONENTS", "BoulwareTBNegotiator")
    monkeypatch.setenv("HANI2_SUPPORT_AGENT", "on")
    from hani2.server import app, hub

    hub.sessions.clear()
    with TestClient(app) as client:
        login(client)
        sid = client.post("/api/session", json={"mode": "main", "query": {}}).json()["sid"]
        got: list[dict] = []
        with client.websocket_connect(f"/api/ws/{sid}") as ws:
            st = recv_until(ws, lambda m: m["type"] == "state", got)["state"]
            assert st["support"] is not None
            ws.send_text(json.dumps({"type": "start"}))
            recv_until(ws, lambda m: m["type"] == "state" and m["state"]["negotiation"]["is_my_turn"]
                       and not m["state"]["negotiation"]["thinking"], got)
            issue = st["scenario"]["issues"][0]
            value = issue["values"][-1] if issue.get("values") else issue["max"]
            time.sleep(0.5)  # let the assistant react to the start of the negotiation first
            scripted(("set_offer", {"outcome": {issue["name"]: value}}), "Try this offer.")
            ws.send_text(json.dumps({"type": "chat", "text": "what should I offer?"}))
            recv_until(ws, lambda m: m["type"] == "chat" and m["message"]["text"] == "Try this offer.", got)
            ws.send_text(json.dumps({"type": "send"}))
            recv_until(ws, lambda m: m["type"] == "state" and len(m["state"]["history"]) >= 3, got)
            ws.send_text(json.dumps({"type": "end"}))
            recv_until(ws, lambda m: m["type"] == "state" and m["state"]["phase"] in ("ended", "questionnaire"), got)
            time.sleep(0.3)
        hub.remove(sid)
    rec = Recording.load(next(f for f in iter_recordings(hani2_home) if f.name.endswith(".hrec")))
    assert any(c["text"] == "what should I offer?" for c in rec.of("chat"))
    assert any(f["name"] == "set_offer" and f["result"].get("ok") for f in rec.of("fn"))
    sugg = [d for d in rec.of("draft") if d["by"] == "agent"]
    assert sugg and sugg[-1]["values"][issue["name"]] == value
    sent = [a for a in rec.of("act") if a["type"] == "offer"]
    assert sent[0]["actor"] == "human" and sent[0]["values"][issue["name"]] == value
    states = {seq: st for _, seq, st in rec.states()}
    for m in got:
        if m["type"] == "state" and m.get("_seq") in states:
            assert states[m["_seq"]] == json.loads(json.dumps(m["state"]))
    from hani2.evaluation import evaluate_recording

    row = evaluate_recording(rec, ["system_use", "assistant_interaction"])["row"]
    assert row["n_suggestions"] >= 1 and row["suggestion_adoption"] == 1.0 and row["fn_success_rate"] == 1.0
    assert row["n_user_messages"] == 1 and row["assistant_response_seconds"] is not None


def test_llm_calls_through_the_litellm_wrapper():
    import litellm

    from hani2 import llm_logging
    from hani2.recording import recorder as rec

    s = _headless()
    assert llm_logging._installed
    with rec.bind(s.sid, "opponent"):
        litellm.completion(model="openai/gpt-4o-mini", messages=[{"role": "user", "content": "hi"}],
                           mock_response="hello there")
    r = Recording.load(s.recorder.finalize())
    call = r.of("llm")[-1]
    assert call["role"] == "opponent" and call["response"]["content"] == "hello there"
    assert call["usage"].get("total_tokens")
