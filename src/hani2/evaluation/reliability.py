"""Judge reliability: may the language-model judged components of the combined scores be ranked on?

The interaction scores of the competition tracks (``han_interaction``, ``hi_assistant``,
``hi_team``, see :mod:`hani2.evaluation.scores`) mix log and questionnaire components with
*soft* ones that a language model judges (``jo_overall``, ``ja_helpfulness``, ``assertions_met``,
``assistant_critical_errors``, …). Before such a soft component is used in an official ranking:

1. **Inter-judge agreement** — two different judge models, judging the same recordings, agree on
   it (Krippendorff's α, chance-corrected, on the value as it enters the score; plus Spearman's ρ,
   the mean difference and, for 1–7 ratings, exact and within-one agreement);
2. **Judge–questionnaire correlation** — where the participants answered a matching question
   (e.g. ``jo_human_likeness`` and ``scale_opponent_humanlike_norm``), the judges go with the
   participants' own view (Spearman's ρ).

The report also shows what the choice of judge does to the scores themselves (agreement of every
combined score computed with each judge) and to the leaderboards (the entrants' order under each
judge). :func:`hani2.evaluation.leaderboard` takes the report (``reliability=``) and leaves out the
soft components that did not pass; ``official=True`` leaves out every soft component without one.

Use it from Python::

    from hani2.evaluation import judge_reliability
    from hani2.evaluation.reliability import reliability_markdown
    rep = judge_reliability(["results/"], judges=["openai:gpt-5", "anthropic:claude-sonnet-5-5"])
    print(reliability_markdown(rep))

or ``hani2 replay judge-reliability results/ --judge openai:gpt-5 --judge anthropic:claude-sonnet-5-5``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

#: judge column ↔ questionnaire columns that ask the participant about the same thing
#: (the ``_norm`` columns the scores use; the rank correlation is the same as on the raw scale)
DEFAULT_PAIRS: dict[str, list[str]] = {
    "jo_human_likeness": ["scale_opponent_humanlike_norm"],
    "jo_overall": ["scale_opponent_kindness_norm", "scale_opponent_intelligence_norm", "scale_relationship_norm"],
    "jo_kindness": ["scale_opponent_kindness_norm"],
    "jo_intelligence": ["scale_opponent_intelligence_norm"],
    "ja_overall": ["scale_ueq_pragmatic_norm", "scale_tam_usefulness_norm", "scale_intention_to_use_norm"],
    "ja_helpfulness": ["scale_tam_usefulness_norm"],
    "ja_user_understanding": ["scale_felt_heard_norm"],
    "ja_communication": ["scale_ueq_pragmatic_norm"],
}

#: Krippendorff's α below which conclusions should not be drawn (Krippendorff 2004: 0.667
#: tentative, 0.8 reliable)
ALPHA_MIN = 0.667
RHO_MIN = 0.3
P_MAX = 0.05
MIN_N = 10



# --------------------------------------------------------------------------- #
# Statistics                                                                   #
# --------------------------------------------------------------------------- #
def krippendorff_alpha(units: Iterable[Sequence[Any]], level: str = "interval") -> float | None:
    """Krippendorff's α for reliability data given per unit (the values the coders gave it;
    ``None`` = missing). ``level``: ``nominal``, ``ordinal`` or ``interval``. ``None`` when there
    is no variation at all (α is undefined) or fewer than two pairable values."""
    us = [[v for v in u if v is not None and not (isinstance(v, float) and math.isnan(v))] for u in units]
    us = [u for u in us if len(u) >= 2]
    if not us:
        return None
    values = sorted({v for u in us for v in u}, key=lambda x: (str(type(x)), x))
    idx = {v: i for i, v in enumerate(values)}
    k = len(values)
    o = np.zeros((k, k))
    for u in us:
        m = len(u)
        for i, a in enumerate(u):
            for j, b in enumerate(u):
                if i != j:
                    o[idx[a], idx[b]] += 1.0 / (m - 1)
    nc = o.sum(axis=1)
    n = nc.sum()
    if level == "nominal":
        d = 1.0 - np.eye(k)
    elif level == "ordinal":
        cum = np.cumsum(nc)
        d = np.zeros((k, k))
        for a in range(k):
            for b in range(k):
                lo, hi = min(a, b), max(a, b)
                d[a, b] = (cum[hi] - (cum[lo - 1] if lo > 0 else 0.0) - (nc[a] + nc[b]) / 2.0) ** 2
    elif level == "interval":
        v = np.array([float(x) for x in values])
        d = (v[:, None] - v[None, :]) ** 2
    else:
        raise ValueError(f"unknown level {level!r}")
    do = float((o * d).sum()) / n
    de = float((np.outer(nc, nc) * d).sum()) / (n * (n - 1))
    if de <= 1e-12:
        return None
    return 1.0 - do / de


def _ranks(x: np.ndarray) -> np.ndarray:
    order = np.argsort(x, kind="mergesort")
    r = np.empty(len(x))
    r[order] = np.arange(1, len(x) + 1)
    for v in np.unique(x):  # average ranks for ties
        m = x == v
        r[m] = r[m].mean()
    return r


def spearman(a: Any, b: Any) -> tuple[float | None, float | None]:
    """Spearman's ρ and its two-sided p-value (t approximation); ``(None, None)`` when either
    side is constant or there are fewer than three pairs."""
    x, y = np.asarray(a, float), np.asarray(b, float)
    if len(x) < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return None, None
    rx, ry = _ranks(x), _ranks(y)
    rho = float(np.corrcoef(rx, ry)[0, 1])
    n = len(x)
    if abs(rho) >= 1.0:
        return rho, 0.0
    t = rho * math.sqrt((n - 2) / (1 - rho * rho))
    try:
        from scipy import stats

        p = float(2 * stats.t.sf(abs(t), n - 2))
    except Exception:  # pragma: no cover - scipy missing
        p = math.erfc(abs(t) / math.sqrt(2))
    return rho, p




# --------------------------------------------------------------------------- #
# Components                                                                   #
# --------------------------------------------------------------------------- #
def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    return v if math.isfinite(v) else None


def soft_columns() -> set[str]:
    """Every column of a soft (language-model judged) metric."""
    from hani2.evaluation.base import REGISTRY

    return {c.name for m in REGISTRY.values() if m.kind == "soft" for c in m.columns if "<" not in c.name}


def score_components(all_soft: bool = False, options: dict | None = None) -> list[dict]:
    """The soft components of the combined scores (``all_soft``: every soft column), each with its
    measurement level, normaliser and the scores (with weights) that use it."""
    from hani2.evaluation.base import REGISTRY
    from hani2.evaluation.scores import SCORES, _weights

    uses: dict[str, list[dict]] = {}
    norm: dict[str, str] = {}
    for s in SCORES:
        w = _weights(s, options)
        for c in s.components:
            if w.get(c.column, 0) > 0:
                uses.setdefault(c.column, []).append(dict(score=s.name, track=s.track, weight=w[c.column]))
                norm.setdefault(c.column, c.norm)
    out = []
    for m in REGISTRY.values():
        if m.kind != "soft":
            continue
        for c in m.columns:
            if "<" in c.name or (not all_soft and c.name not in uses):
                continue
            rng = str(c.range or "")
            level = "nominal" if rng == "category" else "ordinal" if rng == "1–7" else "interval"
            out.append(dict(name=c.name, metric=m.name, title=c.title, level=level, range=rng,
                            norm=norm.get(c.name), scores=uses.get(c.name, []), in_score=c.name in uses))
    return out


def _entered(comp: dict, v: Any) -> Any:
    """The value as it enters the score (normalised for interval components)."""
    from hani2.evaluation.scores import NORMALISERS

    if comp["level"] == "nominal":
        return v if v is not None and v != "" else None
    x = _num(v)
    if x is None or comp["level"] == "ordinal" or not comp.get("norm"):
        return x
    return float(NORMALISERS[comp["norm"]][2](x))


def _agreement(units: list[list[Any]], level: str) -> dict:
    """α, ρ, mean difference and exact / within-one agreement of paired values."""
    judged = [u for u in units if any(v is not None for v in u)]
    both = [u for u in units if all(v is not None for v in u)]
    out: dict[str, Any] = dict(n=len(both), dropped=len(judged) - len(both), alpha=krippendorff_alpha(both, level))
    if not both:
        return out
    if level == "nominal":
        out["exact"] = float(np.mean([len(set(map(str, u))) == 1 for u in both]))
        return out
    a, b = np.array([u[0] for u in both], float), np.array([u[1] for u in both], float)
    out["rho"], out["rho_p"] = spearman(a, b)
    out["mean_difference"] = float(np.mean(b - a))
    if level == "ordinal":
        out["exact"] = float(np.mean(a == b))
        out["within_one"] = float(np.mean(np.abs(a - b) <= 1))
    return out


# --------------------------------------------------------------------------- #
# The report                                                                   #
# --------------------------------------------------------------------------- #
def _same(a, b) -> bool:
    return (a.connection.name if a.connection else "", a.provider, a.model, a.entry.params if a.entry else {}) == \
        (b.connection.name if b.connection else "", b.provider, b.model, b.entry.params if b.entry else {})


def judge_reliability(paths: Iterable[str | Path] | None = None, judges: Sequence[Any] = (), *,
                      recordings: list | None = None, all_soft: bool = False, refresh: bool = False,
                      options: dict | None = None, pairs: dict | None = None,
                      alpha_min: float = ALPHA_MIN, rho_min: float = RHO_MIN, p_max: float = P_MAX,
                      min_n: int = MIN_N, require_validation: bool = False, boards: bool = True) -> dict:
    """Evaluate the recordings once per judge model and report, per soft score component, the
    inter-judge agreement and the judge–questionnaire correlation, with a verdict on whether the
    component may be used in an official ranking; then the agreement of every combined score and
    the leaderboards under each judge.

    ``judges``: two or more model specs (``"provider:model"`` / ``"connection:model"`` / mappings),
    each used alone (no chain fallback). ``recordings``: ``(key, Recording)`` pairs instead of
    ``paths``. ``all_soft``: also report soft columns that no score uses. ``pairs``: judge column →
    questionnaire columns (default :data:`DEFAULT_PAIRS`, or env.json
    ``evaluation.reliability.pairs``). A component is *ready* when α ≥ ``alpha_min`` on at least
    ``min_n`` sessions and — where it has a questionnaire counterpart with ``min_n`` answers — the
    judges' mean correlates with it (ρ ≥ ``rho_min``, p < ``p_max``). With ``require_validation``
    a component without a counterpart is never ready. ``boards``: also rank both tracks with each
    judge. With more than two judges α uses all of them; ρ, the mean difference and the boards
    compare the first two."""
    from hani2.config import get_env
    from hani2.evaluation import evaluate_many, load_paths
    from hani2.evaluation.llm_judge import pin_judge
    from hani2.evaluation.scores import BY_NAME, SCORES

    if len(judges) < 2:
        raise ValueError("give at least two judge models")
    resolved = [pin_judge(j) for j in judges]
    for i in range(len(resolved)):
        for j in range(i):
            if _same(resolved[i], resolved[j]):
                raise ValueError(f"judges {i + 1} and {j + 1} are the same model ({resolved[i].short()})")
    recs = recordings if recordings is not None else load_paths(paths or [])
    comps = score_components(all_soft, options)
    pairs = pairs if pairs is not None else (get_env("evaluation.reliability.pairs", None) or DEFAULT_PAIRS)

    # every judge's rows: every default metric (so the scores are computed) with the soft ones judged
    per_judge: list[dict[str, dict]] = []
    errors: dict[str, dict] = {}
    for res in resolved:
        ev = evaluate_many(recs, None, use_llm=True, refresh=refresh, options=options, judge=res)
        per_judge.append({r["key"]: r for r in ev["rows"]})
        if ev["errors"]:
            errors[res.short()] = ev["errors"]
    keys = [k for k, _ in recs]
    qrows = per_judge[0]  # the questionnaire does not depend on the judge

    def in_track(k: str, tracks: set[str]) -> bool:
        # a component is measured on the sessions of the tracks whose scores use it
        if not tracks:
            return True
        has = str((qrows.get(k) or {}).get("support_agent") or "none") != "none"
        return ("hi" in tracks and has) or ("han" in tracks and not has)

    out = []
    for c in comps:
        tracks = {u["track"] for u in c["scores"]}
        ks = [k for k in keys if in_track(k, tracks)]
        units = [[_entered(c, pj.get(k, {}).get(c["name"])) for pj in per_judge] for k in ks]
        if not any(v is not None for u in units for v in u):
            continue
        row: dict[str, Any] = dict(c, tracks=sorted(tracks), **_agreement(units, c["level"]))
        qs = []
        for qc in (pairs.get(c["name"]) or []) if c["level"] != "nominal" else []:
            means, qv, per = [], [], [[] for _ in per_judge]
            for k, u in zip(ks, units):
                h = _num((qrows.get(k) or {}).get(qc))
                if h is None or any(v is None for v in u):
                    continue
                means.append(float(np.mean([float(v) for v in u if v is not None])))
                qv.append(h)
                for i, v in enumerate(u):
                    per[i].append((v, h))
            rho, p = spearman(means, qv)
            qs.append(dict(questionnaire=qc, n=len(qv), rho=rho, p=p,
                           per_judge=[spearman([x for x, _ in pp], [y for _, y in pp])[0] for pp in per]))
        row["questionnaire"] = qs
        row["verdict"], row["ready"] = _verdict(row, alpha_min, rho_min, p_max, min_n, require_validation)
        out.append(row)

    # the combined scores with each judge (only the soft components differ)
    soft = {c["name"] for c in comps}
    score_rows = []
    for s in SCORES:
        if not _uses_soft(s.name, soft, BY_NAME):
            continue
        units = [[_num(pj.get(k, {}).get(s.name)) for pj in per_judge] for k in keys]
        if any(v is not None for u in units for v in u):
            score_rows.append(dict(name=s.name, title=s.title, track=s.track, **_agreement(units, "interval")))

    board_rows = _compare_boards(per_judge, options) if boards else []
    ready = [r["name"] for r in out if r["ready"]]
    return dict(judges=[r.short() for r in resolved], recordings=len(recs), components=out, scores=score_rows,
                boards=board_rows, errors=errors, ready=ready,
                not_ready=[r["name"] for r in out if not r["ready"]],
                thresholds=dict(alpha_min=alpha_min, rho_min=rho_min, p_max=p_max, min_n=min_n,
                                require_validation=require_validation))


def _uses_soft(name: str, soft: set[str], by_name: dict) -> bool:
    return any(c.column in soft or (c.column in by_name and _uses_soft(c.column, soft, by_name))
               for c in by_name[name].components)


def _compare_boards(per_judge: list[dict[str, dict]], options: dict | None) -> list[dict]:
    """Rank both tracks' interaction boards with the first two judges and compare the orders."""
    from hani2.evaluation.tracks import TRACKS, leaderboard

    out = []
    a_rows, b_rows = list(per_judge[0].values()), list(per_judge[1].values())
    for track in TRACKS:
        try:
            la = leaderboard(a_rows, track, "interaction", options=options, n_boot=0)
            lb = leaderboard(b_rows, track, "interaction", options=options, n_boot=0)
        except Exception as e:  # noqa: BLE001
            out.append(dict(track=track, error=f"{type(e).__name__}: {e}"))
            continue
        main = la["ranked_by"]
        ma = {e["entrant"]: e["scores"][main]["mean"] for e in la["entries"]}
        mb = {e["entrant"]: e["scores"][main]["mean"] for e in lb["entries"]}
        common = [g for g in ma if ma[g] is not None and mb.get(g) is not None]
        if not common:
            continue
        rho = spearman([ma[g] for g in common], [mb[g] for g in common])[0] if len(common) >= 3 else None
        lead_a = next((e["entrant"] for e in la["entries"] if e["rank"] == 1), None)
        lead_b = next((e["entrant"] for e in lb["entries"] if e["rank"] == 1), None)
        out.append(dict(track=track, board="interaction", ranked_by=main, entrants=len(common),
                        order=[dict(entrant=g, first=ma[g], second=mb[g],
                                    rank_first=next(e["rank"] for e in la["entries"] if e["entrant"] == g),
                                    rank_second=next(e["rank"] for e in lb["entries"] if e["entrant"] == g))
                               for g in sorted(common, key=lambda g: -ma[g])],
                        rho=rho, same_leader=lead_a == lead_b,
                        same_order=sorted(common, key=lambda g: -ma[g]) == sorted(common, key=lambda g: -mb[g])))
    return out


