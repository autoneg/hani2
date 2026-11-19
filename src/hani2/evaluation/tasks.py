"""Per-scenario evaluation criteria: rule checks, judged facts and assertions,
and task success.

A scenario can say what a good session looks like in an ``evaluation`` block of
its ``_info.yaml``::

    evaluation:
      targets:                    # conditions on evaluation columns of the session
        agreement: 1
        human_advantage: ">= 0.4"
      rules: [irrational_accept]  # rule checks (columns of rule_checks) that must be 0
      communicate:                # facts the Assistant must tell the human (language-model judge)
        - Price is your most important issue
      assertions:                 # statements about the session (language-model judge)
        - The Assistant never pressured the human to accept.
      basis: [targets, rules]     # what task success requires (default: every component defined)

The block is taken out of the scenario when it is loaded (the Opponent, the
Assistant and the browser never see it) and stored in the recording, so the
session is evaluated with the criteria it was played with. Scenarios without a
block use ``env.json`` ``evaluation.criteria`` or the metric option ``criteria``.

``task_success`` is 1 only when every component of the basis holds: the product
of the components, as in task-based agent benchmarks.
"""

from __future__ import annotations

import hashlib
import json
import operator
import re
from typing import Any

from hani2.evaluation.base import Column as C
from hani2.evaluation.base import EvalContext, metric, num

EPS = 1e-9
COMPONENTS = ("targets", "rules", "communicate", "assertions")
#: the rule checks a scenario may name in ``rules``
RULES = ("irrational_accept", "opponent_irrational_accept", "irrational_suggestions", "opponent_failed",
         "infrastructure_failure")


def criteria_of(ctx: EvalContext, options: dict) -> dict | None:
    """The evaluation criteria of a recording: the scenario's own block (as
    recorded), else the option ``criteria``, else ``env.json``
    ``evaluation.criteria``; ``None`` when there are none."""
    c = (ctx.scenario or {}).get("evaluation")
    if not c:
        c = options.get("criteria")
    if not c:
        from hani2.config import get_env

        c = get_env("evaluation.criteria", None)
    return dict(c) if isinstance(c, dict) and c else None


def _list(x: Any) -> list[str]:
    if x is None:
        return []
    if isinstance(x, str):
        return [x] if x.strip() else []
    return [str(v) for v in x if str(v).strip()]


# --------------------------------------------------------------------------- #
# Rule checks (no judgement)                                                   #
# --------------------------------------------------------------------------- #
def _who_accepted(ctx: EvalContext) -> str | None:
    """``human`` (the Human seat, whoever acted on it) or ``agent`` (the Opponent)."""
    by = ctx.summary.get("ended_by")
    if by in ("human", "agent"):
        return by
    # ``act`` events are the Human seat's actions (by the Human, the Assistant or the autopilot)
    if any(a.get("type") == "accept" for a in ctx.acts):
        return "human"
    return "agent" if ctx.agreement is not None else None


