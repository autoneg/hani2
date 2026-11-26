"""What the human may choose for their next negotiation: the scenario, the opponent and the Assistant.

Every negotiation starts with the scenario, opponent and Assistant that HANI2 picks as always
(the scenario order, the opponent pool or the study's scheduling, the Assistant pool). When the
admin allows it, the human may then pick another one from the allowed set before starting.
A choice holds for one negotiation: the next one starts from HANI2's own pick again.

The policy is a mapping ``{"scenario": …, "opponent": …, "assistant": …}``; each value is

* ``false`` (or missing): the human may not choose (the default everywhere);
* ``true``: any member of the session's own pool (the scenario types of its scenario set, its
  opponent pool, its Assistant pool);
* a list: exactly these (scenario types; opponent specs or ``:group`` tokens; Assistant specs or
  ``:group`` tokens, ``none`` for no Assistant).

Where it is read:

* **Outside any project or study** (the playground, a signed-in user's own sessions): env.json
  ``playground.choices`` of the settings folder (and ``hani2 --settings``).
* **In a study**: the ``choices`` key of the study's own env.json, else of its project's own
  env.json, key by key. The settings folder's values never reach a project or study, and the
  default project has no layer of its own, so its studies only use their own folder.
* **Prolific studies never allow it** (whatever the settings say).

The old ``negotiation.allow_scenario_selection`` switch still allows choosing the scenario (any
type), as before. Admins keep their own pickers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hani2 import projects

if TYPE_CHECKING:  # pragma: no cover
    from hani2.session import NegotiationSession

KINDS = ("scenario", "opponent", "assistant")
#: the scheduling / source value recorded when the human chose
USER = "user"


def _norm(v: Any) -> bool | list[str]:
    if v is None or v is False:
        return False
    if v is True:
        return True
    if isinstance(v, str):
        if v.strip().lower() in ("", "false", "no", "off", "0"):
            return False
        if v.strip().lower() in ("true", "yes", "on", "1", "any", "all"):
            return True
        return [s.strip() for s in v.split(",") if s.strip()] or False
    if isinstance(v, (list, tuple)):
        return [str(s).strip() for s in v if str(s).strip()] or False
    return bool(v)


def is_prolific(session: "NegotiationSession") -> bool:
    """A Prolific participant or a session of a Prolific study."""
    if getattr(getattr(session, "study", None), "KIND", "") == "prolific":
        return True
    if str(getattr(session, "user", "")).startswith("prolific_"):
        return True
    ref = getattr(session, "study_ref", None)
    if ref is None:
        return False
    st = projects.get_study(ref)
    return st is None or st.type == "prolific"


def raw_policy(ref: "projects.StudyRef | None") -> dict[str, Any]:
    """The configured ``choices`` of a study (its own and its project's env.json), or of the
    playground (``ref`` is ``None``), before any Prolific or admin rule."""
    from hani2.config import get_env, read_json_own_file

    if ref is None:
        with projects.use_study(None):
            raw = get_env("playground.choices", {}) or {}
        return dict(raw) if isinstance(raw, dict) else {}
    out: dict[str, Any] = {}
    dirs = [projects.project_layer_dir(ref.project)]
    try:
        dirs.append(projects.study_dir(ref))
    except ValueError:
        pass
    for d in dirs:  # the project first, then the study (the more specific wins)
        if d is None:
            continue
        own = read_json_own_file(d / "env.json").get("choices")
        if isinstance(own, dict):
            out.update({k: v for k, v in own.items() if v is not None})
    return out


def configured_policy(session: "NegotiationSession") -> dict[str, bool | list[str]]:
    """The ``choices`` setting of this session (all ``False`` in a Prolific study), without the old switch."""
    if is_prolific(session):
        return {k: False for k in KINDS}
    raw = raw_policy(getattr(session, "study_ref", None))
    return {k: _norm(raw.get(k)) for k in KINDS}


def policy(session: "NegotiationSession") -> dict[str, bool | list[str]]:
    """What this session's human may choose (``False``, ``True`` = the pool, or the allowed list)."""
    out = configured_policy(session)
    # the old switch, as before: any type, on every layer (a Prolific or participant-link session's
    # schedule never took the pick, so it shows no picker there)
    if out["scenario"] is False and bool((getattr(session, "admin_prefs", None) or {}).get("allow_scenario_selection")) \
            and getattr(getattr(session, "study", None), "KIND", "") not in ("prolific", "participant"):
        out["scenario"] = True
    return out


def spec_key(spec: Any) -> str:
    """A pool member as a string (classes by their qualified name)."""
    if isinstance(spec, str):
        return spec
    mod, name = getattr(spec, "__module__", ""), getattr(spec, "__qualname__", None) or getattr(spec, "__name__", None)
    return f"{mod}.{name}" if name else str(spec)


def label(spec: Any) -> str:
    from hani2.agents import short_name
    from hani2.assignment import is_no_assistant

    if is_no_assistant(spec):
        return "No Assistant"
    return short_name(spec) or spec_key(spec)


def scenario_options(session: "NegotiationSession", allowed: bool | list[str]) -> list[str]:
    from hani2 import scenario_store as store

    if allowed is False:
        return []
    pool = list(store.scenario_order(session.admin_prefs.get("scenario_set")))
    if allowed is True:
        return pool
    known = set(store.available_types(session.admin_prefs.get("scenario_set")))
    return [t for t in allowed if t in known]


def opponent_options(session: "NegotiationSession", allowed: bool | list[str]) -> list:
    from hani2.agents import client_spec_allowed, expand_agents

    if allowed is False:
        return []
    with projects.use_study(session.study_ref):
        pool = list(session.opponent_pool()) if allowed is True else expand_agents(allowed)
    from hani2.matches import is_human

    out, seen = [], set()
    for p in pool:
        k = spec_key(p)
        # another participant (human / human+assistant) comes through pairing, not as a pick
        if k not in seen and client_spec_allowed(k) and not is_human(p):
            seen.add(k)
            out.append(p)
    return out


def assistant_options(session: "NegotiationSession", allowed: bool | list[str]) -> list[str]:
    from hani2 import assignment, groups

    if allowed is False or session.assistant_settings is None:
        return []
    from hani2.support_agent.settings import support_agent_enabled

    if not support_agent_enabled(session.assistant_settings, is_admin=session.is_admin):
        return []
    if allowed is True:
        with projects.use_study(session.study_ref):
            c = assignment.assistant_pool(session, session.assistant_settings, getattr(session, "round_plan", None))
        pool = list(c.pool)
    else:
        pool = groups.expand_assistants(allowed, session.study_ref)
        if any(assignment.is_no_assistant(a) for a in allowed) and not any(assignment.is_no_assistant(a) for a in pool):
            pool.append(assignment.NO_ASSISTANT)
    return list(dict.fromkeys(str(p) for p in pool))


def options(session: "NegotiationSession") -> dict[str, list]:
    """The allowed members of each kind (empty: the human may not choose it)."""
    pol = policy(session)
    return {"scenario": scenario_options(session, pol["scenario"]),
            "opponent": opponent_options(session, pol["opponent"]),
            "assistant": assistant_options(session, pol["assistant"])}


def client_state(session: "NegotiationSession") -> dict[str, Any] | None:
    """What the browser shows: the allowed options and the current pick of each kind (``None``
    when the human may choose nothing)."""
    try:
        opts = options(session)
    except Exception:  # noqa: BLE001 - a broken pool must not break the page
        import traceback

        traceback.print_exc()
        return None
    if not any(opts.values()):
        return None
    from hani2 import scenario_store as store

    c = session.__dict__.get("assistant_choice")
    names = {t: store.list_scenarios(t) for t in opts["scenario"]}
    chosen_opp = session.__dict__.get("chosen_opponent")
    return {
        "scenario": {"options": opts["scenario"], "names": names,
                     "current": session.ss.get("scenario_type")},
        "opponent": {"options": [{"value": spec_key(p), "label": label(p)} for p in opts["opponent"]],
                     "current": spec_key(chosen_opp) if chosen_opp is not None else None},
        "assistant": {"options": [{"value": a, "label": label(a)} for a in opts["assistant"]],
                      "current": (c.spec if c is not None else None),
                      "chosen": session.__dict__.get("chosen_assistant") is not None},
    }
