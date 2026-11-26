# Admin console

The admin console at `/admin` is laid out like a system settings window: a sidebar on the left with a search field and the pages in groups, and the chosen page on the right. Every page is a list of rounded groups; each row has a label and a short hint on the left and its control (a switch, a pop-up menu, a number with − / + buttons, a text field) on the right. Rows with a `›` open a sub-page, with a back button and a path ("Projects & Studies › HI2027 › hi-2027-01") in the title bar. Administrators also get extra controls on the negotiation page itself, described at the end of this page.

![The admin console: the sidebar and the Opponents page](../assets/screens/admin.png)

## Access

Open `http://localhost:5006/admin`, or choose **Administration** in the account menu of the negotiation page. If you are not logged in, the console sends you to the login page and back. A logged-in user who is not an administrator sees "This page is for administrators."

A user is an administrator when any of these is true:

- the username is `admin`;
- the account has the role `admin` (`hani2 users add --admin`, the **Administrator** switch when adding a user, or **Make admin** on the Users page);
- the account's email is listed in `admin.emails` in `env.json` (useful for OAuth sign-in).

See [Authentication](authentication.md). The `?admin=1` query parameter does nothing for a non-admin and does not open the console; see [the interface](interface.md).

## Pages

| Group | Page | What it holds |
|---|---|---|
| Activity | Live sessions | The sessions on this server, refreshed every five seconds. |
| | Results | Every negotiation, the leaderboard and the results CSV. |
| | Event analytics | Charts and a filterable event log, recorded sessions, the events CSV. |
| | Replay | Opens [Replay](recordings.md). |
| Studies | Projects & Studies | Projects, their studies, `project.yaml` and `study.yaml`, the links to give participants, results counts and the Assistant balance. |
| | Texts | The welcome text, the consent form, the scenario sets and the custom order, per layer, with a live preview. |
| | Study forms | Consent for study participants, and the pre, per-negotiation and post-session questionnaires, per layer, with predefined questionnaires and a live preview. |
| Library | Scenarios | Every scenario type, its details, new ones by upload or link, and the scenario sets. |
| | Opponents | Opponent groups and their members, your own opponent classes, and the pool participants face. |
| | Assistants | Assistant groups, your own Assistant classes, the pool participants get, and the balance per study. |
| | Tools | Tool groups, the tools sessions are offered, where each tool goes in each view, and your own tools. |
| Server | General | Title, public address, sign-in and OAuth (`env.json`). |
| | Negotiation | Timing, negotiation rules, scenarios and opponents of every session (`env.json` → `negotiation`), per layer. |
| | Participant interface | What participants may change themselves, the defaults of their settings, moving tools, notifications (`env.json` → `interface`), per layer. |
| | Tool settings | Which tools exist and to whom they go (`env.json` → `tools`). |
| | Language model | `llm_settings.json`. |
| | Assistant settings | `assistant_settings.json`. |
| | Autopilot | `autopilot_settings.json`. |
| Language models | Connections | Connections to model providers and agent harnesses (API keys, local servers): status, test, remove; the harnesses, the providers and their sign-in methods. Settings folder only. |
| | Models | The model chains per purpose, per layer: reorder, duplicate, parameters, test an entry, test the chains. |
| Accounts | Users | Add users, make admins, set passwords, delete. |

The sidebar ends with **Replay recordings** and **Back to negotiating**. The page is kept in the URL fragment, so `/admin#results` opens the results directly; a fragment may also name a row (`/admin#opponents/opponent-pool`). The fragments of earlier versions still work (`#server` opens General, `#agent` Assistant settings, `#tools` Tool settings).

On a narrow screen (a phone) the sidebar is a page of its own: pick a page to open it, and the back button at the top left returns to the list.

### Search

Type in the search field at the top of the sidebar (or press ⌘F / Ctrl+F). The sidebar then lists every setting whose label, hint or file key contains all the words you typed, across all pages, with the page each one is on: "temperature" finds the temperature of the language model and of the Assistant, "consent" the consent switch and the consent form. Press Enter for the first result, or the arrow keys to move through them. Choosing a result opens its page, scrolls to the row, highlights it briefly and puts the keyboard focus on its control. The search also covers the tools and the Assistant's abilities, which come from the server.