@metric("rule_checks", kind="hard", title="Rule checks",
        formula=r"\text{irrational\_accept} = \mathbb{1}\big[\omega^* \neq \varnothing \wedge h \text{ accepted} \wedge u_h(\omega^*) < r_h\big]",
        details=r"""
Mistakes that need no judgement because the utility table proves them: accepting a deal worth less
than walking away, the Assistant suggesting such an offer, and sessions that failed because of the
Opponent agent or of the system. A scenario's `evaluation` block can require some of them to be 0
(`rules`), and the combined scores use them.

**Example.** The reservation value of the Human is $r_h = 0.2$. The Assistant suggests offers worth
0.6, 0.15 and 0.3 to the Human; the Human then accepts the Opponent's offer worth 0.18. Then
`irrational_suggestions` $= 1$ and `irrational_accept` $= 1$.

Empty without a utility table (e.g. continuous issues), except the two failure flags.
""", columns=[
    C("irrational_accept", "Accepted below reservation", "1 if the Human seat accepted a deal worth less than no deal", False,
      formula=r"\mathbb{1}\big[\omega^* \neq \varnothing \wedge h \text{ accepted} \wedge u_h(\omega^*) < r_h\big]",
      range="0 or 1",
      details=r"""
1 when the negotiation ended because the Human seat (the Human, the Assistant or the autopilot acting
for them) accepted an offer whose utility for the Human is below their reservation value $r_h$: the
Human would have done better without a deal. 0 otherwise, also when there was no deal.
"""),
    C("opponent_irrational_accept", "Opponent accepted below reservation", "1 if the Opponent accepted a deal worth less to it than no deal", False,
      formula=r"\mathbb{1}\big[\omega^* \neq \varnothing \wedge o \text{ accepted} \wedge u_o(\omega^*) < r_o\big]",
      range="0 or 1",
      details=r"""
The same for the Opponent: it accepted an offer worth less to it than its reservation value $r_o$. A
well-built negotiation agent never does this.
"""),
    C("irrational_suggestions", "Suggestions below reservation", "Assistant suggestions worth less to the Human than no deal", False,
      formula=r"\lvert \{\sigma \in \Sigma : u_h(\sigma) < r_h\} \rvert", range="count",
      details=r"""
How many of the Assistant's suggestions $\Sigma$ (offers it filled into the Human's seat) are worth less
to the Human than their reservation value. Empty when there was no Assistant activity.
"""),
    C("opponent_failed", "Opponent failed", "1 if the session ended because the Opponent agent raised an error", False,
      formula=r"\mathbb{1}\left[\text{status} = \text{agent\_failed}\right]", range="0 or 1",
      details=r"""
1 when the negotiation ended because the Opponent agent failed. In the Human-Agent Negotiation track
this counts against the Opponent; in the Hybrid Intelligence track the session is left out of the
leaderboard (it is not the Assistant's fault).
"""),
    C("infrastructure_failure", "System failure", "1 if the negotiation mechanism failed", False,
      formula=r"\mathbb{1}\left[\text{status} = \text{erred}\right]", range="0 or 1",
      details=r"""
1 when the negotiation ended because the mechanism (the system) failed. Such sessions are left out of
every leaderboard.
"""),
])
def rule_checks(ctx: EvalContext, options: dict) -> dict:
    """Mistakes the utility table proves (accepting or suggesting a deal worth
    less than no deal) and failed sessions."""
    s = ctx.summary
    status = s.get("status")
    out: dict[str, Any] = dict(
        opponent_failed=None if not s else int(status == "agent_failed"),
        infrastructure_failure=None if not s else int(status == "erred"),
    )
    if not ctx.has_scenario:
        return out
    d = ctx.disagreement
    pt = ctx.point_of(ctx.agreement) if ctx.agreement is not None else None
    who = _who_accepted(ctx) if pt is not None else None
    out["irrational_accept"] = int(who == "human" and pt is not None and pt[0] < d[0] - EPS) if s else None
    out["opponent_irrational_accept"] = int(who == "agent" and pt is not None and pt[1] < d[1] - EPS) if s else None
    names = ctx.scenario.get("issue_names") or []
    sugg = [d_ for d_ in ctx.drafts if d_.get("by") == "agent" and d_.get("values")]
    from hani2.evaluation.llm_judge import _has_assistant

    if sugg or _has_assistant(ctx):
        vals = [ctx.hu([g["values"].get(n) for n in names]) for g in sugg]
        out["irrational_suggestions"] = sum(1 for v in vals if v is not None and v < d[0] - EPS)
    return out


# --------------------------------------------------------------------------- #
# Judged criteria: facts to communicate and the scenario's assertions          #
# --------------------------------------------------------------------------- #
def _judge_inputs(ctx: EvalContext, options: dict) -> tuple[list[str], list[str]]:
    c = criteria_of(ctx, options) or {}
    return _list(c.get("communicate")), _list(c.get("assertions"))


def _judge_cache(ctx: EvalContext, options: dict) -> str:
    facts, asserts = _judge_inputs(ctx, options)
    return "crit#" + hashlib.sha1(json.dumps([facts, asserts]).encode()).hexdigest()[:10]


