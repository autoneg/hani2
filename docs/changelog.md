# Changelog

## Unreleased

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
