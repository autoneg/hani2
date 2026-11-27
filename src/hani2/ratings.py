"""Leaderboard update rules: pooled, latest tournament, and continuous (recency-weighted) ratings.

A pure module (the Python standard library only, no HANI2 imports) so other sites — scmlweb's scripts,
for example — can import it, or shell out to ``python -m hani2.ratings`` (JSON lines in, JSON out).

Every method recomputes from scratch from time-stamped observations and an explicit ``now``, so a
board is reproducible::

    from hani2.ratings import Observation, method_from_config, rank

    obs = [Observation("team-a", "2026-11-01T10:00:00Z", 0.62), ...]
    est = method_from_config({"mode": "continuous"}).estimate(obs, now="2026-11-27T00:00:00Z")
    for e in rank(est):
        print(e.rank, e.entrant, e.mean, e.lower)

Modes (``mode``):

* ``pooled`` — every observation weighs the same (the mean and a normal interval).
* ``latest`` — only the newest tournament counts (``Observation.tournament``; the tournament whose
  latest observation is newest), and an entrant missing from it is not listed: the classic periodic /
  aperiodic competition whose every tournament replaces the board.
* ``continuous`` — every observation, recent ones weigh more, and nothing assumes the entrant's code
  is unchanged. ``method: kalman`` (default) is a local-level Kalman filter in wall-clock time with a
  two-sided CUSUM on its standardised innovations that flags a probable new version and widens the
  posterior; ``method: decayed`` is an exponentially time-decayed mean with shrinkage. A change of the
  declared ``version`` is a hint only: it widens the posterior like a detected change, and never splits
  an entrant.

Feed values that are already adjusted for what the entrant does not control (the scenario, its side,
the opponent): otherwise a change in the mix of games reads as a change in the agent.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Protocol

__all__ = ["Observation", "Estimate", "ChangePoint", "PooledMean", "LatestTournament", "DecayedMean",
           "KalmanLocalLevel", "Method", "method_from_config", "rank", "check_config", "MODES", "METHODS",
           "DAY"]

DAY = 86400.0
MODES = ("pooled", "latest", "continuous")
METHODS = ("kalman", "decayed")
#: the keys a configuration mapping may hold, with their defaults
CONFIG_DEFAULTS: dict[str, Any] = {
    "mode": "pooled", "method": "kalman", "z": 1.0, "rank_by": "lower",
    # kalman
    "drift_sd": 0.1, "noise_sd": None, "prior_sd": None, "change_k": 0.5, "change_h": 5.0,
    "reset_on_change": True, "version_hint": True,
    # decayed
    "half_life_days": 30.0, "shrinkage": 5.0,
}


def _ts(t: Any) -> float:
    """Seconds since the epoch from a number, a datetime or an ISO string (``Z`` allowed)."""
    if t is None:
        raise ValueError("an observation needs a time")
    if isinstance(t, (int, float)) and not isinstance(t, bool):
        return float(t)
    if isinstance(t, datetime):
        return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).timestamp()
    s = str(t).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    d = datetime.fromisoformat(s)
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()


def _iso(t: float | None) -> str | None:
    if t is None:
        return None
    return datetime.fromtimestamp(t, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class Observation:
    """One game's value for one entrant. ``version`` is what the entrant declared (a hint);
    ``tournament`` groups observations for ``mode: latest``; ``weight`` scales the game's evidence."""

    entrant: str
    time: Any
    value: float
    version: str | None = None
    tournament: str | None = None
    weight: float = 1.0

    @property
    def t(self) -> float:
        return _ts(self.time)


@dataclass
class ChangePoint:
    """A probable change of the entrant: detected (``cusum``) or declared (``version``)."""

    time: str | None
    kind: str
    before: float | None = None
    detail: str = ""


@dataclass
class Estimate:
    entrant: str
    mean: float | None
    sd: float | None
    lo: float | None
    hi: float | None
    n: int
    n_eff: float
    first_time: str | None = None
    last_time: str | None = None
    changes: list[ChangePoint] = field(default_factory=list)
    versions: list[str] = field(default_factory=list)
    rank: int | None = None
    #: what the ranking uses (``lower`` = ``mean − z·sd`` by default; see :func:`rank`)
    score: float | None = None

    @property
    def lower(self) -> float | None:
        return self.lo

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["lower"] = self.lo
        return d


class Method(Protocol):
    def estimate(self, observations: Iterable[Observation], now: Any = None) -> dict[str, Estimate]: ...


