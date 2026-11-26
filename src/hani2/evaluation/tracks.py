"""The two competition tracks and their leaderboards.

* ``han`` — Human-Agent Negotiation: sessions without an Assistant; the
  entrants are the Opponent agents.
* ``hi`` — Hybrid Intelligence: sessions with an Assistant; the entrants are
  the Assistants (with their language model).

Each track has two boards: **outcome** (what the entrant's side obtained) and
**interaction** (how well it behaved: as an opponent in HAN; as an Assistant
and as a team in HI). See :mod:`hani2.evaluation.scores` for the scores.

Per entrant a board reports the ranked score as a cell-balanced mean (cells are
scenarios in HAN, scenario × opponent in HI) with a 95 % bootstrap confidence
interval that resamples participants (sessions of one participant are not
independent), the other scores of the board, pass^k on a success criterion,
the mean language-model cost and whether it is statistically tied with the
leader. Every entrant is scored on the same components: those present in at
least ``min_coverage`` of the sessions of every entrant.

Strata. HI boards are shown per stratum: ``solo`` (AI opponents, including the
fallbacks of Paired studies), ``paired`` (a person on the other side; cells are
scenario × side × opposing Assistant) and ``combined`` (cell-balanced over both
kinds of cells). A Paired match gives one observation to each of its two
Assistants; a same-Assistant match is one observation (the mean of its rows);
board-wide totals count each match once. HAN boards have the official
``alone`` stratum (no Assistant) and ``vs_team`` (HI Solo sessions against HAN
entrants; cells scenario × Assistant), pooled only with ``stratum="both"``. HAN
rows against a person are counted under ``excluded["human opponent"]``.
:func:`head_to_head` ranks Assistants from their Paired matches (Bradley–Terry).

    from hani2.evaluation import evaluate_paths, leaderboards
    rows = evaluate_paths(["results/"])["rows"]
    boards = leaderboards(rows, "hi")
    boards["interaction"]["entries"][0]
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from hani2.evaluation.base import num
from hani2.evaluation.scores import BY_NAME, _weights, active_components, score_row

#: a board warns when its ranked score uses less than this share of the score's full weight
LOW_WEIGHT_SHARE = 0.5

TRACKS: dict[str, dict[str, Any]] = {
    "han": dict(
        title="Human-Agent Negotiation", entrant="opponent", entrant_title="Opponent", cells=("scenario",),
        boards={"outcome": ["han_outcome"], "interaction": ["han_interaction"]},
        # an Opponent failure is the entrant's fault (it scores 0); a system failure is not
        exclude_status={"erred": "system failure"},
        strata=("alone", "vs_team", "both"), default_stratum="alone",
    ),
    "hi": dict(
        title="Hybrid Intelligence", entrant="support_agent", entrant_title="Assistant", cells=("scenario", "opponent"),
        boards={"outcome": ["hi_outcome"], "interaction": ["hi_interaction", "hi_assistant", "hi_team"]},
        # neither an Opponent failure nor a system failure is the Assistant's fault
        exclude_status={"erred": "system failure", "agent_failed": "opponent failure"},
        strata=("combined", "solo", "paired"), default_stratum="combined",
    ),
}
BOARDS = ("outcome", "interaction")
#: the board of :mod:`hani2.evaluation.boards`: rows scored beforehand, ranked by ``rank_by`` (any score or
#: criterion) with the game's rules applied by the caller (``_exclude`` / ``_hidden`` / ``_only_stratum``)
GAME_BOARD = "game"
#: what a bootstrap cluster is: a participant (default) or a match (a sensitivity check for Paired rows)
CI_UNITS = ("participant", "match")
STRATUM_TITLES = {
    "combined": "Solo and Paired combined", "solo": "Solo (against AI opponents, including Paired fallbacks)",
    "paired": "Paired (person against person)", "alone": "HAN agents against people without an Assistant",
    "vs_team": "HAN agents against people with an Assistant",
    "both": "HAN agents against people with and without an Assistant (pooled)",
}
#: the cells of the HI Paired stratum, and the extra cells the HAN strata with Assistants use
PAIRED_CELLS = ("scenario", "side", "opponent_assistant")


def _blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    return str(v).strip() in ("", "nan", "None", "NaN")


def has_assistant(r: dict) -> bool:
    return str(r.get("support_agent") or "none") != "none"


def is_paired(r: dict) -> bool:
    """Whether a person sat on the other side (what happened, not what was planned): a row with a
    human ``opponent_kind`` or, in rows that do not say, a ``match_id``. A Paired study's AI fallback
    (``pairing = fallback``) is not."""
    if str(r.get("pairing") or "") == "fallback":
        return False
    kind = r.get("opponent_kind")
    if not _blank(kind):
        return str(kind).startswith("human")
    return not _blank(r.get("match_id"))


def study_stratum(r: dict) -> str:
    """The HI stratum of a row: ``paired`` (a person on the other side) or ``solo`` (an AI opponent,
    including the fallbacks of Paired studies and the AI games of Mixed ones)."""
    return "paired" if is_paired(r) else "solo"


def han_stratum(r: dict) -> str | None:
    """The HAN stratum of a row: ``alone`` (no Assistant, an AI opponent), ``vs_team`` (an Assistant
    against a HAN entrant, ``opponent_han_year`` set), ``human opponent`` (no Assistant against a
    person: nothing to rank) or ``None`` (not a HAN row)."""
    if not has_assistant(r):
        return "human opponent" if is_paired(r) else "alone"
    if not is_paired(r) and not _blank(r.get("opponent_han_year")):
        return "vs_team"
    return None


def _in_track(r: dict, track: str) -> bool:
    return has_assistant(r) if track == "hi" else han_stratum(r) is not None


def entrant_of(r: dict, track: str) -> str:
    if r.get("_entrant"):  # set by the boards (an outside system's entrant id, else the spec)
        return str(r["_entrant"])
    if track == "hi":
        name, model = str(r.get("support_agent") or "none"), r.get("support_model")
        return f"{name} · {model}" if model else name
    return str(r.get("opponent") or "?")


def _match_of(r: dict) -> str | None:
    return None if _blank(r.get("match_id")) or not is_paired(r) else str(r.get("match_id"))


def _abandoned(r: dict) -> bool:
    return not _blank(r.get("abandoned")) and str(r.get("abandoned")).lower() not in ("false", "0")


def _filter(rows: list[dict], track: str, include_practice: bool, include_simulated: bool = False,
            stratum: str | None = None) -> tuple[list[dict], dict[str, int], dict[str, int]]:
    """The rows of ``track`` that count, in ``stratum`` (default: every stratum), the excluded
    counts by reason, and the counted rows per stratum (whatever ``stratum`` is)."""
    spec = TRACKS[track]
    kept, excluded, counts = [], {}, {s: 0 for s in spec["strata"] if s not in ("combined", "both")}
    # an abandoned match drops both of its rows
    gone = {_match_of(r) for r in rows if _abandoned(r) and _match_of(r)}

    def drop(reason):
        excluded[reason] = excluded.get(reason, 0) + 1

    for r in rows:
        if not _in_track(r, track):
            continue
        st = study_stratum(r) if track == "hi" else han_stratum(r)
        if r.get("_only_stratum") and st != r["_only_stratum"]:
            continue  # a row taken in from another project for one stratum only
        if st == "human opponent":
            if stratum in (None, "alone", "both"):
                drop("human opponent")  # a HAN row of a Paired study: no entrant to rank
            continue
        if r.get("practice") and not include_practice:
            drop("practice")
            continue
        if r.get("mode") == "simulated" and not include_simulated:
            drop("simulated participant")  # never ranked with human sessions
            continue
        status = r.get("status")
        if (status is None and r.get("agreement") is None) or _abandoned(r) or (_match_of(r) in gone and _match_of(r)):
            drop("abandoned")
            continue
        if status in spec["exclude_status"]:
            drop(spec["exclude_status"][status])
            continue
        if r.get("_exclude"):  # a rule of the caller (boards: own-team games, caps, not counted)
            drop(str(r["_exclude"]))
            continue
        if r.get("_hidden"):  # a view of the caller (boards: the games and window switches); not excluded
            continue
        counts[st] = counts.get(st, 0) + 1
        if stratum in (None, "combined", "both") or st == stratum:
            kept.append(r)
    return kept, excluded, counts


def _partners(rows: list[dict]) -> dict[int, dict]:
    """The other row of each Paired match (by ``id()`` of a row), among ``rows``."""
    by: dict[str, list[dict]] = {}
    for r in rows:
        m = _match_of(r)
        if m:
            by.setdefault(m, []).append(r)
    out: dict[int, dict] = {}
    for rs in by.values():
        if len(rs) == 2:
            out[id(rs[0])], out[id(rs[1])] = rs[1], rs[0]
    return out


def _opposing(r: dict, partner: dict | None) -> str:
    """The opposing Assistant of a Paired row: the partner row's entrant (the same naming as the
    board's entrants), else the row's ``opponent_assistant_entrant`` or ``opponent_assistant``."""
    if partner is not None:
        return entrant_of(partner, "hi") if has_assistant(partner) else "none"
    for k in ("opponent_assistant_entrant", "opponent_assistant"):
        if not _blank(r.get(k)):
            return str(r[k])
    return "?"


def _same_assistant(r: dict, partner: dict | None) -> bool:
    if not has_assistant(r):
        return False
    if partner is not None:
        return has_assistant(partner) and entrant_of(partner, "hi") == entrant_of(r, "hi")
    opp, own = r.get("opponent_assistant"), r.get("assistant")
    return not _blank(opp) and not _blank(own) and str(opp) == str(own)


def _cell(r: dict, track: str, stratum: str, partner: dict | None) -> tuple:
    """A row's cell. HI: (scenario, opponent) for an AI opponent; (scenario, side, opposing
    Assistant) for a person, tagged so the two kinds never share a cell. HAN ``alone``: the
    scenario; ``vs_team`` and ``both``: scenario × the human's Assistant (``none`` without one)."""
    sc = str(r.get("scenario"))
    if track == "han":
        if stratum == "alone":
            return (sc,)
        return (sc, entrant_of(r, "hi") if has_assistant(r) else "none")
    if is_paired(r):
        side = r.get("side") if not _blank(r.get("side")) else r.get("human_index")
        return ("paired", sc, str(side) if not _blank(side) else "?", _opposing(r, partner))
    return ("solo", sc, str(r.get("opponent")))


