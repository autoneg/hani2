"""Hard metrics: computed from the recording alone (no judgement involved)."""

from __future__ import annotations

import math
from collections import Counter

import numpy as np

from hani2.evaluation.base import Column as C
from hani2.evaluation.base import EvalContext, mean, median, metric, num


# --------------------------------------------------------------------------- #
# Outcome                                                                      #
# --------------------------------------------------------------------------- #
@metric("outcome", kind="hard", title="Outcome", columns=[
    C("agreement", "Agreement", "1 if the negotiation ended with a deal", True),
    C("status", "Status", "success, broken, timedout, erred or agent_failed"),
    C("ended_by", "Ended by", "Who ended it (accepted or broke off): human or agent"),
    C("human_utility", "Human utility", "Utility of the result for the human–agent team", True),
    C("opponent_utility", "Opponent utility", "Utility of the result for the opponent"),
    C("human_advantage", "Human advantage", "(u − reserved) / (max − reserved) for the human team", True),
    C("opponent_advantage", "Opponent advantage", "The same for the opponent"),
    C("welfare", "Social welfare", "Sum of every party's utility", True),
    C("practice", "Practice", "1 for a practice round"),
])
def outcome(ctx: EvalContext, options: dict) -> dict:
    """Did the team reach a deal, and how good was it for each side?"""
    s = ctx.summary
    agr = ctx.agreement
    hu = num(s.get("human_utility"))
    pt = ctx.point_of(agr)
    if pt is not None and ctx.has_scenario:
        hu, ou = float(pt[0]), float(pt[1])
    else:
        ou = num(s.get("agent_utility"))

    def adv(u, i_vals, r):
        if u is None or ctx.U.size == 0:
            return None
        mx = float(np.nanmax(i_vals))
        return (u - r) / (mx - r) if mx - r > 1e-12 else 0.0

    hadv = num(s.get("human_advantage"))
    oadv = None
    if ctx.has_scenario:
        d = ctx.disagreement
        hadv = adv(hu, ctx.two_party[0], d[0])
        oadv = adv(ou, ctx.two_party[1], d[1])
    st = ctx.rec.start or {}
    return dict(
        agreement=1 if agr is not None else 0 if s else None,
        status=s.get("status"), ended_by=s.get("ended_by") or None,
        human_utility=hu, opponent_utility=ou, human_advantage=hadv, opponent_advantage=oadv,
        welfare=(hu + ou) if hu is not None and ou is not None else None,
        practice=1 if st.get("practice") else 0,
    )


@metric("optimality", kind="hard", title="Optimality", columns=[
    C("pareto_distance", "Pareto distance", "Distance of the result from the Pareto frontier (utility space)", False),
    C("pareto_optimal", "Pareto optimal", "1 if the result is on the Pareto frontier", True),
    C("nash_distance", "Nash distance", "Distance from the Nash bargaining solution", False),
    C("kalai_distance", "Kalai–Smorodinsky distance", "Distance from the Kalai–Smorodinsky solution", False),
    C("welfare_optimality", "Welfare optimality", "Social welfare / the best possible welfare", True),
    C("nash_product_ratio", "Nash product ratio", "Nash product of the result / the largest possible", True),
    C("fairness_gap", "Fairness gap", "|human advantage − opponent advantage|", False),
])
def optimality(ctx: EvalContext, options: dict) -> dict:
    """How far the result is from the efficient and fair outcomes of the scenario."""
    if not ctx.has_scenario:
        return {}
    pt = ctx.point_of(ctx.agreement)
    if pt is None:
        return {}
    d = ctx.disagreement
    pd_ = ctx.dist_to_pareto(pt)
    nash, ks = ctx.nash_point, ctx.ks_point
    P = ctx.two_party
    gains = np.clip(P[0] - d[0], 0, None) * np.clip(P[1] - d[1], 0, None)
    best_np = float(gains.max()) if gains.size else 0.0
    my_np = max(0.0, pt[0] - d[0]) * max(0.0, pt[1] - d[1])
    mw = ctx.max_welfare
    hadv = (pt[0] - d[0]) / (P[0].max() - d[0]) if P[0].max() - d[0] > 1e-12 else 0.0
    oadv = (pt[1] - d[1]) / (P[1].max() - d[1]) if P[1].max() - d[1] > 1e-12 else 0.0
    return dict(
        pareto_distance=pd_, pareto_optimal=int(pd_ is not None and pd_ < 1e-6),
        nash_distance=float(np.linalg.norm(pt - nash)) if nash is not None else None,
        kalai_distance=float(np.linalg.norm(pt - ks)) if ks is not None else None,
        welfare_optimality=float(pt.sum() / mw) if mw else None,
        nash_product_ratio=my_np / best_np if best_np > 0 else None,
        fairness_gap=abs(hadv - oadv),
    )


