"""Evaluate recorded negotiations (``.hrec`` files) with optional metrics.

Four kinds of metrics:

* **hard** — computed from the log: outcome, optimality (Pareto / Nash /
  Kalai–Smorodinsky distances, welfare), length, LLM usage and cost, move types
  and theory of mind, timing, activity, use of the assistant and tools,
  engagement flags, assistant interaction quality.
* **soft** — judged by a language model from the transcript (opt-in).
* **subjective** — the participant's questionnaire answers (UEQ, TAM, …).
* **score** — combinations of the others: per-scenario task success and the
  combined scores of the HAN and HI tracks (see :mod:`hani2.evaluation.scores`).

Rank the entrants of a track with :func:`leaderboard` (``hani2 replay leaderboard``).

Use it from Python::

    from hani2.evaluation import evaluate_paths, compare_rows
    rows = evaluate_paths(["results/"], metrics=["outcome", "optimality", "system_use"])
    groups = compare_rows(rows, by="opponent")

or from the command line (``hani2 replay evaluate``) or the replay tool.
"""

from __future__ import annotations

import json
import math
import traceback
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from hani2.evaluation import hard as _hard  # noqa: F401  (registers metrics)
from hani2.evaluation import llm_judge as _llm  # noqa: F401
from hani2.evaluation import subjective as _subj  # noqa: F401
from hani2.evaluation import factors as _factors  # noqa: F401
from hani2.evaluation import tasks as _tasks  # noqa: F401
from hani2.evaluation import scores as _scores  # noqa: F401
from hani2.evaluation import ablation as _ablation  # noqa: F401  (the condition metric)
from hani2.evaluation.ablation import ablation_report
from hani2.evaluation.base import KINDS, REGISTRY, Column, EvalContext, Metric, metric
from hani2.evaluation.tracks import TRACKS, leaderboard, leaderboards
from hani2.evaluation.llm_judge import llm_judge_status
from hani2.evaluation.reference import metric_reference
from hani2.recording.format import Recording, iter_recordings, recording_id

__all__ = [
    "REGISTRY", "Column", "EvalContext", "Metric", "metric", "available_metrics", "evaluate_recording",
    "evaluate_paths", "evaluate_keys", "compare_rows", "compare_keys", "pass_hat_k", "llm_judge_status",
    "metric_reference", "leaderboard", "leaderboards", "TRACKS", "load_paths", "judge_reliability",
    "ablation_report",
]


def judge_reliability(*args, **kwargs):
    """See :func:`hani2.evaluation.reliability.judge_reliability`."""
    from hani2.evaluation.reliability import judge_reliability as f

    return f(*args, **kwargs)

#: fields copied from the recording into every row (used to group and filter)
ID_FIELDS = ("key", "id", "user", "mode", "participant_type", "persona", "scenario", "opponent", "support_agent",
             "support_model", "experiment", "started", "practice", "judge_model", "assistant", "human_index")


def available_metrics(full: bool = False) -> list[dict]:
    """Every registered metric (hard, subjective, soft); ``full`` adds the
    reference texts (formulas, details, dynamic columns, figures)."""
    order = {k: i for i, k in enumerate(KINDS)}
    return sorted((m.info(full) for m in REGISTRY.values()), key=lambda m: order.get(m["kind"], 9))


def _select(metrics: Iterable[str] | None, use_llm: bool) -> list[Metric]:
    if metrics:
        names = list(metrics)
        unknown = [n for n in names if n not in REGISTRY]
        if unknown:
            raise ValueError(f"unknown metric(s): {', '.join(unknown)}; known: {', '.join(REGISTRY)}")
        # add what the selected metrics need (in front of them)
        todo, names = names, []
        while todo:
            n = todo.pop(0)
            if n in names:
                continue
            names.append(n)
            todo += [r for r in REGISTRY[n].requires if r in REGISTRY]
        sel = [REGISTRY[n] for n in names]
    else:
        sel = [m for m in REGISTRY.values() if m.default]
    sel = [m for m in sel if use_llm or not m.needs_llm]
    return sorted(sel, key=lambda m: m.stage)  # stable: the given order within a stage


def _ident(rec: Recording, key: str | None) -> dict:
    sess = rec.header.get("session") or {}
    st = rec.start or {}
    sa = st.get("support_agent") or {}
    sim = rec.first("sim") or {}
    row = (rec.result or {}).get("row") or {}
    mode = sess.get("mode")
    if sim and mode != "simulated":
        mode = "simulated"
    ptype = (f"simulated-{sim.get('difficulty')}" if sim else
             (row.get("participant_type") or (rec.first("pre_questionnaire") or {}).get("participant_type") or ""))
    return dict(
        key=key or str(rec.path or rec.id), id=rec.id, user=sess.get("user"), mode=mode,
        participant_type=ptype or None, persona=sim.get("persona"),
        scenario=(rec.scenario or {}).get("name"), opponent=st.get("opponent"),
        support_agent=(sa.get("name") or sa.get("cls")) if sa and sa.get("enabled") else "none",
        support_model=sa.get("model") if sa else None, experiment=rec.header.get("experiment"),
        started=rec.header.get("created"), practice=bool(st.get("practice")),
        # the Assistant as assigned (``none`` for the no-Assistant arm), and the human's side (part of a cell)
        assistant=(st.get("assignment") or {}).get("assistant") or None, human_index=st.get("human_index"),
    )


