"""Hard metrics: computed from the recording alone (no judgement involved)."""

from __future__ import annotations

import math
from collections import Counter

import numpy as np

from hani2.evaluation.base import Column as C
from hani2.evaluation.base import EvalContext, mean, median, metric, num


# --------------------------------------------------------------------------- #
# Outcome                                                                      #
# --------------------------------------------------------------------------- #
@metric("outcome", kind="hard", title="Outcome", figures=["outcome_space"],
        formula=r"p(\omega^*) = \big(u_h(\omega^*),\ u_o(\omega^*)\big), \qquad p(\varnothing) = d = (r_h, r_o)",
        details=r"""
Whether the negotiation ended with a deal and what the result was worth to each side. This is the
first thing to look at: every other outcome metric is computed from the point $p(\omega^*)$.

Utilities come from the scenario's utility table, so they are in the scenario's units (usually
normalised to $[0, 1]$). The Human side is the Human's seat, whoever acted on it (the Human, the
Assistant acting for them or the autopilot); the Opponent side sums every other party, which is the
single Opponent in a bilateral negotiation.

**Example** (the scenario of the figure): the parties agree on F with $p(F) = (0.5, 0.45)$, the
reservation values are $r_h = r_o = 0.2$ and the best outcome for each side is worth $1$. Then
`human_utility` $= 0.5$, `opponent_utility` $= 0.45$, `human_advantage` $= (0.5 - 0.2)/(1 - 0.2) = 0.375$,
`opponent_advantage` $= 0.3125$ and `welfare` $= 0.95$.

**Caveats.** Without an agreement the result is the reservation point $d$ (not empty). Without a
utility table (e.g. continuous issues) the utilities and the Human advantage come from the session's
own summary and the Opponent advantage is empty.
""", columns=[
    C("agreement", "Agreement", "1 if the negotiation ended with a deal", True,
      formula=r"\mathbb{1}\left[\omega^* \neq \varnothing\right]", range="0 or 1",
      details=r"""
1 when the negotiation ended with an agreement, 0 when it ended without one (broken off, timed out,
failed). Empty when the recording has no result at all (the session was abandoned). Its mean over a
group of recordings is the **agreement rate**, and it is the default success criterion of pass^k.
"""),
    C("status", "Status", "success, broken, timedout, erred or agent_failed",
      formula=r"\text{status} \in \{\text{success}, \text{broken}, \text{timedout}, \text{erred}, \text{agent\_failed}\}",
      range="category",
      details=r"""
How the negotiation ended, as reported by the session: **success** (an agreement), **broken** (one side
ended it), **timedout** (the time or step limit was reached), **erred** (the mechanism failed) or
**agent_failed** (the Opponent agent raised an error). Use it to separate failed sessions from real
disagreements.
"""),
    C("ended_by", "Ended by", "Who ended it (accepted or broke off): human or agent",
      formula=r"\text{ended\_by} \in \{\text{human}, \text{agent}\}", range="category",
      details=r"""
Which side ended the negotiation by accepting an offer or breaking off: **human** is the Human's seat
(the Human, or the Assistant or autopilot acting for them), **agent** is the Opponent. Empty when the
negotiation ended by the time limit or an error.
"""),
    C("human_utility", "Human utility", "Utility of the result for the human–agent team", True,
      formula=r"u_h(\omega^*), \qquad u_h(\varnothing) = r_h", range="utility (usually [0, 1])",
      details=r"""
What the result is worth to the Human side under the scenario's utility function. Higher is better.
Compare it with the reservation value $r_h$ (what the Human gets without a deal): a value below $r_h$
means the Human accepted a deal worse than walking away. Without an agreement it equals $r_h$.
"""),
    C("opponent_utility", "Opponent utility", "Utility of the result for the opponent",
      formula=r"u_o(\omega^*) = \sum_{j \neq h} u_j(\omega^*), \qquad u_o(\varnothing) = r_o",
      range="utility (usually [0, 1])",
      details=r"""
What the result is worth to the Opponent side (summed over every non-Human party). It has no
"better" direction for the Human, but a very low value next to a high `human_utility` shows a
one-sided deal. Without an agreement it equals $r_o$.
"""),
    C("human_advantage", "Human advantage", "(u − reserved) / (max − reserved) for the human team", True,
      formula=r"A_h = \frac{u_h(\omega^*) - r_h}{\bar u_h - r_h}, \qquad \bar u_h = \max_{\omega \in \Omega} u_h(\omega)",
      range="≤ 1 (1 = the best outcome, 0 = no better than no deal)",
      details=r"""
The share of the largest possible gain over walking away that the Human side obtained: 1 for the
Human's best outcome, 0 for an outcome worth exactly the reservation value, negative for a deal
below it. Unlike the raw utility it is comparable across scenarios with different reservation values.

Example: $u_h(\omega^*) = 0.5$, $r_h = 0.2$, $\bar u_h = 1$ gives $A_h = 0.3 / 0.8 = 0.375$.

It is 0 when $\bar u_h - r_h \le 10^{-12}$ (no outcome is better than no deal) and 0 without an agreement.
The maximum is over every outcome, not only those acceptable to the Opponent.
"""),
    C("opponent_advantage", "Opponent advantage", "The same for the opponent",
      formula=r"A_o = \frac{u_o(\omega^*) - r_o}{\bar u_o - r_o}, \qquad \bar u_o = \max_{\omega \in \Omega} u_o(\omega)",
      range="≤ 1",
      details=r"""
The Opponent side's share of its largest possible gain over no deal (see `human_advantage`). In the
example $A_o = (0.45 - 0.2)/(1 - 0.2) = 0.3125$. Empty when the scenario has no utility table.
"""),
    C("welfare", "Social welfare", "Sum of every party's utility", True,
      formula=r"W = u_h(\omega^*) + u_o(\omega^*)", range="utility sum (usually [0, number of parties])",
      details=r"""
The total value created for both sides: higher means a more efficient (integrative) deal. Example:
$0.5 + 0.45 = 0.95$. Without an agreement it is $r_h + r_o$. Compare it across scenarios with
`welfare_optimality`, which divides by the best possible welfare.
"""),
    C("practice", "Practice", "1 for a practice round", formula=r"\mathbb{1}\left[\text{practice round}\right]",
      range="0 or 1",
      details=r"""
1 when the session was a practice round. Usually filtered out of analyses.
"""),
])
def outcome(ctx: EvalContext, options: dict) -> dict:
    """Did the team reach a deal, and how good was it for each side?"""
    s = ctx.summary
    agr = ctx.agreement
    hu = num(s.get("human_utility"))
    pt = ctx.point_of(agr)
    if pt is not None and ctx.has_scenario:
        hu, ou = float(pt[0]), float(pt[1])
    else:
        ou = num(s.get("agent_utility"))

    def adv(u, i_vals, r):
        if u is None or ctx.U.size == 0:
            return None
        mx = float(np.nanmax(i_vals))
        return (u - r) / (mx - r) if mx - r > 1e-12 else 0.0

    hadv = num(s.get("human_advantage"))
    oadv = None
    if ctx.has_scenario:
        d = ctx.disagreement
        hadv = adv(hu, ctx.two_party[0], d[0])
        oadv = adv(ou, ctx.two_party[1], d[1])
    st = ctx.rec.start or {}
    return dict(
        agreement=1 if agr is not None else 0 if s else None,
        status=s.get("status"), ended_by=s.get("ended_by") or None,
        human_utility=hu, opponent_utility=ou, human_advantage=hadv, opponent_advantage=oadv,
        welfare=(hu + ou) if hu is not None and ou is not None else None,
        practice=1 if st.get("practice") else 0,
    )


