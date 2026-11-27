"""The generated docs pages of the catalogue: ``docs/guide/metric-catalog.md`` (every metric
column in its group, the user-defined scores, validation) and ``docs/guide/questionnaires.md``
(every predefined questionnaire with its items). Written by ``scripts/make_metric_catalog.py``;
``tests/test_metric_catalog.py`` fails when a page is out of date."""

from __future__ import annotations

from pathlib import Path

from hani2.evaluation import catalog as C

HEADER = ("<!-- Generated from src/hani2/evaluation/catalog.py by scripts/make_metric_catalog.py. "
          "Do not edit by hand. -->\n\n")
MARK = "✓"
#: the published pages (relative to the repository root)
PAGES = {"metric-catalog": "docs/guide/metric-catalog.md", "questionnaires": "docs/guide/questionnaires.md"}


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def _mark(test: str, tip: str = C.VALIDATED_TOOLTIP) -> str:
    return f'<abbr title="{tip}: {test}">{MARK}</abbr>' if test else ""


def _use(c) -> str:
    """Whether a score can use a criterion."""
    if c.direction == "none":
        return "with a direction"
    return "yes"


# --------------------------------------------------------------------------- #
# The metric catalogue                                                         #
# --------------------------------------------------------------------------- #
def _validation_section() -> str:
    return f"""## What “validated” means {{#validated}}

A {MARK} next to a measure means that its implementation is **validated**: a test computes it on a
small hand-worked negotiation (known offers, utilities, timings, messages or answers) and compares
it with a value derived by hand from the measure's definition, with the derivation written next to
the expected value. The mark's tooltip names the test (in `tests/validation/`). A test that only
checks that a value lies in its range does not count.

For a questionnaire, {MARK} means that its items were compared with the source instrument (wording,
number of items, anchors and direction), that its reversed items are reversed, and that its scales
are scored as the source says (see [Questionnaires](questionnaires.md)).

What is **not** validated is said so, with the reason. The ratings of the language-model judge (the
`ja_`, `jo_`, `jh_` columns, the assertion checks and the error review) are judgements that no
hand-computed example can check; only the parsing and aggregation of the judge's answers are
tested. A project's own scores are not marked: the rules that combine their parts are validated
(`{C.SCORE_RULES_VALIDATED_BY.split('::')[-1]}` and its neighbours), but their weights are the
project's choice.

The marks are kept honest by a test (`tests/test_metric_catalog.py`): every validated entry must name
a test that exists and that names the entry.
"""


def _scores_section() -> str:
    from hani2.evaluation import scores as S

    rows = []
    for s in S.SCORES:
        total = sum(c.weight for c in s.components) or 1.0
        parts = ", ".join(f"`{c.column}` {c.weight / total:.0%}" for c in s.components)
        rules = []
        if s.zero_if:
            rules.append("0 when " + ", ".join(f"`{z}`" for z in s.zero_if) + " is 1")
        if s.needs_assistant:
            rules.append("empty without an Assistant")
        rows.append(f"| `{s.name}` {_mark(C.validation_of(s.name))} | {s.track} | {_cell(s.description)} | {parts} | "
                    f"{'; '.join(rules) or '—'} |")
    table = "\n".join(rows)
    return f"""## Scores: combining criteria {{#scores}}

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
{table}

### Scores on leaderboards

A leaderboard ranks entrants (Assistants on the HI track, opponents on the HAN track) by one of its
`sort_options`, each a score or a criterion with a direction, and shows its `columns`. Each entrant's
value is the cell-adjusted mean over its counted games with a bootstrap confidence interval; an
entrant whose interval overlaps the leader's is tied with it. The pickers of the score builder and of the board settings show the
criteria in the groups below, with {MARK} next to validated ones. See
[Configuring a board](project-management.md#configuring-a-board) and
[Tracks and leaderboards](evaluation.md#tracks-and-leaderboards).
"""


