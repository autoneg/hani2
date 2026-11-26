# HANI2

HANI2 is a web interface for human–agent negotiation studies. People negotiate in the browser against automated agents built with [negmas](https://github.com/yasserfarouk/negmas), optionally helped by an AI Assistant, while HANI2 records every offer, message, click and questionnaire answer. It is used to run the human–agent negotiation and hybrid intelligence tracks of the [ANAC competition](https://anac.cs.brown.edu).

HANI2 is a Python package with a FastAPI backend and a React frontend that ships pre-built inside the wheel. One command starts everything on one port.

![The negotiation desk](assets/screens/app-overview.png)

## Features

The full list, with how to turn each one on, is on the [Features](features.md) page.

- **Negotiation desk.** The opponent's offer on the table with its value to you. Accept it, send a counter-offer with an optional message, or end the negotiation; accepting and ending ask for confirmation. Gauges show what each offer is worth, with a tick at your no-deal value, and the history reads like a conversation.
- **A layout you control.** Full, simple, focus and bare (no tools) views; drag the dividers to resize panes; enlarge any tool into a window or the full screen and put it back; layouts for tablets and phones.
- **Tools.** Fourteen built-in tools, from your preferences (for any kind of utility function) to a negotiation plot with the Pareto frontier. Write your own in Python with a small component API; no frontend code needed.
- **Assistant.** An AI helper beside the negotiation. It chats, keeps a status board, highlights and annotates the interface, rearranges and resizes the layout, shows its own panels, fills in offers and, with permission, acts. It finds the participant's tools, reads and uses them, and adds new tools while they negotiate. Sixteen capabilities that admins grant and participants can narrow.
- **Competitions.** Run the Human-Agent Negotiation competition without an assistant (`--no-assistant`) and the Hybrid Intelligence competition with the built-in assistant or a team's (`--assistant team.py:TeamAgent`), with the team's tools (`--tools`), against the opponent agents you choose (`--opponents`).
- **Any opponent.** Any negmas or Genius negotiator, LLM negotiators from negmas-llm, your own classes, and named groups of them, chosen per server, per experiment or per link.
- **Studies and Prolific.** Self-contained experiments, questionnaires, results CSV files, an event log with analytics, and a Prolific flow with practice rounds and completion links.
- **Admin console.** Live sessions, results, analytics, users and every setting in the browser.
- **Autopilot and WebMCP.** Let the Assistant or any negotiator play the human's seat, and let browser AI agents use the page.
- **Any language model.** Local models through Ollama or any provider supported by litellm.
- **Easy to install.** `pip install hani2` on Python 3.11 to 3.15, on Linux, macOS and Windows.

## Quick start

```bash
pip install hani2
hani2 setup
hani2
```

Your browser opens `http://localhost:5006/app`. Log in as `user` / `userpass`, or as `admin` / `adminpass` for the admin tools. The same port serves:

| URL | What |
| --- | --- |
| `/app` | The negotiation interface for logged-in users. |
| `/play` | The playground: no login. Prolific participants use `/play?PROLIFIC_PID=...`. |
| `/admin` | The admin console. |

The assistant and LLM opponents need a language model. The defaults expect [Ollama](https://ollama.com) with `qwen3:4b-instruct`:

```bash
ollama pull qwen3:4b-instruct
```

![The admin console](assets/screens/admin.png)

## Where to go next

- [Features](features.md) lists everything HANI2 does.
- [Installation](getting-started/installation.md) and the [quick start](getting-started/quickstart.md) walk through a first negotiation.
- [The interface](guide/interface.md) describes what participants see.
- [Studies and results](guide/studies.md) and [Prolific](guide/prolific.md) explain how to run an experiment.
- [Build an Assistant](tutorials/assistant.md) and [Build a tool](tutorials/tools.md) are hands-on tutorials.
- [Configuration reference](guide/configuration.md) lists every setting and environment variable.

HANI2 is free software under the AGPL-3.0-or-later license. The source is at [github.com/autoneg/hani2](https://github.com/autoneg/hani2).
