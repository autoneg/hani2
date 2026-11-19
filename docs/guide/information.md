# Who knows what

By default the human and the Assistant know the same kind of things: the human's preferences,
the scenario and everything that happens in the negotiation. To study how a person and an AI
collaborate, you can give them **different information**, so that each holds something the
other needs. The `information` setting does this, per project, per study or for the whole
server.

It can split these kinds of information:

| What | Example |
|------|---------|
| [Past negotiations](#past-negotiations) | Records of earlier negotiations in the same scenario. The human gets some of them and the Assistant gets the rest. |
| [Preferences](#preferences) | The human knows how important each issue is (the weights), and the Assistant knows what each option is worth (the values). |
| [Market research](#market-research) | Only the Assistant knows how preferences in this scenario are usually distributed, as if it had done a market study. |
| [Private briefings](#private-briefings-and-hidden-constraints) | Only the human is told "your manager will not approve a rent above 3200", a limit that is not in their preferences. The Assistant has to ask. |
| [Decisions only the human makes](#decisions-only-the-human-makes) | The Assistant may suggest a price or suggest accepting, but only the human can set the price or accept. |

Each part can be used alone or together with the others. When nothing is set, nothing is split
and HANI2 behaves exactly as before.

## Setting it

Put an `information` block in a study's `study.yaml`, a project's `project.yaml`, or
`env.json` → `negotiation`. Only the keys you give change. A study's block replaces its
project's block as a whole, as with every other study setting.

```yaml title="projects/HI2027/studies/split-01/study.yaml"
information:
  past_negotiations:
    count: 6            # six past negotiations per scenario
    human_share: 0.5    # three for the human, three for the Assistant
  preferences:
    human: weights      # the human sees the issue weights
    assistant: values   # the Assistant knows what each option is worth
  market_research:
    audience: assistant
```

In the [admin console](admin.md), the project and study forms under *Projects* have an
*Information split* section with the most-used keys. Edit the file for the others.

All the keys and their defaults:

```yaml
information:
  past_negotiations:
    count: 0                 # how many past negotiations each scenario has (0: none)
    preferences: similar     # similar | same | different: how the past parties' preferences relate to this one's
    opponent_preferences:    # the same, for the opponent's side only (empty: as preferences)
    noise: 0.25              # how far "similar" preferences move (0 to 1)
    human_share: 0.5         # the fraction for the human; the Assistant gets the rest (0: all to the Assistant, 1: all to the human)
    shared: false            # true: both get every record
    assignment: random       # random (per participant and round) | first (the human gets P1, P2, ...)
    utilities: own           # what a record shows: own (the utilities of the party in the human's role) | both | none
    n_steps: 20              # rounds of a simulated negotiation
    negotiators: [BoulwareTBNegotiator, LinearTBNegotiator, ConcederTBNegotiator, NaiveTitForTatNegotiator]
    use_scenario_file: true  # use the scenario folder's _past_negotiations.yaml when it has one
    seed: 0
  preferences:
    human: full              # full | weights | values | none: what the human knows of their own preferences
    assistant: full          # the same, for the Assistant
    reserved_value: both     # both | human | assistant | none: who knows the value on disagreement
    show_totals_to_partial: false  # show deal values to a side that knows only part of the preferences
  market_research:
    audience: none           # none | assistant | human | both
    sides: opponent          # opponent | own | both: whose preferences it describes
    samples: 40              # how many comparable profiles the statistics come from
    noise: 0.3               # how spread out those profiles are
  briefing: []               # private instructions, added to the scenario's own (see below)
  use_scenario_briefing: true   # use the briefing in the scenario's _info.yaml
  briefing_audience:         # human | assistant | both: give the scenario's briefings to this side instead
  control:
    human_only_issues: []    # issues only the human may set
    human_only_actions: []   # any of send, accept, end: actions only the human may take
```

## Past negotiations

A past negotiation is a record of an earlier negotiation in the **same scenario**. The party in
the human's role had preferences like the human's, and its opponent had preferences like the
opponent's. A record has every offer, who made it, how the negotiation ended and (by default)
what each offer was worth to the party in the human's role, by that party's own preferences.

`preferences` says how alike the past parties are:

- `similar` (the default): the weights, the option values and the value on disagreement move by
  about `noise`.
- `same`: exactly this negotiation's preferences.
- `different`: unrelated random preferences over the same issues.

`opponent_preferences` sets the opponent's side on its own, for example
`preferences: same, opponent_preferences: different`.

### Where the records come from

When the scenario folder has a `_past_negotiations.yaml`, its records are used, the first
`count` of them. Otherwise HANI2 simulates `count` negotiations when the scenario is loaded,
played by the negmas negotiators in `negotiators`. A simulation is deterministic: the same
scenario and settings always give the same records. So in a [strict study](scenarios.md#strict-scenarios)
every participant who meets a scenario sees the same records. To fix the records once and for
all, or to edit them, write them into the scenario folders:

```bash
hani2 scenario past ~/negmas/hani2/settings/scenarios/Lease --count 6
hani2 scenario past ./Lease/0003 --count 4 --human-role Tenant --opponent-preferences different
```

`--force` replaces an existing file. The file is plain YAML. You can add a `notes` text to a
record, or write records of real negotiations by hand:

```yaml title="Lease/0003/_past_negotiations.yaml"
negotiations:
- id: P1
  roles: [Landlord, Tenant]
  styles: {Landlord: tough (Boulware), Tenant: conceding}
  steps: 12
  agreement: {Rent: 3200, Deposit: 2000, Move-in date: 1 June, Lease length: 1 year}
  utilities: {Landlord: 0.71, Tenant: 0.55}
  offers:
  - {step: 0, by: Landlord, offer: {Rent: 3600, Deposit: 4000, Move-in date: 1 May, Lease length: 2 years},
     utilities: {Landlord: 1.0, Tenant: 0.0}}
  # ...
  notes: The tenant gave in on rent to get the move-in date.
```

### Who gets which

`human_share` decides how many records the human gets. With `assignment: random` each
participant gets a random share that is fixed for that participant and round. `shared: true`
gives every record to both.

The human sees their records in the **Past Negotiations** tool: a table of the records, and
for the one picked, its offers in a chart and a table. The tool tells them how many records
their Assistant has. The Assistant reads its own records with `get_private_information` (a
summary of each) and `show_past_negotiation` (every offer of one). It knows the ids the human
holds but not what is in them, and it cannot read the human's tool (unless every record in it is
one the Assistant holds as well).

## Preferences

`preferences.human` and `preferences.assistant` say how much each side knows of the human's
utility function:

| Value | Means |
|-------|-------|
| `full` | Everything (the default). |
| `weights` | How important each issue is. |
| `values` | What each option of each issue is worth. |
| `none` | Nothing. |

For example, `human: weights, assistant: values` gives each side one half. The human's
*Preferences* tool then shows only the issue weights, with a note that the Assistant knows the
option values. `get_private_information` gives the Assistant the option values.

A side that does not know the full function cannot see what a deal is worth to the human, and
HANI2 hides these numbers from it:

- **The human** loses the utility gauges on the offer on the table and on their draft, and the
  utilities in the history. The tools that show deal values are not offered: Utility Plot,
  Negotiation Plot, Trace, Utility Selector and Response Generator. The counter-offer fields
  are not filled with the human's best deal, and the scenario hints are hidden, because they
  are worked out from the preferences.
- **The Assistant** gets no utilities in the negotiation state, and the scenario hints are
  hidden from it as well.
- **Past negotiations** show no utilities to a side that cannot see deal values, whatever
  `utilities` says, since with `preferences: same` they would be the real values.

Set `show_totals_to_partial: true` to show deal values to a side that knows only part of the
preferences.

`reserved_value` says who knows the value on disagreement. The human's *Preferences* tool shows
"Unknown" when they do not know it, and the Assistant's state leaves it out when it does not.

Weights and values exist only for preferences that are a weighted sum of issue values, which
is true of every built-in scenario type. For other preferences HANI2 cannot split them: both
sides know them fully, and admins get a warning when the scenario is loaded.

## Market research

Market research tells what parties in this scenario usually want. For each role it covers
(`sides`), it gives:

- the typical weight of each issue, with its spread;
- the option of each issue that is most often the best, and how often;
- the most likely best deal;
- the usual value on disagreement.

It is computed from `samples` other scenarios of the same type: new ones from the type's
generator, or the saved scenarios of the category when the type has no generator. So it
describes the population the preferences are drawn from, not this opponent. A one-off scenario,
with neither a generator nor at least two saved scenarios, falls back to profiles near the real
preferences (`noise` says how near). These are close to the opponent's own preferences, and admins
get a warning when the scenario is loaded. A scenario can add its own text under
`market_research` in `_info.yaml`, either one text or one per role:

```yaml title="_info.yaml"
market_research:
  Landlord: Landlords in this district rarely lower the rent but often waive the deposit.
```

With `audience: assistant` it reaches the human only through what the Assistant tells them.
With `audience: human` the human gets a **Market Research** tool.

## What the Assistant is told

When the two sides know different things, the negotiation state the Assistant reads with every
message has an `information` section. It says what each side knows and which past negotiations
the human holds, but not their contents. The Assistant's instructions tell it to call
`get_private_information` and to ask the participant about what only they know.

The new ability `private_info` (*Its own information*) unlocks `get_private_information` and
`show_past_negotiation`. Both are offered only in rounds where something is split. Like every
ability, participants can switch it off when the interface allows it. See the
[Assistant guide](assistant.md#capabilities).

Python Assistants can read `self.session.human_ufun` directly, and HANI2 cannot stop that. To
keep to the study's design, use the helpers instead:

```python
class MyAssistant(Assistant):
    def on_event(self, event_name, nmi=None):
        if event_name == "negotiation_started":
            mine = self.private_information()  # what only the Assistant knows
            for rec in mine.get("past_negotiations_you_hold", []):
                full = self.past_negotiation(rec["id"])["negotiation"]
                ...
```

`self.session.information` is the round's `InformationState`. It says which part of the
preferences each side knows (`human_prefs`, `assistant_prefs`), which past negotiations each
holds (`human_past`, `assistant_past`) and whether deal values may be shown
(`human_sees_totals`, `assistant_sees_totals`).

Tools can depend on the split too. A tool with `needs_totals = True` is not offered while the
human cannot see deal values. A tool with `private_information = True` cannot be read or used
by the Assistant while the two sides know different things; override `private_now()` to refuse
it only when it shows something the Assistant does not know. *Preferences* does this: with only
past negotiations split, the Assistant still reads it. Override `available()` to offer a
tool only in some rounds. See [Tools](tools.md).

!!! note "Negotiator autopilot"
    An [autopilot](autopilot.md) driven by a negotiator plays with the human's full
    preferences. In studies that split the preferences, use the Assistant as the autopilot
    driver, or turn the autopilot off.

## Private briefings and hidden constraints

A briefing is a private instruction for one side, such as a limit set by someone the human
negotiates for, or a preference that is not in the utility function. A scenario writes its
briefings in `_info.yaml`, per role. A study can add its own under `information.briefing`.

```yaml title="_info.yaml"
briefing:
  Tenant:
    text: Your family insists on a one-year lease; anything else needs their approval.
    constraints:
      - {issue: Lease length, allowed: [1 year]}
  Landlord:
    to: human              # human (default) | assistant | both
    text: The bank needs the rent to be at least 3000.
    constraints:
      - {issue: Rent, min: 3000}
```

Only the briefing for the role the participant plays is used. An entry is a text, a mapping with
`text`, `to`, `constraints` and `pin`, or a list of those. Without a `text`, the constraints are
written out in words. A constraint names an `issue` and any of `min`, `max`, `allowed` (a list of
options) and `forbidden`.

- A briefing **for the human** is shown in the **Briefing** tool and pinned above the negotiation
  when it starts (`pin: false` turns that off). The Assistant cannot read it. It is told only that
  the participant has a private briefing and that it should ask them about it.
- A briefing **for the Assistant** reaches it through `get_private_information`.
- `briefing_audience` redirects a scenario's briefings, so one scenario serves several
  conditions: `assistant` gives the human's limit to the Assistant instead, and
  `use_scenario_briefing: false` leaves it out for a control group.

The constraints are checked against the agreement, on the raw option values. Each results row has
`constraints_met`: 1 when the agreement keeps every constraint, 0 when it breaks one
(`constraint_violations` counts the broken ones), and empty without an agreement. The `dual_control`
[evaluation metric](metrics.md) gives the same from a recording.

Briefing texts stay out of the scenario once a round is set up: the opponent, the tools and the
saved copy of the scenario never see them, and the results row names briefings only by id
(`B1:human`). The recording keeps the texts. Nothing stops a participant from
breaking a limit, so the column shows whether the information reached the decision.

## Decisions only the human makes

`control` keeps some decisions for the human. The Assistant may only suggest them:

```yaml
information:
  control:
    human_only_issues: [Price]     # the Assistant cannot fill these in
    human_only_actions: [accept]   # nor take these actions: send, accept, end
```

- When the Assistant fills in the offer, the human-only issues keep the participant's values, and
  the Assistant is told so.
- A human-only send, accept or end by the Assistant becomes a suggestion: it fills in the offer
  and highlights the button, whatever its autonomy level. Because sending or accepting decides
  every issue, a human-only issue makes sending and accepting the participant's decision too. The session also refuses these actions
  from Python Assistants.
- The negotiation state marks each human-only issue with `only_the_participant_may_set`. The
  participant sees the rules in the Briefing tool and in a pinned note.
- The [autopilot](autopilot.md) is not restricted, because the participant handed it the
  controls.

## In the results

When something is split, each results row has these columns:

| Column | Content |
|--------|---------|
| `information_split` | `True` |
| `info_human_preferences`, `info_assistant_preferences` | What each side knew of the preferences. |
| `info_human_reserved_value`, `info_assistant_reserved_value` | Whether each side knew the value on disagreement. |
| `info_past_negotiations`, `info_past_source` | How many records there were, and where they came from (`scenario` or `simulated`). |
| `info_human_past`, `info_assistant_past` | The ids each side held. |
| `info_market_research` | Who got the market research. |
| `info_briefings` | The briefings by id and audience (`B1:human,B2:assistant`). |
| `constraints_met`, `constraint_violations` | Whether the agreement kept the briefings' constraints, and how many it broke (see [above](#private-briefings-and-hidden-constraints)). |
| `info_human_only_issues`, `info_human_only_actions` | What only the human could set or do. |

The [recording](recordings.md) of the negotiation keeps the same data and the records
themselves, under `information` in its scenario entry. The scenario-loaded event has it too.
