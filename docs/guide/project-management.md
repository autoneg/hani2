# Project management

One HANI2 server can run many data collections at once, each with its own texts, settings and results. They are organised as *projects* and *studies*. No restart is needed to add one: HANI2 reads the project and study files when a participant arrives.

This page is about projects: what they are, how to create and edit them, and the defaults they give their studies. Running one study (its type, its links, its assignment, its forms and its results) is described in [Study management](study-management.md).

## What a project is

| Term | Meaning | Examples |
|---|---|---|
| **Project** | A long-lived research or competition programme. It owns the participant-facing identity (name, year, organiser, contact, consent text) and the defaults its studies share. Its *kind* says what is evaluated: `opponent` (submitted opponents face humans), `assistant` (submitted assistants help humans) or `none` (plain research). | `HAN2027`, `HI2027` |
| **Study** | One data collection inside a project, with its own results. Its *type* is `prolific` (a Prolific study), `online` (you recruit people and send them a link) or `lab` (in person). See [Study types](study-management.md#study-types). | `hi-2027-01`, `han-lab-kyoto` |
| **Human** | The participant's side of a negotiation. | |
| **Assistant** | The AI helper on the human's side. | |
| **Opponent** | The other side. | |

The built-in project `default` holds every study you do not put in a project. Experiments from earlier versions are studies of this project (see [Migrating from experiments](study-management.md#migrating-from-experiments)).

### Folder layout

```text
$HANI2_HOME/projects/<project>/        default ~/negmas/hani2/projects
├── project.yaml          name, full name, kind, year, organiser, contact, defaults for its studies
├── consent.md            any settings file, shared by the project's studies (optional)
├── announcements.md
├── env.json, assistant_settings.json, questionnaires/, scenarios/, scenario_sets.yaml, ...
└── studies/<study>/
    ├── study.yaml        type, title, dates, Prolific study id, completion code, overrides
    ├── consent.md ...    optional per-study copies of any settings file
    └── results/          per-participant folders, events.db, recordings, group files
```

`HANI2_PROJECTS` moves the projects folder elsewhere.

User accounts are shared by all projects and studies.

## Creating and editing a project

A project can be created and edited in three ways, which all write the same `project.yaml`:

- the admin console's **Projects & Studies** page (see [Admin console](admin.md#projects-studies));
- the command line, `hani2 project create` (see [Command line](#command-line));
- the [admin API](#admin-api), `PUT /api/admin/projects/{project}`.

`create` on an existing project updates the given fields. `hani2 study create` also creates the project when it is missing.

### `project.yaml`

```yaml title="projects/HI2027/project.yaml"
full_name: Human-AI Interaction League 2027
short_description: People negotiate with the help of AI assistants.
link: https://example.org/hi2027
year: 2027
kind: assistant            # opponent | assistant | none
organizer: The Negotiation Lab
contact: lab@example.org
defaults:                  # every study of the project starts from these
  n_required: 4            # counted negotiations per participant
  practice: true           # one practice negotiation first
  practice_time_limit: 300
  counted_time_limit: 600
  minutes: 45              # expected maximum duration
  scenario_set: HI2027
  role_rule: auto
  strict_scenarios: true   # only saved scenarios; a missing pool is an error
  force_reserved_value: 0  # every party's value on disagreement, in every negotiation
  opponents: [BoulwareTBNegotiator]
sponsor: ACME              # any other key is available to texts as {{project_sponsor}}
```

`full_name`, `short_description`, `link`, `year`, `organizer`, `contact` and any key you add yourself fill the [text variables](study-management.md#texts-with-variables) of every study of the project.

### Forcing the value on disagreement

`force_reserved_value` gives every party (the participant and the opponent) the same value on
disagreement in every negotiation of a project or study, whatever each scenario says. It is unset by
default, and then every scenario keeps its own values. Set it in `project.yaml` (for all the
project's studies) or `study.yaml` (for one study; a study's value wins, and `0` is a value, not
"unset"). The number is on the scenario's utility scale: 0 to 1 for normalised scenarios, so `0`
means that any agreement is at least as good as none. In the console it is *Forced value on
disagreement* under *Projects*; the field starts empty (each scenario's own values), and its − button
sets it to 0.

The forced value is applied in memory when a scenario loads: saved scenarios are never changed, the
recorded scenario of each negotiation carries the value that was played, and the basic scenario info
records it as `forced_reserved_value`.

A setting given twice in `project.yaml` with different values (at the top level and again under `defaults:`) is refused when the file is saved through the admin API or the command line, and reported (server log, `hani2 project show`) when a hand-edited file has it; the value under `defaults:` is then used.

### What a study inherits

A study starts from its project:

- its settings come, first match wins, from an environment variable, the study's `overrides`, the project's `defaults` and the built-in default (see [`study.yaml`](study-management.md#studyyaml));
- every settings file (consent, welcome text, `env.json`, questionnaires, scenarios, …) placed in the project folder is used by every study that has no copy of its own (see [Settings files per study](study-management.md#settings-files-per-study));
- the project's opponent and Assistant groups are available to all its studies (see [Pools of opponents and Assistants](#pools-of-opponents-and-assistants)).

## Defaults for its studies

The keys of `defaults` may also be written at the top level. They are: `scenario_set`, `n_required`, `practice`, `practice_time_limit`, `counted_time_limit`, `time_limit`, `n_steps`, `minutes`, `role_rule`, `human_roles`, `strict_scenarios` (serve saved scenarios only, see [Strict scenarios](scenarios.md#strict-scenarios)), `simple_scenarios` (round numbers and plain shapes in generated scenarios, on unless switched off, see [Simple scenarios](scenarios.md#simple-scenarios)), `information` (what the participant and the Assistant each know, see [Who knows what](information.md)), `assistant_starts_on` (Prolific and online participants start with the Assistant switched on instead of off), `force_reserved_value` (every party's value on disagreement in every negotiation of the study, whatever the scenario says, see [Forcing the value on disagreement](#forcing-the-value-on-disagreement)), `questionnaires` (`false`: no questionnaire at all in this study, see [Where the questionnaire is looked up](study-management.md#where-the-questionnaire-is-looked-up)), `opponents` and `assistants` (the pools below), and `scheduling` (how each study assigns them, see [Assignment](#assignment)).

A study changes any of them under `overrides:` in its `study.yaml`.

### Pools of opponents and Assistants

A project shares its pools with all its studies:

```
projects/HI2027/
  project.yaml               # opponents: [":finalists"]   assistants: [":entries"]
  groups/finalists.json      # opponent group   {"agents": [...], "syspath": [...]}
  assistant_groups/entries.json   # Assistant group  {"assistants": [...], "syspath": [...]}
  studies/hi-2027-01/
    study.yaml               # may override opponents / assistants
    groups/ assistant_groups/   # optional groups of this study only
    results/
      groups/                # files an outside system drops (they win)
      assignments.json       # each human's index and Assistant
```

A token `:key` is looked up in the study's `results/groups/`, the study folder, the project folder,
the settings folder and finally the built-in groups (see [Group files](opponents.md#group-files)
and [Assistant groups](assistant.md#assistant-groups)). `hani2 groups list --project <P>` lists a
project's groups, and the admin API edits them (see [Admin API](#admin-api)).

### Assignment

A project chooses, for all its studies, how each dimension is assigned to the humans: the
opponents, the Assistants and the scenario types. A study can choose another method per dimension:

```yaml
scheduling:
  opponents: latin_square   # random, cyclic, fixed_order, external
  assistants: balanced      # random_fixed, random_each, round_robin, external
  scenarios: by_participant # set_order, random, latin_square, external
```

What these defaults do within a study is described in
[Assigning Assistants, opponents and scenarios](study-management.md#assigning-assistants-opponents-and-scenarios),
and every method, with its formulas and examples, in [Scheduling methods](scheduling.md).

## Connecting a website

There are two ways to run HANI2.

**Standalone.** HANI2 runs the whole study: create the project and the study, give out the link it prints, and HANI2 shows the consent form and the questionnaires, assigns scenarios and opponents, and ends with the completion code, the Prolific redirect or a thank-you page.

```bash
hani2 project create HI2027 --kind assistant --full-name "Human-AI Interaction League 2027" --year 2027
hani2 study create HI2027/hi-2027-01 --type prolific --title "January run" --completion-code C1A2B3
hani2 --host 0.0.0.0 --no-browser
```

**Driven by an outside system** (for example a trusted website such as a competition's site, which recruits participants and schedules the opponents). Such a system usually starts one HANI2 process per league with `HANI2_EXPERIMENT=<wave>`, `--root-path`, `--assistant on|off` and `--page play`, sends participants to `<root>/play?PROLIFIC_PID=<pid>&group=<key>`, writes `schedule.json` and `groups/<key>.json` into the results folder and sets `PROLIFIC_*` variables. All of this works unchanged: the wave is the default study of that process, its results stay in `$HANI2_EXPERIMENTS/<wave>/results/prolific_<PID>/` with the same files and columns (new columns are only ever added), and the rule is that **an outside system's explicit input wins**: environment variables, `schedule.json`, group files and query parameters always take precedence over what `project.yaml` and `study.yaml` say. HANI2's own project and study settings only fill in what is not given.

## Command line and admin API

### Command line

```bash
hani2 project create NAME [--full-name TEXT] [--kind opponent|assistant|none] [--description TEXT]
                          [--link URL] [--year N] [--organizer TEXT] [--contact TEXT]
hani2 project list
hani2 project show NAME
hani2 groups list [--project P | --study P/S] [--kind opponent|assistant] [--no-builtin]
hani2 scheduling list [--details]   # the scheduling methods
```

The commands for studies (`hani2 study create`, `list`, `show`) are in [Study management](study-management.md#command-line).

### Admin API

These JSON endpoints are for admins only. Project, study and group names may contain only letters, digits, `.`, `_` and `-`. The project's group folder of the `default` project is the settings folder.

A layer `L` is `settings`, `project:<P>` or `study:<P>/<S>`; the old `?study=P/S` and `?project=P` are accepted too. Values "in effect at a layer" are computed for that layer, whatever study the request URL is in. A settings write (PUT, PATCH, DELETE) sent from inside a study (`/s/P/S/api/admin/...`) that names no layer is refused with 409, so the console can never silently write the shared settings while it shows a study.

| Endpoint | Does |
|---|---|
| `GET /api/admin/projects` | The projects with their settings and study names, and the server's default study. |
| `GET /api/admin/projects/{project}` | A project: its settings, `project.yaml` as text, and its studies (with participant counts and links). |
| `PUT /api/admin/projects/{project}` | Create or replace `project.yaml`: `{"data": {...}}` or `{"yaml": "..."}`. |
| `GET /api/admin/layers` | The layers (`settings`, `project:P`, `study:P/S`) with their folders, and the study the request is bound to (`bound`). |
| `GET /api/admin/settings/{kind}?layer=L` | `kind`: `env`, `llm`, `assistant`, `autopilot` or a text (`consent`, `announcements`, `scenario_sets`, `scenario_order`). JSON kinds: `{"own", "effective", "inherited"}` (the layer's own file, the values in effect at that layer, and those without its file). Texts: `{"text", "exists", "effective", "source", "source_path"}` (`source`: the layer the text in effect comes from). The old `?study=P/S` / `?project=P` return the layer's raw file, and no parameter the effective settings, as before. |
| `PATCH /api/admin/settings/{kind}?layer=L` | JSON kinds: merge the body into the layer's own file. |
| `PUT /api/admin/settings/{kind}?layer=L` | Replace the layer's own file (texts: `{"text": "..."}`). Without a layer: the settings folder, as before. |
| `DELETE /api/admin/settings/{kind}?layer=L[&key=a.b]` | Remove one dotted key from the layer's own JSON file, or (without `key`) the layer's own file. |
| `GET` / `PUT /api/admin/pools/{kind}?layer=L` | The opponent or Assistant pool set at a layer (`env.json` `opponents`; `defaults.<kind>s` in project.yaml; `overrides.<kind>s` in study.yaml), what it inherits and what it expands to. PUT `{"items": [...]}` rewrites only that key. |
| `/api/admin/library/...` | Scenario types, opponents, Assistants and tools: items, upload, link, remove, groups, the default scenario set, the tools offered and their placement per view. See the [Library API](../reference/library-api.md). |
| `GET /api/admin/scenarios/{name}?layer=L[&scenario=S][&generate=N]` | A type's details: texts, roles, issues and options, sample utilities, its pool, and a `plot_token` for the plot below. |
| `GET /api/admin/scenarios/plot/{token}` | The outcome-space plots of the example those details showed: `plots` (one Plotly figure per pair of roles) and `plot_note`. Fetched apart so the details never wait for it; 404 once the example is no longer kept. |
| `GET /api/admin/groups?project=P` | The project's opponent and Assistant groups (its folder, its studies, the settings folder and the built-in groups): key, members, `syspath`, description, the group file's `assistant`, source and file. With `?study=P/S` instead: the groups as that study resolves them, `active` marking the file a token resolves to. |
| `GET /api/admin/projects/{project}/groups/{kind}/{key}` | One group file of the project (`kind`: `opponent` or `assistant`, plural accepted). |
| `PUT /api/admin/projects/{project}/groups/{kind}/{key}` | Create or replace it: a list of specs, or `{"description", "syspath", "agents"` (opponents) or `"assistants"`, and for opponent groups `"assistant"` and `"ai_fallback"` (a boolean)`}`. Checked before it is written. |
| `DELETE /api/admin/projects/{project}/groups/{kind}/{key}` | Delete it. |
| `POST /api/admin/templates/preview` | `{"text": "...", "study": "P/S"}` or `{"kind": "consent", "study": "P/S"}`: the rendered text, the unknown variables, and every variable with its value. |

The endpoints for one study (its `study.yaml`, its balance and its assignments) are in [Study management](study-management.md#admin-api).
