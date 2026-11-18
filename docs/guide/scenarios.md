# Scenarios

A scenario defines what is negotiated (the issues and their values) and what each side wants (one utility function per side). HANI2 uses the negmas scenario format, adds a small info file for the participant-facing texts, and ships generators for 19 scenario types, grouped into [scenario sets](scenario-sets.md).

## Where scenarios live

HANI2 looks for scenarios in the *scenarios directory*, chosen in this order:

1. `<study>/scenarios` when a study (or experiment) is active and has that folder.
2. The directory in the `HANI2_SCENARIOS_BASE` environment variable.
3. `projects/<project>/scenarios` when the study's project has that folder.
4. `~/negmas/hani2/settings/scenarios` (`$HANI2_HOME/settings/scenarios`).

A category is looked up by name, first hit wins: the scenarios directory above, then a link in
`scenario_links.yaml` (study, then project, then settings folder), then the other scenarios
folders (the study's, the project's, the settings'). So a project or study with its own
`scenarios/` folder still serves the categories of the settings folder that it does not have.

Add scenarios with the [library](library.md): `hani2 library add scenarios Rentals.zip` copies a
zip of scenario folders into the chosen layer's `scenarios/` folder (after checking every
scenario), and `--link` records a folder that stays where it is:

```yaml title="scenario_links.yaml"
links:
  Rentals: /data/scenarios/rentals      # a category or one scenario folder
```

A new type's name must not equal or start like a registered scenario type (`TradeExtra`), which
would show it with that type's display.

`hani2 setup` copies the three bundled sample scenarios into an `Examples` category: `settings/scenarios/Examples/Trade`, `.../Island` and `.../Grocery`. They do not shadow the `Trade`, `Island` and `Grocery` types, which are generated fresh for every round until you create a pool for them with `hani2 generate`. To present the samples, pick the `Examples` category in the scenario picker or add `Examples` to a scenario set. `hani2 info` prints the scenarios directory in use.

## Scenario types and categories

Each folder directly inside the scenarios directory is a *scenario type* (a category). A category holds either:

- **A pool of numbered scenarios**: sub-folders such as `0000Trade/`, `0001Trade/`, ... as written by `hani2 generate`.
- **Named scenarios**: sub-folders with any names, each a scenario folder. The `Examples` category from `hani2 setup` looks like this (`Examples/Trade/`, `Examples/Island/`, `Examples/Grocery/`).
- **One scenario**: the category folder is itself a scenario folder.

Sub-folders are sorted by name and used in that order. When a category has scenario sub-folders, HANI2 uses them and ignores any scenario files at the category level.

A folder counts as a scenario folder when it contains at least one `.yml` or `.yaml` file whose name does not start with `_`. Folders whose names start with `.` or `_` are skipped.

