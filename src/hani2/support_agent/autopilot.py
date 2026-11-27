"""Autopilot: let an agent make *all* of the human's negotiation decisions.

The *driver* is either ``"Assistant"`` (the Assistant decides each
turn, with forced tool calls and a stall safety net) or any negotiator (it
plays the human's seat directly, with the human's preferences). Configured in
``settings/autopilot_settings.json``:

* ``allowed`` — admin master switch;
* ``driver`` — the admin-fixed default driver;
* ``allowed_drivers`` — drivers offered in the selector (``null`` = all);
* ``step_delay`` — seconds between autopilot steps;
* ``user_can_choose`` — whether non-admins may pick the driver
  (``null`` = only in the guest playground).

The old driver name ``"Support Agent"`` is still accepted wherever a driver
is read (settings, the participant's choice) and means ``"Assistant"``.
"""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING, Any

from hani2.config import load_json_settings, save_json_settings

if TYPE_CHECKING:  # pragma: no cover
    from hani2.session import NegotiationSession

ASSISTANT_DRIVER = "Assistant"
#: old name of the Assistant driver, still accepted
OLD_ASSISTANT_DRIVERS = ("Support Agent",)
SUPPORT_AGENT_DRIVER = ASSISTANT_DRIVER  # old name of the constant


def normalize_driver(driver: Any) -> Any:
    """Map an old driver name (``"Support Agent"``) to its current one."""
    return ASSISTANT_DRIVER if isinstance(driver, str) and driver in OLD_ASSISTANT_DRIVERS else driver
AUTOPILOT_NEGOTIATORS: list[str] = [
    "AspirationNegotiator",
    "NaiveTitForTatNegotiator",
    "BoulwareTBNegotiator",
    "ConcederTBNegotiator",
    "LinearTBNegotiator",
]
FILENAME = "autopilot_settings.json"
DEFAULT_AUTOPILOT_SETTINGS: dict[str, Any] = {
    "allowed": False,
    "driver": ASSISTANT_DRIVER,
    "allowed_drivers": None,
    "step_delay": 0.5,
    "user_can_choose": None,
}


def all_autopilot_negotiators() -> list[str]:
    from hani2.agents import LLM_NEGOTIATORS, TEMPLATE_BASED_NEGOTIATORS

    names = list(AUTOPILOT_NEGOTIATORS)
    for extra in list(TEMPLATE_BASED_NEGOTIATORS) + list(LLM_NEGOTIATORS):
        if extra not in names:
            names.append(extra)
    return names


def load_autopilot_settings() -> dict:
    s = load_json_settings(FILENAME, DEFAULT_AUTOPILOT_SETTINGS)
    s["driver"] = normalize_driver(s.get("driver"))
    if isinstance(s.get("allowed_drivers"), list):
        s["allowed_drivers"] = list(dict.fromkeys(normalize_driver(d) for d in s["allowed_drivers"]))
    return s


def save_autopilot_settings(settings: dict) -> None:
    save_json_settings(FILENAME, settings)


def autopilot_allowed(settings: dict | None = None) -> bool:
    return bool((settings or load_autopilot_settings()).get("allowed"))


def user_can_select_driver(session: "NegotiationSession", settings: dict | None = None) -> bool:
    if session.is_admin:
        return True
    s = settings or load_autopilot_settings()
    if s.get("user_can_choose") is not None:
        return bool(s["user_can_choose"])
    return session.mode == "guest" and not session.user.startswith("prolific_")


def driver_options(settings: dict | None = None, session: "NegotiationSession | None" = None) -> list[str]:
    """The drivers on offer; without the Assistant in ``session`` the
    Assistant driver is left out."""
    s = settings or load_autopilot_settings()
    opts = [ASSISTANT_DRIVER] + all_autopilot_negotiators()
    if session is not None and session.support_agent is None:
        opts = opts[1:]
    allowed = s.get("allowed_drivers")
    if allowed:
        allowed = {normalize_driver(d) for d in allowed}
        opts = [o for o in opts if o in allowed]
    return opts


def resolve_driver(session: "NegotiationSession", settings: dict | None = None) -> str | None:
    s = settings or load_autopilot_settings()
    opts = driver_options(s, session)
    chosen = normalize_driver(session.autopilot_driver_name)
    if user_can_select_driver(session, s) and chosen in opts:
        return chosen
    driver = normalize_driver(s.get("driver")) or None
    if driver and driver not in opts:
        return opts[0] if opts else None
    return driver


