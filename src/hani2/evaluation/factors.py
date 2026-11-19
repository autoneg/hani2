"""The ``factors`` metric: difficulty factors and target attainment of compositional scenarios."""

from __future__ import annotations

from typing import Any

from hani2.evaluation.base import Column as C
from hani2.evaluation.base import EvalContext, metric, num

_FACTOR_DOC = {
    "issues": ("Issues", "Number-of-issues level (2, 4 or 6)",
               "The number of negotiated issues of the scenario."),
    "opposition": ("Opposition level", "Opposition level (low, medium, high)",
                   "How opposed the two preference profiles are: the opposition level (the distance from the best "
                   "outcome to the ideal point $(1, 1)$) falls in the band of the level."),
    "zopa": ("ZOPA level", "ZOPA-size level (wide, narrow)",
             "The share of outcomes that both sides prefer to no deal, set through the reservation values."),
    "constraint": ("Constraint level", "Hidden-constraint level (none, hidden)",
                   "**hidden**: the participant has a private hard limit that the opponent does not know (the "
                   "opponent's favourite option on its most important issue is worth less than no deal)."),
    "deception": ("Deception level", "Opponent honesty (honest, deceptive)",
                  "The opponent actually played: **honest** or **deceptive** (it lies about its priorities, its "
                  "deadline and its outside option) when it is one of the factor's opponents, otherwise its name."),
    "time_pressure": ("Time-pressure level", "Time-pressure level (relaxed, tight)",
                      "The step limit actually used: the level whose step count matches, otherwise `steps=<n>`."),
}


def _cols() -> list[C]:
    cols = [C(f"factor_{k}", t, d, None, formula=rf"\text{{level of {k.replace('_', ' ')}}}", range="level name",
              details=det + "\n\nEmpty for a scenario that was not composed from factors.")
            for k, (t, d, det) in _FACTOR_DOC.items()]
    cols += [
        C("target_attainment", "Target attainment", "Gain over the reservation value relative to the target's", True,
          formula=r"\frac{u_h(\omega) - r_h}{u_h(\omega^\ast) - r_h}", range="(-inf, inf); 1 = the target",
          details=r"""
The human team's gain over its reservation value $r_h$, as a share of the gain the **target** deal
$\omega^\ast$ would give. The target is the Nash bargaining solution over the zone of possible
agreement (respecting the participant's hidden constraint), stored in the scenario when it was composed.

1 means the team got as much as the target, above 1 more (at the opponent's expense), 0 the
reservation value (no deal), below 0 a deal worse than no deal (for example one that breaks the hidden
constraint). Because it is normalised by the target, it compares fairly across scenarios of different
difficulty, unlike the raw utility.

**Example.** $r_h = 0.2$, the target gives $0.6$ and the deal $0.5$: $(0.5 - 0.2) / (0.6 - 0.2) = 0.75$.
"""),
        C("reached_target", "Reached target", "1 if the deal is at least as good as the target for the human", True,
          formula=r"\mathbb{1}\left[u_h(\omega) \ge u_h(\omega^\ast)\right]", range="{0, 1}",
          details=r"""
1 when the human team's utility is at least the target's (see `target_attainment`), 0 otherwise
(including no deal).
"""),
        C("constraint_violated", "Constraint violated", "1 if the deal breaks the hidden constraint", False,
          formula=r"\mathbb{1}\left[\omega_j = v^\dagger\right]", range="{0, 1}",
          details=r"""
For a scenario with a hidden constraint ($v^\dagger$ is the forbidden option of issue $j$): 1 when the
agreement uses the forbidden option, 0 otherwise (no deal counts as 0). Empty for scenarios without a
hidden constraint.
"""),
    ]
    return cols


def _level(fname: str, cell: dict, start: dict) -> Any:
    from hani2.compositional import FACTORS

    f = FACTORS.get(fname)
    if f is None:
        return cell.get(fname)
    if fname == "deception":
        opp = str(start.get("opponent") or "")
        for lv, spec in f.levels.items():
            if opp and (opp == spec or opp == str(spec).split(".")[-1]):
                return lv
        return opp or cell.get(fname)
    if fname == "time_pressure":
        n = start.get("n_steps")
        if n is None:
            return cell.get(fname)
        for lv, steps in f.levels.items():
            if int(n) == int(steps):
                return lv
        return f"steps={int(n)}"
    return cell.get(fname)


@metric("factors", kind="hard", title="Difficulty factors", default=False,
        formula=r"\text{levels}(\sigma), \qquad \frac{u_h(\omega) - r_h}{u_h(\omega^\ast) - r_h}",
        details=r"""
For scenarios composed from difficulty factors (`hani2 compose`): the level of every factor and how
close the result came to the scenario's **target** deal $\omega^\ast$ (the Nash bargaining solution over the
zone of possible agreement). Scenario factors (issues, opposition, ZOPA, constraint) are read from the
scenario; episode factors (deception, time pressure) from what was actually played, so a study that
overrides the opponent or the step limit is reported as it ran. Group by a `factor_*` column (or use
`hani2 compose report`) to see which factor makes an Assistant fail.

Recordings of other scenarios give empty columns.
""", columns=_cols())
def factors(ctx: EvalContext, options: dict) -> dict:
    """Difficulty factors of a compositional scenario and target attainment."""
    comp = (ctx.scenario.get("info") or {}).get("composition")
    if not isinstance(comp, dict) or not comp.get("cell"):
        return {}
    cell = dict(comp["cell"])
    start = ctx.rec.start or {}
    out: dict[str, Any] = {f"factor_{k}": _level(k, cell, start) for k in _FACTOR_DOC}
    agr = ctx.agreement
    pt = ctx.point_of(agr)
    target = comp.get("target") or {}
    r = float(ctx.disagreement[0]) if ctx.has_scenario else None
    hu = float(pt[0]) if pt is not None else num((ctx.summary or {}).get("human_utility"))
    tu = num(target.get("human_utility"))
    if hu is not None and tu is not None and r is not None and tu - r > 1e-9:
        out["target_attainment"] = (hu - r) / (tu - r)
        out["reached_target"] = int(agr is not None and hu >= tu - 1e-9)
    cons = comp.get("constraint")
    if cons:
        out["constraint_violated"] = 0
        if agr is not None:
            names = ctx.scenario.get("issue_names") or []
            if isinstance(agr, dict):
                v = agr.get(cons["issue"])
            elif cons["issue"] in names and len(agr) == len(names):
                v = agr[names.index(cons["issue"])]
            else:
                v = None
            out["constraint_violated"] = int(v is not None and str(v) == str(cons["value"]))
    return out
