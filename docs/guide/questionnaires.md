<!-- Generated from src/hani2/evaluation/catalog.py by scripts/make_metric_catalog.py. Do not edit by hand. -->


# Questionnaires

Every predefined questionnaire a project or study can use: what it measures, its source, its scales and every question with its answer scale. A ✓ marks a questionnaire validated against its source instrument: items, anchors, reversed items and scale scoring (see [What “validated” means](metric-catalog.md#validated)).

Pick them on the admin console's **Study forms** page (**Add predefined questionnaires**), which shows the same marks, or with `hani2 questionnaire compose`; see [Study forms](study-forms.md#predefined-questionnaires). Their scales and items become measures of the [Questionnaires (subjective)](metric-catalog.md#group-subjective) group, usable in scores and on leaderboards.

Each questionnaire is tagged with the party its questions are about (`tags`): `assistant`, `opponent`, both, or none (questions about the participant, the task or the system). A questionnaire tagged with both says `{{agent}}` (`{{Agent}}` at the start of a sentence) for the party, and each study fills in the party it evaluates: `opponent` in a HAN project (`kind: opponent`), `assistant` otherwise, or what the study's `questionnaire_agent` setting says.

| Questionnaire | Id | Questions | Validated | Source |
| --- | --- | --- | --- | --- |
| [NASA-TLX workload (raw, 7-point)](#nasa-tlx) | `nasa_tlx` | 6 | <abbr title="validated against the source instrument: tests/validation/test_validate_questionnaires.py::test_nasa_tlx_matches_source">✓</abbr> | [link](https://doi.org/10.1016/S0166-4115%2808%2962386-9) |
| [Subjective Value Inventory (SVI), 16 items](#subjective-value) | `subjective_value` | 16 | <abbr title="validated against the source instrument: tests/validation/test_validate_questionnaires.py::test_svi_matches_source">✓</abbr> | [link](https://www.subjectivevalue.com/) |
| [System Usability Scale (SUS), 10 items](#sus) | `sus` | 10 | <abbr title="validated against the source instrument: tests/validation/test_validate_questionnaires.py::test_sus_matches_source">✓</abbr> | yes |
| [TAM perceived ease of use, 6 items](#tam-ease) | `tam_ease` | 6 |  | [link](https://doi.org/10.2307/249008) |
| [TAM perceived usefulness, 6 items](#tam-usefulness) | `tam_usefulness` | 6 |  | [link](https://doi.org/10.2307/249008) |
| [TAM perceived usefulness, 2 items](#tam-usefulness-short) | `tam_usefulness_short` | 2 |  | [link](https://doi.org/10.2307/249008) |
| [Trust in automation (Jian et al.), 12 items](#trust-in-automation) | `trust_in_automation` | 12 | <abbr title="validated against the source instrument: tests/validation/test_validate_questionnaires.py::test_trust_in_automation_matches_source">✓</abbr> | [link](https://doi.org/10.1207/S15327566IJCE0401_04) |
| [UEQ, 8 items (the evaluation selection)](#ueq-eval) | `ueq_eval` | 8 |  | [link](https://www.ueq-online.org/) |
| [UEQ-S (short User Experience Questionnaire)](#ueq-s) | `ueq_s` | 8 | <abbr title="validated against the source instrument: tests/validation/test_validate_questionnaires.py::test_ueq_s_matches_source">✓</abbr> | [link](https://doi.org/10.9781/ijimai.2017.09.001) |
| [HAN2026-PreSession](#HAN2026-PreSession) | `HAN2026-PreSession` | 4 |  | competition |
| [HAN2026-PostNegotiation](#HAN2026-PostNegotiation) | `HAN2026-PostNegotiation` | 10 |  | competition |
| [HAN2026-PostSession](#HAN2026-PostSession) | `HAN2026-PostSession` | 8 |  | competition |
| [HAN2025-PreStudy](#HAN2025-PreStudy) | `HAN2025-PreStudy` | 19 |  | competition |
| [HAN2025-PostSession](#HAN2025-PostSession) | `HAN2025-PostSession` | 13 |  | competition |
| [HAN2025-PostStudy](#HAN2025-PostStudy) | `HAN2025-PostStudy` | 17 |  | competition |
| [ANAC-HAL2018-PostNegotiation](#ANAC-HAL2018-PostNegotiation) | `ANAC-HAL2018-PostNegotiation` | 3 |  | [link](https://doi.org/10.1109/ACII.2019.8925437) |
| [ANAC-HAL2017-PostNegotiation](#ANAC-HAL2017-PostNegotiation) | `ANAC-HAL2017-PostNegotiation` | 3 |  | [link](https://doi.org/10.1145/3267851.3267907) |
| [Experience with AI assistants](#ai-experience) | `ai_experience` | 4 |  | own items |
| [Use of and reliance on the Assistant](#assistant-reliance) | `assistant_reliance` | 4 |  | own items |
| [Attention check](#attention-check) | `attention_check` | 1 |  | own items |
| [Demographics](#demographics) | `demographics` | 4 |  | own items |
| [Intention to use and felt heard](#intention-to-use) | `intention_to_use` | 3 |  | own items |
| [Negotiation experience (participant type)](#negotiation-experience) | `negotiation_experience` | 2 |  | own items |
| [Opponent perception and relationship](#opponent-perception) | `opponent_perception` | 6 |  | own items |
| [Outcome satisfaction and enjoyment](#outcome-appreciation) | `outcome_appreciation` | 2 |  | own items |
| [Session feedback](#session-feedback) | `session_feedback` | 5 |  | own items |

## Standard instruments

### NASA-TLX workload (raw, 7-point) <abbr title="validated against the source instrument: tests/validation/test_validate_questionnaires.py::test_nasa_tlx_matches_source">✓</abbr> {#nasa-tlx}

Id `nasa_tlx` · 6 questions · for: `per_negotiation`, `post_session`

**Measures:** Workload of the task: mental, physical and temporal demand, performance, effort and frustration (raw TLX; lower is better).

**Source:** [Hart & Staveland (1988). Development of NASA-TLX (Task Load Index): results of empirical and theoretical research. In Hancock & Meshkati (eds.), Human Mental Workload. Advances in Psychology 52, 139–183.](https://doi.org/10.1016/S0166-4115%2808%2962386-9)

**Validated:** Checked against the NASA-TLX rating sheet: the six questions and their anchors (Very low … Very high; Performance from Perfect to Failure, so every item runs towards more workload), scored as the raw TLX (the unweighted mean of the six, without the pairwise weighting) and lower-is-better. Adapted: 7 answer points instead of the sheet's 21 gradations, so values are not on the 0–100 scale (100 × the _norm column is comparable).

Scales: `workload` (6 items) — each the mean of its items, reversed items scored backwards, as `scale_<name>` and `scale_<name>_norm`.

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `tlx_mental` | **Mental demand**: how mentally demanding was the task? | 1–7 (1 = Very low, 7 = Very high) | `workload` (lower is better) |
| 2 | `tlx_physical` | **Physical demand**: how physically demanding was the task? | 1–7 (1 = Very low, 7 = Very high) | `workload` (lower is better) |
| 3 | `tlx_temporal` | **Temporal demand**: how hurried or rushed was the pace of the task? | 1–7 (1 = Very low, 7 = Very high) | `workload` (lower is better) |
| 4 | `tlx_performance` | **Performance**: how successful were you in accomplishing what you were asked to do? | 1–7 (1 = Perfect, 7 = Failure) | `workload` (lower is better) |
| 5 | `tlx_effort` | **Effort**: how hard did you have to work to accomplish your level of performance? | 1–7 (1 = Very low, 7 = Very high) | `workload` (lower is better) |
| 6 | `tlx_frustration` | **Frustration**: how insecure, discouraged, irritated, stressed, and annoyed were you? | 1–7 (1 = Very low, 7 = Very high) | `workload` (lower is better) |

### Subjective Value Inventory (SVI), 16 items <abbr title="validated against the source instrument: tests/validation/test_validate_questionnaires.py::test_svi_matches_source">✓</abbr> {#subjective-value}

Id `subjective_value` · 16 questions · for: `per_negotiation`, `post_session`

**Measures:** Subjective value of a negotiation: feelings about the instrumental outcome, the self, the process and the relationship.

**Source:** [Curhan, Elfenbein & Xu (2006). What do people value when they negotiate? Mapping the domain of subjective value in negotiation. Journal of Personality and Social Psychology 91, 493–512.](https://www.subjectivevalue.com/)

**Validated:** Checked against the authors' item document: the 16 items, their 1/7 anchors, items 3 and 5 reversed, four 4-item subscales averaged. Worded for one opponent (the inventory says counterpart(s)); the midpoint anchors are not shown. The inventory's optional Global score (the mean of the four subscales) and Rapport score (Process and Relationship) are not columns: define them as scores with equal weights.

Scales: `svi_instrumental` (4 items), `svi_self` (4 items), `svi_process` (4 items), `svi_relationship` (4 items) — each the mean of its items, reversed items scored backwards, as `scale_<name>` and `scale_<name>_norm`.

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `svi_own_outcome` | How satisfied are you with your own outcome, i.e., the extent to which the terms of your agreement (or lack of agreement) benefit you? | 1–7 (1 = Not at all, 7 = Perfectly) | `svi_instrumental` |
| 2 | `svi_balance` | How satisfied are you with the balance between your own outcome and your opponent's outcome? | 1–7 (1 = Not at all, 7 = Perfectly) | `svi_instrumental` |
| 3 | `svi_lost` | Did you feel like you forfeited or "lost" in this negotiation? | 1–7 (1 = Not at all, 7 = A great deal) | `svi_instrumental` (reversed) |
| 4 | `svi_legitimate` | Do you think the terms of your agreement are consistent with principles of legitimacy or objective criteria (e.g., common standards of fairness, precedent, industry practice, legality, etc.)? | 1–7 (1 = Not at all, 7 = Perfectly) | `svi_instrumental` |
| 5 | `svi_lose_face` | Did you "lose face" (damage your sense of pride) in the negotiation? | 1–7 (1 = Not at all, 7 = A great deal) | `svi_self` (reversed) |
| 6 | `svi_competent` | Did this negotiation make you feel more or less competent as a negotiator? | 1–7 (1 = It made me feel less competent, 7 = It made me feel more competent) | `svi_self` |
| 7 | `svi_principles` | Did you behave according to your own principles and values? | 1–7 (1 = Not at all, 7 = Perfectly) | `svi_self` |
| 8 | `svi_self_image` | Did this negotiation positively or negatively impact your self-image or your impression of yourself? | 1–7 (1 = It negatively impacted my self-image, 7 = It positively impacted my self-image) | `svi_self` |
| 9 | `svi_listened` | Do you feel your opponent listened to your concerns? | 1–7 (1 = Not at all, 7 = Perfectly) | `svi_process` |
| 10 | `svi_fair` | Would you characterize the negotiation process as fair? | 1–7 (1 = Not at all, 7 = Perfectly) | `svi_process` |
| 11 | `svi_ease` | How satisfied are you with the ease (or difficulty) of reaching an agreement? | 1–7 (1 = Not at all satisfied, 7 = Perfectly satisfied) | `svi_process` |
| 12 | `svi_considered` | Did your opponent consider your wishes, opinions or needs? | 1–7 (1 = Not at all, 7 = Perfectly) | `svi_process` |
| 13 | `svi_impression` | What kind of "overall" impression did your opponent make on you? | 1–7 (1 = Extremely negative, 7 = Extremely positive) | `svi_relationship` |
| 14 | `svi_relationship` | How satisfied are you with your relationship with your opponent as a result of this negotiation? | 1–7 (1 = Not at all, 7 = Perfectly) | `svi_relationship` |
| 15 | `svi_trust` | Did the negotiation make you trust your opponent? | 1–7 (1 = Not at all, 7 = Perfectly) | `svi_relationship` |
| 16 | `svi_foundation` | Did the negotiation build a good foundation for a future relationship with your opponent? | 1–7 (1 = Not at all, 7 = Perfectly) | `svi_relationship` |

### System Usability Scale (SUS), 10 items <abbr title="validated against the source instrument: tests/validation/test_validate_questionnaires.py::test_sus_matches_source">✓</abbr> {#sus}

Id `sus` · 10 questions · for: `post_session`

**Measures:** Perceived usability of the negotiation interface (0–100).

**Source:** Brooke (1996). SUS: a “quick and dirty” usability scale. In Jordan et al. (eds.), Usability Evaluation in Industry. Taylor & Francis.

**Validated:** Checked: the 10 items, the 5-point agreement anchors, even items reversed, and that the standard score 2.5 × Σ(contributions) equals 100 × scale_sus_norm. “System” is kept as in the original.

Scales: `sus` (10 items) — each the mean of its items, reversed items scored backwards, as `scale_<name>` and `scale_<name>_norm`.

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `sus_1` | I think that I would like to use this system frequently. | 1–5 (1 = Strongly disagree, 5 = Strongly agree) | `sus` |
| 2 | `sus_2` | I found the system unnecessarily complex. | 1–5 (1 = Strongly disagree, 5 = Strongly agree) | `sus` (reversed) |
| 3 | `sus_3` | I thought the system was easy to use. | 1–5 (1 = Strongly disagree, 5 = Strongly agree) | `sus` |
| 4 | `sus_4` | I think that I would need the support of a technical person to be able to use this system. | 1–5 (1 = Strongly disagree, 5 = Strongly agree) | `sus` (reversed) |
| 5 | `sus_5` | I found the various functions in this system were well integrated. | 1–5 (1 = Strongly disagree, 5 = Strongly agree) | `sus` |
| 6 | `sus_6` | I thought there was too much inconsistency in this system. | 1–5 (1 = Strongly disagree, 5 = Strongly agree) | `sus` (reversed) |
| 7 | `sus_7` | I would imagine that most people would learn to use this system very quickly. | 1–5 (1 = Strongly disagree, 5 = Strongly agree) | `sus` |
| 8 | `sus_8` | I found the system very cumbersome to use. | 1–5 (1 = Strongly disagree, 5 = Strongly agree) | `sus` (reversed) |
| 9 | `sus_9` | I felt very confident using the system. | 1–5 (1 = Strongly disagree, 5 = Strongly agree) | `sus` |
| 10 | `sus_10` | I needed to learn a lot of things before I could get going with this system. | 1–5 (1 = Strongly disagree, 5 = Strongly agree) | `sus` (reversed) |

### TAM perceived ease of use, 6 items {#tam-ease}

Id `tam_ease` · 6 questions · for: `per_negotiation`, `post_session`

**Measures:** Perceived ease of use of the Assistant (Technology Acceptance Model).

**Source:** [Davis (1989). Perceived usefulness, perceived ease of use, and user acceptance of information technology. MIS Quarterly 13(3), 319–340.](https://doi.org/10.2307/249008)

**Validation:** Not validated: not yet checked against the published items (no readable copy of the item sheet was found). The six items follow Davis's ease-of-use items, reworded for a negotiation assistant, with agree–disagree anchors.

!!! warning "Items not checked against the source"
    The TAM items have not been checked against the published instrument (Davis, 1989): no readable copy of the item sheet was found. The scoring of the scale is validated; the wording of its items is not, so results may not be comparable with published TAM scores.

Scales: `tam_ease` (6 items) — each the mean of its items, reversed items scored backwards, as `scale_<name>` and `scale_<name>_norm`.

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `tam_easy_learn` | Learning to work with this assistant was easy for me. *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `tam_ease` |
| 2 | `tam_controllable` | I found it easy to get the assistant to do what I wanted. *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `tam_ease` |
| 3 | `tam_clear` | My interaction with the assistant was clear and understandable. *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `tam_ease` |
| 4 | `tam_flexible` | I found the assistant flexible to interact with. *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `tam_ease` |
| 5 | `tam_skillful` | It would be easy for me to become skillful at using this assistant. *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `tam_ease` |
| 6 | `tam_easy_use` | I found the assistant easy to use. *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `tam_ease` |

### TAM perceived usefulness, 6 items {#tam-usefulness}

Id `tam_usefulness` · 6 questions · for: `per_negotiation`, `post_session`

**Measures:** Perceived usefulness of the Assistant (Technology Acceptance Model).

**Source:** [Davis (1989). Perceived usefulness, perceived ease of use, and user acceptance of information technology. MIS Quarterly 13(3), 319–340.](https://doi.org/10.2307/249008)

**Validation:** Not validated: not yet checked against the published items (no readable copy of the item sheet was found). The six items follow Davis's usefulness items, reworded for a negotiation assistant, with agree–disagree anchors.

!!! warning "Items not checked against the source"
    The TAM items have not been checked against the published instrument (Davis, 1989): no readable copy of the item sheet was found. The scoring of the scale is validated; the wording of its items is not, so results may not be comparable with published TAM scores.

Scales: `tam_usefulness` (6 items) — each the mean of its items, reversed items scored backwards, as `scale_<name>` and `scale_<name>_norm`.

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `tam_quicker` | Using this assistant would let me negotiate more quickly. *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `tam_usefulness` |
| 2 | `tam_performance` | Using this assistant would improve my negotiation results. *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `tam_usefulness` |
| 3 | `tam_productivity` | Using this assistant would make me more productive when negotiating. *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `tam_usefulness` |
| 4 | `tam_effectiveness` | Using this assistant would enhance my effectiveness in negotiation. *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `tam_usefulness` |
| 5 | `tam_easier` | Using this assistant would make negotiating easier. *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `tam_usefulness` |
| 6 | `tam_useful` | I would find this assistant useful in negotiations. *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `tam_usefulness` |

### TAM perceived usefulness, 2 items {#tam-usefulness-short}

Id `tam_usefulness_short` · 2 questions · for: `per_negotiation`, `post_session`

**Measures:** Perceived usefulness of the Assistant, two items (Technology Acceptance Model).

**Source:** [Davis (1989). Perceived usefulness, perceived ease of use, and user acceptance of information technology. MIS Quarterly 13(3), 319–340.](https://doi.org/10.2307/249008)

**Validation:** Not validated: a two-item selection of the usefulness items, reworded; not yet checked against the published items (no readable copy of the item sheet was found).

!!! warning "Items not checked against the source"
    The TAM items have not been checked against the published instrument (Davis, 1989): no readable copy of the item sheet was found. The scoring of the scale is validated; the wording of its items is not, so results may not be comparable with published TAM scores.

Scales: `tam_usefulness` (2 items) — each the mean of its items, reversed items scored backwards, as `scale_<name>` and `scale_<name>_norm`.

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `tam_effectiveness` | Using this assistant would enhance my effectiveness in negotiation. *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `tam_usefulness` |
| 2 | `tam_useful` | I would find this assistant useful in negotiations. *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `tam_usefulness` |

### Trust in automation (Jian et al.), 12 items <abbr title="validated against the source instrument: tests/validation/test_validate_questionnaires.py::test_trust_in_automation_matches_source">✓</abbr> {#trust-in-automation}

Id `trust_in_automation` · 12 questions · for: `per_negotiation`, `post_session`

**Measures:** Trust in the Assistant or the opponent, the party the study evaluates (Checklist for Trust between People and Automation).

**Source:** [Jian, Bisantz & Drury (2000). Foundations for an empirically determined scale of trust in automated systems. International Journal of Cognitive Ergonomics 4(1), 53–71.](https://doi.org/10.1207/S15327566IJCE0401_04)

**Validated:** Checked against the checklist's 12 items as reproduced in McGrath et al. (2025, Frontiers in Artificial Intelligence, Table 1): wording, 1 = not at all … 7 = extremely, items 1–5 reverse scored, the trust score the mean of the 12. Adapted: “the system” is worded as “the assistant” or “the opponent” ({{agent}}).

Scales: `trust_automation` (12 items) — each the mean of its items, reversed items scored backwards, as `scale_<name>` and `scale_<name>_norm`.

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `tia_deceptive` | The {{agent}} is deceptive. *(about the Assistant: only with one)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` (reversed) |
| 2 | `tia_underhanded` | The {{agent}} behaves in an underhanded manner. *(about the Assistant: only with one)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` (reversed) |
| 3 | `tia_suspicious` | I am suspicious of the {{agent}}'s intent, action, or output. *(about the Assistant: only with one)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` (reversed) |
| 4 | `tia_wary` | I am wary of the {{agent}}. *(about the Assistant: only with one)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` (reversed) |
| 5 | `tia_harmful` | The {{agent}}'s action will have a harmful or injurious outcome. *(about the Assistant: only with one)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` (reversed) |
| 6 | `tia_confident` | I am confident in the {{agent}}. *(about the Assistant: only with one)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` |
| 7 | `tia_security` | The {{agent}} provides security. *(about the Assistant: only with one)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` |
| 8 | `tia_integrity` | The {{agent}} has integrity. *(about the Assistant: only with one)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` |
| 9 | `tia_dependable` | The {{agent}} is dependable. *(about the Assistant: only with one)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` |
| 10 | `tia_reliable` | The {{agent}} is reliable. *(about the Assistant: only with one)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` |
| 11 | `tia_trust` | I can trust the {{agent}}. *(about the Assistant: only with one)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` |
| 12 | `tia_familiar` | I am familiar with the {{agent}}. *(about the Assistant: only with one)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` |

### UEQ, 8 items (the evaluation selection) {#ueq-eval}

Id `ueq_eval` · 8 questions · for: `per_negotiation`, `post_session`

**Measures:** Usability of the Assistant or the opponent (the party the study evaluates) with eight items of the full UEQ, as two scales (ueq_pragmatic, ueq_hedonic).

**Source:** [Laugwitz, Held & Schrepp (2008). Construction and evaluation of a user experience questionnaire. USAB 2008, LNCS 5298, 63–76.](https://www.ueq-online.org/)

**Validation:** Not validated as a UEQ scale: the items are UEQ items 2, 5, 11, 12, 13, 20, 21 and 22 and the positive-left ones are reversed (tested; the handbook confirms the poles of item 21, while the positive-left order of items 5 and 12 could not be checked against a copy of the full questionnaire). The UEQ has six scales, not these two: ueq_hedonic mixes a Stimulation item (valuable) with an Attractiveness item (good), and the UEQ handbook counts Attractiveness as neither pragmatic nor hedonic.

Scales: `ueq_pragmatic` (6 items), `ueq_hedonic` (2 items) — each the mean of its items, reversed items scored backwards, as `scale_<name>` and `scale_<name>_norm`.

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `ueq_understandable` | The {{agent}} was …  (1 = not understandable, 7 = understandable) *(about the Assistant: only with one)* | 1–7 (1 = not understandable, 7 = understandable) | `ueq_pragmatic` |
| 2 | `ueq_valuable` | The {{agent}} was …  (1 = valuable, 7 = inferior) *(about the Assistant: only with one)* | 1–7 (1 = valuable, 7 = inferior) | `ueq_hedonic` (reversed) |
| 3 | `ueq_supportive` | The {{agent}} was …  (1 = obstructive, 7 = supportive) *(about the Assistant: only with one)* | 1–7 (1 = obstructive, 7 = supportive) | `ueq_pragmatic` |
| 4 | `ueq_good` | The {{agent}} was …  (1 = good, 7 = bad) *(about the Assistant: only with one)* | 1–7 (1 = good, 7 = bad) | `ueq_hedonic` (reversed) |
| 5 | `ueq_easy` | The {{agent}} was …  (1 = complicated, 7 = easy) *(about the Assistant: only with one)* | 1–7 (1 = complicated, 7 = easy) | `ueq_pragmatic` |
| 6 | `ueq_efficient` | The {{agent}} was …  (1 = inefficient, 7 = efficient) *(about the Assistant: only with one)* | 1–7 (1 = inefficient, 7 = efficient) | `ueq_pragmatic` |
| 7 | `ueq_clear` | The {{agent}} was …  (1 = clear, 7 = confusing) *(about the Assistant: only with one)* | 1–7 (1 = clear, 7 = confusing) | `ueq_pragmatic` (reversed) |
| 8 | `ueq_practical` | The {{agent}} was …  (1 = impractical, 7 = practical) *(about the Assistant: only with one)* | 1–7 (1 = impractical, 7 = practical) | `ueq_pragmatic` |

### UEQ-S (short User Experience Questionnaire) <abbr title="validated against the source instrument: tests/validation/test_validate_questionnaires.py::test_ueq_s_matches_source">✓</abbr> {#ueq-s}

Id `ueq_s` · 8 questions · for: `per_negotiation`, `post_session`

**Measures:** User experience of the Assistant or the opponent (the party the study evaluates): pragmatic quality (supportive, easy, efficient, clear) and hedonic quality (exciting, interesting, inventive, leading edge).

**Source:** [Schrepp, Hinderks & Thomaschewski (2017). Design and evaluation of a short version of the User Experience Questionnaire (UEQ-S). IJIMAI 4(6), 103–108.](https://doi.org/10.9781/ijimai.2017.09.001)

**Validated:** Checked against the UEQ-S item sheet and the UEQ handbook: the 8 items in order, negative pole left, items 1–4 pragmatic and 5–8 hedonic, each scale the mean of its items. HANI2 scores 1–7; subtract 4 for the handbook's −3…+3.

Scales: `ueqs_pragmatic` (4 items), `ueqs_hedonic` (4 items) — each the mean of its items, reversed items scored backwards, as `scale_<name>` and `scale_<name>_norm`.

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `ueqs_supportive` | The {{agent}} was … *(about the Assistant: only with one)* | 1–7 (1 = obstructive, 7 = supportive) | `ueqs_pragmatic` |
| 2 | `ueqs_easy` | The {{agent}} was … *(about the Assistant: only with one)* | 1–7 (1 = complicated, 7 = easy) | `ueqs_pragmatic` |
| 3 | `ueqs_efficient` | The {{agent}} was … *(about the Assistant: only with one)* | 1–7 (1 = inefficient, 7 = efficient) | `ueqs_pragmatic` |
| 4 | `ueqs_clear` | The {{agent}} was … *(about the Assistant: only with one)* | 1–7 (1 = confusing, 7 = clear) | `ueqs_pragmatic` |
| 5 | `ueqs_exciting` | The {{agent}} was … *(about the Assistant: only with one)* | 1–7 (1 = boring, 7 = exciting) | `ueqs_hedonic` |
| 6 | `ueqs_interesting` | The {{agent}} was … *(about the Assistant: only with one)* | 1–7 (1 = not interesting, 7 = interesting) | `ueqs_hedonic` |
| 7 | `ueqs_inventive` | The {{agent}} was … *(about the Assistant: only with one)* | 1–7 (1 = conventional, 7 = inventive) | `ueqs_hedonic` |
| 8 | `ueqs_leading_edge` | The {{agent}} was … *(about the Assistant: only with one)* | 1–7 (1 = usual, 7 = leading edge) | `ueqs_hedonic` |

## Questionnaires of negotiation competitions

The questions that human-agent negotiation competitions asked their participants, as asked (typos included), so that a study can repeat them and compare with the competition's results. They are not validated instruments.

### HAN2026-PreSession {#HAN2026-PreSession}

Id `HAN2026-PreSession` · 4 questions · for: `pre_questionnaire`

**Measures:** HAN 2026, once before the first session: negotiation experience, familiarity with AI, own skill and the skill expected of the opponents.

**Source:** Questionnaires of the HAN 2026 human-agent negotiation competition

**Validation:** Not validated: the questions as asked in HAN 2026 (from the competition's form files), not a validated instrument; typos are kept as asked.

Scales: none (single items).

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `experience_negotiation` | How much prior experience do you have negotiating in everyday life (e.g. salary, prices, agreements)? | 1–5 (1 = None, 5 = A great deal) |  |
| 2 | `experience_ai` | How familiar are you with AI / chatbot systems? | 1–5 (1 = Not at all familiar, 5 = Very familiar) |  |
| 3 | `self_skill` | How skilled are you as a negotiator? | Very Unskilled · Unskilled · Neither · Skilled · Very Skilled |  |
| 4 | `session_expectation` | How skilled do you expect your opponent agents as negotiators? | Very Unskilled · Unskilled · Neither · Skilled · Very Skilled |  |

### HAN2026-PostNegotiation {#HAN2026-PostNegotiation}

Id `HAN2026-PostNegotiation` · 10 questions · for: `per_negotiation`

**Measures:** HAN 2026, after each negotiation: the opponent's strategy, intelligence and skill, employability, engagement, its messages, time pressure and satisfaction with the outcome.

**Source:** Questionnaires of the HAN 2026 human-agent negotiation competition

**Validation:** Not validated: the questions as asked in HAN 2026 (from the competition's form files), not a validated instrument; typos are kept as asked.

Scales: none (single items).

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `agent_strategy` | How would you describe the agent's strategy this round? | Cooperative · Competitive · Random · Couldn't tell |  |
| 2 | `agent_employability` | How likely is it for you to employ your opponent agent to negotiate in your behalf? | Very Unlikely · Unlikely · Couldn't tell · Likely · Very Likely |  |
| 3 | `agent_intelligenct` | How intelligent was your opponent in this negotiation? | Very Stupid · Stupid · Neither · Intelligent · Very Intelligent |  |
| 4 | `agent_skill` | How skilled was your opponent in this negotiation? | Very Unskilled · Unskilled · Neither · Skilled · Very Skilled |  |
| 5 | `agent_engagement` | How engaging was this negotiation? | Not at all · A little · Neutral · Engaging · Very Engaging |  |
| 6 | `agent_text_useful` | Did the agent's text messages (if any) influence your decisions? | No text · Yes, helpful · Yes, misleading · Ignored them |  |
| 7 | `agent_time` | To what extend did you consider the time-limit during the negotiation? | 1–5 (1 = Not At All, 3 = Moderate, 5 = Very Much) |  |
| 8 | `agent_opponent_behavior` | To what extend did you consider the opponent offers during the negotiation | 1–5 (1 = Not At All, 3 = Moderate, 5 = Very Much) |  |
| 9 | `satisfaction_with_outcome` | How satisfied are you with the outcome of this negotiation? | 1–5 (1 = Very dissatisfied, 5 = Very satisfied) |  |
| 10 | `comment` | Anything specific about this negotiation? (Optional, one line.) | free text |  |

### HAN2026-PostSession {#HAN2026-PostSession}

Id `HAN2026-PostSession` · 8 questions · for: `post_session`

**Measures:** HAN 2026, after each session: ease of use, engagement and the usefulness of each interface tool.

**Source:** Questionnaires of the HAN 2026 human-agent negotiation competition

**Validation:** Not validated: the questions as asked in HAN 2026 (from the competition's form files), not a validated instrument; typos are kept as asked.

Scales: none (single items).

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `ease_of_use` | How easy was the negotiation interface to use? | 1–5 (1 = Very difficult, 5 = Very easy) |  |
| 2 | `engagement` | How engaging did you find the negotiation task? | 1–5 (1 = Not at all engaging, 5 = Very engaging) |  |
| 3 | `tool_preferences` | How useful was the Preferences tab (your utility weights / preferences) during the session? | I did not use this tool · Not useful at all · Slightly useful · Moderately useful · Very useful · Extremely useful |  |
| 4 | `tool_scenario_info` | How useful was the Scenario Info tab (description of the scenario you were bargaining over)? | I did not use this tool · Not useful at all · Slightly useful · Moderately useful · Very useful · Extremely useful |  |
| 5 | `tool_value_histogram` | How useful was the Value Histogram tab (distribution of issue values you've offered/received)? | I did not use this tool · Not useful at all · Slightly useful · Moderately useful · Very useful · Extremely useful |  |
| 6 | `tool_trace` | How useful was the Trace tab (full history of offers and messages)? | I did not use this tool · Not useful at all · Slightly useful · Moderately useful · Very useful · Extremely useful |  |
| 7 | `tool_utility_selector` | How useful was the outcome-sampling helper on the right side (the Utility-based Selector that lets you generate offers at a target utility)? | I did not use this tool · Not useful at all · Slightly useful · Moderately useful · Very useful · Extremely useful |  |
| 8 | `comments` | Anything else you would like to tell us about this session? (Optional.) | free text |  |

### HAN2025-PreStudy {#HAN2025-PreStudy}

Id `HAN2025-PreStudy` · 19 questions · for: `pre_questionnaire`

**Measures:** HAN 2025, once before any negotiation: background, expertise and expectations about the system and AI negotiators.

**Source:** Questionnaires of the HAN 2025 human-agent negotiation competition (pilot, IJCAI 2025)

**Validation:** Not validated: the questions of the competition's Google Form as asked (typos included), not a validated instrument. Converted to HANI2 questions: the identification items (user name, session id, date and time, number of negotiations) are left out, a question the form asks twice is kept once, the expertise grid is one question per field, and the 1–5 linear scales (no endpoint labels in the form) are likert5.

Scales: none (single items).

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `han2025_age` | What is your age? | 18-25 · 25-30 · 30-35 · 40+ |  |
| 2 | `han2025_country` | What is your country of residence? | free text |  |
| 3 | `han2025_degree` | What is your latest degree? | free text |  |
| 4 | `han2025_prior_study` | Did you participate in any study in which you negotiated with a human or machine? If yes, explain briefly. | free text |  |
| 5 | `han2025_expertise_ai` | Did you study or conduct your own research in the following area? Please indicate your level of expertise in each. — Artificial Intelligence | Expert · Beginner · Layman |  |
| 6 | `han2025_expertise_game_theory` | Did you study or conduct your own research in the following area? Please indicate your level of expertise in each. — Game Theory | Expert · Beginner · Layman |  |
| 7 | `han2025_expertise_economics` | Did you study or conduct your own research in the following area? Please indicate your level of expertise in each. — Economics | Expert · Beginner · Layman |  |
| 8 | `han2025_expertise_business` | Did you study or conduct your own research in the following area? Please indicate your level of expertise in each. — Business | Expert · Beginner · Layman |  |
| 9 | `han2025_expertise_automated_negotiation` | Did you study or conduct your own research in the following area? Please indicate your level of expertise in each. — Automated Negotiation | Expert · Beginner · Layman |  |
| 10 | `han2025_expect_enjoyable` | (7) How enjoyable do you expect the negotiation with our system (5 = most enjoyable)? | 1–5 |  |
| 11 | `han2025_expect_easy` | How easy do you expect the negotiation with our system (5 = easiest)? | 1–5 |  |
| 12 | `han2025_expect_usable` | How usable do you expect our system to be (5 = most usable)? | 1–5 |  |
| 13 | `han2025_expect_humanlike` | How human-like do you expect your AI negotiation partner to b (5 = most human-like)? | 1–5 |  |
| 14 | `han2025_expect_ai_negotiating` | How effective do you expect an AI negotiation system in negotiating with human partners (5 = most effective)? | 1–5 |  |
| 15 | `han2025_expect_ai_supporting` | How effective do you expect an AI negotiation system in supporting its own human user (5 = most effective)? | 1–5 |  |
| 16 | `han2025_expect_high_utility` | How confident are you in achieving high utilities (scores) when negotiating with our system (5 = most confident)? | 1–5 |  |
| 17 | `han2025_expect_structured_offers` | How effective do you expect structured offers in human-agent negotiation (5 = most effective)? | 1–5 |  |
| 18 | `han2025_expect_natural_language` | How effective do you expect allowing natural language interaction in human-agent negotiation (5 = most effective)? | 1–5 |  |
| 19 | `han2025_expect_fairness` | How fair do you expect the results of negotiations with an AI be? (0 = fair)? | (-2) highly biased towards the AI · (-1) slightly biased towards the AI · (0) fair · (1) slightly biased towards the human · (2) highly biased towards the human |  |

### HAN2025-PostSession {#HAN2025-PostSession}

Id `HAN2025-PostSession` · 13 questions · for: `post_session`

**Measures:** HAN 2025, after a negotiation session: enjoyment, ease, the opponent's human-likeness, intelligence, speed and predictability, support and expectations about AI negotiators.

**Source:** Questionnaires of the HAN 2025 human-agent negotiation competition (pilot, IJCAI 2025)

**Validation:** Not validated: the questions of the competition's Google Form as asked (typos included), not a validated instrument. Converted to HANI2 questions: the identification items (user name, session id, date and time, number of negotiations) are left out, a question the form asks twice is kept once, the expertise grid is one question per field, and the 1–5 linear scales (no endpoint labels in the form) are likert5.

Scales: none (single items).

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `han2025_enjoyable` | How enjoyable was the negotiation with our system (5 = most enjoyable)? | 1–5 |  |
| 2 | `han2025_easy` | How easy was the negotiation with our system (5 = easiest)? | 1–5 |  |
| 3 | `han2025_humanlike` | How human-like was your AI negotiation partner to b (5 = most human-like)? | 1–5 |  |
| 4 | `han2025_helpful_support` | How helpful is our system as a negotiation support system (5 = most helpful)? | 1–5 |  |
| 5 | `han2025_useful_tools` | Which tools were most useful for you in supporting your negotiation? | free text |  |
| 6 | `han2025_opponent_intelligent` | How intelligent was our system as a negotiator against you (5 = most intelligent)? | 1–5 |  |
| 7 | `han2025_opponent_fast` | How fast was our system as a negotiator against you (5 = fastest)? | 1–5 |  |
| 8 | `han2025_opponent_predictable` | How predictable was the performance of our system as a negotiator against you (5 = most predictable)? | 1–5 |  |
| 9 | `han2025_expect_ai_negotiating` | How effective do you expect an AI negotiation system in negotiating with human partners (5 = most effective)? | 1–5 |  |
| 10 | `han2025_expect_ai_supporting` | How effective do you expect an AI negotiation system in supporting its own human user (5 = most effective)? | 1–5 |  |
| 11 | `han2025_expect_high_utility` | How confident are you in achieving high utilities (scores) when negotiating with our system (5 = most confident)? | 1–5 |  |
| 12 | `han2025_expect_structured_offers` | How effective do you expect structured offers in human-agent negotiation (5 = most effective)? | 1–5 |  |
| 13 | `han2025_expect_natural_language` | How effective do you expect allowing natural language interaction in human-agent negotiation (5 = most effective)? | 1–5 |  |

### HAN2025-PostStudy {#HAN2025-PostStudy}

Id `HAN2025-PostStudy` · 17 questions · for: `post_session`

**Measures:** HAN 2025, once after the whole competition: the post-session questions, understanding of the scenario, comments and strategy.

**Source:** Questionnaires of the HAN 2025 human-agent negotiation competition (pilot, IJCAI 2025)

**Validation:** Not validated: the questions of the competition's Google Form as asked (typos included), not a validated instrument. Converted to HANI2 questions: the identification items (user name, session id, date and time, number of negotiations) are left out, a question the form asks twice is kept once, the expertise grid is one question per field, and the 1–5 linear scales (no endpoint labels in the form) are likert5.

Scales: none (single items).

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `han2025_enjoyable` | How enjoyable was the negotiation with our system (5 = most enjoyable)? | 1–5 |  |
| 2 | `han2025_easy_understanding` | How easy was understanding the negotiation scenario and your preferences (5 = easiest)? | 1–5 |  |
| 3 | `han2025_easy` | How easy was the negotiation with our system (5 = easiest)? | 1–5 |  |
| 4 | `han2025_humanlike` | How human-like was your AI negotiation partner to b (5 = most human-like)? | 1–5 |  |
| 5 | `han2025_understood_confident` | How confident are you that you fully understood the description of the negotiation scenario and your preferences (5 = most confident)? | 1–5 |  |
| 6 | `han2025_helpful_support` | How helpful is our system as a negotiation support system (5 = most helpful)? | 1–5 |  |
| 7 | `han2025_useful_tools` | Which tools were most useful for you in supporting your negotiation? | free text |  |
| 8 | `han2025_opponent_intelligent` | How intelligent was our system as a negotiator against you (5 = most intelligent)? | 1–5 |  |
| 9 | `han2025_opponent_fast` | How fast was our system as a negotiator against you (5 = fastest)? | 1–5 |  |
| 10 | `han2025_opponent_predictable` | How predictable was the performance of our system as a negotiator against you (5 = most predictable)? | 1–5 |  |
| 11 | `han2025_expect_ai_negotiating` | How effective do you expect an AI negotiation system in negotiating with human partners (5 = most effective)? | 1–5 |  |
| 12 | `han2025_expect_ai_supporting` | How effective do you expect an AI negotiation system in supporting its own human user (5 = most effective)? | 1–5 |  |
| 13 | `han2025_expect_high_utility` | How confident are you in achieving high utilities (scores) when negotiating with our system (5 = most confident)? | 1–5 |  |
| 14 | `han2025_expect_structured_offers` | How effective do you expect structured offers in human-agent negotiation (5 = most effective)? | 1–5 |  |
| 15 | `han2025_expect_natural_language` | How effective do you expect allowing natural language interaction in human-agent negotiation (5 = most effective)? | 1–5 |  |
| 16 | `han2025_comments` | Please freely add any comments, challenges, suggestions, or thoughts about your experience in this competition. | free text |  |
| 17 | `han2025_strategy` | Please describe your strategy for conducting negotiations. Any tips that can be helpful for negotiating with AI agents that you learned or tested in your negotiations with our systems are highly appreciated | free text |  |

### ANAC-HAL2018-PostNegotiation {#ANAC-HAL2018-PostNegotiation}

Id `ANAC-HAL2018-PostNegotiation` · 3 questions · for: `per_negotiation`

**Measures:** ANAC 2018 Human-Agent League, after each negotiation: likeability of the agent (satisfaction with the agreement, liking the opponent, would negotiate again).

**Source:** [Mell, Gratch, Aydoğan, Baarslag & Jonker (2019). The likeability-success tradeoff: results of the 2nd annual human-agent automated negotiating agents competition. ACII 2019.](https://doi.org/10.1109/ACII.2019.8925437)

**Validation:** Not validated: the questions as reported in the competition's results paper, with its 7-point answers; the paper gives no anchor labels and no rule for combining the items. HANI2 scores them as the mean of the three (hal_likeability), its own choice.

Scales: `hal_likeability` (3 items) — each the mean of its items, reversed items scored backwards, as `scale_<name>` and `scale_<name>_norm`.

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `hal_satisfied_agreement` | How satisfied were you with the final agreement? | 1–7 | `hal_likeability` |
| 2 | `hal_like_opponent` | How much do you like your opponent? | 1–7 | `hal_likeability` |
| 3 | `hal_negotiate_again` | Would you negotiate with this opponent again? | 1–7 | `hal_likeability` |

### ANAC-HAL2017-PostNegotiation {#ANAC-HAL2017-PostNegotiation}

Id `ANAC-HAL2017-PostNegotiation` · 3 questions · for: `per_negotiation`

**Measures:** ANAC 2017 Human-Agent League, after the negotiation: likeability of the agent (satisfaction with the agreement, liking the opponent, would negotiate again).

**Source:** [Mell, Gratch, Baarslag, Aydoğan & Jonker (2018). Results of the first annual human-agent league of the automated negotiating agents competition. IVA '18, 23–28.](https://doi.org/10.1145/3267851.3267907)

**Validation:** Not validated: the questions as reported in the competition's results paper, with its 7-point answers; the paper gives no anchor labels and no rule for combining the items. HANI2 scores them as the mean of the three (hal_likeability), its own choice.

Scales: `hal_likeability` (3 items) — each the mean of its items, reversed items scored backwards, as `scale_<name>` and `scale_<name>_norm`.

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `hal_satisfied_agreement` | How satisfied were you with the final agreement? | 1–7 | `hal_likeability` |
| 2 | `hal_like_opponent` | How much do you like your opponent? | 1–7 | `hal_likeability` |
| 3 | `hal_negotiate_again` | Would you negotiate with this opponent again? | 1–7 | `hal_likeability` |

## HANI2's own question sets

Items written for HANI2 studies. They have no source instrument, so they are not validated against one; their scales are scored by the same validated rules as every questionnaire.

### Experience with AI assistants {#ai-experience}

Id `ai_experience` · 4 questions · for: `pre_questionnaire`

**Measures:** Familiarity with AI assistants and expected reliance on one.

**Validation:** Own items; there is no source instrument.

Scales: none (single items).

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `ai_use_frequency` | How often do you use AI assistants (ChatGPT, Claude, Gemini, Copilot, …)? | Never · Less than once a month · A few times a month · Weekly · Daily |  |
| 2 | `ai_experience` | How experienced are you with AI assistants? | 1–5 (1 = Not at all, 5 = Very experienced) |  |
| 3 | `ai_expected_reliance` | How much do you expect to rely on an AI assistant when negotiating? | 1–5 (1 = Not at all, 5 = Completely) |  |
| 4 | `ai_general_trust` | In general, I trust AI systems. | 1–7 (1 = Strongly disagree, 7 = Strongly agree) |  |

### Use of and reliance on the Assistant {#assistant-reliance}

Id `assistant_reliance` · 4 questions · for: `per_negotiation`

**Measures:** How much the participant used, followed and trusted the Assistant, and who gets the credit.

**Validation:** Own items; there is no source instrument.

Scales: `reliance` (2 items) — each the mean of its items, reversed items scored backwards, as `scale_<name>` and `scale_<name>_norm`.

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `reliance_use` | How much did you use the assistant in this negotiation? | I did not use it · A little · Moderately · A lot · For almost every move |  |
| 2 | `reliance_follow` | How often did you follow the assistant's suggestions? *(only with an Assistant)* | 1–7 (1 = Never, 7 = Always) | `reliance` |
| 3 | `reliance_trust` | I trusted the assistant's suggestions in this negotiation. *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `reliance` |
| 4 | `reliance_credit` | Who deserves the credit for the result of this negotiation? *(only with an Assistant)* | Mostly me · More me than the assistant · Equally · More the assistant than me · Mostly the assistant |  |

### Attention check {#attention-check}

Id `attention_check` · 1 question · for: `per_negotiation`, `post_session`

**Measures:** Whether the participant reads the questions (an instructed-response item).

**Validation:** Own item; there is no source instrument.

Scales: none (single items).

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `attention_check` | To show that you are reading the questions, please choose **Strongly disagree** here. | Strongly disagree · Disagree · Neutral · Agree · Strongly agree |  |

### Demographics {#demographics}

Id `demographics` · 4 questions · for: `pre_questionnaire`, `post_session`

**Measures:** Age range, gender, education and English level.

**Validation:** Common demographic items; there is no source instrument.

Scales: none (single items).

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `age_range` | What is your age? | 18–24 · 25–34 · 35–44 · 45–54 · 55–64 · 65 or older · Prefer not to say |  |
| 2 | `gender` | What is your gender? | Woman · Man · Non-binary · Prefer to self-describe · Prefer not to say |  |
| 3 | `education` | What is the highest level of education you have completed? | Secondary school · Vocational training · Bachelor's degree · Master's degree · Doctorate · Other · Prefer not to say |  |
| 4 | `english_level` | How would you rate your English? | Basic · Intermediate · Fluent · Native |  |

### Intention to use and felt heard {#intention-to-use}

Id `intention_to_use` · 3 questions · for: `per_negotiation`, `post_session`

**Measures:** Intention to use the Assistant again and feeling heard by it.

**Validation:** Own items; there is no source instrument.

Scales: `intention_to_use` (1 item), `felt_heard` (1 item) — each the mean of its items, reversed items scored backwards, as `scale_<name>` and `scale_<name>_norm`.

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `use_again` | I would use this assistant again. *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `intention_to_use` |
| 2 | `felt_heard` | I felt **heard** by the assistant (it took my wishes into account). *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `felt_heard` |
| 3 | `agent_insights` | What insights, if any, did the assistant give you? *(only with an Assistant)* | free text |  |

### Negotiation experience (participant type) {#negotiation-experience}

Id `negotiation_experience` · 2 questions · for: `pre_questionnaire`

**Measures:** How often the participant negotiates and whether they had training (the participant type).

**Validation:** Own items; there is no source instrument.

Scales: none (single items).

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `expertise` | How often do you negotiate (prices, contracts, salaries, …)? | Never · A few times · Regularly · It is part of my job |  |
| 2 | `negotiation_training` | Have you ever had training in negotiation? | yes / no |  |

### Opponent perception and relationship {#opponent-perception}

Id `opponent_perception` · 6 questions · for: `per_negotiation`

**Measures:** How kind, intelligent and human-like the opponent seemed, and the relationship with it.

**Validation:** Own items (the relationship items are inspired by the Subjective Value Inventory); there is no source instrument.

Scales: `opponent_kindness` (1 item), `opponent_intelligence` (1 item), `opponent_humanlike` (1 item), `relationship` (3 items) — each the mean of its items, reversed items scored backwards, as `scale_<name>` and `scale_<name>_norm`.

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `opponent_kind` | How **kind** was your opponent? | 1–7 (1 = Not at all, 7 = Very) | `opponent_kindness` |
| 2 | `opponent_intelligent` | How **intelligent** was your opponent? | 1–7 (1 = Not at all, 7 = Very) | `opponent_intelligence` |
| 3 | `opponent_human` | Do you think your opponent was a human or an AI? | 1–7 (1 = Surely an AI, 7 = Surely a human) | `opponent_humanlike` |
| 4 | `negotiate_again` | I would like to negotiate with this opponent again. | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `relationship` |
| 5 | `opponent_connected` | I felt a human connection with my opponent. | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `relationship` |
| 6 | `opponent_keep_deal` | I expect both sides would live up to the deal we reached. | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `relationship` |

### Outcome satisfaction and enjoyment {#outcome-appreciation}

Id `outcome_appreciation` · 2 questions · for: `per_negotiation`

**Measures:** Satisfaction with the outcome and enjoyment of the negotiation.

**Validation:** Own items; there is no source instrument.

Scales: `satisfaction` (1 item), `appreciation` (1 item) — each the mean of its items, reversed items scored backwards, as `scale_<name>` and `scale_<name>_norm`.

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `satisfaction_outcome` | How satisfied are you with the **outcome** of this negotiation? | 1–7 (1 = Not at all, 7 = Extremely) | `satisfaction` |
| 2 | `fun` | How much did you **enjoy** this negotiation? | 1–7 (1 = Not at all, 7 = Very much) | `appreciation` |

### Session feedback {#session-feedback}

Id `session_feedback` · 5 questions · for: `post_session`

**Measures:** The whole session: how the Assistants differed and helped, the interface, technical problems, comments.

**Validation:** Own items; there is no source instrument.

Scales: none (single items).

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `assistants_differed` | Did the assistants feel different from one negotiation to the next? *(only with an Assistant)* | 1–7 (1 = All the same, 7 = Very different) |  |
| 2 | `assistants_overall` | Overall, how helpful were the assistants in this session? *(only with an Assistant)* | 1–7 (1 = Not at all, 7 = Extremely) |  |
| 3 | `interface_clear` | The negotiation interface was easy to understand. | 1–7 (1 = Strongly disagree, 7 = Strongly agree) |  |
| 4 | `technical_problems` | Did you have any technical problems? | yes / no |  |
| 5 | `comments` | Anything else you want to tell us? (optional) | free text |  |

## Bundled forms

Complete forms that a study can name instead of writing its own (`HANI2_PER_NEG_YAML=evaluation`, or `"pre_questionnaire": "expertise"` in `env.json`; see [Study forms](study-forms.md)).

### After this negotiation (`evaluation`) {#evaluation}

Id `evaluation` · 21 questions · 

**Measures:** The evaluation questionnaire after each negotiation: satisfaction, enjoyment, UEQ items, TAM usefulness, intention to use, feeling heard, and the view of the opponent.

**Validation:** A combination of own items and the ueq_eval and tam_usefulness_short selections (see those).

!!! warning "Items not checked against the source"
    Its `tam_usefulness` scale uses TAM items. The TAM items have not been checked against the published instrument (Davis, 1989): no readable copy of the item sheet was found. The scoring of the scale is validated; the wording of its items is not, so results may not be comparable with published TAM scores.

Scales: `satisfaction` (1 item), `appreciation` (1 item), `ueq_pragmatic` (6 items), `ueq_hedonic` (2 items), `tam_usefulness` (2 items), `intention_to_use` (1 item), `felt_heard` (1 item), `opponent_kindness` (1 item), `opponent_intelligence` (1 item), `opponent_humanlike` (1 item), `relationship` (2 items) — each the mean of its items, reversed items scored backwards, as `scale_<name>` and `scale_<name>_norm`.

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `satisfaction_outcome` | How satisfied are you with the **outcome** of this negotiation? | 1–7 (1 = Not at all, 7 = Extremely) | `satisfaction` |
| 2 | `fun` | How much did you **enjoy** this negotiation? | 1–7 (1 = Not at all, 7 = Very much) | `appreciation` |
| 3 | `ueq_understandable` | The assistant was …  (1 = not understandable, 7 = understandable) *(only with an Assistant)* | 1–7 (1 = not understandable, 7 = understandable) | `ueq_pragmatic` |
| 4 | `ueq_valuable` | The assistant was …  (1 = valuable, 7 = inferior) *(only with an Assistant)* | 1–7 (1 = valuable, 7 = inferior) | `ueq_hedonic` (reversed) |
| 5 | `ueq_supportive` | The assistant was …  (1 = obstructive, 7 = supportive) *(only with an Assistant)* | 1–7 (1 = obstructive, 7 = supportive) | `ueq_pragmatic` |
| 6 | `ueq_good` | The assistant was …  (1 = good, 7 = bad) *(only with an Assistant)* | 1–7 (1 = good, 7 = bad) | `ueq_hedonic` (reversed) |
| 7 | `ueq_easy` | The assistant was …  (1 = complicated, 7 = easy) *(only with an Assistant)* | 1–7 (1 = complicated, 7 = easy) | `ueq_pragmatic` |
| 8 | `ueq_efficient` | The assistant was …  (1 = inefficient, 7 = efficient) *(only with an Assistant)* | 1–7 (1 = inefficient, 7 = efficient) | `ueq_pragmatic` |
| 9 | `ueq_clear` | The assistant was …  (1 = clear, 7 = confusing) *(only with an Assistant)* | 1–7 (1 = clear, 7 = confusing) | `ueq_pragmatic` (reversed) |
| 10 | `ueq_practical` | The assistant was …  (1 = impractical, 7 = practical) *(only with an Assistant)* | 1–7 (1 = impractical, 7 = practical) | `ueq_pragmatic` |
| 11 | `tam_effectiveness` | Using this assistant would enhance my effectiveness in negotiation. *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `tam_usefulness` |
| 12 | `tam_useful` | I would find this assistant useful in negotiations. *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `tam_usefulness` |
| 13 | `use_again` | I would use this assistant again. *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `intention_to_use` |
| 14 | `felt_heard` | I felt **heard** by the assistant (it took my wishes into account). *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `felt_heard` |
| 15 | `agent_insights` | What insights, if any, did the assistant give you? *(only with an Assistant)* | free text |  |
| 16 | `opponent_kind` | How **kind** was your opponent? | 1–7 (1 = Not at all, 7 = Very) | `opponent_kindness` |
| 17 | `opponent_intelligent` | How **intelligent** was your opponent? | 1–7 (1 = Not at all, 7 = Very) | `opponent_intelligence` |
| 18 | `opponent_human` | Do you think your opponent was a human or an AI? | 1–7 (1 = Surely an AI, 7 = Surely a human) | `opponent_humanlike` |
| 19 | `negotiate_again` | I would like to negotiate with this opponent again. | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `relationship` |
| 20 | `connected` | I felt humanly connected to the other party. | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `relationship` |
| 21 | `comments` | Anything else you want to tell us? (optional) | free text |  |

### Before you start (`expertise`) {#expertise}

Id `expertise` · 2 questions · 

**Measures:** Negotiation experience before the first negotiation (the participant type).

**Validation:** Own items; there is no source instrument.

Scales: none (single items).

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `expertise` | How often do you negotiate (prices, contracts, salaries, …)? | Never · A few times · Regularly · It is part of my job |  |
| 2 | `negotiation_training` | Have you ever had training in negotiation? | yes / no |  |

### After this negotiation (`per_negotiation`) {#per-negotiation}

Id `per_negotiation` · 3 questions · 

**Measures:** A minimal example form: satisfaction with the outcome and the opponent's cooperativeness.

**Validation:** Own items; there is no source instrument.

Scales: none (single items).

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `satisfaction_with_outcome` | How satisfied are you with the **outcome** of this negotiation? | 1–5 (1 = Not at all, 5 = Extremely) |  |
| 2 | `partner_cooperativeness` | How cooperative did your opponent feel? | Very competitive · Somewhat competitive · Neutral · Somewhat cooperative · Very cooperative |  |
| 3 | `comments` | Anything else you want to tell us? (optional) | free text |  |
