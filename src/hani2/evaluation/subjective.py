"""Subjective metrics: the participant's own answers to the questionnaire.

Questions carry ``scale`` (the score they belong to) and optionally
``reverse: true``; see ``default_settings/questionnaires/evaluation.yaml``.
Every scale becomes a column ``scale_<name>`` (mean of its items on the
item's own range) and ``scale_<name>_norm`` (rescaled to 0–1). Numeric
answers to questions without a scale become ``q_<id>``.
"""

from __future__ import annotations

from hani2.evaluation.base import Column as C
from hani2.evaluation.base import EvalContext, metric, num

_RANGES = {"likert5": (1, 5), "likert7": (1, 7), "yes_no": (0, 1)}

#: well-known scales and their descriptions (others are named after the YAML)
SCALES = {
    "satisfaction": "Satisfaction with the outcome",
    "appreciation": "Enjoyment of the negotiation",
    "ueq_pragmatic": "UEQ pragmatic quality of the assistant: perspicuity (understandable, easy, clear), efficiency (efficient, practical) and dependability (supportive) items",
    "ueq_hedonic": "UEQ items on the assistant's value and overall impression (valuable — a stimulation item; good — an attractiveness item)",
    "tam_usefulness": "TAM perceived usefulness of the assistant",
    "intention_to_use": "Intention to use the assistant again",
    "felt_heard": "Feeling heard by the assistant",
    "opponent_kindness": "Perceived kindness of the opponent",
    "opponent_intelligence": "Perceived intelligence of the opponent",
    "opponent_humanlike": "Belief that the opponent was human",
    "relationship": "Wish to negotiate again / feeling connected to the opponent",
}


def _value(q: dict, a) -> tuple[float | None, float, float]:
    lo, hi = _RANGES.get(str(q.get("type")), (q.get("min", 1), q.get("max", 7)))
    lo, hi = float(q.get("min", lo)), float(q.get("max", hi))
    if q.get("type") == "yes_no":
        if isinstance(a, str):
            a = {"yes": 1, "no": 0, "true": 1, "false": 0}.get(a.strip().lower(), a)
        v = num(1 if a is True else 0 if a is False else a)
    elif q.get("type") == "select" and isinstance(a, str) and q.get("options"):
        opts = [str(o) for o in q["options"]]
        v = float(opts.index(a) + 1) if a in opts else None
        lo, hi = 1.0, float(len(opts))
    else:
        v = num(a)
    if v is not None and q.get("reverse"):
        v = lo + hi - v
    return v, lo, hi


#: the items of the well-known scales in the bundled evaluation questionnaire (``evaluation.yaml``)
SCALE_ITEMS = {
    "satisfaction": "“How satisfied are you with the outcome of this negotiation?” (1–7).",
    "appreciation": "“How much did you enjoy this negotiation?” (1–7).",
    "ueq_pragmatic": ("Six 7-point semantic differentials of the User Experience Questionnaire (UEQ, Laugwitz, Held and "
                      "Schrepp, 2008) about the Assistant: not understandable–understandable, obstructive–supportive, "
                      "complicated–easy, inefficient–efficient, impractical–practical and clear–confusing (reversed)."),
    "ueq_hedonic": ("Two 7-point UEQ differentials about the Assistant, both reversed because the positive pole comes "
                    "first: valuable–inferior and good–bad."),
    "tam_usefulness": ("Perceived usefulness from the Technology Acceptance Model (TAM, Davis, 1989): “Using this assistant "
                       "would enhance my effectiveness in negotiation” and “I would find this assistant useful in "
                       "negotiations” (1 = strongly disagree … 7 = strongly agree)."),
    "intention_to_use": "“I would use this assistant again” (1–7).",
    "felt_heard": "“I felt heard by the assistant (it took my wishes into account)” (1–7).",
    "opponent_kindness": "“How kind was your opponent?” (1 = not at all … 7 = very).",
    "opponent_intelligence": "“How intelligent was your opponent?” (1 = not at all … 7 = very).",
    "opponent_humanlike": "“Do you think your opponent was a human or an AI?” (1 = surely an AI … 7 = surely a human).",
    "relationship": ("“I would like to negotiate with this opponent again” and “I felt humanly connected to the other "
                     "party” (1 = strongly disagree … 7 = strongly agree)."),
}

_SCALE_F = r"Q_{%s} = \frac{1}{\lvert S \rvert} \sum_{i \in S} v'_i, \qquad v'_i = \begin{cases} \ell_i + h_i - v_i & \text{reversed item} \\ v_i & \text{otherwise} \end{cases}"
_NORM_F = r"\hat Q_{%s} = \frac{1}{\lvert S \rvert} \sum_{i \in S} \frac{v'_i - \ell_i}{h_i - \ell_i}"
_SCALE_D = ("The mean answer to the items $S$ of the scale **{name}**, on the items' own range (1–7 for 7-point items; "
            "reversed items scored backwards). Higher means more of what the scale measures. {items} "
            "Empty when the participant answered none of its items (e.g. questions about the Assistant when there "
            "was none). See `scale_{name}_norm` for the 0–1 version.")
_NORM_D = ("The same scale rescaled to $[0, 1]$ item by item ($0$ = the lowest answer, $1$ = the highest), so scales "
           "and items with different ranges can be compared. For a 7-point item, $(v' - 1)/6$.")


