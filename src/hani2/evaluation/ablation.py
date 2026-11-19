"""Ablations as diagnostics: which condition a negotiation ran in, and the gaps between conditions.

Every recording is put in one **condition** (the ``condition`` metric):

* ``team`` — a human negotiated with an Assistant (``oracle_team``: the Assistant knew the opponent's
  utility function, the ``opponent_utility`` capability);
* ``human_alone`` — a human negotiated without one: the no-Assistant control arm (the Assistant pool
  member ``none``);
* ``no_human`` — the Assistant drove the human's seat on autopilot for every action (``oracle_no_human``
  with the oracle): the Assistant's negotiation ceiling;
* ``negotiator_autopilot`` — a negotiator (not the Assistant) drove every action;
* ``mixed`` — autopilot took some of the seat's actions and the human the rest;
* ``assistant_off`` / ``assistant_error`` — the Assistant was switched off in the settings or failed to
  start (not a control: it was not assigned);
* ``unknown`` — a recording made before conditions were recorded.

The **ablation report** (:func:`ablation_report`) compares conditions cell by cell. A cell is a
combination of the ``cell`` fields (default: scenario × opponent × the human's side). For a gap
"A − B" it averages the
value within each cell and condition, takes A − B in every cell where both conditions were played and
averages over those cells (never the difference of pooled means, which mixes easy and hard cells):

* ``added_value`` = team − human_alone: what the Assistant adds to a human (the added-value score);
* ``through_human_loss`` = no_human − team: what the Assistant loses by working through a human;
* ``autopilot_vs_human`` = no_human − human_alone;
* ``information_gain`` = oracle_no_human − no_human: what knowing the opponent is worth (the
  information ceiling); ``oracle_team_gain`` = oracle_team − team.

With ``by`` (e.g. ``assistant``) every gap is given per Assistant: a gap between two conditions with
an Assistant compares that Assistant with itself, and ``human_alone`` is a baseline shared by all
of them, which is how an Assistant's added-value score is ranked.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Iterable

import numpy as np

from hani2.evaluation.base import Column as C
from hani2.evaluation.base import EvalContext, metric

__all__ = ["CONDITIONS", "GAPS", "condition_of", "ablation_report"]

ASSISTANT_DRIVER = "Assistant"
#: every condition label, in report order
CONDITIONS = ("human_alone", "team", "oracle_team", "no_human", "oracle_no_human", "negotiator_autopilot", "mixed",
              "assistant_off", "assistant_error", "unknown")
#: the conditions with an Assistant (split by ``by`` in the report; ``human_alone`` is a shared baseline)
WITH_ASSISTANT = frozenset({"team", "oracle_team", "no_human", "oracle_no_human"})
#: the gaps of the report: name -> (minuend, subtrahend, what it means)
GAPS: dict[str, tuple[str, str, str]] = {
    "added_value": ("team", "human_alone", "What the Assistant adds to a human (team − human alone)."),
    "through_human_loss": ("no_human", "team",
                           "What the Assistant loses by working through a human (autopilot − team)."),
    "autopilot_vs_human": ("no_human", "human_alone", "The Assistant alone against a human alone."),
    "information_gain": ("oracle_no_human", "no_human",
                         "What knowing the opponent's utility function is worth to the Assistant on autopilot."),
    "oracle_team_gain": ("oracle_team", "team", "What knowing the opponent's utility function is worth to a team."),
}


def condition_of(start: dict | None, acts: Iterable[dict], events: Iterable[dict] = ()) -> dict[str, Any]:
    """The condition of a negotiation from its ``start`` record, the actions on the human's seat and
    the recording's events (see the module docs)."""
    st = start or {}
    cond = st.get("condition")
    seat = [a for a in acts if a.get("type") in ("offer", "accept", "end", "text")]
    by = Counter(a.get("actor") for a in seat)
    n = len(seat)
    share = by["autopilot"] / n if n else 0.0
    driver = ""
    for e in events:
        if e.get("type") == "autopilot" and e.get("active"):
            driver = str(e.get("driver") or "")
    if not isinstance(cond, dict):
        return dict(condition="unknown", assistant_condition="", oracle=None, opponent_info_tools=None,
                    autopilot_driver=driver, autopilot_share=share if n else None)
    driver = driver or (str(cond.get("autopilot_driver") or "") if share else "")
    oracle = bool(cond.get("oracle"))
    assistant = str(cond.get("assistant") or "")
    if n and share >= 1.0 - 1e-9:
        if driver in (ASSISTANT_DRIVER, "Support Agent"):
            label = "oracle_no_human" if oracle else "no_human"
        else:
            label = "negotiator_autopilot"
    elif share > 0:
        label = "mixed"
    elif assistant == "none":
        label = "human_alone"
    elif assistant == "on":
        label = "oracle_team" if oracle else "team"
    elif assistant in ("off", "error"):
        label = f"assistant_{assistant}"
    else:
        label = "unknown"
    return dict(condition=label, assistant_condition=assistant, oracle=1 if oracle else 0,
                opponent_info_tools=1 if cond.get("opponent_info_tools") else 0, autopilot_driver=driver,
                autopilot_share=share if n else None)


