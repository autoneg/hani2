"""How two people are paired in a Paired study: match cells, the host's commit, the joiner's choice.

In a Paired study the fairness is decided when two people are paired, over **match cells**::

    cell = (scenario, Assistant at side 0, Assistant at side 1)   # "<scenario>|<A>@0|<B>@1"

*scenario* is the scenario type (``pairing.cell_scenario: type``, the default) or the scenario's
name (``name``). Sides are the ufun indices, so one match is one cell, the same in both rows.
The counts live in ``<study results>/match_cells.json`` (see :mod:`hani2.assignment`): only
completed matches fill a cell; matches being played count while a match is chosen (in flight).

The study's ``assistants`` scheduling method gives each person a **set** of remaining Assistants
(:func:`hani2.assignment.remaining_assistants`), with a preferred order. Then:

1. **The host commits.** Someone who finds nobody to join waits as a host, with **one** Assistant
   of their set and a scenario type chosen now: the pair with the fewest completed + in-flight
   matches that have this Assistant in this scenario type, then the fewest uses of the Assistant at
   the person's position, then the preferred order, then the scenario method's own pick.
   ``scenarios: by_participant`` keeps the person's own type.
2. **The joiner chooses, and binds late.** A joiner looks at every waiting host that fits, and at
   every Assistant ``a`` of its set (not the host's, unless ``pairing.allow_same_assistant``). It
   scores each (host, ``a``) by ``(cell count, a's count at the joiner's position, host's set size,
   joiner's set size, chance)`` and takes the lowest; cell counts within ``pairing.slack`` of the
   lowest are tied. Only then is the joiner's Assistant built. With ``scenarios: by_participant``
   a joiner fits only hosts of its own scenario type.
3. The chosen cell is put in flight under the lobby's lock (two joiners never choose at the same
   moment), and filled when both rows are written clean (:func:`hani2.assignment.cell_row_written`).

``pairing.assign: order`` takes each person's next planned Assistant only; ``random`` keeps the
random choice among the people who fit (with the same-Assistant filter of a Paired study).

This applies to studies declared ``study_mode: paired`` and to any study whose ``pairing`` block
sets ``assign: cells`` or ``order`` explicitly (for example a Mixed game). Other studies and
sessions outside a study pair as before.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

from hani2 import assignment

if TYPE_CHECKING:  # pragma: no cover
    from hani2.matches import Match
    from hani2.session import NegotiationSession


def settings(session: Any) -> dict[str, Any] | None:
    """The effective ``pairing`` settings when the cell-aware pairing applies to ``session``
    (``None``: it pairs as before). ``declared`` is whether the study is declared ``paired``."""
    info = getattr(session, "study_mode_info", None)
    if getattr(session, "study_ref", None) is None or info is None:
        return None
    from hani2.study_modes import PAIRED

    declared = bool(info.explicit and info.mode == PAIRED)
    eff = info.pairing_effective
    if not declared and info.pairing.get("assign") not in ("cells", "order"):
        return None
    return {**eff, "declared": declared}


def fallback(session: Any) -> str | None:
    """``pairing.fallback`` (``ai``, ``wait``, ``end``) when the study declares it or is declared
    Paired; ``None``: the settings of before (``human_opponent_fallback``)."""
    info = getattr(session, "study_mode_info", None)
    if getattr(session, "study_ref", None) is None or info is None:
        return None
    from hani2.study_modes import PAIRED

    if "fallback" in info.pairing or (info.explicit and info.mode == PAIRED):
        return str(info.pairing_effective.get("fallback") or "ai")
    return None


def fallback_partner(session: Any) -> Any:
    """The AI opponent of the fallback: from ``pairing.fallback_opponents`` when set, else from the
    study's non-human pool, else (a Paired study has none) from ``:pan``; outside a Paired study
    without ``fallback_opponents``, the built-in default pool as before."""
    from hani2 import matches
    from hani2.agents import expand_agents
    from hani2.study_modes import PAIRED

    info = getattr(session, "study_mode_info", None)
    named = (info.pairing.get("fallback_opponents") if info is not None else None) or None
    if named:
        pool = expand_agents(list(named))
        if pool:
            return random.choice(pool)
    default = None
    if info is not None and info.explicit and info.mode == PAIRED:
        default = expand_agents([":pan"]) or None
    return matches.fallback_opponent(session.opponent_pool(), default)


def _study_pool_size(ref: Any) -> int:
    from hani2 import groups, projects

    raw = projects.setting("assistants", None, ref=ref)
    if raw is None:
        return 1
    try:
        with projects.use_study(ref):
            return len(groups.expand_assistants(raw, ref))
    except Exception:  # noqa: BLE001
        return 1


def context(session: "NegotiationSession", plan: dict, scenario_type: str | None, eff: dict[str, Any]) -> dict[str, Any]:
    """What the pairing knows about this side for the coming match (kept on the session as
    ``_pair_ctx`` and on the match per seat). ``remaining`` is filled here for a late-binding side
    (an HI Paired study), else by the caller after the Assistant is built."""
    from hani2 import matches
    from hani2.support_agent.settings import support_agent_enabled

    ref = session.study_ref
    sched = str(plan.get("scenario_scheduling") or "")
    by_type = sched.startswith("by_participant")
    ctx: dict[str, Any] = {
        "assign": str(eff.get("assign") or "random"),
        "slack": int(eff.get("slack") or 0),
        "cell_scenario": str(eff.get("cell_scenario") or "type"),
        "same_ok": bool(eff.get("allow_same_assistant")) or _study_pool_size(ref) < 2,
        "declared": bool(eff.get("declared")),
        "ref": ref,
        "counted": assignment.counts_as_human(session),
        "scenario_type": scenario_type or "",
        "own_type": scenario_type or "",
        "by_type": by_type,
        # the scenario type is not the host's to choose: the person's own type, their own pick, a
        # named scenario, or an outside schedule
        "fixed_type": bool(by_type or plan.get("name") or sched in ("user", "external", "practice")
                           or plan.get("practice")),
        "code": matches.match_key(session).startswith("code:"),
        "assistant": None,
        "remaining": [],
        "method": "",
        "position": len(assignment.used_assistants(session)),
        "time_limit": session.admin_prefs.get("time_limit"),
        "late": False,
    }
    st = session.assistant_settings
    enabled = st is not None and (support_agent_enabled(st, is_admin=session.is_admin)
                                  or bool(assignment.group_assistant(session)))
    if ctx["declared"] and enabled:
        try:
            rest, method = assignment.remaining_assistants(session, st, plan)
        except Exception:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            rest, method = [], ""
        ctx["method"] = method
        if not rest or not assignment.is_no_assistant(rest[0]):
            ctx["remaining"] = rest
            ctx["late"] = True
    return ctx


def _host_assistant(m: "Match", hctx: dict) -> str:
    a = hctx.get("assistant")
    if a:
        return str(a)
    c = getattr(m.host, "assistant_choice", None)
    sa = getattr(m.host, "__dict__", {}).get("support_agent")
    return str(getattr(c, "spec", "") or "") if sa is not None else assignment.NO_ASSISTANT


def _same(a: str, b: str) -> bool:
    return bool(a) and a == b and not assignment.is_no_assistant(a)


def selector(ctx: dict[str, Any], rng: random.Random | None = None):
    """The ``select`` of :meth:`hani2.matches.Lobby.pair` for a joiner with pairing context ``ctx``:
    the best (host, Assistant) by the rule in the module docs; puts the cell in flight."""
    rng = rng or random.Random()

    def select(fits: list["Match"]) -> "Match | None":
        stores: dict[str, dict | None] = {}

        def store(ref: Any) -> dict | None:
            if ref is None:
                return None
            k = str(ref)
            if k not in stores:
                try:
                    stores[k] = assignment.read_cells(ref)
                except Exception:  # noqa: BLE001
                    stores[k] = None
            return stores[k]

        mine_all = list(ctx.get("remaining") or [])
        mine = mine_all[:1] if ctx.get("assign") == "order" else mine_all
        cands: list[tuple] = []
        for m in fits:
            hi = m.host_index()
            hctx = m.ctx.get(hi) or {}
            if ctx.get("by_type") and ctx.get("own_type") and m.scenario_type and m.scenario_type != ctx["own_type"]:
                continue  # by_participant: only hosts of the joiner's own scenario type
            ha = _host_assistant(m, hctx)
            ji = m.free_index()
            same_ok = ctx.get("same_ok", True) and hctx.get("same_ok", True)
            for a in mine:
                if not same_ok and _same(a, ha):
                    continue
                sides = {hi: ha, ji: a}
                key = assignment.cell_key(hctx.get("scenario") or m.scenario_type, sides[0], sides[1])
                ref = hctx.get("ref") if hctx.get("ref") is not None else ctx.get("ref")
                d = store(ref)
                c = assignment.cell_count(d, key) if d else 0
                pos = assignment.position_count(d, a, int(ctx.get("position") or 0)) if d else 0
                cands.append((c, pos, len(hctx.get("remaining") or [ha]), len(mine_all), m, a, key, ref, hi, ha, hctx))
        if not cands:
            return None
        if ctx.get("assign") == "random":
            best = rng.choice(cands)
        else:
            low, slack = min(x[0] for x in cands), int(ctx.get("slack") or 0)
            ranked = [((low if x[0] <= low + slack else x[0]), x[1], x[2], x[3], rng.random(), i)
                      for i, x in enumerate(cands)]
            best = cands[min(ranked)[-1]]
        _c, _p, _rh, _rj, m, a, key, ref, hi, ha, hctx = best
        ji = m.free_index()
        m.ctx[ji] = {**ctx, "assistant": a}
        m.pairing = "code" if ctx.get("code") else str(ctx.get("assign") or "")
        m.cell = key
        m.cell_ref = None
        if ref is not None and ctx.get("counted") and hctx.get("counted"):
            try:
                with assignment.cell_store(ref) as d:
                    assignment.reserve_cell(d, m.id, key, scenario_type=m.scenario_type,
                                            sides={hi: (ha, hctx.get("position")), ji: (a, ctx.get("position"))},
                                            ttl=_ttl(ctx.get("time_limit")))
                m.cell_ref = ref
            except Exception:  # noqa: BLE001
                import traceback

                traceback.print_exc()
        return m

    return select


def _ttl(limit: Any) -> float | None:
    try:
        v = float(limit)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def commit(ctx: dict[str, Any], types: list[str], pick: str, rng: random.Random | None = None) -> tuple[str | None, str]:
    """The host's ``(Assistant, scenario type)``: the pair with the fewest completed + in-flight
    matches of that type with that Assistant, then its count at the host's position, then the
    preferred order, then the scenario method's own ``pick`` (see the module docs)."""
    rng = rng or random.Random()
    mine = list(ctx.get("remaining") or [])
    if ctx.get("assign") == "order":
        mine = mine[:1]
    if not mine:
        mine = [ctx.get("assistant") or ""]
    types = [t for t in dict.fromkeys(types) if t] or [pick]
    ref = ctx.get("ref")
    try:
        d = assignment.read_cells(ref) if ref is not None else None
    except Exception:  # noqa: BLE001
        d = None
    k = int(ctx.get("position") or 0)
    best = None
    for i, h in enumerate(mine):
        for t in types:
            score = (assignment.assistant_scenario_count(d, h, t) if d and h else 0,
                     assignment.position_count(d, h, k) if d and h else 0,
                     i, t != pick, rng.random())
            if best is None or score < best[0]:
                best = (score, h, t)
    assert best is not None
    return (best[1] or None), best[2]
