# Scenarios

A scenario defines what is negotiated (the issues and their values) and what each side wants (one utility function per side). HANI2 uses the negmas scenario format, adds a small info file for the participant-facing texts, and ships three scenario generators.

## Where scenarios live

HANI2 looks for scenarios in the *scenarios directory*, chosen in this order:

1. `<experiment>/scenarios` when an experiment is active and has that folder.
2. The directory in the `HANI2_SCENARIOS_BASE` environment variable.
3. `~/negmas/hani2/settings/scenarios` (`$HANI2_HOME/settings/scenarios`).

`hani2 setup` copies the three bundled sample scenarios into an `Examples` category: `settings/scenarios/Examples/Trade`, `.../Island` and `.../Grocery`. They do not shadow the `Trade`, `Island` and `Grocery` types, which are generated fresh for every round until you create a pool for them with `hani2 generate`. To present the samples, pick the `Examples` category in the scenario picker or add `Examples` to `scenario_order.txt`. `hani2 info` prints the scenarios directory in use.

## Scenario types and categories

Each folder directly inside the scenarios directory is a *scenario type* (a category). A category holds either:

- **A pool of numbered scenarios**: sub-folders such as `0000Trade/`, `0001Trade/`, ... as written by `hani2 generate`.
- **Named scenarios**: sub-folders with any names, each a scenario folder. The `Examples` category from `hani2 setup` looks like this (`Examples/Trade/`, `Examples/Island/`, `Examples/Grocery/`).
- **One scenario**: the category folder is itself a scenario folder.

Sub-folders are sorted by name and used in that order. When a category has scenario sub-folders, HANI2 uses them and ignores any scenario files at the category level.

A folder counts as a scenario folder when it contains at least one `.yml` or `.yaml` file whose name does not start with `_`. Folders whose names start with `.` or `_` are skipped.

The list of types HANI2 offers is the order in `scenario_order.txt`, then the built-in generators `Trade`, `Island` and `Grocery`, then any other category folder in the scenarios directory.

### Which scenario a participant gets

Each participant has a counter in `<results>/<user>/last_scenario.txt` that goes up by one on every load. The counter picks the slot in the pool and wraps around, so with a pool of 50 the 51st load reuses slot 0.

The type is chosen by the counter too:

- With *Follow the scenario order* on (the default), the counter walks through `scenario_order.txt`: the first load uses the first line, the second load the second line, and so on, wrapping around.
- With it off, every load picks a random type from `scenario_order.txt`.

Admins, and participants when an admin turns on *Participants may choose the scenario*, can pick a type and a named scenario on the start screen instead.

With *Use saved scenario pools* off, HANI2 ignores the pool and generates a fresh scenario on every load (only for `Trade`, `Island` and `Grocery`). The guest playground (`/play` without a Prolific ID) works this way by default: it generates a fresh scenario of a random type each time. Add `?load_existing=1` to the playground URL to use the pools instead.

If a pool scenario fails to load, HANI2 generates one instead when the type has a generator (the admin setting `generate_on_failure`, on by default). A type with no pool and no generator falls back to the bundled sample of the same name, if there is one.

The [Prolific](prolific.md) study has its own rules for the type and slot.

### `scenario_order.txt`

A plain text file with one scenario type per line. Blank lines and lines starting with `#` are ignored. The bundled default is:

```text
Trade
Island
Grocery
```

It is looked up like every other settings file: the active experiment first, then the settings folder, then the bundled default (see [Configuration reference](configuration.md)). Admins can edit it under *Texts* in the admin console.

## The on-disk format

A scenario folder contains:

| File | Content |
|------|---------|
| `<Name>.yml` | The outcome space: the issues and their values (negmas format). |
| One `.yml` per side | A utility function in negmas format, with a `name` (the role) and an optional `reserved_value`. |
| `_info.yaml` | Texts for the participant (optional). `_info.yml` and `_info.yaml.yml` also work. |
| `display.py` | How to write an offer as text (optional). |
| `inverter_h<i>.pkl` | A cached utility inverse (optional, written by `hani2 generate`). |

