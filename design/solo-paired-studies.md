# Design note: Solo and Paired studies, fair assignment, HAN opponents in HI, the game leaderboard

Status: **decisions settled, nothing built yet** (2026-11-26). The next step is WP0. This note is internal and is not in the
MkDocs nav (it lives outside `docs/`). It should not be published as written. Each work package
writes its user docs into the Project Management and Study Management pages (§11).

Terms: the three parties are the **human** ("participant" in a study), the **Assistant** and the
**opponent**. *HI* is the Hybrid Intelligence track, and its entrants are Assistants. *HAN* is the
Human-Agent Negotiation track, and its entrants are opponent agents. A project's `kind` is
`assistant` (HI), `opponent` (HAN) or `none` (for example the game).

---

## 1. What exists today (the starting point)

Code facts this design builds on, each checked in the code:

| Area | Where | What it does today |
|---|---|---|
| Scheduling | `scheduling.py`, `assignment.py`, `docs/guide/scheduling.md` | Three dimensions (`opponents`, `assistants`, `scenarios`), each with a method per study, falling back to the project's and then the default. The Assistant methods are `balanced`, `random_fixed` and `round_robin` (one Assistant per human) and `latin_square`, `cyclic` and `random_each` (a new one each negotiation), plus `external`. Participant index $i$, counted slot $k$. State is kept in `<study results>/assignments.json`. |
| Pairing | `matches.py` (`Lobby`, `Match`), `session.py` ≈1655–1765 | The pool entries `human` and `human+assistant`. The joiner takes the host's scenario and the free side. The lobby key is `project:<p>` or `code:<c>`. **The joiner picks a waiting host with `random.choice`**. `refresh_assistant(plan)` runs **before** `LOBBY.pair`, so both sides' Assistants are fixed before anyone is paired. Other settings: `human_opponents_first`, `human_opponent_choice`, `human_opponent_wait/fallback/absent`, `"ai_fallback": false` in group files. |
| Results | `results.py` `save_result` | `opponent_kind`, `match_id`, `opponent_user` (a **user name**), `abandoned`, `invited_by`, the attribution columns (`assistant`, `assistant_group`, …, `opponent_group`) and the scheduling columns. **`mode` is already taken**: it is `simulated` for simulated participants (`PARTICIPANT_COLUMNS`, `tracks._filter`), so the new setting cannot be called `mode`. In `results.csv`, `support_agent` is a bool ("was used"). In evaluation rows (`evaluation/__init__.py`, built from recordings) it is the Assistant's name. |
| Tracks | `evaluation/tracks.py` | A row belongs to `hi` if it has an Assistant and to `han` otherwise. **So an HI session against a HAN agent gives that agent nothing.** HI cells are scenario × opponent, HAN cells are scenario. The 95 % bootstrap resamples participants and falls back to sessions when there is only one participant. |
| Scores | `evaluation/scores.py` | `hi_outcome` (= `human_advantage`), `hi_assistant`, `hi_team`, `hi_interaction`, `han_outcome`, `han_interaction`. They are weighted means of normalised components, with weights overridable in `env.json` under `evaluation.scores.<score>.weights`. |
| Leaderboards | `results.py` `leaderboard` (per *user*, by utility), `simulated_leaderboard`; `POST /api/replay/leaderboard` (admin, per track) | There is no per-Assistant board for the game and no endpoint an outside system can call. |
| HAN groups | `agents.py` `han_groups()` | `:han<year>-all/-qualified/-finalists/-winners`, for every year that the installed `han-agents` package covers (only 2026 today). There is no source for the current year's submitted zips yet (§3.4). |
| Auth | `server.py`, `sso.py` | Only cookie auth (`require_user` / `require_admin`) and the HS256 sign-in hand-off secret shared with scmlweb. **No service-to-service auth exists.** |
| Group files | `groups.py` | Opponent group files take `agents`, `assistant` (old name `support_agent`), `syspath`, `description` and `ai_fallback`. `load_file` ignores any other key, and `validate_data` (the admin `PUT`) **drops other keys from what it saves**, with no message. New keys must be added to `load_file`, `validate_data`, `Group` and `to_dict`. |
| Editor | `frontend/src/admin/schema.tsx` (`Field`), `Row.tsx`, `pages/Projects.tsx` | `Field` has `hint` (a one-line grey text) and **no `help`**. `Projects.tsx` builds most rows with a bare `<Row hint=…>`, not with `Field`. The only `?` today is `ToolHelp` in `negotiate/ToolPane.tsx` (a `CircleHelp` button with a portalled dialog). Scheduling methods already bring their Markdown `details` from the server (`GET /api/admin/scheduling-methods`). |

Two problems in today's code matter for fairness and are fixed below:

- **P1: Assistant and opponent are confounded.** `pick_assistant_slot("latin_square")` and
  `pick_opponent("latin_square")` both return `pool[latin_index(n, i, k)]`. Take a study with 5
  finalist Assistants and 5 HAN finalists, both on `latin_square`: Assistant $j$ meets opponent $j$
  in every single negotiation. Assistant and opponent effects then cannot be separated (§3.3).
  Both paths use the same index and slot: `study._pick_opponent` passes `participant_index()` and
  `counted()`, and `assignment._assistant_slot` returns `counted()` too. `scenarios: latin_square`
  takes the same row as well. This happens **only when hani2 schedules both dimensions itself**.
  A Prolific participant with a non-empty `schedule.json` gets the old rotation for the opponent and
  the slot's Assistant as given (§3.5).
- **P2: random pairing.** The lobby's `random.choice` cannot balance anything (§4).

---

## 2. Solo and Paired: a named setting over `opponents`

### 2.1 The modes

| Mode | Meaning | HI (`kind: assistant`) | HAN (`kind: opponent`) |
|---|---|---|---|
| **Solo** | One person per negotiation, against an AI opponent | The human has an Assistant, and the opponent is an agent (built-in, PAN, or HAN entrants) | Today's mode: a human without an Assistant against the entrant agents |
| **Paired** | Two people negotiate with each other | Each has their own Assistant (`human+assistant` on both sides) | Two people without Assistants (`human`). **It tests no HAN agent**: it exists for completeness, and its rows are not ranked |
| **Mixed** | Whatever the pool draws: people when someone fits, otherwise AI | The game | Only for completeness |

### 2.2 Keys

A new study default key, **`study_mode`**, takes `solo`, `paired` or `mixed`. It is added to
`projects.DEFAULT_KEYS`, so it can be set in `project.yaml` (top level or `defaults:`) and
overridden in `study.yaml`. When it is unset, the mode is **derived** from `opponents`:
no human entry means `solo`, only human entries means `paired`, both means `mixed`. Old projects
therefore keep working unchanged, and the editor shows the derived value as "(derived)".

`study_mode` does not replace `opponents`. `opponents` stays the one mechanism that decides who
plays. `study_mode` is a declared intent that HANI2 **checks** against `opponents`, and it chooses
which assignment options apply (§3, §4). The two cannot contradict each other, because a file in
which they disagree is refused:

| `study_mode` | `opponents` must be | Assistant | When `opponents` is missing |
|---|---|---|---|
| `solo` | no `human` / `human+assistant` entry | any (HI: not `none` only) | the default pool, as today |
| `paired`, project `kind: assistant` | exactly `[human+assistant]` | required, not `none` | HANI2 fills in `[human+assistant]` |
| `paired`, project `kind: opponent` | exactly `[human]` | `none` | HANI2 fills in `[human]` and `assistants: [none]` |
| `paired`, project `kind: none` | human entries only | either | taken from `assistants` |
| `mixed` | at least one human and one AI entry | any | refused (name the pool) |

Where each check runs:

- **On save** (`projects.file_problems` → `hani2 study create`, the admin `PUT`): a disagreement is
  a 400 error that names both keys and the allowed pool.
- **When a hand-edited file is loaded**: the problem goes to the server log, to `hani2 study show`
  and to the study's `errors` list, and **`opponents` wins**, the same rule as for unknown
  scheduling names. The recorded `study_mode` is then the derived one, with
  `study_mode_error: true` in the events.
- **Group files and `schedule.json` slots** that bring their own `agents` or `agent_class_name`
  are checked per session. In a `paired` study, a group file that lists AI agents loses them (with
  a warning, the same mechanism as `ai_fallback: false`). In a `solo` study, a human entry from a
  group file or a slot is refused, and the session uses the study's pool. An admin's `?opponents=`
  is never checked (it is a test link).

Pairing options get their own block. It is read only when the mode is `paired` or `mixed`, and the
editor hides it otherwise:

```yaml
pairing:
  scope: study            # study | project | code   (where people meet; §4.6)
  assign: cells           # cells | order | random   (how a match is formed; §4.2)
  slack: 1                # cells within this count of the emptiest are tied (§4.2)
  cell_scenario: type     # type | name: what "scenario" means in a cell (§4.1)
  allow_same_assistant: false   # may both sides use the same Assistant? (§4.4)
  fallback: ai            # ai | wait | end          (when nobody fits in human_opponent_wait s; §4.5)
  fallback_opponents: null      # the AI pool of the fallback (default: the study's non-human pool, else :pan)
```

`pairing` is added to `DEFAULT_KEYS` as one nested key that merges key by key, the same way
`scheduling` merges per dimension. The existing `human_opponent_*` settings stay as they are.
`fallback: wait` is the same as `human_opponent_fallback: false`. When both are given and disagree,
the file is refused.

