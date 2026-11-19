"""Combined scores: a few numbers in [0, 1] that summarise a session for the
two competition tracks.

* **HAN** (Human-Agent Negotiation, no Assistant) ranks Opponent agents:
  ``han_outcome`` (what the agent obtained) and ``han_interaction`` (how well it
  behaved as an opponent: the participant's impressions, the judge, no failures).
* **HI** (Hybrid Intelligence, with an Assistant) ranks Assistants:
  ``hi_outcome`` (what the human–Assistant team obtained) and
  ``hi_interaction``, the mean of ``hi_assistant`` (how well it worked as an
  Assistant) and ``hi_team`` (how well the team worked: reliance, errors,
  efficiency).

A score is a weighted mean of normalised components; components without a
value are left out and ``<score>_coverage`` is the share of the weight that was
present. Change the weights in ``env.json``::

    {"evaluation": {"scores": {"hi_assistant": {"weights": {"ja_overall": 2, "fn_success_rate": 0}}}}}

(a weight of 0 drops a component) or with the metric option ``scores``.
:func:`hani2.evaluation.leaderboard` ranks the entrants of a track.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from hani2.evaluation.base import Column, EvalContext, metric, num

#: normalisers: raw value -> [0, 1] (higher is better)
NORMALISERS: dict[str, tuple[str, str, Any]] = {
    "unit": ("the value, clipped to [0, 1]", r"\min(1, \max(0, x))", lambda x: min(1.0, max(0.0, x))),
    "likert7": ("a 1–7 rating mapped to [0, 1]", r"(x - 1) / 6", lambda x: min(1.0, max(0.0, (x - 1) / 6))),
    "advantage": ("an advantage clipped to [0, 1] (no better than no deal = 0)", r"\min(1, \max(0, x))",
                  lambda x: min(1.0, max(0.0, x))),
    "inverse": ("one minus a [0, 1] value where lower is better (e.g. a 0/1 flag)", r"1 - \min(1, \max(0, x))",
                lambda x: 1.0 - min(1.0, max(0.0, x))),
    "count": ("a count where lower is better", r"1 / (1 + x)", lambda x: 1.0 / (1.0 + max(0.0, x))),
}


@dataclass
class Component:
    column: str
    weight: float
    norm: str = "unit"
    label: str = ""


@dataclass
class Score:
    name: str
    title: str
    track: str  # "han" or "hi"
    board: str  # "outcome" or "interaction"
    description: str
    components: list[Component]
    details: str = ""
    #: columns that, when 1, force the score to 0 (e.g. the opponent failed)
    zero_if: list[str] = field(default_factory=list)
    #: only for sessions with an Assistant (empty otherwise)
    needs_assistant: bool = False


def _c(col, w, norm="unit", label=""):
    return Component(col, w, norm, label)


SCORES: list[Score] = [
    Score("han_outcome", "HAN outcome", "han", "outcome",
          "What the Opponent agent obtained against the Human (Human-Agent Negotiation track)",
          [_c("opponent_advantage", 1, "advantage", "the Opponent's advantage")],
          zero_if=["opponent_failed"],
          details=r"""
The outcome board of the Human-Agent Negotiation track ranks Opponent agents by the share of their
largest possible gain over no deal that they obtained against human participants. No deal scores 0,
and so does a session that the agent ended by failing.
"""),
    Score("han_interaction", "HAN interaction", "han", "interaction",
          "How well the Opponent agent behaved as an opponent (Human-Agent Negotiation track)",
          [_c("scale_opponent_kindness_norm", 1, label="questionnaire: kindness"),
           _c("scale_opponent_intelligence_norm", 1, label="questionnaire: intelligence"),
           _c("scale_opponent_humanlike_norm", 1, label="questionnaire: human-likeness"),
           _c("scale_relationship_norm", 1, label="questionnaire: wanting to negotiate again"),
           _c("scale_satisfaction_norm", 0.5, label="questionnaire: the participant's satisfaction"),
           _c("jo_overall", 1, "likert7", "judge: overall"),
           _c("jo_communication", 0.5, "likert7", "judge: communication"),
           _c("jo_consistency", 0.5, "likert7", "judge: consistency"),
           _c("jo_human_likeness", 0.5, "likert7", "judge: human-likeness"),
           _c("opponent_failed", 1, "inverse", "did not fail"),
           _c("opponent_irrational_accept", 0.5, "inverse", "did not accept below its reservation value")],
          details=r"""
The interaction board of the Human-Agent Negotiation track: how the participants experienced the
agent (questionnaire), how a language-model judge rates its behaviour and messages, and whether it
negotiated soundly (no failure, no deal accepted below its own reservation value).
"""),
    Score("hi_outcome", "HI outcome", "hi", "outcome",
          "What the human–Assistant team obtained (Hybrid Intelligence track)",
          [_c("human_advantage", 1, "advantage", "the Human side's advantage")],
          details=r"""