@metric("task_judge", kind="soft", title="LLM judge: scenario criteria", needs_llm=True, version="1",
        cache_extra=_judge_cache,
        options={"criteria": "Evaluation criteria for scenarios without their own (a dict with communicate, assertions, …)."},
        formula=r"c_i, a_j \in \{\text{true}, \text{false}, \text{null}\} \ \text{for every fact } i \text{ and assertion } j",
        details=r"""
A language model checks the judged parts of the scenario's evaluation criteria (its `evaluation`
block, see [Scenarios](scenarios.md#evaluation-criteria)):

* **communicate** — facts the Assistant should have conveyed to the Human (for example "Price is your
  most important issue"). A fact counts when the Assistant's messages state it or something that
  clearly means the same; the judge gives one verdict per fact.
* **assertions** — statements about the session specific to this scenario, each met, not met or not
  applicable (like `nl_assertions`, whose statements apply to every scenario).

**Example.** Three facts, two conveyed: `task_communicated` $= 2/3$. Two assertions, one met and one
not applicable: `task_assertions_met` $= 1$.

Not computed when the criteria define neither facts nor assertions.
""", columns=[
    C("task_communicated", "Facts communicated", "Share of the scenario's facts the Assistant conveyed to the Human", True,
      formula=r"\frac{\lvert \{i : c_i = \text{true}\} \rvert}{\lvert \{i : c_i \neq \text{null}\} \rvert}", range="[0, 1]",
      details=r"""
The share of the facts of the scenario's `communicate` list that the Assistant told the Human. 1 is
needed for the `communicate` component of `task_success`.
"""),
    C("task_assertions_met", "Scenario assertions met", "Share of the scenario's applicable assertions that were met", True,
      formula=r"\frac{\lvert \{j : a_j = \text{true}\} \rvert}{\lvert \{j : a_j \neq \text{null}\} \rvert}", range="[0, 1]",
      details=r"""
The share of the scenario's applicable `assertions` that the judge found met (not-applicable ones are
left out). 1 is needed for the `assertions` component of `task_success`.
"""),
])
def task_judge(ctx: EvalContext, options: dict) -> dict:
    """A language model checks the facts the Assistant had to convey and the
    scenario's own assertions."""
    facts, asserts = _judge_inputs(ctx, options)
    if not facts and not asserts:
        return {}
    from hani2.evaluation.llm_judge import ask_json, transcript

    prompt = (
        "You evaluate a record of a negotiation in which a HUMAN was helped by an AI ASSISTANT against an OPPONENT.\n"
        "1. FACTS: for each fact, did the ASSISTANT convey it to the human in its messages (true), or not (false)? "
        "Paraphrases with the same meaning count; facts the human found out by other means do not.\n"
        "2. ASSERTIONS: for each statement, is it met (true), not met (false) or not applicable (null, when the "
        "record gives no opportunity to check it)?\n\nAnswer with JSON: {\"facts\": [{\"fact\": \"<copied>\", "
        "\"conveyed\": true|false, \"reasoning\": \"<one sentence>\"}, ...], \"assertions\": [{\"assertion\": "
        "\"<copied>\", \"met\": true|false|null, \"reasoning\": \"<one sentence>\"}, ...]}\n\n"
        "FACTS:\n" + ("\n".join(f"{i + 1}. {f}" for i, f in enumerate(facts)) or "(none)")
        + "\n\nASSERTIONS:\n" + ("\n".join(f"{i + 1}. {a}" for i, a in enumerate(asserts)) or "(none)")
        + "\n\nRECORD:\n" + transcript(ctx)
    )
    obj = ask_json(prompt)

    def verdicts(items, key, field):
        res = obj.get(key) or []
        out = []
        for i, it in enumerate(items):
            r = res[i] if i < len(res) and isinstance(res[i], dict) else {}
            v = r.get(field)
            out.append({key[:-1]: it, field: v if isinstance(v, bool) else None, "reasoning": str(r.get("reasoning") or "")})
        return out

    fv = verdicts(facts, "facts", "conveyed")
    av = verdicts(asserts, "assertions", "met")

    def share(vs, field):
        j = [v for v in vs if v[field] is not None]
        return sum(1 for v in j if v[field]) / len(j) if j else None

    out: dict[str, Any] = {"_details": {"facts": fv, "assertions": av}}
    if facts:
        out["task_communicated"] = share(fv, "conveyed")
    if asserts:
        out["task_assertions_met"] = share(av, "met")
    return out


