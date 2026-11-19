"""Saving and reading negotiation results.

Per user directory ``<results root>/<user>/``:

* ``results.csv`` — one row per negotiation
* ``logs/<mechanism id>.csv`` — the full trace
* ``scenarios/<mechanism id>/`` — the scenario as negotiated
* ``mechanisms/<mechanism id>.json`` — mechanism parameters
"""

from __future__ import annotations

import json
from attrs import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from negmas.helpers.inout import add_records, dump
from negmas.preferences.ops import (
    calc_outcome_distances,
    calc_outcome_optimality,
    calc_scenario_stats,
    estimate_max_dist,
)
from negmas.sao import SAOMechanism, SAOState
from negmas.serialization import serialize

from hani2.config import results_root

TRACE_COLUMNS = ["time", "relative_time", "step", "negotiator", "offer", "responses", "state", "text", "data"]
DEFAULT_COLUMNS = ["scenario", "agent_type", "status", "ended_by", "human_utility", "agent_utility", "human_advantage", "nash_optimality", "ended_at"]


def negotiation_advantage(ufun, utility: float) -> float:
    """``(u - reserved) / (max - reserved)`` — the HAN *advantage* metric."""
    try:
        r = float(ufun.reserved_value)
    except Exception:
        r = float("nan")
    try:
        mn, mx = ufun.minmax()
        mn, mx = float(mn), float(mx)
    except Exception:
        return 0.0
    u = float(utility)
    if (np.isinf(r) and r < 0) or np.isnan(r):
        return u - mn if not np.isnan(mn) else 0.0
    if mx != r:
        return (u - r) / (mx - r)
    return 0.0


def _stamp(ss: dict[str, Any]) -> dict[str, str]:
    """The ``project`` and ``study`` columns (from the session, not the calling thread)."""
    from hani2 import projects

    sess = ss.get("_session")
    return projects.stamp(sess.study_ref) if sess is not None else projects.stamp()


#: columns naming who took part besides the human (added after the existing ones)
ATTRIBUTION_COLUMNS = ["assistant", "assistant_group", "assistant_class", "assistant_error", "opponent_group"]
#: the scheduling methods that chose the opponent, the Assistant and the scenario type
#: (see hani2.scheduling; "" when HANI2 did not schedule that part)
SCHEDULING_COLUMNS = ["opponent_scheduling", "assistant_scheduling", "scenario_scheduling"]


def _attribution(ss: dict[str, Any]) -> dict[str, str]:
    """The Assistant (spec, group, class, error), the opponent's group, the scheduling methods and
    the language models the session used (see :mod:`hani2.model_chain`)."""
    a = dict(ss.get("assistant_attribution") or {})
    out = {k: str(a.get(k) or "") for k in ATTRIBUTION_COLUMNS if k != "opponent_group"}
    out["opponent_group"] = str(ss.get("opponent_group") or "")
    out["opponent_scheduling"] = str(ss.get("opponent_scheduling") or "")
    out["assistant_scheduling"] = str(a.get("assistant_scheduling") or "")
    out["scenario_scheduling"] = str(ss.get("scenario_scheduling") or "")
    from hani2.model_chain import MODEL_COLUMNS, models_of

    models = models_of(ss)
    out.update(models.attribution() if models is not None else {k: "" for k in MODEL_COLUMNS})
    return out


def _state_record(state: Any) -> dict[str, Any]:
    """The mechanism state as columns, with any stored key or token masked in its error texts."""
    d = asdict(state)
    if d.get("error_details"):
        from hani2.connections import redact

        d["error_details"] = redact(d["error_details"])
    return d


def get_status(state: SAOState) -> str:
    if state.agreement is not None:
        return "success"
    if state.broken:
        return "broken"
    if state.timedout:
        return "timedout"
    if state.has_error:
        return "erred"
    return "ended"


