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
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from negmas import (
    EnumerableCartesianOutcomeSpace,
    LinearAdditiveUtilityFunction,
    Scenario,
    make_issue,
    make_os,
    opposition_level,
)
from negmas.preferences.value_fun import TableFun

from hani2.display import OfferContext, OfferDisplay
from hani2.tools import ui

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
    "DERIVED_HINTS",
    "derived_hints",
    "fill_hints",
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
    title: str = ""
    short_description: str = ""
    long_description: str = ""
    roles: dict[str, RoleFn] = field(default_factory=dict)
    role_descriptions: dict[str, str] = field(default_factory=dict)
    issues: Sequence[Issue] = ()
    disagreement: str = "Without a deal both sides walk away and take their best alternative."
    human_role: str | None = None
    role_stories: dict[str, str] = field(default_factory=dict)
    setup: Callable[[Rng], dict] | None = None
    source: str = ""
    band: tuple[float, float] = (0.35, 0.90)
    reserved: tuple[float, float] = (0.0, 0.15)
    max_tries: int = 40
    n_issue_columns: int = 2
    #: the template folder this story was read from (see :meth:`from_folder`)
    folder: Path | None = None
    #: the template's info: its texts are used as written in every generated scenario
    base_info: dict[str, Any] | None = None
    #: the template's issues (their negmas types are kept in generated scenarios)
    issue_objects: Sequence[Any] | None = None
    #: how offers are shown (:class:`~hani2.display.OfferDisplay`); ``None`` uses
    #: :class:`StoryOutcomeDisplay`. :meth:`from_folder` reads the folder's ``display.py``.
    display: Any = None

    @classmethod
    def from_folder(cls, folder: str | Path, roles: dict[str, RoleFn], **kwargs: Any) -> "Story":
        """A story whose texts, issues and roles come from a scenario folder.

        ``folder`` is a scenario in the on-disk format (``<Type>.yml``, one
        ``<Role>.yml`` per role, ``_info.yaml``) that can be played as it is;
        a bare name is looked up among the bundled templates
        (``hani2/sample_scenarios/Default/<name>``). Everything a participant
        reads (title, descriptions, issue descriptions and formats, item units,
        role descriptions, hints that are not computed) is taken from the
        folder, so editing the YAML changes every generated scenario without
        touching code. ``roles`` maps every role of the folder to the function
        that draws its preferences; the other keyword arguments (``setup``,
        ``band``, ``reserved``, ``max_tries``, ``source``) are as for
        :class:`Story`.
        """
        from negmas import Scenario as _Scenario

        from hani2.config import DEFAULT_SCENARIOS

        if isinstance(folder, str) and "/" not in folder and "\\" not in folder and not folder.startswith("~"):
            p = DEFAULT_SCENARIOS / folder  # a bare name is always a bundled template, never a folder in the cwd
        else:
            p = Path(folder).expanduser()
        if not p.is_dir():
            raise FileNotFoundError(f"no scenario folder {folder!r}")
        base = _Scenario.load(p, load_stats=False)
        if base is None:
            raise ValueError(f"{p} is not a scenario folder")
        info = _read_info(p) or dict(base.info or {})
        type_ = str(kwargs.pop("type", None) or p.name)  # the folder name (the generated outcome spaces get it)
        names = sorted(str(u.name) for u in base.ufuns)
        if sorted(roles) != names:
            raise ValueError(f"{type_}: the folder has roles {names} but generators were given for {sorted(roles)}")
        descs = info.get("issue_description") or {}
        fmts = info.get("issue_format") or {}
        units = (info.get("split") or {}).get("units") or {}
        issues = [Issue(i.name, list(i.all), descs.get(i.name, ""), fmts.get(i.name, "{}"),
                        tuple(units[i.name]) if i.name in units else None)  # type: ignore[arg-type]
                  for i in base.outcome_space.issues]
        role_desc = dict(info.get("role_descriptions") or {})
        if "display" not in kwargs and (p / "display.py").exists():
            from hani2.scenario_store import load_display_file

            kwargs["display"] = load_display_file(p / "display.py")
        return cls(type=type_, title=str(info.get("title", type_)),
                   short_description=str(info.get("short_description", "")),
                   long_description=str(info.get("long_description", "")), roles=dict(roles),
                   role_descriptions=role_desc, issues=issues, human_role=info.get("human_role"),
                   n_issue_columns=int(info.get("n_issue_columns", 2)), folder=p, base_info=info,
                   issue_objects=tuple(base.outcome_space.issues), **kwargs)


def _read_info(folder: Path) -> dict[str, Any]:
    from negmas.helpers.inout import load

    for name in ("_info.yml", "_info.yaml", "_info.yaml.yml"):
        f = folder / name
        if f.exists():
            return dict(load(f) or {})
    return {}


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
    objs = story.issue_objects or [make_issue(list(i.values), name=i.name) for i in issues]
    os = make_os(list(objs), name=story.type)
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
            unknown = [v for v in i.values if v not in vals]
            if unknown:
                raise ValueError(f"{story.type}/{role}: no score for {i.name} = {unknown} (the options in the "
                                 f"scenario are {list(i.values)}, the role function scored {list(vals)})")
            tables.append(TableFun(_rescale({v: float(vals[v]) for v in i.values})))
        ufuns.append(LinearAdditiveUtilityFunction(
            tuple(tables), weights=ws, reserved_value=round(rng.uniform(*story.reserved), 4),
            name=role, id=role, outcome_space=os))
        sides[role] = side
    return ctx, issues, os, ufuns, sides


