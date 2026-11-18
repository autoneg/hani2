"""The metric reference: what every metric and column measures and how it is
calculated, built from the metric definitions (single source of truth).

Every :class:`~hani2.evaluation.base.Metric` and
:class:`~hani2.evaluation.base.Column` carries a one-line ``description``, a
LaTeX ``formula`` and Markdown ``details``. This module adds what is shared by
all of them (the notation, the figures, the statistics of ``compare`` and the
identifier columns) and renders the reference for the API
(:func:`metric_reference`), the command line (:func:`details_markdown`) and the
documentation (:func:`reference_markdown`, written by
``scripts/make_metric_reference.py``).

Math is written ``$...$`` (inline) and ``$$...$$`` (display). An inline ``$``
opens math only when the next character is not a space, and closes it only
when the previous character is not a space (the docs' arithmatex "smart
dollar"); the replay tool also requires that the closing ``$`` is not followed
by a digit. Write ``\\$`` for a literal dollar sign. So "costs $5 or $6" stays
text in both.
"""

from __future__ import annotations

import html
from functools import lru_cache
from pathlib import Path
from typing import Callable

from hani2.evaluation.base import REGISTRY, Column, Metric

FIG_DIR = Path(__file__).parent / "figures"

KINDS = {
    "hard": ("Hard metrics", "Computed from the recording alone, with no judgement involved."),
    "subjective": ("Subjective metrics", "The participant's own answers to the questionnaire."),
    "soft": ("Soft metrics (language-model judge)",
             "Judged by a language model from a transcript of the session. Opt-in, because every judgement costs "
             "calls."),
}

#: the symbols used by every formula
NOTATION = r"""
Every formula uses the same symbols.

* $\Omega$ — the outcomes of the scenario (every combination of issue values); $\omega \in \Omega$ one
  outcome, $\omega^*$ the agreement and $\varnothing$ "no agreement".
* $h$ — the Human's seat. Its offers and actions may be made by the Human, by the Assistant acting for
  them or by the autopilot; $A_h$ are the actions the Human took themselves.
* $u_h(\omega)$ — the Human's utility of $\omega$; $u_o(\omega) = \sum_{j \neq h} u_j(\omega)$ — the
  Opponent side's utility (the single Opponent in a bilateral negotiation, the sum of the other parties
  otherwise).
* $r_h$, $r_o = \sum_{j \neq h} r_j$ — the reservation values: what each side gets without an agreement
  (0 when the scenario gives none). $d = (r_h, r_o)$ is the disagreement (reservation) point.
* $p(\omega) = (u_h(\omega), u_o(\omega))$ — the outcome as a point of the utility space, with
  $p(\varnothing) = d$; $\lVert \cdot \rVert_2$ is the Euclidean distance in that space.
* $\bar u_h = \max_{\omega \in \Omega} u_h(\omega)$ and $\bar u_o = \max_{\omega \in \Omega} u_o(\omega)$ —
  each side's best possible utility; $(\bar u_h, \bar u_o)$ is the ideal point.
* $\mathcal{P}$ — the Pareto frontier: the outcomes $\omega$ for which no $\omega'$ has
  $u_h(\omega') \geq u_h(\omega)$ and $u_o(\omega') \geq u_o(\omega)$ with one of them strictly greater
  (of several outcomes with the same utilities, one is kept).
* $\nu$ — the Nash bargaining solution and $\kappa$ the Kalai–Smorodinsky solution (see `optimality`).
* $x^+ = \max(x, 0)$; $\mathbb{1}[\cdot]$ is 1 when the condition holds and 0 otherwise.
* $t$ — times in seconds on the recording clock (0 when the recording started, i.e. when the scenario
  was loaded).

The examples use one small scenario, drawn in the figure: eight outcomes A–H, reservation values
$r_h = r_o = 0.2$ and an agreement on F $= (0.5, 0.45)$.
"""

