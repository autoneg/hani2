# Architecture

This page is for developers who extend HANI2, deploy it at scale, or write another client. It describes how the server is organised, how it talks to the browser and where the extension points are.

## Components

```text
browser (React app)  ── REST /api/... ──────────┐
        │                                        │
        └── WebSocket /api/ws/{sid} ── Hub ── NegotiationSession ── negmas SAOMechanism
                                                 ├── tools (hani2.tools)
                                                 ├── Assistant (hani2.assistant)
                                                 ├── autopilot
                                                 └── study (Prolific flow, questionnaires)
```

| Module | Role |
| --- | --- |
| `hani2.cli` | The `hani2` command (Typer). |
| `hani2.server` | The FastAPI app: REST API, WebSocket endpoint, OAuth, static files. |
| `hani2.hub` | Maps session IDs to sessions and to the open WebSockets; delivers messages. |
| `hani2.session` | `NegotiationSession`: scenario, mechanism, draft offer, history, tools, Assistant, autopilot. |
| `hani2.tool_controller` | Tool placement: panes, order, visibility, enable switch. |
| `hani2.tools` | The `Tool` base class, the UI components, the registry and the built-in tools. |
| `hani2.assistant` | The Assistant runtime, its function tools, capabilities, settings and the autopilot. |
| `hani2.agents` | Opponent specs, groups and the opponent factory. |
| `hani2.scenario_store`, `hani2.make_scenarios` | Loading and generating scenarios. |
| `hani2.study` | The study flow: round planning, practice rounds, questionnaires, Prolific completion. |
| `hani2.results`, `hani2.events` | Results files and the SQLite event log. |
| `hani2.auth` | User store, password hashing, roles, consent. |
| `hani2.config` | File locations and settings loading. |
| `hani2.llm_service`, `hani2.llm_logging`, `hani2.ollama_fallback` | The message helpers, LLM call logs and the local Ollama fallback. |
| `hani2.testing` | `make_session` for browserless tests. |

## Process model

The server runs as **one uvicorn worker process**. `hani2` always passes `workers=1`, because every live session is an in-memory Python object: the negmas mechanism, the opponent, the tools and the Assistant conversation are not serialisable. Do not run several workers or several replicas behind a load balancer without sticky routing to a single process.

Sessions are kept in the `Hub`, keyed by a session ID that the server derives from who is connecting:

| Session ID | Who | Key |
| --- | --- | --- |
| `main:<user>` | A logged-in user at `/app` (or an anonymous `user_<id>` in `auth.mode = none`). | The `hani2_auth` login cookie. |
| `guest:<id>` | A playground visitor at `/play`. | The `hani2_guest` cookie. |
| `prolific:<pid>` | A Prolific participant at `/play?PROLIFIC_PID=<pid>`. | The PID (letters, digits, `-` and `_`, up to 64 characters). |

`POST /api/session` creates the session on first contact (and loads the first scenario) or returns the existing one, so reloading the page or opening a second tab joins the same session. Passing `"fresh": true` discards the existing session first. All tabs of a session receive the same updates.

A background task removes sessions that have had no open WebSocket for six hours, unless a negotiation is running. Restarting the server drops all sessions; results already written to disk are kept.

## Threading

HANI2 keeps the event loop free by running all session work in threads.

- **Session lock.** `NegotiationSession.lock` is a re-entrant lock that guards session state. It is held only briefly. `run_on_doc(fn)` runs a callable under it; Assistants and tools use it to read or change state safely.
- **Step lock.** `step_lock` serialises stepping the mechanism. Opponent steps, which may wait for a slow LLM, run in a worker thread without holding the session lock, so the UI, the tools and the assistant stay responsive while the opponent thinks.
- **Worker pool.** A process-wide thread pool (`HANI2_WORKERS` threads, default 32) runs mechanism steps, Assistant events and any work submitted with `session.submit(fn, ...)`.
- **Per-session UI queue.** Each session has a single-thread executor that applies UI messages from the browser in arrival order (`submit_ui`). Messages that may block on an LLM or on the human (`chat`, `answer`, `panel_action`, `extract`, `generate`) go to the worker pool instead, so they never hold up the queue.
- **Delivery.** Sessions call `Hub.push`, `Hub.push_state` and `Hub.tool_changed` from any thread. The hub hands the work to the event loop. State pushes are coalesced (about 20 ms) and tool re-renders are coalesced per tool (about 50 ms), so a burst of changes produces one message.
- **Timeouts.** A timer thread watches the negotiation deadline. When time runs out on the human's turn, it repeats the human's last offer so the mechanism can register the timeout.

## WebSocket protocol