def _finite(obs: Iterable[Observation]) -> list[Observation]:
    out = []
    for o in obs:
        try:
            v = float(o.value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(v) and o.weight and o.weight > 0:
            out.append(o)
    return sorted(out, key=lambda o: (o.t, o.entrant))


def _by_entrant(obs: list[Observation]) -> dict[str, list[Observation]]:
    out: dict[str, list[Observation]] = {}
    for o in obs:
        out.setdefault(str(o.entrant), []).append(o)
    return out


def _versions(rs: list[Observation]) -> list[str]:
    return list(dict.fromkeys(str(o.version) for o in rs if o.version not in (None, "")))


def _mean_var(vals: list[float]) -> tuple[float, float]:
    m = sum(vals) / len(vals)
    v = sum((x - m) ** 2 for x in vals) / (len(vals) - 1) if len(vals) > 1 else 0.0
    return m, v


@dataclass
class PooledMean:
    """Every observation weighs the same: the mean and ``mean ± z·se``."""

    z: float = 1.96

    def estimate(self, observations: Iterable[Observation], now: Any = None) -> dict[str, Estimate]:
        out = {}
        for e, rs in _by_entrant(_finite(observations)).items():
            vals = [float(o.value) for o in rs]
            m, v = _mean_var(vals)
            se = math.sqrt(v / len(vals)) if len(vals) > 1 else None
            out[e] = Estimate(e, m, se, m - self.z * se if se is not None else None,
                              m + self.z * se if se is not None else None, len(vals), float(len(vals)),
                              _iso(rs[0].t), _iso(rs[-1].t), versions=_versions(rs))
        return out


@dataclass
class LatestTournament:
    """Only the newest tournament counts (the one whose latest observation is newest); observations
    without a tournament form one tournament together. ``inner`` scores it (default :class:`PooledMean`)."""

    inner: Any = None

    def latest(self, observations: Iterable[Observation]) -> str | None:
        last: dict[str | None, float] = {}
        for o in _finite(observations):
            last[o.tournament] = max(last.get(o.tournament, -math.inf), o.t)
        if not last:
            return None
        return max(last, key=lambda k: (last[k], str(k)))

    def estimate(self, observations: Iterable[Observation], now: Any = None) -> dict[str, Estimate]:
        obs = _finite(observations)
        t = self.latest(obs)
        return (self.inner or PooledMean()).estimate([o for o in obs if o.tournament == t], now)


@dataclass
class DecayedMean:
    """An exponentially time-decayed mean (half-life in days, from ``now``) shrunk toward the grand mean
    by ``shrinkage`` pseudo-games: ``(Σw·y + k·μ₀) / (Σw + k)``; the interval uses ``n_eff``."""

    half_life_days: float = 30.0
    shrinkage: float = 5.0
    z: float = 1.0

    def estimate(self, observations: Iterable[Observation], now: Any = None) -> dict[str, Estimate]:
        obs = _finite(observations)
        if not obs:
            return {}
        t_now = _ts(now) if now is not None else obs[-1].t
        grand, var_all = _mean_var([float(o.value) for o in obs])
        h = max(float(self.half_life_days), 1e-9) * DAY
        out = {}
        for e, rs in _by_entrant(obs).items():
            w = [o.weight * 2.0 ** (-max(0.0, t_now - o.t) / h) for o in rs]
            sw, sw2 = sum(w), sum(x * x for x in w)
            k = max(0.0, float(self.shrinkage))
            m = (sum(wi * float(o.value) for wi, o in zip(w, rs)) + k * grand) / (sw + k)
            n_eff = (sw * sw / sw2) if sw2 > 0 else 0.0
            vals = [float(o.value) for o in rs]
            _, v = _mean_var(vals)
            v = v if len(vals) > 2 else var_all
            sd = math.sqrt(v / (n_eff + k)) if (n_eff + k) > 0 else None
            out[e] = Estimate(e, m, sd, m - self.z * sd if sd is not None else None,
                              m + self.z * sd if sd is not None else None, len(rs), n_eff,
                              _iso(rs[0].t), _iso(rs[-1].t), versions=_versions(rs))
        return out


@dataclass
class KalmanLocalLevel:
    """A local-level Kalman filter per entrant, in wall-clock time, with a CUSUM change flag.

    ``y_t = μ_t + ε`` (``Var ε = noise_sd²``) and ``μ_t = μ_{t−1} + η`` with ``Var η = drift_sd² · Δt/30 days``.
    The prior is the grand mean with ``prior_sd`` (default: the between-entrant spread, at least
    ``drift_sd``); ``noise_sd`` defaults to the pooled within-entrant SD. Between the last game and
    ``now`` the posterior widens with the drift, so an idle entrant grows uncertain.

    A two-sided CUSUM on the standardised innovations (``change_k``, ``change_h``) flags a probable
    change; with ``reset_on_change`` the posterior variance goes back to at least the prior's, so the
    estimate re-learns within a few games. A change of the declared version does the same when
    ``version_hint`` is on (it never splits the entrant)."""

    drift_sd: float = 0.1
    noise_sd: float | None = None
    prior_sd: float | None = None
    z: float = 1.0
    change_k: float = 0.5
    change_h: float = 5.0
    reset_on_change: bool = True
    version_hint: bool = True

    def _params(self, obs: list[Observation]) -> tuple[float, float, float]:
        vals = [float(o.value) for o in obs]
        grand, var_all = _mean_var(vals)
        groups = _by_entrant(obs)
        within, dof, means = 0.0, 0, []
        for rs in groups.values():
            vs = [float(o.value) for o in rs]
            m, v = _mean_var(vs)
            means.append(m)
            if len(vs) > 1:
                within += v * (len(vs) - 1)
                dof += len(vs) - 1
        noise = self.noise_sd if self.noise_sd is not None else (
            math.sqrt(within / dof) if dof > 0 else (math.sqrt(var_all) if var_all > 0 else 0.2))
        noise = max(float(noise), 1e-6)
        if self.prior_sd is not None:
            prior = float(self.prior_sd)
        else:
            between = _mean_var(means)[1] if len(means) > 1 else 0.0
            prior = math.sqrt(between) if between > 0 else noise
            prior = max(prior, float(self.drift_sd), 1e-6)
        return grand, noise, prior

    def estimate(self, observations: Iterable[Observation], now: Any = None) -> dict[str, Estimate]:
        obs = _finite(observations)
        if not obs:
            return {}
        t_now = _ts(now) if now is not None else obs[-1].t
        grand, noise, prior = self._params(obs)
        r, p0 = noise * noise, prior * prior
        q_per_s = (float(self.drift_sd) ** 2) / (30 * DAY)
        out = {}
        for e, rs in _by_entrant(obs).items():
            mu, p, t_prev = grand, p0, rs[0].t
            s_hi = s_lo = 0.0
            n_eff = 0.0
            changes: list[ChangePoint] = []
            version = None
            for o in rs:
                p += q_per_s * max(0.0, o.t - t_prev)
                t_prev = o.t
                if self.version_hint and o.version not in (None, ""):
                    if version is not None and str(o.version) != version:
                        changes.append(ChangePoint(_iso(o.t), "version", mu, f"{version} → {o.version}"))
                        p = max(p, p0)
                        s_hi = s_lo = 0.0
                    version = str(o.version)
                rr = r / max(float(o.weight), 1e-9)
                y = float(o.value)
                innov = y - mu
                s_var = p + rr
                zt = innov / math.sqrt(s_var)
                s_hi = max(0.0, s_hi + zt - self.change_k)
                s_lo = max(0.0, s_lo - zt - self.change_k)
                gain = p / s_var
                mu = mu + gain * innov
                p = (1 - gain) * p
                n_eff = n_eff * (1 - gain) + 1.0  # an index of how much the estimate rests on its games
                if self.change_h and (s_hi > self.change_h or s_lo > self.change_h):
                    changes.append(ChangePoint(_iso(o.t), "cusum", mu, "up" if s_hi > self.change_h else "down"))
                    s_hi = s_lo = 0.0
                    if self.reset_on_change:
                        p = max(p, p0)
            p += q_per_s * max(0.0, t_now - t_prev)
            sd = math.sqrt(p)
            out[e] = Estimate(e, mu, sd, mu - self.z * sd, mu + self.z * sd, len(rs), r / p if p > 0 else n_eff,
                              _iso(rs[0].t), _iso(rs[-1].t), changes=changes, versions=_versions(rs))
        return out


def check_config(cfg: Any) -> list[str]:
    """What is wrong with an ``update`` configuration (a mode name or a mapping); ``[]``: nothing."""
    if cfg is None:
        return []
    if isinstance(cfg, str):
        return [] if cfg in MODES else [f"update must be one of {', '.join(MODES)} (got {cfg!r})"]
    if not isinstance(cfg, dict):
        return ["update must be a mode name or a mapping like {mode: continuous}"]
    out = []
    unknown = sorted(set(cfg) - set(CONFIG_DEFAULTS))
    if unknown:
        out.append(f"update: unknown key(s) {', '.join(unknown)}; use {', '.join(CONFIG_DEFAULTS)}")
    if cfg.get("mode", "pooled") not in MODES:
        out.append(f"update.mode must be one of {', '.join(MODES)} (got {cfg.get('mode')!r})")
    if cfg.get("method", "kalman") not in METHODS:
        out.append(f"update.method must be one of {', '.join(METHODS)} (got {cfg.get('method')!r})")
    if cfg.get("rank_by", "lower") not in ("lower", "mean"):
        out.append(f"update.rank_by must be lower or mean (got {cfg.get('rank_by')!r})")
    for k in ("z", "drift_sd", "change_k", "change_h", "half_life_days", "shrinkage"):
        v = cfg.get(k)
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0):
            out.append(f"update.{k} must be a number ≥ 0 (got {v!r})")
    for k in ("noise_sd", "prior_sd"):
        v = cfg.get(k)
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0):
            out.append(f"update.{k} must be a number > 0 or null (got {v!r})")
    if cfg.get("half_life_days") == 0:
        out.append("update.half_life_days must be > 0")
    for k in ("reset_on_change", "version_hint"):
        if cfg.get(k) is not None and not isinstance(cfg[k], bool):
            out.append(f"update.{k} must be true or false")
    return out


