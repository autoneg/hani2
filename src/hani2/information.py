"""Who knows what: splitting information between the human and the Assistant.

By default the human and the Assistant see the same kind of information: the
human's preferences, the scenario and the negotiation so far. The ``information``
setting (``env.json`` → ``negotiation`` → ``information``, or ``information`` in
``project.yaml`` / ``study.yaml``) gives each of them a different share so that
they must work together:

``past_negotiations``
    Records of earlier negotiations in the same scenario, between parties whose
    preferences are similar to (or the same as, or different from) this
    negotiation's. Some go to the human and the rest to the Assistant.
``preferences``
    Which part of the human's utility function each of them knows (``full``,
    ``weights``, ``values`` or ``none``) and who knows the value on
    disagreement.
``market_research``
    Statistics about how preferences in this scenario are usually distributed
    (and any text the scenario author wrote under ``market_research`` in
    ``_info.yaml``), for the Assistant, the human, both or neither.
``briefing``
    Private instructions for one side, such as a constraint that is not in the
    utility function ("your manager will not approve a rent above 3200"). They
    come from the scenario's ``_info.yaml`` and from the setting; a structured
    ``constraints`` list is checked against the agreement (``constraints_met``).
``control``
    Issues only the human may set and actions (send, accept, end) only the human
    may take: the Assistant can only suggest them.

A scenario folder may ship its own past negotiations in
``_past_negotiations.yaml``; otherwise they are simulated when the scenario is
loaded (deterministically, from the scenario's name, so every participant of a
strict study meets the same records).

:func:`build_state` turns the settings into an :class:`InformationState` for one
round; the session keeps it as ``session.information`` and uses it to decide
what the browser and the Assistant are shown.
"""

from __future__ import annotations

import copy
import json
import math
import random
import threading
import traceback
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np

__all__ = [
    "DEFAULTS",
    "ACTIONS",
    "check_constraints",
    "constraint_text",
    "PARTS",
    "PAST_FILE",
    "InformationState",
    "resolve_settings",
    "build_state",
    "load_past_file",
    "write_past_file",
    "simulate_past_negotiations",
    "perturb_ufun",
    "market_research",
    "preference_part",
]

#: keys of a scenario's ``_info.yaml`` that are private (taken out of the scenario once resolved)
PRIVATE_INFO_KEYS = ("briefing", "market_research")
#: the file in a scenario folder that holds its past negotiations
PAST_FILE = "_past_negotiations.yaml"
#: what a party may know of the human's preferences
PARTS = ("full", "weights", "values", "none")
AUDIENCES = ("human", "assistant", "both", "none")
PREFERENCE_MODES = ("similar", "same", "different")
#: actions that can be kept for the human (``control.human_only_actions``)
ACTIONS = ("send", "accept", "end")
DEFAULT_NEGOTIATORS = ["BoulwareTBNegotiator", "LinearTBNegotiator", "ConcederTBNegotiator",
                       "NaiveTitForTatNegotiator"]

#: The defaults: the human and the Assistant know the same things (nothing is split).
DEFAULTS: dict[str, Any] = {
    "past_negotiations": {
        # how many past negotiations exist for every scenario (0: none)
        "count": 0,
        # how the past parties' preferences relate to this negotiation's: similar | same | different
        "preferences": "similar",
        # the same for the opponent's side only (None: as "preferences")
        "opponent_preferences": None,
        # how far "similar" preferences move (0: the same, 1: very different)
        "noise": 0.25,
        # the share the human gets (0: all go to the Assistant, 1: all to the human)
        "human_share": 0.5,
        # give every record to both (the share is then ignored)
        "shared": False,
        # which share goes to whom: random (per participant and round) | first (the human gets the first ones)
        "assignment": "random",
        # whose utilities a record shows: own (the party in the human's role) | both | none
        "utilities": "own",
        # rounds of a simulated negotiation, and the negmas negotiators that play them
        "n_steps": 20,
        "negotiators": list(DEFAULT_NEGOTIATORS),
        # the past negotiations of a scenario folder's _past_negotiations.yaml are used when it has one
        "use_scenario_file": True,
        # extra seed for the simulation (the scenario's name is always part of it)
        "seed": 0,
    },
    "preferences": {
        # what the human knows of their own utility function: full | weights | values | none
        "human": "full",
        # what the Assistant knows of it
        "assistant": "full",
        # who knows the value on disagreement: both | human | assistant | none
        "reserved_value": "both",
        # show deal values (utilities) to a party that knows only part of the preferences
        "show_totals_to_partial": False,
    },
    # private instructions (see _briefings); added to the scenario's own _info.yaml "briefing"
    "briefing": [],
    # use the briefing of the scenario's _info.yaml
    "use_scenario_briefing": True,
    # give every scenario briefing to this side instead of the one it names: human | assistant | both (None: as written)
    "briefing_audience": None,
    "control": {
        # issues only the human may set: the Assistant may only suggest values for them
        "human_only_issues": [],
        # actions only the human may take: any of send, accept, end
        "human_only_actions": [],
    },
    "market_research": {
        # who gets it: none | assistant | human | both
        "audience": "none",
        # whose preferences it describes: opponent | own | both
        "sides": "opponent",
        # how many plausible preference profiles it is computed from, and how spread out they are
        "samples": 40,
        "noise": 0.3,
    },
}


