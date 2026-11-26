# Human opponents

A project or study chooses who its participants negotiate against:

| Opponents | Pool entry | The other side is |
|-----------|------------|-------------------|
| AI agents | agent specs and groups (see [Opponents](opponents.md)) | an automated opponent |
| Human | `human` | another participant, without an Assistant |
| Human with an Assistant | `human+assistant` | another participant, with their own Assistant |

Write the entry in the pool like any opponent: in `study.yaml` or `project.yaml`
(`opponents: [human+assistant]`), in the admin console (**Opponents → Opponents participants face**,
where both entries are listed first), with `--opponents human` or, for admins, `?opponents=human`. In a URL, `?opponents=human+assistant` works
as written: the `+` becomes a space there, and `human assistant`, `human_assistant` and
`Human + Assistant` all mean the same entry. A
pool can mix them with agents (`opponents: [human, :pan]`); every negotiation then draws one entry as usual,
and scheduling methods treat `human` like any other pool member.

Each participant keeps their own page, tools and Assistant. Whether a participant has an Assistant is
decided as always (the study's Assistant settings, its Assistant pool and balance). The opponent entry
only says what the *other* side must be.

## Pairing

When a participant's next opponent is `human` or `human+assistant`, HANI2 pairs them as their scenario loads:

1. If someone is waiting who fits, the participant joins them. They take the same scenario and the other
   side of it, whatever the role rules would have chosen.
2. Otherwise the participant loads their scenario as usual and waits for someone to join.
3. The negotiation starts once both have pressed **Start** (or were started by the study). Until then the
   page shows *Waiting for the other participant…*.

Two people fit when each is what the other asked for. A participant who asked for `human` needs someone
without an Assistant, and one who asked for `human+assistant` needs someone with one. The common designs:

| Design | How to set it up |
|--------|------------------|
| Team against team | One study with an Assistant and `opponents: [human+assistant]` |
| Human against human | One study without an Assistant and `opponents: [human]` |
| Team against a human alone | Two studies of one project. The team study has an Assistant and `opponents: [human]`. The solo study has no Assistant and `opponents: [human+assistant]` |

One study whose participants all have an Assistant and want `human` opponents, or all lack one and want
`human+assistant`, cannot pair its participants with each other. HANI2 logs a warning (an `error` event
`unpairable_alone`). Its participants meet only another study's, and otherwise get the fallback below.

A participant who is still answering the consent form or pre-questionnaire of their first negotiation
can be joined. The other side waits until they press **Start**.

People are paired within a project, so its studies can be paired with each other. Links with
`?match=<code>` pair only people who share that code, whatever their project. Use this for sessions
arranged in advance or for testing.

!!! note "One server process"
    The waiting room lives in the server's memory. HANI2 runs a single server process (`hani2` starts
    uvicorn with one worker), so everyone on one server can meet.

## When nobody comes, or someone leaves

- **Nobody joins.** After `human_opponent_wait` seconds (an admin setting, default `120`; `0` waits
  forever), the participant gets an AI opponent from the rest of the pool, or from the default pool when the
  pool holds only human entries. A notification tells them. Set `human_opponent_fallback` to `false` to
  keep waiting instead.
- **Someone does not press Start.** When one side has pressed **Start** and the other has not within
  `human_opponent_wait` seconds, they are separated. The side that pressed waits for someone else. The
  other keeps its scenario and side, and waits for someone new.
- **Someone leaves before the start.** The other participant waits for someone else.
- **Someone leaves during the negotiation.** A participant has left when their session closes, or when
  they have had no open page for `human_opponent_absent` seconds (an admin setting, default `60`). A reload
  or a short network drop does not count. Their side then ends the negotiation on its next turn. The other
  participant sees *The other participant left the negotiation*, and the negotiation ends without
  agreement. A time limit (`time_limit`) also ends negotiations where one side stays on the page but
  stops acting. Use one for studies with human opponents.

## Turns and time

The two participants take turns. The side whose turn it is acts as usual (offer, accept, end, messages,
the Assistant, autopilot). The other side sees *Your opponent is deciding…*. The time limit and the
number of rounds are the waiting participant's, the one whose scenario is used. Each side's own timer
acts for that side when time runs out.

## Results

Each participant gets their own row in `results.csv`, from their own side:

| Column | Value |
|--------|-------|
| `agent_type`, `opponent_kind` | `human` or `human+assistant` (what the other side actually was), else `agent` |
| `match_id` | Shared by both participants' rows (empty for AI opponents) |
| `opponent_user` | The other participant's user name |
| `mechanism_id` | Shared by both rows too, as are the negotiation log and the trace |
| `agent_utility` | The other participant's utility |
| `abandoned` | `self` (this participant left), `opponent` (the other one left), else empty. `ended_by` stays `human` / `agent` as for AI opponents |

The participant who joined keeps their own plan columns (such as `scenario_scheduling`), although the
scenario is the one the waiting participant loaded. A study that falls back to AI opponents has rows with
`opponent_kind` `agent`. A participant whose session was closed gets no row.

When you analyse a study, count each `match_id` once for negotiation-level measures (agreement rate,
welfare). Use both rows for participant-level measures.
