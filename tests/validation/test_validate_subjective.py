"""Validation of the questionnaire metric and of the aggregation of the LLM-judged (soft) metrics.

Every expected value is derived by hand from the metric's written definition (comment above it).

The soft-metric tests validate AGGREGATION ONLY (parsing, clamping, counting, shares) from a stubbed
judge; they say nothing about whether a language model would judge well.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from hani2.evaluation import evaluate_recording, llm_judge
from hani2.evaluation.criteria import questionnaire_criteria
from hani2.evaluation.subjective import answer_values
from hani2.recording.format import Recording

SPEC_PATH = Path(__file__).resolve().parents[2] / "src/hani2/default_settings/questionnaires/evaluation.yaml"


def _bundled() -> dict:
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


_HEADER = {"k": "header", "format": "hani2-recording", "version": 1, "id": "v", "t0": 0}
_SCENARIO = {"t": 0, "k": "scenario", "name": "toy", "human_index": 0, "outcomes": [[0], [1], [2], [3]],
             "utilities": [[1.0, 0.7, 0.4, 0.0], [0.0, 0.6, 0.8, 1.0]], "reserved": [0.0, 0.0], "issue_names": ["x"]}


def _rec(*extra, questionnaire=None, assistant=True, acts=True, trace=True):
    recs = [_HEADER, _SCENARIO,
            {"t": 1, "k": "start", "human_index": 0, "human_id": "H",
             "support_agent": {"enabled": assistant}}]
    if acts:
        recs.append({"t": 2, "k": "act", "actor": "human", "type": "offer", "offer": [1], "values": {"x": 1}})
    if assistant:
        recs.append({"t": 3, "k": "chat", "user": "Assistant", "text": "I can suggest offers."})
    if trace:
        recs.append({"t": 4, "k": "trace", "rows": [{"t": 0.1, "negotiator": "O", "offer": [3]}]})
    recs.extend(extra)
    if questionnaire is not None:
        recs.append({"t": 9, "k": "questionnaire", **questionnaire})
    return Recording.from_records(recs)


def _q_row(spec, answers):
    rec = _rec(questionnaire={"spec": spec, "answers": answers}, assistant=False, acts=False, trace=False)
    return evaluate_recording(rec, ["questionnaire"])


# =========================================================================== #
# questionnaire: the bundled form                                              #
# =========================================================================== #
def test_questionnaire_bundled_form_scales():
    # Bundled items are all likert7 (1-7); reversed: ueq_valuable, ueq_good, ueq_clear (v' = 8 - v).
    # ueq_pragmatic = understandable 6, supportive 5, easy 6, efficient 5, clear 2->6, practical 5
    #   raw = 33/6 = 5.5; norm = mean((v'-1)/6) = (5+4+5+4+5+4)/6/6 = 27/36 = 0.75
    # ueq_hedonic = valuable 2->6, good 3->5: raw 5.5; norm = (5/6 + 4/6)/2 = 0.75
    # tam_usefulness = 4, 7: raw 5.5; norm = (3/6 + 6/6)/2 = 0.75
    # satisfaction = 6: norm 5/6.   appreciation(fun) = 3: norm 2/6.
    # intention_to_use = 2: norm 1/6.  felt_heard: not answered -> no column.
    # opponent_kindness = 1: norm 0.  opponent_intelligence = 7: norm 1.
    # opponent_humanlike = 4 (given as the string "4"): norm 3/6 = 0.5
    # relationship = negotiate_again 3, connected 6: raw 4.5, norm (2/6 + 5/6)/2 = 7/12
    answers = {"satisfaction_outcome": 6, "fun": 3,
               "ueq_understandable": 6, "ueq_valuable": 2, "ueq_supportive": 5, "ueq_good": 3,
               "ueq_easy": 6, "ueq_efficient": 5, "ueq_clear": 2, "ueq_practical": 5,
               "tam_effectiveness": 4, "tam_useful": 7, "use_again": 2,
               "agent_insights": "It was useful.", "opponent_kind": 1, "opponent_intelligent": 7,
               "opponent_human": "4", "negotiate_again": 3, "connected": 6, "comments": "bye"}
    expected = {
        "questionnaire_answered": 1,
        "scale_satisfaction": 6.0, "scale_satisfaction_norm": 5 / 6,
        "scale_appreciation": 3.0, "scale_appreciation_norm": 2 / 6,
        "scale_ueq_pragmatic": 5.5, "scale_ueq_pragmatic_norm": 0.75,
        "scale_ueq_hedonic": 5.5, "scale_ueq_hedonic_norm": 0.75,
        "scale_tam_usefulness": 5.5, "scale_tam_usefulness_norm": 0.75,
        "scale_intention_to_use": 2.0, "scale_intention_to_use_norm": 1 / 6,
        "scale_opponent_kindness": 1.0, "scale_opponent_kindness_norm": 0.0,
        "scale_opponent_intelligence": 7.0, "scale_opponent_intelligence_norm": 1.0,
        "scale_opponent_humanlike": 4.0, "scale_opponent_humanlike_norm": 0.5,
        "scale_relationship": 4.5, "scale_relationship_norm": 7 / 12,
        # q_<id> pattern: the answer, reversed items already reversed (8 - v)
        "q_satisfaction_outcome": 6.0, "q_ueq_valuable": 6.0, "q_ueq_good": 5.0, "q_ueq_clear": 6.0,
        "q_ueq_understandable": 6.0, "q_opponent_human": 4.0, "q_connected": 6.0,
    }
    out = _q_row(_bundled(), answers)
    row = out["row"]
    for col, want in expected.items():
        assert row[col] == pytest.approx(want), col
    # felt_heard unanswered: no column; free text: no column, kept in the details
    assert "scale_felt_heard" not in row and "scale_felt_heard_norm" not in row and "q_felt_heard" not in row
    assert "q_agent_insights" not in row and "q_comments" not in row
    assert out["details"]["questionnaire"]["texts"] == {"agent_insights": "It was useful.", "comments": "bye"}


def test_questionnaire_bundled_form_docs_example():
    # docs example: ueq_pragmatic answers 6,5,6,5,(clear=2 reversed 1+7-2=6),5 -> Q = 33/6 = 5.5, norm = (5.5-1)/6 = 0.75
    answers = {"ueq_understandable": 6, "ueq_supportive": 5, "ueq_easy": 6, "ueq_efficient": 5,
               "ueq_clear": 2, "ueq_practical": 5}
    expected = {"scale_ueq_pragmatic": 5.5, "scale_ueq_pragmatic_norm": 0.75}
    row = _q_row(_bundled(), answers)["row"]
    for col, want in expected.items():
        assert row[col] == pytest.approx(want), col
    # only the answered scale exists
    assert not [k for k in row if k.startswith("scale_") and "ueq_pragmatic" not in k]


def test_questionnaire_partial_scale_uses_answered_items_only():
    # tam_usefulness has two items; only tam_useful = 3 answered -> mean over the answered item = 3, norm 2/6.
    # ueq_pragmatic: only ueq_clear = 7 (reversed -> 1) answered -> raw 1, norm 0.
    expected = {"scale_tam_usefulness": 3.0, "scale_tam_usefulness_norm": 2 / 6,
                "scale_ueq_pragmatic": 1.0, "scale_ueq_pragmatic_norm": 0.0}
    row = _q_row(_bundled(), {"tam_useful": 3, "ueq_clear": 7, "tam_effectiveness": None, "fun": "n/a"})["row"]
    for col, want in expected.items():
        assert row[col] == pytest.approx(want), col
    # None and non-numeric answers count as missing (no scale_appreciation, no q_fun, no q_tam_effectiveness)
    assert not {"scale_appreciation", "q_fun", "q_tam_effectiveness"} & set(row)


def test_questionnaire_answered_flag():
    # no questionnaire record -> 0 and nothing else; a record (even with no answers) -> 1 and no scale columns
    no_q = evaluate_recording(_rec(assistant=False, acts=False, trace=False), ["questionnaire"])["row"]
    empty = _q_row(_bundled(), {})["row"]
    expected = {"questionnaire_answered": (no_q.get("questionnaire_answered"), 0)}
    expected["questionnaire_answered_empty_answers"] = (empty.get("questionnaire_answered"), 1)
    for col, (got, want) in expected.items():
        assert got == want, col
    assert not [k for k in no_q if k.startswith(("scale_", "q_"))]
    assert not [k for k in empty if k.startswith(("scale_", "q_"))]


# =========================================================================== #
# questionnaire: mixed ranges and item types                                   #
# =========================================================================== #
_MIXED = {"questions": [
    {"id": "a", "type": "likert5", "scale": "mix", "reverse": True},    # 1-5
    {"id": "b", "type": "likert7", "scale": "mix"},                     # 1-7
    {"id": "c", "type": "yes_no", "scale": "yn"},                       # 0-1
    {"id": "f", "type": "yes_no", "scale": "yn", "reverse": True},
    {"id": "d", "type": "select", "options": ["low", "mid", "high"], "scale": "sel"},               # position 1-3
    {"id": "g", "type": "select", "options": ["low", "mid", "high"], "scale": "sel", "reverse": True},
    {"id": "e", "type": "number", "min": 0, "max": 10, "scale": "num"},
    {"id": "h", "type": "likert7", "scale": "num"},
    {"id": "solo", "type": "likert5"},                                  # no scale
    {"id": "free", "type": "text", "scale": "ignored"},                 # text never numeric
]}


def test_questionnaire_mixed_ranges_and_types():
    # a: likert5 reversed, answer 2 -> 1+5-2 = 4 (range 1-5).  b: likert7, 5.
    #   mix raw = (4+5)/2 = 4.5 ; norm = ((4-1)/4 + (5-1)/6)/2 = (0.75 + 2/3)/2 = 17/24
    # c: yes_no "Yes" -> 1.  f: yes_no reversed, answer False -> 0+1-0 = 1.
    #   yn raw = (1+1)/2 = 1 ; norm = (1 + 1)/2 = 1
    # d: select "high" -> position 3 (range 1-3).  g: select reversed, "mid" -> position 2 -> 1+3-2 = 2.
    #   sel raw = 2.5 ; norm = ((3-1)/2 + (2-1)/2)/2 = (1 + 0.5)/2 = 0.75
    # e: min 0 max 10 answer 5 ; h: likert7 answer 7.
    #   num raw = 6 ; norm = (5/10 + 6/6)/2 = 0.75
    # solo: likert5 answer 4 -> q_solo = 4 and in no scale.  free text: only in texts.
    answers = {"a": 2, "b": 5, "c": "Yes", "f": False, "d": "high", "g": "mid", "e": 5, "h": 7,
               "solo": 4, "free": "words"}
    expected = {
        "scale_mix": 4.5, "scale_mix_norm": 17 / 24,
        "scale_yn": 1.0, "scale_yn_norm": 1.0,
        "scale_sel": 2.5, "scale_sel_norm": 0.75,
        "scale_num": 6.0, "scale_num_norm": 0.75,
        "q_a": 4.0, "q_b": 5.0, "q_c": 1.0, "q_f": 1.0, "q_d": 3.0, "q_g": 2.0, "q_e": 5.0, "q_h": 7.0,
        "q_solo": 4.0,
    }
    out = answer_values(_MIXED, answers)
    vals, texts = out
    for col, want in expected.items():
        assert vals[col] == pytest.approx(want), col
    assert set(vals) == set(expected)  # nothing else, in particular no scale for the text item
    assert texts == {"free": "words"}


def test_questionnaire_yes_no_and_select_encodings():
    # yes_no accepts yes/no/true/false in any case, booleans and 1/0: yes -> 1, no -> 0.
    # reversed yes_no: 0+1-v. select: position (1-based) in options; unknown option -> missing.
    spec = {"questions": [
        {"id": "y1", "type": "yes_no"}, {"id": "y2", "type": "yes_no"}, {"id": "y3", "type": "yes_no"},
        {"id": "y4", "type": "yes_no"}, {"id": "y5", "type": "yes_no"}, {"id": "y6", "type": "yes_no", "reverse": True},
        {"id": "s1", "type": "select", "options": ["red", "green", "blue", "pink"]},
        {"id": "s2", "type": "select", "options": ["red", "green", "blue", "pink"]},
        {"id": "s3", "type": "select", "options": ["red", "green", "blue", "pink"]},
        {"id": "s4", "type": "select", "options": ["x", "y"], "scale": "p"},
    ]}
    answers = {"y1": " YES ", "y2": "no", "y3": True, "y4": "False", "y5": 1, "y6": "yes",
               "s1": "red", "s2": "pink", "s3": "purple", "s4": "y"}
    expected = {"q_y1": 1.0, "q_y2": 0.0, "q_y3": 1.0, "q_y4": 0.0, "q_y5": 1.0,
                "q_y6": 0.0,  # reversed yes: 0 + 1 - 1
                "q_s1": 1.0, "q_s2": 4.0,
                "q_s4": 2.0, "scale_p": 2.0, "scale_p_norm": 1.0}  # position 2 of 2 -> (2-1)/(2-1)
    vals, _ = answer_values(spec, answers)
    for col, want in expected.items():
        assert vals[col] == pytest.approx(want), col
    assert "q_s3" not in vals  # not an option -> missing


def test_questionnaire_answer_values_prefix():
    # same arithmetic as the unprefixed form, every column gets the prefix; texts are keyed by the question id.
    # likert7 reversed 2 -> 6 ; plain 4 ; scale mean 5, norm ((6-1)/6 + (4-1)/6)/2 = 8/12 = 2/3
    spec = {"questions": [{"id": "r", "type": "likert7", "scale": "s", "reverse": True},
                          {"id": "p", "type": "likert7", "scale": "s"}, {"id": "t", "type": "text"}]}
    vals, texts = answer_values(spec, {"r": 2, "p": 4, "t": "hi", "unknown": 3}, prefix="post_")
    expected = {"post_q_r": 6.0, "post_q_p": 4.0, "post_scale_s": 5.0, "post_scale_s_norm": 2 / 3}
    assert vals == pytest.approx(expected)
    assert texts == {"t": "hi"}


# =========================================================================== #
# questionnaire_criteria                                                       #
# =========================================================================== #
def test_questionnaire_criteria_bundled_bounds():
    # 11 scales (each with raw + norm) + 19 likert7 items = 41 criteria; item types are likert7 -> bounds 1-7;
    # scale norm columns are bounded 0-1; text items (agent_insights, comments) have no criterion.
    crit = {c.id: c for c in questionnaire_criteria(_bundled(), "per_negotiation")}
    scales = ["satisfaction", "appreciation", "ueq_pragmatic", "ueq_hedonic", "tam_usefulness", "intention_to_use",
              "felt_heard", "opponent_kindness", "opponent_intelligence", "opponent_humanlike", "relationship"]
    items = ["satisfaction_outcome", "fun", "ueq_understandable", "ueq_valuable", "ueq_supportive", "ueq_good",
             "ueq_easy", "ueq_efficient", "ueq_clear", "ueq_practical", "tam_effectiveness", "tam_useful",
             "use_again", "felt_heard", "opponent_kind", "opponent_intelligent", "opponent_human",
             "negotiate_again", "connected"]
    assert set(crit) == ({f"scale_{s}" for s in scales} | {f"scale_{s}_norm" for s in scales}
                         | {f"q_{i}" for i in items})
    assert len(crit) == 41
    for s in scales:
        raw, norm = crit[f"scale_{s}"], crit[f"scale_{s}_norm"]
        assert raw.normaliser == {"kind": "bounded", "lo": 1.0, "hi": 7.0} and raw.range == "1–7"
        assert norm.normaliser == {"kind": "bounded", "lo": 0.0, "hi": 1.0} and norm.range == "[0, 1]"
        assert raw.direction == norm.direction == "higher"
        assert raw.level == "negotiation" and raw.form == "per_negotiation" and raw.source == "questionnaire"
    for i in items:
        c = crit[f"q_{i}"]
        assert c.normaliser == {"kind": "bounded", "lo": 1.0, "hi": 7.0} and c.range == "1–7"
        assert c.direction == "higher"  # every bundled item belongs to a scale
    assert "(reversed)" in crit["q_ueq_clear"].description and "(reversed)" not in crit["q_ueq_easy"].description


def test_questionnaire_criteria_item_types_and_mixed_scale():
    # likert5 -> 1-5; yes_no -> 0-1; select with 3 options -> 1-3; min/max -> 0-10;
    # text and an empty-options select -> no criterion; unscaled item -> direction "none"; explicit direction kept.
    # scale "mix" has items 1-5 and 1-7 -> raw column has no normaliser and range "mixed ranges", norm is 0-1.
    # scale "yn" has two 0-1 items -> bounded 0-1 raw column.  scale "sel" 1-3.
    spec = dict(_MIXED)
    spec["questions"] = _MIXED["questions"] + [
        {"id": "emptysel", "type": "select", "options": []},
        {"id": "low", "type": "likert7", "scale": "mix", "direction": "lower"},
        {"id": "dflt", "type": "likert5", "direction": "bogus"},
        {"id": "flat", "type": "number", "min": 3, "max": 3, "scale": "flat"},
    ]
    crit = {c.id: c for c in questionnaire_criteria(spec)}
    assert crit["scale_mix"].normaliser is None and crit["scale_mix"].range == "mixed ranges"
    assert crit["scale_mix_norm"].normaliser == {"kind": "bounded", "lo": 0.0, "hi": 1.0}
    assert crit["scale_yn"].normaliser == {"kind": "bounded", "lo": 0.0, "hi": 1.0} and crit["scale_yn"].range == "0–1"
    assert crit["scale_sel"].normaliser == {"kind": "bounded", "lo": 1.0, "hi": 3.0} and crit["scale_sel"].range == "1–3"
    assert crit["scale_num"].normaliser is None  # 0-10 and 1-7 mixed
    expected_ranges = {"q_a": "1–5", "q_c": "0–1", "q_d": "1–3", "q_e": "0–10", "q_solo": "1–5", "q_h": "1–7"}
    for cid, rng in expected_ranges.items():
        assert crit[cid].range == rng, cid
    assert crit["q_e"].normaliser == {"kind": "bounded", "lo": 0.0, "hi": 10.0}
    assert crit["q_solo"].direction == "none" and crit["q_low"].direction == "lower"
    assert crit["q_dflt"].direction == "none"  # unknown direction -> none
    assert "q_free" not in crit and "q_emptysel" not in crit and "scale_ignored" not in crit
    assert "q_flat" not in crit and "scale_flat" not in crit  # hi <= lo has no range


def test_questionnaire_criteria_post_session_form():
    # post_session: ids prefixed "post_", level "participant", form kept; empty/None spec -> no criteria.
    spec = {"questions": [{"id": "x", "type": "likert5", "scale": "s"}]}
    crit = {c.id: c for c in questionnaire_criteria(spec, "post_session")}
    assert set(crit) == {"post_scale_s", "post_scale_s_norm", "post_q_x"}
    assert all(c.level == "participant" and c.form == "post_session" for c in crit.values())
    assert crit["post_scale_s"].normaliser == {"kind": "bounded", "lo": 1.0, "hi": 5.0}
    assert questionnaire_criteria(None) == [] and questionnaire_criteria({}) == []


# =========================================================================== #
# Soft metrics: aggregation only, from a stubbed judge                         #
# =========================================================================== #
def _stub(monkeypatch, reply):
    calls = []

    def fake(prompt, settings):
        calls.append(prompt)
        return reply

    monkeypatch.setattr(llm_judge, "CALL", fake)
    return calls


def _judge(monkeypatch, reply, metric, rec=None, options=None):
    calls = _stub(monkeypatch, reply)
    out = evaluate_recording(rec or _rec(), [metric], use_llm=True, options=options)
    assert not out["errors"], out["errors"]
    return out, calls


def test_judge_assistant_rating_parsing_and_clamping(monkeypatch):
    # rating = min(7, max(1, x)); null / missing / unparsable / NaN -> empty; numeric strings are parsed; no rounding.
    # helpfulness 6 -> 6 ; explanation 9 -> 7 ; opponent_insight 0 -> 1 ; user_understanding "5" -> 5
    # scenario_explanation null -> None ; capability_disclosure 3.5 -> 3.5 ; autonomy_respect -2 -> 1
    # communication "abc" -> None ; message_improvement missing -> None ; overall 4 -> 4
    reply = ('{"helpfulness": 6, "explanation": 9, "opponent_insight": 0, "user_understanding": "5", '
             '"scenario_explanation": null, "capability_disclosure": 3.5, "autonomy_respect": -2, '
             '"communication": "abc", "overall": 4, "justification": "fine"}')
    expected = {"ja_helpfulness": 6.0, "ja_explanation": 7.0, "ja_opponent_insight": 1.0,
                "ja_user_understanding": 5.0, "ja_scenario_explanation": None, "ja_capability_disclosure": 3.5,
                "ja_autonomy_respect": 1.0, "ja_communication": None, "ja_message_improvement": None,
                "ja_overall": 4.0}
    out, calls = _judge(monkeypatch, reply, "judge_assistant")
    for col, want in expected.items():
        assert out["row"][col] == (pytest.approx(want) if want is not None else None), col
    assert out["details"]["judge_assistant"] == {"justification": "fine"}
    assert "I can suggest offers." in calls[0]


def test_judge_assistant_skipped_without_assistant(monkeypatch):
    # no chat / fn / agent draft / agent act -> nothing judged and the judge is not even asked
    out, calls = _judge(monkeypatch, '{"overall": 5}', "judge_assistant", rec=_rec(assistant=False))
    assert not [k for k in out["row"] if k.startswith("ja_")] and calls == []


def test_judge_opponent_rating_parsing_and_clamping(monkeypatch):
    # kindness 7 -> 7 ; intelligence 7.9 -> 7 (clamped, not rounded) ; cooperativeness 1 -> 1 ;
    # human_likeness 2.25 -> 2.25 ; communication null -> None ; consistency 100 -> 7 ; overall "6" -> 6
    reply = ('```json\n{"kindness": 7, "intelligence": 7.9, "cooperativeness": 1, "human_likeness": 2.25, '
             '"communication": null, "consistency": 100, "overall": "6", "justification": "j"}\n```')
    expected = {"jo_kindness": 7.0, "jo_intelligence": 7.0, "jo_cooperativeness": 1.0, "jo_human_likeness": 2.25,
                "jo_communication": None, "jo_consistency": 7.0, "jo_overall": 6.0}
    out, _ = _judge(monkeypatch, reply, "judge_opponent")
    for col, want in expected.items():
        assert out["row"][col] == (pytest.approx(want) if want is not None else None), col


def test_judge_opponent_skipped_without_offers(monkeypatch):
    out, calls = _judge(monkeypatch, '{"overall": 5}', "judge_opponent", rec=_rec(trace=False, acts=False))
    assert not [k for k in out["row"] if k.startswith("jo_")] and calls == []


def test_judge_human_rating_parsing_and_clamping(monkeypatch):
    # engagement 3 -> 3 ; strategy 0.5 -> 1 ; cooperativeness null -> None ; use_of_assistant 7 -> 7 ;
    # communication 4.5 -> 4.5 ; overall -3 -> 1 ; answer wrapped in prose is still parsed
    reply = ('Here: {"engagement": 3, "strategy": 0.5, "cooperativeness": null, "use_of_assistant": 7, '
             '"communication": 4.5, "overall": -3, "justification": "j"} done')
    expected = {"jh_engagement": 3.0, "jh_strategy": 1.0, "jh_cooperativeness": None, "jh_use_of_assistant": 7.0,
                "jh_communication": 4.5, "jh_overall": 1.0}
    out, _ = _judge(monkeypatch, reply, "judge_human")
    for col, want in expected.items():
        assert out["row"][col] == (pytest.approx(want) if want is not None else None), col


def test_judge_human_skipped_without_actions(monkeypatch):
    out, calls = _judge(monkeypatch, '{"overall": 5}', "judge_human", rec=_rec(acts=False))
    assert not [k for k in out["row"] if k.startswith("jh_")] and calls == []


def test_nl_assertions_share_of_applicable(monkeypatch):
    # 7 default assertions; verdicts: true, false, null, true, "yes" (not a boolean -> not applicable), and only 5
    # results given (the 6th and 7th are missing -> not applicable).
    # judged = {true, false, true} -> total 3 ; met = 2/3
    reply = '{"results": [{"met": true}, {"met": false}, {"met": null}, {"met": true}, {"met": "yes"}]}'
    expected = {"assertions_met": 2 / 3, "assertions_total": 3}
    out, _ = _judge(monkeypatch, reply, "nl_assertions")
    for col, want in expected.items():
        assert out["row"][col] == pytest.approx(want), col
    checks = out["details"]["nl_assertions"]["checks"]
    assert len(checks) == 7 and [c["met"] for c in checks] == [True, False, None, True, None, None, None]


def test_nl_assertions_docs_example(monkeypatch):
    # docs: seven assertions, four met, one not met, two not applicable -> 4/5 = 0.8 and total 5
    reply = ('{"results": [{"met": true}, {"met": true}, {"met": false}, {"met": null}, {"met": true},'
             ' {"met": null}, {"met": true}]}')
    expected = {"assertions_met": 0.8, "assertions_total": 5}
    out, _ = _judge(monkeypatch, reply, "nl_assertions")
    for col, want in expected.items():
        assert out["row"][col] == pytest.approx(want), col


def test_nl_assertions_none_applicable_and_custom_list(monkeypatch):
    # all null -> met is empty (0/0 undefined), total 0.
    out, _ = _judge(monkeypatch, '{"results": [{"met": null}, {"met": null}]}', "nl_assertions",
                    options={"assertions": ["a", "b"]})
    expected = {"assertions_met": None, "assertions_total": 0}
    for col, want in expected.items():
        assert out["row"][col] == want, col
    # explicit assertions are judged even without any Assistant activity: [false, false] -> met 0, total 2
    out, calls = _judge(monkeypatch, '{"results": [{"met": false}, {"met": false}]}', "nl_assertions",
                        rec=_rec(assistant=False), options={"assertions": ["a", "b", "  "]})
    expected = {"assertions_met": 0.0, "assertions_total": 2}  # blank statement is dropped
    for col, want in expected.items():
        assert out["row"][col] == want, col
    assert "1. a" in calls[0] and "2. b" in calls[0] and "3." not in calls[0]
    # default assertions on a session without Assistant: not computed, judge not asked
    out, calls = _judge(monkeypatch, '{"results": []}', "nl_assertions", rec=_rec(assistant=False))
    assert "assertions_met" not in out["row"] and calls == []


def _errors_reply(errors, helped=None, hurt=None):
    import json

    d = {"errors": errors}
    if helped is not None:
        d["overrides_helped"] = helped
    if hurt is not None:
        d["overrides_hurt"] = hurt
    return json.dumps(d)


def test_error_review_counts_by_source_and_severity(monkeypatch):
    # source: contains "assist" or "agent" -> assistant, anything else -> human (no simulator without a sim record).
    # severity: case-insensitive; unknown -> minor.
    #  1 Assistant critical 03:05   2 "the agent" MINOR   3 human critical 02:30
    #  4 Human "weird" -> minor     5 assistant major 01:10   6 "simulator" (no sim) -> human   7 not a dict: ignored
    # assistant_errors = {1,2,5} = 3 ; assistant_critical = {1} = 1
    # human_errors = {3,4,6} = 3 ; human_critical = {3} = 1 ; simulator_* = None (not a simulated session)
    # first critical = earliest of 02:30 (human) and 03:05 (assistant) = human
    # overrides: helped 2 -> 2 ; hurt "1" -> 1
    errs = [{"source": "Assistant", "time": "03:05", "severity": "critical"},
            {"source": "the agent", "time": "00:10", "severity": "MINOR"},
            {"source": "human", "time": "02:30", "severity": "critical"},
            {"source": "Human", "time": "00:20", "severity": "weird"},
            {"source": "assistant", "time": "01:10", "severity": "major"},
            {"source": "simulator", "time": "00:30", "severity": "minor"},
            "garbage"]
    expected = {"assistant_errors": 3, "assistant_critical_errors": 1, "human_errors": 3, "human_critical_errors": 1,
                "simulator_errors": None, "simulator_critical_errors": None,
                "human_overrode_helpfully": 2, "human_overrode_harmfully": 1, "first_critical": "human"}
    out, _ = _judge(monkeypatch, _errors_reply(errs, 2, "1"), "error_review")
    for col, want in expected.items():
        assert out["row"][col] == want, col


def test_error_review_docs_example(monkeypatch):
    # docs: minor assistant 01:10, critical human 02:30, critical assistant 03:05
    # -> assistant_errors 2, assistant_critical_errors 1, human_errors 1, human_critical_errors 1, first_critical human
    errs = [{"source": "assistant", "time": "01:10", "severity": "minor"},
            {"source": "human", "time": "02:30", "severity": "critical"},
            {"source": "assistant", "time": "03:05", "severity": "critical"}]
    expected = {"assistant_errors": 2, "assistant_critical_errors": 1, "human_errors": 1,
                "human_critical_errors": 1, "first_critical": "human",
                "human_overrode_helpfully": None, "human_overrode_harmfully": None}  # counts not reported -> empty
    out, _ = _judge(monkeypatch, _errors_reply(errs), "error_review")
    for col, want in expected.items():
        assert out["row"][col] == want, col


def test_error_review_first_critical_ordering_and_none(monkeypatch):
    # critical errors: assistant with unreadable time "soon" (sorts last), human at 10:00, human at 00:05 (not critical)
    # -> the readable critical one comes first: human.  Then without any critical error -> "none", counts 0.
    errs = [{"source": "assistant", "time": "soon", "severity": "critical"},
            {"source": "human", "time": "10:00", "severity": "critical"},
            {"source": "assistant", "time": "00:05", "severity": "major"}]
    out, _ = _judge(monkeypatch, _errors_reply(errs), "error_review")
    expected = {"first_critical": "human", "assistant_errors": 2, "assistant_critical_errors": 1,
                "human_errors": 1, "human_critical_errors": 1}
    for col, want in expected.items():
        assert out["row"][col] == want, col
    out, _ = _judge(monkeypatch, _errors_reply([]), "error_review")
    expected = {"first_critical": "none", "assistant_errors": 0, "assistant_critical_errors": 0,
                "human_errors": 0, "human_critical_errors": 0}
    for col, want in expected.items():
        assert out["row"][col] == want, col


def test_error_review_simulated_participant(monkeypatch):
    # with a sim record, a source naming "simul" or "persona" is the simulator's; it is never also counted as
    # the assistant's or human's.
    #  simulator minor 00:40, "Persona broke character" critical 00:50, assistant critical 02:00, human minor 03:00
    # simulator_errors = 2 ; simulator_critical = 1 ; assistant 1 / critical 1 ; human 1 / critical 0
    # first critical = simulator at 00:50
    sim = {"t": 1.5, "k": "sim", "persona": "Pat", "kind": "tough", "difficulty": "hard", "policy": "p",
           "reservation": 0.3}
    errs = [{"source": "simulator", "time": "00:40", "severity": "minor"},
            {"source": "Persona broke character", "time": "00:50", "severity": "critical"},
            {"source": "assistant", "time": "02:00", "severity": "critical"},
            {"source": "human", "time": "03:00", "severity": "minor"}]
    expected = {"simulator_errors": 2, "simulator_critical_errors": 1, "assistant_errors": 1,
                "assistant_critical_errors": 1, "human_errors": 1, "human_critical_errors": 0,
                "first_critical": "simulator"}
    out, _ = _judge(monkeypatch, _errors_reply(errs, 0, 0), "error_review", rec=_rec(sim))
    for col, want in expected.items():
        assert out["row"][col] == want, col
    assert out["row"]["human_overrode_helpfully"] == 0 and out["row"]["human_overrode_harmfully"] == 0


def test_error_review_skipped_without_actions(monkeypatch):
    out, calls = _judge(monkeypatch, _errors_reply([]), "error_review", rec=_rec(acts=False))
    assert "assistant_errors" not in out["row"] and calls == []


_CRIT = {"criteria": {"communicate": ["Price matters most", "Time is short", "Quality is fixed"],
                      "assertions": ["Never pressured", "Asked first"]}}


def test_task_judge_shares(monkeypatch):
    # facts conveyed [true, true, false] -> 2/3 ; assertions met [true, null] -> only one applicable, met -> 1.0
    reply = ('{"facts": [{"conveyed": true}, {"conveyed": true}, {"conveyed": false}], '
             '"assertions": [{"met": true}, {"met": null}]}')
    expected = {"task_communicated": 2 / 3, "task_assertions_met": 1.0}
    out, calls = _judge(monkeypatch, reply, "task_judge", options=_CRIT)
    for col, want in expected.items():
        assert out["row"][col] == pytest.approx(want), col
    assert "1. Price matters most" in calls[0] and "2. Asked first" in calls[0]


def test_task_judge_non_boolean_missing_and_empty(monkeypatch):
    # facts: [true, "yes" (non-bool -> not judged), false, (missing -> not judged)] -> 1/2... use 4 facts:
    #   judged = {true, false} -> task_communicated = 1/2
    # assertions: all null -> empty (0/0)
    crit = {"criteria": {"communicate": ["f1", "f2", "f3", "f4"], "assertions": ["a1", "a2"]}}
    reply = ('{"facts": [{"conveyed": true}, {"conveyed": "yes"}, {"conveyed": false}], '
             '"assertions": [{"met": null}, {"met": null}]}')
    expected = {"task_communicated": 0.5, "task_assertions_met": None}
    out, _ = _judge(monkeypatch, reply, "task_judge", options=crit)
    for col, want in expected.items():
        assert out["row"][col] == want, col


def test_task_judge_only_facts_or_nothing(monkeypatch):
    # only facts defined -> only task_communicated is produced: [false, false] -> 0.0
    out, _ = _judge(monkeypatch, '{"facts": [{"conveyed": false}, {"conveyed": false}]}', "task_judge",
                    options={"criteria": {"communicate": ["f1", "f2"]}})
    expected = {"task_communicated": 0.0}
    assert out["row"]["task_communicated"] == expected["task_communicated"]
    assert "task_assertions_met" not in out["row"]
    # only assertions -> only task_assertions_met: [true, true, false] -> 2/3
    out, _ = _judge(monkeypatch, '{"assertions": [{"met": true}, {"met": true}, {"met": false}]}', "task_judge",
                    options={"criteria": {"assertions": ["a", "b", "c"]}})
    assert out["row"]["task_assertions_met"] == pytest.approx(2 / 3) and "task_communicated" not in out["row"]
    # no criteria at all -> nothing, judge not asked
    out, calls = _judge(monkeypatch, "{}", "task_judge")
    assert "task_communicated" not in out["row"] and "task_assertions_met" not in out["row"] and calls == []
