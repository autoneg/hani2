# Study management

A study is one data collection inside a [project](project-management.md), with its own results. This page covers running a study: its type and its links, what it overrides, how it assigns Assistants, opponents and scenarios, the questions asked after every negotiation, and what HANI2 records. For paid online studies, see also [Prolific](prolific.md).

## A study's life

1. **Create** the study: `hani2 study create PROJECT/STUDY` (or **New study** on the admin console's [Projects & Studies](admin.md#projects-studies) page). It prints the links to give participants. The project is created when it is missing.
2. **Configure** it: `study.yaml` and its overrides of the project's defaults (see [`study.yaml` and overrides](#studyyaml-and-overrides)), its texts and forms (see [Forms and questionnaires](#forms-and-questionnaires)) and how it assigns Assistants, opponents and scenarios (see [Assigning Assistants, opponents and scenarios](#assigning-assistants-opponents-and-scenarios)).
3. **Test** it: open the participant link yourself (for a Prolific study, see [Testing locally](prolific.md#testing-locally)), and try a negotiation between two people on one machine with [`hani2 human-trial`](../getting-started/cli.md#hani2-human-trial).
4. **Run** it: start the server (`hani2 --study PROJECT/STUDY` makes it the server's default study) and give out the link.
5. **Monitor** it: see [Monitoring](#monitoring).
6. **Close** it: stop giving out the link. `start` and `end` in `study.yaml` record the study's dates, and its results stay in its own folder (see [Results](#results)).

## Study types

A study's *type* is `prolific`, `online` or `lab`. Every type keeps its files in the study's folder (see [Folder layout](project-management.md#folder-layout)) and is reached at its own addresses.

### URLs

Each study has its own pages:

| URL | Page |
|---|---|
| `/s/<project>/<study>/play` | The playground and the participant entry (`?PROLIFIC_PID=`, `?pid=`, `?code=`). |
| `/s/<project>/<study>/app` | The main app (log in), for example for a lab study with accounts. |
| `/s/<project>/<study>/login`, `/admin`, … | Every other page, within the study. |

Everything a page does from there (sign-in, consent, the negotiation channel) stays in that study. `?study=<project>/<study>` on any page moves it to the study's address, and API calls accept `?study=` too. A URL naming a study that does not exist gets *404*.

`/play` and `/app` without a study use the server's *default study*: the one given with `hani2 --study <project>/<study>` (`HANI2_STUDY`), or with the old `--experiment <name>` (`HANI2_EXPERIMENT`, a study of the `default` project). Without either, results go to `$HANI2_HOME/db` as always.

Behind a reverse proxy, the study path comes after the mount path: `https://example.org/hani/s/HI2027/hi-2027-01/play` with `hani2 --root-path /hani`.

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

### Texts with variables

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

A placeholder HANI2 does not know is left as written, so a typo shows up in the text. Prolific's own placeholders such as `{{%PROLIFIC_PID%}}` are never touched. The admin API previews a text for a study and lists its unknown variables (see [Admin API](project-management.md#admin-api)).

### Consent per study

With `auth.enforce_consent` on, a logged-in participant consents once per study. HANI2 records, in the user's metadata, which study, when, and a hash of the consent text they accepted. A new study, or a changed consent text, asks again. Consent given before projects existed still counts for the server's default study, so existing users are not asked again there.

Participants who arrive with a Prolific ID, an online participant ID or a session code do not pass through the consent page. To ask them for consent in the session itself, switch on `auth.participant_consent` for the project or study (see [Study forms](study-forms.md#consent-for-study-participants)).

## `study.yaml` and overrides

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

A setting given twice in `study.yaml` or `project.yaml` with different values (at the top level
and again under `overrides:` / `defaults:`) is refused when the file is saved through the admin
API or the command line, and reported (server log, `hani2 study show`, the admin study page's
`errors`) when a hand-edited file has it; the value under `overrides:` / `defaults:` is then used.

### Settings files per study

Every settings file is looked up per session, first match wins:

1. the study folder,
2. the project folder (the `default` project has none: its layer is the settings folder),
3. the settings folder (`$HANI2_HOME/settings`),
4. the defaults bundled with HANI2.

JSON files (`env.json`, `assistant_settings.json`, …) are merged in the same layers, so a study's `env.json` only needs the keys it changes. Scenarios come from the study's `scenarios/`, then `HANI2_SCENARIOS_BASE`, then the project's `scenarios/`, then the settings folder. The questionnaire after each negotiation comes from `questionnaires/per_negotiation.yaml` in the study and then the project folder (after the environment variables and `env.json`, see [Where the questionnaire is looked up](#where-the-questionnaire-is-looked-up)).

User accounts are shared by all studies.

## Assigning Assistants, opponents and scenarios

Within a study HANI2 assigns, from the pools the study inherits from its project (see [Pools of opponents and Assistants](project-management.md#pools-of-opponents-and-assistants)):

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

The full rules of every method are in [Scheduling methods](scheduling.md).

## Forms and questionnaires

A study can ask for consent and show a pre-questionnaire, a questionnaire after every negotiation and a post-session questionnaire. [Study forms](study-forms.md) describes all of them and how the admin console edits them; the per-negotiation questionnaire and the pre-questionnaire are described in full below.

### Per-negotiation questionnaires

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

Likert and yes/no questions start with nothing selected, so the participant must pick an answer to a required one.

#### Where the questionnaire is looked up

A study (or project) with `questionnaires: false` in `study.yaml` / `project.yaml`, or `"questionnaires": false` in its `env.json`, shows no questionnaire at all: no pre-questionnaire, no per-negotiation one and no post-session one, whatever the environment variables below name.

Otherwise HANI2 uses the first of these files that exists and has questions (a file with `enabled: false` switches the questionnaire off and ends the search; see [Study forms](study-forms.md#switching-a-form-off)):

1. The file in the `HANI2_PER_NEG_YAML` environment variable.
2. The file in the `PROLIFIC_PER_NEG_YAML` environment variable.
3. The questionnaire named by `"questionnaire"` in `env.json`.
4. `<study>/questionnaires/per_negotiation.yaml` (the experiment folder), when a study is active.
5. `<project>/questionnaires/per_negotiation.yaml`, for a study of a project.
6. `~/negmas/hani2/settings/questionnaires/per_negotiation.yaml`.

Every text of the questionnaire (title, intro, questions, labels, options) may use the [`{{variables}}`](#texts-with-variables) of the study's texts.

Instead of a path, the first three can name a questionnaire: `evaluation` is
`settings/questionnaires/evaluation.yaml`, or the one bundled with HANI2 — the
[evaluation questionnaire](evaluation.md#subjective-metrics) (UEQ, TAM, opponent perception).

Two optional keys per question feed the [subjective metrics](evaluation.md#subjective-metrics):
`scale` (the score the item belongs to; add `reverse: true` for reversed items) and
`requires: support_agent` (ask only when an assistant took part).

`hani2 setup` writes an example to `settings/questionnaires/per_negotiation.example.yaml`. Copy or rename it to `per_negotiation.yaml` to turn the questionnaire on.

The admin console edits the questionnaire of every layer on the **Study forms** page, which also adds complete predefined questionnaires (UEQ, TAM, the Subjective Value Inventory, NASA-TLX, SUS, …) to a form. A post-session questionnaire and consent for Prolific participants are described in [Study forms](study-forms.md).

#### When it is shown

In normal sessions the questionnaire appears after a negotiation in which the participant took at least one action (an offer or an acceptance) and the opponent did not fail. It is never shown in the guest playground. Prolific participants have their own rules (see [Prolific](prolific.md)).

While the questionnaire is open the participant cannot load the next negotiation. Submitting it with a required question unanswered shows a warning.

#### Answers

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

### Pre-questionnaire and participant types

A **pre-questionnaire** is shown once to each participant, after their first scenario loads and
before the negotiation can start. Its main use is the **participant type**: one answer (for example
how much negotiating experience they have) is stored with every result of that participant, and
the leaderboard is then also shown **per participant type**. Novices are not ranked against
professional negotiators, and an Assistant can be compared on easy and on hard participants.

It is off unless you configure one. HANI2 uses the first of:

1. the file (or bundled name) in `HANI2_PRE_YAML`;
2. the questionnaire named by `"pre_questionnaire"` in `env.json` (`expertise` is bundled);
3. `<study>/questionnaires/pre_questionnaire.yaml`, then the project's, then
   `settings/questionnaires/pre_questionnaire.yaml` (`enabled: false` in one of them switches it
   off, see [Study forms](study-forms.md#switching-a-form-off)).

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

## Monitoring

- The admin console's study page (**Projects & Studies**, then the study) shows the number of participants and of recorded negotiations, how many counted humans each Assistant of the pool has, and every assignment (see [Admin console](admin.md#projects-studies)).
- Open the console at `/s/<project>/<study>/admin` (or use **Open in this study**) to see the study's results, events and recordings.
- `GET /api/admin/projects/{project}/studies/{study}/balance` and `.../assignments` return the same as JSON (see [Admin API](#admin-api)).

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

### Results per study

Every row of `results.csv` and of `negotiation_questionnaires.csv`, every event (`events.db`) and every recording carries `project` and `study` columns. The returning-participant check, the practice round, `prolific_session.json`, `schedule.json` and the opponent rotation all live in the study's `results/` folder, so they never mix across studies. The admin console's results, events and recordings show the server's default study; add `?study=<project>/<study>` to the API calls, or open the admin page at `/s/<project>/<study>/admin` to see a study's results, events and recordings. Settings edited there are saved in the layer chosen at the top of each page (the study by default); see [Layers](admin.md#layers-where-a-setting-is-saved).

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
| `assistant_condition` | `on` (an Assistant ran), `none` (the no-Assistant arm), `off` (switched off in the settings) or `error`. See [Ablations](ablations.md). |
| `oracle` | Whether the Assistant knew the opponent's utility function (the `opponent_utility` capability). |
| `opponent_info_tools` | Whether the participant's tools could show the opponent's utilities (admins, or `tools.show_opponent_utility`). |
| `autopilot_driver` | Who drove the seat when autopilot was used (`Assistant` or a negotiator); empty otherwise. |
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

### The event log

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

#### Event analytics in the admin console

The *Event analytics* section of the admin console shows:

- a bar chart of events by type,
- a chart of activity per hour (the last 168 hours with events),
- a searchable table of the latest 2000 events, filtered by user, event type and date range,
- recent sessions,
- an *Export CSV* button that downloads the whole `events` table (`/api/admin/events.csv`).

The same data is available from the API at `/api/admin/events` (parameters `user`, `session_id`, `types` as a comma-separated list, `since`, `until`, `limit`, `offset`) and `/api/admin/events/summary`. Both need an admin login.

## Experiments

An *experiment* is a self-contained folder with its own scenarios, texts, questionnaire and results. Running HANI2 with an experiment keeps the data of one study apart from everything else on the server. It is the study `default/<name>` (see [Migrating from experiments](#migrating-from-experiments)).

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

The same applies to every study of a project, with the project folder as an extra layer between the study and the settings folder (see [Settings files per study](#settings-files-per-study)).

The admin console always saves to the settings folder (the admin API can also write to a study's or project's folder). If the experiment folder has its own copy of a file (for example `consent.md`), that copy wins and edits made in the admin console do not show up until you edit or delete the copy. See [Configuration reference](configuration.md) for the full precedence rules.

### Migrating from experiments

Nothing has to move. An experiment folder `$HANI2_EXPERIMENTS/<name>/` (default `~/negmas/hani2/experiments`) is the study `default/<name>`, read where it is:

| Before | Now |
|---|---|
| `hani2 experiment create NAME` | Still works; the result is the study `default/NAME`. `hani2 study create default/NAME` adds a `study.yaml` to it. |
| `hani2 --experiment NAME`, `HANI2_EXPERIMENT` | Still work: the default study of the server. `hani2 --study default/NAME` is the same. |
| `hani2 experiment list` | Still works; `hani2 study list` shows experiments as `default/<name>`. |
| One process per experiment | Optional: one server reaches every study at `/s/<project>/<study>/`. |
| The `experiment` column of events and recordings | Still filled; `project` and `study` are added. |

To move an experiment into a project, create the study (`hani2 study create HI2027/wave1`) and move the experiment's files into `projects/HI2027/studies/wave1/`, keeping its `results/` folder. Move texts shared by several studies (for example `consent.md`) up to the project folder.

## Command line and admin API

### Command line

```bash
hani2 study create PROJECT/STUDY [--type prolific|online|lab] [--title TEXT] [--completion-code CODE]
                                 [--completion-url URL] [--prolific-study-id ID] [--link URL]
                                 [--start DATE] [--end DATE] [--n-required N] [--end-text TEXT] [--base-url URL]
                                 [--opponent-scheduling M] [--assistant-scheduling M] [--scenario-scheduling M]
hani2 study list [PROJECT]
hani2 study show PROJECT/STUDY [--base-url URL]
hani2 --study PROJECT/STUDY         # the default study of this server
hani2 experiment create|list ...    # see Experiments above
```

`create` on an existing study updates the given fields. `study create` also creates the project when it is missing, and prints the links to give participants. The links start with `--base-url`, else `HANI2_PUBLIC_URL`, else `public_url` in `env.json`, else `http://localhost:5006` plus the root path. A bare study name (`hani2 study create pilot`) is a study of the `default` project.

The commands for projects, groups and scheduling methods are in [Project management](project-management.md#command-line).

### Admin API

These JSON endpoints are for admins only; the conventions (names, layers) are those of the [project admin API](project-management.md#admin-api).

| Endpoint | Does |
|---|---|
| `GET /api/admin/projects/{project}/studies/{study}` | A study: its settings, `study.yaml` as text, its links. |
| `PUT /api/admin/projects/{project}/studies/{study}` | Create or replace `study.yaml` (the project is created when missing). What the GET adds (`path`, `links`, `participants`, `results_rows`, `scheduling_effective`, `errors`, …) is dropped, so a client may send back what it read; the top-level `scheduling` wins over the copy under `overrides`, and an empty `scheduling` (`{}`) inherits every dimension again (the same holds for a project). |
| `GET /api/admin/projects/{project}/studies/{study}/balance` | The study's Assistant pool and how many counted humans each Assistant has, with every assignment. |
| `GET /api/admin/projects/{project}/studies/{study}/assignments` | The study's `assignments.json`. |