@metric("optimality", kind="hard", title="Optimality", figures=["outcome_space"],
        formula=r"\begin{aligned} \nu &= \operatorname*{arg\,max}_{\omega \in \mathcal{P}} (u_h(\omega) - r_h)^+ (u_o(\omega) - r_o)^+ \\ \kappa &= \operatorname*{arg\,max}_{\omega \in \mathcal{P},\ p(\omega) \geq d} \min\left(\frac{u_h(\omega) - r_h}{\bar u_h - r_h}, \frac{u_o(\omega) - r_o}{\bar u_o - r_o}\right) \end{aligned}",
        details=r"""
How far the result is from the efficient and the fair outcomes of the scenario. All distances are
Euclidean, in the two-dimensional utility space of the Human ($u_h$, horizontal) and the Opponent side
($u_o$, vertical).

* The **Pareto frontier** $\mathcal{P}$ holds the outcomes that cannot be improved for one side
  without hurting the other. An agreement off the frontier leaves value on the table.
* The **Nash bargaining solution** $\nu$ is the Pareto outcome with the largest product of the two
  sides' gains over the reservation point $d$ (Nash, 1950). It is the classic "fair and efficient"
  reference.
* The **Kalai–Smorodinsky solution** $\kappa$ gives both sides the same share of their best possible
  gain (Kalai and Smorodinsky, 1975). On a finite set of outcomes it is the individually rational
  Pareto outcome whose smaller normalised gain is the largest.

**Example** (the figure): the frontier is A, B, C, D, E; $d = (0.2, 0.2)$; the Nash point is B
$(0.8, 0.6)$ with product $0.6 \times 0.4 = 0.24$; the Kalai–Smorodinsky point is C $(0.62, 0.75)$ with
normalised gains $(0.525, 0.6875)$. The agreement F $(0.5, 0.45)$ is $0.323$ from the frontier (its
nearest Pareto outcome is C), $0.335$ from the Nash point and $0.323$ from the Kalai point.

**Caveats.** Ties are broken by taking the first outcome in order of decreasing $u_h$. The distance to the
frontier is to the nearest Pareto *outcome*, not to the line joining them. Without an agreement the
columns are computed for the reservation point $d$. All columns are empty when the scenario has no
utility table. The Nash point is undefined (and `nash_distance` empty) when no Pareto outcome gives
both sides a positive gain; the Kalai point when no Pareto outcome is acceptable to both.
""", columns=[
    C("pareto_distance", "Pareto distance", "Distance of the result from the Pareto frontier (utility space)", False,
      formula=r"D_{\mathcal{P}}(\omega^*) = \min_{\omega \in \mathcal{P}} \left\lVert p(\omega^*) - p(\omega) \right\rVert_2",
      range="≥ 0 (0 = on the frontier)",
      details=r"""
How much value the parties left on the table: 0 for a Pareto-optimal result, larger when both could
have been better off. Lower is better. Example: F $(0.5, 0.45)$ to C $(0.62, 0.75)$ gives
$\sqrt{0.12^2 + 0.30^2} = 0.323$.
"""),
    C("pareto_optimal", "Pareto optimal", "1 if the result is on the Pareto frontier", True,
      formula=r"\mathbb{1}\left[D_{\mathcal{P}}(\omega^*) < 10^{-6}\right]", range="0 or 1",
      details=r"""
1 when the result is (numerically) on the Pareto frontier. Its mean over recordings is the share of
efficient results. A no-deal result counts as optimal only if the reservation point itself lies on
the frontier (rare).
"""),
    C("nash_distance", "Nash distance", "Distance from the Nash bargaining solution", False,
      formula=r"\left\lVert p(\omega^*) - p(\nu) \right\rVert_2", range="≥ 0",
      details=r"""
How far the result is from the Nash bargaining solution $\nu$, the efficient outcome that maximises the
product of both sides' gains. Lower is better. Example: F to B gives
$\sqrt{0.3^2 + 0.15^2} = 0.335$. Empty when the Nash point is undefined.
"""),
    C("kalai_distance", "Kalai–Smorodinsky distance", "Distance from the Kalai–Smorodinsky solution", False,
      formula=r"\left\lVert p(\omega^*) - p(\kappa) \right\rVert_2", range="≥ 0",
      details=r"""
How far the result is from the Kalai–Smorodinsky solution $\kappa$, the efficient outcome where both
sides get the same share of their best possible gain. Lower is better. Example: F to C gives $0.323$.
Empty when no Pareto outcome is acceptable to both sides.
"""),
    C("welfare_optimality", "Welfare optimality", "Social welfare / the best possible welfare", True,
      formula=r"\frac{u_h(\omega^*) + u_o(\omega^*)}{\max_{\omega \in \Omega} \big(u_h(\omega) + u_o(\omega)\big)}",
      range="usually [0, 1]",
      details=r"""
The share of the largest total value the scenario allows that the result achieves: 1 for a
welfare-maximising deal. Example: $0.95 / 1.4 = 0.679$ (B has the largest sum, $1.4$). It is not
measured from the reservation point, so a no-deal result scores $(r_h + r_o)$ divided by the best
welfare. Empty when the best welfare is 0.
"""),
    C("nash_product_ratio", "Nash product ratio", "Nash product of the result / the largest possible", True,
      formula=r"\frac{(u_h(\omega^*) - r_h)^+ \, (u_o(\omega^*) - r_o)^+}{\max_{\omega \in \Omega} (u_h(\omega) - r_h)^+ \, (u_o(\omega) - r_o)^+}, \qquad x^+ = \max(x, 0)",
      range="[0, 1]",
      details=r"""
The result's product of gains over the reservation point relative to the best product (that of the
Nash point): 1 for the Nash solution, 0 when one side gains nothing (and for no deal). It rewards
results that are both efficient and balanced. Example: $(0.3 \times 0.25) / 0.24 = 0.3125$. Empty when
no outcome gives both sides a gain.
"""),
    C("fairness_gap", "Fairness gap", "|human advantage − opponent advantage|", False,
      formula=r"\left\lvert A_h - A_o \right\rvert", range="≥ 0 (0 = gains shared evenly)",
      details=r"""
How unevenly the gains over no deal were shared, measured on the normalised advantages $A_h$ and
$A_o$ (see `human_advantage`). Lower is fairer. Example: $\lvert 0.375 - 0.3125 \rvert = 0.0625$.
A no-deal result has gap 0 (nobody gained), so read it together with `agreement`.
"""),
])
def optimality(ctx: EvalContext, options: dict) -> dict:
    """How far the result is from the efficient and fair outcomes of the scenario."""
    if not ctx.has_scenario:
        return {}
    pt = ctx.point_of(ctx.agreement)
    if pt is None:
        return {}
    d = ctx.disagreement
    pd_ = ctx.dist_to_pareto(pt)
    nash, ks = ctx.nash_point, ctx.ks_point
    P = ctx.two_party
    gains = np.clip(P[0] - d[0], 0, None) * np.clip(P[1] - d[1], 0, None)
    best_np = float(gains.max()) if gains.size else 0.0
    my_np = max(0.0, pt[0] - d[0]) * max(0.0, pt[1] - d[1])
    mw = ctx.max_welfare
    hadv = (pt[0] - d[0]) / (P[0].max() - d[0]) if P[0].max() - d[0] > 1e-12 else 0.0
    oadv = (pt[1] - d[1]) / (P[1].max() - d[1]) if P[1].max() - d[1] > 1e-12 else 0.0
    return dict(
        pareto_distance=pd_, pareto_optimal=int(pd_ is not None and pd_ < 1e-6),
        nash_distance=float(np.linalg.norm(pt - nash)) if nash is not None else None,
        kalai_distance=float(np.linalg.norm(pt - ks)) if ks is not None else None,
        welfare_optimality=float(pt.sum() / mw) if mw else None,
        nash_product_ratio=my_np / best_np if best_np > 0 else None,
        fairness_gap=abs(hadv - oadv),
    )