The browser opens `ws(s)://<host>/api/ws/<sid>` after `POST /api/session` returned the `sid`. The server checks the login cookie for `main:` sessions (unless `auth.mode` is `none`) and the guest cookie for `guest:` sessions, and closes the socket with code `4401` on a mismatch or `4404` for an unknown session.

All messages are JSON objects with a `type`. On connect the server sends a full `state` message and a `tool` message for every tool.

### Client to server

| `type` | Fields | Effect |
| --- | --- | --- |
| `ping` | | Server answers `{"type": "pong"}`. |
| `load` | `scenario_type?`, `name?` | Load the next scenario. The type and name are honoured only when the user may choose scenarios (admins, or `allow_scenario_selection`). |
| `start` | | Start the negotiation on the loaded scenario. |
| `draft` | `values` | Update the counter-offer fields (issue → value). |
| `draft_text` | `text` | Update the message to the opponent. |
| `send` | `values?`, `text?`, `text_only?` | Send the counter-offer. `text_only` is honoured for admins only. |
| `accept` | | Accept the opponent's current offer. |
| `end` | | End the negotiation without agreement. |
| `tool_input` | `id`, `name`, `value` | A tool input changed (calls `Tool.on_input`). |
| `tool_action` | `id`, `action`, `payload?` | A tool button or row was clicked (calls `Tool.on_action`). |
| `tool_layout` | `op`, `name`, `position?`, `pane?`, `enabled?` | `op` is `move`, `hide`, `show`, `enable`, `focus` or `restore`. `move` is ignored when `allow_moving_tools` is off. |
| `active_tab` | `pane`, `name` | The user switched tabs in a pane. |
| `pref` | `key`, `value` | Change a user preference, or an admin setting (admins only). |
| `layout` | `view?`, `sizes?`, `collapsed?` | Change the layout. |
| `chat` | `text` | A message to the assistant. |
| `answer` | `text` | The answer to a question the assistant asked. |
| `support` | `op`, `key?`, `value?` | Assistant settings: `op` is `enable`, `capability`, `autonomy`, `delivery` or `reset`. |
| `panel_action` | `panel_id`, `action`, `payload?` | A button in an assistant panel (calls `Assistant.on_panel_action`). |
| `close_panel` | `panel_id` | Close an assistant panel. |
| `clear_highlight` | `target?` | Remove one highlight, or all when `target` is missing. |
| `autopilot` | `active`, `driver?` | Turn autopilot on or off. |
| `questionnaire` | `answers` | Submit the post-negotiation questionnaire. |
| `opponent` | `spec` | Choose the next opponent (admin view only). |
| `extract` | | Fill the offer from the message with the LLM (admins only). |
| `generate` | | Write a message for the offer with the LLM (admins only). |
| `event` | `name?`, `component?`, `action?`, `value?` | Write an entry to the event log (default name `button_clicked`). The bundled frontend does not send it; it is there for custom clients. |

Unknown types are ignored.

### Server to client

| `type` | Fields | Meaning |
| --- | --- | --- |
| `state` | `state` | The full session snapshot (see below). Sent on connect and after every state change. |
| `tool` | `id`, `view` | The rendered components of one tool, or `view: null` when the tool is switched off. |
| `history` | `items` | The full negotiation history. |
| `chat` | `message` | One new assistant chat message. |
| `draft` | `draft`, `utility`, `by_agent` | The counter-offer fields changed; `by_agent` is true when a tool or the assistant changed them. |
| `draft_text` | `text` | The message field was changed by a tool or the assistant. |
| `toast` | `message`, `level`, `duration`, `action` | Show a notification. |
| `confirm` | `kind`, `message` | Ask the human to confirm `accept` or `end` (sent when the assistant or a tool requests it). |
| `pong` | | Answer to `ping`. |

NaN and infinite numbers are replaced before sending, so every message is valid JSON.

The `state` snapshot has these keys: `sid`, `user`, `display_name`, `mode`, `is_admin`, `admin_mode`, `phase` (`idle`, `ready`, `starting`, `running`, `ended`, `questionnaire` or `finished`), `round`, `scenario`, `opponent`, `negotiation`, `partner_offer`, `reserved_value`, `draft`, `result`, `history`, `tools`, `active_tabs`, `prefs`, `settings`, `highlights`, `annotations`, `layout`, `agent_panels`, `board`, `chat`, `pending_question`, `support`, `autopilot`, `notice`, `questionnaire`, `finish_url`, `study`, `can_choose_scenario` and `next_opponent`. Non-admins receive only a few of the admin settings in `settings`.

## REST API

All endpoints are under `/api`. Admin endpoints require an admin login cookie. They return `401` when nobody is logged in and `403` for users who are not admins.

### Public and session