def normalise_config(cfg: Any) -> dict[str, Any]:
    """The configuration with its defaults (a mode name becomes ``{mode: <name>}``)."""
    given = {"mode": cfg} if isinstance(cfg, str) else dict(cfg or {})
    return {**CONFIG_DEFAULTS, **{k: v for k, v in given.items()
                                  if k in CONFIG_DEFAULTS and (v is not None or k in ("noise_sd", "prior_sd"))}}


def method_from_config(cfg: Any) -> Method:
    """The method of a configuration (see :data:`CONFIG_DEFAULTS`); raises ``ValueError`` if invalid."""
    problems = check_config(cfg)
    if problems:
        raise ValueError("; ".join(problems))
    c = normalise_config(cfg)
    if c["mode"] == "pooled":
        return PooledMean()
    if c["mode"] == "latest":
        return LatestTournament(PooledMean())
    if c["method"] == "decayed":
        return DecayedMean(half_life_days=float(c["half_life_days"]), shrinkage=float(c["shrinkage"]), z=float(c["z"]))
    return KalmanLocalLevel(drift_sd=float(c["drift_sd"]), noise_sd=c["noise_sd"], prior_sd=c["prior_sd"],
                            z=float(c["z"]), change_k=float(c["change_k"]), change_h=float(c["change_h"]),
                            reset_on_change=bool(c["reset_on_change"]), version_hint=bool(c["version_hint"]))