def _cache_path(rec: Recording) -> Path | None:
    if rec.path is None:
        return None
    return rec.path.with_name(f"{recording_id(rec.path)}.eval.json")


def _load_cache(rec: Recording) -> dict:
    p = _cache_path(rec)
    if p is None or not p.is_file():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _save_cache(rec: Recording, cache: dict) -> None:
    p = _cache_path(rec)
    if p is None:
        return
    try:
        p.write_text(json.dumps(cache, indent=1, default=str))
    except Exception:  # pragma: no cover - read-only folder
        pass


def _clean(v: Any) -> Any:
    if isinstance(v, (np.floating, np.integer)):
        v = v.item()
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def evaluate_recording(rec: Recording, metrics: Iterable[str] | None = None, *, use_llm: bool = False,
                       refresh: bool = False, options: dict | None = None, key: str | None = None,
                       judge: Any = None) -> dict:
    """Evaluate one recording: ``{"row": {...}, "details": {metric: ...}, "errors": {metric: msg}}``.

    ``judge``: judge the soft metrics with exactly this model (``"provider:model"``, see
    :func:`hani2.evaluation.llm_judge.use_judge`) instead of the configured judge chain."""
    if judge is not None:
        from hani2.evaluation.llm_judge import use_judge

        with use_judge(judge):
            return evaluate_recording(rec, metrics, use_llm=use_llm, refresh=refresh, options=options, key=key)
    options = dict(options or {})
    ctx = EvalContext(rec)
    row = _ident(rec, key)
    ctx.row = row  # later stages read the values computed so far
    details: dict[str, Any] = {}
    errors: dict[str, str] = {}
    cache = _load_cache(rec) if use_llm else {}
    dirty = False
    for m in _select(metrics, use_llm):
        try:
            if m.needs_llm:
                from hani2.evaluation.llm_judge import cache_key, stamp

                ck = cache_key(m.name, m.version, options, rec.complete)
                if "judge_model" not in row:
                    from hani2.evaluation.llm_judge import judge_model

                    row["judge_model"] = judge_model().short()  # who judged this row's soft metrics
                if m.cache_extra is not None:
                    ck += "|" + m.cache_extra(ctx, options)
                if not refresh and ck in cache:
                    vals = cache[ck]["values"]
                else:
                    vals = m.fn(ctx, options) or {}
                    cache[ck] = {"values": vals, "at": stamp()}
                    dirty = True
            else:
                vals = m.fn(ctx, options) or {}
            vals = dict(vals)
            d = vals.pop("_details", None)
            if d is not None:
                details[m.name] = d
            row.update({k: _clean(v) for k, v in vals.items()})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            errors[m.name] = f"{type(e).__name__}: {e}"
    if dirty:
        _save_cache(rec, cache)
    return {"row": row, "details": details, "errors": errors}


def _columns(selected: list[Metric], rows: list[dict]) -> list[dict]:
    cols, seen = [], set()
    for m in selected:
        for c in m.columns:
            if any(c.name in r for r in rows):
                cols.append(dict(name=c.name, metric=m.name, kind=m.kind, title=c.title, description=c.description,
                                 higher_is_better=c.higher_is_better))
                seen.add(c.name)
        # dynamic columns (e.g. questionnaire items)
        extra = sorted({k for r in rows for k in r if k.startswith(("q_", "scale_")) and k not in seen}) \
            if m.name == "questionnaire" else []
        for k in extra:
            pat = m.column_info(k)
            cols.append(dict(name=k, metric=m.name, kind=m.kind, title=k.replace("_", " "),
                             description=pat.description if pat else "",
                             higher_is_better=pat.higher_is_better if pat else None))
            seen.add(k)
    return cols


def evaluate_many(recs: list[tuple[str, Recording]], metrics=None, *, use_llm=False, refresh=False,
                  options=None, judge=None) -> dict:
    if judge is not None:
        from hani2.evaluation.llm_judge import use_judge

        with use_judge(judge):
            return evaluate_many(recs, metrics, use_llm=use_llm, refresh=refresh, options=options)
    rows, details, errors = [], {}, {}
    for key, rec in recs:
        r = evaluate_recording(rec, metrics, use_llm=use_llm, refresh=refresh, options=options, key=key)
        rows.append(r["row"])
        details[key] = r["details"]
        if r["errors"]:
            errors[key] = r["errors"]
    return {"rows": rows, "columns": _columns(_select(metrics, use_llm), rows), "details": details, "errors": errors}


def evaluate_keys(keys: list[str], metrics=None, *, use_llm=False, refresh=False, options=None, judge=None) -> dict:
    from hani2.recording import store

    recs, errors = [], {}
    for k in keys:
        try:
            recs.append((k, store.load(k)))
        except Exception as e:  # noqa: BLE001
            errors[k] = {"load": str(e)}
    out = evaluate_many(recs, metrics, use_llm=use_llm, refresh=refresh, options=options, judge=judge)
    out["errors"].update(errors)
    return out