@metric("scenario_stats", kind="hard", title="Scenario", default=False, figures=["outcome_space"],
        formula=r"\Omega,\ \mathcal{P},\ (\bar u_h, \bar u_o)",
        details=r"""
Descriptors of the scenario itself, not of how it was played: its size, how much of it is acceptable
to everyone and how competitive it is. Use them to balance or stratify comparisons (an agreement in a
highly opposed scenario is harder). Not run by default. Empty when the scenario has no utility table.

**Example** (the figure): 8 outcomes, 7 acceptable to both sides (only E gives the Human less than
$r_h$), 5 on the Pareto frontier, and the ideal point $(1, 1)$ is $0.447$ from the nearest Pareto
outcome (B).
""", columns=[
    C("n_outcomes", "Outcomes", "Number of possible outcomes", formula=r"\lvert \Omega \rvert", range="count",
      details=r"""
The number of outcomes in the scenario's utility table (all combinations of issue values).
"""),
    C("zopa_fraction", "ZOPA fraction", "Share of outcomes acceptable to every party (at least all reserved values)",
      formula=r"\frac{1}{\lvert \Omega \rvert} \left\lvert \{\omega \in \Omega : u_j(\omega) \geq r_j \ \forall j\} \right\rvert",
      range="[0, 1]",
      details=r"""
The size of the zone of possible agreement: the share of outcomes that every party prefers to (or
values as much as) no deal. Each party is checked separately (not the summed Opponent side). Small
values mean a hard scenario where most deals are unacceptable to someone. Example: $7/8 = 0.875$.
"""),
    C("pareto_size", "Pareto size", "Number of Pareto-optimal outcomes", formula=r"\lvert \mathcal{P} \rvert",
      range="count",
      details=r"""
How many outcomes are Pareto optimal (in the Human vs Opponent-side utility space). Example: 5.
"""),
    C("opposition", "Opposition", "Distance of the ideal point (best for each side) from the frontier: how competitive the scenario is",
      formula=r"\min_{\omega \in \mathcal{P}} \left\lVert (\bar u_h, \bar u_o) - p(\omega) \right\rVert_2",
      range="≥ 0 (0 = no conflict)",
      details=r"""
How far the ideal point (each side's best utility at once) is from what can actually be achieved:
0 when one outcome is the best for both (no conflict of interest), larger for more competitive
scenarios. Example: the ideal point $(1, 1)$ to B $(0.8, 0.6)$ gives $\sqrt{0.2^2 + 0.4^2} = 0.447$.
The ideal point is $(\bar u_h, \bar u_o)$, which is $(1, 1)$ only when both utilities reach 1.
"""),
])
def scenario_stats(ctx: EvalContext, options: dict) -> dict:
    """Descriptors of the scenario (useful to balance comparisons)."""
    if not ctx.has_scenario:
        return {}
    U = ctx.U
    ok = np.all(U >= ctx.reserved[:, None], axis=0)
    P = ctx.two_party[:, ctx.pareto]
    mx = ctx.two_party.max(axis=1)
    opp = float(np.min(np.linalg.norm(P - mx[:, None], axis=0))) if P.size else None
    return dict(n_outcomes=int(U.shape[1]), zopa_fraction=float(ok.mean()), pareto_size=int(ctx.pareto.size),
                opposition=opp)


# --------------------------------------------------------------------------- #
# Length and cost                                                              #
# --------------------------------------------------------------------------- #
@metric("length", kind="hard", title="Length",
        formula=r"O = (o_1, \dots, o_{\lvert O \rvert}), \qquad O = O_h \cup O_o",
        details=r"""
How long the negotiation took, in offers, mechanism steps and seconds. Long negotiations cost the
participant time and attention; very short ones may mean an early acceptance or a click-through.

$O$ is the sequence of offers in the mechanism's trace (both sides), $O_h$ those made from the Human's
seat (by the Human, or the Assistant or autopilot acting for them) and $O_o$ those of the Opponent.
Times are on the recording clock (seconds since the recording started).

**Caveat.** A session abandoned mid-negotiation has no trace: the offers are then the Human seat's
offer actions and the Opponent offers shown on screen.
""", columns=[
    C("n_offers", "Offers", "Offers exchanged", formula=r"\lvert O \rvert", range="count",
      details=r"""
Every offer made in the negotiation, by both sides.
"""),
    C("n_human_offers", "Human offers", "Offers made by the human team", formula=r"\lvert O_h \rvert", range="count",
      details=r"""
Offers made from the Human's seat, whoever made them (the Human, the Assistant acting for them or
the autopilot). See `actions_by_human` for who acted.
"""),
    C("n_opponent_offers", "Opponent offers", "Offers made by the opponent", formula=r"\lvert O_o \rvert",
      range="count",
      details=r"""
Offers made by the Opponent.
"""),
    C("n_steps", "Steps", "Mechanism steps used", formula=r"s_{\text{end}}", range="count",
      details=r"""
The mechanism's step counter when the negotiation ended (from the result, else the last trace row).
In an alternating-offers protocol one step is one turn.
"""),
    C("relative_time", "Relative time", "Share of the time/step limit used", formula=r"\tau_{\text{end}} \in [0, 1]",
      range="[0, 1]",
      details=r"""
The mechanism's relative time when the negotiation ended: the fraction of its step or time limit that
was used (1 = the deadline was reached).
"""),
    C("negotiation_seconds", "Negotiation time (s)", "From the start to the end of the negotiation",
      formula=r"t_{\text{result}} - t_{\text{start}}", range="seconds",
      details=r"""
Wall-clock seconds from the moment the negotiation started to its result. Empty when either is missing
(e.g. an abandoned session).
"""),
    C("session_seconds", "Recording time (s)", "From loading the scenario to the end of the recording",
      formula=r"t_{\text{last event}}", range="seconds",
      details=r"""
The length of the whole recording: from loading the scenario (time 0) to its last event, so it
includes reading the instructions and the questionnaire.
"""),
    C("n_text_messages", "Text messages", "Offers or turns that carried a message to the other side",
      formula=r"\left\lvert \{k : \text{text}_k \neq \varnothing\} \right\rvert", range="count",
      details=r"""
Turns of the trace (both sides) that carried a text message, with or without an offer.
"""),
])
def length(ctx: EvalContext, options: dict) -> dict:
    """How long the negotiation took, in offers, steps and seconds."""
    rows = ctx.rec.trace
    last = rows[-1] if rows else {}
    row = ctx.rec.result or {}
    dur = (ctx.ended_at - ctx.started_at) if ctx.ended_at is not None and ctx.started_at is not None else None
    return dict(
        n_offers=len(ctx.offers), n_human_offers=len(ctx.human_offers), n_opponent_offers=len(ctx.opponent_offers),
        n_steps=num(row.get("step", last.get("step"))), relative_time=num(row.get("relative_time", last.get("rel"))),
        negotiation_seconds=dur, session_seconds=ctx.rec.duration,
        n_text_messages=sum(1 for r in rows if r.get("text")),
    )