def _opposition(os, ufuns) -> float:
    return float(opposition_level(ufuns, outcome_space=os, max_utils=tuple(1.0 for _ in ufuns)))


#: Hints computed from a role's utility function (rewritten for every generated scenario).
DERIVED_HINTS = ("Most important issue", "Least important issue", "Your ideal deal")


def _derive(issues, ufun, fmts: dict[str, str], split: bool) -> dict[str, Any]:
    """The most and least important issue and the ideal deal of a
    linear-additive ``ufun`` (nothing for other kinds of utility function)."""
    ws, tables = getattr(ufun, "weights", None), getattr(ufun, "values", None)
    if ws is None or tables is None:
        return {}
    h: dict[str, Any] = {}
    if len(issues) > 1:
        ranked = sorted(zip(ws, issues), key=lambda x: -x[0])
        h["Most important issue"] = ranked[0][1].name
        h["Least important issue"] = ranked[-1][1].name
    if not split:
        best = []
        for t, i in zip(tables, issues):
            v = max(list(i.all), key=lambda x: float(t(x)))
            try:
                best.append(f"{i.name}: {fmts.get(i.name, '{}').format(v)}")
            except (ValueError, TypeError, IndexError):
                best.append(f"{i.name}: {v}")
        h["Your ideal deal"] = "; ".join(best)
    return h


def derived_hints(scenario: Scenario) -> dict[str, dict[str, Any]]:
    """``{role: hints}`` computed from the utility functions of any scenario
    (uses ``issue_format`` and ``split`` from its info)."""
    info = scenario.info or {}
    fmts = info.get("issue_format") or {}
    split = bool((info.get("split") or {}).get("units"))
    return {u.name: _derive(scenario.outcome_space.issues, u, fmts, split) for u in scenario.ufuns}


def fill_hints(scenario: Scenario, overwrite: bool = False) -> Scenario:
    """Add the computed hints (see :data:`DERIVED_HINTS`) to the scenario's info,
    keeping the hints written by hand (``overwrite`` replaces the computed ones too)."""
    info = scenario.info = dict(scenario.info or {})
    hints = info.setdefault("hints", {})
    for role, d in derived_hints(scenario).items():
        h = hints.setdefault(role, {})
        for k, v in d.items():
            if overwrite or k not in h:
                h[k] = v
    return scenario


def _role_hints(base: dict[str, Any], derived: dict[str, Any], side: Side) -> dict[str, Any]:
    h = {k: v for k, v in base.items() if k not in DERIVED_HINTS and k not in side.hints}
    h.update({k: v for k, v in derived.items() if k != "Your ideal deal"})
    h.update(side.hints)
    if "Your ideal deal" in derived:
        h["Your ideal deal"] = derived["Your ideal deal"]
    return h