def _information(ss: dict[str, Any], m: Any = None) -> dict[str, Any]:
    """The round's information split as flat columns (none when nothing was split; see hani2.information).
    ``constraints_met``: whether the agreement keeps the hidden constraints of the briefings."""
    rec = ss.get("information") or {}
    if not rec.get("split"):
        return {}
    extra: dict[str, Any] = {}
    if rec.get("constraints"):
        from hani2.information import check_constraints

        agreement = getattr(m, "agreement", None)
        issues = list(ss["scenario"].outcome_space.issues) if ss.get("scenario") is not None else []
        agr = {str(i.name): v for i, v in zip(issues, agreement)} if agreement is not None else None
        met, bad = check_constraints(rec["constraints"], agr)
        extra = {"constraints_met": met, "constraint_violations": len(bad) if met is not None else None}
    return extra | {
        "information_split": True,
        "info_human_preferences": rec.get("human_preferences"),
        "info_assistant_preferences": rec.get("assistant_preferences"),
        "info_human_reserved_value": rec.get("human_reserved_value"),
        "info_assistant_reserved_value": rec.get("assistant_reserved_value"),
        "info_past_negotiations": rec.get("past_negotiations"),
        "info_past_source": rec.get("past_source"),
        "info_human_past": ",".join(rec.get("human_past") or []),
        "info_assistant_past": ",".join(rec.get("assistant_past") or []),
        "info_market_research": rec.get("market_research"),
        # ids and audiences only: the texts are private (they are in the recording)
        "info_briefings": ",".join(f"{b['id']}:{b['to']}" for b in rec.get("briefings") or []),
        "info_human_only_issues": ",".join(rec.get("human_only_issues") or []),
        "info_human_only_actions": ",".join(rec.get("human_only_actions") or []),
    }


def save_result(ss: dict[str, Any], m: SAOMechanism) -> tuple[dict, dict]:
    """Write all result files for a finished negotiation.

    Returns ``(row, summary)`` where ``summary`` has ``n_human_actions``,
    ``status``, ``ended_by``, ``agent_failed`` and ``agent_error``.
    """
    scenario = ss["scenario"]
    ufuns = scenario.ufuns
    human_index = ss["human_index"]
    human_ufun = ss["human_ufun"]
    utils = tuple(u(m.agreement) for u in ufuns)
    human_utility = float(human_ufun(m.agreement))
    human_advantage = negotiation_advantage(human_ufun, human_utility)
    agent_utility = float(sum(u(m.agreement) for i, u in enumerate(ufuns) if i != human_index))
    human_id = str(ss.get("human_id", ""))

    agent_failed = bool(getattr(m.state, "has_error", False)) and (
        str(getattr(m.state, "erred_negotiator", "")) != human_id
    )
    agent_error = ""
    if agent_failed:
        from hani2.connections import redact

        agent_error = redact(str(getattr(m.state, "error_details", "")) or "agent raised an exception")
        try:
            agent_utility = float(ufuns[1 - human_index].minmax()[0])
        except Exception:
            agent_utility = 0.0

    agent_type = str(ss.get("last_partner_type", "")).strip() or "+".join(
        type(n).__name__ for i, n in enumerate(m.negotiators) if i != human_index
    )

    n_human_actions = 0
    step_times: list[float] = []
    for row in m.full_trace:
        if len(row) > 3 and str(row[3]) == human_id:
            n_human_actions += 1
            try:
                step_times.append(float(row[1]))
            except (TypeError, ValueError):
                pass
    per_round, prev = [], 0.0
    for t in step_times:
        per_round.append(round(max(0.0, t - prev), 3))
        prev = t

    status = get_status(m.state)
    if status == "success":
        n_human_actions = max(n_human_actions, 1)
    ended_by = ""
    if status == "broken":
        ended_by = "human" if ss.get("human_ended_negotiation") else "agent"
    elif status == "success":
        last = ""
        for row in reversed(m.full_trace):
            if len(row) > 4 and row[4] is not None:
                last = str(row[3])
                break
        ended_by = "agent" if last == human_id else ("human" if last else "")
    if agent_failed:
        status, ended_by = "agent_failed", "agent"

    try:
        stats = calc_scenario_stats(ufuns)
        optimality = asdict(
            calc_outcome_optimality(calc_outcome_distances(utils, stats), stats, estimate_max_dist(ufuns))
        )
    except Exception as e:  # pragma: no cover - continuous / huge spaces
        print(f"[hani2] could not compute optimality: {e}")
        optimality = {}

    now = datetime.now()
    load_at, start_at = ss.get("load_at_dt"), ss.get("start_at_dt")
    scenario_name = str(scenario.outcome_space.name).split("/")[-1].split(".")[0]
    row = serialize(
        dict(ss.get("scenario_info") or {})
        | dict(
            scenario=scenario_name,
            human_index=human_index,
            human_id=human_id,
            user=ss["user"],
            agent_type=agent_type,
            agreement=m.agreement,
            human_utility=human_utility,
            human_advantage=human_advantage,
            agent_utility=agent_utility,
            welfare=human_utility + agent_utility,
            ended_at=str(now),
            status=status,
            ended_by=ended_by,
            agent_error=agent_error,
            mechanism_name=m.name,
            mechanism_id=m.id,
            practice=bool(ss.get("is_practice_round", False)),
            n_human_actions=n_human_actions,
            load_at=load_at.isoformat() if load_at else "",
            start_at=start_at.isoformat() if start_at else "",
            load_to_start_seconds=round((start_at - load_at).total_seconds(), 3) if load_at and start_at else None,
            duration_seconds=round((now - start_at).total_seconds(), 3) if start_at else None,
            per_round_times=json.dumps(per_round),
            view_mode=ss.get("view_mode", ""),
            view_source=ss.get("view_source", ""),
            user_agent=ss.get("user_agent", ""),
            device=ss.get("device", ""),
            orientation=ss.get("orientation", ""),
            support_agent=bool(ss.get("support_agent_used", False)),
            autopilot=bool(ss.get("autopilot_used", False)),
        )
        | _attribution(ss)
        | _information(ss, m)
        | _stamp(ss)
        | _state_record(m.state)
        | {k: v for k, v in asdict(m.nmi).items() if not k.startswith("_") and not k.startswith("outcome_space")}
        | optimality,
        python_class_identifier="type",
    )
    user_path: Path = ss["user_path"]
    user_path.mkdir(parents=True, exist_ok=True)
    add_records(user_path / "results.csv", [row])
    try:
        (user_path / "logs").mkdir(exist_ok=True, parents=True)
        pd.DataFrame.from_records(m.full_trace, columns=TRACE_COLUMNS).to_csv(
            user_path / "logs" / f"{m.id}.csv", index=True, index_label="index"
        )
        sdir = user_path / "scenarios" / f"{m.id}"
        from hani2.scenario_store import save_scenario

        save_scenario(scenario, sdir)  # the same files as the pool slot it came from
        (user_path / "mechanisms").mkdir(exist_ok=True, parents=True)
        dump(
            dict(
                id=m.nmi.id,
                end_on_no_response=m.nmi.end_on_no_response,
                one_offer_per_step=m.nmi.one_offer_per_step,
                n_outcomes=m.nmi.n_outcomes,
                time_limit=m.nmi.time_limit,
                pend=m.nmi.pend,
                pend_per_second=m.nmi.pend_per_second,
                step_time_limit=m.nmi.step_time_limit,
                negotiator_time_limit=m.nmi.negotiator_time_limit,
                n_steps=m.nmi.n_steps,
            ),
            user_path / "mechanisms" / f"{m.id}.json",
        )
    except Exception as e:  # pragma: no cover
        print(f"[hani2] could not save trace/scenario: {e}")
    summary = dict(
        n_human_actions=n_human_actions,
        status=status,
        ended_by=ended_by,
        agent_failed=agent_failed,
        agent_error=agent_error,
        human_utility=human_utility,
        agent_utility=agent_utility,
        human_advantage=human_advantage,
    )
    return row, summary