def _deep_merge(base: dict, over: dict | None) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def resolve_settings(raw: dict | None) -> dict:
    """The full ``information`` settings: :data:`DEFAULTS` with ``raw`` merged in
    and every value checked (an unknown value falls back to its default)."""
    s = _deep_merge(DEFAULTS, raw if isinstance(raw, dict) else {})
    p, pr, mr = s["past_negotiations"], s["preferences"], s["market_research"]
    try:
        p["count"] = max(0, int(p.get("count") or 0))
    except (TypeError, ValueError):
        p["count"] = 0
    for key in ("preferences", "opponent_preferences"):
        if p.get(key) is not None and p[key] not in PREFERENCE_MODES:
            p[key] = DEFAULTS["past_negotiations"].get(key)
    p["noise"] = _clamp(p.get("noise"), 0.0, 1.0, DEFAULTS["past_negotiations"]["noise"])
    p["human_share"] = _clamp(p.get("human_share"), 0.0, 1.0, 0.5)
    if p.get("utilities") not in ("own", "both", "none"):
        p["utilities"] = "own"
    if p.get("assignment") not in ("random", "first"):
        p["assignment"] = "random"
    try:
        p["n_steps"] = max(2, min(500, int(p.get("n_steps") or 20)))
    except (TypeError, ValueError):
        p["n_steps"] = 20
    if not isinstance(p.get("negotiators"), list) or not p["negotiators"]:
        p["negotiators"] = list(DEFAULT_NEGOTIATORS)
    for key in ("human", "assistant"):
        if pr.get(key) not in PARTS:
            pr[key] = "full"
    if pr.get("reserved_value") not in AUDIENCES:
        pr["reserved_value"] = "both"
    if mr.get("audience") not in AUDIENCES:
        mr["audience"] = "none"
    if mr.get("sides") not in ("opponent", "own", "both"):
        mr["sides"] = "opponent"
    try:
        mr["samples"] = max(2, min(500, int(mr.get("samples") or 40)))
    except (TypeError, ValueError):
        mr["samples"] = 40
    mr["noise"] = _clamp(mr.get("noise"), 0.0, 1.0, 0.3)
    if not isinstance(s.get("briefing"), (list, dict, str)):
        s["briefing"] = []
    if s.get("briefing_audience") not in (None, "human", "assistant", "both"):
        s["briefing_audience"] = None
    ctl = s["control"] if isinstance(s.get("control"), dict) else {}
    ctl["human_only_issues"] = [str(x) for x in (ctl.get("human_only_issues") or []) if str(x).strip()]
    ctl["human_only_actions"] = [a for a in (str(x).lower() for x in (ctl.get("human_only_actions") or []))
                                 if a in ACTIONS]
    s["control"] = ctl
    return s


def _clamp(v: Any, lo: float, hi: float, default: float) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(x) else max(lo, min(hi, x))


def _gets(audience: str, who: str) -> bool:
    return audience == "both" or audience == who


def stable_seed(*parts: Any) -> int:
    """A seed that is the same in every process (unlike ``hash``)."""
    return zlib.crc32("|".join(str(p) for p in parts).encode())


# --------------------------------------------------------------------------- #
# Preferences: parts, perturbations                                           #
# --------------------------------------------------------------------------- #
def is_additive(ufun: Any) -> bool:
    """Whether ``ufun`` is a weighted sum of one value function per issue (so its
    weights and its value functions can be told apart)."""
    try:
        from negmas.preferences import LinearAdditiveUtilityFunction

        if not isinstance(ufun, LinearAdditiveUtilityFunction):
            return False
        issues = ufun.outcome_space.issues  # type: ignore[union-attr]
        return len(ufun.values) == len(issues) == len(ufun.weights)
    except Exception:  # noqa: BLE001
        return False


def _jsonable(v: Any) -> Any:
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    return v


def _issue_points(issue: Any, n: int = 6) -> list:
    """The values of a discrete issue, or ``n`` evenly spaced points of a continuous one."""
    try:
        if issue.is_discrete():
            return list(issue.all)
    except Exception:  # noqa: BLE001
        pass
    lo, hi = float(issue.min_value), float(issue.max_value)
    return [lo + (hi - lo) * k / (n - 1) for k in range(n)]


def preference_part(ufun: Any, part: str, *, digits: int = 3) -> dict[str, Any]:
    """The part ``part`` (``weights`` / ``values`` / ``full``) of an additive
    utility function as plain data: ``{"weights": {issue: w}, "values": {issue:
    {value: v}}}``. A non-additive function gives ``{"utility": "not additive"}``."""
    out: dict[str, Any] = {}
    if part == "none" or ufun is None:
        return out
    if not is_additive(ufun):
        return {"note": "these preferences are not a weighted sum of issue values; only the full function exists"}
    issues = list(ufun.outcome_space.issues)
    if part in ("weights", "full"):
        out["weights"] = {str(i.name): round(float(w), digits) for i, w in zip(issues, ufun.weights)}
    if part in ("values", "full"):
        vals: dict[str, Any] = {}
        for i, fn in zip(issues, ufun.values):
            row = {}
            for x in _issue_points(i):
                try:
                    row[str(_jsonable(x))] = round(float(fn(x)), digits)
                except Exception:  # noqa: BLE001
                    continue
            vals[str(i.name)] = row
        out["values"] = vals
    return out


def _value_table(fn: Any, points: list) -> np.ndarray:
    return np.array([float(fn(x)) for x in points], dtype=float)