The bundled `Trade` sample (installed as `Examples/Trade`) looks like this:

```text
Trade/
├── Trade.yml        # issues: Quantity (1–10), Price (100, 110, 120, 200)
├── Buyer.yml        # the buyer's utility function
├── Seller.yml       # the seller's utility function
├── _info.yaml
└── display.py
```

```yaml title="Trade.yml"
issues:
- name: Quantity
  type: ContiguousIssue
  values:
  - 1
  - 10
- name: Price
  type: DiscreteCardinalIssue
  values:
  - 100
  - 110
  - 120
  - 200
name: Trade
type: EnumerableCartesianOutcomeSpace
```

```yaml title="Buyer.yml"
name: buyer
reserved_value: 0.0
type: LinearAdditiveUtilityFunction
values:
- type: TableFun
  mapping: {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.5, 6: 1.0, 7: 0.8, 8: 0.6, 9: 0.4, 10: 0.2}
- type: TableFun
  mapping: {100: 1.0, 110: 0.8, 120: 0.4, 200: 0.0}
weights: [0.25, 0.75]
```

Any outcome space and utility function type that negmas can load works. HANI2 renders each issue in the counter-offer editor according to its type:

- Integer ranges with at most 31 values and discrete issues become a choice of values.
- Wider integer ranges and continuous issues become numeric inputs with a minimum and maximum.

### Which side the participant plays

The utility functions are numbered in the order negmas loads them. The participant takes index `human_index` (an admin setting, default `1`) and the opponent takes the other one. The utility function's `name` is the participant's *role*: the interface shows "You act as <role>", and the role selects role-specific texts in `_info.yaml`.

The `reserved_value` is the participant's *value on disagreement*: the utility they get when the negotiation ends without a deal. The utility gauge marks it with a tick, and offers below it are flagged in the history.

### `_info.yaml`

All fields are optional.

| Field | Used for |
|-------|----------|
| `title` | The scenario title on the start screen and in the *Scenario Info* tool. Defaults to the outcome space name. |
| `short_description` | A Markdown paragraph shown in the *Scenario Info* tool. |
| `long_description` | Longer Markdown text, shown as a collapsed *Full description* card in the *Scenario Info* tool. |
| `issue_description` | A description per issue, shown under the issue in the counter-offer editor and in the *Scenario Info* table. Either a mapping `issue: text`, or a mapping `role: {issue: text}` for role-specific descriptions. |
| `hints` | A mapping `role: {label: value}`, shown as a *Hints* list in the *Scenario Info* tool for the participant's role only. |
| `n_issue_columns` | The number of columns in the counter-offer editor (default `2`). |

The keys of `hints` and of role-specific `issue_description` must match the utility function `name` exactly, including case.

```yaml title="_info.yaml"
title: Simple Trading Scenario
n_issue_columns: 2
issue_description:
  Quantity: The quantity to be traded
  Price: The unit price to trade at
hints:
  seller:
    Target Quantity: 5
  buyer:
    Target Quantity: 6
short_description: >-
  You trade with an agent. Each side has a target quantity and a value for money.
long_description: |
  **The domain** A buyer and a seller negotiate the quantity and the price of one trade.
```

### `display.py`

By default an offer is written as `Issue: value, Issue: value`. To write offers in domain language, add a `display.py` that defines a subclass of `hani2.display.DefaultOutcomeDisplay`:

```python title="display.py"
from negmas import Outcome, Scenario

from hani2.display import DefaultOutcomeDisplay


class TradeOutcomeDisplay(DefaultOutcomeDisplay):
    def str(self, outcome: Outcome | None, scenario: Scenario, is_done: bool, from_human: bool) -> str:
        if outcome is None:
            return super().str(outcome, scenario, is_done, from_human)
        return f"{outcome[0]} items at {outcome[1]}$"
```

`str()` receives the outcome as a tuple in issue order, the scenario, whether the negotiation is over (`is_done`) and whether the offer came from the participant (`from_human`). You can also override `table()`, which returns a list of row dictionaries.