def _collapse(rs: list[dict]) -> list[dict]:
    """Same-Assistant matches (both sides with one Assistant) become one observation: the mean of
    the two rows' numbers, in the cell (scenario, ``both``, Assistant)."""
    out, pairs = [], {}
    for r in rs:
        if r.get("_same") and r.get("_match"):
            pairs.setdefault(r["_match"], []).append(r)
        else:
            out.append(r)
    for m, two in pairs.items():
        if len(two) == 1:
            out.append(two[0])
            continue
        a, b = two[0], two[1]
        merged = dict(a)
        for k in set(a) | set(b):
            if k.startswith("_"):
                continue
            x, y = num(a.get(k)), num(b.get(k))
            if x is not None and y is not None and k not in ("side", "human_index"):
                merged[k] = (x + y) / 2
            elif x is None and y is not None:
                merged[k] = b.get(k)
        merged["_users"] = sorted(set(a["_users"]) | set(b["_users"]))
        merged["_participant"] = "+".join(merged["_users"])
        merged["_cell"] = ("paired", str(a.get("scenario")), "both", entrant_of(a, "hi"))
        merged["_collapsed"] = True
        out.append(merged)
    return out


def _active_components(rows: list[dict], track: str, names: list[str], min_coverage: float,
                       blocked: set[str] | None = None) -> dict[str, set[str]]:
    """Per score, the components present in at least ``min_coverage`` of the
    sessions of every entrant (so every entrant is scored on the same things);
    ``blocked`` columns are never used."""
    return active_components(rows, [BY_NAME[n] for n in names], lambda r: entrant_of(r, track),
                             min_coverage=min_coverage, blocked=blocked)