---

## 3. Assignment in Solo

### 3.1 What is asked

Each person plays **K** counted sessions (`n_required`) over **N ≥ K** Assistants. Each Assistant
is used **at most once per person**, and positions and orders are balanced. "Every Assistant once"
is the case K = N (the finals). The method is chosen per project and can be overridden per study.
This is the existing `scheduling.assistants` key, so no new mechanism is needed.

### 3.2 Methods: existing and new

| Method | Per person | Each at most once | Balance | Status |
|---|---|---|---|---|
| `balanced`, `random_fixed`, `round_robin` | one Assistant for all K | no (K > 1 repeats it) | number of people per Assistant | exists (between-subjects designs) |
| `latin_square` | row $i \bmod R$ of a Williams square over the N; slots $0..K-1$ | **yes, when K ≤ N** (a row is a permutation) | position: column $k$ of a Latin square holds every Assistant once per $n$ rows. Carry-over: exact only for K = N. Each Assistant is used $K\cdot R/N$ times per $R$ people | exists; **add the K ≤ N check** |
| `cyclic` | $(i+k) \bmod N$ | yes when K ≤ N | position; consecutive windows only | exists; add the check |
| `random_each` | an independent draw for each $k$ | **no** | none | exists; refused when `assistant_repeats: false` |
| **`balanced_subset`** (new) | a K-subset and its order, chosen greedily on arrival | yes | totals per Assistant (±1); counts per (Assistant, position) (±1 when greedy succeeds); **pair co-occurrence** (how often two Assistants are used by the same person) as even as the greedy allows | new: the method for K < N when within-person comparisons matter |
| `random_subset` (new) | a seeded random permutation, first K | yes | in expectation only | new, cheap and reproducible |
| `external` | `schedule.json` slots | as given; validated: a repeat is an `external:repeat` error | as given | exists; add the check |

`latin_square` with K = N is already the agreed final-evaluation design: each participant uses every
finalist once, with a Latin-square rotation. It needs no new method, only the K ≤ N check and the
crossing in §3.3.

Why `balanced_subset` is needed: with K < N, the first K columns of a Williams row are always the
"prefixes" of the square. Assistants that sit next to each other in the square's first row are then
used together by the same person much more often than others. That biases any within-person
comparison (Bradley–Terry, paired differences). The greedy rule runs on a new person's arrival and
is persisted in `assignments.json` (`humans[u].assistant_plan = [a_0..a_{K-1}]`). It picks the
ordered K-tuple that minimises, in lexicographic order:

1. the sum, over the tuple, of the Assistants' total counts;
2. the sum of the pair co-occurrence counts for the pairs in the tuple;
3. the sum of the (Assistant, position) counts;

with ties broken by the seeded RNG of `(study, user)`. For N ≤ 8 and K ≤ 5, enumerating all ordered
tuples ($8\cdot7\cdot6\cdot5\cdot4 = 6720$) is cheap. Above that, it runs as a greedy fill, one
position at a time.

New key **`scheduling.assistant_repeats`** (default `false` for the per-negotiation methods): with
`false`, a study where `n_required > N` for a method that promises "at most once" is refused on save
("K = 6 negotiations but only 5 Assistants"). With `true`, the Assistants wrap around as today. A
running study whose file already breaks the rule gets a warning, not a refusal.

### 3.3 Crossing the Assistant with the opponent (fixes P1)

When both `assistants` and `opponents` use a per-negotiation method, HANI2 **crosses** them: the
opponent sequence is the participant's own opponent sequence, shifted by a block offset:

$$
d(i) = \lfloor i / R \rfloor \bmod n_o, \qquad o(i,k) = P_o\big[(\,W_{i \bmod R,\,k} + d(i)) \bmod n_o\big]
$$

where $W$ is the opponents' Williams square and $R$ its number of rows. Within each block of $R$
participants, the opponent is the Assistant's index shifted by $d$. Over $n_o$ blocks, every
(Assistant, opponent) pair occurs equally often. A shift is a bijection, so each column is still a
Latin column and carry-over balance survives. A full design is $R\cdot n_o$ participants: for
5 × 5 that is 50, which matches the agreed plan of "5 participants × 10 repetitions". When the
pools differ in size, the shift is taken mod $n_o$ and the crossing is exact only over
$\mathrm{lcm}$-sized blocks. The `hani2 study balance` report (WP2) shows how far coverage got.

**Scope of this guarantee.** The equal-count argument holds when **both** dimensions use
`latin_square` (or `cyclic`) and the two pools have the same size. Other combinations work as
follows:

- `assistants: balanced_subset` with a per-negotiation `opponents` method: the opponents are
  planned **together** with the Assistants. The greedy rule of §3.2 gets a 4th criterion, the
  (Assistant, opponent) pair counts, and the plan stores both sequences. This is still an
  enumeration over K-tuples, with the opponent sequence fixed by the crossed square, so the cost
  stays small.
- `random_*` methods: balance holds in expectation only. The `balance` report shows the real
  counts.
- `scenarios: latin_square` gets its own block offset, $d_s(i) = \lfloor i / (R\cdot n_o)\rfloor
  \bmod n_s$, so that scenario type is not confounded with either of them.
- With different pool sizes, the counts stay within ±1 only over $\mathrm{lcm}$-sized blocks.

The key is **`scheduling.cross: shift | none`**. It defaults to `shift` for studies created after
WP2. A human's crossing rule is stored at first sight (`humans[u].cross`), so a study already
running never changes plan for people already in it. *(Decision D3.)*

### 3.4 Solo HI against HAN agents (one study, both tracks)

The opponent pool of an HI Solo study can name HAN entrants. The keys already exist:
`opponents: [":han2026-finalists"]`, or several years, such as
`[":han2026-finalists", ":han2027-finalists"]`.

- **The year is always stored explicitly** as the group key. In the editor, "this year" and
  "last year" are only labels, computed from the **project's `year` field, not from the clock**.
  For a project with `year: 2027`, "last year" writes `:han2026-…`. A year not covered by
  either source is shown greyed out ("no agents for 2025": `han-agents` covers the past years,
  and the submissions index covers `han.current_year`). On save it is refused with the same
  message, and when a hand-edited file is loaded it is reported (the group expands to nothing,
  and the study falls back as today).
- **Where the agents of a year come from: the current year comes from the submitted zips, every
  other year from `han-agents`** (decided). The current year is an explicit setting, never the
  clock: `env.json` → `han.current_year: 2027`. The rule:
  - `:han<current_year>-<set>` resolves from the **submissions index** of that year;
  - `:han<other year>-<set>` resolves from the installed `han-agents` package (`han_groups()`), as
    today;
  - a year that neither source covers is an error, refused on save and reported on load;
  - when a year's agents have been packaged into `han-agents` and the competition moves on, an
    admin raises `han.current_year`. From then on that year comes from the package. Studies
    already run keep their recorded source (below).
- **The submissions index** (*its format is to confirm with scmlweb*). `han.submissions` in
  `env.json` names a folder per year, such as `{"2027": {"dir": "~/anac/_agents_han/2027"}}`.
  The folder holds the zips and an `index.json` that scmlweb writes from `agent_placements`, one
  entry per submission:
  `{"entrant": "sub_0981", "team": "t17", "zip": "t17.zip", "class": "t17_agent.agent:MyNegotiator",
  "qualified": true, "finalist": false, "winner": false}`.
  - `hani2 han import --year 2027` unpacks each zip into
    `<data>/han_submissions/2027/<entrant>/<sha256 of the zip>/`. Untrusted archives get their own
    empty folder, and nothing in them is run while unpacking. It also checks that the class
    imports.
  - The sets `all`, `qualified`, `finalists` and `winners` come from the index flags, so they
    follow scmlweb's placements.
  - A new upload (a new hash) is a new folder. Each game records which one it used, so an agent
    can be updated without changing what past games mean.
  - `hani2 han check --year <y>` lists the entries, their sets and whether each imports. It reports
    entries whose class does not import and zips that the index does not list.
- **What every game records:** `opponent_han_year` (below), `opponent_han_source`
  (`submissions` or `han-agents`) and `opponent_han_version` (the zip hash, or the `han-agents`
  version). Boards can therefore always tell which build of an agent was played.
- In a game invitation, scmlweb may still write a group file that lists unpacked agents with
  `syspath` and `han_year` (§9.3). The submissions index is the normal path.
- New result column **`opponent_han_year`** (an int, or empty), filled when the opponent came from
  a `:han<year>-*` group. `opponent_group` already keeps the group key.

### 3.5 Prolific with scmlweb's `schedule.json`: who owns the plan

Today, when a Prolific participant's `schedule.json` has any slot, `ProlificStudy.plan_round`
handles the opponent with the old `fallback_rotation` (the `elif not method or sched or legacy`
branch), and a slot's `assistant` is used as given. scmlweb writes such a schedule per PID, so
**none of §3.2–§3.3 would run for those participants**. There are two ways out *(D14)*:

- **hani2 owns the plan (recommended).** scmlweb writes a schedule that gives only what it must
  (for example `scenario_type`), or no schedule at all, and leaves `assistant` and
  `agent_class_name` empty. WP2 changes the branch above so that open slots use the study's methods
  and crossing instead of the old rotation. The old rotation stays only for participants who
  already have `fallback_rotation.txt`.
