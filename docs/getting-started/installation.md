# Installation

HANI2 is a regular Python package. The web interface ships pre-built inside the wheel, so you do not need Node.js unless you change the frontend.

## Requirements

- Python 3.11 or newer (3.11 to 3.15 are tested).
- A modern browser.
- Optional: a language model. The built-in Assistant, the LLM opponents and the message-writing tools need one. A local model served by [Ollama](https://ollama.com) works; so does any hosted provider. See [Language models](../guide/llms.md).

## Install the package

=== "pip"

    ```bash
    python -m venv .venv
    source .venv/bin/activate
    pip install hani2
    ```

=== "uv"

    ```bash
    uv venv
    source .venv/bin/activate
    uv pip install hani2
    ```

    Or run it without installing it into a project:

    ```bash
    uvx hani2
    ```

=== "pipx"

    ```bash
    pipx install hani2
    ```

The package installs one command, `hani2`. Check it with:

```bash
hani2 --version
```

## Create the settings folder

```bash
hani2 setup
```

`hani2 setup` creates the settings folder, `~/negmas/hani2/settings` by default, and fills it with:

| Path | What it is |
| --- | --- |
| `env.json` | The main deployment configuration: title, authentication, opponents, negotiation defaults, tools. |
| `llm_settings.json` | The language model used to write and read negotiation messages and by LLM opponents. |
| `assistant_settings.json` | The Assistant: who gets it, its model, autonomy and capabilities. |
| `autopilot_settings.json` | Whether autopilot is allowed and which drivers are offered. |
| `consent.md` | The consent form shown at registration. |
| `announcements.md` | The welcome text shown before a negotiation. |
| `scenario_order.txt` | The scenario types of the `Custom` set, in order. |
| `scenario_sets.yaml` | The [scenario sets](../guide/scenario-sets.md) and the default set. |
| `questionnaires/per_negotiation.example.yaml` | An example post-negotiation questionnaire. It is inactive until you rename it to `per_negotiation.yaml`. |
| `scenarios/Examples/` | The three sample scenarios `Trade`, `Island` and `Grocery`, as one `Examples` category. The `Trade`, `Island` and `Grocery` scenario types themselves are generated fresh for each round until you build pools with `hani2 generate`. |
| `users.json`, `users_meta.json` | The user store, with two default accounts: `admin` (password `adminpass`) and `user` (password `userpass`). |

Existing files are kept. Use `--force` to overwrite them with the defaults, and `--admin-password` to choose the admin password:

```bash
hani2 setup --admin-password 's3cret'
```

You can skip this step: the first `hani2` run calls setup for you when `env.json` is missing.

The [configuration reference](../guide/configuration.md) documents every file and key.

### Choosing another home folder

Everything HANI2 writes lives under one home folder, `~/negmas/hani2` by default:

```text
~/negmas/hani2/
├── settings/      # configuration, users, scenarios
├── db/            # results, per-user data and events.db
└── experiments/   # one folder per experiment (see Studies)
```

Set `HANI2_HOME` to move it, for example to keep a separate installation per study:

```bash
export HANI2_HOME=/srv/hani2-pilot
hani2 setup
hani2
```

`hani2 info` prints the folders in use.

## Run the server

```bash
hani2
```

The server listens on `http://127.0.0.1:5006` and opens your browser. One port serves:

| URL | Purpose |
| --- | --- |
| `/app` | The negotiation interface for logged-in users. |
| `/play` | The no-login playground. Prolific participants arrive here with `?PROLIFIC_PID=...`. |
| `/admin` | The admin console. |
| `/api/...` | The REST and WebSocket API used by the web app. |

Continue with the [quick start](quickstart.md).

## Upgrading

```bash
pip install --upgrade hani2      # or: uv pip install --upgrade hani2
```

Upgrading never touches your settings folder. New settings keys get their default values automatically, because every JSON settings file is merged over the defaults bundled with the package. To see the new defaults side by side with your files, run `hani2 setup` with a temporary home:

```bash
HANI2_HOME=$(mktemp -d) hani2 setup
```

## Installing from source

```bash
git clone https://github.com/autoneg/hani2
cd hani2
uv venv
uv pip install -e '.[dev]'
```

A source checkout does not contain the built web app. Build it once (Node.js 20 or newer is recommended):

```bash
cd frontend
npm install
npm run build
```

The build writes to `src/hani2/web`, which is where the server looks for it. Until it exists, every page returns a short "the web interface has not been built" message.

For frontend work, run the Vite dev server next to the backend. It proxies `/api` (including the WebSocket) to port 5006:

```bash
hani2 --no-browser --dev        # terminal 1: backend with auto-reload
cd frontend && npm run dev      # terminal 2: http://localhost:5173
```

To build the documentation:

```bash
uv pip install -e '.[docs]'
mkdocs serve
```

## Troubleshooting

**The page says the web interface has not been built.**
You are running from a source checkout. Build the frontend as shown above.

**`Address already in use`.**
Another process holds port 5006. Pick another one with `hani2 --port 8080`.

**Other computers cannot reach the server.**
The server binds to `127.0.0.1` by default. Use `hani2 --host 0.0.0.0` and open the port in your firewall. For a public deployment, put a reverse proxy with HTTPS in front of it and forward WebSocket upgrades for `/api/ws/`.

**The assistant or LLM opponents never answer.**
No language model is reachable. With the default settings HANI2 expects Ollama on `http://localhost:11434` with the model `qwen3:4b-instruct`. Run `ollama pull qwen3:4b-instruct`, or configure another provider. See [Language models](../guide/llms.md).

**I forgot the admin password.**
Run `hani2 users passwd admin`.

**Everyone was logged out after a restart.**
Login cookies are signed with `auth.cookie_secret` from `env.json`. When it is empty, HANI2 generates one and stores it in `settings/.cookie_secret`. Deleting that file, or changing `HANI2_HOME`, invalidates existing cookies.

### Serving under a sub-path

Behind a reverse proxy you can mount HANI2 under a path such as `/hanplay`: start it with `hani2 --root-path /hanplay` (or set `HANI2_ROOT_PATH`). It works whether the proxy strips the prefix or forwards it unchanged. Forward WebSocket upgrades for `<prefix>/api/ws/`.