def is_negotiator_driver(driver: str | None) -> bool:
    return bool(driver) and normalize_driver(driver) != ASSISTANT_DRIVER


def make_negotiator_driver(session: "NegotiationSession"):
    """The negotiator that plays the human seat under negotiator-driven autopilot
    (``None`` for the Assistant driver or when autopilot is unavailable)."""
    s = load_autopilot_settings()
    if not autopilot_allowed(s):
        return None
    driver = resolve_driver(session, s)
    if not is_negotiator_driver(driver):
        return None
    try:
        from hani2.agents import make_agent

        sa = getattr(session, "support_agent", None)
        seq = sa._sequence() if sa is not None and hasattr(sa, "_sequence") else ""  # the Assistant's chosen sequence
        agent = make_agent(driver, {"name": "Autopilot"}, models=getattr(session, "models", None), purpose="assistant",
                           sequence=seq)
        # make_agent wraps the class to refuse accepting a None offer; that is
        # what we want for the human seat too.
        return agent
    except Exception as e:  # noqa: BLE001
        print(f"[autopilot] could not build driver {driver!r}: {e}")
        return None


def client_state(session: "NegotiationSession") -> dict[str, Any]:
    s = load_autopilot_settings()
    allowed = autopilot_allowed(s)
    driver = resolve_driver(session, s)
    sa_ok = session.support_agent is not None
    available = allowed and bool(driver) and (is_negotiator_driver(driver) or sa_ok)
    return {
        "allowed": allowed,
        "available": available,
        "active": session.autopilot_active,
        "driver": driver,
        "drivers": driver_options(s, session) if user_can_select_driver(session, s) else None,
        "can_choose": user_can_select_driver(session, s),
    }


def set_autopilot(session: "NegotiationSession", active: bool, driver: str | None = None) -> dict:
    s = load_autopilot_settings()
    driver = normalize_driver(driver)
    if driver and user_can_select_driver(session, s) and driver in driver_options(s, session):
        session.autopilot_driver_name = driver
        if session.mechanism is not None and is_negotiator_driver(driver):
            # rebuild the seat's driver so a mid-round switch takes effect
            try:
                human = session.mechanism.negotiators[session.human_index]
                new = make_negotiator_driver(session)
                if new is not None:
                    new.join(human.nmi, human._nmi.state if hasattr(human, "_nmi") else None,  # type: ignore
                             preferences=human.preferences, ufun=human.ufun, role=human.role if hasattr(human, "role") else None)
                human._driver = new
                session.ss["autopilot_driver"] = new
            except Exception:
                traceback.print_exc()
    if active:
        if not autopilot_allowed(s):
            return {"ok": False, "error": "Autopilot is not allowed on this server."}
        drv = resolve_driver(session, s)
        if not drv:
            return {"ok": False, "error": "No autopilot driver is configured."}
        if not is_negotiator_driver(drv) and session.support_agent is None:
            return {"ok": False, "error": "The Assistant is not available in this session."}
        if is_negotiator_driver(drv) and session.mechanism is not None:
            human = session.mechanism.negotiators[session.human_index]
            if getattr(human, "_driver", None) is None:
                return {"ok": False, "error": "Autopilot will be available from the next negotiation."}
    session.autopilot_active = bool(active)
    if active:
        session.ss["autopilot_used"] = True
    sa = session.support_agent
    drv = resolve_driver(session, s)
    rec = getattr(session, "recorder", None)
    if rec is not None:
        try:
            # who drove the human's seat (the ablation report needs the driver, not just "autopilot")
            rec.event("autopilot", active=bool(active), driver=drv or "")
        except Exception:  # noqa: BLE001
            traceback.print_exc()
    if sa is not None:
        sa.set_autopilot(bool(active) and not is_negotiator_driver(drv))
    session.push_state()
    if active and session.is_my_turn():
        # kick the first autopilot decision
        if is_negotiator_driver(drv):
            from negmas import ResponseType, SAOResponse

            session.act(SAOResponse(ResponseType.REJECT_OFFER, None))
        elif sa is not None:
            from hani2.recording.recorder import acting

            with acting("autopilot"):
                session.submit(sa.autopilot_step, 0.0)
    return {"ok": True, "active": session.autopilot_active}
