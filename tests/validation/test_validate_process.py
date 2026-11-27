"""Hand-worked validation of the process metrics: length, timing, activity, llm_usage, dynamics.

Every expected value is derived by hand from the metric's written definition (see the comments)."""

import math

import pytest

from hani2.evaluation import evaluate_recording
from hani2.recording.format import Recording


def _ev(rec_events, metrics):
    out = evaluate_recording(Recording.from_records(rec_events), metrics)
    assert not out["errors"], out["errors"]
    return out["row"]


def _hdr():
    return {"k": "header", "format": "hani2-recording", "version": 1, "id": "v", "t0": 0}


def _scenario(outcomes, utils, names=("x",), human_index=0):
    return {"t": 0, "k": "scenario", "name": "toy", "human_index": human_index, "outcomes": outcomes,
            "utilities": utils, "reserved": [0.0, 0.0], "issue_names": list(names)}


def _tel(T, items, sent=1_000_000):
    """One telemetry batch received at T; items are (absolute time, type, *payload)."""
    return {"t": T, "k": "tel", "sent": sent,
            "ev": [[sent + int(round((t - T) * 1000)), typ, *p] for t, typ, *p in items]}


def _state(t, seq, *, mine, thinking=False, phase="running"):
    return {"t": t, "k": "out", "m": "state", "seq": seq,
            "full": {"phase": phase, "negotiation": {"is_my_turn": mine, "thinking": thinking}}}


def _act(t, typ, actor="human", **kw):
    return {"t": t, "k": "act", "type": typ, "actor": actor, **kw}


# =========================================================================== #
# length                                                                       #
# =========================================================================== #
def _length_recs(result_row):
    return [
        _hdr(),
        {"t": 2, "k": "start", "human_index": 0, "human_id": "H"},
        {"t": 10, "k": "trace", "rows": [
            {"t": 3, "negotiator": "O", "offer": [3], "step": 1, "rel": 0.1, "text": "hi"},
            {"t": 4, "negotiator": "H", "offer": [0], "step": 2, "rel": 0.2},
            {"t": 5, "negotiator": "O", "offer": [2], "step": 3, "rel": 0.3, "text": ""},
            {"t": 6, "negotiator": "H", "offer": None, "step": 4, "rel": 0.4, "text": "how about"},
            {"t": 7, "negotiator": "H", "offer": [1], "step": 5, "rel": 0.5, "text": "ok"},
            {"t": 8, "negotiator": "O", "offer": [2], "step": 6, "rel": 0.6},
        ]},
        {"t": 11.5, "k": "result", "summary": {}, "row": result_row, "agreement": [1]},
        {"t": 20, "k": "end"},
    ]


def test_length_trace_without_result_fields():
    # Offers (rows with an offer): O@1,3,6 = 3 opponent; H@2,5 = 2 human (row 4 is text only, no offer) -> 5.
    # Texts: rows 1 ("hi"), 4 ("how about"), 5 ("ok"); "" and missing do not count -> 3.
    # Result row empty -> steps and relative time come from the last trace row: 6 and 0.6.
    # Negotiation 2 -> 11.5 = 9.5 s; the recording's last event is at 20.
    expected = {"n_offers": 5, "n_human_offers": 2, "n_opponent_offers": 3, "n_steps": 6, "relative_time": 0.6,
                "negotiation_seconds": 9.5, "session_seconds": 20.0, "n_text_messages": 3}
    row = _ev(_length_recs({}), ["length"])
    for k, v in expected.items():
        assert row[k] == pytest.approx(v), k


def test_length_result_row_wins():
    # The result's own step (7) and relative_time (0.75) take precedence over the last trace row.
    expected = {"n_steps": 7, "relative_time": 0.75, "n_offers": 5, "negotiation_seconds": 9.5}
    row = _ev(_length_recs({"step": 7, "relative_time": 0.75}), ["length"])
    for k, v in expected.items():
        assert row[k] == pytest.approx(v), k


