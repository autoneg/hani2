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

An outside system's schedule works the same way: `agent_class_name: human+assistant` in a
`schedule.json` slot, or the entry in a group file a `?group=` link names. Practice rounds use the
practice opponents as before.

Each participant keeps their own page, tools and Assistant. Whether a participant has an Assistant is
decided as always (the study's Assistant settings, its Assistant pool and balance). The opponent entry
only says what the *other* side must be.

!!! tip "Try it on one machine"
    `hani2 human-trial` starts a trial server and opens two linked pages, one per participant, in
    your browser. See [`hani2 human-trial`](../getting-started/cli.md#hani2-human-trial).

The bundled welcome text (`announcements.md`) speaks of an AI opponent. A study with human opponents
should have its own `announcements.md` that says the other side is a person.

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

People are paired within a project, so its studies can be paired with each other. When several
people who fit are waiting, the newcomer joins one of them at random, so nobody can aim at a
particular person. Links with `?match=<code>` pair only people who share that code, whatever their
project. Use this for sessions arranged in advance or for testing. A study that sets
`human_opponent_codes: false` ignores `?match=` for everyone but admins.

### A person first, any person

By default each negotiation draws one entry from the pool, so a pool such as
`[human+assistant, human, :pan]` gives an AI opponent in most negotiations. A participant who
drew `human` also never meets someone with an Assistant. With `human_opponents_first: true`
(a study or admin setting), every negotiation looks for a person first:

- the participant takes **any** human kind the pool lists. With `[human+assistant, human, :pan]`
  that is someone with or without an Assistant. The other side's wishes still apply: someone who
  takes only `human+assistant` opponents meets only a participant with an Assistant;
- the pool's AI entries are used only for the fallback after `human_opponent_wait` seconds, and for
  *Play an AI opponent now* (below).

### Choosing a person or an AI

With `human_opponent_choice: true` (a study or admin setting), or `?opponent_choice=1` on the page,
a participant whose next opponent may be a person first chooses:

- **Play a person.** The button shows how many people who fit are waiting right now. The participant
  joins one of them directly when someone fits, and otherwise waits as described above.
- **Play an AI opponent now.** An opponent from the rest of the pool, with no waiting.

Nobody is paired before the choice, and the negotiation cannot start until it is made. While
waiting for a person, the page offers **Play an AI opponent instead** (also without the choice
screen, unless `human_opponent_fallback` is `false`). It leaves the waiting room and starts with an
AI opponent.

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

## What participants see

Each participant sees only their own side. The page, the tools and the Assistant never get the other
participant's preferences, value on disagreement or utility (the `opponent_utility` capability, the
opponent's preferences tool and the real-utility views of the negotiation plot give nothing while the
opponent is a person). They also never get the other participant's user name, chats, Assistant output
or the match id. The result of the negotiation leaves out the other side's utility. **My Results** drops
`opponent_user` and `match_id` and blanks the other side's values in those rows. All of these stay in
`results.csv` for analysis. To keep participant-written Assistants from reading any of this in the
server's memory or files, run them [isolated](assistant.md#isolated-assistants).

The page says when the opponent is another participant: the waiting messages, a person icon instead
of a robot, and `opponent_kind` in the page state. This holds whatever `show_opponent_type` says. While
paired, a participant cannot change their Assistant (it decides who fits whom). Where participants may
pick their opponent ([What participants may choose](configuration.md#what-participants-may-choose)),
the list never shows `human` or `human+assistant`, and picking an AI opponent leaves the waiting room.

## Turns and time

The two participants take turns. The side whose turn it is acts as usual (offer, accept, end, messages,
the Assistant, autopilot). The other side sees *Your opponent is deciding…*. The time limit runs from the moment both have started. The time limit and the
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
| `invited_by` | For a guest who came through an invitation (see [Guests](authentication.md#guests)): who invited them, else empty |

The participant who joined keeps their own plan columns (such as `scenario_scheduling`), although the
scenario is the one the waiting participant loaded. A study that falls back to AI opponents has rows with
`opponent_kind` `agent`. A participant whose session was closed gets no row.

When you analyse a study, count each `match_id` once for negotiation-level measures (agreement rate,
welfare). Use both rows for participant-level measures.

## A game

A *game* is a study, outside any evaluation, where people play each other with their Assistants
whenever they like, and may invite friends. Its results are kept apart from the study the
participants' Assistants were submitted to. A complete configuration:

```yaml title="projects/arena/project.yaml"
full_name: Negotiation arena
kind: none                 # not an evaluation
defaults:
  practice: false
  time_limit: 600          # every game ends, also when one side stops acting
  opponents: [human+assistant, human, ":pan"]
  questionnaires: false    # no questionnaire, whatever the server's environment names
```

```yaml title="projects/arena/studies/play/study.yaml"
type: online
title: Arena
```

```json title="projects/arena/studies/play/env.json"
{
  "negotiation": {
    "human_opponents_first": true,
    "human_opponent_choice": false,
    "human_opponent_codes": false,
    "human_opponent_wait": 120,
    "human_opponent_fallback": true,
    "human_opponent_absent": 60,
    "assistant_isolation": "process",
    "show_opponent_type": false
  }
}
```

- Participants come from a trusted website through the [sign-in hand-off](authentication.md#sign-in-from-a-trusted-website),
  with `next=/app?study=arena/play&group=<key>`. The group file names their Assistant (`"assistant":
  "<spec>"`, or `"none"` for no Assistant) and the pool. When the group file lists `agents`, they
  replace the study's `opponents`, so write the human entries there too.
- People they invite get a [guest](authentication.md#guests) hand-off with `&opponent_choice=1`. They
  choose between a person and an AI, and play with the inviter's Assistant.
- Logged-in accounts play as many games as they like. After a game, *Next negotiation* starts another,
  and so does a new hand-off from the website.
- `assistant_isolation: process` runs participant-written Assistants in a sandboxed worker process,
  and refuses to run one where no sandbox is available (`assistant_sandbox` stays `required`).
- `time_limit` (not `counted_time_limit`, which only Prolific and `?pid=` participants use) limits
  each game of a logged-in account; `n_required` and `end_text` do not apply to them.