@metric("llm_usage", kind="hard", title="LLM usage and cost",
        formula=r"\tau(c) = \text{total\_tokens}(c) \ \text{or}\ \text{prompt\_tokens}(c) + \text{completion\_tokens}(c)",
        details=r"""
Language-model calls made during the session, their tokens, cost, latency and failures, overall and per
role. Tokens are a proxy for energy use and climate impact, cost for the price of running a study.

$L$ is the set of recorded calls (every role: the Assistant, the autopilot and the Opponent), $L_a$ the
calls made by the Assistant or the autopilot and $L_o$ those made by the Opponent. $\tau(c)$ is the
tokens of call $c$ as reported by the provider (0 when it reported none).

**Caveats.** Only calls that go through HANI2's language-model service are recorded; an agent calling
a model on its own is invisible. Cost is known only when the provider's price is; the per-role and
per-model counts are in the details.
""", columns=[
    C("llm_calls", "LLM calls", "Language-model calls during the negotiation", formula=r"\lvert L \rvert",
      range="count",
      details=r"""
Every recorded language-model call, by any role.
"""),
    C("llm_tokens", "LLM tokens", "Prompt + completion tokens (energy / climate proxy)", False,
      formula=r"\sum_{c \in L} \tau(c)", range="tokens",
      details=r"""
Total tokens of every call: the provider's `total_tokens`, else prompt + completion tokens. Calls
without usage information count 0, so this is a lower bound when some providers do not report it.
"""),
    C("llm_cost_usd", "LLM cost (USD)", "Estimated cost of every call (when the provider's price is known)", False,
      formula=r"\sum_{c \in L,\ \text{cost}(c)\ \text{known}} \text{cost}(c)", range="US dollars",
      details=r"""
The summed estimated cost in US dollars of the calls whose price is known. Empty when no call has a
price; a lower bound when only some do.
"""),
    C("llm_latency_mean", "LLM latency (s)", "Mean seconds per call", False,
      formula=r"\frac{1}{\lvert L' \rvert} \sum_{c \in L'} \text{latency}(c), \qquad L' = \{c \in L : \text{latency known}\}",
      range="seconds",
      details=r"""
The mean time a call took. Long latencies make the Assistant or the Opponent feel slow.
"""),
    C("llm_error_rate", "LLM error rate", "Share of calls that failed", False,
      formula=r"\frac{\lvert \{c \in L : c\ \text{failed}\} \rvert}{\lvert L \rvert}", range="[0, 1]",
      details=r"""
The share of calls that raised an error. Empty without calls.
"""),
    C("support_llm_calls", "Assistant LLM calls", "Calls made by the Assistant", formula=r"\lvert L_a \rvert",
      range="count",
      details=r"""
Calls made by the Assistant, including the autopilot.
"""),
    C("support_tokens", "Assistant tokens", "Tokens used by the Assistant", False,
      formula=r"\sum_{c \in L_a} \tau(c)", range="tokens",
      details=r"""
Tokens used by the Assistant and the autopilot (see `llm_tokens`).
"""),
    C("opponent_llm_calls", "Opponent LLM calls", "Calls made by the opponent", formula=r"\lvert L_o \rvert",
      range="count",
      details=r"""
Calls made by the Opponent (an LLM-based opponent agent).
"""),
    C("opponent_tokens", "Opponent tokens", "Tokens used by the opponent", False,
      formula=r"\sum_{c \in L_o} \tau(c)", range="tokens",
      details=r"""
Tokens used by the Opponent (see `llm_tokens`).
"""),
])
def llm_usage(ctx: EvalContext, options: dict) -> dict:
    """Language-model calls, tokens, cost and latency, overall and per role."""
    calls = ctx.llm_calls

    def tok(c):
        u = c.get("usage") or {}
        return u.get("total_tokens") or ((u.get("prompt_tokens") or 0) + (u.get("completion_tokens") or 0)) or None

    def tsum(cs):
        v = [tok(c) for c in cs]
        v = [x for x in v if x]
        return int(sum(v)) if v else 0

    costs = [num(c.get("cost")) for c in calls]
    costs = [c for c in costs if c is not None]
    sup = [c for c in calls if c.get("role") in ("support", "autopilot")]
    opp = [c for c in calls if c.get("role") == "opponent"]
    by_role = Counter(c.get("role") for c in calls)
    by_model = Counter(c.get("model") for c in calls)
    return dict(
        llm_calls=len(calls), llm_tokens=tsum(calls), llm_cost_usd=float(sum(costs)) if costs else None,
        llm_latency_mean=mean([c.get("latency") for c in calls]),
        llm_error_rate=(sum(1 for c in calls if c.get("error")) / len(calls)) if calls else None,
        support_llm_calls=len(sup), support_tokens=tsum(sup), opponent_llm_calls=len(opp), opponent_tokens=tsum(opp),
        _details=dict(by_role=dict(by_role), by_model=dict(by_model)),
    )


# --------------------------------------------------------------------------- #
# Dynamics: move types (DANS) and theory of mind                              #
# --------------------------------------------------------------------------- #
MOVE_TYPES = ("silent", "nice", "fortunate", "unfortunate", "concession", "selfish")


def classify_move(d_self: float, d_other: float, eps: float = 1e-6) -> str:
    """The move type of a change of offer (Hindriks et al.'s DANS framework)."""
    s = 0 if abs(d_self) <= eps else (1 if d_self > 0 else -1)
    o = 0 if abs(d_other) <= eps else (1 if d_other > 0 else -1)
    if s == 0 and o == 0:
        return "silent"
    if s == 0 and o > 0:
        return "nice"
    if s > 0 and o > 0:
        return "fortunate"
    if s <= 0 and o <= 0:
        return "unfortunate"
    if s < 0 and o > 0:
        return "concession"
    return "selfish"  # s > 0, o <= 0  (or s == 0 and o < 0 handled above as unfortunate)


def _moves(seq: list[tuple[float | None, float | None]]) -> list[str]:
    out = []
    for (a_s, a_o), (b_s, b_o) in zip(seq, seq[1:]):
        if None in (a_s, a_o, b_s, b_o):
            continue
        out.append(classify_move(b_s - a_s, b_o - a_o))
    return out


#: the rule of every move type, on the change of the mover's own utility (Δs) and of the other side's (Δo)
MOVE_RULES = {
    "silent": (r"\lvert \Delta^{s}_k \rvert \leq \epsilon \ \wedge\ \lvert \Delta^{o}_k \rvert \leq \epsilon",
               "neither utility changed (the same offer, or one worth the same to both)"),
    "nice": (r"\lvert \Delta^{s}_k \rvert \leq \epsilon \ \wedge\ \Delta^{o}_k > \epsilon",
             "the other side gained at no cost to the mover"),
    "fortunate": (r"\Delta^{s}_k > \epsilon \ \wedge\ \Delta^{o}_k > \epsilon", "both sides gained"),
    "unfortunate": (r"\Delta^{s}_k, \Delta^{o}_k \leq \epsilon,\ \text{not silent}",
                    "neither side gained and at least one lost (a move that helps nobody)"),
    "concession": (r"\Delta^{s}_k < -\epsilon \ \wedge\ \Delta^{o}_k > \epsilon",
                   "the mover gave up utility and the other side gained"),
    "selfish": (r"\Delta^{s}_k > \epsilon \ \wedge\ \Delta^{o}_k \leq \epsilon",
                "the mover gained and the other side did not"),
}

_MOVE_SEQ = {
    "human_move": ("the Human seat's consecutive offers $o^h_k$, with $\\Delta^s_k = u_h(o^h_{k+1}) - u_h(o^h_k)$ "
                   "and $\\Delta^o_k = u_o(o^h_{k+1}) - u_o(o^h_k)$"),
    "opponent_move": ("the Opponent's consecutive offers $o^o_k$, with $\\Delta^s_k = u_o(o^o_{k+1}) - u_o(o^o_k)$ "
                      "and $\\Delta^o_k = u_h(o^o_{k+1}) - u_h(o^o_k)$"),
    "suggested_move": ("the Assistant's suggestions (offers it filled in), each compared with the Human seat's latest "
                       "offer before it (or, before any offer, with the previous suggestion), with $\\Delta^s_k$ the "
                       "change of $u_h$ and $\\Delta^o_k$ the change of $u_o$"),
}


def _move_cols(prefix: str, who: str) -> list:
    cols = []
    for m in MOVE_TYPES:
        rule, plain = MOVE_RULES[m]
        cols.append(C(
            f"{prefix}_{m}", f"{who}: {m}", f"Share of {who.lower()} moves that were {m}",
            formula=(r"\frac{\left\lvert \{k : m_k = \text{%s}\} \right\rvert}{M}, \qquad m_k = \text{%s} \iff %s"
                     % (m, m, rule)),
            range="[0, 1]",
            details=(f"The share of the {who.lower()} moves that were **{m}**: {plain}. A move $k$ is the change "
                     f"between {_MOVE_SEQ[prefix]}; $M$ is the number of moves whose utilities are known and "
                     r"$\epsilon = 10^{-6}$. The six shares of one side add up to 1. Empty when there are no moves "
                     "(for the Human and the Opponent: fewer than two offers; for suggestions: no suggestion "
                     "after an offer or another suggestion)."),
        ))
    return cols