# --------------------------------------------------------------------------- #
# Reading                                                                      #
# --------------------------------------------------------------------------- #
def read_user_results(user: str) -> pd.DataFrame:
    f = results_root() / user / "results.csv"
    if not f.is_file():
        return pd.DataFrame()
    try:
        return pd.read_csv(f, index_col=None)
    except Exception:
        return pd.DataFrame()


def read_all_results() -> pd.DataFrame:
    frames = []
    for d in sorted(results_root().glob("*")):
        f = d / "results.csv"
        if f.is_file():
            try:
                frames.append(pd.read_csv(f, index_col=None))
            except Exception:
                pass
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def scenario_scores(df: pd.DataFrame, normalize_by_time: bool = False) -> tuple[float, dict[str, tuple[float, int]]]:
    """The participant score: per scenario the mean of the best (≤3) results excluding
    the worst one, averaged over scenarios (×100)."""
    scores: dict[str, tuple[float, int]] = {}
    if df is None or len(df) == 0 or "scenario" not in df:
        return 0.0, scores
    for s in df["scenario"].unique():
        lst = sorted(df[df["scenario"] == s]["human_utility"].astype(float).tolist(), reverse=True)
        n = len(lst)
        if n < 2:
            scores[str(s)] = (0.0, n)
            continue
        best = lst[:-1][:3]
        scores[str(s)] = (sum(best) / len(best) if best else 0.0, n)
    score = 100 * sum(v for v, _ in scores.values()) / len(scores) if scores else 0.0
    if normalize_by_time and "time" in df:
        base = df["time"].sum()
        score = 0.0 if base < 1e-3 else score / base
    return score, scores


def leaderboard(df: pd.DataFrame) -> list[dict]:
    if df is None or len(df) == 0 or "user" not in df:
        return []
    out = []
    for user in df["user"].unique():
        sub = df[df["user"] == user]
        score, _ = scenario_scores(sub)
        out.append(dict(user=str(user), score=score, negotiations=len(sub),
                        mean_utility=float(sub["human_utility"].astype(float).mean())))
    return sorted(out, key=lambda r: -r["score"])
