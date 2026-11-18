# Prolific

HANI2 can run paid studies on [Prolific](https://www.prolific.com). Participants arrive through a link that carries their Prolific ID, do one practice negotiation and a fixed number of counted negotiations, and get a completion link at the end. They never create an account.

## The entry URL

Point your Prolific study at the playground with the participant's ID in the query string:

```text
https://negotiate.example.org/play?PROLIFIC_PID={{%PROLIFIC_PID%}}
```

For a study of a project, use the study's address (`hani2 study create` prints it, see [Projects and studies](projects.md#prolific)):

```text
https://negotiate.example.org/s/HI2027/hi-2027-01/play?PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}
```

The lowercase `prolific_pid` parameter also works. HANI2 keeps only letters, digits, `-` and `_` from the ID, up to 64 characters.

What changes for a URL with a Prolific ID:

- The participant's user name is `prolific_<PID>` and their session key is `prolific:<PID>` (for a study other than the server's default study, the key also names the study, so the same person can take part in two studies). Opening the link again, in any browser, returns to the same session while the server is running.
- The link works even when the playground is disabled in `env.json`.
- The session is never in admin mode, even for a logged-in admin and even with `?admin=1`.
- The Assistant starts switched off. The participant can still switch it on, if the Assistant is available to them at all (see [Assistant](assistant.md)).
- The *Different scenario* button on the start screen is hidden.

## The study flow

1. **Practice round.** The first negotiation is a practice round. It does not count. The opponent comes from `PROLIFIC_PRACTICE_OPPONENTS` and cannot end the negotiation itself (see [Opponents](opponents.md)). The time limit is `PROLIFIC_PRACTICE_TIME_LIMIT`.
2. **Counted rounds.** Then come `PROLIFIC_N_REQUIRED` counted negotiations, each with the time limit `PROLIFIC_COUNTED_TIME_LIMIT`.
3. **Questionnaire.** If a per-negotiation questionnaire is configured, it follows each round (see below).
4. **Completion.** When the last counted round is done, the participant sees *You're all done* and a *Finish and submit* button that opens the completion URL in the top window.

After every round, HANI2 shows a notice and a toast with the progress, for example "2 of 5 counted negotiations complete — 3 to go."

### What counts

A non-practice round counts when the participant took at least one action in it (an offer or an acceptance), or when the opponent failed with an error. A round in which the participant did nothing is not counted, and the notice says so in red. Ending a negotiation without having made an offer does not count as an action.

The practice round is complete only when the participant took at least one action in it. Otherwise the next round is a practice round again.

### Questionnaires

The questionnaire configured for the study (see [Studies and results](studies.md)) is shown after every round, including the practice round, except after a counted round that did not count or a round in which the opponent failed. The answers go to `negotiation_questionnaires.csv` with `practice` set accordingly.

### Scenarios and opponents

