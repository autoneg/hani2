HANI2 0.2.0: one server for many projects and studies, with shared libraries, a new admin console,
and recording, replay and evaluation for the ANAC Human-Agent Negotiation (HAN) and Hybrid
Intelligence (HI) competitions.

```bash
pip install -U hani2
hani2
```

Highlights:

- **Projects and studies.** One server serves many studies, each with its own settings, schedule,
  opponent and Assistant groups, and results. A new admin console, laid out like system
  settings, has explorers for scenarios, opponents, Assistants and tools.
- **Library and groups.** You can upload and link scenarios, opponents, Assistants and tools, and
  combine them into groups and groups of groups. The optional `han` extra adds the HAN league
  opponents (`:han2026-finalists` and others).
- **Scenarios.** This release adds scenario sets (HAN2027, HI2027, ANAC2027), 16 new scenario
  types with YAML templates, compositional scenarios (`hani2 compose`), role-assignment rules,
  scenario pictures, and scenarios that shape how offers are shown. With *who knows what*, the
  participant and the Assistant can hold different information.
- **Evaluation.** Negotiations are recorded and can be replayed. There are hard, subjective and
  language-model judged metrics, combined scores, judge reliability, and HAN / HI leaderboards.
  Simulated participants come from `hani2 simulate`, and ablations work as diagnostics.
- **Assistant and models.** Model chains with fallback, harness connections (Claude Code, Codex,
  pi), pinned messages, a notification list, and an Assistant persona.
- **Access.** Sign-in from a trusted website (for example ANAC accounts), `--root-path` for
  reverse proxies, and admins negotiating as participants.
- **Security and reliability fixes.** This release closes the default-password and
  self-registration admin holes, sanitises HTML with DOMPurify, and masks secrets in model errors.
  The web app also reconnects more reliably, and sessions no longer freeze while the Assistant
  sends.

Full changelog: https://autoneg.github.io/hani2/changelog/

Documentation: https://autoneg.github.io/hani2/
