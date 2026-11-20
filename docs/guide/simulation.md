# Simulated participants

A **simulated participant** is a persona that plays the human seat of a negotiation, so an
Assistant can be tried many times, cheaply and repeatably, before any human takes part. Use it to
measure an Assistant's reliability (pass^k), to debug it, and as a **qualifying round** for
entrants: only Assistants that do well with simulated participants go on to the human study.

Simulated sessions are tagged `mode: simulated` everywhere (results rows, recordings, evaluation
rows). They are **never ranked with human sessions**: the leaderboards leave them out, `compare`
keeps them in groups of their own, and they get no questionnaires and never count towards a
study's balancing or quotas.

## Run it

```bash
hani2 simulate -a my_agent.py:MyAgent                      # follower, skeptic, stubborn, click_through × 4
hani2 simulate -a my_agent.py:MyAgent -p skeptic -p "stubborn:max_concession=0.1" -k 8 -s Trade -s Job
hani2 simulate -a my_agent.py:MyAgent -p "llm:goal=\"Keep the price under 300\",reservation=0.5" -k 3
```

Every trial prints its result; at the end come the goal rate per persona and pass^k. Results and
recordings are saved under `HANI2_HOME` as user `sim_<persona>` (`--temp` writes them to a
temporary folder instead), so they show up in the admin console's **Qualifying round** table and
can be evaluated like any other recording. `--out trials.csv` writes one row per trial.

From Python:

```python
from hani2.simulator import simulate, run_trials, Stubborn

trial = simulate("skeptic", agent_class="my_agent:MyAgent", scenario="Trade", seed=1)
print(trial.goal_met, trial.human_utility, trial.suggestions_taken, trial.recording)

report = run_trials(["follower", Stubborn(max_concession=0.1)], k=4, agent_class="my_agent:MyAgent",
                    scenarios=["Trade"], opponents=["BoulwareTBNegotiator"])
print(report["reliability"])   # pass^k per persona
```

`run_trials` runs every persona × scenario × opponent `k` times, one after the other. All the
trials of a cell play **the same scenario** (`scenario_index`, default 0, also for generated
scenario types), so pass^k measures how consistently the Assistant handles one task. Trial *i* uses
seed `seed + i` for the opponent's and the session's random choices.

## Personas

| Persona | Type | Behaviour |
| --- | --- | --- |
| `follower` | easy | Always does what the Assistant suggests. Without a suggestion it accepts an offer at least as good as its own next offer and otherwise counters with it. |
| `click_through` | easy | Does not read: takes the suggestion when there is one, otherwise accepts whatever the opponent offers. |
| `skeptic` | hard | Takes the suggestion only if it is worth at least as much to them as their own next offer. |
| `stubborn` | hard | Never accepts or offers anything more than `max_concession` (default 0.2) below their best utility, whatever the Assistant says. |
| `llm` | hard | Played by a language model (below). |

Every persona has a negotiation strategy of its own, used when it does not follow the Assistant:
a time-based concession from its best utility down to its reservation value
(`aspiration_exponent`, 2 by default and 6 for `stubborn`). Options are given as
`name:key=value,…`: `seed`, `reservation` (the persona's own walk-away value; by default the
scenario's), `difficulty`, `aspiration_exponent` and the persona's own (`max_concession`, and the
language-model options). A value may contain commas (quote it to be safe:
`llm:goal="Win, but politely",seed=2`); only a comma followed by `key=` starts a new option.

The persona's type, `easy` or `hard`, becomes its **participant type** (`simulated-easy`,
`simulated-hard`), which stratifies the qualifying table and can be grouped on with
`hani2 replay compare --by participant_type`.

### What counts as a suggestion

Anything the Assistant did since the participant's turn began: filling in the counter-offer
(`set_offer`) suggests that offer; asking to confirm *accept* or *end* suggests accepting or walking
away; a spotlight on *accept*, *end*, *reject* or *send* suggests that button (a spotlight on
*reject* or *send* without a filled-in offer means "counter with your own offer"). A confirmation
request beats a spotlight. Questions the Assistant asks with `ask_user` are answered by the persona
(the scripted ones pick an option), so a trial never waits for a human.

If the Assistant acts on the participant's seat itself (semi or full autonomy), the persona
waits for the next turn.

### Language-model personas

