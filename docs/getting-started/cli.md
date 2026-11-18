# Command line

HANI2 installs a single command, `hani2`. Without a subcommand it starts the server. Every command accepts `--help`.

```text
hani2 [OPTIONS] [COMMAND]
```

## Starting the server

```bash
hani2 [OPTIONS]
```

Starts the HANI2 server: the app, the playground, the admin console and the API on one port. If the settings folder has no `env.json` yet, it first runs `hani2 setup` silently. It then prints the URLs and the settings folder:

```text
  HANI2 0.1.0
  App         http://localhost:5006/app
  Playground  http://localhost:5006/play
  Admin       http://localhost:5006/admin
  Settings    /home/me/negmas/hani2/settings
```

| Option | Default | Description |
| --- | --- | --- |
| `--port`, `-p` | `5006` | Port to listen on. |
| `--host` | `127.0.0.1` | Interface to bind. Use `0.0.0.0` to accept remote connections. |
| `--opponents`, `--opponent`, `-o` | none | The opponent agent(s) participants negotiate against: comma-separated negotiators and/or group tokens (`:llm`, `:template`, `:notext`, `:negmas`, `:classic`, `:genius`, `:custom`). Sets `HANI2_OPPONENTS`. The old name `--agents` still works. See [Opponents](../guide/opponents.md). |
| `--assistant` | none | Who gets the Assistant: `on`, `off`, `auto` (admins only), or a Assistant class for everyone (`package.module:Class` or `path/to/file.py:Class`). Sets `HANI2_ASSISTANT` (and `HANI2_ASSISTANT_CLASS` for a class), overriding `mode` and `agent_class` in `assistant_settings.json`. |
| `--no-assistant` | off | Run without an Assistant; the same as `--assistant off`. |
| `--assistants` | none | The Assistant pool: comma-separated Assistant classes and Assistant groups (`:default`, `:tutorial`, `:<key>` for a group file). With more than one, each human keeps one Assistant for the whole study, balanced across the study's humans. Every member is loaded before the server starts. Sets `HANI2_ASSISTANTS`. See [Assistant pools and assignment](../guide/assistant.md#assistant-pools-and-assignment). |