def perturb_ufun(ufun: Any, mode: str, noise: float, rng: np.random.Generator) -> Any:
    """A utility function related to ``ufun``: the same one (``same``), a nearby
    one (``similar``: weights, option values and value on disagreement moved by
    about ``noise``) or an unrelated random one over the same outcome space
    (``different``). Uses ``rng`` only (never the global random state)."""
    from negmas.preferences import LinearAdditiveUtilityFunction, MappingUtilityFunction
    from negmas.preferences.value_fun import TableFun

    if mode == "same" or ufun is None:
        return ufun
    os_ = ufun.outcome_space
    rv = float(getattr(ufun, "reserved_value", 0.0) or 0.0)
    if not math.isfinite(rv):
        rv = 0.0
    different = mode == "different"
    if is_additive(ufun):
        issues = list(os_.issues)
        w = np.array([float(x) for x in ufun.weights], dtype=float)
        total = float(w.sum()) or 1.0
        if different:
            w2 = rng.dirichlet(np.ones(len(w))) * total
        else:
            w2 = np.abs(w) * np.exp(rng.normal(0.0, noise * 1.5, len(w)))
            w2 = w2 / (w2.sum() or 1.0) * total
        values = []
        for issue, fn in zip(issues, ufun.values):
            try:
                discrete = issue.is_discrete()
            except Exception:  # noqa: BLE001
                discrete = False
            if not discrete:
                values.append(fn)
                continue
            pts = list(issue.all)
            v = _value_table(fn, pts)
            lo, hi = float(v.min()), float(v.max())
            if hi - lo < 1e-9:
                lo, hi = 0.0, max(1.0, hi)
            if different:
                v2 = rng.uniform(lo, hi, len(v))
            else:
                v2 = np.clip(v + rng.normal(0.0, noise * (hi - lo) * 0.5, len(v)), lo, hi)
            values.append(TableFun(dict(zip(pts, (float(x) for x in v2)))))
        try:
            mn, mx = ufun.minmax()
            span = float(mx - mn)
        except Exception:  # noqa: BLE001
            mn, span = 0.0, 1.0
        rv2 = rv if not span else float(np.clip(rv + rng.normal(0.0, noise * 0.15 * span), mn, mn + span * 0.9))
        return LinearAdditiveUtilityFunction(values=tuple(values), weights=tuple(float(x) for x in w2),
                                             bias=float(getattr(ufun, "bias", 0.0) or 0.0),
                                             outcome_space=os_, reserved_value=rv2, name=ufun.name)
    # any other function over a small enough discrete outcome space: move every outcome's value
    try:
        outcomes = list(os_.enumerate_or_sample(max_cardinality=20_000))
    except Exception:  # noqa: BLE001
        return ufun
    vals = np.array([float(ufun(o)) for o in outcomes], dtype=float)
    lo, hi = float(np.nanmin(vals)), float(np.nanmax(vals))
    if hi - lo < 1e-9:
        hi = lo + 1.0
    if different:
        v2 = rng.uniform(lo, hi, len(vals))
    else:
        v2 = np.clip(vals + rng.normal(0.0, noise * (hi - lo) * 0.5, len(vals)), lo, hi)
    return MappingUtilityFunction(dict(zip(outcomes, (float(x) for x in v2))), outcome_space=os_,
                                  reserved_value=rv, name=ufun.name)


# --------------------------------------------------------------------------- #
# Past negotiations                                                            #
# --------------------------------------------------------------------------- #
def _negotiator_class(name: str):
    import negmas

    cls = getattr(negmas, str(name), None)
    if cls is None:
        try:
            from negmas import sao

            cls = getattr(sao, str(name), None)
        except Exception:  # noqa: BLE001
            cls = None
    return cls


def _style(name: str) -> str:
    n = str(name)
    for suffix in ("Negotiator", "TB", "Agent"):
        n = n.replace(suffix, "")
    return {"NaiveTitForTat": "tit-for-tat", "Boulware": "tough (Boulware)", "Conceder": "conceding",
            "Linear": "steady"}.get(n, n)


def _offer_dict(issues: list, outcome: Any) -> dict[str, Any] | None:
    if outcome is None:
        return None
    return {str(i.name): _jsonable(v) for i, v in zip(issues, outcome)}


def simulate_past_negotiations(scenario: Any, settings: dict, *, seed_text: str = "") -> list[dict[str, Any]]:
    """Simulate ``settings["count"]`` past negotiations of ``scenario`` (the
    ``past_negotiations`` settings). Each one is played by two negmas
    negotiators with preferences related to the scenario's (see
    :func:`perturb_ufun`). Deterministic for a given ``seed_text`` and settings.

    A record is plain data, keyed by role names::

        {"id": "P1", "roles": [r0, r1], "styles": {r0: ..., r1: ...},
         "preferences": "similar", "n_steps": 20, "steps": 12,
         "agreement": {issue: value} | None, "utilities": {r0: u, r1: u},
         "reserved_values": {r0: rv, r1: rv},
         "offers": [{"step": 0, "by": r0, "offer": {...}, "utilities": {r0: u, r1: u}}, ...]}
    """
    from negmas import SAOMechanism

    count = int(settings.get("count") or 0)
    if count <= 0 or scenario is None:
        return []
    os_ = scenario.outcome_space
    issues = list(os_.issues)
    ufuns = list(scenario.ufuns)
    roles = [str(u.name) for u in ufuns]
    mode = settings.get("preferences") or "similar"
    opp_mode = settings.get("opponent_preferences") or mode
    noise = float(settings.get("noise", 0.25))
    n_steps = int(settings.get("n_steps") or 20)
    names = [n for n in settings.get("negotiators") or DEFAULT_NEGOTIATORS if _negotiator_class(n) is not None] \
        or list(DEFAULT_NEGOTIATORS)
    base = stable_seed(seed_text, settings.get("seed", 0), mode, opp_mode, noise, n_steps, count)
    out: list[dict[str, Any]] = []
    for k in range(count):
        rng = np.random.default_rng(base + k)
        # side 0 / 1 use the mode of "the human's side" / "the opponent's side" only when we know which
        # side the human plays; records are role-keyed, so "opponent_preferences" applies to every role
        # but the first one listed in settings["human_role"] (set by build_state)
        human_role = settings.get("human_role")
        past = [perturb_ufun(u, (mode if (human_role is None or u.name == human_role) else opp_mode), noise, rng)
                for u in ufuns]
        picks = [names[int(rng.integers(len(names)))] for _ in ufuns]
        try:
            m = SAOMechanism(outcome_space=os_, n_steps=n_steps, name=f"past-{k + 1}")
            for r, u, cname in zip(roles, past, picks):
                m.add(_negotiator_class(cname)(name=r), ufun=u)
            m.run()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            continue
        ids = {n.id: str(n.name) for n in m.negotiators}
        offers = []
        for row in m.extended_trace:
            step, nid, outcome = row[0], row[1], row[2]
            if outcome is None:
                continue
            offers.append({"step": int(step), "by": ids.get(nid, str(nid)), "offer": _offer_dict(issues, outcome),
                           "utilities": {r: round(float(u(outcome)), 4) for r, u in zip(roles, past)}})
        agreement = m.agreement
        out.append({
            "id": f"P{k + 1}",
            "roles": roles,
            "styles": {r: _style(c) for r, c in zip(roles, picks)},
            "preferences": {r: (mode if (human_role is None or r == human_role) else opp_mode) for r in roles},
            "n_steps": n_steps,
            "steps": int(m.state.step),
            "agreement": _offer_dict(issues, agreement),
            "utilities": {r: round(float(u(agreement)), 4) for r, u in zip(roles, past)},
            "reserved_values": {r: round(float(getattr(u, "reserved_value", 0.0) or 0.0), 4) for r, u in zip(roles, past)},
            "offers": offers,
        })
    return out