| Method and path | Purpose |
| --- | --- |
| `GET /api/config` | Title, subtitle, version, effective auth mode, OAuth providers, registration and consent flags, whether the playground is on, the active experiment and `docs_url`. |
| `GET /api/announcements` | The content of `announcements.md`. |
| `GET /api/consent` | The content of `consent.md`. |
| `POST /api/consent` | Record consent for the logged-in user (`agree`, `full_name`). |
| `POST /api/session` | Create or join a session. Body: `mode` (`main` or `guest`), `query` (the page's URL parameters), `fresh`. Returns `{"sid": ...}`. |
| `WS /api/ws/{sid}` | The live channel described above. |

### Authentication

| Method and path | Purpose |
| --- | --- |
| `GET /api/auth/me` | The current user, display name, email, admin flag and consent state. |
| `POST /api/auth/login` | Log in with `username` and `password`. |
| `POST /api/auth/logout` | Log out. |
| `POST /api/auth/register` | Register (`username`, `password`, `confirm`, `email`, `confirm_email`, `full_name`, `consent`). |
| `POST /api/auth/password` | Change the logged-in user's password (`old`, `new`). |
| `GET /api/oauth/{provider}/login` | Start an OAuth login (`github` or `google`). |
| `GET /api/oauth/{provider}/callback` | The OAuth callback. |

### Admin

| Method and path | Purpose |
| --- | --- |
| `GET`, `PUT /api/admin/settings/{kind}` | Read or save a settings file. `kind` is `env`, `llm`, `support_agent`, `autopilot` (JSON) or `consent`, `announcements`, `scenario_order`, `scenario_sets` (text, as `{"text": ...}`). Saving always writes to the settings folder. |
| `GET /api/admin/meta` | Opponent groups, scenario types and names, tools, capability labels and autopilot drivers, for the console's forms. |
| `GET /api/admin/results` | All results rows, the column lists and the leaderboard. |
| `GET /api/admin/results.csv` | All results as one CSV file. |
| `GET /api/admin/events` | Query the event log (`user`, `session_id`, `types`, `since`, `until`, `limit`, `offset`). |
| `GET /api/admin/events/summary` | Event counts and recent sessions. |
| `GET /api/admin/events.csv` | The full event log as CSV. |
| `GET`, `POST /api/admin/users` | List users, or create one (`username`, `password`, `email`, `full_name`, `is_admin`). |
| `PATCH /api/admin/users/{username}` | Set `password` or `is_admin`. |
| `DELETE /api/admin/users/{username}` | Delete a user (not `admin`, not yourself). |
| `GET /api/admin/sessions` | Live sessions: user, mode, phase, round, connections, idle seconds, opponent, scenario. |
| `GET /api/admin/llm/status` | Whether the message-helper LLM is configured. |

FastAPI's interactive documentation is available at `/docs` while the server runs.

Every other path returns the single-page app (`index.html`), which routes `/app`, `/play`, `/admin`, `/login` and the other pages in the browser. Built assets are served from `/assets`.

## Frontend

The frontend lives in `frontend/` and uses React 19, TypeScript, Vite, Tailwind CSS, zustand for state, react-markdown and Plotly.

| Path | Content |
| --- | --- |
| `src/store.ts` | The WebSocket client and the session store; applies the server messages. |
| `src/negotiate/` | The negotiation page: header, action dock, history thread, tool panes, assistant dock, settings drawer. |
| `src/pages/` | The login, registration and consent pages, and the admin console. |
| `src/ui/` | Shared pieces: the component renderer for tool views, gauges, plots, markdown, modals, toasts and highlight anchors. |

`npm run build` type-checks and writes the bundle to `src/hani2/web`, which the wheel includes. The server serves whatever is in that folder, so a rebuilt frontend needs no Python change. During development, `npm run dev` serves the app on port 5173 and proxies `/api` (including WebSockets) to the backend on port 5006.

Tools and Assistant panels never ship frontend code. They describe their views with the components in `hani2.tools.ui`, which the generic renderer in `src/ui/Renderer.tsx` displays. See [Build a tool](../tutorials/tools.md).

## Extension points

| What | How |
| --- | --- |
| Tools | Subclass `hani2.tools.base.Tool`; register by saving the file in `$HANI2_HOME/tools` (or a `--tools` folder), with `register_tool`, through `env.json` → `tools.extra` or a `hani2.tools` entry point. See [Tools](../guide/tools.md). |
| Assistants | Subclass `hani2.assistant.runtime.Assistant`; set `agent_class` in `assistant_settings.json`. See [Assistant](../guide/assistant.md). |
| Opponents | Any negmas negotiator class, by dotted path or `file:` spec. See [Opponents](../guide/opponents.md). |
| Scenarios | Folders on disk. See [Scenarios](../guide/scenarios.md). |
