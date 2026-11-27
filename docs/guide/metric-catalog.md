<!-- Generated from src/hani2/evaluation/catalog.py by scripts/make_metric_catalog.py. Do not edit by hand. -->


# Metric catalogue

Every measure HANI2 computes for a negotiation, in groups of similar measures: what it measures, its range and direction, whether a score can use it, and whether its implementation is validated (✓). The same groups and marks appear in the app: in the score builder's criteria picker, the leaderboard's sort and column choices and the board settings. How each measure is calculated, with formulas and worked examples, is in the [Metric reference](metrics.md); defaults for scores are in the [Criteria and scores reference](criteria.md). The questionnaires a study can use are listed in [Questionnaires](questionnaires.md).

190 numeric measures of 25 metrics; 155 are validated.

| Group | Measures | Validated | What it holds |
| --- | --- | --- | --- |
| [Outcome and utility](#group-outcome) | 7 | 7 | Whether there was a deal and what it was worth to each side: agreement, utilities, advantages, targets. |
| [Efficiency and welfare](#group-efficiency) | 4 | 4 | How much value the deal created and how close it is to the best deals: welfare, Pareto distance and optimality. |
| [Fairness](#group-fairness) | 4 | 4 | How evenly the gains were shared: distances to the Nash and Kalai–Smorodinsky solutions, the Nash product, the fairness gap. |
| [Task success and rules](#group-rules) | 15 | 13 | Whether the task was done within its rules: task success, constraints, deals below the reservation value, failures. |
| [Process and timing](#group-process) | 14 | 14 | How the negotiation went in time: offers, steps, messages, durations, decision times. |
| [Negotiation behaviour](#group-behaviour) | 22 | 22 | What kind of moves each side made: concessions, nice or selfish moves, theory-of-mind indicators. |
| [Assistant use](#group-assistant) | 23 | 23 | How the human used the Assistant and how the Assistant behaved: messages, suggestions and their adoption, who acted, response times, function calls, engagement flags. |
| [Attention and activity](#group-activity) | 8 | 8 | What the participant did with mouse, keyboard and window: clicks, keys, scrolls, idle and away time. |
| [Questionnaires (subjective)](#group-subjective) | 23 | 23 | The participant's own answers: questionnaire scales and items, after each negotiation or after the session. |
| [Language-model judgements](#group-judge) | 33 | 0 | Ratings and checks by a language-model judge: the Assistant, the opponent and the human, natural-language assertions, error review. |
| [Combined scores](#group-scores) | 14 | 14 | Scores that combine criteria into one number in [0, 1]: the built-in HAN and HI scores and the project's own. |
| [LLM usage and cost](#group-cost) | 9 | 9 | Language-model calls, tokens, cost, latency and errors of the Assistant and the opponent. |
| [Simulated participants](#group-simulation) | 6 | 6 | Measures of games played by a simulated participant (persona): goal met, valid trial, conformance. |
| [Scenario and condition](#group-context) | 8 | 8 | What describes the game rather than measures it: scenario statistics, difficulty factors, the ablation condition, practice. |

## What “validated” means {#validated}

A ✓ next to a measure means that its implementation is **validated**: a test computes it on a
small hand-worked negotiation (known offers, utilities, timings, messages or answers) and compares
it with a value derived by hand from the measure's definition, with the derivation written next to
the expected value. The mark's tooltip names the test (in `tests/validation/`). A test that only
checks that a value lies in its range does not count.

For a questionnaire, ✓ means that its items were compared with the source instrument (wording,
number of items, anchors and direction), that its reversed items are reversed, and that its scales
are scored as the source says (see [Questionnaires](questionnaires.md)).

What is **not** validated is said so, with the reason. The ratings of the language-model judge (the
`ja_`, `jo_`, `jh_` columns, the assertion checks and the error review) are judgements that no
hand-computed example can check; only the parsing and aggregation of the judge's answers are
tested. A project's own scores are not marked: the rules that combine their parts are validated
(`test_defined_score_three_components_catalogue_defaults` and its neighbours), but their weights are the
project's choice.

The marks are kept honest by a test (`tests/test_metric_catalog.py`): every validated entry must name
a test that exists and that names the entry.

## Measures by group

### Outcome and utility {#group-outcome}

Whether there was a deal and what it was worth to each side: agreement, utilities, advantages, targets.

| Measure | Title | What it measures | Range | Direction | Score | Validated | Metric |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `agreement` | Agreement | 1 if the negotiation ended with a deal | 0 or 1 | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_outcome_docs_example_agreement_on_F">✓</abbr> | [`outcome`](metrics.md) |
| `human_utility` | Human utility | Utility of the result for the human–agent team | utility (usually [0, 1]) | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_outcome_docs_example_agreement_on_F">✓</abbr> | [`outcome`](metrics.md) |
| `opponent_utility` | Opponent utility | Utility of the result for the opponent | utility (usually [0, 1]) | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_outcome_docs_example_agreement_on_F">✓</abbr> | [`outcome`](metrics.md) |
| `human_advantage` | Human advantage | (u − reserved) / (max − reserved) for the human team | ≤ 1 (1 = the best outcome, 0 = no better than no deal) | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_outcome_docs_example_agreement_on_F">✓</abbr> | [`outcome`](metrics.md) |
| `opponent_advantage` | Opponent advantage | The same for the opponent | ≤ 1 | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_outcome_docs_example_agreement_on_F">✓</abbr> | [`outcome`](metrics.md) |
| `target_attainment` | Target attainment | Gain over the reservation value relative to the target's | (-inf, inf); 1 = the target | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_factors_target_attainment_below_target_and_constraint_hit">✓</abbr> | [`factors`](metrics.md) |
| `reached_target` | Reached target | 1 if the deal is at least as good as the target for the human | {0, 1} | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_factors_target_attainment_below_target_and_constraint_hit">✓</abbr> | [`factors`](metrics.md) |

Labels in this group (not numbers, so not usable in a score): `status`, `ended_by`.

### Efficiency and welfare {#group-efficiency}

How much value the deal created and how close it is to the best deals: welfare, Pareto distance and optimality.

| Measure | Title | What it measures | Range | Direction | Score | Validated | Metric |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `welfare` | Social welfare | Sum of every party's utility | utility sum (usually [0, number of parties]) | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_outcome_docs_example_agreement_on_F">✓</abbr> | [`outcome`](metrics.md) |
| `pareto_distance` | Pareto distance | Distance of the result from the Pareto frontier (utility space) | ≥ 0 (0 = on the frontier) | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_optimality_docs_example_agreement_on_F">✓</abbr> | [`optimality`](metrics.md) |
| `pareto_optimal` | Pareto optimal | 1 if the result is on the Pareto frontier | 0 or 1 | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_optimality_docs_example_agreement_on_F">✓</abbr> | [`optimality`](metrics.md) |
| `welfare_optimality` | Welfare optimality | Social welfare / the best possible welfare | usually [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_optimality_docs_example_agreement_on_F">✓</abbr> | [`optimality`](metrics.md) |

### Fairness {#group-fairness}

How evenly the gains were shared: distances to the Nash and Kalai–Smorodinsky solutions, the Nash product, the fairness gap.

| Measure | Title | What it measures | Range | Direction | Score | Validated | Metric |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `nash_distance` | Nash distance | Distance from the Nash bargaining solution | ≥ 0 | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_optimality_docs_example_agreement_on_F">✓</abbr> | [`optimality`](metrics.md) |
| `kalai_distance` | Kalai–Smorodinsky distance | Distance from the Kalai–Smorodinsky solution | ≥ 0 | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_optimality_docs_example_agreement_on_F">✓</abbr> | [`optimality`](metrics.md) |
| `nash_product_ratio` | Nash product ratio | Nash product of the result / the largest possible | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_optimality_docs_example_agreement_on_F">✓</abbr> | [`optimality`](metrics.md) |
| `fairness_gap` | Fairness gap | \|human advantage − opponent advantage\| | ≥ 0 (0 = gains shared evenly) | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_optimality_docs_example_agreement_on_F">✓</abbr> | [`optimality`](metrics.md) |

### Task success and rules {#group-rules}

Whether the task was done within its rules: task success, constraints, deals below the reservation value, failures.

| Measure | Title | What it measures | Range | Direction | Score | Validated | Metric |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `information_split` | Information split | Whether the Human and the Assistant knew different things | {0, 1} | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_dual_control_both_broken">✓</abbr> | [`dual_control`](metrics.md) |
| `constraints_met` | Constraints met | The agreement keeps every constraint of the private briefings | {0, 1} | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_dual_control_both_broken">✓</abbr> | [`dual_control`](metrics.md) |
| `n_constraint_violations` | Constraints broken | How many briefing constraints the agreement breaks | count | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_dual_control_both_broken">✓</abbr> | [`dual_control`](metrics.md) |
| `constraint_violated` | Constraint violated | 1 if the deal breaks the hidden constraint | {0, 1} | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_factors_target_attainment_below_target_and_constraint_hit">✓</abbr> | [`factors`](metrics.md) |
| `irrational_accept` | Accepted below reservation | 1 if the Human seat accepted a deal worth less than no deal | 0 or 1 | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_rule_checks_human_accepts_below_reservation">✓</abbr> | [`rule_checks`](metrics.md) |
| `opponent_irrational_accept` | Opponent accepted below reservation | 1 if the Opponent accepted a deal worth less to it than no deal | 0 or 1 | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_rule_checks_human_accepts_below_reservation">✓</abbr> | [`rule_checks`](metrics.md) |
| `irrational_suggestions` | Suggestions below reservation | Assistant suggestions worth less to the Human than no deal | count | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_rule_checks_irrational_suggestions_counts_assistant_drafts">✓</abbr> | [`rule_checks`](metrics.md) |
| `opponent_failed` | Opponent failed | 1 if the session ended because the Opponent agent raised an error | 0 or 1 | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_rule_checks_human_accepts_below_reservation">✓</abbr> | [`rule_checks`](metrics.md) |
| `infrastructure_failure` | System failure | 1 if the negotiation mechanism failed | 0 or 1 | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_rule_checks_human_accepts_below_reservation">✓</abbr> | [`rule_checks`](metrics.md) |
| `task_communicated` | Facts communicated | Share of the scenario's facts the Assistant conveyed to the Human | [0, 1] | higher | yes |  | [`task_judge`](metrics.md) |
| `task_assertions_met` | Scenario assertions met | Share of the scenario's applicable assertions that were met | [0, 1] | higher | yes |  | [`task_judge`](metrics.md) |
| `task_success` | Task success | 1 if the session met every component of its scenario's evaluation criteria | 0 or 1 | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_task_success_all_components_hold">✓</abbr> | [`task_success`](metrics.md) |
| `task_targets_met` | Targets met | Share of the scenario's targets the session met | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_task_success_all_components_hold">✓</abbr> | [`task_success`](metrics.md) |
| `task_rules_ok` | Rules respected | 1 if every rule check the scenario names is 0 | 0 or 1 | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_task_success_all_components_hold">✓</abbr> | [`task_success`](metrics.md) |
| `task_components` | Components checked | How many components the task success was computed from | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_task_success_all_components_hold">✓</abbr> | [`task_success`](metrics.md) |

*Not validated:* The rating is a language-model judgement, which no hand-computed example can check; only the parsing, clamping and aggregation of the judge's answer are tested (tests/validation/test_validate_subjective.py::test_task_judge_shares).

### Process and timing {#group-process}

How the negotiation went in time: offers, steps, messages, durations, decision times.

| Measure | Title | What it measures | Range | Direction | Score | Validated | Metric |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `n_offers` | Offers | Offers exchanged | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_length_trace_without_result_fields">✓</abbr> | [`length`](metrics.md) |
| `n_human_offers` | Human offers | Offers made by the human team | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_length_trace_without_result_fields">✓</abbr> | [`length`](metrics.md) |
| `n_opponent_offers` | Opponent offers | Offers made by the opponent | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_length_trace_without_result_fields">✓</abbr> | [`length`](metrics.md) |
| `n_steps` | Steps | Mechanism steps used | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_length_trace_without_result_fields">✓</abbr> | [`length`](metrics.md) |
| `relative_time` | Relative time | Share of the time/step limit used | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_length_trace_without_result_fields">✓</abbr> | [`length`](metrics.md) |
| `negotiation_seconds` | Negotiation time (s) | From the start to the end of the negotiation | seconds | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_length_trace_without_result_fields">✓</abbr> | [`length`](metrics.md) |
| `session_seconds` | Recording time (s) | From loading the scenario to the end of the recording | seconds | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_length_trace_without_result_fields">✓</abbr> | [`length`](metrics.md) |
| `n_text_messages` | Text messages | Offers or turns that carried a message to the other side | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_length_trace_without_result_fields">✓</abbr> | [`length`](metrics.md) |
| `decision_time_mean` | Decision time (s) | Mean time from the start of the human's turn to their action | seconds | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_timing_screen_states">✓</abbr> | [`timing`](metrics.md) |
| `decision_time_median` | Decision time, median (s) | Median time per decision | seconds | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_timing_screen_states">✓</abbr> | [`timing`](metrics.md) |
| `decision_time_min` | Fastest decision (s) | Shortest time per decision | seconds | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_timing_screen_states">✓</abbr> | [`timing`](metrics.md) |
| `time_to_first_action` | Time to first action (s) | From the start of the negotiation to the first human action | seconds | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_timing_screen_states">✓</abbr> | [`timing`](metrics.md) |
| `load_to_start_seconds` | Reading time (s) | From loading the scenario to starting the negotiation | seconds | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_timing_screen_states">✓</abbr> | [`timing`](metrics.md) |
| `questionnaire_seconds` | Questionnaire time (s) | Time spent on the questionnaire | seconds | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_timing_screen_states">✓</abbr> | [`timing`](metrics.md) |

### Negotiation behaviour {#group-behaviour}

What kind of moves each side made: concessions, nice or selfish moves, theory-of-mind indicators.

| Measure | Title | What it measures | Range | Direction | Score | Validated | Metric |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `human_move_silent` | Human: silent | Share of human moves that were silent | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_dynamics_documented_example">✓</abbr> | [`dynamics`](metrics.md) |
| `human_move_nice` | Human: nice | Share of human moves that were nice | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_dynamics_documented_example">✓</abbr> | [`dynamics`](metrics.md) |
| `human_move_fortunate` | Human: fortunate | Share of human moves that were fortunate | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_dynamics_documented_example">✓</abbr> | [`dynamics`](metrics.md) |
| `human_move_unfortunate` | Human: unfortunate | Share of human moves that were unfortunate | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_dynamics_documented_example">✓</abbr> | [`dynamics`](metrics.md) |
| `human_move_concession` | Human: concession | Share of human moves that were concession | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_dynamics_documented_example">✓</abbr> | [`dynamics`](metrics.md) |
| `human_move_selfish` | Human: selfish | Share of human moves that were selfish | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_dynamics_documented_example">✓</abbr> | [`dynamics`](metrics.md) |
| `opponent_move_silent` | Opponent: silent | Share of opponent moves that were silent | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_dynamics_documented_example">✓</abbr> | [`dynamics`](metrics.md) |
| `opponent_move_nice` | Opponent: nice | Share of opponent moves that were nice | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_dynamics_documented_example">✓</abbr> | [`dynamics`](metrics.md) |
| `opponent_move_fortunate` | Opponent: fortunate | Share of opponent moves that were fortunate | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_dynamics_documented_example">✓</abbr> | [`dynamics`](metrics.md) |
| `opponent_move_unfortunate` | Opponent: unfortunate | Share of opponent moves that were unfortunate | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_dynamics_documented_example">✓</abbr> | [`dynamics`](metrics.md) |
| `opponent_move_concession` | Opponent: concession | Share of opponent moves that were concession | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_dynamics_documented_example">✓</abbr> | [`dynamics`](metrics.md) |
| `opponent_move_selfish` | Opponent: selfish | Share of opponent moves that were selfish | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_dynamics_documented_example">✓</abbr> | [`dynamics`](metrics.md) |
| `suggested_move_silent` | Assistant suggestion: silent | Share of assistant suggestion moves that were silent | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_dynamics_suggestions">✓</abbr> | [`dynamics`](metrics.md) |
| `suggested_move_nice` | Assistant suggestion: nice | Share of assistant suggestion moves that were nice | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_dynamics_suggestions">✓</abbr> | [`dynamics`](metrics.md) |
| `suggested_move_fortunate` | Assistant suggestion: fortunate | Share of assistant suggestion moves that were fortunate | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_dynamics_suggestions">✓</abbr> | [`dynamics`](metrics.md) |
| `suggested_move_unfortunate` | Assistant suggestion: unfortunate | Share of assistant suggestion moves that were unfortunate | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_dynamics_suggestions">✓</abbr> | [`dynamics`](metrics.md) |
| `suggested_move_concession` | Assistant suggestion: concession | Share of assistant suggestion moves that were concession | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_dynamics_suggestions">✓</abbr> | [`dynamics`](metrics.md) |
| `suggested_move_selfish` | Assistant suggestion: selfish | Share of assistant suggestion moves that were selfish | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_dynamics_suggestions">✓</abbr> | [`dynamics`](metrics.md) |
| `human_concession` | Human concession | Utility the human gave up from the first to the last offer | utility difference | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_dynamics_documented_example">✓</abbr> | [`dynamics`](metrics.md) |
| `human_offer_pareto_distance` | Human offers' Pareto distance | Mean distance of the human's offers from the Pareto frontier | ≥ 0 | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_dynamics_documented_example">✓</abbr> | [`dynamics`](metrics.md) |
| `tom_reflect_index` | Theory of mind: reflect index | Share of the human's moves up to the first one that raised the opponent's utility (lower = sooner) | (0, 1] | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_dynamics_documented_example">✓</abbr> | [`dynamics`](metrics.md) |
| `tom_other_trend` | Theory of mind: other's-utility trend | Correlation of the opponent's utility of the human's offers with their order (higher = the human moved toward the other's interests) | [−1, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_dynamics_documented_example">✓</abbr> | [`dynamics`](metrics.md) |

### Assistant use {#group-assistant}

How the human used the Assistant and how the Assistant behaved: messages, suggestions and their adoption, who acted, response times, function calls, engagement flags.

| Measure | Title | What it measures | Range | Direction | Score | Validated | Metric |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `n_user_messages` | Messages to assistant | Chat messages the human sent to the assistant | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_system_use_documented_example">✓</abbr> | [`system_use`](metrics.md) |
| `n_assistant_messages` | Assistant messages | Messages the assistant posted | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_system_use_documented_example">✓</abbr> | [`system_use`](metrics.md) |
| `n_suggestions` | Suggestions | Drafts (offers or messages) the assistant filled in for the human | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_system_use_documented_example">✓</abbr> | [`system_use`](metrics.md) |
| `suggestion_adoption` | Suggestion adoption | Share of human offers made after a suggestion that were exactly the suggestion | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_system_use_documented_example">✓</abbr> | [`system_use`](metrics.md) |
| `suggestions_ignored` | Suggestions ignored | Suggestions followed by a different offer | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_system_use_documented_example">✓</abbr> | [`system_use`](metrics.md) |
| `drafts_explored` | Offers explored | Counter-offers the human tried in the editor before acting | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_system_use_documented_example">✓</abbr> | [`system_use`](metrics.md) |
| `drafts_per_action` | Offers explored per action | Mean explorations before each human action | ≥ 0 | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_system_use_documented_example">✓</abbr> | [`system_use`](metrics.md) |
| `n_tool_interactions` | Tool interactions | Inputs and actions in tools | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_system_use_documented_example">✓</abbr> | [`system_use`](metrics.md) |
| `n_tools_used` | Tools used | Distinct tools the human used | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_system_use_documented_example">✓</abbr> | [`system_use`](metrics.md) |
| `n_tab_changes` | Tab changes | Tool tabs opened | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_system_use_documented_example">✓</abbr> | [`system_use`](metrics.md) |
| `actions_by_human` | Actions by human | Share of the seat's actions taken by the human | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_system_use_documented_example">✓</abbr> | [`system_use`](metrics.md) |
| `actions_by_agent` | Actions by assistant | Share taken by the assistant | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_system_use_documented_example">✓</abbr> | [`system_use`](metrics.md) |
| `actions_by_autopilot` | Actions by autopilot | Share taken by the autopilot | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_system_use_documented_example">✓</abbr> | [`system_use`](metrics.md) |
| `never_acted` | Never acted | 1 if the human never took an action themselves (filter out) | 0 or 1 | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_engagement_flags_click_through">✓</abbr> | [`engagement_flags`](metrics.md) |
| `click_through` | Click-through | 1 if the human acted very fast without exploring offers (not invested) | 0 or 1 | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_engagement_flags_click_through">✓</abbr> | [`engagement_flags`](metrics.md) |
| `always_follows` | Always follows assistant | 1 if every human offer made after a suggestion was the suggestion (≥ 3 offers) | 0 or 1 | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_engagement_flags_click_through">✓</abbr> | [`engagement_flags`](metrics.md) |
| `never_follows` | Never follows assistant | 1 if no suggestion was ever taken (≥ 3 suggestions) | 0 or 1 | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_engagement_flags_click_through">✓</abbr> | [`engagement_flags`](metrics.md) |
| `assistant_response_seconds` | Response time (s) | Mean time from a human message to the assistant's next message | seconds | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_assistant_interaction_documented_example">✓</abbr> | [`assistant_interaction`](metrics.md) |
| `unanswered_messages` | Unanswered messages | Human messages the assistant never answered | count | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_assistant_interaction_documented_example">✓</abbr> | [`assistant_interaction`](metrics.md) |
| `unsolicited_messages` | Proactive messages | Assistant messages not answering the human (> 30 s after their last message) | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_assistant_interaction_documented_example">✓</abbr> | [`assistant_interaction`](metrics.md) |
| `max_assistant_streak` | Longest monologue | Most assistant messages in a row without the human writing | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_assistant_interaction_documented_example">✓</abbr> | [`assistant_interaction`](metrics.md) |
| `fn_calls` | Function calls | Functions the assistant called | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_assistant_interaction_documented_example">✓</abbr> | [`assistant_interaction`](metrics.md) |
| `fn_success_rate` | Function success | Share of the assistant's function calls that succeeded | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_assistant_interaction_documented_example">✓</abbr> | [`assistant_interaction`](metrics.md) |

### Attention and activity {#group-activity}

What the participant did with mouse, keyboard and window: clicks, keys, scrolls, idle and away time.

| Measure | Title | What it measures | Range | Direction | Score | Validated | Metric |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `n_clicks` | Clicks | Mouse / touch clicks | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_activity_documented_example">✓</abbr> | [`activity`](metrics.md) |
| `n_keys` | Key presses | Keys pressed | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_activity_documented_example">✓</abbr> | [`activity`](metrics.md) |
| `mouse_distance` | Mouse distance (px) | Distance travelled by the pointer | pixels | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_activity_documented_example">✓</abbr> | [`activity`](metrics.md) |
| `n_scrolls` | Scrolls | Scroll events | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_activity_documented_example">✓</abbr> | [`activity`](metrics.md) |
| `idle_fraction` | Idle fraction | Share of the negotiation without any input for more than 5 s | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_activity_documented_example">✓</abbr> | [`activity`](metrics.md) |
| `hidden_seconds` | Away (s) | Time the page was hidden (another tab or window) | seconds | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_activity_documented_example">✓</abbr> | [`activity`](metrics.md) |
| `n_blur` | Focus lost | Times the window lost focus | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_activity_documented_example">✓</abbr> | [`activity`](metrics.md) |
| `has_telemetry` | Has telemetry | 1 if browser telemetry was recorded | 0 or 1 | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_activity_documented_example">✓</abbr> | [`activity`](metrics.md) |

### Questionnaires (subjective) {#group-subjective}

The participant's own answers: questionnaire scales and items, after each negotiation or after the session.

Besides the scales of the bundled evaluation questionnaire listed here, every item and scale of a project's own forms is a measure of this group: `q_<id>`, `scale_<name>`, `scale_<name>_norm`, and `post_q_<id>`, `post_scale_<name>` for the post-session form. They are computed by the same validated rules <abbr title="validated against a hand-computed example: tests/validation/test_validate_subjective.py::test_questionnaire_mixed_ranges_and_types">✓</abbr>.

| Measure | Title | What it measures | Range | Direction | Score | Validated | Metric |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `scale_satisfaction` | Satisfaction | Satisfaction with the outcome | the items' range (1–7) | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_subjective.py::test_questionnaire_bundled_form_scales">✓</abbr> | [`questionnaire`](metrics.md) |
| `scale_satisfaction_norm` | Satisfaction (0–1) | Satisfaction with the outcome, rescaled to 0–1 | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_subjective.py::test_questionnaire_bundled_form_scales">✓</abbr> | [`questionnaire`](metrics.md) |
| `scale_appreciation` | Appreciation | Enjoyment of the negotiation | the items' range (1–7) | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_subjective.py::test_questionnaire_bundled_form_scales">✓</abbr> | [`questionnaire`](metrics.md) |
| `scale_appreciation_norm` | Appreciation (0–1) | Enjoyment of the negotiation, rescaled to 0–1 | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_subjective.py::test_questionnaire_bundled_form_scales">✓</abbr> | [`questionnaire`](metrics.md) |
| `scale_ueq_pragmatic` | Ueq pragmatic | UEQ pragmatic quality of the assistant: perspicuity (understandable, easy, clear), efficiency (efficient, practical) and dependability (supportive) items | the items' range (1–7) | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_subjective.py::test_questionnaire_bundled_form_scales">✓</abbr> | [`questionnaire`](metrics.md) |
| `scale_ueq_pragmatic_norm` | Ueq pragmatic (0–1) | UEQ pragmatic quality of the assistant: perspicuity (understandable, easy, clear), efficiency (efficient, practical) and dependability (supportive) items, rescaled to 0–1 | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_subjective.py::test_questionnaire_bundled_form_scales">✓</abbr> | [`questionnaire`](metrics.md) |
| `scale_ueq_hedonic` | Ueq hedonic | UEQ items on the assistant's value and overall impression (valuable — a stimulation item; good — an attractiveness item) | the items' range (1–7) | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_subjective.py::test_questionnaire_bundled_form_scales">✓</abbr> | [`questionnaire`](metrics.md) |
| `scale_ueq_hedonic_norm` | Ueq hedonic (0–1) | UEQ items on the assistant's value and overall impression (valuable — a stimulation item; good — an attractiveness item), rescaled to 0–1 | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_subjective.py::test_questionnaire_bundled_form_scales">✓</abbr> | [`questionnaire`](metrics.md) |
| `scale_tam_usefulness` | Tam usefulness | TAM perceived usefulness of the assistant | the items' range (1–7) | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_subjective.py::test_questionnaire_bundled_form_scales">✓</abbr> | [`questionnaire`](metrics.md) |
| `scale_tam_usefulness_norm` | Tam usefulness (0–1) | TAM perceived usefulness of the assistant, rescaled to 0–1 | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_subjective.py::test_questionnaire_bundled_form_scales">✓</abbr> | [`questionnaire`](metrics.md) |
| `scale_intention_to_use` | Intention to use | Intention to use the assistant again | the items' range (1–7) | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_subjective.py::test_questionnaire_bundled_form_scales">✓</abbr> | [`questionnaire`](metrics.md) |
| `scale_intention_to_use_norm` | Intention to use (0–1) | Intention to use the assistant again, rescaled to 0–1 | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_subjective.py::test_questionnaire_bundled_form_scales">✓</abbr> | [`questionnaire`](metrics.md) |
| `scale_felt_heard` | Felt heard | Feeling heard by the assistant | the items' range (1–7) | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_questionnaires.py::test_felt_heard_single_item_scale">✓</abbr> | [`questionnaire`](metrics.md) |
| `scale_felt_heard_norm` | Felt heard (0–1) | Feeling heard by the assistant, rescaled to 0–1 | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_questionnaires.py::test_felt_heard_single_item_scale">✓</abbr> | [`questionnaire`](metrics.md) |
| `scale_opponent_kindness` | Opponent kindness | Perceived kindness of the opponent | the items' range (1–7) | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_subjective.py::test_questionnaire_bundled_form_scales">✓</abbr> | [`questionnaire`](metrics.md) |
| `scale_opponent_kindness_norm` | Opponent kindness (0–1) | Perceived kindness of the opponent, rescaled to 0–1 | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_subjective.py::test_questionnaire_bundled_form_scales">✓</abbr> | [`questionnaire`](metrics.md) |
| `scale_opponent_intelligence` | Opponent intelligence | Perceived intelligence of the opponent | the items' range (1–7) | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_subjective.py::test_questionnaire_bundled_form_scales">✓</abbr> | [`questionnaire`](metrics.md) |
| `scale_opponent_intelligence_norm` | Opponent intelligence (0–1) | Perceived intelligence of the opponent, rescaled to 0–1 | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_subjective.py::test_questionnaire_bundled_form_scales">✓</abbr> | [`questionnaire`](metrics.md) |
| `scale_opponent_humanlike` | Opponent humanlike | Belief that the opponent was human | the items' range (1–7) | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_subjective.py::test_questionnaire_bundled_form_scales">✓</abbr> | [`questionnaire`](metrics.md) |
| `scale_opponent_humanlike_norm` | Opponent humanlike (0–1) | Belief that the opponent was human, rescaled to 0–1 | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_subjective.py::test_questionnaire_bundled_form_scales">✓</abbr> | [`questionnaire`](metrics.md) |
| `scale_relationship` | Relationship | Wish to negotiate again / feeling connected to the opponent | the items' range (1–7) | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_subjective.py::test_questionnaire_bundled_form_scales">✓</abbr> | [`questionnaire`](metrics.md) |
| `scale_relationship_norm` | Relationship (0–1) | Wish to negotiate again / feeling connected to the opponent, rescaled to 0–1 | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_subjective.py::test_questionnaire_bundled_form_scales">✓</abbr> | [`questionnaire`](metrics.md) |
| `questionnaire_answered` | Answered | 1 if the participant answered the questionnaire | 0 or 1 | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_subjective.py::test_questionnaire_bundled_form_scales">✓</abbr> | [`questionnaire`](metrics.md) |

### Language-model judgements {#group-judge}

Ratings and checks by a language-model judge: the Assistant, the opponent and the human, natural-language assertions, error review.

| Measure | Title | What it measures | Range | Direction | Score | Validated | Metric |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ja_helpfulness` | Assistant: helpfulness | How much the assistant helped the human get a good outcome. | 1–7 | higher | yes |  | [`judge_assistant`](metrics.md) |
| `ja_explanation` | Assistant: explanation | Whether its recommendations came with clear reasons. | 1–7 | higher | yes |  | [`judge_assistant`](metrics.md) |
| `ja_opponent_insight` | Assistant: opponent insight | Whether it explained the opponent's behaviour or likely preferences correctly. | 1–7 | higher | yes |  | [`judge_assistant`](metrics.md) |
| `ja_user_understanding` | Assistant: user understanding | Whether it understood what the human wanted (theory of mind) and checked it. | 1–7 | higher | yes |  | [`judge_assistant`](metrics.md) |
| `ja_scenario_explanation` | Assistant: scenario explanation | Whether it helped the human understand the scenario and their preferences. | 1–7 | higher | yes |  | [`judge_assistant`](metrics.md) |
| `ja_capability_disclosure` | Assistant: capability disclosure | Whether it told the human what it can and cannot do. | 1–7 | higher | yes |  | [`judge_assistant`](metrics.md) |
| `ja_autonomy_respect` | Assistant: autonomy respect | Whether it left the human in control (no unwanted actions, no taking over). | 1–7 | higher | yes |  | [`judge_assistant`](metrics.md) |
| `ja_communication` | Assistant: communication | Clarity, brevity and tone of its messages. | 1–7 | higher | yes |  | [`judge_assistant`](metrics.md) |
| `ja_message_improvement` | Assistant: message improvement | Whether it improved the messages the human sent to the opponent (if it did that). | 1–7 | higher | yes |  | [`judge_assistant`](metrics.md) |
| `ja_overall` | Assistant: overall | Overall judgement of the assistant (1–7) | 1–7 | higher | yes |  | [`judge_assistant`](metrics.md) |
| `jo_kindness` | Opponent: kindness | How kind / polite the opponent was. | 1–7 | higher | yes |  | [`judge_opponent`](metrics.md) |
| `jo_intelligence` | Opponent: intelligence | How intelligent and strategic the opponent was. | 1–7 | higher | yes |  | [`judge_opponent`](metrics.md) |
| `jo_cooperativeness` | Opponent: cooperativeness | How willing it was to find a mutually good deal. | 1–7 | higher | yes |  | [`judge_opponent`](metrics.md) |
| `jo_human_likeness` | Opponent: human likeness | How human-like it seemed (7 = indistinguishable from a person). | 1–7 | higher | yes |  | [`judge_opponent`](metrics.md) |
| `jo_communication` | Opponent: communication | Quality of its messages (if any). | 1–7 | higher | yes |  | [`judge_opponent`](metrics.md) |
| `jo_consistency` | Opponent: consistency | How consistent its offers and messages were. | 1–7 | higher | yes |  | [`judge_opponent`](metrics.md) |
| `jo_overall` | Opponent: overall | Overall judgement of the opponent (1–7) | 1–7 | higher | yes |  | [`judge_opponent`](metrics.md) |
| `jh_engagement` | Human: engagement | How invested the human was (explored offers, thought about moves, did not just click through). | 1–7 | higher | yes |  | [`judge_human`](metrics.md) |
| `jh_strategy` | Human: strategy | Quality of the human's negotiation strategy. | 1–7 | higher | yes |  | [`judge_human`](metrics.md) |
| `jh_cooperativeness` | Human: cooperativeness | How cooperative the human was toward the opponent. | 1–7 | higher | yes |  | [`judge_human`](metrics.md) |
| `jh_use_of_assistant` | Human: use of assistant | How well the human used the assistant (neither ignoring nor blindly following it). | 1–7 | higher | yes |  | [`judge_human`](metrics.md) |
| `jh_communication` | Human: communication | Quality of the human's messages (if any). | 1–7 | higher | yes |  | [`judge_human`](metrics.md) |
| `jh_overall` | Human: overall | Overall judgement of the human (1–7) | 1–7 | higher | yes |  | [`judge_human`](metrics.md) |
| `assertions_met` | Assertions met | Share of the applicable natural-language assertions the judge found satisfied | [0, 1] | higher | yes |  | [`nl_assertions`](metrics.md) |
| `assertions_total` | Assertions judged | Assertions that applied to this session | count | none | with a direction |  | [`nl_assertions`](metrics.md) |
| `assistant_errors` | Assistant errors | Errors the judge found in the assistant's behaviour | count | lower | yes |  | [`error_review`](metrics.md) |
| `assistant_critical_errors` | Assistant critical errors | … of which critical (changed the outcome) | count | lower | yes |  | [`error_review`](metrics.md) |
| `human_errors` | Human errors | Errors the judge found in the human's decisions | count | lower | yes |  | [`error_review`](metrics.md) |
| `human_critical_errors` | Human critical errors | … of which critical | count | lower | yes |  | [`error_review`](metrics.md) |
| `simulator_errors` | Simulator errors | Errors of the user simulator (simulated participants only) | count | lower | yes |  | [`error_review`](metrics.md) |
| `simulator_critical_errors` | Simulator critical errors | … of which critical | count | lower | yes |  | [`error_review`](metrics.md) |
| `human_overrode_helpfully` | Helpful overrides | Times the human went against the assistant and it helped | count | higher | yes |  | [`error_review`](metrics.md) |
| `human_overrode_harmfully` | Harmful overrides | Times the human went against the assistant and it hurt | count | lower | yes |  | [`error_review`](metrics.md) |

Labels in this group (not numbers, so not usable in a score): `first_critical`.

*Not validated:* The rating is a language-model judgement, which no hand-computed example can check; only the parsing, clamping and aggregation of the judge's answer are tested (tests/validation/test_validate_subjective.py::test_error_review_counts_by_source_and_severity).

*Not validated:* The rating is a language-model judgement, which no hand-computed example can check; only the parsing, clamping and aggregation of the judge's answer are tested (tests/validation/test_validate_subjective.py::test_judge_assistant_rating_parsing_and_clamping).

*Not validated:* The rating is a language-model judgement, which no hand-computed example can check; only the parsing, clamping and aggregation of the judge's answer are tested (tests/validation/test_validate_subjective.py::test_judge_human_rating_parsing_and_clamping).

*Not validated:* The rating is a language-model judgement, which no hand-computed example can check; only the parsing, clamping and aggregation of the judge's answer are tested (tests/validation/test_validate_subjective.py::test_judge_opponent_rating_parsing_and_clamping).

*Not validated:* The rating is a language-model judgement, which no hand-computed example can check; only the parsing, clamping and aggregation of the judge's answer are tested (tests/validation/test_validate_subjective.py::test_nl_assertions_share_of_applicable).

### Combined scores {#group-scores}

Scores that combine criteria into one number in [0, 1]: the built-in HAN and HI scores and the project's own.

A project's own scores join this group (see [Scores](#scores)).

| Measure | Title | What it measures | Range | Direction | Score | Validated | Metric |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `han_outcome` | HAN outcome | What the Opponent agent obtained against the Human (Human-Agent Negotiation track) | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_scores.py::test_scores_han_outcome">✓</abbr> | [`scores`](metrics.md) |
| `han_outcome_coverage` | HAN outcome coverage | Share of the weight of han_outcome that had a value | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_scores.py::test_scores_han_outcome">✓</abbr> | [`scores`](metrics.md) |
| `han_interaction` | HAN interaction | How well the Opponent agent behaved as an opponent (Human-Agent Negotiation track) | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_scores.py::test_scores_han_interaction_full_row">✓</abbr> | [`scores`](metrics.md) |
| `han_interaction_coverage` | HAN interaction coverage | Share of the weight of han_interaction that had a value | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_scores.py::test_scores_han_interaction_full_row">✓</abbr> | [`scores`](metrics.md) |
| `hi_outcome` | HI outcome | What the human–Assistant team obtained (Hybrid Intelligence track) | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_scores.py::test_scores_hi_outcome_and_utility">✓</abbr> | [`scores`](metrics.md) |
| `hi_outcome_coverage` | HI outcome coverage | Share of the weight of hi_outcome that had a value | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_scores.py::test_scores_hi_outcome_and_utility">✓</abbr> | [`scores`](metrics.md) |
| `hi_assistant` | HI Assistant | How well the Assistant worked as an Assistant (Hybrid Intelligence track) | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_scores.py::test_scores_hi_assistant_full_row">✓</abbr> | [`scores`](metrics.md) |
| `hi_assistant_coverage` | HI Assistant coverage | Share of the weight of hi_assistant that had a value | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_scores.py::test_scores_hi_assistant_full_row">✓</abbr> | [`scores`](metrics.md) |
| `hi_team` | HI team | How well the human–Assistant team worked together (Hybrid Intelligence track) | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_scores.py::test_scores_hi_team_full_row">✓</abbr> | [`scores`](metrics.md) |
| `hi_team_coverage` | HI team coverage | Share of the weight of hi_team that had a value | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_scores.py::test_scores_hi_team_full_row">✓</abbr> | [`scores`](metrics.md) |
| `hi_interaction` | HI interaction | The Assistant and the team together: the ranked score of the HI interaction board | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_scores.py::test_scores_hi_interaction_full_row">✓</abbr> | [`scores`](metrics.md) |
| `hi_interaction_coverage` | HI interaction coverage | Share of the weight of hi_interaction that had a value | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_scores.py::test_scores_hi_interaction_full_row">✓</abbr> | [`scores`](metrics.md) |
| `utility` | Utility | The Human side's advantage alone, for any session | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_scores.py::test_scores_hi_outcome_and_utility">✓</abbr> | [`scores`](metrics.md) |
| `utility_coverage` | Utility coverage | Share of the weight of utility that had a value | [0, 1] | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_scores.py::test_scores_hi_outcome_and_utility">✓</abbr> | [`scores`](metrics.md) |

### LLM usage and cost {#group-cost}

Language-model calls, tokens, cost, latency and errors of the Assistant and the opponent.

| Measure | Title | What it measures | Range | Direction | Score | Validated | Metric |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `llm_calls` | LLM calls | Language-model calls during the negotiation | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_llm_usage_mixed_roles">✓</abbr> | [`llm_usage`](metrics.md) |
| `llm_tokens` | LLM tokens | Prompt + completion tokens (energy / climate proxy) | tokens | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_llm_usage_mixed_roles">✓</abbr> | [`llm_usage`](metrics.md) |
| `llm_cost_usd` | LLM cost (USD) | Estimated cost of every call (when the provider's price is known) | US dollars | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_llm_usage_mixed_roles">✓</abbr> | [`llm_usage`](metrics.md) |
| `llm_latency_mean` | LLM latency (s) | Mean seconds per call | seconds | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_llm_usage_mixed_roles">✓</abbr> | [`llm_usage`](metrics.md) |
| `llm_error_rate` | LLM error rate | Share of calls that failed | [0, 1] | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_llm_usage_mixed_roles">✓</abbr> | [`llm_usage`](metrics.md) |
| `support_llm_calls` | Assistant LLM calls | Calls made by the Assistant | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_llm_usage_mixed_roles">✓</abbr> | [`llm_usage`](metrics.md) |
| `support_tokens` | Assistant tokens | Tokens used by the Assistant | tokens | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_llm_usage_mixed_roles">✓</abbr> | [`llm_usage`](metrics.md) |
| `opponent_llm_calls` | Opponent LLM calls | Calls made by the opponent | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_llm_usage_mixed_roles">✓</abbr> | [`llm_usage`](metrics.md) |
| `opponent_tokens` | Opponent tokens | Tokens used by the opponent | tokens | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_process.py::test_llm_usage_mixed_roles">✓</abbr> | [`llm_usage`](metrics.md) |

### Simulated participants {#group-simulation}

Measures of games played by a simulated participant (persona): goal met, valid trial, conformance.

| Measure | Title | What it measures | Range | Direction | Score | Validated | Metric |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `sim_goal_met` | Goal met | The simulated participant got a deal worth at least its reservation value | {0, 1} | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_simulation_stubborn_documented_example">✓</abbr> | [`simulation`](metrics.md) |
| `sim_valid` | Valid trial | The trial ended normally (no time-out, turn cap or simulator failure) | {0, 1} | higher | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_simulation_stubborn_documented_example">✓</abbr> | [`simulation`](metrics.md) |
| `sim_turns` | Persona turns | Moves the persona made | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_simulation_stubborn_documented_example">✓</abbr> | [`simulation`](metrics.md) |
| `sim_take_rate` | Suggestions taken | Share of the turns with a suggestion where the persona took it | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_simulation_stubborn_documented_example">✓</abbr> | [`simulation`](metrics.md) |
| `sim_violations` | Persona violations | Turns where a scripted persona broke its own policy | count | lower | yes | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_simulation_stubborn_documented_example">✓</abbr> | [`simulation`](metrics.md) |
| `sim_stopped` | Persona stopped | The language-model persona ended its participation with the stop token | {0, 1} | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_assistant.py::test_simulation_stubborn_documented_example">✓</abbr> | [`simulation`](metrics.md) |

### Scenario and condition {#group-context}

What describes the game rather than measures it: scenario statistics, difficulty factors, the ablation condition, practice.

| Measure | Title | What it measures | Range | Direction | Score | Validated | Metric |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `practice` | Practice | 1 for a practice round | 0 or 1 | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_outcome_docs_example_agreement_on_F">✓</abbr> | [`outcome`](metrics.md) |
| `n_outcomes` | Outcomes | Number of possible outcomes | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_scenario_stats_docs_example">✓</abbr> | [`scenario_stats`](metrics.md) |
| `zopa_fraction` | ZOPA fraction | Share of outcomes acceptable to every party (at least all reserved values) | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_scenario_stats_docs_example">✓</abbr> | [`scenario_stats`](metrics.md) |
| `pareto_size` | Pareto size | Number of Pareto-optimal outcomes | count | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_scenario_stats_docs_example">✓</abbr> | [`scenario_stats`](metrics.md) |
| `opposition` | Opposition | Distance of the ideal point (best for each side) from the frontier: how competitive the scenario is | ≥ 0 (0 = no conflict) | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_scenario_stats_docs_example">✓</abbr> | [`scenario_stats`](metrics.md) |
| `oracle` | Oracle | 1 when the Assistant knew the opponent's utility function | 0 or 1 | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_condition_team_human_acts_only">✓</abbr> | [`condition`](metrics.md) |
| `opponent_info_tools` | Opponent info in tools | 1 when the Human's tools could show the opponent's utilities | 0 or 1 | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_condition_team_human_acts_only">✓</abbr> | [`condition`](metrics.md) |
| `autopilot_share` | Autopilot share | Share of the seat's actions taken by autopilot | [0, 1] | none | with a direction | <abbr title="validated against a hand-computed example: tests/validation/test_validate_outcome.py::test_condition_team_human_acts_only">✓</abbr> | [`condition`](metrics.md) |

Labels in this group (not numbers, so not usable in a score): `factor_issues`, `factor_opposition`, `factor_zopa`, `factor_constraint`, `factor_deception`, `factor_time_pressure`, `condition`, `assistant_condition`, `autopilot_driver`.

## Scores: combining criteria {#scores}

Any numeric measure on this page is a **criterion** that a score can be built from, together with the
items and scales of the project's own questionnaires (`q_<id>`, `scale_<name>`, and `post_q_<id>`,
`post_scale_<name>` for the post-session form). The column **Score** says whether a score can use a
criterion directly (*yes*) or only when it states a direction (*with a direction*: descriptive
counts and times, where neither more nor less is better by itself). Labels cannot be used.

A **score** is a weighted mean of criteria:

1. **Normalise.** Each component is mapped to $[0, 1]$, where 1 is the best value, by its
   criterion's default normaliser or its own (`bounded`, `advantage`, `reciprocal`, `saturating`,
   `percentile`, `clip`; see [Criteria and scores reference](criteria.md#normalisers)). With
   direction `lower` the mapping is turned around. Unbounded criteria are scaled by the median of
   the project's frozen reference, so adding games does not change past scores.
2. **Weigh.** Weights are ≥ 0 and **sum to 1**; a weight of 0 keeps a component without using it.
3. **Handle missing values** with `missing`: `renormalise` (default: the weights of the values
   present are rescaled to sum to 1), `zero` (a missing value counts as 0) or `skip_game` (no value
   for this game). `<score>_coverage` is the share of the weight whose values were present.
4. **Same parts for everyone.** On a board, a component present in fewer than `min_coverage` of
   some entrant's games is dropped for every entrant.

5. **Rules.** `zero_if` gives the game 0 (with coverage 1) when one of the listed criteria is 1 (an
   opponent that failed); `needs_assistant: true` leaves a game without an Assistant without a value
   (see [Rules for failures and sessions without an Assistant](project-management.md#rules-for-failures-and-sessions-without-an-assistant)).

A score is in $[0, 1]$, so it can be part of another score (no cycles). How to write a score is in
[Project management: scores](project-management.md#defining-a-score).

### Built-in scores

| Score | Track | What it measures | Parts (weights) | Rules |
| --- | --- | --- | --- | --- |
| `han_outcome` <abbr title="validated against a hand-computed example: tests/validation/test_validate_scores.py::test_scores_han_outcome">✓</abbr> | han | What the Opponent agent obtained against the Human (Human-Agent Negotiation track) | `opponent_advantage` 100% | 0 when `opponent_failed` is 1 |
| `han_interaction` <abbr title="validated against a hand-computed example: tests/validation/test_validate_scores.py::test_scores_han_interaction_full_row">✓</abbr> | han | How well the Opponent agent behaved as an opponent (Human-Agent Negotiation track) | `scale_opponent_kindness_norm` 12%, `scale_opponent_intelligence_norm` 12%, `scale_opponent_humanlike_norm` 12%, `scale_relationship_norm` 12%, `scale_satisfaction_norm` 6%, `jo_overall` 12%, `jo_communication` 6%, `jo_consistency` 6%, `jo_human_likeness` 6%, `opponent_failed` 12%, `opponent_irrational_accept` 6% | — |
| `hi_outcome` <abbr title="validated against a hand-computed example: tests/validation/test_validate_scores.py::test_scores_hi_outcome_and_utility">✓</abbr> | hi | What the human–Assistant team obtained (Hybrid Intelligence track) | `human_advantage` 100% | — |
| `hi_assistant` <abbr title="validated against a hand-computed example: tests/validation/test_validate_scores.py::test_scores_hi_assistant_full_row">✓</abbr> | hi | How well the Assistant worked as an Assistant (Hybrid Intelligence track) | `ja_overall` 11%, `ja_helpfulness` 5%, `ja_autonomy_respect` 5%, `assertions_met` 11%, `task_communicated` 11%, `assistant_critical_errors` 11%, `assistant_errors` 5%, `irrational_suggestions` 11%, `fn_success_rate` 5%, `unanswered_messages` 5%, `scale_ueq_pragmatic_norm` 5%, `scale_tam_usefulness_norm` 5%, `scale_felt_heard_norm` 5%, `scale_intention_to_use_norm` 5% | empty without an Assistant |
| `hi_team` <abbr title="validated against a hand-computed example: tests/validation/test_validate_scores.py::test_scores_hi_team_full_row">✓</abbr> | hi | How well the human–Assistant team worked together (Hybrid Intelligence track) | `human_overrode_harmfully` 17%, `human_critical_errors` 17%, `jh_use_of_assistant` 17%, `jh_engagement` 8%, `always_follows` 8%, `click_through` 8%, `irrational_accept` 17%, `welfare_optimality` 8% | empty without an Assistant |
| `hi_interaction` <abbr title="validated against a hand-computed example: tests/validation/test_validate_scores.py::test_scores_hi_interaction_full_row">✓</abbr> | hi | The Assistant and the team together: the ranked score of the HI interaction board | `hi_assistant` 50%, `hi_team` 50% | empty without an Assistant |
| `utility` <abbr title="validated against a hand-computed example: tests/validation/test_validate_scores.py::test_scores_hi_outcome_and_utility">✓</abbr> | any | The Human side's advantage alone, for any session | `human_advantage` 100% | — |

### Scores on leaderboards

A leaderboard ranks entrants (Assistants on the HI track, opponents on the HAN track) by one of its
`sort_options`, each a score or a criterion with a direction, and shows its `columns`. Each entrant's
value is the cell-adjusted mean over its counted games with a bootstrap confidence interval; an
entrant whose interval overlaps the leader's is tied with it. A board's count columns (games, players, guests, abandon rate, cost) describe the entrant, not a negotiation, so they are not measures of this page. The pickers of the score builder and of the board settings show the
criteria in the groups below, with ✓ next to validated ones. See
[Configuring a board](project-management.md#configuring-a-board) and
[Tracks and leaderboards](evaluation.md#tracks-and-leaderboards).