def load_past_file(folder: str | Path | None) -> list[dict[str, Any]] | None:
    """The past negotiations in a scenario folder's ``_past_negotiations.yaml``
    (``None`` when it has none). The file is a list of records (see
    :func:`simulate_past_negotiations`) or ``{"negotiations": [...]}``."""
    if not folder:
        return None
    f = Path(folder) / PAST_FILE
    if not f.is_file():
        return None
    import yaml

    try:
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"[hani2] could not read {f}: {e!r}")
        return None
    if isinstance(data, dict):
        data = data.get("negotiations")
    if not isinstance(data, list):
        return None
    out = []
    for k, rec in enumerate(data):
        if not isinstance(rec, dict):
            continue
        rec = dict(rec)
        rec.setdefault("id", f"P{k + 1}")
        rec["id"] = str(rec["id"])
        rec.setdefault("offers", [])
        rec.setdefault("utilities", {})
        out.append(rec)
    return out


def write_past_file(folder: str | Path, records: list[dict[str, Any]]) -> Path:
    """Write ``records`` to ``<folder>/_past_negotiations.yaml``."""
    import yaml

    f = Path(folder) / PAST_FILE
    f.write_text(yaml.safe_dump({"negotiations": _jsonable(records)}, sort_keys=False, allow_unicode=True),
                 encoding="utf-8")
    return f


# --------------------------------------------------------------------------- #
# Market research                                                              #
# --------------------------------------------------------------------------- #
def _best_values(ufun: Any) -> dict[str, Any]:
    out = {}
    for i, fn in zip(ufun.outcome_space.issues, ufun.values):
        pts = _issue_points(i)
        try:
            v = _value_table(fn, pts)
        except Exception:  # noqa: BLE001
            continue
        out[str(i.name)] = _jsonable(pts[int(np.argmax(v))])
    return out


_POPULATIONS: dict[tuple, tuple[list, str]] = {}


def scenario_population(scenario_type: str | None, n: int) -> tuple[list, str]:
    """Up to ``n`` other scenarios of ``scenario_type``: the population its
    preferences are drawn from. From the type's generator when it has one
    (``"generator"``), else from its saved scenarios (``"pool"``, at least two
    needed); ``([], "")`` otherwise. Cached per type."""
    if not scenario_type:
        return [], ""
    key = (scenario_type, n)
    with _CACHE_LOCK:
        if key in _POPULATIONS:
            return _POPULATIONS[key]
    from hani2 import scenario_store as store
    from hani2.scenarios import registry

    pop: list = []
    source = ""
    maker = registry.MAKERS.get(scenario_type)
    if maker is not None:
        for i in range(n):
            try:
                pop.append(maker(i))
            except Exception:  # noqa: BLE001
                continue
        source = "generator"
    else:
        try:
            for f in store._pool(scenario_type)[:n]:
                sc = store._load_dir(f)
                if sc is not None:
                    pop.append(sc)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        source = "pool" if len(pop) >= 2 else ""
        if not source:
            pop = []
    with _CACHE_LOCK:
        _POPULATIONS[key] = (pop, source)
    return pop, source


def _role_ufun(sc: Any, role: str, index: int):
    ufuns = list(getattr(sc, "ufuns", None) or [])
    u = next((x for x in ufuns if str(x.name).lower() == role.lower()), None)
    if u is None and 0 <= index < len(ufuns):
        u = ufuns[index]
    return u


def market_research(scenario: Any, roles: Iterable[str], settings: dict, *, seed_text: str = "",
                    population: list | None = None, source: str = "") -> dict[str, Any]:
    """What a market study would tell about the preferences of ``roles``: for
    each, the typical issue weights (mean and spread), the option of each issue
    that is most often the best, the most common best deal and the usual value
    on disagreement. Also any ``market_research`` text in the scenario's
    ``_info.yaml`` (a string, or a mapping of role to string).

    The statistics come from ``population``, other scenarios of the same type
    (see :func:`scenario_population`), so they describe the distribution the
    preferences are drawn from, not this negotiation's. Without a population
    (a one-off scenario) they come from ``settings["samples"]`` profiles near
    the real ones (``source == "nearby"``), which are close to the real
    preferences."""
    roles = [str(r) for r in roles]
    n = int(settings.get("samples") or 40)
    noise = float(settings.get("noise", 0.3))
    info = (getattr(scenario, "info", None) or {}) if scenario is not None else {}
    text = info.get("market_research")
    out: dict[str, Any] = {"roles": {}, "samples": n, "source": source if population else "nearby"}
    for index, u in enumerate(scenario.ufuns if scenario is not None else []):
        role = str(u.name)
        if role not in roles:
            continue
        if population:
            samples = [x for x in (_role_ufun(sc, role, index) for sc in population) if x is not None]
        else:
            rng = np.random.default_rng(stable_seed(seed_text, "market", role, n, noise))
            samples = [perturb_ufun(u, "similar", noise, rng) for _ in range(n)]
        if not samples:
            continue
        out["samples"] = len(samples)
        rec: dict[str, Any] = {}
        rvs = [float(getattr(s, "reserved_value", 0.0) or 0.0) for s in samples]
        rec["value_on_disagreement"] = {"typical": round(float(np.median(rvs)), 3),
                                        "range": [round(float(np.percentile(rvs, 10)), 3),
                                                  round(float(np.percentile(rvs, 90)), 3)]}
        if is_additive(u) and all(is_additive(x) for x in samples):
            names = [str(i.name) for i in u.outcome_space.issues]

            def _weights(x) -> list[float]:
                by_name = {str(i.name): float(w) for i, w in zip(x.outcome_space.issues, x.weights)}
                return [by_name.get(nm, 0.0) for nm in names]

            ws = np.array([_weights(x) for x in samples])
            ws = ws / np.where(ws.sum(axis=1, keepdims=True) == 0, 1, ws.sum(axis=1, keepdims=True))
            rec["issue_weights"] = {nm: {"mean": round(float(ws[:, j].mean()), 3), "spread": round(float(ws[:, j].std()), 3)}
                                    for j, nm in enumerate(names)}
            order = sorted(names, key=lambda nm: -rec["issue_weights"][nm]["mean"])
            rec["issues_by_importance"] = order
            bests = [_best_values(s) for s in samples]
            favs: dict[str, Any] = {}
            for nm in names:
                counts: dict[str, int] = {}
                for b in bests:
                    if nm in b:
                        key = json.dumps(b[nm])
                        counts[key] = counts.get(key, 0) + 1
                if counts:
                    key, c = max(counts.items(), key=lambda kv: kv[1])
                    favs[nm] = {"option": json.loads(key), "share": round(c / len(bests), 2)}
            rec["favourite_options"] = favs
            rec["likely_best_deal"] = {nm: f["option"] for nm, f in favs.items()}
        else:
            try:
                best = [tuple(s.best()) for s in samples[: min(10, n)]]
                common = max(set(best), key=best.count)
                rec["likely_best_deal"] = _offer_dict(list(u.outcome_space.issues), common)
            except Exception:  # noqa: BLE001
                pass
        if isinstance(text, dict):
            t = next((v for k, v in text.items() if str(k).lower() == role.lower()), None)
            if t:
                rec["notes"] = str(t)
        out["roles"][role] = rec
    if isinstance(text, str) and text.strip():
        out["notes"] = text.strip()
    return out


