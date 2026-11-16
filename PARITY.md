# HANI → HANI2 feature parity checklist

Derived from an inventory of `hani/src/hani/app.py` and friends (HANI 0.4.0).
`[x]` = implemented in hani2, `[ ]` = pending, `[-]` = intentionally dropped (reason given).

## Page flow
- [ ] Login (password), logout, registration page (rejects username "AI", password confirm, duplicates)
- [ ] OAuth (GitHub / Google), dual mode (password + OAuth), auto mode
- [ ] Consent page (`consent.md`, checkbox + full-name signature) when `auth.enforce_consent`
- [ ] Announcements / intro text before first negotiation (`announcements.md`)
- [ ] Load → Start → Negotiate → End → (questionnaire) → Load next
- [ ] Guest playground (no login), Prolific mode (`?PROLIFIC_PID=`)
- [ ] Query params: `?agents=`, `?group=`, `?admin=1`, `?PROLIFIC_PID=`, `?noautostart`, `?view=simple|full`

## Negotiation
- [ ] Agent spec resolution: `file:`, `LLM*`, `*WithTextNegotiator`, bare negmas names, `helpers.`, `genius.`, dotted paths
- [ ] Groups `:llm :template :negmas :hani :genius :pan :notext :custom`, group files `<results>/groups/<key>.json`
- [ ] Pool precedence: query → CLI/env → admin selection; fallback template pool
- [ ] Mechanism params: n_steps, time_limit, pend, pend_per_second, step/negotiator time limits, ignore_negotiator_exceptions
- [ ] allow_none_with_data (text-only offers), end_on_no_response toggle
- [ ] LLM model/provider injection for LLM opponents; no-accept-None wrapper; no-end wrapper in practice rounds
- [ ] Human seat placeholder; partner steps off the event loop; "Partner is thinking…" indicator
- [ ] Countdown timer (red ≤10 s, timeout → reject with last offer)
- [ ] History bubbles: text, offer (scenario OutcomeDisplay), utility % (red if below reserved), relative time, newest-first option
- [ ] Action panel: offer on the table (util), Reject / Accept (util) / End (reserved), confirmations with warnings
- [ ] Counter-offer: message box, per-issue widgets (int input / select / float), n_issue_columns, live utility, Undo
- [ ] Init draft with best offer / last offer
- [ ] Text-only mode (admin), Extract Outcome / Generate Text (admin, LLM)
- [ ] Save results: results.csv row (all HANI fields incl. advantage, optimality), logs/<id>.csv trace, scenarios/<id>/, mechanisms/<id>.json, last_scenario.txt
- [ ] Status success/broken/timedout/erred/agent_failed, ended_by, n_human_actions, per_round_times

## Layout
- [ ] Header: title, phase badge (Practice / Negotiation N), ADMIN badge, opponent pill, view switch, autopilot switch + driver select
- [ ] Three tool panes (upper / lower / side) + move/close buttons (when allowed); simple view
- [ ] Summary: step n of N, timer, progress bar
- [ ] Toasts; bottom status board
- [ ] Settings drawer: Display toggles, Display control (fonts/colors/offer display), Tool settings, Negotiation rules, Offer init, Text & Offers, Timing, Scenario, Partner, LLM settings, Support agent, Autopilot

## Tools
- [ ] Tool base API: hooks (init, scenario_loaded, negotiation_started/ended, action_requested, action_to_execute, action_executed), permanent, enabled switch, OutcomeSelector
- [ ] Registry with name / timing / pane / admin_only / enabled default; pluggable custom tools
- [ ] Preferences, Scenario Info, Utility Plot, Outcome Plot, Trace, Value Histogram, User Results,
      Utility-based Selector, LLM (Response Generator), Random, All Results, Agent Preferences

## Support agent & autopilot
- [ ] SupportAgent API parity (post, toast, message_user, ask_user, show_on_board, run_on_doc, _post_async, handle_user_message, on_event, proactive_note, build_system_prompt, _complete, _context_snapshot, _run_turn, _execute_tool_call, dispatcher_class, make_dispatcher)
- [ ] ToolDispatcher + make_function_schema, all built-in LLM tools, capability gating
- [ ] CapabilityState (admin ∩ user), autonomy suggest/semi/full, highlight / confirm dialogs
- [ ] Floating chat bubble: on/off, capability switches, autonomy select, proactive delivery toast/board
- [ ] Draft-below-reserved warning; mode on/off/auto, `HANI_SUPPORT_AGENT`, custom `agent_class`, fallback on load failure
- [ ] Autopilot: Support-Agent driver (forced tool calls, stall net, auto-disengage) and negotiator drivers, step delay, admin gate
- [ ] Attribution logging (component=SupportAgent, actor=agent)

## Settings, CLI, env
- [ ] env.json, users.json (+ meta), llm_settings.json, support_agent_settings.json, autopilot_settings.json, consent.md, scenario_order.txt, announcements.md
- [ ] CLI: run (main+guest), setup, generate scenarios, experiment create, auth info, analysis
- [ ] Env vars: experiment, support agent mode, custom agents, LLM log, Ollama local fallback, Prolific vars, SCMLWEB_BASE_URL

## Scenarios
- [ ] Load from `<base>/<Type>/NNNN<Type>/` pools (+ cached inverters), generate Trade/Island/Grocery on the fly
- [ ] Scenario order file / random / Prolific PID-hash type; per-user scenario index
- [ ] Scenario-specific OutcomeDisplay (Trade/Island/Grocery + display.py)
- [ ] `generate` command with opposition filtering

## Experiments & Prolific
- [ ] Experiment folders (consent, order, scenarios, questionnaires, results)
- [ ] Prolific session meta, practice round, counted rounds, schedule.json, finalist rotation, zero-action rule
- [ ] Auto-start / auto-load timers with warning; noautostart
- [ ] Per-negotiation questionnaire (likert5/7, yes_no, select, text) → negotiation_questionnaires.csv
- [ ] Completion panel link

## Events & analytics
- [ ] Event log (SQLite) with the HANI event types; sessions; button/tool tracking
- [ ] Analytics dashboard (filters, overview, events, sessions, CSV export)

## Other
- [ ] LLM call logging per negotiation (`HANI_LLM_LOG`), Ollama local fallback
- [ ] Docs: install, quickstart, tutorial, support agent, tools (new API), LLMs/Ollama, scenarios, agents, experiments, Prolific, auth
