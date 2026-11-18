# Projects and studies

One HANI2 server can run many data collections at once, each with its own texts, settings and results. They are organised as *projects* and *studies*. No restart is needed to add one: HANI2 reads the project and study files when a participant arrives.

## Terms

| Term | Meaning | Examples |
|---|---|---|
| **Project** | A long-lived research or competition programme. It owns the participant-facing identity (name, year, organiser, contact, consent text) and the defaults its studies share. Its *kind* says what is evaluated: `opponent` (submitted opponents face humans), `assistant` (submitted assistants help humans) or `none` (plain research). | `HAN2027`, `HI2027` |
| **Study** | One data collection inside a project, with its own results. Its *type* is `prolific` (a Prolific study), `online` (you recruit people and send them a link) or `lab` (in person). | `hi-2027-01`, `han-lab-kyoto` |
| **Human** | The participant's side of a negotiation. | |
| **Assistant** | The AI helper on the human's side. | |
| **Opponent** | The other side. | |

The built-in project `default` holds every study you do not put in a project. Experiments from earlier versions are studies of this project (see [Migrating from experiments](#migrating-from-experiments)).

## Folder layout

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
  opponents: [BoulwareTBNegotiator]
sponsor: ACME              # any other key is available to texts as {{project_sponsor}}
```

The keys of `defaults` may also be written at the top level. They are: `scenario_set`, `n_required`, `practice`, `practice_time_limit`, `counted_time_limit`, `time_limit`, `n_steps`, `minutes`, `role_rule`, `human_roles`, `strict_scenarios` (serve saved scenarios only, see [Strict scenarios](scenarios.md#strict-scenarios)), `opponents` and `assistants` (the last is kept for the assignment of assistants, which a later version adds).

### `study.yaml`

```yaml title="projects/HI2027/studies/hi-2027-01/study.yaml"
type: prolific             # prolific | online | lab
title: January 2027 run
start: 2027-01-05
end: 2027-01-31
prolific_study_id: 65a0c0ffee
completion_code: C1A2B3
# completion_url: https://example.org/thanks?id={pid}   # online studies: where participants go at the end
# end_text: Thank you! Your code is {{completion_code}}. # the end page's text
overrides:                 # the project's defaults this study changes
  n_required: 3
wave: 1                    # any other key is available to texts as {{study_wave}}
```

Settings of a study come, first match wins, from: an environment variable set by whoever starts HANI2 (`PROLIFIC_N_REQUIRED`, `PROLIFIC_MAX_MINUTES`, …), the study's `overrides`, the project's `defaults`, and the built-in default.

## Settings files per study

Every settings file is looked up per session, first match wins:

1. the study folder,
2. the project folder (the `default` project has none: its layer is the settings folder),
3. the settings folder (`$HANI2_HOME/settings`),
4. the defaults bundled with HANI2.

JSON files (`env.json`, `assistant_settings.json`, …) are merged in the same layers, so a study's `env.json` only needs the keys it changes. Scenarios come from the study's `scenarios/`, then `HANI2_SCENARIOS_BASE`, then the project's `scenarios/`, then the settings folder. The questionnaire after each negotiation comes from `questionnaires/per_negotiation.yaml` in the study and then the project folder (after the environment variables and `env.json`, see [Studies and results](studies.md#where-the-questionnaire-is-looked-up)).

User accounts are shared by all studies.

## URLs

Each study has its own pages:

| URL | Page |
|---|---|
| `/s/<project>/<study>/play` | The playground and the participant entry (`?PROLIFIC_PID=`, `?pid=`, `?code=`). |
| `/s/<project>/<study>/app` | The main app (log in), for example for a lab study with accounts. |
| `/s/<project>/<study>/login`, `/admin`, … | Every other page, within the study. |

Everything a page does from there (sign-in, consent, the negotiation channel) stays in that study. `?study=<project>/<study>` on any page moves it to the study's address, and API calls accept `?study=` too. A URL naming a study that does not exist gets *404*.

`/play` and `/app` without a study use the server's *default study*: the one given with `hani2 --study <project>/<study>` (`HANI2_STUDY`), or with the old `--experiment <name>` (`HANI2_EXPERIMENT`, a study of the `default` project). Without either, results go to `$HANI2_HOME/db` as always.

Behind a reverse proxy, the study path comes after the mount path: `https://example.org/hani/s/HI2027/hi-2027-01/play` with `hani2 --root-path /hani`.

## Study types

### Prolific

Give Prolific the study URL with Prolific's placeholders:

```text
https://example.org/s/HI2027/hi-2027-01/play?PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}
```

`hani2 study create` and `hani2 study show` print it. The flow is the one in the [Prolific guide](prolific.md). The completion link is, first match wins:

1. `PROLIFIC_COMPLETION_URL` (`{pid}` is the participant's ID),
2. an outside system's completion path (`SCMLWEB_BASE_URL` / `SCMLWEB_PROLIFIC_PATH`), when one of them is set,
3. `completion_url` in `study.yaml`,
4. Prolific's completion link for `completion_code` in `study.yaml` (`https://app.prolific.com/submissions/complete?cc=<code>`),
5. the default completion path of the outside system.

A Prolific ID is accepted by every study, whatever its type.

### Online

Send each participant a link with their ID:

```text
https://example.org/s/HAN2027/online-01/play?pid=<PARTICIPANT_ID>
```

`?participant=` works too. The participant's results folder is `participant_<ID>` and the flow is the same as for Prolific (practice, counted negotiations, questionnaires, timers, `schedule.json`). At the end the *Finish* button opens `completion_url` from `study.yaml` (`{pid}` and `{{variables}}` are filled in); without one, the end page shows `end_text`, or a thank-you with the completion code when the study has one. Participants who log in at `/s/<project>/<study>/app` take part with their account instead.

### Lab

Either create accounts for the participants (`hani2 users add`, or in the admin console) and let them log in at `/s/<project>/<study>/app`, or hand out session codes:

```text
https://example.org/s/HAN2027/lab-kyoto/play?code=<SESSION_CODE>
```

A session code works like an online participant ID. A lab study has no completion link: the end page shows `end_text` (or a thank-you).

## Texts with variables

The consent form, the welcome text (`announcements.md`), the page title and subtitle in `env.json`, the end page (`end_text`), `completion_url` and every text of the per-negotiation questionnaire may contain `{{variables}}`. They are filled per session from the session's project and study:

| Variable | Value |
|---|---|
| `project_name` | The project's short name (its folder name). |
| `project_full_name` | `full_name` in `project.yaml` (else the name). |
| `project_short_description` | `short_description` in `project.yaml`. |
| `project_link` | `link` in `project.yaml`. |
| `project_year` | `year` in `project.yaml`. |
| `study_name` | The study's short name. |
| `study_title` | `title` in `study.yaml` (else the name). |
| `study_type` | `prolific`, `online` or `lab`. |
| `study_link` | `link` in `study.yaml`. |
| `study_year` | `year` in `study.yaml`, else the year of `start`, else the project's year. |
| `organizer` | `organizer` in `study.yaml`, else in `project.yaml`. |
| `contact` | `contact` in `study.yaml`, else in `project.yaml`. |
| `n_required` | Counted negotiations per participant. |
| `minutes` | The expected maximum duration in minutes. |
| `completion_code` | `PROLIFIC_COMPLETION_CODE`, else `completion_code` in `study.yaml`. |
| `project_<key>`, `study_<key>` | Any other key of `project.yaml` / `study.yaml` (and of their defaults / overrides). |

So one consent text can serve every study of a project:

```markdown title="projects/HI2027/consent.md"
# Consent: {{project_full_name}} ({{study_title}})

You will do {{n_required}} negotiations, about {{minutes}} minutes in total.
Questions? Write to {{contact}}.
```

A placeholder HANI2 does not know is left as written, so a typo shows up in the text. Prolific's own placeholders such as `{{%PROLIFIC_PID%}}` are never touched. The admin API previews a text for a study and lists its unknown variables (see [Admin API](#admin-api)).

## Consent per study

With `auth.enforce_consent` on, a logged-in participant consents once per study. HANI2 records, in the user's metadata, which study, when, and a hash of the consent text they accepted. A new study, or a changed consent text, asks again. Consent given before projects existed still counts for the server's default study, so existing users are not asked again there.

Participants who arrive with a Prolific ID, an online participant ID or a session code do not pass through the consent page.

## Results

Every row of `results.csv` and of `negotiation_questionnaires.csv`, every event (`events.db`) and every recording carries `project` and `study` columns. The returning-participant check, the practice round, `prolific_session.json`, `schedule.json` and the opponent rotation all live in the study's `results/` folder, so they never mix across studies. The admin console's results, events and recordings show the server's default study; add `?study=<project>/<study>` to the API calls, or open the admin page at `/s/<project>/<study>/admin` to see a study's results, events and recordings. Settings edited there are saved in the layer chosen at the top of each page (the study by default); see [Layers](admin.md#layers-where-a-setting-is-saved).

## Groups and assignment

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
and [Assistant groups](assistant.md#assistant-groups)). Within a study HANI2 assigns:

- **Assistants** fixed per human and balanced across the study's humans (fewest assigned first,
  ties in pool order; admins and playground guests not counted; drop-outs counted). See
  [Fixed per human, balanced](assistant.md#fixed-per-human-balanced).
- **Opponents** in a balanced Latin-square order over the study's opponent pool, by participant
  index. See [Latin squares](opponents.md#latin-squares).
- **Scenario types** by participant index over the active scenario set; each negotiation takes the
  participant's next slot of that type.

These are the default [scheduling methods](scheduling.md). A study (or its project, for all its
studies) can choose another method per dimension:

```yaml
scheduling:
  opponents: latin_square   # random, cyclic, fixed_order, external
  assistants: balanced      # random_fixed, random_each, round_robin, external
  scenarios: by_participant # set_order, random, latin_square, external
```

`hani2 scheduling list --details` explains each one with examples; `hani2 study create
--opponent-scheduling M --assistant-scheduling M --scenario-scheduling M` sets them. The methods
used are recorded in the `opponent_scheduling`, `assistant_scheduling` and `scenario_scheduling`
columns.

Participants are counted per study (their index is kept in the study's `assignments.json`), so
each study is balanced on its own. A `schedule.json` (and a group file named in the URL) still wins
over all of this. The assigned Assistant, its group and the opponent's group are written to every
results row (`assistant`, `assistant_group`, `assistant_class`, `assistant_error`,
`opponent_group`, plus the three `*_scheduling` columns), to the `scenario_started` event and to
the recordings.

A setting given twice in `study.yaml` or `project.yaml` with different values (at the top level
and again under `overrides:` / `defaults:`) is refused when the file is saved through the admin
API or the command line, and reported (server log, `hani2 study show`, the admin study page's
`errors`) when a hand-edited file has it; the value under `overrides:` / `defaults:` is then used.

## Two ways to run HANI2

**Standalone.** HANI2 runs the whole study: create the project and the study, give out the link it prints, and HANI2 shows the consent form and the questionnaires, assigns scenarios and opponents, and ends with the completion code, the Prolific redirect or a thank-you page.

```bash
hani2 project create HI2027 --kind assistant --full-name "Human-AI Interaction League 2027" --year 2027
hani2 study create HI2027/hi-2027-01 --type prolific --title "January run" --completion-code C1A2B3
hani2 --host 0.0.0.0 --no-browser
```

**Driven by an outside system** (for example a competition website that recruits participants and schedules the opponents). Such a system usually starts one HANI2 process per league with `HANI2_EXPERIMENT=<wave>`, `--root-path`, `--assistant on|off` and `--page play`, sends participants to `<root>/play?PROLIFIC_PID=<pid>&group=<key>`, writes `schedule.json` and `groups/<key>.json` into the results folder and sets `PROLIFIC_*` variables. All of this works unchanged: the wave is the default study of that process, its results stay in `$HANI2_EXPERIMENTS/<wave>/results/prolific_<PID>/` with the same files and columns (new columns are only ever added), and the rule is that **an outside system's explicit input wins**: environment variables, `schedule.json`, group files and query parameters always take precedence over what `project.yaml` and `study.yaml` say. HANI2's own project and study settings only fill in what is not given.

## Command line

```bash
hani2 project create NAME [--full-name TEXT] [--kind opponent|assistant|none] [--description TEXT]
                          [--link URL] [--year N] [--organizer TEXT] [--contact TEXT]
hani2 project list
hani2 project show NAME
hani2 study create PROJECT/STUDY [--type prolific|online|lab] [--title TEXT] [--completion-code CODE]
                                 [--completion-url URL] [--prolific-study-id ID] [--link URL]
                                 [--start DATE] [--end DATE] [--n-required N] [--end-text TEXT] [--base-url URL]
                                 [--opponent-scheduling M] [--assistant-scheduling M] [--scenario-scheduling M]
hani2 study list [PROJECT]
hani2 study show PROJECT/STUDY [--base-url URL]
hani2 --study PROJECT/STUDY         # the default study of this server
hani2 groups list [--project P | --study P/S] [--kind opponent|assistant] [--no-builtin]
hani2 scheduling list [--details]   # the scheduling methods
```

`create` on an existing project or study updates the given fields. `study create` also creates the project when it is missing, and prints the links to give participants. The links start with `--base-url`, else `HANI2_PUBLIC_URL`, else `public_url` in `env.json`, else `http://localhost:5006` plus the root path. A bare study name (`hani2 study create pilot`) is a study of the `default` project.

## Admin API

These JSON endpoints are for admins only. Project, study and group names may contain only letters, digits, `.`, `_` and `-`. The project's group folder of the `default` project is the settings folder.

A layer `L` is `settings`, `project:<P>` or `study:<P>/<S>`; the old `?study=P/S` and `?project=P` are accepted too. Values "in effect at a layer" are computed for that layer, whatever study the request URL is in. A settings write (PUT, PATCH, DELETE) sent from inside a study (`/s/P/S/api/admin/...`) that names no layer is refused with 409, so the console can never silently write the shared settings while it shows a study.

| Endpoint | Does |
|---|---|
| `GET /api/admin/projects` | The projects with their settings and study names, and the server's default study. |
| `GET /api/admin/projects/{project}` | A project: its settings, `project.yaml` as text, and its studies (with participant counts and links). |
| `PUT /api/admin/projects/{project}` | Create or replace `project.yaml`: `{"data": {...}}` or `{"yaml": "..."}`. |
| `GET /api/admin/projects/{project}/studies/{study}` | A study: its settings, `study.yaml` as text, its links. |
| `PUT /api/admin/projects/{project}/studies/{study}` | Create or replace `study.yaml` (the project is created when missing). What the GET adds (`path`, `links`, `participants`, `results_rows`, `scheduling_effective`, `errors`, …) is dropped, so a client may send back what it read; the top-level `scheduling` wins over the copy under `overrides`, and an empty `scheduling` (`{}`) inherits every dimension again (the same holds for a project). |
| `GET /api/admin/layers` | The layers (`settings`, `project:P`, `study:P/S`) with their folders, and the study the request is bound to (`bound`). |
| `GET /api/admin/settings/{kind}?layer=L` | `kind`: `env`, `llm`, `assistant`, `autopilot` or a text (`consent`, `announcements`, `scenario_sets`, `scenario_order`). JSON kinds: `{"own", "effective", "inherited"}` (the layer's own file, the values in effect at that layer, and those without its file). Texts: `{"text", "exists", "effective", "source", "source_path"}` (`source`: the layer the text in effect comes from). The old `?study=P/S` / `?project=P` return the layer's raw file, and no parameter the effective settings, as before. |
| `PATCH /api/admin/settings/{kind}?layer=L` | JSON kinds: merge the body into the layer's own file. |
| `PUT /api/admin/settings/{kind}?layer=L` | Replace the layer's own file (texts: `{"text": "..."}`). Without a layer: the settings folder, as before. |
| `DELETE /api/admin/settings/{kind}?layer=L[&key=a.b]` | Remove one dotted key from the layer's own JSON file, or (without `key`) the layer's own file. |
| `GET` / `PUT /api/admin/pools/{kind}?layer=L` | The opponent or Assistant pool set at a layer (`env.json` `opponents`; `defaults.<kind>s` in project.yaml; `overrides.<kind>s` in study.yaml), what it inherits and what it expands to. PUT `{"items": [...]}` rewrites only that key. |
| `GET /api/admin/projects/{project}/studies/{study}/balance` | The study's Assistant pool and how many counted humans each Assistant has, with every assignment. |
| `/api/admin/library/...` | Scenario types, opponents, Assistants and tools: items, upload, link, remove, groups, the default scenario set, the tools offered and their placement per view. See the [Library API](../reference/library-api.md). |
| `GET /api/admin/scenarios/{name}?layer=L[&scenario=S][&generate=N]` | A type's details: texts, roles, issues and options, sample utilities, its pool. |
| `GET /api/admin/groups?project=P` | The project's opponent and Assistant groups (its folder, its studies, the settings folder and the built-in groups): key, members, `syspath`, description, the group file's `assistant`, source and file. With `?study=P/S` instead: the groups as that study resolves them, `active` marking the file a token resolves to. |
| `GET /api/admin/projects/{project}/groups/{kind}/{key}` | One group file of the project (`kind`: `opponent` or `assistant`, plural accepted). |
| `PUT /api/admin/projects/{project}/groups/{kind}/{key}` | Create or replace it: a list of specs, or `{"description", "syspath", "agents"` (opponents) or `"assistants"`, and for opponent groups `"assistant"}`. Checked before it is written. |
| `DELETE /api/admin/projects/{project}/groups/{kind}/{key}` | Delete it. |
| `GET /api/admin/projects/{project}/studies/{study}/assignments` | The study's `assignments.json`. |
| `POST /api/admin/templates/preview` | `{"text": "...", "study": "P/S"}` or `{"kind": "consent", "study": "P/S"}`: the rendered text, the unknown variables, and every variable with its value. |

## Migrating from experiments

Nothing has to move. An experiment folder `$HANI2_EXPERIMENTS/<name>/` (default `~/negmas/hani2/experiments`) is the study `default/<name>`, read where it is:

| Before | Now |
|---|---|
| `hani2 experiment create NAME` | Still works; the result is the study `default/NAME`. `hani2 study create default/NAME` adds a `study.yaml` to it. |
| `hani2 --experiment NAME`, `HANI2_EXPERIMENT` | Still work: the default study of the server. `hani2 --study default/NAME` is the same. |
| `hani2 experiment list` | Still works; `hani2 study list` shows experiments as `default/<name>`. |
| One process per experiment | Optional: one server reaches every study at `/s/<project>/<study>/`. |
| The `experiment` column of events and recordings | Still filled; `project` and `study` are added. |

To move an experiment into a project, create the study (`hani2 study create HI2027/wave1`) and move the experiment's files into `projects/HI2027/studies/wave1/`, keeping its `results/` folder. Move texts shared by several studies (for example `consent.md`) up to the project folder.
