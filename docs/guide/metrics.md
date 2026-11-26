<!-- Generated from the metric definitions in src/hani2/evaluation by scripts/make_metric_reference.py. Do not edit by hand. -->

# Metric reference

What every [evaluation metric](evaluation.md) and every column measures and exactly how it is calculated: a plain-language explanation, the formula, how to read it, a worked example and the caveats. The same texts are shown by `hani2 replay metrics --details [NAME]`, by the **Metric reference** panel of the replay tool (the ⓘ buttons next to metrics and columns) and by `GET /api/replay/metric-reference`.

## Notation

Every formula uses the same symbols.

* $\Omega$ — the outcomes of the scenario (every combination of issue values); $\omega \in \Omega$ one
  outcome, $\omega^*$ the agreement and $\varnothing$ "no agreement".
* $h$ — the Human's seat. Its offers and actions may be made by the Human, by the Assistant acting for
  them or by the autopilot; $A_h$ are the actions the Human took themselves.
* $u_h(\omega)$ — the Human's utility of $\omega$; $u_o(\omega) = \sum_{j \neq h} u_j(\omega)$ — the
  Opponent side's utility (the single Opponent in a bilateral negotiation, the sum of the other parties
  otherwise).
* $r_h$, $r_o = \sum_{j \neq h} r_j$ — the reservation values: what each side gets without an agreement
  (0 when the scenario gives none). $d = (r_h, r_o)$ is the disagreement (reservation) point.
* $p(\omega) = (u_h(\omega), u_o(\omega))$ — the outcome as a point of the utility space, with
  $p(\varnothing) = d$; $\lVert \cdot \rVert_2$ is the Euclidean distance in that space.
* $\bar u_h = \max_{\omega \in \Omega} u_h(\omega)$ and $\bar u_o = \max_{\omega \in \Omega} u_o(\omega)$ —
  each side's best possible utility; $(\bar u_h, \bar u_o)$ is the ideal point.
* $\mathcal{P}$ — the Pareto frontier: the outcomes $\omega$ for which no $\omega'$ has
  $u_h(\omega') \geq u_h(\omega)$ and $u_o(\omega') \geq u_o(\omega)$ with one of them strictly greater
  (of several outcomes with the same utilities, one is kept).
* $\nu$ — the Nash bargaining solution and $\kappa$ the Kalai–Smorodinsky solution (see `optimality`).
* $x^+ = \max(x, 0)$; $\mathbb{1}[\cdot]$ is 1 when the condition holds and 0 otherwise.
* $t$ — times in seconds on the recording clock (0 when the recording started, i.e. when the scenario
  was loaded).

The examples use one small scenario, drawn in the figure: eight outcomes A–H, reservation values
$r_h = r_o = 0.2$ and an agreement on F $= (0.5, 0.45)$.

## Hard metrics

Computed from the recording alone, with no judgement involved.

### `outcome` — Outcome

*hard*

Did the team reach a deal, and how good was it for each side?

$$
p(\omega^*) = \big(u_h(\omega^*),\ u_o(\omega^*)\big), \qquad p(\varnothing) = d = (r_h, r_o)
$$

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

<figure class="metric-figure" id="fig-outcome_space">
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 560 440" width="560" role="img" aria-labelledby="os-t os-d" class="metric-figure" style="max-width:100%;height:auto;font-family:inherit">
<title id="os-t">Outcome space of the example scenario</title>
<desc id="os-d">Eight outcomes plotted by the Human utility (x) and the Opponent utility (y). Five lie on the Pareto frontier. The reservation point d is (0.2, 0.2). The Nash point is B, the Kalai-Smorodinsky point is C, the agreement F lies inside the frontier; its distances to C and B are drawn.</desc>
<rect x="158.0" y="32.0" width="320.0" height="272.0" fill="#6b74f0" fill-opacity="0.07"/>
<text x="342.0" y="66.0" font-size="11" fill="#6b74f0">individually rational (ZOPA)</text>
<rect x="158.0" y="168.0" width="240.0" height="136.0" fill="#d9922b" fill-opacity="0.12" stroke="#d9922b" stroke-dasharray="4 3" stroke-width="1"/>
<text x="278.0" y="287.0" font-size="11" fill="#d9922b" text-anchor="middle">Nash product of B = 0.6 × 0.4</text>
<g stroke="currentColor" stroke-opacity="0.55" stroke-width="1.2" fill="none"><path d="M78 372 H492 M78 372 V18"/></g>
<path d="M492 372 l-7 -4 v8 z M78 18 l-4 7 h8 z" fill="currentColor" fill-opacity="0.55"/>
<line x1="78.0" y1="372" x2="78.0" y2="377" stroke="currentColor" stroke-opacity="0.55"/>
<text x="78.0" y="390" font-size="11" text-anchor="middle" fill="currentColor" fill-opacity="0.75">0</text>
<line x1="73" y1="372.0" x2="78" y2="372.0" stroke="currentColor" stroke-opacity="0.55"/>
<text x="69" y="376.0" font-size="11" text-anchor="end" fill="currentColor" fill-opacity="0.75">0</text>
<line x1="158.0" y1="372" x2="158.0" y2="377" stroke="currentColor" stroke-opacity="0.55"/>
<text x="158.0" y="390" font-size="11" text-anchor="middle" fill="currentColor" fill-opacity="0.75">0.2</text>
<line x1="73" y1="304.0" x2="78" y2="304.0" stroke="currentColor" stroke-opacity="0.55"/>
<text x="69" y="308.0" font-size="11" text-anchor="end" fill="currentColor" fill-opacity="0.75">0.2</text>
<line x1="278.0" y1="372" x2="278.0" y2="377" stroke="currentColor" stroke-opacity="0.55"/>
<text x="278.0" y="390" font-size="11" text-anchor="middle" fill="currentColor" fill-opacity="0.75">0.5</text>
<line x1="73" y1="202.0" x2="78" y2="202.0" stroke="currentColor" stroke-opacity="0.55"/>
<text x="69" y="206.0" font-size="11" text-anchor="end" fill="currentColor" fill-opacity="0.75">0.5</text>
<line x1="478.0" y1="372" x2="478.0" y2="377" stroke="currentColor" stroke-opacity="0.55"/>
<text x="478.0" y="390" font-size="11" text-anchor="middle" fill="currentColor" fill-opacity="0.75">1</text>
<line x1="73" y1="32.0" x2="78" y2="32.0" stroke="currentColor" stroke-opacity="0.55"/>
<text x="69" y="36.0" font-size="11" text-anchor="end" fill="currentColor" fill-opacity="0.75">1</text>
<text x="278.0" y="412" font-size="13" text-anchor="middle" fill="currentColor">Human utility u<tspan font-size="10" dy="3">h</tspan></text>
<text transform="translate(24 202.0) rotate(-90)" font-size="13" text-anchor="middle" fill="currentColor">Opponent utility u<tspan font-size="10" dy="3">o</tspan></text>
<line x1="158.0" y1="304.0" x2="478.0" y2="32.0" stroke="#1fa77a" stroke-dasharray="2 4" stroke-width="1.4"/>
<line x1="478.0" y1="32.0" x2="398.0" y2="168.0" stroke="currentColor" stroke-opacity="0.5" stroke-dasharray="3 3"/>
<text x="450.0" y="100.0" font-size="11" fill="currentColor" fill-opacity="0.8">opposition</text>
<polyline points="118.0,32.0 218.0,66.0 326.0,117.0 398.0,168.0 478.0,304.0" fill="none" stroke="#6b74f0" stroke-width="2.2" stroke-linejoin="round"/>
<text x="130.0" y="93.2" font-size="12" fill="#6b74f0" font-weight="600">Pareto frontier 𝒫</text>
<line x1="278.0" y1="219.0" x2="326.0" y2="117.0" stroke="#e0525f" stroke-width="1.8"/>
<line x1="278.0" y1="219.0" x2="398.0" y2="168.0" stroke="#e0525f" stroke-width="1.6" stroke-dasharray="5 3"/>
<text x="266.0" y="161.2" font-size="11" fill="#e0525f" text-anchor="end">Pareto / Kalai distance 0.32</text>
<text x="342.0" y="212.2" font-size="11" fill="#e0525f">Nash distance 0.34</text>
<circle cx="198.0" cy="253.0" r="5" fill="none" stroke="#8a93a6" stroke-width="1.6"/>
<text x="206.0" y="257.0" font-size="12" fill="currentColor" fill-opacity="0.8">G</text>
<circle cx="358.0" cy="270.0" r="5" fill="none" stroke="#8a93a6" stroke-width="1.6"/>
<text x="366.0" y="274.0" font-size="12" fill="currentColor" fill-opacity="0.8">H</text>
<circle cx="478.0" cy="304.0" r="5" fill="#6b74f0"/>
<text x="462.0" y="296.0" font-size="12" fill="currentColor">A</text>
<circle cx="218.0" cy="66.0" r="5" fill="#6b74f0"/>
<text x="226.0" y="58.0" font-size="12" fill="currentColor">D</text>
<circle cx="118.0" cy="32.0" r="5" fill="#6b74f0"/>
<text x="126.0" y="24.0" font-size="12" fill="currentColor">E</text>
<path d="M398.0 160.0 l8 8 l-8 8 l-8 -8 z" fill="#d9922b" stroke="#d9922b"/>
<text x="409.0" y="172.0" font-size="12" fill="currentColor"><tspan font-weight="600">B</tspan> Nash point</text>
<path d="M326.0 108.0 l8 14 h-16 z" fill="#1fa77a"/>
<text x="337.0" y="113.0" font-size="12" fill="currentColor"><tspan font-weight="600">C</tspan> Kalai–Smorodinsky</text>
<circle cx="278.0" cy="219.0" r="6.5" fill="#e0525f"/>
<text x="268.0" y="237.0" font-size="12" fill="currentColor"><tspan font-weight="600">F</tspan> agreement ω</text>
<rect x="153.0" y="299.0" width="10" height="10" fill="currentColor"/>
<text x="167.0" y="320.0" font-size="12" fill="currentColor">d = (r<tspan font-size="9" dy="3">h</tspan><tspan dy="-3">, r</tspan><tspan font-size="9" dy="3">o</tspan><tspan dy="-3">) = (0.2, 0.2)</tspan></text>
<path d="M472.0 26.0 l12 12 M484.0 26.0 l-12 12" stroke="currentColor" stroke-width="2"/>
<text x="468.0" y="22.0" font-size="11" text-anchor="end" fill="currentColor" fill-opacity="0.85">ideal point (max u<tspan font-size="9" dy="3">h</tspan><tspan dy="-3">, max u</tspan><tspan font-size="9" dy="3">o</tspan><tspan dy="-3">)</tspan></text>
</svg>
<figcaption>The example scenario in the utility space: the Pareto frontier A–E, the reservation point d, the Nash point B (the largest product of gains, the shaded rectangle), the Kalai–Smorodinsky point C (on the dotted line from d to the ideal point), the agreement F and its distances, and the opposition of the scenario (from the ideal point to the frontier).</figcaption>
</figure>

#### `agreement` — Agreement

*1 if the negotiation ended with a deal*

**Range:** 0 or 1 · **Direction:** higher is better

$$
\mathbb{1}\left[\omega^* \neq \varnothing\right]
$$

1 when the negotiation ended with an agreement, 0 when it ended without one (broken off, timed out,
failed). Empty when the recording has no result at all (the session was abandoned). Its mean over a
group of recordings is the **agreement rate**, and it is the default success criterion of pass^k.

#### `status` — Status

*success, broken, timedout, erred or agent_failed*

**Range:** category · **Direction:** no better direction

$$
\text{status} \in \{\text{success}, \text{broken}, \text{timedout}, \text{erred}, \text{agent\_failed}\}
$$

How the negotiation ended, as reported by the session: **success** (an agreement), **broken** (one side
ended it), **timedout** (the time or step limit was reached), **erred** (the mechanism failed) or
**agent_failed** (the Opponent agent raised an error). Use it to separate failed sessions from real
disagreements.

#### `ended_by` — Ended by

*Who ended it (accepted or broke off): human or agent*

**Range:** category · **Direction:** no better direction

$$
\text{ended\_by} \in \{\text{human}, \text{agent}\}
$$

Which side ended the negotiation by accepting an offer or breaking off: **human** is the Human's seat
(the Human, or the Assistant or autopilot acting for them), **agent** is the Opponent. Empty when the
negotiation ended by the time limit or an error.

#### `human_utility` — Human utility

*Utility of the result for the human–agent team*

**Range:** utility (usually [0, 1]) · **Direction:** higher is better

$$
u_h(\omega^*), \qquad u_h(\varnothing) = r_h
$$

What the result is worth to the Human side under the scenario's utility function. Higher is better.
Compare it with the reservation value $r_h$ (what the Human gets without a deal): a value below $r_h$
means the Human accepted a deal worse than walking away. Without an agreement it equals $r_h$.

#### `opponent_utility` — Opponent utility

*Utility of the result for the opponent*

**Range:** utility (usually [0, 1]) · **Direction:** no better direction

$$
u_o(\omega^*) = \sum_{j \neq h} u_j(\omega^*), \qquad u_o(\varnothing) = r_o
$$

What the result is worth to the Opponent side (summed over every non-Human party). It has no
"better" direction for the Human, but a very low value next to a high `human_utility` shows a
one-sided deal. Without an agreement it equals $r_o$.

#### `human_advantage` — Human advantage

*(u − reserved) / (max − reserved) for the human team*

**Range:** ≤ 1 (1 = the best outcome, 0 = no better than no deal) · **Direction:** higher is better

$$
A_h = \frac{u_h(\omega^*) - r_h}{\bar u_h - r_h}, \qquad \bar u_h = \max_{\omega \in \Omega} u_h(\omega)
$$

The share of the largest possible gain over walking away that the Human side obtained: 1 for the
Human's best outcome, 0 for an outcome worth exactly the reservation value, negative for a deal
below it. Unlike the raw utility it is comparable across scenarios with different reservation values.

Example: $u_h(\omega^*) = 0.5$, $r_h = 0.2$, $\bar u_h = 1$ gives $A_h = 0.3 / 0.8 = 0.375$.

It is 0 when $\bar u_h - r_h \le 10^{-12}$ (no outcome is better than no deal) and 0 without an agreement.
The maximum is over every outcome, not only those acceptable to the Opponent.

#### `opponent_advantage` — Opponent advantage

*The same for the opponent*

**Range:** ≤ 1 · **Direction:** no better direction

$$
A_o = \frac{u_o(\omega^*) - r_o}{\bar u_o - r_o}, \qquad \bar u_o = \max_{\omega \in \Omega} u_o(\omega)
$$

The Opponent side's share of its largest possible gain over no deal (see `human_advantage`). In the
example $A_o = (0.45 - 0.2)/(1 - 0.2) = 0.3125$. Empty when the scenario has no utility table.

#### `welfare` — Social welfare

*Sum of every party's utility*

**Range:** utility sum (usually [0, number of parties]) · **Direction:** higher is better

$$
W = u_h(\omega^*) + u_o(\omega^*)
$$

The total value created for both sides: higher means a more efficient (integrative) deal. Example:
$0.5 + 0.45 = 0.95$. Without an agreement it is $r_h + r_o$. Compare it across scenarios with
`welfare_optimality`, which divides by the best possible welfare.

#### `practice` — Practice

*1 for a practice round*

**Range:** 0 or 1 · **Direction:** no better direction

$$
\mathbb{1}\left[\text{practice round}\right]
$$

1 when the session was a practice round. Usually filtered out of analyses.

### `optimality` — Optimality

*hard*

How far the result is from the efficient and fair outcomes of the scenario.

$$
\begin{aligned} \nu &= \operatorname*{arg\,max}_{\omega \in \mathcal{P}} (u_h(\omega) - r_h)^+ (u_o(\omega) - r_o)^+ \\ \kappa &= \operatorname*{arg\,max}_{\omega \in \mathcal{P},\ p(\omega) \geq d} \min\left(\frac{u_h(\omega) - r_h}{\bar u_h - r_h}, \frac{u_o(\omega) - r_o}{\bar u_o - r_o}\right) \end{aligned}
$$

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

*Figure:* see [Outcome space of the example scenario](#fig-outcome_space) above.

#### `pareto_distance` — Pareto distance

*Distance of the result from the Pareto frontier (utility space)*

**Range:** ≥ 0 (0 = on the frontier) · **Direction:** lower is better

$$
D_{\mathcal{P}}(\omega^*) = \min_{\omega \in \mathcal{P}} \left\lVert p(\omega^*) - p(\omega) \right\rVert_2
$$

How much value the parties left on the table: 0 for a Pareto-optimal result, larger when both could
have been better off. Lower is better. Example: F $(0.5, 0.45)$ to C $(0.62, 0.75)$ gives
$\sqrt{0.12^2 + 0.30^2} = 0.323$.

#### `pareto_optimal` — Pareto optimal

*1 if the result is on the Pareto frontier*

**Range:** 0 or 1 · **Direction:** higher is better

$$
\mathbb{1}\left[D_{\mathcal{P}}(\omega^*) < 10^{-6}\right]
$$

1 when the result is (numerically) on the Pareto frontier. Its mean over recordings is the share of
efficient results. A no-deal result counts as optimal only if the reservation point itself lies on
the frontier (rare).

#### `nash_distance` — Nash distance

*Distance from the Nash bargaining solution*

**Range:** ≥ 0 · **Direction:** lower is better

$$
\left\lVert p(\omega^*) - p(\nu) \right\rVert_2
$$

How far the result is from the Nash bargaining solution $\nu$, the efficient outcome that maximises the
product of both sides' gains. Lower is better. Example: F to B gives
$\sqrt{0.3^2 + 0.15^2} = 0.335$. Empty when the Nash point is undefined.

#### `kalai_distance` — Kalai–Smorodinsky distance

*Distance from the Kalai–Smorodinsky solution*

**Range:** ≥ 0 · **Direction:** lower is better

$$
\left\lVert p(\omega^*) - p(\kappa) \right\rVert_2
$$

How far the result is from the Kalai–Smorodinsky solution $\kappa$, the efficient outcome where both
sides get the same share of their best possible gain. Lower is better. Example: F to C gives $0.323$.
Empty when no Pareto outcome is acceptable to both sides.

#### `welfare_optimality` — Welfare optimality

*Social welfare / the best possible welfare*

**Range:** usually [0, 1] · **Direction:** higher is better

$$
\frac{u_h(\omega^*) + u_o(\omega^*)}{\max_{\omega \in \Omega} \big(u_h(\omega) + u_o(\omega)\big)}
$$

The share of the largest total value the scenario allows that the result achieves: 1 for a
welfare-maximising deal. Example: $0.95 / 1.4 = 0.679$ (B has the largest sum, $1.4$). It is not
measured from the reservation point, so a no-deal result scores $(r_h + r_o)$ divided by the best
welfare. Empty when the best welfare is 0.

#### `nash_product_ratio` — Nash product ratio

*Nash product of the result / the largest possible*

**Range:** [0, 1] · **Direction:** higher is better

$$
\frac{(u_h(\omega^*) - r_h)^+ \, (u_o(\omega^*) - r_o)^+}{\max_{\omega \in \Omega} (u_h(\omega) - r_h)^+ \, (u_o(\omega) - r_o)^+}, \qquad x^+ = \max(x, 0)
$$

The result's product of gains over the reservation point relative to the best product (that of the
Nash point): 1 for the Nash solution, 0 when one side gains nothing (and for no deal). It rewards
results that are both efficient and balanced. Example: $(0.3 \times 0.25) / 0.24 = 0.3125$. Empty when
no outcome gives both sides a gain.