```python
from hani2.simulator import LLMPersona, simulate

p = LLMPersona(goal="Buy the car for at most 9,000 and get the winter tyres.",
               reservation=0.45,
               temperament="Impatient, a little suspicious of advice.",
               disclosure="Mention your budget only if asked, and your limit only if pressed.",
               max_chat_per_turn=1, model=None)
trial = simulate(p, agent_class="my_agent:MyAgent")
```

The model sees only what a human would see: the issues, the opponent's offers and their
utility *to the participant*, the history, the Assistant's messages and its current suggestion,
and its own idea for a counter-offer. It never sees the opponent's preferences. Give it a
`reservation` to make its walk-away value **private**: it is then only in the persona's prompt, and
the Assistant can learn it only by asking, which is what the `disclosure` instruction is for
(information comes out gradually, as with a real participant). Without one the persona uses the
scenario's reservation value, which the Assistant can already see.

On every turn the persona may first talk to the Assistant (up to `max_chat_per_turn` messages),
then accepts, counters, follows the suggestion or walks away. Writing `###STOP###` ends its
participation (goal met or given up). If the negotiation is still running it walks away, and the
token itself is never sent to the Assistant.

It uses the `tools` model chain (see [Models and connections](models.md)) unless you give
`provider` / `model`. Its calls are recorded with the role `simulator`, so they are never counted
as the Assistant's tokens or cost.

## Success, validity and pass^k

A trial **meets its goal** (`goal_met`) when it ends in a deal worth at least the persona's
reservation value to it. That is the success criterion of pass^k for simulated runs. Do not use
"a deal was reached": a follower with an Assistant that accepts everything would always succeed.

A trial is **invalid** when it says nothing about the Assistant: it timed out, hit the turn cap,
the Assistant was still busy after `assistant_timeout` seconds (default 180), the simulator's
model failed or the opponent failed. The reason is in the `sim_invalid` column of its results row
(and its `goal_met` is empty). Invalid trials are left out of pass^k and of the qualifying table and
counted separately.

## What is recorded

Each simulated recording holds, besides everything a human recording holds:

- a `sim` record: the persona, its type, policy, parameters, seed, reservation value and the best
  utility it could get;
- a `sim_turn` record per move: the suggestion seen, the persona's own next offer, the move, its
  utility and whether the suggestion was taken;
- a `sim_end` record: goal met, valid (and why not), stopped.

The [`simulation` metric](metrics.md#simulation-simulated-participant) turns these into columns
(`sim_goal_met`, `sim_valid`, `sim_take_rate`, …). It also checks, without a language model, that a
scripted persona kept to its policy (`sim_violations`, which should be 0).

## Auditing the simulator

A simulated participant can fail too. It can break character, reveal its private limit
unprompted, or stop for no reason. With a failing simulator a bad trial looks like a bad
Assistant. The [`error_review`](evaluation.md#soft-metrics-language-model-judge) judge therefore
gets a third source for simulated recordings. It is shown the persona and blames errors on the
**simulator** when the persona broke its instructions, and on the **human** only for in-character
negotiating mistakes:

```bash
hani2 replay evaluate ~/negmas/hani2/db/sim_llm -m simulation,error_review --llm -o audit.csv
```

`simulator_errors` and `simulator_critical_errors` count them. Trials with a critical simulator
error are candidates to discard before you report pass^k. Read a sample of them to decide whether
the persona's prompt needs work.

## Keeping simulated and human results apart

- The results rows of simulated sessions have `mode = simulated`, a `participant_type` of
  `simulated-easy` or `simulated-hard`, the `persona` and `goal_met`. Their users start with `sim_`.
- The leaderboard (admin console, *All Results* tool) and its summary rank human participants
  only. Simulated runs appear in a separate **Qualifying round** table: per Assistant and persona,
  the valid trials, the goal rate and pass^k. It pools every run of the same Assistant spec, so give
  an entrant's version a new file or class name, or use `--temp`, to keep runs apart.
- `hani2 replay compare` puts simulated recordings in their own groups (`<group> [simulated]`)
  unless you group by `mode`. Group by several fields to stratify:
  `--by support_agent,participant_type` shows each Assistant on easy and on hard participants.
- User names starting with `sim_` (and `guest_`) are reserved, so no account is mistaken for a
  simulated participant.
- Simulated sessions get no questionnaires (neither the
  [pre-questionnaire](studies.md#pre-questionnaire-and-participant-types) nor the per-negotiation
  one) and never count as study participants for balancing.