def _balanced(vals: list[tuple[tuple, float]]) -> float | None:
    cells: dict[tuple, list[float]] = {}
    for c, v in vals:
        cells.setdefault(c, []).append(v)
    return float(np.mean([np.mean(v) for v in cells.values()])) if cells else None


def _bootstrap(items: list[tuple[str, tuple, float]], n_boot: int, rng: np.random.Generator,
               unit: str = "participant", level: float = 0.95) -> tuple[float | None, float | None, str]:
    """Percentile CI (``level``, default 95 %) of the balanced mean, resampling the clusters named by
    the first item of each tuple: participants (or sessions when there is only one participant), or
    matches."""
    if unit == "participant":
        users = sorted({u for u, _, _ in items})
        unit = "participant" if len(users) >= 2 else "session"
    clusters: dict[Any, list[tuple[tuple, float]]] = {}
    for i, (u, c, v) in enumerate(items):
        clusters.setdefault(i if unit == "session" else u, []).append((c, v))
    keys = list(clusters)
    if len(keys) < 2 or n_boot <= 0:
        return None, None, unit
    stats = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(keys), len(keys))
        b = _balanced([x for k in pick for x in clusters[keys[k]]])
        if b is not None:
            stats.append(b)
    if not stats:
        return None, None, unit
    a = 100 * (1 - level) / 2
    return float(np.percentile(stats, a)), float(np.percentile(stats, 100 - a)), unit


