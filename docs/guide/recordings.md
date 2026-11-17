# Recording and replay

HANI2 records **everything** that happens in every negotiation, in a file you can replay
later exactly as the participant saw it, and evaluate with the
[evaluation metrics](evaluation.md). Recording is on by default.

## What is recorded

One recording per negotiation. It starts when a scenario is loaded and ends when the next one is
loaded or the session closes, so the questionnaire after a negotiation belongs to it.

| What | Details |
| --- | --- |
| The screen | Every state and tool view the server sent to the browser, in order, with a sequence number. Replaying them rebuilds what was on screen (see [the known limits](#known-limits-of-the-replay)). |
| The browser | Pointer moves and clicks (with the element clicked), keys, text typed in fields, scrolling, window focus, tab visibility, the viewport size, device and theme, which server message was on screen when, and the participant's local UI state (open drawers, menus, tabs, the assistant panel, enlarged tools, dialogs). |
| Every action | Every message the browser sent (button clicks, offer edits, chat, tool inputs, layout changes, questionnaire answers), and every action on the participant's seat with **who** took it: the human, the assistant or the autopilot. |
| The negotiation | The scenario with each party's utility for every outcome and the reserved values, the opponent, the settings, the full offer trace and the result. |
| The assistant | Every chat message, every offer it filled in, every function it called (arguments, result, time). |
| Language models | Every call by the assistant, the opponent or HANI2 itself: model, prompt (stored once — later calls store only new messages), response, tool calls, latency, tokens and cost. |
| Events | Everything also written to the event log (tool opened, tab changed, offer made, …). |

Recordings are stored per participant in `<results>/<user>/recordings/`:

- `<id>.hrec` — the recording: gzip-compressed JSON lines (a few hundred kB for a long negotiation);
- `<id>.json` — a short summary used for listing;
- `<id>.eval.json` — cached language-model judgements (see [evaluation](evaluation.md#language-model-judgements)).

While a negotiation runs the file is `<id>.hrec.jsonl` (plain, flushed after every line), so a
session that is abandoned or a server that crashes still leaves a readable recording.

!!! warning "Recordings contain everything"
    A recording holds both parties' preferences and everything participants typed. Only admins
    can list, open or download recordings in the app.

### Turning it off

```bash
HANI2_RECORD=0 hani2
```

or in `env.json`:

```json
{ "recording": { "enabled": false } }
```

## The replay tool

Open **Replay** from the admin console, go to `/replay`, or run:

```bash
hani2 replay open                       # every recording in the results folder
hani2 replay open path/to/folder file.hrec   # also show these
```

### Library

A table of recordings with search and filters (user, opponent, status, scenario). Select
recordings to **evaluate** them (pick metrics by kind, optionally with the language-model judge)
or **compare** them grouped by opponent, assistant, user, scenario or experiment. Every table can
be exported as CSV. You can also upload `.hrec` files from elsewhere.

### Player

Opens one recording. The negotiation is shown at the participant's own window size (scaled to
fit) with their pointer, clicks and key presses drawn on top.

- Play, pause, speed (0.5× to 8×), skip idle periods, jump to the previous or next action.
- A timeline with markers for human actions, partner offers, assistant messages and suggestions,
  language-model calls, clicks and the questionnaire.
- **Events**: everything in order, readable ("Human offered …", "Assistant: …", "LLM call
  (support, 1.2 s, 845 tokens)", "Clicked *Accept*"); click one to jump there.
- **Metrics**: the evaluation of this recording.
- **Fidelity**: checks the replay against the participant's browser. Every few seconds the browser
  recorded a fingerprint of what it was showing; the player rebuilds the same moment and compares.
  It also reports server messages the browser never confirmed. Use it to confirm a recording
  really captured everything.
- **Info**: the session, scenario, opponent, assistant, result and file.

### Known limits of the replay

The replay rebuilds everything the server sent and everything the browser reported. A few things
that never left the participant's browser are approximated:

- a slider being dragged before the value was sent is not shown moving;
- a notification closed early is shown for its full duration;
- the collapsed / page / sort state of a tool card or table without a component `id`;
- a fingerprint taken while a dragged divider waits for the server's echo may briefly not match
  (the next one does);
- a recording made without browser telemetry (e.g. a headless run) has no pointer, clicks or
  local UI state.

## From the command line

```bash
hani2 replay list [PATHS…]                 # recordings, with result and length
hani2 replay show FILE.hrec [--events]     # what a recording holds
hani2 replay export FILE.hrec -o out.json  # as plain JSON
hani2 replay metrics                       # the evaluation metrics
hani2 replay evaluate [PATHS…] [-m outcome,optimality] [--llm] [-o table.csv]
hani2 replay compare  [PATHS…] --by opponent [-o groups.csv]
```

`PATHS` are recording files or folders (searched recursively); the default is the results folder.

## From Python

```python
from hani2.recording import Recording

rec = Recording.load("results/alice/recordings/20261117-101500-Trade-1a2b3c.hrec")
rec.summary            # the result
rec.offers()           # every offer, by whom
rec.of("chat")         # assistant chat
rec.of("llm")          # language-model calls
rec.telemetry()        # (time, type, data) from the browser
rec.state_at(42.0)     # what was on screen 42 s into the recording
```

## The file format

Each line is a JSON object. The first is the header
(`{"k": "header", "format": "hani2-recording", "version": 1, "id", "t0", "session", …}`); every
other line has `t` (seconds since `t0`) and `k` (its kind):

| `k` | Contents |
| --- | --- |
| `out` | A message sent to the browser: `m` (its type) and `seq`. `state` and `tool` messages are stored as a full copy (`full`) or as changes since the previous one (`delta`); others as `msg`. |
| `in` | A message from the browser (`msg`). |
| `tel` | A batch of browser telemetry: `sent` (browser clock, ms) and `ev`, a list of `[browser ms, type, …]`. Types: `vp` viewport, `mm` pointer move, `pd`/`pu` pointer down/up, `click`, `key`, `input`, `scroll`, `focus`, `blur`, `vis`, `recv` (a server message was applied), `ui` (local UI state), `toast`, `chk` (fingerprint). |
| `ev` | An event-log entry (`type`, `component`, `action`, `value`, …). |
| `act` | An action on the participant's seat: `actor` (human, agent, autopilot), `type` (offer, accept, end, text), `offer`, `values`, `text`, `utility`. |
| `draft` | The counter-offer was edited (`by`: human or agent). |
| `chat` | An assistant chat message. |
| `llm` | A language-model call: `role`, `model`, `latency`, `usage`, `cost`, `prefix` (messages shared with the previous call of that role) and the new `messages`, `response`. |
| `fn` | A function the assistant called: `name`, `args`, `result`, `latency`. |
| `scenario` | Issues, `outcomes`, `utilities` (one list per party), `reserved`, `human_index`, serialized utility functions. |
| `start`, `trace`, `result`, `questionnaire`, `end` | The negotiation's start (opponent, settings, assistant), its full trace, its result, the questionnaire and its answers, and the end of the recording. |

Deltas map a key to `{"s": value}` (set), `{"a": [items]}` (append to a list), `{"d": 1}`
(delete) or `{"o": delta}` (changes inside a nested object). `hani2.recording.format.patch`
applies them.