#: figures shown with the metrics that name them
FIGURES = {
    "outcome_space": dict(
        title="Outcome space of the example scenario",
        caption=("The example scenario in the utility space: the Pareto frontier A–E, the reservation point d, the "
                 "Nash point B (the largest product of gains, the shaded rectangle), the Kalai–Smorodinsky point C "
                 "(on the dotted line from d to the ideal point), the agreement F and its distances, and the "
                 "opposition of the scenario (from the ideal point to the frontier)."),
    ),
    "move_types": dict(
        title="Move types",
        caption=("A move is the change from one offer of a side to its next, placed by the change of the mover's "
                 "own utility (Δself) and of the other side's (Δother). The axes belong to the region of the same "
                 "colour: Δother = 0 counts as selfish when Δself > 0 and as unfortunate when Δself < 0."),
    ),
}

#: the statistics ``compare`` reports per group
AGGREGATES = [
    Column("n", "n", "Recordings in the group", formula=r"n_g = \lvert R_g \rvert", range="count",
           details=r"""
The number of recordings $R_g$ in group $g$ (all of them, also those where a column is empty; the
mean of a column uses only the recordings that have a value).
"""),
    Column("mean", "Mean", "Mean of a column over the group",
           formula=r"\bar x_g = \frac{1}{\lvert R^x_g \rvert} \sum_{r \in R^x_g} x_r, \qquad R^x_g = \{r \in R_g : x_r \text{ is a number}\}",
           range="the column's range",
           details=r"""
The plain mean of a numeric column over the recordings of the group that have a value.
"""),
    Column("std", "Standard deviation", "Sample standard deviation of a column over the group",
           formula=r"s_g = \sqrt{\frac{1}{\lvert R^x_g \rvert - 1} \sum_{r \in R^x_g} (x_r - \bar x_g)^2}",
           range="≥ 0",
           details=r"""
The sample standard deviation (with $n - 1$); 0 when only one recording has a value.
"""),
    Column("balanced", "Scenario-balanced mean", "Mean of the per-scenario means",
           formula=r"\tilde x_g = \frac{1}{\lvert S_g \rvert} \sum_{s \in S_g} \bar x_{g,s}",
           range="the column's range",
           details=r"""
The mean of a column computed within each scenario $s$ played by the group first ($\bar x_{g,s}$), then
averaged over the scenarios $S_g$, so that a group that happened to play more of an easy scenario is
not favoured.

**Example.** Group A has three recordings of scenario s1 with values 0.2, 0.4 and 0.6 and one of s2
with 1.0. The mean is $2.2/4 = 0.55$; the scenario-balanced mean is $(0.4 + 1.0)/2 = 0.7$.
"""),
    Column("pass_hat_k", "pass^k", "Chance that k recordings of the same scenario all succeed", True,
           formula=r"\text{pass}^k_g = \frac{1}{\lvert S_g \rvert} \sum_{s \in S_g} \frac{\binom{c_s}{k}}{\binom{n_s}{k}}, \qquad k = 1, \dots, \min\big(5, \min_{s} n_s\big)",
           range="[0, 1]",
           details=r"""
Reliability across repeated sessions (from τ-bench, Yao et al., 2024): the probability that $k$
recordings drawn without replacement from the $n_s$ recordings of the group in scenario $s$ all
succeed, when $c_s$ of them did, averaged over the scenarios. pass^1 is the success rate; a fast drop
with $k$ shows an inconsistent Assistant or Opponent.

A recording succeeds when its success column (default `agreement`) is at least the threshold (default
1, i.e. a deal); set e.g. `--option success=human_advantage --option success_threshold=0.5`. Only
recordings with a value of the success column count. The largest $k$ is limited by the scenario with
the fewest recordings.

**Example.** 4 recordings of one scenario, 2 successful: pass^1 $= 2/4 = 0.5$,
pass^2 $= \binom{2}{2} / \binom{4}{2} = 1/6$, pass^3 $= 0$.
"""),
    Column("scenarios", "Scenarios", "Scenarios averaged in pass^k", formula=r"\lvert S_g \rvert", range="count",
           details=r"""
The number of scenarios whose pass^k values were averaged for the group.
"""),
]

