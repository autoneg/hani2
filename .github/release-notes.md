HANI2 0.3.0: Solo and Paired studies, your own scores and leaderboards, self-hosted agents, a
questionnaire library and a simpler participant interface.

```bash
pip install -U hani2
hani2
```

Highlights:

- **Solo, Paired and Mixed studies.** `study_mode` declares who negotiates with whom. Paired
  studies match two people, each with their own Assistant, and each person plays each of
  their Assistants at most once. New ways to assign Assistants (K of N per person, crossing with opponents)
  come with `hani2 study balance` to check the result.
- **Scores and leaderboards.** You can define your own scores over any criterion (outcomes, judge
  ratings, questionnaire scales) and preview them live. Projects and studies get boards with
  strata, `pooled`, `latest` or `continuous` updates, pages of their own and an API for a
  competition website.
- **Self-hosted Assistants and opponents.** `hani2 host-assistant` and `hani2 host-opponent` let
  a team run its agent on its own machine. The current year's HAN agents come from the submitted
  zips.
- **Models.** `models.json` can define named model sequences that an Assistant may choose among.
  This choice is off by default.
- **Questionnaires.** A questionnaire library has an explorer and an item editor in the admin
  console. It includes the questionnaires of past negotiation competitions, and each one is
  tagged by the party it asks about.
- **Participant interface.** The simple view is now the default. The Preferences tool is more
  compact, and the release adds the Utility Bar, *Send offer* in the offer generators, an
  estimate of the opponent's preferences, any tool in a popup, and a different look for the
  Assistant and the opponent in each negotiation. A tool that fails stays in its own tab.
- **The Assistant answers the interface's AI features** (*Write message*, *Offer from message*)
  with its own model and context.
- **Admin console.** Every settings-file key can be set in the console, every setting has a
  **?** help text, and a scenario explorer has been added.

**Upgrading:** saved scenarios that are not normalized are now played normalized. Their utilities
are therefore not comparable with earlier results; set `assume_normalized` to keep the old scale.

Full changelog: https://autoneg.github.io/hani2/changelog/

Documentation: https://autoneg.github.io/hani2/
