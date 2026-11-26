# Ablations

How good is an Assistant? Its team's score alone does not say: a strong score may come from an easy
set of scenarios, from the human, or from information the Assistant should not have had. HANI2
runs the same scenarios and opponents under a few **conditions** and reports the gaps between
them. Each gap isolates one thing.

| Condition | Who negotiates | What it measures |
| --- | --- | --- |
| `human_alone` | A human, no Assistant | The baseline: what people manage by themselves. |
| `team` | A human with the Assistant | What the study is about. |
| `no_human` | The Assistant alone, on [autopilot](autopilot.md) | The Assistant's **negotiation ceiling**. |
| `oracle_no_human` / `oracle_team` | As above, and the Assistant knows the opponent's utility function | The **information ceiling**. |

The gaps, all on the human's side of the deal (`human_advantage` by default):

| Gap | Definition | Reads as |
| --- | --- | --- |
| `added_value` | team − human_alone | What the Assistant adds to a human: the **added-value score**. |
| `through_human_loss` | no_human − team | What the Assistant loses by working through a human. Large: it negotiates well but does not get its advice across. |
| `autopilot_vs_human` | no_human − human_alone | The Assistant alone against a human alone. |
| `information_gain` | oracle_no_human − no_human | What knowing the opponent's preferences is worth. Large: the Assistant's opponent modelling has room to improve. |
| `oracle_team_gain` | oracle_team − team | The same, for a team. |

## Matched cells

Gaps are computed **cell by cell**. A cell is a scenario × opponent × human side combination (you can choose the
fields). Within every cell and condition the values are averaged. The gap is A − B in every cell
played in both conditions, averaged over those cells:

$$\text{gap}_{A-B} = \frac{1}{\lvert K \rvert} \sum_{k \in K} \left(\bar v_{A,k} - \bar v_{B,k}\right)$$

Pooled means are never subtracted. If the team happened to play the easy scenarios more often than
the humans alone, pooling would credit the Assistant for the scenarios. The report shows how many
cells were matched and how many were played in only one condition.

A negotiation that ends without a deal counts with its value (advantage 0). It is not dropped.

## Running the conditions

**Team and human alone: one study with a control group.** Add the pool member `none` to the
study's Assistants. With the default `balanced` scheduling, half the participants get the Assistant
and half negotiate without one, on the same scenarios and opponents:

```yaml
# projects/HI/studies/s1/study.yaml
type: prolific
assistants: ["team_x.agent:TeamX", "none"]
```

Several Assistants can share one control group: `assistants: [":finalists", "none"]`. With
`--by assistant` the report then gives each Assistant its own added-value score against that shared
baseline, and each of its other gaps against itself (its own autopilot runs against its own teams).
A separate no-Assistant study (`hani2 experiment create --no-assistant`) records its sessions as
`assistant_off`; `--off-is-control` counts them as the human-alone baseline. A participant who switches their Assistant off still counts as `team`: the condition is what
was assigned, not what was used.

**No-Human: the Assistant on autopilot.** No participants are needed. Run it on the cells your
participants played, so that every cell can be matched:

```bash
hani2 ablation run --like ~/negmas/hani2/results/HI --reps 3
hani2 ablation run --scenario-types Trade,Jobs --opponents BoulwareTBNegotiator,ConcederTBNegotiator --reps 5
```

`--like PATH` takes the cells (scenario, opponent and the human's side) of the team and human-alone
recordings under `PATH`. Without it, every scenario type × opponent is run. The Assistants are the
study's pool without `none` (`--assistants pkg.mod:A,pkg.mod:B` to choose), each on every cell.

Each negotiation is recorded under the user `ablation_autopilot` in the current study (`--study
project/study` for another). These runs are **not participants**: they take no participant index and
no Assistant slot, the study's scheduling does not pick their opponent or scenario, and they are
never practice rounds. Autopilot is allowed for these runs only: `autopilot_settings.json` is not
changed. If the autopilot gives up (its stall safety net) or the time runs out, the negotiation is
ended and counts as **no deal**. Dropping it would flatter the Assistant. The same is available in
Python:

```python
from hani2.ablation import cells_of, run_no_human

runs = run_no_human(cells=cells_of(["~/negmas/hani2/results/HI"]), reps=3)
```

**Oracle: the Assistant knows the opponent.** Add `--oracle` to `hani2 ablation run`, or grant the
`opponent_utility` capability in a study's `assistant_settings.json` to run an oracle team:

```json
{"capabilities": {"opponent_utility": true}}
```

The capability is off by default and admin-only: the participant neither sees it nor can switch it.
With it, the Assistant's view of the negotiation has an `opponent` entry: the opponent's issue weights
and option values (or its best outcomes), its reserved value, and its utility of the offer on the table,
the draft and the recent history. It also gets the `get_opponent_utility` function to score any offer
for both sides (see [the capabilities](assistant.md#capabilities)).

## The report

```bash
hani2 ablation report                           # every recording in the results folder
hani2 ablation report results/HI --by assistant # one added-value score per Assistant
hani2 ablation report --value agreement --cell scenario,opponent --cells
```

The report first lists the conditions found, with the number of negotiations, cells and the mean.
Then it gives every gap with its value, its standard error over cells, the number of matched cells,
the negotiations on each side and the two cell-matched means. `--cells` prints every cell, and
`--out report.json` writes everything. Practice rounds are left out (`--practice` keeps them). So
are sessions whose tools showed the opponent's utilities (admins, or env.json
`tools.show_opponent_utility`), since those people knew more than their condition says
(`--opponent-info` keeps them).

In Python, use `hani2.evaluation.ablation_report(rows, value=..., cell=..., by=...)` on the rows of
`evaluate_paths`.

## How a condition is recorded

When a negotiation starts, its recording stores the condition: whether an Assistant ran (`on`), the
session was assigned the no-Assistant arm (`none`), the Assistant was switched off in the settings
(`off`) or failed to start (`error`). It also stores whether the Assistant had the oracle, whether
the tools could show the opponent's utilities, and the autopilot driver. Every time autopilot is
switched on or off, the recording also notes which driver it used. The
[`condition` metric](metrics.md#condition-condition-ablations) combines these with who took each
action on the human's seat:

* every action by autopilot, driven by the Assistant: `no_human` (`oracle_no_human`);
* every action by autopilot, driven by a negotiator: `negotiator_autopilot`;
* some actions by autopilot: `mixed`, which is in no gap;
* otherwise `team` (`oracle_team`), `human_alone`, `assistant_off` or `assistant_error`.

The same fields are in `results.csv` (`assistant_condition`, `oracle`, `opponent_info_tools`,
`autopilot_driver`; see [Study management](study-management.md#resultscsv-columns)). Recordings made
before conditions were recorded are `unknown` and are left out of every gap.
