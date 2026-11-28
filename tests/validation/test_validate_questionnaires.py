"""The predefined questionnaires checked against their source instruments: items (wording and
count), anchors, reversed items and the scoring of their scales.

The source facts are copied here from the instruments themselves:
* SVI — the authors' item document (subjectivevalue.com, "SVI synopsis and items"): 16 items,
  1–7, anchors per item, items 3 and 5 reverse-scored, four 4-item subscales averaged.
* SUS — Brooke (1996): 10 items, 1 = strongly disagree … 5 = strongly agree, score
  2.5 × (Σ(odd − 1) + Σ(5 − even)).
* UEQ-S — the UEQ-S item sheet and the UEQ handbook (ueq-online.org): 8 items, negative pole
  left, items 1–4 pragmatic, 5–8 hedonic, a scale is the mean of its items.
* UEQ (full) — the handbook's item list (items 2, 5, 11, 12, 13, 20, 21, 22 and their poles).
"""

import re

import pytest

from hani2 import questionnaires
from hani2.evaluation.subjective import answer_values
from hani2.templates import render


def _set(sid):
    return questionnaires.library()[sid]


# --------------------------------------------------------------------------- SVI
SVI_SOURCE = [  # (the item as printed in the source, subscale, reversed, anchor 1, anchor 7)
    ("How satisfied are you with your own outcome—i.e., the extent to which the terms of your agreement (or lack of "
     "agreement) benefit you?", "svi_instrumental", False, "Not at all", "Perfectly"),
    ("How satisfied are you with the balance between your own outcome and your counterpart(s)’s outcome(s)?",
     "svi_instrumental", False, "Not at all", "Perfectly"),
    ("Did you feel like you forfeited or “lost” in this negotiation?", "svi_instrumental", True, "Not at all",
     "A great deal"),
    ("Do you think the terms of your agreement are consistent with principles of legitimacy or objective criteria "
     "(e.g., common standards of fairness, precedent, industry practice, legality, etc.)?", "svi_instrumental", False,
     "Not at all", "Perfectly"),
    ("Did you “lose face” (i.e., damage your sense of pride) in the negotiation?", "svi_self", True, "Not at all",
     "A great deal"),
    ("Did this negotiation make you feel more or less competent as a negotiator?", "svi_self", False,
     "It made me feel less competent", "It made me feel more competent"),
    ("Did you behave according to your own principles and values?", "svi_self", False, "Not at all", "Perfectly"),
    ("Did this negotiation positively or negatively impact your self-image or your impression of yourself?",
     "svi_self", False, "It negatively impacted my self-image", "It positively impacted my self-image"),
    ("Do you feel your counterpart(s) listened to your concerns?", "svi_process", False, "Not at all", "Perfectly"),
    ("Would you characterize the negotiation process as fair?", "svi_process", False, "Not at all", "Perfectly"),
    ("How satisfied are you with the ease (or difficulty) of reaching an agreement?", "svi_process", False,
     "Not at all satisfied", "Perfectly satisfied"),
    ("Did your counterpart(s) consider your wishes, opinions, or needs?", "svi_process", False, "Not at all",
     "Perfectly"),
    ("What kind of “overall” impression did your counterpart(s) make on you?", "svi_relationship", False,
     "Extremely negative", "Extremely positive"),
    ("How satisfied are you with your relationship with your counterpart(s) as a result of this negotiation?",
     "svi_relationship", False, "Not at all", "Perfectly"),
    ("Did the negotiation make you trust your counterpart(s)?", "svi_relationship", False, "Not at all", "Perfectly"),
    ("Did the negotiation build a good foundation for a future relationship with your counterpart(s)?",
     "svi_relationship", False, "Not at all", "Perfectly"),
]


def _words(text):
    """The words of an item: the source's two-party wording (counterpart → opponent, as its administration notes
    allow for one counterpart), without punctuation, quotes or "i.e."."""
    t = text.replace("counterpart(s)’s outcome(s)", "opponent's outcome").replace("counterpart(s)", "opponent")
    t = re.sub(r"[*_`]", "", t).lower().replace("i.e.", " ")
    return re.findall(r"[a-z]+(?:-[a-z]+)?", t.replace("’", "'").replace("'s", "s"))