The old names `--support-agent` and `--no-support-agent` still work, here and in `hani2 experiment create` (see [Old names](../guide/assistant.md#old-names)).
| `--tools` | none | Extra tools: comma-separated `package.module:Class`, `path/to/file.py:Class`, or a folder or `.py` file (every tool in it, see [Build a tool](../tutorials/tools.md#set-up)). Each is loaded before the server starts. Sets `HANI2_TOOLS`. Tools with `timing = "agent"` appear only when the Assistant adds them. |
| `--study` | none | The default study, as `project/study`, for URLs without one (see `hani2 study create`). Every study is still reachable at `/s/<project>/<study>/`. Sets `HANI2_STUDY`. |
| `--experiment` | none | Old name: the default study is this experiment, `default/<name>` (see `hani2 experiment create`). Sets `HANI2_EXPERIMENT`. |
| `--scenario-set`, `--set` | the default set | The [scenario set](../guide/scenario-sets.md) to use, e.g. `HAN2026` or `ANAC2027` (any case). Sets `HANI2_SCENARIO_SET`. Admins can still change it per session. |
| `--scenario-types` | none | Python files or modules that register extra scenario types, comma separated. Sets `HANI2_SCENARIO_TYPES`. See [Writing your own scenario type](../guide/scenarios.md#writing-your-own-scenario-type). |
| `--scenarios` | the settings' scenarios folder | A folder of saved scenarios to serve. Sets `HANI2_SCENARIOS_BASE`. |
| `--browser` / `--no-browser` | `--browser` | Open the browser once the server answers. |
| `--page` | `app` | Page to open in the browser: `app`, `play` or `admin`. |
| `--verbose` / `--no-verbose` | off | Ask negotiators to print what they do (sets `HANI2_VERBOSE=1`). Opponents whose constructor accepts `verbose` get `verbose=True`. |
| `--dev` / `--no-dev` | off | Auto-reload the server when Python files change. |
| `--version` | | Print the version and exit. |

The server always runs a single worker process, because sessions live in memory. See [Architecture](../reference/architecture.md).

Examples:

```bash
hani2 --port 8080 --host 0.0.0.0 --no-browser
hani2 --opponents ":template,AspirationNegotiator" --page play
hani2 --assistant off --experiment pilot-1
hani2 --no-assistant --opponents :template       # Human-Agent Negotiation competition
hani2 --assistant submissions/team_a.py:TeamAgent # Hybrid Intelligence: a submitted assistant
hani2 --assistants "team_a.agent:A,team_b.agent:B"  # compare two Assistants, balanced per study
PYTHONPATH=$PWD hani2 --page play      # make local modules (custom agents, tools) importable
hani2 --tools ./my-tools --page play   # load every tool in ./my-tools
```

## `hani2 setup`

```bash
hani2 setup [--force] [--admin-password TEXT]
```

Creates the settings folder with the default settings files, the sample scenarios (in the `Examples` category, `settings/scenarios/Examples/`) and the default users. Existing files are kept unless you pass `--force`.

| Option | Description |
| --- | --- |
| `--force`, `-f` | Overwrite existing settings files and sample scenarios. |
| `--admin-password` | Password for the `admin` account. It is written to `admin.password` in `env.json` and, if the account already exists, set on it. |

See [Installation](installation.md) for the list of files it creates.

## `hani2 info`

```bash
hani2 info
```

Shows where HANI2 keeps its files and how it is configured:

```text
version         0.1.0
home            /home/me/negmas/hani2
settings        /home/me/negmas/hani2/settings
scenarios       /home/me/negmas/hani2/settings/scenarios
results         /home/me/negmas/hani2/db
study           -  (no study folder)
auth mode       password  (oauth: none)
assistant       on
assistants      study / project / assistant_settings.json
opponents       built-in default pool
```

`auth mode` is the effective mode after fallbacks (for example `oauth` falls back to `password` when no provider is configured). It honours `HANI2_HOME`, `HANI2_EXPERIMENT` and `HANI2_ASSISTANT`.

## `hani2 generate`

```bash
hani2 generate [OPTIONS]
```

Generates a pool of scenarios with the registered generators, keeping only scenarios whose opposition lies in a given range. See [Scenarios](../guide/scenarios.md) for the folder layout it produces.

| Option | Default | Description |
| --- | --- | --- |
| `--type`, `-t` | the active set | Scenario type to generate. Repeat the option for several types. |
| `--set` | the active set | Generate every type of this scenario set. |
| `--count`, `-n` | `50` | Scenarios per type. |
| `--base` | the scenarios folder | Pool directory to write into. |
| `--human-index` | `1` | The human's negotiator index. |
| `--cache-inverter` / `--no-cache-inverter` | on | Cache the utility inverse of every role with each scenario, so loading is fast. |
| `--rebuild-inverses` | off | Only rebuild the cached inverses of existing scenarios. |
| `--min-opposition` | `0.35` | Minimum opposition of an accepted scenario. |
| `--max-opposition` | `0.90` | Maximum opposition of an accepted scenario. |
| `--set-reservations` / `--no-set-reservations` | on | Draw random reserved values. |
| `--user-reserved-max` | `0.10` | Upper bound of the human's reserved value. |
| `--agent-reserved-max` | `0.20` | Upper bound of the agent's reserved value. |
| `--max-tries` | `60` | Attempts per scenario to hit the opposition range. |
| `--seed` | `0` | Random seed. |
| `--force` | off | Overwrite existing scenarios. |

```bash
hani2 generate -t Trade -t Grocery -n 20 --seed 7   # the same seed always gives the same pool
hani2 generate --set ANAC2027 -n 20
```

## `hani2 scenario`

```bash
hani2 scenario new TYPE DEST [--generate] [--seed N] [--force]
hani2 scenario check PATH... [--fill-hints]
```

`new` copies the template folder of a scenario type to `DEST` so you can edit it by hand; with `--generate` it writes a draw of the type's generator instead (seeded, within the default opposition band). `check` validates scenario folders, categories or whole scenario directories: each scenario must load, show an offer and load back unchanged after saving; missing texts and hints are reported as warnings, and `--fill-hints` adds the computed hints. It exits with code 1 when a scenario has errors. See [Writing a scenario by hand](../guide/scenarios.md#writing-a-scenario-by-hand).

## `hani2 sets`

```bash
hani2 sets [NAME]
```

Lists the scenario sets with their scenario types, marks the active and the default set, and flags types that have neither a generator nor a folder. See [Scenario sets](../guide/scenario-sets.md).

## `hani2 groups`

```bash
hani2 groups list [--project P | --study P/S] [--kind opponent|assistant] [--no-builtin]
```

Lists the opponent and Assistant groups with their members, the file each comes from (and
whether another file shadows it), a group file's description and `assistant`. Without options it
shows the groups as the server's default study resolves them; `--project` lists a project's
folder, its studies and the settings folder. See [Group files](../guide/opponents.md#group-files)
and [Assistant groups](../guide/assistant.md#assistant-groups).

```text
Opponent groups
  :finalists              project    /home/me/negmas/hani2/projects/HI2027/groups/finalists.json
      members: a123.module.FinalistA, a456.module.FinalistB
  :llm                    builtin    built-in
      Negotiators driven by a language model
      members: LLMHybridNegotiator, LLMBoulwareTBNegotiator, ...
Assistant groups
  :default                builtin    built-in
      members: hani2.assistant:Assistant
```

## `hani2 project` and `hani2 study`

Create and inspect [projects and studies](../guide/projects.md):

```bash
hani2 project create HI2027 --kind assistant --full-name "Human-AI Interaction League 2027" --year 2027 \
    --organizer "The Lab" --contact lab@example.org
hani2 project list
hani2 project show HI2027
hani2 study create HI2027/hi-2027-01 --type prolific --title "January run" --completion-code C1A2B3 \
    --prolific-study-id 65a0c0ffee
hani2 study list [PROJECT]
hani2 study show HI2027/hi-2027-01
```

`project create` writes `projects/NAME/project.yaml` (`--description` is `short_description`). `study create PROJECT/STUDY` writes `projects/PROJECT/studies/STUDY/study.yaml` and `results/`, creating the project when it is missing; the other options are `--completion-url`, `--link`, `--start`, `--end`, `--n-required`, `--end-text` and `--type prolific|online|lab` (default `prolific`). Running `create` again updates the given fields. `study create` and `study show` print the links to give participants, for example:

```text
  Prolific study URL   https://example.org/s/HI2027/hi-2027-01/play?PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}
  Play page            https://example.org/s/HI2027/hi-2027-01/play
  App (log in)         https://example.org/s/HI2027/hi-2027-01/app
```

The links start with `--base-url`, else `HANI2_PUBLIC_URL`, else `public_url` in `env.json`, else `http://localhost:5006`. A bare name (`hani2 study create pilot`) is a study of the `default` project, that is, an experiment folder.

## `hani2 experiment`

An experiment is a study of the `default` project; these commands keep their earlier behaviour.

Experiments are self-contained studies with their own settings, scenarios and results. See [Studies and results](../guide/studies.md).

### `hani2 experiment create`

```bash
hani2 experiment create NAME [--force] [--opponents SPECS] [--tools CLASSES] [--no-assistant | --assistant VALUE] [--no-webmcp]
```

Scaffolds `<experiments>/NAME` (by default `~/negmas/hani2/experiments/NAME`) with:

- `results/` (empty),
- `questionnaires/per_negotiation.yaml` (the example questionnaire, active),
- copies of `consent.md`, `scenario_order.txt` and `announcements.md` from the active settings,
- `scenarios/`, a copy of the current scenarios folder (or of the bundled samples).

`--force`, `-f` overwrites existing files. `--no-assistant` writes `{"mode": "off"}` to the experiment's `assistant_settings.json` and `{"allowed": false}` to its `autopilot_settings.json`, so participants negotiate without an assistant (as in a competition). `--assistant` takes the same values as the server option (`on`, `off`, `auto` or a class) and writes `mode` (and `agent_class`) to the experiment's `assistant_settings.json`; `off` also turns the autopilot off. `--opponents` writes the opponent agents to the experiment's `env.json` (`opponents`), and `--tools` adds the tool classes, folders and files to its `tools.extra`. `--no-webmcp` sets `webmcp.enabled` to `false` in the experiment's `env.json`. The command prints how to run the experiment:

```bash
hani2 --experiment NAME
```

### `hani2 experiment list`

```bash
hani2 experiment list
```

Lists the experiments with the number of participants who have a `results.csv` in each.

## `hani2 replay`

Explore, replay and evaluate [recordings](../guide/recordings.md). `PATHS` are recording files or
folders (default: the results folder).

| Command | What it does |
| --- | --- |
| `hani2 replay open [PATHS…] [--port 5006]` | Start the server and open the replay tool, also listing recordings in `PATHS`. |
| `hani2 replay list [PATHS…] [--all]` | List recordings with their result and length (`--all`: also those where no negotiation started). |
| `hani2 replay show FILE [--events]` | What a recording holds. |
| `hani2 replay export FILE -o out.json` | The recording as plain JSON. |
| `hani2 replay metrics` | Every [evaluation metric](../guide/evaluation.md) and its columns. |
| `hani2 replay evaluate [PATHS…] [-m a,b] [--llm] [--refresh] [-o file.csv] [--option k=v]` | One row of metrics per recording; `.json` output also works. |
| `hani2 replay compare [PATHS…] --by opponent [-m …] [--llm] [-o file.csv]` | Means per group, and pass^k reliability. |

```bash
hani2 replay evaluate -m outcome,optimality,system_use,engagement_flags -o metrics.csv
hani2 replay compare --by support_agent --columns human_utility,suggestion_adoption,llm_tokens
```

## `hani2 tools`

Commands for tools. Tool files saved in the tools folder (`$HANI2_HOME/tools`) are loaded automatically; see [Build a tool](../tutorials/tools.md).

### `hani2 tools list`

Lists every tool the server would offer: its name, pane and timing, whether it is admin-only or off by default, and where it comes from (built-in, a package, a file). Tools without a help text are flagged.

### `hani2 tools path`

Prints the folders and files searched for tools: the tools folder, `env.json` → `tools.paths`, and the folders and files in `tools.extra` and `--tools` (`HANI2_TOOLS`).

### `hani2 tools new`

```bash
hani2 tools new NAME [--llm] [--folder DIR] [--force]
```

Writes a new tool file, ready to edit, named after `NAME` (`"Deal Summary"` becomes `deal_summary.py` with the class `DealSummary`). With `--llm` the tool is an `LLMTool` that asks the language model. The file goes into the tools folder unless you pass `--folder`; `--force` overwrites an existing file.

## `hani2 users`

Manages the accounts in `settings/users.json`. See [Authentication](../guide/authentication.md).

### `hani2 users list`

Lists every user with its role (`admin` or `user`) and email.

### `hani2 users add`

```bash
hani2 users add USERNAME [--password TEXT] [--admin] [--email TEXT]
```

Creates an account. You are prompted for the password (twice) when you omit `--password`. `--admin` gives the account the admin role. Accounts created here count as having consented. The command fails if the username is taken, reserved (`ai`, `agent`, `guest`, `admin2`, or anything starting with `prolific_`), contains spaces or path characters, or if the password is shorter than 4 characters.

### `hani2 users passwd`

```bash
hani2 users passwd USERNAME [--password TEXT]
```

Sets a user's password. Prompts when `--password` is omitted.

### `hani2 users remove`

```bash
hani2 users remove USERNAME
```

Deletes an account and its metadata. Results already written for that user are kept.
