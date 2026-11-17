# Changelog

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