def _pass_hat_k(rows: list[dict], cell, success: str, threshold: float | None, max_k: int) -> dict[int, float]:
    from hani2.evaluation import pass_hat_k

    per: dict[tuple, list[bool]] = {}
    for r in rows:
        v = num(r.get(success))
        if v is None:
            continue
        per.setdefault(cell(r), []).append(v >= (threshold if threshold is not None else 1 - 1e-9))
    if not per:
        return {}
    kmax = min(max_k, min(len(v) for v in per.values()))
    return {k: float(np.mean([pass_hat_k(len(v), sum(v), k) for v in per.values()])) for k in range(1, kmax + 1)}


def _totals(rows: list[dict]) -> dict:
    """Board-wide totals, each negotiation once (the two rows of a Paired match count once)."""
    seen: dict[Any, dict] = {}
    for i, r in enumerate(rows):
        m = r.get("_match") if "_match" in r else _match_of(r)
        seen.setdefault(m if m else ("row", i), r)
    neg = list(seen.values())
    agr = [num(r.get("agreement")) for r in neg]
    agr = [a for a in agr if a is not None]
    wel = [num(r.get("welfare")) for r in neg]
    wel = [w for w in wel if w is not None]
    return dict(rows=len(rows), sessions=len(neg), matches=sum(1 for k in seen if not isinstance(k, tuple)),
                agreement_rate=float(np.mean(agr)) if agr else None, welfare=float(np.mean(wel)) if wel else None)


def head_to_head(rows: list[dict], column: str = "human_advantage", *, prior: float = 0.5,
                 iterations: int = 1000) -> dict:
    """Direct comparisons of Assistants from Paired matches: in each match with two different
    Assistants, the one whose human got the higher ``column`` wins (equal values: a tie, half a win
    each). A Bradley–Terry model gives each Assistant a strength (log scale, mean 0 within each
    connected group); ``prior`` adds that many tied games to every pair that met, so an Assistant
    that never won still gets a finite strength.

    ``rows`` are evaluated rows (``evaluate_*()["rows"]``); give the rows a board counts."""
    by: dict[str, list[dict]] = {}
    for r in rows:
        m = _match_of(r)
        if m and has_assistant(r) and num(r.get(column)) is not None:
            by.setdefault(m, []).append(r)
    pairs: dict[tuple[str, str], dict] = {}
    for rs in by.values():
        if len(rs) != 2:
            continue
        a, b = sorted(rs, key=lambda r: entrant_of(r, "hi"))
        ea, eb = entrant_of(a, "hi"), entrant_of(b, "hi")
        if ea == eb:
            continue  # a same-Assistant match compares nothing
        d = float(num(a.get(column))) - float(num(b.get(column)))
        p = pairs.setdefault((ea, eb), dict(a=ea, b=eb, matches=0, a_wins=0, b_wins=0, ties=0, diffs=[]))
        p["matches"] += 1
        p["diffs"].append(d)
        if abs(d) <= 1e-9:
            p["ties"] += 1
        elif d > 0:
            p["a_wins"] += 1
        else:
            p["b_wins"] += 1
    names = sorted({e for k in pairs for e in k})
    idx = {n: i for i, n in enumerate(names)}
    n = len(names)
    wins = np.zeros((n, n))
    for (ea, eb), p in pairs.items():
        i, j = idx[ea], idx[eb]
        wins[i, j] += p["a_wins"] + 0.5 * p["ties"] + prior / 2
        wins[j, i] += p["b_wins"] + 0.5 * p["ties"] + prior / 2
    games = wins + wins.T
    # connected groups: strengths are comparable only within one
    group = list(range(n))

    def root(i):
        while group[i] != i:
            group[i] = group[group[i]]
            i = group[i]
        return i

    for i in range(n):
        for j in range(n):
            if games[i, j] > 0:
                group[root(i)] = root(j)
    comps = sorted({root(i) for i in range(n)})
    p_ = np.ones(n)
    for _ in range(iterations if n else 0):
        new = np.empty(n)
        for i in range(n):
            den = sum(games[i, j] / (p_[i] + p_[j]) for j in range(n) if j != i and games[i, j] > 0)
            new[i] = wins[i].sum() / den if den > 0 else p_[i]
        for c in comps:
            mem = [i for i in range(n) if root(i) == c]
            new[mem] /= np.exp(np.mean(np.log(new[mem])))
        done = np.max(np.abs(new - p_)) < 1e-10
        p_ = new
        if done:
            break
    entries = []
    for e in names:
        i = idx[e]
        mine = [p for k, p in pairs.items() if e in k]
        w = sum(p["a_wins"] if p["a"] == e else p["b_wins"] for p in mine)
        l_ = sum(p["b_wins"] if p["a"] == e else p["a_wins"] for p in mine)
        entries.append(dict(entrant=e, strength=float(np.log(p_[i])), matches=sum(p["matches"] for p in mine),
                            wins=w, losses=l_, ties=sum(p["ties"] for p in mine), group=comps.index(root(i))))
    entries.sort(key=lambda x: (-x["strength"], x["entrant"]))
    for k, e in enumerate(entries):
        e["rank"] = k + 1
    out_pairs = [dict({k: v for k, v in p.items() if k != "diffs"}, mean_diff=float(np.mean(p["diffs"])))
                 for p in pairs.values()]
    notes = []
    if len(comps) > 1:
        notes.append(f"the Assistants form {len(comps)} groups that never met one another: strengths are "
                     "comparable only within a group")
    return dict(column=column, model="bradley-terry", prior=prior, matches=sum(p["matches"] for p in pairs.values()),
                groups=len(comps), entries=entries, pairs=out_pairs, notes=notes)