# --------------------------------------------------------------------------- #
# Task success                                                                 #
# --------------------------------------------------------------------------- #
_OPS = {">=": operator.ge, "<=": operator.le, "!=": operator.ne, "==": operator.eq, ">": operator.gt,
        "<": operator.lt, "=": operator.eq}
_COND = re.compile(r"^\s*(>=|<=|!=|==|=|>|<)?\s*(.+?)\s*$")


def check_target(value: Any, cond: Any) -> bool | None:
    """Whether ``value`` satisfies a target: a number or boolean (equal), a
    string such as ``">= 0.4"`` or ``"== success"``, or a ``[low, high]``
    range. ``None`` when the value is missing."""
    if value is None:
        return None
    if isinstance(cond, (list, tuple)) and len(cond) == 2:
        v = num(value)
        lo, hi = num(cond[0]), num(cond[1])
        if v is None:
            return None
        return (lo is None or v >= lo - EPS) and (hi is None or v <= hi + EPS)
    if isinstance(cond, bool):
        return bool(num(value)) == cond if num(value) is not None else bool(value) == cond
    if isinstance(cond, (int, float)):
        v = num(value)
        return None if v is None else abs(v - float(cond)) <= 1e-6
    m = _COND.match(str(cond))
    if not m:
        return None
    op, rhs = _OPS[m.group(1) or "=="], m.group(2)
    v, r = num(value), num(rhs)
    if v is not None and r is not None:
        tol = 1e-6  # utilities are rounded in recordings: compare with a small tolerance
        return {operator.eq: abs(v - r) <= tol, operator.ne: abs(v - r) > tol, operator.ge: v >= r - tol,
                operator.le: v <= r + tol, operator.gt: v > r + tol, operator.lt: v < r - tol}[op]
    if op in (operator.eq, operator.ne):
        return op(str(value), rhs.strip("'\""))
    return None