The outcome board of the Hybrid Intelligence track ranks Assistants by the share of the largest
possible gain over no deal that the team (the Human with the Assistant) obtained. No deal scores 0.
"""),
    Score("hi_assistant", "HI Assistant", "hi", "interaction",
          "How well the Assistant worked as an Assistant (Hybrid Intelligence track)",
          [_c("ja_overall", 1, "likert7", "judge: overall"),
           _c("ja_helpfulness", 0.5, "likert7", "judge: helpfulness"),
           _c("ja_autonomy_respect", 0.5, "likert7", "judge: left the Human in control"),
           _c("assertions_met", 1, label="judge: assertions met"),
           _c("task_communicated", 1, label="judge: scenario facts conveyed"),
           _c("assistant_critical_errors", 1, "count", "judge: critical errors"),
           _c("assistant_errors", 0.5, "count", "judge: errors"),
           _c("irrational_suggestions", 1, "count", "suggestions below the reservation value"),
           _c("fn_success_rate", 0.5, label="function calls that worked"),
           _c("unanswered_messages", 0.5, "count", "unanswered messages"),
           _c("scale_ueq_pragmatic_norm", 0.5, label="questionnaire: UEQ pragmatic quality"),
           _c("scale_tam_usefulness_norm", 0.5, label="questionnaire: usefulness"),
           _c("scale_felt_heard_norm", 0.5, label="questionnaire: felt heard"),
           _c("scale_intention_to_use_norm", 0.5, label="questionnaire: would use it again")],
          needs_assistant=True,
          details=r"""
The Assistant itself: how a language-model judge rates its help, whether it conveyed what the
scenario requires and met the assertions, its errors, unsound suggestions, technical reliability and
responsiveness, and how the participant experienced it.
"""),
    Score("hi_team", "HI team", "hi", "interaction",
          "How well the human–Assistant team worked together (Hybrid Intelligence track)",
          [_c("human_overrode_harmfully", 1, "count", "judge: harmful overrides of the Assistant"),
           _c("human_critical_errors", 1, "count", "judge: the Human's critical errors"),
           _c("jh_use_of_assistant", 1, "likert7", "judge: use of the Assistant"),
           _c("jh_engagement", 0.5, "likert7", "judge: engagement"),
           _c("always_follows", 0.5, "inverse", "did not blindly follow every suggestion"),
           _c("click_through", 0.5, "inverse", "did not click through"),
           _c("irrational_accept", 1, "inverse", "did not accept below the reservation value"),
           _c("welfare_optimality", 0.5, label="efficiency of the result")],
          needs_assistant=True,
          details=r"""
The team: appropriate reliance on the Assistant (neither ignoring it harmfully nor following it
blindly), the Human's engagement and critical errors, a sound final decision and an efficient result.
"""),
    Score("hi_interaction", "HI interaction", "hi", "interaction",
          "The Assistant and the team together: the ranked score of the HI interaction board",
          [_c("hi_assistant", 1, label="the HI Assistant score"), _c("hi_team", 1, label="the HI team score")],
          needs_assistant=True,
          details=r"""
The interaction board of the Hybrid Intelligence track ranks Assistants by the mean of how well they
worked as an Assistant (`hi_assistant`) and how well their teams worked (`hi_team`).
"""),
]
BY_NAME = {s.name: s for s in SCORES}


def _weights(score: Score, options: dict | None) -> dict[str, float]:
    """The components' weights after the overrides of ``env.json`` and ``options``."""
    from hani2.config import get_env

    w = {c.column: float(c.weight) for c in score.components}
    for src in (get_env("evaluation.scores", None), (options or {}).get("scores")):
        if isinstance(src, dict) and isinstance(src.get(score.name), dict):
            for k, v in (src[score.name].get("weights") or {}).items():
                if k in w and num(v) is not None:
                    w[k] = float(v)
    return w


def compute(score: Score, row: dict, *, options: dict | None = None, only: set[str] | None = None) -> tuple[float | None, float | None]:
    """``(score, coverage)`` of one row; ``only`` restricts the components."""
    w = _weights(score, options)
    if score.needs_assistant and str(row.get("support_agent") or "none") == "none":
        return None, None
    if any(num(row.get(z)) == 1 for z in score.zero_if):
        return 0.0, 1.0
    total = got = acc = 0.0
    for c in score.components:
        wt = w.get(c.column, 0.0)
        if wt <= 0 or (only is not None and c.column not in only):
            continue
        total += wt
        x = num(row.get(c.column))
        if x is None:
            continue
        acc += wt * float(NORMALISERS[c.norm][2](x))
        got += wt
    if got <= 0:
        return None, (0.0 if total > 0 else None)
    v = acc / got
    return (v if math.isfinite(v) else None), got / total


