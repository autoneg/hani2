# Design note: self-hosted agents and a continuous leaderboard

This note records the research and design behind two features:

* **Self-hosted Assistants and opponents.** A team runs its agent on its own machine, with any language
  model it likes. HANI2 reaches the agent at an address instead of importing a class.
* **A continuously updating leaderboard.** It uses every score, gives recent results more weight, and
  does not assume that an agent's code stays the same.

The user guide for teams is [Self-hosting an Assistant or opponent](../guide/self-hosting.md). The
settings are in [Leaderboard update modes](../guide/project-management.md#leaderboard-update-modes) and in the
[settings reference](../guide/settings-reference.md).

## 1. Research

### 1.1 How GLEE lets participants self-host

GLEE is a benchmark of LLM agents in language-based economic games: bargaining, negotiation and
persuasion ([paper](https://arxiv.org/abs/2410.05254)). Its competition ran in August 2026
([site](https://glee-competition.com), [full documentation as one file](https://glee-competition.com/llms.txt),
[SDK](https://github.com/eilamshapira/GLEE_competition/blob/main/sdk/README.md)). The relevant points:

| Topic | GLEE |
|---|---|
| Who calls whom | **The agent calls the platform.** A participant's process joins a queue, polls `GET /api/agent/games/pending` and posts moves to `POST /api/agent/games/{game_id}/move`. No webhook or callback is documented, so a participant needs no public address. |
| What a participant runs | `pip install glee-sdk` and `client.run(strategy, concurrency=8)`, or plain REST from any language. |
| Isolation | Every game has a server-made `game_id`. The platform keeps the game state and returns it, history included, with every poll, so an agent can be stateless and key everything by `game_id`. |
| Identity and authentication | Up to 5 agents per account, each with an API key sent as `Authorization: Bearer <key>`. Resetting the key keeps the agent's ratings and public id. |
| Versions | None. "Update your agent's code anytime; iterating is encouraged." The platform never sees a version or hash of the code. |
| Time limits | 120 s per turn, after which the game ends as no deal. An abandoned game (a timeout or five invalid moves) scores at the 5th percentile, unless the agent never moved, in which case the game is dropped. |
| Leaderboard | Continuous, updated after every game. The payoff becomes a percentile among games of the same configuration and role, adjusted for opponent strength by an hourly refitted model, then `game_rating = 2000 + 8000·(pct − 0.5)`. The rating moves by `ΔR = η·(game_rating − R)`, with η falling from 1 % for new agents to 0.2 % after about 120 games. The board ranks a rating shrunk toward 1000 by `g/(g+30)` (g = games played). |

The constant-gain update is an exponentially weighted mean whose half-life is about ln 2/η games.
That is roughly 350 games at η = 0.2 % (our derivation, not GLEE's), so a silent change of code
takes hundreds of games to show on GLEE's board.

**What we take from GLEE.** One command to run, a bearer token per agent, every game kept apart by an
id, a per-turn time limit, a timeout that counts against the agent, and a board that updates with
every game and shrinks entrants with few games.

**Where we differ.** GLEE's agents *pull* their work. The request was for HANI2 to *call* an agent at
an address it is given, through an adapter that looks like a local agent. We therefore **push**:
HANI2 sends requests to the team's address. The price is that the team needs an address HANI2 can
reach, such as a public host, a port opened on a campus machine or a tunnel. The message set below
does not depend on the transport, so a later version can add a mode in which the host connects out
to HANI2 (GLEE's model) without changing what the messages say (see [Open points](#5-open-points)).

### 1.2 Leaderboards that favour recent results

The setting: each game gives an entrant a score in [0, 1], such as utility or a composite score. The
score is measured against a pool of scenarios and opponents, not as a win or a loss. The agent's code
can change without notice. We want **every** score used, with recent ones weighted more.

| Method | Idea | For us |
|---|---|---|
| Exponentially decayed mean ([exponential smoothing](https://en.wikipedia.org/wiki/Exponential_smoothing)) | Weight `w_i = 2^{−(t−t_i)/h}` with half-life `h`; the uncertainty comes from the effective number of games `n_eff = (Σw)²/Σw²`. | Simple, uses all data, one knob. A fixed `h` trades lag for noise, and gives no principled uncertainty for new entrants. |
| Window or decayed counts with shrinkage ([empirical Bayes](https://en.wikipedia.org/wiki/Empirical_Bayes_method), [Bayesian average](https://en.wikipedia.org/wiki/Bayesian_average)) | `μ̂ = n/(n+k)·ȳ + k/(n+k)·μ₀`. GLEE's `g/(g+30)` is this rule. | Tames small samples. A hard window throws away old data. |
| [Elo](https://en.wikipedia.org/wiki/Elo_rating_system) | `R ← R + K(S − E)`: a constant-gain update. | Pairwise win/loss likelihood and no uncertainty. Our scores are against a pool. |
| [Glicko / Glicko-2](http://www.glicko.net/glicko/glicko2.pdf) | A rating deviation that grows with idle time (`φ* = √(φ² + σ²)`), plus a volatility σ. | Uncertainty is explicit and grows over time. The likelihood is binary and the rating periods are batched. |
| [TrueSkill](https://papers.nips.cc/paper_files/paper/2006/file/f44ee263952e65b3610b8ba51229d1f9-Paper.pdf) / [Through Time](https://proceedings.neurips.cc/paper/2007/hash/9f53d83ec0691550f7d2507d57f4f5a2-Abstract.html) | Gaussian skill with a dynamic factor τ, ranked by μ − 3σ; Through Time smooths over the whole history. | Principled, but the likelihood is ordinal. With a Gaussian likelihood it reduces to the Kalman filter below. |
| [Kalman local-level model](https://en.wikipedia.org/wiki/Kalman_filter) | `y_t = μ_t + ε`, `μ_t = μ_{t−1} + η` with `Var η = q·Δt`. Gain `K = P⁻/(P⁻ + r)`. In steady state it is an exponentially weighted mean ([Muth 1960](https://doi.org/10.1080/01621459.1960.10482064)). | A Gaussian likelihood suits continuous scores. It uses every score, its recency weighting follows from `q/r`, and it gives a posterior SD for ranking. Idle entrants grow uncertain. Jumps need a change detector. |
| Change-point detection: [CUSUM](https://en.wikipedia.org/wiki/CUSUM) (Page 1954), [Page–Hinkley](https://riverml.xyz/latest/api/drift/PageHinkley/), [BOCPD](https://arxiv.org/abs/0710.3742) (Adams & MacKay 2007) | CUSUM: `S⁺ = max(0, S⁺ + z − k)` (and its mirror); an alarm when `S > h`. | Flags a probable new version. It detects a shift in performance, not a change of code, which is what matters for ranking. It needs adjusted residuals, or a change in the pool looks like a change in the agent. |

**Recommended default: a Kalman local-level filter with a CUSUM change flag.**

1. The filter runs over **cell-adjusted** per-game values. Each value is the game's value minus the mean
   of its cell (scenario, side and opponent), plus the grand mean. This is the same adjustment the board
   already makes, so a change in the mix of scenarios or opponents is not read as a change in the agent.
2. The drift is per day of wall-clock time (`drift_sd` per 30 days), so the posterior of an idle entrant
   widens. The observation noise is the pooled within-entrant variance of the board's own data. The
   prior is the board's grand mean with the between-entrant spread, so an entrant with few games is
   shrunk toward the field, as GLEE does.
3. The board ranks by the **lower bound** `μ − z·sd` (z = 1 by default), not by the mean. New, idle and
   just-changed entrants are thereby treated the same way.
4. A two-sided CUSUM runs on the standardised innovations (k = 0.5, h = 5). An alarm records a
   *probable new version* and widens the posterior back to the prior, so the estimate re-learns within a
   few games instead of hundreds, while the history stays. A change in the version an entrant declares
   does the same, but only as a hint: a declared version never splits an entrant, because we cannot
   verify it.

Why not the others: Elo, Glicko and TrueSkill model wins and losses, and their recency mechanisms are
covered more directly by the filter's drift and the CUSUM. A plain decayed mean is offered as the
simpler alternative (`method: decayed`). Its half-life is set by hand.

## 2. Hosted-agent protocol

**Transport:** HTTP/JSON, version `hani2-hosted/1`. Every request carries
`Authorization: Bearer <token>`, where the token is a per-team secret that HANI2 and the host share.
The host rejects any request without it, so nobody else can spend the team's model credit.

| Request | Body → reply |
|---|---|
| `GET /info` | → `{protocol, kind: assistant\|opponent, name, version, events?, model?}`. `version` is whatever the team declares. `events` lists the optional Assistant events the host wants: `draft_changed`, and `action_requested` (which it also gets when the admin turned on the proactive note for it). |
| `POST /sessions` | `{session_id, kind, setup}` → `{ok, model?}`. Creates **one agent instance for this negotiation**. |
| `POST /sessions/{id}/step` | `{seq, …}` → the agent's reply (below). `seq` grows by one per step, and a repeated `seq` returns the stored reply, so a retry never acts twice. |
| `DELETE /sessions/{id}` | → `{ok}`. Ends the negotiation's instance. |

**Isolation.** A session id is an opaque random id that HANI2 makes per negotiation. The host keeps
one agent instance per id and never shares state between ids. Ids from other HANI2 servers or other
negotiations cannot collide. The host drops a session idle for `--idle-timeout` (default 1 h) and
refuses new sessions beyond `--max-sessions`.

**Opponent.**

* The setup holds the negotiator's name, its utility function and the outcome space (negmas
  serialisation; the utility function as YAML, because JSON would turn the integer keys of a value
  table into strings, with a table of every outcome's utility as the fallback), and the mechanism's
  limits (`n_steps`, `time_limit`).
* A step sends the negotiation state: step, relative time, the offer on the table, its text and the
  history. The reply is `{response: accept|reject|end, outcome, text, data?, model?}`.
* The Python helper wraps any negmas `SAONegotiator`. It builds a local stand-in mechanism with the
  same outcome space so the negotiator sees a normal interface.

**Assistant.**

* The setup holds the capabilities the admin granted, the autonomy, the issues (outcome space) and the
  function schemas that a local Assistant's language model would see.
* A step sends one event: `message`, `negotiation_started`, `action_requested`, `negotiation_ended`,
  `panel_action`, `suggest_offer`, `write_message`, `offer_from_message`, `autopilot`, `draft_changed`,
  `clear` or `results`. It also sends the same
  `context` snapshot a local Assistant reads, and nothing about the participant's identity.
* The reply is `{status: done|calls, actions: […], calls: […], suggestion?, model?}`.
    * `actions` are fire-and-forget: `post`, `toast`, `show_on_board`, `highlight`, `annotate`,
      `set_layout` and so on (the Assistant helpers).
    * `calls` are functions whose results the agent needs, such as `get_negotiation_state` or
      `submit_counter_offer`. HANI2 runs them and sends their results back in a `results` step, until
      the host answers `done`.
* **Everything runs through the local Assistant helpers and function dispatcher, with the admin's
  capabilities and autonomy enforced on the HANI2 side.** A host can only do what a local Assistant
  with the same settings could do.
* The Python helper runs an unchanged HANI2 `Assistant` subclass on the host. The class's helpers
  become actions, and its function calls become `calls`. It uses the host's own model chain, which is
  the team's LLM. Extra functions defined in the class's own dispatcher run on the host.
  `session_state["actions"]` maps to the same functions, so a tutorial-style Assistant runs unchanged
  and stays gated. A step may take the rest of the turn's deadline, since one step can be a whole
  language-model turn on the host.
* An opponent's state names the side that made the current offer `self` or `other` (the human's side).
  The host builds the negotiator the way HANI2 builds a local opponent, so an LLM negotiator uses the
  **host's** model chain, and the host reports that model.

**Model attribution.** Any reply may carry `model: {provider, model}`. HANI2 records it, unverified,
in the existing results columns `assistant_llm` / `opponent_llm` as `remote:<provider>/<model>`. The
`…_llm_entry` column holds `hosted:<name>@<version>`. Remote agents never use HANI2's own model chain.

## 3. Inside HANI2

**Specs.** Wherever an Assistant or opponent class is accepted, HANI2 also accepts:

* `remote:<name>`: an endpoint registered for the project (the normal way). Results, events and the
  board record this name, never the address or token.
* `remote+https://host:port[/path]`, optionally with `#token_env=VAR`: a direct address. It is for
  admins and files only. A non-admin's URL (`?opponents=`) can never name an address, so the server
  cannot be steered to call arbitrary hosts.
* A mapping `{url: …, token_env: …}` in `study.yaml` / `project.yaml` lists.

**Adapters.**

* `RemoteOpponent` is a negmas `SAONegotiator`. On `on_negotiation_start` it opens the host session; on
  each turn it posts the state with a time limit (`timeout`, default 30 s); at the end it closes the
  session.
* On an error or a timeout, the opponent answers with a rejection without a counter-offer, so the
  negotiation does not hang, and a toast appears once. After `max_failures` failures in a row (default
  3) it ends the negotiation.
* `RemoteAssistant` is an `Assistant` subclass. It opens one host session per negotiation (one Assistant
  object spans several negotiations in a session) and forwards events. Every turn has a deadline and
  always releases the busy lock. An unreachable host gives a visible error in the chat and never blocks
  the negotiation.
* `RemoteAssistant` overrides `model()`, so the local chain is never resolved for it. It shows the
  model the host reports.

**Scoring a failure.** A game whose host failed still counts against the host's entrant, as in GLEE:
it ends as the opponent's walk-away or as an Assistant that said nothing. It is not dropped, so a
team cannot remove bad games by timing out. Rows carry `hosted_failures` (the number of failed calls)
so admins can review such games.

**Registry and mode.** `<project>/hosted_agents.json` lists the endpoints:
`{name, kind, url, token, team, enabled}`. Tokens stay on the server and never reach a browser, an
event or a results row. You manage it with `hani2 hosted add|list|remove|check` and the admin console
(Projects → Hosted agents). A project or study sets

```yaml
hosted:
  assistants: true    # the Assistant pool = the enabled hosted Assistants (unless `assistants:` lists some)
  opponents: false    # the same for opponents
  timeout: 30         # seconds per call
```

Teams run `hani2 host-assistant my_module:MyAssistant --token-env TEAM_TOKEN` or
`hani2 host-opponent my_module:MyNegotiator …`.

## 4. Leaderboard update modes

`hani2.ratings` is a pure module that depends only on the Python standard library. scmlweb's Python
scripts can import it, and its `python -m hani2.ratings` command reads JSON lines from standard input,
so the PHP side can shell out to it. It takes time-stamped observations
`(entrant, time, value, version?, tournament?)` and a `now`, and recomputes from scratch, so a board is
reproducible. The board's `leaderboard:` block picks the mode:

```yaml
leaderboard:
  update: pooled        # default: every counted game weighs the same (the window switch still applies)
  # update: latest      # periodic / aperiodic tournaments: only the newest tournament (a study) counts
  # update: {mode: continuous, method: kalman, drift_sd: 0.1, z: 1.0, change_h: 5}
```

* `latest`: each study of a project board is one tournament. The newest one, by its latest game,
  replaces the board, and an entrant missing from it is not listed. This is the classic style of
  periodic competitions.
* `continuous`: every counted game, with the recommended default above. The `window` switch still hides
  older games if an admin offers it. `min_games` and `min_participants` work as before. Each entry gains
  an optional `rating` field (`mean`, `sd`, `lower`, `n_eff`, `last_game`, `changes`, `versions`), and
  `values[k].mean`/`ci` hold the filtered mean and `mean ± z·sd`. Ranks use `rating.lower`. The schema
  stays `hani2.leaderboard/2`, with new fields optional.

## 5. Open points

* **An outbound-connect mode** (the host opens a WebSocket to HANI2, as GLEE's agents poll it). It would
  spare teams a public address. The message set is ready for it, but the transport is not built.
* The filter's parameters are fixed defaults. They are not fitted by maximum likelihood across entrants.
* A host can claim any model; we record it and cannot verify it.
* A hosted Assistant answers events; it cannot speak between them (push transport).
* The registry file is locked per process: two HANI2 processes writing it at the same moment could lose
  an edit.
* Rows record a hosted entrant's declared version only as a hint. The board's change flag rests on the
  results.