The list of types HANI2 offers is the active [scenario set](#scenario-sets) in order, then the other registered generators, then any other category folder in the scenarios folders and the linked categories.

### Which scenario a participant gets

Each participant has a counter in `<results>/<user>/last_scenario.txt` that goes up by one on every load. The counter picks the slot in the pool and wraps around, so with a pool of 50 the 51st load reuses slot 0.

The type is chosen by the counter too:

- With *Follow the scenario order* on (the default), the counter walks through the active scenario set: the first load uses its first type, the second load the second type, and so on, wrapping around.
- With it off, every load picks a random type from the active scenario set.

Admins, and participants when an admin turns on *Participants may choose the scenario*, can pick a type and a named scenario on the start screen instead.

With *Use saved scenario pools* off, HANI2 ignores the pool and generates a fresh scenario on every load (for types that have a generator). The guest playground (`/play` without a Prolific ID) works this way by default: it generates a fresh scenario of a random type each time. Add `?load_existing=1` to the playground URL to use the pools instead.

If a pool scenario fails to load, HANI2 generates one instead when the type has a generator (the admin setting `generate_on_failure`, on by default). A type with no pool and no generator falls back to the bundled sample of the same name, if there is one.

The [Prolific](prolific.md) study has its own rules for the type and slot.

## Scenario sets

A *scenario set* is a named, ordered list of scenario types. The active set decides which types participants get and in which order. HANI2 ships these sets (see [Scenario sets](scenario-sets.md) for every scenario in them):

| Set | Scenario types |
|-----|----------------|
| `HAN2026` (default) | Trade, Island, Grocery |
| `MIT2025` | Furniture, Lease, Consulting |
| `PieArena2026` | JobOffer, License, HomeRepair |
| `ANL` | Supply, Acquisition, Chores, Energy, HealthFund, UsedCar, CityTrip, LaborContract, Grocery, Trade, JobOffer, Lease |
| `ANL2010` … `ANL2026` | One set per ANL year whose domains are available: `ANL2010`, `ANL2011`, `ANL2012`, `ANL2013`, `ANL2025` and `ANL2026`. |
| `IAGO` | Resources, Estate, Grocery |
| `HAN2027` | Lease, Supply, Acquisition, License, Chores, Energy, Estate, CityTrip |
| `HI2027` | `HAN2027` (a set made of a set) |
| `ANAC2027` | `HAN2027` + `HI2027` (the same eight types; duplicates are dropped) |
| `Custom` | The types listed in `scenario_order.txt`. |

The active set is chosen by, first hit wins:

1. The admin's session setting: *Scenario set* in the settings drawer, or the set picker on the start screen (admins only).
2. The `HANI2_SCENARIO_SET` environment variable, which `hani2 --scenario-set NAME` sets.
3. `env.json` → `negotiation` → `scenario_set`.
4. `Custom`, when `scenario_order.txt` was changed from the bundled default.
5. The `default` of `scenario_sets.yaml` (`HAN2026`).

!!! note "For contributors"
    The [Scenario sets](scenario-sets.md) page is generated from the registered scenario types and the bundled sets. Regenerate it whenever a scenario text (title, descriptions, roles, issues) or a bundled set changes:

    ```bash
    .venv/bin/python scripts/make_scenario_catalog.py docs/guide/scenario-sets.md
    ```

Set names are matched without regard to case (`anac2027` works). `hani2 sets` lists the sets, marks the active one and flags any type that has neither a generator nor a folder.

### `scenario_sets.yaml`

Sets are defined in `scenario_sets.yaml`. It is looked up like every other settings file: the bundled default, then the settings folder, then the active experiment. Sets in a later file are added, and a set with the same name as an earlier one replaces it. Admins can edit the file under *Texts* → *Scenario sets* in the admin console. A file that does not parse is ignored with a warning.

```yaml title="scenario_sets.yaml"
default: HAN2026
sets:
  HAN2026: [Trade, Island, Grocery]
  Pilot: [Lease, Examples, Trade]   # a type can be a generator or any category folder
  Everything: [HAN2026, Pilot, "@ANAC2027", Energy]   # sets made of sets
```

A set can list other sets as well as scenario types. Write `@Name` to always mean the set `Name`, or just the name: an entry that names a set (in any case) is that set, otherwise it is a scenario type. A set's types are inserted where it is listed, and each type is kept only at its first occurrence, so `Everything` above is Trade, Island, Grocery, Lease, Examples, then the ANAC2027 types not seen yet, then Energy if it was not already there. A cycle (a set that includes itself) is reported and broken. `hani2 sets` shows what each composed set is made of. Opponent, Assistant and tool groups follow the same rule (see [Groups and composition](library.md#groups-and-composition)); `hani2 library group-set scenarios NAME ENTRY...` writes a set into the settings, project or study file.

### `scenario_order.txt`

A plain text file with one scenario type per line; blank lines and lines starting with `#` are ignored. It defines the `Custom` set. A changed `scenario_order.txt` becomes the active set when no set is chosen explicitly, so setups made before scenario sets existed keep working. Admins can edit it under *Texts* → *Custom order*.

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

The utility function's `name` is a *role*: the participant plays one role and the opponent the other. The interface shows "You act as <role>", and the role selects role-specific texts in `_info.yaml`. Which role the participant gets is decided by the admin setting *Participant's role* (`role_rule`, also settable in `env.json` → `negotiation`):

| Rule | The participant plays |
|------|-----------------------|
| `auto` (default) | The scenario's suggested role (`human_role` in `_info.yaml`), else the utility function at index `human_index` (default `1`). |
| `index` | The utility function at index `human_index`. |
| `roles` | The first role in the admin setting *Preferred roles* (`human_roles`, e.g. `["Tenant", "Buyer"]`) that the scenario has, else as `auto`. |
| `alternate` | The roles in turn, one negotiation after the other. |
| `random` | A random role for each negotiation. |

A role named `human` always goes to the participant, whatever the rule: such scenarios are written from the participant's point of view (issue values like `human`/`agent` and "you get …" texts refer to that role). To let participants play either side of your own scenario, name the roles after the story (`Buyer`/`Seller`) instead.

negmas loads the utility functions sorted by name, so index `0` is the role that comes first alphabetically.

The `reserved_value` is the participant's *value on disagreement*: the utility they get when the negotiation ends without a deal. The utility gauge marks it with a tick, and offers below it are flagged in the history.

### `_info.yaml`

All fields are optional. negmas writes the file as `_info.yml`; `_info.yaml` and `_info.yaml.yml` are read too.

| Field | Used for |
|-------|----------|
| `title` | The scenario title on the start screen and in the *Scenario Info* tool. Defaults to the outcome space name. |
| `short_description` | A Markdown paragraph shown in the *Scenario Info* tool. |
| `long_description` | Longer Markdown text, shown as a collapsed *Full description* card in the *Scenario Info* tool. |
| `issue_description` | A description per issue, shown under the issue in the counter-offer editor and in the *Scenario Info* table. Either a mapping `issue: text`, or a mapping `role: {issue: text}` for role-specific descriptions. |
| `hints` | A mapping `role: {label: value}`, shown as a *Hints* list in the *Scenario Info* tool for the participant's role only. |
| `n_issue_columns` | The number of columns in the counter-offer editor (default `2`). |
| `human_role` | The role a participant plays by default (see [Which side the participant plays](#which-side-the-participant-plays)). |
| `issue_format` | A Python format string per issue for writing values in offers, e.g. `Rent: "${:,}/month"` turns `3400` into `$3,400/month`. Used by the built-in story display. |
| `split` | For item splits: `units` (issue → `[singular, plural]`) and `totals` (issue → number of items). Issue values are then how many items the `human` role gets, and offers read "You get 2 clocks; your opponent gets 1 clock". |
| `story` | The scenario type that generated the scenario (set by the generators). |
| `role_descriptions` | A one-line description per role (`role: text`). Written by the generators for reference; the participant reads the roles in `long_description` and in the *Your role* hint. |

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

HANI2 uses the first subclass it finds in the file. A scenario's own `display.py` always wins. Scenarios without one whose outcome-space name is (or starts with) a registered scenario type use that type's display; scenarios with an `issue_format` or `story` entry in their info use the story display, which formats values with `issue_format`.

## Built-in generators

HANI2 can generate random scenarios of 19 types. Every type is two things:

- a **template folder** in the [on-disk format](#the-on-disk-format) (`hani2/sample_scenarios/Default/<Type>/`, copied to `<settings>/scenarios/Examples/<Type>/` by `hani2 setup`). It is a complete scenario you can play as it is, and it holds everything a participant reads: the title, the descriptions, the issues and their options, issue descriptions and formats, the roles and their hints. The built-in generators read the folder inside the installed package, so editing the `Examples` copy changes that one scenario, not the generator. To change what a generator produces, copy the template, edit it and register it as your own type with [`Story.from_folder`](#writing-your-own-scenario-type).
- a **generator**, a few lines of Python per role that draw new preferences, for variations of the template.

Each type has a fixed story: the same title, descriptions, issues and roles every time. Every call draws new utility functions (issue weights and value curves) and the hints that come from them (the most and least important issues, the ideal deal, and drawn facts such as an estimate or a power need), and redraws until the opposition level lies in the type's band, so even scenarios generated on the fly have real but not hopeless conflict.

| Type | What is negotiated | Sets |
|------|--------------------|------|
| `Trade` | A quantity and a unit price between a buyer and a seller with target quantities. | HAN2026, ANL |
| `Island` | Who gets each of eight survival items. | HAN2026 |
| `Grocery` | How four kinds of fruit bought together are split. | HAN2026, ANL, IAGO |
| `Furniture` | The price, pickup and payment of a used armchair. | MIT2025 |
| `Lease` | Rent, deposit, move-in date and lease length of an apartment. | MIT2025, ANL, ANAC2027 |
| `Consulting` | Fee, expense budget, travel and invoicing of a summer consulting contract. | MIT2025 |
| `JobOffer` | Salary, signing bonus, start date, location and vacation days. | PieArena2026, ANL |
| `License` | Upfront payment, approval payment, royalty and exclusivity of a device license. | PieArena2026, ANAC2027 |
| `HomeRepair` | Price, start, warranty and cleanup of a roof repair. | PieArena2026 |
| `Supply` | Unit price, delivery, payment terms and returns of a parts supply contract. | ANL, ANAC2027 |
| `Acquisition` | Price, IP, founders' equity and roles, staff terms and liability of a startup sale. | ANL, ANAC2027 |
| `Chores` | Who does each of five chores (one flatmate, shared, or paid help). | ANL, ANAC2027 |
| `Energy` | Power reserved in four blocks of a day and the price per kWh. | ANL, ANAC2027 |
| `HealthFund` | A tobacco-control fund and the aid and trade terms between two countries. | ANL |
| `UsedCar` | The price and four extras of a used car. | ANL |
| `CityTrip` | Activity, start day, length, transport and food of a weekend visit. | ANL, ANAC2027 |
| `LaborContract` | Pay, vacation, patrols, sergeants and the review board of a police contract. | ANL |
| `Resources` | How five items each of four goods are split. | IAGO |
| `Estate` | How four piles of different sizes are split between two heirs. | IAGO, ANAC2027 |

## Writing a scenario by hand

You do not need any code to write a scenario. Start from a template, edit the YAML files, and check the folder:

```bash
hani2 scenario new License ~/my-scenarios/HearingAid/Base   # copy the License template
# ... edit HearingAid/Base/_info.yaml, License.yml, Firm.yml, Inventor.yml ...
hani2 scenario check ~/my-scenarios/HearingAid               # validate every scenario in a folder
hani2 --scenarios ~/my-scenarios --scenario-set Pilot        # run with them
```

with `Pilot: [HearingAid]` in `scenario_sets.yaml`. `hani2 scenario new TYPE DEST --generate --seed N` writes a fresh draw of the type's generator instead of the template. A hand-written folder without Python is a fixed scenario: it is served exactly as written, never varied. Several hand-written scenarios in one category folder (`HearingAid/Base`, `HearingAid/Hard`, …) are served in turn, like a pool. To get variations, add a generator (next section).

`hani2 scenario check` takes scenario folders, categories or whole scenario directories (a generated pool too). For every scenario it:

- loads it and reports what stops it from being served (no outcome space, fewer than two utility functions, two info files, a `human_role` that is not a role, an offer that cannot be shown);
- saves it to a temporary folder, loads it back and reports any difference in the issues, options, roles, utilities, reservation values or info, so you know the files will load exactly as written;
- warns about what the participant would miss: no title or descriptions, issues without a description, roles without hints, hints for roles or issues that do not exist (the names must match exactly, including case), utilities outside 0–1;
- prints the roles, the number of outcomes and the opposition level.

`--fill-hints` adds the hints HANI2 can compute from the utility functions (*Most important issue*, *Least important issue*, *Your ideal deal*) where they are missing, and keeps the hints you wrote.

## Writing your own scenario type

A scenario type is a *generator*: a function `maker(index) -> negmas.Scenario` that HANI2 calls for every fresh scenario, registered under a type name. The easiest way to write one is a `Story` (from `hani2.scenarios.story`) read from a scenario folder, the way the built-in types are made: the folder holds the scenario (texts, issues, roles), and Python only draws each role's preferences.

```text
scenario_types/
├── shirt.py
└── Shirt/            # a scenario folder: hani2 scenario new Furniture Shirt, then edit
    ├── Shirt.yml     # issues: Price (20, 25, 30, 35, 40), Size (S, M, L, XL)
    ├── Buyer.yml
    ├── Seller.yml
    └── _info.yaml    # title, descriptions, issue_format, role_descriptions, hints
```

```python title="shirt.py"
from pathlib import Path

from hani2.scenarios.story import Side, Story, down, peak, up, weights

PRICES = [20, 25, 30, 35, 40]
SIZES = ["S", "M", "L", "XL"]


def buyer(rng, ctx):
    # The buyer wants a low price and has a size that fits best.
    return Side(
        values={"Price": down(PRICES, rng), "Size": peak(SIZES, rng.randrange(len(SIZES)), rng)},
        weights=weights(rng, Price=(2, 4), Size=(1, 3)),
    )


def seller(rng, ctx):
    # The seller wants a high price and has too many of the large sizes in stock.
    return Side(
        values={"Price": up(PRICES, rng), "Size": up(SIZES, rng)},
        weights=weights(rng, Price=(3, 5), Size=(0.5, 1.5)),
    )


SHIRT = Story.from_folder(Path(__file__).with_name("Shirt"), roles={"Buyer": buyer, "Seller": seller})
STORIES = [SHIRT]
```

`Story.from_folder(folder, roles, setup=..., band=..., reserved=..., max_tries=...)` reads the issues and their options from `<Type>.yml`, the roles from the utility files (`roles` must give a function for each of them), and every text from `_info.yaml`. A bare name (`Story.from_folder("License", ...)`) is one of the bundled templates. In each generated scenario:

- the utility functions and reservation values are new draws;
- the computed hints (*Most important issue*, *Least important issue*, *Your ideal deal*) and the role function's `Side.hints` are rewritten;
- everything else in `_info.yaml` is kept as written, including hints you wrote yourself, such as *Your role*.

The template's own utility functions are not used by the generator; they make the folder a playable scenario and a worked example. A role function must score every option listed in `<Type>.yml`; if you add an option to the YAML and not to the function, generation stops with an error naming the issue and the option.

You can also write the texts in Python and skip the folder:

```python title="shirt.py"
from hani2.scenarios.story import Issue, Story

SHIRT = Story(  # buyer() and seller() as above
    type="Shirt",
    title="Shirt Sale",
    short_description="In this scenario, a buyer and a seller negotiate the price and the size of a shirt.",
    long_description="**The Domain** There are two issues: the price of the shirt and its size.",
    roles={"Buyer": buyer, "Seller": seller},
    role_descriptions={"Buyer": "the person buying the shirt", "Seller": "the shop selling it"},
    issues=[
        Issue("Price", PRICES, "The price of the shirt", fmt="${}"),
        Issue("Size", SIZES, "The size of the shirt"),
    ],
    disagreement="Without a deal the buyer shops elsewhere.",
    human_role="Buyer",
)

STORIES = [SHIRT]
```

- `values` gives a score to every option of every issue on any scale (each issue is rescaled to 0–1), and `weights` gives every issue an importance (normalized to sum to 1). The helpers `up`, `down`, `peak`, `scores`, `taste` and `weights` draw typical curves with random shapes.
- `setup(rng)` may draw hidden facts both roles see through `ctx` (for example two different estimates of the same chance). `Side.hints` adds facts to that role's hints.
- `band` (default `(0.35, 0.90)`) is the opposition range draws must hit, and `reserved` the range of reservation values.
- The roles are stored in alphabetical order, the same order negmas loads them in, so a saved scenario reloads unchanged.
- The long description gets the standard *Roles*, *Utility Function*, *Opponent Utility Function* and *Value on Disagreement* paragraphs.
- `hani2 scenario new Shirt Shirt/ --generate` (with the file registered) writes a draw as a folder, so you can move a story written in Python to `Story.from_folder` later.

### Registering it

HANI2 imports scenario-type files from:

- every `*.py` file in `<settings>/scenario_types/` (and `<experiment>/scenario_types/` when an experiment is active), and
- the files or modules listed in `HANI2_SCENARIO_TYPES` (comma-separated), which `hani2 --scenario-types path/to/shirt.py` sets.

A file registers its types with a module-level `STORIES` list, a `SCENARIO_TYPES` dict `{name: maker}` for plain maker functions, or calls to `hani2.scenarios.registry.register(name, maker, display)` / `register_story(story)`. Name the outcome space of your scenarios after the type, so saved scenarios find their display again. A file that fails to import is reported and skipped.

Then add the type to a set in `scenario_sets.yaml`, and generate a pool if you want one:

```bash
hani2 --scenario-types shirt.py --scenario-set Pilot   # run with it
hani2 sets                                            # check that every type is found
HANI2_SCENARIO_TYPES=shirt.py hani2 generate -t Shirt -n 20
```

### Loading saved scenarios for a run

Any folder in the format above can be served without a generator. Put it in the scenarios directory as a category (`<scenarios>/MyCase/` holding one scenario, named scenarios or a numbered pool) and list `MyCase` in a set, or point a run at a whole folder of categories:

```bash
hani2 --scenarios ./my-scenarios --scenario-set Pilot
```

with `Pilot: [MyCase, OtherCase]` in `scenario_sets.yaml` (or list the categories in `scenario_order.txt` and use the `Custom` set). `--scenarios` sets `HANI2_SCENARIOS_BASE` for this run; admins also see every category of the folder in the scenario picker on the start screen.

## Generating a pool with `hani2 generate`

Pools make a study reproducible: every participant who reaches slot 7 of `Trade` gets the same scenario. Generation is seeded: the same `--seed`, type and slot always give the same scenario, whichever other types or how many slots you generate. A saved scenario loads back exactly as it was generated, and `hani2 scenario check` proves it for a whole pool. `hani2 generate` writes them into the scenarios directory of the settings folder, or of the active experiment:

```bash
hani2 generate                           # 50 scenarios of every type in the active set
hani2 generate --set ANAC2027 -n 20      # 20 of every type in a set
hani2 generate --type Trade -n 20        # 20 Trade scenarios
HANI2_EXPERIMENT=pilot hani2 generate    # into experiments/pilot/scenarios
hani2 generate --base ./my-pool          # anywhere else
```

Each slot is written to `<base>/<Type>/<NNNN><Type>/` (for example `Trade/0007Trade/`).

| Option | Default | Meaning |
|--------|---------|---------|
| `--type`, `-t` | the active set | A type to generate (any registered generator). Repeat the option for several types. |
| `--set` | the active set | Generate every type of this scenario set. |
| `--count`, `-n` | `50` | Scenarios per type. |
| `--base` | the scenarios directory | Where to write the pool. |
| `--human-index` | `1` | The participant's utility function index under the `auto` role rule when the scenario suggests no role (used for the reservation values). |
| `--cache-inverter / --no-cache-inverter` | on | Save a utility inverse next to each scenario. |
| `--rebuild-inverses` | off | Do not generate anything; only rewrite the cached inverse of every existing slot. |
| `--min-opposition` | `0.35` | Reject scenarios whose opposition level is below this value. |
| `--max-opposition` | `0.90` | Reject scenarios whose opposition level is above this value. |
| `--set-reservations / --no-set-reservations` | on | Replace the generator's reservation values with small random ones. |
| `--user-reserved-max` | `0.10` | Largest reservation value for the participant (on the normalized 0–1 scale). |
| `--agent-reserved-max` | `0.20` | Largest reservation value for the opponent. |
| `--max-tries` | `60` | How many scenarios to draw per slot to hit the opposition band. |
| `--seed` | `0` | The seed of the pool: the same seed, type and slot always give the same scenario. |
| `--force` | off | Overwrite slots that already exist. |

The opposition level measures how much the two sides' preferences conflict. Near 0 there is an outcome that is good for both, so there is little to negotiate. The default band keeps real but not hopeless conflict in every slot. If no draw falls in the band after `--max-tries` attempts, that slot is reported as an error and skipped.

Generation is idempotent: a slot that already has its scenario file (and its inverse, when caching) is skipped unless you pass `--force`. You can run the command again to fill gaps.

Without `--base`, the pool is written where the server reads scenarios: the experiment's `scenarios/` folder, else `HANI2_SCENARIOS_BASE`, else `settings/scenarios`.

### Fixed pools for a competition or a study

To make sure every participant meets the same scenarios, generate the pools once, check them, and keep the folder:

```bash
hani2 generate --set ANAC2027 -n 30 --seed 2027 --base ./anac2027-pool
hani2 scenario check ./anac2027-pool        # loads, shows and round-trips every slot
hani2 --scenarios ./anac2027-pool --scenario-set ANAC2027
```

The saved folder is the reference: keep it (or ship it to the participants) rather than relying on the seed, which gives the same pool only with the same versions of hani2, negmas and Python. Without `--seed` the seed is `0`, so two runs give the same pool; pass another seed for a different one. Hand-written scenarios can sit next to the generated categories in the same folder. HANI2 also saves the scenario of every negotiation next to its results (`<user>/scenarios/<negotiation id>/`) in the same files as the pool slot, so you can check later which scenario each negotiation used.

### Cached inverters

The *Utility-based Selector* tool lists every outcome whose utility lies in a range the participant chooses. To do that it needs the inverse of the participant's utility function, which can take a moment to compute for large outcome spaces.

With `--cache-inverter`, `hani2 generate` computes that inverse once for every role and saves it as `inverter_h<index>.pkl` in the slot folder. The tool loads the file when it exists, checks it against the live utility function on a sample of outcomes, and recomputes when they differ or the file cannot be read. A missing or stale file is therefore always safe; it only costs time. Use `hani2 generate --rebuild-inverses` to refresh all cached inverses after you change `--human-index` or edit the utility files.

Pools generated before scenario sets existed cache the inverse for one index only; `hani2 generate --rebuild-inverses` writes the one for `--human-index`, and the tool computes any other on first use.