#### `fairness_gap` — Fairness gap

*|human advantage − opponent advantage|*

**Range:** ≥ 0 (0 = gains shared evenly) · **Direction:** lower is better

$$
\left\lvert A_h - A_o \right\rvert
$$

How unevenly the gains over no deal were shared, measured on the normalised advantages $A_h$ and
$A_o$ (see `human_advantage`). Lower is fairer. Example: $\lvert 0.375 - 0.3125 \rvert = 0.0625$.
A no-deal result has gap 0 (nobody gained), so read it together with `agreement`.

### `scenario_stats` — Scenario

*hard · not run by default*

Descriptors of the scenario (useful to balance comparisons).

$$
\Omega,\ \mathcal{P},\ (\bar u_h, \bar u_o)
$$

Descriptors of the scenario itself, not of how it was played: its size, how much of it is acceptable
to everyone and how competitive it is. Use them to balance or stratify comparisons (an agreement in a
highly opposed scenario is harder). Not run by default. Empty when the scenario has no utility table.

**Example** (the figure): 8 outcomes, 7 acceptable to both sides (only E gives the Human less than
$r_h$), 5 on the Pareto frontier, and the ideal point $(1, 1)$ is $0.447$ from the nearest Pareto
outcome (B).

*Figure:* see [Outcome space of the example scenario](#fig-outcome_space) above.

#### `n_outcomes` — Outcomes

*Number of possible outcomes*

**Range:** count · **Direction:** no better direction

$$
\lvert \Omega \rvert
$$

The number of outcomes in the scenario's utility table (all combinations of issue values).

#### `zopa_fraction` — ZOPA fraction

*Share of outcomes acceptable to every party (at least all reserved values)*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{1}{\lvert \Omega \rvert} \left\lvert \{\omega \in \Omega : u_j(\omega) \geq r_j \ \forall j\} \right\rvert
$$

The size of the zone of possible agreement: the share of outcomes that every party prefers to (or
values as much as) no deal. Each party is checked separately (not the summed Opponent side). Small
values mean a hard scenario where most deals are unacceptable to someone. Example: $7/8 = 0.875$.

#### `pareto_size` — Pareto size

*Number of Pareto-optimal outcomes*

**Range:** count · **Direction:** no better direction

$$
\lvert \mathcal{P} \rvert
$$

How many outcomes are Pareto optimal (in the Human vs Opponent-side utility space). Example: 5.

#### `opposition` — Opposition

*Distance of the ideal point (best for each side) from the frontier: how competitive the scenario is*

**Range:** ≥ 0 (0 = no conflict) · **Direction:** no better direction

$$
\min_{\omega \in \mathcal{P}} \left\lVert (\bar u_h, \bar u_o) - p(\omega) \right\rVert_2
$$

How far the ideal point (each side's best utility at once) is from what can actually be achieved:
0 when one outcome is the best for both (no conflict of interest), larger for more competitive
scenarios. Example: the ideal point $(1, 1)$ to B $(0.8, 0.6)$ gives $\sqrt{0.2^2 + 0.4^2} = 0.447$.
The ideal point is $(\bar u_h, \bar u_o)$, which is $(1, 1)$ only when both utilities reach 1.

### `length` — Length

*hard*

How long the negotiation took, in offers, steps and seconds.

$$
O = (o_1, \dots, o_{\lvert O \rvert}), \qquad O = O_h \cup O_o
$$

How long the negotiation took, in offers, mechanism steps and seconds. Long negotiations cost the
participant time and attention; very short ones may mean an early acceptance or a click-through.

$O$ is the sequence of offers in the mechanism's trace (both sides), $O_h$ those made from the Human's
seat (by the Human, or the Assistant or autopilot acting for them) and $O_o$ those of the Opponent.
Times are on the recording clock (seconds since the recording started).

**Caveat.** A session abandoned mid-negotiation has no trace: the offers are then the Human seat's
offer actions and the Opponent offers shown on screen.

#### `n_offers` — Offers

*Offers exchanged*

**Range:** count · **Direction:** no better direction

$$
\lvert O \rvert
$$

Every offer made in the negotiation, by both sides.

#### `n_human_offers` — Human offers

*Offers made by the human team*

**Range:** count · **Direction:** no better direction

$$
\lvert O_h \rvert
$$

Offers made from the Human's seat, whoever made them (the Human, the Assistant acting for them or
the autopilot). See `actions_by_human` for who acted.

#### `n_opponent_offers` — Opponent offers

*Offers made by the opponent*

**Range:** count · **Direction:** no better direction

$$
\lvert O_o \rvert
$$

Offers made by the Opponent.

#### `n_steps` — Steps

*Mechanism steps used*

**Range:** count · **Direction:** no better direction

$$
s_{\text{end}}
$$

The mechanism's step counter when the negotiation ended (from the result, else the last trace row).
In an alternating-offers protocol one step is one turn.

#### `relative_time` — Relative time

*Share of the time/step limit used*

**Range:** [0, 1] · **Direction:** no better direction

$$
\tau_{\text{end}} \in [0, 1]
$$

The mechanism's relative time when the negotiation ended: the fraction of its step or time limit that
was used (1 = the deadline was reached).

#### `negotiation_seconds` — Negotiation time (s)

*From the start to the end of the negotiation*

**Range:** seconds · **Direction:** no better direction

$$
t_{\text{result}} - t_{\text{start}}
$$

Wall-clock seconds from the moment the negotiation started to its result. Empty when either is missing
(e.g. an abandoned session).

#### `session_seconds` — Recording time (s)

*From loading the scenario to the end of the recording*

**Range:** seconds · **Direction:** no better direction

$$
t_{\text{last event}}
$$

The length of the whole recording: from loading the scenario (time 0) to its last event, so it
includes reading the instructions and the questionnaire.

#### `n_text_messages` — Text messages

*Offers or turns that carried a message to the other side*

**Range:** count · **Direction:** no better direction

$$
\left\lvert \{k : \text{text}_k \neq \varnothing\} \right\rvert
$$

Turns of the trace (both sides) that carried a text message, with or without an offer.

### `llm_usage` — LLM usage and cost

*hard*

Language-model calls, tokens, cost and latency, overall and per role.

$$
\tau(c) = \text{total\_tokens}(c) \ \text{or}\ \text{prompt\_tokens}(c) + \text{completion\_tokens}(c)
$$

Language-model calls made during the session, their tokens, cost, latency and failures, overall and per
role. Tokens are a proxy for energy use and climate impact, cost for the price of running a study.

$L$ is the set of recorded calls (every role: the Assistant, the autopilot and the Opponent), $L_a$ the
calls made by the Assistant or the autopilot and $L_o$ those made by the Opponent. $\tau(c)$ is the
tokens of call $c$ as reported by the provider (0 when it reported none).

**Caveats.** Only calls that go through HANI2's language-model service are recorded; an agent calling
a model on its own is invisible. Cost is known only when the provider's price is; the per-role and
per-model counts are in the details.

#### `llm_calls` — LLM calls

*Language-model calls during the negotiation*

**Range:** count · **Direction:** no better direction

$$
\lvert L \rvert
$$

Every recorded language-model call, by any role.

#### `llm_tokens` — LLM tokens

*Prompt + completion tokens (energy / climate proxy)*

**Range:** tokens · **Direction:** lower is better

$$
\sum_{c \in L} \tau(c)
$$

Total tokens of every call: the provider's `total_tokens`, else prompt + completion tokens. Calls
without usage information count 0, so this is a lower bound when some providers do not report it.

#### `llm_cost_usd` — LLM cost (USD)

*Estimated cost of every call (when the provider's price is known)*

**Range:** US dollars · **Direction:** lower is better

$$
\sum_{c \in L,\ \text{cost}(c)\ \text{known}} \text{cost}(c)
$$

The summed estimated cost in US dollars of the calls whose price is known. Empty when no call has a
price; a lower bound when only some do.

#### `llm_latency_mean` — LLM latency (s)

*Mean seconds per call*

**Range:** seconds · **Direction:** lower is better

$$
\frac{1}{\lvert L' \rvert} \sum_{c \in L'} \text{latency}(c), \qquad L' = \{c \in L : \text{latency known}\}
$$

The mean time a call took. Long latencies make the Assistant or the Opponent feel slow.

#### `llm_error_rate` — LLM error rate

*Share of calls that failed*

**Range:** [0, 1] · **Direction:** lower is better

$$
\frac{\lvert \{c \in L : c\ \text{failed}\} \rvert}{\lvert L \rvert}
$$

The share of calls that raised an error. Empty without calls.

#### `support_llm_calls` — Assistant LLM calls

*Calls made by the Assistant*

**Range:** count · **Direction:** no better direction

$$
\lvert L_a \rvert
$$

Calls made by the Assistant, including the autopilot.

#### `support_tokens` — Assistant tokens

*Tokens used by the Assistant*

**Range:** tokens · **Direction:** lower is better

$$
\sum_{c \in L_a} \tau(c)
$$

Tokens used by the Assistant and the autopilot (see `llm_tokens`).

#### `opponent_llm_calls` — Opponent LLM calls

*Calls made by the opponent*

**Range:** count · **Direction:** no better direction

$$
\lvert L_o \rvert
$$

Calls made by the Opponent (an LLM-based opponent agent).

#### `opponent_tokens` — Opponent tokens

*Tokens used by the opponent*

**Range:** tokens · **Direction:** lower is better

$$
\sum_{c \in L_o} \tau(c)
$$

Tokens used by the Opponent (see `llm_tokens`).

### `dynamics` — Negotiation dynamics

*hard*

Move types of each side and of the assistant's suggestions, concession and
how quickly the human's offers reflect the other's perspective.

$$
\Delta^{s}_k = u_{\text{self}}(o_{k+1}) - u_{\text{self}}(o_k), \qquad \Delta^{o}_k = u_{\text{other}}(o_{k+1}) - u_{\text{other}}(o_k)
$$

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

<figure class="metric-figure" id="fig-move_types">
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 420" width="520" role="img" aria-labelledby="mt-t mt-d" class="metric-figure" style="max-width:100%;height:auto;font-family:inherit">
<title id="mt-t">Move types</title>
<desc id="mt-d">A move is classified by the change of the mover's own utility (x axis) and of the other side's utility (y axis): fortunate (both up), concession (own down, other up), unfortunate (own not up and other not up, including the negative axes), selfish (own up, other not up, including the positive x axis), nice (own unchanged, other up) and silent (no change).</desc>
<rect x="260" y="40" width="160" height="160" fill="#1fa77a" fill-opacity="0.13"/>
<text x="340.0" y="116.0" font-size="15" font-weight="600" text-anchor="middle" fill="#1fa77a">fortunate</text>
<text x="340.0" y="134.0" font-size="11" text-anchor="middle" fill="currentColor" fill-opacity="0.8">Δself > 0, Δother > 0</text>
<rect x="100" y="40" width="160" height="160" fill="#6b74f0" fill-opacity="0.13"/>
<text x="180.0" y="116.0" font-size="15" font-weight="600" text-anchor="middle" fill="#6b74f0">concession</text>
<text x="180.0" y="134.0" font-size="11" text-anchor="middle" fill="currentColor" fill-opacity="0.8">Δself < 0, Δother > 0</text>
<rect x="100" y="200" width="160" height="160" fill="#e0525f" fill-opacity="0.13"/>
<text x="180.0" y="276.0" font-size="15" font-weight="600" text-anchor="middle" fill="#e0525f">unfortunate</text>
<text x="180.0" y="294.0" font-size="11" text-anchor="middle" fill="currentColor" fill-opacity="0.8">Δself ≤ 0, Δother ≤ 0</text>
<rect x="260" y="200" width="160" height="160" fill="#d9922b" fill-opacity="0.13"/>
<text x="340.0" y="276.0" font-size="15" font-weight="600" text-anchor="middle" fill="#d9922b">selfish</text>
<text x="340.0" y="294.0" font-size="11" text-anchor="middle" fill="currentColor" fill-opacity="0.8">Δself > 0, Δother ≤ 0</text>
<line x1="260" y1="200" x2="260" y2="40" stroke="#2aa3b8" stroke-width="4"/>
<line x1="260" y1="200" x2="420" y2="200" stroke="#d9922b" stroke-width="4"/>
<line x1="260" y1="200" x2="100" y2="200" stroke="#e0525f" stroke-width="4"/>
<line x1="260" y1="200" x2="260" y2="360" stroke="#e0525f" stroke-width="4"/>
<text x="268" y="56" font-size="13" font-weight="600" fill="#2aa3b8">nice</text>
<text x="268" y="71" font-size="11" fill="currentColor" fill-opacity="0.8">Δself = 0, Δother &gt; 0</text>
<circle cx="260" cy="200" r="9" fill="#8a93a6" stroke="currentColor" stroke-width="1.2"/>
<text x="246" y="188" font-size="13" font-weight="600" text-anchor="end" fill="currentColor">silent</text>
<g stroke="currentColor" stroke-opacity="0.6" fill="none"><path d="M94 200 H434 M260 366 V26"/></g>
<path d="M434 200 l-7 -4 v8 z M260 26 l-4 7 h8 z" fill="currentColor" fill-opacity="0.6"/>
<text x="430" y="220" font-size="13" text-anchor="end" fill="currentColor">Δself</text>
<text x="252" y="34" font-size="13" text-anchor="end" fill="currentColor">Δother</text>
<text x="260" y="404" font-size="11" text-anchor="middle" fill="currentColor" fill-opacity="0.8">Δself: change of the mover's own utility; Δother: change of the other side's. |Δ| ≤ ε = 10⁻⁶ counts as 0.</text>
</svg>
<figcaption>A move is the change from one offer of a side to its next, placed by the change of the mover&#x27;s own utility (Δself) and of the other side&#x27;s (Δother). The axes belong to the region of the same colour: Δother = 0 counts as selfish when Δself &gt; 0 and as unfortunate when Δself &lt; 0.</figcaption>
</figure>

#### `human_move_silent` — Human: silent

*Share of human moves that were silent*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\left\lvert \{k : m_k = \text{silent}\} \right\rvert}{M}, \qquad m_k = \text{silent} \iff \lvert \Delta^{s}_k \rvert \leq \epsilon \ \wedge\ \lvert \Delta^{o}_k \rvert \leq \epsilon
$$

The share of the human moves that were **silent**: neither utility changed (the same offer, or one worth the same to both). A move $k$ is the change between the Human seat's consecutive offers $o^h_k$, with $\Delta^s_k = u_h(o^h_{k+1}) - u_h(o^h_k)$ and $\Delta^o_k = u_o(o^h_{k+1}) - u_o(o^h_k)$; $M$ is the number of moves whose utilities are known and $\epsilon = 10^{-6}$. The six shares of one side add up to 1. Empty when there are no moves (for the Human and the Opponent: fewer than two offers; for suggestions: no suggestion after an offer or another suggestion).

#### `human_move_nice` — Human: nice

*Share of human moves that were nice*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\left\lvert \{k : m_k = \text{nice}\} \right\rvert}{M}, \qquad m_k = \text{nice} \iff \lvert \Delta^{s}_k \rvert \leq \epsilon \ \wedge\ \Delta^{o}_k > \epsilon
$$

The share of the human moves that were **nice**: the other side gained at no cost to the mover. A move $k$ is the change between the Human seat's consecutive offers $o^h_k$, with $\Delta^s_k = u_h(o^h_{k+1}) - u_h(o^h_k)$ and $\Delta^o_k = u_o(o^h_{k+1}) - u_o(o^h_k)$; $M$ is the number of moves whose utilities are known and $\epsilon = 10^{-6}$. The six shares of one side add up to 1. Empty when there are no moves (for the Human and the Opponent: fewer than two offers; for suggestions: no suggestion after an offer or another suggestion).

#### `human_move_fortunate` — Human: fortunate

*Share of human moves that were fortunate*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\left\lvert \{k : m_k = \text{fortunate}\} \right\rvert}{M}, \qquad m_k = \text{fortunate} \iff \Delta^{s}_k > \epsilon \ \wedge\ \Delta^{o}_k > \epsilon
$$

The share of the human moves that were **fortunate**: both sides gained. A move $k$ is the change between the Human seat's consecutive offers $o^h_k$, with $\Delta^s_k = u_h(o^h_{k+1}) - u_h(o^h_k)$ and $\Delta^o_k = u_o(o^h_{k+1}) - u_o(o^h_k)$; $M$ is the number of moves whose utilities are known and $\epsilon = 10^{-6}$. The six shares of one side add up to 1. Empty when there are no moves (for the Human and the Opponent: fewer than two offers; for suggestions: no suggestion after an offer or another suggestion).

#### `human_move_unfortunate` — Human: unfortunate

*Share of human moves that were unfortunate*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\left\lvert \{k : m_k = \text{unfortunate}\} \right\rvert}{M}, \qquad m_k = \text{unfortunate} \iff \Delta^{s}_k, \Delta^{o}_k \leq \epsilon,\ \text{not silent}
$$

The share of the human moves that were **unfortunate**: neither side gained and at least one lost (a move that helps nobody). A move $k$ is the change between the Human seat's consecutive offers $o^h_k$, with $\Delta^s_k = u_h(o^h_{k+1}) - u_h(o^h_k)$ and $\Delta^o_k = u_o(o^h_{k+1}) - u_o(o^h_k)$; $M$ is the number of moves whose utilities are known and $\epsilon = 10^{-6}$. The six shares of one side add up to 1. Empty when there are no moves (for the Human and the Opponent: fewer than two offers; for suggestions: no suggestion after an offer or another suggestion).