@metric("dynamics", kind="hard", title="Negotiation dynamics", figures=["move_types"],
        formula=r"\Delta^{s}_k = u_{\text{self}}(o_{k+1}) - u_{\text{self}}(o_k), \qquad \Delta^{o}_k = u_{\text{other}}(o_{k+1}) - u_{\text{other}}(o_k)",
        details=r"""
How each side moved through the outcome space: the type of every move of the Human, of the Opponent
and of the Assistant's suggestions, how much the Human conceded, and how soon the Human's offers took
the Opponent's interests into account (a behavioural sign of theory of mind).

A **move** is the change from one offer of a side to its next. It is classified by the change of the
mover's own utility $\Delta^s$ and of the other side's $\Delta^o$ (Hindriks, Jonker and Tykhonov's
dynamics analysis of negotiation strategies), with changes of at most $\epsilon = 10^{-6}$ counting as
none:

* **silent** — neither changed;
* **nice** — $\Delta^s = 0$, $\Delta^o > 0$;
* **fortunate** — both up;
* **concession** — $\Delta^s < 0$, $\Delta^o > 0$;
* **selfish** — $\Delta^s > 0$, $\Delta^o \leq 0$;
* **unfortunate** — $\Delta^s \leq 0$, $\Delta^o \leq 0$ (and not silent).

**Example.** The Human offers A $(1.0, 0.2)$, then B $(0.8, 0.6)$, then B again, then C $(0.62, 0.75)$:
the moves are concession ($-0.2$, $+0.4$), silent, concession. `human_move_concession` $= 2/3$,
`human_move_silent` $= 1/3$, `human_concession` $= 1.0 - 0.62 = 0.38$ and `tom_reflect_index` $= 1/3$.

**Caveats.** A move with $\Delta^s < 0$ and $\Delta^o = 0$ counts as unfortunate and one with
$\Delta^s > 0$ and $\Delta^o = 0$ as selfish. The Opponent side's utility is summed over every
non-Human party. Offers whose utilities are unknown are skipped.
""", columns=[
    *_move_cols("human_move", "Human"),
    *_move_cols("opponent_move", "Opponent"),
    *_move_cols("suggested_move", "Assistant suggestion"),
    C("human_concession", "Human concession", "Utility the human gave up from the first to the last offer",
      formula=r"u_h(o^h_1) - u_h(o^h_K)", range="utility difference",
      details=r"""
How much the Human seat's own utility dropped from its first offer to its last ($K$ offers with a
known utility, at least 2). Positive means the Human conceded, negative that they hardened. Example:
first offer worth $1.0$, last worth $0.62$ gives $0.38$. Neither higher nor lower is better in itself.
"""),
    C("human_offer_pareto_distance", "Human offers' Pareto distance", "Mean distance of the human's offers from the Pareto frontier", False,
      formula=r"\frac{1}{K} \sum_{k=1}^{K} D_{\mathcal{P}}(o^h_k)", range="≥ 0",
      details=r"""
How efficient the Human's offers were on average: 0 when every offer was Pareto optimal. Lower is
better. Offers far from the frontier hurt both sides. Not computed without a utility table.
"""),
    C("tom_reflect_index", "Theory of mind: reflect index",
      "Share of the human's moves up to the first one that raised the opponent's utility (lower = sooner)", False,
      formula=r"R = \frac{k^\star}{M}, \qquad k^\star = \min\{k : \Delta^{o}_k > \epsilon\} \quad (R = 1 \text{ if there is none})",
      range="(0, 1]",
      details=r"""
How soon the Human's offers started to reflect the Opponent's interests: $k^\star$ is the (1-based)
index of the Human's first nice, fortunate or concession move (the moves that raise the Opponent's
utility) among their $M$ moves. Lower means sooner. Example: moves selfish, silent, concession,
nice give $R = 3/4$.

Caveat: a Human who never raised the Opponent's utility gets 1, the same as one who did so only on
the last move. Empty without moves.
"""),
    C("tom_other_trend", "Theory of mind: other's-utility trend",
      "Correlation of the opponent's utility of the human's offers with their order (higher = the human moved toward the other's interests)", True,
      formula=r"\rho\big(k,\ u_o(o^h_k)\big) = \frac{\operatorname{cov}(k, u_o(o^h_k))}{\sigma_k \, \sigma_{u_o}}",
      range="[−1, 1]",
      details=r"""
The Pearson correlation between the position $k$ of each Human offer and the Opponent's utility of it:
near 1 when the Human's offers steadily moved toward what the Opponent wants, near −1 when they moved
away. It uses the order of the offers, not their times. Empty with fewer than 3 offers or when the
Opponent's utility never changed.
"""),
])
def dynamics(ctx: EvalContext, options: dict) -> dict:
    """Move types of each side and of the assistant's suggestions, concession and
    how quickly the human's offers reflect the other's perspective."""
    out: dict = {}
    hum = [(o["hu"], o["ou"]) for o in ctx.human_offers]
    opp = [(o["ou"], o["hu"]) for o in ctx.opponent_offers]  # self = opponent
    # suggestions relative to the human's previous offer (or the previous suggestion)
    sug_seq: list[tuple] = []
    last_h = None
    events = sorted([(a["t"], "act", a) for a in ctx.acts if a.get("type") == "offer"]
                    + [(d["t"], "draft", d) for d in ctx.drafts if d.get("by") == "agent" and d.get("values")],
                    key=lambda x: x[0])
    names = ctx.scenario.get("issue_names") or []
    sug_moves = []
    for _, kind, e in events:
        offer = e.get("offer") if kind == "act" else [e["values"].get(n) for n in names]
        pt = (ctx.hu(offer), ctx.ou(offer))
        if kind == "act":
            last_h = pt
        else:
            base = last_h if last_h is not None else (sug_seq[-1] if sug_seq else None)
            if base is not None and None not in base and None not in pt:
                sug_moves.append(classify_move(pt[0] - base[0], pt[1] - base[1]))
            sug_seq.append(pt)
    for prefix, mv in (("human_move", _moves(hum)), ("opponent_move", _moves(opp)), ("suggested_move", sug_moves)):
        c = Counter(mv)
        n = len(mv)
        for m in MOVE_TYPES:
            out[f"{prefix}_{m}"] = c[m] / n if n else None
    hs = [h for h, _ in hum if h is not None]
    out["human_concession"] = (hs[0] - hs[-1]) if len(hs) >= 2 else None
    if ctx.has_scenario and ctx.human_offers:
        ds = [ctx.dist_to_pareto(np.array([h, o])) for h, o in hum if h is not None and o is not None]
        out["human_offer_pareto_distance"] = mean(ds)
    hm = _moves(hum)
    first = next((i for i, m in enumerate(hm) if m in ("nice", "fortunate", "concession")), None)
    out["tom_reflect_index"] = ((first + 1) / len(hm)) if hm and first is not None else (1.0 if hm else None)
    os_ = [o for _, o in hum if o is not None]
    if len(os_) >= 3 and np.std(os_) > 0:
        out["tom_other_trend"] = float(np.corrcoef(np.arange(len(os_)), os_)[0, 1])
    else:
        out["tom_other_trend"] = None
    out["_details"] = dict(human_moves=hm, opponent_moves=_moves(opp), suggested_moves=sug_moves)
    return out