HANI2 uses the first subclass it finds in the file. A scenario's own `display.py` always wins. Scenarios without one whose outcome-space name starts with `Trade`, `Island` or `Grocery` use the built-in display for that type.

## Built-in generators

HANI2 can generate random scenarios of three types:

| Type | What is negotiated |
|------|--------------------|
| `Trade` | A buyer and a seller agree on a quantity and a unit price. Each side has a target quantity, penalties for buying or selling too little or too much, and a non-linear value for money. |
| `Island` | Two people stranded on an island divide a set of survival items. |
| `Grocery` | Two people who bought fruit together divide it between them. |

Generated scenarios come with their own `_info` texts and hints, and every call draws new random preferences.

## Generating a pool with `hani2 generate`

Pools make a study reproducible: every participant who reaches slot 7 of `Trade` gets the same scenario. `hani2 generate` writes them into the scenarios directory of the settings folder, or of the active experiment:

```bash
hani2 generate                           # 50 scenarios of every type
hani2 generate --type Trade -n 20        # 20 Trade scenarios
HANI2_EXPERIMENT=pilot hani2 generate    # into experiments/pilot/scenarios
hani2 generate --base ./my-pool          # anywhere else
```

Each slot is written to `<base>/<Type>/<NNNN><Type>/` (for example `Trade/0007Trade/`).

| Option | Default | Meaning |
|--------|---------|---------|
| `--type`, `-t` | all types | A type to generate (`Trade`, `Island` or `Grocery`). Repeat the option for several types. |
| `--count`, `-n` | `50` | Scenarios per type. |
| `--base` | the scenarios directory | Where to write the pool. |
| `--human-index` | `1` | The participant's utility function index (used for the reservation values and the cached inverse). |
| `--cache-inverter / --no-cache-inverter` | on | Save a utility inverse next to each scenario. |
| `--rebuild-inverses` | off | Do not generate anything; only rewrite the cached inverse of every existing slot. |
| `--min-opposition` | `0.35` | Reject scenarios whose opposition level is below this value. |
| `--max-opposition` | `0.90` | Reject scenarios whose opposition level is above this value. |
| `--set-reservations / --no-set-reservations` | on | Replace the generator's reservation values with small random ones. |
| `--user-reserved-max` | `0.10` | Largest reservation value for the participant (on the normalized 0–1 scale). |
| `--agent-reserved-max` | `0.20` | Largest reservation value for the opponent. |
| `--max-tries` | `60` | How many scenarios to draw per slot to hit the opposition band. |
| `--seed` | `0` | Random seed for the reservation values. |
| `--force` | off | Overwrite slots that already exist. |

The opposition level measures how much the two sides' preferences conflict. Near 0 there is an outcome that is good for both, so there is little to negotiate. The default band keeps real but not hopeless conflict in every slot. If no draw falls in the band after `--max-tries` attempts, that slot is reported as an error and skipped.

Generation is idempotent: a slot that already has its scenario file (and its inverse, when caching) is skipped unless you pass `--force`. You can run the command again to fill gaps.

Without `--base`, the pool is written where the server reads scenarios: the experiment's `scenarios/` folder, else `HANI2_SCENARIOS_BASE`, else `settings/scenarios`.

### Cached inverters

The *Utility-based Selector* tool lists every outcome whose utility lies in a range the participant chooses. To do that it needs the inverse of the participant's utility function, which can take a moment to compute for large outcome spaces.

With `--cache-inverter`, `hani2 generate` computes that inverse once and saves it as `inverter_h<human_index>.pkl` in the slot folder. The tool loads the file when it exists, checks it against the live utility function on a sample of outcomes, and recomputes when they differ or the file cannot be read. A missing or stale file is therefore always safe; it only costs time. Use `hani2 generate --rebuild-inverses` to refresh all cached inverses after you change `--human-index` or edit the utility files.

The inverse is cached for one human index only. If you change the `human_index` admin setting, regenerate the inverses with the matching `--human-index`.
