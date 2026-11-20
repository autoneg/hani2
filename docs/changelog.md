# Changelog

## Unreleased

- **Number fields keep offers in range.** The number field of a continuous or wide-range issue (and
  `number` controls) no longer sends empty, partial or out-of-range values: such text is outlined and
  reverts to the last valid value when you leave the field. The server also refuses an infinite value
  for a whole-number issue instead of failing.
- **Persona options may contain commas.** In `name:key=value,…` persona specs (`hani2 simulate -p`),
  a value such as `llm:goal="Keep it under 300, please",reservation=0.5` is no longer split at its comma;
  options are separated only by commas that start a new `key=`.
- **`kalai_distance` handles degenerate scenarios.** When one side's best utility equals its reservation
  value, or utilities are infinite, computing the Kalai–Smorodinsky point no longer fails (which left the
  whole `optimality` group empty) or picks an outcome below a reservation value. Pareto outcomes with
  non-finite utilities are skipped, and the metric is empty if no remaining one is acceptable to both sides.
- **Model fallback is triggered by real model failures only.** A failed model call now moves to the next
  entry of the chain based on the error's type and HTTP status, and on messages saying the *model* is not found;
  errors that merely contain "not found" (a missing tool, quoted text) no longer switch the session's model.
- **Replacing a Library upload keeps the index in step.** When a replaced `.py`/`.zip` upload no longer
  defines a class it had before, that class's entry is now dropped instead of staying in the Library as a
  dangling item.
- **Practice rounds no longer count in results.** The score, negotiation and agreement counts of
  *My Results* and *All Results* and the leaderboards leave out practice rounds; the results table
  still lists them.
- **Closed sessions stay closed.** Closing a session (or the server dropping it) now cancels its
  timers: a pending auto-start or auto-load of the next negotiation, its warning toast and the time-limit
  check no longer fire later on the closed session.
- **`ui.html()` is sanitised with an allowlist.** The HTML is now cleaned with DOMPurify, which keeps only
  plain HTML tags and attributes, instead of a blocklist that let through `javascript:` links hidden by
  entities or whitespace, SVG links, `data:` links and form actions. SVG, MathML and forms are no longer
  rendered in this component.
- **Language-model errors no longer leak secrets to the browser.** When a model call fails, participants
  see a generic message (in the Assistant chat, offer extraction, the instruction tool and LLM tools)
  and admins see the error with API keys, Bearer tokens and stored secrets masked. The full error is
  written only to the server log.
- **Default passwords are no longer left open.** Every server start warns about a default account
  (`admin`, `user`) that still has its well-known password, and a server listening on a non-loopback
  interface refuses the admin login with `adminpass` until it is changed with `hani2 users passwd admin`.
  The new `auth.default_password_login` setting (`auto`, `refuse`, `allow`) applies the rule behind a
  reverse proxy or switches it off.
- **Every fallback model is tried.** When calls running at the same time failed on the same model,
  one of them moved past the next model of the chain without trying it (and could give up early);
  each call now tries every later model in order, and the session's model only moves forward.
- **The interface no longer freezes while the Assistant sends with `auto_extract` / `auto_generate`.**
  The language model used to run while the session was locked, so every click, edit and update
  waited for it. It now runs unlocked, and the send is refused if the offer, the message or the
  turn changed meanwhile. See [Language models](guide/llms.md).
- **One session per browser, even on a double load.** Two tabs, a double page load or a retry that
  open the same session at the same moment now share one session instead of each making one (which
  split the history, duplicated result rows and left a tab attached to a discarded session).
- **Participants arriving together get distinct rotation offsets.** The shared
  `_prolific_fallback_counter.txt` (the opponent rotation outside a study) is now updated under a
  thread and file lock and written atomically, so two participants can no longer get the same offset.
