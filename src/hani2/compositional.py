"""Compositional scenarios: build negotiations from atomic difficulty factors.

Each scenario is one *cell* of a factorial design: a level of every factor.

=================  =========  ==================================================
factor             kind       levels
=================  =========  ==================================================
``issues``         scenario   how many issues are negotiated (2, 4, 6)
``opposition``     scenario   how opposed the two sides' preferences are
``zopa``           scenario   how many deals both sides prefer to no deal
``constraint``     scenario   a private hard limit of the participant
``deception``      episode    an honest or a bluffing opponent
``time_pressure``  episode    how many rounds the negotiation may take
=================  =========  ==================================================

*Scenario* factors shape the scenario files; *episode* factors are settings of
the negotiation (the opponent and the step limit), stored in the scenario's
info as ``composition.episode`` and applied by :func:`run_pool` (a session's own
settings win over the scenario files, so they cannot live there).

Every scenario is checked automatically (:func:`verify`, run on the scenario as
reloaded from disk): each factor's measured value lies in its level's band, the
zone of possible agreement (ZOPA) holds enough deals, the *target* deal is
reachable, a hidden constraint really bites, and the episode settings resolve.

**The target** is the Nash bargaining solution over the ZOPA: the deal that
maximises the product of both sides' gains over their reservation values,
among the deals that respect the participant's constraint. It is a deal the
opponent would accept and the fair, efficient benchmark the participant's
result is compared with (``target_attainment`` in :mod:`hani2.evaluation.factors`).

:func:`sample_cells` draws a balanced set of cells (every level of every
factor, and every pair of levels, appears about equally often), and
:func:`factor_report` reports scores per factor level, so you can see which
factor makes an Assistant fail.
"""

from __future__ import annotations

import copy
import itertools
import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence, cast

import numpy as np
from negmas import LinearAdditiveUtilityFunction, Scenario, make_issue, make_os
from negmas.preferences.value_fun import TableFun

__all__ = [
    "CATEGORY", "Factor", "FACTORS", "Cell", "Composed", "Verification", "all_cells", "sample_cells",
    "compose", "verify", "generate_pool", "run_pool", "factor_report", "format_report", "parse_levels",
]

#: the scenario category (folder) generated pools use by default
CATEGORY = "Compositional"
HUMAN_ROLE = "Buyer"
OPPONENT_ROLE = "Supplier"


# --------------------------------------------------------------------------- #
# Factors                                                                     #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Factor:
    """One difficulty factor. ``levels`` maps a level name to its setting (in
    order of increasing difficulty); ``kind`` is ``scenario`` or ``episode``."""

    name: str
    title: str
    kind: str
    levels: dict[str, Any]
    description: str = ""

    @property
    def level_names(self) -> list[str]:
        return list(self.levels)


FACTORS: dict[str, Factor] = {
    f.name: f for f in (
        Factor("issues", "Number of issues", "scenario", {"2": 2, "4": 4, "6": 6},
               "How many issues are negotiated. More issues give more room for trade-offs but more to track."),
        Factor("opposition", "Opposition", "scenario",
               {"low": (0.05, 0.25), "medium": (0.25, 0.42), "high": (0.42, 0.75)},
               "The opposition level of the two preference profiles: the distance from the best outcome to the "
               "ideal point (1, 1), over all outcomes (reservation values ignored, so it is independent of the "
               "ZOPA factor). Low: much common ground; high: nearly zero-sum."),
        Factor("zopa", "ZOPA size", "scenario", {"wide": (0.20, 0.50), "narrow": (0.01, 0.06)},
               "The share of all outcomes that both sides prefer to no deal (set through the reservation values)."),
        Factor("constraint", "Hidden constraint", "scenario", {"none": False, "hidden": True},
               "A private hard limit of the participant that the opponent does not know: the opponent's favourite "
               "option on its most important issue is worth less than no deal to the participant."),
        Factor("deception", "Opponent honesty", "episode",
               {"honest": "helpers.HonestTBNegotiator", "deceptive": "helpers.DeceptiveTBNegotiator"},
               "The opponent: both concede on the same curve; the deceptive one lies about its priorities, calls "
               "every offer final and cites an outside offer it does not have."),
        Factor("time_pressure", "Time pressure", "episode", {"relaxed": 40, "tight": 8},
               "The number of rounds (mechanism steps) before the negotiation ends without a deal."),
    )
}


def parse_levels(specs: Iterable[str] | None) -> dict[str, list[str]]:
    """``["issues=2,4", "zopa=narrow"]`` → ``{"issues": ["2", "4"], "zopa": ["narrow"]}`` (validated)."""
    out: dict[str, list[str]] = {}
    for spec in specs or []:
        name, _, levels = str(spec).partition("=")
        name = name.strip()
        if name not in FACTORS:
            raise ValueError(f"unknown factor {name!r}; known: {', '.join(FACTORS)}")
        lv = [x.strip() for x in levels.split(",") if x.strip()]
        bad = [x for x in lv if x not in FACTORS[name].levels]
        if bad or not lv:
            raise ValueError(f"factor {name}: unknown level(s) {bad or levels!r}; known: {FACTORS[name].level_names}")
        out[name] = lv
    return out