@metric("condition", kind="hard", title="Condition (ablations)",
        formula=r"\text{share}_{\text{auto}} = \frac{\lvert A^{\text{seat}}_{\text{autopilot}} \rvert}{\lvert A^{\text{seat}} \rvert}",
        details=r"""
Which experimental condition the negotiation ran in, for the ablation report (`hani2 ablation
report`). It is read from the condition recorded when the negotiation started (whether an Assistant
ran or the session was assigned the no-Assistant arm, and whether the Assistant had the
`opponent_utility` oracle) and from who acted on the Human's seat: when the autopilot took every
action ($\text{share}_{\text{auto}} = 1$) the Human did not take part, and the driver recorded when
autopilot was switched on says whether the Assistant or a negotiator played.

The report compares conditions cell by cell (by default scenario × opponent × the Human's side). For a gap A − B it
averages the value within each cell and condition and takes the mean of A − B over the cells where
both were played:

$$\text{gap}_{A-B} = \frac{1}{\lvert K \rvert} \sum_{k \in K} \left(\bar v_{A,k} - \bar v_{B,k}\right)$$

with $K$ the cells played in both conditions. The *added value* of an Assistant is
team − human\_alone on `human_advantage`.
""", columns=[
    C("condition", "Condition", "team, human_alone, no_human, oracle_team, oracle_no_human, …",
      formula=r"\text{team} \mid \text{human\_alone} \mid \text{no\_human} \mid \text{oracle\_*} \mid \ldots",
      range="a label", higher_is_better=None, details=r"""
The experimental condition of the negotiation, from what was recorded when it started and who acted on
the Human's seat:

* `team` — a Human with an Assistant; `oracle_team` when the Assistant knew the Opponent's utility
  function (the `opponent_utility` capability);
* `human_alone` — the no-Assistant control arm (the Assistant pool member `none`);
* `no_human` — the Assistant drove *every* action of the Human's seat on autopilot; `oracle_no_human`
  with the opponent's utility function;
* `negotiator_autopilot` — a negotiator drove every action; `mixed` — autopilot took only some;
* `assistant_off` / `assistant_error` — the Assistant was switched off in the settings or failed to
  start; `unknown` — a recording from before conditions were recorded.

A Human who switched their Assistant off during the negotiation still counts as `team`: the condition
is what was assigned, not what was used (see `system_use` for that).
"""),
    C("assistant_condition", "Assistant", "on, none, off or error (as assigned)", range="a label",
      formula=r"\text{on} \mid \text{none} \mid \text{off} \mid \text{error}",
      higher_is_better=None, details=r"""
Whether an Assistant ran (`on`), the session was assigned the no-Assistant arm (`none`), the
Assistant was switched off in the settings (`off`) or it failed to start (`error`).
"""),
    C("oracle", "Oracle", "1 when the Assistant knew the opponent's utility function",
      formula=r"\mathbb{1}\left[\text{opponent\_utility granted}\right]", range="0 or 1", higher_is_better=None,
      details=r"""
1 when the Assistant had the admin-only `opponent_utility` capability: the Opponent's preferences and
its utility of every offer were in the Assistant's view of the negotiation.
"""),
    C("opponent_info_tools", "Opponent info in tools", "1 when the Human's tools could show the opponent's utilities",
      formula=r"\mathbb{1}\left[\text{tools show } u_o\right]", range="0 or 1", higher_is_better=None, details=r"""
1 when the Human's tools could show the Opponent's utilities (admins, or env.json
`tools.show_opponent_utility`). Such sessions are left out of the ablation report by default: the
Human (and the Assistant through the tools) had information the condition does not say.
"""),
    C("autopilot_driver", "Autopilot driver", "Who drove the seat on autopilot", range="a name",
      formula=r"\text{the driver when autopilot was last switched on}",
      higher_is_better=None, details=r"""
The autopilot driver (`Assistant` or a negotiator's name); empty when autopilot never acted.
"""),
    C("autopilot_share", "Autopilot share", "Share of the seat's actions taken by autopilot",
      formula=r"\frac{\lvert A^{\text{seat}}_{\text{autopilot}} \rvert}{\lvert A^{\text{seat}} \rvert}", range="[0, 1]",
      higher_is_better=None, details=r"""
The share of the Human seat's actions the autopilot took (1 for `no_human`, 0 for a Human negotiating
themselves).
"""),
])
def condition(ctx: EvalContext, options: dict) -> dict:
    """The experimental condition of the negotiation (for ablations): team, human alone, the Assistant on
    autopilot, with or without the opponent's utility function."""
    return condition_of(ctx.rec.start, ctx.acts, ctx.rec.of("ev"))


# --------------------------------------------------------------------------- #
# The report                                                                   #
# --------------------------------------------------------------------------- #
def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if math.isfinite(float(v)) else None


