# Features

Everything HANI2 does, grouped by who uses it. Each entry says how to turn it on and where the
details are.

## For participants

### The negotiation desk

| Feature | What it does | Details |
| --- | --- | --- |
| Offer on the table | The opponent's current offer, what it is worth to you, and **Accept**, **Counter-offer** and **End** buttons. Accepting and ending ask for confirmation. | [The action dock](guide/interface.md#the-action-dock) |
| Counter-offer editor | One field per issue (buttons, lists or numbers), a gauge of the offer's value with a tick at your no-deal value, and an optional message. Large scenarios use three columns so the **Send** button stays in view. | [During the negotiation](guide/interface.md#during-the-negotiation) |
| History thread | Every offer and message as a conversation, oldest first, scrolling to the newest. | [The history thread](guide/interface.md#the-history-thread) |
| Your preferences in view | When a negotiation starts, your Preferences tool comes to the front (and the tools tray or tab opens on tablets and phones). | [Your preferences when the negotiation starts](guide/interface.md#your-preferences-when-the-negotiation-starts) |
| Clear names | With an assistant present, scenarios that call the sides `human` and `agent` show **You** and **Opponent** instead. | [`names`](guide/configuration.md#names) |
| Questionnaires and consent | Optional questions after each negotiation and a consent form before the first. | [Studies](guide/studies.md#per-negotiation-questionnaires) |

### Layout

| Feature | What it does | Details |
| --- | --- | --- |
| Three views | **Full** (tools left, offer generators beside the offer area), **simple** (one tools column) and **focus** (negotiation only). | [Layout views](guide/interface.md#layout-views) |
| Resizable panes | Drag the dividers between panes; double-click to reset. Sizes survive a reload. | [Resizing the panes](guide/interface.md#resizing-the-panes) |
| Enlarge a tool | Open any tool in a large window or full screen, and put it back where it came from. | [Enlarge and put back](guide/interface.md#enlarge-and-put-back) |
| Tablets and phones | Landscape and portrait tablet layouts with a tools tray, and a phone layout with Negotiate / Tools / Assistant tabs. | [Phones and tablets](guide/interface.md#phones-and-tablets) |
| Display settings | Light or dark theme, text size, history options, offers as sentences or chips. | [Display settings](guide/interface.md#display-settings) |

### Tools

| Feature | What it does | Details |
| --- | --- | --- |
| Thirteen built-in tools | Preferences, Scenario Info, My Results, Value Histogram, Utility Plot, Negotiation Plot, Outcome Plot, Trace, Utility-based Selector, LLM, Random, All Results and Opponent Preferences. | [Built-in tools](guide/tools.md#built-in-tools) |
| Negotiation Plot | The negotiation in utility space with the Pareto frontier, Nash and Kalai points and both offer trajectories (admins, or everyone if allowed). | [Built-in tools](guide/tools.md#built-in-tools) |
| Any kind of preferences | The Preferences and Opponent Preferences tools show linear, affine, additive, generalized linear, polynomial, nonlinear, hyper-rectangle, weighted, discounted, rank-only, constant and probabilistic utility functions, and anything else as a ranked list. | [Showing other preferences](guide/preferences.md) |
| Rearrange tools | Tabs, an enable switch, move between panes, hide and restore. | [Tool panes](guide/interface.md#tool-panes) |
| Smooth updates | Only visible tools are computed, in the background; charts draw when the browser is idle. | [How tools are rendered](guide/tools.md#how-tools-are-rendered) |

## The Assistant

| Feature | What it does | Details |
| --- | --- | --- |
| Assistant dock and status board | Chat with the assistant, answer its questions with buttons, and see its current advice on an always-visible board. | [The assistant dock](guide/interface.md#the-assistant-dock) |
| Sixteen capabilities | Chat, notifications, tool control (enable, show, rearrange), fill the offer and message, send, accept, end, highlight, annotate, change the layout, custom panels, **add tools** and **use tools**. Admins grant them; each participant can switch them off. | [Capabilities](guide/assistant.md#capabilities) |
| Three autonomy levels | Suggest, semi-autonomous or fully autonomous for sending, accepting and ending. | [Autonomy](guide/assistant.md#autonomy) |
| Interface control | Spotlight buttons, issues and tools with a short note, attach notes, switch views, resize panes and show interactive panels. | [Interface control](guide/assistant.md#interface-control) |
| Finds and uses tools | Reads any tool as text (numbers, tables, chart summaries, inputs and buttons) and operates it like the participant, within its own permissions. A tool written for people needs no extra code. | [Tools the agent can find, use and add](guide/assistant.md#tools-the-agent-can-find-use-and-add) |
| Adds tools while you negotiate | Puts its own tools, or registered ones, on the screen at the right moment; tools with `timing = "agent"` wait for it. | [Tools the agent can find, use and add](guide/assistant.md#tools-the-agent-can-find-use-and-add) |
| Your own agent | Subclass `Assistant` with or without a language model; ten tutorial levels from an echo bot to an agent that brings its own tools. | [Build an Assistant](tutorials/assistant.md) |
| Autopilot | The Assistant or any negotiator plays the human's seat. | [Autopilot](guide/autopilot.md) |

## For competitions

| Feature | How | Details |
| --- | --- | --- |
| Human-Agent Negotiation (no assistant) | `hani2 --no-assistant` | [With or without an Assistant](guide/assistant.md#with-or-without-an-assistant-competitions) |
| Hybrid Intelligence, built-in assistant | `hani2 --assistant on` | [With or without an Assistant](guide/assistant.md#with-or-without-an-assistant-competitions) |
| Hybrid Intelligence, a team's assistant | `hani2 --assistant team.py:TeamAgent` (or `package.module:Class`) | [Submitting tools and agents](guide/assistant.md#hybrid-intelligence-submitting-tools-and-agents) |
| A team's tools | `hani2 --tools team.py:TeamTool` | [Submitting tools and agents](guide/assistant.md#hybrid-intelligence-submitting-tools-and-agents) |
| Opponent agents | `hani2 --opponents BoulwareTBNegotiator,:template` (also `?opponents=` per link and `opponents` in `env.json`) | [Opponents](guide/opponents.md) |
| Saved competition setups | `hani2 experiment create NAME --no-assistant --opponents ... --tools ... --no-webmcp`, then `hani2 --experiment NAME` | [Command line](getting-started/cli.md#hani2-experiment-create) |

The **opponent agent** negotiates against the participant; the **Assistant** helps the
participant. Options, settings and admin screens use these two names throughout.

## For researchers and administrators

| Feature | What it does | Details |
| --- | --- | --- |
| Experiments | Self-contained folders with their own settings, scenarios, questionnaires and results. | [Studies and results](guide/studies.md) |
| Scenario sets | 19 scenario types grouped into sets (HAN2026, MIT2025, PieArena2026, ANL and one per ANL year, IAGO, HAN2027, HI2027, ANAC2027, or your own; sets can include other sets). Pick the set with `hani2 --scenario-set`, `env.json` or, as an admin, in the settings drawer or on the start screen. | [Scenario sets](guide/scenario-sets.md) |
| Who plays which role | Rules for the participant's role: the scenario's suggested role, a fixed index, preferred role names, alternating or random. | [Which side the participant plays](guide/scenarios.md#which-side-the-participant-plays) |
| Your own scenarios | Write a story or a generator in Python and register it from a file, or serve saved scenarios from any folder with `--scenarios`. | [Writing your own scenario type](guide/scenarios.md#writing-your-own-scenario-type) |
| Recording and replay | Every negotiation is recorded completely — screens, clicks, pointer, keys, offers, assistant messages and function calls, language-model calls with tokens and cost — and can be replayed exactly as the participant saw it, with a check that the replay matches their screen. On by default. | [Recording and replay](guide/recordings.md) |
| Evaluation metrics | Hard metrics (outcome, Pareto / Nash / Kalai distances, welfare, length, tokens and cost, move types, theory of mind, decision times, activity, use of the assistant, engagement flags), questionnaire scales (UEQ, TAM, opponent perception) and language-model judgements (assistant, opponent, human, assertions, error review), for any set of recordings; compare groups with scenario-balanced means and pass^k. `hani2 replay evaluate`, `hani2 replay compare` or the replay tool. | [Evaluation metrics](guide/evaluation.md) |
| Evaluation questionnaire | UEQ, TAM, intention to use, feeling heard, and how the opponent came across, after every negotiation: `HANI2_PER_NEG_YAML=evaluation`. | [Subjective metrics](guide/evaluation.md#subjective-metrics) |
| Results and events | A results CSV per participant (including the layout used: `device` and `orientation`) and an SQLite event log of every action, with analytics in the admin console. | [Results](guide/studies.md#results) |
| Prolific | A no-login flow keyed by the Prolific ID, with practice and counted rounds and the completion link. | [Prolific](guide/prolific.md) |
| Admin console | Live sessions (with each one's opponent and Assistant), results, events, users and every setting, in the browser. | [Admin console](guide/admin.md) |
| Opening admin-only tools | Give any admin-only tool, or opponent utilities, to all participants. | [Opening admin-only tools](guide/tools.md#opening-admin-only-tools-to-participants) |
| Enlarged tools | Choose whether tools enlarge into a window, fill the screen, or not at all. | [Enlarge and put back](guide/interface.md#enlarge-and-put-back) |
| Accounts | Password, GitHub and Google login, or none; `hani2 users`. | [Authentication](guide/authentication.md) |
| Language models | Ollama or any litellm provider, for the assistant and for LLM opponents. | [Language models](guide/llms.md) |
| WebMCP | Browser AI agents can read and (if allowed) act on the negotiation through the page; off for Prolific by default. | [WebMCP](guide/webmcp.md) |

## For developers

| Feature | What it does | Details |
| --- | --- | --- |
| Tools in Python | Write a class with a `view()` built from components; no frontend code. Register in `env.json`, with `--tools`, or as a package entry point. | [Build a tool](tutorials/tools.md) |
| Tools agents can use | Give a tool an `agent_hint`, or override `describe_for_agent()`; `timing = "agent"` for tools only an agent adds. | [Make your tool usable by an Assistant](tutorials/tools.md#make-your-tool-usable-by-an-assistant) |
| Views for new kinds of preferences | Register a view for any utility-function class with a decorator or an entry point. | [Showing other preferences](guide/preferences.md) |
| Headless testing | `hani2.testing.make_session` runs a whole session without a browser. | [Testing agents offline](tutorials/assistant.md#testing-agents-offline) |
| Installation | `pip install hani2` on Python 3.11 to 3.15, on Linux, macOS and Windows. | [Installation](getting-started/installation.md) |
