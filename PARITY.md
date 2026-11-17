# Feature parity checklist (internal)

Inventory of the Panel-based predecessor (0.4.0) and where each feature lives in hani2.
`[x]` implemented, `[~]` implemented differently, `[-]` intentionally dropped (reason given).
This file is a development note; it is not part of the user documentation or the sdist.

## Page flow
- [x] Password login / logout / registration (reserved names, password + email confirmation, duplicates) — `server.py`, `pages/AuthPages.tsx`
- [x] OAuth GitHub / Google, dual mode, auto mode — `server.py` (`/api/oauth/{provider}/…`)
- [x] Consent page (`consent.md`, checkbox + full-name signature) when `auth.enforce_consent`
- [x] Welcome text before the first negotiation (`announcements.md`) and Prolific intro
- [x] Load → Start → Negotiate → End → (questionnaire) → next negotiation
- [x] Guest playground `/play` (also `/hanplay`, `/guest`), Prolific mode `?PROLIFIC_PID=`
- [x] Query params `?agents=`, `?group=`, `?admin=1` (UI admin mode only), `?PROLIFIC_PID=`, `?noautostart`, `?view=`
- [~] "Load reloads the page" → explicit server-side `load()`; sessions survive reloads/reconnects
- [-] Registration "filled pre-questionnaire" checkbox and the profile-update stub (unused)
- [-] DB "experiment selector" (never wired in); directory experiments cover studies

## Negotiation
- [x] Agent specs: `file:`, `LLM*`, `*WithTextNegotiator`, bare negmas names, `helpers.`, `genius.`, dotted paths
- [x] Groups `:llm :template :negmas :hani :genius :pan :notext :custom`, group files `<results>/groups/<key>.json`, syspath priming
- [x] Pool precedence: query → `--agents`/`HANI2_AGENTS` → admin session setting → env.json `agents` → template pool
- [x] Mechanism params (n_steps, time_limit, pend, pend_per_second, step/negotiator limits, ignore_negotiator_exceptions)
- [x] `allow_none_with_data` (text-only offers), `end_on_no_response`
- [x] LLM model/provider injection, no-accept-None wrapper, no-end wrapper in practice rounds, verbose flag
- [x] Human seat placeholder; partner steps in a worker thread; "partner is thinking" indicator
- [x] Countdown (red ≤10 s); timeout → reject with the last offer
- [x] History: text, offer (scenario display), utility gauge (red below reserved), relative time, newest-first, hide history, hide own offers
- [x] Action panel: offer on the table + utility, Accept (util) / Counter-offer / End (reserved), confirmation dialogs with below-reserved warning
- [x] Counter-offer editor: message, per-issue inputs (buttons / select / number), `n_issue_columns`, live utility, keep-open option
- [x] Init draft with last offer / best outcome
- [x] Text-only mode (admin), offer-from-message / write-message (admin, LLM), auto-generate, auto-extract
- [x] Results: results.csv (all fields incl. advantage, optimality, timing, view), logs/, scenarios/, mechanisms/, last_scenario.txt
- [x] Status success / broken / timedout / erred / agent_failed, ended_by, n_human_actions, per_round_times
- [-] "Undo" of a counter-offer edit (the editor keeps the draft; not needed)

## Layout
- [x] Header: title, role, round badge (practice / negotiation N), admin badge, partner pill, layout switch, autopilot + driver, assistant
- [x] Three tool panes (upper / lower / side) with move / hide / restore; simple view; new focus view; mobile layout
- [x] Timer, round counter, progress
- [x] Toasts; status board
- [x] Settings: display prefs (all) + per-session admin settings (timing, rules, text, offer init, scenarios, partners, tools)
- [x] Admin console: sessions, results, analytics, users, server, LLM, support agent, autopilot, texts
- [~] Font size → text-size slider; colour scheme → light/dark/system theme
- [-] Per-side foreground/background colour pickers and the "Panel" outcome display method
- [-] Random header images