def _verdict(row: dict, alpha_min, rho_min, p_max, min_n, require_validation) -> tuple[str, bool]:
    if row["n"] < min_n:
        return f"too few sessions judged by both ({row['n']} < {min_n})", False
    a = row["alpha"]
    if a is None:
        return "no variance (the judges gave one value only; α undefined)", False
    if a < alpha_min:
        return f"judges disagree (α = {a:.2f} < {alpha_min})", False
    qs = [q for q in row["questionnaire"] if q["n"] >= min_n]
    if row["questionnaire"] and not qs:
        return f"agreement ok; too few questionnaire answers to validate (< {min_n})", False
    if qs:
        good = [q for q in qs if q["rho"] is not None and q["rho"] >= rho_min and q["p"] is not None and q["p"] < p_max]
        if good:
            best = max(good, key=lambda q: q["rho"])
            return f"ready (α = {a:.2f}; ρ = {best['rho']:.2f} with {best['questionnaire']})", True
        if all(q["rho"] is None for q in qs):
            return "agreement ok; no variance in the questionnaire or judges' mean (ρ undefined)", False
        q = max((q for q in qs if q["rho"] is not None), key=lambda q: q["rho"])
        return (f"agreement ok; not shown to follow the questionnaire (best: ρ = {q['rho']:.2f}, p = {q['p']:.3f}, "
                f"n = {q['n']} with {q['questionnaire']}; needs ρ ≥ {rho_min}, p < {p_max})"), False
    if require_validation:
        return f"agreement ok (α = {a:.2f}); no questionnaire counterpart to validate it", False
    return f"ready on agreement only (α = {a:.2f}; no questionnaire counterpart)", True


