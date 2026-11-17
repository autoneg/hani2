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
| `--support-agent` | none | Who gets the support agent: `on`, `off`, `auto` (admins only), or a support-agent class for everyone (`package.module:Class` or `path/to/file.py:Class`). Sets `HANI2_SUPPORT_AGENT` (and `HANI2_SUPPORT_AGENT_CLASS` for a class), overriding `mode` and `agent_class` in `support_agent_settings.json`. |
| `--no-support-agent` | off | Run without a support agent; the same as `--support-agent off`. |
| `--experiment` | none | Run this experiment (see `hani2 experiment create`). Sets `HANI2_EXPERIMENT`. |
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
hani2 --support-agent off --experiment pilot-1
hani2 --no-support-agent --opponents :template       # Human-Agent Negotiation competition
hani2 --support-agent submissions/team_a.py:TeamAgent # Hybrid Intelligence: a submitted assistant
PYTHONPATH=$PWD hani2 --page play      # make local modules (custom agents, tools) importable
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
experiment      -
auth mode       password  (oauth: none)
support agent   on
```

`auth mode` is the effective mode after fallbacks (for example `oauth` falls back to `password` when no provider is configured). It honours `HANI2_HOME`, `HANI2_EXPERIMENT` and `HANI2_SUPPORT_AGENT`.

## `hani2 generate`

```bash
hani2 generate [OPTIONS]
```

Generates a pool of scenarios with the built-in generators, keeping only scenarios whose opposition lies in a given range. See [Scenarios](../guide/scenarios.md) for the folder layout it produces.

| Option | Default | Description |
| --- | --- | --- |
| `--type`, `-t` | all | Scenario type to generate (`Trade`, `Island`, `Grocery`). Repeat the option for several types. |
| `--count`, `-n` | `50` | Scenarios per type. |
| `--base` | the scenarios folder | Pool directory to write into. |
| `--human-index` | `1` | The human's negotiator index. |
| `--cache-inverter` / `--no-cache-inverter` | on | Cache the utility inverse with each scenario, so loading is fast. |
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
hani2 generate -t Trade -t Grocery -n 20 --seed 7
```

## `hani2 experiment`

Experiments are self-contained studies with their own settings, scenarios and results. See [Studies and results](../guide/studies.md).

### `hani2 experiment create`

```bash
hani2 experiment create NAME [--force] [--opponents SPECS] [--no-support-agent | --support-agent VALUE] [--no-webmcp]
```

Scaffolds `<experiments>/NAME` (by default `~/negmas/hani2/experiments/NAME`) with:

- `results/` (empty),
- `questionnaires/per_negotiation.yaml` (the example questionnaire, active),
- copies of `consent.md`, `scenario_order.txt` and `announcements.md` from the active settings,
- `scenarios/`, a copy of the current scenarios folder (or of the bundled samples).

`--force`, `-f` overwrites existing files. `--no-support-agent` writes `{"mode": "off"}` to the experiment's `support_agent_settings.json` and `{"allowed": false}` to its `autopilot_settings.json`, so participants negotiate without an assistant (as in a competition). `--support-agent` takes the same values as the server option (`on`, `off`, `auto` or a class) and writes `mode` (and `agent_class`) to the experiment's `support_agent_settings.json`; `off` also turns the autopilot off. `--opponents` writes the opponent agents to the experiment's `env.json` (`opponents`). `--no-webmcp` sets `webmcp.enabled` to `false` in the experiment's `env.json`. The command prints how to run the experiment:

```bash
hani2 --experiment NAME
```

### `hani2 experiment list`

```bash
hani2 experiment list
```

Lists the experiments with the number of participants who have a `results.csv` in each.

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