def test_length_abandoned_session_without_trace():
    # No trace: human seat offers are the offer acts (two by the human, one by the assistant = 3 human-team);
    # opponent offers are the history items seen on screen, each id once (id 1 appears in two states -> 1; id 2 -> 2).
    # No result -> no negotiation seconds, steps or relative time; no trace rows -> 0 text messages.
    # The recording lasts until its last event, t = 30.
    recs = [
        _hdr(), _scenario([[0], [1], [2], [3]], [[0] * 4, [0] * 4]),
        {"t": 1, "k": "start", "human_index": 0, "human_id": "H"},
        _act(5, "offer", offer=[0]), _act(9, "offer", offer=[1]), _act(12, "offer", actor="agent", offer=[2]),
        {"t": 6, "k": "out", "m": "state", "seq": 1,
         "full": {"history": [{"kind": "offer", "by": "agent", "id": 1, "offer": {"x": 3}}]}},
        {"t": 13, "k": "out", "m": "state", "seq": 2,
         "full": {"history": [{"kind": "offer", "by": "agent", "id": 1, "offer": {"x": 3}},
                              {"kind": "offer", "by": "agent", "id": 2, "offer": {"x": 2}},
                              {"kind": "chat", "by": "agent", "id": 3}]}},
        {"t": 30, "k": "end"},
    ]
    row = _ev(recs, ["length"])
    expected = {"n_offers": 5, "n_human_offers": 3, "n_opponent_offers": 2, "n_steps": None, "relative_time": None,
                "negotiation_seconds": None, "session_seconds": 30.0, "n_text_messages": 0}
    for k, v in expected.items():
        if v is None:
            assert row.get(k) is None, k
        else:
            assert row[k] == pytest.approx(v), k


# =========================================================================== #
# llm_usage                                                                    #
# =========================================================================== #
def _llm(role, model, usage, cost, latency, error=None):
    return {"t": 5, "k": "llm", "role": role, "model": model, "usage": usage, "cost": cost, "latency": latency,
            "error": error}


def test_llm_usage_mixed_roles():
    recs = [_hdr(), {"t": 1, "k": "start", "human_index": 0},
            # total_tokens (100) wins over prompt + completion (60 + 30 = 90)
            _llm("support", "m1", {"prompt_tokens": 60, "completion_tokens": 30, "total_tokens": 100}, 0.01, 1.0),
            # no total -> prompt + completion = 30 + 20 = 50
            _llm("support", "m1", {"prompt_tokens": 30, "completion_tokens": 20}, 0.02, 3.0),
            _llm("autopilot", "m1", {"total_tokens": 10}, None, 2.0),
            _llm("opponent", "m2", {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300}, 0.05, 4.0),
            # a failed call: no usage, no cost, no latency
            _llm("opponent", "m2", {}, None, None, error="boom"),
            _llm("judge", "m3", {"total_tokens": 7}, 0.005, 1.5),
            {"t": 9, "k": "end"}]
    # calls = 6.  tokens = 100 + 50 + 10 + 300 + 0 + 7 = 467.  cost = .01 + .02 + .05 + .005 = .085 (known only).
    # latency mean over the 5 known = (1 + 3 + 2 + 4 + 1.5) / 5 = 2.3.  error rate = 1 / 6.
    # Assistant = support + autopilot: 3 calls, 100 + 50 + 10 = 160 tokens.  Opponent: 2 calls, 300 tokens.
    expected = {"llm_calls": 6, "llm_tokens": 467, "llm_cost_usd": 0.085, "llm_latency_mean": 2.3,
                "llm_error_rate": 1 / 6, "support_llm_calls": 3, "support_tokens": 160,
                "opponent_llm_calls": 2, "opponent_tokens": 300}
    out = evaluate_recording(Recording.from_records(recs), ["llm_usage"])
    assert not out["errors"]
    for k, v in expected.items():
        assert out["row"][k] == pytest.approx(v), k


def test_llm_usage_no_calls():
    # No calls: counts and tokens are 0; cost, latency and error rate are undefined (empty).
    expected = {"llm_calls": 0, "llm_tokens": 0, "llm_cost_usd": None, "llm_latency_mean": None,
                "llm_error_rate": None, "support_llm_calls": 0, "support_tokens": 0,
                "opponent_llm_calls": 0, "opponent_tokens": 0}
    row = _ev([_hdr(), {"t": 1, "k": "end"}], ["llm_usage"])
    for k, v in expected.items():
        if v is None:
            assert row.get(k) is None, k
        else:
            assert row[k] == v, k