_head_to_head = head_to_head  # the leaderboard's ``head_to_head`` argument hides the function


def leaderboard(rows: list[dict], track: str = "hi", board: str = "outcome", *, options: dict | None = None,
                success: str | None = None, success_threshold: float | None = None, max_k: int = 4,
                min_coverage: float = 0.5, relative: bool = False, n_boot: int = 1000, seed: int = 0,
                include_practice: bool = False, reliability: Any = None, official: bool = False,
                include_simulated: bool = False, stratum: str | None = None, ci_unit: str = "participant",
                head_to_head: bool | str = False, rank_by: str | None = None, values: list[str] | None = None,
                directions: dict[str, str] | None = None, ci: float = 0.95) -> dict:
    """Rank the entrants of ``track`` (``han`` or ``hi``) on ``board``
    (``outcome`` or ``interaction``) from evaluated rows (``evaluate_*()["rows"]``).

    ``success`` is the pass^k criterion (default: in HI ``task_success`` when
    the scenarios define criteria, else ``agreement``; in HAN ``agreement``). ``relative`` subtracts each
    cell's mean over all entrants first (removes the difficulty of the
    scenarios and opponents when entrants played different cells).

    ``stratum``: in HI ``combined`` (default: every row, cell-balanced over Solo and Paired cells),
    ``solo`` (AI opponents, including the fallbacks of Paired studies) or ``paired`` (a person on
    the other side); in HAN ``alone`` (default, the official board: people without an Assistant),
    ``vs_team`` (people with an Assistant against HAN entrants, ``opponent_han_year`` set) or
    ``both`` (the two pooled, labelled as such). HAN rows against a person are counted under
    ``excluded["human opponent"]``. A Paired match's two rows are two observations, one per
    Assistant; a same-Assistant match is one (the mean of its two rows); board-wide totals count
    each match once.

    ``ci_unit``: what the bootstrap resamples, ``participant`` (default) or ``match`` (a
    sensitivity check: the two rows of a match belong to two participants that the default
    resamples independently). ``head_to_head`` (HI): add the Bradley–Terry view of the Paired
    matches on ``human_advantage`` (or on the column it names) under ``head_to_head``.

    ``board="game"`` (:mod:`hani2.evaluation.boards`): the rows already carry their scores; the board
    ranks by ``rank_by`` (any score or criterion column) in its direction (``directions``, default
    ``higher``) and reports ``values`` too. With ``relative`` the cell-adjusted means are shifted back by
    the grand mean, so they stay on the scale of the values. Rows may carry ``_entrant`` (the entrant's
    name), ``_exclude`` (a reason: the row is excluded and counted), ``_hidden`` (left out of this view)
    and ``_only_stratum`` (counted in that stratum only); partners are found among every row.

    ``reliability``: a judge reliability report (a dict or the ``.json`` file of
    ``hani2 replay judge-reliability``); the soft (language-model judged)
    components it did not find ready are left out. ``official``: an official
    ranking; without a report (argument or env.json
    ``evaluation.reliability.report``) every soft component is left out.
    ``include_simulated``: rank simulated participants' sessions (``mode ==
    "simulated"``) too; by default they are left out, never mixed with humans.
    """
    if track not in TRACKS:
        raise ValueError(f"unknown track {track!r}; use one of {', '.join(TRACKS)}")
    game = board == GAME_BOARD
    if board not in BOARDS and not game:
        raise ValueError(f"unknown board {board!r}; use one of {', '.join(BOARDS)}")
    if game and not rank_by:
        raise ValueError("the game board needs rank_by (a score or criterion column)")
    directions = dict(directions or {})
    spec = TRACKS[track]
    stratum = stratum or spec["default_stratum"]
    if stratum not in spec["strata"]:
        raise ValueError(f"unknown {track} stratum {stratum!r}; use one of {', '.join(spec['strata'])}")
    if ci_unit not in CI_UNITS:
        raise ValueError(f"unknown ci_unit {ci_unit!r}; use one of {', '.join(CI_UNITS)}")
    if game:
        names = list(dict.fromkeys([str(rank_by), *(values or [])]))
    else:
        names = list(spec["boards"][board])
    kept, excluded, strata = _filter(rows, track, include_practice, include_simulated, stratum)
    # the sub-scores first, so a score of scores knows which of them exist
    order = [] if game else [s for s in BY_NAME if s in names or any(c.column == s for n in names
                                                                       for c in BY_NAME[n].components)]
    if game:
        gate: dict[str, Any] = dict(blocked=set(), warnings=[], source=None, judges=None)
        active: dict[str, set[str]] = {}
    else:
        gate = _reliability_gate(reliability, official, {str(r["judge_model"]) for r in kept if r.get("judge_model")})
        active = _active_components(kept, track, order, min_coverage, gate["blocked"])
    partners = _partners([r for r in rows if _in_track(r, track)])  # a partner row left out still names the opponent
    scored = []
    for i, r in enumerate(kept):
        r2 = dict(r)
        if not game:
            r2.update(score_row(r, options, only=active))
        partner = partners.get(id(r))
        r2["_cell"] = _cell(r, track, stratum, partner)
        r2["_match"] = _match_of(r)
        r2["_same"] = track == "hi" and _match_of(r) is not None and _same_assistant(r, partner)
        r2["_users"] = [str(r.get("user"))]
        r2["_participant"] = str(r.get("user"))
        r2["_session"] = ("row", i)
        scored.append(r2)
    totals = _totals(scored)
    if track == "hi":
        scored = _collapse(scored)
    if success is None:  # scenario criteria are written for the Human side: they define success in HI only
        success = "task_success" if track == "hi" and any(num(r.get("task_success")) is not None for r in scored) \
            else "agreement"

    def cell(r):
        return r["_cell"]

    if relative:
        for n in names:
            per: dict[tuple, list[float]] = {}
            for r in scored:
                if num(r.get(n)) is not None:
                    per.setdefault(cell(r), []).append(float(r[n]))
            means = {c: float(np.mean(v)) for c, v in per.items()}
            # the game board stays on the values' scale: the adjusted means are shifted by the grand mean
            grand = float(np.mean([x for v in per.values() for x in v])) if game and per else 0.0
            for r in scored:
                if num(r.get(n)) is not None:
                    r[n] = float(r[n]) - means[cell(r)] + grand
    rng = np.random.default_rng(seed)
    groups: dict[str, list[dict]] = {}
    for r in scored:
        groups.setdefault(entrant_of(r, track), []).append(r)

    def cluster(r):
        if ci_unit == "match":
            return r["_match"] or r["_session"]
        return r["_participant"]

    entries = []
    for g, rs in groups.items():
        sc: dict[str, dict] = {}
        for n in names:
            items = [(cluster(r), cell(r), float(r[n])) for r in rs if num(r.get(n)) is not None]
            covs = [num(r.get(f"{n}_coverage")) for r in rs]
            lo, hi, unit = _bootstrap(items, n_boot, rng, ci_unit, ci)
            sc[n] = dict(mean=_balanced([(c, v) for _, c, v in items]), lo=lo, hi=hi, n=len(items), ci_unit=unit,
                         coverage=float(np.mean([c for c in covs if c is not None])) if any(c is not None for c in covs) else None)
        ph = _pass_hat_k(rs, cell, success, success_threshold, max_k)
        costs = [num(r.get("llm_cost_usd")) for r in rs]
        costs = [c for c in costs if c is not None]
        entries.append(dict(
            entrant=g, n=len(rs), cells=len({cell(r) for r in rs}),
            participants=len({u for r in rs for u in r["_users"]}),
            solo=sum(1 for r in rs if r["_match"] is None), paired=sum(1 for r in rs if r["_match"] is not None),
            same_assistant=sum(1 for r in rs if r.get("_collapsed")),
            scores=sc, pass_hat_k=ph, success_rate=ph.get(1), cost_usd=float(np.mean(costs)) if costs else None,
        ))
    main = names[0]
    sign = -1.0 if directions.get(main, "higher") == "lower" else 1.0

    def key(e):
        m = e["scores"][main]["mean"]
        return (m is None, -sign * (m if m is not None else 0.0), e["entrant"])

    entries.sort(key=key)
    leader = entries[0]["scores"][main] if entries else None
    rank, prev = 0, None
    for i, e in enumerate(entries):
        m = e["scores"][main]["mean"]
        if m is None:
            e["rank"] = None
        else:
            if prev is None or not math.isclose(m, prev, abs_tol=1e-12):
                rank = i + 1
            e["rank"], prev = rank, m
        s = e["scores"][main]
        if sign > 0:
            tied = leader is not None and leader["lo"] is not None and s["hi"] is not None and s["hi"] >= leader["lo"]
        else:  # lower is better: tied when the CI reaches below the leader's upper end
            tied = leader is not None and leader["hi"] is not None and s["lo"] is not None and s["lo"] <= leader["hi"]
        e["tied_with_leader"] = bool(i > 0 and tied)
    n_paired = sum(1 for r in scored if r["_match"] is not None)
    if track == "han":
        cells = list(spec["cells"]) + ([] if stratum == "alone" else ["assistant"])
    elif stratum == "paired":
        cells = list(PAIRED_CELLS)
    elif stratum == "solo" or not n_paired:
        cells = list(spec["cells"])
    else:
        cells = list(spec["cells"]) + list(PAIRED_CELLS[1:])
    out = dict(
        track=track, track_title=spec["title"], board=board, entrant=spec["entrant"],
        entrant_title=spec["entrant_title"], ranked_by=main, scores=names, cells=cells, success=success,
        success_threshold=success_threshold, relative=relative, min_coverage=min_coverage,
        stratum=stratum, stratum_title=STRATUM_TITLES[stratum], pooled=stratum == "both", strata=strata,
        ci_unit=ci_unit,
        components={n: sorted(active.get(n, set())) for n in order},
        dropped_components={n: sorted({c.column for c in BY_NAME[n].components} - active.get(n, set())) for n in order},
        weight_share=(share := {n: _share(n, active, options) for n in order}),
        warnings=gate["warnings"] + _warnings(main, share, entries, game),
        directions={n: directions.get(n, "higher") for n in names},
        notes=_notes(track, stratum, ci_unit, n_paired, scored),
        reliability=dict(report=gate["source"], judges=gate["judges"], official=official,
                         left_out={n: sorted({c.column for c in BY_NAME[n].components} & gate["blocked"]) for n in order}),
        excluded=excluded, sessions=totals["sessions"], totals=totals, entries=entries,
    )
    if head_to_head and track == "hi":
        col = head_to_head if isinstance(head_to_head, str) else "human_advantage"
        # from every counted HI row, whatever the stratum shown (only Paired matches take part)
        every = kept if stratum in ("combined", "paired") else _filter(rows, track, include_practice,
                                                                       include_simulated)[0]
        out["head_to_head"] = _head_to_head(every, col)
    return out


