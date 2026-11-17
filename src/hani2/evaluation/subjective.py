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


@metric("questionnaire", kind="subjective", title="Questionnaire", columns=[
    *[C(f"scale_{k}", k.replace("_", " ").capitalize(), v, True) for k, v in SCALES.items()],
    C("questionnaire_answered", "Answered", "1 if the participant answered the questionnaire"),
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