def catalog_markdown() -> str:
    """The page ``docs/guide/metric-catalog.md``."""
    from hani2.evaluation.base import REGISTRY
    from hani2.evaluation.criteria import metric_criteria

    crits = metric_criteria()
    by_group: dict[str, list] = {g: [] for g in C.GROUP_IDS}
    for c in crits:
        by_group.setdefault(c.group, []).append(c)
    labels: dict[str, list[str]] = {g: [] for g in C.GROUP_IDS}
    for m in REGISTRY.values():
        for col in m.columns:
            if col.range.strip().lower() in ("category", "level name", "a label", "a name"):
                labels.setdefault(C.group_of(col.name, m.name), []).append(f"`{col.name}`")
    n_val = sum(c.validated for c in crits)
    out = [HEADER, "# Metric catalogue\n",
           "Every measure HANI2 computes for a negotiation, in groups of similar measures: what it measures, its "
           "range and direction, whether a score can use it, and whether its implementation is validated "
           f"({MARK}). The same groups and marks appear in the app: in the score builder's criteria picker, the "
           "leaderboard's sort and column choices and the board settings. How each measure is calculated, with "
           "formulas and worked examples, is in the [Metric reference](metrics.md); defaults for scores are in "
           "the [Criteria and scores reference](criteria.md). The questionnaires a study can use are listed in "
           "[Questionnaires](questionnaires.md).\n",
           f"{len(crits)} numeric measures of {len(REGISTRY)} metrics; {n_val} are validated.\n",
           "| Group | Measures | Validated | What it holds |\n| --- | --- | --- | --- |"]
    for g in C.GROUPS:
        cs = by_group.get(g.id, [])
        out.append(f"| [{g.title}](#group-{g.id}) | {len(cs)} | {sum(c.validated for c in cs)} | {_cell(g.description)} |")
    out.append("")
    out.append(_validation_section())
    out.append("## Measures by group\n")
    for g in C.GROUPS:
        cs = by_group.get(g.id, [])
        out.append(f"### {g.title} {{#group-{g.id}}}\n")
        out.append(g.description + "\n")
        if g.id == "subjective":
            out.append("Besides the scales of the bundled evaluation questionnaire listed here, every item and scale of "
                       "a project's own forms is a measure of this group: `q_<id>`, `scale_<name>`, `scale_<name>_norm`, "
                       "and `post_q_<id>`, `post_scale_<name>` for the post-session form. They are computed by the "
                       f"same validated rules {_mark(C.validation_of('scale_<name>'))}.\n")
        if g.id == "scores":
            out.append("A project's own scores join this group (see [Scores](#scores)).\n")
        if cs:
            out.append("| Measure | Title | What it measures | Range | Direction | Score | Validated | Metric |\n"
                       "| --- | --- | --- | --- | --- | --- | --- | --- |")
            for c in cs:
                out.append(f"| `{c.id}` | {_cell(c.title)} | {_cell(c.description)} | {_cell(c.range)} | {c.direction} | "
                           f"{_use(c)} | {_mark(c.validated_by)} | [`{c.metric}`](metrics.md) |")
            out.append("")
        if labels.get(g.id):
            out.append("Labels in this group (not numbers, so not usable in a score): " + ", ".join(labels[g.id]) + ".\n")
        why = sorted({C.not_validated_reason(c.id, c.metric) for c in cs if not c.validated} - {""})
        for w in why:
            out.append(f"*Not validated:* {w}\n")
    out.append(_scores_section())
    return "\n".join(out).rstrip() + "\n"


# --------------------------------------------------------------------------- #
# The questionnaires                                                           #
# --------------------------------------------------------------------------- #
_TYPE = {"likert5": "1–5", "likert7": "1–7", "yes_no": "yes / no", "text": "free text"}


def _scale_of(q: dict) -> str:
    t = str(q.get("type"))
    if t == "select":
        return " · ".join(str(o) for o in q.get("options") or [])
    rng = _TYPE.get(t, f"{q.get('min', 1)}–{q.get('max', 7)}")
    labels = q.get("labels") or {}
    if labels:
        anchors = ", ".join(f"{k} = {v}" for k, v in sorted(labels.items(), key=lambda kv: float(kv[0])))
        return f"{rng} ({anchors})"
    return rng


def _questions_table(qs: list[dict]) -> str:
    rows = ["| # | Id | Question | Answer | Scale |", "| --- | --- | --- | --- | --- |"]
    for i, q in enumerate(qs, 1):
        scale = f"`{q['scale']}`" if q.get("scale") else ""
        if q.get("reverse"):
            scale += " (reversed)"
        if q.get("direction") == "lower":
            scale += " (lower is better)"
        extra = " *(only with an Assistant)*" if q.get("requires") == "support_agent" else ""
        rows.append(f"| {i} | `{q.get('id')}` | {_cell(q.get('text', ''))}{extra} | {_cell(_scale_of(q))} | {scale} |")
    return "\n".join(rows)


def _scales_line(qs: list[dict]) -> str:
    scales: dict[str, int] = {}
    for q in qs:
        if q.get("scale"):
            scales[str(q["scale"])] = scales.get(str(q["scale"]), 0) + 1
    if not scales:
        return "Scales: none (single items)."
    return "Scales: " + ", ".join(f"`{k}` ({n} item{'s' if n > 1 else ''})" for k, n in scales.items()) + \
        " — each the mean of its items, reversed items scored backwards, as `scale_<name>` and `scale_<name>_norm`."