def _notes(track: str, stratum: str, ci_unit: str, n_paired: int, scored: list[dict]) -> list[str]:
    out = []
    if track == "han" and stratum == "both":
        out.append("pooled: HAN agents against people with and without an Assistant; the official board is "
                   "'alone', and the cells keep the two apart (scenario × Assistant)")
    if track == "han" and stratum != "alone":
        out.append("vs_team cells are scenario × Assistant: the Assistant is a source of difficulty for the agent")
    if n_paired:
        if ci_unit == "participant":
            out.append("the two rows of a Paired match belong to two participants that the bootstrap resamples "
                       "independently, which slightly understates their dependence; ci_unit=match is the "
                       "sensitivity check")
        else:
            out.append("ci_unit=match: the bootstrap resamples matches (an AI game is its own match); within one "
                       "Assistant a match is one observation, so this ignores that a participant played several")
        same = sum(1 for r in scored if r.get("_collapsed"))
        if same:
            out.append(f"{same} same-Assistant match(es) counted once each, as the mean of the two rows")
    return out


def strata_boards(rows: list[dict], track: str = "hi", board: str = "outcome", **kw) -> dict[str, dict]:
    """A board per stratum, side by side: HI ``combined``, ``solo`` and ``paired``; HAN ``alone`` and
    ``vs_team`` (the pooled ``both`` only when asked for with :func:`leaderboard`)."""
    if track not in TRACKS:
        raise ValueError(f"unknown track {track!r}; use one of {', '.join(TRACKS)}")
    kw.pop("stratum", None)
    strata = [s for s in TRACKS[track]["strata"] if s != "both"]
    return {s: leaderboard(rows, track, board, stratum=s, **kw) for s in strata}