# =========================================================================== #
# timing                                                                       #
# =========================================================================== #
def test_timing_screen_states():
    # Screen turn starts: state at 5 (not mine), 10 (mine -> start), 16 (thinking -> not mine),
    # 30 (mine -> start), 45 (questionnaire phase -> not mine).  Starts S = {10, 30}.
    # Decisions by the human: text@12 -> 2; offer@14.5 -> 4.5; accept@37 -> 7; end@40 -> 10.
    # Ignored: the human's non-decision act (draft@13) and the assistant's offer@31.
    # mean = 23.5 / 4 = 5.875; median = (4.5 + 7) / 2 = 5.75; min = 2.
    # Negotiation starts at 4 -> load_to_start = 4; first action at 12 -> time_to_first_action = 8.
    # Questionnaire shown at 45, submitted at 60 -> 15 s.
    recs = [_hdr(), {"t": 4, "k": "start", "human_index": 0, "human_id": "H"},
            _state(5, 1, mine=False), _state(10, 2, mine=True),
            _act(12, "text"), _act(13, "draft"), _act(14.5, "offer"),
            _state(16, 3, mine=True, thinking=True), _state(30, 4, mine=True),
            _act(31, "offer", actor="agent"), _act(37, "accept"), _act(40, "end"),
            _state(45, 5, mine=False, phase="questionnaire"),
            {"t": 60, "k": "questionnaire", "answers": {}}]
    expected = {"decision_time_mean": 5.875, "decision_time_median": 5.75, "decision_time_min": 2.0,
                "time_to_first_action": 8.0, "load_to_start_seconds": 4.0, "questionnaire_seconds": 15.0}
    row = _ev(recs, ["timing"])
    for k, v in expected.items():
        assert row[k] == pytest.approx(v), k


def test_timing_turn_events():
    # No browser: each human action pairs with the last turn event before it.
    # turn@10: text@12 -> 2, offer@14.5 -> 4.5; turn@30: accept@37 -> 7 (assistant's offer@31 ignored).
    # mean = 13.5 / 3 = 4.5; median = 4.5; min = 2.  start@4: first action 12 -> 8; load = 4.
    # No states -> no questionnaire time.
    recs = [_hdr(), {"t": 4, "k": "start", "human_index": 0, "human_id": "H"},
            {"t": 10, "k": "turn"}, _act(12, "text"), _act(14.5, "offer"),
            {"t": 30, "k": "turn"}, _act(31, "offer", actor="agent"), _act(37, "accept"),
            {"t": 50, "k": "questionnaire", "answers": {}}]
    expected = {"decision_time_mean": 4.5, "decision_time_median": 4.5, "decision_time_min": 2.0,
                "time_to_first_action": 8.0, "load_to_start_seconds": 4.0, "questionnaire_seconds": None}
    row = _ev(recs, ["timing"])
    for k, v in expected.items():
        if v is None:
            assert row.get(k) is None, k
        else:
            assert row[k] == pytest.approx(v), k


def test_timing_legacy_recording():
    # Neither screen states nor turn events: a turn starts with the negotiation (4) or the human's previous
    # non-text move.  Human acts: text@7 -> 7-4 = 3; offer@10 -> 6; text@20 -> 20-10 = 10 (the text@7 does
    # not end a turn); accept@25 -> 25-10 = 15.  mean = 34/4 = 8.5; median = (6+10)/2 = 8; min = 3.
    # First action at 7 -> 3.  Load to start = 4.
    recs = [_hdr(), {"t": 4, "k": "start", "human_index": 0, "human_id": "H"},
            _act(7, "text"), _act(10, "offer"), _act(20, "text"), _act(25, "accept")]
    expected = {"decision_time_mean": 8.5, "decision_time_median": 8.0, "decision_time_min": 3.0,
                "time_to_first_action": 3.0, "load_to_start_seconds": 4.0, "questionnaire_seconds": None}
    row = _ev(recs, ["timing"])
    for k, v in expected.items():
        if v is None:
            assert row.get(k) is None, k
        else:
            assert row[k] == pytest.approx(v), k