def _info(story: Story, issues: list[Issue], sides: dict[str, Side], ufuns, os=None) -> dict[str, Any]:
    fmts = {i.name: i.fmt for i in issues if i.fmt != "{}"}
    split = any(i.unit for i in issues)
    os_issues = os.issues if os is not None else ufuns[0].outcome_space.issues
    if story.base_info is not None:
        # a story read from a folder: its texts are used as written, only the hints change
        info = deepcopy(story.base_info)
        base_hints = info.get("hints") or {}
        info["hints"] = {u.name: _role_hints(base_hints.get(u.name) or {}, _derive(os_issues, u, fmts, split),
                                             sides[u.name]) for u in ufuns}
        info["story"] = story.type
        return info
    hints: dict[str, dict[str, Any]] = {}
    for u in ufuns:
        desc = story.role_descriptions.get(u.name, "")
        base = {"Your role": story.role_stories.get(u.name) or (f"{u.name}: {desc}" if desc else u.name)}
        hints[u.name] = _role_hints(base, _derive(os_issues, u, fmts, split), sides[u.name])
    roles = "\n".join(f"- **{r}**: {story.role_descriptions.get(r, '')}" for r in sorted(story.roles))
    long = (story.long_description.strip()
            + f"\n\n**The Roles**\n\n{roles}"
            + "\n\n**Utility Function** Every option of every issue has a value for you, and some issues matter "
              "more to you than others. You can see your preferences in the *Preferences* pane, and the hints "
              "tell you your most and least important issues."
            + "\n\n**Opponent Utility Function** Your opponent has their own values and priorities, which you do "
              "not know. Their role, described above, tells you which way they probably lean."
            + "\n\n**Value on Disagreement (Reservation Value)** " + story.disagreement.strip()
            + " Your reservation value is the utility you get in that case; your opponent has one too, which you "
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
        "role_descriptions": {r: story.role_descriptions.get(r, "") for r in sorted(story.roles)},
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
    return Scenario(outcome_space=os, ufuns=tuple(ufuns), info=_info(story, issues, sides, ufuns, os))


# --------------------------------------------------------------------------- #
# Display                                                                     #
# --------------------------------------------------------------------------- #
class StoryOutcomeDisplay(OfferDisplay):
    """Shows an offer in the story's terms, using the formats saved in the
    scenario info (so it also works for scenarios loaded from disk).

    For item splits (a ``split`` entry in the info) every surface is custom:
    the text reads "You get 2 clocks; your opponent gets 1 clock", history and
    the offer on the table show what each side gets, and the editor asks how
    many of each item *you* get, with a "Split evenly" button. Other stories
    use the default views with ``issue_format`` values.
    """

    # -- item splits ----------------------------------------------------------
    @staticmethod
    def _split(ctx: OfferContext) -> dict[str, Any]:
        return ctx.info.get("split") or {}

    @staticmethod
    def _flipped(ctx: OfferContext) -> bool:
        """Issue values count the items of the ``human`` role; a participant
        playing the other role gets the rest."""
        roles = {str(u.name).lower() for u in ctx.scenario.ufuns}
        return "human" in roles and bool(ctx.role) and ctx.role.lower() != "human"

    def _shares(self, offer: dict[str, Any], ctx: OfferContext) -> list[tuple[str, int, int, str, str]]:
        """``(issue, mine, theirs, singular, plural)`` per item kind."""
        split = self._split(ctx)
        units, totals = split.get("units", {}) or {}, split.get("totals", {}) or {}
        out = []
        for name in ctx.issue_names:
            v = offer.get(name)
            if v is None:
                continue
            one, many = (list(units.get(name) or []) + [name, name])[:2]
            total = int(totals.get(name, v))
            mine = int(v)
            if self._flipped(ctx):
                mine = total - mine
            out.append((name, mine, total - mine, str(one), str(many)))
        return out

    @staticmethod
    def _count(n: int, one: str, many: str) -> str:
        return f"{n} {one if n == 1 else many}"

    def text(self, offer: dict[str, Any] | None, ctx: OfferContext) -> str:
        if offer is None or not self._split(ctx):
            return super().text(offer, ctx)
        mine = [self._count(m, one, many) for _, m, _, one, many in self._shares(offer, ctx) if m]
        theirs = [self._count(t, one, many) for _, _, t, one, many in self._shares(offer, ctx) if t]
        return f"You get {', '.join(mine) or 'nothing'}; your opponent gets {', '.join(theirs) or 'nothing'}."

    def _sides(self, offer: dict[str, Any], ctx: OfferContext) -> list[dict] | None:
        if not self._split(ctx):
            return None
        shares = self._shares(offer, ctx)
        mine = {many: m for _, m, _, _, many in shares if m}
        theirs = {many: t for _, _, t, _, many in shares if t}
        return [ui.row(ui.outcome(mine, label="You get" + ("" if mine else " nothing")),
                       ui.outcome(theirs, label="Your opponent gets" + ("" if theirs else " nothing")), gap=2)]

    def history(self, offer: dict[str, Any], ctx: OfferContext) -> list[dict] | None:
        return self._sides(offer, ctx)

    def on_table(self, offer: dict[str, Any], ctx: OfferContext) -> list[dict] | None:
        return self._sides(offer, ctx)

    def controls(self, draft: dict[str, Any], ctx: OfferContext) -> list[dict] | None:
        split = self._split(ctx)
        if not split:
            return None
        units, totals = split.get("units", {}) or {}, split.get("totals", {}) or {}
        fields = []
        for name in ctx.issue_names:
            many = str((list(units.get(name) or []) + [name, name])[1])
            total = int(totals.get(name, 0))
            label = f"{many[:1].upper()}{many[1:]} you get (of {total})"
            widget = "buttons" if total <= 8 else "slider"
            if self._flipped(ctx):  # the issue counts the opponent's items: edit "mine" through on_input
                v = draft.get(name)
                mine = None if v is None else total - int(v)
                fields.append(ui.slider(f"mine:{name}", 0, total, mine if mine is not None else 0, label=label)
                              if widget == "slider" else
                              ui.radio(f"mine:{name}", list(range(total + 1)), mine, label=label))
            else:
                fields.append(ui.issue(name, widget=widget, label=label))
        return [ui.grid(*fields, cols=2),
                ui.row(ui.button("Split evenly", action="split_evenly", icon="scale"), align="center")]

    def on_input(self, name: str, value: Any, draft: dict[str, Any], ctx: OfferContext) -> dict[str, Any] | None:
        if name.startswith("mine:") and value is not None:
            issue = name[5:]
            total = int((self._split(ctx).get("totals") or {}).get(issue, 0))
            return {issue: total - int(value)}
        return None

    def on_action(self, action: str, payload: dict[str, Any], draft: dict[str, Any],
                  ctx: OfferContext) -> dict[str, Any] | None:
        if action == "split_evenly":
            totals = self._split(ctx).get("totals") or {}
            return {k: int(t) // 2 for k, t in totals.items() if k in ctx.issue_names}
        return None