def test_svi_matches_source():
    qs = _set("subjective_value")["questions"]
    assert len(qs) == 16
    for i, (q, (text, scale, rev, lo, hi)) in enumerate(zip(qs, SVI_SOURCE), 1):
        assert _words(q["text"]) == _words(text), f"item {i}: {q['text']!r}"
        assert q["type"] == "likert7" and q["scale"] == scale, f"item {i}"
        assert bool(q.get("reverse")) is rev, f"item {i}"
        assert (q["labels"][1], q["labels"][7]) == (lo, hi), f"item {i}"
    # scoring: reverse 3 and 5 (7 → 1, 6 → 2, …), then average each subscale with equal weights.
    answers = {q["id"]: v for q, v in zip(qs, [6, 5, 2, 4, 7, 6, 5, 4, 3, 4, 5, 6, 7, 6, 5, 4])}
    vals, _ = answer_values({"questions": qs}, answers)
    # instrumental: 6, 5, (8 − 2) = 6, 4 → 21/4; self: (8 − 7) = 1, 6, 5, 4 → 16/4
    # process: 3, 4, 5, 6 → 18/4; relationship: 7, 6, 5, 4 → 22/4
    expected = {"scale_svi_instrumental": 5.25, "scale_svi_self": 4.0, "scale_svi_process": 4.5,
                "scale_svi_relationship": 5.5, "q_svi_lost": 6, "q_svi_lose_face": 1,
                "scale_svi_self_norm": (4.0 - 1) / 6}
    for k, v in expected.items():
        assert vals[k] == pytest.approx(v), k
    # the source's optional Global score: the mean of the four subscales = (5.25 + 4 + 4.5 + 5.5) / 4
    glob = sum(vals[f"scale_svi_{s}"] for s in ("instrumental", "self", "process", "relationship")) / 4
    assert glob == pytest.approx(19.25 / 4)


# --------------------------------------------------------------------------- SUS
SUS_SOURCE = [
    "I think that I would like to use this system frequently.",
    "I found the system unnecessarily complex.",
    "I thought the system was easy to use.",
    "I think that I would need the support of a technical person to be able to use this system.",
    "I found the various functions in this system were well integrated.",
    "I thought there was too much inconsistency in this system.",
    "I would imagine that most people would learn to use this system very quickly.",
    "I found the system very cumbersome to use.",
    "I felt very confident using the system.",
    "I needed to learn a lot of things before I could get going with this system.",
]


def test_sus_matches_source():
    qs = _set("sus")["questions"]
    assert [q["text"] for q in qs] == SUS_SOURCE
    for i, q in enumerate(qs, 1):
        assert q["type"] == "likert5" and q["scale"] == "sus"
        assert (q["labels"][1], q["labels"][5]) == ("Strongly disagree", "Strongly agree")
        assert bool(q.get("reverse")) is (i % 2 == 0), f"even items are reversed (item {i})"
    raw = [4, 2, 5, 1, 4, 2, 5, 2, 4, 1]
    vals, _ = answer_values({"questions": qs}, {q["id"]: v for q, v in zip(qs, raw)})
    # Brooke: odd items contribute x − 1 → 3, 4, 3, 4, 3 = 17; even items 5 − x → 3, 4, 3, 3, 4 = 17;
    # SUS = 2.5 × 34 = 85.
    sus = 2.5 * (sum(x - 1 for x in raw[0::2]) + sum(5 - x for x in raw[1::2]))
    assert sus == 85
    expected = {"scale_sus_norm": 0.85, "scale_sus": 1 + 4 * 0.85}  # mean of the reversed answers 4.4
    for k, v in expected.items():
        assert vals[k] == pytest.approx(v), k
    assert 100 * vals["scale_sus_norm"] == pytest.approx(sus)


# --------------------------------------------------------------------------- UEQ-S and UEQ items
UEQ_S_SOURCE = [("obstructive", "supportive"), ("complicated", "easy"), ("inefficient", "efficient"),
                ("confusing", "clear"), ("boring", "exciting"), ("not interesting", "interesting"),
                ("conventional", "inventive"), ("usual", "leading edge")]


def test_ueq_s_matches_source():
    qs = _set("ueq_s")["questions"]
    assert [(q["labels"][1], q["labels"][7]) for q in qs] == UEQ_S_SOURCE
    assert [q["scale"] for q in qs] == ["ueqs_pragmatic"] * 4 + ["ueqs_hedonic"] * 4
    assert not any(q.get("reverse") for q in qs)  # negative pole always left: nothing to reverse
    vals, _ = answer_values({"questions": qs}, {q["id"]: v for q, v in zip(qs, [7, 6, 5, 6, 3, 4, 2, 3])})
    # pragmatic (7 + 6 + 5 + 6) / 4 = 6 → +2 on the handbook's −3…+3; hedonic (3 + 4 + 2 + 3) / 4 = 3 → −1
    expected = {"scale_ueqs_pragmatic": 6.0, "scale_ueqs_hedonic": 3.0}
    for k, v in expected.items():
        assert vals[k] == pytest.approx(v), k
    assert vals["scale_ueqs_pragmatic"] - 4 == 2 and vals["scale_ueqs_hedonic"] - 4 == -1


UEQ_ITEMS = {2: ("not understandable", "understandable"), 5: ("valuable", "inferior"), 11: ("obstructive", "supportive"),
             12: ("good", "bad"), 13: ("complicated", "easy"), 20: ("inefficient", "efficient"),
             21: ("clear", "confusing"), 22: ("impractical", "practical")}
POSITIVE_LEFT = {5, 12, 21}