#### `human_move_concession` — Human: concession

*Share of human moves that were concession*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\left\lvert \{k : m_k = \text{concession}\} \right\rvert}{M}, \qquad m_k = \text{concession} \iff \Delta^{s}_k < -\epsilon \ \wedge\ \Delta^{o}_k > \epsilon
$$

The share of the human moves that were **concession**: the mover gave up utility and the other side gained. A move $k$ is the change between the Human seat's consecutive offers $o^h_k$, with $\Delta^s_k = u_h(o^h_{k+1}) - u_h(o^h_k)$ and $\Delta^o_k = u_o(o^h_{k+1}) - u_o(o^h_k)$; $M$ is the number of moves whose utilities are known and $\epsilon = 10^{-6}$. The six shares of one side add up to 1. Empty when there are no moves (for the Human and the Opponent: fewer than two offers; for suggestions: no suggestion after an offer or another suggestion).

#### `human_move_selfish` — Human: selfish

*Share of human moves that were selfish*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\left\lvert \{k : m_k = \text{selfish}\} \right\rvert}{M}, \qquad m_k = \text{selfish} \iff \Delta^{s}_k > \epsilon \ \wedge\ \Delta^{o}_k \leq \epsilon
$$

The share of the human moves that were **selfish**: the mover gained and the other side did not. A move $k$ is the change between the Human seat's consecutive offers $o^h_k$, with $\Delta^s_k = u_h(o^h_{k+1}) - u_h(o^h_k)$ and $\Delta^o_k = u_o(o^h_{k+1}) - u_o(o^h_k)$; $M$ is the number of moves whose utilities are known and $\epsilon = 10^{-6}$. The six shares of one side add up to 1. Empty when there are no moves (for the Human and the Opponent: fewer than two offers; for suggestions: no suggestion after an offer or another suggestion).

#### `opponent_move_silent` — Opponent: silent

*Share of opponent moves that were silent*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\left\lvert \{k : m_k = \text{silent}\} \right\rvert}{M}, \qquad m_k = \text{silent} \iff \lvert \Delta^{s}_k \rvert \leq \epsilon \ \wedge\ \lvert \Delta^{o}_k \rvert \leq \epsilon
$$

The share of the opponent moves that were **silent**: neither utility changed (the same offer, or one worth the same to both). A move $k$ is the change between the Opponent's consecutive offers $o^o_k$, with $\Delta^s_k = u_o(o^o_{k+1}) - u_o(o^o_k)$ and $\Delta^o_k = u_h(o^o_{k+1}) - u_h(o^o_k)$; $M$ is the number of moves whose utilities are known and $\epsilon = 10^{-6}$. The six shares of one side add up to 1. Empty when there are no moves (for the Human and the Opponent: fewer than two offers; for suggestions: no suggestion after an offer or another suggestion).

#### `opponent_move_nice` — Opponent: nice

*Share of opponent moves that were nice*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\left\lvert \{k : m_k = \text{nice}\} \right\rvert}{M}, \qquad m_k = \text{nice} \iff \lvert \Delta^{s}_k \rvert \leq \epsilon \ \wedge\ \Delta^{o}_k > \epsilon
$$

The share of the opponent moves that were **nice**: the other side gained at no cost to the mover. A move $k$ is the change between the Opponent's consecutive offers $o^o_k$, with $\Delta^s_k = u_o(o^o_{k+1}) - u_o(o^o_k)$ and $\Delta^o_k = u_h(o^o_{k+1}) - u_h(o^o_k)$; $M$ is the number of moves whose utilities are known and $\epsilon = 10^{-6}$. The six shares of one side add up to 1. Empty when there are no moves (for the Human and the Opponent: fewer than two offers; for suggestions: no suggestion after an offer or another suggestion).

#### `opponent_move_fortunate` — Opponent: fortunate

*Share of opponent moves that were fortunate*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\left\lvert \{k : m_k = \text{fortunate}\} \right\rvert}{M}, \qquad m_k = \text{fortunate} \iff \Delta^{s}_k > \epsilon \ \wedge\ \Delta^{o}_k > \epsilon
$$

The share of the opponent moves that were **fortunate**: both sides gained. A move $k$ is the change between the Opponent's consecutive offers $o^o_k$, with $\Delta^s_k = u_o(o^o_{k+1}) - u_o(o^o_k)$ and $\Delta^o_k = u_h(o^o_{k+1}) - u_h(o^o_k)$; $M$ is the number of moves whose utilities are known and $\epsilon = 10^{-6}$. The six shares of one side add up to 1. Empty when there are no moves (for the Human and the Opponent: fewer than two offers; for suggestions: no suggestion after an offer or another suggestion).

#### `opponent_move_unfortunate` — Opponent: unfortunate

*Share of opponent moves that were unfortunate*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\left\lvert \{k : m_k = \text{unfortunate}\} \right\rvert}{M}, \qquad m_k = \text{unfortunate} \iff \Delta^{s}_k, \Delta^{o}_k \leq \epsilon,\ \text{not silent}
$$

The share of the opponent moves that were **unfortunate**: neither side gained and at least one lost (a move that helps nobody). A move $k$ is the change between the Opponent's consecutive offers $o^o_k$, with $\Delta^s_k = u_o(o^o_{k+1}) - u_o(o^o_k)$ and $\Delta^o_k = u_h(o^o_{k+1}) - u_h(o^o_k)$; $M$ is the number of moves whose utilities are known and $\epsilon = 10^{-6}$. The six shares of one side add up to 1. Empty when there are no moves (for the Human and the Opponent: fewer than two offers; for suggestions: no suggestion after an offer or another suggestion).

#### `opponent_move_concession` — Opponent: concession

*Share of opponent moves that were concession*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\left\lvert \{k : m_k = \text{concession}\} \right\rvert}{M}, \qquad m_k = \text{concession} \iff \Delta^{s}_k < -\epsilon \ \wedge\ \Delta^{o}_k > \epsilon
$$

The share of the opponent moves that were **concession**: the mover gave up utility and the other side gained. A move $k$ is the change between the Opponent's consecutive offers $o^o_k$, with $\Delta^s_k = u_o(o^o_{k+1}) - u_o(o^o_k)$ and $\Delta^o_k = u_h(o^o_{k+1}) - u_h(o^o_k)$; $M$ is the number of moves whose utilities are known and $\epsilon = 10^{-6}$. The six shares of one side add up to 1. Empty when there are no moves (for the Human and the Opponent: fewer than two offers; for suggestions: no suggestion after an offer or another suggestion).

#### `opponent_move_selfish` — Opponent: selfish

*Share of opponent moves that were selfish*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\left\lvert \{k : m_k = \text{selfish}\} \right\rvert}{M}, \qquad m_k = \text{selfish} \iff \Delta^{s}_k > \epsilon \ \wedge\ \Delta^{o}_k \leq \epsilon
$$

The share of the opponent moves that were **selfish**: the mover gained and the other side did not. A move $k$ is the change between the Opponent's consecutive offers $o^o_k$, with $\Delta^s_k = u_o(o^o_{k+1}) - u_o(o^o_k)$ and $\Delta^o_k = u_h(o^o_{k+1}) - u_h(o^o_k)$; $M$ is the number of moves whose utilities are known and $\epsilon = 10^{-6}$. The six shares of one side add up to 1. Empty when there are no moves (for the Human and the Opponent: fewer than two offers; for suggestions: no suggestion after an offer or another suggestion).

#### `suggested_move_silent` — Assistant suggestion: silent

*Share of assistant suggestion moves that were silent*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\left\lvert \{k : m_k = \text{silent}\} \right\rvert}{M}, \qquad m_k = \text{silent} \iff \lvert \Delta^{s}_k \rvert \leq \epsilon \ \wedge\ \lvert \Delta^{o}_k \rvert \leq \epsilon
$$

The share of the assistant suggestion moves that were **silent**: neither utility changed (the same offer, or one worth the same to both). A move $k$ is the change between the Assistant's suggestions (offers it filled in), each compared with the Human seat's latest offer before it (or, before any offer, with the previous suggestion), with $\Delta^s_k$ the change of $u_h$ and $\Delta^o_k$ the change of $u_o$; $M$ is the number of moves whose utilities are known and $\epsilon = 10^{-6}$. The six shares of one side add up to 1. Empty when there are no moves (for the Human and the Opponent: fewer than two offers; for suggestions: no suggestion after an offer or another suggestion).

#### `suggested_move_nice` — Assistant suggestion: nice

*Share of assistant suggestion moves that were nice*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\left\lvert \{k : m_k = \text{nice}\} \right\rvert}{M}, \qquad m_k = \text{nice} \iff \lvert \Delta^{s}_k \rvert \leq \epsilon \ \wedge\ \Delta^{o}_k > \epsilon
$$

The share of the assistant suggestion moves that were **nice**: the other side gained at no cost to the mover. A move $k$ is the change between the Assistant's suggestions (offers it filled in), each compared with the Human seat's latest offer before it (or, before any offer, with the previous suggestion), with $\Delta^s_k$ the change of $u_h$ and $\Delta^o_k$ the change of $u_o$; $M$ is the number of moves whose utilities are known and $\epsilon = 10^{-6}$. The six shares of one side add up to 1. Empty when there are no moves (for the Human and the Opponent: fewer than two offers; for suggestions: no suggestion after an offer or another suggestion).

#### `suggested_move_fortunate` — Assistant suggestion: fortunate

*Share of assistant suggestion moves that were fortunate*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\left\lvert \{k : m_k = \text{fortunate}\} \right\rvert}{M}, \qquad m_k = \text{fortunate} \iff \Delta^{s}_k > \epsilon \ \wedge\ \Delta^{o}_k > \epsilon
$$

The share of the assistant suggestion moves that were **fortunate**: both sides gained. A move $k$ is the change between the Assistant's suggestions (offers it filled in), each compared with the Human seat's latest offer before it (or, before any offer, with the previous suggestion), with $\Delta^s_k$ the change of $u_h$ and $\Delta^o_k$ the change of $u_o$; $M$ is the number of moves whose utilities are known and $\epsilon = 10^{-6}$. The six shares of one side add up to 1. Empty when there are no moves (for the Human and the Opponent: fewer than two offers; for suggestions: no suggestion after an offer or another suggestion).

#### `suggested_move_unfortunate` — Assistant suggestion: unfortunate

*Share of assistant suggestion moves that were unfortunate*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\left\lvert \{k : m_k = \text{unfortunate}\} \right\rvert}{M}, \qquad m_k = \text{unfortunate} \iff \Delta^{s}_k, \Delta^{o}_k \leq \epsilon,\ \text{not silent}
$$

The share of the assistant suggestion moves that were **unfortunate**: neither side gained and at least one lost (a move that helps nobody). A move $k$ is the change between the Assistant's suggestions (offers it filled in), each compared with the Human seat's latest offer before it (or, before any offer, with the previous suggestion), with $\Delta^s_k$ the change of $u_h$ and $\Delta^o_k$ the change of $u_o$; $M$ is the number of moves whose utilities are known and $\epsilon = 10^{-6}$. The six shares of one side add up to 1. Empty when there are no moves (for the Human and the Opponent: fewer than two offers; for suggestions: no suggestion after an offer or another suggestion).

#### `suggested_move_concession` — Assistant suggestion: concession

*Share of assistant suggestion moves that were concession*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\left\lvert \{k : m_k = \text{concession}\} \right\rvert}{M}, \qquad m_k = \text{concession} \iff \Delta^{s}_k < -\epsilon \ \wedge\ \Delta^{o}_k > \epsilon
$$

The share of the assistant suggestion moves that were **concession**: the mover gave up utility and the other side gained. A move $k$ is the change between the Assistant's suggestions (offers it filled in), each compared with the Human seat's latest offer before it (or, before any offer, with the previous suggestion), with $\Delta^s_k$ the change of $u_h$ and $\Delta^o_k$ the change of $u_o$; $M$ is the number of moves whose utilities are known and $\epsilon = 10^{-6}$. The six shares of one side add up to 1. Empty when there are no moves (for the Human and the Opponent: fewer than two offers; for suggestions: no suggestion after an offer or another suggestion).

#### `suggested_move_selfish` — Assistant suggestion: selfish

*Share of assistant suggestion moves that were selfish*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\left\lvert \{k : m_k = \text{selfish}\} \right\rvert}{M}, \qquad m_k = \text{selfish} \iff \Delta^{s}_k > \epsilon \ \wedge\ \Delta^{o}_k \leq \epsilon
$$

The share of the assistant suggestion moves that were **selfish**: the mover gained and the other side did not. A move $k$ is the change between the Assistant's suggestions (offers it filled in), each compared with the Human seat's latest offer before it (or, before any offer, with the previous suggestion), with $\Delta^s_k$ the change of $u_h$ and $\Delta^o_k$ the change of $u_o$; $M$ is the number of moves whose utilities are known and $\epsilon = 10^{-6}$. The six shares of one side add up to 1. Empty when there are no moves (for the Human and the Opponent: fewer than two offers; for suggestions: no suggestion after an offer or another suggestion).

#### `human_concession` — Human concession

*Utility the human gave up from the first to the last offer*

**Range:** utility difference · **Direction:** no better direction

$$
u_h(o^h_1) - u_h(o^h_K)
$$

How much the Human seat's own utility dropped from its first offer to its last ($K$ offers with a
known utility, at least 2). Positive means the Human conceded, negative that they hardened. Example:
first offer worth $1.0$, last worth $0.62$ gives $0.38$. Neither higher nor lower is better in itself.

#### `human_offer_pareto_distance` — Human offers' Pareto distance

*Mean distance of the human's offers from the Pareto frontier*

**Range:** ≥ 0 · **Direction:** lower is better

$$
\frac{1}{K} \sum_{k=1}^{K} D_{\mathcal{P}}(o^h_k)
$$

How efficient the Human's offers were on average: 0 when every offer was Pareto optimal. Lower is
better. Offers far from the frontier hurt both sides. Not computed without a utility table.

#### `tom_reflect_index` — Theory of mind: reflect index

*Share of the human's moves up to the first one that raised the opponent's utility (lower = sooner)*

**Range:** (0, 1] · **Direction:** lower is better

$$
R = \frac{k^\star}{M}, \qquad k^\star = \min\{k : \Delta^{o}_k > \epsilon\} \quad (R = 1 \text{ if there is none})
$$

How soon the Human's offers started to reflect the Opponent's interests: $k^\star$ is the (1-based)
index of the Human's first nice, fortunate or concession move (the moves that raise the Opponent's
utility) among their $M$ moves. Lower means sooner. Example: moves selfish, silent, concession,
nice give $R = 3/4$.

Caveat: a Human who never raised the Opponent's utility gets 1, the same as one who did so only on
the last move. Empty without moves.

#### `tom_other_trend` — Theory of mind: other's-utility trend