# --------------------------------------------------------------------------- #
# Briefings and hidden constraints                                             #
# --------------------------------------------------------------------------- #
def _num(x: Any) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def constraint_text(c: dict[str, Any]) -> str:
    """A constraint in words ("Rent must be at most 3200.")."""
    issue = c.get("issue", "?")
    parts = []
    if c.get("min") is not None and c.get("max") is not None:
        parts.append(f"between {c['min']} and {c['max']}")
    elif c.get("min") is not None:
        parts.append(f"at least {c['min']}")
    elif c.get("max") is not None:
        parts.append(f"at most {c['max']}")
    if c.get("allowed"):
        parts.append("one of " + ", ".join(str(v) for v in c["allowed"]))
    if c.get("forbidden"):
        parts.append("not " + ", ".join(str(v) for v in c["forbidden"]))
    return f"{issue} must be {' and '.join(parts)}." if parts else ""


def _constraint_ok(c: dict[str, Any], value: Any) -> bool:
    if c.get("allowed") and str(value) not in {str(v) for v in c["allowed"]}:
        return False
    if c.get("forbidden") and str(value) in {str(v) for v in c["forbidden"]}:
        return False
    x = _num(value)
    if c.get("min") is not None and (x is None or x < float(c["min"]) - 1e-9):
        return False
    if c.get("max") is not None and (x is None or x > float(c["max"]) + 1e-9):
        return False
    return True


def check_constraints(constraints: list[dict[str, Any]], agreement: dict[str, Any] | None) -> tuple[int | None, list[str]]:
    """``(met, violations)``: whether the agreement keeps every constraint (``1`` /
    ``0``; ``None`` without an agreement or without constraints) and the broken ones in words."""
    if not constraints or agreement is None:
        return None, []
    by_name = {str(k).lower(): v for k, v in agreement.items()}
    bad = []
    for c in constraints:
        v = by_name.get(str(c.get("issue", "")).lower())
        if not _constraint_ok(c, v):
            bad.append(constraint_text(c) or str(c))
    return (0 if bad else 1), bad


def _entries(raw: Any, default_role: str | None = None) -> list[dict[str, Any]]:
    """Briefing entries from a string, an entry, a list of them or a mapping of role to those."""
    if raw is None:
        return []
    if isinstance(raw, str):
        return [{"text": raw, "role": default_role}] if raw.strip() else []
    if isinstance(raw, list):
        return [e for x in raw for e in _entries(x, default_role)]
    if isinstance(raw, dict):
        if any(k in raw for k in ("text", "constraints", "to")):
            return [{**raw, "role": raw.get("role", default_role)}]
        return [e for k, v in raw.items() for e in _entries(v, str(k))]
    return []


def resolve_briefings(info: dict | None, settings: dict, human_role: str,
                      roles: Iterable[str] = ()) -> list[dict[str, Any]]:
    """The briefings of a round: the scenario's ``briefing`` (unless
    ``use_scenario_briefing`` is off; ``briefing_audience`` can redirect them) and
    the setting's ``briefing``, keeping those for the human's role (or no role).
    Each is ``{"id", "to", "text", "constraints", "pin"}``."""
    out: list[dict[str, Any]] = []
    sources = []
    if settings.get("use_scenario_briefing", True):
        sources.append(("scenario", _entries((info or {}).get("briefing")), settings.get("briefing_audience")))
    sources.append(("setting", _entries(settings.get("briefing")), None))
    for source, entries, audience in sources:
        role_names = {str(r).lower() for r in roles} | {human_role.lower()}
        for e in entries:
            role = str(e.get("role") or "").lower()
            implied = None
            if role and role not in role_names:  # not a role of the scenario: an audience key
                if role in ("human", "participant"):
                    implied = "human"
                elif role in ("assistant", "both"):
                    implied = role
                else:
                    continue
            elif role and role != human_role.lower():
                continue  # the briefing of the role the participant does not play
            to = audience or e.get("to") or implied or "human"
            if to == "participant":
                to = "human"
            if to not in ("human", "assistant", "both"):
                to = "human"
            cons = [dict(c) for c in (e.get("constraints") or []) if isinstance(c, dict) and c.get("issue")]
            text = str(e.get("text") or "").strip() or " ".join(t for t in (constraint_text(c) for c in cons) if t)
            if not text:
                continue
            out.append({"id": f"B{len(out) + 1}", "to": to, "text": text, "constraints": cons,
                        "pin": bool(e.get("pin", to != "assistant")), "source": source})
    return out