def rank(estimates: dict[str, Estimate] | Iterable[Estimate], by: str = "lower",
         direction: str = "higher") -> list[Estimate]:
    """The estimates in rank order (best first), each with ``rank`` and ``score`` set. ``by``: ``lower``
    (the conservative ``mean − z·sd``, falling back to the mean) or ``mean``; equal scores share a rank.
    ``direction="lower"`` ranks smaller values first (then the conservative bound is the upper one)."""
    items = list(estimates.values() if isinstance(estimates, dict) else estimates)
    sign = -1.0 if direction == "lower" else 1.0
    for e in items:
        if e.mean is None:
            e.score = None
        elif by == "lower":
            b = e.lo if sign > 0 else e.hi
            e.score = b if b is not None else e.mean
        else:
            e.score = e.mean
    items.sort(key=lambda e: (e.score is None, -sign * (e.score or 0.0), e.entrant))
    r, prev = 0, None
    for i, e in enumerate(items):
        if e.score is None:
            e.rank = None
            continue
        if prev is None or not math.isclose(e.score, prev, abs_tol=1e-12):
            r = i + 1
        e.rank, prev = r, e.score
    return items


def _main(argv: list[str] | None = None) -> int:
    """``python -m hani2.ratings [config-json] [now] < observations.jsonl``: prints the ranked estimates as
    JSON. Each input line is ``{"entrant", "time", "value", "version"?, "tournament"?, "weight"?}``."""
    argv = list(sys.argv[1:] if argv is None else argv)
    cfg = json.loads(argv[0]) if argv else {"mode": "continuous"}
    now = argv[1] if len(argv) > 1 else None
    obs = []
    for line in sys.stdin:
        line = line.strip()
        if line:
            d = json.loads(line)
            obs.append(Observation(str(d["entrant"]), d["time"], float(d["value"]), d.get("version"),
                                   d.get("tournament"), float(d.get("weight", 1.0))))
    c = normalise_config(cfg)
    ranked = rank(method_from_config(cfg).estimate(obs, now), by=c["rank_by"])
    json.dump({"config": c, "now": now, "entries": [e.to_dict() for e in ranked]}, sys.stdout, indent=1, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