# =========================================================================== #
# activity                                                                     #
# =========================================================================== #
def test_activity_documented_example():
    # Doc example: negotiation 0 -> 60 s, inputs at 2, 3, 20, 24, 58 s; gaps 2,1,17,4,34,2;
    # gaps > 5 s: 17 + 34 = 51 -> idle_fraction = 51 / 60 = 0.85.
    # Clicks: two (both at 3 s).  Keys: two (both at 20 s).  Scrolls: one (24 s).  Blur: two (not inputs).
    # Pointer path: (0,0)@2 -> (3,4)@3 [5] -> (3,4) second click [0] -> (6,8)@58 [5] -> pu (12,16)@59 [10] = 20.
    # Hidden: 30 -> 41.5 = 11.5 and 50 -> 52 = 2 (a repeated hidden while hidden is ignored) = 13.5.
    items = [(2, "mm", 0, 0), (3, "click", 3, 4), (3, "click", 3, 4), (10, "blur"), (11, "blur"),
             (20, "key", "a"), (20, "key", "b"), (24, "scroll", 0, 120),
             (30, "vis", "hidden"), (35, "vis", "hidden"), (41.5, "vis", "visible"),
             (50, "vis", "hidden"), (52, "vis", "visible"), (58, "mm", 6, 8), (59, "pu", 12, 16)]
    recs = [_hdr(), {"t": 0, "k": "start", "human_index": 0}, _tel(59.5, items),
            {"t": 60, "k": "result", "summary": {}, "row": {}, "agreement": None}]
    expected = {"n_clicks": 2, "n_keys": 2, "mouse_distance": 20.0, "n_scrolls": 1, "idle_fraction": 0.85,
                "hidden_seconds": 13.5, "n_blur": 2, "has_telemetry": 1}
    row = _ev(recs, ["activity"])
    for k, v in expected.items():
        assert row[k] == pytest.approx(v), k


def test_activity_window_edges_and_open_hidden():
    # Negotiation 10 -> 40.  Inputs inside the window: mm@12, key@14, input@30 (mm@5 is before the start,
    # mm@45 after the end: not inputs).  Points 10,12,14,30,40: gaps 2,2,16,10 -> idle 26 -> 26/30.
    # Pointer path over the whole recording: (0,0)@5 -> (3,4)@12 [5] -> (3,10)@45 [6] = 11.
    # Hidden: 2->4 = 2 (before the start still counts) and 35 -> never visible: until t1 = 40 -> 5.  Total 7.
    items = [(2, "vis", "hidden"), (4, "vis", "visible"), (5, "mm", 0, 0), (12, "mm", 3, 4), (14, "key", "a"),
             (30, "input"), (35, "vis", "hidden"), (45, "mm", 3, 10)]
    recs = [_hdr(), {"t": 10, "k": "start", "human_index": 0}, _tel(46, items),
            {"t": 40, "k": "result", "summary": {}, "row": {}, "agreement": None}, {"t": 50, "k": "end"}]
    expected = {"n_clicks": 0, "n_keys": 1, "mouse_distance": 11.0, "n_scrolls": 0, "idle_fraction": 26 / 30,
                "hidden_seconds": 7.0, "n_blur": 0, "has_telemetry": 1}
    row = _ev(recs, ["activity"])
    for k, v in expected.items():
        assert row[k] == pytest.approx(v), k


def test_activity_no_inputs_is_fully_idle_and_no_telemetry():
    # Telemetry with only a blur: no inputs, so the single gap 0 -> 30 > 5 is idle -> 30/30 = 1.
    recs = [_hdr(), {"t": 0, "k": "start", "human_index": 0}, _tel(10, [(5, "blur")]),
            {"t": 30, "k": "result", "summary": {}, "row": {}, "agreement": None}]
    expected = {"n_clicks": 0, "n_keys": 0, "mouse_distance": 0.0, "n_scrolls": 0, "idle_fraction": 1.0,
                "hidden_seconds": 0.0, "n_blur": 1, "has_telemetry": 1}
    row = _ev(recs, ["activity"])
    for k, v in expected.items():
        assert row[k] == pytest.approx(v), k
    # Without any telemetry only has_telemetry (0) is set.
    row = _ev([_hdr(), {"t": 0, "k": "start", "human_index": 0}, {"t": 30, "k": "end"}], ["activity"])
    assert row["has_telemetry"] == 0
    assert all(row.get(k) is None for k in ("n_clicks", "n_keys", "mouse_distance", "n_scrolls", "idle_fraction",
                                            "hidden_seconds", "n_blur"))


# =========================================================================== #
# dynamics                                                                     #
# =========================================================================== #
def _trace_rec(scn, rows, extra=()):
    return [_hdr(), scn, {"t": 1, "k": "start", "human_index": 0, "human_id": "H"},
            *extra, {"t": 9, "k": "trace", "rows": rows}, {"t": 10, "k": "result", "summary": {}, "row": {},
                                                           "agreement": None}]


def _rows(seq):
    return [{"t": i + 1, "negotiator": who, "offer": [idx], "step": i} for i, (who, idx) in enumerate(seq)]


