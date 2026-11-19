# Evaluation metrics

Every [recording](recordings.md) can be evaluated with optional metrics of four kinds:

- **hard** — computed from the log alone;
- **subjective** — the participant's own answers to the questionnaire;
- **soft** — judged by a language model from the transcript (opt-in, because it costs calls);
- **score** — computed from the others: whether the session met its scenario's
  [evaluation criteria](scenarios.md#evaluation-criteria), and the combined scores of the two
  competition tracks, which the [leaderboards](#tracks-and-leaderboards) rank.

The same metrics evaluate human participants, the Assistant and opponents:
compare recordings grouped by any of them.

Run them in the [replay tool](recordings.md#the-replay-tool), with `hani2 replay evaluate` /
`hani2 replay compare`, or from Python:

```python
from hani2.evaluation import evaluate_paths, compare_rows

res = evaluate_paths(["results/"], metrics=["outcome", "optimality", "system_use"])
res["rows"]       # one row per recording
compare_rows(res["rows"], by="support_agent")
```

`hani2 replay metrics` lists every metric and column. The [metric reference](metrics.md) explains
each of them: what it measures, its formula, how to read it, a worked example and the caveats. The
same texts are shown by `hani2 replay metrics --details [NAME]` (a metric, a column or a `compare`
statistic, e.g. `hani2 replay metrics --details nash_distance`), by the ⓘ buttons and the **Metric
reference** panel of the replay tool, and by `GET /api/replay/metric-reference` (admins).

## Hard metrics

| Metric | Columns | Measures |
| --- | --- | --- |
| `outcome` | `agreement`, `status`, `ended_by`, `human_utility`, `opponent_utility`, `human_advantage`, `opponent_advantage`, `welfare`, `practice` | Whether there was a deal and what it was worth to each side. *Advantage* is `(u − reserved) / (max − reserved)`. |
| `optimality` | `pareto_distance`, `pareto_optimal`, `nash_distance`, `kalai_distance`, `welfare_optimality`, `nash_product_ratio`, `fairness_gap` | Distance of the result from the Pareto frontier and from the Nash and Kalai–Smorodinsky solutions, welfare relative to the best possible, and how evenly the gains were shared. |
| `scenario_stats` | `n_outcomes`, `zopa_fraction`, `pareto_size`, `opposition` | How large and how competitive the scenario is (not run by default). |
| `length` | `n_offers`, `n_human_offers`, `n_opponent_offers`, `n_steps`, `relative_time`, `negotiation_seconds`, `session_seconds`, `n_text_messages` | How long it took. |
| `llm_usage` | `llm_calls`, `llm_tokens`, `llm_cost_usd`, `llm_latency_mean`, `llm_error_rate`, and per role (assistant, opponent) | Language-model use — tokens as a proxy for energy, cost when the provider's price is known. |
| `dynamics` | `human_move_*`, `opponent_move_*`, `suggested_move_*` (silent, nice, fortunate, unfortunate, concession, selfish), `human_concession`, `human_offer_pareto_distance`, `tom_reflect_index`, `tom_other_trend` | The type of each move — the human's, the opponent's and the assistant's suggestions — and how quickly the human's offers take the other side's interests into account (theory of mind). |
| `timing` | `decision_time_mean`, `decision_time_median`, `decision_time_min`, `time_to_first_action`, `load_to_start_seconds`, `questionnaire_seconds` | Time per decision (from the start of the human's turn to their action) and overall. |
| `activity` | `n_clicks`, `n_keys`, `mouse_distance`, `n_scrolls`, `idle_fraction`, `hidden_seconds`, `n_blur`, `has_telemetry` | Low-level interaction and attention (time away from the page). |
| `system_use` | `n_user_messages`, `n_assistant_messages`, `n_suggestions`, `suggestion_adoption`, `suggestions_ignored`, `drafts_explored`, `drafts_per_action`, `n_tool_interactions`, `n_tools_used`, `n_tab_changes`, `actions_by_human`, `actions_by_agent`, `actions_by_autopilot` | How the assistant and the tools were used: messages, suggestions and how often the human sent exactly what the assistant suggested, how many counter-offers they explored before acting, who acted. |
| `engagement_flags` | `never_acted`, `click_through`, `always_follows`, `never_follows` | Sessions to inspect or remove: a participant who never acted, clicked through as fast as possible without exploring offers, always sent the assistant's suggestion, or never took one. Option `click_through_seconds` (default 3). |
| `rule_checks` | `irrational_accept`, `opponent_irrational_accept`, `irrational_suggestions`, `opponent_failed`, `infrastructure_failure` | Mistakes the utility table proves (accepting or suggesting a deal worth less than no deal) and sessions that failed because of the opponent agent or the system. |
| `assistant_interaction` | `assistant_response_seconds`, `unanswered_messages`, `unsolicited_messages`, `max_assistant_streak`, `fn_calls`, `fn_success_rate` | The assistant in conversation with the participant: responsiveness, unanswered messages, proactive messages, monologues and how often its function calls worked. |

Move types follow the usual negotiation-dynamics classification: a move is the change from a
side's previous offer to its next one, by the change of its own utility (Δself) and of the other
side's (Δother): **silent** (no change), **nice** (Δself = 0, Δother > 0), **fortunate** (both up),
**unfortunate** (Δself ≤ 0 and Δother ≤ 0, not silent), **concession** (Δself < 0, Δother > 0)
and **selfish** (Δself > 0, Δother ≤ 0). The assistant's suggestions are classified against the
human's previous offer. See the [metric reference](metrics.md#dynamics-negotiation-dynamics) for the
exact rules and a figure.

## Subjective metrics

`questionnaire` turns the answers to the post-negotiation questionnaire into scale scores:
`scale_<name>` (mean on the items' own range) and `scale_<name>_norm` (0–1); numeric answers to
questions without a scale become `q_<id>`.

HANI2 ships an evaluation questionnaire with:

| Scale | Items |
| --- | --- |
| `satisfaction`, `appreciation` | Satisfaction with the outcome; enjoyment. |
| `ueq_pragmatic`, `ueq_hedonic` | Eight 7-point UEQ items about the assistant. `ueq_pragmatic`: not understandable–understandable, obstructive–supportive, complicated–easy, inefficient–efficient, clear–confusing, impractical–practical (perspicuity, dependability and efficiency items). `ueq_hedonic`: valuable–inferior and good–bad. Items whose positive pole comes first are scored backwards. |
| `tam_usefulness` | Perceived usefulness (TAM): "Using this assistant would enhance my effectiveness in negotiation", "I would find this assistant useful in negotiations". |
| `intention_to_use`, `felt_heard` | "I would use this assistant again"; "I felt heard by the assistant". |
| `opponent_kindness`, `opponent_intelligence`, `opponent_humanlike` | How kind and intelligent the opponent was, and whether it seemed human or AI. |
| `relationship` | Wanting to negotiate with the opponent again; feeling humanly connected. |

plus free-text questions (insights the assistant gave, comments). Questions about the assistant
(`requires: support_agent`) are skipped when there was no assistant. Use it with

```bash
HANI2_PER_NEG_YAML=evaluation hani2
```

or `"questionnaire": "evaluation"` in `env.json`, or copy
`default_settings/questionnaires/evaluation.yaml` into `<settings>/questionnaires/` and edit it.
In your own questionnaires, add `scale: <name>` (and `reverse: true`) to any question to get a
scale score.

## Soft metrics (language-model judge)

Add `--llm` (command line), tick **Use LLM judge** (replay tool) or pass `use_llm=True`.
The judge reads a transcript of the negotiation with both sides' utilities, the assistant's
messages, suggestions and function calls. It is not told which opponent agent was used, nor the
participant's questionnaire answers, so its judgements are independent of both.

| Metric | Columns | Measures |
| --- | --- | --- |
| `judge_assistant` | `ja_helpfulness`, `ja_explanation`, `ja_opponent_insight`, `ja_user_understanding`, `ja_scenario_explanation`, `ja_capability_disclosure`, `ja_autonomy_respect`, `ja_communication`, `ja_message_improvement`, `ja_overall` (1–7) | The assistant: did it help, explain its recommendations, explain the opponent, understand and check what the human wanted, explain the scenario and its own abilities, leave the human in control, improve their messages? |
| `judge_opponent` | `jo_kindness`, `jo_intelligence`, `jo_cooperativeness`, `jo_human_likeness`, `jo_communication`, `jo_consistency`, `jo_overall` | The opponent as the human experienced it. |
| `judge_human` | `jh_engagement`, `jh_strategy`, `jh_cooperativeness`, `jh_use_of_assistant`, `jh_communication`, `jh_overall` | The human: invested or clicking through, strategy, use of the assistant. |
| `nl_assertions` | `assertions_met`, `assertions_total` | Natural-language statements the session should satisfy, each judged met, not met or not applicable. The defaults check the assistant's explanatory behaviour; set your own (below). |
| `task_judge` | `task_communicated`, `task_assertions_met` | The judged parts of the scenario's [evaluation criteria](scenarios.md#evaluation-criteria): did the Assistant convey the facts it had to, and were the scenario's own assertions met? |
| `error_review` | `assistant_errors`, `assistant_critical_errors`, `human_errors`, `human_critical_errors`, `human_overrode_helpfully`, `human_overrode_harmfully`, `first_critical` | Mistakes of the assistant and of the human with their severity (minor, major, critical = changed the outcome), and whether going against the assistant helped or hurt. |

### Language-model judgements

The judge uses the language model configured for HANI2 ([Language models](llms.md)). To judge
with another one, and to set your own assertions:

```json
{
  "evaluation": {
    "llm": { "provider": "openai", "model": "gpt-4.1-mini", "api_key_env": "OPENAI_API_KEY" },
    "assertions": [
      "The assistant explained why it recommended each offer.",
      "The assistant never pressured the human to accept."
    ]
  }
}
```

Judgements are cached next to each recording (`<id>.eval.json`) per metric, prompt version and
model; use **Refresh** / `--refresh` to ask again.

## Task success and combined scores

| Metric | Columns | Measures |
| --- | --- | --- |
| `task_success` | `task_success`, `task_targets_met`, `task_rules_ok`, `task_components` | Pass/fail against the scenario's [evaluation criteria](scenarios.md#evaluation-criteria): the product of its targets, rules, facts and assertions. Empty for scenarios without criteria. |
| `scores` | `han_outcome`, `han_interaction`, `hi_outcome`, `hi_assistant`, `hi_team`, `hi_interaction`, and `<score>_coverage` for each | The combined scores of the two tracks, each in [0, 1], higher is better. |

Each combined score is a weighted mean of components taken from the other metrics, each mapped to
[0, 1]: ratings of 1–7 become (x − 1)/6, error counts 1/(1 + x), flags 1 − x, advantages are
clipped to [0, 1]. Components without a value are left out, and `<score>_coverage` is the share of
the weight that was present: run the questionnaire and the judge (`--llm`) for full coverage.

| Score | Track · board | Built from |
| --- | --- | --- |
| `han_outcome` | Human-Agent Negotiation · outcome | the opponent's advantage; 0 when the opponent agent failed |
| `han_interaction` | Human-Agent Negotiation · interaction | how participants rated the opponent (kindness, intelligence, human-likeness, wanting to negotiate again, satisfaction), the judge's view of it, no failures, no deal accepted below its own reservation value |
| `hi_outcome` | Hybrid Intelligence · outcome | the participant's advantage (what the team obtained) |
| `hi_assistant` | Hybrid Intelligence · interaction | the judge's view of the Assistant, assertions met, facts conveyed, its errors, suggestions below the reservation value, working function calls, unanswered messages, UEQ, usefulness, felt heard, intention to use |
| `hi_team` | Hybrid Intelligence · interaction | harmful overrides and critical errors of the participant, use of the Assistant (neither ignoring nor blindly following it), engagement, no deal below the reservation value, efficiency of the result |
| `hi_interaction` | Hybrid Intelligence · interaction (ranked) | the mean of `hi_assistant` and `hi_team` |

The [metric reference](metrics.md#scores-combined-scores-han-and-hi-tracks) lists every component
with its weight. Change the weights (a weight of 0 drops a component) in `env.json`, e.g. for a
competition's study:

```json
{"evaluation": {"scores": {"hi_assistant": {"weights": {"ja_overall": 2, "fn_success_rate": 0}}}}}
```

## Comparing

`compare` groups evaluated recordings by a field (`opponent`, `support_agent`, `user`,
`scenario`, `experiment`, …) and reports per group:

- `n`, the **mean** and standard deviation of every numeric column;
- a **scenario-balanced** mean: averaged within each scenario first, so a group that played more
  of an easy scenario is not favoured;
- **pass^k** reliability: the chance that *k* sessions of the group, drawn from the same
  scenario, *all* succeed (success = a deal by default; set `--option success=human_advantage
  --option success_threshold=0.5` for another criterion). pass^k comes from τ-bench (Yao et al.,
  2024): pass^1 is the success rate, and a fast drop with *k* shows an inconsistent agent.

## Tracks and leaderboards

The two competition tracks each have two leaderboards, or **boards**:

| | Human-Agent Negotiation (`han`) | Hybrid Intelligence (`hi`) |
| --- | --- | --- |
| Sessions | without an Assistant | with an Assistant |
| Entrants | opponent agents | Assistants (with their language model) |
| Outcome board | `han_outcome`: what the agent obtained | `hi_outcome`: what the participant and the Assistant obtained |
| Interaction board | `han_interaction`: how well it behaved as an opponent | `hi_interaction`: how well it worked as an Assistant (`hi_assistant`) and how well the team worked (`hi_team`) |
| Balanced over | scenarios | scenario × opponent cells |
| Left out | practice rounds, abandoned sessions, system failures | the same, and sessions where the opponent agent failed |

In HAN an opponent agent that fails scores 0 for that session; in HI an opponent failure is not the
Assistant's fault and the session is left out.

```bash
hani2 replay leaderboard results/ --track hi --llm             # both boards
hani2 replay leaderboard results/ --track han --board outcome -o han.csv
```

or select recordings in the replay tool and press **Leaderboard**, or from Python:

```python
from hani2.evaluation import evaluate_paths, leaderboards

rows = evaluate_paths(["results/"], use_llm=True)["rows"]
boards = leaderboards(rows, "hi")      # {"outcome": ..., "interaction": ...}
for e in boards["interaction"]["entries"]:
    print(e["rank"], e["entrant"], e["scores"]["hi_interaction"])
```

For every entrant a board reports:

- **rank** by the board's score;
- the **score**: the mean over cells of each cell's mean, so an entrant that met easier scenarios or
  opponents more often is not favoured, with a **95 % confidence interval** from 1000 bootstrap
  resamples of *participants* (sessions of one participant are not independent; with a single
  participant, sessions are resampled);
- the board's other scores (`hi_assistant` and `hi_team` on the HI interaction board);
- **pass^1 … pass^k**: the chance that *k* sessions of the same cell all succeed. Success is
  `task_success` in HI when the scenarios define [evaluation criteria](scenarios.md#evaluation-criteria),
  and an agreement otherwise (`--success COLUMN --success-threshold X` to change it);
- the mean language-model **cost** per session;
- **tied with leader**: its interval overlaps the leader's, so the data does not separate them.

**Everyone is scored on the same components.** A component counts only if it has a value in at least
half of the sessions of *every* entrant (`--min-coverage`); the board lists the components it used
and those it dropped. Without this, an entrant whose participants skipped the questionnaire would be
scored on different things.

`--relative` subtracts each cell's mean over all entrants before averaging. Use it when entrants
played different scenarios or opponents.

## Adding a metric

```python
from hani2.evaluation import Column, metric

@metric("offers_with_text", kind="hard", title="Offers with a message",
        columns=[Column("share_with_text", "Share with text", "Human offers that carried a message", True)])
def offers_with_text(ctx, options):
    offers = [a for a in ctx.acts if a["actor"] == "human" and a["type"] == "offer"]
    return {"share_with_text": sum(bool(a.get("text")) for a in offers) / len(offers) if offers else None}
```

Import the module before evaluating (for example in your experiment's code) and the metric
appears in the replay tool and in `hani2 replay metrics`. `ctx` (an `EvalContext`) gives the
recording (`ctx.rec`), utilities (`ctx.hu(offer)`, `ctx.ou(offer)`), the Pareto frontier, the Nash
and Kalai points, offers, actions, drafts, chat, language-model and function calls, and the
browser telemetry. Return `"_details"` for anything that is not a number per recording.
