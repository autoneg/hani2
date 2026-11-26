# Opponents

!!! note "Two kinds of agents"
    HANI2 has two kinds of agents. The **opponent agent** negotiates *against* the participant; it is
    chosen with `--opponents`, `HANI2_OPPONENTS`, `?opponents=` (admins) and `opponents` in `env.json`. The
    **Assistant** helps the participant; it is chosen with `--assistant` (see
    [Assistant](assistant.md)). Participants see it labelled **Opponent**.
    The older names `--agents`, `HANI2_AGENTS`, `?agents=` and `agents` still work.

Every negotiation pairs the participant with one *opponent*: an automated agent or, with the pool entries `human` and `human+assistant`, another participant (see [Human opponents](human-opponents.md)). HANI2 picks it from a *pool* of agent specs when the negotiation starts. This page explains how specs are written, how the pool is chosen and what HANI2 does to the opponent before it plays.

## Agent specs

An agent spec is a string that names a negotiator class. HANI2 resolves it as follows.

| Spec | Resolves to | Example |
|------|-------------|---------|
| A bare name (no dot) | A class in `negmas.sao` | `BoulwareTBNegotiator`, `AspirationNegotiator` |
| `LLM...` | An LLM negotiator from negmas-llm | `LLMHybridNegotiator` |
| `...WithTextNegotiator` | A template-based talking negotiator from negmas-llm | `HybridWithTextNegotiator` |
| `helpers.<Class>` | A classic negotiator bundled with HANI2 (`hani2.helpers.negotiators`) | `helpers.AgentK` |
| `genius.<Class>` | A Genius agent wrapper (`negmas.genius.gnegotiators`) | `genius.Atlas3` |
| `file:<path>.<Class>` | A class loaded from a Python file | `file:agents/mine.MyNegotiator` |
| A dotted path | Any importable class | `my_package.agents.MyNegotiator` |

Notes on the less obvious forms:

- `file:` paths are relative to the server's working directory unless they are absolute (`file:/home/me/neg.MyNegotiator`). Leave out the `.py` extension; the part after the last dot is the class name. Both `/` and `\` work as separators.
- A dotted path must be importable by the server process. Put your package on `PYTHONPATH` or install it into the same environment.
- `genius.*` agents need a running Genius bridge, as described in the negmas documentation.

The negmas-llm negotiators that HANI2 knows by name are:

- LLM negotiators: `LLMHybridNegotiator`, `LLMBoulwareTBNegotiator`, `LLMConcederTBNegotiator`, `LLMLinearTBNegotiator`.
- Template-based talking negotiators: `HybridWithTextNegotiator`, `BoulwareWithTextNegotiator`, `ConcederWithTextNegotiator`, `LinearWithTextNegotiator`.

### Honest and bluffing opponents

`helpers.HonestTBNegotiator` and `helpers.DeceptiveTBNegotiator` concede slowly on the same
time-based curve and accept only by their true utility; neither uses a language model. The honest one
names its real most important issue. The deceptive one claims that its least important issue matters
most and shapes its offers to fit that claim, calls almost every offer final and cites an outside
offer it does not have. They are the two levels of the `deception` factor of
[compositional scenarios](compositional.md), and they need a linear-additive utility function to know
their priorities.

## Group tokens

A spec that starts with `:` expands to a list of specs. Tokens are case-insensitive.