def load_report(src: Any) -> dict:
    """A reliability report from a dict or a ``.json`` file written by ``judge-reliability -o``."""
    if isinstance(src, dict):
        rep = src
    else:
        rep = json.loads(Path(src).expanduser().read_text(encoding="utf-8"))
    if not isinstance(rep, dict) or "ready" not in rep or "judges" not in rep:
        raise ValueError(f"{src!r} is not a judge reliability report (write one with `hani2 replay "
                         "judge-reliability -o report.json`)")
    return rep


# --------------------------------------------------------------------------- #
# Markdown                                                                     #
# --------------------------------------------------------------------------- #
def _f(v, d=2):
    return "–" if v is None else f"{v:.{d}f}"


def reliability_markdown(rep: dict) -> str:
    """The report as Markdown tables."""
    t = rep["thresholds"]
    lines = ["# Judge reliability", "",
             f"Judges: {' vs '.join(rep['judges'])}; {rep['recordings']} recordings. A soft score component is "
             f"ready for an official ranking when α ≥ {t['alpha_min']} on ≥ {t['min_n']} sessions and, where a "
             f"questionnaire counterpart exists, ρ ≥ {t['rho_min']} (p < {t['p_max']}).", "",
             f"**Ready:** {', '.join(f'`{n}`' for n in rep['ready']) or 'none'}. "
             f"**Not ready:** {', '.join(f'`{n}`' for n in rep['not_ready']) or 'none'}.", "",
             "## Inter-judge agreement per score component", "",
             "| Component | Used in | Level | n | dropped | α | ρ | mean diff | exact | ±1 | Verdict |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rep["components"]:
        used = ", ".join(f"{u['score']} ×{u['weight']:g}" for u in r["scores"]) or "–"
        lines.append(f"| `{r['name']}` | {used} | {r['level']} | {r['n']} | {r['dropped']} | {_f(r.get('alpha'))} | "
                     f"{_f(r.get('rho'))} | {_f(r.get('mean_difference'))} | {_f(r.get('exact'))} | "
                     f"{_f(r.get('within_one'))} | {'✅ ' if r['ready'] else ''}{r['verdict']} |")
    lines.append("")
    lines.append("Interval components are compared as they enter the score (normalised); the mean difference is "
                 "the second judge minus the first.")
    qrows = [(r, q) for r in rep["components"] for q in r["questionnaire"]]
    lines += ["", "## Judge–questionnaire correlation", ""]
    if qrows:
        lines += ["| Component | Questionnaire | n | ρ (judges' mean) | p | " + " | ".join(f"ρ {j}" for j in rep["judges"]) + " |",
                  "| --- | --- | --- | --- | --- | " + " | ".join("---" for _ in rep["judges"]) + " |"]
        for r, q in qrows:
            lines.append(f"| `{r['name']}` | `{q['questionnaire']}` | {q['n']} | {_f(q['rho'])} | {_f(q['p'], 3)} | "
                         + " | ".join(_f(x) for x in q["per_judge"]) + " |")
    else:
        lines.append("No component has a questionnaire counterpart.")
    if rep.get("scores"):
        lines += ["", "## Combined scores under each judge", "",
                  "| Score | Track | n | α | ρ | mean diff |", "| --- | --- | --- | --- | --- | --- |"]
        for s in rep["scores"]:
            lines.append(f"| `{s['name']}` | {s['track'].upper()} | {s['n']} | {_f(s.get('alpha'))} | {_f(s.get('rho'))} | "
                         f"{_f(s.get('mean_difference'), 3)} |")
    if rep.get("boards"):
        lines += ["", "## Leaderboards under each judge", ""]
        for b in rep["boards"]:
            if b.get("error"):
                lines.append(f"- {b['track'].upper()}: {b['error']}")
                continue
            lines.append(f"**{b['track'].upper()} {b['board']}** (ranked by `{b['ranked_by']}`, {b['entrants']} entrants): "
                         f"same leader {'yes' if b['same_leader'] else '**no**'}, same order "
                         f"{'yes' if b['same_order'] else '**no**'}, ρ {_f(b['rho'])}.")
            lines += ["", f"| Entrant | {rep['judges'][0]} | rank | {rep['judges'][1]} | rank |",
                      "| --- | --- | --- | --- | --- |"]
            for o in b["order"]:
                lines.append(f"| {o['entrant']} | {_f(o['first'], 3)} | {o['rank_first']} | {_f(o['second'], 3)} | {o['rank_second']} |")
            lines.append("")
    if rep["errors"]:
        lines += ["", "## Errors", ""]
        for j, errs in rep["errors"].items():
            lines.append(f"- {j}: {len(errs)} recording(s) failed, e.g. {next(iter(errs.values()))}")
    return "\n".join(lines) + "\n"