## Tools
- [x] Tool base API: same lifecycle hooks, `permanent`, enable switch, `OutcomeSelector`; new: declarative `view()`, `on_input`, `on_action`, `draft_changed`
- [x] Registry: name / timing / pane / admin_only / guest / enabled / order; `tools.extra`, `tools.disabled`, `tools.overrides`, `hani2.tools` entry points
- [x] New: tool `help` texts behind a ? button (all built-ins), tools folder `$HANI2_HOME/tools` + `--tools`/`HANI2_TOOLS`/`tools.paths` (hot reload), `register_tool`, `hani2 tools list|path|new`, `LLMTool` + `Tool.ask_llm`/`transcript`, `llm_service.complete`
- [x] Preferences, Scenario Info, Utility Plot, Outcome Plot, Trace, Value Histogram, My Results (was "User Results"), Utility-based Selector (cached inverter), LLM (Response Generator), Random, All Results, Opponent Preferences
- [-] Session Results (was disabled)

## Support agent & autopilot
- [x] `SupportAgent` API (post, toast, message_user, ask_user, show_on_board, run_on_doc, _post_async, handle_user_message, on_event, proactive_note, build_system_prompt, _complete, _context_snapshot, _run_turn, _execute_tool_call, dispatcher_class, make_dispatcher)
- [x] New: highlight, clear_highlights, annotate, set_layout, focus_tool, show_panel / close_panel, on_panel_action, on_draft_changed, context()
- [x] ToolDispatcher + make_function_schema; all built-in LLM functions + focus_tool, highlight, clear_highlights, annotate, set_layout, show_panel, close_panel, describe_tools, read_tool, use_tool (`use_tools` capability)
- [x] Capabilities (14) admin ∩ user; autonomy suggest / semi / full; highlight / confirm dialogs
- [x] Assistant dock: on/off, abilities, autonomy, proactive delivery (toast / board / chat), clear conversation
- [x] Draft-below-reserved warning (toast with "discuss" action, note on the editor, board)
- [x] mode on / off / auto, `HANI2_SUPPORT_AGENT` / `--support-agent`, custom `agent_class` with fallback
- [x] Autopilot: support-agent driver (forced tool calls, stall net, auto-disengage), negotiator drivers, step delay, admin gate, driver choice
- [x] Attribution logging (event type `support_agent`, value.actor)

## Settings, CLI, env
- [x] env.json, users.json (+ users_meta.json, hashed passwords), llm/support_agent/autopilot settings, consent.md, scenario_order.txt, announcements.md, questionnaires/
- [~] CLI: one `hani2` command serves app + playground + admin on one port; `setup`, `info`, `generate`, `experiment create/list`, `users list/add/passwd/remove`
- [~] Env vars renamed to `HANI2_*` (old `HANI_*` names still read for LLM log, Ollama fallback, custom agents, code base, scenario base)

## Scenarios
- [x] Pools `<base>/<Type>/NNNN<Type>/` (+ cached inverters), named scenario folders, single-scenario categories, on-the-fly generation
- [x] Scenario order / random / Prolific PID hash; per-user index
- [x] OutcomeDisplay per scenario (built-in + display.py)
- [x] `hani2 generate` with opposition filtering

## Experiments & Prolific
- [x] Experiment folders (consent, order, announcements, scenarios, questionnaires, results)
- [x] Prolific: session meta, practice, counted rounds, schedule.json, rotation over finalists, zero-action rule, returning participants
- [x] Auto-start / auto-load with warning; `?noautostart`
- [x] Per-negotiation questionnaire (likert5/7, yes_no, select, text) → negotiation_questionnaires.csv; cannot be skipped
- [x] Completion link (`PROLIFIC_COMPLETION_URL` or `SCMLWEB_BASE_URL`), also after reload
- [-] Hard-coded finalist fallback list (use `PROLIFIC_FINALISTS` or the pool)

## Events & analytics
- [x] SQLite event log (same event types + support_agent), sessions table; logged: login/logout, page views, tab changes, tool open/close/interactions, dialogs, offers/accept/end, scenario load/start, support-agent actions
- [~] Per-button click events: actions are logged by meaning (counter-offer, accept, end…) rather than as raw clicks
- [x] Analytics in the admin console (by type, timeline, filters, sessions, CSV export)
- [-] Separate analytics app and event-DB experiment CLI (both were broken entry points)

## Other
- [x] Per-negotiation LLM logging, Ollama local fallback
- [x] Message helpers / LLM tool accept any litellm provider (was ollama/openai/anthropic only)
- [x] Docs (self-contained), tutorials (support agent levels 0–9, tools), examples, offline test helpers