def _entry(qid: str, title: str, forms: list[str], qs: list[dict], heading: str = "###") -> list[str]:
    info = C.questionnaire_info(qid)
    v = bool(info and info.validated_by)
    mark = f" {_mark(info.validated_by, C.VALIDATED_SOURCE_TOOLTIP)}" if v else ""
    out = [f"{heading} {title}{mark} {{#{qid.replace('_', '-')}}}\n",
           f"Id `{qid}` · {len(qs)} question{'s' if len(qs) != 1 else ''} · for: " + ", ".join(f"`{f}`" for f in forms) + "\n"]
    if info:
        out.append(f"**Measures:** {info.measures}\n")
        if info.citation:
            src = f"[{info.citation}]({info.url})" if info.url else info.citation
            out.append(f"**Source:** {src}\n")
        out.append(f"**{'Validated' if v else 'Validation'}:** {info.note}\n")
    out.append(_scales_line(qs) + "\n")
    out.append(_questions_table(qs) + "\n")
    return out


def questionnaires_markdown() -> str:
    """The page ``docs/guide/questionnaires.md`` (bundled sets and forms only)."""
    import yaml

    from hani2 import questionnaires as Q
    from hani2.config import DEFAULT_SETTINGS_DIR

    lib = {}
    for p in sorted((DEFAULT_SETTINGS_DIR / Q.LIBRARY_DIR).glob("*.y*ml")):
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        lib[str(d.get("id") or p.stem)] = d
    sourced = [k for k in lib if (C.questionnaire_info(k) and C.questionnaire_info(k).citation)]
    own = [k for k in lib if k not in sourced]
    out = [HEADER, "# Questionnaires\n",
           "Every predefined questionnaire a project or study can use: what it measures, its source, its "
           f"scales and every question with its answer scale. A {MARK} marks a questionnaire validated against "
           "its source instrument: items, anchors, reversed items and scale scoring (see "
           "[What “validated” means](metric-catalog.md#validated)).\n",
           "Pick them on the admin console's **Study forms** page (**Add predefined questionnaires**), which shows "
           "the same marks, or with `hani2 questionnaire compose`; see [Study forms](study-forms.md#predefined-questionnaires). "
           "Their scales and items become measures of the [Questionnaires (subjective)](metric-catalog.md#group-subjective) "
           "group, usable in scores and on leaderboards.\n",
           "| Questionnaire | Id | Questions | Validated | Source |\n| --- | --- | --- | --- | --- |"]
    for k in sourced + own:
        d, info = lib[k], C.questionnaire_info(k)
        v = _mark(info.validated_by, C.VALIDATED_SOURCE_TOOLTIP) if info and info.validated_by else ""
        src = (f"[link]({info.url})" if info and info.url else ("yes" if info and info.citation else "own items"))
        out.append(f"| [{_cell(d.get('title', k))}](#{k.replace('_', '-')}) | `{k}` | {len(d['questions'])} | {v} | {src} |")
    out.append("")
    out.append("## Standard instruments\n")
    for k in sourced:
        d = lib[k]
        out += _entry(k, str(d.get("title", k)), list(d.get("forms") or []), d["questions"])
    out.append("## HANI2's own question sets\n")
    out.append("Items written for HANI2 studies. They have no source instrument, so they are not validated against "
               "one; their scales are scored by the same validated rules as every questionnaire.\n")
    for k in own:
        d = lib[k]
        out += _entry(k, str(d.get("title", k)), list(d.get("forms") or []), d["questions"])
    out.append("## Bundled forms\n")
    out.append("Complete forms that a study can name instead of writing its own (`HANI2_PER_NEG_YAML=evaluation`, or "
               "`\"pre_questionnaire\": \"expertise\"` in `env.json`; see [Study forms](study-forms.md)).\n")
    for p in sorted((DEFAULT_SETTINGS_DIR / "questionnaires").glob("*.y*ml")):
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        out += _entry(p.stem, f"{d.get('title') or p.stem} (`{p.stem}`)", [], d.get("questions") or [])
    return "\n".join(out).replace("for: \n", "\n").rstrip() + "\n"


def pages() -> dict[str, str]:
    return {PAGES["metric-catalog"]: catalog_markdown(), PAGES["questionnaires"]: questionnaires_markdown()}


def write(root: str | Path) -> list[str]:
    """Write the pages under ``root``; returns the ones that changed."""
    changed = []
    for rel, text in pages().items():
        p = Path(root) / rel
        if not p.is_file() or p.read_text(encoding="utf-8") != text:
            p.write_text(text, encoding="utf-8")
            changed.append(rel)
    return changed