#: the identifier columns copied into every row
IDENTIFIERS = [
    Column("key", "Key", "Where the recording is stored (the key used by the replay tool, or the file path)"),
    Column("id", "Recording", "The recording's id"),
    Column("user", "User", "The participant's user name"),
    Column("mode", "Mode", "The session mode (e.g. normal or a study)"),
    Column("scenario", "Scenario", "The scenario's name (used by the scenario-balanced means and pass^k)"),
    Column("opponent", "Opponent", "The Opponent agent"),
    Column("support_agent", "Assistant", "The Assistant's name or class, or none when there was no Assistant"),
    Column("support_model", "Assistant model", "The language model the Assistant used"),
    Column("experiment", "Experiment", "The experiment (study) the session belonged to"),
    Column("started", "Started", "When the recording was made"),
]


@lru_cache(maxsize=None)
def figure_svg(name: str) -> str:
    """The SVG of a figure (``FIGURES``), to inline in a page."""
    if name not in FIGURES:
        raise KeyError(name)
    return (FIG_DIR / f"{name}.svg").read_text().strip()


def _metrics() -> list[Metric]:
    order = {"hard": 0, "subjective": 1, "soft": 2}
    return sorted(REGISTRY.values(), key=lambda m: order.get(m.kind, 9))


def metric_reference(figures: bool = True) -> dict:
    """Everything the reference shows: ``notation``, ``metrics`` (full info),
    ``aggregates``, ``identifiers`` and ``figures`` (title, caption, svg)."""
    out = dict(
        notation=NOTATION.strip(),
        kinds={k: dict(title=t, description=d) for k, (t, d) in KINDS.items()},
        metrics=[m.info(full=True) for m in _metrics()],
        aggregates=[c.info() for c in AGGREGATES],
        identifiers=[dict(name=c.name, title=c.title, description=c.description) for c in IDENTIFIERS],
    )
    if figures:
        out["figures"] = {k: dict(v, svg=figure_svg(k)) for k, v in FIGURES.items()}
    return out


# --------------------------------------------------------------------------- #
# Markdown                                                                     #
# --------------------------------------------------------------------------- #
def direction(c: Column) -> str:
    return {True: "higher is better", False: "lower is better"}.get(c.higher_is_better, "no better direction")


def column_markdown(c: Column, level: int = 4) -> str:
    h = "#" * level
    meta = [f"*{c.description}*"] if c.description else []
    facts = [f"**Range:** {c.range}" if c.range else "", f"**Direction:** {direction(c)}"]
    meta.append(" · ".join(f for f in facts if f))
    parts = [f"{h} `{c.name}` — {c.title}", "\n\n".join(meta)]
    if c.formula:
        parts.append(f"$$\n{c.formula}\n$$")
    if c.details:
        parts.append(c.details.strip())
    return "\n\n".join(parts)


def metric_markdown(m: Metric, level: int = 3, figure: Callable[[str], str] | None = None,
                    column_level: int | None = None) -> str:
    """A metric with all its columns as Markdown. ``figure(name)`` returns the
    Markdown/HTML that shows a figure (default: a one-line mention)."""
    h = "#" * level
    flags = [m.kind] + (["needs a language model"] if m.needs_llm else []) + ([] if m.default else ["not run by default"])
    parts = [f"{h} `{m.name}` — {m.title}", f"*{' · '.join(flags)}*"]
    if m.description:
        parts.append(m.description.strip())
    if m.formula:
        parts.append(f"$$\n{m.formula}\n$$")
    if m.details:
        parts.append(m.details.strip())
    for f in m.figures:
        parts.append(figure(f) if figure else f"*Figure: {FIGURES[f]['title']}* — {FIGURES[f]['caption']}")
    if m.options:
        parts.append("**Options:**\n\n" + "\n".join(f"* `{k}` — {v}" for k, v in m.options.items()))
    cl = column_level or level + 1
    parts += [column_markdown(c, cl) for c in m.columns]
    if m.patterns:
        parts.append(f"{'#' * cl} Dynamic columns\n\nColumns whose names depend on the questionnaire.")
        parts += [column_markdown(c, cl + 1 if cl < 6 else cl) for c in m.patterns]
    return "\n\n".join(parts)


