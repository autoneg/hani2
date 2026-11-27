# Configuration reference

HANI2 is configured with a few files in the settings folder and a handful of environment variables. This page lists all of them. Most settings can also be edited in the [admin console](admin.md).

## Files and folders

```text
$HANI2_HOME/                      default ~/negmas/hani2
├── settings/
│   ├── env.json                  main configuration
│   ├── llm_settings.json         LLM opponents and message helpers
│   ├── assistant_settings.json
│   ├── autopilot_settings.json
│   ├── models.json               model chains per purpose (a project or study may have its own)
│   ├── connections.json          connections to model providers (no secrets)
│   ├── secrets/                  keys (connections.json, 0600) and sign-in tokens (<name>/)
│   ├── consent.md                consent form (Markdown)
│   ├── announcements.md          welcome text (Markdown)
│   ├── scenario_order.txt        order of scenario categories
│   ├── questionnaires/           per_negotiation.yaml (optional)
│   ├── scenarios/                scenario categories
│   ├── scenario_sets.yaml        scenario sets (groups of scenario types)
│   ├── scenario_links.yaml       linked scenario categories (library)
│   ├── tools.yaml                tool groups, offered tools, placement per view
│   ├── library.yaml              uploaded and linked opponents, Assistants, tools
│   ├── library/<kind>/           uploaded code (library)
│   ├── groups/                   opponent groups; assistant_groups/: Assistant groups
│   ├── users.json                password hashes
│   ├── users_meta.json           user metadata
│   └── .cookie_secret            generated cookie secret
├── db/                           results and events (when no study is active)
├── experiments/<name>/           one folder per experiment (a study of the default project)
└── projects/<project>/           projects: project.yaml, shared settings files,
    └── studies/<study>/          and their studies: study.yaml, settings files, results/
```

