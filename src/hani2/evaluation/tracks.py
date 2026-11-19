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
from hani2.evaluation.scores import BY_NAME, _weights, score_row

#: a board warns when its ranked score uses less than this share of the score's full weight
LOW_WEIGHT_SHARE = 0.5

TRACKS: dict[str, dict[str, Any]] = {
    "han": dict(
        title="Human-Agent Negotiation", entrant="opponent", entrant_title="Opponent", cells=("scenario",),
        boards={"outcome": ["han_outcome"], "interaction": ["han_interaction"]},
        # an Opponent failure is the entrant's fault (it scores 0); a system failure is not
        exclude_status={"erred": "system failure"},
    ),
    "hi": dict(
        title="Hybrid Intelligence", entrant="support_agent", entrant_title="Assistant", cells=("scenario", "opponent"),
        boards={"outcome": ["hi_outcome"], "interaction": ["hi_interaction", "hi_assistant", "hi_team"]},
        # neither an Opponent failure nor a system failure is the Assistant's fault
        exclude_status={"erred": "system failure", "agent_failed": "opponent failure"},
    ),
}
BOARDS = ("outcome", "interaction")


def _in_track(r: dict, track: str) -> bool:
    has = str(r.get("support_agent") or "none") != "none"
    return has if track == "hi" else not has


def entrant_of(r: dict, track: str) -> str:
    if track == "hi":
        name, model = str(r.get("support_agent") or "none"), r.get("support_model")
        return f"{name} · {model}" if model else name
    return str(r.get("opponent") or "?")


def _filter(rows: list[dict], track: str, include_practice: bool,
            include_simulated: bool = False) -> tuple[list[dict], dict[str, int]]:
    spec = TRACKS[track]
    kept, excluded = [], {}

    def drop(reason):
        excluded[reason] = excluded.get(reason, 0) + 1

    for r in rows:
        if not _in_track(r, track):
            continue
        if r.get("practice") and not include_practice:
            drop("practice")
            continue
        if r.get("mode") == "simulated" and not include_simulated:
            drop("simulated participant")  # never ranked with human sessions
            continue
        status = r.get("status")
        if status is None and r.get("agreement") is None:
            drop("abandoned")
            continue
        if status in spec["exclude_status"]:
            drop(spec["exclude_status"][status])
            continue
        kept.append(r)
    return kept, excluded