def _reliability_gate(reliability: Any, official: bool, row_judges: set[str]) -> dict:
    """The soft components a board must leave out, given a reliability report and the judges that
    scored the rows."""
    from hani2.config import get_env, settings_dir
    from hani2.evaluation.reliability import load_report, soft_columns

    src = reliability
    if src is None and official:
        src = get_env("evaluation.reliability.report", None)
        if src and not Path(str(src)).expanduser().is_absolute():
            src = settings_dir() / str(src)  # a relative path is read from the settings folder
    out: dict[str, Any] = dict(blocked=set(), warnings=[], source=None, judges=None)
    if src is None:
        if official:
            out["blocked"] = soft_columns()
            out["warnings"].append("official ranking without a judge reliability report: every language-model "
                                   "judged component is left out (run `hani2 replay judge-reliability`)")
        return out
    rep = load_report(src)
    soft = soft_columns()
    out["blocked"] = soft - set(rep.get("ready") or [])
    out["source"] = str(src) if not isinstance(src, dict) else "given"
    out["judges"] = rep.get("judges")
    other = sorted(row_judges - set(rep.get("judges") or []))
    if other:
        if official:
            out["blocked"] = soft
            out["warnings"].append(f"these sessions were judged by {', '.join(other)}, which the judge reliability "
                                   f"report ({' vs '.join(rep['judges'])}) did not check: every language-model judged "
                                   "component is left out of this official ranking")
        else:
            out["warnings"].append(f"these sessions were judged by {', '.join(other)}, but the judge reliability "
                                   f"report compares {' and '.join(rep['judges'])}")
    return out