@metric("scenario_stats", kind="hard", title="Scenario", default=False, columns=[
    C("n_outcomes", "Outcomes", "Number of possible outcomes"),
    C("zopa_fraction", "ZOPA fraction", "Share of outcomes acceptable to every party (above all reserved values)"),
    C("pareto_size", "Pareto size", "Number of Pareto-optimal outcomes"),
    C("opposition", "Opposition", "Distance of the best joint point (1,1) from the frontier: how competitive the scenario is"),
])
def scenario_stats(ctx: EvalContext, options: dict) -> dict:
    """Descriptors of the scenario (useful to balance comparisons)."""
    if not ctx.has_scenario:
        return {}
    U = ctx.U
    ok = np.all(U >= ctx.reserved[:, None], axis=0)
    P = ctx.two_party[:, ctx.pareto]
    mx = ctx.two_party.max(axis=1)
    opp = float(np.min(np.linalg.norm(P - mx[:, None], axis=0))) if P.size else None
    return dict(n_outcomes=int(U.shape[1]), zopa_fraction=float(ok.mean()), pareto_size=int(ctx.pareto.size),
                opposition=opp)


# --------------------------------------------------------------------------- #
# Length and cost                                                              #
# --------------------------------------------------------------------------- #
@metric("length", kind="hard", title="Length", columns=[
    C("n_offers", "Offers", "Offers exchanged"),
    C("n_human_offers", "Human offers", "Offers made by the human team"),
    C("n_opponent_offers", "Opponent offers", "Offers made by the opponent"),
    C("n_steps", "Steps", "Mechanism steps used"),
    C("relative_time", "Relative time", "Share of the time/step limit used"),
    C("negotiation_seconds", "Negotiation time (s)", "From the start to the end of the negotiation"),
    C("session_seconds", "Recording time (s)", "From loading the scenario to the end of the recording"),
    C("n_text_messages", "Text messages", "Offers or turns that carried a message to the other side"),
])
def length(ctx: EvalContext, options: dict) -> dict:
    """How long the negotiation took, in offers, steps and seconds."""
    rows = ctx.rec.trace
    last = rows[-1] if rows else {}
    row = ctx.rec.result or {}
    dur = (ctx.ended_at - ctx.started_at) if ctx.ended_at is not None and ctx.started_at is not None else None
    return dict(
        n_offers=len(ctx.offers), n_human_offers=len(ctx.human_offers), n_opponent_offers=len(ctx.opponent_offers),
        n_steps=num(row.get("step", last.get("step"))), relative_time=num(row.get("relative_time", last.get("rel"))),
        negotiation_seconds=dur, session_seconds=ctx.rec.duration,
        n_text_messages=sum(1 for r in rows if r.get("text")),
    )


@metric("llm_usage", kind="hard", title="LLM usage and cost", columns=[
    C("llm_calls", "LLM calls", "Language-model calls during the negotiation"),
    C("llm_tokens", "LLM tokens", "Prompt + completion tokens (energy / climate proxy)", False),
    C("llm_cost_usd", "LLM cost (USD)", "Estimated cost of every call (when the provider's price is known)", False),
    C("llm_latency_mean", "LLM latency (s)", "Mean seconds per call", False),
    C("llm_error_rate", "LLM error rate", "Share of calls that failed", False),
    C("support_llm_calls", "Assistant LLM calls", "Calls made by the Assistant"),
    C("support_tokens", "Assistant tokens", "Tokens used by the Assistant", False),
    C("opponent_llm_calls", "Opponent LLM calls", "Calls made by the opponent"),
    C("opponent_tokens", "Opponent tokens", "Tokens used by the opponent", False),
])
def llm_usage(ctx: EvalContext, options: dict) -> dict:
    """Language-model calls, tokens, cost and latency, overall and per role."""
    calls = ctx.llm_calls

    def tok(c):
        u = c.get("usage") or {}
        return u.get("total_tokens") or ((u.get("prompt_tokens") or 0) + (u.get("completion_tokens") or 0)) or None

    def tsum(cs):
        v = [tok(c) for c in cs]
        v = [x for x in v if x]
        return int(sum(v)) if v else 0

    costs = [num(c.get("cost")) for c in calls]
    costs = [c for c in costs if c is not None]
    sup = [c for c in calls if c.get("role") in ("support", "autopilot")]
    opp = [c for c in calls if c.get("role") == "opponent"]
    by_role = Counter(c.get("role") for c in calls)
    by_model = Counter(c.get("model") for c in calls)
    return dict(
        llm_calls=len(calls), llm_tokens=tsum(calls), llm_cost_usd=float(sum(costs)) if costs else None,
        llm_latency_mean=mean([c.get("latency") for c in calls]),
        llm_error_rate=(sum(1 for c in calls if c.get("error")) / len(calls)) if calls else None,
        support_llm_calls=len(sup), support_tokens=tsum(sup), opponent_llm_calls=len(opp), opponent_tokens=tsum(opp),
        _details=dict(by_role=dict(by_role), by_model=dict(by_model)),
    )


