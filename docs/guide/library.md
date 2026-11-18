# Library and groups

HANI2 works with four kinds of things a study is built from. The **library** treats them the same
way: you can list them, add your own by uploading or linking them, remove what you added, and
put them in **groups**, which can be made of other groups.

| Kind | Items | Groups | Used for |
|---|---|---|---|
| `scenarios` | Scenario types: the built-in generators, registered types, uploaded and linked folders | [Scenario sets](scenarios.md#scenario-sets) (`scenario_sets.yaml`) | Which scenarios a study serves, in which order |
| `opponents` | Negotiator classes | Opponent groups (`groups/<key>.json`) | The opponent pool (`?group=`, `:key` tokens, project and study `opponents`) |
| `assistants` | Assistant classes | Assistant groups (`assistant_groups/<key>.json`) | The Assistant pool of a study |
| `tools` | Tool classes | Tool groups (`tools.yaml`, plus built-in groups from the tools themselves) | Which tools a study offers, and where they go |

Everything here works from the command line (`hani2 library`, see
[Command line](../getting-started/cli.md#hani2-library)), from Python (`hani2.library`) and over
the admin API ([Library API](../reference/library-api.md)).

## Items and where they come from

Every item has a **source**:

| Source | Meaning |
|---|---|
| `builtin` | Ships with HANI2 (the Trade, Island and Grocery generators and the story types, the built-in negotiators, the built-in Assistant and tutorial Assistants, the built-in tools) |
| `registered` | Made available another way: a scenario-type plugin, `env.json` → `tools.extra`, a tools folder, `HANI2_CUSTOM_AGENTS`, a spec listed in a group file |
| `uploaded` | A copy the library owns: scenarios under `<layer>/scenarios/<name>/`, code under `<layer>/library/<kind>/<name>/` |
| `linked` | A folder, file or class spec left where it is; the library only remembers it |

```bash
hani2 library list scenarios
hani2 library list opponents --layer project:HAN2027
hani2 library list tools --layer study:HAN2027/lab-kyoto
```

## Layers

Where you add an item or a group is its **layer**:

| Layer | Folder | Seen by |
|---|---|---|
| `settings` | `$HANI2_HOME/settings/` | every project and study |
| `project:<P>` | `projects/<P>/` (`project:default` is the settings folder) | the project's studies |
| `study:<P>/<S>` | the study's folder | that study |

A layer sees its own items and groups and those of the less specific layers; a more specific
group of the same name replaces a less specific one. You can only remove an item, or delete a
group, at the layer that defines it; a group of another layer can be *shadowed* by writing one of
the same name at your layer.

## Adding items

### Uploading

Upload a `.zip` (any kind) or a single `.py` file (opponents, Assistants, tools):

```bash
hani2 library add scenarios ~/Downloads/Rentals.zip --layer project:HAN2027 --group Rentals
hani2 library add opponents my_team.py --group qualified --layer project:HAN2027
hani2 library add assistants coach_package.zip --layer study:HI2027/hi-01
hani2 library add tools offer_counter.py
```

- **Scenarios.** The zip holds one scenario folder (`<Type>.yml` and one file per role, see
  [The on-disk format](scenarios.md#the-on-disk-format)) or a category of them. Every scenario is
  checked like `hani2 scenario check` does: errors refuse the upload, warnings are shown. The type
  is named after the zip's top folder (or `--name`). A name that equals a registered scenario
  type, or starts like one (`TradeExtra`, `Tra`), is refused: it could make the scenarios show
  with that type's display. Scenarios that bring Python files (a `display.py`) need
  `--allow-code`.
- **Code.** The library imports the file or package, takes every class of the kind (negotiators
  for opponents, Assistant subclasses, tool classes; `--classes` picks some) and checks that each
  loads the way HANI2 will load it. A class that does not import is refused with the error. A
  package (a zip with folders holding `__init__.py`) is imported by its dotted names; its
  top-level module names must not clash with installed modules.

!!! warning "Uploaded code runs on the server"
    Opponents, Assistants, tools and a scenario's `display.py` are Python code. Adding them runs
    that code inside the HANI2 server, with the server's permissions, when it is checked and
    whenever it is used. Only administrators can add items; only add code you trust.

### Linking

Link a folder or file on disk, or a class spec, instead of copying it:

```bash
hani2 library add scenarios /data/scenarios/rentals --link --name Rentals
hani2 library add opponents /srv/teams/team_a --link            # a package folder
hani2 library add opponents mypkg.agents.Boulware2 --syspath /srv/pkgs
hani2 library add tools /srv/tools/counter.py --link
```

Scenario links are written to `<layer>/scenario_links.yaml`; code items to
`<layer>/library.yaml`:

```yaml title="scenario_links.yaml"
links:
  Rentals: /data/scenarios/rentals      # a category or one scenario folder
  Kyoto: ../shared/kyoto-trip           # relative: to this file
```

```yaml title="library.yaml"
opponents:
  LibBoulware:
    source: uploaded
    path: library/opponents/my_team     # the copy (relative: to the layer folder)
    class: LibBoulware
    file: library/opponents/my_team/my_team.py
assistants:
  Coach:
    source: linked
    spec: coachpkg.coach:Coach
    syspath: [/srv/pkgs]
```

### Removing

```bash
hani2 library remove opponents LibBoulware --layer project:HAN2027
```

An uploaded item's files (when no other item uses them) are moved to the layer's `.trash` folder
(`scenarios/.trash/<name>-<time>` or `library/<kind>/.trash/<name>-<time>`), so a removal can be
undone by hand; folders whose names start with `.` are never served. A replaced upload
(`--replace`) goes there too. A linked item is forgotten and its target left alone. Groups that
list the item keep their entries.

The library never rewrites a file it cannot read: when `library.yaml`, `scenario_links.yaml` or
`scenario_sets.yaml` of the layer is not valid YAML, adding, removing or editing is refused
(HTTP 409) until the file is fixed by hand, instead of replacing what is in it.

## Groups and composition

A group lists items **and other groups**. The same rule applies to every kind:

- `@name` always names a group. `:name` does too (the older spelling of opponent and Assistant
  groups, which keeps working).
- A bare entry names a group when there is one of that name, otherwise it is an item. For
  opponents and Assistants a bare word is looked up in the group *files* only; built-in groups
  (`:llm`, `:template`, `:default`, …) need `@` or `:`. In a scenario set, an entry equal to the
  set's own name is the scenario type of that name.
- Groups expand in place, recursively. Duplicates are dropped; the first occurrence keeps its
  place.
- A cycle (`A` lists `@B`, `B` lists `@A`) is reported once and broken by ignoring the step that
  closes it. A group listing itself is a cycle too.
- Group names are case-insensitive.

```yaml title="scenario_sets.yaml"
sets:
  Basics: [Trade, Island]
  Course: ["@Basics", Grocery, Trade]      # Trade, Island, Grocery
```

```json title="projects/HAN2027/groups/finalists.json"
{"description": "The finalists and two baselines",
 "syspath": ["/srv/teams"],
 "agents": ["@qualified", "team_x.agent.Agent", ":notext"]}
```

```yaml title="tools.yaml"
groups:
  core: ["@information", "Utility-based Selector"]
  plots: [visualization, Trace]
```

Each file keeps its own format and location (scenario sets in `scenario_sets.yaml`, opponent and
Assistant groups in their JSON files with `syspath`, `description` and, for opponent groups,
`assistant`), so files written by an outside system stay readable. Files written through the
library store an item's spec (not its library name) and its `syspath`, so they also work on their
own.

Edit groups from the command line:

```bash
hani2 library groups opponents --layer project:HAN2027 --expanded
hani2 library group-set opponents finalists @qualified team_x.agent.Agent --layer project:HAN2027
hani2 library group-set scenarios Course @Basics Grocery
hani2 library group-set tools core @information "Utility-based Selector"
hani2 library group-set scenarios Course2 @Basics --rename-from Course
hani2 library group-delete tools core
```

Saving a group checks its entries and returns warnings (the group is saved anyway): a reference
to an unknown group, an entry that is no known item (scenario types, tools) or no class that
loads (opponents, Assistants), and a cycle through other groups.

Built-in groups (opponents `:llm`, `:template`, …; Assistants `:default`, `:tutorial`; the
built-in tool groups; the scenario sets bundled with HANI2) cannot be changed or deleted, but a
group of the same name at a layer replaces them there. The scenario set `Custom` is
`scenario_order.txt`.

## Tool groups

Every tool belongs to the groups its class lists in `groups`, plus:

| Group | Tools |
|---|---|
| `all` | every tool |
| `admin` | admin-only tools (`admin_only = True`) |
| `assistant` | tools the Assistant adds when it chooses (`timing = "agent"`) |
| `information` | what the participant knows: Preferences, Opponent Preferences, Scenario Info, Trace, My Results, All Results |
| `visualization` | plots and charts: Utility Plot, Negotiation Plot, Outcome Plot, Value Histogram |
| `recommendation` | tools that suggest offers: Utility-based Selector, LLM, Random (and every `OutcomeSelector`) |

Give your own tools a group in their class:

```python
class OfferCounter(Tool):
    name = "Offer Counter"
    groups = ("information",)
```

### Choosing the tools a study offers

`tools.yaml` → `offer` lists the tools sessions get, as tools and groups. The most specific layer
that sets it wins; without it every tool is offered, as before. An empty list (`offer: []`)
offers no tool. Admin-only and guest rules still
apply to the offered tools, and the Assistant can only add offered tools.

```yaml title="projects/HI2027/studies/hi-01/tools.yaml"
offer: ["@information", "@recommendation", "Utility Plot"]
```

```bash
hani2 library offer @information @recommendation "Utility Plot" --layer study:HI2027/hi-01
hani2 library offer --all --layer study:HI2027/hi-01      # every tool again
```

## Where tools go in each view

The page has three views: **full** (every pane), **simple** (one tool column) and **focus** (the
negotiation only). A tool can sit in a different pane, at a different place, or be hidden,
depending on the view. A tool class gives its placement per view:

```python
class Histogram(Tool):
    pane = "lower"
    placement = {
        "full": {"pane": "lower", "visible": True},
        "simple": {"pane": "upper", "visible": False},   # hidden in the simple view
    }
```

A view or key not given falls back to the tool's `pane`, its `order` and visible. The enable
switch stays `enabled`, the same in every view.

Layers override placements in `tools.yaml` (per tool; keys outside a view apply to every view):

```yaml title="tools.yaml"
placement:
  Trace: {pane: side}
  Value Histogram:
    simple: {visible: false}
    full: {order: 5}
```

```bash
hani2 library placement "Value Histogram" --view simple --hidden
hani2 library placement Trace --pane side --layer project:HAN2027
hani2 library placement            # every tool's placement per view
```

The placement of a tool in a view is, later wins: the tool's `pane` and `order` (visible), the
class's `placement`, `env.json` → `tools.overrides` (`pane`, `order` and a `placement` mapping),
then `tools.yaml` from the settings folder, the project and the study.

When the participant (or the Assistant) switches the view, every tool moves to its place in the
new view. Where the participant moved or hid a tool is remembered per view, so going back to the
full view restores the full view's arrangement. Tools without a placement do not move, so
nothing changes until you configure one.

## In the admin console

The **Scenarios**, **Opponents**, **Assistants** and **Tools** pages of the
[admin console](admin.md#the-library-pages-scenarios-opponents-assistants-and-tools) do all of
the above for a chosen layer: list items with their source and groups, upload and link, remove,
edit groups with their composition, choose the default scenario set, the tools offered and where
each tool goes in each view.
