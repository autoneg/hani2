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
  assistants: balanced      # random_fixed, round_robin, random_each, latin_square, cyclic,
                            # balanced_subset, random_subset, external
  scenarios: by_participant # set_order, random, latin_square, external
  cross: shift              # cross the Assistant with the opponent: shift (default) | none
  assistant_repeats: false  # may a person get one Assistant twice?
```

The two options `cross` and `assistant_repeats` are described in
[Options: crossing and repeats](#options-crossing-and-repeats).

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
  their own pool (an admin's `?opponents=`, `?group=`), the opponent picker and an
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
recorded as `external`. A slot (or a whole schedule) that leaves the opponent or the
Assistant open is filled by the study's own methods, crossed as described below, so
an outside system only needs to write what it must fix (for example the scenario
type). Participants who already started on HANI2's older rotation for open slots
(their results folder holds `fallback_rotation.txt`) keep it. The `external` method
means *only* such input is used; what happens when it is missing is described with
each `external` method below.

## Recorded in the results

Every result row says which method chose what, in three columns added after the
existing ones:

| Column | Values |
|---|---|
| `opponent_scheduling` | a method key; `external` when `schedule.json` named the opponent; `practice` for a practice round; `external:missing` when `external` found no input; `user` when the participant chose it; empty when HANI2 did not schedule the opponent |
| `assistant_scheduling` | a method key; `external` for an Assistant from `schedule.json`; `external:repeat` when `schedule.json` names an Assistant the participant already had (see [Assistant repeats](#assistant-repeats)); `user` when the participant chose it; empty for an admin's or a test link's explicit choice |
| `scenario_scheduling` | a method key; `external` / `external:missing` as above; `user` when the participant chose it; empty for an admin's choice or outside a study |

A participant may choose for themselves only where the admin allows it, and never in a Prolific
study (see [What participants may choose](configuration.md#what-participants-may-choose)). Their
choice holds for one negotiation and is not kept in `assignments.json`: the balancing counts are
not affected by it.

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
next opponent of the pool in each negotiation. (Before Latin squares, HANI2 used
a rotation like this one for every Prolific participant; participants who already
started with that old rotation keep it.)

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
| [`latin_square`](#assistants-latin-square) | Every human works with every Assistant, in an order from a balanced (Williams) Latin square (within-subjects). |
| [`cyclic`](#assistants-cyclic) | Human i starts with Assistant i and goes round the pool, one Assistant per negotiation (within-subjects). |
| [`balanced_subset`](#assistants-balanced-subset) | Each human gets K different Assistants of the N, chosen on arrival to balance totals, pairs and positions. |
| [`random_subset`](#assistants-random-subset) | Each human gets the first K of a random order of the N Assistants. |
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

### Balanced Latin square (each negotiation) (`latin_square`) {#assistants-latin-square}

*Every human works with every Assistant, in an order from a balanced (Williams) Latin square (within-subjects).*

Every human works with the Assistants of the pool **one after another**, one per
counted negotiation, in the order of one row of a **balanced Latin square** (a
Williams design), exactly as opponents are scheduled by the opponents'
`latin_square` method. Over a full set of rows every Assistant appears equally
often in every position and directly follows every other Assistant equally often,
so neither the position of an Assistant nor the Assistant just before it can
explain a result. This is the counterbalanced *within-subjects* design for
comparing finalists: with 5 Assistants and 5 counted negotiations, each human
works with each Assistant once.

Example: 3 Assistants A, B, C and 4 participants.

| Participant | Negotiation 1 | Negotiation 2 | Negotiation 3 |
|---|---|---|---|
| 0 | A | B | C |
| 1 | B | C | A |
| 2 | C | A | B |
| 3 | C | B | A |

**Rule.** Participant $i$ (their index in the study) takes row $i \bmod R$ of the
square $W$ (see the opponents' `latin_square`); $k$ counts the counted
negotiations (a practice round uses the Assistant of $k = 0$):

$$
a(i, k) = A\left[\, W_{i \bmod R,\; k \bmod m} \,\right], \quad m = |A|
$$

**Advantages**

- Balances position and carry-over effects; deterministic and reproducible.
- Each human compares the Assistants, so fewer humans are needed.

**Disadvantages**

- Exact balance needs a multiple of $R$ humans ($m$ or $2m$); drop-outs leave
  rows under-filled.
- What one Assistant taught can still help in the next negotiation (balanced,
  not removed).
- With $K < m$ negotiations, the first $K$ columns of a row are always the
  same neighbours in the square, so some pairs of Assistants are used together
  much more often than others; use `balanced_subset` for K-of-N designs.

**Crossing with the opponent.** When the opponents use `latin_square` (or
`cyclic`) too, the same rule would give Assistant $j$ the same opponent $j$ in
every negotiation, so their effects could not be told apart. With
`scheduling.cross: shift` (the default) the opponent sequence is shifted by a
block offset instead (see *Crossing Assistants with opponents* under the
scheduling options). With `cross: none` HANI2 warns about the confounding (a
`scheduling_confounded` event).

### Cyclic rotation (each negotiation) (`cyclic`) {#assistants-cyclic}

*Human i starts with Assistant i and goes round the pool, one Assistant per negotiation (within-subjects).*

Every human works with the Assistants **one after another**: human $i$ starts with
Assistant $i$ (modulo the pool size) and takes the next Assistant of the pool in
each counted negotiation. With $m$ Assistants, $m$ consecutive humans use every
Assistant in every position once (a cyclic Latin square). To randomise which
Assistant comes after which, shuffle the pool once when you set up the study.

Example: 3 Assistants A, B, C and 4 participants.

| Participant | Negotiation 1 | Negotiation 2 | Negotiation 3 |
|---|---|---|---|
| 0 | A | B | C |
| 1 | B | C | A |
| 2 | C | A | B |
| 3 | A | B | C |

**Rule.** With $k$ the counted negotiation (a practice round uses $k = 0$):

$$
a(i, k) = A\left[(i + k) \bmod m\right], \quad m = |A|
$$

**Advantages**

- Every Assistant in every position equally often after each block of $m$ humans.
- Simple to explain and to audit.

**Disadvantages**

- Carry-over is not balanced: each Assistant always follows the same one
  (`latin_square` balances it too).

Like `latin_square`, it is crossed with a `latin_square` or `cyclic` opponent
method when `scheduling.cross` is `shift` (see *Crossing Assistants with
opponents* under the scheduling options).

### Balanced subset (K of N, each negotiation) (`balanced_subset`) {#assistants-balanced-subset}

*Each human gets K different Assistants of the N, chosen on arrival to balance totals, pairs and positions.*

Each human works with **K different Assistants out of the N** of the pool, one per
counted negotiation ($K$ is `n_required`). The subset and its order are chosen
when the human first arrives, so that, over the humans so far:

1. every Assistant is used about equally often (totals within one of each other);
2. every **pair** of Assistants is used by the same human about equally often
   (*co-occurrence*), which matters for any within-person comparison
   (paired differences, Bradley–Terry);
3. every Assistant appears about equally often in every **position**.

The plan is kept in the study's `assignments.json`, so a reload, a reconnect or
a later visit continues the same plan. This is the method for **K-of-N
screening**; for $K = N$ (everyone uses every Assistant) use `latin_square`.

Example: 4 Assistants A, B, C, D, $K = 2$ negotiations, 6 participants arriving
one after another. Every pair of Assistants appears once.

| Participant (in order of arrival) | Negotiation 1 | Negotiation 2 |
|---|---|---|
| 0 | C | B |
| 1 | D | A |
| 2 | B | D |
| 3 | A | C |
| 4 | B | A |
| 5 | C | D |

**Rule.** With $c_a$ the number of humans who have Assistant $a$ in their plan,
$c_{ab}$ the number who have both $a$ and $b$, $c_{a,p}$ the number who have $a$
at position $p$, and (when the opponents are planned with it) $c_{a,o}$ the number
of negotiations of $a$ against opponent $o$, the new human $i$ gets the ordered
tuple

$$
(a_0, \dots, a_{K-1}) = \operatorname*{arg\,min}_{\text{distinct } a_p \in A}
\Big(\sum_p c_{a_p},\ \sum_{p<q} c_{a_p a_q},\ \sum_p c_{a_p,p},\ \sum_p c_{a_p, o(i,p)}\Big)
$$

in lexicographic order, ties broken by a random draw seeded by the study and
the human. Every ordered tuple is tried when $N \le 8$ and $K \le 5$; above that
the tuple is filled one position at a time with the same criteria. The last
criterion uses the human's own opponent sequence $o(i, p)$ (crossed as
described under the scheduling options), so Assistants and opponents are
planned together.

**Advantages**

- Each human sees each Assistant at most once, and the pairs of Assistants that
  meet in one person are balanced, which a prefix of a Latin square is not.
- Robust to drop-outs: each new human fills the gaps the earlier ones left.

**Disadvantages**

- Depends on arrival order and on the humans before (reproducible from the
  stored plans, not from the participant index alone).
- Carry-over (which Assistant follows which) is not balanced.
- $K \le N$ is required unless `assistant_repeats: true`.

### Random subset (K of N, each negotiation) (`random_subset`) {#assistants-random-subset}

*Each human gets the first K of a random order of the N Assistants.*

Each human works with **K different Assistants out of the N**, one per counted
negotiation: the first $K$ of a **random permutation** of the pool, seeded by the
study and the human (so it is reproducible and needs no shared state).

Example (one possible draw): 4 Assistants A, B, C, D, $K = 2$, 6 participants.

| Participant (in order of arrival) | Negotiation 1 | Negotiation 2 |
|---|---|---|
| 0 | A | B |
| 1 | C | B |
| 2 | A | D |
| 3 | C | B |
| 4 | C | B |
| 5 | C | B |

**Rule.** With $\pi_i$ a random permutation of $A$ seeded by the study and human $i$,

$$
a(i, k) = A\left[\pi_i(k)\right], \quad k = 0, \dots, K-1
$$

**Advantages**

- Simple and cheap; each human sees each Assistant at most once.
- Independent of arrival order.

**Disadvantages**

- Totals, positions and pairs are balanced only in expectation: small studies
  can be noticeably uneven (`balanced_subset` evens them out).

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

## Options: crossing and repeats

Two options sit next to the three methods in the same `scheduling` mapping, and
merge the same way (study over project, each on its own):

```yaml
scheduling:
  assistants: latin_square
  opponents: latin_square
  cross: shift              # shift (default) | none
  assistant_repeats: false  # default: false for the methods that use each Assistant at most once