@metric("task_success", kind="score", title="Task success", stage=1,
        requires=["outcome", "optimality", "rule_checks"],
        options={"criteria": "Evaluation criteria for scenarios without their own (a dict with targets, rules, "
                             "communicate, assertions, basis)."},
        formula=r"\text{task\_success} = \prod_{c \in B} \mathbb{1}[c \text{ holds}], \qquad B \subseteq \{\text{targets}, \text{rules}, \text{communicate}, \text{assertions}\}",
        details=r"""
Whether the session did what its scenario asks, as a pass/fail result: the product of the components
of the scenario's evaluation criteria (its `evaluation` block, or `env.json` `evaluation.criteria`):

* **targets** — every condition on the session's columns holds (e.g. `agreement: 1`,
  `human_advantage: ">= 0.4"`, `pareto_distance: "<= 0.15"`); a target on a column without a value
  leaves `task_success` empty (unless another component already failed);
* **rules** — every named rule check (`rule_checks`) is 0;
* **communicate** — the Assistant conveyed every fact (`task_communicated` $= 1$, needs the judge);
* **assertions** — every applicable scenario assertion was met (`task_assertions_met` $= 1$, needs the
  judge).

`basis` lists the components that count. Without it, every component the criteria define counts if it
was evaluated (the judged ones only with the language-model judge) and `task_components` tells how
many did; any failed component makes it 0. With an explicit `basis`, a component that was not evaluated leaves `task_success` empty
instead of passing. Its mean is the success rate, and it is the default success criterion of the
leaderboards' pass^k.

**Example.** Targets `agreement: 1` and `human_advantage: ">= 0.4"`, rules `[irrational_accept]`.
A deal with `human_advantage` $= 0.5$, accepted above the reservation value: `task_targets_met` $= 1$,
`task_rules_ok` $= 1$ and `task_success` $= 1$. With `human_advantage` $= 0.3$ instead,
`task_targets_met` $= 1/2$ and `task_success` $= 0$.

Empty for scenarios without criteria.
""", columns=[
    C("task_success", "Task success", "1 if the session met every component of its scenario's evaluation criteria", True,
      formula=r"\prod_{c \in B} \mathbb{1}[c \text{ holds}]", range="0 or 1",
      details=r"""
1 when every component of the basis holds, 0 when one fails. Empty when the scenario has no criteria or
a component of an explicit `basis` was not evaluated.
"""),
    C("task_targets_met", "Targets met", "Share of the scenario's targets the session met", True,
      formula=r"\frac{\lvert \{t \in T : t \text{ holds}\} \rvert}{\lvert T \rvert}", range="[0, 1]",
      details=r"""
The share of the conditions of `targets` that hold. A target on a column that has no value (for
example a questionnaire scale without a questionnaire, or a misspelled column) makes the share empty.
"""),
    C("task_rules_ok", "Rules respected", "1 if every rule check the scenario names is 0", True,
      formula=r"\prod_{\rho \in R} \mathbb{1}[\rho = 0]", range="0 or 1",
      details=r"""
1 when none of the rule checks named in `rules` fired (missing checks count as respected: e.g.
`irrational_suggestions` without an Assistant).
"""),
    C("task_components", "Components checked", "How many components the task success was computed from",
      formula=r"\lvert B \rvert", range="count",
      details=r"""
The number of components (targets, rules, communicate, assertions) that `task_success` multiplied.
"""),
])
def task_success(ctx: EvalContext, options: dict) -> dict:
    """Pass/fail against the scenario's evaluation criteria (the product of its
    components: targets, rules, facts communicated, assertions)."""
    crit = criteria_of(ctx, options)
    if not crit:
        return {}
    row = ctx.row
    comp: dict[str, bool | None] = {}
    out: dict[str, Any] = {}
    targets = crit.get("targets") or {}
    if isinstance(targets, dict) and targets:
        res = {k: check_target(row.get(k), v) for k, v in targets.items()}
        if any(v is False for v in res.values()):
            comp["targets"] = False  # a failed target fails, even if another one cannot be checked
        elif any(v is None for v in res.values()):
            comp["targets"] = None
        else:
            comp["targets"] = True
        if all(v is not None for v in res.values()):
            out["task_targets_met"] = sum(1 for v in res.values() if v) / len(res)
        out.setdefault("_details", {})["targets"] = res
    rules = _list(crit.get("rules"))
    if rules:
        unknown = [r for r in rules if r not in RULES]
        if unknown:
            raise ValueError(f"unknown rule(s) {unknown}; known: {', '.join(RULES)}")
        ok = all(not num(row.get(r)) for r in rules)
        out["task_rules_ok"] = int(ok)
        comp["rules"] = ok
    for name, col in (("communicate", "task_communicated"), ("assertions", "task_assertions_met")):
        if _list(crit.get(name)):
            v = num(row.get(col))
            comp[name] = None if v is None else v >= 1 - 1e-9
    basis = _list(crit.get("basis"))
    if basis:
        bad = [b for b in basis if b not in COMPONENTS]
        if bad:
            raise ValueError(f"unknown basis component(s) {bad}; known: {', '.join(COMPONENTS)}")
        used = [comp.get(b) for b in basis]
        out["task_success"] = None if any(u is None for u in used) else int(all(used))
        out["task_components"] = len(basis)
    else:
        used = [v for v in comp.values() if v is not None]
        if any(v is False for v in used):
            out["task_success"] = 0
        elif "targets" in comp and comp["targets"] is None:
            out["task_success"] = None  # targets are computed from the recording: one that cannot be checked never passes
        else:
            out["task_success"] = int(all(used)) if used else None
        out["task_components"] = len(used)
    out.setdefault("_details", {})["components"] = comp
    return out