# --------------------------------------------------------------------------- #
# The state of one round                                                       #
# --------------------------------------------------------------------------- #
@dataclass
class InformationState:
    """What the human and the Assistant each know in one round."""

    settings: dict = field(default_factory=lambda: resolve_settings(None))
    human_role: str = ""
    opponent_role: str = ""
    #: the effective preference parts (an unsplittable function gives both ``full``)
    human_prefs: str = "full"
    assistant_prefs: str = "full"
    human_reserved: bool = True
    assistant_reserved: bool = True
    #: every past negotiation, and the ids each party holds
    past: list[dict[str, Any]] = field(default_factory=list)
    human_past: list[str] = field(default_factory=list)
    assistant_past: list[str] = field(default_factory=list)
    past_source: str = ""
    market: dict[str, Any] | None = None
    market_audience: str = "none"
    #: private instructions ({id, to, text, constraints, pin, source})
    briefings: list[dict[str, Any]] = field(default_factory=list)
    #: issue names only the human may set, and actions (send / accept / end) only the human may take
    human_only_issues: list[str] = field(default_factory=list)
    human_only_actions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # -- what each side sees -------------------------------------------------- #
    @property
    def split(self) -> bool:
        """Whether the human and the Assistant know different things this round."""
        return bool(self.past) or self.human_prefs != self.assistant_prefs \
            or self.human_reserved != self.assistant_reserved or (self.market is not None) \
            or bool(self.briefings) or bool(self.human_only_issues) or bool(self.human_only_actions)

    @property
    def human_sees_totals(self) -> bool:
        return self.human_prefs == "full" or bool(self.settings["preferences"].get("show_totals_to_partial"))

    @property
    def assistant_sees_totals(self) -> bool:
        return self.assistant_prefs == "full" or bool(self.settings["preferences"].get("show_totals_to_partial"))

    @property
    def human_sees_reserved(self) -> bool:
        return self.human_reserved

    @property
    def assistant_sees_reserved(self) -> bool:
        return self.assistant_reserved

    @property
    def human_market(self) -> bool:
        return self.market is not None and _gets(self.market_audience, "human")

    @property
    def assistant_market(self) -> bool:
        return self.market is not None and _gets(self.market_audience, "assistant")

    def briefings_for(self, who: str) -> list[dict[str, Any]]:
        return [b for b in self.briefings if _gets(b["to"], who)]

    @property
    def constraints(self) -> list[dict[str, Any]]:
        """Every hidden constraint of the round (checked against the agreement)."""
        return [c for b in self.briefings for c in b.get("constraints") or []]

    def decisions_text(self, include_issues: bool = True) -> str:
        """What only the human may do, in words ("set Price, accept or end the negotiation")."""
        words = {"send": "send offers", "accept": "accept", "end": "end the negotiation"}
        items = ([f"set {', '.join(self.human_only_issues)}"] if self.human_only_issues and include_issues else []) \
            + [words[a] for a in self.human_only_actions]
        return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " or " + items[-1] if items else ""

    def human_only_issue(self, name: str) -> bool:
        return str(name).lower() in {i.lower() for i in self.human_only_issues}

    def past_by_id(self, pid: str) -> dict[str, Any] | None:
        pid = str(pid).strip()
        return next((p for p in self.past if str(p.get("id")).lower() == pid.lower()), None)

    def held_by(self, who: str) -> list[dict[str, Any]]:
        ids = self.human_past if who == "human" else self.assistant_past
        return [p for p in self.past if p["id"] in ids]

    def record(self) -> dict[str, Any]:
        """The realised split, for results rows, events and recordings."""
        return {
            "split": self.split,
            "human_preferences": self.human_prefs,
            "assistant_preferences": self.assistant_prefs,
            "human_reserved_value": self.human_reserved,
            "assistant_reserved_value": self.assistant_reserved,
            "past_negotiations": len(self.past),
            "past_source": self.past_source,
            "human_past": list(self.human_past),
            "assistant_past": list(self.assistant_past),
            "market_research": self.market_audience if self.market is not None else "none",
            "briefings": [{k: b[k] for k in ("id", "to", "text", "constraints", "source")} for b in self.briefings],
            "constraints": self.constraints,
            "human_only_issues": list(self.human_only_issues),
            "human_only_actions": list(self.human_only_actions),
            "warnings": list(self.warnings),
        }

    # -- summaries --------------------------------------------------------- #
    def past_utilities(self, who: str) -> str:
        """Which utilities a past negotiation shows to ``who`` (``human`` / ``assistant``):
        the ``utilities`` setting, but ``none`` for a side that may not see what deals are
        worth (a record's utilities are close to, or with ``same`` equal to, the real ones)."""
        utilities = self.settings["past_negotiations"].get("utilities", "own")
        sees = self.human_sees_totals if who == "human" else self.assistant_sees_totals
        return utilities if sees else "none"

    def summary_row(self, rec: dict[str, Any], who: str) -> dict[str, Any]:
        """One line about a past negotiation, from the point of view of the human's role."""
        own, other = self.human_role, self._other_role(rec)
        utilities = self.past_utilities(who)
        row: dict[str, Any] = {
            "id": rec["id"],
            "result": "agreement" if rec.get("agreement") else "no agreement",
            "rounds": rec.get("steps"),
            "your_side_style": (rec.get("styles") or {}).get(own, ""),
            "opponent_style": (rec.get("styles") or {}).get(other, ""),
        }
        if utilities in ("own", "both"):
            row["your_side_utility"] = (rec.get("utilities") or {}).get(own)
        if utilities == "both":
            row["opponent_utility"] = (rec.get("utilities") or {}).get(other)
        row["held_by"] = ("both" if rec["id"] in self.human_past and rec["id"] in self.assistant_past
                          else "human" if rec["id"] in self.human_past else "assistant")
        return row

    def _other_role(self, rec: dict[str, Any]) -> str:
        roles = [str(r) for r in rec.get("roles") or []]
        return next((r for r in roles if r != self.human_role), self.opponent_role)

    def describe_split(self) -> dict[str, Any]:
        """Who holds what (no contents): what the Assistant is told about the split."""
        mr = self.market_audience if self.market is not None else "none"
        return {
            "participant_knows_of_their_preferences": self.human_prefs,
            "you_know_of_the_participants_preferences": self.assistant_prefs,
            "participant_knows_value_on_disagreement": self.human_reserved,
            "you_know_value_on_disagreement": self.assistant_reserved,
            "participant_sees_deal_values": self.human_sees_totals,
            "you_see_deal_values": self.assistant_sees_totals,
            "past_negotiations_you_hold": list(self.assistant_past),
            "past_negotiations_the_participant_holds": list(self.human_past),
            "market_research_given_to": mr,
            "participant_has_private_briefings": len([b for b in self.briefings if b["to"] == "human"]),
            "you_have_private_briefings": len([b for b in self.briefings if b["to"] == "assistant"]),
            "only_the_participant_may_set": list(self.human_only_issues),
            "only_the_participant_may": list(self.human_only_actions),
        }