def evaluate_paths(paths: Iterable[str | Path], metrics=None, *, use_llm=False, refresh=False,
                   options=None, include_unstarted: bool = False, judge=None) -> dict:
    recs = load_paths(paths, include_unstarted)
    return evaluate_many(recs, metrics, use_llm=use_llm, refresh=refresh, options=options, judge=judge)


def load_paths(paths: Iterable[str | Path], include_unstarted: bool = False) -> list[tuple[str, Recording]]:
    """The recordings under ``paths`` as ``(key, recording)`` (unreadable ones are skipped)."""
    recs = []
    for p in paths:
        for f in iter_recordings(p):
            try:
                rec = Recording.load(f)
            except Exception as e:  # noqa: BLE001
                print(f"[hani2] skipping {f}: {e}")
                continue
            if not include_unstarted and rec.start is None:
                continue
            recs.append((str(f), rec))
    return recs


# --------------------------------------------------------------------------- #
# Comparing groups                                                             #
# --------------------------------------------------------------------------- #
def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k: the chance that ``k`` trials drawn from ``n`` (``c`` successful)
    all succeed — reliability across repeated sessions (Yao et al., τ-bench)."""
    if n < k:
        raise ValueError("fewer trials than k")
    return math.comb(c, k) / math.comb(n, k)


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def compare_rows(rows: list[dict], by: str = "opponent", columns: list[dict] | None = None,
                 success: str = "agreement", success_threshold: float | None = None, max_k: int = 5) -> dict:
    """Aggregate rows by a field: per group ``n``, ``mean``, ``std`` and a
    scenario-balanced mean (average within each scenario first), plus pass^k
    reliability (success = ``success`` column ≥ threshold, default: a deal).

    ``by`` may name several fields (``"opponent,participant_type"``): a group per combination,
    e.g. to see each opponent or Assistant on easy and on hard participants.

    Simulated sessions (``mode == "simulated"``) are never pooled with human ones: their group
    name gets `` [simulated]`` (unless grouping by ``mode`` itself)."""
    groups: dict[str, list[dict]] = {}
    fields = [f.strip() for f in str(by).split(",") if f.strip()] or [by]
    for r in rows:
        g = " / ".join(str(r.get(f)) for f in fields)
        if r.get("mode") == "simulated" and "mode" not in fields and not g.endswith("[simulated]"):
            g += " [simulated]"
        groups.setdefault(g, []).append(r)
    names = [c["name"] for c in columns] if columns else sorted(
        {k for r in rows for k, v in r.items() if _is_num(v) and k not in ID_FIELDS})
    out_groups, reliability = [], []
    for g, rs in sorted(groups.items()):
        mean, std, balanced = {}, {}, {}
        for c in names:
            vals = [float(r[c]) for r in rs if _is_num(r.get(c))]
            if vals:
                mean[c] = float(np.mean(vals))
                std[c] = float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0
                per_s: dict[str, list[float]] = {}
                for r in rs:
                    if _is_num(r.get(c)):
                        per_s.setdefault(str(r.get("scenario")), []).append(float(r[c]))
                balanced[c] = float(np.mean([np.mean(v) for v in per_s.values()]))
        out_groups.append(dict(group=g, n=len(rs), mean=mean, std=std, balanced=balanced))
        # pass^k per task (a scenario against one opponent), averaged over tasks: pooling two opponents'
        # trials into one list would turn "4/4 against A, 0/4 against B" into ~0 instead of 0.5
        per_s2: dict[str, list[bool]] = {}
        for r in rs:
            v = r.get(success)
            if not _is_num(v):
                continue
            ok = float(v) >= (success_threshold if success_threshold is not None else 1.0 - 1e-9)
            per_s2.setdefault(f"{r.get('scenario')}|{r.get('opponent')}", []).append(ok)
        if per_s2:
            kmax = min(max_k, min(len(v) for v in per_s2.values()))
            for k in range(1, kmax + 1):
                vals = [pass_hat_k(len(v), sum(v), k) for v in per_s2.values()]
                reliability.append(dict(group=g, k=k, pass_hat_k=float(np.mean(vals)), scenarios=len(vals)))
    return {"by": by, "groups": out_groups, "columns": columns or [{"name": n} for n in names],
            "reliability": reliability, "success": success, "success_threshold": success_threshold}


def compare_keys(keys: list[str], by: str = "opponent", metrics=None, *, use_llm=False, options=None) -> dict:
    ev = evaluate_keys(keys, metrics, use_llm=use_llm, options=options)
    opts = options or {}
    res = compare_rows(ev["rows"], by=by, columns=[c for c in ev["columns"] if any(_is_num(r.get(c["name"])) for r in ev["rows"])],
                       success=str(opts.get("success", "agreement")), success_threshold=opts.get("success_threshold"))
    res["errors"] = ev["errors"]
    return res
