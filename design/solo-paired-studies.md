# Design note: Solo and Paired studies, fair assignment, HAN opponents in HI, the game leaderboard

Status: **draft for review, nothing built yet** (2026-11-26). This note is internal and is not in the
MkDocs nav (it lives outside `docs/`). It should not be published as written. Each work package
writes its own user docs.

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
| HAN groups | `agents.py` `han_groups()` | `:han<year>-all/-qualified/-finalists/-winners`, for every year that the installed `han-agents` package covers (only 2026 today). |
| Auth | `server.py`, `sso.py` | Only cookie auth (`require_user` / `require_admin`) and the HS256 sign-in hand-off secret shared with scmlweb. **No service-to-service auth exists.** |
| Group files | `groups.py` | Opponent group files take `agents`, `assistant` (old name `support_agent`), `syspath` and `ai_fallback`. **Other keys are ignored silently**. New keys must be added to `load_file`, `Group` and `to_dict`. |
| Editor | `frontend/src/admin/schema.tsx` (`Field`), `Row.tsx`, `pages/Projects.tsx` | `Field` has `hint` (a one-line grey text) and **no `help`**. `Projects.tsx` builds most rows with a bare `<Row hint=…>`, not with `Field`. The only `?` today is `ToolHelp` in `negotiate/ToolPane.tsx` (a `CircleHelp` button with a portalled dialog). Scheduling methods already bring their Markdown `details` from the server (`GET /api/admin/scheduling-methods`). |

Two problems in today's code matter for fairness and are fixed below:

- **P1: Assistant and opponent are confounded.** `pick_assistant_slot("latin_square")` and
  `pick_opponent("latin_square")` both return `pool[latin_index(n, i, k)]`. Take a study with 5
  finalist Assistants and 5 HAN finalists, both on `latin_square`: Assistant $j$ meets opponent $j$
  in every single negotiation. Assistant and opponent effects then cannot be separated (§3.3).
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
  `han_years()` is shown greyed out ("han-agents covers only 2026"). On save it is refused with the
  same message, and when a hand-edited file is loaded it is reported (the group expands to nothing,
  and the study falls back as today).
- **Which agents count as 2026 finalists:** the installed `han-agents` package decides, through
  `han_groups()`. scmlweb chooses agents by `agent_placements.year`, from zips in
  `~/anac/_agents_han`. *To confirm with scmlweb:* both lists must name the same agents. WP1 adds
  `hani2 han check --year 2026 --expect <file>`, which compares the package's groups with a list
  that scmlweb exports. In a game invitation, scmlweb may instead write a group file listing the
  unpacked zips (with `syspath`), as it does today for invited agents.
- New result column **`opponent_han_year`** (an int, or empty), filled when the opponent came from
  a `:han<year>-*` group. `opponent_group` already keeps the group key.

---

## 4. Assignment in Paired: the match is the unit

### 4.1 Cells

In Paired, fairness is decided **when two people are paired**, over **match cells**:

$$
\text{cell} = (\text{scenario},\ \text{Assistant at side 0},\ \text{Assistant at side 1})
$$

This is one canonical key per match, `"<scenario>|<A>@0|<B>@1"`. From each participant's own row,
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
§6.2 and §7.1.

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

## 7. The game leaderboard (the default HI board)

### 7.1 Which games count