def _share(name: str, active: dict[str, set[str]], options: dict | None) -> float:
    """The share of a score's full weight that the board uses (a score of
    scores: the weighted shares of its sub-scores)."""
    w = _weights(BY_NAME[name], options)
    total = sum(v for v in w.values() if v > 0)
    if total <= 0:
        return 0.0
    got = 0.0
    for c in BY_NAME[name].components:
        if w.get(c.column, 0) <= 0 or c.column not in active.get(name, set()):
            continue
        got += w[c.column] * (_share(c.column, active, options) if c.column in BY_NAME else 1.0)
    return got / total


def _warnings(main: str, share: dict[str, float], entries: list[dict], game: bool = False) -> list[str]:
    out = []
    if not game and share.get(main, 0) < LOW_WEIGHT_SHARE:
        out.append(f"{main} uses only {share.get(main, 0):.0%} of its weight: most of its components (questionnaire, "
                   "language-model judge) were not measured for every entrant, so the ranking rests on few components")
    means = [e["scores"][main]["mean"] for e in entries if e["scores"][main]["mean"] is not None]
    if len(means) >= 2 and len({round(m, 9) for m in means}) == 1:
        out.append(f"every entrant has the same {main}: the board does not separate them")
    return out


def leaderboards(rows: list[dict], track: str = "hi", **kw) -> dict[str, dict]:
    """Both boards of a track: ``{"outcome": ..., "interaction": ...}``."""
    return {b: leaderboard(rows, track, b, **kw) for b in BOARDS}