See [Project management](project-management.md) and [Study management](study-management.md) for the project and study files. A project or study folder may hold the same library files (`scenario_links.yaml`, `tools.yaml`, `library.yaml`, `library/`, `scenarios/`); they apply to its sessions, a more specific layer winning (see [Library and groups](library.md#layers)).

## Precedence

Each settings file is looked up in up to four places, per session. The first one that exists wins:

1. `<study>/<file>`, when the session belongs to a study (its URL `/s/<project>/<study>/…`, or the server's default study from `--study` / `HANI2_STUDY` or the old `--experiment` / `HANI2_EXPERIMENT`); an experiment folder is a study,
2. `<project>/<file>`, the study's project folder (not for the `default` project),
3. `$HANI2_HOME/settings/<file>`,
4. the defaults bundled with the package.

JSON files are then **merged over the built-in defaults**: HANI2 starts from its internal defaults, merges the bundled file over them, and merges the chosen file over the result. Nested objects merge key by key, so a file only needs the keys you change:

```json title="env.json"
{"negotiation": {"n_steps": 30}}
```

The JSON files are merged in layers: the bundled defaults, then the settings folder, then the [start-time settings file](#start-time-settings-file) (`hani2 --settings`), then the project folder, then the study folder. A key set in a later layer wins; keys it does not mention keep their earlier value.

Every setting of these files can be set per project and per study, not only the language models: the negotiation rules, what participants may change, how the Assistant appears, the tools, autopilot. The exceptions are the server-wide parts of `env.json` (`title`, `admin`, `auth`, `oauth`, the cookie secret) and the [connections](models.md) (API keys and servers), which only the settings folder sets: sign-in happens before a session belongs to a study.

### Start-time settings file

`hani2 --settings overrides.yaml` starts the server with a YAML (or JSON) file of settings that win over the settings folder. Its top-level keys `env`, `llm`, `assistant`, `autopilot` and `models` override `env.json`, `llm_settings.json`, `assistant_settings.json`, `autopilot_settings.json` and `models.json`; any other top-level key is a key of `env.json`:

```yaml title="overrides.yaml"
negotiation:            # env.json → negotiation
  time_limit: 120
interface:              # env.json → interface
  participant_settings:
    theme: false
assistant:              # assistant_settings.json
  presentation:
    style: persona
models:                 # models.json
  default: ["ollama:qwen3:4b-instruct"]
```

The file applies to the playground and to every session outside a project or study. A project's or study's own settings still win over it, so a study keeps exactly what its organisers set. The file is re-read when it changes. The server refuses to start with a file that is not a mapping; the admin console names the file on the settings-folder layer and shows values that include it. The path is passed to the server in `HANI2_SETTINGS_OVERRIDES`.

Text files (`consent.md`, `announcements.md`, `scenario_order.txt`) are taken from the first location that has them.

The admin console saves each setting in the layer chosen at the top of its page: the settings folder, a project or a study (see [Layers](admin.md#layers-where-a-setting-is-saved)).

Texts shown to participants (consent, welcome text, title and subtitle, questionnaire texts) may use `{{variables}}` such as `{{project_full_name}}` and `{{n_required}}`; see [Texts with variables](study-management.md#texts-with-variables).

Scenarios, results and questionnaires follow their own rules, described in [Scenarios](scenarios.md) and [Study management](study-management.md).

## `env.json`

The main deployment configuration.

```json
{
  "title": "HANI2",
  "subtitle": "Human-Agent Negotiation Interface",
  "admin": {"password": "adminpass", "emails": []},
  "auth": {
    "mode": "password",
    "cookie_secret": "",
    "enforce_consent": false,
    "allow_registration": true,
    "default_password_login": "auto"
  },
  "oauth": {
    "redirect_uri": "",
    "providers": {
      "github": {"enabled": false, "key": "", "secret": ""},
      "google": {"enabled": false, "key": "", "secret": ""}
    }
  },
  "opponents": [],
  "negotiation": {"n_steps": 100, "time_limit": 300},
  "playground": {"enabled": true},
  "tools": {"extra": [], "disabled": [], "overrides": {}}
}
```

### Branding

| Key | Default | Meaning |
| --- | --- | --- |
| `title` | `"HANI2"` | Name shown in the header, on the login page and, after the scenario title, in the browser tab. |
| `subtitle` | `"Human-Agent Negotiation Interface"` | Line shown under the title on the login page. |
| `docs_url` | `"https://autoneg.github.io/hani2/"` | Documentation URL reported by `GET /api/config`. The bundled web app does not use it yet. |
| `public_url` | none | The address participants use to reach this server, including any root path (for example `https://example.org/hani`). Used for the study links that `hani2 study` and the admin API give out. `HANI2_PUBLIC_URL` wins over it. |

`title` and `subtitle` may use [text variables](study-management.md#texts-with-variables), for example `"{{project_full_name}}"`.

### `admin`

| Key | Default | Meaning |
| --- | --- | --- |
| `admin.password` | `"adminpass"` | Initial password of the `admin` account, used when the account is created. |
| `auth.sso` | `{}` | Sign-in from trusted websites: per provider `secret`, `login_url`, `label`, `prefix`, `issuer`, `guest_studies`, `trust_admin_claim` (default `false`: `true` lets the token's `"admin": true` make admins of this server), `enabled`. See [Authentication](authentication.md#sign-in-from-a-trusted-website). |
| `admin.emails` | `[]` | Users whose email is in this list are admins (case-insensitive). Emails typed at self-registration are unverified and never count. |

### `auth` and `oauth`

| Key | Default | Meaning |
| --- | --- | --- |
| `auth.mode` | `"password"` | `password`, `oauth`, `dual`, `none` or `auto`. |
| `auth.cookie_secret` | `""` | Secret for signing login cookies. Generated and stored in `settings/.cookie_secret` when empty. |
| `auth.enforce_consent` | `false` | Require logged-in users to sign the consent form before negotiating. |
| `auth.participant_consent` | `false` | Show the consent form to Prolific and online / lab participants in the session, before their first negotiation. See [Study forms](study-forms.md#consent-for-study-participants). |
| `auth.allow_registration` | `true` | Offer the registration form. |
| `auth.default_password_login` | `"auto"` | Admin logins with the default password: `auto` (refused on a non-loopback bind), `refuse` or `allow`. See [Authentication](authentication.md#default-accounts). |
| `oauth.redirect_uri` | `""` | Public base URL used to build `/api/oauth/<provider>/callback`. Empty: the request's base URL. |
| `oauth.providers.github` | disabled | `enabled`, `key` (client ID), `secret`. |
| `oauth.providers.google` | disabled | `enabled`, `key` (client ID), `secret`. |

See [Authentication](authentication.md).

### `opponents`

A list of opponent specs and group tokens that form the default opponent pool, for example `["AspirationNegotiator", ":template"]`. Empty means the built-in default pool. It has lower precedence than the `?opponents=`/`?group=` URL parameters, `--opponents`/`HANI2_OPPONENTS` and the admin session setting `opponent_types`. The older key `agents` is still read when `opponents` is empty. See [Opponents](opponents.md).

### `han`

The HAN league agents of the current year: `current_year` (a year, set explicitly; that year's `:han<year>-<set>` groups come from its submitted zips, every other year from the `han-agents` package), `submissions` (per year, `{"dir": "<folder with the zips and index.json>"}`) and `import_dir` (where `hani2 han import` unpacks them, default `<HANI2_HOME>/han_submissions`). See [HAN agents of the current year](opponents.md#han-agents-of-the-current-year).

### `negotiation`

Default values of the per-session negotiation settings. Every key below may appear here, in any layer. The admin console edits them on the **Negotiation** page (timing, rules, scenarios and opponents) and the **Participant interface** page (`allow_tool_switch`, `allow_moving_tools`), per layer.

| Key | Default | Meaning |
| --- | --- | --- |
| `n_steps` | `100` | Maximum number of negotiation steps. `null` for no step limit. |
| `time_limit` | `300` | Time limit in seconds. `null` for no time limit. Always `null` for admin sessions. |
| `pend` | `0.0` | Probability that the negotiation ends at each step. |
| `pend_per_second` | `0.0` | Probability that the negotiation ends per second. |
| `step_time_limit` | `null` | Time limit of a single step in seconds. |
| `negotiator_time_limit` | `null` | Total time each negotiator may use, in seconds. |
| `human_index` | `1` | Which side of the scenario the human plays (0 or 1) under the `index` rule, and under `auto` when the scenario suggests no role. |
| `role_rule` | `"auto"` | How the human's role is chosen: `auto`, `index`, `roles`, `alternate` or `random`. See [Which side the participant plays](scenarios.md#which-side-the-participant-plays). |
| `human_roles` | `[]` | Preferred roles for the `roles` rule, e.g. `["Tenant", "Buyer"]`. |
| `information` | not set | What the participant and the Assistant each know: past negotiations, which part of the preferences, market research. Not set: both know the same. See [Who knows what](information.md). |
| `scenario_set` | `null` | The [scenario set](scenario-sets.md) to use. `null`: `HANI2_SCENARIO_SET`, a changed `scenario_order.txt`, then the default set. |
| `end_on_no_response` | `false` | End the negotiation when a negotiator gives no response. |
| `allow_text_only_offers` | `true` | Let negotiators send a message without an offer. |
| `allow_text_agent` | `true` | Show the opponent's messages. |
| `allow_text_human` | `true` | Give the human a message field. |
| `text_only_mode` | `false` | The human sends messages only, no structured offer. |
| `auto_extract` | `false` | Read an offer out of the human's message with the LLM before sending. |
| `auto_generate` | `false` | Write a message with the LLM when the human sends an offer without one. |
| `init_with_best` | `true` | Start the counter-offer editor at the human's best outcome. |
| `init_with_last` | `true` | Start the counter-offer editor at the human's last offer, when there is one. |
| `allow_tool_switch` | `true` | Let the human switch tools on and off. |
| `allow_moving_tools` | `true` | Let the human move tools between panes (the server refuses the move otherwise). The Assistant's own moves are its `tool_order` capability. |
| `load_existing` | `true` | Load saved scenarios instead of generating new ones. Off in the playground unless the URL has `?load_existing=1`. |
| `generate_on_failure` | `true` | Generate a scenario when none can be loaded. |
| `predefined_order` | `true` | Present scenario types in the order of the active scenario set. Always off in the playground. |
| `allow_scenario_selection` | `false` | Let non-admins pick any scenario type (the older switch; it applies on every layer). Prefer [`choices`](#what-participants-may-choose). |
| `show_opponent_type` | `false` | Show the opponent agent's type. Always on for admins. (Old name: `show_partner_type`.) |
| `opponent_types` | `[]` | Opponent agents for this session. (Old name: `partner_types`.) |
| `human_opponent_wait` | `120` | Seconds a participant waits for a [human opponent](human-opponents.md) before the fallback (0: forever). |
| `human_opponent_fallback` | `true` | After that wait, negotiate with an AI opponent from the rest of the pool (else keep waiting). For one invitation's participants only, use `"ai_fallback": false` in its group file ([People-only invitations](human-opponents.md#people-only-invitations)). |
| `human_opponent_absent` | `60` | Seconds without an open page after which a participant counts as having left a human-opponent negotiation. |
| `human_opponents_first` | `false` | When the pool has human entries, every negotiation looks for a person first, of any human kind the pool lists; the AI entries are only the fallback. See [A person first](human-opponents.md#a-person-first-any-person). |
| `human_opponent_choice` | `false` | Before pairing, the participant chooses *Play a person* or *Play an AI opponent now* (also `?opponent_choice=1`). See [Choosing a person or an AI](human-opponents.md#choosing-a-person-or-an-ai). |
| `human_opponent_codes` | `true` | Whether `?match=<code>` pairs non-admins (false: pairing is only random among those waiting). |

The Prolific flow overrides some of these per round (for example the time limits). See [Prolific](prolific.md).

### `interface`

What participants may adjust themselves, the defaults of their own settings, and notifications. Like every `env.json` key it can be set in the settings folder, a project or a study; the console edits it on the **Participant interface** page.

| Key | Default | Meaning |
| --- | --- | --- |
| `participant_settings.<key>` | all `true` | Whether participants may change this. Off: the control is not shown and the server refuses the change. Administrators may always change everything (their settings drawer marks what participants do not see). |
| `prefs.<key>` | (the built-in defaults) | What a new session starts with, for `show_history`, `show_human_offers`, `color_utility_by_issue`, `last_offer_on_top`, `offer_panel_always_visible`, `offer_display`, `font_scale`, `show_scenario_picture`, `scenario_picture_style` and `open_scenario_description` (see [Display settings](interface.md#display-settings)). |
| `notifications.toast_seconds` | `6` | How long a notification stays on screen. `0`: until it is closed. Errors stay at least nine seconds. |
| `notifications.center` | `true` | The bell in the header that lists every notification of the session. |
| `view` | `simple` | The view a session starts in: `full`, `simple`, `focus` or `bare` (no tools). `?view=` in the URL wins. See [Layout views](interface.md#layout-views). |
| `view_locked` | `false` | `true`: participants and the Assistant cannot leave that view (administrators still can). Use it with `view: bare` for a no-tools condition. |
| `simple_tools_side` | `right` | Where the tools column goes in the simple view: `right` or `left` of the negotiation. |

The `participant_settings` keys:

| Key | Controls |
| --- | --- |
| `show_history`, `show_human_offers`, `color_utility_by_issue`, `last_offer_on_top`, `offer_panel_always_visible`, `offer_display`, `font_scale` | The display settings of the same name. |
| `show_scenario_picture` | **Show the scenario's picture** in the settings drawer and the *Picture* switch of the *Scenario Info* tool. |
| `scenario_picture_style` | **Scenario picture** in the settings drawer and the style menu of the *Scenario Info* tool. |
| `open_scenario_description` | **Open the full scenario description**. |
| `device` | **Layout for** (phone, tablet, desktop). |
| `theme` | The theme button and **Theme** setting. |
| `layout_view` | The layout menu (full, simple, focus, bare). |
| `assistant_switch` | The Assistant's on/off switch. |
| `assistant_autonomy` | **How much may the assistant do?** |
| `assistant_abilities` | The Assistant's ability switches. |
| `assistant_delivery` | **Unprompted messages appear as**. |

```json title="projects/HI2027/studies/hi-01/env.json"
{"interface": {"participant_settings": {"assistant_switch": false, "layout_view": false},
               "prefs": {"offer_display": "table"}},
 "negotiation": {"allow_moving_tools": false}}
```

For example, a study whose participants always start with the full scenario description open and
never see the scenario pictures, and cannot change either:

```json title="projects/HI2027/studies/hi-02/env.json"
{"interface": {"prefs": {"show_scenario_picture": false, "open_scenario_description": true},
               "participant_settings": {"show_scenario_picture": false, "open_scenario_description": false}}}
```

### `playground`

| Key | Default | Meaning |
| --- | --- | --- |
| `playground.enabled` | `true` | Allow the no-login playground at `/play`. Prolific links work even when it is off. |
| `playground.choices` | nothing | What participants may choose outside any project or study (see below). |

### What participants may choose

Each negotiation starts with the scenario, opponent and Assistant that HANI2 picks as usual: the
scenario order or the study's scheduling, the opponent pool, the Assistant pool. The admin can let
participants pick another one from an allowed set before they press **Start negotiation** (see
[The interface](interface.md#before-the-negotiation)). A choice holds for one negotiation; the next
one starts from HANI2's own pick again.

The setting is a mapping with the keys `scenario`, `opponent` and `assistant`. Each value is:

| Value | Meaning |
| --- | --- |
| `false` or missing | Participants may not choose (the default). |
| `true` | Any member of the session's own pool: the scenario types of its scenario set, its opponent pool, its Assistant pool. |
| a list | Exactly these: scenario types; opponent specs or `:group` tokens; Assistant specs or `:group` tokens, with `none` for "no Assistant". |

Where it is read:

- **Outside any project or study** (the playground, and a signed-in user's sessions that belong to
  no study): `playground.choices` in the settings folder's `env.json` (or the start-time settings
  file).
- **In a study**: `choices` in the study folder's own `env.json`, else in its project folder's own
  `env.json`, key by key (the study wins). The settings folder never reaches a project or study,
  so participants of a study may choose nothing unless its project or the study itself allows it.
- **Prolific studies never allow it**, whatever the files say. Remember that a study's `type`
  defaults to `prolific`: set `type: online` or `type: lab` in `study.yaml` first.

The admin console edits both on **Negotiation → What participants may choose**: with
*All projects (settings folder)* selected it edits the playground's setting, with a project or a
study selected it edits that layer's own `choices`.

```json title="settings/env.json — the playground offers two opponents and any scenario type"
{"playground": {"choices": {"scenario": true, "opponent": ["BoulwareTBNegotiator", "ConcederTBNegotiator"]}}}
```

```json title="projects/HAN2027/env.json — participants of every study of the project pick their Assistant"
{"choices": {"assistant": ["my_assistant:MyAssistant", "none"]}}
```

The results record the participant's pick: `user` in the `opponent_scheduling`,
`assistant_scheduling` or `scenario_scheduling` column, and `assistant_source = user`. Their pick
is not kept in `assignments.json`, so it does not change how the study balances its Assistants.

### `names`

Some scenarios call the two sides `human` and `agent` (on the island, for example, every item goes
to `human` or `agent`). With an Assistant in the session, "agent" is ambiguous, so HANI2 shows
these values as **You** and **Opponent** instead: in the offer fields, the offer text, the
opponent's messages, tool tables and charts, and in what the Assistant reads. Values typed or
picked with the new names are mapped back, so results, logs and the opponent keep the scenario's
own values, and results from sessions with and without an assistant stay comparable.

```json
"names": {"apply": "auto", "self": "You", "opponent": "Opponent"}
```

| Key | Default | Meaning |
| --- | --- | --- |
| `apply` | `auto` | `auto`: relabel when the session has an Assistant; `always`; or `never`. |
| `self` | `You` | Shown instead of `human`. |
| `opponent` | `Opponent` | Shown instead of `agent`. |

Only scenarios that use these words (as issue values or role names) are relabelled; a Buyer/Seller
scenario is left alone. When relabelling applies, the scenario description, hints and result text
use the new names too, and the header no longer says "You are the human". Messages the participant
or the assistant write to the opponent are sent as written.

### `tools`

| Key | Meaning |
| --- | --- |
| `tools.extra` | Extra tool classes, as `"module:Class"`, `"module.Class"` or `"path/to/file.py:Class"`. |
| `tools.paths` | Extra folders (or `.py` files) to load tools from, besides `$HANI2_HOME/tools`. |
| `tools.disabled` | Names of tools to remove (case-insensitive). |
| `tools.weights_chart` | How the Preferences tool draws issue weights: `donut` (default) or `bar` (one thin horizontal bar, saves space). See [Weights as a donut or a bar](preferences.md#weights-as-a-donut-or-a-bar). |
| `tools.show_opponent_utility` | Let every participant show the opponent's utility in the Utility Plot and Trace (default `false`; admins always can). |
| `tools.overrides` | Per-tool changes keyed by tool name (case-insensitive): `pane`, `timing`, `enabled`, `admin_only`, `guest`, `order`, `at_front`, and `placement` (per view, see [Placement per view](tools.md#placement-per-view)). |
| `webmcp.enabled` | Register WebMCP tools for browser agents (default `true`). See [WebMCP](webmcp.md). |
| `webmcp.actions` | Also register tools that act in the negotiation (default `true`). |
| `webmcp.studies` | Register them for Prolific participants too (default `false`). |

```json
{
  "tools": {
    "extra": ["my_tools:OfferCounter"],
    "disabled": ["Random"],
    "overrides": {"Trace": {"pane": "side", "enabled": true}}
  }
}
```

See [Tools](tools.md).

### `scenario_stats`

The negmas statistics of every scenario, computed in the background and cached next to it. See
[Scenario statistics](scenarios.md#scenario-statistics).

| Key | Meaning |
| --- | --- |
| `scenario_stats.enabled` | Compute and show them (default `true`). |
| `scenario_stats.pareto_max_outcomes` | Keep the Pareto frontier in the cache only for scenarios with at most this many outcomes (default `1000000`). |
| `scenario_stats.timeout` | Seconds one computation may take; a slower scenario is skipped (default `300`). |
| `scenario_stats.max_outcomes` | Skip larger outcome spaces without trying (default negmas's `STATS_MAX_CARDINALITY`). |

### `tools.yaml`

Tool groups, the tools sessions get and where tools go in each view, read from the settings
folder, then the project folder, then the study folder (groups merge by name; `offer` comes from
the most specific layer that sets it; placements merge per tool and view):

```yaml title="tools.yaml"
groups:
  core: ["@information", "Utility-based Selector"]
offer: ["@core", "Utility Plot"]        # default: every tool
placement:
  Trace: {pane: side}                   # every view
  Value Histogram:
    simple: {visible: false}
```

See [Library and groups](library.md#tool-groups).

### `recording`, `evaluation` and the questionnaires

| Key | Meaning |
| --- | --- |
| `recording.enabled` | Record every negotiation (default `true`). See [Recording and replay](recordings.md). |
| `evaluation.llm` | Language-model settings for the evaluation judge (same keys as `llm_settings.json`); default: the HANI2 language model. |
| `evaluation.assertions` | Statements for the `nl_assertions` metric. See [Evaluation metrics](evaluation.md#language-model-judgements). |
| `evaluation.reliability.pairs` | Judge column → questionnaire columns compared by `hani2 replay judge-reliability`, e.g. `{"jo_overall": ["scale_opponent_kindness_norm"]}`. See [Judge reliability](evaluation.md#judge-reliability). |
| `evaluation.reliability.report` | The judge reliability report (`.json`) an official leaderboard (`--official`) uses to leave out the judged components that are not ready. Without one, an official board leaves out every judged component. |
| `questionnaire` | The questionnaire after each negotiation, by name (`evaluation`) or path. |
| `pre_questionnaire` | The questionnaire shown once before a participant's first negotiation, by name (`expertise`) or path; its answer sets the participant type. Off when unset. See [Pre-questionnaire and participant types](study-management.md#pre-questionnaire-and-participant-types). |
| `post_questionnaire` | The questionnaire shown once after a study participant's last counted negotiation, by name or path. Off when unset. See [Study forms](study-forms.md#the-post-session-questionnaire). |

## `llm_settings.json`

The language model for LLM opponents and for the message helpers. `provider` and `model` (with
`api_key_env`, `ollama_base_url`, `api_base`) are the old single-model settings: they are used only
when no [model chain](models.md) is set for the purpose. The prompts always apply.

| Key | Default | Meaning |
| --- | --- | --- |
| `provider` | `"ollama"` | Any litellm provider. |
| `model` | `"qwen3:4b-instruct"` | Model name. |
| `api_key_env` | `"OPENAI_API_KEY"` | Name of the environment variable holding the key (message helpers). |
| `ollama_base_url` | `"http://localhost:11434/v1"` | OpenAI-compatible endpoint used by the message helpers with `provider: ollama`. |
| `temperature` | `0.3` | Sampling temperature (message helpers). |
| `max_tokens` | `2000` | Maximum answer length (message helpers). |
| `extraction_prompt` | built in | Template for reading an offer out of a message. |
| `generation_prompt` | built in | Template for writing a message for an offer. |
| `instruction_prompt` | built in | Template for the `LLM` tool. |

See [Language models](llms.md) for the prompt placeholders.

## `assistant_settings.json`

`provider`, `model`, `api_key_env` and `api_base` are the old single-model settings of the
Assistant, used only when no [model chain](models.md) gives the `assistant` purpose a chain;
`temperature` and `max_tokens` also tune a chain entry that does not set them.

The old name of this file, `support_agent_settings.json`, is still read; where both exist, `assistant_settings.json` is merged over it (see [Old names](assistant.md#old-names)).

| Key | Default | Meaning |
| --- | --- | --- |
| `mode` | `"on"` | Who gets the Assistant: `on` (everyone), `off` (nobody) or `auto` (admins only). Overridden by `--assistant`/`HANI2_ASSISTANT`. |
| `agent_class` | `null` | Your `Assistant` subclass, as `"module:Class"` or `"module.Class"`. `null`: the built-in agent. Used when nothing else names an Assistant pool (see [Assistant pools and assignment](assistant.md#assistant-pools-and-assignment)); the `:default` Assistant group. A class that cannot be loaded leaves the session without an Assistant and shows the error ([no fallback](assistant.md#when-an-assistant-does-not-load)). |
| `provider` | `"ollama"` | Any litellm provider. |
| `model` | `"qwen3:4b-instruct"` | Model name. |
| `api_key_env` | `"OPENAI_API_KEY"` | Name of the environment variable holding the key. |
| `api_base` | `null` | Custom endpoint URL. |
| `temperature` | `0.3` | Sampling temperature. |
| `max_tokens` | `2000` | Maximum answer length. |
| `max_tool_iterations` | `10` | Maximum rounds of function calls per user message; then one last call without functions gives the answer. |
| `autonomy` | `"full"` | `suggest`, `semi` or `full`. |
| `capabilities` | all `true` except `opponent_utility` | The twenty-four capability switches: `chat`, `toast`, `pin`, `tool_enable`, `tool_visibility`, `tool_order`, `fill_offer`, `fill_text`, `submit_counter`, `accept`, `end`, `highlight`, `annotate`, `layout`, `offer_display`, `interface`, `presentation`, `panels`, `tool_add`, `tool_use`, `llm_tool`, `private_info`, `opponent_model`, and the admin-only oracle `opponent_utility` (default `false`; see [Ablations](ablations.md)). |
| `toolbox` | `[]` | Tool classes (`module:Class` or `path/to/file.py:Class`) the agent may add by name, in addition to its own `tools`. |
| `proactive.on_negotiation_started` | `false` | Speak up when a negotiation starts. |
| `proactive.on_action_requested` | `false` | Speak up at each of the human's turns. |
| `proactive.on_negotiation_ended` | `false` | Speak up when a negotiation ends. |
| `system_prompt` | built in | The assistant's system prompt. |
| `presentation.style` | `"panel"` | How the Assistant appears: `panel` (opened from the header), `persona` (a character in a corner of the screen), `both`, or `choice` (the participant picks in their settings). Phones always use the Assistant tab. See [The Assistant as a character](interface.md#the-assistant-as-a-character). |
| `presentation.choice_default` | `"panel"` | What a participant starts with under `choice`. |
| `presentation.persona_movable` | `true` | Whether participants may drag the character. |
| `presentation.place` | `"beside"` | Where the open Assistant goes: `beside` the page (a dock or a slide-over) or `tools` (in the tool area, in the open tool's place; closing it brings the tool back). Where no tool area is shown it opens beside the page. The Assistant may change it for its session. See [The Assistant in the tool area](interface.md#the-assistant-in-the-tool-area). |

See [Assistant](assistant.md).

## `autopilot_settings.json`

| Key | Default | Meaning |
| --- | --- | --- |
| `allowed` | `false` | Master switch for autopilot. |
| `driver` | `"Assistant"` | Default driver: `"Assistant"` or a negotiator name. |
| `allowed_drivers` | `null` | Drivers that may be used. `null`: all. If `driver` is not listed, the first allowed driver is used. |
| `step_delay` | `0.5` | Seconds to wait before each autopilot move (both kinds of driver). |
| `user_can_choose` | `null` | Whether non-admins may pick the driver. `null`: only in the playground. |

See [Autopilot](autopilot.md).

## Text files

| File | Content |
| --- | --- |
| `consent.md` | The consent form, shown at registration and, with `enforce_consent`, before the first negotiation. Markdown. |
| `announcements.md` | The welcome text shown on the negotiation page before a scenario starts. Markdown. |
| `scenario_order.txt` | Scenario category names, one per line, in presentation order. Blank lines and lines starting with `#` are ignored. |

## Questionnaires

`questionnaires/per_negotiation.yaml` in the experiment or the settings folder defines the questionnaire shown after each negotiation. `hani2 setup` installs an inactive example as `per_negotiation.example.yaml`. See [Per-negotiation questionnaires](study-management.md#per-negotiation-questionnaires) for the format.

## Environment variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `HANI2_HOME` | `~/negmas/hani2` | Root folder for settings, results and experiments. |
| `HANI2_EXPERIMENTS` | `$HANI2_HOME/experiments` | Folder that holds experiments (the studies of the `default` project). |
| `HANI2_EXPERIMENT` | none | Old name: the server's default study is this experiment (`default/<name>`). Set by `--experiment`. |
| `HANI2_STUDY` | none | The server's default study, as `project/study`, for URLs without one. Set by `--study`. Setting both with different studies is refused at startup. |
| `HANI2_PROJECTS` | `$HANI2_HOME/projects` | Folder that holds projects. |
| `HANI2_PUBLIC_URL` | none | The address participants use to reach the server, for the links `hani2 study create` prints (else `public_url` in `env.json`). |
| `HANI2_OPPONENTS` | none | Opponent agents (comma-separated specs and group tokens). Set by `--opponents`. The old name `HANI2_AGENTS` is still read (both with different values: refused at startup). |
| `HANI2_TOOLS` | none | Extra tool classes, folders and `.py` files, comma separated. Set by `--tools`. |
| `HANI2_ASSISTANTS` | none | The Assistant pool: comma-separated Assistant classes and Assistant group tokens (`:default`, `:tutorial`, `:<key>`). With more than one, each human keeps one Assistant (as the study's [`assistants` scheduling method](scheduling.md#assistants) says, by default balanced across the study). Wins over `assistants` in study.yaml / project.yaml and `agent_class`; loses to a group file's `assistant` and to `schedule.json`. Cannot be combined with `HANI2_ASSISTANT_CLASS` or `HANI2_ASSISTANT=off` (refused at startup). Set by `--assistants`. See [Assistant pools and assignment](assistant.md#assistant-pools-and-assignment). |
| `HANI2_ASSISTANT_CLASS` | none | Assistant class for everyone. Set by `--assistant <class>`. Wins over `assistants` in study.yaml / project.yaml and `agent_class`. Cannot be combined with `HANI2_ASSISTANTS`. |
| `HANI2_ASSISTANT` | none | `on`, `off` or `auto`; overrides `mode` in `assistant_settings.json`. Set by `--assistant`. Also accepts `1`/`true`/`yes`/`enabled`, `0`/`false`/`no`/`disabled` and `admin`/`admins`. |
| `HANI2_VERBOSE` | none | `1` asks opponents to print what they do. Set by `--verbose`. |
| `HANI2_CUSTOM_AGENTS` | none | Comma-separated opponent specs for the `:custom` group. |
| `HANI2_SCENARIOS_BASE` | none | Scenario folder to use when the study provides none, instead of the project's or the settings' `scenarios`. Set by `--scenarios`. |
| `HANI2_SCENARIO_SET` | none | The scenario set to use. Set by `--scenario-set`. |
| `HANI2_SCENARIO_TYPES` | none | Python files or modules that register extra scenario types, comma separated. Set by `--scenario-types`. |
| `HANI2_PER_NEG_YAML` | none | Path or name (`evaluation`) of the questionnaire file; takes precedence over the study, project and settings folders. |
| `HANI2_PRE_YAML` | none | Path or name (`expertise`) of the pre-questionnaire; takes precedence over `env.json` and the folders. |
| `HANI2_POST_YAML` | none | Path or name of the post-session questionnaire; takes precedence over `env.json` and the folders. See [Study forms](study-forms.md). |
| `HANI2_EVENTS` | `1` | `0`, `false`, `no` or `off` disables the event log. |
| `HANI2_RECORD` | `1` | `0`, `false`, `no` or `off` disables [recordings](recordings.md). |
| `HANI2_REPLAY_DIRS` | none | Extra folders of recordings shown in the replay tool (`os.pathsep`-separated). Set by `hani2 replay open PATHS`. |
| `HANI2_LLM_LOG` | off | `1`, `true`, `yes` or `on` logs every LLM call opponents make. |
| `HANI2_OLLAMA_LOCAL_BASE` | `http://localhost:11434` | The local Ollama daemon: the `ollama-local` connection, and the fallback entry after a remote Ollama in old settings. |
| `HANI2_SETTINGS_OVERRIDES` | none | The [start-time settings file](#start-time-settings-file). Set by `--settings`. |
| `HANI2_MODELS` | none | The start-time model list (`provider:model` or `connection:model`, comma separated); replaces the settings folder's model chains, loses to a project's or study's own. Set by `--models`. See [Models and connections](models.md). |
| `HANI2_MODEL_PROBE` | `on` | `off` checks only a connection's credentials before using an entry (no network check). |
| `HANI2_MODEL_PROBE_TIMEOUT` | `3` | Seconds a provider check may take. |
| `HANI2_WORKERS` | `32` | Size of the worker thread pool. |
| `HANI2_CODE_BASE` | none | First folder searched for `pan.py`, the module behind the `:pan` group. |
| `SCMLWEB_CODE_BASE` | `~/scmlweb` | `$SCMLWEB_CODE_BASE/python` is also searched for `pan.py`. |
| `PROLIFIC_N_REQUIRED` | `5` | Counted rounds a Prolific participant completes. |
| `PROLIFIC_PRACTICE_TIME_LIMIT` | `300` | Time limit of the practice round, in seconds. |
| `PROLIFIC_COUNTED_TIME_LIMIT` | `600` | Time limit of counted rounds, in seconds. |
| `PROLIFIC_AUTO_START_SECONDS` | `120` | Seconds before a loaded round starts by itself. |
| `PROLIFIC_AUTO_LOAD_SECONDS` | `30` | Seconds before the next round loads by itself. |
| `PROLIFIC_AUTO_LOAD_PRACTICE_SECONDS` | `60` | The same, after the practice round. |
| `PROLIFIC_AUTO_LOAD_WARN_SECONDS` | `15` | When to warn before an automatic load. |
| `PROLIFIC_MAX_MINUTES` | `45` | Expected maximum study duration in minutes, recorded with the participant's study metadata. |
| `PROLIFIC_FINALISTS` | none | Opponent pool for counted rounds. Empty: the normal opponent pool. |
| `PROLIFIC_PRACTICE_OPPONENTS` | `:pan` | Opponent agents for the practice round (old name `PROLIFIC_PRACTICE_AGENTS`). |
| `PROLIFIC_PER_NEG_YAML` | none | Same as `HANI2_PER_NEG_YAML`, checked second. |
| `PROLIFIC_COMPLETION_URL` | none | Completion link; `{pid}` is replaced by the participant's ID. |
| `PROLIFIC_COMPLETION_CODE` | none | Value of the `{{completion_code}}` text variable (else `completion_code` in `study.yaml`). |
| `SCMLWEB_BASE_URL` | `https://anac.cs.brown.edu` | Base of the default completion link. |
| `SCMLWEB_PROLIFIC_PATH` | `/prolific` | Path of the default completion link. |

The [Prolific guide](prolific.md) explains the `PROLIFIC_*` variables in detail.

## Confusing combinations

Settings that mean the same thing (a new name and its old one) or contradict each other are
refused with a message that says which one to keep. Each old name alone keeps working.

| Where | Refused | Use |
| --- | --- | --- |
| Command line | `--assistant <class>` with `--assistants` | `--assistants` alone (a pool may hold one class) or `--assistant <class>` alone; `--assistant on` / `auto` may be combined with `--assistants` |
| Command line | `--assistant off`, `--no-assistant` or `--no-support-agent` (its old name) with `--assistants`; `--no-assistant` with `--assistant on` / `auto` / a class | one of them |
| Command line | a new name with its old name: `--assistant` with `--support-agent`, `--study` with `--experiment`, `--opponents` with `--agents`, `--scenario-set` with `--set` | the new name |
| Command line | an option that contradicts the environment (e.g. `--assistant <class>` while `HANI2_ASSISTANTS` is set) | unset the variable or drop the option |
| Environment (at startup) | `HANI2_ASSISTANT_CLASS` (or `HANI2_SUPPORT_AGENT_CLASS`) with `HANI2_ASSISTANTS` | one of them |
| Environment (at startup) | `HANI2_ASSISTANT=off` (or `HANI2_SUPPORT_AGENT=off`) with `HANI2_ASSISTANTS` | one of them |
| Environment (at startup) | different values in `HANI2_ASSISTANT` / `HANI2_SUPPORT_AGENT`, `HANI2_ASSISTANT_CLASS` / `HANI2_SUPPORT_AGENT_CLASS`, `HANI2_OPPONENTS` / `HANI2_AGENTS`, `PROLIFIC_PRACTICE_OPPONENTS` / `PROLIFIC_PRACTICE_AGENTS`, `HANI2_PER_NEG_YAML` / `PROLIFIC_PER_NEG_YAML` | the first (new) name |
| Environment (at startup) | `HANI2_STUDY` and `HANI2_EXPERIMENT` naming different studies | `HANI2_STUDY` |
| `env.json` (at startup) | `opponents` and its old name `agents` with different values | `opponents` |
| Command line | `--models` while `HANI2_MODELS` is set to a different list; a list that cannot be read | one of them; `provider:model` entries |
| Environment (at startup) | a `HANI2_MODELS` list that cannot be read (not `provider:model`, an unknown provider or connection) | a valid list |
| `models.json` (at startup and when saved) | the settings folder's `models.json` with an unknown purpose, an entry without a model, or a key, token, header or address among an entry's `params` | purposes `default`, `assistant`, `opponent`, `tools`, `text`, `judge`; secrets on a connection |
| `study.yaml` / `project.yaml` | a setting at the top level and under `overrides:` / `defaults:` with different values; an unknown scheduling method | one place; a method from `hani2 scheduling list` |
| Group files | `assistant` and its old name `support_agent` naming different Assistants; members under both `assistants` and `agents` (Assistant groups) with different lists | `assistant`; `assistants` |

The startup checks run in `hani2` before anything is set and again when the server starts, so a
server launched another way (for example `uvicorn hani2.server:app`) is checked too. Files are
refused when saved through the admin API (400) or the command line; a hand-edited file that has
a problem is reported in the server log, `hani2 study show` and the admin study page (`errors`),
and a conflicting group file makes the Assistant fail loudly. The same pair given with *equal*
values (as `hani2` itself sets `HANI2_ASSISTANT` and `HANI2_SUPPORT_AGENT`) is fine. API keys for language models are read from the variables you name in `api_key_env`, or, for LLM opponents, from each provider's standard variable.