```

### Crossing Assistants with opponents (`cross`) {#crossing}

When the Assistants change every negotiation (`latin_square`, `cyclic`,
`balanced_subset`, `random_subset`, `random_each`) and the opponents use
`latin_square` or `cyclic`, the two rules would otherwise line up: with 5
Assistants and 5 opponents both on `latin_square`, Assistant $j$ would meet
opponent $j$ in every negotiation, and the effect of an Assistant could not be
told apart from the effect of its opponent. With `cross: shift` (the default)
the opponent sequence of participant $i$ is their own Latin-square row, shifted
by a block offset:

$$
d(i) = \left\lfloor i / R \right\rfloor \bmod n_o, \qquad
o(i,k) = P_o\left[\,(W_{i \bmod R,\,k} + d(i)) \bmod n_o\,\right]
$$

where $W$ is the opponents' square (for `cyclic`, $W_{i,k} = i + k$), $R$ its
number of rows and $n_o$ the number of opponents. Within each block of $R$
participants the opponent is shifted by the same $d$; over $n_o$ blocks every
(Assistant, opponent) pair occurs equally often. A shift keeps every column a
Latin column, so the position and carry-over balance of the opponents is kept.
A full design is $R \cdot n_o$ participants: for 5 Assistants and 5 opponents
($R = 10$) that is 50 participants, each pair 10 times.

Example: 3 Assistants A, B, C and 3 opponents a, b, c, both on `latin_square`
($R = 6$): Assistant / opponent of each negotiation.

| Participant | Offset $d$ | Negotiation 1 | Negotiation 2 | Negotiation 3 |
|---|---|---|---|---|
| 0 | 0 | A / a | B / b | C / c |
| 1 | 0 | B / b | C / c | A / a |
| 2 | 0 | C / c | A / a | B / b |
| 3 | 0 | C / c | B / b | A / a |
| 4 | 0 | A / a | C / c | B / b |
| 5 | 0 | B / b | A / a | C / c |
| 6 | 1 | A / b | B / c | C / a |
| 7 | 1 | B / c | C / a | A / b |
| 8 | 1 | C / a | A / b | B / c |
| 9 | 1 | C / a | B / c | A / b |
| 10 | 1 | A / b | C / a | B / c |
| 11 | 1 | B / c | A / b | C / a |

- With `assistants: balanced_subset`, the opponents keep this crossed sequence
  and the Assistant plan takes it into account (its 4th criterion).
- With `scenarios: latin_square`, the scenario type gets its own offset
  $d_s(i) = \lfloor i / (R \cdot n_o) \rfloor \bmod n_s$ (or
  $\lfloor i / R_s \rfloor \bmod n_s$ when the opponents are not crossed), so the
  type is confounded with neither.
- The counts are equal only when both pools have the same size; otherwise they
  stay within one of each other over blocks of the least common multiple.
  `random_*` methods are balanced in expectation only. `hani2 study balance`
  shows the real counts.
- **Each human keeps the rule they started with.** It is stored for them in the
  study's `assignments.json` the first time they are seen, so changing `cross`
  in a running study changes nothing for people already in it. People who
  joined a study before crossing existed keep `none`.
- `cross: none` turns it off; HANI2 then warns when the Assistant and the
  opponent are confounded (a `scheduling_confounded` event).

### Assistant repeats (`assistant_repeats`) {#assistant-repeats}

`latin_square`, `cyclic`, `balanced_subset`, `random_subset` and `external`
promise that a human gets **each Assistant at most once**. That is possible only
when the counted negotiations per person ($K$, `n_required`) are at most the
Assistants of the pool ($N$): the pool a session would use (`assistants` of the
study, else of the project, else the one Assistant of `assistant_settings.json`).
With `assistant_repeats` unset (or `false`), a study or project file where
$K > N$ is **refused on save** ("n_required = 6 negotiations but only 5
Assistants"), and so is a project change that would give one of its studies
$K > N$; a study already running with such a file only gets a
warning in the log, in `hani2 study show` and in `hani2 study balance`, and the
Assistants wrap around. With `assistant_repeats: true` the Assistants wrap around
on purpose.

`random_each` can repeat an Assistant by nature: it is allowed unless
`assistant_repeats: false` is set explicitly, which refuses it. For `external`,
a `schedule.json` that names one Assistant in two slots is used as written, and
flagged: an `ERROR` event (`scheduling_repeat`) and `external:repeat` in the
`assistant_scheduling` column.

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
