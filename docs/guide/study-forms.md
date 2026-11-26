# Study forms

A study can ask its participants for consent and three kinds of questionnaires. Each project and each study decides which of them it uses: none, some or all.

| Form | When | File | Answers go to |
|------|------|------|---------------|
| **Consent** | Before the first negotiation (Prolific and online / lab participants) | `consent.md` | `consent.json` |
| **Pre-questionnaire** | Once, after the first scenario loads and before the negotiation starts | `questionnaires/pre_questionnaire.yaml` | `pre_questionnaire.json` |
| **After each negotiation** | After every negotiation, the practice round included | `questionnaires/per_negotiation.yaml` | `negotiation_questionnaires.csv` |
| **Post-session** | Once, after the last counted negotiation, before the completion link | `questionnaires/post_session.yaml` | `post_session.json` |

The answer files are in the participant's results folder (see [Study management](study-management.md#results)). For a Prolific participant the order is: consent, pre-questionnaire, the practice round and its questionnaire, the counted negotiations each with its questionnaire, the post-session questionnaire, then *Finish and submit*.

Every form is off until you set it up. Edit them in the admin console on the **Study forms** page, or write the files yourself.

## One file per layer

The questionnaire files live in the same layers as every other settings file (see [Study management](study-management.md#settings-files-per-study)): the study folder, then its project folder, then the settings folder. The first file found wins, so a project defines the forms its studies share and a study overrides only what it changes:

```text
projects/HI2027/
├── consent.md                               consent text of every study of the project
├── questionnaires/
│   ├── pre_questionnaire.yaml               shared by every study of the project
│   ├── per_negotiation.yaml
│   └── post_session.yaml
└── studies/
    ├── pilot/questionnaires/
    │   └── post_session.yaml                enabled: false   (no post-session form in the pilot)
    └── final/questionnaires/
        └── per_negotiation.yaml             the final's own form after each negotiation
```

A study replaces a form as a whole; it does not add questions to its project's form. To start from the project's form, use **Copy the inherited form** on the Study forms page (or copy the file) and edit the copy.

### Switching a form off

A file with `enabled: false` switches the form off for its layer and everything below it, even when a higher layer defines one:

```yaml title="projects/HI2027/studies/pilot/questionnaires/post_session.yaml"
enabled: false
```

**Switch off here** on the Study forms page writes exactly this file. Removing the file (**Remove this layer's file**) brings back the inherited form. A file without questions and without `enabled: false` is ignored, as if it were not there.

### What wins over the files

For each form, an environment variable or a name in `env.json` wins over every layer's file:

| Form | Environment variables | `env.json` key |
|------|----------------------|----------------|
| Pre-questionnaire | `HANI2_PRE_YAML` | `pre_questionnaire` |
| After each negotiation | `HANI2_PER_NEG_YAML`, then `PROLIFIC_PER_NEG_YAML` | `questionnaire` |
| Post-session | `HANI2_POST_YAML` | `post_questionnaire` |

The value is a path, or a bare name such as `evaluation`: a file `questionnaires/<name>.yaml` in the study, the project, the settings folder or the questionnaires bundled with HANI2 (`evaluation`, `expertise`). When one of them is set, the Study forms page says so: edits to the files have no effect until it is unset.

## The form file

All three questionnaires share one format (see [Per-negotiation questionnaires](study-management.md#per-negotiation-questionnaires) for every field):

```yaml
version: "1"
title: "Before you finish"
intro: "A few last questions about the whole session."
questions:
  - id: overall
    text: "Overall, how helpful were the assistants?"
    type: likert7
    required: true
    labels: {1: "Not at all", 7: "Extremely"}
  - id: comments
    text: "Anything else you want to tell us?"
    type: text
```

The question types are `likert5`, `likert7`, `yes_no`, `select` (with `options`) and `text`. Every text may use the `{{variables}}` of [Study management](study-management.md#texts-with-variables). `scale` and `reverse` feed the [subjective metrics](evaluation.md#subjective-metrics). A question with `requires: support_agent` is asked only when an Assistant took part in the negotiation (for the post-session questionnaire: in the last negotiation). The pre-questionnaire may also have a `participant_type` block (see [Pre-questionnaire and participant types](study-management.md#pre-questionnaire-and-participant-types)).

The admin console checks a file before saving it: valid YAML, an `id` and a `text` for every question, unique ids, known types, and `options` for every `select`. `hani2 questionnaire check <files>` does the same on the command line.

## Consent for study participants

Logged-in participants consent on the consent page (`auth.enforce_consent`, see [Consent per study](study-management.md#consent-per-study)). Prolific and online / lab participants do not log in; to ask them in the session itself, switch on **Ask study participants for consent** on the Study forms page, or set it in the `env.json` of the layer:

```json title="projects/HI2027/env.json"
{"auth": {"participant_consent": true}}
```

The participant then sees the study's consent text (`consent.md` of the study, its project or the settings folder, edited on the [Texts](admin.md#texts) page, with `{{variables}}` filled in) before their first negotiation, with *I agree to take part* and *I do not agree*. Nothing starts until they answer.

- **Agree.** HANI2 writes `consent.json` (`agreed`, the hash of the text they read, timestamps, project and study) and goes on with the pre-questionnaire or the negotiation. They are not asked again, unless the consent text changes.
- **Do not agree.** The session ends with a short text asking a Prolific participant to return the study, and no completion link. `consent.json` records `"agreed": false`; opening the link again shows the consent form again.

It is off by default. Turn it off when another system already shows the consent form before sending participants to HANI2.

## The post-session questionnaire

When the last counted negotiation (and its questionnaire) is done, a participant of a Prolific or online / lab study gets the post-session questionnaire, if one is set up, and only then the end page with *Finish and submit*. It is asked once: the answers go to `post_session.json` (`answers`, timestamps, `version`, project and study) and, when the form follows the last negotiation directly, to that negotiation's recording (a `post_session` record). A participant who closes the page before answering gets it again when they open their link; then `post_session.json` is the only record. Consent is recorded the same way (a `consent` record in the first negotiation's recording). Use it for questions about the whole session: usability of the interface, comparisons between negotiations, demographics, free comments.

## Predefined questionnaires

HANI2 comes with complete question sets for questionnaires commonly used in human-agent negotiation studies. On the Study forms page, **Add predefined questionnaires** lists the sets meant for the form you are editing (tick *Show sets meant for other forms* for all of them); tick one or more and **Add** them. Their questions are copied into the form, where you can change, reorder or delete any of them; questions whose `id` is already in the form are skipped. The sets that score a construct carry `scale` and `reverse`, so the [subjective metrics](evaluation.md#subjective-metrics) score them.

| Set | Questions | Meant for | What it measures |
|-----|-----------|-----------|------------------|
| `ueq_eval` | 8 | after each negotiation, post-session | UEQ items 2, 5, 11, 12, 13, 20, 21, 22 about the Assistant (7-point differentials; Laugwitz, Held & Schrepp, 2008) |
| `ueq_s` | 8 | after each negotiation, post-session | UEQ-S, the short UEQ: 4 pragmatic and 4 hedonic items (Schrepp, Hinderks & Thomaschewski, 2017) |
| `tam_usefulness_short` | 2 | after each negotiation, post-session | TAM perceived usefulness, the two items "would enhance my effectiveness" and "would find it useful" (Davis, 1989) |
| `tam_usefulness` | 6 | after each negotiation, post-session | TAM perceived usefulness, all six items |
| `tam_ease` | 6 | after each negotiation, post-session | TAM perceived ease of use, six items |
| `intention_to_use` | 3 | after each negotiation, post-session | Would use the Assistant again, felt heard, insights it gave |
| `assistant_reliance` | 4 | after each negotiation | How much the participant used, followed and trusted the Assistant, and who deserves the credit |
| `trust_in_automation` | 12 | after each negotiation, post-session | Trust between people and automation (Jian, Bisantz & Drury, 2000) |
| `subjective_value` | 16 | after each negotiation, post-session | Subjective Value Inventory: instrumental outcome, self, process, relationship (Curhan, Elfenbein & Xu, 2006) |
| `opponent_perception` | 6 | after each negotiation | Kindness, intelligence, human-likeness of the opponent; would negotiate again, felt connected, deal would be kept |
| `outcome_appreciation` | 2 | after each negotiation | Satisfaction with the outcome, enjoyment |
| `nasa_tlx` | 6 | after each negotiation, post-session | Workload, raw NASA-TLX on 7-point items (Hart & Staveland, 1988) |
| `sus` | 10 | post-session | System Usability Scale of the interface (Brooke, 1996) |
| `session_feedback` | 5 | post-session | The Assistants over the session, the interface, technical problems, comments |
| `negotiation_experience` | 2 | pre-questionnaire | How often the participant negotiates, negotiation training |
| `ai_experience` | 4 | pre-questionnaire | Use of and experience with AI assistants, expected reliance, general trust in AI |
| `demographics` | 4 | pre-questionnaire, post-session | Age range, gender, education, English level |
| `attention_check` | 1 | after each negotiation, post-session | One instructed-response item |

Check the wording of a published instrument against its source before a study, and cite the source in your paper. Prolific already records most demographics and has its own rules for attention checks; ask only what you need.

### Your own sets

Put your own sets in `questionnaire_library/` in the settings folder, one YAML file per set. A set with the id of a bundled set replaces it:

```yaml title="~/negmas/hani2/settings/questionnaire_library/team_trust.yaml"
id: team_trust
title: "Trust in my teammate"
description: "Three items about the human-Assistant team."
reference: "Our lab's items."
forms: [per_negotiation, post_session]
questions:
  - {id: team_trust_1, text: "My teammate and I worked well together.", type: likert7, required: true, scale: team_trust, labels: {1: "Strongly disagree", 7: "Strongly agree"}}
```

### On the command line

```bash
hani2 questionnaire list --form post_session          # the sets for one form (--details: every question)
hani2 questionnaire compose ueq_eval tam_usefulness_short opponent_perception \
    -o projects/HI2027/questionnaires/per_negotiation.yaml
hani2 questionnaire check projects/HI2027/questionnaires/*.yaml
```

`compose` appends to an existing file (keeping its comments when `questions:` is its last key) or starts a new one; `--form` picks the title and intro of a new file. Without `-o` it prints the result, so the files of another system can be built the same way.

## Who gets the forms

- Consent and the post-session questionnaire: Prolific and online / lab participants only (logged-in users have the consent page and no end of session).
- The pre-questionnaire and the questionnaire after each negotiation: every participant, logged in or not.
- Never: administrators, playground guests and [simulated participants](simulation.md).

A participant who declines consent, or drops out, keeps their participant index, so their row of a [counterbalanced order](scheduling.md#assistants) stays unfilled; recruit until every row has completed participants.

While a form is open the participant cannot start or load a negotiation, and the automatic start and load timers of [Prolific](prolific.md#automatic-timers) wait for it.
