# Compositional scenarios

Most scenario types tell a story and draw preferences that fit it. That gives realistic
negotiations, but it does not tell you **why** an Assistant fails: was it the number of issues, a
tight deadline, a lying opponent? *Compositional scenarios* answer that question. Each scenario is
built from a chosen level of every **difficulty factor**, checked automatically, and a set of them
is sampled so that every factor varies independently of the others. After you run an Assistant on
the set, the report shows the scores **per factor level** and ranks the factors by how much they
hurt.

```bash
hani2 compose factors                                   # the factors and their levels
hani2 compose generate -n 48 --base ./pool --seed 0     # 48 balanced, verified scenarios
hani2 compose run ./pool/Compositional --home ./runs/my-assistant --driver Assistant
hani2 compose report ./runs/my-assistant                # scores per factor
```

## The factors

| Factor | Kind | Levels (easiest first) | What it changes |
|---|---|---|---|
| `issues` | scenario | `2`, `4`, `6` | The number of negotiated issues. |
| `opposition` | scenario | `low`, `medium`, `high` | How opposed the two sides' preferences are. |
| `zopa` | scenario | `wide`, `narrow` | How many deals both sides prefer to no deal. |
| `constraint` | scenario | `none`, `hidden` | A private hard limit of the participant. |
| `deception` | episode | `honest`, `deceptive` | Whether the opponent bluffs. |
| `time_pressure` | episode | `relaxed` (40 rounds), `tight` (8 rounds) | The step limit of the negotiation. |

All scenarios share one domain: a **supply contract** between a *Buyer* (the participant) and a
*Supplier* (the opponent), with up to six issues: price, delivery time, warranty, payment terms,
quantity and late-delivery penalty. Every issue has its own range and format ("$96 per unit",
"6 weeks"). Fewer issues get more options each, so even a narrow ZOPA holds several deals.

**Number of issues.** The first 2, 4 or 6 issues of the domain.

**Opposition.** The opposition level of the two utility functions: the smallest distance from any
outcome to the ideal point $(1, 1)$. Zero means a deal that is perfect for both sides exists; about
0.7 is zero-sum. The bands are `low` $[0.05, 0.25]$, `medium` $[0.25, 0.42]$ and `high`
$[0.42, 0.75]$. It is measured on the preferences alone, ignoring reservation values, so it does not
depend on the ZOPA factor. Preferences are drawn until the level falls in its band. For each issue the
Supplier either wants the opposite of the Buyer, which creates conflict, or the same, which creates
common ground; the chance of conflict adapts during the search.