| Rule | Value |
|---|---|
| Games counted | **People and AI**: Paired matches (`opponent_kind` human or `human+assistant`) and AI games (`agent`, including fallbacks). Shown **apart and combined** (`games=people\|ai\|all`, default `all`) |
| Entrant | The row's Assistant (`assistant_entrant`, else the spec) |
| Guests | **Count for the inviter's Assistant**: a guest plays with it, so their rows already carry that Assistant. `invited_by` is kept, but no name is ever shown |
| Not counted | Practice; simulated participants; playground (`guest_*`, `play:`) and admin sessions (`counts_as_human` false); `erred`; abandoned matches (both rows: shown only as the Assistant's *abandon rate*) |
| Same-Assistant games (inviter against guest) | Left out of the **utility** category (they are not a contest). Counted **once** in HI-score (the mean of the two rows) |
| Minimum to be ranked | `min_games: 10` counted games **and** `min_participants: 3` distinct participants who do **not** own the Assistant. Entrants below either minimum are listed as "not ranked yet" |
| Caps | `max_games_per_pair: 3` (the same two users, either side, per Assistant, over the board's window) and `max_games_per_participant: 20` per Assistant. Games over a cap are skipped, counted under `excluded["cap"]`, and the latest games are the ones dropped |
| Own-team games | Counted, but `own_assistant` rows can be excluded with `exclude_own: true` (*D8*) |

### 7.2 Categories

Each board has categories that can be switched (`?category=`), configured under
`leaderboard.categories` (project or study, merged key by key):

```yaml
leaderboard:
  source: game            # game | tournament   (the default HI board; §7.5)
  games: all              # all | people | ai
  window: {since: 2026-12-01, until: null}
  min_games: 10
  min_participants: 3
  max_games_per_pair: 3
  max_games_per_participant: 20
  exclude_own: false
  adjust: relative        # relative | balanced  (D7)
  categories:
    - key: utility
      title: Utility
      score: hi_outcome           # the team's advantage over no deal, in [0, 1]
    - key: hi_score
      title: HI-score
      score: hi_score             # see below
      weights: {}                 # overrides of hi_score's component weights
    - key: agreement              # optional extra categories: any column or score
      title: Deals
      score: agreement
```

**`hi_score`** is a new `Score` in `evaluation/scores.py` (track `hi`, board `game`). Its default
components, all with configurable weights:

| Component | Default weight | Live? |
|---|---|---|
| `agreement` | 0.5 | yes (eval cache, no language model) |
| `welfare_optimality` (or `nash_optimality`) | 0.5 | yes (eval cache) |
| `irrational_accept` (inverse) | 0.5 | yes (eval cache) |
| `hi_assistant` (the judge, errors, function calls, its questionnaire items) | 1 | judge parts: offline |
| `hi_team` (reliance, engagement, the human's errors) | 1 | judge parts: offline |
| questionnaire scales: `scale_ueq_pragmatic_norm`, `scale_tam_usefulness_norm`, `scale_felt_heard_norm`, `scale_intention_to_use_norm` | **0** until the game asks a questionnaire | when asked |

Weights come, in order of precedence, from the category's `weights`, then
`env.json evaluation.scores.hi_score.weights`, then the defaults. A weight of 0 drops a component.
Components missing for too many entrants are dropped for everyone (`_active_components`,
`min_coverage`), so every entrant is scored on the same parts. The board shows `components`,
`dropped_components` and `weight_share`, and marks a category **provisional** when the judge has
not yet scored a share of the games (`judge_share < 0.8`).

The game project has `questionnaires: false` today. To use subjective scales, the game needs a short
post-game questionnaire, for example the four items above, optional or every *n*-th game. *(D6)*

### 7.3 Where the numbers come from (two data paths)

- **Live path**: a per-game evaluation cache. When a game's row is written, the non-LLM metrics of
  its recording are computed and stored in `<study results>/eval_cache/<recording key>.json`.
  The metrics are those `evaluate_paths` computes without `llm`: outcome, welfare, irrational
  accept, function-call success, reliance flags. The endpoint aggregates these cache files and
  never re-reads recordings, so it is cheap. The cache is also rebuilt by
  `hani2 leaderboard refresh <study>`.
- **Offline path**: `hani2 leaderboard judge <study> --since …` runs the language-model judge on
  games that have not been judged yet and adds its scores to the same cache files. Its cost is
  logged as usual. It runs under the judge-reliability gate (`official` boards leave out soft
  components without a report).
- The aggregation is the existing `tracks.leaderboard` with `relative` or cell balance, the cells
  (scenario, side, opponent), and the bootstrap. One function, `evaluation/game_board.py:
  game_leaderboard(rows, config)`, applies §7.1 (filters, caps, minimums, same-Assistant handling)
  and then calls it per category.

### 7.4 Confidence intervals and privacy

- A 95 % percentile bootstrap, **resampling participants** (the existing `_bootstrap`). When an
  Assistant has been played by only one participant (often its owner), the fallback to sessions is
  shown as `ci_unit: "session"`. `min_participants` mostly keeps such entrants unranked.
- `tied_with_leader` stays as it is today: the upper bound reaches the leader's lower bound. A rank
  is shown as "=2" when tied.
- **No user names anywhere** in the board or the endpoint: no `user`, `opponent_user`,
  `invited_by` or participant index. Counts only (games, participants, people/AI split).

### 7.5 The default HI board

`leaderboard.source: game` is the default for HI. The tournament board, which scmlweb computes from
its Tournament rows and which `hani2.results.simulated_leaderboard` mirrors, stays selectable:

- **In hani2**: a new admin page, **Leaderboards** (WP7), with a source switch (game / simulated
  tournament), a category switch, a games switch and strata tabs (Solo / Paired / combined; HAN
  `alone` / `vs_team`).
- **In scmlweb** (*to confirm with scmlweb*): the HI leaderboard page reads the endpoint in §8 by
  default and keeps its Tournament view as a second tab.

---

## 8. The contract with scmlweb

### 8.1 The endpoint

`GET /api/v1/leaderboards/hi`

| Query | Default | Meaning |
|---|---|---|
| `study` | the project's `leaderboard` study, else `hi-game/play` | `<project>/<study>` |
| `category` | the first configured category | `utility`, `hi_score`, … (`categories` lists them) |
| `games` | `all` | `all`, `people`, `ai` |
| `stratum` | `combined` | `combined`, `solo`, `paired` |
| `since`, `until` | the board's `window` | ISO dates |

`GET /api/v1/leaderboards/han` takes `stratum=alone|vs_team|both` and is the same otherwise.

**Auth (new).** `Authorization: Bearer <JWT>`, HS256, signed with the **existing** SSO provider
secret (`auth.sso.scmlweb.secret` / `HANI2_SSO_SCMLWEB_SECRET`), so there is no new secret to share.
Claims: `iss` (the provider's issuer), **`aud: "hani2-api"`** plus the root path (different from the
sign-in audience, so a sign-in token can never read the API and an API token can never sign anyone
in), `scope: "leaderboard:read"`, and `iat`/`exp` at most 120 s apart. Unlike the sign-in token it
is **not** single-use, so it can be retried. Admin cookies work too. Board config
`leaderboard.public: true` would allow unauthenticated reads, since no names are in the data.
*(D9)*

**Response** (`200`, `application/json`; schema version 1):

```json
{
  "schema": "hani2.leaderboard/1",
  "track": "hi",
  "study": "hi-game/play",
  "source": "game",
  "generated_at": "2026-12-14T09:30:00Z",
  "data_version": "sha1:4be1…",
  "category": {"key": "hi_score", "title": "HI-score", "score": "hi_score",
               "components": {"agreement": 0.5, "welfare_optimality": 0.5, "irrational_accept": 0.5,
                              "hi_assistant": 1, "hi_team": 1},
               "dropped_components": ["scale_ueq_pragmatic_norm"],
               "provisional": false},
  "categories": [{"key": "utility", "title": "Utility"}, {"key": "hi_score", "title": "HI-score"}],
  "games": "all",
  "stratum": "combined",
  "rules": {"min_games": 10, "min_participants": 3, "max_games_per_pair": 3,
            "max_games_per_participant": 20, "exclude_own": false, "adjust": "relative",
            "window": {"since": "2026-12-01", "until": null}},
  "entries": [
    {"rank": 1, "tied_with_leader": false, "ranked": true,
     "entrant": "sub_0412", "assistant": "team42.assistant:Helper", "label": "Helper",
     "score": 0.71, "ci": [0.64, 0.77], "ci_unit": "participant",
     "games": {"all": 58, "people": 21, "ai": 37},
     "participants": 17, "guests": 6,
     "abandon_rate": 0.03, "cost_usd": 0.012,
     "coverage": 0.93}
  ],
  "unranked": [
    {"entrant": "sub_0533", "assistant": "team7.a:Coach", "label": "Coach",
     "games": {"all": 4, "people": 1, "ai": 3}, "participants": 2, "reason": "min_games"}
  ],
  "excluded": {"practice": 3, "abandoned": 5, "cap": 12, "same_assistant (utility)": 4},
  "warnings": []
}
```

- `entrant` is the group file's `entrant` id when there is one, else the Assistant spec.
- `score` is in [0, 1]. With `adjust: relative` it is the cell-adjusted mean plus the board-wide
  mean, so it stays on the [0, 1] scale. `ci` is `null` when there are fewer than 2 clusters.
- `data_version` changes only when the counted data changes, so scmlweb can cache on it.
- Errors: `400` (unknown study, category, games or stratum), `401` (missing or bad token), `403`
  (wrong `aud` or `scope`), `404` (the study has no `leaderboard` block).

*Alternative:* hani2 could push a tournament-style payload into scmlweb's Tournament API. That is
**not recommended**, because it would put a second copy of the rules in scmlweb. Pull plus caching
on `data_version` is simpler. *(D10)*

### 8.2 What scmlweb writes (to confirm with scmlweb)

**(a) Game projects** (`resources/hani2/projects/hi-game/`, copied in on start):

```yaml title="project.yaml"
full_name: HI game
kind: none                 # outside any evaluation study, but with its own board
year: 2026
defaults:
  practice: false
  time_limit: 600
  study_mode: mixed
  opponents: [human+assistant, ":han2026-finalists"]   # people first, else a HAN finalist (feeds HAN vs_team)
  assistants: []           # always from the group file
  scheduling: {assistants: balanced}
  pairing: {scope: project, assign: cells, allow_same_assistant: true, fallback: ai}
  questionnaires: false    # D6
leaderboard:
  source: game
  categories: [{key: utility, score: hi_outcome}, {key: hi_score, score: hi_score}]
```

`han-game` stays as it is (`kind: none`, `study_mode: solo`). Its board is the HAN endpoint with
`stratum=alone`.

**(b) Runtime group files** (`<project>/studies/play/results/groups/<key>.json`). The new keys are
`entrant`, `own` and `han_year`. Each is optional and ignored by older hani2 versions:

```json
{"agents": ["human+assistant", ":han2026-finalists"],
 "assistant": "team42.assistant:Helper",
 "entrant": "sub_0412",
 "own": true,
 "ai_fallback": true}
```

For a guest's invitation, the same file has `"own": false`.

**(c) Prolific:** `<results_base>/groups/<key>.json` and `schedule.json` per PID are unchanged. A
Prolific `paired` study with `assistants: external` treats the schedule's slots as a **set** (§4.2),
so slot order is a preference, not a promise. *(D4)*

**(d) Guest settings** (`--settings`): unchanged.

---

## 9. The editor: one `?` help mechanism

**Today:** `Field.hint` is a one-line grey text, `Row` has no help, and `Projects.tsx` builds most
rows by hand. The only `?` is `ToolHelp` (`CircleHelp`, a portalled dialog) for tools.

**Design (one mechanism):**

1. **Texts on the server.** A new `src/hani2/help_texts.py` holds `HELP: dict[str, Help]` keyed by
   **setting id** (`study_mode`, `pairing.assign`, `scheduling.assistants`, `scheduling.cross`,
   `opponents.han`, `leaderboard.min_games`, …). Each entry has `title`, `summary` (≤ 1 line, used
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
  picker (year: the years in `han_years()`, labelled "this year" / "last year" from the project's
  `year`; set: all / qualified / finalists / winners) writes `:han<year>-<set>`.
- **Assignment** (the Scheduling group): the methods valid for the mode. The row shows K
  (`n_required`) against N (the pool size), with a warning when K > N and repeats are off, and a
  **Crossing** row.
- **Pairing** (only Paired / Mixed): the scope, how matches are formed, same-Assistant matches, the
  fallback and its pool.
- **Leaderboard** (only projects that have the block): source, games, minimums, caps, own-team
  games, adjustment, and categories with their weights (a small table).
- Every row above has a `?`. Rows whose meaning is plain (Full name, Link, Start / end, Year,
  Organizer, Contact) do not.

---

## 10. Work packages, in order

Each package ends with its tests green (`.venv/bin/pytest -q`), its docs written, and a commit.
**Only WP6 and WP7 touch `frontend/`, and they run one after the other**. Each rebuilds and commits
`src/hani2/web`.

| WP | What | Files | Tests | Docs |
|---|---|---|---|---|
| **1. Mode keys and validation** | `study_mode`, the `pairing` block (parsed, merged, validated against `opponents`, the Assistant and the project kind), the derived mode, per-session checks of group files and slots, `hani2 study show` output, `hani2 han check` | `projects.py` (`DEFAULT_KEYS`, `file_problems`), `matches.py` (`study:` scope in `match_key`), `session.py` (per-session filter, reusing `people_only`), `assignment.py` (group-file checks), `cli.py` | `tests/test_projects.py`, `tests/test_human_opponents.py` (scope, contradictions), `tests/test_agents.py` (han check) | `docs/guide/projects.md`, `studies.md`, `human-opponents.md` |
| **2. Solo assignment** | The K ≤ N check, `assistant_repeats`, `balanced_subset`, `random_subset`, the `cross: shift` crossing, the `hani2 study balance` report (Solo part) | `scheduling.py` (registry, rules, generated docs), `assignment.py` (plans in `assignments.json`), `study.py` (`plan_round` crossing) | `tests/test_scheduling.py` (subset and position balance, crossing coverage for 5 × 5 over 50 people, P1 regression), `tests/test_study.py` | `docs/guide/scheduling.md` (regenerated with `python -m hani2.scheduling`) |
| **3. Paired assignment** | The `match_cells.json` store, host commit, joiner late binding (`refresh_assistant` after `pair` in `paired`), cell-aware `Lobby.pair`, in-flight reservation and release, completion hook, `pairing.fallback`, scenario fit for `by_participant`, `used_assistants`, the new result columns of §5, the Paired part of `hani2 study balance` | `matches.py`, `session.py` (≈1655–1765, `_leave_match`, end of round), `assignment.py` (cell store), `results.py` (columns), `events.py` | new `tests/test_pairing_cells.py` (hard guarantees, dead-end fallback, abandon releases, concurrency with two joiners), `tests/test_human_opponents.py`, `tests/test_session.py` | `docs/guide/human-opponents.md` (Paired section), `scheduling.md` (Paired note) |
| **4. Evaluation** | Paired cells per row, match dedup, same-Assistant collapse, `ci_unit: match`, the `study_mode` strata, the HAN `vs_team` stratum, `excluded["human opponent"]`, optional head-to-head | `evaluation/__init__.py` (`ID_FIELDS`), `evaluation/tracks.py`, `evaluation/base.py` | `tests/test_tracks.py` | `docs/guide/evaluation.md` |
| **5. Game board backend** | The `hi_score` Score, the `leaderboard` config block, `evaluation/game_board.py` (filters, caps, minimums, categories), the eval cache (written at row save), `hani2 leaderboard refresh/judge`, the endpoint `/api/v1/leaderboards/{hi,han}`, API-token auth, the new group-file keys `entrant`, `own`, `han_year` | `evaluation/scores.py`, new `evaluation/game_board.py`, `projects.py` (`leaderboard` key), `server.py`, `sso.py` (`verify_api_token`), `groups.py`, `results.py`, `cli.py` | new `tests/test_game_board.py`, `tests/test_server.py` (endpoint, 401/403/400), `tests/test_sso.py` (audience separation), `tests/test_groups_and_assignment.py` | new `docs/guide/leaderboards.md` (added to the `mkdocs.yml` nav), `human-opponents.md#a-game`, `authentication.md` (API tokens) |
| **6. Help mechanism and editor** *(frontend)* | `help_texts.py` and `/api/admin/help`; `Row.help`, `Field.help`, the shared `HelpDialog`; the Mode, HAN picker, Assignment, Pairing and Leaderboard rows in `Projects.tsx`; the generated settings reference; rebuild `src/hani2/web` | `src/hani2/help_texts.py`, `server.py`, `frontend/src/admin/{Row,schema}.tsx`, `frontend/src/ui/HelpDialog.tsx`, `frontend/src/negotiate/ToolPane.tsx` (use it), `frontend/src/admin/pages/Projects.tsx`, `src/hani2/web/**` | `tests/test_admin_api.py` (help coverage of `REQUIRED`), `frontend/tests/help.test.mjs`, `tests/e2e` (open a `?`, save a contradiction and get a 400) | `docs/guide/admin.md`, `projects.md` (generated reference) |
| **7. Leaderboards admin page** *(frontend, after WP6)* | The page with source, category, games and strata switches, unranked entrants and exclusions; rebuild `src/hani2/web` | `frontend/src/admin/pages/Leaderboards.tsx`, `Sidebar.tsx`, `src/hani2/web/**` | `tests/e2e` (switch categories) | `docs/guide/leaderboards.md` |
| **8. scmlweb** *(other repo, after WP5)* | Read the endpoint and make it the default HI board with the Tournament tab; write `entrant` and `own`; update `resources/hani2/projects/hi-game` | scmlweb | scmlweb's | scmlweb's |

WP1 → WP2 → WP3 → WP4 → WP5 are backend only and in dependency order. WP4 and WP5 could be swapped,
but WP5 reuses WP4's strata. WP6 can start once WP1–WP3 have fixed the keys. WP7 follows WP6.

---

## 11. Decisions for the user

Each question has a recommended answer.

| # | Question | Recommended |
|---|---|---|
| D1 | Should the new setting be called `study_mode` (`mode` is taken by `simulated`), with the values `solo`, `paired` and `mixed`? | **Yes.** The UI says "Mode: Solo / Paired / Mixed" |
| D2 | Should Solo K-of-N with K < N use the new `balanced_subset` (balanced co-occurrence), or is `latin_square` enough? | **`balanced_subset` for K < N**, and `latin_square` for K = N (the finals) |
| D3 | Should the Assistant × opponent crossing (`cross: shift`) be on by default for new studies? It fixes the confounding P1 | **Yes**, stored per human so that running studies do not change |
| D4 | In Paired, should a person's Assistants be a *set* (the order is only a preference), so that the cell balance can work? | **Yes.** Strict order (`assign: order`) stays available for scripted lab sessions |
| D5 | When nobody fits in Paired: should the fallback default to playing an AI opponent with the planned Assistant, counting it as used, filling no cell and being ranked under Solo? | **Yes** (`fallback: ai`). Prolific participants are paid for the time anyway |
| D6 | Should the game ask a short questionnaire so that HI-score can include subjective scales? | **Yes: 4 items, optional, after every 3rd game**, starting at weight 0 until enough people answer |
| D7 | Game board adjustment: cell-adjusted means (`relative`) or the cell-balanced mean? | **`relative`**, because the game's cells are sparse and uneven. Cell-balanced for planned studies |
| D8 | Should games where a team plays its own Assistant count? | **Count them, but require `min_participants: 3` players who are not the owners.** `exclude_own` stays available |
| D9 | Endpoint auth: a JWT on the existing SSO secret, or a public board (no names in it)? | **The JWT** (`aud: hani2-api`). The board can be made public later with `leaderboard.public` |
| D10 | Should scmlweb pull from the endpoint, or should hani2 push tournament-style results? | **Pull**, cached on `data_version` |
| D11 | Should same-Assistant matches (an inviter against their guest) be out of the utility category but counted once in HI-score? | **Yes.** They are not allowed at all in Paired evaluation studies |
| D12 | Where do HAN entrants come from: the installed `han-agents` package or scmlweb's `agent_placements` and zips? | **The package for `:han<year>-*`**, with `hani2 han check` comparing it to scmlweb's list. Group files from scmlweb can still name the zips |
| D13 | Should the HAN board show HI-Solo games against HAN agents as a separate `vs_team` stratum next to the official `alone` board, never pooled by default? | **Yes** |