*Correlation of the opponent's utility of the human's offers with their order (higher = the human moved toward the other's interests)*

**Range:** [−1, 1] · **Direction:** higher is better

$$
\rho\big(k,\ u_o(o^h_k)\big) = \frac{\operatorname{cov}(k, u_o(o^h_k))}{\sigma_k \, \sigma_{u_o}}
$$

The Pearson correlation between the position $k$ of each Human offer and the Opponent's utility of it:
near 1 when the Human's offers steadily moved toward what the Opponent wants, near −1 when they moved
away. It uses the order of the offers, not their times. Empty with fewer than 3 offers or when the
Opponent's utility never changed.

### `timing` — Timing

*hard*

Interaction time per decision and overall.

$$
\delta_a = t_a - \max\{s \in S : s \leq t_a\}
$$

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

#### `decision_time_mean` — Decision time (s)

*Mean time from the start of the human's turn to their action*

**Range:** seconds · **Direction:** no better direction

$$
\frac{1}{\lvert A_h \rvert} \sum_{a \in A_h} \delta_a
$$

The mean decision time over the Human's own actions $A_h$. Sensitive to a single long pause; see the
median.

#### `decision_time_median` — Decision time, median (s)

*Median time per decision*

**Range:** seconds · **Direction:** no better direction

$$
\operatorname{median}_{a \in A_h} \delta_a
$$

The median decision time: robust to a few long pauses. `click_through` uses it.

#### `decision_time_min` — Fastest decision (s)

*Shortest time per decision*

**Range:** seconds · **Direction:** no better direction

$$
\min_{a \in A_h} \delta_a
$$

The shortest decision time. Near 0 means at least one action was taken without reading the
Opponent's offer.

#### `time_to_first_action` — Time to first action (s)

*From the start of the negotiation to the first human action*

**Range:** seconds · **Direction:** no better direction

$$
t_{a_1} - t_{\text{start}}
$$

Seconds from the start of the negotiation to the Human's first own action.

#### `load_to_start_seconds` — Reading time (s)

*From loading the scenario to starting the negotiation*

**Range:** seconds · **Direction:** no better direction

$$
t_{\text{start}}
$$

Seconds from loading the scenario (the start of the recording, time 0) to starting the negotiation:
the time spent reading the instructions and the preferences.

#### `questionnaire_seconds` — Questionnaire time (s)

*Time spent on the questionnaire*

**Range:** seconds · **Direction:** no better direction

$$
t_{\text{submitted}} - t_{\text{shown}}
$$

Seconds from the moment the questionnaire appeared on screen to its submission. Very short times
suggest answers given without reading. Empty without a questionnaire or without screen states.

### `activity` — Activity (mouse, keyboard, attention)

*hard*

Low-level interaction: clicks, keys, pointer travel, idle time and attention.

$$
\text{idle} = \sum_{i : g_i > 5\,\text{s}} g_i, \qquad g_i = \tau_{i+1} - \tau_i, \quad (\tau_i) = (t_0, \text{inputs in } [t_0, t_1], t_1)
$$

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

#### `n_clicks` — Clicks

*Mouse / touch clicks*

**Range:** count · **Direction:** no better direction

$$
\lvert \{e : \text{type}(e) = \text{click}\} \rvert
$$

Clicks and taps over the whole recording.

#### `n_keys` — Key presses

*Keys pressed*

**Range:** count · **Direction:** no better direction

$$
\lvert \{e : \text{type}(e) = \text{key}\} \rvert
$$

Key presses over the whole recording (typing chat messages and offers).

#### `mouse_distance` — Mouse distance (px)

*Distance travelled by the pointer*

**Range:** pixels · **Direction:** no better direction

$$
\sum_{i \geq 2} \left\lVert x_i - x_{i-1} \right\rVert_2
$$

The distance the pointer travelled, summed between consecutive pointer positions $x_i$ (moves, presses,
releases and clicks) over the whole recording, rounded to 0.1 px.

#### `n_scrolls` — Scrolls

*Scroll events*

**Range:** count · **Direction:** no better direction

$$
\lvert \{e : \text{type}(e) = \text{scroll}\} \rvert
$$

Scroll events over the whole recording.

#### `idle_fraction` — Idle fraction

*Share of the negotiation without any input for more than 5 s*

**Range:** [0, 1] · **Direction:** no better direction

$$
\min\left(1, \frac{\text{idle}}{t_1 - t_0}\right)
$$

The share of the negotiation spent in pauses longer than 5 s without any input. Each such pause counts
in full (not only the part after 5 s). High values mean the participant was reading, thinking or away;
compare with `hidden_seconds`.

#### `hidden_seconds` — Away (s)

*Time the page was hidden (another tab or window)*

**Range:** seconds · **Direction:** no better direction

$$
\sum_j \left(t^{\text{visible}}_j - t^{\text{hidden}}_j\right)
$$

Seconds the page was hidden (the participant switched to another tab or minimised the window): each
"hidden" event until the next "visible" one; a page still hidden at the end counts until $t_1$.

#### `n_blur` — Focus lost

*Times the window lost focus*

**Range:** count · **Direction:** no better direction

$$
\lvert \{e : \text{type}(e) = \text{blur}\} \rvert
$$

How often the window lost the keyboard focus (another window was activated).

#### `has_telemetry` — Has telemetry

*1 if browser telemetry was recorded*

**Range:** 0 or 1 · **Direction:** no better direction

$$
\mathbb{1}[\text{telemetry}]
$$

1 when the browser sent telemetry. Recordings made without a browser (e.g. scripted sessions) have 0,
and the other activity columns are empty.

### `system_use` — Use of the assistant and tools

*hard*

Actual system use: messages, suggestions and how they were used, exploration and tools.

$$
\text{adoption} = \frac{\lvert \{a \in A^{\text{offer}}_h : a\ \text{after a suggestion},\ a = \text{suggestion}\} \rvert}{\lvert \{a \in A^{\text{offer}}_h : a\ \text{after a suggestion}\} \rvert}
$$

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

#### `n_user_messages` — Messages to assistant

*Chat messages the human sent to the assistant*

**Range:** count · **Direction:** no better direction

$$
\lvert \{c \in \text{chat} : \text{by Human}\} \rvert
$$

Chat messages the Human wrote to the Assistant.

#### `n_assistant_messages` — Assistant messages

*Messages the assistant posted*

**Range:** count · **Direction:** no better direction

$$
\lvert \{c \in \text{chat} : \text{not by Human}\} \rvert
$$

Chat messages posted by the Assistant (every chat message not written by the Human).

#### `n_suggestions` — Suggestions

*Drafts (offers or messages) the assistant filled in for the human*

**Range:** count · **Direction:** no better direction

$$
\lvert \{d \in \text{drafts} : \text{by Assistant}\} \rvert
$$

Drafts the Assistant wrote into the Human's editor: filled-in offers and drafted messages to the
Opponent (both count).

#### `suggestion_adoption` — Suggestion adoption

*Share of human offers made after a suggestion that were exactly the suggestion*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{n_{\text{adopted}}}{n_{\text{adopted}} + n_{\text{ignored}}}
$$

Of the Human's offers made while a suggestion was pending, the share that were exactly the suggestion
(compared issue by issue as text). 1 means every suggestion that was followed by an offer was taken.
Offers made with no suggestion pending do not count. Empty when no offer followed a suggestion.

#### `suggestions_ignored` — Suggestions ignored

*Suggestions followed by a different offer*

**Range:** count · **Direction:** no better direction

$$
n_{\text{ignored}}
$$

Human offers made while a suggestion was pending that differed from it.

#### `drafts_explored` — Offers explored

*Counter-offers the human tried in the editor before acting*

**Range:** count · **Direction:** no better direction

$$
\lvert \{d \in \text{drafts} : \text{by Human, with offer values}\} \rvert
$$

How many offers the Human tried in the offer editor (each change of the edited offer). A sign of an
invested participant who weighs alternatives.

#### `drafts_per_action` — Offers explored per action

*Mean explorations before each human action*

**Range:** ≥ 0 · **Direction:** no better direction

$$
\frac{1}{\lvert A_h \rvert} \sum_{a \in A_h} \left\lvert \{d : \text{Human draft between the previous Human action and } a\} \right\rvert
$$

The mean number of explored offers before each of the Human's own seat actions.

#### `n_tool_interactions` — Tool interactions

*Inputs and actions in tools*

**Range:** count · **Direction:** no better direction

$$
\lvert \{e : \text{tool interaction}\} \rvert
$$

Inputs and actions the Human made in the tools (sliders, buttons, forms, …).

#### `n_tools_used` — Tools used

*Distinct tools the human used*

**Range:** count · **Direction:** no better direction

$$
\lvert \{\text{component}(e) : e\ \text{tool interaction}\} \rvert
$$

How many different tool components the Human interacted with.

#### `n_tab_changes` — Tab changes

*Tool tabs opened*

**Range:** count · **Direction:** no better direction

$$
\lvert \{e : \text{tab changed}\} \rvert
$$

How often the Human switched between tool tabs.

#### `actions_by_human` — Actions by human

*Share of the seat's actions taken by the human*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\lvert A^{\text{seat}}_{\text{Human}} \rvert}{\lvert A^{\text{seat}} \rvert}
$$

The share of the Human seat's actions (offers, acceptances, ending, messages) the Human took
themselves. The three `actions_by_*` shares add up to 1. Empty without seat actions.

#### `actions_by_agent` — Actions by assistant

*Share taken by the assistant*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\lvert A^{\text{seat}}_{\text{Assistant}} \rvert}{\lvert A^{\text{seat}} \rvert}
$$

The share of the Human seat's actions the Assistant took for the Human.

#### `actions_by_autopilot` — Actions by autopilot

*Share taken by the autopilot*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\lvert A^{\text{seat}}_{\text{autopilot}} \rvert}{\lvert A^{\text{seat}} \rvert}
$$

The share of the Human seat's actions the autopilot took.

### `engagement_flags` — Engagement flags

*hard*

Flags for sessions to inspect or remove: never acted, clicking through,
blindly following or always ignoring the assistant. Options:
``click_through_seconds`` (default 3).

$$
\text{click\_through} = \mathbb{1}\left[\lvert A_h \rvert > 0 \wedge \operatorname{median} \delta < \theta \wedge \text{drafts\_explored} = 0\right]
$$

Flags for sessions to inspect or remove before an analysis: a participant who never acted, clicked
through as fast as possible, blindly followed the Assistant or never took a suggestion. They reuse the
`timing` and `system_use` values. The option `click_through_seconds` sets the threshold $\theta$
(default 3 s).

**Options:**

* `click_through_seconds` — Median decision time (s) under which a session counts as click-through (default 3).

#### `never_acted` — Never acted

*1 if the human never took an action themselves (filter out)*

**Range:** 0 or 1 · **Direction:** lower is better

$$
\mathbb{1}\left[\lvert A_h \rvert = 0\right]
$$

1 when the Human took no action of any kind themselves: everything was done by the Assistant, the
autopilot or the Opponent. Usually filtered out.

#### `click_through` — Click-through

*1 if the human acted very fast without exploring offers (not invested)*

**Range:** 0 or 1 · **Direction:** lower is better

$$
\mathbb{1}\left[\lvert A_h \rvert > 0 \ \wedge\ \operatorname{median}_{a} \delta_a < \theta \ \wedge\ \text{drafts\_explored} = 0\right]
$$

1 when the Human acted, their median decision time was under $\theta$ seconds (default 3) and they
never explored an offer in the editor: a participant clicking through without engaging.

#### `always_follows` — Always follows assistant

*1 if every human offer made after a suggestion was the suggestion (≥ 3 offers)*

**Range:** 0 or 1 · **Direction:** lower is better

$$
\mathbb{1}\left[\text{adoption} \geq 0.999 \ \wedge\ \lvert A^{\text{offer}}_h \rvert \geq 3\right]
$$

1 when the Human made at least 3 offers and every offer they made after a suggestion was the
suggestion: possibly blind trust in the Assistant. Offers made with no suggestion pending are not
checked.

#### `never_follows` — Never follows assistant

*1 if no suggestion was ever taken (≥ 3 suggestions)*

**Range:** 0 or 1 · **Direction:** no better direction

$$
\mathbb{1}\left[n_{\text{suggestions}} \geq 3 \ \wedge\ \text{adoption} \in \{0, \varnothing\}\right]
$$

1 when the Assistant made at least 3 suggestions (offers or messages) and the Human never sent one of
them (including when no offer followed a suggestion at all).

### `assistant_interaction` — Assistant interaction quality

*hard*

Responsiveness, unanswered messages, proactivity, monologues and function-call success.

$$
\bar r = \frac{1}{\lvert Q \rvert} \sum_{(q, a) \in Q} (t_a - t_q)
$$

The Assistant in conversation with the Human: how fast it answered, whether it left messages unanswered,
how often it spoke up on its own, its longest monologue and how often its function calls worked.

The chat is read in time order. A Human message $q$ waits for an answer; the next Assistant message
$a$ answers it ($Q$ is the set of such pairs). A Human message followed by another Human message
before any answer is unanswered (the newer one then waits). $q_1, \dots, q_n$ are the Human's messages and
$a$ the Assistant's.

**Example.** The Human writes at $10$ s and $12$ s, the Assistant answers at $15$ s and writes again at
$60$ s: the message at 10 s is unanswered, the response time is $15 - 12 = 3$ s, and the message at
60 s is proactive (48 s after the Human's last message). The longest streak is 2.

#### `assistant_response_seconds` — Response time (s)

*Mean time from a human message to the assistant's next message*

**Range:** seconds · **Direction:** lower is better

$$
\frac{1}{\lvert Q \rvert} \sum_{(q, a) \in Q} (t_a - t_q)
$$

The mean time from a waiting Human message to the Assistant's next message. Lower is better. Empty
when the Assistant never answered.

#### `unanswered_messages` — Unanswered messages

*Human messages the assistant never answered*

**Range:** count · **Direction:** lower is better

$$
\left\lvert \{ i : \nexists\, a \text{ with } t_{q_i} < t_a < t_{q_{i+1}} \} \right\rvert, \qquad t_{q_{n+1}} = \infty
$$

Human messages the Assistant did not answer before the Human wrote again or the session ended.

#### `unsolicited_messages` — Proactive messages

*Assistant messages not answering the human (> 30 s after their last message)*

**Range:** count · **Direction:** no better direction

$$
\lvert \{a : \text{no Human message waiting} \ \wedge\ (\text{no Human message yet} \vee t_a - t_{q_{\text{last}}} > 30\,\text{s})\} \rvert
$$

Assistant messages that answered nothing: written before the Human's first message or more than 30 s
after their last one. Some proactivity is useful (warnings, explanations); a lot can be distracting.

#### `max_assistant_streak` — Longest monologue

*Most assistant messages in a row without the human writing*

**Range:** count · **Direction:** no better direction

$$
\max \{\ell : \ell\ \text{consecutive Assistant messages}\}
$$

The longest run of Assistant messages without a Human message in between.

#### `fn_calls` — Function calls

*Functions the assistant called*

**Range:** count · **Direction:** no better direction

$$
\lvert F \rvert
$$

Functions (tools) the Assistant called: filling in offers, reading the state, using tools, …

#### `fn_success_rate` — Function success

*Share of the assistant's function calls that succeeded*

**Range:** [0, 1] · **Direction:** higher is better

$$
\frac{\lvert \{f \in F : \text{result}(f)\ \text{is an object with}\ \text{ok} \neq \text{false}\} \rvert}{\lvert F \rvert}
$$

The share of function calls that worked. A call counts as failed when its result says `ok: false`
or when the result is not an object (e.g. an error text). Empty without calls; the calls per function
are in the details.

### `simulation` — Simulated participant

*hard*

Goal, validity, suggestion uptake and policy conformance of a simulated participant.

$$
\text{goal\_met} = [\,\omega \neq \varnothing \wedge u_h(\omega) \ge r_p\,]
$$

For sessions played by a simulated participant (`mode: simulated`, see the simulation guide): whether
the persona reached its goal, whether the trial is valid, how often it saw and took the Assistant's
suggestion, and whether a scripted persona kept to its own rules. $\omega$ is the agreement and
$r_p$ the persona's reservation value (its private one, or the scenario's).

A trial is **invalid** when it hit the time-out or the turn cap, the simulator's language model failed
or the opponent failed; leave invalid trials out of pass^k (`hani2 simulate` does), because they say
nothing about the Assistant. **Violations** are the turns where a scripted persona broke its own
policy (a follower ignoring a suggestion, a stubborn persona going below its floor, …), checked
without a language model; they should be 0, and are not computed for language-model personas.

**Example.** A stubborn persona with reservation value $0.4$ reaches a deal worth $0.7$ after 6 turns,
seeing 4 suggestions and taking 1: `sim_goal_met` $= 1$, `sim_take_rate` $= 1/4$.

Not computed for human sessions.

#### `sim_goal_met` — Goal met

*The simulated participant got a deal worth at least its reservation value*

**Range:** {0, 1} · **Direction:** higher is better

$$
[\,\omega \neq \varnothing \wedge u_h(\omega) \ge r_p\,]
$$

1 when the negotiation ended in a deal worth at least the persona's reservation value to it, else 0.
The success criterion of pass^k for simulated runs.

#### `sim_valid` — Valid trial

*The trial ended normally (no time-out, turn cap or simulator failure)*

**Range:** {0, 1} · **Direction:** higher is better

$$
[\,\text{no time-out, turn cap or failure}\,]
$$

0 when the trial says nothing about the Assistant: it timed out, hit the turn cap, or the simulator's
model or the opponent failed.

#### `sim_turns` — Persona turns

*Moves the persona made*

**Range:** count · **Direction:** no better direction

$$
\lvert T \rvert
$$

The number of moves (offers, acceptances, endings) the persona made.

#### `sim_take_rate` — Suggestions taken

*Share of the turns with a suggestion where the persona took it*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\lvert \{t \in T : \text{took}(t)\} \rvert}{\lvert \{t \in T : \text{suggestion}(t)\} \rvert}
$$

Of the persona's turns on which the Assistant had suggested something (filled an offer, asked to confirm
accept / end, or spotlighted a button), the share where the persona did what was suggested.
Empty when the Assistant never suggested anything.

#### `sim_violations` — Persona violations

*Turns where a scripted persona broke its own policy*

**Range:** count · **Direction:** lower is better

$$
\lvert \{t \in T : \text{policy}(t)\ \text{broken}\} \rvert
$$

Turns where a scripted persona did not behave as specified, found by deterministic checks. Should be 0;
anything else is a simulator bug. Empty for language-model personas.

#### `sim_stopped` — Persona stopped

*The language-model persona ended its participation with the stop token*

**Range:** {0, 1} · **Direction:** no better direction

$$
[\,\texttt{\#\#\#STOP\#\#\#}\,]
$$

1 when a language-model persona wrote the stop token (its goal met or it gave up) and so walked away.

### `dual_control` — Dual control

*hard*

Whether the agreement kept the private briefings' constraints.

$$
\mathcal{C} = \bigcup_{b \in B} \mathcal{C}_b, \qquad \omega^{*} \models c \iff \omega^{*}_{i_c} \in V_c
$$

How a negotiation went when the Human and the Assistant knew different things (see *Who knows what*
in the guide). $B$ are the round's briefings and $\mathcal{C}_b$ the constraints of briefing $b$; a
constraint $c$ names an issue $i_c$ and the values $V_c$ it allows (a minimum, a maximum, allowed or
forbidden options). The recording keeps the round's information split: the private briefings with their
constraints, which issues and actions only the Human could decide, and who held which past
negotiations. Empty for negotiations without a split.

**Caveat.** A constraint is checked on the raw option values of the agreement, not on the labels
shown to the participant.

#### `information_split` — Information split

*Whether the Human and the Assistant knew different things*

**Range:** {0, 1} · **Direction:** no better direction

$$
\mathbb{1}[\text{split}]
$$

1 when the round split the information (past negotiations, preferences, market research, briefings
or human-only decisions), else 0.

#### `constraints_met` — Constraints met

*The agreement keeps every constraint of the private briefings*

**Range:** {0, 1} · **Direction:** higher is better

$$
\prod_{c \in \mathcal{C}} \mathbb{1}[\omega^{*} \models c]
$$

1 when the agreement $\omega^{*}$ keeps every constraint $c$ of the round's briefings (a limit that
is not in the utility function, such as "rent at most 3200"), 0 when it breaks at least one. Empty
without an agreement or without constraints. When the constraint was given to the Human only, it
shows whether the Assistant's help respected what it had to learn from the Human.

#### `n_constraint_violations` — Constraints broken

*How many briefing constraints the agreement breaks*

**Range:** count · **Direction:** lower is better

$$
\left\lvert \{c \in \mathcal{C} : \omega^{*} \not\models c\} \right\rvert
$$

The number of constraints the agreement breaks (empty without an agreement or without constraints).

### `factors` — Difficulty factors

*hard · not run by default*

Difficulty factors of a compositional scenario and target attainment.

$$
\text{levels}(\sigma), \qquad \frac{u_h(\omega) - r_h}{u_h(\omega^\ast) - r_h}
$$

For scenarios composed from difficulty factors (`hani2 compose`): the level of every factor and how
close the result came to the scenario's **target** deal $\omega^\ast$ (the Nash bargaining solution over the
zone of possible agreement). Scenario factors (issues, opposition, ZOPA, constraint) are read from the
scenario; episode factors (deception, time pressure) from what was actually played, so a study that
overrides the opponent or the step limit is reported as it ran. Group by a `factor_*` column (or use
`hani2 compose report`) to see which factor makes an Assistant fail.

Recordings of other scenarios give empty columns.

#### `factor_issues` — Issues

*Number-of-issues level (2, 4 or 6)*

**Range:** level name · **Direction:** no better direction

$$
\text{level of issues}
$$

The number of negotiated issues of the scenario.