# --------------------------------------------------------------------------- #
# Dynamics: move types (DANS) and theory of mind                              #
# --------------------------------------------------------------------------- #
MOVE_TYPES = ("silent", "nice", "fortunate", "unfortunate", "concession", "selfish")


def classify_move(d_self: float, d_other: float, eps: float = 1e-6) -> str:
    """The move type of a change of offer (Hindriks et al.'s DANS framework)."""
    s = 0 if abs(d_self) <= eps else (1 if d_self > 0 else -1)
    o = 0 if abs(d_other) <= eps else (1 if d_other > 0 else -1)
    if s == 0 and o == 0:
        return "silent"
    if s == 0 and o > 0:
        return "nice"
    if s > 0 and o > 0:
        return "fortunate"
    if s <= 0 and o <= 0:
        return "unfortunate"
    if s < 0 and o > 0:
        return "concession"
    return "selfish"  # s > 0, o <= 0  (or s == 0 and o < 0 handled above as unfortunate)


def _moves(seq: list[tuple[float | None, float | None]]) -> list[str]:
    out = []
    for (a_s, a_o), (b_s, b_o) in zip(seq, seq[1:]):
        if None in (a_s, a_o, b_s, b_o):
            continue
        out.append(classify_move(b_s - a_s, b_o - a_o))
    return out


def _move_cols(prefix: str, who: str) -> list:
    return [C(f"{prefix}_{m}", f"{who}: {m}", f"Share of {who.lower()} moves that were {m}") for m in MOVE_TYPES]


@metric("dynamics", kind="hard", title="Negotiation dynamics", columns=[
    *_move_cols("human_move", "Human"),
    *_move_cols("opponent_move", "Opponent"),
    *_move_cols("suggested_move", "Assistant suggestion"),
    C("human_concession", "Human concession", "Utility the human gave up from the first to the last offer"),
    C("human_offer_pareto_distance", "Human offers' Pareto distance", "Mean distance of the human's offers from the Pareto frontier", False),
    C("tom_reflect_index", "Theory of mind: reflect index",
      "Share of the human's offers made before the first move that raised the opponent's utility (lower = sooner)", False),
    C("tom_other_trend", "Theory of mind: other's-utility trend",
      "Correlation of the opponent's utility of the human's offers with time (higher = the human moved toward the other's interests)", True),
])
def dynamics(ctx: EvalContext, options: dict) -> dict:
    """Move types of each side and of the assistant's suggestions, concession and
    how quickly the human's offers reflect the other's perspective."""
    out: dict = {}
    hum = [(o["hu"], o["ou"]) for o in ctx.human_offers]
    opp = [(o["ou"], o["hu"]) for o in ctx.opponent_offers]  # self = opponent
    # suggestions relative to the human's previous offer (or the previous suggestion)
    sug_seq: list[tuple] = []
    last_h = None
    events = sorted([(a["t"], "act", a) for a in ctx.acts if a.get("type") == "offer"]
                    + [(d["t"], "draft", d) for d in ctx.drafts if d.get("by") == "agent" and d.get("values")],
                    key=lambda x: x[0])
    names = ctx.scenario.get("issue_names") or []
    sug_moves = []
    for _, kind, e in events:
        offer = e.get("offer") if kind == "act" else [e["values"].get(n) for n in names]
        pt = (ctx.hu(offer), ctx.ou(offer))
        if kind == "act":
            last_h = pt
        else:
            base = last_h if last_h is not None else (sug_seq[-1] if sug_seq else None)
            if base is not None and None not in base and None not in pt:
                sug_moves.append(classify_move(pt[0] - base[0], pt[1] - base[1]))
            sug_seq.append(pt)
    for prefix, mv in (("human_move", _moves(hum)), ("opponent_move", _moves(opp)), ("suggested_move", sug_moves)):
        c = Counter(mv)
        n = len(mv)
        for m in MOVE_TYPES:
            out[f"{prefix}_{m}"] = c[m] / n if n else None
    hs = [h for h, _ in hum if h is not None]
    out["human_concession"] = (hs[0] - hs[-1]) if len(hs) >= 2 else None
    if ctx.has_scenario and ctx.human_offers:
        ds = [ctx.dist_to_pareto(np.array([h, o])) for h, o in hum if h is not None and o is not None]
        out["human_offer_pareto_distance"] = mean(ds)
    hm = _moves(hum)
    first = next((i for i, m in enumerate(hm) if m in ("nice", "fortunate", "concession")), None)
    out["tom_reflect_index"] = ((first + 1) / len(hm)) if hm and first is not None else (1.0 if hm else None)
    os_ = [o for _, o in hum if o is not None]
    if len(os_) >= 3 and np.std(os_) > 0:
        out["tom_other_trend"] = float(np.corrcoef(np.arange(len(os_)), os_)[0, 1])
    else:
        out["tom_other_trend"] = None
    out["_details"] = dict(human_moves=hm, opponent_moves=_moves(opp), suggested_moves=sug_moves)
    return out


