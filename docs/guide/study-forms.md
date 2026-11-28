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

The question types are `likert5`, `likert7`, `yes_no`, `select` (with `options`) and `text`. Every text may use the `{{variables}}` of [Study management](study-management.md#texts-with-variables). `scale` and `reverse` feed the [subjective metrics](evaluation.md#subjective-metrics). `direction: lower` says that a lower answer is better (workload, for example); a scale whose items all say so is lower-is-better too, so a score or a leaderboard ranks it the right way round. A question with `requires: support_agent` is asked only when an Assistant took part in the negotiation (for the post-session questionnaire: in the last negotiation). The pre-questionnaire may also have a `participant_type` block (see [Pre-questionnaire and participant types](study-management.md#pre-questionnaire-and-participant-types)).

The admin console checks a file before saving it: valid YAML, an `id` and a `text` for every question, unique ids, known types, and `options` for every `select`. `hani2 questionnaire check <files>` does the same on the command line.

### Editing the items of a form

On the Study forms page, each layer's form can be edited as **Items** (the default) or as **YAML**. Both edit the same file, and the checks, the preview and **Save** are the same.

- **Title** and **Intro** of the form.
- **Reorder** an item with its up and down arrows. **Remove** it with the bin.
- Click an item to **edit** its id, text, type, required flag, the labels of the two ends of a 1–5 or 1–7 scale, and the options of a choice question. *Stop scoring it* removes its `scale` and `reverse`.
- **New item** adds a blank 1–7 question. **Add an item from a set** adds one question of any predefined set; **Add predefined questionnaires** adds whole sets.

The items of a form are yours, whatever set they came from, including published instruments. If you edit or remove a scored item of a published instrument, or keep only some of its scored items, a notice says that its scale score may no longer match the published instrument. The notice does not block saving.

Editing items rewrites the file in a standard layout (one line per question) and drops YAML comments. Switch to **YAML** to keep them. A file that does not parse can only be edited as YAML.

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

HANI2 comes with complete question sets for questionnaires commonly used in human-agent negotiation studies. On the Study forms page, **Add predefined questionnaires** lists the sets meant for the form you are editing (tick *Show sets meant for other forms* for all of them); tick one or more and **Add** them. Their questions are copied into the form, where you can change, reorder or delete any of them (see [Editing the items of a form](#editing-the-items-of-a-form)); questions whose `id` is already in the form are skipped. The sets that score a construct carry `scale` and `reverse`, so the [subjective metrics](evaluation.md#subjective-metrics) score them. [Questionnaires](questionnaires.md) lists every question of every set with its source, and marks with ✓ the sets validated against their source instrument (the same mark is shown on the Study forms page).

!!! warning "TAM items not checked against the source"
    The three TAM sets (`tam_usefulness`, `tam_usefulness_short`, `tam_ease`) have not been checked against the published item sheet (Davis, 1989). The Study forms page shows this warning on each of them in the picker, above the preview of a form that uses their questions, and under *In effect here* when the form in effect uses them. It comes from the same registry as the warnings in [Questionnaires](questionnaires.md) and the [metric catalogue](metric-catalog.md). It is for admins only: participants never see it, neither in the form they fill in nor anywhere else in the session.

| Set | Questions | Meant for | About | What it measures |
|-----|-----------|-----------|-------|------------------|
| `ueq_eval` | 8 | after each negotiation, post-session | both | UEQ items 2, 5, 11, 12, 13, 20, 21, 22 about the party the study evaluates (7-point differentials; Laugwitz, Held & Schrepp, 2008) |
| `ueq_s` | 8 | after each negotiation, post-session | both | UEQ-S, the short UEQ: 4 pragmatic and 4 hedonic items (Schrepp, Hinderks & Thomaschewski, 2017) |
| `tam_usefulness_short` | 2 | after each negotiation, post-session | Assistant | TAM perceived usefulness, the two items "would enhance my effectiveness" and "would find it useful" (Davis, 1989) |
| `tam_usefulness` | 6 | after each negotiation, post-session | Assistant | TAM perceived usefulness, all six items |
| `tam_ease` | 6 | after each negotiation, post-session | Assistant | TAM perceived ease of use, six items |
| `intention_to_use` | 3 | after each negotiation, post-session | Assistant | Would use the Assistant again, felt heard, insights it gave |
| `assistant_reliance` | 4 | after each negotiation | Assistant | How much the participant used, followed and trusted the Assistant, and who deserves the credit |
| `trust_in_automation` | 12 | after each negotiation, post-session | both | Trust between people and automation (Jian, Bisantz & Drury, 2000) |
| `subjective_value` | 16 | after each negotiation, post-session | opponent | Subjective Value Inventory: instrumental outcome, self, process, relationship (Curhan, Elfenbein & Xu, 2006) |
| `opponent_perception` | 6 | after each negotiation | opponent | Kindness, intelligence, human-likeness of the opponent; would negotiate again, felt connected, deal would be kept |
| `outcome_appreciation` | 2 | after each negotiation | — | Satisfaction with the outcome, enjoyment |
| `nasa_tlx` | 6 | after each negotiation, post-session | — | Workload, raw NASA-TLX on 7-point items (Hart & Staveland, 1988) |
| `sus` | 10 | post-session | — | System Usability Scale of the interface (Brooke, 1996) |
| `session_feedback` | 5 | post-session | Assistant | The Assistants over the session, the interface, technical problems, comments |
| `negotiation_experience` | 2 | pre-questionnaire | — | How often the participant negotiates, negotiation training |
| `ai_experience` | 4 | pre-questionnaire | Assistant | Use of and experience with AI assistants, expected reliance, general trust in AI |
| `demographics` | 4 | pre-questionnaire, post-session | — | Age range, gender, education, English level |
| `attention_check` | 1 | after each negotiation, post-session | — | One instructed-response item |
| `HAN2026-PreSession` | 4 | pre-questionnaire | opponent | HAN 2026, as asked: negotiation experience, familiarity with AI, own skill, expected skill of the opponents |
| `HAN2026-PostNegotiation` | 10 | after each negotiation | opponent | HAN 2026, as asked: the opponent's strategy, intelligence and skill, would employ it, engagement, its messages, time limit, its offers, satisfaction, comment |
| `HAN2026-PostSession` | 8 | post-session | — | HAN 2026, as asked: ease of use, engagement, usefulness of each interface tool, comments |
| `HAN2025-PreStudy` | 19 | pre-questionnaire | opponent | HAN 2025, as asked once before any negotiation: background, expertise, expectations about the system and AI negotiators |
| `HAN2025-PostSession` | 13 | post-session | opponent | HAN 2025, as asked after a negotiation session: enjoyment, ease, the opponent, support, expectations |
| `HAN2025-PostStudy` | 17 | post-session | opponent | HAN 2025, as asked after the whole competition: the post-session questions, understanding of the scenario, comments, strategy |
| `ANAC-HAL2018-PostNegotiation` | 3 | after each negotiation | opponent | ANAC 2018 Human-Agent League, as reported: likeability of the agent (7-point) |
| `ANAC-HAL2017-PostNegotiation` | 3 | after each negotiation | opponent | ANAC 2017 Human-Agent League, as reported: likeability of the agent (7-point) |

The `HAN…` and `ANAC-HAL…` sets repeat the questionnaires of human-agent negotiation competitions exactly as asked (the ANAC Human-Agent League ones as its results papers report them; the papers give no anchor labels) (their typos included), so a study can compare its answers with the competition's; their question ids are kept, so `HAN2026-PostSession`'s `comments` is skipped in a form that already has `session_feedback`. The HAN 2025 forms were Google Forms: the sets leave out their identification items (user name, session, date, number of negotiations), keep a question asked twice once, and turn the expertise grid into one question per field.

Check the wording of a published instrument against its source before a study, and cite the source in your paper. Prolific already records most demographics and has its own rules for attention checks; ask only what you need.

### Questionnaires about the Assistant or the opponent

Each set is tagged (`tags`) with the party its questions are about. The *About* column above shows it:

- **Assistant**: only makes sense when the participant has an Assistant (TAM, reliance, intention to use, session feedback). Their questions have `requires: support_agent`.
- **opponent**: about the other side (SVI, opponent perception, the HAN and ANAC-HAL sets).
- **both**: the instrument fits either party (UEQ, UEQ-S, trust in automation). Its texts say `{{agent}}` (`{{Agent}}` at the start of a sentence) where the party goes, and its questions have `requires: agent`.
- **—** (no tag): about the participant, the task or the system (demographics, NASA-TLX, SUS, outcome, attention check).

When a participant sees a form, `{{agent}}` becomes the party the study evaluates: `opponent` in a HAN project (`kind: opponent`), `assistant` in any other, or what the **Questionnaires ask about** setting of the study or its project says (`questionnaire_agent: assistant` or `opponent`). With `assistant`, a `requires: agent` question is skipped when no Assistant took part; with `opponent`, it is always asked. So "The {{agent}} is reliable." reads "The assistant is reliable." in an HI study and "The opponent is reliable." in a HAN study, and one form file serves both:

```yaml title="projects/HAN2027/project.yaml"
kind: opponent                    # {{agent}} is "opponent" in every study of this project
defaults:
  questionnaire_agent: opponent   # or set it per study; empty follows the kind
```

The question ids stay the same whichever party a study asks about, so the scales and metric columns do not change; tell the answers apart by project or study. A study asks about one party: to ask a both-party set about the Assistant *and* the opponent in one form, copy the set and give the copy other question ids. The preview on the Study forms page fills in the party of the layer being edited. The Questionnaires page shows each set's party and can show only the sets about one party. The Study forms picker shows it too, and in a HAN project (`kind: opponent`, no Assistant) it hides the sets only about the Assistant until you tick *Show sets about the Assistant*.

### Your own sets

The admin console's **Questionnaires** page is the explorer of every set. Search titles, ids, questions and scales, or show only the sets meant for one form. The sets come in three groups:

- **Published instruments**: sets that reproduce a published questionnaire (UEQ, UEQ-S, the three TAM sets, trust in automation, the Subjective Value Inventory, NASA-TLX, SUS). They are **read-only in the app**: **Copy as new** is their only action.
- **Your own sets**: the files in `questionnaire_library/` in the settings folder, including overrides of bundled sets.
- **Built-in sets**: HANI2's own bundled sets that cite no published instrument (demographics, attention check, opponent perception, ...).

Open a set to see its questions, its scales, the ✓ of a validated set, its source and source link, and the file that defines it, with a copy button. A set whose items have not been checked against their source (the TAM sets) also shows its warning. Only administrators see these warnings; participants never do.

**What counts as published.** A set is read-only in the app when the [metric catalogue](questionnaires.md) cites a published instrument for its id, or when its file has a `url` that links to one. `reference` alone does not count, because HANI2's own sets name themselves there too ("HANI2 items."). An own file that overrides a published set by id stays read-only as well. To change a published set anyway, edit its file by hand. The API refuses edits to these sets, not only the page.

**Edit.** **Edit** opens the set's YAML in an editor that checks it as you type. **Save set** is refused while there are problems. The checks are the form checks (valid YAML, an `id` and a `text` for every question, unique ids, known types, `options` for every `select`) plus the set checks: an id made of letters, digits, `_` and `-`, a title, `forms` from `pre_questionnaire`, `per_negotiation` and `post_session`, `tags` from `assistant` and `opponent` (a set tagged with both must say `{{agent}}`, not "assistant" or "opponent", and use `requires: agent`), at least one question, and no `url` (that would make the set read-only). The id of an existing set cannot change; use **Copy as new** for another id.

- Saving a **bundled** set writes an override, `<settings>/questionnaire_library/<id>.yaml`. The bundled file inside the HANI2 package is never changed, and deleting the override brings the bundled version back.
- Saving **your own** set rewrites the file that defines it, whatever that file is called.

**Add.** **New set** starts from a small blank set. **Copy as new** starts from any set, published ones included. The copy gets a new id (`<id>_copy`, which you can change), drops `reference` and `url`, and records its origin in `based_on` (the source it is based on) and `copied_from` (the id of the first set it was copied from, so a copy of a TAM set keeps the TAM warning). A new set is saved as `<settings>/questionnaire_library/<id>.yaml`. Its id must be new, so adding a set never overrides another one. The new set is listed under **Add predefined questionnaires** on the Study forms page at once.

**Delete.** The app has no delete button. Open the set to find the file that defines it and the exact command, e.g. `rm ~/negmas/hani2/settings/questionnaire_library/team_trust.yaml`, with a copy button. After you remove the file and reload the page, your own set is gone and an override falls back to the bundled set. Bundled sets cannot be deleted. Files in the folder that are not sets (bad YAML, no questions) are listed at the top of the page with their delete command.

You can also write the files yourself, one YAML file per set; a set with the id of a bundled set replaces it:

```yaml title="~/negmas/hani2/settings/questionnaire_library/team_trust.yaml"
id: team_trust
title: "Trust in my teammate"
description: "Three items about the human-Assistant team."
reference: "Our lab's items."
forms: [per_negotiation, post_session]
tags: [assistant]              # the party the questions are about: [assistant], [opponent], both, or [] for neither
questions:
  - {id: team_trust_1, text: "My teammate and I worked well together.", type: likert7, required: true, scale: team_trust, labels: {1: "Strongly disagree", 7: "Strongly agree"}}
```

`hani2 questionnaire check --set <files>` checks set files with the same rules (files inside a `questionnaire_library/` folder are always checked as sets; a hand-written file may have a `url`).

### On the command line

```bash
hani2 questionnaire list --form post_session          # the sets for one form (--details: every question)
hani2 questionnaire list --about opponent             # the sets tagged opponent (both-party sets too)
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