@dataclass(frozen=True)
class Cell:
    """A level of every factor."""

    levels: tuple[tuple[str, str], ...]

    @classmethod
    def of(cls, **levels: str) -> "Cell":
        full = {n: f.level_names[0] for n, f in FACTORS.items()}
        for k, v in levels.items():
            if k not in FACTORS or str(v) not in FACTORS[k].levels:
                raise ValueError(f"bad level {k}={v}")
            full[k] = str(v)
        return cls(tuple((n, full[n]) for n in FACTORS))

    def get(self, name: str) -> str:
        return dict(self.levels)[name]

    def setting(self, name: str) -> Any:
        return FACTORS[name].levels[self.get(name)]

    @property
    def code(self) -> str:
        """A readable id, e.g. ``i4-opp_high-zopa_narrow-hidden-deceptive-tight``."""
        d = dict(self.levels)
        return "-".join([f"i{d['issues']}", f"opp_{d['opposition']}", f"zopa_{d['zopa']}",
                         "hidden" if d["constraint"] == "hidden" else "free", d["deception"],
                         d["time_pressure"]])

    def as_dict(self) -> dict[str, str]:
        return dict(self.levels)


def all_cells(levels: dict[str, list[str]] | None = None) -> list[Cell]:
    """The full factorial (restricted to ``levels`` where given)."""
    levels = levels or {}
    names = list(FACTORS)
    choices = [levels.get(n) or FACTORS[n].level_names for n in names]
    return [Cell(tuple(zip(names, combo))) for combo in itertools.product(*choices)]