# --------------------------------------------------------------------------- #
# Timing and engagement                                                        #
# --------------------------------------------------------------------------- #
@metric("timing", kind="hard", title="Timing",
        formula=r"\delta_a = t_a - \max\{s \in S : s \leq t_a\}",
        details=r"""
How long the Human took per decision and overall. Very short decision times suggest a participant who
is not engaged; very long ones a hard decision or a distraction.

For every action $a$ the Human took themselves (an offer, an acceptance, ending, or a text message) at
time $t_a$, the decision time $\delta_a$ is the time since the latest start of the Human's turn. The
turn starts $S$ are the moments the screen switched to "your turn" (from the recorded screen states).
Actions of the Assistant or the autopilot are not decisions of the Human and are left out.

**Example.** The turn starts at $10$ s; the Human sends a message at $12$ s and then offers at
$14.5$ s. The two decisions take $2$ s and $4.5$ s (both from the same turn start).

**Recordings without a browser.** They have no screen states; the turn starts are then the `turn`
events the session writes when the Opponent has answered and it is the Human's turn again. Older
recordings have neither: a turn then starts with the negotiation or with the Human's previous move
(an offer, acceptance or ending; messages do not end a turn), so the Opponent's thinking time is
counted as part of the decision.
""", columns=[
    C("decision_time_mean", "Decision time (s)", "Mean time from the start of the human's turn to their action",
      formula=r"\frac{1}{\lvert A_h \rvert} \sum_{a \in A_h} \delta_a", range="seconds",
      details=r"""
The mean decision time over the Human's own actions $A_h$. Sensitive to a single long pause; see the
median.
"""),
    C("decision_time_median", "Decision time, median (s)", "Median time per decision",
      formula=r"\operatorname{median}_{a \in A_h} \delta_a", range="seconds",
      details=r"""
The median decision time: robust to a few long pauses. `click_through` uses it.
"""),
    C("decision_time_min", "Fastest decision (s)", "Shortest time per decision",
      formula=r"\min_{a \in A_h} \delta_a", range="seconds",
      details=r"""
The shortest decision time. Near 0 means at least one action was taken without reading the
Opponent's offer.
"""),
    C("time_to_first_action", "Time to first action (s)", "From the start of the negotiation to the first human action",
      formula=r"t_{a_1} - t_{\text{start}}", range="seconds",
      details=r"""
Seconds from the start of the negotiation to the Human's first own action.
"""),
    C("load_to_start_seconds", "Reading time (s)", "From loading the scenario to starting the negotiation",
      formula=r"t_{\text{start}}", range="seconds",
      details=r"""
Seconds from loading the scenario (the start of the recording, time 0) to starting the negotiation:
the time spent reading the instructions and the preferences.
"""),
    C("questionnaire_seconds", "Questionnaire time (s)", "Time spent on the questionnaire",
      formula=r"t_{\text{submitted}} - t_{\text{shown}}", range="seconds",
      details=r"""
Seconds from the moment the questionnaire appeared on screen to its submission. Very short times
suggest answers given without reading. Empty without a questionnaire or without screen states.
"""),
])
def timing(ctx: EvalContext, options: dict) -> dict:
    """Interaction time per decision and overall."""
    acts = [a for a in ctx.acts if a.get("actor") == "human" and a.get("type") in ("offer", "accept", "end", "text")]
    starts = ctx.turn_starts
    if starts:
        def latest(t):
            return max((s for s in starts if s <= t), default=None)
    else:
        # older recordings without a browser or turn events: a turn starts with the negotiation or
        # with the human's previous move (text messages do not end a turn)
        starts = [ctx.started_at or 0.0] + [a["t"] for a in acts if a.get("type") != "text"]

        def latest(t):
            return max((s for s in starts if s < t), default=None)
    times = []
    for a in acts:
        s = latest(a["t"])
        if s is not None:
            times.append(a["t"] - s)
    q = ctx.rec.questionnaire
    qs = None
    if q is not None:
        shown = None
        for t, _, st in ctx.rec.states():
            if st.get("phase") == "questionnaire":
                shown = t
                break
        qs = (q["t"] - shown) if shown is not None else None
    return dict(
        decision_time_mean=mean(times), decision_time_median=median(times),
        decision_time_min=min(times) if times else None,
        time_to_first_action=(acts[0]["t"] - ctx.started_at) if acts and ctx.started_at is not None else None,
        load_to_start_seconds=ctx.started_at, questionnaire_seconds=qs,
        _details=dict(decision_times=times),
    )


@metric("activity", kind="hard", title="Activity (mouse, keyboard, attention)",
        formula=r"\text{idle} = \sum_{i : g_i > 5\,\text{s}} g_i, \qquad g_i = \tau_{i+1} - \tau_i, \quad (\tau_i) = (t_0, \text{inputs in } [t_0, t_1], t_1)",
        details=r"""
Low-level interaction recorded by the browser (telemetry): clicks, key presses, pointer travel,
scrolling, idle time and attention (time away from the page). Use it to spot participants who were
not paying attention.

$t_0$ is the start of the negotiation and $t_1$ its end (the end of the recording if it did not end).
Inputs are pointer moves and presses, clicks, key presses, scrolls and form inputs.

**Example.** A negotiation from $t_0 = 0$ to $t_1 = 60$ s with inputs at $2, 3, 20, 24, 58$ s has gaps
$2, 1, 17, 4, 34, 2$; the gaps longer than 5 s add up to $51$ s, so `idle_fraction` $= 51/60 = 0.85$.

**Caveats.** Counts, pointer distance and hidden time cover the whole recording (including reading the
instructions and the questionnaire); only the idle fraction is restricted to the negotiation. Pixel
distances depend on the screen size and zoom. Without telemetry only `has_telemetry` (0) is set.
""", columns=[
    C("n_clicks", "Clicks", "Mouse / touch clicks", formula=r"\lvert \{e : \text{type}(e) = \text{click}\} \rvert",
      range="count",
      details=r"""
Clicks and taps over the whole recording.
"""),
    C("n_keys", "Key presses", "Keys pressed", formula=r"\lvert \{e : \text{type}(e) = \text{key}\} \rvert",
      range="count",
      details=r"""
Key presses over the whole recording (typing chat messages and offers).
"""),
    C("mouse_distance", "Mouse distance (px)", "Distance travelled by the pointer",
      formula=r"\sum_{i \geq 2} \left\lVert x_i - x_{i-1} \right\rVert_2", range="pixels",
      details=r"""
The distance the pointer travelled, summed between consecutive pointer positions $x_i$ (moves, presses,
releases and clicks) over the whole recording, rounded to 0.1 px.
"""),
    C("n_scrolls", "Scrolls", "Scroll events", formula=r"\lvert \{e : \text{type}(e) = \text{scroll}\} \rvert",
      range="count",
      details=r"""
Scroll events over the whole recording.
"""),
    C("idle_fraction", "Idle fraction", "Share of the negotiation without any input for more than 5 s",
      formula=r"\min\left(1, \frac{\text{idle}}{t_1 - t_0}\right)", range="[0, 1]",
      details=r"""
The share of the negotiation spent in pauses longer than 5 s without any input. Each such pause counts
in full (not only the part after 5 s). High values mean the participant was reading, thinking or away;
compare with `hidden_seconds`.
"""),
    C("hidden_seconds", "Away (s)", "Time the page was hidden (another tab or window)",
      formula=r"\sum_j \left(t^{\text{visible}}_j - t^{\text{hidden}}_j\right)", range="seconds",
      details=r"""
Seconds the page was hidden (the participant switched to another tab or minimised the window): each
"hidden" event until the next "visible" one; a page still hidden at the end counts until $t_1$.
"""),
    C("n_blur", "Focus lost", "Times the window lost focus", formula=r"\lvert \{e : \text{type}(e) = \text{blur}\} \rvert",
      range="count",
      details=r"""
How often the window lost the keyboard focus (another window was activated).
"""),
    C("has_telemetry", "Has telemetry", "1 if browser telemetry was recorded", formula=r"\mathbb{1}[\text{telemetry}]",
      range="0 or 1",
      details=r"""
1 when the browser sent telemetry. Recordings made without a browser (e.g. scripted sessions) have 0,
and the other activity columns are empty.
"""),
])
def activity(ctx: EvalContext, options: dict) -> dict:
    """Low-level interaction: clicks, keys, pointer travel, idle time and attention."""
    tel = ctx.telemetry
    if not tel:
        return dict(has_telemetry=0)
    t0 = ctx.started_at or 0.0
    t1 = ctx.ended_at or ctx.rec.duration
    clicks = keys = scrolls = blur = 0
    dist = 0.0
    last = None
    inputs = []
    hidden, hidden_since = 0.0, None
    for t, typ, p in tel:
        if typ in ("mm", "pd", "pu", "click") and len(p) >= 2:
            try:
                xy = (float(p[0]), float(p[1]))
                if last is not None:
                    dist += math.dist(last, xy)
                last = xy
            except (TypeError, ValueError):
                pass
        if typ == "click":
            clicks += 1
        elif typ == "key":
            keys += 1
        elif typ == "scroll":
            scrolls += 1
        elif typ == "blur":
            blur += 1
        elif typ == "vis":
            if p and p[0] == "hidden" and hidden_since is None:
                hidden_since = t
            elif p and p[0] == "visible" and hidden_since is not None:
                hidden += t - hidden_since
                hidden_since = None
        if typ in ("mm", "pd", "click", "key", "scroll", "input") and t0 <= t <= t1:
            inputs.append(t)
    if hidden_since is not None:
        hidden += max(0.0, t1 - hidden_since)
    idle = 0.0
    pts = [t0] + inputs + [t1]
    for a, b in zip(pts, pts[1:]):
        if b - a > 5:
            idle += b - a
    span = max(1e-9, t1 - t0)
    return dict(n_clicks=clicks, n_keys=keys, mouse_distance=round(dist, 1), n_scrolls=scrolls,
                idle_fraction=min(1.0, idle / span), hidden_seconds=hidden, n_blur=blur, has_telemetry=1)