| Token | Expands to |
|-------|------------|
| `:llm` | The four `LLM*` negotiators above. They call a language model on every turn. |
| `:template` | The four `*WithTextNegotiator` negotiators. They send messages from templates, without a language model. |
| `:notext` | `BoulwareTBNegotiator`, `ConcederTBNegotiator`, `LinearTBNegotiator`, `HybridNegotiator` (offers only, no messages). |
| `:negmas` | Every SAO negotiator type that negmas registers. |
| `:classic` | The classic negotiators in `hani2.helpers.negotiators`: `helpers.AverageTitForTat`, `helpers.HardHeaded`, `helpers.AgentK`, `helpers.Atlas3`, `helpers.CUHKAgent`, `helpers.AgentGG`. |
| `:genius` | Every agent in `negmas.genius.gnegotiators`, as `genius.<Class>`. |
| `:custom` | The comma-separated specs in the `HANI2_CUSTOM_AGENTS` environment variable (these may contain group tokens too). |
| `:pan` | The classes in an external `pan.py` module (see below). Empty when no such module is found. |
| `:han<year>-all` | Every participant of that year's HAN league (Human-Agent Negotiation, ANAC), e.g. `:han2026-all`. Needs the `han` extra (below). |
| `:han<year>-qualified` | That year's qualified participants (disqualified entries dropped). |
| `:han<year>-finalists` | That year's finalists. |
| `:han<year>-winners` | That year's winners (empty until they are announced). |

