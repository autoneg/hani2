# HANI2

HANI2 is a web interface for human–agent negotiation studies. People negotiate in the browser against automated agents built with [negmas](https://github.com/yasserfarouk/negmas), optionally helped by an AI support agent, while HANI2 records every offer, message, click and questionnaire answer. It runs the human–agent negotiation and hybrid intelligence tracks of the [ANAC competition](https://anac.cs.brown.edu).

HANI2 is a Python package: a FastAPI backend plus a React frontend that ships pre-built inside the wheel.

**Documentation:** <https://autoneg.github.io/hani2/>

## Install and run

Requires Python 3.11 or newer (tested up to 3.15).

```bash
pip install hani2
hani2 setup      # creates ~/negmas/hani2/settings with defaults, users and sample scenarios
hani2            # http://localhost:5006
```

One port (default 5006) serves:

| URL | What |
| --- | --- |
| `/app` | The negotiation interface for logged-in users (`user` / `userpass`, `admin` / `adminpass`). |
| `/play` | The no-login playground. Prolific participants arrive at `/play?PROLIFIC_PID=...`. |
| `/admin` | The admin console. |
| `/api` | The REST and WebSocket API. |

The support agent and LLM opponents need a language model. The defaults use a local [Ollama](https://ollama.com) model:

```bash
ollama pull qwen3:4b-instruct
```

Any provider supported by litellm works too; see [Language models](https://autoneg.github.io/hani2/guide/llms/).

## Features

- **Negotiation desk**: the partner's offer on the table, a counter-offer editor, utility gauges with a no-deal marker, a conversation-style history, confirmation before accepting or ending, three layouts and a phone layout.
- **Tools**: preferences, plots, histograms, the offer trace, an offer picker and more, in panes participants can rearrange. Write new ones in Python.
- **Support agent**: an assistant that chats, highlights and annotates the interface, rearranges tools, shows interactive panels and, with permission, makes offers. It can also find, use and add tools. Sixteen capabilities and three autonomy levels.
- **Autopilot**: the support agent or any negotiator plays the human's seat.
- **WebMCP**: browser AI agents can read and (optionally) negotiate through the page's tools.
- **Opponents**: any negmas, Genius or negmas-llm negotiator, your own classes, and named groups.
- **Studies**: self-contained experiments, questionnaires, results CSV files and an event log with analytics.
- **Prolific**: practice rounds, counted rounds and completion links.
- **Admin console**: live sessions, results, analytics, users and all settings in the browser.
- **Accounts**: password, GitHub and Google OAuth, or no login; optional consent form.

## A custom support agent

```python
# my_agent.py
from hani2.support_agent.runtime import SupportAgent


class RulesAgent(SupportAgent):
    def handle_user_message(self, text: str) -> None:
        actions = self.session_state.get("actions")
        if not actions:
            self.post("Load a scenario and start a negotiation first.")
            return
        ctx = self.run_on_doc(actions["context"])
        if ctx["partner_offer"] is None:
            self.post("Your partner has not made an offer yet.")
        elif ctx["partner_offer_utility"] < ctx["reserved_value"]:
            self.post("That offer is worse than walking away.")
        else:
            self.post("That offer beats your reserved value.")
```

Point `agent_class` in `~/negmas/hani2/settings/support_agent_settings.json` at it and start the server from the folder that holds `my_agent.py`:

```json
{"agent_class": "my_agent:RulesAgent"}
```

```bash
PYTHONPATH=$PWD hani2 --page play
```

The [support agent tutorial](https://autoneg.github.io/hani2/tutorials/support-agent/) goes from this to LLM agents that highlight the interface and show their own panels.

## A custom tool

```python
# my_tools.py
from hani2.tools import Tool, ui


class OfferCounter(Tool):
    name = "Offer Counter"
    description = "How many offers each side made so far."
    icon = "hash"
    pane = "side"

    def view(self):
        trace = self.trace()
        me = self.session_state.get("human_id")
        mine = sum(1 for row in trace if row[3] == me)
        return [ui.stats(ui.stat("Your offers", mine), ui.stat("Partner offers", len(trace) - mine))]
```

Register it in `~/negmas/hani2/settings/env.json`:

```json
{"tools": {"extra": ["my_tools:OfferCounter"]}}
```

See the [tools tutorial](https://autoneg.github.io/hani2/tutorials/tools/).

## Development

```bash
git clone https://github.com/autoneg/hani2
cd hani2
uv venv
uv pip install -e '.[dev]'
pytest

# the web app (writes the bundle to src/hani2/web)
cd frontend
npm install
npm run build
```

For frontend work, run `hani2 --no-browser --dev` and `npm run dev` in `frontend/` (port 5173, proxied to the backend). To build the documentation, install `.[docs]` and run `mkdocs serve`.

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE).
