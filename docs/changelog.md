# Changelog

## 0.1.0

First release.

- **Server and web app.** A FastAPI server and a React single-page app shipped pre-built in the wheel. One port serves the logged-in app (`/app`), the no-login playground (`/play`), the admin console (`/admin`) and the API. Negotiations update live over a WebSocket.
- **Negotiation desk.** The partner's offer on the table, a counter-offer editor with per-issue fields, utility gauges with a no-deal marker, a history thread with messages, confirmation dialogs for accepting and ending, three layouts (full, simple, focus) and a mobile layout.
- **Tools.** Twelve built-in tools (preferences, scenario info, utility and outcome plots, value histograms, trace, utility-based offer selector, random offers, results, the opponent's preferences for admins, and an LLM offer writer for admins), arranged in upper, lower and side panes. Tools are Python classes with a declarative component API (`hani2.tools.ui`) and can be added through `env.json` or a `hani2.tools` entry point.
- **Support agent.** An LLM assistant that chats, keeps a status board, fills and sends offers, accepts or ends with confirmation, controls tools, highlights and annotates the interface, changes the layout and shows its own interactive panels. Sixteen capabilities and three autonomy levels, granted by the admin and narrowed by each participant. Subclass `SupportAgent` to write your own.
- **Autopilot.** The support agent or any negotiator can play the human's seat.
- **Opponents.** Any negmas, Genius or negmas-llm negotiator, group tokens, group files and per-link pools.
- **Scenarios.** On-disk scenario categories and pools, the built-in Trade, Island and Grocery generators and `hani2 generate`.
- **Studies.** Experiments with their own settings and results, per-negotiation questionnaires, results CSV files, an SQLite event log with analytics, and a Prolific flow with practice rounds and completion links.
- **Authentication.** Password, GitHub and Google OAuth, both, or none; consent enforcement; PBKDF2 password hashes; `hani2 users`.
- **Language models.** Any litellm provider for the assistant and LLM opponents, local models through Ollama, editable prompt templates and per-negotiation LLM call logs.
- **Layout control.** Drag the dividers between panes to resize them (kept in the session and settable by the support agent); enlarge any tool into a large window or the full screen and put it back where it came from; your own preferences come into view when a negotiation starts.
- **Competitions.** `hani2 --no-support-agent` for the Human-Agent Negotiation competition, `hani2 --support-agent <class or file.py:Class>` to give every participant a submitted assistant for the Hybrid Intelligence competition, and the same choices for `hani2 experiment create`. Opponent agents are chosen with `--opponents` (`HANI2_OPPONENTS`, `?opponents=`, `opponents` in `env.json`), clearly separate from the support agent; the old `agents` names still work.
- **Agents and tools.** The support agent finds the participant's tools, reads them as text and operates their inputs and buttons (within its own permissions), and adds tools while the session runs: its own (`SupportAgent.tools`), a `toolbox` setting, or tools with `timing = "agent"`. `hani2 --tools` loads submitted tool files. Tutorial level 10 shows an agent that brings and uses tools.
- **Testing.** `hani2.testing.make_session` runs a full session without a browser for testing tools and agents.