def test_dynamics_documented_example():
    # Doc example.  Outcomes (human, opponent): 0=(1.0,.2) A, 1=(.8,.6) B, 2=(.62,.75) C,
    # 3=(.3,.9), 4=(.5,.7), 5=(.5,.4).
    # Human offers A, B, B, C: moves A->B (-.2,+.4) concession; B->B silent; B->C (-.18,+.15) concession.
    #   concession 2/3, silent 1/3, others 0.  human_concession = 1.0 - .62 = .38.
    #   tom_reflect: first raising move is move 1 of 3 -> 1/3.
    #   tom_other_trend: Pearson of k = 0..3 with u_o = .2,.6,.6,.75: dk = -1.5,-.5,.5,1.5, du = u_o - .5375;
    #   sum dk du = .825, sum dk^2 = 5, sum du^2 = .166875 -> .825 / sqrt(5 * .166875).
    # Opponent offers (self = u_o, other = u_h): 3=(.3,.9) -> 4=(.5,.7) -> 5=(.5,.4):
    #   3->4: du_o = -.2, du_h = +.2 concession; 4->5: du_o = -.3, du_h = 0 unfortunate (neither gained, one lost).
    # Pareto front of the 6 points = {(1,.2), (.8,.6), (.62,.75), (.3,.9)}; every human offer lies on it -> 0.
    U = [[1.0, .8, .62, .3, .5, .5], [.2, .6, .75, .9, .7, .4]]
    scn = _scenario([[i] for i in range(6)], U)
    seq = [("H", 0), ("O", 3), ("H", 1), ("O", 4), ("H", 1), ("O", 5), ("H", 2)]
    row = _ev(_trace_rec(scn, _rows(seq)), ["dynamics"])
    expected = {
        "human_move_silent": 1 / 3, "human_move_nice": 0.0, "human_move_fortunate": 0.0,
        "human_move_unfortunate": 0.0, "human_move_concession": 2 / 3, "human_move_selfish": 0.0,
        "opponent_move_silent": 0.0, "opponent_move_nice": 0.0, "opponent_move_fortunate": 0.0,
        "opponent_move_unfortunate": 0.5, "opponent_move_concession": 0.5, "opponent_move_selfish": 0.0,
        "human_concession": 0.38, "human_offer_pareto_distance": 0.0, "tom_reflect_index": 1 / 3,
        "tom_other_trend": 0.825 / math.sqrt(5 * 0.166875),
    }
    for k, v in expected.items():
        assert row[k] == pytest.approx(v, abs=1e-9), k


def _scn2():
    # outcomes (human, opponent): 0=(.5,.5), 1=(.75,.25), 2=(.5,.75), 3=(.75,.75)
    return _scenario([[0], [1], [2], [3]], [[.5, .75, .5, .75], [.5, .25, .75, .75]])


def test_dynamics_all_move_types_reflect_trend_pareto():
    # Human offers 0,1,1,0,2 -> (h,o): (.5,.5) (.75,.25) (.75,.25) (.5,.5) (.5,.75).
    #   0->1: (+.25,-.25) selfish; 1->1 silent; 1->0: (-.25,+.25) concession; 0->2: (0,+.25) nice.
    #   Moves: selfish, silent, concession, nice -> .25 each; fortunate, unfortunate 0.
    #   human_concession = h_first - h_last = .5 - .5 = 0.
    #   tom_reflect: first move raising u_o is the 3rd (concession) of 4 -> 3/4 (the doc's example).
    #   tom_other_trend: u_o = .5,.25,.25,.5,.75, k = 0..4: mean .45, dk du = (-2)(.05)+(-1)(-.2)+0+(1)(.05)+2(.3) = .75,
    #   sum dk^2 = 10, sum du^2 = .175 -> .75 / sqrt(1.75).
    #   Pareto front = {(.75,.75)} alone.  Distances: (.5,.5): sqrt(.125); (.75,.25): .5; (.5,.75): .25.
    #   Offers 0,1,1,0,2 -> mean = (2 sqrt(.125) + 2 * .5 + .25) / 5.
    # Opponent offers 0,3,2,3,1,0 (self = u_o, other = u_h):
    #   0->3 (+.25,+.25) fortunate; 3->2 (0,-.25) unfortunate; 2->3 (0,+.25) nice;
    #   3->1 (-.5,0) unfortunate; 1->0 (+.25,-.25) selfish.  5 moves.
    seq = [("H", 0), ("O", 0), ("H", 1), ("O", 3), ("H", 1), ("O", 2), ("H", 0), ("O", 3), ("H", 2),
           ("O", 1), ("O", 0)]
    row = _ev(_trace_rec(_scn2(), _rows(seq)), ["dynamics"])
    expected = {
        "human_move_silent": .25, "human_move_nice": .25, "human_move_fortunate": 0.0,
        "human_move_unfortunate": 0.0, "human_move_concession": .25, "human_move_selfish": .25,
        "opponent_move_silent": 0.0, "opponent_move_nice": .2, "opponent_move_fortunate": .2,
        "opponent_move_unfortunate": .4, "opponent_move_concession": 0.0, "opponent_move_selfish": .2,
        "human_concession": 0.0, "tom_reflect_index": .75,
        "tom_other_trend": .75 / math.sqrt(1.75),
        "human_offer_pareto_distance": (2 * math.sqrt(.125) + 2 * .5 + .25) / 5,
    }
    for k, v in expected.items():
        assert row[k] == pytest.approx(v, abs=1e-9), k


