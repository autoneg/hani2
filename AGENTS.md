# Working on HANI2

## Layout
- `src/hani2/` — the Python package (FastAPI server, session engine, tools, support agent).
  - `session.py` — one `NegotiationSession` per browser session: scenario, mechanism, draft, history,
    tools, support agent, autopilot; `snapshot()` is what the browser renders.
  - `server.py` — REST + WebSocket (`_dispatch` maps client messages to session methods).
  - `hub.py` — thread-safe pushes to WebSockets (coalesced state / tool renders; NaN-safe JSON).
  - `tools/` — `Tool` base, declarative `ui` components, built-in tools, registry.
  - `support_agent/` — `SupportAgent` runtime, `ToolDispatcher` (LLM functions), capabilities, autopilot.
  - `study.py` — normal and Prolific study logic, questionnaires.
  - `web/` — the **built** frontend (generated; do not edit by hand).
- `frontend/` — React + TypeScript + Tailwind source. `npm run build` writes to `src/hani2/web`.
- `examples/` — tutorial agents (levels 1–10), agent template, example tools. Tests import them.
- `docs/` — MkDocs site. Must be self-contained: never refer to the predecessor project.
- `PARITY.md` — internal feature-parity checklist (not published).

## Commands
```bash
uv venv && uv pip install -e ".[dev,docs]"
.venv/bin/pytest -q                       # backend tests (headless sessions via hani2.testing)
cd frontend && npm install && npm run build   # rebuild the web app after frontend changes
.venv/bin/hani2 --dev                      # run with auto-reload
.venv/bin/mkdocs serve                     # docs
```

## Rules
- Rebuild the frontend and commit `src/hani2/web` whenever `frontend/src` changes (the wheel ships it).
- Never push without an explicit request.
- New support-agent abilities need: a `Capability`, a `CAPABILITY_INFO` entry, a default in
  `support_agent/settings.py` and `default_settings/support_agent_settings.json`, a dispatcher function,
  a `SupportAgent` helper, docs and a test.