**ZOPA size.** The zone of possible agreement is the set of deals that both sides value at least as
much as no deal. Its share of all outcomes is set through the reservation values (the same quantile
of each side's utilities). `wide` is 20–50 % of all outcomes and `narrow` 1–6 %, with at least three
deals in every case.

**Hidden constraint.** The participant has a hard limit that the opponent does not know: the
opponent's favourite option on its most important issue is worth *less than no deal* to the
participant. The limit is built into the participant's utility function, so every metric accounts
for it, and it is stated in the participant's hints ("Hard limit (private)"). The opponent's ideal
deal always breaks it, so the limit always matters.

The limit is visible to anyone who reads the participant's utility values, including an Assistant
that reads them. What this factor tests, then, is whether the team keeps to the limit while the
opponent pushes for exactly that option. It does not test whether the Assistant can discover the
limit.

**Opponent honesty.** Both opponents concede slowly on the same time-based curve of their *true*
utility, reach their reservation value by their last turn, and accept by their true utility. They differ only in what they say and how they shape
their offers:

- `helpers.HonestTBNegotiator` names its real most important issue.
- `helpers.DeceptiveTBNegotiator` claims that its *least* important issue matters most. It picks
  its offers to fit that claim, calls almost every offer "our final offer" and, from 30 % of the
  time on, cites a better outside offer it does not have.

Neither uses a language model, so runs are reproducible. You can also use them as ordinary
opponents. Their class names give the factor away, so leave `show_opponent_type` off (the default)
when participants play them.

**Time pressure.** The number of rounds before the negotiation ends without a deal. The deadline is
also written in the scenario's description.

*Scenario* factors are built into the scenario files. *Episode* factors are settings of the
negotiation: they are stored in each scenario's `_info.yml` (under `composition.episode`) and applied
by `hani2 compose run`. A session's own settings take precedence over a scenario's files, so if you
serve these scenarios in a study, set the opponent and step limit there. The report reads the episode
factors from what was actually played.

## The target

Every scenario stores a **target** deal: the Nash bargaining solution over the ZOPA, restricted to
deals that respect the participant's constraint. It is the deal that maximises the product of both
sides' gains over their reservation values. The opponent would accept it, and it is the fair,
efficient benchmark for the participant's result. The main score is the **target attainment**:

$$\frac{u_h(\omega) - r_h}{u_h(\omega^\ast) - r_h}$$

Here $\omega$ is the result, $\omega^\ast$ the target and $r_h$ the participant's reservation value.
A score of 1 matches the target, 0 equals no deal, and a negative score means a deal worse than no
deal (for example one that breaks the hidden constraint). Because it is normalised by each scenario's
own target, it compares fairly across scenarios of very different difficulty, unlike raw utility.

## Verification

Each generated scenario is saved, loaded back and checked against its cell. If any check fails, the
scenario is left out of the pool and listed in the manifest. The checks are:

| Check | Passes when |
|---|---|
| `human_side` | The participant (by the normal role rules) plays the Buyer. |
| `issues` | The scenario has the level's number of issues. |
| `opposition` | The measured opposition lies in the level's band. |
| `zopa_nonempty` | The ZOPA holds at least three deals. |
| `zopa` | The ZOPA share lies in the level's band. |
| `target_reachable` | The stored target is in the ZOPA and is still its Nash point. |
| `target_reached_in_play` | A participant who offers only the target, and accepts nothing worse, gets a deal from the episode's opponent within its step limit, whichever side moves first. So a missed target is never caused by the deadline alone. |
| `constraint_bites` | With `hidden`, every deal that breaks the limit is worse than no deal, and the opponent's ideal deal breaks it. With `none`, there is no limit. |
| `episode` | The opponent class resolves and the step limit is positive. |

`hani2 compose verify <folder>` re-runs the checks on a pool (or one scenario folder) at any time.

## Generating a balanced set

```bash
hani2 compose generate -n 48 --seed 0                      # into the scenarios directory
hani2 compose generate -n 24 -f issues=2,6 -f zopa=narrow  # restrict some factors' levels
hani2 compose generate -n 288 --force                      # two copies of the full factorial
```

The full factorial has 144 cells. For `n` cells the sampler first takes whole copies of the factorial,
then picks the remaining cells (without repeats) so that every level of every factor appears about
equally often (counts differ by at most one), and so does every pair of levels of two factors.
In our checks of pools of 5 to 200 scenarios, level counts differed by at most one and pair counts
by at most four. Generation is seeded: the same seed and options always give the same pool.
`generate` refuses to write into a category that already holds scenarios, because the two sets would
mix and the result would no longer be balanced. Pass `--force` to replace them, or `--category` to
use another folder.

Scenario folders have opaque names (`0007Compositional`), because the scenario name is shown in the
browser and must not give the cell away. The cell, its code (such as
`i4-opp_high-zopa_narrow-hidden-deceptive-tight`), the measured values and the target are stored in
each scenario's `_info.yml` under `composition`. The category's `_composition.json` manifest lists
every scenario, plus any cells that could not be composed or verified.

From Python:

```python
from hani2.compositional import Cell, compose, verify, sample_cells

cell = Cell.of(issues="4", opposition="high", zopa="narrow", constraint="hidden")
scenario = compose(cell, name="hard-one", seed=1).scenario
print(verify(scenario).checks)
print(scenario.info["composition"]["target"])
```

## Running an Assistant on the set

```bash
hani2 compose run ./pool/Compositional --home ./runs/assistant-a --driver Assistant \
    --agent-class my_agent:MyAssistant --settings my_assistant_settings.json
hani2 compose run ./pool/Compositional --home ./runs/conceder --driver ConcederTBNegotiator
```

Each scenario is played in a headless session. The participant's seat is driven by the
[autopilot](autopilot.md): `--driver Assistant` lets the configured Assistant decide every turn, and
a negotiator class name plays a baseline that needs no language model. Each negotiation uses the
opponent and step limit from its scenario's episode factors and is recorded under `--home`, like any
other negotiation. `--repeats` plays each scenario several times, and `--limit` plays only the first
few scenarios. If a negotiation runs past `--timeout` seconds, the autopilot is switched off and the
negotiation is ended. It is then recorded as a no-deal, so it still counts in the report.

## The report

```bash
hani2 compose report ./runs/assistant-a
hani2 compose report ./runs/assistant-a ./runs/conceder -o report.md   # compare two runs
```

The report evaluates the recordings with the `outcome` and [`factors`](metrics.md) metrics. For each
factor level it shows the mean and standard error of the target attainment, the agreement rate, the
human advantage and the rate of constraint violations. Each factor also gets an **effect**: the mean
at its hardest level minus the mean at its easiest, with its standard error. The factors are ranked
by their effect on target attainment. The report names as *failures* only the factors whose drop is
larger than twice its standard error. A drop inside the noise is reported as such, with a hint to run
more scenarios or repeats (`--repeats`). With several run folders, each
folder gets its own section; `--by` groups by any other field of the evaluation rows.

The `factors` metric is not run by default (it is empty for other scenarios). Ask for it by name in
the [replay tool](recordings.md) or with `hani2 replay evaluate --metrics outcome,factors`, and you can group any recordings of compositional scenarios by a `factor_*`
column, including recordings of human participants.
