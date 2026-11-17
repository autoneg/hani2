"""Story-driven scenario generator.

A :class:`Story` describes a negotiation in plain terms: the issues and their
options, a public description, a private story for each role, and one
function per role that *draws* that role's preferences for a new scenario.
The story is the same in every scenario generated from it; the drawn
preferences decide which way the role leans on every issue and how much each
issue matters (always in a way the story explains), so every generated
scenario is different but always makes sense.

:func:`make_story_scenario` turns a story into a negmas ``Scenario`` with one
linear-additive utility function per role. Each issue's values are rescaled
to [0, 1] and the weights sum to 1, so utilities are on the [0, 1] scale. Draws
are repeated until the scenario's opposition level falls in the story's band
(real conflict, but a deal is possible), so on-the-fly scenarios are as good
as the ones in a saved pool.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from negmas import (
    EnumerableCartesianOutcomeSpace,
    LinearAdditiveUtilityFunction,
    Outcome,
    Scenario,
    make_issue,
    make_os,
    opposition_level,
)
from negmas.preferences.value_fun import TableFun

from hani2.display import DefaultOutcomeDisplay

__all__ = [
    "Issue",
    "Side",
    "Story",
    "StoryOutcomeDisplay",
    "make_story_scenario",
    "up",
    "down",
    "peak",
    "scores",
    "taste",
    "jitter",
    "weights",
]

Rng = random.Random


@dataclass
class Issue:
    """One negotiated issue.

    ``fmt`` formats a value for display (``"${:,}"`` → ``$3,400``). For an item
    split, ``unit`` is the item's ``(singular, plural)`` name and the issue's
    values are how many items the ``human`` side gets.
    """

    name: str
    values: Sequence[Any]
    description: str = ""
    fmt: str = "{}"
    unit: tuple[str, str] | None = None


@dataclass
class Side:
    """One role's drawn preferences for one scenario.

    ``values`` maps issue → option → score (any scale; rescaled to [0, 1] per
    issue). ``weights`` maps issue → importance (normalised to sum to 1).
    ``hints`` are extra facts of this draw shown to the role (for example a
    drawn estimate); the most and least important issues and the ideal deal
    are added automatically.
    """

    values: dict[str, dict[Any, float]]
    weights: dict[str, float]
    hints: dict[str, Any] = field(default_factory=dict)


#: Draws a role's preferences: ``(rng, context) -> Side``. ``context`` is shared
#: by both roles of one draw (it holds what :attr:`Story.setup` returned).
RoleFn = Callable[[Rng, dict], Side]


@dataclass
class Story:
    """A negotiation story that generates scenarios.

    The story itself (title, descriptions, issues, roles) is the same in
    every scenario generated from it; only the utility functions (and the
    hints derived from them) change.

    ``type`` is the scenario type and the outcome-space name. ``roles`` maps a
    role name to the function drawing its preferences; roles are stored in
    alphabetical order (the order ``Scenario.load`` returns them in), so the
    participant (negotiator index 1 by default) is the second role
    alphabetically. ``role_descriptions`` are one-line descriptions of the
    roles (shown to both sides, and to each role as the hint "Your role");
    ``role_stories`` optionally replace that hint with a longer private text. ``long_description`` describes the domain (start it
    with ``**The Domain**``); the paragraphs on the utility functions and on
    disagreement (from ``disagreement``) are added in the same form for every
    story. ``human_role`` is the role a participant plays by default (see the
    role-assignment rules in :mod:`hani2.scenario_store`). ``setup`` draws
    hidden shared facts (``context``) that both role functions see.
    """

    type: str
    title: str
    short_description: str
    long_description: str
    roles: dict[str, RoleFn]
    role_descriptions: dict[str, str]
    issues: Sequence[Issue]
    disagreement: str = "Without a deal both sides walk away and take their best alternative."
    human_role: str | None = None
    role_stories: dict[str, str] = field(default_factory=dict)
    setup: Callable[[Rng], dict] | None = None
    source: str = ""
    band: tuple[float, float] = (0.35, 0.90)
    reserved: tuple[float, float] = (0.0, 0.15)
    max_tries: int = 40
    n_issue_columns: int = 2


# --------------------------------------------------------------------------- #
# Value-curve helpers (all return {option: score})                            #
# --------------------------------------------------------------------------- #
def up(values: Sequence[Any], rng: Rng, curve: tuple[float, float] = (0.6, 1.8)) -> dict[Any, float]:
    """More is better: the first option scores 0, the last 1. ``curve`` is the
    range of the exponent (below 1: early steps matter most; above 1: only the
    top options really count)."""
    n = len(values)
    e = rng.uniform(*curve)
    return {v: (i / (n - 1)) ** e if n > 1 else 1.0 for i, v in enumerate(values)}


def down(values: Sequence[Any], rng: Rng, curve: tuple[float, float] = (0.6, 1.8)) -> dict[Any, float]:
    """Less is better: the first option scores 1, the last 0."""
    s = up(list(reversed(values)), rng, curve)
    return {v: s[v] for v in values}


def peak(values: Sequence[Any], at: int, rng: Rng, below: tuple[float, float] = (0.2, 0.5),
         above: tuple[float, float] = (0.2, 0.5)) -> dict[Any, float]:
    """The option at index ``at`` is best; each step away loses a random share
    (``below`` / ``above`` give the loss per step on each side)."""
    n = len(values)
    at = max(0, min(n - 1, at))
    out = [0.0] * n
    out[at] = 1.0
    for i in range(at - 1, -1, -1):
        out[i] = max(0.0, out[i + 1] - rng.uniform(*below))
    for i in range(at + 1, n):
        out[i] = max(0.0, out[i - 1] - rng.uniform(*above))
    return dict(zip(values, out))


def scores(values: Sequence[Any], base: Sequence[float], rng: Rng, noise: float = 0.1) -> dict[Any, float]:
    """Given scores per option, with a little noise so no two draws are equal."""
    return {v: max(0.0, b + rng.uniform(-noise, noise)) for v, b in zip(values, base)}


def taste(values: Sequence[Any], rng: Rng, favourite: Any = None) -> dict[Any, float]:
    """A random taste over unordered options (``favourite`` scores highest)."""
    out = {v: rng.random() for v in values}
    if favourite is not None:
        out[favourite] = max(out.values()) + 0.3
    return out


def jitter(d: dict[Any, float], rng: Rng, noise: float = 0.1) -> dict[Any, float]:
    return {k: max(0.0, v + rng.uniform(-noise, noise)) for k, v in d.items()}


def weights(rng: Rng, **ranges: tuple[float, float]) -> dict[str, float]:
    """Issue importances drawn from ranges: ``weights(rng, Rent=(3, 5), ...)``.
    Issue names with spaces are passed with ``**{"Move-in date": (1, 2)}``."""
    return {k: rng.uniform(*r) for k, r in ranges.items()}


# --------------------------------------------------------------------------- #
# Building the scenario                                                       #
# --------------------------------------------------------------------------- #
def _rescale(d: dict[Any, float]) -> dict[Any, float]:
    lo, hi = min(d.values()), max(d.values())
    if hi - lo < 1e-9:
        return {k: 1.0 for k in d}
    return {k: round((v - lo) / (hi - lo), 4) for k, v in d.items()}


def _draw(story: Story, rng: Rng):
    ctx = dict(story.setup(rng)) if story.setup else {}
    issues = list(story.issues)
    os = make_os([make_issue(list(i.values), name=i.name) for i in issues], name=story.type)
    assert isinstance(os, EnumerableCartesianOutcomeSpace)
    sides: dict[str, Side] = {}
    ufuns = []
    for role in sorted(story.roles):
        side = story.roles[role](rng, ctx)
        missing = [i.name for i in issues if i.name not in side.values or i.name not in side.weights]
        if missing:
            raise ValueError(f"{story.type}/{role}: no preferences for {missing}")
        total = sum(max(0.0, side.weights[i.name]) for i in issues) or 1.0
        ws = tuple(max(0.0, side.weights[i.name]) / total for i in issues)
        tables = []
        for i in issues:
            vals = side.values[i.name]
            tables.append(TableFun(_rescale({v: float(vals[v]) for v in i.values})))
        ufuns.append(LinearAdditiveUtilityFunction(
            tuple(tables), weights=ws, reserved_value=round(rng.uniform(*story.reserved), 4),
            name=role, id=role, outcome_space=os))
        sides[role] = side
    return ctx, issues, os, ufuns, sides


def _opposition(os, ufuns) -> float:
    return float(opposition_level(ufuns, outcome_space=os, max_utils=tuple(1.0 for _ in ufuns)))


def _info(story: Story, issues: list[Issue], sides: dict[str, Side], ufuns) -> dict[str, Any]:
    hints: dict[str, dict[str, Any]] = {}
    for u in ufuns:
        side = sides[u.name]
        ranked = sorted(zip(u.weights, issues), key=lambda x: -x[0])
        desc = story.role_descriptions.get(u.name, "")
        h: dict[str, Any] = {"Your role": story.role_stories.get(u.name) or (f"{u.name}: {desc}" if desc else u.name)}
        if len(issues) > 1:
            h["Most important issue"] = ranked[0][1].name
            h["Least important issue"] = ranked[-1][1].name
        h.update(side.hints)
        if not any(i.unit for i in issues):
            best = []
            for t, i in zip(u.values, issues):
                v = max(i.values, key=lambda x: float(t(x)))
                try:
                    best.append(f"{i.name}: {i.fmt.format(v)}")
                except (ValueError, TypeError, IndexError):
                    best.append(f"{i.name}: {v}")
            h["Your ideal deal"] = "; ".join(best)
        hints[u.name] = h
    roles = "\n".join(f"- **{r}**: {story.role_descriptions.get(r, '')}" for r in sorted(story.roles))
    long = (story.long_description.strip()
            + f"\n\n**The Roles**\n\n{roles}"
            + "\n\n**Utility Function** Every option of every issue has a value for you, and some issues matter "
              "more to you than others. You can see your preferences in the *Preferences* pane, and the hints "
              "tell you your most and least important issues."
            + "\n\n**Partner Utility Function** Your partner has their own values and priorities, which you do "
              "not know. Their role, described above, tells you which way they probably lean."
            + "\n\n**Value on Disagreement (Reservation Value)** " + story.disagreement.strip()
            + " Your reservation value is the utility you get in that case; your partner has one too, which you "
              "do not know.")
    if story.source:
        long += f"\n\n*{story.source}*"
    info: dict[str, Any] = {
        "Name": story.type,
        "title": story.title,
        "n_issue_columns": story.n_issue_columns,
        "issue_description": {i.name: i.description for i in issues},
        "issue_format": {i.name: i.fmt for i in issues if i.fmt != "{}"},
        "hints": hints,
        "short_description": story.short_description.strip(),
        "long_description": long,
        "story": story.type,
    }
    if story.human_role:
        info["human_role"] = story.human_role
    units = {i.name: list(i.unit) for i in issues if i.unit}
    if units:
        info["split"] = {"units": units, "totals": {i.name: max(i.values) for i in issues if i.unit}}
    return info


def make_story_scenario(story: Story, index: int = 0, rng: Rng | None = None) -> Scenario:
    """Generate one scenario from ``story`` (``index`` is the pool slot; it is
    accepted for compatibility with the other makers and not used)."""
    rng = rng or random.Random(random.random())
    best = None
    lo, hi = story.band
    for _ in range(max(1, story.max_tries)):
        ctx, issues, os, ufuns, sides = _draw(story, rng)
        opp = _opposition(os, ufuns)
        if lo <= opp <= hi:
            best = (0.0, issues, os, ufuns, sides)
            break
        dist = lo - opp if opp < lo else opp - hi
        if best is None or dist < best[0]:
            best = (dist, issues, os, ufuns, sides)
    assert best is not None
    _, issues, os, ufuns, sides = best
    return Scenario(outcome_space=os, ufuns=tuple(ufuns), info=_info(story, issues, sides, ufuns))


# --------------------------------------------------------------------------- #
# Display                                                                     #
# --------------------------------------------------------------------------- #
class StoryOutcomeDisplay(DefaultOutcomeDisplay):
    """Writes an offer in the story's terms, using the formats saved in the
    scenario info (so it also works for scenarios loaded from disk)."""

    def str(self, outcome: Outcome | None, scenario: Scenario, is_done: bool, from_human: bool) -> str:
        if outcome is None:
            return super().str(outcome, scenario, is_done, from_human)
        info = scenario.info or {}
        issues = scenario.outcome_space.issues
        split = info.get("split") or {}
        if split:
            units, totals = split.get("units", {}), split.get("totals", {})
            mine, theirs = [], []
            for issue, v in zip(issues, outcome):
                one, many = units.get(issue.name, (issue.name, issue.name))
                n_mine = int(v)
                n_theirs = int(totals.get(issue.name, n_mine)) - n_mine
                if n_mine:
                    mine.append(f"{n_mine} {one if n_mine == 1 else many}")
                if n_theirs:
                    theirs.append(f"{n_theirs} {one if n_theirs == 1 else many}")
            return f"You get {', '.join(mine) or 'nothing'}; your partner gets {', '.join(theirs) or 'nothing'}."
        fmts = info.get("issue_format", {}) or {}
        parts = []
        for issue, v in zip(issues, outcome):
            f = fmts.get(issue.name, "{}")
            try:
                txt = f.format(v)
            except (ValueError, TypeError, IndexError):
                txt = str(v)
            parts.append(f"{issue.name}: {txt}")
        return ", ".join(parts)

    def table(self, outcome: Outcome | None, scenario: Scenario, is_done: bool, from_human: bool):
        if not outcome:
            return []
        fmts = (scenario.info or {}).get("issue_format", {}) or {}
        row = {}
        for issue, v in zip(scenario.outcome_space.issues, outcome):
            try:
                row[issue.name] = fmts.get(issue.name, "{}").format(v)
            except (ValueError, TypeError, IndexError):
                row[issue.name] = v
        return [row]
