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
│   ├── consent.md                consent form (Markdown)
│   ├── announcements.md          welcome text (Markdown)
│   ├── scenario_order.txt        order of scenario categories
│   ├── questionnaires/           per_negotiation.yaml (optional)
│   ├── scenarios/                scenario categories
│   ├── users.json                password hashes
│   ├── users_meta.json           user metadata
│   └── .cookie_secret            generated cookie secret
├── db/                           results and events (when no experiment is active)
└── experiments/<name>/           one folder per experiment
```

## Precedence

Each settings file is looked up in up to three places. The first one that exists wins:

1. `<experiment>/<file>`, when an experiment is active (`--experiment` or `HANI2_EXPERIMENT`),
2. `$HANI2_HOME/settings/<file>`,
3. the defaults bundled with the package.

JSON files are then **merged over the built-in defaults**: HANI2 starts from its internal defaults, merges the bundled file over them, and merges the chosen file over the result. Nested objects merge key by key, so a file only needs the keys you change:

```json title="env.json"
{"negotiation": {"n_steps": 30}}
```

The JSON files are merged in layers: the bundled defaults, then the settings folder, then the experiment folder. A key set in a later layer wins; keys it does not mention keep their earlier value.

Text files (`consent.md`, `announcements.md`, `scenario_order.txt`) are taken from the first location that has them.

The admin console always saves to the settings folder. While an experiment with its own copy of a file is active, edits to that file in the console have no effect; edit the experiment's copy instead.

Scenarios, results and questionnaires follow their own rules, described in [Scenarios](scenarios.md) and [Studies and results](studies.md).

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
    "allow_registration": true
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

### `admin`

| Key | Default | Meaning |
| --- | --- | --- |
| `admin.password` | `"adminpass"` | Initial password of the `admin` account, used when the account is created. |
| `admin.emails` | `[]` | Users whose email is in this list are admins (case-insensitive). |

### `auth` and `oauth`

| Key | Default | Meaning |
| --- | --- | --- |
| `auth.mode` | `"password"` | `password`, `oauth`, `dual`, `none` or `auto`. |
| `auth.cookie_secret` | `""` | Secret for signing login cookies. Generated and stored in `settings/.cookie_secret` when empty. |
| `auth.enforce_consent` | `false` | Require logged-in users to sign the consent form before negotiating. |
| `auth.allow_registration` | `true` | Offer the registration form. |
| `oauth.redirect_uri` | `""` | Public base URL used to build `/api/oauth/<provider>/callback`. Empty: the request's base URL. |
| `oauth.providers.github` | disabled | `enabled`, `key` (client ID), `secret`. |
| `oauth.providers.google` | disabled | `enabled`, `key` (client ID), `secret`. |

See [Authentication](authentication.md).

### `opponents`

A list of opponent specs and group tokens that form the default opponent pool, for example `["AspirationNegotiator", ":template"]`. Empty means the built-in default pool. It has lower precedence than the `?opponents=`/`?group=` URL parameters, `--opponents`/`HANI2_OPPONENTS` and the admin session setting `opponent_types`. The older key `agents` is still read when `opponents` is empty. See [Opponents](opponents.md).

### `negotiation`

Default values of the per-session negotiation settings. Every key below may appear here. Admins can change them per session in the settings drawer of the negotiation page.

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
| `allow_moving_tools` | `true` | Let the human move tools between panes. |
| `load_existing` | `true` | Load saved scenarios instead of generating new ones. Off in the playground unless the URL has `?load_existing=1`. |
| `generate_on_failure` | `true` | Generate a scenario when none can be loaded. |
| `predefined_order` | `true` | Present scenario types in the order of the active scenario set. Always off in the playground. |
| `allow_scenario_selection` | `false` | Let non-admins pick the scenario. |
| `show_opponent_type` | `false` | Show the opponent agent's type. Always on for admins. (Old name: `show_partner_type`.) |
| `opponent_types` | `[]` | Opponent agents for this session. (Old name: `partner_types`.) |

The Prolific flow overrides some of these per round (for example the time limits). See [Prolific](prolific.md).

### `playground`

| Key | Default | Meaning |
| --- | --- | --- |
| `playground.enabled` | `true` | Allow the no-login playground at `/play`. Prolific links work even when it is off. |

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
| `tools.show_opponent_utility` | Let every participant show the opponent's utility in the Utility Plot and Trace (default `false`; admins always can). |
| `tools.overrides` | Per-tool changes keyed by tool name (case-insensitive): `pane`, `timing`, `enabled`, `admin_only`, `guest`, `order`, `at_front`. |
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

### `recording`, `evaluation` and `questionnaire`

| Key | Meaning |
| --- | --- |
| `recording.enabled` | Record every negotiation (default `true`). See [Recording and replay](recordings.md). |
| `evaluation.llm` | Language-model settings for the evaluation judge (same keys as `llm_settings.json`); default: the HANI2 language model. |
| `evaluation.assertions` | Statements for the `nl_assertions` metric. See [Evaluation metrics](evaluation.md#language-model-judgements). |
| `questionnaire` | The questionnaire after each negotiation, by name (`evaluation`) or path. |

## `llm_settings.json`

The language model for LLM opponents and for the message helpers.

| Key | Default | Meaning |
| --- | --- | --- |
| `provider` | `"ollama"` | Opponents: any litellm provider. Message helpers: `ollama`, `openai` or `anthropic`. |
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

The old name of this file, `support_agent_settings.json`, is still read; where both exist, `assistant_settings.json` is merged over it (see [Old names](assistant.md#old-names)).

| Key | Default | Meaning |
| --- | --- | --- |
| `mode` | `"on"` | Who gets the Assistant: `on` (everyone), `off` (nobody) or `auto` (admins only). Overridden by `--assistant`/`HANI2_ASSISTANT`. |
| `agent_class` | `null` | Your `Assistant` subclass, as `"module:Class"` or `"module.Class"`. `null`: the built-in agent. |
| `provider` | `"ollama"` | Any litellm provider. |
| `model` | `"qwen3:4b-instruct"` | Model name. |
| `api_key_env` | `"OPENAI_API_KEY"` | Name of the environment variable holding the key. |
| `api_base` | `null` | Custom endpoint URL. |
| `temperature` | `0.3` | Sampling temperature. |
| `max_tokens` | `2000` | Maximum answer length. |
| `max_tool_iterations` | `10` | Maximum rounds of function calls per user message. |
| `autonomy` | `"full"` | `suggest`, `semi` or `full`. |
| `capabilities` | all `true` | The sixteen capability switches: `chat`, `toast`, `tool_enable`, `tool_visibility`, `tool_order`, `fill_offer`, `fill_text`, `submit_counter`, `accept`, `end`, `highlight`, `annotate`, `layout`, `panels`, `tool_add`, `tool_use`. |
| `toolbox` | `[]` | Tool classes (`module:Class` or `path/to/file.py:Class`) the agent may add by name, in addition to its own `tools`. |
| `proactive.on_negotiation_started` | `false` | Speak up when a negotiation starts. |
| `proactive.on_action_requested` | `false` | Speak up at each of the human's turns. |
| `proactive.on_negotiation_ended` | `false` | Speak up when a negotiation ends. |
| `system_prompt` | built in | The assistant's system prompt. |

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

`questionnaires/per_negotiation.yaml` in the experiment or the settings folder defines the questionnaire shown after each negotiation. `hani2 setup` installs an inactive example as `per_negotiation.example.yaml`. See [Studies and results](studies.md) for the format.

## Environment variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `HANI2_HOME` | `~/negmas/hani2` | Root folder for settings, results and experiments. |
| `HANI2_EXPERIMENTS` | `$HANI2_HOME/experiments` | Folder that holds experiments. |
| `HANI2_EXPERIMENT` | none | Name of the active experiment. Set by `--experiment`. |
| `HANI2_OPPONENTS` | none | Opponent agents (comma-separated specs and group tokens). Set by `--opponents`. The old name `HANI2_AGENTS` is still read. |
| `HANI2_TOOLS` | none | Extra tool classes, folders and `.py` files, comma separated. Set by `--tools`. |
| `HANI2_ASSISTANT_CLASS` | none | Assistant class for everyone. Set by `--assistant <class>`. |
| `HANI2_ASSISTANT` | none | `on`, `off` or `auto`; overrides `mode` in `assistant_settings.json`. Set by `--assistant`. Also accepts `1`/`true`/`yes`/`enabled`, `0`/`false`/`no`/`disabled` and `admin`/`admins`. |
| `HANI2_VERBOSE` | none | `1` asks opponents to print what they do. Set by `--verbose`. |
| `HANI2_CUSTOM_AGENTS` | none | Comma-separated opponent specs for the `:custom` group. |
| `HANI2_SCENARIOS_BASE` | none | Scenario folder to use when no experiment provides one, instead of `settings/scenarios`. Set by `--scenarios`. |
| `HANI2_SCENARIO_SET` | none | The scenario set to use. Set by `--scenario-set`. |
| `HANI2_SCENARIO_TYPES` | none | Python files or modules that register extra scenario types, comma separated. Set by `--scenario-types`. |
| `HANI2_PER_NEG_YAML` | none | Path or name (`evaluation`) of the questionnaire file; takes precedence over the experiment and settings folders. |
| `HANI2_EVENTS` | `1` | `0`, `false`, `no` or `off` disables the event log. |
| `HANI2_RECORD` | `1` | `0`, `false`, `no` or `off` disables [recordings](recordings.md). |
| `HANI2_REPLAY_DIRS` | none | Extra folders of recordings shown in the replay tool (`os.pathsep`-separated). Set by `hani2 replay open PATHS`. |
| `HANI2_LLM_LOG` | off | `1`, `true`, `yes` or `on` logs every LLM call opponents make. |
| `HANI2_OLLAMA_LOCAL_BASE` | `http://localhost:11434` | Local Ollama daemon for the missing-model fallback. |
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
| `SCMLWEB_BASE_URL` | `https://anac.cs.brown.edu` | Base of the default completion link. |
| `SCMLWEB_PROLIFIC_PATH` | `/prolific` | Path of the default completion link. |

The [Prolific guide](prolific.md) explains the `PROLIFIC_*` variables in detail. API keys for language models are read from the variables you name in `api_key_env`, or, for LLM opponents, from each provider's standard variable.