_CACHE: dict[str, list[dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()


def _scenario_key(scenario: Any, scenario_dir: str | None, info: dict | None) -> str:
    forced = (info or {}).get("forced_reserved_value")  # a study's forced value changes the records
    if scenario_dir:
        return f"dir:{scenario_dir}" + (f"|rv={forced}" if forced is not None else "")
    return f"gen:{(info or {}).get('scenario_type')}:{(info or {}).get('index')}:{id(scenario)}"


def build_state(scenario: Any, *, human_index: int, settings: dict | None, scenario_dir: str | None = None,
                scenario_info: dict | None = None, assign_seed: str = "") -> InformationState:
    """The :class:`InformationState` of a round. ``settings``: the raw
    ``information`` block (merged with :data:`DEFAULTS`). ``assign_seed`` makes
    the random share of past negotiations differ per participant and round."""
    s = resolve_settings(settings)
    st = InformationState(settings=s)
    if scenario is None:
        return st
    ufuns = list(scenario.ufuns)
    human = ufuns[human_index]
    st.human_role = str(human.name)
    st.opponent_role = next((str(u.name) for i, u in enumerate(ufuns) if i != human_index), "")

    # preferences
    pr = s["preferences"]
    hp, ap = pr["human"], pr["assistant"]
    if (hp in ("weights", "values") or ap in ("weights", "values")) and not is_additive(human):
        st.warnings.append("the participant's preferences are not a weighted sum of issue values, so they cannot be "
                           "split into weights and values; both the participant and the Assistant know them fully")
        hp = "full" if hp != "none" else hp
        ap = "full" if ap != "none" else ap
    st.human_prefs, st.assistant_prefs = hp, ap
    st.human_reserved = _gets(pr["reserved_value"], "human")
    st.assistant_reserved = _gets(pr["reserved_value"], "assistant")

    # past negotiations
    p = s["past_negotiations"]
    records: list[dict[str, Any]] = []
    if p["count"] > 0:
        seed_text = f"{getattr(scenario.outcome_space, 'name', '')}|{scenario_dir or ''}|{st.human_role}"
        from_file = load_past_file(scenario_dir) if p.get("use_scenario_file", True) else None
        if from_file:
            records, st.past_source = from_file[: p["count"]], "scenario"
        else:
            key = _scenario_key(scenario, scenario_dir, scenario_info) + "|" + json.dumps(p, sort_keys=True) + st.human_role
            with _CACHE_LOCK:
                cached = _CACHE.get(key) if scenario_dir else None
            if cached is None:
                cached = simulate_past_negotiations(scenario, {**p, "human_role": st.human_role}, seed_text=seed_text)
                if scenario_dir:  # a generated scenario is new every time: nothing to reuse
                    with _CACHE_LOCK:
                        if len(_CACHE) > 256:
                            _CACHE.clear()
                        _CACHE[key] = cached
            records, st.past_source = copy.deepcopy(cached), "simulated"
    st.past = records
    ids = [r["id"] for r in records]
    if p.get("shared"):
        st.human_past, st.assistant_past = list(ids), list(ids)
    else:
        n_h = int(round(p["human_share"] * len(ids)))
        order = list(ids)
        if p.get("assignment") == "random":
            random.Random(stable_seed(assign_seed, "past", len(ids))).shuffle(order)
        human_ids = set(order[:n_h])
        st.human_past = [i for i in ids if i in human_ids]
        st.assistant_past = [i for i in ids if i not in human_ids]

    # briefings and who may act
    st.briefings = resolve_briefings(getattr(scenario, "info", None) or {}, s, st.human_role,
                                     roles=[str(u.name) for u in ufuns])
    issues = {str(i.name).lower(): str(i.name) for i in scenario.outcome_space.issues}
    for b in st.briefings:
        for c in b["constraints"]:
            if str(c["issue"]).lower() not in issues:
                st.warnings.append(f"briefing {b['id']}: no issue named {c['issue']!r}")
    st.human_only_issues = [issues[x.lower()] for x in s["control"]["human_only_issues"] if x.lower() in issues]
    for x in s["control"]["human_only_issues"]:
        if x.lower() not in issues:
            st.warnings.append(f"control: no issue named {x!r}")
    st.human_only_actions = list(s["control"]["human_only_actions"])

    # market research
    mr = s["market_research"]
    if mr["audience"] != "none":
        sides = {"opponent": [st.opponent_role], "own": [st.human_role], "both": [st.human_role, st.opponent_role]}
        try:
            pop, source = scenario_population((scenario_info or {}).get("scenario_type"), mr["samples"])
            st.market = market_research(scenario, sides[mr["sides"]], mr, population=pop, source=source,
                                        seed_text=f"{getattr(scenario.outcome_space, 'name', '')}|{scenario_dir or ''}")
            if st.market.get("source") == "nearby":
                st.warnings.append("market research for a scenario with no generator or pool is computed from "
                                   "profiles near the real preferences, so it is close to them")
            st.market_audience = mr["audience"]
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            st.warnings.append(f"market research could not be computed: {e}")
    return st


# --------------------------------------------------------------------------- #
# Views for one party (need a session: option labels, offer texts)             #
# --------------------------------------------------------------------------- #
def _shown_dict(session: Any, d: dict | None) -> dict | None:
    if d is None:
        return None
    try:
        return session.display_outcome(dict(d))
    except Exception:  # noqa: BLE001
        return dict(d)


def _outcome_of(session: Any, d: dict | None):
    if d is None:
        return None
    try:
        return tuple(d.get(str(i.name)) for i in session.issues)
    except Exception:  # noqa: BLE001
        return None


def _offer_text(session: Any, d: dict | None, from_human: bool) -> str:
    o = _outcome_of(session, d)
    if o is None:
        return "no agreement"
    try:
        return str(session.relabel_text(session.outcome_str(o, from_human=from_human)) or "")
    except Exception:  # noqa: BLE001
        return ", ".join(f"{k}: {v}" for k, v in (d or {}).items())


def past_view(session: Any, rec: dict[str, Any], *, who: str = "human", max_offers: int | None = None) -> dict[str, Any]:
    """A past negotiation as ``who`` (``human`` / ``assistant``) sees it: "your
    side" is the party in the human's role, "opponent" the other one."""
    st: InformationState = session.information
    own, other = st.human_role, st._other_role(rec)
    utilities = st.past_utilities(who)

    def utils(u: dict | None) -> dict[str, Any]:
        u = u or {}
        out: dict[str, Any] = {}
        if utilities in ("own", "both") and own in u:
            out["your_side"] = u.get(own)
        if utilities == "both" and other in u:
            out["opponent"] = u.get(other)
        return out

    offers = []
    for o in rec.get("offers") or []:
        mine = str(o.get("by")) == own
        offers.append({"step": o.get("step"), "by": "your side" if mine else "opponent",
                       "offer": _shown_dict(session, o.get("offer")),
                       "text": _offer_text(session, o.get("offer"), mine), **{f"utility_{k}": v for k, v in utils(o.get("utilities")).items()}})
    if max_offers is not None and len(offers) > max_offers:
        offers = offers[:max_offers // 2] + offers[-(max_offers - max_offers // 2):]
    view = {
        "id": rec["id"],
        "result": "agreement" if rec.get("agreement") else "no agreement",
        "rounds": rec.get("steps"),
        "styles": {"your_side": (rec.get("styles") or {}).get(own, ""), "opponent": (rec.get("styles") or {}).get(other, "")},
        "preferences": {"your_side": (rec.get("preferences") or {}).get(own, "") if isinstance(rec.get("preferences"), dict)
                        else rec.get("preferences", ""),
                        "opponent": (rec.get("preferences") or {}).get(other, "") if isinstance(rec.get("preferences"), dict)
                        else rec.get("preferences", "")},
        "agreement": _shown_dict(session, rec.get("agreement")),
        "agreement_text": _offer_text(session, rec.get("agreement"), True) if rec.get("agreement") else "no agreement",
        "final_utilities": utils(rec.get("utilities")),
        "offers": offers,
    }
    if rec.get("notes"):
        view["notes"] = str(rec["notes"])
    return view


def market_view(session: Any) -> dict[str, Any] | None:
    """The market research with roles named "you" / "your opponent" and options as shown."""
    st: InformationState = session.information
    if st.market is None:
        return None
    out: dict[str, Any] = {"based_on": f"{st.market.get('samples')} comparable negotiators per role"}
    for role, rec in (st.market.get("roles") or {}).items():
        who = "your_side" if role == st.human_role else "opponent"
        r = dict(rec)
        if "likely_best_deal" in r:
            r["likely_best_deal_text"] = _offer_text(session, r["likely_best_deal"], True)
            r["likely_best_deal"] = _shown_dict(session, r["likely_best_deal"])
        if "favourite_options" in r:
            r["favourite_options"] = {k: {**v, "option": (_shown_dict(session, {k: v["option"]}) or {}).get(k, v["option"])}
                                      for k, v in r["favourite_options"].items()}
        out[who] = r
    if st.market.get("notes"):
        out["notes"] = st.market["notes"]
    return out


def private_view(session: Any) -> dict[str, Any]:
    """Everything only the Assistant knows this round, plus who holds what."""
    st: InformationState = session.information
    out: dict[str, Any] = {"who_holds_what": st.describe_split()}
    if not st.split:
        out["note"] = "You and the participant know the same things in this negotiation."
    if st.assistant_prefs != "none":
        part = preference_part(session.human_ufun, st.assistant_prefs)
        if "values" in part:
            part["values"] = {issue: {str((_shown_dict(session, {issue: k}) or {}).get(issue, k)): v for k, v in row.items()}
                              for issue, row in part["values"].items()}
        out["participant_preferences_you_know"] = {"part": st.assistant_prefs, **part}
    if st.assistant_sees_reserved:
        try:
            out["participant_value_on_disagreement"] = round(float(session.reserved_value()), 4)
        except Exception:  # noqa: BLE001
            pass
    if st.assistant_past:
        out["past_negotiations_you_hold"] = [st.summary_row(r, "assistant") for r in st.held_by("assistant")]
        out["past_negotiations_hint"] = "Call show_past_negotiation with an id to see every offer of one of them."
    if st.human_past:
        out["past_negotiations_the_participant_holds"] = list(st.human_past)
    if st.assistant_market:
        out["market_research"] = market_view(session)
    mine = st.briefings_for("assistant")
    if mine:
        out["briefings_for_you"] = [{"text": b["text"], **({"constraints": [constraint_text(c) for c in b["constraints"]]}
                                                         if b["constraints"] else {})} for b in mine]
    if any(b["to"] == "human" for b in st.briefings):
        out["participant_briefing_hint"] = ("The participant has private instructions you cannot see (for example a "
                                            "limit that is not in their preferences). Ask them about it.")
    if st.human_only_issues or st.human_only_actions:
        out["control_hint"] = (f"Only the participant may {st.decisions_text()}. Suggest these to them; "
                               "you cannot do them yourself.")
    return out