def test_dynamics_fortunate_human_and_never_reflecting():
    # Human offers 0 -> 3: (.5,.5) -> (.75,.75) fortunate: 1 move, fortunate = 1.
    # Reflect: first raising move is move 1 of 1 -> 1.  Fewer than 3 offers -> no trend.
    row = _ev(_trace_rec(_scn2(), _rows([("H", 0), ("H", 3)])), ["dynamics"])
    expected = {"human_move_fortunate": 1.0, "human_move_silent": 0.0, "tom_reflect_index": 1.0,
                "human_concession": -0.25, "tom_other_trend": None}  # concession = .5 - .75
    for k, v in expected.items():
        if v is None:
            assert row.get(k) is None, k
        else:
            assert row[k] == pytest.approx(v), k
    # Human offers 0 -> 1 -> 0.. never raising u_o: 0->1 selfish only: R = 1 by definition (none), moves=1.
    row = _ev(_trace_rec(_scn2(), _rows([("H", 0), ("H", 1)])), ["dynamics"])
    assert row["human_move_selfish"] == 1.0 and row["tom_reflect_index"] == 1.0
    assert row["human_concession"] == pytest.approx(-0.25)  # .5 - .75: hardened, negative
    # A single offer has no moves: everything empty.
    row = _ev(_trace_rec(_scn2(), _rows([("H", 0)])), ["dynamics"])
    assert row.get("human_move_silent") is None and row.get("human_concession") is None
    assert row.get("tom_reflect_index") is None


def test_dynamics_suggestions():
    # Events in time order (agent drafts are suggestions; offer acts set the human's latest offer, any actor):
    #  t=19 draft 1 (.75,.25): no base yet -> no move, becomes the previous suggestion.
    #  t=19.5 draft 3 (.75,.75) vs the previous suggestion (.75,.25): (0,+.5) nice.
    #  t=20 offer act 0 (.5,.5): the human's latest offer.
    #  t=21 draft 3 (.75,.75) vs (.5,.5): (+.25,+.25) fortunate.
    #  t=22 draft 2 (.5,.75) vs (.5,.5): (0,+.25) nice.
    #  t=23 offer act 1 (.75,.25).
    #  t=24 draft 0 (.5,.5) vs (.75,.25): (-.25,+.25) concession.
    #  t=25 draft 1 (.75,.25) vs (.75,.25): silent.
    # 5 moves: nice 2/5, fortunate 1/5, concession 1/5, silent 1/5, selfish 0, unfortunate 0.
    def draft(t, i):
        return {"t": t, "k": "draft", "by": "agent", "values": {"x": i}}

    recs = [_hdr(), _scn2(), {"t": 1, "k": "start", "human_index": 0, "human_id": "H"},
            draft(19, 1), draft(19.5, 3), _act(20, "offer", offer=[0]), draft(21, 3), draft(22, 2),
            _act(23, "offer", offer=[1]), draft(24, 0), draft(25, 1), {"t": 30, "k": "end"}]
    row = _ev(recs, ["dynamics"])
    expected = {"suggested_move_silent": .2, "suggested_move_nice": .4, "suggested_move_fortunate": .2,
                "suggested_move_unfortunate": 0.0, "suggested_move_concession": .2, "suggested_move_selfish": 0.0}
    for k, v in expected.items():
        assert row[k] == pytest.approx(v), k
    # Without suggestions the shares are empty.
    row = _ev(_trace_rec(_scn2(), _rows([("H", 0), ("H", 1)])), ["dynamics"])
    assert row.get("suggested_move_nice") is None