def aggregates_markdown(level: int = 3) -> str:
    return "\n\n".join(column_markdown(c, level) for c in AGGREGATES)


def identifiers_markdown() -> str:
    rows = "\n".join(f"| `{c.name}` | {c.description} |" for c in IDENTIFIERS)
    return "| Column | Meaning |\n| --- | --- |\n" + rows


def find(name: str) -> list[tuple[str, object]]:
    """Metrics, columns and statistics called ``name``: ``[(kind, obj)]``
    with kind ``metric``, ``column`` (``(metric, column)``) or ``aggregate``."""
    out: list[tuple[str, object]] = []
    if name in REGISTRY:
        out.append(("metric", REGISTRY[name]))
    for m in _metrics():
        c = m.column_info(name)
        if c is not None:
            out.append(("column", (m, c)))
    out += [("aggregate", c) for c in AGGREGATES if c.name == name]
    return out


def details_markdown(name: str | None = None) -> str:
    """The reference as Markdown: everything, or one metric / column / statistic."""
    if not name:
        parts = ["## Notation", NOTATION.strip()]
        for kind, (title, desc) in KINDS.items():
            ms = [m for m in _metrics() if m.kind == kind]
            if ms:
                parts += [f"## {title}", desc] + [metric_markdown(m, 3) for m in ms]
        parts += ["## Comparing groups", aggregates_markdown(3)]
        return "\n\n".join(parts) + "\n"
    hits = find(name)
    if not hits:
        raise KeyError(name)
    parts = []
    for kind, obj in hits:
        if kind == "metric":
            parts.append(metric_markdown(obj, 2))  # type: ignore[arg-type]
        elif kind == "column":
            m, c = obj  # type: ignore[misc]
            parts.append(f"*Column of `{m.name}` ({m.title})*\n\n" + column_markdown(c, 2))
        else:
            parts.append("*Statistic of `compare`*\n\n" + column_markdown(obj, 2))  # type: ignore[arg-type]
    return "\n\n".join(parts) + "\n"


def _figure_html(name: str) -> str:
    f = FIGURES[name]
    return (f'<figure class="metric-figure" id="fig-{name}">\n{figure_svg(name)}\n'
            f"<figcaption>{html.escape(f['caption'])}</figcaption>\n</figure>")


def reference_markdown() -> str:
    """The documentation page ``docs/guide/metrics.md``."""
    shown: set[str] = set()

    def fig(name: str) -> str:
        if name in shown:
            return f"*Figure:* see [{FIGURES[name]['title']}](#fig-{name}) above."
        shown.add(name)
        return _figure_html(name)

    parts = [
        "<!-- Generated from the metric definitions in src/hani2/evaluation by "
        "scripts/make_metric_reference.py. Do not edit by hand. -->",
        "# Metric reference",
        "What every [evaluation metric](evaluation.md) and every column measures and exactly how it is "
        "calculated: a plain-language explanation, the formula, how to read it, a worked example and the "
        "caveats. The same texts are shown by `hani2 replay metrics --details [NAME]`, by the **Metric "
        "reference** panel of the replay tool (the ⓘ buttons next to metrics and columns) and by "
        "`GET /api/replay/metric-reference`.",
        "## Notation",
        NOTATION.strip(),
    ]
    for kind, (title, desc) in KINDS.items():
        ms = [m for m in _metrics() if m.kind == kind]
        if ms:
            parts += [f"## {title}", desc] + [metric_markdown(m, 3, figure=fig) for m in ms]
    parts += ["## Comparing groups",
              "`compare` (`hani2 replay compare`, **Compare** in the replay tool) groups evaluated recordings "
              "by a field (`opponent`, `support_agent`, `user`, `scenario`, `experiment`, …) and reports for "
              "every group and numeric column:",
              aggregates_markdown(3),
              "## Identifier columns",
              "Every row also carries these fields, used to group and filter:",
              identifiers_markdown()]
    return "\n\n".join(parts) + "\n"
