# Studies and results

This page covers running a study: keeping each study in its own folder, asking questions after every negotiation, and reading what HANI2 records. For paid online studies, see also [Prolific](prolific.md).

!!! tip "Projects and studies"
    One server can run many studies at once, grouped in projects, each reached at its own address
    (`/s/<project>/<study>/play`), with texts that fill in the project's and study's names, and
    consent per study. See [Projects and studies](projects.md). An *experiment*, described below,
    is a study of the built-in `default` project: everything on this page applies to every study.

## Experiments

An *experiment* is a self-contained folder with its own scenarios, texts, questionnaire and results. Running HANI2 with an experiment keeps the data of one study apart from everything else on the server. It is the study `default/<name>` (see [Projects and studies](projects.md#migrating-from-experiments)).

### Creating an experiment

```bash
hani2 experiment create pilot
```

This creates `~/negmas/hani2/experiments/pilot/` (the experiments root is `$HANI2_HOME/experiments`, or the directory in `HANI2_EXPERIMENTS`):

```text
experiments/pilot/
├── consent.md                      # copied from your settings
├── announcements.md                # copied from your settings
├── scenario_order.txt              # copied from your settings
├── questionnaires/
│   └── per_negotiation.yaml        # a working example questionnaire
├── scenarios/                      # a copy of your scenarios directory
└── results/                        # everything the study records
```

The text files are copied from the settings folder (or the bundled defaults), and `scenarios/` is a copy of your current scenarios directory, or of the bundled samples when you have none. Existing files are kept; pass `--force` to overwrite them.

Unlike the settings folder, a new experiment has an active per-negotiation questionnaire. Delete `questionnaires/per_negotiation.yaml` if you do not want one.

### Running an experiment

```bash
hani2 --experiment pilot
# or
HANI2_EXPERIMENT=pilot hani2
```

`hani2 experiment list` shows every experiment and how many participants have results in it. The experiment is the server's default study; every other study is still reachable at `/s/<project>/<study>/`.

### What an experiment changes

While an experiment is active:

- **Settings files.** Any settings file placed in the experiment folder takes priority over the one in the settings folder: `env.json`, `llm_settings.json`, `assistant_settings.json`, `autopilot_settings.json`, `consent.md`, `announcements.md`, `scenario_order.txt` and `scenario_sets.yaml`. For the JSON files, the experiment's file is merged over the settings-folder file, which is merged over the bundled defaults. Files you do not add are read from the settings folder as usual.
- **Scenarios** come from `<experiment>/scenarios`.
- **The questionnaire** comes from `<experiment>/questionnaires/per_negotiation.yaml`.
- **Results** go to `<experiment>/results` instead of `~/negmas/hani2/db`. This includes the per-participant folders, the event log and the agent group files (`results/groups/`).
- **Events** carry the experiment name in their `experiment` column, and the `project` and `study` columns.

User accounts are shared by all experiments.

The same applies to every study of a project, with the project folder as an extra layer between the study and the settings folder (see [Projects and studies](projects.md#settings-files-per-study)).

The admin console always saves to the settings folder (the admin API can also write to a study's or project's folder). If the experiment folder has its own copy of a file (for example `consent.md`), that copy wins and edits made in the admin console do not show up until you edit or delete the copy. See [Configuration reference](configuration.md) for the full precedence rules.

## Per-negotiation questionnaires

A questionnaire can follow every negotiation. It is a YAML file:

```yaml title="per_negotiation.yaml"
version: "1"
title: "After this negotiation"
intro: "Two quick questions before we continue."
questions:
  - id: satisfaction_with_outcome
    text: "How satisfied are you with the **outcome** of this negotiation?"
    type: likert5
    required: true
    labels:
      1: "Not at all"
      5: "Extremely"
  - id: partner_cooperativeness
    text: "How cooperative did your opponent feel?"
    type: select
    required: true
    options: ["Very competitive", "Somewhat competitive", "Neutral", "Somewhat cooperative", "Very cooperative"]
  - id: comments
    text: "Anything else you want to tell us? (optional)"
    type: text
    required: false
```

| Field | Meaning |
|-------|---------|
| `title` | The heading of the form (default "A few questions"). |
| `intro` | A line of text under the heading. |
| `questions` | The questions, in order. A file without questions is ignored. |
| `questions[].id` | The column name in the answers CSV. |
| `questions[].text` | The question, in Markdown. |
| `questions[].type` | One of the types below. |
| `questions[].required` | The participant cannot submit without answering. |
| `questions[].labels` | For Likert questions: labels for the lowest (`1`) and highest (`5` or `7`) points. |
| `questions[].options` | For `select` questions: the choices. |

Question types:

| Type | Shown as | Stored value |
|------|----------|--------------|
| `likert5` | Buttons 1–5 | The number |
| `likert7` | Buttons 1–7 | The number |
| `yes_no` | Yes and No buttons | `yes` or `no` |
| `select` | A drop-down list of `options` | The chosen option |
| `text` | A text area | The text |

### Where the questionnaire is looked up

HANI2 uses the first of these files that exists and has questions:

1. The file in the `HANI2_PER_NEG_YAML` environment variable.
2. The file in the `PROLIFIC_PER_NEG_YAML` environment variable.
3. The questionnaire named by `"questionnaire"` in `env.json`.
4. `<study>/questionnaires/per_negotiation.yaml` (the experiment folder), when a study is active.
5. `<project>/questionnaires/per_negotiation.yaml`, for a study of a project.
6. `~/negmas/hani2/settings/questionnaires/per_negotiation.yaml`.

Every text of the questionnaire (title, intro, questions, labels, options) may use the `{{variables}}` of [Projects and studies](projects.md#texts-with-variables).

Instead of a path, the first three can name a questionnaire: `evaluation` is
`settings/questionnaires/evaluation.yaml`, or the one bundled with HANI2 — the
[evaluation questionnaire](evaluation.md#subjective-metrics) (UEQ, TAM, opponent perception).

Two optional keys per question feed the [subjective metrics](evaluation.md#subjective-metrics):
`scale` (the score the item belongs to; add `reverse: true` for reversed items) and
`requires: support_agent` (ask only when an assistant took part).

`hani2 setup` writes an example to `settings/questionnaires/per_negotiation.example.yaml`. Copy or rename it to `per_negotiation.yaml` to turn the questionnaire on.

### When it is shown

In normal sessions the questionnaire appears after a negotiation in which the participant took at least one action (an offer or an acceptance) and the opponent did not fail. It is never shown in the guest playground. Prolific participants have their own rules (see [Prolific](prolific.md)).

While the questionnaire is open the participant cannot load the next negotiation. Submitting it with a required question unanswered shows a warning.

### Answers

Answers are appended to `<results>/<user>/negotiation_questionnaires.csv`. Each row has these columns, followed by one column per question `id`:

| Column | Meaning |
|--------|---------|
| `mechanism_id` | The negotiation, matching `mechanism_id` in `results.csv`. |
| `scenario` | The scenario name. |
| `agent_type` | The opponent's spec. |
| `practice` | Whether it was a practice round. |
| `shown_at`, `submitted_at` | ISO timestamps. |
| `duration_seconds` | Time spent on the form. |
| `project`, `study` | The study the answers belong to. |

If you add questions during a study, HANI2 rewrites the file with the extra columns and keeps the earlier rows.

## Pre-questionnaire and participant types

A **pre-questionnaire** is shown once to each participant, after their first scenario loads and
before the negotiation can start. Its main use is the **participant type**: one answer (for example
how much negotiating experience they have) is stored with every result of that participant, and
the leaderboard is then also shown **per participant type**. Novices are not ranked against
professional negotiators, and an Assistant can be compared on easy and on hard participants.

It is off unless you configure one. HANI2 uses the first of:

1. the file (or bundled name) in `HANI2_PRE_YAML`;
2. the questionnaire named by `"pre_questionnaire"` in `env.json` (`expertise` is bundled);
3. `<study>/questionnaires/pre_questionnaire.yaml`, then the project's, then
   `settings/questionnaires/pre_questionnaire.yaml`.

It has the same format as the per-negotiation questionnaire, plus a `participant_type` block that
names the question and maps answers to types (an unmapped answer is used as it is):

```yaml
title: "Before you start"
participant_type:
  question: expertise
  map: {"Never": novice, "A few times": novice, "Regularly": experienced, "It is part of my job": expert}
questions:
  - id: expertise
    text: "How often do you negotiate (prices, contracts, salaries, …)?"
    type: select
    required: true
    options: ["Never", "A few times", "Regularly", "It is part of my job"]
```

The answers are saved in the participant's folder as `pre_questionnaire.json` (answers, type,
timestamps, project and study) and in the recording (a `pre_questionnaire` record). They are not
written to `negotiation_questionnaires.csv` and do not feed the subjective metrics. The type is in
the `participant_type` column of every later result. Administrators, playground guests and
[simulated participants](simulation.md) never get the pre-questionnaire. A simulated participant's
type is its persona's difficulty (`simulated-easy`, `simulated-hard`).

## Results

Everything is written under the *results root*: `~/negmas/hani2/db` (`$HANI2_HOME/db`), or `<study>/results` for a session of a study (an experiment's `<experiment>/results`).

```text
<results>/
├── events.db                        # the event log (SQLite)
├── groups/<key>.json                # optional agent group files
└── <user>/                          # one folder per participant
    ├── results.csv                  # one row per negotiation
    ├── logs/<mechanism id>.csv      # the full offer trace
    ├── scenarios/<mechanism id>/    # the scenario exactly as negotiated
    ├── mechanisms/<mechanism id>.json
    ├── negotiation_questionnaires.csv
    ├── last_scenario.txt            # the participant's scenario counter
    └── llm_logs/<mechanism id>.jsonl  # only with HANI2_LLM_LOG=1
```

The folder name is the user name: the account name for logged-in users, `guest_<id>` for each playground browser, `prolific_<PID>` for Prolific participants and `participant_<ID>` for participants of an online or lab study. Playground visitors therefore do not share a folder. Prolific participants have a few extra files, described in [Prolific](prolific.md). For `llm_logs/`, see [Language models](llms.md).

### The trace logs

`logs/<mechanism id>.csv` has one row per action with the columns `index`, `time`, `relative_time`, `step`, `negotiator`, `offer`, `responses`, `state`, `text` and `data`. `text` is the message that came with the offer.

`mechanisms/<mechanism id>.json` records the negotiation protocol settings: `id`, `n_steps`, `time_limit`, `pend`, `pend_per_second`, `step_time_limit`, `negotiator_time_limit`, `end_on_no_response`, `one_offer_per_step` and `n_outcomes`.

### `results.csv` columns

Each finished negotiation adds one row. The columns fall into these groups.

**Scenario selection**

| Column | Meaning |
|--------|---------|
| `index` | The participant's scenario counter for this load. |
| `load_index` | The slot used in the pool (empty for generated scenarios). |
| `load_path` | The scenario folder (empty for generated scenarios). |
| `scenario_name` | The scenario folder name, or the generated scenario's name. |
| `generated` | Whether the scenario was generated on the fly. |
| `scenario_type` | The scenario type (category). |

**Participants**

| Column | Meaning |
|--------|---------|
| `scenario` | The outcome space name. The leaderboard groups by this column. |
| `human_index` | The participant's utility function index. |
| `human_id` | The participant's negotiator name, for example `Seller (You)`. |
| `user` | The user name. |
| `agent_type` | The opponent's spec, for example `BoulwareTBNegotiator`. |

**Outcome**

| Column | Meaning |
|--------|---------|
| `agreement` | The agreed outcome, or empty. |
| `human_utility` | The participant's utility for the agreement (the reservation value without one). |
| `human_advantage` | `(utility − reserved) / (max − reserved)` for the participant. |
| `agent_utility` | The opponent's utility. |
| `welfare` | `human_utility + agent_utility`. |
| `status` | `success`, `broken` (someone ended it), `timedout`, `erred`, `ended` or `agent_failed`. |
| `ended_by` | `human` or `agent`: who ended a broken negotiation, or who accepted the final offer. |
| `agent_error` | The opponent's error, when `status` is `agent_failed`. |
| `ended_at` | When the negotiation ended. |
| `mechanism_name`, `mechanism_id` | The negotiation's identifiers. |

For an agreement, `ended_by` is `human` when the participant accepted and `agent` when the opponent accepted the participant's offer.

**Study bookkeeping**

| Column | Meaning |
|--------|---------|
| `practice` | Whether this was a practice round. |
| `n_human_actions` | How many offers the participant made (at least 1 for an agreement). |

**Timing**

| Column | Meaning |
|--------|---------|
| `load_at`, `start_at` | When the scenario was loaded and when the negotiation started. |
| `load_to_start_seconds` | Time spent on the start screen. |
| `duration_seconds` | Time from start to end. |
| `per_round_times` | A JSON list of the time the participant took for each of their actions, in units of relative time. |

**Interface and assistance**

| Column | Meaning |
|--------|---------|
| `view_mode` | The layout in use at the end (`full`, `simple` or `focus`). |
| `view_source` | `query` when the layout came from the `?view=` URL parameter, else `default`. |
| `user_agent` | The browser's user agent string. |
| `device` / `orientation` | The layout in use (`desktop`, `tablet` or `phone`) and `landscape` or `portrait`. |
| `support_agent` | Whether the Assistant acted (sent a message or changed something) during this negotiation. |
| `autopilot` | Whether the autopilot was switched on during this negotiation. |
| `assistant` | The Assistant assigned for this negotiation (its spec), empty without one. See [Assistant pools and assignment](assistant.md#assistant-pools-and-assignment). |
| `assistant_group` | The Assistant group it came from, if any. |
| `assistant_class` | The class that actually ran (`module.Class`). |
| `assistant_error` | Why the assigned Assistant could not be started, if it failed. |
| `opponent_group` | The opponent group the opponent came from (`?group=`, a single group token), if any. |
| `opponent_scheduling`, `assistant_scheduling`, `scenario_scheduling` | The [scheduling method](scheduling.md#recorded-in-the-results) that chose the opponent, the Assistant and the scenario type (`external` for `schedule.json`, empty when HANI2 did not schedule it). |
| `project`, `study` | The project and study of the session (`default` and an empty study without one). Added after the other columns in files from earlier versions. |

**Final mechanism state.** The fields of the negmas `SAOState` at the end, for example `step`, `time`, `relative_time`, `broken`, `timedout`, `has_error`, `error_details`, `erred_negotiator`, `current_offer`, `current_proposer`, `n_acceptances` and `current_data`.

**Mechanism settings.** The public fields of the negmas negotiator-mechanism interface, for example `n_outcomes`, `n_steps`, `time_limit`, `pend`, `pend_per_second`, `step_time_limit`, `negotiator_time_limit`, `end_on_no_response`, `one_offer_per_step` and `allow_none_with_data`.

**Optimality.** How close the agreement is to the scenario's reference points, from negmas: `pareto_optimality`, `nash_optimality`, `kalai_optimality`, `modified_kalai_optimality`, `max_welfare_optimality`, `ks_optimality` and `modified_ks_optimality`. These are missing when they cannot be computed (for example for continuous outcome spaces).

The exact state and settings columns depend on the installed negmas version. Read the CSV with a tool that matches columns by name, such as pandas.

### Reading results

The admin console shows every row from every participant under *Results*, newest first, with a *Choose columns* picker, a searchable table, a leaderboard and a *Download CSV* button (`/api/admin/results.csv`, all participants in one file). See [Admin console](admin.md).

To analyse results in Python:

```python
from pathlib import Path

import pandas as pd

root = Path.home() / "negmas" / "hani2" / "db"
df = pd.concat(pd.read_csv(f) for f in root.glob("*/results.csv"))
print(df.groupby("agent_type")["human_utility"].mean())
```

The leaderboard score of a participant is computed per scenario name: drop the worst result, average the best three of the rest, and score 0 for scenarios with fewer than two results. The score is the average over scenarios, times 100.

The leaderboard ranks human participants only and also comes stratified by `participant_type`
(from the [pre-questionnaire](#pre-questionnaire-and-participant-types)). Rows with
`mode = simulated` (users `sim_…`, see [Simulated participants](simulation.md)) are never ranked
with them. They have their own *Qualifying round* table, per Assistant and persona, with the goal
rate and pass^k. Rows written before the `mode` column existed count as human.

Five columns say who sat in the human seat: `mode` (`main`, `guest`, `simulated`, …),
`participant_type`, and for simulated participants `persona`, `goal_met` (a deal worth at least
the persona's reservation value) and `sim_invalid` (why the trial does not count, empty when it
does).

## The event log

HANI2 records what happens in an append-only SQLite database, `<results>/events.db`. Logging never interrupts the application; failures are printed to the server log. Set `HANI2_EVENTS=0` to switch it off.

The database has two tables:

- `events`: `id`, `session_id`, `user`, `experiment`, `event_type`, `timestamp` (UTC, ISO format), `component`, `action`, `value` (JSON), `scenario_id`, `round_number`, `utility_value`, `duration_ms`, `project` and `study`.
- `sessions`: one row per browser session, with `id`, `user`, `experiment`, `mode`, `start_time`, `end_time`, `ip`, `user_agent`, `project` and `study`.

An events database from an earlier version gets the `project` and `study` columns the first time HANI2 opens it.

The server writes these event types:

| `event_type` | When | Notable fields |
|--------------|------|----------------|
| `session_start` | A session is created. | `value.mode` |
| `login`, `logout`, `login_failed` | Password or OAuth sign-in and sign-out. | `user`; `value.oauth` for OAuth |
| `scenario_loaded` | A scenario is loaded. | `scenario_id` |
| `scenario_started` | A negotiation starts. | `value.partner` (wire name, the old name of the opponent) |
| `counter_offer` | The participant sends an offer. | `value.offer`, `value.text`, `utility_value` |
| `offer_accepted` | The participant accepts. | `utility_value`, `round_number` |
| `negotiation_ended` | The participant clicks End (`action` = `end_by_human`), and again when any negotiation finishes (`value` holds the summary). | `utility_value` |
| `tool_interaction` | The participant uses a tool. | `component` (tool name), `action` (`input:<field>` or the action name) |
| `tab_changed` | The participant switches tool tab. | `component` |
| `support_agent` | The participant chats with the assistant, or the assistant acts. | `component`, `action`, `value` |

`session_id` is the session key: `main:<user>`, `guest:<id>` or `prolific:<PID>`.

You can query the database directly:

```bash
sqlite3 ~/negmas/hani2/db/events.db \
  "select event_type, count(*) from events group by event_type"
```

### Event analytics in the admin console

The *Event analytics* section of the admin console shows:

- a bar chart of events by type,
- a chart of activity per hour (the last 168 hours with events),
- a searchable table of the latest 2000 events, filtered by user, event type and date range,
- recent sessions,
- an *Export CSV* button that downloads the whole `events` table (`/api/admin/events.csv`).

The same data is available from the API at `/api/admin/events` (parameters `user`, `session_id`, `types` as a comma-separated list, `since`, `until`, `limit`, `offset`) and `/api/admin/events/summary`. Both need an admin login.