- **scmlweb owns the plan.** scmlweb implements the same K-of-N and crossing rules and writes them
  as complete slots. hani2 then only validates them (no repeats, K ≤ N: `external:repeat`).

---

## 4. Assignment in Paired: the match is the unit

### 4.1 Cells

In Paired, fairness is decided **when two people are paired**, over **match cells**:

$$
\text{cell} = (\text{scenario},\ \text{Assistant at side 0},\ \text{Assistant at side 1})
$$

This is one canonical key per match, `"<scenario>|<A>@0|<B>@1"`. By default, *scenario* is the
**scenario type** (the domain), and the scenario instance (which predefined utility functions were
used) is recorded but not balanced. Balancing instances too, with `pairing.cell_scenario: name`,
multiplies the number of cells by the instances per type. With 5 utility functions per domain, the
60 cells below would become 300. *(D16)* From each participant's own row,
the cell reads as (own Assistant, opposing Assistant, scenario, own side). One match therefore fills
the two mirrored row-views at once, and is counted **once**. In HAN Paired (no Assistants), the cell
is just (scenario, side).

Size: with N Assistants, S scenarios and no same-Assistant matches, there are $S\cdot N(N-1)$ cells.
For N = 5 and S = 3 that is 60 cells. With K = 5 matches per person and two people per match,
50 participants give 125 matches, about 2 per cell.

**Persisted** in `<study results>/match_cells.json`, under the same file and thread locks as
`assignments.json`, written atomically:

```json
{"version": 1,
 "cells":    {"pizza|teamA.Helper@0|teamB.Coach@1": {"completed": 2, "match_ids": ["m-…", "m-…"]}},
 "inflight": {"m-7f3": {"cell": "pizza|teamA.Helper@0|teamC.Pal@1", "since": "2026-…"}},
 "positions": {"teamA.Helper": [3, 2, 4, 1, 2]}}
```

- **Only completed matches fill a cell.** A match is completed when both rows were written with no
  `abandoned` and a status that is not `erred` (a deal, or no deal reached in time or by a refusal,
  all count). An abandoned match, one whose partners were separated before the start, or one that
  erred releases its in-flight entry and fills nothing.
- **Fallbacks never fill a cell**, because an AI game is not a match.
- In-flight matches count when a match is chosen (completed + in-flight), so two concurrent joiners
  do not both pick the emptiest cell. An in-flight entry older than `time_limit` + 10 min is
  dropped when the file is next read.
- **Per-person use is kept in `assignments.json`** (`humans[u].used_assistants`, as a list of
  `[assistant, match_id]`). For a person, an Assistant counts as **used once the negotiation has
  started** (both pressed Start), even if the match is later abandoned: they have seen it, and
  "at most once" is about exposure. The cell, however, counts only completed matches.

### 4.2 How a match is formed (`pairing.assign`)

| `pairing.assign` | Rule | Use |
|---|---|---|
| **`cells`** (default for `paired`) | The cell-aware choice below | Evaluation studies, the HI game |
| `order` | Each person follows their planned order strictly. Two people fit only when their next planned Assistants form an allowed pair | Small, scripted lab sessions; thins the pool a lot |
| `random` | Today's `random.choice` among people who fit | Back-compatible; today's game |

**The Assistant method gives each person a set, not a slot.** In Paired, the study's
`scheduling.assistants` decides each person's **remaining set** $R_u$ and a preferred order:

- `balanced` / `random_fixed` / `round_robin`: $R_u$ is the person's one fixed Assistant, used for
  every match. This is the game, where a person always plays their own Assistant.
- `latin_square` / `cyclic` / `balanced_subset` / `random_subset`: $R_u$ is the first K of the
  person's sequence, minus the used ones. The order is a preference, not a promise.
- `random_each`: $R_u$ is all N, with repeats.
- `external`: $R_u$ is the set of Assistants in the person's `schedule.json` slots (their order is
  a preference).

**Host and joiner.** This respects how pairing works today: `refresh_assistant` runs before
`LOBBY.pair`, and the host waits with its Assistant already live.

1. **The host commits.** A person who finds nobody to join becomes a host. They commit **one**
   Assistant $h \in R_H$, the one that minimises (completed + in-flight cells containing $h$ for
   the chosen scenario, $h$'s count at the host's position $k$, the preferred order). The scenario
   is chosen by the scenario rule in §4.3, and the side by `role_rule`, as today. The host's
   Assistant is then fixed and live while they wait, as today.
2. **The joiner chooses, and binds late.** A joiner $J$ looks at every waiting host that fits
   (same scope, scenario type allowed, not just separated). For each such host and each
   $a \in R_J$ with $a \neq h$ (unless `allow_same_assistant`), it computes the cell and the score

   $$
   \big(\,c(\text{cell}),\ \text{pos}_a(k_J),\ |R_H|,\ |R_J|,\ \text{rng}\,\big)
   $$

   where $c$ is completed + in-flight. It takes the lowest score in lexicographic order. The
   $|R_H|$ term prefers the most constrained host, which avoids dead ends at the end of a study.
   `random` pairing today has a useful property: nobody can aim at a particular person. To keep it,
   every candidate whose $c$ is within `pairing.slack` (default 1) of the minimum is treated as
   tied on $c$. The remaining terms break the tie, and finally the RNG does. With `slack: 0` the
   choice is the strictest balance, but who meets whom becomes easier to predict.
   **This is a change**: in `paired` HI studies, the joiner's `refresh_assistant` moves to *after*
   `LOBBY.pair`. Fitting does not depend on it, because every side has an Assistant. Only then is
   the joiner's Assistant built. In `mixed` studies (the game) the order stays as it is.
3. The chosen cell is put in flight, `used_assistants` is updated at the start, and the cell is
   completed when the match ends (§4.1).

### 4.3 Scenarios in Paired

The joiner takes the host's scenario, as today. The scenario is therefore a **match-level**
decision, and the joiner's own scenario plan is ignored (recorded as `scenario_scheduling: host`):

- `scenarios: by_participant` (one domain per person, as in the agreed plan): a joiner **fits only
  hosts of their own type**. This is a hard filter, and it divides the pool waiting for each person
  by S.
- Any other scenario method: the host chooses the scenario type that has the fewest completed +
  in-flight matches for its committed Assistant, ties going to the method's own pick.

### 4.4 Same-Assistant matches

`pairing.allow_same_assistant` is **`false` by default** in `paired` studies. A match of A against A
says nothing about A compared with the others: the two utilities split one deal between copies of
the same Assistant. It is **`true` in the game**, where an invited guest plays with the inviter's
Assistant, so the inviter and the guest necessarily share one. How such matches are scored:
§6.2 and §8.1.

### 4.5 What can and cannot be guaranteed

| Guarantee | Paired | Why |
|---|---|---|
| Each Assistant at most once per person | **Hard** | The joiner chooses only from $R_J$, and the host commits only from $R_H$ |
| No same-Assistant match (when disallowed) | **Hard** | A filter at pairing |
| A match fills at most one cell, and only when completed | **Hard** | §4.1 |
| Totals per Assistant within ±1 | Best effort | Depends on who is waiting at the same moment |
| Cell balance | Best effort, greedy | The same reason |
| Position balance | Best effort | The joiner's pick depends on whom it meets |
| Order and carry-over balance (Williams) | **Not guaranteed** | Pairing reorders each person's set |
| Every person completes all K with people | **Not guaranteed** | Arrivals; the last person waiting can be left without a partner |

**When nobody fits.** The typical case is a person whose $R_u = \{a\}$ when every waiting person
also has only $a$ left. After `human_opponent_wait` seconds, `pairing.fallback` applies:

- **`ai`** (default): the person plays their committed Assistant against an AI opponent from
  `pairing.fallback_opponents`. The Assistant is now **used** for them, because the person spent the
  time and we pay for it. The row has `study_mode = paired`, `opponent_kind = agent` and
  `pairing = fallback`. It fills no cell and is ranked only in the Solo stratum (§6). *(D5)*
- **`wait`**: keep waiting, the same as `human_opponent_fallback: false`. Only for supervised lab
  sessions.
- **`end`**: the slot is skipped. The person moves on to their next Assistant, or finishes early
  with the completion code, and the Assistant is not used.

`hani2 study balance <project>/<study>` (WP3) prints the cell counts, totals, positions and
co-occurrence, the number of fallbacks, and the people who could not complete. The same report is
shown on the study page.

**The finals are not weakened.** The agreed final evaluation (every finalist once, Latin-square
rotation, no human-human) is a `solo` study with `assistants: latin_square`, K = N, and
`cross: shift` against `:han2026-finalists` or `:pan`. Paired is an extra option for other studies
and never changes a Solo study.

### 4.6 Where people meet (`pairing.scope`)

Cell counts belong to one study, so a `paired` study with `assign: cells` pairs **within the study**
by default (lobby key `study:<p>/<s>`, a new value in `matches.match_key`). `scope: project` keeps
today's project-wide lobby, which the game uses. `?match=<code>` still wins when
`human_opponent_codes` allows it. When people from two studies meet, each match is counted in the
host's study and marked `cross_study` in both rows.

---

## 5. New result columns

They are added after the existing ones in `results.csv`, in the evaluation rows (`ID_FIELDS` in
`evaluation/__init__.py`), and in the `scenario_started` event:

| Column | Values | Notes |
|---|---|---|
| `study_mode` | `solo`, `paired`, `mixed` | The **planned** mode. It is not `mode`, which is already `simulated` |
| `opponent_kind` | exists: `agent`, `human`, `human+assistant` | What actually happened (an AI fallback in a Paired study shows here) |
| `pairing` | `cells`, `order`, `random`, `fallback`, `code`, empty | How the match was formed. Empty for Solo |
| `match_id` | exists | Shared by both rows |
| `match_cell` | `"<scenario>|<A>@0|<B>@1"`, empty | The canonical cell, the same in both rows |
| `side` | 0 or 1: the human's ufun index (`ss["human_index"]`) | `save_result` uses it but does not write it as a column today |
| `opponent_assistant` | the other side's Assistant spec, `none`, or empty for AI | |
| `opponent_assistant_entrant` | the other side's `assistant_entrant` | |
| `opponent_participant` | the other side's **participant index** in its study | Pseudonymous; the leaderboard endpoint never uses `opponent_user` |
| `assistant_entrant` | an id from the group file's `entrant` (scmlweb's submission or team id), else empty | Lets scmlweb map entries without parsing specs |
| `own_assistant` | `true` / `false` / empty | From the group file's `own` key: the participant plays their own team's Assistant |
| `assistant_position` | $k$: the position of this Assistant in the person's plan | For position balance |
| `plan_size` | K | |
| `opponent_han_year` | int or empty | §3.4 |
| `cross_study` | bool | §4.6 |

The cell store (§4.1) records whether a match filled its cell. No row column records it, because
the second row is written after the first.

---

## 6. HI and HAN evaluation with Paired rows

### 6.1 HI board (`tracks.leaderboard(rows, "hi", …)`)

- **Two rows per match, one per Assistant.** Each row is an observation for **its own** Assistant
  (`entrant_of` stays as it is). For Paired rows, the cell is
  (scenario, side, opposing Assistant entrant). For Solo rows it is (scenario, opponent), as today.
  `TRACKS["hi"]["cells"]` becomes a function of the row.
- **Each match counted once.** An Assistant appears in a match once, so its own mean already counts
  every match once. Board-wide totals (`sessions`, agreement rate, welfare) **deduplicate by
  `match_id`**. Same-Assistant matches collapse into **one** observation for that Assistant (the
  mean of the two rows).
- **Bootstrap by participant**, as today: a match's two rows belong to two participants, who are
  resampled independently. This slightly understates the dependence between them.
  `ci_unit: match` (resampling matches as clusters) is added as a sensitivity option and shown in
  the board's notes.
- **Strata.** The boards are shown per `study_mode` stratum (`solo`, `paired`) and combined. The
  combined board is the cell-balanced mean over all cells, which works because cells include the
  opponent kind. Fallback rows (`pairing = fallback`) go to the Solo stratum.
- **Head-to-head** (optional, WP4): from Paired matches, the within-match difference in
  `human_advantage` between the two Assistants gives direct comparisons. A Bradley–Terry ranking is
  shown beside the board, not instead of it.

### 6.2 HAN board

- HAN rows of Paired studies (`human` against `human`) **have no entrant**. They are excluded and
  counted under `excluded["human opponent"]`.
- **Cross-track (HI Solo against HAN agents).** These rows have an Assistant **and** a HAN entrant
  as the opponent (`opponent_han_year` set). They feed a **separate HAN board stratum**,
  `vs_team`, and are **never pooled silently** with the classic stratum `alone` (no Assistant):
  - `tracks.leaderboard(rows, "han", board, stratum="alone" | "vs_team")`. The default is `alone`,
    the official HAN board as today.
  - The cells of `vs_team` are scenario × Assistant, because the Assistant is now a source of
    difficulty.
  - The admin and endpoint views show both strata side by side. A pooled view exists only when
    asked for explicitly (`stratum=both`), and it is labelled as pooled.
  - `han_interaction` needs the opponent questionnaire scales. An HI study that should feed HAN
    interaction must ask those items too, otherwise only `han_outcome` is ranked (the board's
    coverage warning says so).
- `_in_track` changes: a row is in `han/vs_team` when it has an Assistant and its opponent is a HAN
  entrant. It stays in `hi` as well.

---

## 7. Evaluation criteria and scores you define

A **criterion** is any number HANI2 measures for a negotiation: a metric column or a questionnaire
answer. A **score** combines criteria with weights. You can define as many scores as you like, make
any of them available in any project or study, and sort any leaderboard by them (§8).

### 7.1 The criteria catalogue

A new module, `evaluation/criteria.py`, builds one catalogue, served by
`GET /api/admin/criteria?project=…&study=…`. It holds:

1. **Every column of every registered metric.** Today that is 25 metrics with 200 columns:
   125 hard, 36 soft (judged by a language model), 23 subjective and 16 scores.
2. **Every questionnaire item** of the questionnaires the project or study uses (`q_<id>`), and
   every scale (`scale_<name>`). Their bounds come from the questionnaire YAML (`likert5`,
   `likert7`, `yes_no`, `select`, `min`/`max`). Reversed items are already reversed by
   `subjective.py`.
3. **Every score**, the built-in ones and yours, so one score can contain another.

Each criterion carries:

| Field | Meaning |
|---|---|
| `id`, `title`, `description` | From the metric's `Column`, or from the question text |
| `source` | `hard`, `soft`, `subjective`, `questionnaire` or `score` |
| `level` | `negotiation` (one value per game) or `participant` (a post-session answer, one per person) |
| `direction` | `higher`, `lower` or `none`. It comes from `Column.higher_is_better`, which 110 of the 200 columns set. The other 90 are descriptive (for example `n_offers`, `negotiation_seconds`, the move-type shares, `opponent_advantage`), so a score that uses one of them must state the direction |
| `normaliser` | The default mapping to [0, 1] (§7.2) |
| `cost` | `live` (computed when the game ends), `judge` (needs the offline judge run) or `questionnaire` |
| `coverage` | The share of the board's games that have a value |

The 11 columns that are not numbers (`status`, `ended_by`, labels, level names) cannot be chosen.

**Participant-level answers.** A post-session answer is attached to every game of that
participant, **but only when the participant used one Assistant throughout** (the game, or
between-subjects studies). When a participant used several Assistants, as in the finals, the answer
cannot be credited to one of them. The editor then greys the criterion out for HI scores and says
why.

### 7.2 Normalisation: every component in [0, 1], where 1 is best

Before weighting, every component value is mapped to [0, 1] with 1 as the best value. The mapping
is machine-readable. Today `Column.range` is free text for the docs; it stays, and a normaliser is
added next to it.

| Normaliser | Rule | Default for |
|---|---|---|
| `bounded [lo, hi]` | $(x-lo)/(hi-lo)$, clipped | `[0, 1]` (57 columns), `0 or 1` / `{0, 1}` (24), `1–7` (34), `[−1, 1]`, utilities, every questionnaire item with its own bounds |
| `advantage` | clipped to [0, 1]; no better than no deal = 0 | the `*_advantage` columns, as today |
| `reciprocal(s)` | $s/(s+x)$ (lower is better, unbounded) | counts, seconds, tokens, distances, US dollars, when lower is better |
| `saturating(s)` | $x/(x+s)$ (higher is better, unbounded) | unbounded counts when higher is better |
| `percentile` | the share of reference games with a lower value (the empirical CDF) | any criterion, on request |
| `clip [lo, hi]` | your own bounds | any criterion, on request |

With `direction: lower`, the bounded rules use $1-\cdot$ instead.

**The reference for unbounded criteria.** The scale $s$ is the median in a **frozen reference**,
so the median game scores 0.5. Without a frozen reference, adding a game would change everyone's
past scores. The reference is set per project with `normalisation.reference` (a list of studies and
an end date). `hani2 scores freeze <project>` computes the medians and quantiles and stores them in
`projects/<p>/results/normalisation.json`. The board shows them in its notes. Until a reference is
frozen, the board uses the current data and is labelled **provisional**.

**Checks.** `criteria.py` has a table of default normalisers, keyed by column and derived from
`range` where the text parses. A test checks that every numeric column has one. A component whose
criterion has no default must give its own normaliser, otherwise the score cannot be saved.

### 7.3 Defining a score: weights that sum to 1

```yaml
scores:
  hi_score:
    title: HI-score
    description: The team's result, the Assistant's help and how people experienced it
    track: hi                    # hi (ranks Assistants) | han (ranks opponents) | any
    components:
      - {criterion: human_advantage,       weight: 0.30}
      - {criterion: welfare_optimality,    weight: 0.10}
      - {criterion: ja_overall,            weight: 0.15}            # judge
      - {criterion: hi_team,               weight: 0.15}            # a score inside a score
      - {criterion: scale_tam_usefulness,  weight: 0.10}            # a questionnaire scale
      - {criterion: q_ueq_2,               weight: 0.05}            # one questionnaire item
      - {criterion: irrational_accept,     weight: 0.10}            # direction lower comes from the catalogue
      - {criterion: n_offers, weight: 0.05, direction: lower,
         normaliser: {kind: reciprocal, scale: reference_median}}
    missing: renormalise         # renormalise | zero | skip_game
    min_coverage: 0.5
```