# --------------------------------------------------------------------------- #
# Timing and engagement                                                        #
# --------------------------------------------------------------------------- #
@metric("timing", kind="hard", title="Timing", columns=[
    C("decision_time_mean", "Decision time (s)", "Mean time from the start of the human's turn to their action"),
    C("decision_time_median", "Decision time, median (s)", "Median time per decision"),
    C("decision_time_min", "Fastest decision (s)", "Shortest time per decision"),
    C("time_to_first_action", "Time to first action (s)", "From the start of the negotiation to the first human action"),
    C("load_to_start_seconds", "Reading time (s)", "From loading the scenario to starting the negotiation"),
    C("questionnaire_seconds", "Questionnaire time (s)", "Time spent on the questionnaire"),
])
def timing(ctx: EvalContext, options: dict) -> dict:
    """Interaction time per decision and overall."""
    starts = ctx.turn_starts
    acts = [a for a in ctx.acts if a.get("actor") == "human" and a.get("type") in ("offer", "accept", "end", "text")]
    if not starts:
        # no browser: the turn starts when the previous action / the negotiation started
        prev = ctx.started_at or 0.0
        starts = []
        for a in acts:
            starts.append(prev)
            prev = a["t"]
    times = []
    for a in acts:
        before = [s for s in starts if s <= a["t"]]
        if before:
            times.append(a["t"] - before[-1])
    q = ctx.rec.questionnaire
    qs = None
    if q is not None:
        shown = None
        for t, _, st in ctx.rec.states():
            if st.get("phase") == "questionnaire":
                shown = t
                break
        qs = (q["t"] - shown) if shown is not None else None
    return dict(
        decision_time_mean=mean(times), decision_time_median=median(times),
        decision_time_min=min(times) if times else None,
        time_to_first_action=(acts[0]["t"] - ctx.started_at) if acts and ctx.started_at is not None else None,
        load_to_start_seconds=ctx.started_at, questionnaire_seconds=qs,
        _details=dict(decision_times=times),
    )