The HAN groups come from the optional [`han-agents`](https://pypi.org/project/han-agents/) package and appear for every year it covers:

```bash
pip install "hani2[han]"      # or: uv pip install -e ".[han]" in a checkout
hani2 --opponents :han2026-finalists
```

Without the package, and for a year it does not cover, these tokens have no agents (a project or study naming such a year is refused when saved). The current year is the exception: it comes from the submitted zips (below). The groups list class paths only, so an agent is imported only when a session uses it. Some agents use a language model and need a reachable model backend (see [LLM model injection](#llm-model-injection) below).

### HAN agents of the current year

While a league runs, its agents are not packaged yet. `han.current_year` in `env.json` names that year (put it in the settings folder's `env.json`, so that `hani2 han import` and every project see the same year) (it is never taken from the clock), and `han.submissions` names the folder of its submissions:

```json title="settings/env.json"
{
  "han": {
    "current_year": 2027,
    "submissions": {"2027": {"dir": "~/league/han/2027"}}
  }
}
```

Then `:han2027-<set>` comes from that folder, and every other year still comes from `han-agents`. The folder holds the submitted zips and an `index.json` (usually written by a trusted website, for example the competition's site), with one entry per submission:

```json title="~/league/han/2027/index.json"
[
  {"entrant": "sub_0981", "team": "t17", "zip": "t17.zip",
   "class": "t17_agent.agent:MyNegotiator",
   "qualified": true, "finalist": false, "winner": false},
  {"entrant": "sub_0982", "team": "t18", "zip": "t18.zip",
   "class": "t18_agent.agent:MyNegotiator",
   "qualified": true, "finalist": true, "winner": false}
]
```

| Key | Meaning | Also accepted |
|---|---|---|
| `entrant` | The submission's id; it names the agent's folder. Characters other than letters, digits, `.`, `_` and `-` become `_`. Missing: the zip's name, else the team | `entrant_id`, `id`, `submission`, `submission_id`, `entry`, `entry_id` |
| `team` | The team's id (informative) | `team_id`, `team_name` |
| `zip` | The zip's file name, inside the folder | `zip_file`, `file`, `filename`, `archive`, `path` |
| `class` | The negotiator class, `package.module:Class` or `package.module.Class` | `class_name`, `agent_class`, `agent_class_name`, `negotiator`, `spec` |
| `qualified`, `finalist`, `winner` | The entry's placement: `true`/`false`, or `yes`/`no`, `1`/`0` | `finalists`, `winners`, `is_qualified`, … |
| `sha256` | Optional: the zip's hash. When given, an import refuses a zip that does not match | `hash`, `zip_sha256` |
| `name` | Optional label | `label`, `agent_name`, `title` |

The file may also be a mapping with the list under `entries`, `submissions` or `agents`, or a mapping of entrant id to entry. Other keys are ignored. An entry without an id is skipped, and an id listed twice keeps its last entry. The sets follow the flags: `all` is every entry, `qualified` the entries flagged qualified, finalist or winner, `finalists` those flagged finalist or winner, and `winners` those flagged winner.

Import the zips before a study uses them, and again after new uploads:

```bash
hani2 han import                 # the current year; --year 2027 for another
hani2 han check                  # entries, sets, imported version, whether each class imports
```

`hani2 han import` unpacks each zip into its own new folder, `<HANI2_HOME>/han_submissions/<year>/<entrant>/<sha256 of the zip>/`, and runs nothing while unpacking: archives with absolute paths, `..`, symbolic links or more than the size limit are refused. It then checks, in a separate Python process, that the class imports, and makes that folder the entrant's current version. An entry whose class does not import is left out of the groups, with a warning in the server log; when it is a new upload of an entrant whose earlier version works, the earlier version keeps playing (and `hani2 han check` says which version plays). A new upload has a new hash and so gets a new folder; the earlier one is kept, so past games keep their meaning, and every game records the version it played (`opponent_han_version`, next to `opponent_han_year` and `opponent_han_source`, see [`results.csv` columns](study-management.md#resultscsv-columns)).

`hani2 han check` also reports zips the index does not list, zips that changed since they were imported, entries not imported yet, and module names two entrants share. Python loads a module once per process, so of two entries with the same top-level package only the first one used can run until the server restarts; the same holds for a new version of an agent that already ran (restart the server after importing new uploads).

Unknown tokens print a warning in the server log and expand to nothing. Lists are de-duplicated and keep their order, so `:notext,BoulwareTBNegotiator` has `BoulwareTBNegotiator` only once.

### The `:pan` group

`:pan` is for deployments that keep a pool of personality-adjusted negotiators in a separate file called `pan.py`. HANI2 looks for that file in these directories, in order, and adds the first one that has it to `sys.path`:

1. The directory in `HANI2_CODE_BASE`.
2. `$SCMLWEB_CODE_BASE/python` (default `~/scmlweb/python`).
3. The server's working directory.
4. `python/` under the working directory.

The module must define the lists `HSHP`, `HSLP`, `LSHP` and `LSLP` of negotiator classes. Each class becomes the spec `pan.<ClassName>`. If `pan.py` cannot be imported, the server prints a warning and the group is empty, so anything that falls back on an empty pool keeps working. The [Prolific](prolific.md) practice round uses `:pan` by default.

### Group files

A group file `groups/<key>.json` names a pool of opponents. The token `:<key>` expands to the agents in it, and so does a *bare* spec `<key>` (no `:` and no dot) when such a file exists. HANI2 looks for the file in these folders, in order, and the first file found wins:

1. The study's results folder, `<results>/groups/`. `<results>` is `~/negmas/hani2/db` without a study, or the study's `results/` folder (see [Results](study-management.md#results)). An outside system (for example a competition website) drops its files here, so its groups always win.
2. The study folder, `<study>/groups/`.
3. The project folder, `projects/<project>/groups/`, shared by all studies of the project. For the `default` project this is the settings folder.
4. The settings folder, `settings/groups/`, for every project.
5. The built-in groups above (`:llm`, `:template`, …). A file with the same name, such as `groups/llm.json`, replaces the built-in group.

A group file has one of two shapes:

=== "List"

    ```json
    ["NaiveTitForTatNegotiator", ":notext", "helpers.AgentK"]
    ```

=== "Object with code paths"

    ```json
    {
      "syspath": ["/srv/agents/unpacked"],
      "agents": ["team42.negotiator.MyAgent", "team7.agent.Hardliner"]
    }
    ```

Group files may list other groups: `@key` or `:key` always names a group (a group file, else a
built-in group), and a bare `key` names a group file when one exists. Groups expand in place,
duplicates are dropped (the first one keeps its place), names are case-insensitive, and a cycle
(a group that ends up listing itself, such as `llm.json` listing `:llm`) is reported and broken.
The same rule holds for scenario sets, Assistant groups and tool groups; see
[Groups and composition](library.md#groups-and-composition).

In the object form, every directory in `syspath` (relative folders are relative to the file) is appended to `sys.path` before the agents are imported, so you can drop unpacked agent packages anywhere on disk. HANI2 adds the `syspath` entries of all group files at server start-up, so an agent from a group file imports even in a session that never named the group. Group files may contain group tokens and other group keys. HANI2 only reads these files; other tools can write them.

A group file takes priority over a negmas class with the same bare name. The object form may also carry a `description`, an `assistant` (old name `support_agent`): the Assistant for the participants who arrive with `?group=<key>` (see [Assistant pools and assignment](assistant.md#the-group-files-assistant-key)), and `"ai_fallback": false`: those participants then never get an AI opponent, only people (see [People-only invitations](human-opponents.md#people-only-invitations)).

Upload or link your own negotiators with the [library](library.md)
(`hani2 library add opponents my_team.py --group qualified --layer project:HAN2027`) and edit
groups with `hani2 library group-set opponents …`; the group files it writes hold the class specs
and their `syspath`, so they work without the library.

`hani2 groups list` shows every group with its members, its file and whether another file shadows it; `--project <P>` lists a project's groups (its folder, its studies and the settings folder). Admins can browse every group and its members, edit groups and upload or link their own opponent classes on the *Opponents* page of the [admin console](admin.md#opponents), or through the [admin API](project-management.md#admin-api).

## Choosing the pool

When a negotiation starts, HANI2 builds the pool from the first source in this list that yields at least one agent:

1. The query string of the page: `?opponents=<specs>` (comma-separated specs and tokens; admins only, ignored for everyone else), else `?group=<key>` (anyone). `?group=` accepts a group-file key or a built-in token with or without the colon (`?group=template`, `?group=:template`).
2. The `--opponents` option of `hani2` (stored in the `HANI2_OPPONENTS` environment variable).
3. The *Opponent agents* setting (`env.json → negotiation → opponent_types`, on the admin console's Negotiation page, per layer).
4. The `opponents` list in `env.json`, also editable as *Opponents participants face* on the *Opponents* page of the admin console (which also writes a project's or study's `opponents`).
5. The default pool: the four template-based talking negotiators (`:template`).

The default needs no language model, so a casual visitor never causes LLM costs.

```bash
# Everyone negotiates against conceder and boulware agents
hani2 --opponents BoulwareTBNegotiator,ConcederTBNegotiator

# Mix groups and single agents
hani2 --opponents ":notext,helpers.AgentK"
```

```text
http://localhost:5006/play?opponents=LLMHybridNegotiator    # logged in as an admin
http://localhost:5006/play?group=finalists
```

```json
{
  "opponents": [":template", "helpers.HardHeaded"]
}
```

The opponent is then chosen at random from the pool, with these exceptions:

- In a study, every participant faces the pool in a balanced order (see [Latin squares](#latin-squares)), or as the study's [scheduling method](scheduling.md#opponents) says.
- A `schedule.json` fixes the opponent per round. The [Prolific](prolific.md) study also fixes the practice opponent.
- In admin mode, the *Opponent for the next negotiation* field on the start screen overrides the random choice (see below).

## Latin squares

In a [study](study-management.md) run by HANI2 itself (no `schedule.json` for the participant), the
opponents follow a **balanced Latin square** (a Williams design) over the pool: every opponent
appears once in every position, and every opponent follows every other opponent equally often,
so order and carry-over effects cancel out across participants. With `n` opponents the square has
`n` rows (`2n` when `n` is odd). Participant number *i* of the study (counted in order of arrival,
stored in the study's `assignments.json`) takes row `i mod rows`, and their *k*-th counted
negotiation uses position `k mod n` of that row. With four opponents A, B, C, D:

| Participant | 1st | 2nd | 3rd | 4th |
|---|---|---|---|---|
| 0 | A | B | D | C |
| 1 | B | C | A | D |
| 2 | C | D | B | A |
| 3 | D | A | C | B |

Admins and playground guests are not counted and keep the random choice, and so do admin-mode sessions and logged-in users whose pool comes from the URL (an admin's `?opponents=`, `?group=`, a test link); Prolific, online and lab participants arriving with `?group=` follow the square over that group. Participants are
counted per study, so each study is balanced on its own. A participant with a `schedule.json`
gets the schedule's opponents; participants of a study started before this rule (with a
`fallback_rotation.txt`) and sessions outside a study keep the older rotation. Each participant
of a study also gets the scenario type `i mod t` of the active scenario set's `t` types.

The Latin square is the default `opponents` [scheduling method](scheduling.md#opponents). A study
or project can choose another one in its YAML file (`scheduling: {opponents: random}`): `random`
(a uniform draw per negotiation), `cyclic` (the older rotation by participant index), `fixed_order`
(everyone in pool order) or `external` (only `schedule.json`; a missing slot is filled with the
rotation and flagged as `external:missing`). The method used is written to the
`opponent_scheduling` column of every result row.

`--opponents` and its old name `--agents` (and `HANI2_OPPONENTS` / `HANI2_AGENTS`) cannot be given
together with different values; HANI2 refuses to start and says to keep `--opponents`.

## The admin opponent picker

When a session is in admin mode, the start screen shows a field labelled *Opponent for the next negotiation*. It suggests every agent in the groups offered to admins (`llm`, `template`, `notext`, `negmas`, `classic`, `genius`), but you can type any spec. Leave it empty to draw from the pool. The choice stays in place for later negotiations in the same session until you clear it.

Admin sessions also show the opponent's name in the interface. For other participants, the opponent's type stays hidden unless the admin turns on *Show the opponent's type* on the Negotiation page of the admin console (per layer). See [Admin console](admin.md) and [Authentication](authentication.md) for how a session enters admin mode.

## What HANI2 does to an opponent

`hani2.agents.make_agent()` builds the opponent. Besides instantiating the class, it does three things.

### LLM model injection

Opponents that call a language model use the model configured in `llm_settings.json` (see [Language models](llms.md)):

- For a spec that starts with `LLM`, HANI2 passes both `model` and `provider`.
- For any other subclass of negmas-llm's `LLMNegotiator`, it passes `model`.
- For subclasses of negmas-llm's `LLMMetaNegotiator` (a numeric strategy wrapped by an LLM message layer), it passes `model` and `provider`, but only when the constructor declares those parameters by name.

Without this step, LLM negotiators would fall back to negmas-llm's built-in default model.

### Robustness wrappers

Two wrappers change the opponent's class at runtime:

- **No accept without an offer.** If the opponent tries to accept while no offer is on the table (for example on its first move, or after the participant sent a message without an offer), the accept becomes a plain "no counter-offer" response that keeps any message. The negotiation continues instead of breaking. Every opponent gets this wrapper.
- **No ending in practice rounds.** In a practice round, an attempt by the opponent to end the negotiation becomes a "no counter-offer" response, so a participant who is still learning the interface never sees the opponent walk away. Real rounds keep the unwrapped behaviour.

The wrapped class names start with `NoAcceptNone_` and `NoEnd_`. The `agent_type` column in `results.csv` keeps the spec you configured, not the wrapper name.

### Verbose mode

`hani2 --verbose` sets `HANI2_VERBOSE=1`. HANI2 then tries to construct opponents with `verbose=True`, and falls back to the normal constructor if the class does not accept that argument.

## Writing your own opponent

Any negmas `SAONegotiator` works. Save it in a file and use a `file:` spec, or put it in an importable package and use a dotted path:

```python title="agents/stubborn.py"
from negmas.sao import AspirationNegotiator


class Stubborn(AspirationNegotiator):
    """Concedes very late."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("aspiration_type", 10.0)  # a high exponent concedes late
        super().__init__(*args, **kwargs)
```

```bash
hani2 --opponents file:agents/stubborn.Stubborn
```

Opponents that send messages put the text in the `data` of their response under the `text` key, as the negmas-llm negotiators do. HANI2 shows that text in the negotiation history.