def _scale_cols() -> list:
    out = []
    for k, v in SCALES.items():
        out.append(C(f"scale_{k}", k.replace("_", " ").capitalize(), v, True, formula=_SCALE_F % (r"\text{%s}" % k.replace("_", r"\_")),
                     range="the items' range (1–7)",
                     details=_SCALE_D.format(name=k, items=f"Items in the bundled questionnaire: {SCALE_ITEMS[k]}")))
        out.append(C(f"scale_{k}_norm", f"{k.replace('_', ' ').capitalize()} (0–1)", f"{v}, rescaled to 0–1", True,
                     formula=_NORM_F % (r"\text{%s}" % k.replace("_", r"\_")), range="[0, 1]", details=_NORM_D))
    return out


@metric("questionnaire", kind="subjective", title="Questionnaire",
        formula=r"Q_s = \frac{1}{\lvert S_s \rvert} \sum_{i \in S_s} v'_i, \qquad \hat Q_s = \frac{1}{\lvert S_s \rvert} \sum_{i \in S_s} \frac{v'_i - \ell_i}{h_i - \ell_i}",
        details=r"""
The participant's own view, from the questionnaire answered after the negotiation: satisfaction,
usability and usefulness of the Assistant, intention to use it again, and how they saw the Opponent.

Every question with `scale: <name>` belongs to the scale $S$ of that name. An answer $v_i$ to item $i$
lies in the item's range $[\ell_i, h_i]$: 1–5 for `likert5`, 1–7 for `likert7`, 0–1 for `yes_no`
(yes = 1), the option's position $1, \dots, n$ for `select`, or the question's own `min` / `max`.
Items marked `reverse: true` are scored backwards, $v'_i = \ell_i + h_i - v_i$, so that higher always
means more of the scale. A scale's score is the mean of its answered items; its normalised score
rescales each item to $[0, 1]$ first.

**Example** (`ueq_pragmatic`, six 7-point items): answers 6 (understandable), 5 (supportive),
6 (easy), 5 (efficient), 2 on clear–confusing (reversed: $1 + 7 - 2 = 6$) and 5 (practical) give
$Q = 33/6 = 5.5$ and $\hat Q = (5.5 - 1)/6 = 0.75$.

**Reading the scales.** UEQ items are usually reported on $-3 \dots +3$; subtract 4 from a 1–7 score to
compare with UEQ benchmarks. Scales with a single item are just that answer. Free-text answers are in
the details, not in columns.

**Caveats.** The scores mean what the questionnaire's items ask; with your own questionnaire the
scale names are yours. Items of different ranges in one scale are averaged on their raw values
(use the normalised score to compare them).
""", columns=[
    *_scale_cols(),
    C("questionnaire_answered", "Answered", "1 if the participant answered the questionnaire",
      formula=r"\mathbb{1}\left[\text{questionnaire submitted}\right]", range="0 or 1",
      details=r"""
1 when the participant submitted the questionnaire. When it is 0 the scale columns are empty.
"""),
], patterns=[
    C("scale_<name>_norm", "<name> (0–1)", "Any other scale of the questionnaire, rescaled to 0–1", True,
      formula=_NORM_F % "s", range="[0, 1]",
      details="A scale defined by your questionnaire (`scale: <name>`), rescaled to $[0, 1]$ item by item. " + _NORM_D),
    C("scale_<name>", "<name>", "Any other scale of the questionnaire (mean of its items)", True,
      formula=_SCALE_F % "s", range="the items' range",
      details=("The mean answer to the items of a scale defined by your questionnaire (`scale: <name>`), on the items' "
               "own range with reversed items (`reverse: true`) scored backwards.")),
    C("q_<id>", "<id>", "The numeric answer to a question without a scale",
      formula=r"v'_{\text{id}}", range="the question's range",
      details=("The answer to the question with this `id` when it belongs to no scale: the number for rating "
               "questions, 1/0 for yes/no, the option's position for a choice, reversed when `reverse: true`.")),
])
def questionnaire(ctx: EvalContext, options: dict) -> dict:
    """Scale scores (UEQ, TAM, intention to use, opponent perception, …) and
    single answers from the post-negotiation questionnaire."""
    q = ctx.rec.questionnaire
    if q is None:
        return dict(questionnaire_answered=0)
    spec = q.get("spec") or {}
    answers = q.get("answers") or {}
    out: dict = {"questionnaire_answered": 1}
    scales: dict[str, list[tuple[float, float, float]]] = {}
    texts = {}
    for item in spec.get("questions", []):
        qid = item.get("id")
        if qid not in answers:
            continue
        a = answers[qid]
        if item.get("type") == "text":
            if a:
                texts[qid] = a
            continue
        v, lo, hi = _value(item, a)
        if v is None:
            continue
        if item.get("scale"):
            scales.setdefault(str(item["scale"]), []).append((v, lo, hi))
        else:
            out[f"q_{qid}"] = v
    for name, vals in scales.items():
        out[f"scale_{name}"] = sum(v for v, _, _ in vals) / len(vals)
        out[f"scale_{name}_norm"] = sum((v - lo) / (hi - lo) if hi > lo else 0.0 for v, lo, hi in vals) / len(vals)
    out["_details"] = dict(answers=answers, texts=texts)
    return out