@metric("activity", kind="hard", title="Activity (mouse, keyboard, attention)", columns=[
    C("n_clicks", "Clicks", "Mouse / touch clicks"),
    C("n_keys", "Key presses", "Keys pressed"),
    C("mouse_distance", "Mouse distance (px)", "Distance travelled by the pointer"),
    C("n_scrolls", "Scrolls", "Scroll events"),
    C("idle_fraction", "Idle fraction", "Share of the negotiation without any input for more than 5 s"),
    C("hidden_seconds", "Away (s)", "Time the page was hidden (another tab or window)"),
    C("n_blur", "Focus lost", "Times the window lost focus"),
    C("has_telemetry", "Has telemetry", "1 if browser telemetry was recorded"),
])
def activity(ctx: EvalContext, options: dict) -> dict:
    """Low-level interaction: clicks, keys, pointer travel, idle time and attention."""
    tel = ctx.telemetry
    if not tel:
        return dict(has_telemetry=0)
    t0 = ctx.started_at or 0.0
    t1 = ctx.ended_at or ctx.rec.duration
    clicks = keys = scrolls = blur = 0
    dist = 0.0
    last = None
    inputs = []
    hidden, hidden_since = 0.0, None
    for t, typ, p in tel:
        if typ in ("mm", "pd", "pu", "click") and len(p) >= 2:
            try:
                xy = (float(p[0]), float(p[1]))
                if last is not None:
                    dist += math.dist(last, xy)
                last = xy
            except (TypeError, ValueError):
                pass
        if typ == "click":
            clicks += 1
        elif typ == "key":
            keys += 1
        elif typ == "scroll":
            scrolls += 1
        elif typ == "blur":
            blur += 1
        elif typ == "vis":
            if p and p[0] == "hidden" and hidden_since is None:
                hidden_since = t
            elif p and p[0] == "visible" and hidden_since is not None:
                hidden += t - hidden_since
                hidden_since = None
        if typ in ("mm", "pd", "click", "key", "scroll", "input") and t0 <= t <= t1:
            inputs.append(t)
    if hidden_since is not None:
        hidden += max(0.0, t1 - hidden_since)
    idle = 0.0
    pts = [t0] + inputs + [t1]
    for a, b in zip(pts, pts[1:]):
        if b - a > 5:
            idle += b - a
    span = max(1e-9, t1 - t0)
    return dict(n_clicks=clicks, n_keys=keys, mouse_distance=round(dist, 1), n_scrolls=scrolls,
                idle_fraction=min(1.0, idle / span), hidden_seconds=hidden, n_blur=blur, has_telemetry=1)


@metric("system_use", kind="hard", title="Use of the assistant and tools", columns=[
    C("n_user_messages", "Messages to assistant", "Chat messages the human sent to the assistant"),
    C("n_assistant_messages", "Assistant messages", "Messages the assistant posted"),
    C("n_suggestions", "Suggestions", "Offers the assistant filled in for the human"),
    C("suggestion_adoption", "Suggestion adoption", "Share of human offers sent exactly as the assistant suggested"),
    C("suggestions_ignored", "Suggestions ignored", "Suggestions followed by a different offer"),
    C("drafts_explored", "Offers explored", "Counter-offers the human tried in the editor before acting"),
    C("drafts_per_action", "Offers explored per action", "Mean explorations before each human action"),
    C("n_tool_interactions", "Tool interactions", "Inputs and actions in tools"),
    C("n_tools_used", "Tools used", "Distinct tools the human used"),
    C("n_tab_changes", "Tab changes", "Tool tabs opened"),
    C("actions_by_human", "Actions by human", "Share of the seat's actions taken by the human"),
    C("actions_by_agent", "Actions by assistant", "Share taken by the assistant"),
    C("actions_by_autopilot", "Actions by autopilot", "Share taken by the autopilot"),
])
def system_use(ctx: EvalContext, options: dict) -> dict:
    """Actual system use: messages, suggestions and how they were used, exploration and tools."""
    chat = ctx.chat
    user_msgs = [c for c in chat if ctx.is_human_chat(c)]
    agent_msgs = [c for c in chat if not ctx.is_human_chat(c)]
    names = ctx.scenario.get("issue_names") or []
    seat = [a for a in ctx.acts if a.get("type") in ("offer", "accept", "end", "text")]
    timeline = sorted([(d["t"], "d", d) for d in ctx.drafts] + [(a["t"], "a", a) for a in seat], key=lambda x: x[0])
    last_sugg = None
    adopted = ignored = after_sugg = 0
    explored, per_action, cur = 0, [], 0
    for _, kind, e in timeline:
        if kind == "d":
            if e.get("by") == "agent" and e.get("values"):
                last_sugg = [e["values"].get(n) for n in names]
            elif e.get("by") == "human" and e.get("values"):
                explored += 1
                cur += 1
            continue
        if e.get("actor") != "human":
            last_sugg = None
            continue
        per_action.append(cur)
        cur = 0
        if e.get("type") == "offer" and last_sugg is not None:
            after_sugg += 1
            if [str(v) for v in (e.get("offer") or [])] == [str(v) for v in last_sugg]:
                adopted += 1
            else:
                ignored += 1
            last_sugg = None
    evs = ctx.rec.of("ev")
    tool_ev = [e for e in evs if e.get("type") == "tool_interaction"]
    by = Counter(a.get("actor") for a in seat)
    n = len(seat)
    return dict(
        n_user_messages=len(user_msgs), n_assistant_messages=len(agent_msgs),
        n_suggestions=sum(1 for d in ctx.drafts if d.get("by") == "agent"),
        suggestion_adoption=adopted / after_sugg if after_sugg else None, suggestions_ignored=ignored,
        drafts_explored=explored, drafts_per_action=mean(per_action),
        n_tool_interactions=len(tool_ev), n_tools_used=len({e.get("component") for e in tool_ev}),
        n_tab_changes=sum(1 for e in evs if e.get("type") == "tab_changed"),
        actions_by_human=by["human"] / n if n else None, actions_by_agent=by["agent"] / n if n else None,
        actions_by_autopilot=by["autopilot"] / n if n else None,
    )


