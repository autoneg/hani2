# Self-hosting an Assistant or opponent

Run your Assistant or opponent on your own machine, with any language model you like. HANI2 calls it
over HTTP for every negotiation, and to the rest of HANI2 it looks like a local agent.

## For teams: three steps

**1. Install and write your agent** as you would for HANI2. An Assistant is a subclass of
`hani2.assistant.Assistant` ([Build an Assistant](../tutorials/assistant.md)); an opponent is any negmas
`SAONegotiator`.

```bash
pip install hani2
```

**2. Serve it** with the token the organisers gave you:

```bash
export HANI2_HOSTED_TOKEN=h2t_...            # from the organisers; keep it secret
hani2 host-assistant my_agent:MyAssistant --port 8700 --version 1.0
# or
hani2 host-opponent my_negotiator:MyNegotiator --port 8701 --version 1.0
```

The host listens on all interfaces. It answers only requests that carry your token.

**3. Send the organisers your address**, for example `https://team.example.org:8700`. It must be
reachable from the HANI2 server: a public host, a port opened on your machine, or a tunnel.

That is all. Change your code whenever you like and restart the host. `--version` is shown to the
organisers but is never checked.

**Your language model.**

* An Assistant served this way uses the model chain of the HANI2 installation **on your machine**
  (your `models.json` and connections, [Models and connections](models.md)), or its own `_complete`.
  HANI2's server never sees your keys.
* Pass `--model provider:model` to report the model you use. HANI2 records it as you report it.

**Test locally before you send the address:**

```python
from hani2.hosting import make_app, run_host

with run_host(make_app("opponent", "my_negotiator:MyNegotiator", token="t")) as url:
    print(url)   # register it in a local HANI2 project and play against it
```

## What your agent can do

* **An opponent** gets its utility function and the negotiation's limits when a negotiation starts.
  On each of its turns it gets the state, and it answers by accepting, countering (an offer and an
  optional message) or ending.
* **An Assistant** gets the same events a local one gets: chat messages, the start and end of a
  negotiation, panel clicks, the LLM offer tool and autopilot turns. It reads the same negotiation
  state and uses the same functions and helpers.
* Everything an Assistant does runs in HANI2 with the capabilities and autonomy the organisers
  granted, exactly as for a local Assistant. Functions its own dispatcher adds run on your machine.

Two limits apply to a hosted Assistant:

* It answers events; it cannot speak on its own between them.
* It cannot read interface objects directly (`self.session.<…>`). It uses the helpers (`post`,
  `toast`, `highlight`, …), the functions (`get_negotiation_state`, …) and
  `session_state["actions"]`.

**Isolation.** Every negotiation is a separate session with its own instance of your agent, so two
negotiations running at once never share state. A negotiation idle for an hour is dropped (change it
with `--idle-timeout`). At most 200 run at once (change it with `--max-sessions`).

**Time limits.** HANI2 waits 30 s per call by default, and the organisers may change it.

* A hosted opponent that does not answer passes its turn, and the participant is told. After 3
  failures in a row it walks away.
* A hosted Assistant that does not answer shows an error in the chat.
* **The game still counts**, so make sure your host stays up.

## For organisers

Register each team's endpoint in the admin console (**Library → Hosted agents**) or on the command
line:

```bash
hani2 hosted add HI2027 teamA https://team-a.example.org:8700 --kind assistant --team "Team A"
# prints a new token: send it to the team
hani2 hosted check HI2027        # is every host up, and is it the right kind?
hani2 hosted list HI2027
hani2 hosted enable HI2027 teamA --off   # leave it out of the pool for a while
```

Then either make a side self-hosted, so that every registered agent of that kind that is switched on
is in the pool:

```yaml
# project.yaml (or study.yaml)
hosted: {assistants: true, opponents: false, timeout: 30, max_failures: 3}
```

or name hosted agents wherever a class is accepted, as `remote:<name>`:

```yaml
assistants: [remote:teamA, remote:teamB, hani2.assistant.Assistant]
opponents: [remote:oppX, BoulwareTBNegotiator]
```

An admin may also give a direct address for a test: `remote+https://host:8700#token_env=VAR`, where
the token comes from the variable `VAR` on the HANI2 server. A participant's link can name only
registered `remote:` agents, never an address.

**What is recorded.**

* Results, events and boards use the registered name (`remote:teamA`), never the address or the token.
* `assistant_version` / `opponent_version` hold the version the host declares.
* `assistant_llm` / `opponent_llm` hold `remote:<provider/model>` as the host reported it.
* `hosted_failures` counts the calls that failed in the game.

**Leaderboard.** Self-hosted agents can change without notice, so use a continuous board:
`leaderboard: {update: continuous}` ([Leaderboard update modes](project-management.md#leaderboard-update-modes)).
It uses every game, gives recent games more weight and flags a probable new version.

## The protocol

To write a host in another language, implement four JSON endpoints (protocol `hani2-hosted/1`). Every
request carries `Authorization: Bearer <token>`.

| Request | Body | Reply |
|---|---|---|
| `GET /info` | none | `{protocol, kind, name, version, events?, model?}` |
| `POST /sessions` | `{session_id, kind, setup}` | `{ok, model?}` |
| `POST /sessions/{id}/step` | `{seq, …}` | the agent's reply |
| `DELETE /sessions/{id}` | none | `{ok}` |

`seq` grows by one per step. Answer a repeated `seq` with the stored reply.

**Opponent.**

* `setup` holds `name`, `ufun` (negmas serialisation as YAML, or a table of outcomes and values),
  `outcome_space`, `issues`, `n_steps`, `time_limit` and `reserved_value`.
* A step holds `state`: `step`, `relative_time`, `current_offer` (values in issue order),
  `current_proposer` (`self` or `other`), `current_text` and `n_acceptances`.
* Reply with `{response: accept | reject | end, outcome: [...] | {issue: value}, text?}`.

**Assistant.**

* `setup` holds `issues`, `outcome_space`, `capabilities`, `autonomy`, `functions` (OpenAI-style
  schemas of what you may call) and `settings`.
* A step holds `event` (`message`, `negotiation_started`, `action_requested`, `negotiation_ended`,
  `draft_changed`, `panel_action`, `suggest_offer`, `autopilot`, `clear` or `results`) with its
  `data`, plus `context`, the negotiation state a local Assistant reads.
* Reply with `{status: done | calls, actions: [...], calls: [...], suggestion?, model?}`.
    * `actions` are run in order and not answered, for example `{action: "post", arguments: {text}}`,
      `toast`, `show_on_board`, `highlight`, `annotate` or `set_layout`.
    * `calls` are functions from `functions`, for example
      `{id, function: "set_offer", arguments: {outcome}}`. HANI2 runs them and sends a `results` step
      with `data.results = [{id, result}]`. Answer it like any step, until you reply `done`.
    * A `suggest_offer` event is answered with `suggestion: {outcome, text}`.

The [design note](../reference/hosted-agents-design.md) explains the choices behind the protocol.