Empty for a scenario that was not composed from factors.

#### `factor_opposition` — Opposition level

*Opposition level (low, medium, high)*

**Range:** level name · **Direction:** no better direction

$$
\text{level of opposition}
$$

How opposed the two preference profiles are: the opposition level (the distance from the best outcome to the ideal point $(1, 1)$) falls in the band of the level.

Empty for a scenario that was not composed from factors.

#### `factor_zopa` — ZOPA level

*ZOPA-size level (wide, narrow)*

**Range:** level name · **Direction:** no better direction

$$
\text{level of zopa}
$$

The share of outcomes that both sides prefer to no deal, set through the reservation values.

Empty for a scenario that was not composed from factors.

#### `factor_constraint` — Constraint level

*Hidden-constraint level (none, hidden)*

**Range:** level name · **Direction:** no better direction

$$
\text{level of constraint}
$$

**hidden**: the participant has a private hard limit that the opponent does not know (the opponent's favourite option on its most important issue is worth less than no deal).

Empty for a scenario that was not composed from factors.

#### `factor_deception` — Deception level

*Opponent honesty (honest, deceptive)*

**Range:** level name · **Direction:** no better direction

$$
\text{level of deception}
$$

The opponent actually played: **honest** or **deceptive** (it lies about its priorities, its deadline and its outside option) when it is one of the factor's opponents, otherwise its name.

Empty for a scenario that was not composed from factors.

#### `factor_time_pressure` — Time-pressure level

*Time-pressure level (relaxed, tight)*

**Range:** level name · **Direction:** no better direction

$$
\text{level of time pressure}
$$

The step limit actually used: the level whose step count matches, otherwise `steps=<n>`.

Empty for a scenario that was not composed from factors.

#### `target_attainment` — Target attainment

*Gain over the reservation value relative to the target's*

**Range:** (-inf, inf); 1 = the target · **Direction:** higher is better

$$
\frac{u_h(\omega) - r_h}{u_h(\omega^\ast) - r_h}
$$

The human team's gain over its reservation value $r_h$, as a share of the gain the **target** deal
$\omega^\ast$ would give. The target is the Nash bargaining solution over the zone of possible
agreement (respecting the participant's hidden constraint), stored in the scenario when it was composed.

1 means the team got as much as the target, above 1 more (at the opponent's expense), 0 the
reservation value (no deal), below 0 a deal worse than no deal (for example one that breaks the hidden
constraint). Because it is normalised by the target, it compares fairly across scenarios of different
difficulty, unlike the raw utility.

**Example.** $r_h = 0.2$, the target gives $0.6$ and the deal $0.5$: $(0.5 - 0.2) / (0.6 - 0.2) = 0.75$.

#### `reached_target` — Reached target

*1 if the deal is at least as good as the target for the human*

**Range:** {0, 1} · **Direction:** higher is better

$$
\mathbb{1}\left[u_h(\omega) \ge u_h(\omega^\ast)\right]
$$

1 when the human team's utility is at least the target's (see `target_attainment`), 0 otherwise
(including no deal).

#### `constraint_violated` — Constraint violated

*1 if the deal breaks the hidden constraint*

**Range:** {0, 1} · **Direction:** lower is better

$$
\mathbb{1}\left[\omega_j = v^\dagger\right]
$$

For a scenario with a hidden constraint ($v^\dagger$ is the forbidden option of issue $j$): 1 when the
agreement uses the forbidden option, 0 otherwise (no deal counts as 0). Empty for scenarios without a
hidden constraint.

### `rule_checks` — Rule checks

*hard*

Mistakes the utility table proves (accepting or suggesting a deal worth
less than no deal) and failed sessions.

$$
\text{irrational\_accept} = \mathbb{1}\big[\omega^* \neq \varnothing \wedge h \text{ accepted} \wedge u_h(\omega^*) < r_h\big]
$$

Mistakes that need no judgement because the utility table proves them: accepting a deal worth less
than walking away, the Assistant suggesting such an offer, and sessions that failed because of the
Opponent agent or of the system. A scenario's `evaluation` block can require some of them to be 0
(`rules`), and the combined scores use them.

**Example.** The reservation value of the Human is $r_h = 0.2$. The Assistant suggests offers worth
0.6, 0.15 and 0.3 to the Human; the Human then accepts the Opponent's offer worth 0.18. Then
`irrational_suggestions` $= 1$ and `irrational_accept` $= 1$.

Empty without a utility table (e.g. continuous issues), except the two failure flags.

#### `irrational_accept` — Accepted below reservation

*1 if the Human seat accepted a deal worth less than no deal*

**Range:** 0 or 1 · **Direction:** lower is better

$$
\mathbb{1}\big[\omega^* \neq \varnothing \wedge h \text{ accepted} \wedge u_h(\omega^*) < r_h\big]
$$

1 when the negotiation ended because the Human seat (the Human, the Assistant or the autopilot acting
for them) accepted an offer whose utility for the Human is below their reservation value $r_h$: the
Human would have done better without a deal. 0 otherwise, also when there was no deal.

#### `opponent_irrational_accept` — Opponent accepted below reservation

*1 if the Opponent accepted a deal worth less to it than no deal*

**Range:** 0 or 1 · **Direction:** lower is better

$$
\mathbb{1}\big[\omega^* \neq \varnothing \wedge o \text{ accepted} \wedge u_o(\omega^*) < r_o\big]
$$

The same for the Opponent: it accepted an offer worth less to it than its reservation value $r_o$. A
well-built negotiation agent never does this.

#### `irrational_suggestions` — Suggestions below reservation

*Assistant suggestions worth less to the Human than no deal*

**Range:** count · **Direction:** lower is better

$$
\lvert \{\sigma \in \Sigma : u_h(\sigma) < r_h\} \rvert
$$

How many of the Assistant's suggestions $\Sigma$ (offers it filled into the Human's seat) are worth less
to the Human than their reservation value. Empty when there was no Assistant activity.

#### `opponent_failed` — Opponent failed

*1 if the session ended because the Opponent agent raised an error*

**Range:** 0 or 1 · **Direction:** lower is better

$$
\mathbb{1}\left[\text{status} = \text{agent\_failed}\right]
$$

1 when the negotiation ended because the Opponent agent failed. In the Human-Agent Negotiation track
this counts against the Opponent; in the Hybrid Intelligence track the session is left out of the
leaderboard (it is not the Assistant's fault).

#### `infrastructure_failure` — System failure

*1 if the negotiation mechanism failed*

**Range:** 0 or 1 · **Direction:** lower is better

$$
\mathbb{1}\left[\text{status} = \text{erred}\right]
$$

1 when the negotiation ended because the mechanism (the system) failed. Such sessions are left out of
every leaderboard.

### `condition` — Condition (ablations)

*hard*

The experimental condition of the negotiation (for ablations): team, human alone, the Assistant on
autopilot, with or without the opponent's utility function.

$$
\text{share}_{\text{auto}} = \frac{\lvert A^{\text{seat}}_{\text{autopilot}} \rvert}{\lvert A^{\text{seat}} \rvert}
$$

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

#### `condition` — Condition

*team, human_alone, no_human, oracle_team, oracle_no_human, …*

**Range:** a label · **Direction:** no better direction

$$
\text{team} \mid \text{human\_alone} \mid \text{no\_human} \mid \text{oracle\_*} \mid \ldots
$$

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

#### `assistant_condition` — Assistant

*on, none, off or error (as assigned)*

**Range:** a label · **Direction:** no better direction

$$
\text{on} \mid \text{none} \mid \text{off} \mid \text{error}
$$

Whether an Assistant ran (`on`), the session was assigned the no-Assistant arm (`none`), the
Assistant was switched off in the settings (`off`) or it failed to start (`error`).

#### `oracle` — Oracle

*1 when the Assistant knew the opponent's utility function*

**Range:** 0 or 1 · **Direction:** no better direction

$$
\mathbb{1}\left[\text{opponent\_utility granted}\right]
$$

1 when the Assistant had the admin-only `opponent_utility` capability: the Opponent's preferences and
its utility of every offer were in the Assistant's view of the negotiation.

#### `opponent_info_tools` — Opponent info in tools

*1 when the Human's tools could show the opponent's utilities*

**Range:** 0 or 1 · **Direction:** no better direction

$$
\mathbb{1}\left[\text{tools show } u_o\right]
$$

1 when the Human's tools could show the Opponent's utilities (admins, or env.json
`tools.show_opponent_utility`). Such sessions are left out of the ablation report by default: the
Human (and the Assistant through the tools) had information the condition does not say.

#### `autopilot_driver` — Autopilot driver

*Who drove the seat on autopilot*

**Range:** a name · **Direction:** no better direction

$$
\text{the driver when autopilot was last switched on}
$$

The autopilot driver (`Assistant` or a negotiator's name); empty when autopilot never acted.

#### `autopilot_share` — Autopilot share

*Share of the seat's actions taken by autopilot*

**Range:** [0, 1] · **Direction:** no better direction

$$
\frac{\lvert A^{\text{seat}}_{\text{autopilot}} \rvert}{\lvert A^{\text{seat}} \rvert}
$$

The share of the Human seat's actions the autopilot took (1 for `no_human`, 0 for a Human negotiating
themselves).

## Subjective metrics

The participant's own answers to the questionnaire.

### `questionnaire` — Questionnaire

*subjective*

Scale scores (UEQ, TAM, intention to use, opponent perception, …) and
single answers from the post-negotiation questionnaire.

$$
Q_s = \frac{1}{\lvert S_s \rvert} \sum_{i \in S_s} v'_i, \qquad \hat Q_s = \frac{1}{\lvert S_s \rvert} \sum_{i \in S_s} \frac{v'_i - \ell_i}{h_i - \ell_i}
$$

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

#### `scale_satisfaction` — Satisfaction

*Satisfaction with the outcome*

**Range:** the items' range (1–7) · **Direction:** higher is better

$$
Q_{\text{satisfaction}} = \frac{1}{\lvert S \rvert} \sum_{i \in S} v'_i, \qquad v'_i = \begin{cases} \ell_i + h_i - v_i & \text{reversed item} \\ v_i & \text{otherwise} \end{cases}
$$

The mean answer to the items $S$ of the scale **satisfaction**, on the items' own range (1–7 for 7-point items; reversed items scored backwards). Higher means more of what the scale measures. Items in the bundled questionnaire: “How satisfied are you with the outcome of this negotiation?” (1–7). Empty when the participant answered none of its items (e.g. questions about the Assistant when there was none). See `scale_satisfaction_norm` for the 0–1 version.

#### `scale_satisfaction_norm` — Satisfaction (0–1)

*Satisfaction with the outcome, rescaled to 0–1*

**Range:** [0, 1] · **Direction:** higher is better

$$
\hat Q_{\text{satisfaction}} = \frac{1}{\lvert S \rvert} \sum_{i \in S} \frac{v'_i - \ell_i}{h_i - \ell_i}
$$

The same scale rescaled to $[0, 1]$ item by item ($0$ = the lowest answer, $1$ = the highest), so scales and items with different ranges can be compared. For a 7-point item, $(v' - 1)/6$.

#### `scale_appreciation` — Appreciation

*Enjoyment of the negotiation*

**Range:** the items' range (1–7) · **Direction:** higher is better

$$
Q_{\text{appreciation}} = \frac{1}{\lvert S \rvert} \sum_{i \in S} v'_i, \qquad v'_i = \begin{cases} \ell_i + h_i - v_i & \text{reversed item} \\ v_i & \text{otherwise} \end{cases}
$$

The mean answer to the items $S$ of the scale **appreciation**, on the items' own range (1–7 for 7-point items; reversed items scored backwards). Higher means more of what the scale measures. Items in the bundled questionnaire: “How much did you enjoy this negotiation?” (1–7). Empty when the participant answered none of its items (e.g. questions about the Assistant when there was none). See `scale_appreciation_norm` for the 0–1 version.

#### `scale_appreciation_norm` — Appreciation (0–1)

*Enjoyment of the negotiation, rescaled to 0–1*

**Range:** [0, 1] · **Direction:** higher is better

$$
\hat Q_{\text{appreciation}} = \frac{1}{\lvert S \rvert} \sum_{i \in S} \frac{v'_i - \ell_i}{h_i - \ell_i}
$$

The same scale rescaled to $[0, 1]$ item by item ($0$ = the lowest answer, $1$ = the highest), so scales and items with different ranges can be compared. For a 7-point item, $(v' - 1)/6$.

#### `scale_ueq_pragmatic` — Ueq pragmatic

*UEQ pragmatic quality of the assistant: perspicuity (understandable, easy, clear), efficiency (efficient, practical) and dependability (supportive) items*

**Range:** the items' range (1–7) · **Direction:** higher is better

$$
Q_{\text{ueq\_pragmatic}} = \frac{1}{\lvert S \rvert} \sum_{i \in S} v'_i, \qquad v'_i = \begin{cases} \ell_i + h_i - v_i & \text{reversed item} \\ v_i & \text{otherwise} \end{cases}
$$

The mean answer to the items $S$ of the scale **ueq_pragmatic**, on the items' own range (1–7 for 7-point items; reversed items scored backwards). Higher means more of what the scale measures. Items in the bundled questionnaire: Six 7-point semantic differentials of the User Experience Questionnaire (UEQ, Laugwitz, Held and Schrepp, 2008) about the Assistant: not understandable–understandable, obstructive–supportive, complicated–easy, inefficient–efficient, impractical–practical and clear–confusing (reversed). Empty when the participant answered none of its items (e.g. questions about the Assistant when there was none). See `scale_ueq_pragmatic_norm` for the 0–1 version.

#### `scale_ueq_pragmatic_norm` — Ueq pragmatic (0–1)

*UEQ pragmatic quality of the assistant: perspicuity (understandable, easy, clear), efficiency (efficient, practical) and dependability (supportive) items, rescaled to 0–1*

**Range:** [0, 1] · **Direction:** higher is better

$$
\hat Q_{\text{ueq\_pragmatic}} = \frac{1}{\lvert S \rvert} \sum_{i \in S} \frac{v'_i - \ell_i}{h_i - \ell_i}
$$

The same scale rescaled to $[0, 1]$ item by item ($0$ = the lowest answer, $1$ = the highest), so scales and items with different ranges can be compared. For a 7-point item, $(v' - 1)/6$.

#### `scale_ueq_hedonic` — Ueq hedonic

*UEQ items on the assistant's value and overall impression (valuable — a stimulation item; good — an attractiveness item)*

**Range:** the items' range (1–7) · **Direction:** higher is better

$$
Q_{\text{ueq\_hedonic}} = \frac{1}{\lvert S \rvert} \sum_{i \in S} v'_i, \qquad v'_i = \begin{cases} \ell_i + h_i - v_i & \text{reversed item} \\ v_i & \text{otherwise} \end{cases}
$$

The mean answer to the items $S$ of the scale **ueq_hedonic**, on the items' own range (1–7 for 7-point items; reversed items scored backwards). Higher means more of what the scale measures. Items in the bundled questionnaire: Two 7-point UEQ differentials about the Assistant, both reversed because the positive pole comes first: valuable–inferior and good–bad. Empty when the participant answered none of its items (e.g. questions about the Assistant when there was none). See `scale_ueq_hedonic_norm` for the 0–1 version.

#### `scale_ueq_hedonic_norm` — Ueq hedonic (0–1)

*UEQ items on the assistant's value and overall impression (valuable — a stimulation item; good — an attractiveness item), rescaled to 0–1*

**Range:** [0, 1] · **Direction:** higher is better

$$
\hat Q_{\text{ueq\_hedonic}} = \frac{1}{\lvert S \rvert} \sum_{i \in S} \frac{v'_i - \ell_i}{h_i - \ell_i}
$$

The same scale rescaled to $[0, 1]$ item by item ($0$ = the lowest answer, $1$ = the highest), so scales and items with different ranges can be compared. For a 7-point item, $(v' - 1)/6$.

#### `scale_tam_usefulness` — Tam usefulness

*TAM perceived usefulness of the assistant*

**Range:** the items' range (1–7) · **Direction:** higher is better

$$
Q_{\text{tam\_usefulness}} = \frac{1}{\lvert S \rvert} \sum_{i \in S} v'_i, \qquad v'_i = \begin{cases} \ell_i + h_i - v_i & \text{reversed item} \\ v_i & \text{otherwise} \end{cases}
$$

The mean answer to the items $S$ of the scale **tam_usefulness**, on the items' own range (1–7 for 7-point items; reversed items scored backwards). Higher means more of what the scale measures. Items in the bundled questionnaire: Perceived usefulness from the Technology Acceptance Model (TAM, Davis, 1989): “Using this assistant would enhance my effectiveness in negotiation” and “I would find this assistant useful in negotiations” (1 = strongly disagree … 7 = strongly agree). Empty when the participant answered none of its items (e.g. questions about the Assistant when there was none). See `scale_tam_usefulness_norm` for the 0–1 version.

#### `scale_tam_usefulness_norm` — Tam usefulness (0–1)

*TAM perceived usefulness of the assistant, rescaled to 0–1*

**Range:** [0, 1] · **Direction:** higher is better

$$
\hat Q_{\text{tam\_usefulness}} = \frac{1}{\lvert S \rvert} \sum_{i \in S} \frac{v'_i - \ell_i}{h_i - \ell_i}
$$

The same scale rescaled to $[0, 1]$ item by item ($0$ = the lowest answer, $1$ = the highest), so scales and items with different ranges can be compared. For a 7-point item, $(v' - 1)/6$.

#### `scale_intention_to_use` — Intention to use

*Intention to use the assistant again*

**Range:** the items' range (1–7) · **Direction:** higher is better

$$
Q_{\text{intention\_to\_use}} = \frac{1}{\lvert S \rvert} \sum_{i \in S} v'_i, \qquad v'_i = \begin{cases} \ell_i + h_i - v_i & \text{reversed item} \\ v_i & \text{otherwise} \end{cases}
$$

The mean answer to the items $S$ of the scale **intention_to_use**, on the items' own range (1–7 for 7-point items; reversed items scored backwards). Higher means more of what the scale measures. Items in the bundled questionnaire: “I would use this assistant again” (1–7). Empty when the participant answered none of its items (e.g. questions about the Assistant when there was none). See `scale_intention_to_use_norm` for the 0–1 version.

#### `scale_intention_to_use_norm` — Intention to use (0–1)

*Intention to use the assistant again, rescaled to 0–1*

**Range:** [0, 1] · **Direction:** higher is better

$$
\hat Q_{\text{intention\_to\_use}} = \frac{1}{\lvert S \rvert} \sum_{i \in S} \frac{v'_i - \ell_i}{h_i - \ell_i}
$$

The same scale rescaled to $[0, 1]$ item by item ($0$ = the lowest answer, $1$ = the highest), so scales and items with different ranges can be compared. For a 7-point item, $(v' - 1)/6$.

#### `scale_felt_heard` — Felt heard

*Feeling heard by the assistant*

**Range:** the items' range (1–7) · **Direction:** higher is better

$$
Q_{\text{felt\_heard}} = \frac{1}{\lvert S \rvert} \sum_{i \in S} v'_i, \qquad v'_i = \begin{cases} \ell_i + h_i - v_i & \text{reversed item} \\ v_i & \text{otherwise} \end{cases}
$$

The mean answer to the items $S$ of the scale **felt_heard**, on the items' own range (1–7 for 7-point items; reversed items scored backwards). Higher means more of what the scale measures. Items in the bundled questionnaire: “I felt heard by the assistant (it took my wishes into account)” (1–7). Empty when the participant answered none of its items (e.g. questions about the Assistant when there was none). See `scale_felt_heard_norm` for the 0–1 version.

#### `scale_felt_heard_norm` — Felt heard (0–1)

*Feeling heard by the assistant, rescaled to 0–1*

**Range:** [0, 1] · **Direction:** higher is better

$$
\hat Q_{\text{felt\_heard}} = \frac{1}{\lvert S \rvert} \sum_{i \in S} \frac{v'_i - \ell_i}{h_i - \ell_i}
$$

The same scale rescaled to $[0, 1]$ item by item ($0$ = the lowest answer, $1$ = the highest), so scales and items with different ranges can be compared. For a 7-point item, $(v' - 1)/6$.

#### `scale_opponent_kindness` — Opponent kindness

*Perceived kindness of the opponent*

**Range:** the items' range (1–7) · **Direction:** higher is better

$$
Q_{\text{opponent\_kindness}} = \frac{1}{\lvert S \rvert} \sum_{i \in S} v'_i, \qquad v'_i = \begin{cases} \ell_i + h_i - v_i & \text{reversed item} \\ v_i & \text{otherwise} \end{cases}
$$

The mean answer to the items $S$ of the scale **opponent_kindness**, on the items' own range (1–7 for 7-point items; reversed items scored backwards). Higher means more of what the scale measures. Items in the bundled questionnaire: “How kind was your opponent?” (1 = not at all … 7 = very). Empty when the participant answered none of its items (e.g. questions about the Assistant when there was none). See `scale_opponent_kindness_norm` for the 0–1 version.

#### `scale_opponent_kindness_norm` — Opponent kindness (0–1)

*Perceived kindness of the opponent, rescaled to 0–1*

**Range:** [0, 1] · **Direction:** higher is better

$$
\hat Q_{\text{opponent\_kindness}} = \frac{1}{\lvert S \rvert} \sum_{i \in S} \frac{v'_i - \ell_i}{h_i - \ell_i}
$$

The same scale rescaled to $[0, 1]$ item by item ($0$ = the lowest answer, $1$ = the highest), so scales and items with different ranges can be compared. For a 7-point item, $(v' - 1)/6$.

#### `scale_opponent_intelligence` — Opponent intelligence

*Perceived intelligence of the opponent*

**Range:** the items' range (1–7) · **Direction:** higher is better

$$
Q_{\text{opponent\_intelligence}} = \frac{1}{\lvert S \rvert} \sum_{i \in S} v'_i, \qquad v'_i = \begin{cases} \ell_i + h_i - v_i & \text{reversed item} \\ v_i & \text{otherwise} \end{cases}
$$

The mean answer to the items $S$ of the scale **opponent_intelligence**, on the items' own range (1–7 for 7-point items; reversed items scored backwards). Higher means more of what the scale measures. Items in the bundled questionnaire: “How intelligent was your opponent?” (1 = not at all … 7 = very). Empty when the participant answered none of its items (e.g. questions about the Assistant when there was none). See `scale_opponent_intelligence_norm` for the 0–1 version.

#### `scale_opponent_intelligence_norm` — Opponent intelligence (0–1)

*Perceived intelligence of the opponent, rescaled to 0–1*

**Range:** [0, 1] · **Direction:** higher is better

$$
\hat Q_{\text{opponent\_intelligence}} = \frac{1}{\lvert S \rvert} \sum_{i \in S} \frac{v'_i - \ell_i}{h_i - \ell_i}
$$

The same scale rescaled to $[0, 1]$ item by item ($0$ = the lowest answer, $1$ = the highest), so scales and items with different ranges can be compared. For a 7-point item, $(v' - 1)/6$.

#### `scale_opponent_humanlike` — Opponent humanlike

*Belief that the opponent was human*

**Range:** the items' range (1–7) · **Direction:** higher is better

$$
Q_{\text{opponent\_humanlike}} = \frac{1}{\lvert S \rvert} \sum_{i \in S} v'_i, \qquad v'_i = \begin{cases} \ell_i + h_i - v_i & \text{reversed item} \\ v_i & \text{otherwise} \end{cases}
$$

The mean answer to the items $S$ of the scale **opponent_humanlike**, on the items' own range (1–7 for 7-point items; reversed items scored backwards). Higher means more of what the scale measures. Items in the bundled questionnaire: “Do you think your opponent was a human or an AI?” (1 = surely an AI … 7 = surely a human). Empty when the participant answered none of its items (e.g. questions about the Assistant when there was none). See `scale_opponent_humanlike_norm` for the 0–1 version.

#### `scale_opponent_humanlike_norm` — Opponent humanlike (0–1)

*Belief that the opponent was human, rescaled to 0–1*

**Range:** [0, 1] · **Direction:** higher is better

$$
\hat Q_{\text{opponent\_humanlike}} = \frac{1}{\lvert S \rvert} \sum_{i \in S} \frac{v'_i - \ell_i}{h_i - \ell_i}
$$

The same scale rescaled to $[0, 1]$ item by item ($0$ = the lowest answer, $1$ = the highest), so scales and items with different ranges can be compared. For a 7-point item, $(v' - 1)/6$.

#### `scale_relationship` — Relationship

*Wish to negotiate again / feeling connected to the opponent*

**Range:** the items' range (1–7) · **Direction:** higher is better

$$
Q_{\text{relationship}} = \frac{1}{\lvert S \rvert} \sum_{i \in S} v'_i, \qquad v'_i = \begin{cases} \ell_i + h_i - v_i & \text{reversed item} \\ v_i & \text{otherwise} \end{cases}
$$

The mean answer to the items $S$ of the scale **relationship**, on the items' own range (1–7 for 7-point items; reversed items scored backwards). Higher means more of what the scale measures. Items in the bundled questionnaire: “I would like to negotiate with this opponent again” and “I felt humanly connected to the other party” (1 = strongly disagree … 7 = strongly agree). Empty when the participant answered none of its items (e.g. questions about the Assistant when there was none). See `scale_relationship_norm` for the 0–1 version.

#### `scale_relationship_norm` — Relationship (0–1)

*Wish to negotiate again / feeling connected to the opponent, rescaled to 0–1*

**Range:** [0, 1] · **Direction:** higher is better

$$
\hat Q_{\text{relationship}} = \frac{1}{\lvert S \rvert} \sum_{i \in S} \frac{v'_i - \ell_i}{h_i - \ell_i}
$$

The same scale rescaled to $[0, 1]$ item by item ($0$ = the lowest answer, $1$ = the highest), so scales and items with different ranges can be compared. For a 7-point item, $(v' - 1)/6$.

#### `questionnaire_answered` — Answered

*1 if the participant answered the questionnaire*

**Range:** 0 or 1 · **Direction:** no better direction

$$
\mathbb{1}\left[\text{questionnaire submitted}\right]
$$

1 when the participant submitted the questionnaire. When it is 0 the scale columns are empty.

#### Dynamic columns

Columns whose names depend on the questionnaire.

##### `scale_<name>_norm` — <name> (0–1)

*Any other scale of the questionnaire, rescaled to 0–1*

**Range:** [0, 1] · **Direction:** higher is better

$$
\hat Q_{s} = \frac{1}{\lvert S \rvert} \sum_{i \in S} \frac{v'_i - \ell_i}{h_i - \ell_i}
$$

A scale defined by your questionnaire (`scale: <name>`), rescaled to $[0, 1]$ item by item. The same scale rescaled to $[0, 1]$ item by item ($0$ = the lowest answer, $1$ = the highest), so scales and items with different ranges can be compared. For a 7-point item, $(v' - 1)/6$.

##### `scale_<name>` — <name>

*Any other scale of the questionnaire (mean of its items)*

**Range:** the items' range · **Direction:** higher is better

$$
Q_{s} = \frac{1}{\lvert S \rvert} \sum_{i \in S} v'_i, \qquad v'_i = \begin{cases} \ell_i + h_i - v_i & \text{reversed item} \\ v_i & \text{otherwise} \end{cases}
$$

The mean answer to the items of a scale defined by your questionnaire (`scale: <name>`), on the items' own range with reversed items (`reverse: true`) scored backwards.

##### `q_<id>` — <id>

*The numeric answer to one question*

**Range:** the question's range · **Direction:** no better direction

$$
v'_{\text{id}}
$$

The answer to the question with this `id` (whether or not it belongs to a scale): the number for rating questions, 1/0 for yes/no, the option's position for a choice, reversed when `reverse: true`.

## Soft metrics (language-model judge)

Judged by a language model from a transcript of the session. Opt-in, because every judgement costs calls.

### `judge_assistant` — LLM judge: assistant

*soft · needs a language model*

A language model rates the Assistant (1–7) on helpfulness, explanations,
opponent insight, understanding of the human, autonomy and communication.

$$
J_c \in \{1, \dots, 7\} \ \text{for every criterion } c, \qquad J_{\text{overall}} \in \{1, \dots, 7\}
$$

A language model rates the Assistant from 1 to 7 on helpfulness, explanations, insight into the
Opponent, understanding of the Human, explaining the scenario and its own abilities, respect for the
Human's autonomy, communication and improving the Human's messages. Not computed for sessions without
any Assistant activity (no chat, suggestion, function call or action).

**How it is judged.** The judge is the language model configured for evaluation, asked at temperature
0 with a fixed rubric; its answer must be one JSON object (it is asked again once if not). It sees both
sides' utilities (between 0 and 1), which the Human did not, and is not told which Opponent agent was
used nor the participant's questionnaire answers, so its view is independent of both. Very long
transcripts are shortened in the middle. Judgements are cached next to the recording per metric,
prompt version and judge model.

**Caveats.** A language model's ratings are noisy and may be biased (e.g. toward long, polite
messages); compare groups judged by the same model, and check a sample by hand.

#### `ja_helpfulness` — Assistant: helpfulness

*How much the assistant helped the human get a good outcome.*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{helpfulness}} = \min\big(7, \max(1, x_{\text{helpfulness}})\big), \quad x \text{ the judge's rating}
$$

A language model (the judge) reads a transcript of the session (both sides' utilities, every offer, chat message, suggestion and function call, with times) and rates the Assistant from 1 (very poor) to 7 (excellent) on this criterion, or answers null when the record gives no evidence for it. Higher is better. Answers outside 1–7 are clipped; null and unparsable answers are empty. The criterion as the judge sees it: “How much the assistant helped the human get a good outcome.”

#### `ja_explanation` — Assistant: explanation

*Whether its recommendations came with clear reasons.*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{explanation}} = \min\big(7, \max(1, x_{\text{explanation}})\big), \quad x \text{ the judge's rating}
$$

A language model (the judge) reads a transcript of the session (both sides' utilities, every offer, chat message, suggestion and function call, with times) and rates the Assistant from 1 (very poor) to 7 (excellent) on this criterion, or answers null when the record gives no evidence for it. Higher is better. Answers outside 1–7 are clipped; null and unparsable answers are empty. The criterion as the judge sees it: “Whether its recommendations came with clear reasons.”

#### `ja_opponent_insight` — Assistant: opponent insight

*Whether it explained the opponent's behaviour or likely preferences correctly.*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{opponent\_insight}} = \min\big(7, \max(1, x_{\text{opponent\_insight}})\big), \quad x \text{ the judge's rating}
$$

A language model (the judge) reads a transcript of the session (both sides' utilities, every offer, chat message, suggestion and function call, with times) and rates the Assistant from 1 (very poor) to 7 (excellent) on this criterion, or answers null when the record gives no evidence for it. Higher is better. Answers outside 1–7 are clipped; null and unparsable answers are empty. The criterion as the judge sees it: “Whether it explained the opponent's behaviour or likely preferences correctly.”

#### `ja_user_understanding` — Assistant: user understanding

*Whether it understood what the human wanted (theory of mind) and checked it.*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{user\_understanding}} = \min\big(7, \max(1, x_{\text{user\_understanding}})\big), \quad x \text{ the judge's rating}
$$

A language model (the judge) reads a transcript of the session (both sides' utilities, every offer, chat message, suggestion and function call, with times) and rates the Assistant from 1 (very poor) to 7 (excellent) on this criterion, or answers null when the record gives no evidence for it. Higher is better. Answers outside 1–7 are clipped; null and unparsable answers are empty. The criterion as the judge sees it: “Whether it understood what the human wanted (theory of mind) and checked it.”

#### `ja_scenario_explanation` — Assistant: scenario explanation

*Whether it helped the human understand the scenario and their preferences.*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{scenario\_explanation}} = \min\big(7, \max(1, x_{\text{scenario\_explanation}})\big), \quad x \text{ the judge's rating}
$$

A language model (the judge) reads a transcript of the session (both sides' utilities, every offer, chat message, suggestion and function call, with times) and rates the Assistant from 1 (very poor) to 7 (excellent) on this criterion, or answers null when the record gives no evidence for it. Higher is better. Answers outside 1–7 are clipped; null and unparsable answers are empty. The criterion as the judge sees it: “Whether it helped the human understand the scenario and their preferences.”

#### `ja_capability_disclosure` — Assistant: capability disclosure

*Whether it told the human what it can and cannot do.*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{capability\_disclosure}} = \min\big(7, \max(1, x_{\text{capability\_disclosure}})\big), \quad x \text{ the judge's rating}
$$

A language model (the judge) reads a transcript of the session (both sides' utilities, every offer, chat message, suggestion and function call, with times) and rates the Assistant from 1 (very poor) to 7 (excellent) on this criterion, or answers null when the record gives no evidence for it. Higher is better. Answers outside 1–7 are clipped; null and unparsable answers are empty. The criterion as the judge sees it: “Whether it told the human what it can and cannot do.”

#### `ja_autonomy_respect` — Assistant: autonomy respect

*Whether it left the human in control (no unwanted actions, no taking over).*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{autonomy\_respect}} = \min\big(7, \max(1, x_{\text{autonomy\_respect}})\big), \quad x \text{ the judge's rating}
$$

A language model (the judge) reads a transcript of the session (both sides' utilities, every offer, chat message, suggestion and function call, with times) and rates the Assistant from 1 (very poor) to 7 (excellent) on this criterion, or answers null when the record gives no evidence for it. Higher is better. Answers outside 1–7 are clipped; null and unparsable answers are empty. The criterion as the judge sees it: “Whether it left the human in control (no unwanted actions, no taking over).”

#### `ja_communication` — Assistant: communication

*Clarity, brevity and tone of its messages.*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{communication}} = \min\big(7, \max(1, x_{\text{communication}})\big), \quad x \text{ the judge's rating}
$$

A language model (the judge) reads a transcript of the session (both sides' utilities, every offer, chat message, suggestion and function call, with times) and rates the Assistant from 1 (very poor) to 7 (excellent) on this criterion, or answers null when the record gives no evidence for it. Higher is better. Answers outside 1–7 are clipped; null and unparsable answers are empty. The criterion as the judge sees it: “Clarity, brevity and tone of its messages.”

#### `ja_message_improvement` — Assistant: message improvement

*Whether it improved the messages the human sent to the opponent (if it did that).*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{message\_improvement}} = \min\big(7, \max(1, x_{\text{message\_improvement}})\big), \quad x \text{ the judge's rating}
$$

A language model (the judge) reads a transcript of the session (both sides' utilities, every offer, chat message, suggestion and function call, with times) and rates the Assistant from 1 (very poor) to 7 (excellent) on this criterion, or answers null when the record gives no evidence for it. Higher is better. Answers outside 1–7 are clipped; null and unparsable answers are empty. The criterion as the judge sees it: “Whether it improved the messages the human sent to the opponent (if it did that).”

#### `ja_overall` — Assistant: overall

*Overall judgement of the assistant (1–7)*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{overall}} = \min\big(7, \max(1, x_{\text{overall}})\big)
$$

The judge's overall rating of the Assistant (1–7), given together with the criteria and a short justification (in the details). Higher is better.

### `judge_opponent` — LLM judge: opponent

*soft · needs a language model*

A language model rates the opponent as the human experienced it.

$$
J_c \in \{1, \dots, 7\} \ \text{for every criterion } c, \qquad J_{\text{overall}} \in \{1, \dots, 7\}
$$

A language model rates the Opponent as the Human experienced it from 1 to 7: kindness, intelligence,
cooperativeness, how human-like it seemed, its messages and its consistency. Compare with the
participant's own view (`questionnaire`: `opponent_kindness`, `opponent_intelligence`,
`opponent_humanlike`). Not computed for sessions without offers.

**How it is judged.** The judge is the language model configured for evaluation, asked at temperature
0 with a fixed rubric; its answer must be one JSON object (it is asked again once if not). It sees both
sides' utilities (between 0 and 1), which the Human did not, and is not told which Opponent agent was
used nor the participant's questionnaire answers, so its view is independent of both. Very long
transcripts are shortened in the middle. Judgements are cached next to the recording per metric,
prompt version and judge model.

**Caveats.** A language model's ratings are noisy and may be biased (e.g. toward long, polite
messages); compare groups judged by the same model, and check a sample by hand.

#### `jo_kindness` — Opponent: kindness

*How kind / polite the opponent was.*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{kindness}} = \min\big(7, \max(1, x_{\text{kindness}})\big), \quad x \text{ the judge's rating}
$$

A language model (the judge) reads a transcript of the session (both sides' utilities, every offer, chat message, suggestion and function call, with times) and rates the Opponent from 1 (very poor) to 7 (excellent) on this criterion, or answers null when the record gives no evidence for it. Higher is better. Answers outside 1–7 are clipped; null and unparsable answers are empty. The criterion as the judge sees it: “How kind / polite the opponent was.”

#### `jo_intelligence` — Opponent: intelligence

*How intelligent and strategic the opponent was.*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{intelligence}} = \min\big(7, \max(1, x_{\text{intelligence}})\big), \quad x \text{ the judge's rating}
$$

A language model (the judge) reads a transcript of the session (both sides' utilities, every offer, chat message, suggestion and function call, with times) and rates the Opponent from 1 (very poor) to 7 (excellent) on this criterion, or answers null when the record gives no evidence for it. Higher is better. Answers outside 1–7 are clipped; null and unparsable answers are empty. The criterion as the judge sees it: “How intelligent and strategic the opponent was.”

#### `jo_cooperativeness` — Opponent: cooperativeness

*How willing it was to find a mutually good deal.*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{cooperativeness}} = \min\big(7, \max(1, x_{\text{cooperativeness}})\big), \quad x \text{ the judge's rating}
$$

A language model (the judge) reads a transcript of the session (both sides' utilities, every offer, chat message, suggestion and function call, with times) and rates the Opponent from 1 (very poor) to 7 (excellent) on this criterion, or answers null when the record gives no evidence for it. Higher is better. Answers outside 1–7 are clipped; null and unparsable answers are empty. The criterion as the judge sees it: “How willing it was to find a mutually good deal.”

#### `jo_human_likeness` — Opponent: human likeness

*How human-like it seemed (7 = indistinguishable from a person).*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{human\_likeness}} = \min\big(7, \max(1, x_{\text{human\_likeness}})\big), \quad x \text{ the judge's rating}
$$

A language model (the judge) reads a transcript of the session (both sides' utilities, every offer, chat message, suggestion and function call, with times) and rates the Opponent from 1 (very poor) to 7 (excellent) on this criterion, or answers null when the record gives no evidence for it. Higher is better. Answers outside 1–7 are clipped; null and unparsable answers are empty. The criterion as the judge sees it: “How human-like it seemed (7 = indistinguishable from a person).”

#### `jo_communication` — Opponent: communication

*Quality of its messages (if any).*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{communication}} = \min\big(7, \max(1, x_{\text{communication}})\big), \quad x \text{ the judge's rating}
$$

A language model (the judge) reads a transcript of the session (both sides' utilities, every offer, chat message, suggestion and function call, with times) and rates the Opponent from 1 (very poor) to 7 (excellent) on this criterion, or answers null when the record gives no evidence for it. Higher is better. Answers outside 1–7 are clipped; null and unparsable answers are empty. The criterion as the judge sees it: “Quality of its messages (if any).”

#### `jo_consistency` — Opponent: consistency

*How consistent its offers and messages were.*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{consistency}} = \min\big(7, \max(1, x_{\text{consistency}})\big), \quad x \text{ the judge's rating}
$$

A language model (the judge) reads a transcript of the session (both sides' utilities, every offer, chat message, suggestion and function call, with times) and rates the Opponent from 1 (very poor) to 7 (excellent) on this criterion, or answers null when the record gives no evidence for it. Higher is better. Answers outside 1–7 are clipped; null and unparsable answers are empty. The criterion as the judge sees it: “How consistent its offers and messages were.”

#### `jo_overall` — Opponent: overall

*Overall judgement of the opponent (1–7)*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{overall}} = \min\big(7, \max(1, x_{\text{overall}})\big)
$$

The judge's overall rating of the Opponent (1–7), given together with the criteria and a short justification (in the details). Higher is better.

### `judge_human` — LLM judge: human

*soft · needs a language model*

A language model rates the human's engagement and negotiation.

$$
J_c \in \{1, \dots, 7\} \ \text{for every criterion } c, \qquad J_{\text{overall}} \in \{1, \dots, 7\}
$$

A language model rates what the Human did themselves (not the Assistant) from 1 to 7: engagement,
strategy, cooperativeness, use of the Assistant (neither ignoring nor blindly following it) and their
messages. Not computed for sessions without actions.

**How it is judged.** The judge is the language model configured for evaluation, asked at temperature
0 with a fixed rubric; its answer must be one JSON object (it is asked again once if not). It sees both
sides' utilities (between 0 and 1), which the Human did not, and is not told which Opponent agent was
used nor the participant's questionnaire answers, so its view is independent of both. Very long
transcripts are shortened in the middle. Judgements are cached next to the recording per metric,
prompt version and judge model.

**Caveats.** A language model's ratings are noisy and may be biased (e.g. toward long, polite
messages); compare groups judged by the same model, and check a sample by hand.

#### `jh_engagement` — Human: engagement

*How invested the human was (explored offers, thought about moves, did not just click through).*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{engagement}} = \min\big(7, \max(1, x_{\text{engagement}})\big), \quad x \text{ the judge's rating}
$$

A language model (the judge) reads a transcript of the session (both sides' utilities, every offer, chat message, suggestion and function call, with times) and rates the Human from 1 (very poor) to 7 (excellent) on this criterion, or answers null when the record gives no evidence for it. Higher is better. Answers outside 1–7 are clipped; null and unparsable answers are empty. The criterion as the judge sees it: “How invested the human was (explored offers, thought about moves, did not just click through).”

#### `jh_strategy` — Human: strategy

*Quality of the human's negotiation strategy.*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{strategy}} = \min\big(7, \max(1, x_{\text{strategy}})\big), \quad x \text{ the judge's rating}
$$

A language model (the judge) reads a transcript of the session (both sides' utilities, every offer, chat message, suggestion and function call, with times) and rates the Human from 1 (very poor) to 7 (excellent) on this criterion, or answers null when the record gives no evidence for it. Higher is better. Answers outside 1–7 are clipped; null and unparsable answers are empty. The criterion as the judge sees it: “Quality of the human's negotiation strategy.”

#### `jh_cooperativeness` — Human: cooperativeness

*How cooperative the human was toward the opponent.*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{cooperativeness}} = \min\big(7, \max(1, x_{\text{cooperativeness}})\big), \quad x \text{ the judge's rating}
$$

A language model (the judge) reads a transcript of the session (both sides' utilities, every offer, chat message, suggestion and function call, with times) and rates the Human from 1 (very poor) to 7 (excellent) on this criterion, or answers null when the record gives no evidence for it. Higher is better. Answers outside 1–7 are clipped; null and unparsable answers are empty. The criterion as the judge sees it: “How cooperative the human was toward the opponent.”

#### `jh_use_of_assistant` — Human: use of assistant

*How well the human used the assistant (neither ignoring nor blindly following it).*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{use\_of\_assistant}} = \min\big(7, \max(1, x_{\text{use\_of\_assistant}})\big), \quad x \text{ the judge's rating}
$$

A language model (the judge) reads a transcript of the session (both sides' utilities, every offer, chat message, suggestion and function call, with times) and rates the Human from 1 (very poor) to 7 (excellent) on this criterion, or answers null when the record gives no evidence for it. Higher is better. Answers outside 1–7 are clipped; null and unparsable answers are empty. The criterion as the judge sees it: “How well the human used the assistant (neither ignoring nor blindly following it).”

#### `jh_communication` — Human: communication

*Quality of the human's messages (if any).*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{communication}} = \min\big(7, \max(1, x_{\text{communication}})\big), \quad x \text{ the judge's rating}
$$

A language model (the judge) reads a transcript of the session (both sides' utilities, every offer, chat message, suggestion and function call, with times) and rates the Human from 1 (very poor) to 7 (excellent) on this criterion, or answers null when the record gives no evidence for it. Higher is better. Answers outside 1–7 are clipped; null and unparsable answers are empty. The criterion as the judge sees it: “Quality of the human's messages (if any).”

#### `jh_overall` — Human: overall

*Overall judgement of the human (1–7)*

**Range:** 1–7 · **Direction:** higher is better

$$
J_{\text{overall}} = \min\big(7, \max(1, x_{\text{overall}})\big)
$$

The judge's overall rating of the Human (1–7), given together with the criteria and a short justification (in the details). Higher is better.

### `nl_assertions` — LLM judge: assertions

*soft · needs a language model*

Natural-language statements about the session (by default about the
assistant's explanatory behaviour), each judged met / not met / not
applicable. Set them with ``options.assertions`` or env.json
``evaluation.assertions``.

$$
m_i \in \{\text{true}, \text{false}, \text{null}\} \ \text{for every assertion } i
$$

Natural-language statements the session should satisfy, each judged by a language model as met
(true), not met (false) or not applicable (null, when the record gives no opportunity to check it).
By default they check the Assistant's explanatory behaviour: that it explained what it can do, the
Opponent's behaviour and its recommendations, checked the Human's goals, helped them understand the
scenario, never acted without consent and gave advice consistent with the Human's preferences. Set your
own with the option `assertions` or `evaluation.assertions` in env.json. Each verdict and its
one-sentence reasoning are in the details.

**Example.** Seven assertions: four met, one not met, two not applicable. `assertions_met`
$= 4/5 = 0.8$ and `assertions_total` $= 5$.

Not computed for sessions without Assistant activity unless assertions are given explicitly.

**How it is judged.** The judge is the language model configured for evaluation, asked at temperature
0 with a fixed rubric; its answer must be one JSON object (it is asked again once if not). It sees both
sides' utilities (between 0 and 1), which the Human did not, and is not told which Opponent agent was
used nor the participant's questionnaire answers, so its view is independent of both. Very long
transcripts are shortened in the middle. Judgements are cached next to the recording per metric,
prompt version and judge model.

**Caveats.** A language model's ratings are noisy and may be biased (e.g. toward long, polite
messages); compare groups judged by the same model, and check a sample by hand.

**Options:**

* `assertions` — The statements to check (a list of strings); default: env.json evaluation.assertions or the built-in list.

#### `assertions_met` — Assertions met

*Share of the applicable natural-language assertions the judge found satisfied*

**Range:** [0, 1] · **Direction:** higher is better

$$
\frac{\lvert \{i : m_i = \text{true}\} \rvert}{\lvert \{i : m_i \neq \text{null}\} \rvert}
$$

The share of the applicable assertions that were met; assertions judged not applicable are left out.
Higher is better. Empty when none applied.

#### `assertions_total` — Assertions judged

*Assertions that applied to this session*

**Range:** count · **Direction:** no better direction

$$
\lvert \{i : m_i \neq \text{null}\} \rvert
$$

How many assertions the judge found applicable (met or not met): the denominator of `assertions_met`.
It is not the number of assertions asked.

### `error_review` — LLM judge: error review

*soft · needs a language model*

The judge lists the mistakes of the assistant and of the human with
their severity and tags, and when the human overriding the assistant
helped or hurt.

$$
E = \{(\text{source}, \text{time}, \text{severity}, \dots)\}, \quad \text{severity} \in \{\text{minor}, \text{major}, \text{critical}\}
$$

A language model lists the errors $E$ made by the Assistant and by the Human (wrong or harmful advice,
misreading the Opponent, accepting a bad deal, rejecting a good one, ignoring their own preferences,
unclear or misleading messages, acting without consent, …), each with its source, time, severity
(**critical** = it changed the final outcome) and tags, and counts the times the Human went against the
Assistant's suggestion and whether that helped or hurt. The full list is in the details.

An error whose source mentions "assist" or "agent" is the Assistant's, any other the Human's; an
unknown severity counts as minor.

**Simulated participants.** When a simulated participant played the Human (`mode: simulated`), the
judge is shown the persona (its policy, goal and reservation value) and may also blame a third source,
the **simulator**: the persona broke character or its own instructions (it revealed its private
reservation value unprompted, ignored its policy, stopped for no reason, behaved like no human
would). A "human" error then means an in-character negotiating mistake. Simulator errors are audited
like this, as in τ²-bench, to tell Assistant failures from simulator failures; they count in
`simulator_errors` and never as the Assistant's or the Human's.

**Example.** The judge reports a minor Assistant error at 01:10, a critical Human error at 02:30 and a
critical Assistant error at 03:05: `assistant_errors` $= 2$, `assistant_critical_errors` $= 1$,
`human_errors` $= 1$, `human_critical_errors` $= 1$ and `first_critical` = human.

Not computed for sessions without actions.

**How it is judged.** The judge is the language model configured for evaluation, asked at temperature
0 with a fixed rubric; its answer must be one JSON object (it is asked again once if not). It sees both
sides' utilities (between 0 and 1), which the Human did not, and is not told which Opponent agent was
used nor the participant's questionnaire answers, so its view is independent of both. Very long
transcripts are shortened in the middle. Judgements are cached next to the recording per metric,
prompt version and judge model.

**Caveats.** A language model's ratings are noisy and may be biased (e.g. toward long, polite
messages); compare groups judged by the same model, and check a sample by hand.

#### `assistant_errors` — Assistant errors

*Errors the judge found in the assistant's behaviour*

**Range:** count · **Direction:** lower is better

$$
\lvert \{e \in E : \text{source}(e) = \text{assistant}\} \rvert
$$

How many errors the judge attributed to the Assistant, of any severity. Lower is better.

#### `assistant_critical_errors` — Assistant critical errors

*… of which critical (changed the outcome)*

**Range:** count · **Direction:** lower is better

$$
\lvert \{e \in E : \text{source}(e) = \text{assistant} \wedge \text{severity}(e) = \text{critical}\} \rvert
$$

The Assistant's errors that, according to the judge, changed the final outcome.

#### `human_errors` — Human errors

*Errors the judge found in the human's decisions*

**Range:** count · **Direction:** lower is better

$$
\lvert \{e \in E : \text{source}(e) = \text{human}\} \rvert
$$

How many errors the judge attributed to the Human, of any severity. Lower is better.

#### `human_critical_errors` — Human critical errors

*… of which critical*

**Range:** count · **Direction:** lower is better

$$
\lvert \{e \in E : \text{source}(e) = \text{human} \wedge \text{severity}(e) = \text{critical}\} \rvert
$$

The Human's errors that, according to the judge, changed the final outcome.

#### `simulator_errors` — Simulator errors

*Errors of the user simulator (simulated participants only)*

**Range:** count · **Direction:** lower is better

$$
\lvert \{e \in E : \text{source}(e) = \text{simulator}\} \rvert
$$

For a simulated participant, how many errors the judge blamed on the simulator itself (the persona broke
character or its instructions) rather than on the Assistant or on an in-character mistake. Empty for
human sessions.

#### `simulator_critical_errors` — Simulator critical errors

*… of which critical*

**Range:** count · **Direction:** lower is better

$$
\lvert \{e \in E : \text{source}(e) = \text{simulator} \wedge \text{severity}(e) = \text{critical}\} \rvert
$$

The simulator's errors that, according to the judge, changed the final outcome. A trial with one is a
candidate to discard before computing pass^k. Empty for human sessions.

#### `human_overrode_helpfully` — Helpful overrides

*Times the human went against the assistant and it helped*

**Range:** count · **Direction:** higher is better

$$
n_{\text{override}}^{+}
$$

How often the Human did something different from the Assistant's suggestion and it helped them, as
counted by the judge. Higher means the Human added value over the Assistant.

#### `human_overrode_harmfully` — Harmful overrides

*Times the human went against the assistant and it hurt*

**Range:** count · **Direction:** lower is better

$$
n_{\text{override}}^{-}
$$

How often the Human did something different from the Assistant's suggestion and it hurt them, as
counted by the judge.

#### `first_critical` — First critical error

*Who made the first critical error: assistant, human, simulator or none*

**Range:** category · **Direction:** no better direction

$$
\text{source}\Big(\operatorname*{arg\,min}_{e \in E,\ \text{severity}(e) = \text{critical}} \text{time}(e)\Big) \in \{\text{assistant}, \text{human}, \text{simulator}, \text{none}\}
$$

Who made the earliest critical error (by the mm:ss time the judge gave; errors without a readable
time come last), or none. It shows who first put the outcome at risk.

### `task_judge` — LLM judge: scenario criteria

*soft · needs a language model*

A language model checks the facts the Assistant had to convey and the
scenario's own assertions.

$$
c_i, a_j \in \{\text{true}, \text{false}, \text{null}\} \ \text{for every fact } i \text{ and assertion } j
$$

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

**Options:**

* `criteria` — Evaluation criteria for scenarios without their own (a dict with communicate, assertions, …).

#### `task_communicated` — Facts communicated

*Share of the scenario's facts the Assistant conveyed to the Human*

**Range:** [0, 1] · **Direction:** higher is better

$$
\frac{\lvert \{i : c_i = \text{true}\} \rvert}{\lvert \{i : c_i \neq \text{null}\} \rvert}
$$

The share of the facts of the scenario's `communicate` list that the Assistant told the Human. 1 is
needed for the `communicate` component of `task_success`.

#### `task_assertions_met` — Scenario assertions met

*Share of the scenario's applicable assertions that were met*

**Range:** [0, 1] · **Direction:** higher is better

$$
\frac{\lvert \{j : a_j = \text{true}\} \rvert}{\lvert \{j : a_j \neq \text{null}\} \rvert}
$$

The share of the scenario's applicable `assertions` that the judge found met (not-applicable ones are
left out). 1 is needed for the `assertions` component of `task_success`.

## Task success and combined scores

Computed after the other metrics, from their columns: whether the session met its scenario's evaluation criteria, and the combined scores of the Human-Agent Negotiation and Hybrid Intelligence tracks.

### `task_success` — Task success

*score*

Pass/fail against the scenario's evaluation criteria (the product of its
components: targets, rules, facts communicated, assertions).

$$
\text{task\_success} = \prod_{c \in B} \mathbb{1}[c \text{ holds}], \qquad B \subseteq \{\text{targets}, \text{rules}, \text{communicate}, \text{assertions}\}
$$

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

**Options:**

* `criteria` — Evaluation criteria for scenarios without their own (a dict with targets, rules, communicate, assertions, basis).

#### `task_success` — Task success

*1 if the session met every component of its scenario's evaluation criteria*

**Range:** 0 or 1 · **Direction:** higher is better

$$
\prod_{c \in B} \mathbb{1}[c \text{ holds}]
$$

1 when every component of the basis holds, 0 when one fails. Empty when the scenario has no criteria or
a component of an explicit `basis` was not evaluated.

#### `task_targets_met` — Targets met

*Share of the scenario's targets the session met*

**Range:** [0, 1] · **Direction:** higher is better

$$
\frac{\lvert \{t \in T : t \text{ holds}\} \rvert}{\lvert T \rvert}
$$

The share of the conditions of `targets` that hold. A target on a column that has no value (for
example a questionnaire scale without a questionnaire, or a misspelled column) makes the share empty.

#### `task_rules_ok` — Rules respected

*1 if every rule check the scenario names is 0*

**Range:** 0 or 1 · **Direction:** higher is better

$$
\prod_{\rho \in R} \mathbb{1}[\rho = 0]
$$

1 when none of the rule checks named in `rules` fired (missing checks count as respected: e.g.
`irrational_suggestions` without an Assistant).

#### `task_components` — Components checked

*How many components the task success was computed from*

**Range:** count · **Direction:** no better direction

$$
\lvert B \rvert
$$

The number of components (targets, rules, communicate, assertions) that `task_success` multiplied.

### `scores` — Combined scores (HAN and HI tracks)

*score*

The combined scores of the HAN and HI tracks, from the other metrics.

$$
S = \frac{\sum_{i \in P} w_i\, \phi_i(x_i)}{\sum_{i \in P} w_i}, \qquad P = \{i : x_i \text{ has a value}\}
$$

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

**Options:**

* `scores` — Weight overrides: {score: {weights: {column: weight}}} (0 drops a component).

#### `han_outcome` — HAN outcome

*What the Opponent agent obtained against the Human (Human-Agent Negotiation track)*

**Range:** [0, 1] · **Direction:** higher is better

$$
S = \frac{\sum_{i \in P} w_i\, \phi_i(x_i)}{\sum_{i \in P} w_i}
$$

The outcome board of the Human-Agent Negotiation track ranks Opponent agents by the share of their
largest possible gain over no deal that they obtained against human participants. No deal scores 0,
and so does a session that the agent ended by failing.

| Component | What | Weight | Normalised as |
| --- | --- | --- | --- |
| `opponent_advantage` | the Opponent's advantage | 1 | an advantage clipped to [0, 1] (no better than no deal = 0): $\min(1, \max(0, x))$ |

The score is 0 when `opponent_failed` is 1.

Components without a value are left out (see `han_outcome_coverage`).

#### `han_outcome_coverage` — HAN outcome coverage

*Share of the weight of han_outcome that had a value*

**Range:** [0, 1] · **Direction:** higher is better

$$
\frac{\sum_{i \in P} w_i}{\sum_{i} w_i}
$$

The share of the total weight of `han_outcome` whose components had a value in this session: 1 when
every component was measured, lower when (for example) there was no questionnaire or no judge.
Compare scores only between sessions with similar coverage; the leaderboards use the same
components for every entrant.

#### `han_interaction` — HAN interaction

*How well the Opponent agent behaved as an opponent (Human-Agent Negotiation track)*

**Range:** [0, 1] · **Direction:** higher is better

$$
S = \frac{\sum_{i \in P} w_i\, \phi_i(x_i)}{\sum_{i \in P} w_i}
$$

The interaction board of the Human-Agent Negotiation track: how the participants experienced the
agent (questionnaire), how a language-model judge rates its behaviour and messages, and whether it
negotiated soundly (no failure, no deal accepted below its own reservation value).

| Component | What | Weight | Normalised as |
| --- | --- | --- | --- |
| `scale_opponent_kindness_norm` | questionnaire: kindness | 1 | the value, clipped to [0, 1]: $\min(1, \max(0, x))$ |
| `scale_opponent_intelligence_norm` | questionnaire: intelligence | 1 | the value, clipped to [0, 1]: $\min(1, \max(0, x))$ |
| `scale_opponent_humanlike_norm` | questionnaire: human-likeness | 1 | the value, clipped to [0, 1]: $\min(1, \max(0, x))$ |
| `scale_relationship_norm` | questionnaire: wanting to negotiate again | 1 | the value, clipped to [0, 1]: $\min(1, \max(0, x))$ |
| `scale_satisfaction_norm` | questionnaire: the participant's satisfaction | 0.5 | the value, clipped to [0, 1]: $\min(1, \max(0, x))$ |
| `jo_overall` | judge: overall | 1 | a 1–7 rating mapped to [0, 1]: $(x - 1) / 6$ |
| `jo_communication` | judge: communication | 0.5 | a 1–7 rating mapped to [0, 1]: $(x - 1) / 6$ |
| `jo_consistency` | judge: consistency | 0.5 | a 1–7 rating mapped to [0, 1]: $(x - 1) / 6$ |
| `jo_human_likeness` | judge: human-likeness | 0.5 | a 1–7 rating mapped to [0, 1]: $(x - 1) / 6$ |
| `opponent_failed` | did not fail | 1 | one minus a [0, 1] value where lower is better (e.g. a 0/1 flag): $1 - \min(1, \max(0, x))$ |
| `opponent_irrational_accept` | did not accept below its reservation value | 0.5 | one minus a [0, 1] value where lower is better (e.g. a 0/1 flag): $1 - \min(1, \max(0, x))$ |

Components without a value are left out (see `han_interaction_coverage`).

#### `han_interaction_coverage` — HAN interaction coverage

*Share of the weight of han_interaction that had a value*

**Range:** [0, 1] · **Direction:** higher is better

$$
\frac{\sum_{i \in P} w_i}{\sum_{i} w_i}
$$

The share of the total weight of `han_interaction` whose components had a value in this session: 1 when
every component was measured, lower when (for example) there was no questionnaire or no judge.
Compare scores only between sessions with similar coverage; the leaderboards use the same
components for every entrant.

#### `hi_outcome` — HI outcome

*What the human–Assistant team obtained (Hybrid Intelligence track)*

**Range:** [0, 1] · **Direction:** higher is better

$$
S = \frac{\sum_{i \in P} w_i\, \phi_i(x_i)}{\sum_{i \in P} w_i}
$$

The outcome board of the Hybrid Intelligence track ranks Assistants by the share of the largest
possible gain over no deal that the team (the Human with the Assistant) obtained. No deal scores 0.

| Component | What | Weight | Normalised as |
| --- | --- | --- | --- |
| `human_advantage` | the Human side's advantage | 1 | an advantage clipped to [0, 1] (no better than no deal = 0): $\min(1, \max(0, x))$ |

Components without a value are left out (see `hi_outcome_coverage`).

#### `hi_outcome_coverage` — HI outcome coverage

*Share of the weight of hi_outcome that had a value*

**Range:** [0, 1] · **Direction:** higher is better

$$
\frac{\sum_{i \in P} w_i}{\sum_{i} w_i}
$$

The share of the total weight of `hi_outcome` whose components had a value in this session: 1 when
every component was measured, lower when (for example) there was no questionnaire or no judge.
Compare scores only between sessions with similar coverage; the leaderboards use the same
components for every entrant.

#### `hi_assistant` — HI Assistant

*How well the Assistant worked as an Assistant (Hybrid Intelligence track)*

**Range:** [0, 1] · **Direction:** higher is better

$$
S = \frac{\sum_{i \in P} w_i\, \phi_i(x_i)}{\sum_{i \in P} w_i}
$$

The Assistant itself: how a language-model judge rates its help, whether it conveyed what the
scenario requires and met the assertions, its errors, unsound suggestions, technical reliability and
responsiveness, and how the participant experienced it.

| Component | What | Weight | Normalised as |
| --- | --- | --- | --- |
| `ja_overall` | judge: overall | 1 | a 1–7 rating mapped to [0, 1]: $(x - 1) / 6$ |
| `ja_helpfulness` | judge: helpfulness | 0.5 | a 1–7 rating mapped to [0, 1]: $(x - 1) / 6$ |
| `ja_autonomy_respect` | judge: left the Human in control | 0.5 | a 1–7 rating mapped to [0, 1]: $(x - 1) / 6$ |
| `assertions_met` | judge: assertions met | 1 | the value, clipped to [0, 1]: $\min(1, \max(0, x))$ |
| `task_communicated` | judge: scenario facts conveyed | 1 | the value, clipped to [0, 1]: $\min(1, \max(0, x))$ |
| `assistant_critical_errors` | judge: critical errors | 1 | a count where lower is better: $1 / (1 + x)$ |
| `assistant_errors` | judge: errors | 0.5 | a count where lower is better: $1 / (1 + x)$ |
| `irrational_suggestions` | suggestions below the reservation value | 1 | a count where lower is better: $1 / (1 + x)$ |
| `fn_success_rate` | function calls that worked | 0.5 | the value, clipped to [0, 1]: $\min(1, \max(0, x))$ |
| `unanswered_messages` | unanswered messages | 0.5 | a count where lower is better: $1 / (1 + x)$ |
| `scale_ueq_pragmatic_norm` | questionnaire: UEQ pragmatic quality | 0.5 | the value, clipped to [0, 1]: $\min(1, \max(0, x))$ |
| `scale_tam_usefulness_norm` | questionnaire: usefulness | 0.5 | the value, clipped to [0, 1]: $\min(1, \max(0, x))$ |
| `scale_felt_heard_norm` | questionnaire: felt heard | 0.5 | the value, clipped to [0, 1]: $\min(1, \max(0, x))$ |
| `scale_intention_to_use_norm` | questionnaire: would use it again | 0.5 | the value, clipped to [0, 1]: $\min(1, \max(0, x))$ |

Empty for sessions without an Assistant.

Components without a value are left out (see `hi_assistant_coverage`).

#### `hi_assistant_coverage` — HI Assistant coverage

*Share of the weight of hi_assistant that had a value*

**Range:** [0, 1] · **Direction:** higher is better

$$
\frac{\sum_{i \in P} w_i}{\sum_{i} w_i}
$$

The share of the total weight of `hi_assistant` whose components had a value in this session: 1 when
every component was measured, lower when (for example) there was no questionnaire or no judge.
Compare scores only between sessions with similar coverage; the leaderboards use the same
components for every entrant.

#### `hi_team` — HI team

*How well the human–Assistant team worked together (Hybrid Intelligence track)*

**Range:** [0, 1] · **Direction:** higher is better

$$
S = \frac{\sum_{i \in P} w_i\, \phi_i(x_i)}{\sum_{i \in P} w_i}
$$

The team: appropriate reliance on the Assistant (neither ignoring it harmfully nor following it
blindly), the Human's engagement and critical errors, a sound final decision and an efficient result.

| Component | What | Weight | Normalised as |
| --- | --- | --- | --- |
| `human_overrode_harmfully` | judge: harmful overrides of the Assistant | 1 | a count where lower is better: $1 / (1 + x)$ |
| `human_critical_errors` | judge: the Human's critical errors | 1 | a count where lower is better: $1 / (1 + x)$ |
| `jh_use_of_assistant` | judge: use of the Assistant | 1 | a 1–7 rating mapped to [0, 1]: $(x - 1) / 6$ |
| `jh_engagement` | judge: engagement | 0.5 | a 1–7 rating mapped to [0, 1]: $(x - 1) / 6$ |
| `always_follows` | did not blindly follow every suggestion | 0.5 | one minus a [0, 1] value where lower is better (e.g. a 0/1 flag): $1 - \min(1, \max(0, x))$ |
| `click_through` | did not click through | 0.5 | one minus a [0, 1] value where lower is better (e.g. a 0/1 flag): $1 - \min(1, \max(0, x))$ |
| `irrational_accept` | did not accept below the reservation value | 1 | one minus a [0, 1] value where lower is better (e.g. a 0/1 flag): $1 - \min(1, \max(0, x))$ |
| `welfare_optimality` | efficiency of the result | 0.5 | the value, clipped to [0, 1]: $\min(1, \max(0, x))$ |

Empty for sessions without an Assistant.

Components without a value are left out (see `hi_team_coverage`).

#### `hi_team_coverage` — HI team coverage

*Share of the weight of hi_team that had a value*

**Range:** [0, 1] · **Direction:** higher is better

$$
\frac{\sum_{i \in P} w_i}{\sum_{i} w_i}
$$

The share of the total weight of `hi_team` whose components had a value in this session: 1 when
every component was measured, lower when (for example) there was no questionnaire or no judge.
Compare scores only between sessions with similar coverage; the leaderboards use the same
components for every entrant.

#### `hi_interaction` — HI interaction

*The Assistant and the team together: the ranked score of the HI interaction board*

**Range:** [0, 1] · **Direction:** higher is better

$$
S = \frac{\sum_{i \in P} w_i\, \phi_i(x_i)}{\sum_{i \in P} w_i}
$$

The interaction board of the Hybrid Intelligence track ranks Assistants by the mean of how well they
worked as an Assistant (`hi_assistant`) and how well their teams worked (`hi_team`).

| Component | What | Weight | Normalised as |
| --- | --- | --- | --- |
| `hi_assistant` | the HI Assistant score | 1 | the value, clipped to [0, 1]: $\min(1, \max(0, x))$ |
| `hi_team` | the HI team score | 1 | the value, clipped to [0, 1]: $\min(1, \max(0, x))$ |

Empty for sessions without an Assistant.

Components without a value are left out (see `hi_interaction_coverage`).

#### `hi_interaction_coverage` — HI interaction coverage

*Share of the weight of hi_interaction that had a value*

**Range:** [0, 1] · **Direction:** higher is better

$$
\frac{\sum_{i \in P} w_i}{\sum_{i} w_i}
$$

The share of the total weight of `hi_interaction` whose components had a value in this session: 1 when
every component was measured, lower when (for example) there was no questionnaire or no judge.
Compare scores only between sessions with similar coverage; the leaderboards use the same
components for every entrant.

#### `utility` — Utility

*The Human side's advantage alone, for any session*

**Range:** [0, 1] · **Direction:** higher is better

$$
S = \frac{\sum_{i \in P} w_i\, \phi_i(x_i)}{\sum_{i \in P} w_i}
$$

The simplest score: the share of the largest possible gain over no deal that the Human side obtained,
with or without an Assistant. No deal scores 0. Every project and study has it.

| Component | What | Weight | Normalised as |
| --- | --- | --- | --- |
| `human_advantage` | the Human side's advantage | 1 | an advantage clipped to [0, 1] (no better than no deal = 0): $\min(1, \max(0, x))$ |

Components without a value are left out (see `utility_coverage`).

#### `utility_coverage` — Utility coverage

*Share of the weight of utility that had a value*

**Range:** [0, 1] · **Direction:** higher is better

$$
\frac{\sum_{i \in P} w_i}{\sum_{i} w_i}
$$

The share of the total weight of `utility` whose components had a value in this session: 1 when
every component was measured, lower when (for example) there was no questionnaire or no judge.
Compare scores only between sessions with similar coverage; the leaderboards use the same
components for every entrant.

## Comparing groups

`compare` (`hani2 replay compare`, **Compare** in the replay tool) groups evaluated recordings by a field (`opponent`, `support_agent`, `user`, `scenario`, `experiment`, …) and reports for every group and numeric column:

### `n` — n

*Recordings in the group*

**Range:** count · **Direction:** no better direction

$$
n_g = \lvert R_g \rvert
$$

The number of recordings $R_g$ in group $g$ (all of them, also those where a column is empty; the
mean of a column uses only the recordings that have a value).

### `mean` — Mean

*Mean of a column over the group*

**Range:** the column's range · **Direction:** no better direction

$$
\bar x_g = \frac{1}{\lvert R^x_g \rvert} \sum_{r \in R^x_g} x_r, \qquad R^x_g = \{r \in R_g : x_r \text{ is a number}\}
$$

The plain mean of a numeric column over the recordings of the group that have a value.

### `std` — Standard deviation

*Sample standard deviation of a column over the group*

**Range:** ≥ 0 · **Direction:** no better direction

$$
s_g = \sqrt{\frac{1}{\lvert R^x_g \rvert - 1} \sum_{r \in R^x_g} (x_r - \bar x_g)^2}
$$

The sample standard deviation (with $n - 1$); 0 when only one recording has a value.

### `balanced` — Scenario-balanced mean

*Mean of the per-scenario means*

**Range:** the column's range · **Direction:** no better direction

$$
\tilde x_g = \frac{1}{\lvert S_g \rvert} \sum_{s \in S_g} \bar x_{g,s}
$$

The mean of a column computed within each scenario $s$ played by the group first ($\bar x_{g,s}$), then
averaged over the scenarios $S_g$, so that a group that happened to play more of an easy scenario is
not favoured.

**Example.** Group A has three recordings of scenario s1 with values 0.2, 0.4 and 0.6 and one of s2
with 1.0. The mean is $2.2/4 = 0.55$; the scenario-balanced mean is $(0.4 + 1.0)/2 = 0.7$.

### `pass_hat_k` — pass^k

*Chance that k recordings of the same scenario all succeed*

**Range:** [0, 1] · **Direction:** higher is better

$$
\text{pass}^k_g = \frac{1}{\lvert S_g \rvert} \sum_{s \in S_g} \frac{\binom{c_s}{k}}{\binom{n_s}{k}}, \qquad k = 1, \dots, \min\big(5, \min_{s} n_s\big)
$$

Reliability across repeated sessions (from τ-bench, Yao et al., 2024): the probability that $k$
recordings drawn without replacement from the $n_s$ recordings of the group in scenario $s$ all
succeed, when $c_s$ of them did, averaged over the scenarios. pass^1 is the success rate; a fast drop
with $k$ shows an inconsistent Assistant or Opponent.

A recording succeeds when its success column (default `agreement`) is at least the threshold (default
1, i.e. a deal); set e.g. `--option success=human_advantage --option success_threshold=0.5`. Only
recordings with a value of the success column count. The largest $k$ is limited by the scenario with
the fewest recordings.

**Example.** 4 recordings of one scenario, 2 successful: pass^1 $= 2/4 = 0.5$,
pass^2 $= \binom{2}{2} / \binom{4}{2} = 1/6$, pass^3 $= 0$.

### `scenarios` — Scenarios

*Scenarios averaged in pass^k*

**Range:** count · **Direction:** no better direction

$$
\lvert S_g \rvert
$$

The number of scenarios whose pass^k values were averaged for the group.

## Identifier columns

Every row also carries these fields, used to group and filter:

| Column | Meaning |
| --- | --- |
| `key` | Where the recording is stored (the key used by the replay tool, or the file path) |
| `id` | The recording's id |
| `user` | The participant's user name |
| `mode` | The session mode (e.g. normal or a study) |
| `scenario` | The scenario's name (used by the scenario-balanced means and pass^k) |
| `opponent` | The Opponent agent |
| `support_agent` | The Assistant's name or class, or none when there was no Assistant |
| `support_model` | The language model the Assistant used |
| `experiment` | The experiment (study) the session belonged to |
| `started` | When the recording was made |
