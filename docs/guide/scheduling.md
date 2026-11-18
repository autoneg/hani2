# Scheduling methods

In a study, HANI2 decides three things for every human and every negotiation:

- which **opponent** they face,
- which **Assistant** helps them,
- which **scenario type** they negotiate in.

Each of these *dimensions* has its own scheduling method. A study chooses them in
`study.yaml`, and a project can set defaults for all its studies in `project.yaml`:

```yaml
# projects/HI2027/studies/hi-2027-01/study.yaml
type: prolific
scheduling:
  opponents: latin_square   # random, cyclic, fixed_order, external
  assistants: balanced      # random_fixed, random_each, round_robin, external
  scenarios: by_participant # set_order, random, latin_square, external
```

Each dimension is resolved separately: the study's choice, else the project's
(`scheduling:` in project.yaml, at the top level or under `defaults:`), else the
default (`latin_square`, `balanced`, `by_participant`). A study can therefore change
only the opponents' method and keep the project's choice for the rest. Names are
checked when a study or project is saved (`hani2 study create`, the admin API); an
unknown name in a hand-edited file is reported (server log, `hani2 study show`,
the admin study page) and the default is used.

From the command line:

```bash
hani2 scheduling list               # every method, one line each
hani2 scheduling list --details     # with examples, rules, advantages and disadvantages
hani2 study create HI2027/hi-2027-01 --opponent-scheduling random \
    --assistant-scheduling round_robin --scenario-scheduling latin_square
hani2 project create HI2027 --opponent-scheduling cyclic   # a default for every study
hani2 study show HI2027/hi-2027-01  # the methods in use, and any error
```

## Who is scheduled

- **Participant index.** Every counted human of a study gets an index on first sight
  (0, 1, 2, … in order of arrival), kept in the study's `assignments.json`. The rules
  below use it as $i$; $k$ is the negotiation (counted negotiations for Prolific,
  online and lab participants: practice rounds do not count).
- **Not scheduled.** Admins, playground guests (`guest_*`), test links that bring
  their own pool (`?opponents=`, `?group=`), the opponent picker (`?admin=1`) and an
  admin's own scenario choice are left alone, as are all sessions outside a study:
  they keep HANI2's plain behaviour (a random opponent from the pool, the set order
  of scenarios, the balanced Assistant pick).
- **Practice rounds** draw their opponent from the practice pool
  (`PROLIFIC_PRACTICE_OPPONENTS`, recorded as `practice`) and use the scenario type
  of the first counted negotiation (with `scenarios: external`, the participant's own
  type, recorded as `practice`). With `assistants: external` they use the
  schedule's top-level Assistant, else the first slot's.
- **Scenario types of logged-in users.** For people who log in to the app of a study
  (not Prolific, online or lab participants), scenarios keep following the set order
  unless the study or project chooses a `scenarios` method explicitly.

## Input from an outside system wins

A participant's `schedule.json` (written into their results folder by an outside
system) always wins over the method: a slot's `agent_class_name`, `scenario_type` /
`scenario_index` and `assistant` (or the top-level `assistant`) are used as given and
recorded as `external`. A slot that leaves the opponent open is filled with the
cyclic rotation, as before. The `external` method means *only* such input is used;
what happens when it is missing is described with each `external` method below.

## Recorded in the results

Every result row says which method chose what, in three columns added after the
existing ones:

| Column | Values |
|---|---|
| `opponent_scheduling` | a method key; `external` when `schedule.json` named the opponent; `practice` for a practice round; `external:missing` when `external` found no input; empty when HANI2 did not schedule the opponent |
| `assistant_scheduling` | a method key; `external` for an Assistant from `schedule.json`; empty for an admin's or a test link's explicit choice |
| `scenario_scheduling` | a method key; `external` / `external:missing` as above; empty for an admin's choice or outside a study |

The same values are in the `scenario_started` events. A human's fixed Assistant
(and the method that chose it) is also kept in `assignments.json`; a human keeps
their Assistant when the study's method changes later.

## Admin API

`GET /api/admin/scheduling-methods` (admins only) returns the registry:

```json
{"dimensions": {"opponents": [{"key": "latin_square", "title": "...", "summary": "...",
                               "details": "Markdown with $maths$"}, ...],
                "assistants": [...], "scenarios": [...]},
 "defaults": {"opponents": "latin_square", "assistants": "balanced", "scenarios": "by_participant"}}
```

`GET /api/admin/projects/{project}/studies/{study}` returns the study's own
`scheduling` (as written in study.yaml), `scheduling_effective` (with the project's
and the default methods filled in) and `errors`; `PUT` accepts `scheduling` in the
study data and refuses unknown names with a 400 that lists the valid ones. The
project endpoints do the same for project.yaml.

## The methods

<!-- scheduling-methods:start (generated by `python -m hani2.scheduling docs/guide/scheduling.md`) -->

## Opponents

Default: `latin_square`.

| Method | Summary |
|---|---|
| [`latin_square`](#opponents-latin-square) | Every participant meets the pool in an order from a balanced (Williams) Latin square. |
| [`random`](#opponents-random) | Each negotiation draws an opponent uniformly from the pool. |
| [`cyclic`](#opponents-cyclic) | Participant i starts with opponent i and goes round the pool in order. |
| [`fixed_order`](#opponents-fixed-order) | Everyone meets the pool in the same order, the order of the pool. |
| [`external`](#opponents-external) | Only an outside system decides: the participant's schedule.json names each opponent. |

### Balanced Latin square (`latin_square`) {#opponents-latin-square}

*Every participant meets the pool in an order from a balanced (Williams) Latin square.*

Each participant faces the opponents in the order of one row of a **balanced Latin
square** (a Williams design). Over a full set of rows every opponent appears
equally often in every position (*order balance*) and every opponent directly
follows every other opponent equally often (*carry-over balance*), so neither the
position of an opponent nor the opponent met just before can explain a result.

Example: 3 opponents A, B, C and 4 participants.

| Participant | Negotiation 1 | Negotiation 2 | Negotiation 3 |
|---|---|---|---|
| 0 | A | B | C |
| 1 | B | C | A |
| 2 | C | A | B |
| 3 | C | B | A |

With an odd number of opponents the square has $2n$ rows (each row and its
reverse); for 3 opponents these are the 6 rows below, so a multiple of 6
participants completes the design.

| Row | Position 1 | Position 2 | Position 3 |
|---|---|---|---|
| 0 | A | B | C |
| 1 | B | C | A |
| 2 | C | A | B |
| 3 | C | B | A |
| 4 | A | C | B |
| 5 | B | A | C |

**Rule.**

Number the opponents of the pool $P = (P_0, \dots, P_{n-1})$. The first row of the
square is

$$
r = (0,\ 1,\ n-1,\ 2,\ n-2,\ 3,\ \dots)
$$

and row $j$ adds $j$ to every entry: $W_{j,k} = (r_k + j) \bmod n$ for
$j = 0, \dots, n-1$. For odd $n$ the $n$ reversed rows are appended, so the square
has $R = n$ rows for even $n$ and $R = 2n$ rows for odd $n$. Participant $i$
(their index in the study: 0, 1, 2, … in order of arrival) takes row $i \bmod R$:

$$
o(i, k) = P\left[\, W_{i \bmod R,\; k \bmod n} \,\right]
$$

where $k = 0, 1, \dots$ is the counted negotiation (practice rounds do not count).

**Advantages**

- Balances the position of each opponent and which opponent came just before it.
- Deterministic and reproducible: the participant index alone gives the order.
- Every participant meets every opponent once in the first $n$ negotiations.

**Disadvantages**

- The balance is exact only when the number of participants is a multiple of $R$
  ($n$ or $2n$); drop-outs leave the last rows under-filled.
- When participants play fewer negotiations than there are opponents, each meets
  only a part of the pool (still balanced across participants).

### Random (`random`) {#opponents-random}

*Each negotiation draws an opponent uniformly from the pool.*

Every negotiation draws its opponent **uniformly at random** from the pool,
independently of the other negotiations. The draw is seeded by the study, the
participant and the negotiation, so a reload or a reconnect gives the same
opponent.

Example (one possible draw): 3 opponents A, B, C and 4 participants.

| Participant | Negotiation 1 | Negotiation 2 | Negotiation 3 |
|---|---|---|---|
| 0 | A | A | A |
| 1 | B | C | B |
| 2 | A | C | B |
| 3 | C | C | A |

**Rule.**

$$
o(i, k) \sim \mathrm{Uniform}(P), \quad \text{independently for each } (i, k)
$$

**Advantages**

- Simple, no hidden structure; every opponent is equally likely in every slot.
- Works for any pool size and any number of negotiations.

**Disadvantages**

- No balance in small samples: an opponent can be met twice in a row or never.
- Order and carry-over effects are only averaged out over many participants.

### Cyclic rotation (`cyclic`) {#opponents-cyclic}

*Participant i starts with opponent i and goes round the pool in order.*

Participant $i$ starts with opponent $i$ (modulo the pool size) and then takes the
next opponent of the pool in each negotiation. This is the rotation HANI2 used
before Latin squares (participants that already started with it, and studies
whose `schedule.json` leaves a slot's opponent open, keep it).

Example: 3 opponents A, B, C and 4 participants.

| Participant | Negotiation 1 | Negotiation 2 | Negotiation 3 |
|---|---|---|---|
| 0 | A | B | C |
| 1 | B | C | A |
| 2 | C | A | B |
| 3 | A | B | C |

**Rule.**

$$
o(i, k) = P\left[(i + k) \bmod n\right]
$$

**Advantages**

- Every opponent appears equally often in every position (a cyclic Latin square).
- Easy to explain and to check by hand.

**Disadvantages**

- No carry-over balance: B always follows A, so effects of the previous opponent
  are confounded with the opponent itself.

### Fixed order (`fixed_order`) {#opponents-fixed-order}

*Everyone meets the pool in the same order, the order of the pool.*

Every participant meets the opponents in **the order of the pool**: the first
negotiation is against the first opponent, the second against the second, and so
on (starting again after the last).

Example: 3 opponents A, B, C and 4 participants.

| Participant | Negotiation 1 | Negotiation 2 | Negotiation 3 |
|---|---|---|---|
| 0 | A | B | C |
| 1 | A | B | C |
| 2 | A | B | C |
| 3 | A | B | C |

**Rule.**

$$
o(i, k) = P\left[k \bmod n\right]
$$

**Advantages**

- Identical conditions for every participant; useful for pilots and demos.
- The order is chosen by whoever writes the pool.

**Disadvantages**

- Opponent and position are fully confounded: learning, fatigue or the
  previous opponent cannot be told apart from the opponent's own effect.

### External (schedule.json) (`external`) {#opponents-external}

*Only an outside system decides: the participant's schedule.json names each opponent.*

The opponent of each counted negotiation comes **only** from the participant's
`schedule.json` (written by an outside system into the participant's results
folder): the slot's `agent_class_name`. HANI2 does not schedule opponents itself.

Example `schedule.json`:

```json
{"version": 2, "negotiations": [
  {"slot": 0, "agent_class_name": "BoulwareTBNegotiator", "scenario_type": "Trade"},
  {"slot": 1, "agent_class_name": "ConcederTBNegotiator", "scenario_type": "Island"}
]}
```

**Rule.**

$$
o(i, k) = S_i[k].\mathtt{agent\_class\_name}
$$

where $S_i$ is participant $i$'s schedule.

**When the schedule is missing.** If there is no `schedule.json`, or the slot names
no opponent, HANI2 still has to start the negotiation: it uses the cyclic
rotation over the pool, logs an `ERROR` event (`scheduling_missing`) and writes
`external:missing` in the result row's `opponent_scheduling` column, so the gap is
visible to admins.

Whatever the method, a `schedule.json` that names an opponent always wins; the
column then says `external`.

**Advantages**

- The outside system has full control (its own design, quotas or matching).

**Disadvantages**

- Depends on the outside system writing a complete schedule before the
  participant arrives.

## Assistants

Default: `balanced`.

| Method | Summary |
|---|---|
| [`balanced`](#assistants-balanced) | Each human keeps one Assistant; a new human gets the one with the fewest humans so far. |
| [`random_fixed`](#assistants-random-fixed) | Each human keeps one Assistant drawn at random when they first arrive. |
| [`random_each`](#assistants-random-each) | Every negotiation draws a new Assistant at random (within-subjects). |
| [`round_robin`](#assistants-round-robin) | Human i keeps Assistant i modulo the pool size. |
| [`external`](#assistants-external) | Only an outside system decides: the participant's schedule.json names the Assistant. |

### Fixed per human, balanced (`balanced`) {#assistants-balanced}

*Each human keeps one Assistant; a new human gets the one with the fewest humans so far.*

Each human keeps **one Assistant for the whole study**. A new human gets the pool
member with **the fewest humans assigned so far** in the study, ties going to the
earlier member in pool order. Humans count once assigned, even if they drop out;
admins and playground guests are neither counted nor recorded.

Example: 3 Assistants A, B, C and 6 participants arriving one after another.

| Participant (in order of arrival) | Assistant (every negotiation) |
|---|---|
| 0 | A |
| 1 | B |
| 2 | C |
| 3 | A |
| 4 | B |
| 5 | C |

**Rule.** With $c_a$ the number of humans assigned to Assistant $a$ before human
$i$ arrives,

$$
a(i) = \operatorname*{arg\,min}_{a \in A} \; c_a
\quad \text{(ties: the earliest in pool order)}
$$

and $a(i)$ is kept for every negotiation of human $i$.

**Advantages**

- The groups stay within one human of each other at every moment, even with
  drop-outs and concurrent arrivals.
- Between-subjects comparison: each human sees one Assistant only.

**Disadvantages**

- The assignment depends on arrival order, so a time trend in who arrives
  (e.g. early versus late recruits) can line up with the pool order.

### Fixed per human, random (`random_fixed`) {#assistants-random-fixed}

*Each human keeps one Assistant drawn at random when they first arrive.*

Each human keeps **one Assistant for the whole study**, drawn **uniformly at
random** from the pool when they first arrive (seeded by the study and the human,
so it is reproducible).

Example (one possible draw): 3 Assistants A, B, C and 6 participants.

| Participant (in order of arrival) | Assistant (every negotiation) |
|---|---|
| 0 | C |
| 1 | A |
| 2 | A |
| 3 | C |
| 4 | C |
| 5 | B |

**Rule.**

$$
a(i) \sim \mathrm{Uniform}(A), \quad \text{drawn once and kept}
$$

**Advantages**

- Independent of arrival order (no time trend can line up with the pool).
- Between-subjects comparison: each human sees one Assistant only.

**Disadvantages**

- Group sizes can be unequal, noticeably so in small studies.

### Random each negotiation (`random_each`) {#assistants-random-each}

*Every negotiation draws a new Assistant at random (within-subjects).*

Every negotiation draws its Assistant **uniformly at random** from the pool, so a
human may work with several Assistants (a *within-subjects* design). The draw is
seeded by the study, the human and the negotiation, so a reload gives the same
Assistant. The Assistant is swapped between negotiations only.

Example (one possible draw): 3 Assistants A, B, C and 4 participants.

| Participant | Negotiation 1 | Negotiation 2 | Negotiation 3 |
|---|---|---|---|
| 0 | B | B | A |
| 1 | C | B | C |
| 2 | B | C | C |
| 3 | C | A | B |

**Rule.**

$$
a(i, k) \sim \mathrm{Uniform}(A), \quad \text{independently for each } (i, k)
$$

**Advantages**

- Each human can compare Assistants; fewer humans are needed per Assistant.

**Disadvantages**

- Carry-over: what one Assistant taught can help in the next negotiation.
- No balance in small samples; the human sees the Assistant change.

### Fixed per human, round robin (`round_robin`) {#assistants-round-robin}

*Human i keeps Assistant i modulo the pool size.*

Each human keeps **one Assistant for the whole study**: human $i$ (their index in
the study, in order of arrival) gets pool member $i \bmod m$.

Example: 3 Assistants A, B, C and 6 participants.

| Participant (in order of arrival) | Assistant (every negotiation) |
|---|---|
| 0 | A |
| 1 | B |
| 2 | C |
| 3 | A |
| 4 | B |
| 5 | C |

**Rule.**

$$
a(i) = A\left[i \bmod m\right], \quad m = |A|
$$

**Advantages**

- Predictable from the participant index alone (easy to audit or reproduce).

**Disadvantages**

- Drop-outs are not compensated: if the humans given B tend to leave, B ends
  with fewer completed humans (`balanced` fills the gap instead).

### External (schedule.json) (`external`) {#assistants-external}

*Only an outside system decides: the participant's schedule.json names the Assistant.*

The Assistant comes **only** from the participant's `schedule.json` (written by an
outside system): the slot's `assistant`, else the top-level `assistant`; a
practice round uses the top-level `assistant`, else the first slot's. An admin's
`?assistant=` and a test link's group file naming an Assistant still work as
usual.

Example `schedule.json`:

```json
{"version": 2, "assistant": "my_team.assistant:Coach",
 "negotiations": [{"slot": 0, "agent_class_name": "BoulwareTBNegotiator",
                   "assistant": "other_team.assistant:Helper"}]}
```

**Rule.**

$$
a(i, k) = S_i[k].\mathtt{assistant} \ \text{if given, else } S_i.\mathtt{assistant}
$$

**When the schedule is missing.** If no `schedule.json` names an Assistant, the
negotiation runs **without an Assistant** and the failure is shown like any
failing Assistant: an error notice, an `assistant_failed` event and the
`assistant_error` column. There is no silent fallback.

Whatever the method, a `schedule.json` that names an Assistant always wins; the
`assistant_scheduling` column then says `external`.

**Advantages**

- The outside system has full control (its own matching or quotas).

**Disadvantages**

- A participant without a schedule gets no Assistant.

## Scenarios

Default: `by_participant`.

| Method | Summary |
|---|---|
| [`by_participant`](#scenarios-by-participant) | Each participant keeps one scenario type: type = participant index mod number of types. |
| [`set_order`](#scenarios-set-order) | Negotiations follow the order of the scenario set, with a counter per participant. |
| [`random`](#scenarios-random) | Each negotiation draws a scenario type uniformly from the set. |
| [`latin_square`](#scenarios-latin-square) | Types are counter-balanced across negotiation slots with a balanced Latin square. |
| [`external`](#scenarios-external) | Only an outside system decides: the participant's schedule.json names each type. |

### By participant (`by_participant`) {#scenarios-by-participant}

*Each participant keeps one scenario type: type = participant index mod number of types.*

Each participant keeps **one scenario type** for all their negotiations; the
types are spread evenly over the participants of the study: participant $i$ gets
type $i \bmod t$. Within the type, successive negotiations use successive
scenarios of the pool. Outside a study the type comes from a hash of the
participant id.

Example: 3 types X, Y, Z and 4 participants.

| Participant | Negotiation 1 | Negotiation 2 | Negotiation 3 |
|---|---|---|---|
| 0 | X | X | X |
| 1 | Y | Y | Y |
| 2 | Z | Z | Z |
| 3 | X | X | X |

**Rule.**

$$
s(i, k) = T\left[i \bmod t\right], \quad t = |T|
$$

**Advantages**

- Each participant learns one kind of problem; no switching costs.
- Equal numbers of participants per type (up to one).

**Disadvantages**

- Type is a between-subjects factor: comparing types needs more participants.

### Set order (`set_order`) {#scenarios-set-order}

*Negotiations follow the order of the scenario set, with a counter per participant.*

Each participant goes through the types **in the order of the scenario set**,
one type per negotiation, starting again after the last. The position is the
participant's scenario counter, which counts every scenario loaded for them
(practice rounds included). This is what HANI2 does for logged-in users outside
participant studies.

Example: 3 types X, Y, Z and 4 participants (no practice round).

| Participant | Negotiation 1 | Negotiation 2 | Negotiation 3 |
|---|---|---|---|
| 0 | X | Y | Z |
| 1 | X | Y | Z |
| 2 | X | Y | Z |
| 3 | X | Y | Z |

**Rule.** With $c_{i,k}$ the participant's scenario counter at negotiation $k$,

$$
s(i, k) = T\left[c_{i,k} \bmod t\right]
$$

**Advantages**

- Every participant sees every type; the set's author controls the order.

**Disadvantages**

- Type and position are confounded (everybody meets X first).

### Random (`random`) {#scenarios-random}

*Each negotiation draws a scenario type uniformly from the set.*

Every negotiation draws its scenario type **uniformly at random** from the set
(seeded by the study, the participant and the negotiation, so a reload gives the
same type).

Example (one possible draw): 3 types X, Y, Z and 4 participants.

| Participant | Negotiation 1 | Negotiation 2 | Negotiation 3 |
|---|---|---|---|
| 0 | X | Y | Y |
| 1 | Z | Z | Y |
| 2 | Z | Y | X |
| 3 | Y | Y | Y |

**Rule.**

$$
s(i, k) \sim \mathrm{Uniform}(T), \quad \text{independently for each } (i, k)
$$

**Advantages**

- No structure that could interact with other factors.

**Disadvantages**

- No balance in small samples; a participant may see one type repeatedly.

### Balanced Latin square (`latin_square`) {#scenarios-latin-square}

*Types are counter-balanced across negotiation slots with a balanced Latin square.*

Each participant goes through the types in the order of one row of a **balanced
Latin square** (Williams design) over the types: every type appears equally often
in every slot, and every type follows every other type equally often.

Example: 3 types X, Y, Z and 4 participants.

| Participant | Negotiation 1 | Negotiation 2 | Negotiation 3 |
|---|---|---|---|
| 0 | X | Y | Z |
| 1 | Y | Z | X |
| 2 | Z | X | Y |
| 3 | Z | Y | X |

**Rule.** With $W$ the balanced Latin square over $t$ types ($R = t$ rows for even
$t$, $2t$ for odd $t$; see the opponents' Latin square for its construction),

$$
s(i, k) = T\left[\, W_{i \bmod R,\; k \bmod t} \,\right]
$$

**Advantages**

- Within-subjects comparison of types with position and carry-over balanced.

**Disadvantages**

- Exact balance needs a multiple of $R$ participants.
- Participants switch types every negotiation.

### External (schedule.json) (`external`) {#scenarios-external}

*Only an outside system decides: the participant's schedule.json names each type.*

The scenario type (and optionally the scenario index) of each counted negotiation
comes **only** from the participant's `schedule.json`: the slot's
`scenario_type` and `scenario_index`.

**Rule.**

$$
s(i, k) = S_i[k].\mathtt{scenario\_type}
$$

Practice rounds are not part of the schedule: they keep the participant's
`by_participant` type (recorded as `practice`).

**When the schedule is missing.** If no schedule names a type for the slot,
HANI2 uses the participant's type as `by_participant` would, logs an `ERROR`
event (`scheduling_missing`) and writes `external:missing` in the
`scenario_scheduling` column.

Whatever the method, a `schedule.json` that names a type always wins; the column
then says `external`.

**Advantages**

- The outside system has full control (e.g. scenarios matched to its quotas).

**Disadvantages**

- Depends on the outside system writing a complete schedule.

<!-- scheduling-methods:end -->

## Adding a method

Methods live in `hani2.scheduling`. A plugin can add one with `register`, which
puts it in the registry and so in the admin API, `hani2 scheduling list` and the
validation:

```python
from hani2 import scheduling

def reverse(items, index, slot, seed):
    """Everyone meets the pool backwards."""
    return items[-1 - slot % len(items)]

scheduling.register("opponents", "reverse", "Reverse order",
                    "Everyone meets the pool in reverse order.",
                    "Like `fixed_order`, backwards.\n\n**Advantages**\n\n- ...\n\n**Disadvantages**\n\n- ...",
                    rule=reverse)
```

Opponent and scenario rules get `(items, index, slot, seed)`; an Assistant rule gets
`(pool, index, counts, seed)` and returns the human's fixed Assistant (`counts` holds
the number of humans per pool member so far). `seed` identifies the study and the
human; use `scheduling.rng(seed, slot)` for reproducible random draws.