def score_row(row: dict, options: dict | None = None, only: dict[str, set[str]] | None = None) -> dict:
    """Every score (and its coverage) of a row, in order (scores of scores see
    the earlier ones). ``only`` restricts the components per score."""
    r = dict(row)
    out: dict[str, Any] = {}
    for s in SCORES:
        v, cov = compute(s, r, options=options, only=(only or {}).get(s.name))
        r[s.name] = v
        out[s.name], out[f"{s.name}_coverage"] = v, cov
    return out


# --------------------------------------------------------------------------- #
# The metric (and its reference texts, generated from the definitions)         #
# --------------------------------------------------------------------------- #
def _score_details(s: Score) -> str:
    rows = "\n".join(f"| `{c.column}` | {c.label} | {c.weight:g} | {NORMALISERS[c.norm][0]}: ${NORMALISERS[c.norm][1]}$ |"
                     for c in s.components)
    zero = (f"\n\nThe score is 0 when {', '.join(f'`{z}`' for z in s.zero_if)} is 1." if s.zero_if else "")
    if s.needs_assistant:
        zero += "\n\nEmpty for sessions without an Assistant."
    return (s.details.strip() + "\n\n| Component | What | Weight | Normalised as |\n| --- | --- | --- | --- |\n" + rows
            + zero + "\n\nComponents without a value are left out (see `" + s.name + "_coverage`).")


def _columns() -> list[Column]:
    out = []
    for s in SCORES:
        out.append(Column(s.name, s.title, s.description, True,
                          formula=r"S = \frac{\sum_{i \in P} w_i\, \phi_i(x_i)}{\sum_{i \in P} w_i}", range="[0, 1]",
                          details=_score_details(s)))
        out.append(Column(f"{s.name}_coverage", f"{s.title} coverage", f"Share of the weight of {s.name} that had a value",
                          True, formula=r"\frac{\sum_{i \in P} w_i}{\sum_{i} w_i}", range="[0, 1]",
                          details=f"""
The share of the total weight of `{s.name}` whose components had a value in this session: 1 when
every component was measured, lower when (for example) there was no questionnaire or no judge.
Compare scores only between sessions with similar coverage; the leaderboards use the same
components for every entrant.
"""))
    return out


@metric("scores", kind="score", title="Combined scores (HAN and HI tracks)", stage=2,
        requires=["outcome", "optimality", "rule_checks", "system_use", "engagement_flags", "assistant_interaction",
                  "task_success"],
        options={"scores": "Weight overrides: {score: {weights: {column: weight}}} (0 drops a component)."},
        formula=r"S = \frac{\sum_{i \in P} w_i\, \phi_i(x_i)}{\sum_{i \in P} w_i}, \qquad P = \{i : x_i \text{ has a value}\}",
        details=r"""
A few numbers in $[0, 1]$ (higher is better) that summarise a session for the two competition tracks.
Each is a weighted mean of components $x_i$ taken from the other metrics, each normalised to $[0, 1]$
by $\phi_i$ (ratings of 1–7 become $(x - 1)/6$, error counts $1/(1 + x)$, flags $1 - x$). Components
without a value (no questionnaire, no language-model judge) are left out, and the coverage column tells
how much of the weight was present.

* **Human-Agent Negotiation** (no Assistant; the entrants are Opponent agents): `han_outcome` (what the
  agent obtained) and `han_interaction` (how well it behaved as an opponent).
* **Hybrid Intelligence** (with an Assistant; the entrants are Assistants): `hi_outcome` (what the team
  obtained) and `hi_interaction`, the mean of `hi_assistant` (how well it worked as an Assistant) and
  `hi_team` (how well the team worked).

Change the weights with `env.json` `evaluation.scores` or the option `scores`. The
[leaderboards](evaluation.md#tracks-and-leaderboards) rank entrants by these scores.

**Example.** `hi_outcome` of a session with `human_advantage` $= 0.375$ is $0.375$. A session with
`ja_overall` $= 6$ (normalised $5/6$) and one critical Assistant error (normalised $1/2$), and no other
component of `hi_assistant`, has `hi_assistant` $= (1 \cdot 5/6 + 1 \cdot 1/2)/2 = 0.667$ and a coverage
of $2/9.5 = 0.21$.
""", columns=_columns())
def scores(ctx: EvalContext, options: dict) -> dict:
    """The combined scores of the HAN and HI tracks, from the other metrics."""
    return score_row(ctx.row, options)