def _cell_means(rows: list[dict], cell: tuple[str, ...], value: str) -> dict[tuple, tuple[float, int]]:
    acc: dict[tuple, list[float]] = {}
    for r in rows:
        v = _num(r.get(value))
        if v is not None:
            acc.setdefault(tuple(str(r.get(c)) for c in cell), []).append(v)
    return {k: (float(np.mean(v)), len(v)) for k, v in acc.items()}


def _gap(a: dict[tuple, tuple[float, int]], b: dict[tuple, tuple[float, int]], cell: tuple[str, ...]) -> dict:
    common = sorted(set(a) & set(b))
    diffs = [a[k][0] - b[k][0] for k in common]
    out: dict[str, Any] = dict(cells=len(common), n_a=sum(a[k][1] for k in common),
                               n_b=sum(b[k][1] for k in common), cells_a_only=len(set(a) - set(b)),
                               cells_b_only=len(set(b) - set(a)))
    if diffs:
        sd = float(np.std(diffs, ddof=1)) if len(diffs) > 1 else None
        out.update(gap=float(np.mean(diffs)), sd=sd, se=sd / math.sqrt(len(diffs)) if sd is not None else None,
                   a=float(np.mean([a[k][0] for k in common])), b=float(np.mean([b[k][0] for k in common])),
                   per_cell=[dict(zip(cell, k), a=a[k][0], b=b[k][0], gap=a[k][0] - b[k][0], n_a=a[k][1], n_b=b[k][1])
                             for k in common])
    else:
        out.update(gap=None, sd=None, se=None, a=None, b=None, per_cell=[])
    return out


def ablation_report(rows: list[dict], *, value: str = "human_advantage",
                    cell: Iterable[str] = ("scenario", "opponent", "human_index"), by: str | None = None,
                    include_practice: bool = False, include_opponent_info: bool = False,
                    off_is_control: bool = False) -> dict:
    """The ablation gaps (see the module docs) of evaluation rows that have the ``condition`` metric.

    ``value`` is the column compared (default ``human_advantage``; a negotiation without a deal counts
    with its value, 0 advantage, not dropped). ``cell`` are the fields that make a cell. ``by``
    (e.g. ``assistant``) gives one row per value of that field: both sides of a gap between two
    conditions with an Assistant are that Assistant's; ``human_alone`` is the shared baseline. Practice rounds and sessions whose
    tools showed the opponent's utilities are left out unless asked for. ``off_is_control`` counts
    sessions whose Assistant was switched off in the settings (``assistant_off``, e.g. a separate study
    made with ``hani2 experiment create --no-assistant``) as ``human_alone``."""
    cell = tuple(cell)
    kept, dropped = [], Counter()
    for r in rows:
        if not include_practice and r.get("practice"):
            dropped["practice"] += 1
        elif not include_opponent_info and r.get("opponent_info_tools"):
            dropped["opponent_info_tools"] += 1
        elif r.get("condition") is None:
            dropped["no condition column"] += 1
        else:
            if off_is_control and r.get("condition") == "assistant_off":
                r = dict(r, condition="human_alone")
            kept.append(r)
    by_cond: dict[str, list[dict]] = {}
    for r in kept:
        by_cond.setdefault(str(r.get("condition")), []).append(r)
    conditions = []
    for c in sorted(by_cond, key=lambda x: CONDITIONS.index(x) if x in CONDITIONS else 99):
        vals = [v for v in (_num(r.get(value)) for r in by_cond[c]) if v is not None]
        conditions.append(dict(condition=c, n=len(by_cond[c]), mean=float(np.mean(vals)) if vals else None,
                               cells=len(_cell_means(by_cond[c], cell, value))))
    means = {c: _cell_means(rs, cell, value) for c, rs in by_cond.items()}

    def split(c: str) -> dict[str, dict]:
        groups: dict[str, list[dict]] = {}
        for r in by_cond.get(c, []):
            groups.setdefault(str(r.get(by)), []).append(r)
        return {g: _cell_means(rs, cell, value) for g, rs in groups.items()}

    gaps = []
    for name, (a, b, meaning) in GAPS.items():
        if by and a in WITH_ASSISTANT:
            sa = split(a)
            sb = split(b) if b in WITH_ASSISTANT else None  # both sides one Assistant; else a shared baseline
            for g in sorted(set(sa) | set(sb or {})):
                gaps.append(dict(gap_name=name, a_condition=a, b_condition=b, group=g, meaning=meaning,
                                 **_gap(sa.get(g, {}), (sb or {}).get(g, {}) if sb is not None else means.get(b, {}),
                                        cell)))
        else:
            gaps.append(dict(gap_name=name, a_condition=a, b_condition=b, group="", meaning=meaning,
                             **_gap(means.get(a, {}), means.get(b, {}), cell)))
    return dict(value=value, cell=list(cell), by=by, conditions=conditions, gaps=gaps, dropped=dict(dropped),
                n=len(kept))