The whole console works with the keyboard: Tab moves between controls, the arrow keys move through the sidebar, Space toggles a switch, and Escape clears the search.

## Layers: where a setting is saved

A setting can live in three places, called layers:

- **All projects (settings folder)**: `$HANI2_HOME/settings` (default `~/negmas/hani2/settings`), shared by every project and study;
- **a project**: `projects/<project>/`, for every study of that project;
- **a study**: the study's folder, for that study only.

A session reads each file from its study first, then its project, then the [start-time settings file](configuration.md#start-time-settings-file) when the server was started with `--settings`, then the settings folder, then the bundled defaults (see [Configuration reference](configuration.md)). With a start-time file, the **All projects** layer says so: the values shown there include it, and what it sets wins over what you save in the settings folder (projects and studies still win over it).

Pages whose settings can live in a layer start with an **Edit and save in** bar. Pick the layer there; it stays chosen while you move between pages. The page then shows the values in effect *at that layer*, and **Save** writes only the values you changed, and only into that layer's own file. A row whose value is set in the chosen project or study layer is marked **set here**; its ↺ button removes it from that layer, so the inherited value applies again. The bar at the bottom always says where the next save goes.

When the console is opened inside a study (`/s/<project>/<study>/admin`), it starts with that study's layer chosen, and the bar names the study. It never saves to another layer behind your back: every read and write names its layer explicitly. (The API refuses a settings write that names no layer from inside a study; see the [admin API](project-management.md#admin-api).)

General and Connections are the exceptions: sign-in, identity and the model connections apply to the whole server and are always saved in the settings folder.

Saved settings apply to sessions created after saving. Sessions already open keep their settings.

## Live sessions

Four figures (open sessions, sessions negotiating now, sessions recorded in the event log, logged events) and a searchable table of every session the server holds in memory:

| Column | Meaning |
| --- | --- |
| `user` | The user name (`guest_<id>` for playground visitors, `prolific_<PID>` for Prolific participants) |
| `mode` | `main` (`/app`) or `guest` (`/play`) |
| `phase` | `idle`, `ready`, `starting`, `running`, `ended`, `questionnaire` or `finished` |
| `round` | Negotiations started in this session |
| `scenario` | The loaded scenario |
| `opponent` | The opponent type of the latest negotiation |
| `support_agent` | The Assistant of the session |
| `connections` | Open browser tabs |
| `idle` | Seconds since the last message from the browser |

The server removes sessions that have no open tab, are not negotiating, and have been idle for more than six hours (it checks every ten minutes).

## Results

**Download CSV** (`/api/admin/results.csv`, saved as `hani2_results.csv`), the **Leaderboard** of human participants (`user`, `participant_type`, `score`, `negotiations`, `mean_utility`; practice rounds left out) when there is anything to rank, the leaderboard **by participant type** when there are several types (see [Pre-questionnaire and participant types](study-management.md#pre-questionnaire-and-participant-types)), the **Qualifying round** of [simulated participants](simulation.md) (never ranked with humans), and a searchable table of every negotiation, newest first. **Choose columns** picks the columns to show; it starts with the default columns plus `user`. Utilities and the human advantage are shown as percentages. The console shows the results of the server's default study; open it at `/s/<project>/<study>/admin` (or use **Open in this study** on a study's page) for another study. [Results](study-management.md#results) describes the files and their columns.

## Event analytics

- **Events by type** and **Activity over time (per hour)** charts.
- **Filter events**: user, event type, from date, until date, and **Apply**.
- A searchable event table (up to 2000 rows) with `timestamp`, `user`, `event_type`, `component`, `action`, `value`, `scenario_id` and `utility_value`.
- **Recorded sessions**: start and end time, user, mode, project, study and browser of the latest 200 sessions.
- **Export CSV** downloads every event (`/api/admin/events.csv`, saved as `hani2_events.csv`).

## Projects & Studies

The list shows every project with its full name, kind, year and number of studies, and **New project** creates one. Open a project to edit `project.yaml`.

Every choice whose meaning is not plain has a **?** after its name. It opens a dialog that explains the choice, with tables and formulas where they help; the same texts are collected in the [Settings reference](settings-reference.md). Rows whose meaning is plain (full name, link, start and end, year, organizer, contact, the time limits) have none.

![The project editor: the ? dialog of the Mode row](../assets/screens/editor-help.png)

- **Project**: full name, short description, link, year, kind (research, opponents evaluated, Assistants evaluated), organizer and contact. The hint of each row names the [text variable](study-management.md#texts-with-variables) it fills.
- **Defaults for its studies**:
    - **Mode** (Solo, Paired, Mixed, or derived from the opponents when unset). When the mode and the opponent pool disagree, a red note under the row says why, and **Save** is refused until they agree. In a HAN project, Paired shows the note "tests no HAN agent; its results are not ranked".
    - **HAN agents** (not shown for Paired): pick a year and a set (all, qualified, finalists, winners) and **Add** writes `:han<year>-<set>` into the layer's opponent pool. "This year" and "last year" are labels computed from the project's **Year**; a year that no source covers is greyed out ("no agents for 2025").
    - the scenario set, counted negotiations (`n_required`), practice round, practice and counted time limits, time limit, rounds, expected minutes, the participant's role rule and preferred roles, and what the participant and the Assistant each know. An empty field keeps the default.
- **Pairing** (only for Paired and Mixed): where people meet, how a match is formed, the slack, the scenario in a cell, same-Assistant matches, what happens when nobody fits and the fallback opponents. Each empty field shows the value in effect.
- **Scheduling**: how opponents, Assistants and scenarios are assigned to each human (`scheduling` in the file), from the server's [scheduling methods](scheduling.md). Each row shows the method in use and a one-line summary; a method chosen here is marked *set here*, and the first entry of the menu inherits it again. The `?` of each dimension lists its methods. **K of N** compares the counted negotiations ($K$) with the number of Assistants in the pool ($N$), and turns orange when $K > N$ under a method that promises each Assistant at most once while repeats are off, since saving is then refused. **Repeats** sets `assistant_repeats` (may a person get the same Assistant twice?) and **Crossing** sets `cross` (`shift` crosses the Assistants with the opponents; the hint says whether it applies to the methods chosen). **About these methods** opens a page that explains every method with its formulas, examples, advantages and disadvantages.
- **Scores**: every score of the project. Built-in scores are read-only, and **Duplicate** copies one into the file; your own scores have **Edit** and **Remove**. **New score** opens the score builder (below). Score changes are saved at once.
- **Scores enabled**: which scores the boards, results views and exports compute and show. **Choose here** starts from the scores in effect; the reset button goes back to the default. This one is saved with the page.
- **Custom variables**: any other key of the file, used in texts as `{{project_<key>}}`. Add and remove them here; saving keeps every key, including those the console has no field for.
- **Studies**, with **New study** (a name and a type).

Open a study to see and edit:

- **Participant links** with copy buttons: the Prolific study URL (with Prolific's `{{%PROLIFIC_PID%}}` placeholders), the participant link of an online study, the session link of a lab study, and the play and app links. The address comes from **Public address** on the General page (or `HANI2_PUBLIC_URL`).
- **Results**: the number of participants and of recorded negotiations, and **Open in this study**.
- **Assistant balance**: how many counted humans each Assistant of the pool has, and every assignment.
- **Study**: type, title, link, year, start and end dates, organizer, contact; **Completion**: Prolific study id, completion code, completion URL and the end text.
- **Overrides of the project's defaults** (the same rows as the project's, Mode and HAN agents included; empty: the project's value), **Pairing**, **Scheduling** (each dimension shows the method the study uses; empty: the project's choice, else the server default), **Scores** (the project's and the study's: a project score can be **redefined here**), **Scores enabled** and **Custom variables** (`{{study_<key>}}`). Problems in `study.yaml` (an unknown scheduling method, a setting given twice) are shown at the top of the page.

**Save** writes `project.yaml` or `study.yaml`. A file the checks refuse (for example a mode that contradicts the pool) is not written, and the message names what to fix. See [Project management](project-management.md) and [Study management](study-management.md).

### The score builder

![The score builder: three components, their weights summing to 100 %, and the criteria picker](../assets/screens/editor-score-builder.png)

- **Key**, title, description, **Track** (`hi`, `han`, `any`), **Missing values** and **Minimum coverage**.
- **Components**: one row per criterion, with its weight in %, its direction and its normaliser. Both start from the criterion's own (*Preset*); a criterion that has no direction says **Direction: choose**, and the score cannot be saved until one is chosen. A normaliser can be replaced, with its bounds or scale.
- The **running sum** of the weights is green at 100 %. **Save score** works only then; **Normalise** rescales the weights to 100 % keeping their proportions.
- **Add criteria**: a searchable list of every criterion of the catalogue, grouped by source (measured, judged, questionnaire scales, the items and scales of the project's own forms, scores). Each shows its direction, its default normaliser and its cost; **Show coverage in the current games** adds the share of the games that have a value. Criteria that cannot be used are greyed out with the reason, for example a post-session answer in an HI score when participants used several Assistants.

Saving sends the weights as fractions summing to 1 (`PUT /api/admin/projects/{project}/scores/{key}`, or `.../studies/{study}/scores/{key}`); the server checks the definition again. After a save, the weights in effect are listed with the score.

## Texts

Pick the layer and one of **Welcome text** (`announcements.md`), **Consent form** (`consent.md`), **Scenario sets** (`scenario_sets.yaml`) and **Custom order** (`scenario_order.txt`, one scenario type per line: the `Custom` set).

- **Source** says which layer the text in effect comes from and whether the chosen layer has its own file. Without one, the editor starts with the inherited text, and **Save** creates the layer's own copy; **Use the inherited text** deletes the layer's copy again.
- **Preview** (welcome text and consent form) renders the text as Markdown with the [text variables](study-management.md#texts-with-variables) filled in, as a participant of the chosen study would see it; at the settings or project layer, pick the study to preview with. Unknown `{{variables}}` are listed above the preview and left as written.
- **Available variables** lists every variable with its value for the preview, with a copy button.
- **In effect for a study** shows, for any study, which layer each of the four texts comes from.

Consent is recorded per study (see [Consent per study](study-management.md#consent-per-study)).

## Study forms

Pick the layer, then:

- **Consent.** *Ask study participants for consent* (`auth.participant_consent` in the layer's `env.json`) shows the consent form to Prolific and online / lab participants before their first negotiation. The reset button removes the layer's own value.
- **Form.** One of **Pre-questionnaire**, **After each negotiation** and **Post-session**.
- **In effect here** says whether the form is on (and how many questions it has), switched off or not set up, and where it comes from: this layer, a layer above, or an environment variable or `env.json` name that wins over every file (shown as a warning). **Copy the inherited form** starts this layer's own file from the inherited one, **Switch off here** writes `enabled: false`, and **Remove this layer's file** goes back to the inherited form.
- **Add predefined questionnaires** lists the predefined question sets for the form (UEQ, UEQ-S, TAM, trust in automation, the Subjective Value Inventory, NASA-TLX, SUS, demographics, …) with their description, source and items; tick sets and **Add** them to the editor.
- The editor holds the layer's YAML file. **Preview** shows the form as participants see it, and lists any problems; **Save** refuses a file with problems.

See [Study forms](study-forms.md).

## The library pages: Scenarios, Opponents, Assistants and Tools

The four library pages share one explorer and the [library](library.md) behind it (the admin API
under `/api/admin/library`, see the [Library API](../reference/library-api.md)). Each page has,
for the layer picked at the top:

- **Groups** (scenario sets on the Scenarios page): your groups first, then those inherited from a
  less specific layer, then the built-in ones, each with what it is, where it is defined and how
  many items it holds after composition. Open a group to edit it: add an item or another group
  (`@name`, which includes everything in it, in place; `:name` still works), remove entries, and
  (scenario sets) move them up or down. **Members after composition** lists what the group
  expands to, with duplicates dropped and cycles broken. **Save** writes the group at the chosen
  layer only; a group of the same name at a less specific layer is shadowed, not changed. A group
  of another layer is read-only here, and **Copy into** saves it at the chosen layer, where it
  then replaces the other one. Built-in groups cannot be changed. When a saved group names an
  unknown group or item, a class that does not load, or forms a cycle, it is saved anyway and the
  console lists the warnings. **New group** creates one. Click an entry (or its arrow) to go
  forward: an item opens the same details page as in the item list, a group lists its members.
  **Back** returns to the group with any unsaved changes intact.
- The page's own sections: the default scenario set, the pools, the tools offered and their
  placement (below).
- **Add**: upload a file or link a path, at the chosen layer.
    - **Upload** a `.zip` (scenarios: one scenario folder, `<Type>.yml` plus one file per role, or a
      category of them) or a `.py` file (opponents, Assistants, tools). HANI2 checks it before it
      keeps anything: only plain files with safe relative paths (no `..`, absolute paths or
      symbolic links), at most 5000 entries and 200 MB unpacked, at most 100 MB uploaded; every scenario must pass `hani2 scenario check`, and every class must load
      the way HANI2 will load it. A scenario type's name must not equal or start like a registered
      type, because a scenario finds its display by that name.
    - **Link** an absolute path on the server (a scenario folder or category; a `.py` file or a
      package folder) or a class spec (`pkg.module:Class`), read in place. **Import path** adds
      folders to Python's import path for a class spec.
    - **Name** names the new item (scenarios: the type), **Classes** takes only some classes of a
      file, **Also add to group** adds what was added to a group (created when missing; a group of
      a less specific layer is copied into the chosen one), and **Replace** replaces an item of the
      same name added at this layer.
    - The answer lists what was added and the warnings (for example a scenario without
      `_info.yaml`).
- **Items**: every item with its source (built in, registered, uploaded, linked) and groups,
  searchable. Open one for its details, to add it to a group, or (when it was uploaded or linked at
  the chosen layer) to **Remove** it: an upload's files are moved to the layer's `.trash` folder
  (`scenarios/.trash/`, `library/<kind>/.trash/`), a link is removed and what it points to is left
  alone. Groups that list the item are not changed.

Uploads go to the layer's `scenarios/<name>/` (scenarios) or `library/<kind>/<name>/` folder and
are listed in its `library.yaml`; scenario links are kept in its `scenario_links.yaml`. The same
files are written by `hani2 library` on the command line.

!!! warning "Uploaded code runs on the server"
    Opponents, Assistants and tools are Python code, and a scenario may bring a `display.py`. They
    run inside the HANI2 server, with its permissions, when they are checked and whenever they are
    used. The console asks you to confirm that you trust the code (scenarios: to allow Python
    files) before uploading or linking.

### Scenarios

Items are the scenario types: registered generators and category folders, uploaded or linked.
Open one to explore it. **Example** picks what is shown: a saved scenario of its pool, or, for a
generator, a fresh sample drawn by a **Generation rule**: *Simple* (round numbers: option values in
steps of 5%, weights in steps of 10%, linear or symmetric issues, no noise) or *Random* (preferences
as the generator draws them), or *As this layer* (the layer's `simple_scenarios` setting). Changing
the rule draws a new sample; **Generate** draws another (samples are not saved). **Shown** says
which rule produced it, or, for a saved scenario, its folder and whether it is simple. Scenarios
with a `display.py` are marked.

The rest of the page is in sections that fold away (click a heading; the console remembers which
are open, and a closed section loads nothing):

- **Picture**: the scenario's picture as participants see it (with its dark-theme version).
- **Description**: the title, the short description and the number of outcomes; **Long
  description** (closed at first) is the full text participants read.
- **Preference summaries**: the *In short* text of the Preferences tool for every role.
- **Roles**: every role with its description and no-deal value; the participant's role is marked.
- **Issues**: every issue with its options.
- **Outcome space**: the 2D utility plot (below).
- **Preferences tool** (closed at first): the Preferences tool exactly as each role would see it
  in a negotiation, side by side: the summary, the issue weights, the value of each option (pick
  the issue), the value on disagreement and the hints.
- **Sample utilities** (closed at first): the best outcome for each role and a few others.

**Outcome space** plots every outcome in utility space (negmas's 2D utility plot): the
participant's role on the x axis against another role on the y axis, with the Pareto frontier, the
Nash, Kalai, Kalai–Smorodinsky and maximum-welfare points, and shading where an outcome is worse
than a role's no-deal value. With more than two roles, **Roles** picks the pair (the participant's
role against each other role). Outcome spaces of more than 5000 outcomes, and continuous ones, are
plotted from a random sample of 5000, and the frontier and solutions are those of the sample. The
plot loads after the rest of the page.

**Scenario set in use** is the default set of the chosen layer (`default` in its
`scenario_sets.yaml`; **Inherit** removes it). `Custom` is the custom order, edited under Texts.
See [Scenarios](scenarios.md) and [Scenario sets](scenario-sets.md).

### Opponents

Groups are the built-in groups (`@llm`, `@template`, `@notext`, `@negmas`, `@classic`, `@genius`,
`@pan`, `@custom`) and the group files (`groups/<key>.json` of the settings folder, a project or a
study, and those an outside system put in a study's `results/`). Open a group to see every member
with a one-line description, searchable (useful for `@genius` with its 196 agents); members whose
class does not load are marked.

**Opponents participants face** is the pool of the chosen layer, as a list of groups and single
classes to tick. It is stored in `env.json` (`opponents`) for the settings layer, in
`project.yaml` (`defaults.opponents`) for a project and in `study.yaml` (`overrides.opponents`)
for a study. An admin's `?opponents=`, any URL's `?group=`, `HANI2_OPPONENTS` and an outside system's
schedule still win. See [Opponents](opponents.md#group-files).

### Assistants

The same for Assistants: the built-in groups `@default` and `@tutorial` and the
`assistant_groups/` files; **Assistants participants get** (the pool: `assistants` in
`project.yaml` / `study.yaml`; at the settings layer it is the Assistant class of Assistant
settings); and the **Assistant balance** of a study (how many humans each Assistant has).
Assistant classes are written `module:Class`. See [Assistant](assistant.md).

### Tools

Items are the tools (built in, from `env.json`, or added here), each with its default pane, when
it appears, who gets it and its built-in groups (`information`, `visualization`,
`recommendation`, `admin`, `assistant`, `all`). Tool groups are the built-in ones and those of
`tools.yaml`. See [Tool groups](library.md#tool-groups).

- **Tools offered to sessions**: **Inherit**, or **Choose here** the tools and tool groups sessions
  of the chosen layer get (`tools.yaml` → `offer`). **Offered now** lists the tools that gives;
  choosing nothing offers no tool. Tool settings (`env.json`) can still switch a tool off.
- **Placement in each view**: a table of every tool with its pane and order, or *hidden*, in the
  full, simple and focus views. Tools placed at the chosen layer are in bold. Open a tool (or
  **Change the placement** on its page) for the **placement editor**: for each view, **Shown**,
  **Pane** (upper, lower, side) and **Order** (smaller first). Values set at the chosen layer are
  marked *set here*, with a button to inherit that value again; **Save** writes the tool's entry
  in the layer's `tools.yaml` → `placement`, and **Inherit** removes it. Sessions move the tools
  when the view changes, and a participant's own arrangement is kept per view. See
  [Where tools go in each view](library.md#where-tools-go-in-each-view).

## General

Edits `env.json` in the settings folder.

| Field | Key |
| --- | --- |
| Title, Subtitle | `title`, `subtitle` |
| Public address (used in participant links) | `public_url` |
| Sign-in: username and password, OAuth only, password and OAuth, or no sign-in | `auth.mode` (`password`, `oauth`, `dual`, `none`) |
| People can create accounts | `auth.allow_registration` |
| Require consent | `auth.enforce_consent` |
| Playground | `playground.enabled` |
| Admin emails | `admin.emails` |
| OAuth redirect base | `oauth.redirect_uri` |
| GitHub and Google client id and secret | `oauth.providers.github.key` / `.secret`, `oauth.providers.google.key` / `.secret` |

A provider is used when it has both a key and a secret and is not explicitly disabled.

## Negotiation

`env.json` → `negotiation`, per layer, so every project and study can have its own:

| Group | Fields (keys) |
| --- | --- |
| Timing | Rounds (`n_steps`), time limit (`time_limit`), time per step (`step_time_limit`), negotiator time (`negotiator_time_limit`), end probability per step and per second (`pend`, `pend_per_second`). Empty means no limit. |
| Negotiation rules | An empty offer ends the negotiation (`end_on_no_response`), messages without an offer (`allow_text_only_offers`), the opponent's messages (`allow_text_agent`), the participant's message field (`allow_text_human`), text-only mode (`text_only_mode`), writing a message when none is given (`auto_generate`), reading the offer out of a message (`auto_extract`), where the editor starts (`init_with_last`, `init_with_best`). |
| Scenarios and opponents | Saved scenario pools (`load_existing`), generating when none is saved (`generate_on_failure`), the scenario set (`scenario_set`), the scenario order (`predefined_order`), participants choosing the scenario (`allow_scenario_selection`, the older switch), the role rule, preferred roles and seat (`role_rule`, `human_roles`, `human_index`), showing the opponent's type (`show_opponent_type`), the opponent agents (`opponent_types`). |
| What participants may choose | Whether participants pick the scenario, the opponent and the Assistant of a negotiation, and from which set: *Not allowed*, *Any from the pool* or *Only these*. With the settings folder selected it is the playground's setting (`playground.choices`); with a project or a study selected, that layer's own `choices`. Never in Prolific studies. See [What participants may choose](configuration.md#what-participants-may-choose). |

The links at the top open the opponent pool, the scenario sets and the Participant interface page. See [`negotiation`](configuration.md#negotiation) for every key.

## Participant interface

`env.json` → `interface` (and the two tool keys of `negotiation`), per layer:

- **Participants may change**: one switch per participant setting: the display settings (including the scenario's picture and whether the full scenario description opens), **Layout for**, the theme, the layout view, and the Assistant's on/off switch, autonomy, abilities and delivery. Off: participants of that layer do not see the control and the server refuses the change (`interface.participant_settings.<key>`).
- **Defaults of the participant's settings** (`interface.prefs.<key>`), among them **Show the scenario's picture** (`show_scenario_picture`, on), **Scenario picture style** (`scenario_picture_style`: small, large or watermark; unset: the scenario's, else small) and **Open the full scenario description** (`open_scenario_description`, off: the *Scenario Info* tool shows it collapsed when a scenario loads).
- **Tools**: participants may move tools between panes (`negotiation.allow_moving_tools`) and switch them on and off (`negotiation.allow_tool_switch`).
- **Notifications**: how long they stay (`interface.notifications.toast_seconds`) and the notification list in the header (`interface.notifications.center`).

How the Assistant appears (panel, character, both or the participant's choice) is on the Assistant settings page. See [`interface`](configuration.md#interface).

## Tool settings

`env.json` → `tools`, per layer. **Enlarged tools open as** a large window, the full screen, or not at all (`tools.maximize`: `window`, `fullscreen`, `off`; see [The interface](interface.md#enlarge-and-put-back)). **Participants see opponent utilities** (`tools.show_opponent_utility`). **Extra tools** (`tools.extra`, class paths such as `my_pkg.tools:MyTool`). Then one row per registered tool with its description, pane and timing, and two switches: **Offered** (off adds it to `tools.disabled`) and **Admins only** (`tools.overrides.<name>.admin_only`). See [Tools](tools.md).

## Language model

`llm_settings.json`, used by the LLM offer tool, tools built on `LLMTool`, message writing, offer extraction and LLM opponents. Its provider and model are the old single-model settings, used only when no model chain is set (see [Models](#models)); its prompts always apply. A banner shows whether the model is configured ("Ready: provider / model") or which API key variable is missing. Fields: provider (`ollama`, `openai`, `anthropic`, `gemini`, `azure`, `groq`, `mistral`, `openrouter`), model, Ollama address (`ollama_base_url`), API key variable (`api_key_env`), temperature, max tokens, and the extraction, generation and instruction prompts. See [Language models](llms.md).

## Connections

The connections model chains use, kept in the settings folder for every project and study. Each
row shows a status dot, the provider, the sign-in method, the masked key or the environment
variable, and the address. **Test** checks the connection and lists the provider's models when it
can; for a harness connection it sends a tiny request through the harness. **Show implicit** lists
the connections that exist without being added. **Add a connection** offers only the sign-in
methods the chosen provider supports, and says why when a provider has no subscription sign-in.
**Harnesses** shows, for Claude Code, Codex and pi, whether the harness is installed and its
version, the allowed sign-in (API keys only) and why, and which purposes it can serve. A stored
subscription connection from an earlier version shows as disabled with the reason. See
[Models and connections](models.md#connections) and [Harnesses](models.md#harnesses).

## Models

The model chains of the chosen layer, one group per purpose (`default`, the Assistant, LLM
opponents, tools, offer extraction and message writing, the judge). A purpose without a chain
in the layer shows the chain in effect and where it comes from; **Set a chain here** gives the layer
its own chain. Each entry has a connection (or "the provider's first connection"), a model,
parameters (`temperature=0.2, max_tokens=800`) and a label. You can test, move, duplicate and remove
an entry. **Test chains** shows which entry each purpose resolves to now, and why each earlier entry
was skipped; with unsaved changes it tests those. See [Models and connections](models.md#model-chains).

## Assistant settings

`assistant_settings.json`.

| Field | Key |
| --- | --- |
| Who gets the Assistant: everyone, admins only, nobody | `mode` (`on`, `auto`, `off`) |
| Assistant class (`module:Class`, empty for the built-in one) | `agent_class` |
| Highest autonomy: Suggest, Semi, Full | `autonomy` |
| Abilities granted (one switch each) | `capabilities.<name>` |
| Provider, model, API base, API key variable | `provider`, `model`, `api_base`, `api_key_env` |
| Temperature, max tokens, tool steps per turn | `temperature`, `max_tokens`, `max_tool_iterations` |
| Speaks up unprompted when a negotiation starts, it is the participant's turn, a negotiation ends | `proactive.on_negotiation_started`, `proactive.on_action_requested`, `proactive.on_negotiation_ended` |
| System prompt | `system_prompt` |
| The Assistant appears as: a panel, a character (persona), both, the participant chooses; the first choice; participants may move the character; the open Assistant goes beside the page or over the tool area | `presentation.style` (`panel`, `persona`, `both`, `choice`), `presentation.choice_default`, `presentation.persona_movable`, `presentation.place` (`beside`, `tools`) |

Participants can narrow these permissions in their Assistant settings but never widen them. See [Assistant](assistant.md).

![The Assistant settings page](../assets/screens/admin-agent.png)

## Autopilot

`autopilot_settings.json`.

| Field | Key |
| --- | --- |
| Autopilot allowed | `allowed` |
| Default driver | `driver` |
| Participants choose the driver: playground only, yes, no | `user_can_choose` (`null`, `true`, `false`) |
| Pause between steps (s) | `step_delay` |
| Drivers offered (none ticked offers all) | `allowed_drivers` |

## Users

- **Add a user**: username, password, optional email, and an **Administrator** switch. Users created here count as having consented.
- **Accounts**, with a filter: for every account the name, an `admin` badge, the full name, email, OAuth provider and consent status, and **Make admin** / **Remove admin**, **Set password**, and delete. Deleting asks for confirmation and keeps the user's results.

The `admin` account cannot be demoted or deleted, and you cannot delete your own account. The same operations are available on the command line with `hani2 users` (see [Command line](../getting-started/cli.md)).

## Admin controls on the negotiation page

An administrator negotiating on `/app` (or on `/play` while logged in) gets more than a participant:

- The **Admin** badge and the opponent's name in the header, and no time limit by default (`time_limit` starts as none for admins).
- The **Scenario** picker before each negotiation: a scenario type and a scenario name, then **Load**.
- The **Opponent for the next negotiation** picker, with suggestions from every opponent group. Leave it empty for a random opponent from the pool.
- In the counter-offer editor: **Text only**, **Offer from message** and **Write message**.
- Admin-only tools in the tool panes.
- Every participant setting in **My settings**, marked when the current project or study hides it from participants.

The opponent picker, the opponent's name and `?opponents=` links need an admin account too.

### Negotiate as a participant

To try a study exactly as its participants will see it, choose **Negotiate as a participant** in the account menu (or add `?as_participant=1` to the page address). The page reloads with the participants' interface: no Admin badge, no opponent type or name unless the study shows it, no scenario or opponent pickers, no admin-only tools or controls, and the study's time limit and participant settings apply. The server enforces the same restrictions it applies to participants.

This is a separate session with its own results folder (`<your user name>~participant`), so it does not disturb your admin session, and it is never counted as a study participant for balancing or assignment. Choose **Back to the admin view** in the account menu to return.

### Session settings are in Administration

The settings drawer of the negotiation page (**My settings**) holds only what the current user may change for themselves. Timing, negotiation rules, scenarios and opponents, tools and what participants may change are set in Administration, on the [Negotiation](#negotiation) and [Participant interface](#participant-interface) pages, for all projects, one project or one study. They apply to sessions created after saving; an admin who wants to try a setting opens a new session after saving it.