@metric("system_use", kind="hard", title="Use of the assistant and tools",
        formula=r"\text{adoption} = \frac{\lvert \{a \in A^{\text{offer}}_h : a\ \text{after a suggestion},\ a = \text{suggestion}\} \rvert}{\lvert \{a \in A^{\text{offer}}_h : a\ \text{after a suggestion}\} \rvert}",
        details=r"""
How the Human actually used the system: chat with the Assistant, the Assistant's suggestions and
whether they were taken, offers explored in the editor before acting, tools, and who acted on the
Human's seat.

The events are read in time order. A **suggestion** is an offer the Assistant filled into the Human's
editor; it stays pending until the Human makes an offer or the Assistant or autopilot acts on the
seat. A Human offer made while a suggestion is pending is **adopted** when it equals the suggestion on
every issue, otherwise the suggestion was **ignored**. An **exploration** is an offer the Human edited in
the editor. Seat actions are offers, acceptances, ending and text messages.

**Example.** The Assistant suggests X, the Human sends X; the Assistant suggests Y, the Human tries two
offers in the editor and sends Z. Then `n_suggestions` $= 2$, `suggestion_adoption` $= 1/2$,
`suggestions_ignored` $= 1$, `drafts_explored` $= 2$ and `drafts_per_action` $= (0 + 2)/2 = 1$.
""", columns=[
    C("n_user_messages", "Messages to assistant", "Chat messages the human sent to the assistant",
      formula=r"\lvert \{c \in \text{chat} : \text{by Human}\} \rvert", range="count",
      details=r"""
Chat messages the Human wrote to the Assistant.
"""),
    C("n_assistant_messages", "Assistant messages", "Messages the assistant posted",
      formula=r"\lvert \{c \in \text{chat} : \text{not by Human}\} \rvert", range="count",
      details=r"""
Chat messages posted by the Assistant (every chat message not written by the Human).
"""),
    C("n_suggestions", "Suggestions", "Drafts (offers or messages) the assistant filled in for the human",
      formula=r"\lvert \{d \in \text{drafts} : \text{by Assistant}\} \rvert", range="count",
      details=r"""
Drafts the Assistant wrote into the Human's editor: filled-in offers and drafted messages to the
Opponent (both count).
"""),
    C("suggestion_adoption", "Suggestion adoption", "Share of human offers made after a suggestion that were exactly the suggestion",
      formula=r"\frac{n_{\text{adopted}}}{n_{\text{adopted}} + n_{\text{ignored}}}", range="[0, 1]",
      details=r"""
Of the Human's offers made while a suggestion was pending, the share that were exactly the suggestion
(compared issue by issue as text). 1 means every suggestion that was followed by an offer was taken.
Offers made with no suggestion pending do not count. Empty when no offer followed a suggestion.
"""),
    C("suggestions_ignored", "Suggestions ignored", "Suggestions followed by a different offer",
      formula=r"n_{\text{ignored}}", range="count",
      details=r"""
Human offers made while a suggestion was pending that differed from it.
"""),
    C("drafts_explored", "Offers explored", "Counter-offers the human tried in the editor before acting",
      formula=r"\lvert \{d \in \text{drafts} : \text{by Human, with offer values}\} \rvert", range="count",
      details=r"""
How many offers the Human tried in the offer editor (each change of the edited offer). A sign of an
invested participant who weighs alternatives.
"""),
    C("drafts_per_action", "Offers explored per action", "Mean explorations before each human action",
      formula=r"\frac{1}{\lvert A_h \rvert} \sum_{a \in A_h} \left\lvert \{d : \text{Human draft between the previous Human action and } a\} \right\rvert",
      range="≥ 0",
      details=r"""
The mean number of explored offers before each of the Human's own seat actions.
"""),
    C("n_tool_interactions", "Tool interactions", "Inputs and actions in tools",
      formula=r"\lvert \{e : \text{tool interaction}\} \rvert", range="count",
      details=r"""
Inputs and actions the Human made in the tools (sliders, buttons, forms, …).
"""),
    C("n_tools_used", "Tools used", "Distinct tools the human used",
      formula=r"\lvert \{\text{component}(e) : e\ \text{tool interaction}\} \rvert", range="count",
      details=r"""
How many different tool components the Human interacted with.
"""),
    C("n_tab_changes", "Tab changes", "Tool tabs opened", formula=r"\lvert \{e : \text{tab changed}\} \rvert",
      range="count",
      details=r"""
How often the Human switched between tool tabs.
"""),
    C("actions_by_human", "Actions by human", "Share of the seat's actions taken by the human",
      formula=r"\frac{\lvert A^{\text{seat}}_{\text{Human}} \rvert}{\lvert A^{\text{seat}} \rvert}", range="[0, 1]",
      details=r"""
The share of the Human seat's actions (offers, acceptances, ending, messages) the Human took
themselves. The three `actions_by_*` shares add up to 1. Empty without seat actions.
"""),
    C("actions_by_agent", "Actions by assistant", "Share taken by the assistant",
      formula=r"\frac{\lvert A^{\text{seat}}_{\text{Assistant}} \rvert}{\lvert A^{\text{seat}} \rvert}", range="[0, 1]",
      details=r"""
The share of the Human seat's actions the Assistant took for the Human.
"""),
    C("actions_by_autopilot", "Actions by autopilot", "Share taken by the autopilot",
      formula=r"\frac{\lvert A^{\text{seat}}_{\text{autopilot}} \rvert}{\lvert A^{\text{seat}} \rvert}", range="[0, 1]",
      details=r"""
The share of the Human seat's actions the autopilot took.
"""),
])
def system_use(ctx: EvalContext, options: dict) -> dict:
    """Actual system use: messages, suggestions and how they were used, exploration and tools."""
    chat = ctx.chat
    user_msgs = [c for c in chat if ctx.is_human_chat(c)]
    agent_msgs = [c for c in chat if not ctx.is_human_chat(c)]
    names = ctx.scenario.get("issue_names") or []
    seat = [a for a in ctx.acts if a.get("type") in ("offer", "accept", "end", "text")]
    timeline = sorted([(d["t"], "d", d) for d in ctx.drafts] + [(a["t"], "a", a) for a in seat], key=lambda x: x[0])
    last_sugg = None
    adopted = ignored = after_sugg = 0
    explored, per_action, cur = 0, [], 0
    for _, kind, e in timeline:
        if kind == "d":
            if e.get("by") == "agent" and e.get("values"):
                last_sugg = [e["values"].get(n) for n in names]
            elif e.get("by") == "human" and e.get("values"):
                explored += 1
                cur += 1
            continue
        if e.get("actor") != "human":
            last_sugg = None
            continue
        per_action.append(cur)
        cur = 0
        if e.get("type") == "offer" and last_sugg is not None:
            after_sugg += 1
            if [str(v) for v in (e.get("offer") or [])] == [str(v) for v in last_sugg]:
                adopted += 1
            else:
                ignored += 1
            last_sugg = None
    evs = ctx.rec.of("ev")
    tool_ev = [e for e in evs if e.get("type") == "tool_interaction"]
    by = Counter(a.get("actor") for a in seat)
    n = len(seat)
    return dict(
        n_user_messages=len(user_msgs), n_assistant_messages=len(agent_msgs),
        n_suggestions=sum(1 for d in ctx.drafts if d.get("by") == "agent"),
        suggestion_adoption=adopted / after_sugg if after_sugg else None, suggestions_ignored=ignored,
        drafts_explored=explored, drafts_per_action=mean(per_action),
        n_tool_interactions=len(tool_ev), n_tools_used=len({e.get("component") for e in tool_ev}),
        n_tab_changes=sum(1 for e in evs if e.get("type") == "tab_changed"),
        actions_by_human=by["human"] / n if n else None, actions_by_agent=by["agent"] / n if n else None,
        actions_by_autopilot=by["autopilot"] / n if n else None,
    )


