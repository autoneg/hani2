# WebMCP: browser agents

The negotiation page supports [WebMCP](https://webmachinelearning.github.io/webmcp/), the
browser API that lets a web page offer *tools* to an AI agent running in the browser (an
assistant built into the browser or a browser extension). When the browser provides
`document.modelContext` (or the older `navigator.modelContext`), HANI2 registers its tools and
a green **WebMCP** badge appears next to the round label in the header.

A browser agent can then read the negotiation, use the analysis tools and, if you allow it,
negotiate on the participant's behalf, all through the same actions the participant has.

## The tools

All tool names start with `hani2_`.

| Tool | Changes the negotiation | What it does |
| --- | --- | --- |
| `hani2_get_negotiation_state` | no | The scenario and its issues, whose turn it is, the partner's offer and its utility, the draft, the value on disagreement, recent history, time left, the result and any open questionnaire. |
| `hani2_read_tool` | no | The help text of an analysis tool (what it does and how it works) and its current content (text, tables, statistics, chart data). Switched-off tools are switched on first. |
| `hani2_evaluate_offer` | fills the editor only | Puts an outcome in the offer editor (without sending it) and returns its utility. |
| `hani2_use_tool` | yes | Sets an input of an analysis tool and/or triggers one of its actions (for example picking a row in the Utility-based Selector). |
| `hani2_start_negotiation` | yes | Starts the loaded negotiation and waits for the partner's first move. |
| `hani2_send_counter_offer` | yes | Sends an outcome and an optional message, waits for the partner's reply and returns the new state. |
| `hani2_accept_offer` | yes | Accepts the offer on the table. |
| `hani2_end_negotiation` | yes | Ends without agreement. |
| `hani2_load_next_scenario` | yes | Loads the next scenario after a negotiation ended. |
| `hani2_ask_assistant` | no | Sends a message to the page's support agent and returns its reply (when the session has one). |
| `hani2_answer_questionnaire` | yes | Submits the post-negotiation questionnaire. |

Read-only tools carry the `readOnlyHint` annotation; accept, end and counter-offers carry
`consequentialHint`, so a browser can ask the user before running them.

## Configuration

`env.json`:

```json
{
  "webmcp": {"enabled": true, "actions": true, "studies": false}
}
```

| Key | Default | Meaning |
| --- | --- | --- |
| `enabled` | `true` | Register WebMCP tools at all. |
| `actions` | `true` | Also register the tools that change the negotiation. `false` leaves only the read-only tools. |
| `studies` | `false` | Register the tools for Prolific participants too. Off by default so that a participant's browser agent cannot play the study for them. |

## Telling agents and people apart

Every WebMCP tool call is logged in the event log as event type `webmcp`, with the tool name in
`component` and the arguments in `value` (see [Studies and results](studies.md)). Filter the
admin console's *Event analytics* by `webmcp` to see which sessions used a browser agent.

## Trying it

Browsers ship WebMCP behind origin trials and flags while the specification is a draft; check
your browser's documentation for how to enable it. Without browser support the page works
exactly the same and simply registers nothing.