def test_ueq_eval_items_match_the_ueq():
    """The items and poles of ueq_eval are UEQ items and positive-left ones are reversed. (Its two scales are
    not UEQ scales, so the set is not marked validated; see the catalogue.)"""
    qs = _set("ueq_eval")["questions"]
    assert sorted((q["labels"][1], q["labels"][7]) for q in qs) == sorted(UEQ_ITEMS.values())
    for q in qs:
        n = next(k for k, v in UEQ_ITEMS.items() if v == (q["labels"][1], q["labels"][7]))
        assert bool(q.get("reverse")) is (n in POSITIVE_LEFT), q["id"]


def test_felt_heard_single_item_scale():
    spec = {"questions": _set("intention_to_use")["questions"]}
    vals, texts = answer_values(spec, {"use_again": 6, "felt_heard": 3, "agent_insights": "none"})
    # a one-item scale is that answer; norm (3 − 1) / 6
    expected = {"scale_felt_heard": 3.0, "scale_felt_heard_norm": 2 / 6, "scale_intention_to_use": 6.0}
    for k, v in expected.items():
        assert vals[k] == pytest.approx(v), k
    assert texts == {"agent_insights": "none"}


# --------------------------------------------------------------------------- NASA-TLX
TLX_SOURCE = [  # the NASA-TLX rating sheet: (subscale, question, left anchor, right anchor)
    ("Mental demand", "How mentally demanding was the task?", "Very low", "Very high"),
    ("Physical demand", "How physically demanding was the task?", "Very low", "Very high"),
    ("Temporal demand", "How hurried or rushed was the pace of the task?", "Very low", "Very high"),
    ("Performance", "How successful were you in accomplishing what you were asked to do?", "Perfect", "Failure"),
    ("Effort", "How hard did you have to work to accomplish your level of performance?", "Very low", "Very high"),
    ("Frustration", "How insecure, discouraged, irritated, stressed, and annoyed were you?", "Very low", "Very high"),
]


def test_nasa_tlx_matches_source():
    qs = _set("nasa_tlx")["questions"]
    assert len(qs) == 6
    for q, (name, text, lo, hi) in zip(qs, TLX_SOURCE):
        label, _, question = re.sub(r"[*_`]", "", q["text"]).partition(":")
        assert label.strip().lower() == name.lower()
        assert _words(question) == _words(text), q["id"]
        assert (q["labels"][1].lower(), q["labels"][7].lower()) == (lo.lower(), hi.lower()), q["id"]
        # every subscale runs towards more workload (Performance from perfect to failure): none is reversed,
        # and the scale is lower-is-better
        assert not q.get("reverse") and q["scale"] == "workload" and q["direction"] == "lower"
    # raw TLX: the unweighted mean of the six ratings. 3, 1, 5, 2, 4, 6 -> 21 / 6 = 3.5; 0–1: (3.5 − 1) / 6
    vals, _ = answer_values({"questions": qs}, {q["id"]: v for q, v in zip(qs, [3, 1, 5, 2, 4, 6])})
    expected = {"scale_workload": 3.5, "scale_workload_norm": 2.5 / 6}
    for k, v in expected.items():
        assert vals[k] == pytest.approx(v), k


# --------------------------------------------------------------------------- trust in automation (Jian et al.)
JIAN_SOURCE = [  # the checklist's 12 items; the first five are reverse scored; 1 = not at all … 7 = extremely
    "The system is deceptive.", "The system behaves in an underhanded manner.",
    "I am suspicious of the system's intent, action, or output.", "I am wary of the system.",
    "The system's action will have a harmful or injurious outcome.", "I am confident in the system.",
    "The system provides security.", "The system has integrity.", "The system is dependable.",
    "The system is reliable.", "I can trust the system.", "I am familiar with the system.",
]


def test_trust_in_automation_matches_source():
    qs = _set("trust_in_automation")["questions"]
    assert len(qs) == 12
    for i, (q, text) in enumerate(zip(qs, JIAN_SOURCE), 1):
        # "system" is the party the study evaluates: {{agent}}, the assistant or the opponent
        for party in ("assistant", "opponent"):
            shown = render(q["text"], {"agent": party, "Agent": party.capitalize()})
            assert _words(shown) == _words(text.replace("system", party)), f"item {i} ({party})"
        assert bool(q.get("reverse")) is (i <= 5), f"item {i}"
        assert (q["labels"][1], q["labels"][7]) == ("Not at all", "Extremely") and q["scale"] == "trust_automation"
    # the trust score is the mean of the 12 items with 1–5 reversed:
    # answers 2, 1, 3, 2, 1 -> 6, 7, 5, 6, 7; then 6, 5, 6, 6, 5, 6, 4 -> sum 31 + 38 = 69 -> 69 / 12 = 5.75
    raw = [2, 1, 3, 2, 1, 6, 5, 6, 6, 5, 6, 4]
    vals, _ = answer_values({"questions": qs}, {q["id"]: v for q, v in zip(qs, raw)})
    expected = {"scale_trust_automation": 5.75, "q_tia_deceptive": 6}
    for k, v in expected.items():
        assert vals[k] == pytest.approx(v), k