def _active_components(rows: list[dict], track: str, names: list[str], min_coverage: float,
                       blocked: set[str] | None = None) -> dict[str, set[str]]:
    """Per score, the components present in at least ``min_coverage`` of the
    sessions of every entrant (so every entrant is scored on the same things);
    ``blocked`` columns are never used."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(entrant_of(r, track), []).append(r)
    out: dict[str, set[str]] = {}
    for n in names:
        s = BY_NAME[n]
        keep = set()
        for c in s.components:
            if c.column in BY_NAME:  # a score of scores: keep it if that score has components
                if out.get(c.column):
                    keep.add(c.column)
                continue
            if blocked and c.column in blocked:
                continue
            if groups and all(sum(1 for r in rs if num(r.get(c.column)) is not None) / len(rs) >= min_coverage
                              for rs in groups.values()):
                keep.add(c.column)
        out[n] = keep
    return out


def _balanced(vals: list[tuple[tuple, float]]) -> float | None:
    cells: dict[tuple, list[float]] = {}
    for c, v in vals:
        cells.setdefault(c, []).append(v)
    return float(np.mean([np.mean(v) for v in cells.values()])) if cells else None


def _bootstrap(items: list[tuple[str, tuple, float]], n_boot: int, rng: np.random.Generator) -> tuple[float | None, float | None, str]:
    """95 % percentile CI of the balanced mean, resampling participants (or
    sessions when there is only one participant)."""
    users = sorted({u for u, _, _ in items})
    unit = "participant" if len(users) >= 2 else "session"
    clusters: dict[Any, list[tuple[tuple, float]]] = {}
    for i, (u, c, v) in enumerate(items):
        clusters.setdefault(u if unit == "participant" else i, []).append((c, v))
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
    return float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5)), unit


def _pass_hat_k(rows: list[dict], cells: tuple, success: str, threshold: float | None, max_k: int) -> dict[int, float]:
    from hani2.evaluation import pass_hat_k

    per: dict[tuple, list[bool]] = {}
    for r in rows:
        v = num(r.get(success))
        if v is None:
            continue
        per.setdefault(tuple(str(r.get(c)) for c in cells), []).append(v >= (threshold if threshold is not None else 1 - 1e-9))
    if not per:
        return {}
    kmax = min(max_k, min(len(v) for v in per.values()))
    return {k: float(np.mean([pass_hat_k(len(v), sum(v), k) for v in per.values()])) for k in range(1, kmax + 1)}


def leaderboard(rows: list[dict], track: str = "hi", board: str = "outcome", *, options: dict | None = None,
                success: str | None = None, success_threshold: float | None = None, max_k: int = 4,
                min_coverage: float = 0.5, relative: bool = False, n_boot: int = 1000, seed: int = 0,
                include_practice: bool = False, reliability: Any = None, official: bool = False,
                include_simulated: bool = False) -> dict:
    """Rank the entrants of ``track`` (``han`` or ``hi``) on ``board``
    (``outcome`` or ``interaction``) from evaluated rows (``evaluate_*()["rows"]``).

    ``success`` is the pass^k criterion (default: in HI ``task_success`` when
    the scenarios define criteria, else ``agreement``; in HAN ``agreement``). ``relative`` subtracts each
    cell's mean over all entrants first (removes the difficulty of the
    scenarios and opponents when entrants played different cells).

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
    if board not in BOARDS:
        raise ValueError(f"unknown board {board!r}; use one of {', '.join(BOARDS)}")
    spec = TRACKS[track]
    names: list[str] = list(spec["boards"][board])
    kept, excluded = _filter(rows, track, include_practice, include_simulated)
    # the sub-scores first, so a score of scores knows which of them exist
    order = [s for s in BY_NAME if s in names or any(c.column == s for n in names for c in BY_NAME[n].components)]
    gate = _reliability_gate(reliability, official, {str(r["judge_model"]) for r in kept if r.get("judge_model")})
    active = _active_components(kept, track, order, min_coverage, gate["blocked"])
    scored = []
    for r in kept:
        r2 = dict(r)
        r2.update(score_row(r, options, only=active))
        scored.append(r2)
    if success is None:  # scenario criteria are written for the Human side: they define success in HI only
        success = "task_success" if track == "hi" and any(num(r.get("task_success")) is not None for r in scored) \
            else "agreement"
    cells = spec["cells"]

    def cell(r):
        return tuple(str(r.get(c)) for c in cells)

    if relative:
        for n in names:
            per: dict[tuple, list[float]] = {}
            for r in scored:
                if num(r.get(n)) is not None:
                    per.setdefault(cell(r), []).append(float(r[n]))
            means = {c: float(np.mean(v)) for c, v in per.items()}
            for r in scored:
                if num(r.get(n)) is not None:
                    r[n] = float(r[n]) - means[cell(r)]
    rng = np.random.default_rng(seed)
    groups: dict[str, list[dict]] = {}
    for r in scored:
        groups.setdefault(entrant_of(r, track), []).append(r)
    entries = []
    for g, rs in groups.items():
        sc: dict[str, dict] = {}
        for n in names:
            items = [(str(r.get("user")), cell(r), float(r[n])) for r in rs if num(r.get(n)) is not None]
            covs = [num(r.get(f"{n}_coverage")) for r in rs]
            lo, hi, unit = _bootstrap(items, n_boot, rng)
            sc[n] = dict(mean=_balanced([(c, v) for _, c, v in items]), lo=lo, hi=hi, n=len(items), ci_unit=unit,
                         coverage=float(np.mean([c for c in covs if c is not None])) if any(c is not None for c in covs) else None)
        ph = _pass_hat_k(rs, cells, success, success_threshold, max_k)
        costs = [num(r.get("llm_cost_usd")) for r in rs]
        costs = [c for c in costs if c is not None]
        entries.append(dict(
            entrant=g, n=len(rs), cells=len({cell(r) for r in rs}), participants=len({str(r.get("user")) for r in rs}),
            scores=sc, pass_hat_k=ph, success_rate=ph.get(1), cost_usd=float(np.mean(costs)) if costs else None,
        ))
    main = names[0]

    def key(e):
        m = e["scores"][main]["mean"]
        return (m is None, -(m if m is not None else 0.0), e["entrant"])

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
        e["tied_with_leader"] = bool(
            i > 0 and leader is not None and leader["lo"] is not None and s["hi"] is not None and s["hi"] >= leader["lo"])
    return dict(
        track=track, track_title=spec["title"], board=board, entrant=spec["entrant"],
        entrant_title=spec["entrant_title"], ranked_by=main, scores=names, cells=list(cells), success=success,
        success_threshold=success_threshold, relative=relative, min_coverage=min_coverage,
        components={n: sorted(active.get(n, set())) for n in order},
        dropped_components={n: sorted({c.column for c in BY_NAME[n].components} - active.get(n, set())) for n in order},
        weight_share=(share := {n: _share(n, active, options) for n in order}),
        warnings=gate["warnings"] + _warnings(main, share, entries),
        reliability=dict(report=gate["source"], judges=gate["judges"], official=official,
                         left_out={n: sorted({c.column for c in BY_NAME[n].components} & gate["blocked"]) for n in order}),
        excluded=excluded, sessions=len(kept), entries=entries,
    )


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


def _warnings(main: str, share: dict[str, float], entries: list[dict]) -> list[str]:
    out = []
    if share.get(main, 0) < LOW_WEIGHT_SHARE:
        out.append(f"{main} uses only {share.get(main, 0):.0%} of its weight: most of its components (questionnaire, "
                   "language-model judge) were not measured for every entrant, so the ranking rests on few components")
    means = [e["scores"][main]["mean"] for e in entries if e["scores"][main]["mean"] is not None]
    if len(means) >= 2 and len({round(m, 9) for m in means}) == 1:
        out.append(f"every entrant has the same {main}: the board does not separate them")
    return out


def leaderboards(rows: list[dict], track: str = "hi", **kw) -> dict[str, dict]:
    """Both boards of a track: ``{"outcome": ..., "interaction": ...}``."""
    return {b: leaderboard(rows, track, b, **kw) for b in BOARDS}