- **`?admin=1` and `?opponents=` are for admins.** For other users both are ignored, so a shared
  link no longer shows the opponent picker or the opponent's type, and cannot choose arbitrary
  opponent classes. `?group=` still works for everyone. See
  [The `?admin=1` switch](guide/authentication.md#the-admin1-switch).
- **The playground uses your account when you are logged in.** `/play` in a logged-in browser records
  the rounds under that account and shows them in **My Results**; without a login it is the guest
  playground as before. See [The playground and guests](guide/authentication.md#the-playground-and-guests).
- **Sign-in from a trusted website.** A website with its own accounts, such as the ANAC competition
  site, can sign its users straight into HANI2 with a short-lived signed token: the account
  (`anac_<id>`) is made on the first visit, and the login page shows *Continue with your ANAC
  account*. "Test my agent" links can open a participant's own opponent (HAN) or Assistant (HI) as
  that signed-in user. See [Sign-in from a trusted website](guide/authentication.md#sign-in-from-a-trusted-website).

- **Security fixes.** An email typed at self-registration no longer makes an account an admin through
  `admin.emails` (only OAuth and admin-made accounts count). Non-admin pages can no longer load a
  `file:` opponent from the URL (`?opponents=file:…`) or the opponent picker; group files still can.
  Usernames may not start with `.` or `_`, and `gh_` / `g_` are kept for GitHub and Google sign-in.
- **Fixes.** Refused *End* / *Send* / *Accept* clicks (not your turn, double clicks) no longer mark,
  clear or log anything; the Assistant's offer, accept and end functions report what actually
  happened; LLM offer extraction reads the nested reply; text-only studies never send a hidden
  pre-filled offer; questionnaire answers count only while a questionnaire is open; the
  Utility-based Selector renders the next scenario before it starts; the phone layout no longer
  scrolls sideways; a tool or the Assistant filling the offer no longer wipes the typed message;
  actions taken while reconnecting are kept, with a notice, instead of lost; pass^k is computed per
  scenario and opponent; the assertions judge re-judges when `evaluation.assertions` changes.
- **End-to-end tests.** `tests/e2e` drives a real server in Chromium with Playwright (the new `e2e`
  extra; skipped without it).

- **Scenario picture styles.** The *Scenario Info* tool now shows the picture small, beside the
  story, by default. A menu next to the *Picture* switch picks *Small*, *Large* (full width above
  the story, as before) or *Watermark* (faintly behind the story); it is a participant setting
  too (`scenario_picture_style`, defaulted and locked like the others), and scenarios set their
  own default with `picture_style` in `_info.yaml`. Tools lay pictures out with content with the new `ui.figure`
  component. See [Scenario pictures](guide/scenarios.md#scenario-pictures).
- **Scenario picture and full description are participant settings.** *Show the scenario's
  picture* (`show_scenario_picture`, on) and *Open the full scenario description*
  (`open_scenario_description`, off) are in **My settings**; their defaults and whether
  participants may change them are set for all projects, one project or one study on the
  **Participant interface** page (`env.json → interface.prefs` and
  `interface.participant_settings`). The *Picture* switch of the *Scenario Info* tool changes
  the same setting and is hidden when participants may not change it. See
  [`interface`](guide/configuration.md#interface).
- **Judge reliability for the combined scores.** `hani2 replay judge-reliability --judge A --judge B`
  (or `judge_reliability()`) has two judge models score the same recordings. For every
  language-model judged component of `han_interaction`, `hi_assistant` and `hi_team`, it reports
  how far the judges agree (Krippendorff's α, Spearman's ρ, the mean difference, and exact and
  within-one agreement) and how well the judges correlate with the matching questionnaire scale. It
  says which components are ready for an official ranking, and shows how the scores and the
  interaction leaderboards change with the judge. `hani2 replay leaderboard --reliability
  report.json` leaves out the components that are not ready, and `--official` leaves out every
  judged component unless there is a report. `evaluate_paths(..., judge="provider:model")` judges
  with exactly one model. See [Judge reliability](guide/evaluation.md#judge-reliability).
- **Leaderboards for the Human-Agent Negotiation and Hybrid Intelligence tracks.** Each track has
  an **outcome** board and an **interaction** board. HAN ranks opponent agents by what they
  obtained (`han_outcome`) and by how well they behaved as opponents (`han_interaction`). HI ranks
  Assistants by what the team obtained (`hi_outcome`) and by how well they worked as Assistants and
  as a team (`hi_interaction` = `hi_assistant` + `hi_team`). Scores are cell-balanced means with
  95 % confidence intervals that resample participants, with pass^k reliability and cost. Every
  entrant is scored on the same components. Use `hani2 replay leaderboard`, **Leaderboard** in the
  replay tool or `POST /api/replay/leaderboard`. See
  [Tracks and leaderboards](guide/evaluation.md#tracks-and-leaderboards).
- **Combined scores.** A new metric, `scores`, combines outcome, rule checks, judge, questionnaire
  and log columns into six numbers in [0, 1] per session, each with its coverage. Weights can be
  changed in `env.json → evaluation.scores`.
- **Evaluation criteria per scenario.** An `evaluation` block in `_info.yaml` (targets on outcome
  columns, rule checks, facts the Assistant must convey and assertions) makes every session
  pass/fail (`task_success`, the default success criterion of the HI leaderboard's pass^k). The
  block is hidden from the participant, the Assistant and the opponent, and stored in the
  recording. See [Evaluation criteria](guide/scenarios.md#evaluation-criteria).
- **Rule checks.** A new metric, `rule_checks`, flags mistakes that the utility table proves:
  accepting a deal worth less than no deal, suggesting one, the opponent doing so, and sessions
  that failed because of the opponent or the system. A new judged metric, `task_judge`, checks the
  scenario's facts and assertions.

- **Simulated participants.** `hani2 simulate` (and `hani2.simulator`) lets a persona play the
  human seat of headless sessions, for cheap, repeatable trials and pass^k before the human study,
  as a qualifying round for Assistant entrants. Scripted personas: `follower` and `click_through`
  (easy), `skeptic` and `stubborn` (hard). A language-model persona has a goal, a private
  reservation value, a temperament and an instruction to disclose information gradually, and ends
  with `###STOP###`. Sessions are tagged `mode: simulated` (users `sim_<persona>`), get no
  questionnaires, never count as study participants and are never ranked with humans: the admin
  console shows them in a separate **Qualifying round** table, and `replay compare` keeps them in
  their own groups. Success is `goal_met`, a deal worth at least the persona's reservation value.
  The new `simulation` metric reports it, along with validity, suggestion uptake and
  scripted-persona conformance. `error_review` gains a **simulator** source
  (`simulator_errors`, `simulator_critical_errors`) for auditing the simulator. See
  [Simulated participants](guide/simulation.md).
- **Pre-questionnaire and participant types; stratified leaderboards.** An opt-in questionnaire
  (`"pre_questionnaire": "expertise"` in `env.json`, or `questionnaires/pre_questionnaire.yaml`)
  is shown once before a participant's first negotiation. Its `participant_type` answer (e.g.
  novice / experienced / expert) is stored in the new `participant_type` results column, and the
  leaderboard is also shown per participant type. Results also gain `mode`, `persona` and
  `goal_met` columns. See
  [Pre-questionnaire and participant types](guide/studies.md#pre-questionnaire-and-participant-types).
- **Scenario pictures.** The *Scenario Info* tool shows a picture of the scenario under its
  title, with a *Picture* switch to hide it. Put `picture.svg` (or `.png`, `.jpg`, ...) in a
  scenario or category folder, optionally with `picture_dark.svg` for the dark theme, or name
  them in `_info.yaml` (`picture: {light: ..., dark: ...}`). Every bundled scenario has a light
  and a dark vector picture. Tools can show pictures with the new `ui.image` component. See
  [Scenario pictures](guide/scenarios.md#scenario-pictures).
- **Who knows what: the participant and the Assistant can know different things.** The new
  `information` setting (per project, study or server) splits information so
  that the two must work together. *Past negotiations*: records of earlier negotiations in the
  same scenario between parties with similar (or the same, or different) preferences, shared
  out between the participant (a new **Past Negotiations** tool) and the Assistant. A scenario
  folder can ship its own in `_past_negotiations.yaml` (`hani2 scenario past` writes it).
  *Preferences*: the participant may know only the issue weights and the Assistant only the
  option values (or any other mix), with deal values hidden from a side that knows only part.
  *Market research*: statistics on how preferences in the scenario are usually distributed,
  for the Assistant, the participant (a **Market Research** tool) or both. A new Assistant
  ability, `private_info` (`get_private_information`, `show_past_negotiation`), gives the
  Assistant its share; it cannot read the participant's private tools. Results rows and
  recordings say who held what. See [Who knows what](guide/information.md).
  *Dual control*: private briefings (in `_info.yaml` per role, or in the setting) give one side a
  limit that is not in the preferences; the human sees theirs in a **Briefing** tool and the
  Assistant must ask about it. Their constraints are checked against the agreement
  (`constraints_met`). `control.human_only_issues` and `control.human_only_actions` keep
  decisions for the human: the Assistant can only suggest them.
- **Compositional scenarios: find where Assistants fail.** `hani2 compose` builds scenarios from
  difficulty factors (number of issues, opposition, ZOPA size, a hidden constraint, a deceptive
  opponent, time pressure). Every scenario is verified automatically (each factor in its band, a
  non-empty ZOPA, a reachable target deal, a constraint that bites), and the sampler picks a balanced
  set. `hani2 compose run` plays the set with an Assistant or a baseline through the autopilot, and
  `hani2 compose report` shows the target attainment, agreement rate and constraint violations per
  factor level, with the factors ranked by how much they hurt. The new `factors` metric adds the
  factor levels and target attainment to any evaluation. Two new deterministic opponents:
  `helpers.HonestTBNegotiator` and `helpers.DeceptiveTBNegotiator`, which bluffs. See
  [Compositional scenarios](guide/compositional.md).

- **Ablations as diagnostics.** Three new conditions and a report that compares them cell by cell
  (scenario × opponent × the human's side), never as pooled means:
  - **No-Human**: the Assistant alone on autopilot, its negotiation ceiling. `hani2 ablation run`
    plays it headlessly.
  - **Oracle**: a new admin-only Assistant ability, `opponent_utility` (off by default; the
    `get_opponent_utility` function and the `opponent_view()` helper), gives the Assistant the
    opponent's utility function. This is the information ceiling.
  - **A no-Assistant control group**: the Assistant pool member `none`, as in
    `assistants: [TeamX, none]`.

  `hani2 ablation report` gives the **added-value score** (team − human alone) and the other gaps:
  autopilot − team, autopilot − human alone, and the oracle gains. `--by assistant` gives one
  added-value score per Assistant. Recordings now store each negotiation's condition, and the
  autopilot driver every time autopilot is switched on or off. The new `condition` metric and the
  `results.csv` columns `assistant_condition`, `oracle`, `opponent_info_tools` and
  `autopilot_driver` expose it. Evaluation rows also carry `assistant` (as assigned) and
  `human_index`. See [Ablations](guide/ablations.md).
- **Admins can negotiate as a participant.** **Negotiate as a participant** in the account menu
  (or `?as_participant=1`) opens a separate session with exactly the participants' interface: no
  opponent type, no scenario or opponent pickers, no admin controls. It is not counted as a study
  participant. See [Negotiate as a participant](guide/admin.md#negotiate-as-a-participant).
- **Settings are per project and study; the settings drawer holds only what the user may change.**
  The negotiation page's settings drawer (**My settings**) now shows only what the current user may
  adjust. The session settings administrators used to change there (timing, rules, scenarios and
  opponents, tools) are on the admin console's **Negotiation** page, which now covers every key of
  `env.json → negotiation`, per layer. A new **Participant interface** page (`env.json → interface`)
  decides, for all projects, one project or one study, which settings participants may change
  (`participant_settings`: the display settings, layout, theme, and the Assistant's switch,
  autonomy, abilities and delivery), their defaults (`prefs`), whether participants may move tools
  between panes (`negotiation.allow_moving_tools`) and how notifications behave. Hidden controls are
  refused by the server as well. See [`interface`](guide/configuration.md#interface).
- **Start-time settings file: `hani2 --settings overrides.yaml`.** Its keys override the settings
  folder's `env.json`, `llm_settings.json`, `assistant_settings.json`, `autopilot_settings.json`
  and `models.json`; projects and studies still win over it, so it shapes the playground and
  sessions outside a study. See
  [Start-time settings file](guide/configuration.md#start-time-settings-file).
- **Pinned messages.** A new Assistant ability, `pin` (`pin_message`, `unpin_message`, and the
  `pin_message()` / `unpin_message()` helpers), pins markdown at the top or bottom of the screen;
  the panes shrink to make room. See [Pinned messages](guide/assistant.md#pinned-messages).
- **Notification list.** Every notification is kept in the session; a bell in the header shows the
  unread count and lists them all. Notifications stay `interface.notifications.toast_seconds`
  (default six seconds).
- **The Assistant as a character.** `assistant_settings.json → presentation.style`: `panel` (as
  before), `persona` (a movable character in the corner; its notifications come out of it as
  speech bubbles and clicking it opens the conversation), `both`, or `choice` (the participant
  picks). See [The Assistant as a character](guide/interface.md#the-assistant-as-a-character).

- **Harness connections: Claude Code, Codex and pi.** A connection can run an installed agent
  harness instead of calling the API (`--provider claude-code|codex|pi`; `pip install
  'hani2[harness]'` for the Claude Agent SDK). Harness entries sit in model chains like any other,
  with a check and the same fallback. Plain completion works for every purpose that a harness may
  serve, including LLM opponents (through a litellm custom provider); the Assistant's functions run
  through Claude Code (in-process MCP) and pi (an RPC bridge), and every call goes through the
  Assistant's dispatcher, so capabilities and recordings apply. Usage rules are enforced in code:
  API keys only, an isolated config folder and `HOME` per connection, an allowlisted environment,
  no built-in tools, no user settings, memory files, hooks, plugins or MCP servers, an empty working
  folder, and caps on time and turns. Following Anthropic's and OpenAI's terms, Claude Code and
  Codex serve only the judge and the console's Test (never participants), and Codex runs without
  any tools. The Connections page gains a **Harnesses** group (installed?, version, sign-in,
  purposes). See [Harnesses](guide/models.md#harnesses).
- **Subscription sign-ins are not offered.** The ChatGPT-plan and GitHub Copilot device sign-ins
  are removed (from the presets, the console, `hani2 connections login` and the API): their
  providers' terms do not clearly allow a third-party application to use them to serve others.
  Stored connections of that kind load disabled and say why; `chatgpt:` and `copilot:` entries are
  skipped. Ollama cloud models through a signed-in local server (`-cloud`) are refused for the same
  reason; use an Ollama Cloud API key. See
  [Subscription sign-ins](guide/models.md#subscription-sign-ins-are-not-offered).
- **Model chains and connections.** Language models are now chosen from an ordered list of
  entries (`{connection, model, params, label}`) tried until one is available, so a session falls
  back to the next model when a provider is down, a key is missing or a model is not offered. One
  model may appear several times with different parameters. Chains are kept per purpose
  (`default`, `assistant`, `opponent`, `tools`, `text`, `judge`) in a layer's `models.json`.
  Precedence: the study's > the project's > the start-time list (`hani2 --models
  "anthropic:claude-sonnet-5-5,ollama:qwen3:4b"` / `HANI2_MODELS`) > the settings folder's > the
  old `provider`/`model` settings, which keep working as a one-entry chain. **Connections** sign in
  to providers with an API key (stored 0600 in the settings folder, always masked), a key in an
  environment variable or nothing (a local Ollama server). There
  are presets for Anthropic (API keys only: Anthropic does not permit Claude plan sign-in in
  third-party apps), OpenAI, Ollama Cloud, local Ollama, Gemini, OpenRouter, Groq,
  Mistral, DeepSeek, Azure, Bedrock and OpenAI-compatible servers, and any other litellm provider
  can be used too. Every model call (the Assistant, LLM opponents, tools, offer extraction and
  message writing, the evaluation judge) uses the session's resolved entry. It is checked once with
  a short time-out and a cache, kept for the session, and moved to the next entry after a hard
  failure (`model_fallback` event). When nothing is available the session shows a banner and logs
  `model_unavailable`. The old local-Ollama fallback is now an entry of the chain. Results rows gain
  `assistant_llm`, `assistant_llm_entry`, `opponent_llm`, `opponent_llm_entry` and `llm_models`;
  recordings gain `models`. New admin pages **Connections** and **Models**, new commands
  `hani2 connections …` and `hani2 models list|resolve`, and new endpoints
  `/api/admin/connections`, `/api/admin/providers` and `/api/admin/models`. See
  [Models and connections](guide/models.md).
- **Scenario details from a set, with a plot of the outcome space.** In the console, the entries
  of a scenario set (and of any opponent, Assistant or tool group) open forward: an item shows its
  full details page, a nested group its members, and going back keeps the group's unsaved edits.
  A scenario's details add **Outcome space**, negmas's 2D utility plot (all outcomes, the Pareto
  frontier, the Nash, Kalai, Kalai–Smorodinsky and maximum-welfare points, the no-deal regions),
  the participant's role against each other role; large or continuous outcome spaces are sampled.
  The plot loads after the details (`plot_token` in `GET /api/admin/scenarios/{name}`, then
  `GET /api/admin/scenarios/plot/{token}`), so it never delays the page.
- **Scheduling methods.** A study (`study.yaml`) or a project (`project.yaml`, for all its
  studies) chooses how HANI2 schedules each dimension, merged per dimension:
  `scheduling: {opponents: ..., assistants: ..., scenarios: ...}`. Opponents: `latin_square`
  (default, balanced Williams design), `random`, `cyclic`, `fixed_order`, `external`. Assistants:
  `balanced` (default, fixed per human, fewest first), `random_fixed`, `random_each`,
  `round_robin`, `external`. Scenarios: `by_participant` (default), `set_order`, `random`,
  `latin_square`, `external`. A `schedule.json` still wins; `external` uses only it (a missing
  opponent or scenario is filled in and flagged `external:missing` with a `scheduling_missing`
  error event; a missing Assistant fails loudly). Results rows gain `opponent_scheduling`,
  `assistant_scheduling` and `scenario_scheduling`. New `hani2 scheduling list [--details]`,
  `--opponent-scheduling`, `--assistant-scheduling` and `--scenario-scheduling` on `hani2 study
  create` / `hani2 project create`, `GET /api/admin/scheduling-methods`, and `scheduling`,
  `scheduling_effective` and `errors` in the admin study endpoints (unknown names are refused).
  The docs render maths (KaTeX). See [Scheduling methods](guide/scheduling.md).
- **The configured Assistant fails loudly too.** An `agent_class` in `assistant_settings.json`
  (also written by `hani2 experiment create --assistant <class>`) that cannot be loaded or
  created no longer falls back to the built-in Assistant: the session runs without one and shows
  the error (banner, toast, `assistant_failed` event, `assistant_error` column), as for assigned
  Assistants.
- **Confusing combinations are refused.** `--assistant <class>` with `--assistants`,
  `--assistant off` / `--no-assistant` with `--assistants`, a new option with its
  old name (`--support-agent`, `--experiment`, `--agents`, `--set`), the matching environment variables
  (`HANI2_ASSISTANT_CLASS` + `HANI2_ASSISTANTS`, `HANI2_STUDY` + `HANI2_EXPERIMENT`, old and new
  names with different values), `opponents` + `agents` in `env.json`, a setting given twice in
  `study.yaml` / `project.yaml`, and group files whose `assistant` and `support_agent` disagree
  are refused with a message saying which to use. Old names alone keep working.
  `hani2 experiment create --assistants` now writes the pool to the experiment's `study.yaml`
  (it was ignored). See [Confusing combinations](guide/configuration.md#confusing-combinations).
- **Metric reference.** Every evaluation metric and column now says what it measures and exactly how
  it is calculated: a formula, how to read it, its range and direction, a worked example and the
  caveats, with figures of the outcome space (Pareto frontier, Nash and Kalai–Smorodinsky points,
  distances) and of the move types. The texts live in the metric definitions (`Column` / `metric`
  take `formula`, `details` and `range`; dynamic columns such as `q_<id>` have patterns) and are shown
  by `hani2 replay metrics --details [NAME]`, by `GET /api/replay/metric-reference`, by the ⓘ buttons
  and the searchable **Metric reference** panel of the replay tool, and by the new
  [Metric reference](guide/metrics.md) page (generated by `scripts/make_metric_reference.py`). The docs
  and the web app render math with KaTeX; the app's `Markdown` component takes `math` to render
  `$...$` and `$$...$$` (a `$` followed by a space or a closing `$` before a digit stays text, `\$`
  is a literal dollar).
- **Library and groups.** Scenarios, opponents, Assistants and tools now share one model: list
  them with their source (built-in, registered, uploaded, linked) and groups, add your own by
  uploading a `.zip` or `.py` or by linking a path or class spec, remove what you added, and
  manage groups, per layer (settings, project or study). New `hani2 library` commands and admin
  API under `/api/admin/library` ([Library API](reference/library-api.md)). Uploaded code is
  checked by loading it the way HANI2 will, archives are unpacked safely, and scenario names that
  equal or start like a registered type are refused. Scenario links live in
  `scenario_links.yaml`; uploaded and linked code in `library.yaml`; and a category is now found
  in the study's, the project's or the settings' scenarios folder, so a project with its own
  `scenarios/` folder still serves the settings' categories. See
  [Library and groups](guide/library.md).
- **Groups of groups everywhere.** Opponent, Assistant and tool groups may list other groups
  (`@key`, or `:key` as before), like scenario sets: expanded in place, duplicates dropped,
  case-insensitive, cycles reported and broken (an opponent group that listed itself used to
  recurse forever). One implementation serves every kind.
- **Tool groups and placement per view.** Tools have `groups` (built-in: `information`,
  `visualization`, `recommendation`, plus `admin`, `assistant` and `all` from their metadata) and
  `tools.yaml` defines more groups and the tools a study `offer`s (default: every tool). Tools
  also have a `placement` per view (full, simple, focus: pane, order, shown or hidden), set on the
  class, in `env.json` → `tools.overrides` or per layer in `tools.yaml`; sessions move the tools
  when the view changes and remember the participant's arrangement per view. Nothing moves
  unless a placement is configured.
- New dependency: `python-multipart` (uploads).
- **A new admin console, laid out like system settings.** A sidebar with a search field and the
  pages in groups (Activity, Studies, Library, Server, Accounts); each page is a list of rounded
  groups of rows with switches, pop-up menus, steppers and text fields, and rows that open
  sub-pages with a back button. Search finds any setting by its label, hint or key across all
  pages and jumps to it. Light and dark themes, phone layout (the sidebar becomes a list page),
  keyboard navigation. Every earlier section is kept; old URL fragments still work.
- **Layer-explicit saving.** Settings pages, texts, scenario sets and pools say where they save:
  the settings folder (all projects), a project or a study, picked at the top of the page. Values
  are shown as in effect at that layer, and saving writes only the changed values to that layer's
  own file (a "set here" mark with a reset button shows overrides). A console opened under
  `/s/<project>/<study>/admin` starts on that study's layer, and the API refuses a settings write
  from inside a study that names no layer (409), so the shared settings are never written by
  accident. New: `GET /api/admin/layers`, `?layer=` on the settings endpoints, `PATCH` and
  `DELETE` (with `key`) of settings files.
- **Projects & Studies page**: edit `project.yaml` and `study.yaml` with form fields (defaults,
  overrides, scheduling, custom variables kept on save), the participant links with copy buttons,
  results counts and the Assistant balance (`GET .../studies/{study}/balance`).
- **Texts page**: welcome text, consent, scenario sets and custom order per layer, with the
  layer each text comes from, a live preview with the text variables filled in, the unknown
  variables, and the list of variables.
- **Scenarios, Opponents, Assistants and Tools explorers** (one shared explorer on the
  [library API](reference/library-api.md)): the groups (scenario sets; opponent, Assistant and
  tool groups) with where each is defined, its raw entries and its members after composition
  (`@name`), editing per layer with warnings for unknown entries, classes that do not load and
  cycles; uploading (`.zip`, `.py`) and linking items with their notice and warnings; the items
  with their source and groups, removing what was added at a layer; the default scenario set, the
  opponent and Assistant pools (`GET`/`PUT /api/admin/pools/{kind}`) and the Assistant balance.
  The **Tools** page also chooses the tools sessions are offered and has a **placement editor**:
  per tool and view (full, simple, focus) shown or hidden, pane and order, written to the
  layer's `tools.yaml`. A scenario type's page shows its roles, issues, sample utilities and a
  generated example (`GET /api/admin/scenarios/{name}`). The Server page *Tools* is now *Tool
  settings*.
- **Library additions.** Removed and replaced uploads are moved to the layer's `.trash` folder
  instead of being deleted; a broken `library.yaml`, `scenario_links.yaml` or
  `scenario_sets.yaml` is refused (409) instead of being overwritten; archive bytes are also counted
  while unpacking; saving a group returns `warnings`; an empty `offer` (`[]`) is kept and offers no tool (it used to
  be dropped, so the layer inherited); new `GET`/`PUT /api/admin/library/scenarios/default` and
  `POST /api/admin/library/{kind}/describe`.
- **Scheduling in the console.** The Scheduling groups of a project and a study use
  `GET /api/admin/scheduling-methods`, show the method in effect, and **About these methods**
  renders the formulas. A `PUT` of a study or project with `scheduling: {}` inherits every
  dimension again.

- **Scenarios shape how offers are shown.** A scenario's display (`hani2.display.OfferDisplay`, in
  its `display.py` or passed to `register`) can now define four views: the one-line `text`, the
  offer in the `history`, the offer `on_table` and the counter-offer `controls`. Views are lists
  of `ui` components; `None` keeps the default. Custom controls edit the normal draft: inputs
  named after an issue set it, other inputs and buttons call `on_input` / `on_action`, which return
  the issue values to set, and the new `ui.issue(name)` places the default field of one issue in a
  custom layout. New `_info.yaml` keys need no code: `offer_template`, `value_labels` and
  `issue_widget` (`buttons`, `select`, `slider` — new in the default editor — or `number`), and
  `issue_format` now applies to every scenario and to the editor's buttons. Split scenarios
  (Estate, Resources) show what each side gets in the history and on the table, and their editor
  asks how many items *you* get, with a *Split evenly* button (also right when the participant
  plays the other role). A failing display falls back to the defaults; `hani2 scenario check`
  exercises every view. Old `DefaultOutcomeDisplay.str(...)` displays still work. See
  [Showing offers](guide/scenarios.md#showing-offers).
- **Groups and assignment.** Opponent groups (`groups/<key>.json`) and the new Assistant groups
  (`assistant_groups/<key>.json`, members under `assistants`) can live in a project, shared by its
  studies; a token `:key` or `?group=key` is looked up in the study's results folder, the study
  folder, the project folder, the settings folder and then the built-in groups (new built-in
  Assistant groups `:default` and `:tutorial`). Relative `syspath` folders are relative to the file.
  A group file's `assistant` key (old name `support_agent`) names the Assistant for participants
  arriving with that group, switched on from the start, so a team can try its own Assistant from a
  link. A study's Assistant pool comes from the URL (admins), the group file, `schedule.json`
  (per slot or top level, new `assistant` field), `hani2 --assistants` / `HANI2_ASSISTANTS`
  (new), `assistants` in study.yaml / project.yaml, or `agent_class`; with more than one Assistant,
  each human keeps one for the whole study, balanced across the study's humans (fewest first,
  ties in pool order; admins and playground guests not counted; drop-outs counted), stored in the
  study's `assignments.json`. In a study, opponents follow a balanced Latin square over the pool
  and scenario types are spread by participant index (a `schedule.json` still wins). An assigned
  Assistant that cannot be loaded now fails loudly (an error notice, an `assistant_failed` event,
  no silent fallback). Results rows gain `assistant`, `assistant_group`, `assistant_class`,
  `assistant_error` and `opponent_group`; events, recordings and the admin sessions list carry
  them too. New `hani2 groups list` and admin endpoints to list groups and to read, write and
  delete a project's group files and to read a study's assignments. See
  [Assistant pools and assignment](guide/assistant.md#assistant-pools-and-assignment) and
  [Latin squares](guide/opponents.md#latin-squares).
- **Projects and studies.** One server now runs many data collections at once. A *project*
  (`projects/<project>/project.yaml`: name, full name, kind, year, organiser, contact and defaults
  such as `n_required` and time limits) owns *studies* (`studies/<study>/study.yaml`: type
  `prolific`, `online` or `lab`, title, dates, Prolific study id, completion code), each with its
  own settings files and results. Every study is reached at `/s/<project>/<study>/play` (or `/app`,
  or with `?study=project/study`) without a restart; settings, scenarios, questionnaires and
  results resolve per session (study, then project, then the settings folder). Results rows,
  questionnaire answers, events and recordings gain `project` and `study` columns. Online studies
  take participant ids from `?pid=` / `?participant=`, lab studies session codes from `?code=`, and
  both end with the study's completion link or end page. Consent, welcome, title and questionnaire
  texts may use `{{variables}}` (`{{project_full_name}}`, `{{n_required}}`, …); consent is recorded
  per study with a hash of the text, so a new study or a changed text asks again. New commands
  `hani2 project create|list|show`, `hani2 study create|list|show` (which prints the participant
  links) and `hani2 --study`, and admin API endpoints for projects, studies, settings layers and
  text previews. Experiments keep working unchanged as studies of the `default` project
  (`HANI2_EXPERIMENT`, `--experiment`, `hani2 experiment`, the same folders and files). See
  [Projects and studies](guide/projects.md).
- **Human, Assistant and Opponent.** The three parties of a negotiation now have the same names
  everywhere (interface, admin console, docs, CLI help, messages, scenario texts and prompts): the
  *human* (the participant), the *Assistant* (the AI helper that advises the human and can act for
  them) and the *opponent* (the other side). The relabelled side names default to `You` and
  `Opponent`, and scenario texts say "Opponent Utility Function" and "your opponent". The guide
  page is now [Assistant](guide/assistant.md) and the tutorial [Write an Assistant](tutorials/assistant.md).
  New names, with the old names kept working as aliases:
    - `hani2 --assistant` / `--no-assistant` and `hani2 experiment create --assistant` /
      `--no-assistant` (old names `--support-agent` / `--no-support-agent`, hidden from the help);
    - `HANI2_ASSISTANT` / `HANI2_ASSISTANT_CLASS` (old names `HANI2_SUPPORT_AGENT` /
      `HANI2_SUPPORT_AGENT_CLASS`, still read; the new ones win);
    - `assistant_settings.json` (old name `support_agent_settings.json`, still read). Layers, lowest
      first: bundled default, settings folder old file, settings folder new file, experiment old
      file, experiment new file. The admin console saves the new file, `hani2 setup` keeps an
      existing old file and does not add a new one over it, and the admin settings kind is
      `assistant` (old name `support_agent`);
    - `from hani2.assistant import Assistant` (old name `from hani2.support_agent import
      SupportAgent`, the same class; `hani2.assistant.runtime`, `.settings`, … are the same modules);
      `load_assistant_settings`, `assistant_mode`, `create_assistant_for` and friends next to their
      old names;
    - the autopilot driver `Assistant` (old name `Support Agent`, still accepted in settings);
    - `make_session(opponent=..., assistant_settings=...)` (old names `partner=` and `support_settings=`).

  Stored names do not change, so old recordings, results and evaluations still load: result columns
  such as `support_agent_used`, event types and their fields, session snapshot keys, capability keys,
  LLM function and WebMCP tool names, and the scenario values `human` / `agent`.
- **Scenario catalog script.** `scripts/make_scenario_catalog.py` writes the
  [scenario catalog](guide/scenario-sets.md); run it again when scenario texts change.

- **Tool help.** Every tool has a `help` text (Markdown) saying what it does and how it works. Participants open it with the new **?** button next to a pane's tabs (and in an enlarged tool), and the Assistant reads it at the top of `read_tool`. All built-in tools have one.
- **Easy tool registration.** Tool files in `$HANI2_HOME/tools` are loaded automatically and re-read when they change; more folders come from `env.json` → `tools.paths`, and `hani2 --tools` / `tools.extra` now also take folders and whole `.py` files. New `register_tool` decorator and the `hani2 tools list | path | new` commands.
- **LLM tools.** `LLMTool` turns a prompt into a working tool (button, background call, errors, Markdown answer); `Tool.ask_llm()`, `Tool.transcript()` and `hani2.llm_service.complete()` help write your own. New example tools: Summary and Ask the AI. The Assistant's `use_tool` waits for such a tool to finish, so it gets the answer.
- **Tutorial.** The tools tutorial now covers the tools folder, LLM tools, help texts and the ways to register a tool.
- **Scenario sets**: named, ordered lists of scenario types in `scenario_sets.yaml` (editable under
  *Texts*). The bundled sets are `HAN2026` (Trade, Island, Grocery; the default), `MIT2025`,
  `PieArena2026`, `ANL` (all years) with `ANL2010`, `ANL2011`, `ANL2012`, `ANL2013`, `ANL2025` and
  `ANL2026`, `IAGO`, the short list `HAN2027`, and `HI2027` and `ANAC2027`, which are made of
  other sets (a set can list sets as well as types; duplicates are dropped); `Custom` is `scenario_order.txt`.
  Choose the set with `hani2 --scenario-set NAME` (`HANI2_SCENARIO_SET`), `env.json` →
  `negotiation` → `scenario_set`, or, as an admin, in the settings drawer or on the start screen.
  `hani2 sets` lists them; `hani2 generate --set NAME` generates a set's pools.
- **16 new scenario types** adapted from the MIT AI Negotiation Competition, PieArena MBA cases, ANAC
  Automated Negotiation League domains and IAGO item splits: Furniture, Lease, Consulting, JobOffer,
  License, HomeRepair, Supply, Acquisition, Chores, Energy, HealthFund, UsedCar, CityTrip,
  LaborContract, Resources and Estate. Each has a fixed story and draws new utility functions (and
  hints) every time, within an opposition band.
- **Scenario templates in YAML.** Every one of the 16 new types now has a template folder in the
  standard format (`sample_scenarios/Default/<Type>/`: `<Type>.yml`, one file per role,
  `_info.yaml`), like Trade, Island and Grocery. The texts, issues and roles are read from it with
  `Story.from_folder`; Python only draws the variations. `hani2 setup` copies all templates to
  `Examples`.
- **Writing scenarios by hand**: `hani2 scenario new TYPE DEST` copies a template (or, with
  `--generate`, a seeded draw) to edit; `hani2 scenario check PATH` validates folders and pools,
  proves that they load back unchanged, and `--fill-hints` adds the computed hints.
- **Reproducible pools**: `hani2 generate --seed` now fixes every scenario (the same seed, type and
  slot always give the same scenario). Scenarios are saved with one info file and no stale role
  files or load paths, so saving a loaded scenario writes the same files.
- **Strict scenarios** (opt in per project or study: `strict_scenarios: true` in `project.yaml` or
  `study.yaml`, or *Strict scenarios* under *Projects* in the console): only saved scenarios are
  served; a missing pool, a missing named scenario or a broken scenario folder is an error instead of
  a generated scenario or a bundled sample. `hani2 sets` shows how many saved scenarios each type has
  and flags the types a strict study cannot serve.
- **Sample scenarios fixed**: the Trade, Island and Grocery samples now match their generators (role
  names `Buyer`/`Seller` and `agent`/`human`, the generators' issue names, normalized utilities, issue
  descriptions that show), and their `display.py` files use the built-in displays (the Grocery one
  printed every offer to the console and used an undefined name).
- **Your own scenario types**: write a `Story` (issues, roles, texts and one function per role that
  draws its preferences) or any `maker(index)`, and register it from `<settings>/scenario_types/*.py`
  or `hani2 --scenario-types file.py`. `hani2 --scenarios FOLDER` serves saved scenarios from a folder.
- **Role assignment rules** (`role_rule`): `auto` (the scenario's suggested role), `index`, `roles`
  (preferred role names), `alternate` and `random`. A role named `human` always goes to the
  participant. Pools now cache the utility inverse of every role.

- **Recording and replay**: every negotiation is recorded completely (screens, pointer, clicks,
  keys, local UI state, every message and action with who took it, assistant chat, suggestions and
  function calls, language-model calls with tokens and cost) in a compact `.hrec` file, and can be
  replayed exactly in the new replay tool (`/replay`, `hani2 replay open`), with a fidelity check
  against the participant's screen.
- **Evaluation metrics** for recordings: hard (outcome, optimality, length, LLM usage, move types
  and theory of mind, timing, activity, use of the assistant, engagement flags, assistant
  interaction), subjective (questionnaire scales) and language-model judged (assistant, opponent,
  human, assertions, error review); group comparisons with scenario-balanced means and pass^k.
  `hani2 replay evaluate | compare | list | show | export | metrics`.
- An evaluation questionnaire (UEQ, TAM, intention to use, opponent perception):
  `HANI2_PER_NEG_YAML=evaluation`. Questions can carry `scale`, `reverse` and
  `requires: support_agent`.
- Charts appear at once when a negotiation starts: the charting library is fetched while the app
  loads (not when the first chart is shown), and the app's files are sent gzip-compressed
  (the charting library shrinks from 4.8 MB to 1.5 MB) and cached by the browser for a year.

## 0.1.0 (2026-11-17)

First release. See [Features](features.md) for the full list with links.

**Platform**

- A FastAPI server and a React web app shipped pre-built in the wheel; one port serves the logged-in app (`/app`), the playground (`/play`), the admin console (`/admin`) and the API, with live updates over a WebSocket.
- `pip install hani2` on Python 3.11 to 3.15 (Linux, macOS, Windows).
- Tools are computed only when visible, in their own worker threads; charts draw when the browser is idle.

**Participants**

- Negotiation desk: offer on the table, counter-offer editor (three columns for large scenarios), gauges with a no-deal marker, a conversation-style history, confirmation dialogs.
- Full, simple and focus views; drag-to-resize panes; enlarge any tool into a window or the full screen and put it back; tablet (landscape and portrait) and phone layouts.
- Your Preferences tool comes into view when a negotiation starts.
- With an assistant present, `human` / `agent` scenario values are shown as *You* / *Partner* (`names` in `env.json`); stored results keep the original values.

**Tools**

- Thirteen built-in tools, including the Negotiation Plot (Pareto frontier, Nash and Kalai points) and Opponent Preferences; admins can open admin-only tools to everyone.
- Preferences views for most negmas utility-function types, extensible by registration.
- Tools are Python classes with a declarative component API (`hani2.tools.ui`), registered in `env.json`, with `hani2 --tools`, or through the `hani2.tools` entry point; `timing = "agent"` for tools only a support agent adds.

**Support agent**

- Chat, status board, notifications, highlights and notes, layout control, custom panels, filling and sending offers, accepting and ending; sixteen capabilities and three autonomy levels.
- Finds, reads and uses the participant's tools, and adds tools during the session (`SupportAgent.tools`, the `toolbox` setting, registered tools); tool actions follow the agent's own permissions.
- Ten tutorial levels, from an echo bot to an agent that brings and uses tools.
- Autopilot: the support agent or any negotiator plays the human's seat.

**Competitions and studies**

- `--no-support-agent` (Human-Agent Negotiation), `--support-agent on|off|auto|<class or file.py:Class>` (Hybrid Intelligence), `--opponents`, `--tools`, and the same choices for `hani2 experiment create`.
- Experiments, per-negotiation questionnaires, results CSV files (with the layout used), an SQLite event log with analytics, and a Prolific flow with practice rounds and completion links.
- Opponents from negmas, Genius and negmas-llm, group tokens, group files and per-link pools.
- Password, GitHub and Google login, or none; consent forms; `hani2 users`.
- Any litellm provider or Ollama for the assistant and LLM opponents.
- WebMCP tools for browser AI agents.
- `hani2.testing.make_session` for headless tests of tools and agents.
