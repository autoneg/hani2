<!-- Generated from src/hani2/evaluation/catalog.py by scripts/make_metric_catalog.py. Do not edit by hand. -->


# Questionnaires

Every predefined questionnaire a project or study can use: what it measures, its source, its scales and every question with its answer scale. A ✓ marks a questionnaire validated against its source instrument: items, anchors, reversed items and scale scoring (see [What “validated” means](metric-catalog.md#validated)).

Pick them on the admin console's **Study forms** page (**Add predefined questionnaires**), which shows the same marks, or with `hani2 questionnaire compose`; see [Study forms](study-forms.md#predefined-questionnaires). Their scales and items become measures of the [Questionnaires (subjective)](metric-catalog.md#group-subjective) group, usable in scores and on leaderboards.

| Questionnaire | Id | Questions | Validated | Source |
| --- | --- | --- | --- | --- |
| [NASA-TLX workload (raw, 7-point)](#nasa-tlx) | `nasa_tlx` | 6 |  | [link](https://doi.org/10.1016/S0166-4115(08)62386-9) |
| [Subjective Value Inventory (SVI), 16 items](#subjective-value) | `subjective_value` | 16 | <abbr title="validated against the source instrument: tests/validation/test_validate_questionnaires.py::test_svi_matches_source">✓</abbr> | [link](https://www.subjectivevalue.com/) |
| [System Usability Scale (SUS), 10 items](#sus) | `sus` | 10 | <abbr title="validated against the source instrument: tests/validation/test_validate_questionnaires.py::test_sus_matches_source">✓</abbr> | yes |
| [TAM perceived ease of use, 6 items](#tam-ease) | `tam_ease` | 6 |  | [link](https://doi.org/10.2307/249008) |
| [TAM perceived usefulness, 6 items](#tam-usefulness) | `tam_usefulness` | 6 |  | [link](https://doi.org/10.2307/249008) |
| [TAM perceived usefulness, 2 items](#tam-usefulness-short) | `tam_usefulness_short` | 2 |  | [link](https://doi.org/10.2307/249008) |
| [Trust in automation (Jian et al.), 12 items](#trust-in-automation) | `trust_in_automation` | 12 |  | [link](https://doi.org/10.1207/S15327566IJCE0401_04) |
| [UEQ, 8 items (the evaluation selection)](#ueq-eval) | `ueq_eval` | 8 |  | [link](https://www.ueq-online.org/) |
| [UEQ-S (short User Experience Questionnaire)](#ueq-s) | `ueq_s` | 8 | <abbr title="validated against the source instrument: tests/validation/test_validate_questionnaires.py::test_ueq_s_matches_source">✓</abbr> | [link](https://doi.org/10.9781/ijimai.2017.09.001) |
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

### NASA-TLX workload (raw, 7-point) {#nasa-tlx}

Id `nasa_tlx` · 6 questions · for: `per_negotiation`, `post_session`

**Measures:** Workload of the task: mental, physical and temporal demand, performance, effort and frustration (raw TLX; lower is better).

**Source:** [Hart & Staveland (1988). Development of NASA-TLX (Task Load Index): results of empirical and theoretical research. In Hancock & Meshkati (eds.), Human Mental Workload. Advances in Psychology 52, 139–183.](https://doi.org/10.1016/S0166-4115(08)62386-9)

**Validation:** Not validated: the official rating sheet could not be retrieved, and the items use 7 points instead of the original 21 gradations (0–100 in steps of 5). The raw TLX (the unweighted mean of the six) is the usual short form.

Scales: `workload` (6 items) — each the mean of its items, reversed items scored backwards, as `scale_<name>` and `scale_<name>_norm`.

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `tlx_mental` | **Mental demand**: how mentally demanding was the task? | 1–7 (1 = Very low, 7 = Very high) | `workload` (lower is better) |
| 2 | `tlx_physical` | **Physical demand**: how physically demanding was the task? | 1–7 (1 = Very low, 7 = Very high) | `workload` (lower is better) |
| 3 | `tlx_temporal` | **Temporal demand**: how hurried or rushed was the pace of the task? | 1–7 (1 = Very low, 7 = Very high) | `workload` (lower is better) |
| 4 | `tlx_performance` | **Performance**: how successful were you in accomplishing what you were asked to do? | 1–7 (1 = Perfect, 7 = Failure) | `workload` (lower is better) |
| 5 | `tlx_effort` | **Effort**: how hard did you have to work to accomplish your level of performance? | 1–7 (1 = Very low, 7 = Very high) | `workload` (lower is better) |
| 6 | `tlx_frustration` | **Frustration**: how insecure, discouraged, irritated, stressed or annoyed were you? | 1–7 (1 = Very low, 7 = Very high) | `workload` (lower is better) |

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

**Validation:** Not validated: no open copy of the item sheet could be checked. The six items follow Davis's ease-of-use items, reworded for a negotiation assistant, with agree–disagree anchors.

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

**Validation:** Not validated: no open copy of the item sheet could be checked. The six items follow Davis's usefulness items, reworded for a negotiation assistant, with agree–disagree anchors.

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

**Validation:** Not validated: a two-item selection of the usefulness items, reworded; no open copy of the item sheet could be checked.

Scales: `tam_usefulness` (2 items) — each the mean of its items, reversed items scored backwards, as `scale_<name>` and `scale_<name>_norm`.

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `tam_effectiveness` | Using this assistant would enhance my effectiveness in negotiation. *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `tam_usefulness` |
| 2 | `tam_useful` | I would find this assistant useful in negotiations. *(only with an Assistant)* | 1–7 (1 = Strongly disagree, 7 = Strongly agree) | `tam_usefulness` |

### Trust in automation (Jian et al.), 12 items {#trust-in-automation}

Id `trust_in_automation` · 12 questions · for: `per_negotiation`, `post_session`

**Measures:** Trust in the Assistant (Checklist for Trust between People and Automation).

**Source:** [Jian, Bisantz & Drury (2000). Foundations for an empirically determined scale of trust in automated systems. International Journal of Cognitive Ergonomics 4(1), 53–71.](https://doi.org/10.1207/S15327566IJCE0401_04)

**Validation:** Not validated: no open copy of the checklist could be checked. “The system” is worded as “the assistant”; the five distrust items are reversed.

Scales: `trust_automation` (12 items) — each the mean of its items, reversed items scored backwards, as `scale_<name>` and `scale_<name>_norm`.

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `tia_deceptive` | The assistant is deceptive. *(only with an Assistant)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` (reversed) |
| 2 | `tia_underhanded` | The assistant behaves in an underhanded manner. *(only with an Assistant)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` (reversed) |
| 3 | `tia_suspicious` | I am suspicious of the assistant's intent, actions or outputs. *(only with an Assistant)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` (reversed) |
| 4 | `tia_wary` | I am wary of the assistant. *(only with an Assistant)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` (reversed) |
| 5 | `tia_harmful` | The assistant's actions will have a harmful or injurious outcome. *(only with an Assistant)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` (reversed) |
| 6 | `tia_confident` | I am confident in the assistant. *(only with an Assistant)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` |
| 7 | `tia_security` | The assistant provides security. *(only with an Assistant)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` |
| 8 | `tia_integrity` | The assistant has integrity. *(only with an Assistant)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` |
| 9 | `tia_dependable` | The assistant is dependable. *(only with an Assistant)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` |
| 10 | `tia_reliable` | The assistant is reliable. *(only with an Assistant)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` |
| 11 | `tia_trust` | I can trust the assistant. *(only with an Assistant)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` |
| 12 | `tia_familiar` | I am familiar with the assistant. *(only with an Assistant)* | 1–7 (1 = Not at all, 7 = Extremely) | `trust_automation` |

### UEQ, 8 items (the evaluation selection) {#ueq-eval}

Id `ueq_eval` · 8 questions · for: `per_negotiation`, `post_session`

**Measures:** Usability of the Assistant with eight items of the full UEQ, as two scales (ueq_pragmatic, ueq_hedonic).

**Source:** [Laugwitz, Held & Schrepp (2008). Construction and evaluation of a user experience questionnaire. USAB 2008, LNCS 5298, 63–76.](https://www.ueq-online.org/)

**Validation:** Not validated as a UEQ scale: the items (UEQ items 2, 5, 11, 12, 13, 20, 21, 22) and their poles match the UEQ and the positive-left items are reversed (tested), but the UEQ has six scales, not these two: ueq_hedonic mixes a Stimulation item (valuable) with an Attractiveness item (good), and the UEQ handbook counts Attractiveness as neither pragmatic nor hedonic.

Scales: `ueq_pragmatic` (6 items), `ueq_hedonic` (2 items) — each the mean of its items, reversed items scored backwards, as `scale_<name>` and `scale_<name>_norm`.

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `ueq_understandable` | The assistant was …  (1 = not understandable, 7 = understandable) *(only with an Assistant)* | 1–7 (1 = not understandable, 7 = understandable) | `ueq_pragmatic` |
| 2 | `ueq_valuable` | The assistant was …  (1 = valuable, 7 = inferior) *(only with an Assistant)* | 1–7 (1 = valuable, 7 = inferior) | `ueq_hedonic` (reversed) |
| 3 | `ueq_supportive` | The assistant was …  (1 = obstructive, 7 = supportive) *(only with an Assistant)* | 1–7 (1 = obstructive, 7 = supportive) | `ueq_pragmatic` |
| 4 | `ueq_good` | The assistant was …  (1 = good, 7 = bad) *(only with an Assistant)* | 1–7 (1 = good, 7 = bad) | `ueq_hedonic` (reversed) |
| 5 | `ueq_easy` | The assistant was …  (1 = complicated, 7 = easy) *(only with an Assistant)* | 1–7 (1 = complicated, 7 = easy) | `ueq_pragmatic` |
| 6 | `ueq_efficient` | The assistant was …  (1 = inefficient, 7 = efficient) *(only with an Assistant)* | 1–7 (1 = inefficient, 7 = efficient) | `ueq_pragmatic` |
| 7 | `ueq_clear` | The assistant was …  (1 = clear, 7 = confusing) *(only with an Assistant)* | 1–7 (1 = clear, 7 = confusing) | `ueq_pragmatic` (reversed) |
| 8 | `ueq_practical` | The assistant was …  (1 = impractical, 7 = practical) *(only with an Assistant)* | 1–7 (1 = impractical, 7 = practical) | `ueq_pragmatic` |

### UEQ-S (short User Experience Questionnaire) <abbr title="validated against the source instrument: tests/validation/test_validate_questionnaires.py::test_ueq_s_matches_source">✓</abbr> {#ueq-s}

Id `ueq_s` · 8 questions · for: `per_negotiation`, `post_session`

**Measures:** User experience of the Assistant: pragmatic quality (supportive, easy, efficient, clear) and hedonic quality (exciting, interesting, inventive, leading edge).

**Source:** [Schrepp, Hinderks & Thomaschewski (2017). Design and evaluation of a short version of the User Experience Questionnaire (UEQ-S). IJIMAI 4(6), 103–108.](https://doi.org/10.9781/ijimai.2017.09.001)

**Validated:** Checked against the UEQ-S item sheet and the UEQ handbook: the 8 items in order, negative pole left, items 1–4 pragmatic and 5–8 hedonic, each scale the mean of its items. HANI2 scores 1–7; subtract 4 for the handbook's −3…+3.

Scales: `ueqs_pragmatic` (4 items), `ueqs_hedonic` (4 items) — each the mean of its items, reversed items scored backwards, as `scale_<name>` and `scale_<name>_norm`.

| # | Id | Question | Answer | Scale |
| --- | --- | --- | --- | --- |
| 1 | `ueqs_supportive` | The assistant was … *(only with an Assistant)* | 1–7 (1 = obstructive, 7 = supportive) | `ueqs_pragmatic` |
| 2 | `ueqs_easy` | The assistant was … *(only with an Assistant)* | 1–7 (1 = complicated, 7 = easy) | `ueqs_pragmatic` |
| 3 | `ueqs_efficient` | The assistant was … *(only with an Assistant)* | 1–7 (1 = inefficient, 7 = efficient) | `ueqs_pragmatic` |
| 4 | `ueqs_clear` | The assistant was … *(only with an Assistant)* | 1–7 (1 = confusing, 7 = clear) | `ueqs_pragmatic` |
| 5 | `ueqs_exciting` | The assistant was … *(only with an Assistant)* | 1–7 (1 = boring, 7 = exciting) | `ueqs_hedonic` |
| 6 | `ueqs_interesting` | The assistant was … *(only with an Assistant)* | 1–7 (1 = not interesting, 7 = interesting) | `ueqs_hedonic` |
| 7 | `ueqs_inventive` | The assistant was … *(only with an Assistant)* | 1–7 (1 = conventional, 7 = inventive) | `ueqs_hedonic` |
| 8 | `ueqs_leading_edge` | The assistant was … *(only with an Assistant)* | 1–7 (1 = usual, 7 = leading edge) | `ueqs_hedonic` |

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