- **Scenario type.** Each participant is assigned one scenario type from the active [scenario set](scenario-sets.md). In a study, participant number *i* (in order of arrival) gets type `i mod t` of the set's `t` types, so the types are spread evenly; without a study the type comes from a hash of the Prolific ID. They keep that type for the whole study, unless a schedule says otherwise.
- **Scenario slot.** Each round uses the next slot of that type's pool (the participant's counter in `last_scenario.txt`). Prolific rounds always use the saved pools.
- **Practice opponent.** A random agent from `PROLIFIC_PRACTICE_OPPONENTS` (default `:pan`; the old name `PROLIFIC_PRACTICE_AGENTS` also works). If that list resolves to no agents, HANI2 uses the normal opponent pool.
- **Counted opponents.** HANI2 takes the agents in `PROLIFIC_FINALISTS`, or the normal opponent pool when it is unset. In a study, participants face them in the order of a balanced Latin square (see [Latin squares](opponents.md#latin-squares)). Without a study, or for a participant who already has a `fallback_rotation.txt`, HANI2 rotates through them: round *k* uses agent `(offset + k) mod n`, and each new participant gets the next offset.
- **Assistant.** With an Assistant pool, each participant keeps one Assistant for the whole study, balanced across participants (see [Assistant pools and assignment](assistant.md#assistant-pools-and-assignment)).

### Schedules

To fix the scenario and opponent of every counted round for one participant, write a `schedule.json` into their results folder, `<results>/prolific_<PID>/schedule.json`:

```json
{
  "negotiations": [
    {"agent_class_name": "ConcederTBNegotiator", "scenario_type": "Island", "scenario_index": 0},
    {"agent_class_name": "helpers.AgentK", "scenario_type": "Trade", "scenario_index": 4, "time_limit": 900}
  ]
}
```

A plain list of entries works too. Entry *k* applies to the *k*-th counted round (rounds that did not count do not advance it); the practice round ignores the schedule. Every field is optional:

| Field | Meaning |
|-------|---------|
| `scenario_type` | The scenario type for this round. |
| `scenario_index` | The slot in that type's pool (an integer). |
| `agent_class_name` | The opponent. HANI2 matches it against the counted-opponent pool, by full spec or by class name, and otherwise uses it as a spec as written. |
| `time_limit` | The time limit in seconds. |
| `assistant` | The Assistant for this round (a class spec, a list, or an Assistant group token). |

A top-level `assistant` next to `negotiations` names the Assistant for every round without one of its own, including the practice round. The schedule's Assistant wins over the study's pool and is used as given.

Other tools can write schedule files before participants arrive; HANI2 only reads them.

### Returning participants

When a participant's folder already holds results from before their current `prolific_session.json` was created, HANI2 treats them as returning: they skip the practice round, and only results after `started_at` count toward the required number. To let a participant start over, delete their `prolific_session.json`. Their existing results are kept and their count starts from zero.

## Automatic timers

Prolific sessions keep moving even when a participant leaves the tab open:

- **Auto-start.** After a scenario loads, the negotiation starts by itself after `PROLIFIC_AUTO_START_SECONDS`.
- **Auto-load.** After a round ends (and after the questionnaire is submitted), the next negotiation loads and starts by itself after `PROLIFIC_AUTO_LOAD_SECONDS`. If the practice round has to be repeated, `PROLIFIC_AUTO_LOAD_PRACTICE_SECONDS` applies instead.
- **Warning.** `PROLIFIC_AUTO_LOAD_WARN_SECONDS` before an auto-load, the participant gets a toast: "The next negotiation starts automatically in N seconds."

The start and result screens show a countdown. Set a timer to `0` to switch it off. Add `?noautostart=1` to the URL (also accepted: `noAutoStart`, `no_auto_start`, with any value) to switch off both timers for that session, which is useful for testing.

## Environment variables

All Prolific settings are environment variables, read when a Prolific session is created. For a study of a project, `n_required`, `practice_time_limit`, `counted_time_limit`, `minutes` and `practice` (whether there is a practice round) can also be set in `study.yaml` or `project.yaml`; an environment variable that is set wins over them (see [Projects and studies](projects.md#studyyaml)).

| Variable | Default | Meaning |
|----------|---------|---------|
| `PROLIFIC_N_REQUIRED` | `5` | Counted negotiations per participant. |
| `PROLIFIC_PRACTICE_TIME_LIMIT` | `300` | Time limit of the practice round, in seconds. |
| `PROLIFIC_COUNTED_TIME_LIMIT` | `600` | Time limit of each counted round, in seconds. |
| `PROLIFIC_AUTO_START_SECONDS` | `120` | Delay before a loaded negotiation starts by itself. `0` turns it off. |
| `PROLIFIC_AUTO_LOAD_SECONDS` | `30` | Delay before the next negotiation loads and starts by itself. `0` turns it off. |
| `PROLIFIC_AUTO_LOAD_PRACTICE_SECONDS` | `60` | The same, when the practice round must be repeated. |
| `PROLIFIC_AUTO_LOAD_WARN_SECONDS` | `15` | How long before an auto-load the warning appears. |
| `PROLIFIC_MAX_MINUTES` | `45` | Recorded in `prolific_session.json` and sent to the browser. HANI2 does not enforce it. |
| `PROLIFIC_PRACTICE_OPPONENTS` | `:pan` | Comma-separated specs for the practice opponent. |
| `PROLIFIC_FINALISTS` | the opponent pool | Comma-separated specs for the counted opponents. |
| `PROLIFIC_PER_NEG_YAML` | none | A questionnaire file (used when `HANI2_PER_NEG_YAML` is not set). |
| `PROLIFIC_COMPLETION_URL` | none | The completion URL. `{pid}` is replaced by the Prolific ID. |
| `PROLIFIC_COMPLETION_CODE` | none | The `{{completion_code}}` variable of texts (wins over `completion_code` in `study.yaml`). |
| `SCMLWEB_BASE_URL` | `https://anac.cs.brown.edu` | Base of the completion URL when `PROLIFIC_COMPLETION_URL` is not set. |
| `SCMLWEB_PROLIFIC_PATH` | `/prolific` | Path of the completion URL when `PROLIFIC_COMPLETION_URL` is not set. |

Without `PROLIFIC_COMPLETION_URL`, the completion URL is `<SCMLWEB_BASE_URL><SCMLWEB_PROLIFIC_PATH>/done?PROLIFIC_PID=<PID>`, the completion page of an outside system such as a competition website, when either variable is set. Otherwise a study's `completion_url` or `completion_code` in `study.yaml` is used (the code becomes Prolific's completion link), and without those the outside system's default path. For your own study, put the completion code Prolific gives you in `study.yaml` (`hani2 study create P/S --completion-code ABC123`), or set `PROLIFIC_COMPLETION_URL`:

```bash
export PROLIFIC_COMPLETION_URL="https://app.prolific.com/submissions/complete?cc=ABC123"
```

The usual HANI2 settings apply too: the opponent pool, scenario pools, `scenario_order.txt` and the experiment (see [Configuration reference](configuration.md)).

## Files written

Prolific participants have the usual result files (see [Studies and results](studies.md)) in `<results>/prolific_<PID>/`, plus:

| File | Content |
|------|---------|
| `prolific_session.json` | `started_at`, the assigned `scenario_type`, `max_minutes` and `max_negs` (`PROLIFIC_N_REQUIRED + 1`). Written on the first visit. |
| `fallback_rotation.txt` | The participant's offset in the opponent rotation (sessions outside a study, and older participants). |
| `schedule.json` | Only if you write one. |

The shared counter for the rotation offsets is `<results>/_prolific_fallback_counter.txt`. In a study, `<results>/assignments.json` holds every participant's index (for the Latin square and the scenario type) and Assistant.

The `practice` column of `results.csv` marks the practice round.

## Testing locally

Run a short study on your own machine:

```bash
hani2 experiment create pilot
export PROLIFIC_N_REQUIRED=2
export PROLIFIC_PRACTICE_OPPONENTS=LinearTBNegotiator
export PROLIFIC_FINALISTS=BoulwareTBNegotiator,ConcederTBNegotiator
export PROLIFIC_COMPLETION_URL="https://example.org/done?pid={pid}"
hani2 --experiment pilot --page play --no-browser
```

Then open `http://localhost:5006/play?PROLIFIC_PID=test1&noautostart=1` (or, for a study of a project, `http://localhost:5006/s/<project>/<study>/play?PROLIFIC_PID=test1&noautostart=1`) and:

1. Play the practice round and make at least one offer.
2. In the first counted round, click *End* before making any offer. The notice says the round does not count.
3. Play the two counted rounds properly. The *Finish and submit* button should link to `https://example.org/done?pid=test1`.

Check `~/negmas/hani2/experiments/pilot/results/prolific_test1/` for the files. Use a new PID (`test2`, ...) for every run, or delete the participant's folder. Remove `noautostart` to watch the timers.