def sample_cells(n: int, levels: dict[str, list[str]] | None = None, seed: int | str = 0,
                 iterations: int = 30000) -> list[Cell]:
    """``n`` cells, balanced: whole copies of the full factorial first, then
    distinct cells chosen so that every level of every factor, and every pair
    of levels of two factors, appears as evenly as possible (a local search
    that swaps cells in and out, by simulated annealing, minimising the squared
    deviation of the level counts, then of the pair counts, from perfectly even)."""
    cells = all_cells(levels)
    rng = random.Random(f"sample:{seed}")
    out: list[Cell] = []
    for _ in range(n // len(cells)):
        block = list(cells)
        rng.shuffle(block)
        out.extend(block)
    rest = n - len(out)
    if rest <= 0:
        return out
    names = [k for k, _ in cells[0].levels]
    nlev = {k: len({c.get(k) for c in cells}) for k in names}
    # every level and every pair of levels, with its weight and its perfectly even count
    target: dict[tuple, tuple[float, float]] = {}
    for c in cells:
        for x in c.levels:
            target[x] = (8.0, rest / nlev[x[0]])
        for a, b in itertools.combinations(c.levels, 2):
            target[(a, b)] = (1.0, rest / (nlev[a[0]] * nlev[b[0]]))
    count = dict.fromkeys(target, 0)
    ckeys = {c: list(c.levels) + list(itertools.combinations(c.levels, 2)) for c in cells}

    def delta(a: Cell, b: Cell) -> float:
        """Change of the cost when ``a`` leaves and ``b`` joins."""
        d: dict[tuple, int] = {}
        for k in ckeys[a]:
            d[k] = d.get(k, 0) - 1
        for k in ckeys[b]:
            d[k] = d.get(k, 0) + 1
        out = 0.0
        for k, dv in d.items():
            if dv:
                w, t = target[k]
                v = count[k]
                out += w * ((v + dv - t) ** 2 - (v - t) ** 2)
        return out

    pool = list(cells)
    rng.shuffle(pool)
    chosen, spare = pool[:rest], pool[rest:]
    for c in chosen:
        for k in ckeys[c]:
            count[k] += 1
    steps = iterations if spare else 0
    for step in range(steps):
        i, j = rng.randrange(len(chosen)), rng.randrange(len(spare))
        a, b = chosen[i], spare[j]
        d = delta(a, b)
        temp = 6.0 * (1.0 - step / steps) ** 2 + 1e-3  # simulated annealing: worse swaps early, only better ones late
        if d <= 0 or rng.random() < math.exp(-d / temp):
            for k in ckeys[a]:
                count[k] -= 1
            for k in ckeys[b]:
                count[k] += 1
            chosen[i], spare[j] = b, a
    rng.shuffle(chosen)
    return out + chosen


# --------------------------------------------------------------------------- #
# The domain                                                                  #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _IssueDef:
    name: str
    lo: float
    hi: float
    fmt: str
    description: str
    buyer_up: bool  # does the buyer naturally want more of it?
    integer: bool = True


#: a supply contract between a Buyer (the participant) and a Supplier
ISSUES: tuple[_IssueDef, ...] = (
    _IssueDef("Price", 80, 120, "${:,} per unit", "The price per unit.", False),
    _IssueDef("Delivery", 1, 12, "{} weeks", "Weeks from signing to delivery.", False),
    _IssueDef("Warranty", 0, 36, "{} months", "How long the supplier repairs or replaces faulty units.", True),
    _IssueDef("Payment", 0, 90, "{} days", "Days the buyer has to pay after delivery.", True),
    _IssueDef("Quantity", 100, 1000, "{:,} units", "Units ordered.", True),
    _IssueDef("Penalty", 0, 10, "{}%", "Price reduction for every week of late delivery.", True),
)

#: options per issue, by number of issues (keeps every space big enough for a narrow ZOPA)
_OPTIONS = {1: 21, 2: 11, 3: 8, 4: 6, 5: 5, 6: 4}


def _values(d: _IssueDef, k: int) -> list[Any]:
    vs = np.linspace(d.lo, d.hi, k)
    out: list[Any] = []
    for v in vs:
        x = int(round(float(v))) if d.integer else round(float(v), 2)
        if x not in out:
            out.append(x)
    return out


def _curve(n: int, up: bool, rng: random.Random) -> np.ndarray:
    """A monotone value curve on [0, 1] with a random shape."""
    e = rng.uniform(0.6, 1.8)
    x = np.linspace(0.0, 1.0, n) ** e
    return x if up else x[::-1].copy()


@dataclass
class _Draw:
    issues: list[_IssueDef]
    values: list[list[Any]]
    tables: dict[str, list[np.ndarray]]  # role -> per-issue value arrays
    weights: dict[str, np.ndarray]


def _draw(n_issues: int, conflict: float, rng: random.Random) -> _Draw:
    issues = list(ISSUES[:n_issues])
    k = _OPTIONS.get(n_issues, 4)
    values = [_values(d, k) for d in issues]
    tb: list[np.ndarray] = []
    ts: list[np.ndarray] = []
    for d, vs in zip(issues, values):
        tb.append(_curve(len(vs), d.buyer_up, rng))
        opposed = rng.random() < conflict
        ts.append(_curve(len(vs), (not d.buyer_up) if opposed else d.buyer_up, rng))
    wb = np.array([rng.uniform(0.5, 3.0) for _ in issues])
    ws = np.array([rng.uniform(0.5, 3.0) for _ in issues])
    return _Draw(issues, values, {HUMAN_ROLE: tb, OPPONENT_ROLE: ts},
                 {HUMAN_ROLE: wb / wb.sum(), OPPONENT_ROLE: ws / ws.sum()})


def _utilities(tables: list[np.ndarray], w: np.ndarray) -> np.ndarray:
    """Utility of every outcome (cartesian order, last issue fastest)."""
    u = np.zeros([len(t) for t in tables])
    for k, t in enumerate(tables):
        shape = [1] * len(tables)
        shape[k] = len(t)
        u = u + w[k] * t.reshape(shape)
    return u.reshape(-1)


def opposition(ub: np.ndarray, us: np.ndarray) -> float:
    """negmas' opposition level over all outcomes (reservation values ignored): the
    smallest distance of an outcome to (1, 1)."""
    return float(np.min(np.sqrt((1.0 - ub) ** 2 + (1.0 - us) ** 2)))


def _zopa(ub: np.ndarray, us: np.ndarray, rb: float, rs: float) -> np.ndarray:
    return (ub >= rb) & (us >= rs)


def _fit_reserved(ub: np.ndarray, us: np.ndarray, band: tuple[float, float], min_deals: int) -> tuple[float, float] | None:
    """Reservation values (the same quantile of each side's utilities) that put
    the ZOPA share in ``band`` with at least ``min_deals`` deals."""
    target = math.sqrt(band[0] * band[1])
    okb, oks = np.sort(ub[ub >= 0]), np.sort(us)
    if okb.size == 0:
        return None
    lo, hi = 0.0, 0.999
    best = None
    for _ in range(40):
        q = (lo + hi) / 2
        rb, rs = float(np.quantile(okb, q)), float(np.quantile(oks, q))
        frac = float(_zopa(ub, us, rb, rs).mean())
        n = int(_zopa(ub, us, rb, rs).sum())
        if band[0] <= frac <= band[1] and n >= min_deals:
            best = (round(max(rb, 0.0), 4), round(max(rs, 0.0), 4))
            if abs(math.log(max(frac, 1e-9) / target)) < 0.15:
                break
        if frac > target:
            lo = q
        else:
            hi = q
    if best is None:
        return None
    # rounding may move an outcome across the line: re-check
    frac = float(_zopa(ub, us, *best).mean())
    return best if band[0] <= frac <= band[1] and int(_zopa(ub, us, *best).sum()) >= min_deals else None


def _nash(ub: np.ndarray, us: np.ndarray, rb: float, rs: float) -> int | None:
    z = np.flatnonzero(_zopa(ub, us, rb, rs))
    if z.size == 0:
        return None
    gain = (ub[z] - rb) * (us[z] - rs)
    return int(z[int(np.argmax(gain))])


def _fmt(d: _IssueDef, v: Any) -> str:
    try:
        return d.fmt.format(v)
    except (ValueError, TypeError, IndexError):
        return str(v)


# --------------------------------------------------------------------------- #
# Composing one scenario                                                      #
# --------------------------------------------------------------------------- #
@dataclass
class Composed:
    """A composed scenario (``None`` when no draw fit the cell) and what was measured."""

    cell: Cell
    scenario: Scenario | None
    measured: dict[str, Any] = field(default_factory=dict)
    tries: int = 0
    error: str = ""


MIN_DEALS = 3


def compose(cell: Cell, name: str, seed: int | str = 0, replicate: int = 0, max_tries: int = 400) -> Composed:
    """Compose the scenario of ``cell`` (outcome space named ``name``).

    Draws preferences until the opposition falls in its band (a conflict
    probability per issue is adapted on the way), adds the hidden constraint,
    then sets the reservation values so the ZOPA share falls in its band. The
    random draws come from ``(seed, cell, replicate)`` only."""
    rng = random.Random(f"compose:{seed}:{cell.code}:{replicate}")
    n_issues = int(cell.setting("issues"))
    olo, ohi = cell.setting("opposition")
    zband = cell.setting("zopa")
    hidden = bool(cell.setting("constraint"))
    conflict = {"low": 0.15, "medium": 0.55, "high": 0.95}.get(cell.get("opposition"), 0.5)
    last_err = "no draw"
    for attempt in range(1, max_tries + 1):
        d = _draw(n_issues, conflict, rng)
        ub = _utilities(d.tables[HUMAN_ROLE], d.weights[HUMAN_ROLE])
        us = _utilities(d.tables[OPPONENT_ROLE], d.weights[OPPONENT_ROLE])
        opp = opposition(ub, us)
        if not olo <= opp <= ohi:
            step = 0.04 * rng.random()
            conflict = min(1.0, conflict + step) if opp < olo else max(0.0, conflict - step)
            last_err = f"opposition {opp:.3f} outside [{olo}, {ohi}]"
            continue
        constraint = None
        tb = [t.copy() for t in d.tables[HUMAN_ROLE]]
        if hidden:
            ws = d.weights[OPPONENT_ROLE]
            j = int(np.argmax(ws))
            fav = int(np.argmax(d.tables[OPPONENT_ROLE][j]))
            wj = float(d.weights[HUMAN_ROLE][j])
            k = (1.0 - wj) / max(wj, 1e-6) + 0.5
            original = float(tb[j][fav])
            tb[j][fav] = -k  # any deal with it is worth less than 0 (<= every reservation value)
            constraint = dict(issue=d.issues[j].name, value=d.values[j][fav], original_value=round(original, 4),
                              text=_fmt(d.issues[j], d.values[j][fav]))
            ub = _utilities(tb, d.weights[HUMAN_ROLE])
        res = _fit_reserved(ub, us, zband, MIN_DEALS)
        if res is None:
            last_err = f"no reservation values give a ZOPA share in {zband}"
            continue
        rb, rs = res
        t = _nash(ub, us, rb, rs)
        if t is None:
            last_err = "empty ZOPA"
            continue
        scenario = _build(d, tb, rb, rs, name, cell, constraint)
        outcomes = list(itertools.product(*d.values))
        z = _zopa(ub, us, rb, rs)
        measured = dict(opposition=round(opp, 4), zopa_fraction=round(float(z.mean()), 4), zopa_deals=int(z.sum()),
                        n_outcomes=len(outcomes), reserved={HUMAN_ROLE: rb, OPPONENT_ROLE: rs})
        target = dict(outcome={i.name: v for i, v in zip(d.issues, outcomes[t])},
                      human_utility=round(float(ub[t]), 4), opponent_utility=round(float(us[t]), 4),
                      definition="Nash bargaining solution over the ZOPA (respecting the constraint)")
        comp = scenario.info["composition"]
        comp.update(measured=measured, target=target)
        if constraint:
            comp["constraint"] = constraint
        return Composed(cell, scenario, measured, attempt)
    return Composed(cell, None, {}, max_tries, last_err)


def _build(d: _Draw, human_tables: list[np.ndarray], rb: float, rs: float, name: str, cell: Cell,
           constraint: dict | None) -> Scenario:
    issues = [make_issue(list(vs), name=i.name) for i, vs in zip(d.issues, d.values)]
    os_ = make_os(issues, name=name)
    ufuns = []
    for role, tables, r in ((HUMAN_ROLE, human_tables, rb), (OPPONENT_ROLE, d.tables[OPPONENT_ROLE], rs)):
        fns = tuple(TableFun({v: round(float(x), 4) for v, x in zip(vs, t)}) for vs, t in zip(d.values, tables))
        ufuns.append(LinearAdditiveUtilityFunction(fns, weights=tuple(round(float(w), 4) for w in d.weights[role]),
                                                   reserved_value=r, name=role, id=role, outcome_space=os_))
    episode = {"opponent": cell.setting("deception"), "n_steps": int(cell.setting("time_pressure"))}
    hints: dict[str, dict[str, Any]] = {
        HUMAN_ROLE: {"Your role": "Buyer: you are buying a batch of parts for your production line."},
        OPPONENT_ROLE: {"Your role": "Supplier: you make the parts and want a profitable, workable contract."},
    }
    if constraint:
        hints[HUMAN_ROLE]["Hard limit (private)"] = (
            f"A deal with {constraint['issue']} = {constraint['text']} is worse for you than no deal at all. "
            "Your opponent does not know this.")
    rounds = episode["n_steps"]
    long = (
        "**The Domain** A buyer and a supplier negotiate a supply contract: "
        + ", ".join(i.name.lower() for i in d.issues) + "."
        + f"\n\n**The Roles**\n\n- **{HUMAN_ROLE}**: buys the parts.\n- **{OPPONENT_ROLE}**: makes and sells them."
        + "\n\n**Utility Function** Every option of every issue has a value for you, and some issues matter more "
          "to you than others. You can see your preferences in the *Preferences* pane."
        + "\n\n**Opponent Utility Function** Your opponent has their own values and priorities, which you do not know."
        + "\n\n**Value on Disagreement (Reservation Value)** Without a deal both sides walk away; your reservation "
          "value is the utility you get then. Your opponent has one too, which you do not know."
        + f"\n\n**Deadline** The negotiation ends without a deal after {rounds} rounds."
    )
    info = {
        "Name": name,
        "title": "Supply contract",
        "short_description": "A buyer and a supplier negotiate a supply contract.",
        "long_description": long,
        "issue_description": {i.name: i.description for i in d.issues},
        "issue_format": {i.name: i.fmt for i in d.issues},
        "role_descriptions": {HUMAN_ROLE: "buys the parts", OPPONENT_ROLE: "makes and sells the parts"},
        "human_role": HUMAN_ROLE,
        "n_issue_columns": 2,
        "hints": hints,
        "composition": {"cell": cell.as_dict(), "code": cell.code, "episode": episode},
    }
    scenario = Scenario(outcome_space=os_, ufuns=tuple(ufuns), info=info)
    from hani2.scenarios.story import fill_hints

    return fill_hints(scenario)


# --------------------------------------------------------------------------- #
# Verification                                                                #
# --------------------------------------------------------------------------- #
@dataclass
class Verification:
    ok: bool
    checks: dict[str, bool]
    problems: list[str]
    measured: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return dict(ok=self.ok, checks=self.checks, problems=self.problems, measured=self.measured)


def _scenario_utils(scenario: Scenario, hi: int, oi: int):
    outcomes = list(scenario.outcome_space.enumerate_or_sample(max_cardinality=200_000))
    uh, uo = cast(Any, scenario.ufuns[hi]), cast(Any, scenario.ufuns[oi])
    ub = np.array([float(uh(o)) for o in outcomes])
    us = np.array([float(uo(o)) for o in outcomes])
    return outcomes, ub, us


def verify(scenario: Scenario) -> Verification:
    """Check a composed scenario (best: as reloaded from disk) against its cell."""
    from hani2.scenario_store import assign_human

    info = scenario.info or {}
    comp = info.get("composition") or {}
    problems: list[str] = []
    checks: dict[str, bool] = {}
    if not comp.get("cell"):
        return Verification(False, {"composition": False}, ["no composition info"], {})
    cell = Cell.of(**comp["cell"])
    hi = assign_human(scenario, "auto", 1)
    oi = 1 - hi
    checks["human_side"] = str(scenario.ufuns[hi].name) == HUMAN_ROLE
    outcomes, ub, us = _scenario_utils(scenario, hi, oi)
    rb = float(scenario.ufuns[hi].reserved_value)
    rs = float(scenario.ufuns[oi].reserved_value)
    n_issues = len(scenario.outcome_space.issues)
    checks["issues"] = n_issues == int(cell.setting("issues"))

    # opposition is a property of the preferences without the hard limit
    cons = comp.get("constraint")
    ub_free = ub
    if cons:
        u = cast(Any, copy.deepcopy(scenario.ufuns[hi]))
        names = [i.name for i in scenario.outcome_space.issues]
        j = names.index(cons["issue"])
        u.values[j].mapping[cons["value"]] = float(cons["original_value"])
        ub_free = np.array([float(u(o)) for o in outcomes])
    opp = opposition(ub_free, us)
    olo, ohi = cell.setting("opposition")
    checks["opposition"] = olo - 1e-6 <= opp <= ohi + 1e-6
    z = _zopa(ub, us, rb, rs)
    zlo, zhi = cell.setting("zopa")
    frac = float(z.mean())
    checks["zopa_nonempty"] = int(z.sum()) >= MIN_DEALS
    checks["zopa"] = zlo - 1e-9 <= frac <= zhi + 1e-9
    t = _nash(ub, us, rb, rs)
    target = comp.get("target") or {}
    reach = t is not None
    if reach and target.get("outcome"):
        names = [i.name for i in scenario.outcome_space.issues]
        tout = tuple(target["outcome"].get(n) for n in names)
        try:
            k = outcomes.index(tout)
        except ValueError:
            k = None
        reach = (k is not None and bool(z[k]) and abs(float(ub[k]) - float(target["human_utility"])) < 1e-3
                 and abs((ub[k] - rb) * (us[k] - rs) - (ub[t] - rb) * (us[t] - rs)) < 1e-6)
    checks["target_reachable"] = reach
    ep = comp.get("episode") or {}
    if reach and target.get("outcome"):
        checks["target_reached_in_play"] = _target_in_play(scenario, hi, tout, float(target["human_utility"]), ep)
    if bool(cell.setting("constraint")):
        ok = bool(cons)
        if ok:
            names = [i.name for i in scenario.outcome_space.issues]
            j = names.index(cons["issue"])
            viol = np.array([o[j] == cons["value"] for o in outcomes])
            ok = bool(np.all(ub[viol] < rb)) and bool(viol[int(np.argmax(us))])  # bites: the opponent's ideal breaks it
        checks["constraint_bites"] = ok
    else:
        checks["constraint_bites"] = not cons
    try:
        from hani2.agents import get_agent_type

        get_agent_type(ep.get("opponent"))
        checks["episode"] = int(ep.get("n_steps") or 0) > 0
    except Exception:  # noqa: BLE001
        checks["episode"] = False
    names_ = {"human_side": f"the participant does not play {HUMAN_ROLE}",
              "issues": f"{n_issues} issues, not {cell.get('issues')}",
              "opposition": f"opposition {opp:.3f} outside [{olo}, {ohi}]",
              "zopa_nonempty": f"only {int(z.sum())} deals in the ZOPA",
              "zopa": f"ZOPA share {frac:.3f} outside [{zlo}, {zhi}]",
              "target_reachable": "the target deal is not the Nash point of the ZOPA",
              "target_reached_in_play": "a participant insisting on the target gets no deal from the opponent "
                                        "within the step limit",
              "constraint_bites": "the hidden constraint is missing, harmless or unexpected",
              "episode": f"bad episode settings {ep}"}
    problems = [names_[k] for k, v in checks.items() if not v]
    measured = dict(opposition=round(opp, 4), zopa_fraction=round(frac, 4), zopa_deals=int(z.sum()),
                    n_outcomes=len(outcomes))
    return Verification(not problems, checks, problems, measured)


class _TargetSeat:
    """Plays the participant's seat by insisting on the target: it offers the
    target every turn and accepts only deals at least as good for it."""

    def __new__(cls, target: tuple, floor: float, ufun):
        from negmas.gb.common import ResponseType
        from negmas.sao import SAONegotiator

        class Seat(SAONegotiator):
            def propose(self, state, dest=None):
                return target

            def respond(self, state, source=None):
                o = state.current_offer
                return (ResponseType.ACCEPT_OFFER if o is not None and float(cast(Any, ufun)(o)) >= floor - 1e-9
                        else ResponseType.REJECT_OFFER)

        return Seat(name="target-seat")


def _target_in_play(scenario: Scenario, hi: int, target: tuple, target_u: float, episode: dict) -> bool:
    """Does a participant who insists on the target get a deal from the episode's
    opponent within its step limit (as a session runs it: one offer per step,
    either side moving first)?"""
    from negmas.sao import SAOMechanism

    from hani2.agents import get_agent_type

    try:
        opp_cls = cast(Any, get_agent_type(episode.get("opponent")))
    except Exception:  # noqa: BLE001
        return False
    n = int(episode.get("n_steps") or 0)
    if n <= 0:
        return False
    for first_human in (True, False):
        m = SAOMechanism(outcome_space=scenario.outcome_space, n_steps=n, one_offer_per_step=True)
        seat = _TargetSeat(target, target_u, scenario.ufuns[hi])
        opp = opp_cls(name="opponent")
        order = [(seat, scenario.ufuns[hi]), (opp, scenario.ufuns[1 - hi])]
        if not first_human:
            order.reverse()
        for neg, u in order:
            m.add(neg, ufun=copy.deepcopy(u))
        m.run()
        if m.agreement is None:
            return False
    return True


# --------------------------------------------------------------------------- #
# Pools                                                                       #
# --------------------------------------------------------------------------- #
MANIFEST = "_composition.json"


def generate_pool(base: Path | str, n: int, levels: dict[str, list[str]] | None = None, seed: int | str = 0,
                  category: str = CATEGORY, force: bool = False, log=print) -> dict[str, Any]:
    """Generate a balanced pool of ``n`` verified scenarios under ``base/category``.

    Every cell is composed, saved, reloaded and verified; a cell that cannot be
    composed or fails verification is reported in the manifest
    (``_composition.json``) and left out of the pool, never silently dropped."""
    from hani2.scenario_store import _load_dir, save_scenario

    folder = Path(base).expanduser() / category
    folder.mkdir(parents=True, exist_ok=True)
    old = pool_scenarios(folder)
    if old and not force:
        raise FileExistsError(f"{folder} already holds {len(old)} scenarios: a new set would mix with them "
                              "(use another category or force=True to replace them)")
    if force:
        import shutil

        for p in old:
            shutil.rmtree(p)
    cells = sample_cells(n, levels, seed)
    reps: dict[str, int] = {}
    entries, failed = [], []
    for idx, cell in enumerate(cells):
        rep = reps.get(cell.code, 0)
        reps[cell.code] = rep + 1
        # an opaque name: the scenario name is shown in the browser, so it must not give the cell away
        name = f"{idx:04d}{category}"
        c = compose(cell, name, seed, rep)
        if c.scenario is None:
            failed.append(dict(index=idx, cell=cell.as_dict(), code=cell.code, reason=c.error, tries=c.tries))
            log(f"  [{idx:04d}] {cell.code}: INFEASIBLE ({c.error})")
            continue
        out = folder / name
        save_scenario(c.scenario, out)
        back = _load_dir(out)
        v = verify(back) if back is not None else Verification(False, {"reload": False}, ["cannot reload"], {})
        if not v.ok:
            import shutil

            shutil.rmtree(out, ignore_errors=True)
            failed.append(dict(index=idx, cell=cell.as_dict(), code=cell.code, reason="; ".join(v.problems)))
            log(f"  [{idx:04d}] {cell.code}: FAILED VERIFICATION ({'; '.join(v.problems)})")
            continue
        entries.append(dict(name=name, cell=cell.as_dict(), code=cell.code, tries=c.tries, measured=v.measured,
                            target=c.scenario.info["composition"]["target"]))
        log(f"  [{idx:04d}] {name} opp={v.measured['opposition']:.3f} zopa={v.measured['zopa_fraction']:.3f} "
            f"({v.measured['zopa_deals']} deals) tries={c.tries}")
    manifest = dict(category=category, seed=seed, requested=n, levels=levels or {}, scenarios=entries,
                    failed=failed, factors={k: dict(kind=f.kind, levels=f.level_names) for k, f in FACTORS.items()})
    (folder / MANIFEST).write_text(json.dumps(manifest, indent=1, default=str))
    return manifest


def pool_scenarios(folder: Path | str) -> list[Path]:
    folder = Path(folder).expanduser()
    return sorted(p for p in folder.iterdir() if p.is_dir() and any(p.glob("_info.y*ml")))


def run_pool(folder: Path | str, home: Path | str, *, driver: str = "Assistant", agent_class: str | None = None,
             assistant_settings: dict[str, Any] | None = None, repeats: int = 1, timeout: float = 600.0,
             limit: int | None = None, log=print) -> list[dict[str, Any]]:
    """Play every scenario of a pool with ``driver`` in the participant's seat.

    ``driver`` is ``"Assistant"`` (the configured Assistant decides every
    turn, through the autopilot) or a negotiator class name (a baseline that
    needs no language model). The opponent and the step limit come from each
    scenario's episode factors. Every negotiation is recorded under
    ``home`` (``hani2 compose report <home>`` evaluates them)."""
    import os

    folder = Path(folder).expanduser().resolve()
    home = Path(home).expanduser().resolve()
    home.mkdir(parents=True, exist_ok=True)
    settings = home / "settings"
    settings.mkdir(parents=True, exist_ok=True)
    (settings / "autopilot_settings.json").write_text(json.dumps(
        {"allowed": True, "driver": driver, "allowed_drivers": None, "step_delay": 0}))
    old_env = {k: os.environ.get(k) for k in ("HANI2_SCENARIOS_BASE", "HANI2_HOME")}
    os.environ["HANI2_SCENARIOS_BASE"] = str(folder.parent)
    try:
        return _run(folder, home, agent_class, assistant_settings, repeats, timeout, limit, log)
    finally:
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _run(folder: Path, home: Path, agent_class, assistant_settings, repeats: int, timeout: float,
         limit: int | None, log) -> list[dict[str, Any]]:
    from hani2.scenario_store import _read_info
    from hani2.testing import make_session

    category = folder.name
    out = []
    scenarios = pool_scenarios(folder)[:limit] if limit else pool_scenarios(folder)
    for path in scenarios:
        ep = ((_read_info(path).get("composition") or {}).get("episode")) or {}
        for rep in range(repeats):
            s = make_session(user=f"compose-{rep}", home=str(home), opponent=ep.get("opponent"),
                             n_steps=int(ep.get("n_steps") or 20), agent_class=agent_class,
                             assistant_settings=assistant_settings, load=False, is_admin=False)
            s.load(category, name=path.name)
            s.start()
            s.wait_for_turn(timeout=60)
            r = s.set_autopilot(True)
            if not r.get("ok"):
                raise RuntimeError(f"cannot start the autopilot: {r}")
            done = s.wait_until_done(timeout=timeout)
            if not done:  # end it, so the failure is recorded as a no-deal and counts in the report
                s.set_autopilot(False)
                s.wait_for_turn(timeout=30)
                s.end()
                s.wait_until_done(timeout=30)
            res = dict(s.result or {})
            out.append(dict(scenario=path.name, repeat=rep, done=done, timed_out=not done,
                            agreement=res.get("agreement") is not None, human_utility=res.get("human_utility")))
            log(f"  {path.name} #{rep}: {'deal' if res.get('agreement') else 'no deal'} "
                f"u={res.get('human_utility')}" + ("" if done else " (timed out)"))
            try:
                if s.recorder is not None:
                    s.recorder.finalize()
            except Exception:  # noqa: BLE001
                pass
            try:
                s.close()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
    return out


# --------------------------------------------------------------------------- #
# Reporting                                                                   #
# --------------------------------------------------------------------------- #
#: (column, title, higher is better)
REPORT_COLUMNS: tuple[tuple[str, str, bool], ...] = (
    ("target_attainment", "Target attainment", True),
    ("agreement", "Agreement rate", True),
    ("human_advantage", "Human advantage", True),
    ("constraint_violated", "Constraint violated", False),
)


def _stats(vals: Sequence[float]) -> dict[str, Any]:
    n = len(vals)
    if not n:
        return dict(n=0, mean=None, se=None)
    m = float(np.mean(vals))
    se = float(np.std(vals, ddof=1) / math.sqrt(n)) if n > 1 else None
    return dict(n=n, mean=m, se=se)


def factor_report(rows: list[dict], by: str | None = None,
                  columns: Sequence[tuple[str, str, bool]] = REPORT_COLUMNS) -> dict[str, Any]:
    """Scores per factor level (rows from :func:`hani2.evaluation.evaluate_paths`
    with the ``factors`` metric), optionally separately for each value of ``by``
    (e.g. ``support_agent`` or ``label``).

    For each factor and column: per level ``n``, ``mean`` and standard error,
    and the *effect*: the mean at the hardest level minus the mean at the
    easiest (levels are ordered easiest first), with its standard error.
    Factors are ranked by how much they lower target attainment; ``failures``
    lists those whose drop is larger than twice its standard error (where the
    Assistant reliably fails)."""
    rows = [r for r in rows if r.get("factor_issues") is not None]
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(str(r.get(by)) if by else "all", []).append(r)
    out: dict[str, Any] = {"by": by, "groups": {}}
    for g, rs in groups.items():
        per: dict[str, Any] = {}
        for fname, f in FACTORS.items():
            col = f"factor_{fname}"
            present = [lv for lv in f.level_names if any(str(r.get(col)) == lv for r in rs)]
            others = sorted({str(r.get(col)) for r in rs} - set(f.level_names) - {"None"})
            levels = present + others
            entry: dict[str, Any] = {"levels": {}, "effects": {}}
            lvls: dict[str, dict[str, Any]] = entry["levels"]
            for lv in levels:
                sub = [r for r in rs if str(r.get(col)) == lv]
                entry["levels"][lv] = {c: _stats([float(r[c]) for r in sub if _num(r.get(c))]) for c, _, _ in columns}
                entry["levels"][lv]["n"] = len(sub)
            entry["effect_se"] = {}
            if len(present) >= 2:
                for c, _, _ in columns:
                    a, b = lvls[present[0]][c], lvls[present[-1]][c]
                    entry["effects"][c] = None if a["mean"] is None or b["mean"] is None else b["mean"] - a["mean"]
                    entry["effect_se"][c] = (math.sqrt(a["se"] ** 2 + b["se"] ** 2)
                                             if a["se"] is not None and b["se"] is not None else None)
            per[fname] = entry
        main = columns[0][0]
        ranked = sorted((k for k in per if per[k]["effects"].get(main) is not None),
                        key=lambda k: per[k]["effects"][main])
        failures = [k for k in ranked if per[k]["effects"][main] < 0 and per[k]["effect_se"].get(main) is not None
                    and per[k]["effects"][main] < -2 * per[k]["effect_se"][main]]
        out["groups"][g] = dict(n=len(rs), overall={c: _stats([float(r[c]) for r in rs if _num(r.get(c))])
                                                    for c, _, _ in columns},
                                factors=per, ranking=ranked, failures=failures)
    return out


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def format_report(report: dict[str, Any], columns: Sequence[tuple[str, str, bool]] = REPORT_COLUMNS) -> str:
    """The report as Markdown."""

    def f(x: Any, se: Any = None) -> str:
        if x is None:
            return "–"
        s = f"{x:.3f}"
        return s + (f" ± {se:.3f}" if se is not None else "")

    lines: list[str] = []
    for g, rep in report["groups"].items():
        lines.append(f"## {g if report.get('by') else 'All runs'} ({rep['n']} negotiations)\n")
        lines.append("| | " + " | ".join(t for _, t, _ in columns) + " |")
        lines.append("|---|" + "---|" * len(columns))
        lines.append("| **overall** | " + " | ".join(f(rep["overall"][c]["mean"], rep["overall"][c]["se"])
                                                   for c, _, _ in columns) + " |")
        for fname in FACTORS:
            e = rep["factors"].get(fname)
            if not e or not e["levels"]:
                continue
            for lv, st in e["levels"].items():
                lines.append(f"| {fname} = {lv} (n={st['n']}) | "
                             + " | ".join(f(st[c]["mean"], st[c]["se"]) for c, _, _ in columns) + " |")
            if e["effects"]:
                def _eff(c: str) -> str:
                    v, se = e["effects"].get(c), e["effect_se"].get(c)
                    return "–" if v is None else f"{v:+.3f}" + (f" ± {se:.3f}" if se is not None else "")

                lines.append(f"| *{fname}: effect* | " + " | ".join(_eff(c) for c, _, _ in columns) + " |")
        if rep["ranking"]:
            main = columns[0][1].lower()
            worst = rep["ranking"][0]
            eff = rep["factors"][worst]["effects"][columns[0][0]]
            lines.append("")
            lines.append(f"**Where it fails:** factors ranked by their effect on {main} (hardest − easiest level): "
                         + ", ".join(f"{k} ({rep['factors'][k]['effects'][columns[0][0]]:+.3f})"
                                     for k in rep["ranking"]) + ".")
            if rep["failures"]:
                lines.append("Drops larger than twice their standard error: "
                             + ", ".join(f"**{k}**" for k in rep["failures"]) + ".")
            elif eff is not None and eff < 0:
                lines.append(f"The largest drop ({worst}) is within twice its standard error: run more "
                             "scenarios or repeats before reading it as a weakness.")
        lines.append("")
    return "\n".join(lines)