- **Weights are ≥ 0 and sum to 1.** The editor takes percentages and shows the running sum. Save
  works only at 100 %, and a **Normalise** button rescales the weights to 100 %. The API and the
  CLI refuse a sum that is not 1 (to within 1e-6). A hand-edited file whose sum is not 1 is
  rescaled when it is loaded, with a warning in the log and in the study's `errors`.
- **Missing values** (`missing`):
  - `renormalise` (the default, and today's behaviour): the weights of the components present are
    rescaled to sum to 1, and `<score>_coverage` says how much weight was present.
  - `zero`: a missing value counts as 0.
  - `skip_game`: the game does not count for this score.
- **Coverage across entrants:** a component that is present in fewer than `min_coverage` of some
  entrant's games is dropped for **everyone**, and the rest are rescaled to sum to 1. That way every
  entrant is scored on the same parts. The board shows the weights in effect, the dropped parts and
  a warning.
- **Scores inside scores** are allowed, since a score is already in [0, 1]. Cycles are refused. The
  editor can show the weights flattened down to criteria.
- **Every score is in [0, 1], and its weights in effect always sum to 1.** The board shows both.
- **Built-in scores** (`utility` = `human_advantage` alone, `hi_outcome`, `hi_assistant`,
  `hi_team`, `hi_interaction`, `han_outcome`, `han_interaction`) become definitions in the same
  format, with their weights shown rescaled to sum to 1. Their values do not change, because the
  current weighted mean already divides by the sum of the weights. They are read-only; **Duplicate**
  copies one into the project, where it can be edited.
- **Names:** a score's key must not be the name of a column. The key is checked on save.

### 7.4 Where scores live and where they are available

- **Defined** in `project.yaml` under `scores:`. A study can add scores or redefine one by key in
  its own `study.yaml` (merged key by key). The built-ins come from the server.
- **Available**: `scores_enabled: [hi_score, utility, …]` in the project (default) or the study
  (override) lists the scores that are computed and shown in that study's boards, results views
  and exports. The default is the built-ins plus the project's own scores.
- `hani2 scores list|show|check <project>[/<study>]` prints the definitions, the weights in effect,
  the normalisers and the coverage in the data.

---

## 8. Leaderboards in hani2: per project and per study

### 8.1 Which games count

| Rule | Value |
|---|---|
| Games counted | **People and AI**: Paired matches (`opponent_kind` human or `human+assistant`) and AI games (`agent`, including fallbacks), shown apart and combined |
| Entrant | The row's Assistant (`assistant_entrant`, else the spec). On HAN boards, the opponent agent |
| Guests | **Count for the inviter's Assistant**: a guest plays with it, so their rows already carry that Assistant. No name is ever shown |
| Not counted | Practice; simulated participants; playground and admin sessions (`counts_as_human` false); `erred`; abandoned matches (both rows: shown only as the Assistant's *abandon rate*) |
| Same-Assistant games (an inviter against their guest) | Left out of `utility`. Counted **once** (the mean of the two rows) in other scores, unless the score sets `same_assistant: skip` |
| Minimum to be ranked | `min_games` counted games **and** `min_participants` distinct players who do not own the Assistant. Below either, the entrant is listed as "not ranked yet" |
| Caps | `max_games_per_pair` (the same two users) and `max_games_per_participant`, per Assistant. Games over a cap are counted under `excluded["cap"]`, and the latest games are the ones dropped |
| Own-team games | Counted. `exclude_own: true` leaves them out (D8) |

### 8.2 Configuring a board

A **project board** pools the project's chosen studies, and a **study board** shows one study. Both
use one `leaderboard:` block. The project sets it, and a study overrides it key by key for its own
board:

```yaml
leaderboard:
  track: hi                         # hi: entrants are Assistants; han: entrants are opponents
  source: game                      # game (default for HI) | tournament (hani2's simulated table)
  studies: [play, prolific-03]      # project board: which studies feed it (default: all)
  include:                          # rows from other projects, each with its stratum
    - {study: HI2027/play, stratum: vs_team}       # for example on HAN2027's board
  sort_options: [hi_score, utility, agreement]     # what end users may sort by (enabled scores or criteria)
  default_sort: hi_score
  columns: [hi_score, utility, agreement, games, participants]
  user_options:                     # the switches end users get, with their allowed values
    games:   [all, people, ai]
    stratum: [combined, solo, paired]
    window:  [all, last_30_days]
  defaults: {games: all, stratum: combined, window: all}
  visibility: participants          # public | participants | admins
  rules: {min_games: 10, min_participants: 3, max_games_per_pair: 3,
          max_games_per_participant: 20, exclude_own: false, adjust: relative, ci: 0.95}
```

- **Sorting.** A board can be sorted by **any enabled score or numeric criterion**. Admins may sort
  by anything that is enabled. End users may sort only by `sort_options`, and use only the switches
  and values in `user_options`. A switch that is not listed is not shown, and its default applies.
- **Ranks and ties.** A score is ranked by its entrant-level mean (cell-adjusted or cell-balanced,
  per `adjust`). A raw criterion is ranked by its mean in its own direction, and its raw value is
  shown. Ties use the confidence interval, as today (`tied_with_leader`, shown as "=2").
- **Validation on save:** every key in `sort_options` and `columns` must be enabled in every study
  the board reads, `default_sort` must be in `sort_options`, and each switch value must be one HANI2
  knows.

### 8.3 Where the numbers come from

- **Live:** when a game's row is written, the metrics that need no language model are computed
  from its recording and stored in `<study results>/eval_cache/<recording key>.json`. Boards
  aggregate these files and never re-read recordings, so they are cheap.
  `hani2 leaderboard refresh <project>[/<study>]` rebuilds the cache.
- **Offline:** `hani2 leaderboard judge …` runs the judge on the games not judged yet, and adds the
  `judge` criteria to the same files. A score that needs judge criteria is labelled **provisional**
  while fewer than 80 % of its games have been judged.
- **Aggregation:** `evaluation/boards.py: board(project, study, query)` applies §8.1, computes
  every needed score per game with §7, and calls the existing `tracks.leaderboard` machinery
  (cells, adjustment, bootstrap) with `rank_by=<score or criterion>`. **One function serves every
  view**: hani2's pages, the admin page and the API that scmlweb reads (§9). That is what keeps
  scmlweb on the same rules.

### 8.4 Confidence intervals and privacy

- A 95 % percentile bootstrap that **resamples participants**. When an Assistant has only one
  participant, the bootstrap falls back to sessions, shown as `ci_unit: "session"`.
- **No user names** appear on any board or in the API: no `user`, `opponent_user`, `invited_by` or
  participant index. Only counts.

### 8.5 The pages in hani2 (no scmlweb needed)

| Page | Who sees it | Content |
|---|---|---|
| `/s/<project>/leaderboard` | per `visibility` | The project board, with the switches in `user_options` |
| `/s/<project>/<study>/leaderboard` | per the study's `visibility` | That study's board |
| Admin → **Leaderboards** | admins | Any project or study board; every enabled score and criterion; strata (HI Solo / Paired / combined, HAN `alone` / `vs_team`); excluded games; the weights in effect; and the board and score editors (§10) |

For HI, `source: game` is the default. `source: tournament` shows hani2's own simulated table
(`simulated_leaderboard`, which is not known to match scmlweb's Tournament board) and stays
selectable.

---

## 9. scmlweb: the same rules for the active project

### 9.1 The API (the same function as hani2's pages)

- `GET /api/v1/projects/{project}/leaderboard?sort=&games=&stratum=&window=`
- `GET /api/v1/projects/{project}/studies/{study}/leaderboard?…`
- `GET /api/v1/leaderboards`: every project that has a board, with its track, year and
  `visibility`.

**Auth (new).** `Authorization: Bearer <JWT>`, HS256, signed with the existing SSO provider secret.
Claims: `aud: "hani2-api"` plus the root path (so a sign-in token can't read the API and an API
token can't sign anyone in), `scope: "leaderboard:read"`, and `iat`/`exp` at most 120 s apart. It
is not single-use. Boards with `visibility: public` need no token. Values outside the board's
`user_options` or `sort_options` get a **400**, so scmlweb cannot show a view that the project does
not allow.

**Response** (schema `hani2.leaderboard/2`). The response carries the allowed options, so scmlweb
draws exactly the switches the project allows and keeps no rules of its own:

```json
{
  "schema": "hani2.leaderboard/2",
  "project": "HI2027", "study": null, "track": "hi", "source": "game",
  "generated_at": "2027-03-14T09:30:00Z", "data_version": "sha1:4be1…",
  "query": {"sort": "hi_score", "games": "all", "stratum": "combined", "window": "all"},
  "options": {
    "sort": [{"key": "hi_score", "title": "HI-score", "description": "…", "kind": "score"},
             {"key": "utility", "title": "Utility", "kind": "score"},
             {"key": "agreement", "title": "Deals", "kind": "criterion", "direction": "higher"}],
    "games": ["all", "people", "ai"], "stratum": ["combined", "solo", "paired"],
    "window": ["all", "last_30_days"],
    "defaults": {"sort": "hi_score", "games": "all", "stratum": "combined", "window": "all"}
  },
  "columns": ["hi_score", "utility", "agreement", "games", "participants"],
  "scores": {"hi_score": {"weights_in_effect": {"human_advantage": 0.333, "ja_overall": 0.167, "…": 0},
                          "dropped": ["q_ueq_2"], "provisional": false}},
  "rules": {"min_games": 10, "min_participants": 3, "max_games_per_pair": 3,
            "max_games_per_participant": 20, "exclude_own": false, "adjust": "relative", "ci": 0.95},
  "entries": [
    {"rank": 1, "tied_with_leader": false, "entrant": "sub_0412",
     "assistant": "team42.assistant:Helper", "label": "Helper",
     "values": {"hi_score": {"mean": 0.71, "ci": [0.64, 0.77]},
                "utility":  {"mean": 0.62, "ci": [0.55, 0.69]},
                "agreement": {"mean": 0.88, "ci": [0.80, 0.94]}},
     "games": {"all": 58, "people": 21, "ai": 37}, "participants": 17, "guests": 6,
     "ci_unit": "participant", "abandon_rate": 0.03, "cost_usd": 0.012}
  ],
  "unranked": [{"entrant": "sub_0533", "label": "Coach", "games": {"all": 4}, "reason": "min_games"}],
  "excluded": {"practice": 3, "abandoned": 5, "cap": 12},
  "warnings": []
}
```

**Which project is active.** scmlweb names it in its own configuration, for example
`{"hi": "HI2027", "han": "HAN2027"}`, because the competition year is scmlweb's concept. Its HI page
reads `HI2027`'s project board, with the Tournament view as a second tab. *(D20)*

### 9.2 The HI2027 and HAN2027 projects

scmlweb defines them in its repository (`resources/hani2/projects/HI2027/`,
`resources/hani2/projects/HAN2027/`). **Each game becomes a study of its year's project**
(`HI2027/play`, `HAN2027/play`), so one project board pools the game and the year's Prolific
studies. The 2026 `hi-game` and `han-game` projects stay as they are, for the history. *(D22)*

```yaml title="HI2027/project.yaml"
full_name: HANI HI 2027
kind: assistant
year: 2027
defaults:
  study_mode: mixed
  opponents: [human+assistant, ":han2027-qualified"]   # this year: from the submitted zips (§3.4)
  scheduling: {assistants: balanced}
  pairing: {scope: study, assign: cells, allow_same_assistant: true, fallback: ai}
scores: {hi_score: {…}}                 # §7.3
scores_enabled: [utility, hi_score, hi_interaction]
leaderboard:
  track: hi
  source: game
  studies: [play]                       # add Prolific studies as they run
  sort_options: [hi_score, utility]
  default_sort: hi_score
  user_options: {games: [all, people, ai]}
  visibility: public
```

```yaml title="HAN2027/project.yaml"
full_name: HANI HAN 2027
kind: opponent
year: 2027
defaults:
  study_mode: solo
scores_enabled: [han_outcome, han_interaction]
leaderboard:
  track: han
  studies: [play]
  include: [{study: HI2027/play, stratum: vs_team}]   # HI games against HAN agents, as their own stratum
  sort_options: [han_outcome, han_interaction]
  user_options: {stratum: [alone, vs_team]}
  defaults: {stratum: alone}
```

**Who owns these files** *(D21)*. Today scmlweb copies its projects in on every start, which would
overwrite the controls you set in hani2's editor. Recommended: scmlweb **seeds** them, copying only
files that are missing and never overwriting. After that, hani2's editor owns the scores and
leaderboard keys. `hani2 project export HI2027` writes the files back, so they can be committed to
scmlweb's repository.

### 9.3 What scmlweb writes (to confirm with scmlweb)

**Runtime group files** (`<project>/studies/play/results/groups/<key>.json`). The new keys are
`entrant`, `own` and `han_year`:

```json
{"agents": ["human+assistant", ":han2026-finalists"],
 "assistant": "team42.assistant:Helper",
 "entrant": "sub_0412",
 "own": true,
 "ai_fallback": true}
```

- `entrant` (string): scmlweb's id for the Assistant (a submission or team id). It is written to
  `assistant_entrant` and becomes the API's `entrant`.
- `own` (bool): this participant is on the team that submitted the Assistant. For a guest's
  invitation it is `false`.
- `han_year` (int): the HAN year of the AI agents listed in this file, when they are named by class
  path from scmlweb's zips rather than by a `:han<year>-*` group. It feeds `opponent_han_year`.

`validate_data` accepts these keys from WP7 on. Older hani2 versions ignore them when they read a
file, but drop them when an admin saves the file through the API.

**Prolific:** `<results_base>/groups/<key>.json` and the `schedule.json` per PID keep their format.
If hani2 owns the K-of-N plan (§3.5, D14), scmlweb leaves `assistant` and `agent_class_name` empty.
A `paired` study with `assistants: external` treats the slots as a set (§4.2, D4).

**Guest settings** (`--settings`): unchanged.

---

## 10. The editor: one `?` help mechanism

**Today:** `Field.hint` is a one-line grey text, `Row` has no help, and `Projects.tsx` builds most
rows by hand. The only `?` is `ToolHelp` (`CircleHelp`, a portalled dialog) for tools.

**Design (one mechanism):**

1. **Texts on the server.** A new `src/hani2/help_texts.py` holds `HELP: dict[str, Help]` keyed by
   **setting id** (`study_mode`, `pairing.assign`, `scheduling.assistants`, `scheduling.cross`,
   `opponents.han`, `scores.missing`, `scores.normaliser`, `leaderboard.user_options`, …). Criteria
   reuse their catalogue text (§7.1) as their `?`. Each entry has `title`, `summary` (≤ 1 line, used
   as the hint) and `details` (Markdown with maths and tables, written like the scheduling methods'
   `details`). They are served once by `GET /api/admin/help` (admins), cached on the client like
   `useScheduling`. Scheduling methods keep their own registry, and `help_texts` links to it.
2. **`Row` gets `help?: string | HelpRef`.** When it is set (or when `HELP[id]` exists for the row's
   `id`), the row shows a `CircleHelp` button after the label. It opens a `HelpDialog`, which is
   `ToolHelp`'s dialog moved to `frontend/src/ui/HelpDialog.tsx` and shared by both.
   `Field.help` passes through `FieldRows`. Bare `<Row>`s in `Projects.tsx` pick it up from their
   `id`, so the existing ids (`scheduling-…`, `setting-…`) only need entries.
3. **Coverage is checked.** `help_texts.REQUIRED` lists every editor choice that is not
   self-explanatory. A backend test checks that each has an entry, and a node test
   (`frontend/tests/help.test.mjs`) checks that every id in `REQUIRED` occurs in the editor's
   sources. The docs page `docs/guide/projects.md` gets a generated "Settings reference" section
   from the same registry, as `scheduling.py` does with `write_docs`, so the docs and the `?` texts
   never disagree.

**Editor changes (study and project pages):**

- A **Mode** row (Solo / Paired / Mixed / *derived*) at the top of "Defaults" and "Overrides". It
  shows the derived mode and a red note when the mode and the pool disagree. In a HAN project,
  choosing Paired shows the note "tests no HAN agent; its results are not ranked".
- **Opponents**: the pool editor offers only what the mode allows. A structured **HAN agents**
  picker (year: the years in `han_years()` plus `han.current_year`, labelled "this year" / "last year" from the project's
  `year`; set: all / qualified / finalists / winners) writes `:han<year>-<set>`.
- **Assignment** (the Scheduling group): the methods valid for the mode. The row shows K
  (`n_required`) against N (the pool size), with a warning when K > N and repeats are off, and a
  **Crossing** row.
- **Pairing** (only Paired / Mixed): the scope, how matches are formed, same-Assistant matches, the
  fallback and its pool.
- **Scores** (a project or study page, and Admin → Leaderboards): a list of the scores, built-in
  ones shown read-only with **Duplicate**. The **score builder** has:
  - a criteria picker over the catalogue (§7.1), searchable, grouped by source (outcome metrics,
    behaviour, judge, questionnaire items and scales, scores). Each criterion shows its direction,
    its normaliser, its cost (live, judge or questionnaire) and its coverage in the current data;
    criteria that can't be used are greyed out with the reason;
  - per component, a weight in %, a direction (preset, and required when the catalogue has none)
    and a normaliser (preset, changeable);
  - a running sum of the weights, with Save enabled only at 100 % and a **Normalise** button;
  - a preview: the score's distribution and the top entrants on the current data, with the
    weights in effect after coverage.
- **Scores enabled** (project default, study override): checkboxes over every defined score.
- **Leaderboard** (project, and a study override): track, source, studies and includes, sort
  options and default sort, columns, the switches end users get with their allowed values and
  defaults, visibility, minimums, caps, own-team games, adjustment, and a link to the board as an
  end user sees it.
- Every row above has a `?`. Rows whose meaning is plain (Full name, Link, Start / end, Year,
  Organizer, Contact) do not.

---

## 11. Documentation: Project Management and Study Management pages

Everything in this note gets user documentation in **two main pages**, in a new nav section of
their own. They are written for people who run competitions and studies: they explain every choice
and give complete examples. Long, generated tables live in reference pages under the same section,
and the two main pages link to them.

Today the same subjects are spread over `projects.md` ("Projects and studies"), `studies.md`
("Studies and results"), `scheduling.md`, `human-opponents.md`, `prolific.md`, `study-forms.md`,
`evaluation.md` and `admin.md`. Other pages link to them about 70 times. MkDocs has no redirect
plugin here, so moving content means updating those links.

### 11.1 The new nav section

```yaml
nav:
  - Project and study management:
      - Project management: guide/project-management.md      # new (replaces projects.md)
      - Study management: guide/study-management.md          # new (takes the study parts of projects.md and studies.md)
      - Scheduling methods: guide/scheduling.md              # reference, generated, kept
      - Criteria and scores reference: guide/criteria.md     # reference, generated (WP5)
      - Settings reference: guide/settings-reference.md      # generated from help_texts.py (WP8): the `?` texts
      - Study forms: guide/study-forms.md                    # kept, moved here
      - Prolific: guide/prolific.md                          # kept, moved here
```

`Human opponents` stays in the User guide, where it describes what pairing looks like to the
participants (waiting, turns, leaving). The *choices* about pairing move to Study management.
`Evaluation metrics` stays in the User guide for what the metrics mean. *Defining scores and
boards* moves to Project management.

### 11.2 Project management (`guide/project-management.md`)

1. **What a project is**: a competition year or a research line. Its `kind` (HI: ranks
   Assistants; HAN: ranks opponents; none), its `year`, its studies and its folders.
2. **Creating and editing a project**: the admin console (Projects & Studies, every choice with a
   `?`), the command line, `project.yaml` and the admin API, and what a study inherits.
3. **Defaults for its studies**: every key, with a link to the Settings reference.
   - **Mode**: Solo, Paired or Mixed, what each means in HI and in HAN, and the derived mode.
   - **Opponents**: AI pools, and HAN agents by year and set, where "this year" and "last year"
     come from the project year.
   - **Assistants and assignment**: the methods in short (one Assistant per person, every
     Assistant once, K of N, crossing), linking to Scheduling methods.
   - **Pairing defaults**.
4. **Scores**:
   - criteria (every metric and every questionnaire item);
   - how values are scaled to [0, 1] and why the reference is frozen (`hani2 scores freeze`);
   - defining a score (weights summing to 100 %, missing values, coverage, scores inside scores);
   - built-in scores and duplicating them;
   - which scores each study enables.
5. **Leaderboards**:
   - the project board and its studies, and rows taken in from other projects;
   - sort options, columns, the switches end users get, visibility;
   - which games count (people and AI, guests, own-team games, minimums, caps);
   - confidence intervals and ties;
   - the pages `/s/<project>/leaderboard`;
   - the game board as the HI default, with the simulated table still available.
6. **Connecting a website**: the leaderboard API (paths, API tokens, the JSON schema with an
   example), group files with `entrant` and `own`, seeding projects from the website, and
   `hani2 project export`. It names no particular website: "a trusted website, for example the
   competition's site".
7. **A competition year, worked through**: `HI2027` and `HAN2027` with their games and Prolific
   studies, and how HI games against HAN agents reach the HAN board as their own group.
8. **Command line and admin API**: a summary table.

### 11.3 Study management (`guide/study-management.md`)

1. **A study's life**: create, configure, test (`hani2 human-trial`, test links), run, monitor,
   close.
2. **Study types**: Prolific, online, lab, and a game (online, with sign-in hand-off and
   invitations). Folders, URLs, texts with variables and consent, moved from `projects.md`.
3. **`study.yaml` and overrides**: what a study can override, and how layers merge.
4. **Mode**: Solo, Paired and Mixed, the checks against the opponent pool, and the error messages
   with how to fix them.
5. **Assigning Assistants, opponents and scenarios**:
   - K sessions per person over N Assistants, each at most once;
   - position and co-occurrence balance;
   - crossing Assistants with opponents;
   - schedules from an outside system, and who owns the plan;
   - the full rules are in Scheduling methods.
6. **Paired studies**:
   - match cells and how a match is formed (`cells`, `order`, `random`, `slack`);
   - same-Assistant matches, where people meet, what happens when nobody fits;
   - **what is guaranteed and what is only best effort** (the table from §4.5).
7. **Designs, ready to copy**:
   - the finals (every finalist once, crossed with HAN finalists);
   - K-of-N screening;
   - a Paired HI study;
   - a HAN Solo study;
   - an HI Solo study that also feeds HAN;
   - the game;
   - why a HAN Paired study ranks nothing.
8. **Forms and questionnaires**: in short, with a link to Study forms. It also says which
   questionnaire items can be used in scores, and the rule for post-session answers.
9. **Monitoring**: `hani2 study balance` and the study page (cell counts, positions, fallbacks,
   people who could not complete).
10. **Results**:
    - the `results.csv` columns, including the new ones from §5;
    - reading Paired results (count each match once for negotiation-level measures);
    - the event log;
    - moved from `studies.md`. The old "Experiments" layout becomes a short closing section.
11. **The study's own board and its enabled scores**.
12. **Command line and admin API**: a summary table.

### 11.4 How the docs stay right

- **WP0 (docs restructure, before WP1):**
  - create the two pages from the existing content of `projects.md` and `studies.md`, with no new
    features;
  - delete the old files, update every inbound link and every anchor;
  - add `mkdocs build --strict` to the checks, as `tests/test_docs_build.py`, which is skipped
    when the docs extras are missing, so broken links and anchors fail the tests.
- **Each work package** adds its sections to these two pages (the "Docs" column in §12), not to
  new scattered pages.
- **Single sources:**
  - the Settings reference is generated from `help_texts.py`, so a `?` text and the docs can't
    disagree;
  - the Criteria and scores reference is generated from the criteria catalogue;
  - Scheduling methods stays generated from `scheduling.py`.
- The docs stay self-contained: no mention of the predecessor project and no internal design
  notes.

---

## 12. Work packages, in order

Each package ends with its tests green (`.venv/bin/pytest -q`), its docs written, and a commit.
**Only WP8 and WP9 touch `frontend/`, and they run one after the other**. Each rebuilds and commits
`src/hani2/web`.

| WP | What | Files | Tests | Docs |
|---|---|---|---|---|
| **0. Docs restructure** | The two management pages from existing content, the new nav section, links and anchors updated, the old `projects.md` and `studies.md` removed | `docs/guide/*.md`, `docs/getting-started/*.md`, `mkdocs.yml`, `README.md` | new `tests/test_docs_build.py` (`mkdocs build --strict`) | — |
| **1. Mode keys and validation** | `study_mode`, the `pairing` block (parsed, merged, validated against `opponents`, the Assistant and the project kind), the derived mode, per-session checks of group files and slots, `hani2 study show` output, the HAN source rule (`han.current_year`, the submissions index, `hani2 han import/check`, the `opponent_han_*` columns) | `projects.py` (`DEFAULT_KEYS`, `file_problems`), `agents.py` (resolving `:han<year>-*`), new `han_submissions.py`, `config.py`, `matches.py` (`study:` scope in `match_key`), `session.py` (per-session filter, reusing `people_only`), `assignment.py` (group-file checks), `cli.py` | `tests/test_projects.py`, `tests/test_human_opponents.py` (scope, contradictions), `tests/test_agents.py` and new `tests/test_han_submissions.py` (which source wins per year, import of a test zip into its own folder, a new hash gives a new version, unknown years refused) | Project management §3 (mode, pairing defaults, HAN agents); Study management §2–§4 (types, overrides, mode) |
| **2. Solo assignment** | The K ≤ N check, `assistant_repeats`, `balanced_subset`, `random_subset`, the `cross: shift` crossing, the open-slot branch of `ProlificStudy.plan_round` (§3.5, D14), the `hani2 study balance` report (Solo part) | `scheduling.py` (registry, rules, generated docs), `assignment.py` (plans in `assignments.json`), `study.py` | `tests/test_scheduling.py` (subset and position balance, crossing coverage for 5 × 5 over 50 people, P1 regression), `tests/test_study.py` | Study management §5, §7 (assignment, designs); Scheduling methods (regenerated with `python -m hani2.scheduling`) |
| **3. Paired assignment** | The `match_cells.json` store, host commit, joiner late binding, cell-aware `Lobby.pair` with `slack`, in-flight reservation and release, completion hook, `pairing.fallback`, scenario fit for `by_participant`, `used_assistants`, the result columns of §5, the Paired part of `hani2 study balance` | `matches.py`, `session.py` (≈1655–1765, `_leave_match`, end of round), `assignment.py` (cell store), `results.py`, `events.py` | new `tests/test_pairing_cells.py` (hard guarantees, dead-end fallback, abandon releases, two concurrent joiners), `tests/test_human_opponents.py`, `tests/test_session.py` | Study management §6, §9, §10 (Paired, monitoring, results columns); `human-opponents.md` (what participants see) |
| **4. Evaluation strata** | Paired cells per row, match dedup, same-Assistant collapse, `ci_unit: match`, the `study_mode` strata, HAN `vs_team`, `excluded["human opponent"]`, optional head-to-head | `evaluation/__init__.py` (`ID_FIELDS`), `evaluation/tracks.py`, `evaluation/base.py` | `tests/test_tracks.py` | Study management §10 (reading Paired results); `evaluation.md` (strata) |
| **5. Criteria catalogue and normalisation** | `evaluation/criteria.py` (metric columns, questionnaire items and scales, scores; levels, directions, costs), machine-readable normalisers with a default for every numeric column, frozen references (`normalisation.json`, `hani2 scores freeze`), `GET /api/admin/criteria` | new `evaluation/criteria.py`, `evaluation/base.py` (`Column.normaliser`), `evaluation/hard.py`, `soft`/`llm_judge.py`, `subjective.py`, `questionnaires.py`, `server.py`, `cli.py` | new `tests/test_criteria.py` (every numeric column has a normaliser, every value is in [0, 1], questionnaire bounds and reversed items, participant-level rule) | Project management §4 (criteria, scaling); the new Criteria and scores reference (generated) |
| **6. User-defined scores** | `scores:` and `scores_enabled` in project and study files (merged), validation (weights ≥ 0 summing to 1, no cycles, key clashes, directions), rescaling on load with a warning, `missing` policies, built-ins rewritten as definitions, `hani2 scores list/show/check` | `evaluation/scores.py`, `projects.py` (`DEFAULT_KEYS`), `server.py` (admin CRUD for scores), `cli.py` | `tests/test_scores_defined.py` (weights, missing policies, coverage drop, nested scores, built-ins unchanged against today's values) | Project management §4 (defining and enabling scores); Study management §11 |
| **7. Boards and API** | The `leaderboard` block (project, study override, validation), `evaluation/boards.py` (§8.1 rules, `rank_by`, strata, includes, caps, minimums), the eval cache and `hani2 leaderboard refresh/judge`, the public and admin pages' API `GET /api/v1/projects/{p}[/studies/{s}]/leaderboard` and `/api/v1/leaderboards`, API-token auth, `visibility`, the group-file keys `entrant`, `own` and `han_year`, `hani2 project export` | new `evaluation/boards.py`, `evaluation/tracks.py` (`rank_by`, the `game` board), `projects.py`, `server.py`, `sso.py` (`verify_api_token`), `groups.py`, `results.py`, `cli.py` | new `tests/test_boards.py` (game rules, sort options, 400 for options not allowed, same result for the page and the API), `tests/test_server.py` (401/403/400), `tests/test_sso.py` (audience separation), `tests/test_groups_and_assignment.py` | Project management §5–§7 (boards, the API, connecting a website, a competition year); Study management §11; `authentication.md` (API tokens) |
| **8. Help mechanism and editor** *(frontend)* | `help_texts.py` and `/api/admin/help`; `Row.help`, `Field.help`, the shared `HelpDialog`; Mode, the HAN picker, Assignment, Pairing, the score builder, Scores enabled and Leaderboard settings in `Projects.tsx`; the generated settings reference; rebuild `src/hani2/web` | `src/hani2/help_texts.py`, `server.py`, `frontend/src/admin/{Row,schema}.tsx`, `frontend/src/ui/HelpDialog.tsx`, `frontend/src/negotiate/ToolPane.tsx`, `frontend/src/admin/pages/Projects.tsx`, new `frontend/src/admin/ScoreBuilder.tsx`, `src/hani2/web/**` | `tests/test_admin_api.py` (help coverage), `frontend/tests/help.test.mjs`, `frontend/tests/weights.test.mjs` (sum and Normalise), `tests/e2e` (open a `?`, build a score, save a contradiction and get a 400) | The Settings reference (generated); `admin.md`; screenshots in both management pages |
| **9. Leaderboard pages** *(frontend, after WP8)* | The end-user pages `/s/<p>/leaderboard` and `/s/<p>/<s>/leaderboard` (only the switches allowed), and Admin → Leaderboards (everything, strata, exclusions, weights in effect); rebuild `src/hani2/web` | new `frontend/src/pages/Leaderboard.tsx`, `frontend/src/admin/pages/Leaderboards.tsx`, `Sidebar.tsx`, `router.ts`, `server.py` (the page routes), `src/hani2/web/**` | `tests/e2e` (switch sort options and games; a hidden switch is not shown; visibility) | Project management §5 (the pages, as end users see them) |
| **10. scmlweb** *(other repo, after WP7)* | Seed `HI2027` and `HAN2027` (copy if missing), move the games into them, read the project board API for the active project (scmlweb's configuration) as the default HI board, with the Tournament tab; write `entrant` and `own` | scmlweb | scmlweb's | scmlweb's |

WP0 comes first, so every later package writes into the new pages. WP1 → WP7 are backend only and in dependency order. WP5 and WP6 do not need WP3 or WP4 and could
run right after WP1, but WP7 needs all of them. WP8 starts after WP7, because its editors need the
scores and leaderboard keys. If the editor is wanted earlier, WP8 can be split: the help mechanism
plus Mode, HAN, Assignment and Pairing after WP3, and the score and leaderboard editors after WP7.
WP9 follows WP8.

---

## 13. Decisions (settled 2026-11-26)

You settled D12 yourself. For every other decision you accepted the recommendation, so the right
column is now the decision.


| # | Question | Decision |
|---|---|---|
| D1 | Should the new setting be called `study_mode` (`mode` is taken by `simulated`), with the values `solo`, `paired` and `mixed`? | **Yes.** The UI says "Mode: Solo / Paired / Mixed" |
| D2 | Should Solo K-of-N with K < N use the new `balanced_subset` (balanced co-occurrence), or is `latin_square` enough? | **`balanced_subset` for K < N**, and `latin_square` for K = N (the finals) |
| D3 | Should the Assistant × opponent crossing (`cross: shift`) be on by default for new studies? It fixes the confounding P1 | **Yes**, stored per human so that running studies do not change |
| D4 | In Paired, should a person's Assistants be a *set* (the order is only a preference), so that the cell balance can work? | **Yes.** Strict order (`assign: order`) stays available for scripted lab sessions |
| D5 | When nobody fits in Paired: should the fallback default to playing an AI opponent with the planned Assistant, counting it as used, filling no cell and being ranked under Solo? | **Yes** (`fallback: ai`). Prolific participants are paid for the time anyway |
| D6 | Should the game ask a short questionnaire so that scores can include subjective items? | **Yes: 4 items after every game, skippable**, with `min_coverage: 0.3` on the scores that use them, so partial answers still count |
| D7 | Game board adjustment: cell-adjusted means (`relative`) or the cell-balanced mean? | **`relative`**, because the game's cells are sparse and uneven. Cell-balanced for planned studies |
| D8 | Should games where a team plays its own Assistant count? | **Count them, but require `min_participants: 3` players who are not the owners.** `exclude_own` stays available |
| D9 | API auth: a JWT on the existing SSO secret, or public boards (no names in them)? | **The JWT** (`aud: hani2-api`) for non-public boards. Boards with `visibility: public` need none |
| D10 | Should scmlweb pull from the endpoint, or should hani2 push tournament-style results? | **Pull**, cached on `data_version` |
| D11 | Should same-Assistant matches (an inviter against their guest) be out of `utility` but counted once in other scores? | **Yes.** They are not allowed at all in Paired evaluation studies |
| D12 | Where do HAN entrants come from? | **Decided by you:** the current year (`han.current_year`, set explicitly) from the submitted zips through scmlweb's index; every other year from `han-agents` (§3.4) |
| D13 | Should the HAN board show HI-Solo games against HAN agents as a separate `vs_team` stratum next to the official `alone` board, never pooled by default? | **Yes** |
| D14 | For Prolific, who owns the K-of-N and crossing plan: hani2 (scmlweb leaves the `assistant` and `agent_class_name` slots empty) or scmlweb (it writes complete slots)? | **hani2 owns it**: one implementation of the rules. scmlweb's slots keep only what it must fix |
| D15 | In the game, does each player always use their own team's Assistant (guests: the inviter's), or does the game assign Assistants (balanced at pairing)? With own Assistants, "balanced at pairing" balances only *whom* each Assistant meets, and the non-owner players of an Assistant are mostly invited guests | **Own Assistant for team members and their guests** (as today). Balancing at pairing goes over the opposing Assistant, the scenario and the side. Players who have no team get an Assistant through `balanced` |
| D16 | Is the *scenario* in a match cell the type (domain) or the instance (the predefined utility functions)? | **The type.** The instance is recorded, and the instances follow the scenario method |
| D17 | How should unbounded criteria (counts, seconds, tokens, distances) be normalised by default? | **`reciprocal` / `saturating` around the median of a frozen reference**, so the median game is 0.5. `percentile` and your own bounds stay available |
| D18 | Weights: refuse to save until they sum to 100 %, or rescale them silently? | **Refuse in the editor, the API and the CLI**, with a **Normalise** button. Only hand-edited files are rescaled on load, with a warning |
| D19 | Post-session answers (one per participant): credit them to the Assistant only when the participant used one Assistant throughout? | **Yes.** Otherwise they are greyed out for HI scores |
| D20 | Which project's board does scmlweb show: does scmlweb's configuration name the active project, or does hani2 mark one? | **scmlweb's configuration** (`{"hi": "HI2027", "han": "HAN2027"}`). hani2 lists every board |
| D21 | Who owns the files of `HI2027` and `HAN2027` after scmlweb creates them? | **scmlweb seeds them (copies only missing files), then hani2's editor owns them.** `hani2 project export` writes them back for scmlweb's repository |
| D22 | Should the games move into the year projects (`HI2027/play`, `HAN2027/play`), so that one project board pools the game and the Prolific studies? | **Yes.** The 2026 `hi-game` and `han-game` stay for the history |
| D23 | Default visibility of a project board in hani2? | **`participants`** (signed-in users), and `public` for HI2027 and HAN2027 once you are happy with them |
| D24 | Docs: two new pages (Project management, Study management) that replace `projects.md` and `studies.md`, with generated reference pages under the same nav section, and `mkdocs build --strict` in the tests? | **Yes**, done as WP0 before any feature, so each feature documents itself in the right place |