@metric("engagement_flags", kind="hard", title="Engagement flags", columns=[
    C("never_acted", "Never acted", "1 if the human never took an action themselves (filter out)", False),
    C("click_through", "Click-through", "1 if the human acted very fast without exploring offers (not invested)", False),
    C("always_follows", "Always follows assistant", "1 if every human offer was the assistant's suggestion (≥ 3 offers)", False),
    C("never_follows", "Never follows assistant", "1 if no suggestion was ever taken (≥ 3 suggestions)"),
])
def engagement_flags(ctx: EvalContext, options: dict) -> dict:
    """Flags for sessions to inspect or remove: never acted, clicking through,
    blindly following or always ignoring the assistant. Options:
    ``click_through_seconds`` (default 3)."""
    su = system_use(ctx, options)
    tm = timing(ctx, options)
    human = [a for a in ctx.acts if a.get("actor") == "human"]
    thr = float(options.get("click_through_seconds", 3.0))
    med = tm.get("decision_time_median")
    adoption = su.get("suggestion_adoption")
    n_h = sum(1 for a in human if a.get("type") == "offer")
    return dict(
        never_acted=int(not human),
        click_through=int(bool(human) and med is not None and med < thr and (su.get("drafts_explored") or 0) == 0),
        always_follows=int(adoption is not None and adoption >= 0.999 and n_h >= 3),
        never_follows=int((su.get("n_suggestions") or 0) >= 3 and (adoption or 0) == 0),
    )


# --------------------------------------------------------------------------- #
# The Assistant as a conversational helper                                     #
# --------------------------------------------------------------------------- #
@metric("assistant_interaction", kind="hard", title="Assistant interaction quality", columns=[
    C("assistant_response_seconds", "Response time (s)", "Mean time from a human message to the assistant's next message", False),
    C("unanswered_messages", "Unanswered messages", "Human messages the assistant never answered", False),
    C("unsolicited_messages", "Proactive messages", "Assistant messages not answering the human (> 30 s after their last message)"),
    C("max_assistant_streak", "Longest monologue", "Most assistant messages in a row without the human writing"),
    C("fn_calls", "Function calls", "Functions the assistant called"),
    C("fn_success_rate", "Function success", "Share of the assistant's function calls that succeeded", True),
])
def assistant_interaction(ctx: EvalContext, options: dict) -> dict:
    """Responsiveness, unanswered messages, proactivity, monologues and function-call success."""
    chat = ctx.chat
    resp, unanswered, unsolicited, streak, best = [], 0, 0, 0, 0
    last_user = None
    pending = None
    for c in chat:
        if ctx.is_human_chat(c):
            if pending is not None:
                unanswered += 1
            pending = c["t"]
            last_user = c["t"]
            streak = 0
        else:
            if pending is not None:
                resp.append(c["t"] - pending)
                pending = None
            elif last_user is None or c["t"] - last_user > 30:
                unsolicited += 1
            streak += 1
            best = max(best, streak)
    if pending is not None:
        unanswered += 1
    fns = ctx.fn_calls
    ok = [f for f in fns if isinstance(f.get("result"), dict) and f["result"].get("ok") is not False]
    return dict(
        assistant_response_seconds=mean(resp), unanswered_messages=unanswered, unsolicited_messages=unsolicited,
        max_assistant_streak=best, fn_calls=len(fns), fn_success_rate=(len(ok) / len(fns)) if fns else None,
        _details=dict(fn_by_name=dict(Counter(f.get("name") for f in fns))),
    )