@metric("engagement_flags", kind="hard", title="Engagement flags",
        options={"click_through_seconds": "Median decision time (s) under which a session counts as click-through (default 3)."},
        formula=r"\text{click\_through} = \mathbb{1}\left[\lvert A_h \rvert > 0 \wedge \operatorname{median} \delta < \theta \wedge \text{drafts\_explored} = 0\right]",
        details=r"""
Flags for sessions to inspect or remove before an analysis: a participant who never acted, clicked
through as fast as possible, blindly followed the Assistant or never took a suggestion. They reuse the
`timing` and `system_use` values. The option `click_through_seconds` sets the threshold $\theta$
(default 3 s).
""", columns=[
    C("never_acted", "Never acted", "1 if the human never took an action themselves (filter out)", False,
      formula=r"\mathbb{1}\left[\lvert A_h \rvert = 0\right]", range="0 or 1",
      details=r"""
1 when the Human took no action of any kind themselves: everything was done by the Assistant, the
autopilot or the Opponent. Usually filtered out.
"""),
    C("click_through", "Click-through", "1 if the human acted very fast without exploring offers (not invested)", False,
      formula=r"\mathbb{1}\left[\lvert A_h \rvert > 0 \ \wedge\ \operatorname{median}_{a} \delta_a < \theta \ \wedge\ \text{drafts\_explored} = 0\right]",
      range="0 or 1",
      details=r"""
1 when the Human acted, their median decision time was under $\theta$ seconds (default 3) and they
never explored an offer in the editor: a participant clicking through without engaging.
"""),
    C("always_follows", "Always follows assistant", "1 if every human offer made after a suggestion was the suggestion (≥ 3 offers)", False,
      formula=r"\mathbb{1}\left[\text{adoption} \geq 0.999 \ \wedge\ \lvert A^{\text{offer}}_h \rvert \geq 3\right]",
      range="0 or 1",
      details=r"""
1 when the Human made at least 3 offers and every offer they made after a suggestion was the
suggestion: possibly blind trust in the Assistant. Offers made with no suggestion pending are not
checked.
"""),
    C("never_follows", "Never follows assistant", "1 if no suggestion was ever taken (≥ 3 suggestions)",
      formula=r"\mathbb{1}\left[n_{\text{suggestions}} \geq 3 \ \wedge\ \text{adoption} \in \{0, \varnothing\}\right]",
      range="0 or 1",
      details=r"""
1 when the Assistant made at least 3 suggestions (offers or messages) and the Human never sent one of
them (including when no offer followed a suggestion at all).
"""),
])
def engagement_flags(ctx: EvalContext, options: dict) -> dict:
    """Flags for sessions to inspect or remove: never acted, clicking through,
    blindly following or always ignoring the assistant. Options:
    ``click_through_seconds`` (default 3)."""
    su = system_use(ctx, options)
    tm = timing(ctx, options)
    human = [a for a in ctx.acts if a.get("actor") == "human"]
    thr = float(options.get("click_through_seconds", 3.0))
    med = tm.get("decision_time_median")
    adoption = su.get("suggestion_adoption")
    n_h = sum(1 for a in human if a.get("type") == "offer")
    return dict(
        never_acted=int(not human),
        click_through=int(bool(human) and med is not None and med < thr and (su.get("drafts_explored") or 0) == 0),
        always_follows=int(adoption is not None and adoption >= 0.999 and n_h >= 3),
        never_follows=int((su.get("n_suggestions") or 0) >= 3 and (adoption or 0) == 0),
    )


# --------------------------------------------------------------------------- #
# The Assistant as a conversational helper                                     #
# --------------------------------------------------------------------------- #
@metric("assistant_interaction", kind="hard", title="Assistant interaction quality",
        formula=r"\bar r = \frac{1}{\lvert Q \rvert} \sum_{(q, a) \in Q} (t_a - t_q)",
        details=r"""
The Assistant in conversation with the Human: how fast it answered, whether it left messages unanswered,
how often it spoke up on its own, its longest monologue and how often its function calls worked.

The chat is read in time order. A Human message $q$ waits for an answer; the next Assistant message
$a$ answers it ($Q$ is the set of such pairs). A Human message followed by another Human message
before any answer is unanswered (the newer one then waits). $q_1, \dots, q_n$ are the Human's messages and
$a$ the Assistant's.

**Example.** The Human writes at $10$ s and $12$ s, the Assistant answers at $15$ s and writes again at
$60$ s: the message at 10 s is unanswered, the response time is $15 - 12 = 3$ s, and the message at
60 s is proactive (48 s after the Human's last message). The longest streak is 2.
""", columns=[
    C("assistant_response_seconds", "Response time (s)", "Mean time from a human message to the assistant's next message", False,
      formula=r"\frac{1}{\lvert Q \rvert} \sum_{(q, a) \in Q} (t_a - t_q)", range="seconds",
      details=r"""
The mean time from a waiting Human message to the Assistant's next message. Lower is better. Empty
when the Assistant never answered.
"""),
    C("unanswered_messages", "Unanswered messages", "Human messages the assistant never answered", False,
      formula=r"\left\lvert \{ i : \nexists\, a \text{ with } t_{q_i} < t_a < t_{q_{i+1}} \} \right\rvert, \qquad t_{q_{n+1}} = \infty",
      range="count",
      details=r"""
Human messages the Assistant did not answer before the Human wrote again or the session ended.
"""),
    C("unsolicited_messages", "Proactive messages", "Assistant messages not answering the human (> 30 s after their last message)",
      formula=r"\lvert \{a : \text{no Human message waiting} \ \wedge\ (\text{no Human message yet} \vee t_a - t_{q_{\text{last}}} > 30\,\text{s})\} \rvert",
      range="count",
      details=r"""
Assistant messages that answered nothing: written before the Human's first message or more than 30 s
after their last one. Some proactivity is useful (warnings, explanations); a lot can be distracting.
"""),
    C("max_assistant_streak", "Longest monologue", "Most assistant messages in a row without the human writing",
      formula=r"\max \{\ell : \ell\ \text{consecutive Assistant messages}\}", range="count",
      details=r"""
The longest run of Assistant messages without a Human message in between.
"""),
    C("fn_calls", "Function calls", "Functions the assistant called", formula=r"\lvert F \rvert", range="count",
      details=r"""
Functions (tools) the Assistant called: filling in offers, reading the state, using tools, …
"""),
    C("fn_success_rate", "Function success", "Share of the assistant's function calls that succeeded", True,
      formula=r"\frac{\lvert \{f \in F : \text{result}(f)\ \text{is an object with}\ \text{ok} \neq \text{false}\} \rvert}{\lvert F \rvert}",
      range="[0, 1]",
      details=r"""
The share of function calls that worked. A call counts as failed when its result says `ok: false`
or when the result is not an object (e.g. an error text). Empty without calls; the calls per function
are in the details.
"""),
])
def assistant_interaction(ctx: EvalContext, options: dict) -> dict:
    """Responsiveness, unanswered messages, proactivity, monologues and function-call success."""
    chat = ctx.chat
    resp, unanswered, unsolicited, streak, best = [], 0, 0, 0, 0
    last_user = None
    pending = None
    for c in chat:
        if ctx.is_human_chat(c):
            if pending is not None:
                unanswered += 1
            pending = c["t"]
            last_user = c["t"]
            streak = 0
        else:
            if pending is not None:
                resp.append(c["t"] - pending)
                pending = None
            elif last_user is None or c["t"] - last_user > 30:
                unsolicited += 1
            streak += 1
            best = max(best, streak)
    if pending is not None:
        unanswered += 1
    fns = ctx.fn_calls
    ok = [f for f in fns if isinstance(f.get("result"), dict) and f["result"].get("ok") is not False]
    return dict(
        assistant_response_seconds=mean(resp), unanswered_messages=unanswered, unsolicited_messages=unsolicited,
        max_assistant_streak=best, fn_calls=len(fns), fn_success_rate=(len(ok) / len(fns)) if fns else None,
        _details=dict(fn_by_name=dict(Counter(f.get("name") for f in fns))),
    )
